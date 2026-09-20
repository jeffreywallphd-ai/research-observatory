"""Commit request recovery through the actual project service and durable worker."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ports.import_previews import PreviewDraftChange, PreviewProblem
from research_observatory_core.ports.workflow_executor import WorkflowActor

from tests.service import test_import_summary_workflow as fixture


class ImportCommitServiceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportSummaryWorkflowTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.request = new_uuid_v7()

    def schedule(self, service=None, **extra):
        f = self.fixture
        return (service or f.service).schedule_commit(f.root, f.preview, revision=1, request_id=self.request, **extra)

    def restart(self, epoch=None):
        self.fixture.service.shutdown()
        service = self.fixture.fixture.runtime(epoch)
        self.addCleanup(service.shutdown)
        service.attach(self.fixture.root)
        return service

    def test_service_replays_request_and_worker_commits_after_restart(self):
        job = self.schedule()
        self.assertEqual(job.job_id, self.schedule().job_id)
        restarted = self.restart()
        self.assertEqual(job.job_id, self.schedule(restarted).job_id)
        restarted.run_pending()
        self.assertEqual("succeeded", self.fixture.queue.get(job.job_id).state)
        self.assertEqual(job.job_id, self.schedule(restarted).job_id)

    def test_request_written_before_enqueue_is_recovered_not_lost(self):
        binding = next(iter(self.fixture.service._bindings.values()))
        with (
            patch.object(binding.adapters.queue, "enqueue", side_effect=RuntimeError("synthetic-admission-loss")),
            self.assertRaises(RuntimeError),
        ):
            self.schedule()
        self.assertIsNotNone(self.fixture.repository.commit_request(self.request))
        restarted = self.restart()
        job = self.schedule(restarted)
        restarted.run_pending()
        self.assertEqual("succeeded", self.fixture.queue.get(job.job_id).state)

    def test_changed_request_payload_conflicts_and_preserves_original(self):
        original = self.schedule()
        with self.assertRaises(PreviewProblem):
            self.schedule(previous_manifest_revision_id=new_uuid_v7())
        self.assertEqual(original.job_id, self.schedule().job_id)

    def test_security_epoch_cancels_old_commit_without_automatic_replacement(self):
        job = self.schedule()
        restarted = self.restart("2" * 32)
        restarted.run_pending()
        actual = self.fixture.queue.get(job.job_id)
        self.assertEqual("cancelled", actual.state)
        self.assertEqual(0, actual.attempt_count)
        with self.assertRaises(PreviewProblem):
            self.schedule(restarted)

    def test_concurrent_same_request_has_one_durable_job(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = tuple(pool.map(lambda _: self.schedule(), range(2)))
        self.assertEqual(jobs[0].job_id, jobs[1].job_id)

    def test_preview_cancellation_cancels_queued_commit(self):
        job = self.schedule()
        self.fixture.service.cancel(self.fixture.root, self.fixture.preview, trace_id="4" * 32)
        self.fixture.service.run_pending()
        self.assertEqual("cancelled", self.fixture.queue.get(job.job_id).state)

    def test_changed_draft_before_execution_is_not_silently_adopted(self):
        job = self.schedule()
        f = self.fixture
        f.repository.revise_draft(f.preview, PreviewDraftChange(expected_revision=1, actor=f.actor))
        f.service.run_pending()
        self.assertEqual("failed", f.queue.get(job.job_id).state)
        with self.assertRaises(PreviewProblem):
            self.schedule()

    def test_explicit_cancelled_job_continuation_preserves_saved_command(self):
        job = self.schedule()
        f = self.fixture
        f.queue.request_cancellation(
            job.job_id,
            actor=WorkflowActor(f.fixture.actor, "human", "local-researcher"),
            now=f.fixture.now,
            reason_code="synthetic-cancel",
            interruption_kind="user-cancel",
        )
        f.service.run_pending()
        retry = f.retry(f.queue.get(job.job_id), 1)
        self.assertEqual(retry.job_id, self.schedule().job_id)
        f.service.run_pending()
        self.assertEqual("succeeded", f.queue.get(retry.job_id).state)
