"""Real commit activity/repository boundary with isolated development storage."""

import unittest
from itertools import count
from unittest.mock import patch

from research_observatory_core.ingestion.commit_activity import ImportCommitActivity
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
