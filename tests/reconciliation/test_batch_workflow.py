"""Exact durable batch authority and explicit failed-job continuation."""

import unittest
from dataclasses import replace

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.preview_workflow import PreviewIntentContext
from research_observatory_core.ports.workflow_executor import WorkflowActor
from research_observatory_core.reconciliation.batch import (
    BATCH_ACTIVITY,
    SOURCE_ACTIVITIES,
    BatchInput,
    InventorySnapshot,
)
from research_observatory_core.reconciliation.contracts import ReconciliationProblem
from research_observatory_core.reconciliation.workflow import bind_batch_claim, build_batch_job

from tests.workflows import test_local_workflow_executor as fixtures


class BatchWorkflowTests(unittest.TestCase):
    def test_claim_and_continuation_bind_frozen_configuration_and_predecessor(self):
        f = fixtures.LocalWorkflowExecutorTests(methodName="runTest")
        f.setUp()
        self.addCleanup(f.tearDown)
        queue = f.repository
        project = fixtures.PROJECT_ID
        inputs = BatchInput(
            request_id=new_uuid_v7(),
            project_id=project,
            actor_id=fixtures.SYSTEM.actor_id,
            intent=PreviewIntentContext(
                project_id=project,
                domain_project_id=new_uuid_v7(),
                intent_id=new_uuid_v7(),
                revision_id=new_uuid_v7(),
                content_hash="sha256:" + "a" * 64,
                status="accepted",
            ),
            policy_sha256="sha256:" + "b" * 64,
            session_epoch="c" * 32,
            inventory=InventorySnapshot(project_id=project, activity_types=SOURCE_ACTIVITIES, boundaries=()),
        )
        now = "2026-08-30T12:02:00.000Z"
        job = queue.enqueue(build_batch_job(inputs, actor=fixtures.SYSTEM, now=now), actor=fixtures.SYSTEM)
        claim = queue.claim_next(
            worker_id=fixtures.WORKER_A,
            concurrency_classes=("document",),
            now=now,
            lease_duration_ms=30000,
            activity_types=(BATCH_ACTIVITY,),
        )
        self.assertEqual(inputs, bind_batch_claim(queue.authority(job.job_id), claim, inputs))
        for forged in (
            replace(claim, project_id=new_uuid_v7()),
            replace(claim, command_fingerprint="sha256:" + "0" * 64),
            replace(claim, activity_type="source-acquisition"),
        ):
            with self.assertRaises(ReconciliationProblem):
                bind_batch_claim(queue.authority(job.job_id), forged, inputs)
        queue.start(claim, now=now)
        queue.fail(claim, now=now, error_code="invalid-input")
        failed = queue.task_center()[0]
        continued = queue.retry_as_continuation(
            job.job_id,
            expected_snapshot_revision=failed.snapshot_revision,
            expected_history_sequence=failed.revision,
            idempotency_key="5" * 32,
            actor=WorkflowActor(new_uuid_v7(), "human", "researcher"),
            now=now,
        )
        child = queue.claim_next(
            worker_id=fixtures.WORKER_A,
            concurrency_classes=("document",),
            now=now,
            lease_duration_ms=30000,
            activity_types=(BATCH_ACTIVITY,),
        )
        self.assertEqual(continued.jobs[0].job_id, child.job_id)
        authority = queue.authority(child.job_id)
        with self.assertRaises(ReconciliationProblem):
            bind_batch_claim(authority, child, inputs)
        predecessor = (queue.get(job.job_id), queue.authority(job.job_id))
        self.assertEqual(inputs, bind_batch_claim(authority, child, inputs, predecessor=predecessor))
        with self.assertRaises(ReconciliationProblem):
            bind_batch_claim(
                authority, child, inputs.model_copy(update={"session_epoch": "d" * 32}), predecessor=predecessor
            )
