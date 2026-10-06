"""Portable exact-copy contracts and missing checksum/license semantics."""

import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.ports.acquisition import (  # noqa: E402
    AcquisitionLocation,
    AcquisitionReceipt,
    AcquisitionSelection,
)


class AcquisitionContractTests(unittest.TestCase):
    def test_portable_schemas_match_runtime_and_forbid_extra_fields(self):
        for model, name in (
            (AcquisitionLocation, "acquisition-location"),
            (AcquisitionSelection, "acquisition-selection"),
            (AcquisitionReceipt, "acquisition-receipt"),
        ):
            schema = json.loads((REPO / "packages/contracts/documents" / (name + ".v1.schema.json")).read_text())
            Draft202012Validator.check_schema(schema)
            schema.pop("$schema")
            schema.pop("$id")
            self.assertEqual(model.model_json_schema(by_alias=True), schema)
            self.assertFalse(schema["additionalProperties"])

    def test_selection_cannot_accept_destination_path_or_invent_expected_checksum(self):
        selection = AcquisitionSelection(
            location_id="018f0000-0000-7000-8000-000000000001",
            location_sha256="a" * 64,
            source_assertion_revision_id="018f0000-0000-7000-8000-000000000002",
            work_id="018f0000-0000-7000-8000-000000000003",
            work_revision_id="018f0000-0000-7000-8000-000000000004",
            version_id="018f0000-0000-7000-8000-000000000005",
            version_revision_id="018f0000-0000-7000-8000-000000000006",
        )
        self.assertIsNone(selection.expected_sha256)
        value = selection.model_dump(mode="json", by_alias=True)
        schema = json.loads((REPO / "packages/contracts/documents/acquisition-selection.v1.schema.json").read_text())
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(value)))
        for name, unexpected in (
            ("url", "https://arbitrary.example/content"),
            ("path", "unrestricted"),
            ("expectedSha256", ""),
            ("redirectHosts", ["host.example"] * 6),
        ):
            changed = value | {name: unexpected}
            with self.subTest(name=name), self.assertRaises(ValidationError):
                AcquisitionSelection.model_validate_json(json.dumps(changed))
            self.assertTrue(list(Draft202012Validator(schema).iter_errors(changed)))


if __name__ == "__main__":
    unittest.main()
