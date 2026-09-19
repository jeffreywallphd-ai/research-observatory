"""Persistent researcher decisions over real accepted preview attempts."""

from __future__ import annotations

import sqlite3
import time
import unittest
from contextlib import closing
from unittest.mock import patch

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

    def test_undo_resolves_rights_setwise_instead_of_per_ordinal_history_queries(self):
        preview, records = self.accepted(b"title\n" + b"Synthetic\n" * 300)
        self.change(preview, 0)
        for index in range(3):
            self.change(
                preview,
                index + 1,
                decisions=tuple(
                    review_record(record, included=False, fields=())
                    for record in records[1 + index * 100 : 101 + index * 100]
                ),
            )
        repository = self.repository()
        from research_observatory_core.ports.import_previews import PreviewDraftChange

        with patch.object(repository, "_decision", side_effect=AssertionError("per-record undo history lookup")):
            restored = repository.revise_draft(
                preview, PreviewDraftChange(expected_revision=4, restore_revision=1, actor=self.actor())
            )
        self.assertEqual(5, restored.revision)
        self.assertIsNone(restored.undo_target_revision)
        self.assertTrue(
            all(row.decision.included for row in repository.draft_page(preview, revision=5, after=200, limit=100))
        )

    def test_page_resolves_history_once_and_preserves_abandoned_branch_semantics(self):
        preview, records = self.accepted()
        self.change(preview, 0)
        edits = tuple(review_record(record, included=False, fields=()) for record in records[1:])
        self.change(preview, 1, decisions=edits)
        self.change(preview, 2, restore_revision=1)
        self.change(preview, 3, decisions=(edits[0],))
        repository = self.repository()
        with patch.object(repository, "_decision", side_effect=AssertionError("per-record page history lookup")):
            for revision, expected in ((1, [True, True]), (2, [False, False]), (3, [True, True]), (4, [False, True])):
                rows = repository.draft_page(preview, revision=revision, after=1, limit=2)
                self.assertEqual(expected, [row.decision.included for row in rows])

    def test_page_key_selection_matches_scalar_history_for_every_retained_revision(self):
        preview, records = self.accepted(b"title\nOne\nTwo\nThree\nFour\n")
        self.change(preview, 0)
        for index, ordinal in enumerate((2, 3, 2, 4)):
            self.change(
                preview,
                index + 1,
                decisions=(review_record(records[ordinal - 1], included=False, fields=()),),
            )
        self.change(preview, 5, restore_revision=2)
        self.change(preview, 6, decisions=(review_record(records[4], included=False, fields=()),))
        repository = self.repository()
        with repository._transaction(preview) as connection:
            state = repository._read(connection, preview)
            for revision in range(1, 8):
                draft = repository._draft(connection, state, revision)
                expected = tuple(
                    repository._project_row(
                        repository._record(connection, state, draft.attempt_id, record.ordinal),
                        draft,
                        *repository._decision(connection, preview, revision, record.ordinal),
                    )
                    for record in records
                )
                self.assertEqual(expected, repository.draft_page(preview, revision=revision, after=0, limit=100))

    def test_page_byte_limit_stops_before_loading_later_decisions(self):
        preview, records = self.accepted(b"title\nOne\nTwo\nThree\n")
        self.change(preview, 0)
        denied = ImportRights(inspect=ImportPermission(value="denied", basis="researcher-confirmed"))
        self.change(preview, 1, decisions=(review_record(records[3], included=False, fields=(), rights=denied),))
        repository = self.repository()
        with patch(
            "research_observatory_core.import_draft_repository.StoredImportRecord.model_dump_json",
            return_value="x" * (8 * 1024 * 1024),
        ):
            rows = repository.draft_page(preview, revision=1, after=0, limit=100)
        self.assertEqual([1], [row.record.ordinal for row in rows])
        with self.assertRaisesRegex(PreviewProblem, "record-rights-denied"):
            repository.draft_page(preview, revision=1, after=3, limit=1)

    def test_setwise_undo_preserves_each_action_restriction_outside_visible_page(self):
        allowed = ImportRights.model_validate(
            {
                action: {"value": "permitted", "basis": "researcher-confirmed"}
                for action in ("store", "inspect", "index", "derive", "model-use", "quote", "export", "share")
            }
        )
        preview, records = self.accepted(b"title\n" + b"Synthetic\n" * 30)
        self.change(preview, 0, rights=allowed)
        # Explicit reset is allowed while inspect remains permitted; inspect is last.
        for action in ("store", "index", "derive", "model-use", "quote", "export", "share", "inspect"):
            with self.subTest(action=action):
                before = self.repository().draft(preview).revision
                restricted = ImportRights.model_validate(
                    {**allowed.model_dump(by_alias=True), action: {"value": "denied", "basis": "researcher-confirmed"}}
                )
                self.change(
                    preview,
                    before,
                    decisions=(review_record(records[-1], included=False, fields=(), rights=restricted),),
                )
                with self.assertRaisesRegex(PreviewProblem, "rights-restore-denied"):
                    self.change(preview, before + 1, restore_revision=before)
                self.assertEqual(before + 1, self.repository().draft(preview).revision)
                if action != "inspect":
                    self.change(
                        preview,
                        before + 1,
                        decisions=(review_record(records[-1], included=False, fields=(), rights=allowed),),
                    )

    def test_undo_query_handles_100k_decisions_and_10k_revisions(self):
        # Isolated query-scale proof, not a canonical 100k project/import benchmark.
        # The adjacent tests exercise actual accepted records, immutable history
        # and all rights through the production repository and authenticated API.
        preview, _ = self.accepted()
        initial = self.change(preview, 0)
        rights = initial.authority.rights.model_dump_json(by_alias=True)
        project = initial.authority.project_id
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute(
                "CREATE TABLE import_draft_revisions (preview_id TEXT, project_id TEXT, revision INTEGER, "
                "predecessor_revision INTEGER, undo_revision INTEGER, PRIMARY KEY(preview_id, project_id, revision))"
            )
            connection.execute(
                "CREATE TABLE import_record_decisions (preview_id TEXT, project_id TEXT, revision INTEGER, "
                "ordinal INTEGER, decision_json TEXT, PRIMARY KEY(preview_id, project_id, revision, ordinal))"
            )
            connection.executemany(
                "INSERT INTO import_draft_revisions VALUES (?, ?, ?, ?, NULL)",
                ((preview, project, revision, revision - 1 if revision > 1 else None) for revision in range(1, 10002)),
            )
            connection.executemany(
                "INSERT INTO import_record_decisions VALUES (?, ?, ?, ?, ?)",
                (
                    (preview, project, (ordinal - 1) // 10 + 2, ordinal, '{"rights":' + rights + "}")
                    for ordinal in range(1, 100001)
                ),
            )
            current = initial.model_copy(update={"revision": 10001})
            restored = initial.model_copy(update={"revision": 10000})
            start = time.perf_counter()
            self.repository()._restore_rights(connection, preview, current, restored)
            elapsed = time.perf_counter() - start
            print(f"Synthetic undo query: 100000 decisions, 10001 revisions, {elapsed:.3f}s; in-memory query only")
            # Restriction at the far end must not be lost by the sparse optimization.
            denied = initial.authority.rights.model_copy(
                update={"inspect": ImportPermission(value="denied", basis="researcher-confirmed")}
            )
            connection.execute(
                "UPDATE import_record_decisions SET decision_json=? WHERE ordinal=100000",
                ('{"rights":' + denied.model_dump_json(by_alias=True) + "}",),
            )
            with self.assertRaisesRegex(PreviewProblem, "rights-restore-denied"):
                self.repository()._restore_rights(connection, preview, current, restored)

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
