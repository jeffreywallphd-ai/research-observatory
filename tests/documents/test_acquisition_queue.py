"""Durable intake, owned cleanup and explicit current-authority recovery."""

from __future__ import annotations

import sys
import unittest
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import httpcore2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.ports.object_store import ObjectStoreProblem  # noqa: E402
from research_observatory_core.repositories import sqlite_workflow_queue_repository  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.documents import test_oa_acquisition as fixtures  # noqa: E402


class AcquisitionQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = fixtures.AcquisitionIntegrationTests(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def intake_job(self, operation: str):
        c = self.case
        with closing(open_canonical_database(c.database, expected_project_id=c.project)) as db:
            row = db.execute(
                "SELECT job_id FROM document_intake_jobs WHERE project_id=? AND operation_id=?",
                (c.project, operation),
            ).fetchone()
        self.assertIsNotNone(row)
        return sqlite_workflow_queue_repository(Path(c.fixture.root), c.project).get(row[0])

    def test_download_is_visible_in_queue_before_network_and_candidate_is_not_attached(self) -> None:
        c = self.case
        c.permission()
        c.before_network = lambda: self.assertEqual("running", self.intake_job(c.operation_id).state)
        candidate = c.acquire()
        job = self.intake_job(c.operation_id)
        self.assertEqual("succeeded", job.state)
        self.assertEqual(1, job.max_attempts)
        self.assertIsNotNone(job.committed_output_sha256)
        self.assertEqual(1, c.count("document_attachment_candidates"))
        self.assertEqual(0, c.count("document_attachment_assertions"))
        queue = sqlite_workflow_queue_repository(Path(c.fixture.root), c.project)
        accepted = queue.accepted_output(job.job_id)
        self.assertIsNotNone(accepted)
        self.assertNotEqual(candidate.candidate_id, job.job_id)
        self.assertEqual(1, len(c.calls))

    def test_task_center_binds_exact_intake_and_safe_copy_return_context(self) -> None:
        import json

        from research_observatory_core.models import WorkflowTaskCenterRun

        c = self.case
        c.permission()
        c.acquire()
        job = self.intake_job(c.operation_id)
        queue = sqlite_workflow_queue_repository(Path(c.fixture.root), c.project)
        run = next(item for item in queue.task_center() if item.workflow_run_id == job.workflow_run_id)
        projected = WorkflowTaskCenterRun.model_validate(asdict(run)).model_dump(mode="json", by_alias=True)
        intake = projected["jobs"][0]["documentIntake"]
        self.assertEqual(c.operation_id, intake["operationId"])
        self.assertEqual(c.location.location_id, intake["copyId"])
        self.assertEqual(c.project, intake["projectId"])
        self.assertEqual(
            c.selection().association,
            tuple(
                intake[key]
                for key in ("sourceAssertionRevisionId", "workId", "workRevisionId", "versionId", "versionRevisionId")
            ),
        )
        raw = json.dumps(projected)
        self.assertNotIn(c.location.url, raw)
        self.assertNotIn(c.session, raw)

    def test_owned_download_and_inspection_publish_distinct_durable_phases(self) -> None:
        c = self.case
        c.permission()
        original = c.attachments._inspector

        def status():
            return c.attachments.status(
                source_assertion_revision_id=c.selection().source_assertion_revision_id,
                work_id=c.selection().work_id,
                work_revision_id=c.selection().work_revision_id,
                version_id=c.selection().version_id,
                version_revision_id=c.selection().version_revision_id,
                operation_id=c.operation_id,
                command_id=None,
                session_id=c.session,
                actor=c.actor,
            )

        def network():
            self.assertEqual("intake-running", status().state)
            self.assertEqual("intake-downloading", status().intake_code)
            self.assertEqual("intake-downloading", self.intake_job(c.operation_id).diagnostic_code)

        def inspect(*args, **kwargs):
            self.assertEqual("intake-running", status().state)
            self.assertEqual("intake-validating", status().intake_code)
            self.assertEqual(0, c.count("document_attachment_assertions"))
            return original(*args, **kwargs)

        c.before_network = network
        with patch.object(c.attachments, "_inspector", side_effect=inspect):
            c.acquire()
        self.assertEqual("candidate", status().state)
        self.assertIsNone(status().intake_code)

    def test_runtime_resource_denial_precedes_intake_and_keeps_confirmation_unconsumed(self) -> None:
        from research_observatory_core.main import DocumentAttachmentRuntime
        from research_observatory_core.ports.document_attachments import AttachmentProblem
        from research_observatory_core.repositories import sqlite_workflow_admission_binding
        from research_observatory_core.workflow_executor import (
            LocalAdmissionController,
            ProjectWorkerPolicy,
            WorkerCapacity,
            WorkerResources,
        )

        c = self.case
        c.permission()
        preview = c.service.preview(c.selection(), actor=c.actor)
        queue = sqlite_workflow_queue_repository(Path(c.fixture.root), c.project)
        demand = WorkerResources(1, 256 * 1024**2, 0, 1024**3)
        controller = LocalAdmissionController(interactive_reserve=WorkerResources(1, 256 * 1024**2, 0, 256 * 1024**2))
        binding = sqlite_workflow_admission_binding(
            queue,
            controller=controller,
            policy=ProjectWorkerPolicy(c.project, demand, {"document": demand}, {"document": 1}),
        )
        binding = replace(binding, capacity=lambda: WorkerCapacity(16, 16 * 1024**3, 0, 64 * 1024**3))
        runtime = DocumentAttachmentRuntime(
            c.fixture.service, c.fixture.service, lambda *_: c.objects, admission_factory=lambda *_: binding
        )
        held = controller.reserve(binding, "document", local_limit=1)
        self.assertIsNotNone(held)
        operation = new_uuid_v7()
        with patch.object(runtime, "_acquisition", return_value=(c.service, c.actor)):
            with self.assertRaises(AttachmentProblem):
                runtime.acquisition_download(
                    c.fixture.root,
                    c.project,
                    c.session,
                    preview.preview_id,
                    confirmation=preview.confirmation,
                    operation_id=operation,
                    trace_id="a" * 32,
                    cancellation_requested=lambda: False,
                )
            self.assertEqual(0, c.count("document_intake_jobs"))
            self.assertEqual([], c.calls)
            controller.release(held)
            with patch.object(c.fixture.service, "native_context", return_value=c.session, create=True):
                runtime.acquisition_download(
                    c.fixture.root,
                    c.project,
                    c.session,
                    preview.preview_id,
                    confirmation=preview.confirmation,
                    operation_id=operation,
                    trace_id="a" * 32,
                    cancellation_requested=lambda: False,
                )
        self.assertEqual(1, c.count("document_intake_jobs"))
        self.assertEqual(1, len(c.calls))
        token = controller.reserve(binding, "document", local_limit=1)
        self.assertIsNotNone(token, "runtime releases its resource reservation at the terminal safe point")
        controller.release(token)

    def test_expired_intake_is_abandoned_without_dispatch_and_requires_new_confirmation(self) -> None:
        from datetime import datetime, timedelta

        c = self.case
        c.permission()
        c.operation_id = new_uuid_v7()
        preview = c.service.preview(c.selection(), actor=c.actor)
        claim = c.repository.begin_attempt(
            c.selection(),
            operation_id=c.operation_id,
            session_id=c.session,
            confirmation_sha256=preview.confirmation_sha256,
            expected_policy_revision_id=preview.provider_policy_revision_id,
            actor=c.actor,
        )
        with closing(open_canonical_database(c.database, expected_project_id=c.project)) as db:
            original = tuple(
                db.execute(
                    "SELECT session_id,selection_json,confirmation_sha256 FROM acquisition_attempts "
                    "WHERE operation_id=?",
                    (c.operation_id,),
                ).fetchone()
            )
        after_expiry = (
            (datetime.fromisoformat(claim.lease_expires_at.replace("Z", "+00:00")) + timedelta(seconds=1))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        with patch("research_observatory_core.document_attachment_repository._now", return_value=after_expiry):
            status = c.attachments.status(
                source_assertion_revision_id=c.selection().source_assertion_revision_id,
                work_id=c.selection().work_id,
                work_revision_id=c.selection().work_revision_id,
                version_id=c.selection().version_id,
                version_revision_id=c.selection().version_revision_id,
                operation_id=c.operation_id,
                command_id=None,
                session_id="d" * 32,
                actor=c.actor,
            )
        self.assertEqual("intake-failed", status.state)
        self.assertEqual("attempts-exhausted", status.intake_code)
        self.assertEqual("failed", self.intake_job(c.operation_id).state)
        self.assertEqual([], c.calls)
        self.assertEqual(0, c.count("document_attachment_assertions"))
        self.assertEqual(0, c.count("acquisition_attempt_results"), "no invented transfer outcome")
        with closing(open_canonical_database(c.database, expected_project_id=c.project)) as db:
            self.assertEqual(
                original,
                tuple(
                    db.execute(
                        "SELECT session_id,selection_json,confirmation_sha256 FROM acquisition_attempts "
                        "WHERE operation_id=?",
                        (c.operation_id,),
                    ).fetchone()
                ),
            )
            self.assertEqual(
                "abandoned",
                db.execute(
                    "SELECT state FROM workflow_job_attempts WHERE attempt_id=?",
                    (claim.attempt_id,),
                ).fetchone()[0],
            )
        old_operation = c.operation_id
        c.acquire()
        self.assertNotEqual(old_operation, c.operation_id)
        self.assertEqual(1, len(c.calls), "only a fresh explicit acquisition dispatches")
        self.assertEqual(2, c.count("document_intake_jobs"))

    def test_retained_recovery_rechecks_changed_allowed_policy_and_later_denial(self) -> None:
        from research_observatory_core.ports.acquisition import AcquisitionProblem

        c = self.case
        c.permission()
        candidate = c.acquire()
        origin = c.operation_id
        c.permission()
        recovery = new_uuid_v7()
        session = "d" * 32
        c.repository.recover_candidate(
            candidate.candidate_id,
            original_operation_id=origin,
            recovery_operation_id=recovery,
            session_id=session,
            selection=c.selection(),
            confirmation_sha256=candidate.candidate_sha256,
            actor=c.actor,
        )
        c.permission("denied")
        with self.assertRaises(AcquisitionProblem) as denied:
            c.attachments.commit(
                candidate.candidate_id,
                confirmation_sha256=candidate.candidate_sha256,
                command_id=new_uuid_v7(),
                actor=c.actor,
                operation_id=recovery,
                session_id=session,
                match_confirmed=True,
                permitted_use="project-only",
                exact_selection=c.selection().association,
            )
        self.assertEqual("acquisition-rights-denied", denied.exception.code)
        self.assertEqual(0, c.count("document_attachment_assertions"))
        self.assertEqual(1, c.count("document_attachment_recoveries"))
        self.assertEqual(1, len(c.calls))

    def test_failed_owned_partial_cleanup_stops_http_retry_and_retains_safe_failure(self) -> None:
        c = self.case
        c.permission()
        c.responses = [
            (
                200,
                [(b"content-type", b"text/plain")],
                [b"Synthetic interrupted copy", httpcore2.ReadError("synthetic interruption")],
            ),
            (200, [(b"content-type", b"text/plain")], [b"Synthetic replacement copy\n"]),
        ]
        keep = Path(c.fixture.root) / "exports/unrelated.partial"
        keep.parent.mkdir(exist_ok=True)
        keep.write_bytes(b"Synthetic unrelated retained data")
        original_unlink = Path.unlink
        denied_cleanup: list[Path] = []

        def deny_owned(path: Path, *args, **kwargs):
            if path.suffix == ".partial" and path.is_relative_to(Path(c.fixture.root) / ".tmp"):
                denied_cleanup.append(path)
                raise PermissionError("synthetic owned cleanup denied")
            return original_unlink(path, *args, **kwargs)

        problem = None
        with patch.object(Path, "unlink", new=deny_owned):
            try:
                c.acquire()
            except ObjectStoreProblem as error:
                problem = error
        self.assertTrue(denied_cleanup, "the real owned staging deletion must be faulted")
        self.assertIsNotNone(problem, "cleanup failure must stop intake instead of accepting another HTTP copy")
        self.assertEqual(1, len(c.calls))
        self.assertEqual(b"Synthetic unrelated retained data", keep.read_bytes())
        self.assertEqual(0, c.count("document_attachment_candidates"))
        self.assertEqual(1, c.count("reconciliation_assertions"))
        with closing(open_canonical_database(c.database, expected_project_id=c.project)) as db:
            result = db.execute(
                "SELECT outcome,code FROM acquisition_attempt_results WHERE operation_id=?",
                (c.operation_id,),
            ).fetchone()
        self.assertEqual(("failed", "acquisition-cleanup-required"), tuple(result))

    def test_cleanup_failure_during_queue_cancellation_remains_failed(self) -> None:
        from research_observatory_core.document_attachment_repository import _now
        from research_observatory_core.ports.workflow_executor import WorkflowActor

        c = self.case
        c.permission()
        original_unlink = Path.unlink

        def cancel_during_stream():
            job = self.intake_job(c.operation_id)
            sqlite_workflow_queue_repository(Path(c.fixture.root), c.project).request_cancellation(
                job.job_id,
                actor=WorkflowActor(c.actor.actor_id, "human", "researcher"),
                now=_now(),
                reason_code="document-user-cancel",
                interruption_kind="user-cancel",
            )
            c.during_stream = lambda: None

        def deny_owned(path: Path, *args, **kwargs):
            if path.suffix == ".partial" and path.is_relative_to(Path(c.fixture.root) / ".tmp"):
                raise PermissionError("synthetic owned cleanup denied")
            return original_unlink(path, *args, **kwargs)

        c.during_stream = cancel_during_stream
        with patch.object(Path, "unlink", new=deny_owned), self.assertRaises(ObjectStoreProblem):
            c.acquire()
        job = self.intake_job(c.operation_id)
        self.assertEqual("failed", job.state)
        self.assertEqual("acquisition-cleanup-required", job.diagnostic_code)
        self.assertEqual(0, c.count("document_attachment_candidates"))
        self.assertEqual(1, c.count("acquisition_attempt_results"))
        self.assertEqual(1, len(c.calls))

    def test_fresh_session_recovers_candidate_without_redownload_or_rewriting_origin(self) -> None:
        c = self.case
        c.permission()
        candidate = c.acquire()
        old_operation, old_session = c.operation_id, c.session
        new_operation, new_session = new_uuid_v7(), "b" * 32
        recovered = c.repository.recover_candidate(
            candidate.candidate_id,
            original_operation_id=old_operation,
            recovery_operation_id=new_operation,
            session_id=new_session,
            selection=c.selection(),
            confirmation_sha256=candidate.candidate_sha256,
            actor=c.actor,
        )
        self.assertEqual(candidate, recovered)
        attachment = c.attachments.commit(
            recovered.candidate_id,
            confirmation_sha256=recovered.candidate_sha256,
            command_id=new_uuid_v7(),
            actor=c.actor,
            operation_id=new_operation,
            session_id=new_session,
            match_confirmed=True,
            permitted_use="project-only",
            exact_selection=c.selection().association,
        )
        self.assertEqual(candidate.object_sha256, attachment.object_sha256)
        self.assertEqual(1, len(c.calls))
        self.assertEqual(1, c.count("document_acquisition_sources"))
        with closing(open_canonical_database(c.database, expected_project_id=c.project)) as db:
            original = db.execute(
                "SELECT operation_id,session_id FROM document_attachment_operations WHERE candidate_id=?",
                (candidate.candidate_id,),
            ).fetchone()
        self.assertEqual((old_operation, old_session), tuple(original))

    def test_local_access_need_keeps_metadata_without_network_permission_or_full_text(self) -> None:
        c = self.case
        selection = c.selection()
        for kind in ("unknown", "unavailable", "rights-denied", "entitlement-required"):
            c.repository.record_access_need(
                selection,
                command_id=new_uuid_v7(),
                kind=kind,
                channel="institutional",
                actor=c.actor,
            )
        needs = c.repository.access_needs(selection, actor=c.actor)
        self.assertEqual({"unknown", "unavailable", "rights-denied", "entitlement-required"}, {n.kind for n in needs})
        self.assertEqual([], c.calls)
        self.assertEqual(0, c.count("acquisition_attempts"))
        self.assertEqual(0, c.count("document_attachment_assertions"))
        self.assertEqual(1, c.count("reconciliation_assertions"))
        self.assertIsNone(c.repository.rights.current(c.location.rights_subject, actor=c.actor))

    def test_candidate_and_queue_output_roll_back_together_on_queue_failure(self) -> None:
        from research_observatory_core.repositories import _SqliteWorkflowQueueRepository

        c = self.case
        c.permission()
        prior_outputs = c.count("workflow_committed_outputs")
        with (
            patch.object(
                _SqliteWorkflowQueueRepository,
                "_complete_with_connection",
                side_effect=RuntimeError("synthetic output fault"),
            ),
            self.assertRaises(RuntimeError),
        ):
            c.acquire()
        self.assertEqual(0, c.count("document_attachment_candidates"))
        self.assertEqual(0, c.count("document_acquisition_sources"))
        self.assertEqual(0, c.count("document_attachment_operations"))
        self.assertEqual(prior_outputs, c.count("workflow_committed_outputs"))
        self.assertEqual("failed", self.intake_job(c.operation_id).state)
        self.assertEqual(1, len(c.calls))

    def test_core_generic_retry_cannot_replay_an_acquisition(self) -> None:
        from research_observatory_core.ports.acquisition import AcquisitionProblem
        from research_observatory_core.ports.workflow_executor import WorkflowActor, WorkflowQueueConflict

        c = self.case
        c.permission()
        c.responses = [(500, [], [])]
        with self.assertRaises(AcquisitionProblem):
            c.acquire()
        job = self.intake_job(c.operation_id)
        queue = sqlite_workflow_queue_repository(Path(c.fixture.root), c.project)
        with self.assertRaisesRegex(WorkflowQueueConflict, "fresh source review"):
            queue.retry_as_continuation(
                job.job_id,
                expected_snapshot_revision=1,
                expected_history_sequence=1,
                idempotency_key=new_uuid_v7(),
                actor=WorkflowActor(c.actor.actor_id, "human", "researcher"),
                now=c.actor.occurred_at,
            )
        self.assertEqual(1, len(c.calls))
        self.assertEqual(1, c.count("document_intake_jobs"))

    def test_retained_candidate_listing_is_owned_exact_metadata_only(self) -> None:
        from research_observatory_core.ports.acquisition import AccessNeedSelection

        c = self.case
        c.permission()
        candidate = c.acquire()
        selection = AccessNeedSelection.model_validate(
            {
                key: value
                for key, value in c.selection().model_dump().items()
                if key in AccessNeedSelection.model_fields and not key.startswith("location_")
            }
        )
        pending = c.attachments.retained_candidates(selection, actor=c.actor)
        self.assertEqual((candidate.candidate_id,), tuple(item["candidateId"] for item in pending))
        self.assertEqual({"candidateId", "sourceName", "originalOperationId", "copyId"}, set(pending[0]))
        self.assertEqual(c.location.location_id, pending[0]["copyId"])
        self.assertEqual(0, c.count("document_attachment_assertions"))
        self.assertEqual(1, len(c.calls))

    def test_access_annotation_without_a_known_location_is_idempotent_and_local(self) -> None:
        from research_observatory_core.ports.acquisition import AccessNeedSelection

        c = self.case
        selection = AccessNeedSelection.model_validate(
            {
                key: value
                for key, value in c.selection().model_dump().items()
                if key in AccessNeedSelection.model_fields and not key.startswith("location_")
            }
        )
        command = new_uuid_v7()
        first = c.repository.record_access_need(
            selection, command_id=command, kind="entitlement-required", channel="manual", actor=c.actor
        )
        self.assertEqual(
            first,
            c.repository.record_access_need(
                selection, command_id=command, kind="entitlement-required", channel="manual", actor=c.actor
            ),
        )
        self.assertEqual(1, c.count("document_access_needs"))
        self.assertEqual([], c.calls)
        self.assertEqual(0, c.count("document_attachment_candidates"))


if __name__ == "__main__":
    unittest.main()
