from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any, ClassVar

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO / "packages" / "contracts" / "support-bundle" / "support-bundle.schema.json"


def valid_bundle() -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-support-bundle",
        "bundleId": "a" * 32,
        "generatedAtUnixMs": 1_786_534_400_000,
        "components": [
            {"componentId": "desktop", "version": "0.1.0", "contractVersion": "1.0.0"},
            {"componentId": "core-api", "version": "0.1.0", "contractVersion": "1.0.0"},
        ],
        "runtime": {
            "state": "ready",
            "attempt": 1,
            "retryAvailable": False,
            "diagnosticReference": None,
        },
        "storage": [{"storageId": "application-data", "status": "available"}],
        "resources": {"processRunning": True, "workingSetBytes": 62_000_000},
        "recentDiagnostics": [
            {
                "sequence": 1,
                "code": "RO-CORE-API-REQUEST-COMPLETE",
                "stream": "api",
                "traceId": "b" * 32,
            }
        ],
        "exclusions": [
            "project-documents",
            "imported-sources",
            "manuscript-content",
            "search-and-query-text",
            "credentials-and-tokens",
            "environment-variables",
            "raw-process-logs",
            "process-identifiers",
            "absolute-storage-paths",
        ],
    }


class SupportBundleContractTests(unittest.TestCase):
    schema: ClassVar[dict[str, Any]]
    validator: ClassVar[Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_exact_redacted_bundle_is_valid(self) -> None:
        self.assertEqual([], list(self.validator.iter_errors(valid_bundle())))

    def test_research_content_secrets_paths_and_raw_logs_are_not_extensible_fields(self) -> None:
        for field, value in {
            "projectDocuments": ["private manuscript"],
            "authorization": "Bearer secret",
            "absolutePath": "C:\\Users\\Researcher\\private",
            "rawProcessLogs": ["exception with query text"],
            "processId": 42,
        }.items():
            with self.subTest(field=field):
                candidate = valid_bundle()
                candidate[field] = value
                self.assertTrue(list(self.validator.iter_errors(candidate)))

    def test_diagnostics_are_code_only_bounded_and_trace_identified(self) -> None:
        raw_message = valid_bundle()
        diagnostic = copy.deepcopy(raw_message["recentDiagnostics"])[0]
        diagnostic["message"] = "private query text"
        raw_message["recentDiagnostics"] = [diagnostic]
        self.assertTrue(list(self.validator.iter_errors(raw_message)))

        invalid_trace = valid_bundle()
        invalid_trace["recentDiagnostics"][0]["traceId"] = "../private"
        self.assertTrue(list(self.validator.iter_errors(invalid_trace)))

        oversized = valid_bundle()
        oversized["recentDiagnostics"] = [
            {
                "sequence": sequence,
                "code": "RO-CORE-RUNTIME-LOG",
                "stream": "stderr",
                "traceId": None,
            }
            for sequence in range(1, 34)
        ]
        self.assertTrue(list(self.validator.iter_errors(oversized)))

    def test_storage_unavailability_is_explicit_without_disclosing_a_path(self) -> None:
        candidate = valid_bundle()
        candidate["storage"] = [{"storageId": "application-data", "status": "unavailable"}]
        self.assertEqual([], list(self.validator.iter_errors(candidate)))


if __name__ == "__main__":
    unittest.main()
