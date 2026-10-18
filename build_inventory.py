import argparse
import ipaddress
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "echo.resource_inventory/v1"
URL_PATTERN = re.compile(r"https?://[^\s'\"]+")
PYPI_PATH_PATTERN = re.compile(r"^/pypi/([^/]+)")
CARGO_CRATE_PATTERN = re.compile(
    r"/registry/(?P<area>cache|src)/[^/]+/"
    r"(?P<name>.+)-(?P<version>\d+\.\d+\.\d+(?:[-+][^/.]+)?)"
    r"(?:\.crate|/|$)"
)


def load_events(path: Path) -> list[dict[str, Any]]:
    events = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"line {line_number} is not a JSON object")
        events.append(value)
    if not events:
        raise ValueError("the normalized event file is empty")
    return events


def event_confidence(event: dict[str, Any]) -> float:
    correlation = event.get("correlation", {})
    value = correlation.get("confidence", 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


class InventoryBuilder:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.resources: dict[str, dict[str, Any]] = {}
        self.relationships: dict[tuple[str, str, str], dict[str, Any]] = {}

    def resource(
        self,
        resource_id: str,
        resource_type: str,
        name: str,
        **identity: Any,
    ) -> dict[str, Any]:
        resource = self.resources.setdefault(
            resource_id,
            {
                "resource_id": resource_id,
                "type": resource_type,
                "name": name,
                "identity": {},
                "lifecycle": [],
                "evidence_ids": [],
                "observed_addresses": [],
            },
        )
        resource["identity"].update(
            {key: value for key, value in identity.items() if value is not None}
        )
        return resource

    def evidence(self, resource: dict[str, Any], event_id: str | None) -> None:
        if event_id and event_id not in resource["evidence_ids"]:
            resource["evidence_ids"].append(event_id)

    def lifecycle(
        self,
        resource: dict[str, Any],
        state: str,
        event: dict[str, Any],
        basis: str,
    ) -> None:
        event_id = event.get("event_id")
        self.evidence(resource, event_id)
        for claim in resource["lifecycle"]:
            if claim["state"] == state:
                if event_id and event_id not in claim["evidence_ids"]:
                    claim["evidence_ids"].append(event_id)
                claim["confidence"] = max(
                    claim["confidence"], event_confidence(event)
                )
                return
        resource["lifecycle"].append(
            {
                "state": state,
                "basis": basis,
                "confidence": event_confidence(event),
                "evidence_ids": [event_id] if event_id else [],
            }
        )

    def relationship(
        self,
        source: str,
        relationship_type: str,
        target: str,
        evidence_ids: list[str],
    ) -> None:
        key = (source, relationship_type, target)
        relationship = self.relationships.setdefault(
            key,
            {
                "source": source,
                "type": relationship_type,
                "target": target,
                "evidence_ids": [],
            },
        )
        for event_id in evidence_ids:
            if event_id and event_id not in relationship["evidence_ids"]:
                relationship["evidence_ids"].append(event_id)

    def output(self, input_event_count: int) -> dict[str, Any]:
        for resource in self.resources.values():
            resource["evidence_ids"].sort()
            resource["observed_addresses"].sort(
                key=lambda item: (item["ip"], item["port"])
            )
            resource["lifecycle"].sort(key=lambda item: item["state"])
            for claim in resource["lifecycle"]:
                claim["evidence_ids"].sort()

        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "input_event_count": input_event_count,
            "resources": sorted(
                self.resources.values(), key=lambda item: item["resource_id"]
            ),
            "relationships": sorted(
                self.relationships.values(),
                key=lambda item: (item["source"], item["type"], item["target"]),
            ),
            "scope_notes": [
                "Execution wrappers inserted by the test harness are excluded.",
                "Loopback DNS resolver connections are evidence, not external resources.",
                "Lifecycle states describe only what the available evidence supports.",
            ],
        }


def urls_from_event(event: dict[str, Any]) -> list[str]:
    attributes = event.get("attributes", {})
    values: list[str] = []
    command = attributes.get("command")
    if isinstance(command, str):
        values.extend(URL_PATTERN.findall(command))
    argv = attributes.get("argv", [])
    if isinstance(argv, list):
        values.extend(
            value
            for value in argv
            if isinstance(value, str) and value.startswith(("http://", "https://"))
        )
    return list(dict.fromkeys(values))


def is_external_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True
    return not (
        address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_private
    )


def build_inventory(events: list[dict[str, Any]]) -> dict[str, Any]:
    run_ids = {event.get("run_id") for event in events}
    if len(run_ids) != 1 or None in run_ids:
        raise ValueError("all normalized events must have the same non-empty run_id")
    run_id = str(next(iter(run_ids)))
    builder = InventoryBuilder(run_id)
    events_by_id = {
        event["event_id"]: event
        for event in events
        if isinstance(event.get("event_id"), str)
    }

    service_events: dict[str, list[str]] = {}
    package_events: dict[str, list[str]] = {}
    tools_by_process: dict[str, str] = {}
    files_by_process: dict[str, set[str]] = {}

    # First pass: resolve strong identities from executions, URLs, DNS and files.
    for event in events:
        event_type = event.get("event_type")
        event_id = event.get("event_id")
        attributes = event.get("attributes", {})
        process_id = event.get("process_id")

        if event_type == "execve":
            comm = attributes.get("comm")
            argv = attributes.get("argv", [])
            is_runuser_wrapper = (
                comm == "runuser"
                and isinstance(argv, list)
                and "/usr/sbin/runuser" in argv
                and "--" in argv
            )
            if isinstance(comm, str) and comm and not is_runuser_wrapper:
                tool_id = f"tool:{comm}"
                tool = builder.resource(tool_id, "tool", comm, command=comm)
                builder.lifecycle(
                    tool, "executed", event, "Linux execve event"
                )
                if isinstance(process_id, str):
                    tools_by_process[process_id] = tool_id

            for url in urls_from_event(event):
                parsed = urlparse(url)
                if not parsed.hostname:
                    continue
                host = parsed.hostname.lower()
                service_id = f"service:{host}"
                service = builder.resource(
                    service_id,
                    "service",
                    host,
                    scheme=parsed.scheme,
                    host=host,
                )
                builder.lifecycle(
                    service,
                    "requested",
                    event,
                    "URL present in executed command",
                )
                service_events.setdefault(service_id, []).append(event_id)

                match = PYPI_PATH_PATTERN.match(parsed.path)
                if host == "pypi.org" and match:
                    package_name = match.group(1)
                    package_id = f"package:pypi/{package_name.lower()}"
                    package = builder.resource(
                        package_id,
                        "package",
                        package_name,
                        ecosystem="PyPI",
                        registry="https://pypi.org",
                    )
                    builder.lifecycle(
                        package,
                        "metadata_requested",
                        event,
                        "PyPI project API URL present in executed command",
                    )
                    package_events.setdefault(package_id, []).append(event_id)
                    builder.relationship(
                        service_id, "describes", package_id, [event_id]
                    )

        elif event_type == "dns_query":
            host = attributes.get("host")
            if isinstance(host, str) and host:
                service_id = f"service:{host.lower()}"
                service = builder.resource(
                    service_id, "service", host.lower(), host=host.lower()
                )
                builder.lifecycle(
                    service, "resolved", event, "Linux DNS query event"
                )
                service_events.setdefault(service_id, []).append(event_id)

        elif event_type == "package_lock_entry":
            package_name = attributes.get("name")
            package_version = attributes.get("version")
            package_source = attributes.get("source")
            if isinstance(package_name, str) and isinstance(
                package_version, str
            ) and isinstance(package_source, str):
                package_id = (
                    f"package:cargo/{package_name.lower()}@{package_version}"
                )
                package = builder.resource(
                    package_id,
                    "package",
                    package_name,
                    ecosystem="Cargo",
                    version=package_version,
                    registry="https://crates.io",
                    purl=f"pkg:cargo/{package_name}@{package_version}",
                    checksum=attributes.get("checksum"),
                    source=package_source,
                )
                builder.lifecycle(
                    package,
                    "present_in_final_lockfile",
                    event,
                    "Package entry in the final Cargo.lock",
                )
                package_events.setdefault(package_id, []).append(event_id)

        elif event_type in {
            "file_open",
            "file_write",
            "file_rename",
            "file_change",
        }:
            path = attributes.get("path")
            if isinstance(path, str) and path:
                cargo_match = CARGO_CRATE_PATTERN.search(path)
                if cargo_match:
                    package_name = cargo_match.group("name")
                    package_version = cargo_match.group("version")
                    package_id = (
                        f"package:cargo/{package_name.lower()}@{package_version}"
                    )
                    package = builder.resource(
                        package_id,
                        "package",
                        package_name,
                        ecosystem="Cargo",
                        version=package_version,
                        registry="https://crates.io",
                        purl=f"pkg:cargo/{package_name}@{package_version}",
                    )
                    area = cargo_match.group("area")
                    if event_type in {"file_write", "file_rename"}:
                        if area == "cache" and path.endswith(".crate"):
                            state = "downloaded"
                            basis = "Cargo registry archive written during the task"
                        elif area == "src":
                            state = "extracted"
                            basis = "Cargo registry source extracted during the task"
                        else:
                            state = "written"
                            basis = "Cargo registry file written during the task"
                    else:
                        state = "read_during_build"
                        basis = (
                            "Cargo registry source or archive opened during the task"
                        )
                    builder.lifecycle(package, state, event, basis)
                    package_events.setdefault(package_id, []).append(event_id)
                    continue

                file_id = f"file:{path}"
                file_identity = {"path": path}
                if event_type == "file_change":
                    sha256 = attributes.get("next_sha256")
                    size = attributes.get("next_bytes")
                    if isinstance(sha256, str) and sha256 != "missing":
                        file_identity["sha256"] = sha256
                    if isinstance(size, int):
                        file_identity["size"] = size
                file_resource = builder.resource(
                    file_id, "file", Path(path).name, **file_identity
                )
                if event_type == "file_change":
                    change_type = attributes.get("change_type")
                    state = "created" if change_type == "created" else "changed"
                    basis = "Before-and-after workspace comparison"
                elif event_type == "file_open":
                    state = "opened"
                    basis = "Linux file-open event"
                elif event_type == "file_write":
                    state = "written"
                    basis = "Linux file-write event"
                else:
                    state = "renamed"
                    basis = "Linux file-rename event"
                builder.lifecycle(file_resource, state, event, basis)
                if isinstance(process_id, str):
                    files_by_process.setdefault(process_id, set()).add(file_id)

    service_ids = sorted(service_events)

    # Second pass: attach network and TLS evidence without turning each IP into
    # a separate service. Association is conservative when multiple domains exist.
    for event in events:
        event_type = event.get("event_type")
        event_id = event.get("event_id")
        attributes = event.get("attributes", {})
        process_id = event.get("process_id")

        if event_type == "network_connect":
            host = attributes.get("host") or attributes.get("dst_ip")
            port = str(attributes.get("port", ""))
            if not isinstance(host, str) or not is_external_address(host):
                continue
            if len(service_ids) == 1:
                service = builder.resources[service_ids[0]]
                address = {"ip": host, "port": port}
                if address not in service["observed_addresses"]:
                    service["observed_addresses"].append(address)
                builder.lifecycle(
                    service,
                    "connected",
                    event,
                    "Linux network-connect event associated with the task service",
                )

        elif event_type == "tls_write" and len(service_ids) == 1:
            service = builder.resources[service_ids[0]]
            builder.lifecycle(
                service,
                "tls_write_observed",
                event,
                "OpenSSL TLS write probe event",
            )

        if isinstance(process_id, str) and process_id in tools_by_process:
            tool_id = tools_by_process[process_id]
            if event_type in {"dns_query", "network_connect", "tls_write"}:
                for service_id in service_ids:
                    builder.relationship(
                        tool_id, "accessed", service_id, [event_id]
                    )
            if event_type in {"file_write", "file_change"}:
                for file_id in files_by_process.get(process_id, set()):
                    builder.relationship(tool_id, "wrote", file_id, [event_id])

    # Connect the downloaded metadata artifact to the registry package without
    # claiming that the package itself was downloaded or installed.
    metadata_files = [
        resource_id
        for resource_id, resource in builder.resources.items()
        if resource["type"] == "file" and "metadata" in resource["name"].lower()
    ]
    if len(package_events) == 1:
        package_id = next(iter(package_events))
        package = builder.resources[package_id]
        for file_id in metadata_files:
            file_resource = builder.resources[file_id]
            evidence_ids = sorted(
                set(package["evidence_ids"] + file_resource["evidence_ids"])
            )
            builder.relationship(
                file_id, "contains_metadata_for", package_id, evidence_ids
            )
            for event in events:
                if event.get("event_id") in file_resource["evidence_ids"]:
                    builder.lifecycle(
                        package,
                        "metadata_retrieved",
                        event,
                        "PyPI request produced a created metadata file",
                    )

    cargo_services = [
        resource_id
        for resource_id, resource in builder.resources.items()
        if resource["type"] == "service"
        and str(resource["identity"].get("host", "")).endswith("crates.io")
    ]
    cargo_packages = [
        resource_id
        for resource_id, resource in builder.resources.items()
        if resource["type"] == "package"
        and resource["identity"].get("ecosystem") == "Cargo"
    ]
    for service_id in cargo_services:
        for package_id in cargo_packages:
            evidence_ids = sorted(
                set(
                    builder.resources[service_id]["evidence_ids"]
                    + builder.resources[package_id]["evidence_ids"]
                )
            )
            builder.relationship(
                service_id, "provided", package_id, evidence_ids
            )

    for package_id in cargo_packages:
        package = builder.resources[package_id]
        states = {claim["state"] for claim in package["lifecycle"]}
        if "present_in_final_lockfile" in states:
            continue
        if not states.intersection({"downloaded", "extracted"}):
            continue
        supporting_event = next(
            (
                events_by_id[event_id]
                for event_id in package["evidence_ids"]
                if event_id in events_by_id
            ),
            None,
        )
        if supporting_event is not None:
            builder.lifecycle(
                package,
                "temporary_not_in_final_lockfile",
                supporting_event,
                "Observed in the Cargo registry during the task but absent "
                "from the final Cargo.lock",
            )

    return builder.output(len(events))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve normalized agent events into an evidence-linked inventory."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    events = load_events(args.input)
    inventory = build_inventory(events)
    args.output.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"Resolved {len(inventory['resources'])} resources and "
        f"{len(inventory['relationships'])} relationships into {args.output}"
    )
    for resource in inventory["resources"]:
        states = ", ".join(claim["state"] for claim in resource["lifecycle"])
        print(f"  {resource['resource_id']}: {states}")


if __name__ == "__main__":
    main()
