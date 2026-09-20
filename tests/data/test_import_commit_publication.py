"""Atomic canonical import publication over real queue, provenance and storage."""

import json
import unittest
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.commit_workflow import build_commit_job, commit_job_input
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights, MappedField
from research_observatory_core.ports.import_previews import PreviewDraftChange, PreviewProblem
from research_observatory_core.repositories import _revision_with_connection
from research_observatory_core.storage import open_canonical_database

from tests.data import test_import_commit_preparation as fixture


class ImportCommitPublicationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportCommitPreparationTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.begin()

    def publish(self, clock=None):
        f = self.fixture
        with open_canonical_database(f.database, expected_project_id=f.inputs.project_id) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM import_commit_rows WHERE attempt_id=?", (f.claim.attempt_id,)
            ).fetchone()[0]
        if count == 0:
            f.append()
        return f.repository.publish_commit(
            f.inputs, claim=f.claim, actor=f.actor, now=clock or (lambda: f.actor.occurred_at)
        )

    def counts(self):
        f = self.fixture
        with open_canonical_database(f.database, expected_project_id=f.inputs.project_id) as db:
            return tuple(
                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "aggregate_revisions",
                    "provenance_events",
                    "outbox_events",
                    "import_source_records",
                    "import_manifests",
                    "import_manifest_members",
                    "import_manifest_seals",
                    "workflow_committed_outputs",
                )
            )

    def prepare_another(self, raw=None, previous=None, correct_title=False):
        f = self.fixture
        if raw is None:
            inputs = f.inputs.model_copy(update={"request_id": new_uuid_v7()})
        else:
            service_fixture = f.fixture.fixture.fixture
            preview = service_fixture.intake(raw)
            service_fixture.service.schedule(service_fixture.root, preview)
            service_fixture.service.run_pending()
            draft = f.repository.revise_draft(
                preview,
                PreviewDraftChange(
                    expected_revision=0,
                    actor=f.fixture.fixture.actor,
                ),
            )
            if correct_title:
                item = f.repository.draft_page(preview, revision=1, after=0, limit=100)[-1]
                fields = (
                    *(field for field in item.decision.fields if field.name != "title"),
                    MappedField(
                        name="title", value="Researcher correction", source_field_index=None, origin="correction"
                    ),
                )
                draft = f.repository.revise_draft(
                    preview,
                    PreviewDraftChange(
                        expected_revision=1,
                        actor=f.fixture.fixture.actor,
                        decisions=(item.decision.model_copy(update={"fields": fields}),),
                    ),
                )
            inputs = commit_job_input(
                f.repository.read(preview),
                draft,
                f.inputs.intent,
                f.inputs.preview.policy_hash,
                f.inputs.preview.resume_epoch,
                request_id=new_uuid_v7(),
                previous_manifest_revision_id=previous,
            )
        f.inputs = inputs
        f.job = f.queue.enqueue(
            build_commit_job(inputs, actor=f.fixture.actor, now=f.fixture.now), actor=f.fixture.actor
        )
        f.claim = f.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=f.fixture.now,
            lease_duration_ms=30000,
            activity_types=("local-import-commit",),
        )
        f.queue.start(f.claim, now=f.fixture.now)
        f.actor = f.actor.model_copy(update={"actor_id": f.claim.worker_id})
        f.begin()
        f.append()

    def test_same_scientific_import_reuses_manifest_and_records(self):
        first = self.publish()
        self.prepare_another()
        second = self.publish()
        self.assertEqual(first, second)
        self.assertEqual((1, 1, 2, 1), self.counts()[3:7])

    def test_lost_reply_replays_without_new_facts(self):
        first = self.publish()
        before = self.counts()
        self.assertEqual(first, self.publish())
        self.assertEqual(before, self.counts())

    def test_comparison_denies_current_predecessor_record_rights_revocation(self):
        original = self.publish()
        f = self.fixture
        preview = f.inputs.preview.preview_id
        item = f.repository.draft_page(preview, revision=1, after=0, limit=100)[-1]
        f.repository.revise_draft(
            preview,
            PreviewDraftChange(
                expected_revision=1,
                actor=f.fixture.fixture.actor,
                decisions=(
                    item.decision.model_copy(
                        update={
                            "rights": ImportRights(
                                store=ImportPermission(value="permitted", basis="researcher-confirmed"),
                                inspect=ImportPermission(value="denied", basis="researcher-confirmed"),
                            )
                        }
                    ),
                ),
            ),
        )
        with self.assertRaises(PreviewProblem):
            f.repository.draft_page(preview, revision=1, after=0, limit=100)
        self.prepare_another(b"title,doi\nChanged title,10.99999/EXAMPLE\n", previous=original.revision_id)
        before = self.counts()
        with self.assertRaises(PreviewProblem):
            self.publish()
        self.assertEqual(before, self.counts())

    def test_generic_completed_receipt_is_not_an_import_manifest_replay(self):
        f = self.fixture
        f.append()
        with open_canonical_database(f.database, expected_project_id=f.inputs.project_id) as db:
            revision = db.execute(
                "SELECT receipt_revision_id FROM import_parse_completions WHERE attempt_id=?",
                (f.inputs.parse_attempt_id,),
            ).fetchone()[0]
            output = f.repository._output(_revision_with_connection(db, f.inputs.project_id, revision))
        f.queue.stage_artifact(f.claim, artifact=output, role="output", now=f.actor.occurred_at)
        f.queue.complete(f.claim, now=f.actor.occurred_at, outputs=(output,))
        before = self.counts()
        with self.assertRaises(PreviewProblem):
            self.publish()
        self.assertEqual(before, self.counts())

    def test_forged_prepared_selection_cannot_override_actual_draft(self):
        f = self.fixture
        page = f.repository.draft_page(f.inputs.preview.preview_id, revision=1, after=0, limit=100)
        with open_canonical_database(f.database, expected_project_id=f.inputs.project_id) as db:
            for item in page:
                substituted = item.decision.model_copy(update={"included": False})
                db.execute(
                    "INSERT INTO import_commit_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f.claim.attempt_id,
                        f.inputs.project_id,
                        f.inputs.preview.preview_id,
                        f.inputs.parse_attempt_id,
                        item.record.ordinal,
                        item.record.record_key,
                        0,
                        substituted.model_dump_json(by_alias=True),
                        json.dumps(item.warnings, separators=(",", ":")),
                        item.record.raw_sha256,
                        None,
                    ),
                )
        before = self.counts()
        with self.assertRaises(PreviewProblem):
            self.publish()
        self.assertEqual(before, self.counts())

    def test_same_file_new_preview_reuses_source_assertion_ids(self):
        self.publish()
        with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.inputs.project_id) as db:
            first = db.execute("SELECT revision_id FROM import_source_records").fetchone()[0]
        self.prepare_another(b"title,doi\nSynthetic,10.99999/EXAMPLE\n")
        self.publish()
        with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.inputs.project_id) as db:
            self.assertEqual(
                [(first,)], [tuple(row) for row in db.execute("SELECT revision_id FROM import_source_records")]
            )

    def test_changed_file_retains_old_assertion_and_explains_update(self):
        original = self.publish()
        self.prepare_another(b"title,doi\nChanged title,10.99999/EXAMPLE\n", previous=original.revision_id)
        changed = self.publish()
        self.assertNotEqual(original.revision_id, changed.revision_id)
        self.assertEqual((2, 2, 4, 2), self.counts()[3:7])
        with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.inputs.project_id) as db:
            comparison = db.execute(
                "SELECT comparison, previous_record_revision_id FROM import_manifest_members "
                "WHERE manifest_revision_id=? AND included=1",
                (changed.revision_id,),
            ).fetchone()
            self.assertEqual("updated", comparison[0])
            self.assertIsNotNone(comparison[1])

    def test_equal_raw_bytes_do_not_hide_changed_accepted_mapping(self):
        original = self.publish()
        self.prepare_another(
            b"title,doi\nSynthetic,10.99999/EXAMPLE\n", previous=original.revision_id, correct_title=True
        )
        updated = self.publish()
        with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.inputs.project_id) as db:
            self.assertEqual(
                "updated",
                db.execute(
                    "SELECT comparison FROM import_manifest_members WHERE manifest_revision_id=? AND included=1",
                    (updated.revision_id,),
                ).fetchone()[0],
            )
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM import_source_records").fetchone()[0])

    def test_publication_commits_manifest_records_provenance_and_worker_output(self):
        before = self.counts()
        output = self.publish()
        after = self.counts()
        self.assertEqual(2, after[0] - before[0])
        self.assertGreater(after[1], before[1])
        self.assertGreater(after[2], before[2])
        self.assertEqual((1, 1, 2, 1, before[-1] + 1), after[3:])
        self.assertEqual("succeeded", self.fixture.queue.get(self.fixture.job.job_id).state)
        with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.inputs.project_id) as db:
            self.assertEqual(output.revision_id, db.execute("SELECT revision_id FROM import_manifests").fetchone()[0])
            self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())

    def test_multiple_current_candidates_are_not_reported_as_certain_updates(self):
        original = self.publish()
        self.prepare_another(
            b"title,doi\nChanged A,10.99999/EXAMPLE\nChanged B,10.99999/EXAMPLE\n", previous=original.revision_id
        )
        result = self.publish()
        with open_canonical_database(self.fixture.database, expected_project_id=self.fixture.inputs.project_id) as db:
            self.assertEqual(
                [("ambiguous", None), ("ambiguous", None)],
                [
                    tuple(row)
                    for row in db.execute(
                        "SELECT comparison, previous_record_revision_id FROM import_manifest_members "
                        "WHERE manifest_revision_id=? AND included=1 ORDER BY ordinal",
                        (result.revision_id,),
                    )
                ],
            )

    def test_material_failures_roll_back_entire_publication(self):
        before = self.counts()
        for boundary in (
            "source-record-created",
            "manifest-created",
            "manifest-member-created",
            "manifest-sealed",
            "output-staged",
            "output-completed",
        ):

            def fail(step, expected=boundary):
                if step == expected:
                    raise ValueError("synthetic-publication-interruption")

            with self.subTest(boundary=boundary):
                with (
                    patch("research_observatory_core.import_commit_repository._publication_step_completed", fail),
                    self.assertRaises(PreviewProblem),
                ):
                    self.publish()
                self.assertEqual(before, self.counts())
                self.assertEqual("running", self.fixture.queue.get(self.fixture.job.job_id).state)
        self.publish()
        self.assertEqual("succeeded", self.fixture.queue.get(self.fixture.job.job_id).state)

    def test_expiration_during_publication_uses_fresh_time_and_rolls_back(self):
        before = self.counts()
        expired = False

        def advance(step):
            nonlocal expired
            if step == "manifest-sealed":
                expired = True

        def clock():
            return "2099-01-01T00:00:00.000Z" if expired else self.fixture.actor.occurred_at

        with (
            patch("research_observatory_core.import_commit_repository._publication_step_completed", advance),
            self.assertRaises(PreviewProblem),
        ):
            self.publish(clock)
        self.assertTrue(expired)
        self.assertEqual(before, self.counts())

    def test_more_than_64_records_have_complete_manifest_membership(self):
        self.publish()
        raw = ("title,doi\n" + "".join(f"Synthetic {index},10.99999/{index}\n" for index in range(101))).encode()
        self.prepare_another(raw)
        f = self.fixture
        f.append(after=100)
        output = self.publish()
        with open_canonical_database(f.database, expected_project_id=f.inputs.project_id) as db:
            self.assertEqual(
                (102, 101),
                tuple(
                    db.execute(
                        "SELECT COUNT(*), SUM(included) FROM import_manifest_members WHERE manifest_revision_id=?",
                        (output.revision_id,),
                    ).fetchone()
                ),
            )
            self.assertEqual(
                101,
                db.execute(
                    "SELECT COUNT(DISTINCT source_record_revision_id) FROM import_manifest_members "
                    "WHERE manifest_revision_id=?",
                    (output.revision_id,),
                ).fetchone()[0],
            )

    def test_cancel_before_publication_leaves_canonical_state_unchanged(self):
        f = self.fixture
        f.append()
        before = self.counts()
        f.queue.request_cancellation(
            f.job.job_id,
            actor=f.fixture.actor,
            now=f.fixture.now,
            reason_code="synthetic-cancel",
            interruption_kind="user-cancel",
        )
        with self.assertRaises(PreviewProblem):
            self.publish()
        self.assertEqual(before, self.counts())
