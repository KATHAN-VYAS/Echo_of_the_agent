import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from agentprov import Client


FILTERED_EVENT_TYPES = (
    "execve",
    "dns_query",
    "network_connect",
    "tls_write",
    "file_open",
    "file_write",
    "file_rename",
)


def run_json(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("AgentProvenance returned a non-object JSON value")
    return value


def keep_file_event(
    event: dict[str, Any],
    workspace: Path | None,
    cargo_home: Path | None,
) -> bool:
    """Keep task source files and package-manager cache evidence, not build noise."""
    payload = event.get("payload", "")
    if not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False)
    if "/.cargo/registry/cache/" in payload or "/.cargo/registry/src/" in payload:
        return True
    if cargo_home is not None:
        cargo_registry = str(cargo_home.resolve() / "registry")
        if (
            f"{cargo_registry}/cache/" in payload
            or f"{cargo_registry}/src/" in payload
        ):
            return True
    if workspace is None:
        return False
    workspace_text = str(workspace.resolve())
    if workspace_text not in payload:
        return False
    noisy_fragments = (
        f"{workspace_text}/.git/",
        f"{workspace_text}/./.git/",
        f"{workspace_text}/target/",
        f"{workspace_text}/./target/",
    )
    return not any(fragment in payload for fragment in noisy_fragments)


def cargo_lock_packages(workspace: Path | None) -> list[dict[str, Any]]:
    if workspace is None:
        return []
    lock_path = workspace / "Cargo.lock"
    if not lock_path.is_file():
        return []
    document = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = document.get("package", [])
    if not isinstance(packages, list):
        return []
    return [package for package in packages if isinstance(package, dict)]


def filtered_context(
    agentprov_bin: str,
    data_dir: str,
    run_id: str,
    workspace: Path | None,
    cargo_home: Path | None,
) -> dict[str, Any]:
    """Page through high-value telemetry without constructing signal context."""
    events: list[dict[str, Any]] = []
    base = [agentprov_bin, "--data-dir", data_dir, "telemetry", "list"]

    for event_type in FILTERED_EVENT_TYPES:
        cursor = ""
        while True:
            command = base + [
                "--run",
                run_id,
                "--type",
                event_type,
                "--limit",
                "100",
                "--json",
            ]
            if cursor:
                command.extend(["--cursor", cursor])
            page = run_json(command)
            page_events = page.get("events") or []
            if not isinstance(page_events, list):
                raise ValueError("AgentProvenance telemetry page has no event list")
            for event in page_events:
                if not isinstance(event, dict):
                    continue
                if event_type.startswith("file_") and not keep_file_event(
                    event, workspace, cargo_home
                ):
                    continue
                events.append(event)
            if not page.get("has_more"):
                break
            cursor = page.get("next_cursor", "")
            if not isinstance(cursor, str) or not cursor:
                raise ValueError("Telemetry pagination stopped without a cursor")

    return {
        "run_id": run_id,
        "runtime_events": events,
        "file_changes": [],
        "cargo_lock_packages": cargo_lock_packages(workspace),
        "export": {
            "mode": "filtered_paginated",
            "event_types": list(FILTERED_EVENT_TYPES),
            "workspace": str(workspace.resolve()) if workspace else None,
            "cargo_home": str(cargo_home.resolve()) if cargo_home else None,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export one AgentProvenance run as JSON."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--agentprov-bin", required=True)
    parser.add_argument(
        "--mode",
        choices=("full", "filtered"),
        default="full",
        help="full uses signal context; filtered pages high-value telemetry",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="retain file evidence only for this workspace and Cargo caches",
    )
    parser.add_argument(
        "--cargo-home",
        type=Path,
        help="retain registry evidence from an isolated Cargo home",
    )
    args = parser.parse_args()

    if args.mode == "filtered":
        payload = filtered_context(
            args.agentprov_bin,
            args.data_dir,
            args.run_id,
            args.workspace,
            args.cargo_home,
        )
    else:
        client = Client(
            binary=args.agentprov_bin,
            data_dir=Path(args.data_dir),
        )
        context = client.eval_context(args.run_id)
        payload = context.raw if hasattr(context, "raw") else context

    json.dump(
        payload,
        sys.stdout,
        indent=2,
        ensure_ascii=False,
    )
    print()


if __name__ == "__main__":
    main()
