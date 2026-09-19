"""Import draft decisions never overwrite parser observations or grant rights."""

from __future__ import annotations

import hashlib
import io
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.ingestion.import_drafts import (  # noqa: E402
    DraftAuthority,
    FieldMapping,
    ImportPermission,
    ImportRights,
    MappedField,
    MappingProfile,
    diagnostic_csv,
    effective_draft_sha256,
    propose_fields,
    review_record,
    spreadsheet_cell,
)
from research_observatory_core.ingestion.reference_imports import ImportSession, ImportSource  # noqa: E402

PROJECT = "018f47a2-4d6b-4f78-9f2e-7fb76c86d060"
PREVIEW = "018f47a2-4d6b-7f78-9f2e-7fb76c86d061"
PROFILE = "018f47a2-4d6b-7f78-9f2e-7fb76c86d062"


def parse(raw: bytes, format_name: str = "csv"):
    run = ImportSession(io.BytesIO(raw), ImportSource("synthetic", hashlib.sha256(raw).hexdigest()), format_name)
    records = tuple(run.records())
    assert run.complete
    return records


def profile(*bindings: FieldMapping, revision: int = 1):
    return MappingProfile(
        profile_id=PROFILE,
        revision=revision,
        predecessor_revision=revision - 1 if revision > 1 else None,
        mode="columns" if bindings else "automatic",
        bindings=bindings,
    )


class ImportDraftTests(unittest.TestCase):
    def test_mapping_disambiguates_duplicate_columns_and_preserves_raw_ir(self):
        record = parse(b"heading,heading,identifier\nOriginal,Corrected,https://doi.org/10.99999/ABC\n")[1]
        original = record.to_document()
        mapping = profile(
            FieldMapping(source_name="heading", occurrence=1, target="title"),
            FieldMapping(source_name="identifier", occurrence=0, target="doi"),
        )
        proposal = propose_fields(record, mapping)
        self.assertEqual(
            [(item.name, item.value, item.source_field_index) for item in proposal.fields],
            [("title", "Corrected", 1), ("doi", "10.99999/abc", 2)],
        )
        self.assertEqual((), proposal.conflicts)
        decision = review_record(record, included=True, fields=proposal.fields)
        self.assertTrue(decision.included)
        self.assertEqual(original, record.to_document())

    def test_conflicts_are_explicit_and_manual_corrections_are_separate(self):
        record = parse(b"title,title\nFirst,Second\n")[1]
        proposed = propose_fields(record, profile())
        self.assertEqual(("title",), proposed.conflicts)
        with self.assertRaisesRegex(ValueError, "conflicting-mapped-field"):
            review_record(record, included=True, fields=proposed.fields)
        accepted = review_record(
            record,
            included=True,
            fields=(
                MappedField(name="title", value="Researcher correction", source_field_index=None, origin="correction"),
            ),
        )
        self.assertEqual("Researcher correction", accepted.fields[0].value)
        self.assertEqual("First", record.fields[0].raw_value)
        with self.assertRaises(ValidationError):
            accepted.included = False

    def test_malformed_nonrecord_and_unbound_fields_cannot_be_included(self):
        header, record = parse(b"title\nValid\n")
        malformed = parse(b"not a DOI\n", "doi-list")[0]
        for value in (header, malformed):
            self.assertFalse(review_record(value, included=False, fields=()).included)
            with self.assertRaisesRegex(ValueError, "record-not-importable"):
                review_record(value, included=True, fields=())
        for index in (1, 4095):
            with self.assertRaisesRegex(ValueError, "source-field-mismatch"):
                review_record(
                    record,
                    included=True,
                    fields=(
                        MappedField(name="title", value="Substituted", source_field_index=index, origin="mapping"),
                    ),
                )
        with self.assertRaisesRegex(ValueError, "invalid-mapped-doi"):
            review_record(
                record,
                included=True,
                fields=(MappedField(name="doi", value="not a doi", source_field_index=None, origin="correction"),),
            )

    def test_mapping_profile_revisions_and_occurrences_are_strict(self):
        binding = FieldMapping(source_name="title", occurrence=0, target="title")
        with self.assertRaises(ValidationError):
            profile(binding, binding)
        with self.assertRaises(ValidationError):
            MappingProfile(profile_id=PROFILE, revision=2, predecessor_revision=None, mode="automatic", bindings=())
        with self.assertRaises(ValidationError):
            FieldMapping(source_name="title", occurrence=True, target="title")
        with self.assertRaises(ValidationError):
            MappedField(name="title", value="Synthetic", source_field_index=0, origin="correction")

    def test_rights_are_action_specific_and_unknown_does_not_authorize(self):
        rights = ImportRights()
        for action in ("store", "inspect", "index", "derive", "model-use", "quote", "export", "share"):
            self.assertFalse(rights.permits(action))
        rights = ImportRights(
            store=ImportPermission(value="permitted", basis="researcher-confirmed"),
            inspect=ImportPermission(value="permitted", basis="researcher-confirmed"),
        )
        self.assertTrue(rights.permits("store"))
        self.assertTrue(rights.permits("inspect"))
        self.assertFalse(rights.permits("export"))
        self.assertFalse(rights.permits("model-use"))
        with self.assertRaises(ValidationError):
            ImportPermission(value="permitted", basis="not-reported")

    def test_effective_digest_binds_corrections_selection_rights_options_and_profile(self):
        records = parse(b"title\nFirst\nSecond\n")[1:]
        authority = DraftAuthority(
            project_id=PROJECT,
            preview_id=PREVIEW,
            source_sha256=records[0].source.sha256,
            mapping=profile(),
            rights=ImportRights(),
        )
        decisions = tuple(
            review_record(record, included=True, fields=propose_fields(record, profile()).fields) for record in records
        )
        digest = effective_draft_sha256(authority, iter(decisions))
        self.assertEqual(
            digest,
            effective_draft_sha256(DraftAuthority.model_validate_json(authority.model_dump_json()), iter(decisions)),
        )
        changes = (
            (authority, (decisions[0].model_copy(update={"included": False}), decisions[1])),
            (
                authority,
                (
                    review_record(
                        records[0],
                        included=True,
                        fields=(
                            MappedField(name="title", value="Changed", source_field_index=None, origin="correction"),
                        ),
                    ),
                    decisions[1],
                ),
            ),
            (authority.model_copy(update={"mapping": profile(revision=2)}), decisions),
            (
                authority.model_copy(
                    update={
                        "rights": ImportRights(export=ImportPermission(value="denied", basis="researcher-confirmed"))
                    }
                ),
                decisions,
            ),
        )
        for changed_authority, changed_decisions in changes:
            self.assertNotEqual(digest, effective_draft_sha256(changed_authority, iter(changed_decisions)))
        with self.assertRaisesRegex(ValueError, "record-order"):
            effective_draft_sha256(authority, reversed(decisions))
        with self.assertRaisesRegex(ValueError, "record-order"):
            effective_draft_sha256(authority, iter((decisions[0], decisions[0])))

    def test_diagnostic_report_is_streamed_and_omits_all_source_content(self):
        records = parse(b"title,title\n=SUM(A1),Private sentinel\n")
        chunks = diagnostic_csv(iter(records))
        self.assertEqual("ordinal,line_start,line_end,status,diagnostic\r\n", next(chunks))
        report = "".join(chunks)
        self.assertIn("duplicate-field", report)
        self.assertIn("formula-like-cell", report)
        self.assertNotIn("SUM", report)
        self.assertNotIn("Private", report)
        self.assertNotIn("synthetic", report)
        self.assertNotIn(records[0].source.sha256, report)

    def test_spreadsheet_safety_is_not_just_quoting(self):
        for value in ("=1+1", " +SUM(A1)", "-1", "@call()", "\tformula", "\r\ncontent", "\x00text"):
            self.assertEqual("'" + value, spreadsheet_cell(value))
        for value in ("Title", "10.99999/example", 'a,"b"'):
            self.assertEqual(value, spreadsheet_cell(value))


if __name__ == "__main__":
    unittest.main()
