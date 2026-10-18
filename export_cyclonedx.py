import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from cyclonedx.model import HashAlgorithm, HashType, Property, XsUri
from cyclonedx.model.bom import Bom, BomMetaData
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.model.service import Service
from cyclonedx.output import OutputFormat, SchemaVersion, make_outputter
from packageurl import PackageURL


def property_list(resource: dict[str, Any]) -> list[Property]:
    properties = [
        Property(
            name="echo:evidence_ids",
            value=json.dumps(resource.get("evidence_ids", []), separators=(",", ":")),
        ),
        Property(
            name="echo:lifecycle_claims",
            value=json.dumps(resource.get("lifecycle", []), separators=(",", ":")),
        ),
    ]
    identity = resource.get("identity", {})
    for key, value in sorted(identity.items()):
        if key == "sha256":
            continue
        properties.append(Property(name=f"echo:identity:{key}", value=str(value)))
    addresses = resource.get("observed_addresses", [])
    if addresses:
        properties.append(
            Property(
                name="echo:observed_addresses",
                value=json.dumps(addresses, separators=(",", ":")),
            )
        )
    return properties


def make_component(resource: dict[str, Any]) -> Component:
    resource_type = resource["type"]
    component_type = {
        "tool": ComponentType.APPLICATION,
        "package": ComponentType.LIBRARY,
        "file": ComponentType.FILE,
    }[resource_type]

    identity = resource.get("identity", {})
    purl = None
    if resource_type == "package" and identity.get("ecosystem") == "PyPI":
        purl = PackageURL(type="pypi", name=resource["name"])
    elif resource_type == "package" and identity.get("ecosystem") == "Cargo":
        purl = PackageURL(
            type="cargo",
            name=resource["name"],
            version=identity.get("version"),
        )

    hashes = []
    sha256 = identity.get("sha256")
    if isinstance(sha256, str):
        hashes.append(HashType(alg=HashAlgorithm.SHA_256, content=sha256))

    return Component(
        name=resource["name"],
        type=component_type,
        bom_ref=resource["resource_id"],
        purl=purl,
        hashes=hashes,
        properties=property_list(resource),
    )


def make_service(resource: dict[str, Any]) -> Service:
    identity = resource.get("identity", {})
    scheme = identity.get("scheme", "https")
    host = identity.get("host", resource["name"])
    return Service(
        name=resource["name"],
        bom_ref=resource["resource_id"],
        endpoints=[XsUri(f"{scheme}://{host}")],
        properties=property_list(resource),
    )


def build_bom(inventory: dict[str, Any]) -> Bom:
    run_id = inventory.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("inventory does not contain a valid run_id")

    task = Component(
        name=f"AI coding task {run_id}",
        type=ComponentType.APPLICATION,
        bom_ref=f"task:{run_id}",
        properties=[Property(name="echo:run_id", value=run_id)],
    )
    metadata = BomMetaData(
        component=task,
        properties=[
            Property(name="echo:inventory_schema", value=str(inventory.get("schema_version"))),
            Property(
                name="echo:input_event_count",
                value=str(inventory.get("input_event_count", 0)),
            ),
        ],
    )

    components = []
    services = []
    objects_by_ref: dict[str, Component | Service] = {}
    for resource in inventory.get("resources", []):
        if resource.get("type") == "service":
            item = make_service(resource)
            services.append(item)
        elif resource.get("type") in {"tool", "package", "file"}:
            item = make_component(resource)
            components.append(item)
        else:
            continue
        objects_by_ref[resource["resource_id"]] = item

    serial_number = uuid.uuid5(
        uuid.NAMESPACE_URL, f"https://echo-agent.local/runs/{run_id}"
    )
    relationship_property = Property(
        name="echo:relationships",
        value=json.dumps(
            inventory.get("relationships", []),
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
    bom = Bom(
        components=components,
        services=services,
        serial_number=serial_number,
        metadata=metadata,
        properties=[relationship_property],
    )

    # Register only relationships whose semantics fit CycloneDX dependency
    # edges. Rich relationship types remain in echo:relationships.
    for relationship in inventory.get("relationships", []):
        if relationship.get("type") != "accessed":
            continue
        source = objects_by_ref.get(relationship.get("source"))
        target = objects_by_ref.get(relationship.get("target"))
        if source is not None and target is not None:
            bom.register_dependency(source, [target])

    bom.register_dependency(task, list(objects_by_ref.values()))
    return bom


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export an evidence-linked inventory as CycloneDX 1.7 JSON."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    inventory = json.loads(args.input.read_text(encoding="utf-8"))
    bom = build_bom(inventory)
    if not bom.validate():
        raise ValueError("the in-memory CycloneDX BOM failed model validation")

    outputter = make_outputter(
        bom=bom,
        output_format=OutputFormat.JSON,
        schema_version=SchemaVersion.V1_7,
    )
    args.output.write_text(
        outputter.output_as_string(indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote valid CycloneDX 1.7 JSON to {args.output}")


if __name__ == "__main__":
    main()
