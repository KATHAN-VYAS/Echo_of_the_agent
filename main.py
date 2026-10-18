import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_files(workspace: Path) -> list[dict]:
    files = []

    for path in sorted(workspace.rglob("*")):
        if ".git" in path.relative_to(workspace).parts:
            continue
        if not path.is_file() or path.is_symlink():
            continue

        files.append({
            "path": path.relative_to(workspace).as_posix(),
            "size": path.stat().st_size,
            "sha256": file_sha256(path),
        })

    return files


def write_json(path: Path, data: dict) -> None:
    # "x" refuses to overwrite an existing file.
    with path.open("x", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    workspace = args.workspace.resolve(strict=True)
    output = args.output.resolve()

    if not workspace.is_dir():
        parser.error("workspace must be a directory")
    if output == workspace or output.is_relative_to(workspace):
        parser.error("output must be outside the agent workspace")

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    # Record the existing files before the agent starts working.
    baseline_files = collect_files(workspace)

    output.mkdir(parents=True, exist_ok=True)

    write_json(output / "run.json", {
        "run_id": run_id,
        "task_id": args.task_id,
        "workspace": str(workspace),
        "started_at": started_at,
    })
    write_json(output / "baseline.json", {
        "run_id": run_id,
        "collected_at": started_at,
        "files": baseline_files,
    })

    print(f"Recorded {len(baseline_files)} existing files for run {run_id}")


if __name__ == "__main__":
    main()