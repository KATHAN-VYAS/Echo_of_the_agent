"""Upload an existing CycloneDX BOM to an isolated Dependency-Track instance.

This experiment adapter is intentionally independent from Echo of the Agent's
production pipeline. It reads a BOM, submits it to Dependency-Track, and writes
only derived result files beneath the selected output directory.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def api_request(
    base_url: str,
    api_key: str,
    path: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[Any, dict[str, str]]:
    headers = {"Accept": "application/json", "X-Api-Key": api_key}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
            response_headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dependency-Track returned HTTP {error.code}: {detail}") from error

    if not raw:
        return None, response_headers
    return json.loads(raw), response_headers


def multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----echo-dtrack-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    mime = mimetypes.guess_type(file_path.name)[0] or "application/json"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def paged_get(
    base_url: str,
    api_key: str,
    path: str,
    *,
    page_size: int = 500,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        separator = "&" if "?" in path else "?"
        payload, headers = api_request(
            base_url,
            api_key,
            f"{path}{separator}pageNumber={page}&pageSize={page_size}",
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"Expected a list from {path}, got {type(payload).__name__}")
        items.extend(payload)
        total = int(headers.get("x-total-count", len(items)))
        if len(items) >= total or not payload:
            return items
        page += 1


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--api-key-file", required=True, type=Path)
    parser.add_argument("--bom", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--project-name", default="Echo of the Agent V3")
    parser.add_argument("--project-version", default="v3-dtrack-experiment")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    api_key = args.api_key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        raise ValueError("API key file is empty")
    args.output.mkdir(parents=True, exist_ok=True)

    body, content_type = multipart_body(
        {
            "autoCreate": "true",
            "projectName": args.project_name,
            "projectVersion": args.project_version,
        },
        "bom",
        args.bom,
    )
    upload, _ = api_request(
        args.base_url,
        api_key,
        "/v1/bom",
        method="POST",
        body=body,
        content_type=content_type,
    )
    write_json(args.output / "upload-response.json", upload)
    token = upload.get("token") if isinstance(upload, dict) else None
    if not isinstance(token, str):
        raise RuntimeError("BOM upload response did not contain a processing token")

    deadline = time.monotonic() + args.timeout_seconds
    while True:
        status, _ = api_request(args.base_url, api_key, f"/v1/bom/token/{token}")
        write_json(args.output / "processing-status.json", status)
        if isinstance(status, dict) and status.get("processing") is False:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for Dependency-Track to process the BOM")
        time.sleep(2)

    query = urllib.parse.urlencode({"name": args.project_name})
    projects = paged_get(args.base_url, api_key, f"/v1/project?{query}")
    matching = [
        project
        for project in projects
        if project.get("name") == args.project_name
        and project.get("version") == args.project_version
    ]
    if len(matching) != 1:
        raise RuntimeError(f"Expected one matching project, found {len(matching)}")
    project = matching[0]
    project_uuid = project["uuid"]
    write_json(args.output / "project.json", project)

    components = paged_get(args.base_url, api_key, f"/v1/component/project/{project_uuid}")
    findings = paged_get(args.base_url, api_key, f"/v1/finding/project/{project_uuid}")
    metrics, _ = api_request(args.base_url, api_key, f"/v1/metrics/project/{project_uuid}/current")

    write_json(args.output / "components.json", components)
    write_json(args.output / "findings.json", findings)
    write_json(args.output / "metrics.json", metrics)

    severity_counts: dict[str, int] = {}
    for finding in findings:
        vulnerability = finding.get("vulnerability", {})
        severity = str(vulnerability.get("severity", "UNKNOWN"))
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    summary = {
        "project_name": args.project_name,
        "project_version": args.project_version,
        "project_uuid": project_uuid,
        "input_bom": str(args.bom),
        "dependency_track_component_count": len(components),
        "dependency_track_finding_count": len(findings),
        "finding_severity_counts": severity_counts,
        "metrics": metrics,
        "interpretation_note": (
            "A zero finding count means no known vulnerability match was available to "
            "this Dependency-Track instance at collection time; it does not prove zero risk."
        ),
    }
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
