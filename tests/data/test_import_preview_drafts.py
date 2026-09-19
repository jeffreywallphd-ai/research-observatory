"""Persistent researcher decisions over real accepted preview attempts."""

from __future__ import annotations

import unittest

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import (
    FieldMapping,
    ImportPermission,
    ImportRights,
    MappedField,
    MappingProfile,
    review_record,
)
from research_observatory_core.ports.import_previews import PreviewProblem

from tests.data import test_import_preview_repository as fixture


class ImportPreviewDraftTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportPreviewRepositoryTests(methodName="runTest")
        lifecycle: unittest.TestCase = self.fixture
        lifecycle.setUp()
        self.addCleanup(lifecycle.tearDown)
        self.repository = self.fixture.repository
        self.actor = self.fixture.actor
        self.parse_attempt = self.fixture.parse_attempt
        self.receipt_revision = self.fixture.receipt_revision

    def accepted(self, raw: bytes = b"title,heading\nFirst,Alternate\nSecond,Other\n"):
        preview, sealed, session, claim, queue, actor = self.parse_attempt(raw)
        records = tuple(session.records())
        for offset in range(0, len(records), 100):
            self.repository().append_records(preview, claim=claim, records=records[offset : offset + 100], actor=actor)
        receipt = self.receipt_revision(preview, sealed.manifest_sha256, actor)
        output = self.repository().finish_parse(
            preview, claim=claim, session=session, receipt_revision_id=receipt, actor=actor
        )
        queue.stage_artifact(claim, artifact=output, role="output", now=actor.occurred_at)
        queue.complete(claim, now=actor.occurred_at, outputs=(output,))
        return preview, records

    def change(self, preview: str, expected: int, **values):
        from research_observatory_core.ports.import_previews import PreviewDraftChange

        return self.repository().revise_draft(
            preview, PreviewDraftChange(expected_revision=expected, actor=self.actor(), **values)
        )

    def test_group_edit_restart_compare_and_swap_and_undo_preserve_history(self):
        preview, records = self.accepted()
        first = self.change(preview, 0)
        initial = self.repository().draft_page(preview, revision=first.revision, after=0, limit=10)
        self.assertEqual([False, True, True], [row.decision.included for row in initial])
        edits = tuple(review_record(record, included=False, fields=()) for record in records[1:])
        second = self.change(preview, 1, decisions=edits)
        self.assertEqual(2, self.repository().draft(preview).revision)
        self.assertTrue(
            all(
                not row.decision.included
                for row in self.repository().draft_page(preview, revision=second.revision, after=0, limit=10)
            )
        )
        with self.assertRaisesRegex(PreviewProblem, "revision-conflict"):
            self.change(preview, 1, decisions=edits)
        restored = self.change(preview, 2, restore_revision=1)
        self.assertEqual(3, restored.revision)
        self.assertEqual(first.authority, restored.authority)
        self.assertEqual(initial, self.repository().draft_page(preview, revision=3, after=0, limit=10))
        self.assertEqual(
            self.repository().draft_digest(preview, revision=1),
            self.repository().draft_digest(preview, revision=3),
        )
        self.assertNotEqual(
            self.repository().draft_digest(preview, revision=2),
            self.repository().draft_digest(preview, revision=3),
        )
        # Editing after undo must not resurrect decisions on the abandoned branch.
        fourth = self.change(preview, 3, decisions=(edits[0],))
        rows = self.repository().draft_page(preview, revision=fourth.revision, after=1, limit=2)
        self.assertEqual([False, True], [row.decision.included for row in rows])

    def test_mapping_binding_correction_and_exclusion_survive_remapping(self):
        preview, records = self.accepted()
        first = self.change(preview, 0)
        mapping = MappingProfile(
            profile_id=first.authority.mapping.profile_id,
            revision=2,
            predecessor_revision=1,
            mode="columns",
            bindings=(FieldMapping(source_name="heading", occurrence=0, target="title"),),
        )
        # A real normalized source value is still not authority under a different mapping.
        wrong = review_record(
            records[1],
            included=True,
            fields=(MappedField(name="title", value="Alternate", source_field_index=1, origin="mapping"),),
        )
        with self.assertRaisesRegex(PreviewProblem, "mapping-mismatch"):
            self.change(preview, 1, decisions=(wrong,))
        correction = review_record(
            records[1],
            included=True,
            fields=(
                MappedField(name="title", value="Researcher correction", source_field_index=None, origin="correction"),
            ),
        )
        excluded = review_record(records[2], included=False, fields=())
        self.change(preview, 1, decisions=(correction, excluded))
        third = self.change(preview, 2, mapping=mapping)
        rows = self.repository().draft_page(preview, revision=third.revision, after=1, limit=2)
        self.assertEqual("Researcher correction", rows[0].decision.fields[0].value)
        self.assertFalse(rows[1].decision.included)
        self.assertEqual("First", rows[0].record.fields[0].raw_value)
        with self.assertRaisesRegex(PreviewProblem, "mapping-revision"):
            self.change(preview, 3, mapping=mapping.model_copy(update={"profile_id": new_uuid_v7()}))

    def test_substituted_record_rolls_back_entire_group_and_no_canonical_import(self):
        preview, records = self.accepted()
        self.change(preview, 0)
        valid = review_record(records[1], included=False, fields=())
        bad = review_record(records[2], included=False, fields=()).model_copy(update={"record_key": "f" * 64})
        with self.assertRaisesRegex(PreviewProblem, "record-mismatch"):
            self.change(preview, 1, decisions=(valid, bad))
        self.assertEqual(1, self.repository().draft(preview).revision)
        self.assertTrue(self.repository().draft_page(preview, revision=1, after=1, limit=1)[0].decision.included)
        self.repository().cancel(preview, actor=self.actor())
        with self.assertRaises(PreviewProblem):
            self.repository().draft_page(preview, revision=1, after=0, limit=10)

    def test_full_report_includes_mapping_and_exclusion_without_content(self):
        preview, records = self.accepted()
        first = self.change(preview, 0)
        mapping = MappingProfile(
            profile_id=first.authority.mapping.profile_id,
            revision=2,
            predecessor_revision=1,
            mode="columns",
            bindings=(FieldMapping(source_name="absent", occurrence=0, target="title"),),
        )
        self.change(preview, 1, mapping=mapping, decisions=(review_record(records[2], included=False, fields=()),))
        report = "".join(self.repository().diagnostic_report(preview, revision=2))
        self.assertIn("mapping-source-missing", report)
        self.assertIn("excluded", report)
        self.assertIn("3,", report)  # all records, not one currently visible page
        for private in ("First", "Second", "Alternate", "references.csv", records[0].source.sha256):
            self.assertNotIn(private, report)

    def test_current_rights_deny_historical_pages_and_mid_report_retrieval(self):
        preview, _ = self.accepted()
        self.change(preview, 0)
        report = self.repository().diagnostic_report(preview, revision=1)
        next(report)
        self.change(
            preview,
            1,
            rights=ImportRights(
                store=ImportPermission(value="permitted", basis="researcher-confirmed"),
                inspect=ImportPermission(value="denied", basis="researcher-confirmed"),
            ),
        )
        for action in (
            lambda: self.repository().draft_page(preview, revision=1, after=0, limit=10),
            lambda: self.repository().records_page(preview, after=0, limit=10),
            lambda: next(report),
        ):
            with self.assertRaises(PreviewProblem):
                action()

    def test_record_rights_are_not_bypassed_by_raw_or_historical_pages(self):
        preview, records = self.accepted()
        self.change(preview, 0)
        denied = review_record(records[1], included=False, fields=(), rights=ImportRights())
        self.change(preview, 1, decisions=(denied,))
        for action in (
            lambda: self.repository().draft_page(preview, revision=1, after=1, limit=1),
            lambda: self.repository().draft_page(preview, revision=2, after=1, limit=1),
            lambda: self.repository().records_page(preview, after=1, limit=1),
            lambda: self.repository().draft_digest(preview, revision=1),
        ):
            with self.assertRaisesRegex(PreviewProblem, "record-rights-denied"):
                action()
        # Rights on one record do not leak or silently grant another dimension.
        self.assertEqual(3, self.repository().records_page(preview, after=2, limit=1)[0].ordinal)

    def test_undo_cannot_remove_current_record_rights_restrictions(self):
        preview, records = self.accepted()
        self.change(preview, 0)
        denied = review_record(records[1], included=False, fields=(), rights=ImportRights())
        self.change(preview, 1, decisions=(denied,))
        with self.assertRaisesRegex(PreviewProblem, "rights-restore-denied"):
            self.change(preview, 2, restore_revision=1)
        self.assertEqual(2, self.repository().draft(preview).revision)
        for action in (
            lambda: self.repository().records_page(preview, after=1, limit=1),
            lambda: self.repository().draft_page(preview, revision=1, after=1, limit=1),
        ):
            with self.assertRaisesRegex(PreviewProblem, "record-rights-denied"):
                action()

    def test_undo_checks_export_rights_beyond_the_visible_page_and_defaults(self):
        preview, records = self.accepted(b"title\n" + b"Synthetic\n" * 105)
        allowed = fixture.fixture.RIGHTS.model_copy(
            update={
                "export": ImportPermission(value="permitted", basis="researcher-confirmed"),
            }
        )
        restricted = fixture.fixture.RIGHTS
        self.change(preview, 0, rights=allowed)
        self.change(preview, 1, decisions=(review_record(records[-1], included=False, fields=(), rights=restricted),))
        with self.assertRaisesRegex(PreviewProblem, "rights-restore-denied"):
            self.change(preview, 2, restore_revision=1)
        self.change(preview, 2, rights=restricted)
        with self.assertRaisesRegex(PreviewProblem, "rights-restore-denied"):
            self.change(preview, 3, restore_revision=2)
        self.assertEqual(3, self.repository().draft(preview).revision)

    def test_group_decisions_and_complete_report_cross_page_boundaries(self):
        preview, records = self.accepted(b"title\n" + b"Synthetic\n" * 105)
        self.change(preview, 0)
        self.change(
            preview,
            1,
            decisions=tuple(review_record(record, included=False, fields=()) for record in (records[1], records[-1])),
        )
        self.assertFalse(self.repository().draft_page(preview, revision=2, after=105, limit=1)[0].decision.included)
        self.assertTrue(self.repository().draft_page(preview, revision=2, after=104, limit=1)[0].decision.included)
        report = "".join(self.repository().diagnostic_report(preview, revision=2))
        self.assertEqual(2, report.count(",excluded\r\n"))
        self.assertIn("106,", report)
        self.change(preview, 2, restore_revision=1)
        self.assertTrue(self.repository().draft_page(preview, revision=3, after=105, limit=1)[0].decision.included)

    def test_mapping_revision_cannot_be_redefined_after_undo(self):
        preview, _ = self.accepted()
        first = self.change(preview, 0)
        mapping = MappingProfile(
            profile_id=first.authority.mapping.profile_id,
            revision=2,
            predecessor_revision=1,
            mode="columns",
            bindings=(FieldMapping(source_name="heading", occurrence=0, target="title"),),
        )
        self.change(preview, 1, mapping=mapping)
        self.change(preview, 2, restore_revision=1)
        changed = mapping.model_copy(
            update={"bindings": (FieldMapping(source_name="title", occurrence=0, target="title"),)}
        )
        with self.assertRaisesRegex(PreviewProblem, "mapping-revision-conflict"):
            self.change(preview, 3, mapping=changed)
        next_mapping = changed.model_copy(update={"revision": 3, "predecessor_revision": 2})
        self.assertEqual(3, self.change(preview, 3, mapping=next_mapping).authority.mapping.revision)


if __name__ == "__main__":
    unittest.main()
