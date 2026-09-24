"""Read-only recovery of exact submitted source requests, not a second send."""

from __future__ import annotations

import json
from unittest.mock import patch

from research_observatory_core.connectors.providers import ProviderProblem
from research_observatory_core.domain_contracts import new_uuid_v7

from tests.connectors.test_connector_workflow import ConnectorWorkflowFixture


class ConnectorInspectionTests(ConnectorWorkflowFixture):
    def test_task_center_retry_does_not_duplicate_exact_source_preview(self):
        preview, job = self.schedule()
        self.worker.cancel(self.root, job.job_id)
        self.worker.run_pending()
        original = self.queue.task_center()[0]
        self.queue.retry_as_continuation(
            job.job_id,
            expected_snapshot_revision=original.snapshot_revision,
            expected_history_sequence=original.revision,
            idempotency_key="f" * 32,
            actor=self.worker._actor(),
            now=self.clock.now(),
        )
        recent = self.worker.recent(self.root)
        self.assertEqual(1, len(recent.items))
        self.assertEqual(job.job_id, recent.items[0].job_id)
        self.assertEqual(job.job_id, self.worker.inspect(self.root, preview.preview_id, 0).job.job_id)
        self.assertEqual([], self.calls)

    def test_lost_acknowledgment_is_resolved_by_exact_preview_after_restart(self):
        preview, job = self.schedule()
        pending = self.worker.inspect(self.root, preview.preview_id, 0)
        self.assertEqual(job.job_id, pending.job.job_id)
        self.assertIsNone(pending.observation)
        self.worker.run_pending()
        self.worker.shutdown()
        self.connectors = self.consent_service()
        self.worker = self.worker_service()
        result = self.worker.inspect(self.root, preview.preview_id, 0)
        self.assertEqual(self.request.query.model_dump(mode="json", by_alias=True), json.loads(result.query_json))
        self.assertEqual(self.request.scientific_sha256(), result.scientific_request_sha256)
        self.assertEqual("succeeded", result.job.state)
        self.assertEqual("complete", result.observation.outcome)
        self.assertEqual(1, len(result.observation.records))
        self.assertEqual(1, len(self.calls))
        recent = self.worker.recent(self.root)
        self.assertEqual(preview.preview_id, recent.items[0].preview_id)
        for forbidden in (preview.confirmation, "sessionEpoch", "confirmation", "intentSha256"):
            self.assertNotIn(forbidden, result.model_dump_json(by_alias=True))

    def test_unknown_preview_is_not_a_zero_result_or_new_submission(self):
        self.assertIsNone(self.worker.inspect(self.root, new_uuid_v7(), 0))
        self.assertEqual([], self.calls)
        self.assertEqual((), self.worker.recent(self.root).items)

    def test_inspection_requires_explicit_inspect_right_and_valid_offset(self):
        preview, _ = self.schedule()
        stored = self.repository.operation(preview.preview_id)
        rights = self.rights.rights.model_copy(
            update={
                "inspect": self.rights.rights.inspect.model_copy(update={"value": "unknown", "basis": "not-reported"})
            }
        )
        denied = stored.model_copy(
            update={
                "preview": preview.model_copy(update={"retention": self.rights.model_copy(update={"rights": rights})})
            }
        )
        with patch.object(self.repository, "operation", return_value=denied), self.assertRaises(ProviderProblem):
            self.worker.inspect(self.root, preview.preview_id, 0)
        self.assertEqual([], self.calls)
        for offset in (-1, True, 1000):
            with self.assertRaises(ProviderProblem):
                self.worker.inspect(self.root, preview.preview_id, offset)

    def test_completed_inspection_is_paginated_and_never_fetches_again(self):
        preview, _ = self.schedule()
        self.worker.run_pending()
        first = self.worker.inspect(self.root, preview.preview_id, 0)
        count = first.observation.record_count
        self.assertGreater(count, 0)
        for offset in range(count):
            item = self.worker.inspect(self.root, preview.preview_id, offset)
            self.assertEqual(1, len(item.observation.records))
            self.assertEqual(offset, item.record_offset)
            self.assertTrue(
                all(
                    field.name in {"candidate.title", "candidate.oa-locations", "candidate.discovery"}
                    for field in item.observation.records[0].fields
                )
            )
        self.assertEqual(1, len(self.calls))
        with self.assertRaises(ProviderProblem):
            self.worker.inspect(self.root, preview.preview_id, count)
