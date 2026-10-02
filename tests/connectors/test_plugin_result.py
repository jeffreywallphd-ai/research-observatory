"""Untrusted plugin pages may carry source claims, never Core provenance."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_manifest import (  # noqa: E402
    PluginInvocationRequest,
    PluginProjectGrant,
    authorize_plugin_invocation,
    verify_plugin_package,
)
from research_observatory_core.connectors.plugin_package_intake import inspect_plugin_archive  # noqa: E402
from research_observatory_core.connectors.plugin_result import (  # noqa: E402
    PluginResultProblem,
    validate_plugin_output,
)
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402

from tests.connectors.test_plugin_package_intake import archive  # noqa: E402

PROJECT = "0190a000-0000-7000-8000-000000000040"
RETRIEVED = "2026-10-01T12:00:00.000Z"


class PluginResultTests(unittest.TestCase):
    def setUp(self):
        raw, key = archive()
        inspected = inspect_plugin_archive(raw)
        package = verify_plugin_package(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            {inspected.manifest.publisher_key_id: key},
        )
        manifest = package.manifest
        request = PluginInvocationRequest(
            project_id=PROJECT,
            invocation_id=new_uuid_v7(),
            scientific_request_sha256="sha256:" + hashlib.sha256(b"scientific query").hexdigest(),
            operation=manifest.operations[0],
            destination=manifest.destinations[0],
        )
        grant = PluginProjectGrant(
            project_id=PROJECT,
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.plugin_version,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            publisher_key_id=manifest.publisher_key_id,
            permissions=manifest.permissions,
            destinations=manifest.destinations,
            revision=1,
        )
        self.plan = authorize_plugin_invocation(package, grant, request)
        self.page: dict[str, Any] = {
            "schemaVersion": "1.0",
            "invocationId": request.invocation_id,
            "operation": request.operation,
            "records": [
                {
                    "rawIdentifier": {"scheme": "doi", "value": "10.1234/example"},
                    "identifiers": [{"scheme": "doi", "value": "10.1234/example"}],
                    "fields": [{"name": "title", "encoding": "text", "value": "Reported title"}],
                    "terms": {
                        "license": {"state": "not-reported", "value": None},
                        "terms": {"state": "not-reported", "value": None},
                        "access": "unknown",
                    },
                }
            ],
            "continuation": "exhausted",
        }

    def _validate(self, page):
        return validate_plugin_output(
            self.plan,
            json.dumps(page, separators=(",", ":")).encode(),
            retrieved_at=RETRIEVED,
        )

    def test_core_binds_source_identity_and_retrieval_to_reported_record(self):
        validated = self._validate(self.page)
        self.assertEqual("exhausted", validated.continuation)
        self.assertEqual(1, len(validated.records))
        record = validated.records[0]
        self.assertEqual(self.plan.source_id, record.provider_id)
        self.assertEqual(self.plan.source_id, record.fields[0].namespace)
        self.assertEqual(RETRIEVED, record.retrieved_at)
        self.assertEqual("unknown", record.terms.access)
        self.assertEqual("Reported title", record.fields[0].value)

    def test_wrong_invocation_or_worker_provenance_is_rejected(self):
        for change in (
            {"invocationId": new_uuid_v7()},
            {"operation": "search" if self.plan.operation != "search" else "lookup"},
            {"projectId": PROJECT},
            {"sourceId": self.plan.source_id},
            {"retrievedAt": RETRIEVED},
        ):
            with self.subTest(change=change):
                page = self.page | change
                with self.assertRaises(PluginResultProblem):
                    self._validate(page)

    def test_malformed_source_field_cursor_and_shape_fail_closed(self):
        cases = []
        invalid_json_field = copy.deepcopy(self.page)
        invalid_json_field["records"][0]["fields"][0].update(encoding="json", value="{bad")
        cases.append(invalid_json_field)
        worker_namespace = copy.deepcopy(self.page)
        worker_namespace["records"][0]["fields"][0]["namespace"] = "forged"
        cases.append(worker_namespace)
        missing_cursor = self.page | {"continuation": "next-page"}
        cases.append(missing_cursor)
        cases.append(self.page | {"schemaVersion": "2.0"})
        for page in cases:
            with self.subTest(page=page), self.assertRaises(PluginResultProblem):
                self._validate(page)


if __name__ == "__main__":
    unittest.main()
