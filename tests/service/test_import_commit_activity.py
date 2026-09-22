"""Real commit activity/repository boundary with isolated development storage."""

import unittest
from itertools import count
from unittest.mock import patch

from research_observatory_core.ingestion.commit_activity import ImportCommitActivity
from research_observatory_core.ports.import_previews import PreviewProblem
from research_observatory_core.storage import open_canonical_database
from research_observatory_core.workflow_executor import (
    WorkflowActivityContext,
    WorkflowActivityError,
    WorkflowCancellationRequested,
)

from tests.data import test_import_commit_preparation as preparation


class ImportCommitActivityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = preparation.ImportCommitPreparationTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.context = WorkflowActivityContext(
            self.fixture.queue, self.fixture.claim, lambda: self.fixture.fixture.now, 30000
        )
        self.activity = ImportCommitActivity(
            inputs=self.fixture.inputs,
            repository=self.fixture.repository,
            guard=lambda action: action(),
            trace_id="4" * 32,
        )

    def test_activity_accepts_canonical_manifest_and_exact_worker_output(self):
        completion = self.activity(self.context, self.fixture.claim)
        self.assertEqual("succeeded", self.fixture.queue.get(self.fixture.job.job_id).state)
        receipt = self.fixture.queue.complete(self.context.claim, now=self.context.now(), outputs=completion.outputs)
        self.assertTrue(receipt.replayed)
        self.assertEqual(1, len(completion.outputs))

    def test_cancelled_activity_does_not_begin_publication(self):
        self.fixture.queue.request_cancellation(
            self.fixture.job.job_id,
            actor=self.fixture.fixture.actor,
            now=self.context.now(),
            reason_code="synthetic-cancel",
            interruption_kind="user-cancel",
        )
        with (
            patch.object(self.fixture.repository, "publish_commit") as publish,
            self.assertRaises(WorkflowCancellationRequested),
        ):
            self.activity(self.context, self.fixture.claim)
        publish.assert_not_called()

    def test_nonadvancing_page_is_bounded_failure_not_an_infinite_loop(self):
        with (
            patch.object(self.fixture.repository, "append_commit_page", return_value=0),
            patch.object(self.fixture.repository, "publish_commit") as publish,
            self.assertRaisesRegex(WorkflowActivityError, "import-commit-failed"),
        ):
            self.activity(self.context, self.fixture.claim)
        publish.assert_not_called()

    def test_heartbeat_during_preparation_retains_exact_attempt_authority(self):
        ticks = count(0, 6)
        activity = ImportCommitActivity(
            inputs=self.fixture.inputs,
            repository=self.fixture.repository,
            guard=lambda action: action(),
            trace_id="4" * 32,
            clock=lambda: next(ticks),
        )
        with patch.object(self.fixture.queue, "heartbeat", wraps=self.fixture.queue.heartbeat) as heartbeat:
            result = activity(self.context, self.fixture.claim)
        self.assertGreater(heartbeat.call_count, 0)
        self.assertEqual(1, len(result.outputs))
        self.assertEqual("succeeded", self.fixture.queue.get(self.fixture.job.job_id).state)

    def test_verification_releases_outer_guard_but_pages_and_atomic_writer_are_guarded(self):
        depth = 0
        f = self.fixture

        def guard(action):
            nonlocal depth
            depth += 1
            try:
                return action()
            finally:
                depth -= 1

        verified = f.repository._verified_identity
        page = f.repository.draft_page

        def verify(*args, **kwargs):
            self.assertEqual(0, depth, "full verification must not hold the lifecycle lock")
            return verified(*args, **kwargs)

        def guarded_page(*args, **kwargs):
            self.assertEqual(1, depth)
            return page(*args, **kwargs)

        def writer_step(_step):
            self.assertEqual(1, depth)

        activity = ImportCommitActivity(inputs=f.inputs, repository=f.repository, guard=guard, trace_id="4" * 32)
        with (
            patch.object(f.repository, "_verified_identity", side_effect=verify),
            patch.object(f.repository, "draft_page", side_effect=guarded_page),
            patch("research_observatory_core.import_commit_repository._publication_step_completed", writer_step),
            patch.object(f.queue, "heartbeat", wraps=f.queue.heartbeat) as heartbeat,
        ):
            activity(self.context, f.claim)
        self.assertGreater(heartbeat.call_count, 0, "fresh lease required immediately before writer")

    def test_authority_loss_after_verification_denies_publication_without_canonical_facts(self):
        f = self.fixture
        allowed = True
        verified = f.repository._verified_identity

        def guard(action):
            if not allowed:
                raise PreviewProblem("preview-authority-changed")
            return action()

        def verify(*args, **kwargs):
            nonlocal allowed
            result = verified(*args, **kwargs)
            allowed = False
            return result

        activity = ImportCommitActivity(inputs=f.inputs, repository=f.repository, guard=guard, trace_id="4" * 32)
        with (
            patch.object(f.repository, "_verified_identity", side_effect=verify),
            self.assertRaisesRegex(WorkflowActivityError, "stale-authority"),
        ):
            activity(self.context, f.claim)
        with open_canonical_database(f.database, expected_project_id=f.inputs.project_id) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM import_source_records").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM import_manifests").fetchone()[0])

    def test_cancellation_after_verification_stops_before_writer(self):
        f = self.fixture
        verified = f.repository._verified_identity

        def verify(*args, **kwargs):
            result = verified(*args, **kwargs)
            f.queue.request_cancellation(
                f.job.job_id,
                actor=f.fixture.actor,
                now=self.context.now(),
                reason_code="synthetic-cancel",
                interruption_kind="user-cancel",
            )
            return result

        with (
            patch.object(f.repository, "_verified_identity", side_effect=verify),
            patch.object(f.repository, "_publish_verified") as writer,
            self.assertRaises(WorkflowCancellationRequested),
        ):
            self.activity(self.context, f.claim)
        writer.assert_not_called()
