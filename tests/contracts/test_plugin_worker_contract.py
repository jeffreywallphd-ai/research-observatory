"""The public plugin worker page schema matches Core's admission shape."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))
sys.path.insert(0, str(REPO / "tools"))

from core_api_contract import generated_artifacts  # noqa: E402
from research_observatory_core.connectors.plugin_result import PluginWorkerPage  # noqa: E402


class PluginWorkerContractTests(unittest.TestCase):
    def test_generated_page_schema_accepts_page_and_denies_core_owned_fields(self) -> None:
        path = REPO / "packages/contracts/connectors/connector-plugin-worker-page.schema.json"
        generated = generated_artifacts(REPO)[path]
        self.assertEqual(generated, path.read_bytes())
        schema = json.loads(generated)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        page: dict[str, object] = {
            "schemaVersion": "1.0",
            "invocationId": "0190a000-0000-7000-8000-000000000042",
            "operation": "lookup",
            "records": [],
            "continuation": "exhausted",
            "nextCursor": None,
        }
        self.assertTrue(validator.is_valid(page))
        PluginWorkerPage.model_validate(page)
        for forged in ({"projectId": "forged"}, {"retrievedAt": "forged"}, {"rights": "permitted"}):
            with self.subTest(field=next(iter(forged))):
                self.assertFalse(validator.is_valid(page | forged))


if __name__ == "__main__":
    unittest.main()
