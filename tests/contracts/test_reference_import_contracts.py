"""The new import handoff is data-only, provisional and schema-bound."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.ingestion.reference_imports import ImportSession, ImportSource  # noqa: E402


class ReferenceImportContractTests(unittest.TestCase):
    def test_field_warning_attribution_is_required_and_schema_valid(self):
        schema = json.loads((REPO / "packages/contracts/ingestion/import-record.schema.json").read_text())
        validator = Draft202012Validator(schema)
        samples = (
            ("ris", b"TY  - JOUR\nDO  - invalid\nDO  - 10.99999/valid\nER  -\n"),
            ("bibtex", b"@article{a,title=unknown}"),
            ("csv", b"title,note\nValid,=SUM(A1)\n"),
        )
        for format_name, raw in samples:
            run = ImportSession(
                io.BytesIO(raw), ImportSource("synthetic", hashlib.sha256(raw).hexdigest()), format_name
            )
            for record in run.records():
                document = record.to_document()
                self.assertEqual([], list(validator.iter_errors(document)))
                for item in document["fields"]:
                    self.assertTrue(set(item["warnings"]).issubset(document["warnings"]))
                changed = copy.deepcopy(document)
                del changed["fields"][0]["warnings"]
                self.assertFalse(validator.is_valid(changed))

    def test_source_name_policy_preserves_unicode_basenames_and_denies_paths(self):
        schema = json.loads((REPO / "packages/contracts/ingestion/import-record.schema.json").read_text())
        filename_schema = schema["properties"]["source"]["properties"]["filename"]
        validator = Draft202012Validator(filename_schema)
        for name in ("notes-u.ris", "références.csv", "数据.bib", "library.json"):
            with self.subTest(name=name):
                self.assertTrue(validator.is_valid(name))
                ImportSource(name, "0" * 64)
        for name in ("folder/library.ris", "folder\\library.ris", "X:library.ris", "..", "bad\x00name"):
            with self.subTest(name=name):
                self.assertFalse(validator.is_valid(name))
                with self.assertRaises(ValueError):
                    ImportSource(name, "0" * 64)

    def test_five_format_fixtures_match_the_portable_contract_and_common_unknown_confidence(self):
        schema = json.loads((REPO / "packages/contracts/ingestion/import-record.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        common = json.loads((REPO / "packages/contracts/domain/domain-core.schema.json").read_text())
        confidence = Draft202012Validator(common["$defs"]["UnknownConfidence"])
        fixtures = (
            ("scholarly-corpus/metadata/records.ris", "ris"),
            ("scholarly-corpus/metadata/records.bib", "bibtex"),
            ("scholarly-metadata/records.csl.json", "csl-json"),
            ("scholarly-metadata/records.csv", "csv"),
            ("scholarly-metadata/records.doi", "doi-list"),
        )
        for relative, format_name in fixtures:
            path = REPO / "tests/fixtures" / relative
            raw = path.read_bytes()
            run = ImportSession(io.BytesIO(raw), ImportSource(path.name, hashlib.sha256(raw).hexdigest()), format_name)
            records = list(run.records())
            self.assertTrue(run.complete)
            self.assertEqual(0, run.error_count)
            self.assertEqual(2, len([item for item in records if item.kind == "record"]))
            for record in records:
                document = record.to_document()
                with self.subTest(format=format_name, ordinal=record.ordinal):
                    self.assertEqual([], list(validator.iter_errors(document)))
                    for candidate in document["candidates"]:
                        self.assertEqual([], list(confidence.iter_errors(candidate["confidence"])))
                    changed = copy.deepcopy(document)
                    changed["mappingDecision"] = {"accepted": True}
                    self.assertFalse(validator.is_valid(changed))
                    changed = copy.deepcopy(document)
                    changed["source"]["filename"] = "folder/library.ris"
                    self.assertFalse(validator.is_valid(changed))


if __name__ == "__main__":
    unittest.main()
