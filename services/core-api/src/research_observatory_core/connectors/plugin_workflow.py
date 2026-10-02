"""Exact, restartable connector-plugin binding for the existing durable queue."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..connector_service import _fingerprint
from ..domain_contracts import new_uuid_v7
from ..ingestion.preview_workflow import PreviewIntentContext, build_local_import_job, local_import_definition
from ..ports.workflow_executor import WorkflowActor, WorkflowJobAuthority, WorkflowJobClaim, WorkflowJobSubmission
from ..workflow_contracts import workflow_record_sha256, workflow_snapshot_errors
from .contracts import ConnectorModel, InvocationId, ProjectId
from .plugin_manifest import PluginId, PluginInvocationRequest, Sha256
from .providers import ProviderProblem

ACTIVITY = "plugin-connector-invocation"


class PluginJobInput(ConnectorModel):
    schema_version: Literal["1.0"] = "1.0"
    request: PluginInvocationRequest = Field(repr=False)
    plugin_id: PluginId
    package_sha256: Sha256
    manifest_sha256: Sha256
    signature_sha256: Sha256
    authorization_request_sha256: Sha256
    consent_preview_id: InvocationId
    consent_confirmation_sha256: Sha256
    consent_retention_sha256: Sha256
    input_object_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    input_byte_length: Annotated[int, Field(strict=True, ge=0, le=10 * 1_048_576)]
    intent: PreviewIntentContext
    policy_hash: Sha256
    job_epoch: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]

    @model_validator(mode="after")
    def exact_project_intent(self) -> PluginJobInput:
        if (
            self.intent.status != "accepted"
            or self.intent.project_id != self.request.project_id
            or self.consent_preview_id == self.request.invocation_id
        ):
            raise ValueError("plugin-job-intent-invalid")
        return self

    @property
    def project_id(self) -> ProjectId:
        return self.request.project_id

    @property
    def invocation_id(self) -> InvocationId:
        return self.request.invocation_id

    @property
    def configuration_id(self) -> str:
        return f"plugin-connector.{self.invocation_id}.{self.job_epoch}"

    @property
    def configuration_version(self) -> str:
        return "1.0.0"

    @property
    def configuration_hash(self) -> str:
        return _fingerprint(self.model_dump(mode="json", by_alias=True))

    @property
    def idempotency_key(self) -> str:
        return _fingerprint([ACTIVITY, self.invocation_id, self.package_sha256, self.manifest_sha256])

    def policy_reference(self) -> dict[str, str]:
        return {
            "policyId": "plugin-connector-policy",
            "policyVersion": "1.0.0",
            "policyHash": self.policy_hash,
        }


def _definition(identity: str, revision: str, now: str) -> dict:
    definition = local_import_definition(
        identity,
        revision,
        now,
        input_type=PluginJobInput,
        version="1.0.0",
        activity=ACTIVITY,
        step_key="invoke-signed-plugin",
        schema_id="plugin-connector-invocation",
        key_scope="plugin-connector-invocation",
        scopes=["objects-read", "artifacts-write", "policy-read"],
    )
    step = definition["steps"][0]
    step["permissions"]["network"] = "policy-controlled"
    # A plugin or broker failure cannot be multiplied by the queue retry policy.
    # A fresh human-controlled invocation gets a new job and current consent.
    step["retryPolicy"]["maxAttempts"] = 1
    step["retryPolicy"]["retryableErrorCodes"] = []
    return definition


def build_plugin_job(inputs: PluginJobInput, *, actor: WorkflowActor, now: str) -> WorkflowJobSubmission:
    inputs = PluginJobInput.model_validate(inputs)
    return build_local_import_job(
        inputs,
        _definition(new_uuid_v7(), new_uuid_v7(), now),
        actor=actor,
        now=now,
        step_key="invoke-signed-plugin",
        idempotency_key=inputs.idempotency_key,
    )


def bind_plugin_claim(authority: WorkflowJobAuthority, claim: WorkflowJobClaim, inputs: PluginJobInput) -> None:
    """A matching activity name alone cannot authorize a queued plugin launch."""

    try:
        inputs = PluginJobInput.model_validate(inputs)
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
