"""Exact lexical activity authority uses the existing executor-neutral contract."""

import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.workflow_contracts import workflow_snapshot_errors  # noqa: E402

from tests.search import test_search_run_values as fixtures  # noqa: E402


class SearchWorkflowTests(unittest.TestCase):
    def test_submission_is_exact_current_local_document_lane_activity(self):
        from research_observatory_core.search.workflow import submission

        inputs = fixtures.SearchRunValueTests().request()
        value = submission(inputs, now="2026-10-16T00:00:00.000Z")
        definition, snapshot = json.loads(value.definition_json), json.loads(value.snapshot_json)
        self.assertFalse(workflow_snapshot_errors(definition, snapshot))
        self.assertEqual("lexical-search", value.activity_type)
        self.assertEqual("document", value.concurrency_class)
        self.assertEqual(inputs.idempotency_key, value.idempotency_key)
        self.assertEqual(inputs.configuration_hash, value.command_fingerprint)
        self.assertEqual(inputs.intent.reference(), snapshot["intent"])
        self.assertEqual(inputs.policy_reference(), snapshot["policy"])
        self.assertEqual("local", snapshot["executor"]["profile"])

    def test_definition_and_snapshot_cannot_be_substituted_under_request_hash(self):
        from research_observatory_core.ports.workflow_executor import WorkflowJobAuthority, WorkflowJobClaim
        from research_observatory_core.search.workflow import bind_claim, submission

        inputs = fixtures.SearchRunValueTests().request()
        value = submission(inputs, now="2026-10-16T00:00:00.000Z")
        authority = WorkflowJobAuthority(
            definition_json=value.definition_json,
            snapshot_json=value.snapshot_json,
            definition_record_sha256=value.definition_record_sha256,
            snapshot_record_sha256=value.snapshot_record_sha256,
        )
        claim = WorkflowJobClaim(
            job_id=value.job_id,
            project_id=value.project_id,
            workflow_run_id=value.workflow_run_id,
            step_run_id=value.step_run_id,
            attempt_id="0199e895-0000-7000-8000-000000000050",
            attempt_number=1,
            worker_id="0199e895-0000-7000-8000-000000000051",
            lease_generation=1,
            lease_token="fixture-opaque-token",
            lease_expires_at="2026-10-16T00:00:30.000Z",
            activity_type=value.activity_type,
            concurrency_class=value.concurrency_class,
            idempotency_key=value.idempotency_key,
            command_fingerprint=value.command_fingerprint,
            latest_checkpoint=None,
        )
        self.assertEqual(inputs, bind_claim(authority, claim, inputs))
        changed = json.loads(authority.snapshot_json)
        changed["configuration"]["configurationId"] = "forged"
        with self.assertRaises(ValueError):
            bind_claim(replace(authority, snapshot_json=json.dumps(changed)), claim, inputs)


if __name__ == "__main__":
    unittest.main()
