"""Durable worker integration with synthetic HTTP and real local repositories."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

# ruff: noqa: E402

import httpx2
from research_observatory_core.connector_repository import ConnectorRepository
from research_observatory_core.connector_worker import ConnectorWorkerAdapters, ConnectorWorkerService
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.object_store import create_local_object_store
from research_observatory_core.ports.workflow_executor import WorkflowLeaseRejected
from research_observatory_core.repositories import (
    _SqliteWorkflowQueueRepository,
    sqlite_workflow_admission_binding,
    sqlite_workflow_queue_repository,
)
from research_observatory_core.workflow_executor import LocalAdmissionController, ProjectWorkerPolicy, WorkerResources

from tests.connectors import test_connector_authority as authority_fixtures
from tests.connectors.test_connector_transport import BytesStream
from tests.connectors.test_scholarly_mapping import fixture
from tests.data.test_encrypted_object_store import MemoryKeyProvider


class ConnectorWorkflowFixture(authority_fixtures.ConnectorAuthorityFixture):
    repository: ConnectorRepository

    def setUp(self):
        super().setUp()
        self.calls = []
        self.keys = MemoryKeyProvider({"synthetic-key": b"s" * 32}, "synthetic-key")
        self.repository = ConnectorRepository(
            Path(self.root) / "state/project.sqlite3",
            self.project.project_id,
            create_local_object_store(Path(self.root), self.project.project_id, key_provider=self.keys),
        )
        self.queue = sqlite_workflow_queue_repository(Path(self.root), self.project.project_id)
        demand = WorkerResources(1, 64 * 1024**2, 0, 64 * 1024**2)
        self.admission = sqlite_workflow_admission_binding(
            self.queue,
            controller=LocalAdmissionController(interactive_reserve=demand),
            policy=ProjectWorkerPolicy(self.project.project_id, demand, {"document": demand}, {"document": 1}),
        )
        self.worker = self.worker_service()
        self.intent()
        self.policy()

    def worker_service(self):
        async def respond(wire):
            self.calls.append(wire)
            response = httpx2.Response(200, json=fixture("openalex"))
            return httpx2.Response(200, headers=response.headers, stream=BytesStream(response.content))

        return ConnectorWorkerService(
            self.projects,
            self.connectors,
            lambda _path, _project: ConnectorWorkerAdapters(self.repository, self.queue, self.admission),
            local_actor_id=authority_fixtures.fixtures.ACTOR_ID,
            now=self.clock.now,
            transport_factory=lambda: httpx2.MockTransport(respond),
            clock=self.clock.monotonic,
            sleep=self.clock.sleep,
        )

    def tearDown(self):
        self.worker.shutdown()
        self.projects.shutdown()
        if os.name == "nt":
            subprocess.run(
                [
                    str(Path(os.environ["SYSTEMROOT"]) / "System32/icacls.exe"),
                    self.temp.name,
                    "/reset",
                    "/t",
                    "/c",
                    "/q",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )

    def schedule(self):
        preview = self.connectors.preview(self.root, self.request, self.rights)
        return preview, self.worker.confirm_and_schedule(
            self.root, preview.preview_id, confirmation=preview.confirmation
        )


class ConnectorWorkflowTests(ConnectorWorkflowFixture):
    def test_confirmed_page_is_a_durable_job_with_protected_source_output(self):
        preview, job = self.schedule()
        replay = self.worker.confirm_and_schedule(self.root, preview.preview_id, confirmation=preview.confirmation)
        self.assertEqual(job.job_id, replay.job_id)
        self.assertEqual([], self.calls)
        self.worker.run_pending()
        completed = self.queue.get(job.job_id)
        self.assertEqual("succeeded", completed.state)
        self.assertEqual(1, len(self.calls))
        page = self.repository.replay(self.request)
        assert page is not None
        self.assertEqual("complete", page.outcome)
        self.assertIsNotNone(self.repository.checkpoint(self.request))
        self.assertIsNotNone(completed.committed_output_sha256)
        self.assertEqual(self.request, self.repository.operation(preview.preview_id).preview.request)
        # Reconfirmation of the same invocation cannot create another HTTP observation.
        _, again = self.schedule()
        self.worker.run_pending()
        self.assertEqual("succeeded", self.queue.get(again.job_id).state)
        self.assertEqual(1, len(self.calls))

    def test_cancel_before_dispatch_and_restart_require_new_confirmation(self):
        _, job = self.schedule()
        self.worker.cancel(self.root, job.job_id)
        self.worker.run_pending()
        self.assertEqual("cancelled", self.queue.get(job.job_id).state)
        self.assertEqual([], self.calls)
        self.request = type(self.request).model_validate(self.request.model_dump() | {"invocation_id": new_uuid_v7()})
        _, interrupted = self.schedule()
        self.worker.shutdown()
        self.connectors = self.consent_service()
        self.worker = self.worker_service()
        self.worker.attach(self.root)
        self.worker.run_pending()
        self.assertEqual("cancelled", self.queue.get(interrupted.job_id).state)
        self.assertEqual([], self.calls)
        self.assertIsNone(self.repository.checkpoint(self.request))

    def test_expired_claim_at_publication_cannot_accept_page_or_output(self):
        _, job = self.schedule()
        publish = self.repository.publish

        def expire_then_publish(*args, **kwargs):
            self.clock.seconds += 61
            return publish(*args, **kwargs)

        # A stale executor can neither complete nor report failure using its
        # expired capability. The next supervisor pass owns lease recovery.
        with (
            patch.object(self.repository, "publish", side_effect=expire_then_publish),
            self.assertRaises(WorkflowLeaseRejected),
        ):
            self.worker.run_pending()
        self.assertIsNone(self.repository.replay(self.request))
        self.assertIsNone(self.repository.checkpoint(self.request))
        self.assertIsNone(self.queue.get(job.job_id).committed_output_sha256)
        self.worker.run_pending()
        self.assertEqual("failed", self.queue.get(job.job_id).state)
        self.assertEqual(1, len(self.calls))

    def test_interrupted_completion_rolls_back_page_and_checkpoint_across_restart(self):
        class SimulatedCrash(BaseException):
            pass

        _, job = self.schedule()
        with (
            patch.object(_SqliteWorkflowQueueRepository, "_complete_with_connection", side_effect=SimulatedCrash),
            self.assertRaises(SimulatedCrash),
        ):
            self.worker.run_pending()
        # Reopen the actual protected repositories, not their in-memory state.
        restarted = ConnectorRepository(
            Path(self.root) / "state/project.sqlite3",
            self.project.project_id,
            create_local_object_store(Path(self.root), self.project.project_id, key_provider=self.keys),
        )
        queue = sqlite_workflow_queue_repository(Path(self.root), self.project.project_id)
        self.assertIsNone(restarted.replay(self.request))
        self.assertIsNone(restarted.checkpoint(self.request))
        self.assertIsNone(queue.get(job.job_id).committed_output_sha256)
        self.clock.seconds += 61
        self.worker.run_pending()
        self.assertEqual("failed", queue.get(job.job_id).state)
        self.assertEqual(1, len(self.calls))

    def test_policy_revocation_between_queue_and_dispatch_is_not_an_empty_success(self):
        _, job = self.schedule()
        self.policy(False)
        self.worker.run_pending()
        self.assertIn(self.queue.get(job.job_id).state, ("cancelled", "failed"))
        self.assertEqual([], self.calls)
        self.assertIsNone(self.repository.checkpoint(self.request))

    def test_lost_acknowledgement_after_commit_does_not_turn_success_into_cancellation(self):
        class LostAcknowledgement(BaseException):
            pass

        _, job = self.schedule()
        publish = self.repository.publish

        def publish_then_interrupt(*args, **kwargs):
            publish(*args, **kwargs)
            raise LostAcknowledgement

        with (
            patch.object(self.repository, "publish", side_effect=publish_then_interrupt),
            self.assertRaises(LostAcknowledgement),
        ):
            self.worker.run_pending()
        self.assertEqual("succeeded", self.queue.get(job.job_id).state)
        self.assertIsNotNone(self.repository.checkpoint(self.request))
        self.assertIsNotNone(self.queue.get(job.job_id).committed_output_sha256)
        self.worker.run_pending()
        self.assertEqual(1, len(self.calls))

    def test_queue_cancellation_at_publication_boundary_cannot_advance_checkpoint(self):
        _, job = self.schedule()
        publish = self.repository.publish

        def cancel_then_publish(*args, **kwargs):
            # The generic Task Center updates this same queue without revoking
            # connector-specific in-memory consent. Exercise its race boundary.
            self.queue.request_cancellation(
                job.job_id,
                actor=self.worker._actor(),
                now=self.clock.now(),
                reason_code="synthetic-task-center-cancel",
                interruption_kind="user-cancel",
            )
            return publish(*args, **kwargs)

        with patch.object(self.repository, "publish", side_effect=cancel_then_publish):
            self.worker.run_pending()
        self.assertEqual("cancelled", self.queue.get(job.job_id).state)
        self.assertIsNone(self.repository.checkpoint(self.request))


if __name__ == "__main__":
    unittest.main()
