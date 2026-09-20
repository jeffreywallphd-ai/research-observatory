"""Commit command/claim authority; no canonical publication is claimed here."""

import unittest
from dataclasses import replace

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.commit_workflow import (
    COMMIT_ACTIVITY,
    CommitJobInput,
    bind_commit_claim,
    build_commit_job,
)
from research_observatory_core.ports.import_previews import PreviewProblem
from research_observatory_core.ports.workflow_executor import WorkflowActor

from tests.service import test_import_summary_workflow as summary_fixture


class ImportCommitWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = summary_fixture.ImportSummaryWorkflowTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        summary = self.fixture.inputs()
        values = summary.model_dump()
        values.pop("algorithm")
        self.inputs = CommitJobInput(**values, request_id=new_uuid_v7())
        self.queue = self.fixture.queue
        self.now = self.fixture.fixture.now
        self.actor = WorkflowActor(self.fixture.fixture.actor, "human", "local-researcher")

    def enqueue(self, inputs=None):
        return self.queue.enqueue(
            build_commit_job(inputs or self.inputs, actor=self.actor, now=self.now), actor=self.actor
        )

    def test_request_replay_is_distinct_from_scientific_identity(self):
        submission = build_commit_job(self.inputs, actor=self.actor, now=self.now)
        first = self.queue.enqueue(submission, actor=self.actor)
        self.assertEqual(first.job_id, self.queue.enqueue(submission, actor=self.actor).job_id)
        changed = self.inputs.model_copy(update={"draft_revision": self.inputs.draft_revision + 1})
        self.assertEqual(self.inputs.idempotency_key, changed.idempotency_key)
        self.assertNotEqual(self.inputs.configuration_hash, changed.configuration_hash)
        from research_observatory_core.ports.workflow_executor import WorkflowQueueProblem

        with self.assertRaises(WorkflowQueueProblem):
            self.enqueue(changed)
        fresh_request = self.inputs.model_copy(update={"request_id": new_uuid_v7()})
        self.assertNotEqual(first.job_id, self.enqueue(fresh_request).job_id)

    def test_exact_claim_accepts_but_changed_inputs_or_claims_deny(self):
        job = self.enqueue()
        claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.now,
            lease_duration_ms=30000,
            activity_types=(COMMIT_ACTIVITY,),
        )
        authority = self.queue.authority(job.job_id)
        self.assertEqual(self.inputs, bind_commit_claim(authority, claim, self.inputs))
        for change in ({"activity_type": "local-import-draft-summary"}, {"command_fingerprint": "sha256:" + "f" * 64}):
            with self.subTest(change=change), self.assertRaises(PreviewProblem):
                bind_commit_claim(authority, replace(claim, **change), self.inputs)
        for change in (
            {"draft_revision": self.inputs.draft_revision + 1},
            {"previous_manifest_revision_id": new_uuid_v7()},
            {"request_id": new_uuid_v7()},
            {"parse_attempt_id": new_uuid_v7()},
        ):
            with self.subTest(change=change), self.assertRaises(PreviewProblem):
                bind_commit_claim(authority, claim, self.inputs.model_copy(update=change))

    def test_continuation_requires_exact_cancelled_predecessor(self):
        original = self.enqueue()
        self.queue.request_cancellation(
            original.job_id,
            actor=self.actor,
            now=self.now,
            reason_code="synthetic-cancel",
            interruption_kind="user-cancel",
        )
        continued = self.fixture.retry(original, 1)
        claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.now,
            lease_duration_ms=30000,
            activity_types=(COMMIT_ACTIVITY,),
        )
        authority = self.queue.authority(continued.job_id)
        with self.assertRaises(PreviewProblem):
            bind_commit_claim(authority, claim, self.inputs)
        previous = self.queue.get(original.job_id), self.queue.authority(original.job_id)
        self.assertEqual(self.inputs, bind_commit_claim(authority, claim, self.inputs, predecessor=previous))
        substituted = replace(previous[0], state="succeeded"), previous[1]
        with self.assertRaises(PreviewProblem):
            bind_commit_claim(authority, claim, self.inputs, predecessor=substituted)
