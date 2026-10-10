"""Actual encrypted retained jobs and source fences; authored parser output."""

import hashlib
import sys
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.document_parse_workflow import DocumentParseInput  # noqa: E402
from research_observatory_core.document_revisions import DocumentRevisionProblem  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.documents import test_document_revision_repository as fixtures  # noqa: E402
from tests.workflows import test_local_workflow_executor as workflows  # noqa: E402


class ParsingQualityRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def submit(self):
        f = self.f
        inputs = DocumentParseInput(
            project_id=f.f.source.project_id,
            command_id=new_uuid_v7(),
            actor_id=f.actor.actor_id,
            session_id=f.f.session,
            source=f.f.source,
            selection=f.f.request.selection,
            intent=f.intent,
            policy_sha256=f.actor.policy_sha256,
        )
        return f.repository.submit(inputs)

    def test_partial_retained_quality_precedes_acceptance_and_reopen_never_rewrites_history(self):
        f = self.f
        result = f.parse(
            change=lambda value: value["quality"]["warnings"].append(
                {"code": "parser-partial-output", "severity": "warning", "nodeId": None, "detail": "private output"}
            )
        )
        objects = f.f.fixture.project_root / "objects"
        before_objects = {
            str(p.relative_to(objects)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in objects.rglob("*")
            if p.is_file()
        }
        before = f.counts()
        report = f.repository.quality(result.binding.attempt.job_id)
        self.assertEqual(result.binding.source, report.source)
        self.assertEqual(result.binding.attempt.attempt_id, report.attempt_id)
        self.assertEqual(result.result_id, report.result_id)
        self.assertEqual(result.revision_id, report.result_revision_id)
        self.assertEqual(result.object_sha256, report.result_sha256)
        self.assertIn("parser-partial-output", report.assessment.review_reasons)
        self.assertEqual(report, f.reopen().quality(report.job_id))
        self.assertEqual((), f.repository.history(f.f.source.document_id))
        self.assertEqual(before, f.counts())
        self.assertEqual(
            before_objects,
            {
                str(p.relative_to(objects)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in objects.rglob("*")
                if p.is_file()
            },
        )
        self.assertNotIn("private output", report.model_dump_json(by_alias=True))

    def test_queued_failed_and_cancelled_jobs_have_truthful_null_result_and_exact_attempt(self):
        f = self.f
        for terminal in ("failed", "cancelled"):
            job = self.submit()
            queued = f.repository.quality(job.job_id)
            self.assertEqual("runnable", queued.job_state)
            self.assertIsNone(queued.attempt_id)
            self.assertIsNone(queued.result_id)
            self.assertEqual("not-yet-available", queued.assessment.availability)
            self.assertIsNone(queued.assessment.dimensions.encoding.count)
            claim = f.queue.claim_next(
                worker_id=workflows.WORKER_A,
                concurrency_classes=("document",),
                activity_types=("document-parse",),
                now=f.now,
                lease_duration_ms=30_000,
            )
            assert claim is not None
            self.assertEqual(job.job_id, claim.job_id)
            f.queue.start(claim, now=f.now)
            if terminal == "failed":
                f.queue.fail(claim, now=f.now, error_code="parser-input-invalid")
            else:
                f.queue.cancel(claim, now=f.now, reason_code="user-cancelled")
            report = f.reopen().quality(job.job_id)
            self.assertEqual(terminal, report.job_state)
            self.assertEqual(claim.attempt_id, report.attempt_id)
            self.assertIsNone(report.result_id)
            self.assertEqual("unavailable", report.assessment.availability)
            self.assertTrue(report.assessment.review_required)
            self.assertIsNone(report.assessment.dimensions.table_cell_confidence.reported_count)

    def test_authentic_other_job_output_with_same_source_and_selection_is_denied(self):
        f = self.f
        first, second = f.parse(), f.parse("Other private retained output")
        first_job, second_job = first.binding.attempt.job_id, second.binding.attempt.job_id
        self.assertEqual(first.binding.source, second.binding.source)
        self.assertEqual(first.binding.producer, second.binding.producer)
        self.assertEqual(first.binding.selection_sha256, second.binding.selection_sha256)
        self.assertNotEqual(first_job, second_job)
        self.assertNotEqual(first.binding.attempt.attempt_id, second.binding.attempt.attempt_id)
        before_reports = (f.repository.quality(first_job), f.repository.quality(second_job))
        before_jobs = (f.queue.get(first_job), f.queue.get(second_job))
        before_counts = f.counts()
        objects = f.f.fixture.project_root / "objects"
        before_objects = {
            str(p.relative_to(objects)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in objects.rglob("*")
            if p.is_file()
        }
        queue_type = type(f.queue)
        original_status = queue_type._accepted_status_with_connection
        with closing(open_canonical_database(f.database, expected_project_id=f.f.source.project_id)) as connection:
            _, other_output = original_status(f.queue, connection, second_job)
        self.assertIsNotNone(other_output)

        def substituted_output(queue, connection, job_id):
            job, output = original_status(queue, connection, job_id)
            return job, other_output if job_id == first_job else output

        with (
            patch.object(queue_type, "_accepted_status_with_connection", substituted_output),
            self.assertRaises(DocumentRevisionProblem) as denied,
        ):
            f.repository.quality(first_job)
        self.assertEqual("parsing-quality-result-binding-invalid", str(denied.exception))
        self.assertEqual(before_reports, (f.repository.quality(first_job), f.repository.quality(second_job)))
        self.assertEqual(before_jobs, (f.queue.get(first_job), f.queue.get(second_job)))
        self.assertEqual(before_counts, f.counts())
        self.assertEqual((), f.repository.history(f.f.source.document_id))
        self.assertEqual(
            before_objects,
            {
                str(p.relative_to(objects)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in objects.rglob("*")
                if p.is_file()
            },
        )

    def test_current_source_rights_actor_intent_privacy_resource_and_delivery_stop_deny(self):
        f = self.f
        result = f.parse()
        job = result.binding.attempt.job_id
        for replacement in (
            replace(cast(Any, f.actor), actor_type="worker"),
            replace(f.actor, intent_sha256="0" * 64),
            replace(f.actor, policy_sha256="0" * 64),
        ):
            with (
                self.subTest(actor=replacement),
                patch.object(f.repository, "actor", lambda selected=replacement: selected),
                self.assertRaises(DocumentRevisionProblem),
            ):
                f.repository.quality(job)
        f.f.permit(derive="denied")
        with self.assertRaises(DocumentRevisionProblem):
            f.repository.quality(job)
        f.f.permit()
        with (
            patch("research_observatory_core.document_viewer_allocations.ViewerArtifactReads.cost_multiplier", 10**9),
            self.assertRaises(DocumentRevisionProblem),
        ):
            f.repository.quality(job)
        with self.assertRaises(DocumentRevisionProblem):
            f.repository.quality(job, cancelled=lambda: True)
        before = f.counts()
        with self.assertRaises(DocumentRevisionProblem):
            f.repository.quality(new_uuid_v7())
        self.assertEqual(before, f.counts())


if __name__ == "__main__":
    unittest.main(verbosity=2)
