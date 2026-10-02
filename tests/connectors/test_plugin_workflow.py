"""A queued plugin job binds exact package, input and accepted project authority."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_manifest import PluginInvocationRequest  # noqa: E402
from research_observatory_core.connectors.plugin_package_intake import inspect_plugin_archive  # noqa: E402
from research_observatory_core.connectors.plugin_workflow import (  # noqa: E402
    PluginJobInput,
    bind_plugin_claim,
    build_plugin_job,
)
from research_observatory_core.connectors.providers import ProviderProblem  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.ingestion.preview_workflow import PreviewIntentContext  # noqa: E402
from research_observatory_core.ports.workflow_executor import (  # noqa: E402
    WorkflowActor,
    WorkflowJobAuthority,
    WorkflowJobClaim,
)

from tests.connectors.test_plugin_package_intake import archive  # noqa: E402

PROJECT = "0190a000-0000-7000-8000-000000000040"
NOW = "2026-10-01T12:00:00.000Z"


class PluginWorkflowTests(unittest.TestCase):
    def test_exact_input_claim_and_tampered_manifest_binding(self):
        inspected = inspect_plugin_archive(archive()[0])
        payload = b'{"identifier":"synthetic-1"}'
        request = PluginInvocationRequest(
            project_id=PROJECT,
            invocation_id=new_uuid_v7(),
            scientific_request_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
            operation=inspected.manifest.operations[0],
            destination=inspected.manifest.destinations[0],
        )
        inputs = PluginJobInput(
            request=request,
            plugin_id=inspected.manifest.plugin_id,
            package_sha256=inspected.package_sha256,
            manifest_sha256=inspected.manifest_sha256,
            signature_sha256=inspected.signature_sha256,
            authorization_request_sha256="sha256:" + "7" * 64,
            consent_preview_id=new_uuid_v7(),
            consent_confirmation_sha256="sha256:" + "5" * 64,
            consent_retention_sha256="sha256:" + "6" * 64,
            input_object_sha256=hashlib.sha256(payload).hexdigest(),
            input_byte_length=len(payload),
            intent=PreviewIntentContext(
                project_id=PROJECT,
                domain_project_id=new_uuid_v7(),
                intent_id=new_uuid_v7(),
                revision_id=new_uuid_v7(),
                content_hash="sha256:" + "1" * 64,
                status="accepted",
            ),
            policy_hash="sha256:" + "2" * 64,
            job_epoch="3" * 32,
        )
        submission = build_plugin_job(inputs, actor=WorkflowActor(new_uuid_v7(), "human", "local-researcher"), now=NOW)
        authority = WorkflowJobAuthority(
            submission.definition_json,
            submission.snapshot_json,
            submission.definition_record_sha256,
            submission.snapshot_record_sha256,
        )
        claim = WorkflowJobClaim(
            project_id=PROJECT,
            workflow_run_id=submission.workflow_run_id,
            job_id=submission.job_id,
            step_run_id=submission.step_run_id,
            activity_type=submission.activity_type,
            concurrency_class=submission.concurrency_class,
            attempt_id=new_uuid_v7(),
            attempt_number=1,
            worker_id=new_uuid_v7(),
            lease_token="synthetic",
            lease_generation=1,
            lease_expires_at=NOW,
            idempotency_key=submission.idempotency_key,
            command_fingerprint=submission.command_fingerprint,
            latest_checkpoint=None,
        )
        bind_plugin_claim(authority, claim, inputs)
        with self.assertRaises(ProviderProblem):
            bind_plugin_claim(authority, claim, inputs.model_copy(update={"manifest_sha256": "sha256:" + "4" * 64}))


if __name__ == "__main__":
    unittest.main()
