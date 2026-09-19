"""Exact import job binding and real durable-supervisor integration."""

from __future__ import annotations

import hashlib
import itertools
import json
import unittest
from dataclasses import replace

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.preview_workflow import (
    ACTIVITY,
    PreviewIntentContext,
    bind_preview_claim,
    build_preview_job,
    preview_job_input,
)
from research_observatory_core.ports.import_previews import PreviewActor, PreviewProblem
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_workflow_admission_binding,
    sqlite_workflow_queue_repository,
)
from research_observatory_core.workflow_contracts import workflow_snapshot_errors
from research_observatory_core.workflow_executor import (
    LocalAdmissionController,
    LocalWorkerSupervisor,
    ProjectWorkerPolicy,
    WorkerCapacity,
    WorkerResources,
    prepare_workflow_job,
)

from tests.data import test_import_preview_repository as fixture


class ImportPreviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportPreviewRepositoryTests(methodName="runTest")
        lifecycle: unittest.TestCase = self.fixture
        lifecycle.setUp()
        self.addCleanup(lifecycle.tearDown)
        raw = b"title,doi\nSynthetic,10.99999/EXAMPLE\n"
        self.preview = self.fixture.create()
        for ordinal, chunk in enumerate(self.fixture.retain(raw), 1):
            self.fixture.repository().append_chunk(self.preview, ordinal=ordinal, chunk=chunk)
        self.state = self.fixture.repository().seal(
            self.preview,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            actor=self.fixture.actor(),
        )
        # Explicit synthetic references here; runtime composition must obtain
        # actual validated project-created intent and current privacy policy.
        self.intent = PreviewIntentContext(
            project_id=self.state.project_id,
            domain_project_id=new_uuid_v7(),
            intent_id=new_uuid_v7(),
            revision_id=new_uuid_v7(),
            content_hash="sha256:" + "1" * 64,
            status="draft",
        )
        self.policy = "sha256:" + "2" * 64
        self.epoch = "3" * 32
        self.input = preview_job_input(self.state, self.intent, self.policy, self.epoch)
        self.now = "2026-08-30T12:02:00.000Z"

    def submission(self):
        return build_preview_job(self.input, actor=fixture.worker_fixture.SYSTEM, now=self.now)

    def claimed(self):
        submission = self.submission()
        queue = sqlite_workflow_queue_repository(self.fixture.project, self.state.project_id)
        queue.enqueue(submission, actor=fixture.worker_fixture.SYSTEM)
        claim = queue.claim_next(
            worker_id=fixture.worker_fixture.WORKER_A,
            concurrency_classes=("document",),
            now=self.now,
            lease_duration_ms=30_000,
        )
        assert claim is not None
        return queue, claim

    def test_draft_context_and_exact_declarative_local_authority(self):
        submission = self.submission()
        definition, snapshot = json.loads(submission.definition_json), json.loads(submission.snapshot_json)
        self.assertEqual((), workflow_snapshot_errors(definition, snapshot))
        self.assertEqual(self.intent.revision_id, snapshot["intent"]["revisionId"])
        self.assertEqual("draft", self.input.intent.status)
        self.assertEqual("unknown", submission.progress_total_kind)
        self.assertEqual("records", submission.progress_unit)
        permissions = definition["steps"][0]["permissions"]
        self.assertEqual("none", permissions["network"])
        self.assertEqual("none", permissions["model"])
        self.assertNotIn(self.state.source_name, submission.snapshot_json)
        self.assertEqual([], snapshot["artifacts"])
        self.assertEqual(5, len(snapshot["history"]))

    def test_reloaded_claim_binds_source_intent_policy_epoch_and_worker_identity(self):
        queue, claim = self.claimed()
        authority = queue.authority(claim.job_id)
        self.assertEqual(self.input, bind_preview_claim(authority, claim, self.input))
        for changed in (
            self.input.model_copy(update={"source_sha256": "4" * 64}),
            self.input.model_copy(update={"resume_epoch": "4" * 32}),
            self.input.model_copy(update={"policy_hash": "sha256:" + "4" * 64}),
            self.input.model_copy(update={"intent": self.intent.model_copy(update={"status": "accepted"})}),
            self.input.model_copy(update={"project_id": new_uuid_v7()}),
        ):
            with self.subTest(changed=changed.model_dump()), self.assertRaises(PreviewProblem):
                bind_preview_claim(authority, claim, changed)
        with self.assertRaises(PreviewProblem):
            bind_preview_claim(authority, replace(claim, job_id=new_uuid_v7()), self.input)

    def test_cross_project_intent_and_unsealed_source_are_denied(self):
        with self.assertRaises(PreviewProblem):
            preview_job_input(
                self.state, self.intent.model_copy(update={"project_id": new_uuid_v7()}), self.policy, self.epoch
            )
        with self.assertRaises(PreviewProblem):
            preview_job_input(
                self.state.model_copy(update={"source_sha256": None}), self.intent, self.policy, self.epoch
            )

    def supervisor(self, queue, *, capacity=None, guard=None):
        from research_observatory_core.ingestion.preview_activity import ImportPreviewActivity

        ticks = itertools.count(0, 6)
        activity = ImportPreviewActivity(
            preview_id=self.preview,
            repository=self.fixture.repository(),
            store=self.fixture.store(),
            unit_of_work=create_sqlite_unit_of_work_factory(
                self.fixture.project / "state/project.sqlite3", self.state.project_id
            ),
            guard=guard or (lambda action: action()),
            trace_id="5" * 32,
            clock=lambda: float(next(ticks)),
        )

        def handler(context, claim):
            bind_preview_claim(queue.authority(claim.job_id), claim, self.input)
            return activity(context, claim)

        demand = WorkerResources(1, 64 * 1024 * 1024, 0, 1024 * 1024)
        controller = LocalAdmissionController(interactive_reserve=demand)
        admission = sqlite_workflow_admission_binding(
            queue,
            controller=controller,
            policy=ProjectWorkerPolicy(self.state.project_id, demand, {"document": demand}, {"document": 1}),
        )
        # Actual volume/database binding; deterministic capacity observations,
        # not a claim about platform resource measurements.
        admission = replace(admission, capacity=capacity or (lambda: WorkerCapacity(4, 1024**3, 0, 1024**3)))
        return LocalWorkerSupervisor(
            queue,
            {ACTIVITY: handler},
            concurrency_limits={"document": 1},
            now=lambda: self.now,
            recovery_actor=fixture.worker_fixture.SYSTEM,
            admission=admission,
            activity_types=(ACTIVITY,),
        )

    def test_import_worker_does_not_claim_other_document_activities(self):
        queue = sqlite_workflow_queue_repository(self.fixture.project, self.state.project_id)
        definition, snapshot, other_job = fixture.worker_fixture.runnable_contracts()
        snapshot["projectId"] = self.state.project_id
        queue.enqueue(
            prepare_workflow_job(
                definition,
                snapshot,
                job_id=other_job,
                concurrency_class="document",
                priority=100,
                available_at=self.now,
            ),
            actor=fixture.worker_fixture.SYSTEM,
        )
        submission = self.submission()
        imported = queue.enqueue(submission, actor=fixture.worker_fixture.SYSTEM)
        self.assertEqual(imported, queue.find_idempotency(submission.idempotency_key))
        self.assertIsNone(queue.find_idempotency("sha256:" + "f" * 64))
        self.assertEqual((imported,), queue.active_jobs(activity_type=ACTIVITY, after=None, limit=1))
        self.assertEqual((), queue.active_jobs(activity_type=ACTIVITY, after=imported.job_id, limit=1))
        self.assertEqual("succeeded", self.supervisor(queue).run_available()[0].state)
        self.assertEqual(0, queue.get(other_job).attempt_count)
        self.assertEqual((), queue.active_jobs(activity_type=ACTIVITY, after=None, limit=1))

    def test_supervisor_admission_heartbeat_receipt_and_completed_preview(self):
        queue = sqlite_workflow_queue_repository(self.fixture.project, self.state.project_id)
        job = queue.enqueue(self.submission(), actor=fixture.worker_fixture.SYSTEM)
        starved = self.supervisor(queue, capacity=lambda: WorkerCapacity(1, 1, 0, 1))
        self.assertEqual((), starved.run_available())
        self.assertEqual(0, queue.get(job.job_id).attempt_count)
        completed = self.supervisor(queue).run_available()
        self.assertEqual("succeeded", completed[0].state, completed[0].diagnostic_code)
        self.assertEqual(2, len(self.fixture.repository().records_page(self.preview, after=0, limit=10)))
        self.assertEqual((), self.supervisor(queue).run_available())
        self.assertEqual(1, queue.get(job.job_id).attempt_count)

    def test_expired_ordinary_attempt_replays_from_immutable_source(self):
        queue, first = self.claimed()
        queue.start(first, now=self.now)
        self.fixture.repository().begin_parse(
            self.preview,
            claim=first,
            actor=PreviewActor(actor_id=first.worker_id, trace_id="5" * 32, occurred_at=self.now),
        )
        self.now = "2026-08-30T12:03:00.000Z"
        self.assertEqual("succeeded", self.supervisor(queue).run_available()[0].state)
        self.assertEqual(2, queue.get(first.job_id).attempt_count)
        self.assertEqual((), self.supervisor(queue).run_available())

    def test_security_cancel_fences_pending_parse_and_late_outputs(self):
        queue, first = self.claimed()
        queue.start(first, now=self.now)
        queue.request_cancellation(
            first.job_id,
            actor=fixture.worker_fixture.SYSTEM,
            now=self.now,
            reason_code="application-locked",
            interruption_kind="security-lock",
        )
        self.now = "2026-08-30T12:04:00.000Z"
        self.assertEqual((), self.supervisor(queue).run_available())
        self.assertEqual("cancelled", queue.get(first.job_id).state)
        self.assertEqual(1, queue.get(first.job_id).attempt_count)
        with self.assertRaises(PreviewProblem):
            self.fixture.repository().records_page(self.preview, after=0, limit=10)


if __name__ == "__main__":
    unittest.main()
