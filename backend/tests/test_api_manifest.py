"""Contract artifact tests used by generated Web and mini-program clients."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.manifest import build_manifest


class ApiManifestTests(unittest.TestCase):
    def test_manifest_is_deterministic_and_exposes_migrated_operations(self):
        schema = {
            "openapi": "3.1.0",
            "info": {"version": "0.1.0"},
            "paths": {
                "/api/v1/jobs/{job_id}": {
                    "get": {
                        "operationId": "get_job_v1",
                        "tags": ["jobs-v1"],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        first = build_manifest(schema)
        second = build_manifest(schema)
        self.assertEqual(first["contract_sha256"], second["contract_sha256"])
        self.assertEqual(first["operations"][0]["operation_id"], "get_job_v1")


if __name__ == "__main__":
    unittest.main()
