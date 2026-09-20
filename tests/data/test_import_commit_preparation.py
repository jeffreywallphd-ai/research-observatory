"""Real draft/queue staging fences; staged rows never publish canonical imports."""

import unittest
from dataclasses import replace
from pathlib import Path

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.import_commit_repository import SqliteImportCommitRepository
from research_observatory_core.ingestion.commit_workflow import build_commit_job, commit_job_input
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights, review_record
from research_observatory_core.ports.import_previews import PreviewActor, PreviewDraftChange, PreviewProblem
from research_observatory_core.storage import open_canonical_database

from tests.service import test_import_commit_workflow as fixture


class ImportCommitPreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportCommitWorkflowTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.inputs, self.queue = self.fixture.inputs, self.fixture.queue
        self.database = Path(self.fixture.fixture.root) / "state/project.sqlite3"
        self.repository = SqliteImportCommitRepository(self.database, self.inputs.project_id)
        self.job = self.fixture.enqueue()
        self.claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.fixture.now,
            lease_duration_ms=30000,
            activity_types=("local-import-commit",),
        )
        self.queue.start(self.claim, now=self.fixture.now)
        self.actor = PreviewActor(actor_id=self.claim.worker_id, trace_id="4" * 32, occurred_at=self.fixture.now)

    def begin(self, inputs=None, claim=None):
        self.repository.begin_commit(inputs or self.inputs, claim=claim or self.claim, actor=self.actor)

    def test_immutable_request_reopens_exactly_and_rejects_changed_command_or_actor(self):
        self.assertIsNone(self.repository.commit_request(self.inputs.request_id))
        saved = self.repository.save_commit_request(self.inputs, actor=self.fixture.fixture.actor)
        reopened = SqliteImportCommitRepository(self.database, self.inputs.project_id)
        self.assertEqual(saved, reopened.commit_request(self.inputs.request_id))
        self.assertEqual(saved, reopened.save_commit_request(self.inputs, actor=self.fixture.fixture.actor))
        changed = self.inputs.model_copy(update={"previous_manifest_revision_id": new_uuid_v7()})
        with self.assertRaises(PreviewProblem):
            reopened.save_commit_request(changed, actor=self.fixture.fixture.actor)
        with self.assertRaises(PreviewProblem):
            reopened.save_commit_request(self.inputs, actor=self.actor)

    def test_extra_request_revision_is_rejected_not_latest_wins(self):
        saved = self.repository.save_commit_request(self.inputs, actor=self.fixture.fixture.actor)
        with open_canonical_database(self.database, expected_project_id=self.inputs.project_id) as db:
            db.execute(
                "INSERT INTO settings VALUES (?,?,?,1,'text',?,NULL,NULL,NULL,?,?)",
                (
                    new_uuid_v7(),
                    self.inputs.project_id,
                    "imports.commit-request." + self.inputs.request_id,
                    saved.model_dump_json(by_alias=True),
                    self.actor.occurred_at,
                    self.actor.occurred_at,
                ),
            )
        with self.assertRaises(PreviewProblem):
            self.repository.commit_request(self.inputs.request_id)

    def append(self, after=0):
        return self.repository.append_commit_page(self.inputs, after=after, claim=self.claim, actor=self.actor)

    def test_complete_staging_replays_begin_but_is_not_canonical_publication(self):
        self.begin()
        self.begin()
        with self.assertRaises(PreviewProblem):
            self.repository.prepared_identity(self.inputs, claim=self.claim, actor=self.actor)
        count = self.append()
        self.assertEqual(self.inputs.record_count, count)
        identity = self.repository.prepared_identity(self.inputs, claim=self.claim, actor=self.actor)
        self.assertEqual(count, identity.record_count)
        self.assertEqual(1, identity.selected_count)
        with self.assertRaises(PreviewProblem):
            self.append()
        with open_canonical_database(self.database, expected_project_id=self.inputs.project_id) as db:
            for table in ("import_source_records", "import_manifests", "import_manifest_members"):
                self.assertEqual(0, db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        self.assertEqual("running", self.queue.get(self.job.job_id).state)

    def test_substituted_claim_or_inputs_and_stale_draft_are_denied(self):
        with self.assertRaises(PreviewProblem):
            self.begin(claim=replace(self.claim, command_fingerprint="sha256:" + "f" * 64))
        with self.assertRaises(PreviewProblem):
            self.begin(inputs=self.inputs.model_copy(update={"request_id": new_uuid_v7()}))
        self.begin()
        self.fixture.fixture.repository.revise_draft(
            self.inputs.preview.preview_id,
            PreviewDraftChange(expected_revision=1, actor=self.fixture.fixture.actor),
        )
        with self.assertRaises(PreviewProblem):
            self.append()

    def test_expired_lease_denies_staging(self):
        self.begin()
        expired = self.actor.model_copy(update={"occurred_at": "2099-01-01T00:00:00.000Z"})
        with self.assertRaises(PreviewProblem):
            self.repository.append_commit_page(self.inputs, after=0, claim=self.claim, actor=expired)

    def test_cancellation_denies_staging_and_identity(self):
        self.begin()
        self.append()
        self.queue.request_cancellation(
            self.job.job_id,
            actor=self.fixture.actor,
            now=self.fixture.now,
            reason_code="synthetic-cancel",
            interruption_kind="user-cancel",
        )
        with self.assertRaises(PreviewProblem):
            self.repository.prepared_identity(self.inputs, claim=self.claim, actor=self.actor)

    def test_excluded_denied_record_cannot_be_retained_as_commit_decision(self):
        self.queue.cancel(self.claim, now=self.fixture.now, reason_code="synthetic-replace")
        preview = self.inputs.preview.preview_id
        record = self.repository.records_page(preview, after=0, limit=100)[-1]
        draft = self.repository.revise_draft(
            preview,
            PreviewDraftChange(
                expected_revision=1,
                actor=self.fixture.fixture.actor,
                decisions=(
                    review_record(
                        record,
                        included=False,
                        fields=(),
                        rights=ImportRights(
                            store=ImportPermission(value="denied", basis="researcher-confirmed"),
                            inspect=ImportPermission(value="permitted", basis="researcher-confirmed"),
                        ),
                    ),
                ),
            ),
        )
        self.inputs = commit_job_input(
            self.repository.read(preview),
            draft,
            self.inputs.intent,
            self.inputs.preview.policy_hash,
            self.inputs.preview.resume_epoch,
            request_id=new_uuid_v7(),
        )
        self.queue.enqueue(
            build_commit_job(self.inputs, actor=self.fixture.actor, now=self.fixture.now), actor=self.fixture.actor
        )
        self.claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.fixture.now,
            lease_duration_ms=30000,
            activity_types=("local-import-commit",),
        )
        self.queue.start(self.claim, now=self.fixture.now)
        self.actor = self.actor.model_copy(update={"actor_id": self.claim.worker_id})
        self.begin()
        with self.assertRaises(PreviewProblem):
            self.append()
        with open_canonical_database(self.database, expected_project_id=self.inputs.project_id) as db:
            self.assertEqual(0, db.execute("SELECT count(*) FROM import_commit_rows").fetchone()[0])
