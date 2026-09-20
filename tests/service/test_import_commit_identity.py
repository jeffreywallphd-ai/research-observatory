"""Scientific import identity is not a request ID, Work ID or permission grant."""

from __future__ import annotations

import hashlib
import json
import unittest

from research_observatory_core.ingestion.import_commits import ImportIdentity, import_identity, source_assertion_key
from research_observatory_core.ingestion.import_drafts import (
    DraftAuthority,
    ImportPermission,
    ImportRights,
    MappedField,
    effective_draft_sha256,
    propose_fields,
    review_record,
)

from tests.service.test_import_drafts import PREVIEW, PROJECT, parse, profile


class ImportCommitIdentityTests(unittest.TestCase):
    def setUp(self):
        self.raw = b"title,doi\nSynthetic,10.99999/a\nSecond,10.99999/b\n"
        self.records = parse(self.raw)
        self.authority = DraftAuthority(
            project_id=PROJECT,
            preview_id=PREVIEW,
            source_sha256=hashlib.sha256(self.raw).hexdigest(),
            mapping=profile(),
            rights=ImportRights(),
        )
        self.decisions = tuple(
            review_record(
                record,
                included=record.kind == "record",
                fields=propose_fields(record, self.authority.mapping).fields,
            )
            for record in self.records
        )

    def identity(self, authority=None, decisions=None):
        return import_identity(
            authority or self.authority,
            iter(self.decisions if decisions is None else decisions),
            expected_record_count=3,
        )

    def test_exact_serialization_and_single_traversal(self):
        class Once:
            def __iter__(inner):
                if getattr(inner, "used", False):
                    raise AssertionError("second traversal")
                inner.used = True
                yield from self.decisions

        result = import_identity(self.authority, Once(), expected_record_count=3)
        draft = effective_draft_sha256(self.authority, self.decisions)
        expected = [
            "import-identity/1",
            PROJECT,
            self.authority.source_sha256,
            self.authority.parser_version,
            [self.authority.mapping.profile_id, 1],
            [decision.record_key for decision in self.decisions if decision.included],
            draft,
        ]
        digest = hashlib.sha256(json.dumps(expected, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(digest, result.sha256)
        self.assertEqual(draft, result.effective_draft_sha256)
        self.assertEqual((3, 2), (result.record_count, result.selected_count))

    def test_preview_is_excluded_but_scientific_authority_is_bound(self):
        original = self.identity()
        self.assertEqual(
            original, self.identity(self.authority.model_copy(update={"preview_id": self.authority.mapping.profile_id}))
        )
        changed = (
            {"project_id": "018f47a2-4d6b-4f78-9f2e-7fb76c86d099"},
            {"source_sha256": "f" * 64},
            {"mapping": profile(revision=2)},
            {"rights": ImportRights(store=ImportPermission(value="permitted", basis="researcher-confirmed"))},
            {"delimiter": ";"},
        )
        for delta in changed:
            with self.subTest(fields=list(delta)):
                self.assertNotEqual(original.sha256, self.identity(self.authority.model_copy(update=delta)).sha256)

    def test_corrections_selection_and_per_record_rights_change_manifest_identity(self):
        original = self.identity()
        changes = (
            {"included": False},
            {"fields": (MappedField(name="title", value="Corrected", source_field_index=None, origin="correction"),)},
            {"rights": ImportRights(export=ImportPermission(value="denied", basis="researcher-confirmed"))},
        )
        raw_before = self.records[1].to_document()
        for delta in changes:
            decisions = (self.decisions[0], self.decisions[1].model_copy(update=delta), self.decisions[2])
            self.assertNotEqual(original.sha256, self.identity(decisions=decisions).sha256)
        self.assertEqual(raw_before, self.records[1].to_document())

    def test_incomplete_reordered_or_unbounded_input_cannot_return_identity(self):
        for decisions in (self.decisions[:2], self.decisions[1:], tuple(reversed(self.decisions)), self.decisions * 2):
            with self.subTest(length=len(decisions)), self.assertRaises(ValueError):
                self.identity(decisions=decisions)
        for count in (-1, True, 200001, 3.0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                import_identity(self.authority, iter(self.decisions), expected_record_count=count)
        empty = import_identity(self.authority, iter(()), expected_record_count=0)
        self.assertEqual((0, 0), (empty.record_count, empty.selected_count))

    def test_source_assertion_key_is_scoped_and_not_a_work_or_record_uuid(self):
        key = source_assertion_key(PROJECT, self.authority.source_sha256, self.records[1].record_key)
        self.assertEqual(key, source_assertion_key(PROJECT, self.authority.source_sha256, self.records[1].record_key))
        self.assertEqual(64, len(key))
        for args in (
            (PROJECT, "f" * 64, self.records[1].record_key),
            (PROJECT, self.authority.source_sha256, self.records[2].record_key),
            ("018f47a2-4d6b-4f78-9f2e-7fb76c86d099", self.authority.source_sha256, self.records[1].record_key),
        ):
            self.assertNotEqual(key, source_assertion_key(*args))
        for args in (("private-path", "a" * 64, "b" * 64), (PROJECT, "x" * 64, "b" * 64), (PROJECT, "a" * 64, "")):
            with self.assertRaises(ValueError):
                source_assertion_key(*args)

    def test_identity_projection_rejects_incoherent_counts(self):
        with self.assertRaisesRegex(ValueError, "import-selection-count-mismatch"):
            ImportIdentity(sha256="a" * 64, effective_draft_sha256="b" * 64, record_count=0, selected_count=1)


if __name__ == "__main__":
    unittest.main()
