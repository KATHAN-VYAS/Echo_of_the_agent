import unittest
from pathlib import Path

from import_agentprov import keep_file_event


class FileEvidenceFilterTest(unittest.TestCase):
    def test_keeps_isolated_cargo_registry_evidence(self):
        event = {
            "payload": (
                "/home/ubuntu/aibom-cargo-v3/registry/cache/"
                "index.crates.io/example-1.0.0.crate"
            )
        }

        self.assertTrue(
            keep_file_event(
                event,
                Path("/home/ubuntu/workspace"),
                Path("/home/ubuntu/aibom-cargo-v3"),
            )
        )

    def test_rejects_unrelated_file(self):
        event = {"payload": "/var/log/unrelated.log"}

        self.assertFalse(
            keep_file_event(
                event,
                Path("/home/ubuntu/workspace"),
                Path("/home/ubuntu/aibom-cargo-v3"),
            )
        )


if __name__ == "__main__":
    unittest.main()
