"""One confirmed page per durable job; the broker owns the sole network retry budget."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field, model_validator

from ..connector_service import ConnectorPreview, _fingerprint
from ..domain_contracts import new_uuid_v7
from ..ingestion.preview_workflow import PreviewIntentContext, build_local_import_job, local_import_definition
from ..ports.workflow_executor import WorkflowActor, WorkflowJobAuthority, WorkflowJobClaim, WorkflowJobSubmission
from ..workflow_contracts import workflow_record_sha256, workflow_snapshot_errors
from .contracts import ConnectorModel, InvocationId
from .providers import ProviderProblem

ACTIVITY = "scholarly-connector-page"


class ConnectorJobInput(ConnectorModel):
    schema_version: Literal["1.0"] = "1.0"
    preview: ConnectorPreview = Field(repr=False)
    intent: PreviewIntentContext
    session_epoch: str = Field(pattern=r"^[0-9a-f]{32}$", repr=False)
    predecessor_revision_id: InvocationId | None

    @model_validator(mode="after")
    def exact_authority(self) -> ConnectorJobInput:
        if (
            self.preview.request.project_id != self.intent.project_id
            or self.intent.status != "accepted"
            or self.preview.intent_revision_id != self.intent.revision_id
            or self.preview.intent_sha256 != self.intent.content_hash
        ):
            raise ValueError("connector-job-intent-mismatch")
        return self

    @property
    def project_id(self) -> str:
        return self.preview.request.project_id

    @property
    def configuration_id(self) -> str:
        return f"connector-page.{self.preview.preview_id}.{self.session_epoch}"

    @property
    def configuration_version(self) -> str:
        return "1.0.0"

    @property
    def configuration_hash(self) -> str:
        return _fingerprint(self.model_dump(mode="json", by_alias=True))

    @property
    def idempotency_key(self) -> str:
        return _fingerprint([ACTIVITY, self.preview.preview_id])

    def policy_reference(self) -> dict[str, str]:
        return {
            "policyId": "scholarly-connector-policy",
            "policyVersion": "1.0.0",
            "policyHash": self.preview.policy_sha256,
        }


def _definition(identity: str, revision: str, now: str):
    definition = local_import_definition(
        identity,
        revision,
        now,
        input_type=ConnectorJobInput,
        version="1.0.0",
        activity=ACTIVITY,
        step_key="fetch-confirmed-page",
        schema_id="scholarly-connector-page",
        key_scope="scholarly-connector-page",
        scopes=["objects-read", "artifacts-write", "policy-read"],
    )
    step = definition["steps"][0]
    step["permissions"]["network"] = "policy-controlled"
    # No multiplicative queue + HTTP retry budget. Explicit next-page/resume
    # commands obtain new current consent and retain earlier failed attempts.
    step["retryPolicy"]["maxAttempts"] = 1
    step["retryPolicy"]["retryableErrorCodes"] = []
    return definition


def build_connector_job(inputs: ConnectorJobInput, *, actor: WorkflowActor, now: str) -> WorkflowJobSubmission:
    inputs = ConnectorJobInput.model_validate(inputs)
    return build_local_import_job(
        inputs,
        _definition(new_uuid_v7(), new_uuid_v7(), now),
        actor=actor,
        now=now,
        step_key="fetch-confirmed-page",
        idempotency_key=inputs.idempotency_key,
    )


def bind_connector_claim(authority: WorkflowJobAuthority, claim: WorkflowJobClaim, inputs: ConnectorJobInput) -> None:
    try:
        definition, snapshot = json.loads(authority.definition_json), json.loads(authority.snapshot_json)
        jobs = [job for job in snapshot["jobs"] if job["jobId"] == claim.job_id]
        if (
            workflow_snapshot_errors(definition, snapshot)
            or definition
            != _definition(
                definition["workflowDefinitionId"], definition["definitionRevisionId"], definition["createdAt"]
            )
            or workflow_record_sha256(definition) != authority.definition_record_sha256
            or workflow_record_sha256(snapshot) != authority.snapshot_record_sha256
            or snapshot["projectId"] != inputs.project_id
            or claim.project_id != inputs.project_id
            or snapshot["workflowRunId"] != claim.workflow_run_id
            or claim.activity_type != ACTIVITY
            or claim.concurrency_class != "document"
            or claim.command_fingerprint != inputs.configuration_hash
            or claim.idempotency_key != inputs.idempotency_key
            or snapshot["intent"] != inputs.intent.reference()
            or snapshot["policy"] != inputs.policy_reference()
            or snapshot["configuration"]
            != {
                "configurationId": inputs.configuration_id,
                "configurationVersion": inputs.configuration_version,
                "configurationHash": inputs.configuration_hash,
            }
            or snapshot["executor"]["profile"] != "local"
            or len(jobs) != 1
            or jobs[0]["stepRunId"] != claim.step_run_id
        ):
            raise ValueError
    except ValueError, KeyError, TypeError:
        raise ProviderProblem("policy-denied") from None
