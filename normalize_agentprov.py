import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "echo.normalized_event/v1"


def decode_json_strings(value: Any, max_depth: int = 5) -> Any:
    """Decode JSON strings nested inside other JSON values."""
    for _ in range(max_depth):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            break
    return value


def unpack_payload(event: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the observed attributes and correlation evidence for one event."""
    outer = decode_json_strings(event.get("payload", {}))
    if not isinstance(outer, dict):
        return {}, {}

    inner = decode_json_strings(outer.get("payload", {}))
    if not isinstance(inner, dict):
        return {}, {}

    attributes = decode_json_strings(inner.get("raw", {}))
    correlation = decode_json_strings(inner.get("correlation", {}))

    if not isinstance(attributes, dict):
        attributes = {"raw_value": attributes}
    if not isinstance(correlation, dict):
        correlation = {"raw_value": correlation}

    return attributes, correlation


def normalize_runtime_event(
    run_id: str, event: dict[str, Any]
) -> dict[str, Any]:
    outer = decode_json_strings(event.get("payload", {}))
    if not isinstance(outer, dict):
        outer = {}

    attributes, correlation = unpack_payload(event)

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event.get("id"),
        "run_id": run_id,
        "source": event.get("source"),
        "event_type": event.get("event_type"),
        "process_id": event.get("process_id"),
        "snapshot_id": event.get("snapshot_id"),
        "rollout_id": outer.get("rollout_id"),
        "attempt_id": outer.get("attempt_id"),
        "correlation": {
            "method": correlation.get(
                "method", event.get("correlation_method")
            ),
            "confidence": correlation.get(
                "confidence", event.get("correlation_confidence")
            ),
            "binding_id": correlation.get("binding_id"),
        },
        "attributes": attributes,
    }

    return {key: value for key, value in normalized.items() if value is not None}


def normalize_file_change(
    run_id: str, index: int, change: dict[str, Any]
) -> dict[str, Any]:
    # TODO: Return the normalized file-change event. This function currently
    # returns None because its return block was displaced below
    # normalize_cargo_lock_package(). Fix this together with a regression test.
    # The full unified diff may contain source code or secrets. Keep only the
    # evidence metadata in the normalized event; the original context remains
    # available separately when detailed inspection is authorized.
    attributes = {
        key: value
        for key, value in change.items()
        if key != "unified_diff"
    }


def normalize_cargo_lock_package(
    run_id: str, index: int, package: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"cargo-lock-{index}",
        "run_id": run_id,
        "source": "cargo_lock",
        "event_type": "package_lock_entry",
        "correlation": {
            "method": "final_workspace_manifest",
            "confidence": 1.0,
        },
        "attributes": {
            key: package.get(key)
            for key in ("name", "version", "source", "checksum", "dependencies")
            if package.get(key) is not None
        },
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"file-change-{index}",
        "run_id": run_id,
        "source": "record_file_diff",
        "event_type": "file_change",
        "attributes": attributes,
    }


def normalize_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = context.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("The input context does not contain a valid run_id")

    events = context.get("runtime_events", [])
    changes = context.get("file_changes", [])
    cargo_packages = context.get("cargo_lock_packages", [])
    if not all(
        isinstance(value, list)
        for value in (events, changes, cargo_packages)
    ):
        raise ValueError(
            "runtime_events, file_changes, and cargo_lock_packages must be lists"
        )

    normalized = [
        normalize_runtime_event(run_id, event)
        for event in events
        if isinstance(event, dict)
    ]
    normalized.extend(
        normalize_file_change(run_id, index, change)
        for index, change in enumerate(changes, start=1)
        if isinstance(change, dict)
    )
    normalized.extend(
        normalize_cargo_lock_package(run_id, index, package)
        for index, package in enumerate(cargo_packages, start=1)
        if isinstance(package, dict)
    )
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize an AgentProvenance evaluation context to JSONL."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    context = json.loads(args.input.read_text(encoding="utf-8"))
    normalized = normalize_context(context)

    with args.output.open("w", encoding="utf-8") as output_file:
        for event in normalized:
            output_file.write(json.dumps(event, ensure_ascii=False) + "\n")

    counts = Counter(event.get("event_type") for event in normalized)
    print(f"Normalized {len(normalized)} events into {args.output}")
    for event_type, count in sorted(counts.items()):
        print(f"  {event_type}: {count}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
