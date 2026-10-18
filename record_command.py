import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from finalize import compare_files
from main import collect_files


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record))
        file.write("\n")


def write_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as file:
        file.write(data)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Evidence directory containing run.json",
    )

    parser.add_argument(
        "--cwd",
        type=Path,
        required=True,
        help="Directory where the command will run",
    )

    parser.add_argument(
        "--phase",
        choices=[
            "setup",
            "manual_test",
            "agent",
            "verification",
            "collection",
        ],
        default="manual_test",
        help="Phase in which the command is executed",
    )

    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to execute after --",
    )

    args = parser.parse_args()

    output = args.output.resolve(strict=True)
    cwd = args.cwd.resolve(strict=True)

    run = read_json(output / "run.json")
    workspace = Path(run["workspace"]).resolve(strict=True)

    if cwd != workspace and not cwd.is_relative_to(workspace):
        parser.error("cwd must be inside the recorded workspace")

    command = args.command

    if command and command[0] == "--":
        command = command[1:]

    if not command:
        parser.error("a command is required after --")

    before_files = collect_files(workspace)

    event_id = str(uuid.uuid4())
    started_at = utc_now()
    start_clock = time.monotonic()

    launch_error = None

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
        )

        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr

    except OSError as error:
        exit_code = None
        stdout = b""
        stderr = str(error).encode("utf-8")
        launch_error = str(error)

    ended_at = utc_now()
    duration_ms = round(
        (time.monotonic() - start_clock) * 1000,
        3,
    )

    after_files = collect_files(workspace)
    observed_file_changes = compare_files(
        before_files,
        after_files,
    )

    raw_directory = output / "raw"
    raw_directory.mkdir(exist_ok=True)

    stdout_name = f"{event_id}.stdout"
    stderr_name = f"{event_id}.stderr"

    write_bytes(raw_directory / stdout_name, stdout)
    write_bytes(raw_directory / stderr_name, stderr)

    if exit_code == 0:
        outcome = "success"
    elif exit_code is None:
        outcome = "launch_error"
    else:
        outcome = "failure"

    event = {
        "schema_version": 1,
        "event_id": event_id,
        "run_id": run["run_id"],
        "source": "command_wrapper",
        "event_type": "command_execution",
        "phase": args.phase,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "cwd": str(cwd),
        "command": command,
        "outcome": outcome,
        "exit_code": exit_code,
        "launch_error": launch_error,
        "observed_file_changes": observed_file_changes,
        "file_change_basis": "before_after_workspace_snapshot",
        "stdout": {
            "path": f"raw/{stdout_name}",
            "size": len(stdout),
            "sha256": sha256_bytes(stdout),
        },
        "stderr": {
            "path": f"raw/{stderr_name}",
            "size": len(stderr),
            "sha256": sha256_bytes(stderr),
        },
    }

    append_jsonl(output / "events.jsonl", event)

    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)

    if exit_code is None:
        raise SystemExit(127)

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
