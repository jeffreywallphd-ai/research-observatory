"""Summary jobs use actual project, Intent, privacy and durable worker authority."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_summaries import SUMMARY_ACTIVITY
from research_observatory_core.ingestion.summary_workflow import bind_summary_claim
from research_observatory_core.models import PrivacyPolicyUpdateRequest
from research_observatory_core.ports.import_previews import PreviewDraftChange, PreviewProblem
from research_observatory_core.ports.workflow_executor import WorkflowActor
from research_observatory_core.workflow_contracts import workflow_record_sha256
from research_observatory_core.workflow_executor import WorkflowActivityError

from tests.service import test_import_preview_service as fixture


class ImportSummaryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportPreviewServiceTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service, self.root = self.fixture.service, self.fixture.root
        self.preview = self.fixture.intake()
        self.service.schedule(self.root, self.preview)
        self.service.run_pending()
        self.adapters = self.fixture.adapters(Path(self.root), self.fixture.project_id)
        self.repository = self.adapters.previews
        self.actor = self.service.actor("4" * 32)
        self.repository.revise_draft(self.preview, PreviewDraftChange(expected_revision=0, actor=self.actor))
        self.queue = self.adapters.queue

    def test_same_authority_replays_job_and_real_worker_publishes_complete_summary(self):
        job = self.service.schedule_summary(self.root, self.preview, revision=1)
        self.assertEqual(job.job_id, self.service.schedule_summary(self.root, self.preview, revision=1).job_id)
        snapshot = json.loads(self.queue.authority(job.job_id).snapshot_json)
        self.assertEqual(
            self.fixture.intents.workspace(self.root).current.revision_id, snapshot["intent"]["revisionId"]
        )
        self.assertIsNone(self.repository.summary(self.preview, revision=1))
        self.service.run_pending()
        self.assertEqual("succeeded", self.queue.get(job.job_id).state)
        summary = self.repository.summary(self.preview, revision=1)
        self.assertEqual(job.job_id, summary.job_id)
        self.assertEqual(2, summary.result.counts.source_rows)
        self.assertEqual(1, summary.result.counts.included_records)
        self.assertEqual(1, summary.result.counts.coverage.doi)

    def test_queued_summary_cannot_compute_a_newer_edited_draft(self):
        job = self.service.schedule_summary(self.root, self.preview, revision=1)
        self.repository.revise_draft(self.preview, PreviewDraftChange(expected_revision=1, actor=self.actor))
        self.service.run_pending()
        self.assertEqual("failed", self.queue.get(job.job_id).state)
        self.assertIsNone(self.repository.summary(self.preview, revision=2))
        replacement = self.service.schedule_summary(self.root, self.preview, revision=2)
        self.assertNotEqual(job.job_id, replacement.job_id)
        self.service.run_pending()
        self.assertEqual("succeeded", self.queue.get(replacement.job_id).state)

    def test_ordinary_restart_reconstructs_exact_summary_authority(self):
        job = self.service.schedule_summary(self.root, self.preview, revision=1)
        self.service.shutdown()
        restarted = self.fixture.runtime()
        self.addCleanup(restarted.shutdown)
        restarted.attach(self.root)
        restarted.run_pending()
        self.assertEqual("succeeded", self.queue.get(job.job_id).state)
        self.assertEqual(job.job_id, self.repository.summary(self.preview, revision=1).job_id)

    def test_security_epoch_cancels_old_summary_before_claim_but_explicit_new_calculation_is_allowed(self):
        job = self.service.schedule_summary(self.root, self.preview, revision=1)
        self.service.shutdown()
        restarted = self.fixture.runtime("2" * 32)
        self.addCleanup(restarted.shutdown)
        restarted.attach(self.root)
        restarted.run_pending()
        old = self.queue.get(job.job_id)
        self.assertEqual("cancelled", old.state)
        self.assertEqual(0, old.attempt_count)
        self.assertIsNone(self.repository.summary(self.preview, revision=1))
        replacement = restarted.schedule_summary(self.root, self.preview, revision=1)
        self.assertNotEqual(job.job_id, replacement.job_id)
        restarted.run_pending()
        self.assertEqual("succeeded", self.queue.get(replacement.job_id).state)

    def test_cancel_summary_does_not_cancel_or_edit_preview(self):
        job = self.service.schedule_summary(self.root, self.preview, revision=1)
        self.service.cancel_summary(self.root, self.preview, revision=1, job_id=job.job_id)
        self.service.run_pending()
        self.assertEqual("cancelled", self.queue.get(job.job_id).state)
        self.assertIsNone(self.repository.summary(self.preview, revision=1))
        self.assertEqual(1, self.repository.draft(self.preview).revision)
        self.assertEqual(2, len(self.repository.draft_page(self.preview, revision=1, after=0, limit=10)))

    def test_summary_scheduling_rejects_stale_revision_or_closed_project(self):
        with self.assertRaises(PreviewProblem):
            self.service.schedule_summary(self.root, self.preview, revision=2)
        self.service.detach(self.root)
        self.fixture.projects.close(root=self.root, trace_id="4" * 32)
        with self.assertRaises(fixture.ProjectLifecycleProblem):
            self.service.schedule_summary(self.root, self.preview, revision=1)

    def retry(self, job, index):
        run = next(run for run in self.queue.task_center() if run.workflow_run_id == job.workflow_run_id)
        continued = self.queue.retry_as_continuation(
            job.job_id,
            expected_snapshot_revision=run.snapshot_revision,
            expected_history_sequence=run.revision,
            idempotency_key=f"synthetic-summary-retry-{index}",
            actor=WorkflowActor(self.fixture.actor, "human", "local-researcher"),
            now=self.fixture.now,
        )
        return self.queue.get(continued.jobs[0].job_id)

    def inputs(self):
        return self.service._action(self.root, lambda binding: self.service._summary_inputs(binding, self.preview, 1))

    def claim(self):
        claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.fixture.now,
            lease_duration_ms=30000,
            activity_types=(SUMMARY_ACTIVITY,),
        )
        self.assertIsNotNone(claim)
        return claim

    def test_task_center_continuation_and_retry_of_continuation_publish_actual_job(self):
        original = self.service.schedule_summary(self.root, self.preview, revision=1)
        self.service.cancel_summary(self.root, self.preview, revision=1, job_id=original.job_id)
        self.service.run_pending()
        first = self.retry(original, 1)
        self.assertEqual(first.job_id, self.service.summary_status(self.root, self.preview, revision=1)[1].job_id)
        self.service.cancel_summary(self.root, self.preview, revision=1, job_id=first.job_id)
        self.service.run_pending()
        second = self.retry(first, 2)
        self.assertEqual(second.job_id, self.service.schedule_summary(self.root, self.preview, revision=1).job_id)
        self.service.run_pending()
        self.assertEqual("succeeded", self.queue.get(second.job_id).state)
        summary, status = self.service.summary_status(self.root, self.preview, revision=1)
        self.assertEqual(second.job_id, status.job_id)
        self.assertEqual(second.job_id, summary.job_id)
        self.assertEqual("cancelled", self.queue.get(original.job_id).state)

    def test_binding_rejects_each_material_input_and_claim_substitution(self):
        job = self.service.schedule_summary(self.root, self.preview, revision=1)
        inputs, claim = self.inputs(), self.claim()
        authority = self.queue.authority(job.job_id)
        self.assertEqual(inputs, bind_summary_claim(authority, claim, inputs))
        changed_inputs = [
            inputs.model_copy(update=change)
            for change in (
                {"draft_revision": 2},
                {"parse_attempt_id": new_uuid_v7()},
                {"authority_hash": "sha256:" + "a" * 64},
                {"record_count": 3},
                {"algorithm": "other"},
            )
        ]
        changed_inputs += [
            inputs.model_copy(update={"preview": inputs.preview.model_copy(update=change)})
            for change in (
                {"source_sha256": "a" * 64},
                {"manifest_sha256": "b" * 64},
                {"rights_hash": "sha256:" + "c" * 64},
                {"resume_epoch": "2" * 32},
                {"policy_hash": "sha256:" + "d" * 64},
                {"intent": inputs.intent.model_copy(update={"revision_id": new_uuid_v7()})},
            )
        ]
        for changed in changed_inputs:
            with self.assertRaises(PreviewProblem):
                bind_summary_claim(authority, claim, changed)
        for change in (
            {"project_id": new_uuid_v7()},
            {"workflow_run_id": new_uuid_v7()},
            {"step_run_id": new_uuid_v7()},
            {"activity_type": "local-reference-preview"},
            {"idempotency_key": "wrong"},
            {"command_fingerprint": "sha256:" + "e" * 64},
        ):
            with self.assertRaises(PreviewProblem):
                bind_summary_claim(authority, replace(claim, **change), inputs)

    def test_continuation_requires_real_unsuccessful_predecessor_and_matching_authority(self):
        job = self.service.schedule_summary(self.root, self.preview, revision=1)
        inputs = self.inputs()
        self.service.cancel_summary(self.root, self.preview, revision=1, job_id=job.job_id)
        self.service.run_pending()
        child = self.retry(job, 1)
        claim = self.claim()
        source, source_authority = self.queue.get(job.job_id), self.queue.authority(job.job_id)
        authority = self.queue.authority(child.job_id)
        self.assertEqual(inputs, bind_summary_claim(authority, claim, inputs, predecessor=(source, source_authority)))
        for record in (
            None,
            replace(source, state="succeeded"),
            replace(source, state="running"),
            replace(source, job_id=new_uuid_v7()),
            replace(source, workflow_run_id=new_uuid_v7()),
        ):
            with self.assertRaises(PreviewProblem):
                bind_summary_claim(
                    authority, claim, inputs, predecessor=None if record is None else (record, source_authority)
                )
        for field in ("configuration", "policy", "intent"):
            source_snapshot = json.loads(source_authority.snapshot_json)
            key = next(key for key in source_snapshot[field] if key.endswith("Hash"))
            source_snapshot[field][key] = "sha256:" + "f" * 64
            changed = replace(
                source_authority,
                snapshot_json=json.dumps(source_snapshot),
                snapshot_record_sha256=workflow_record_sha256(source_snapshot),
            )
            with self.assertRaises(PreviewProblem):
                bind_summary_claim(authority, claim, inputs, predecessor=(source, changed))

    def test_current_privacy_change_after_page_prevents_receipt_publication(self):
        job = self.service.schedule_summary(self.root, self.preview, revision=1)
        bound_repository = self.service._action(self.root, lambda binding: binding.adapters.previews)
        append = bound_repository.append_summary_page

        def change_policy(*args, **kwargs):
            rows = append(*args, **kwargs)
            current = self.fixture.privacy.get(self.root)
            self.fixture.privacy.update(
                PrivacyPolicyUpdateRequest(
                    root=self.root,
                    expected_revision=current.revision,
                    network_policy=current.network_policy,
                    remote_model_approval=current.remote_model_approval,
                    telemetry_mode=current.telemetry_mode,
                    log_retention_days=current.log_retention_days,
                    document_retention=current.document_retention,
                    cache_retention_days=current.cache_retention_days,
                ),
                trace_id="4" * 32,
            )
            return rows

        with patch.object(bound_repository, "append_summary_page", side_effect=change_policy):
            self.service.run_pending()
        self.assertEqual("failed", self.queue.get(job.job_id).state)
        self.assertIsNone(self.repository.summary(self.preview, revision=1))

    def test_ordinary_mid_page_close_is_retryable_but_never_publishes_partial_summary(self):
        job = self.service.schedule_summary(self.root, self.preview, revision=1)
        bound_repository = self.service._action(self.root, lambda binding: binding.adapters.previews)
        with patch.object(
            bound_repository, "append_summary_page", side_effect=WorkflowActivityError("dependency-unavailable")
        ):
            self.service.run_pending()
        self.assertEqual("retry-scheduled", self.queue.get(job.job_id).state)
        self.assertIsNone(self.repository.summary(self.preview, revision=1))
        self.fixture.now = "2026-09-19T19:51:00.000Z"
        self.service.run_pending()
        self.assertEqual("succeeded", self.queue.get(job.job_id).state)
        self.assertEqual(2, self.queue.get(job.job_id).attempt_count)
