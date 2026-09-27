"""One bounded local reconciliation snapshot on the existing durable executor."""

from __future__ import annotations

import json

from ..domain_contracts import new_uuid_v7
from ..ingestion.preview_workflow import build_local_import_job, fingerprint, local_import_definition
from ..ports.workflow_executor import (
    WorkflowActor,
    WorkflowJobAuthority,
    WorkflowJobClaim,
    WorkflowJobRecord,
    WorkflowJobSubmission,
)
from ..workflow_contracts import workflow_record_sha256, workflow_snapshot_errors
from .batch import BATCH_ACTIVITY, BatchInput
from .contracts import ReconciliationProblem


def _definition(identity: str, revision: str, now: str):
    return local_import_definition(
        identity,
        revision,
        now,
        input_type=BatchInput,
        version="1.0.0",
        activity=BATCH_ACTIVITY,
        step_key="reconcile-inventory",
        schema_id="scholarly-reconciliation-batch",
        key_scope="scholarly-reconciliation-batch",
        scopes=["objects-read", "artifacts-write", "policy-read"],
    )


def build_batch_job(inputs: BatchInput, *, actor: WorkflowActor, now: str) -> WorkflowJobSubmission:
    inputs = BatchInput.model_validate(inputs)
    if actor.actor_id != inputs.actor_id:
        raise ReconciliationProblem("reconciliation-batch-actor-mismatch")
    return build_local_import_job(
        inputs,
        _definition(new_uuid_v7(), new_uuid_v7(), now),
        actor=actor,
        now=now,
        step_key="reconcile-inventory",
        idempotency_key=inputs.idempotency_key,
    )


def bind_batch_claim(
    authority: WorkflowJobAuthority,
    claim: WorkflowJobClaim,
    inputs: BatchInput,
    *,
    predecessor: tuple[WorkflowJobRecord, WorkflowJobAuthority] | None = None,
) -> BatchInput:
    """Reconstruct current scientific authority; continuations retain their source."""
    try:
        inputs = BatchInput.model_validate(inputs)
        definition, snapshot = json.loads(authority.definition_json), json.loads(authority.snapshot_json)
        expected = _definition(
            definition["workflowDefinitionId"], definition["definitionRevisionId"], definition["createdAt"]
        )
        jobs = [job for job in snapshot["jobs"] if job["jobId"] == claim.job_id]
        if (
            workflow_snapshot_errors(definition, snapshot)
            or definition != expected
            or workflow_record_sha256(definition) != authority.definition_record_sha256
            or workflow_record_sha256(snapshot) != authority.snapshot_record_sha256
            or snapshot["projectId"] != inputs.project_id
            or claim.project_id != inputs.project_id
            or snapshot["workflowRunId"] != claim.workflow_run_id
            or claim.activity_type != BATCH_ACTIVITY
            or claim.concurrency_class != "document"
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
            or jobs[0]["idempotencyKey"] != claim.idempotency_key
            or jobs[0]["commandFingerprint"] != claim.command_fingerprint
        ):
            raise ReconciliationProblem("reconciliation-batch-job-authority-mismatch")
        continuation = snapshot.get("continuation")
        if continuation is None:
            if (
                predecessor is not None
                or claim.idempotency_key != inputs.idempotency_key
                or claim.command_fingerprint != inputs.configuration_hash
            ):
                raise ReconciliationProblem("reconciliation-batch-job-authority-mismatch")
        else:
            if predecessor is None:
                raise ReconciliationProblem("reconciliation-batch-predecessor-unavailable")
            record, source_authority = predecessor
            source_definition = json.loads(source_authority.definition_json)
            source = json.loads(source_authority.snapshot_json)
            if (
                record.state not in {"failed", "cancelled"}
                or source_definition != definition
                or workflow_snapshot_errors(source_definition, source)
                or workflow_record_sha256(source_definition) != source_authority.definition_record_sha256
                or workflow_record_sha256(source) != source_authority.snapshot_record_sha256
                or continuation != {"sourceWorkflowRunId": record.workflow_run_id, "sourceJobId": record.job_id}
                or source["workflowRunId"] != record.workflow_run_id
                or not any(job["jobId"] == record.job_id for job in source["jobs"])
                or any(
                    source[name] != snapshot[name]
                    for name in ("projectId", "definition", "configuration", "intent", "policy", "executor")
                )
                or claim.command_fingerprint
                != fingerprint({"command": "retry-as-continuation", "sourceJobId": record.job_id})
            ):
                raise ReconciliationProblem("reconciliation-batch-predecessor-mismatch")
        return inputs
    except ValueError, KeyError, IndexError, TypeError:
        raise ReconciliationProblem("reconciliation-batch-job-authority-invalid") from None
