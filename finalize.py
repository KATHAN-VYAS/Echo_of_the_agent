import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from main import collect_files, write_json


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def compare_files(before: list[dict], after: list[dict]) -> dict:
    old = {item["path"]: item for item in before}
    new = {item["path"]: item for item in after}

    old_paths = set(old)
    new_paths = set(new)

    return {
        "added": sorted(new_paths - old_paths),
        "removed": sorted(old_paths - new_paths),
        "modified": sorted(
            path
            for path in old_paths & new_paths
            if old[path]["sha256"] != new[path]["sha256"]
        ),
        "unchanged": sorted(
            path
            for path in old_paths & new_paths
            if old[path]["sha256"] == new[path]["sha256"]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory containing run.json and baseline.json",
    )
    args = parser.parse_args()

    output = args.output.resolve()
    run = read_json(output / "run.json")
    baseline = read_json(output / "baseline.json")

    if run["run_id"] != baseline["run_id"]:
        parser.error("run.json and baseline.json belong to different runs")

    workspace = Path(run["workspace"]).resolve(strict=True)
    current_files = collect_files(workspace)

    final = {
        "run_id": run["run_id"],
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "files": current_files,
    }
    changes = {
        "run_id": run["run_id"],
        "files": compare_files(baseline["files"], current_files),
    }

    write_json(output / "final.json", final)
    write_json(output / "file_changes.json", changes)

    print(
        f"Added: {len(changes['files']['added'])}, "
        f"modified: {len(changes['files']['modified'])}, "
        f"removed: {len(changes['files']['removed'])}"
    )


if __name__ == "__main__":
    main()