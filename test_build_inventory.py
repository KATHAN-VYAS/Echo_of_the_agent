import unittest

from build_inventory import build_inventory


RUN_ID = "test-run"


def event(
    event_id,
    event_type,
    attributes,
    *,
    source="agentprov_ebpf",
    confidence=0.98,
):
    return {
        "schema_version": "echo.normalized_event/v1",
        "event_id": event_id,
        "run_id": RUN_ID,
        "source": source,
        "event_type": event_type,
        "process_id": "process-1",
        "correlation": {"confidence": confidence},
        "attributes": attributes,
    }


class InventoryBuilderTest(unittest.TestCase):
    def setUp(self):
        self.events = [
            event(
                "wrapper",
                "execve",
                {
                    "comm": "runuser",
                    "argv": [
                        "/usr/sbin/runuser",
                        "-u",
                        "ubuntu",
                        "--",
                        "curl",
                        "https://pypi.org/pypi/requests/",
                    ],
                },
            ),
            event(
                "curl",
                "execve",
                {
                    "comm": "curl",
                    "argv": [
                        "curl",
                        "https://pypi.org/pypi/requests/",
                        "-o",
                        "requests-metadata.json",
                    ],
                },
            ),
            event("dns", "dns_query", {"host": "pypi.org"}),
            event(
                "dns-stub",
                "network_connect",
                {"host": "127.0.0.53", "port": "53"},
            ),
            event(
                "external-1",
                "network_connect",
                {"host": "151.101.0.223", "port": "443"},
            ),
            event(
                "external-2",
                "network_connect",
                {"host": "151.101.64.223", "port": "443"},
            ),
            event(
                "write",
                "file_write",
                {"path": "requests-metadata.json", "mode": "write"},
            ),
            event(
                "change",
                "file_change",
                {
                    "path": "requests-metadata.json",
                    "change_type": "created",
                },
                source="record_file_diff",
                confidence=1.0,
            ),
        ]

    def test_resolves_expected_resources(self):
        inventory = build_inventory(self.events)
        resources = {item["resource_id"]: item for item in inventory["resources"]}

        self.assertEqual(
            set(resources),
            {
                "tool:curl",
                "service:pypi.org",
                "package:pypi/requests",
                "file:requests-metadata.json",
            },
        )
        self.assertNotIn("tool:runuser", resources)

    def test_merges_addresses_under_one_service(self):
        inventory = build_inventory(self.events)
        resources = {item["resource_id"]: item for item in inventory["resources"]}
        service = resources["service:pypi.org"]

        self.assertEqual(
            service["observed_addresses"],
            [
                {"ip": "151.101.0.223", "port": "443"},
                {"ip": "151.101.64.223", "port": "443"},
            ],
        )

    def test_does_not_claim_package_installation_or_execution(self):
        inventory = build_inventory(self.events)
        resources = {item["resource_id"]: item for item in inventory["resources"]}
        states = {
            claim["state"]
            for claim in resources["package:pypi/requests"]["lifecycle"]
        }

        self.assertEqual(states, {"metadata_requested", "metadata_retrieved"})
        self.assertNotIn("installed", states)
        self.assertNotIn("executed", states)

    def test_distinguishes_file_open_write_and_rename(self):
        file_events = [
            event("open", "file_open", {"path": "/workspace/opened.txt"}),
            event("write", "file_write", {"path": "/workspace/written.txt"}),
            event("rename", "file_rename", {"path": "/workspace/renamed.txt"}),
        ]

        inventory = build_inventory(file_events)
        resources = {item["resource_id"]: item for item in inventory["resources"]}

        expected_states = {
            "file:/workspace/opened.txt": {"opened"},
            "file:/workspace/written.txt": {"written"},
            "file:/workspace/renamed.txt": {"renamed"},
        }
        for resource_id, expected in expected_states.items():
            actual = {
                claim["state"]
                for claim in resources[resource_id]["lifecycle"]
            }
            self.assertEqual(actual, expected)

    def test_resolves_cargo_registry_archive_as_downloaded_package(self):
        cargo_events = [
            event(
                "crates-dns",
                "dns_query",
                {"host": "static.crates.io"},
            ),
            event(
                "crate-write",
                "file_write",
                {
                    "path": (
                        "/home/ubuntu/.cargo/registry/cache/"
                        "index.crates.io-abcd/ratatui-0.26.3.crate"
                    )
                },
            ),
            event(
                "crate-open",
                "file_open",
                {
                    "path": (
                        "/home/ubuntu/.cargo/registry/src/"
                        "index.crates.io-abcd/ratatui-0.26.3/src/lib.rs"
                    )
                },
            ),
        ]

        inventory = build_inventory(cargo_events)
        resources = {item["resource_id"]: item for item in inventory["resources"]}
        package = resources["package:cargo/ratatui@0.26.3"]
        states = {claim["state"] for claim in package["lifecycle"]}

        self.assertEqual(package["identity"]["ecosystem"], "Cargo")
        self.assertEqual(
            states,
            {
                "downloaded",
                "read_during_build",
                "temporary_not_in_final_lockfile",
            },
        )
        self.assertTrue(
            any(
                relationship["source"] == "service:static.crates.io"
                and relationship["target"] == "package:cargo/ratatui@0.26.3"
                and relationship["type"] == "provided"
                for relationship in inventory["relationships"]
            )
        )

    def test_marks_cargo_package_present_in_final_lockfile(self):
        cargo_events = [
            event(
                "crate-write",
                "file_write",
                {
                    "path": (
                        "/home/ubuntu/.cargo/registry/cache/"
                        "index.crates.io-abcd/ratatui-0.26.3.crate"
                    )
                },
            ),
            event(
                "cargo-lock-1",
                "package_lock_entry",
                {
                    "name": "ratatui",
                    "version": "0.26.3",
                    "source": "registry+https://github.com/rust-lang/crates.io-index",
                },
                source="cargo_lock",
                confidence=1.0,
            ),
        ]

        inventory = build_inventory(cargo_events)
        resources = {item["resource_id"]: item for item in inventory["resources"]}
        states = {
            claim["state"]
            for claim in resources["package:cargo/ratatui@0.26.3"]["lifecycle"]
        }

        self.assertIn("downloaded", states)
        self.assertIn("present_in_final_lockfile", states)
        self.assertNotIn("temporary_not_in_final_lockfile", states)

    def test_resolves_package_from_isolated_cargo_home(self):
        cargo_events = [
            event(
                "isolated-crate-write",
                "file_write",
                {
                    "path": (
                        "/home/ubuntu/aibom-cargo-v3/registry/cache/"
                        "index.crates.io-abcd/darling-0.24.1.crate"
                    )
                },
            )
        ]

        inventory = build_inventory(cargo_events)
        resources = {item["resource_id"]: item for item in inventory["resources"]}
        states = {
            claim["state"]
            for claim in resources["package:cargo/darling@0.24.1"]["lifecycle"]
        }

        self.assertEqual(states, {"downloaded", "temporary_not_in_final_lockfile"})


if __name__ == "__main__":
    unittest.main()
