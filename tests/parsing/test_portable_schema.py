"""Independent JSON Schema consumers verify shape; Core checks semantics."""

import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from pydantic import ValidationError  # noqa: E402
from research_observatory_core.parsing.contracts import DocumentIR  # noqa: E402

from tests.parsing.contract_fixtures import rich_ir_wire  # noqa: E402
from tests.parsing.test_parse_handoff import delivery, request  # noqa: E402


class PortableParserSchemaTests(unittest.TestCase):
    def validator(self, name):
        path = REPO / "packages/contracts/documents" / name
        value = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(value)
        self.assertTrue(value["x-research-observatory-semanticRules"])
        return Draft202012Validator(value)

    def test_language_neutral_ir_selection_request_and_results(self):
        req = request()
        samples = (
            ("document-ir.v1.schema.json", rich_ir_wire()),
            ("parser-selection.v1.schema.json", req.selection.model_dump(mode="json", by_alias=True)),
            ("parse-request.v1.schema.json", req.model_dump(mode="json", by_alias=True)),
            ("parse-result.v1.schema.json", json.loads(delivery(req).wire)),
        )
        for name, value in samples:
            with self.subTest(schema=name):
                validator = self.validator(name)
                validator.validate(value)
                value["unrestrictedPath"] = "synthetic-forbidden-field"
                self.assertTrue(list(validator.iter_errors(value)))
        validator = self.validator("parse-result.v1.schema.json")
        for kind, code in (("failure", "parser-failed"), ("cancelled", "cancelled")):
            value = {
                "schemaVersion": "1.0",
                "kind": kind,
                "code": code,
                "binding": req.binding.model_dump(mode="json", by_alias=True),
            }
            validator.validate(value)
            value["ir"] = rich_ir_wire()
            self.assertTrue(list(validator.iter_errors(value)))

    def test_schema_shape_does_not_claim_semantic_authority(self):
        value = rich_ir_wire()
        value["nodes"][0]["parentId"] = "missing-parent"
        self.validator("document-ir.v1.schema.json").validate(value)
        with self.assertRaises(ValidationError):
            DocumentIR.model_validate(value)


if __name__ == "__main__":
    unittest.main()
