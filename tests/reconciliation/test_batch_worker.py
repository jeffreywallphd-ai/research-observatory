"""Real project/Intent/queue/source owner integration for the local batch worker."""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.ports.import_previews import PreviewDraftChange
from research_observatory_core.ports.workflow_executor import WorkflowQueueConflict, WorkflowQueueProblem
from research_observatory_core.reconciliation.batch_inventory import collect_batch_sources
from research_observatory_core.reconciliation.contracts import ReconciliationProblem
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.reconciliation_service import ReconciliationService
from research_observatory_core.reconciliation_worker import ReconciliationBatchAdapters
from research_observatory_core.repositories import sqlite_intent_revision_repository
from research_observatory_core.storage import open_canonical_database
from research_observatory_core.task_center import TaskCenterService

from tests.connectors import test_connector_authority as authority_fixture
from tests.service import test_import_preview_service as fixtures


class BatchWorkerTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ImportPreviewServiceTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        authority = authority_fixture.ConnectorAuthorityFixture()
        authority.root, authority.service, authority.privacy = self.f.root, self.f.intents, self.f.privacy
        authority.intent(mode="local-only", providers=())
        self.authority = authority
        self.root = self.f.root
        preview = self.f.intake(
            b"title,doi\nSynthetic duplicate,10.99999/example\nSynthetic duplicate,10.99999/example\n"
        )
        self.preview = preview
        self.f.service.schedule(self.root, preview)
        self.f.service.run_pending()
        adapters = self.f.adapters(Path(self.root), self.f.project_id)
        self.queue = adapters.queue
        repo = adapters.previews
        actor = self.f.service.actor("a" * 32)
        repo.revise_draft(preview, PreviewDraftChange(expected_revision=0, actor=actor))
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
        decisions = tuple(
            item.decision.model_copy(update={"rights": rights})
            for item in repo.draft_page(preview, revision=1, after=0, limit=100)
            if item.decision.included
        )
        repo.revise_draft(preview, PreviewDraftChange(expected_revision=1, actor=actor, decisions=decisions))
        self.f.service.schedule_commit(self.root, preview, revision=2, request_id=new_uuid_v7())
        self.f.service.run_pending()
        self.service = self.runtime()
        self.addCleanup(self.service.shutdown)

    def runtime(self, epoch=None):
        def repository(path, identity):
            return SqliteReconciliationRepository(path / "state/project.sqlite3", identity)

        def adapters(path, identity):
            existing = self.f.adapters(path, identity)
            return ReconciliationBatchAdapters(repository(path, identity), existing.queue, existing.admission)

        return ReconciliationService(
            self.f.projects,
            self.f.privacy,
            imports=self.f.service,
            connectors=self.f.service,
            repository_factory=repository,
            intent_factory=sqlite_intent_revision_repository,
            actor_id=self.f.actor,
            now=lambda: self.f.now,
            batch_adapter_factory=adapters,
            resume_epoch=epoch or self.f.epoch,
        )

    def test_restart_completes_frozen_request_through_real_owner_and_queue(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        self.service.shutdown()
        self.service = self.runtime()
        self.addCleanup(self.service.shutdown)
        self.service.attach(self.root)
        self.assertEqual(job.job_id, self.service.schedule_batch(self.root, request, trace_id="a" * 32).job_id)
        self.service.run_pending()
        self.assertEqual("succeeded", self.queue.get(job.job_id).state)
        output = self.queue.accepted_output(job.job_id).outputs[0]
        repository = SqliteReconciliationRepository(Path(self.root) / "state/project.sqlite3", self.f.project_id)
        content = repository.candidate_set(
            output.revision_id, resolve=lambda address: self.f.service.reconciliation_source(self.root, address)
        )
        self.assertEqual(2, len(content.members))

    def test_new_epoch_cancels_queued_authority_before_attempt(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        self.service.shutdown()
        self.service = self.runtime("2" * 32)
        self.addCleanup(self.service.shutdown)
        self.service.attach(self.root)
        self.service.run_pending()
        state = self.queue.get(job.job_id)
        self.assertEqual("cancelled", state.state)
        self.assertEqual(0, state.attempt_count)

    def test_candidate_page_discloses_later_accepted_inventory_without_changing_scores(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        self.service.run_pending()
        revision = self.queue.accepted_output(job.job_id).outputs[0].revision_id
        before = self.service.inspect_candidates(self.root, revision, after=0, limit=100, trace_id="a" * 32)
        preview = self.f.intake(b"title,doi\nUnrelated new paper,10.99999/unrelated\n")
        self.f.service.schedule(self.root, preview)
        self.f.service.run_pending()
        repository = self.f.adapters(Path(self.root), self.f.project_id).previews
        actor = self.f.service.actor("a" * 32)
        repository.revise_draft(preview, PreviewDraftChange(expected_revision=0, actor=actor))
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
        decisions = tuple(
            item.decision.model_copy(update={"rights": rights})
            for item in repository.draft_page(preview, revision=1, after=0, limit=100)
        )
        repository.revise_draft(preview, PreviewDraftChange(expected_revision=1, actor=actor, decisions=decisions))
        self.f.service.schedule_commit(self.root, preview, revision=2, request_id=new_uuid_v7())
        self.f.service.run_pending()
        after = self.service.inspect_candidates(self.root, revision, after=0, limit=100, trace_id="a" * 32)
        self.assertEqual(before.items, after.items)
        self.assertEqual(before.record_count, after.record_count)
        self.assertEqual("unchanged", before.inventory_state)
        self.assertEqual("changed", after.inventory_state)
        self.assertEqual(before.inventory_sha256, after.inventory_sha256)
        self.assertEqual(before.inventory_sha256, before.current_inventory_sha256)
        self.assertNotEqual(after.inventory_sha256, after.current_inventory_sha256)

    def test_cancel_reaches_writer_and_durable_state_after_rollback(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        entered = threading.Event()

        def publication(step):
            if step == "batch-exact-complete":
                entered.set()
                active = next(iter(self.service._batch._publications.values()))
                self.assertTrue(active.requested.wait(2))

        with (
            patch("research_observatory_core.reconciliation_repository._publication_step", publication),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            running = pool.submit(self.service.run_pending)
            self.assertTrue(entered.wait(3))
            self.service.cancel_batch(self.root, request_id=request, job_id=job.job_id)
            running.result(timeout=3)
        self.assertEqual("cancelled", self.queue.get(job.job_id).state)
        self.assertIsNone(self.queue.accepted_output(job.job_id))
        with open_canonical_database(
            Path(self.root) / "state/project.sqlite3", expected_project_id=self.f.project_id
        ) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM reconciliation_assertions").fetchone()[0])

    def _task_center_cancel_during_writer(self, *, stale, expired=False):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        entered = threading.Event()
        released = threading.Event()
        runs = []
        reconcile = SqliteReconciliationRepository._reconcile_with_connection

        def advancing(repository, *args, **kwargs):
            result = reconcile(repository, *args, **kwargs)
            if expired:
                self.f.now = (
                    (datetime.fromisoformat(self.f.now) + timedelta(seconds=20))
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z")
                )
            return result

        def publication(step):
            if step == "batch-exact-complete" and not entered.is_set():
                runs.extend(
                    item for item in self.queue.task_center(limit=100) if item.workflow_run_id == job.workflow_run_id
                )
                if expired:
                    with open_canonical_database(
                        Path(self.root) / "state/project.sqlite3", expected_project_id=self.f.project_id
                    ) as db:
                        lease = db.execute(
                            "SELECT lease_expires_at FROM workflow_queue_jobs WHERE job_id=?", (job.job_id,)
                        ).fetchone()[0]
                    self.assertLess(datetime.fromisoformat(lease), datetime.fromisoformat(self.f.now))
                entered.set()
                active = next(iter(self.service._batch._publications.values()))
                if stale:
                    self.assertTrue(released.wait(2))
                    self.assertFalse(active.requested.is_set())
                else:
                    self.assertTrue(active.requested.wait(2))

        center = TaskCenterService(self.f.projects, lambda path, identity: self.queue, self.f.actor)
        with (
            patch("research_observatory_core.reconciliation_repository._publication_step", publication),
            patch.object(SqliteReconciliationRepository, "_reconcile_with_connection", advancing),
            patch("research_observatory_core.task_center._now", lambda: self.f.now),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            running = pool.submit(self.service.run_pending)
            self.assertTrue(entered.wait(3))

            def cancel():
                return self.service.cancel_workflow(
                    self.root,
                    job_id=job.job_id,
                    workflow_run_id=job.workflow_run_id,
                    expected_snapshot_revision=runs[0].snapshot_revision,
                    expected_revision=runs[0].revision + int(stale),
                    action=lambda: center.cancel(
                        root=self.root,
                        job_id=job.job_id,
                        expected_run_id=job.workflow_run_id,
                        expected_snapshot_revision=runs[0].snapshot_revision,
                        expected_revision=runs[0].revision + int(stale),
                        reason_code="user-cancel",
                    ),
                )

            if stale:
                with self.assertRaises(WorkflowQueueConflict):
                    cancel()
                # A stale command must not stop the writer at all.
                released.set()
            else:
                self.assertEqual("cancelling", cancel().state)
            running.result(timeout=4)
        self.assertEqual("succeeded" if stale else "cancelled", self.queue.get(job.job_id).state)
        self.assertEqual(stale, self.queue.accepted_output(job.job_id) is not None)

    def test_task_center_cancel_interrupts_writer_with_original_precondition(self):
        self._task_center_cancel_during_writer(stale=False)

    def test_stale_task_center_cancel_does_not_change_or_fail_batch(self):
        self._task_center_cancel_during_writer(stale=True)

    def test_stale_cancel_preserves_writer_after_committed_lease_has_expired(self):
        self._task_center_cancel_during_writer(stale=True, expired=True)

    def test_valid_cancel_persists_after_provisional_lease_renewals_roll_back(self):
        self._task_center_cancel_during_writer(stale=False, expired=True)

    def test_changed_intent_between_inventory_and_publication_denies_without_output(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)

        def changed(*args, **kwargs):
            addresses = collect_batch_sources(*args, **kwargs)
            self.authority.intent(mode="local-only", providers=())
            return addresses

        with patch("research_observatory_core.reconciliation_worker.collect_batch_sources", changed):
            self.service.run_pending()
        self.assertEqual("failed", self.queue.get(job.job_id).state)
        self.assertEqual("stale-authority", self.queue.get(job.job_id).diagnostic_code)
        self.assertIsNone(self.queue.accepted_output(job.job_id))
        with open_canonical_database(
            Path(self.root) / "state/project.sqlite3", expected_project_id=self.f.project_id
        ) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM reconciliation_assertions").fetchone()[0])

    def test_saved_request_survives_enqueue_failure_and_restart(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        with (
            patch.object(type(self.queue), "enqueue", side_effect=WorkflowQueueProblem("injected-enqueue-failure")),
            self.assertRaises(WorkflowQueueProblem),
        ):
            self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        self.service.shutdown()
        self.service = self.runtime()
        self.addCleanup(self.service.shutdown)
        self.service.attach(self.root)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        self.service.run_pending()
        self.assertEqual("succeeded", self.queue.get(job.job_id).state)

    def test_commit_wins_lost_acknowledgement_without_rewriting_accepted_output(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        publish = SqliteReconciliationRepository.publish_batch

        def lost(repository, *args, **kwargs):
            publish(repository, *args, **kwargs)
            raise RuntimeError("injected-lost-acknowledgement")

        with patch.object(SqliteReconciliationRepository, "publish_batch", lost):
            self.service.run_pending()
        output = self.queue.accepted_output(job.job_id)
        self.assertEqual("succeeded", self.queue.get(job.job_id).state)
        self.service.run_pending()
        self.assertEqual(output, self.queue.accepted_output(job.job_id))
        self.assertEqual(1, self.queue.get(job.job_id).attempt_count)

    def test_close_before_registration_fences_worker_and_failed_drain_keeps_project_open(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        entered, released = threading.Event(), threading.Event()
        authorize = self.service._batch._authorize

        def delayed(root, trace, action):
            if action.__name__ == "execute":
                entered.set()
                self.assertTrue(released.wait(3))
            return authorize(root, trace, action)

        with patch.object(self.service._batch, "_authorize", delayed), ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(self.service.run_pending)
            self.assertTrue(entered.wait(3))
            with self.assertRaisesRegex(ReconciliationProblem, "reconciliation-worker-drain-pending"):
                self.service.detach(self.root)
            self.f.projects.perform_open_project_action(
                root=self.root,
                require_write=True,
                action=lambda path, identity: self.assertEqual(self.f.project_id, identity),
            )
            released.set()
            running.result(timeout=3)
            self.service.detach(self.root)
        self.assertEqual("cancelled", self.queue.get(job.job_id).state)
        self.assertIsNone(self.queue.accepted_output(job.job_id))

    @contextmanager
    def client(self):
        token = "a" * 64
        authority = "127.0.0.1:49152"
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(token),
            expected_authority=authority,
            projects=self.f.projects,
            privacy=self.f.privacy,
            intents=self.f.intents,
            imports=self.f.service,
            reconciliation=self.service,
            task_center=TaskCenterService(self.f.projects, lambda path, identity: self.queue, self.f.actor),
        )
        with (
            patch.object(self.service, "start"),
            patch.object(self.f.service, "start"),
            TestClient(
                app,
                base_url=f"http://{authority}",
                headers={"Authorization": f"Bearer {token}"},
                client=("127.0.0.1", 50000),
            ) as client,
        ):
            yield client

    def test_close_api_signals_before_import_drain_and_preserves_atomic_rollback(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        entered = threading.Event()

        def publication(step):
            if step == "batch-exact-complete":
                entered.set()
                active = next(iter(self.service._batch._publications.values()))
                self.assertTrue(active.requested.wait(2))

        with (
            self.client() as client,
            patch("research_observatory_core.reconciliation_repository._publication_step", publication),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            running = pool.submit(self.service.run_pending)
            self.assertTrue(entered.wait(3))
            response = client.post("/projects/close", json={"root": self.root})
            self.assertEqual(200, response.status_code, response.text)
            running.result(timeout=3)
            self.assertEqual("cancelled", self.queue.get(job.job_id).state)
            self.assertIsNone(self.queue.accepted_output(job.job_id))

    def test_task_center_api_cancel_reaches_active_writer(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        entered = threading.Event()

        def publication(step):
            if step == "batch-exact-complete":
                entered.set()
                active = next(iter(self.service._batch._publications.values()))
                self.assertTrue(active.requested.wait(2))

        with (
            self.client() as client,
            patch("research_observatory_core.reconciliation_repository._publication_step", publication),
            patch("research_observatory_core.task_center._now", lambda: self.f.now),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            running = pool.submit(self.service.run_pending)
            self.assertTrue(entered.wait(3))
            page = client.get("/projects/workflows/task-center", params={"root": self.root, "limit": 100})
            self.assertEqual(200, page.status_code, page.text)
            run = next(item for item in page.json()["items"] if item["workflowRunId"] == job.workflow_run_id)
            self.assertEqual("running", run["state"])
            response = client.post(
                f"/projects/workflows/jobs/{job.job_id}/cancel",
                json={"root": self.root, "reasonCode": "user-cancel"},
                headers={"If-Match": f'"workflow-{run["workflowRunId"]}-{run["revision"]}-{run["snapshotRevision"]}"'},
            )
            self.assertEqual(200, response.status_code, response.text)
            running.result(timeout=3)
            self.assertEqual("cancelled", self.queue.get(job.job_id).state)

    def test_batch_status_poll_then_cancel_reaches_active_writer(self):
        request = self.service.prepare_batch(self.root, trace_id="a" * 32)
        job = self.service.schedule_batch(self.root, request, trace_id="a" * 32)
        entered = threading.Event()

        def publication(step):
            if step == "batch-exact-complete":
                entered.set()
                active = next(iter(self.service._batch._publications.values()))
                self.assertTrue(active.requested.wait(2))

        with (
            self.client() as client,
            patch("research_observatory_core.reconciliation_repository._publication_step", publication),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            running = pool.submit(self.service.run_pending)
            self.assertTrue(entered.wait(3))
            body = {"root": self.root, "requestId": request, "jobId": job.job_id}
            status = client.post("/projects/reconciliation/batches/status", json=body)
            self.assertEqual(200, status.status_code, status.text)
            self.assertEqual("running", status.json()["state"])
            self.assertIsNone(status.json()["setRevisionId"])
            cancelled = client.post("/projects/reconciliation/batches/cancel", json=body)
            self.assertEqual(200, cancelled.status_code, cancelled.text)
            self.assertEqual("cancelled", cancelled.json()["state"])
            running.result(timeout=3)
            self.assertIsNone(self.queue.accepted_output(job.job_id))
            self.assertIsNone(self.queue.accepted_output(job.job_id))

    def test_close_signals_active_import_before_draining_idle_reconciliation(self):
        self.service.attach(self.root)
        job = self.f.service.schedule_commit(self.root, self.preview, revision=2, request_id=new_uuid_v7())
        entered = threading.Event()
        signalled = []

        def publication(step):
            if step == "output-staged":
                entered.set()
                active = next(iter(self.f.service._publications.values()))
                signalled.append(active.requested.wait(2))

        with (
            self.client() as client,
            patch("research_observatory_core.import_commit_repository._publication_step_completed", publication),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            running = pool.submit(self.f.service.run_pending)
            self.assertTrue(entered.wait(3))
            response = client.post("/projects/close", json={"root": self.root})
            self.assertEqual(200, response.status_code, response.text)
            running.result(timeout=3)
            self.assertEqual([True], signalled)
            self.assertIsNone(self.queue.accepted_output(job.job_id))
