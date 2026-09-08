from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))
sys.path.insert(0, str(REPO / "tools"))

from core_api_contract import _interfaces, generated_artifacts  # noqa: E402
from research_observatory_core.model_registry_contracts import ModelManifest  # noqa: E402
from research_observatory_core.model_routing_contracts import RoutingPolicy  # noqa: E402

from tests.ai.test_model_registry import manifest_document  # noqa: E402


class ModelRegistryContractTests(unittest.TestCase):
    def test_generator_preserves_primitive_contract_aliases(self) -> None:
        rendered = _interfaces(
            {
                "components": {
                    "schemas": {
                        "Cost": {"type": "integer", "minimum": 0},
                        "Identity": {"type": "string", "pattern": "^[a-z]+$"},
                        "Flag": {"type": "boolean"},
                    }
                }
            }
        )
        self.assertIn("export type Cost = number;", rendered)
        self.assertIn("export type Identity = string;", rendered)
        self.assertIn("export type Flag = boolean;", rendered)

    def test_generator_publishes_identified_schemas_without_changing_core_rules(self) -> None:
        artifacts = generated_artifacts(REPO)
        for filename, model in (
            ("model-manifest.schema.json", ModelManifest),
            ("routing-policy.schema.json", RoutingPolicy),
        ):
            with self.subTest(filename=filename):
                expected = model.model_json_schema(by_alias=True) | {
                    "$id": f"https://research-observatory.local/contracts/model-gateway/{filename}",
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                }
                generated = artifacts[REPO / "packages/contracts/model-gateway" / filename]
                self.assertEqual(expected, json.loads(generated))
                self.assertEqual((json.dumps(expected, indent=2, sort_keys=True) + "\n").encode(), generated)

    def test_portable_manifest_schema_matches_owned_core_contract(self) -> None:
        schema = ModelManifest.model_json_schema(by_alias=True)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertEqual([], list(validator.iter_errors(manifest_document())))
        changes: dict[str, Any]
        for changes in ({"revision": True}, {"allowed": True}, {"identity": {}}, {"contextTokens": -1}):
            self.assertTrue(list(validator.iter_errors(manifest_document() | changes)))
        committed = json.loads(
            (REPO / "packages/contracts/model-gateway/model-manifest.schema.json").read_text("utf-8")
        )
        self.assertEqual(
            schema
            | {
                "$id": "https://research-observatory.local/contracts/model-gateway/model-manifest.schema.json",
                "$schema": "https://json-schema.org/draft/2020-12/schema",
            },
            committed,
        )
        Draft202012Validator.check_schema(committed)
        published_validator = Draft202012Validator(committed)
        self.assertEqual([], list(published_validator.iter_errors(manifest_document())))
        for changes in ({"revision": True}, {"allowed": True}, {"identity": {}}, {"contextTokens": -1}):
            self.assertTrue(list(published_validator.iter_errors(manifest_document() | changes)))


if __name__ == "__main__":
    unittest.main()
