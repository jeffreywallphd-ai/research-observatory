"""Concurrent authenticated interruption of the real atomic writer, not a mock success."""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ports.import_previews import PreviewProblem
from research_observatory_core.repositories import sqlite_workflow_queue_repository
from research_observatory_core.storage import open_canonical_database

from tests.service import test_import_commit_api as api


class ImportCommitInterruptionTests(unittest.TestCase):
    def setUp(self):
        self.case = api.ImportCommitApiTests(methodName="runTest")
        # Control scheduling only; use the actual supervisor/activity/repository.
        with patch("research_observatory_core.import_preview_service.ImportPreviewService.start"):
            self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.f = self.case.api.fixture
        self.job = self.case.start().json()["jobId"]
        self.queue = sqlite_workflow_queue_repository(Path(self.f.root), self.f.project_id)

    def counts(self):
        with open_canonical_database(
            Path(self.f.root) / "state/project.sqlite3", expected_project_id=self.f.project_id
        ) as db:
            return tuple(
                db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in (
                    "import_source_records",
                    "import_manifests",
                    "import_manifest_members",
                    "import_manifest_seals",
                )
            )

    def interrupt(self, *, close=False, expired=False):
        entered, signalled = threading.Event(), threading.Event()
        original = self.f.service.request_publication_stop

        def signal(*args, **kwargs):
            signalled.set()
            return original(*args, **kwargs)

        def writer(step):
            if expired and step in {"source-record-created", "manifest-created"}:
                self.f.now = (
                    (datetime.fromisoformat(self.f.now) + timedelta(seconds=20))
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z")
                )
            if step == ("manifest-created" if expired else "source-record-created"):
                entered.set()
                self.assertTrue(signalled.wait(2), "cancellation must reach the signal before the lifecycle lock")

        with (
            patch("research_observatory_core.import_commit_repository._publication_step_completed", writer),
            patch.object(self.f.service, "request_publication_stop", side_effect=signal),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            worker = pool.submit(self.f.service.run_pending)
            self.assertTrue(entered.wait(5))
            if close:
                result = self.case.api.client.post("/projects/close", json={"root": self.f.root})
            else:
                result = self.case.post("commit/cancel", requestId=self.case.request, jobId=self.job)
            worker.result(timeout=5)
        self.assertEqual(200, result.status_code, result.json())
        self.assertEqual((0, 0, 0, 0), self.counts())
        self.assertEqual(1, self.queue.get(self.job).attempt_count)
        if not close:
            self.assertEqual("cancelled", self.queue.get(self.job).state)

    def test_cancel_route_interrupts_writer_before_acquiring_lifecycle_lock(self):
        self.interrupt()

    def test_cancel_after_rollback_exposes_expired_durable_lease_uses_recovery_not_revival(self):
        self.interrupt(expired=True)
        self.assertEqual("cancellation-recovered", self.queue.get(self.job).diagnostic_code)

    def test_close_route_interrupts_writer_and_drains_before_closing(self):
        self.interrupt(close=True)

    def test_cancellation_after_commit_keeps_accepted_manifest_and_records(self):
        self.f.service.run_pending()
        before = self.counts()
        self.assertEqual((1, 1, 2, 1), before)
        result = self.case.post("commit/cancel", requestId=self.case.request, jobId=self.job)
        self.assertEqual(200, result.status_code)
        self.assertEqual("succeeded", result.json()["jobState"])
        self.assertEqual(before, self.counts())

    def test_cancel_interrupts_sql_inside_an_adapter_and_rolls_back_before_convergence(self):
        entered = threading.Event()

        def slow_sql(connection, **_kwargs):
            entered.set()
            connection.execute(
                "WITH RECURSIVE synthetic(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM synthetic WHERE n<100000000) "
                "SELECT SUM(n) FROM synthetic"
            ).fetchone()
            self.fail("synthetic long statement should have been interrupted")

        with (
            patch("research_observatory_core.repositories._record_aggregate_provenance", slow_sql),
            ThreadPoolExecutor() as pool,
        ):
            worker = pool.submit(self.f.service.run_pending)
            self.assertTrue(entered.wait(5))
            response = self.case.post("commit/cancel", requestId=self.case.request, jobId=self.job)
            worker.result(timeout=5)
        self.assertEqual(200, response.status_code, response.json())
        self.assertEqual((0, 0, 0, 0), self.counts())
        self.assertEqual("cancelled", self.queue.get(self.job).state)

    def test_wrong_command_and_replaced_binding_cannot_interrupt_publication(self):
        entered, release = threading.Event(), threading.Event()

        def writer(step):
            if step == "source-record-created":
                entered.set()
                self.assertTrue(release.wait(5))

        service = self.f.service
        with (
            patch("research_observatory_core.import_commit_repository._publication_step_completed", writer),
            ThreadPoolExecutor() as pool,
        ):
            worker = pool.submit(service.run_pending)
            try:
                self.assertTrue(entered.wait(5))
                active = service._publications[Path(self.f.root)]
                request = {"preview_id": self.case.api.preview, "request_id": self.case.request, "job_id": self.job}
                for name in request:
                    with self.subTest(name=name), self.assertRaises(PreviewProblem):
                        service.request_publication_stop(self.f.root, **{**request, name: new_uuid_v7()})
                    self.assertFalse(active.requested.is_set())
                service.request_publication_stop(str(Path(self.f.root) / "unrelated"), **request)
                self.assertFalse(active.requested.is_set())
                with service._mutex:
                    service._bindings.pop(active.binding.path)
                try:
                    service.request_publication_stop(self.f.root, **request)
                    self.assertFalse(active.requested.is_set())
                finally:
                    with service._mutex:
                        service._bindings[active.binding.path] = active.binding
            finally:
                release.set()
            worker.result(timeout=5)
        self.assertEqual("succeeded", self.queue.get(self.job).state)

    def test_drain_timeout_is_bounded_and_does_not_claim_no_import_was_published(self):
        entered, release = threading.Event(), threading.Event()

        def writer(step):
            if step == "source-record-created":
                entered.set()
                self.assertTrue(release.wait(5))

        with (
            patch("research_observatory_core.import_commit_repository._publication_step_completed", writer),
            ThreadPoolExecutor() as pool,
        ):
            worker = pool.submit(self.f.service.run_pending)
            try:
                self.assertTrue(entered.wait(5))
                response = self.case.api.client.post("/projects/close", json={"root": self.f.root})
                self.assertEqual(503, response.status_code)
                self.assertNotIn("No canonical import", response.json()["detail"])
                self.assertTrue(response.json()["retryable"])
            finally:
                release.set()
            worker.result(timeout=5)
        self.assertEqual((0, 0, 0, 0), self.counts())


if __name__ == "__main__":
    unittest.main()
