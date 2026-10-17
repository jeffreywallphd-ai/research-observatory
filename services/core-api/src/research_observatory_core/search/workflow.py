"""Exact lexical job authority on the existing executor-neutral local queue."""

import json

from ..domain_contracts import new_uuid_v7
from ..ingestion.preview_workflow import build_local_import_job, local_import_definition
from ..ports.workflow_executor import WorkflowActor, WorkflowJobAuthority, WorkflowJobClaim, WorkflowJobSubmission
from ..workflow_contracts import workflow_record_sha256, workflow_snapshot_errors
from .run_values import SearchRequestInput, content_sha256

ACTIVITY = "lexical-search"
RUN_MEDIA_TYPE = "application/vnd.research-observatory.lexical-search-run+json"
STEP = "execute-lexical-search"


def definition(definition_id: str, revision_id: str, now: str) -> dict:
    return local_import_definition(
        definition_id,
        revision_id,
        now,
        input_type=SearchRequestInput,
        version="1.0.0",
        activity=ACTIVITY,
        step_key=STEP,
        schema_id="lexical-search",
        key_scope="lexical-search-command",
        scopes=["objects-read", "artifacts-write", "policy-read"],
    )


def submission(inputs: SearchRequestInput, *, now: str) -> WorkflowJobSubmission:
    inputs = SearchRequestInput.model_validate(inputs)
    content_sha256(inputs)
    return build_local_import_job(
        inputs,
        definition(new_uuid_v7(), new_uuid_v7(), now),
        actor=WorkflowActor(inputs.actor_id, "human", "researcher"),
        now=now,
        step_key=STEP,
        idempotency_key=inputs.idempotency_key,
    )


def bind_claim(
    authority: WorkflowJobAuthority, claim: WorkflowJobClaim, inputs: SearchRequestInput
) -> SearchRequestInput:
    """No request text, lease token or decoder input enters a public error."""
    try:
        inputs = SearchRequestInput.model_validate(inputs)
        declared, snapshot = json.loads(authority.definition_json), json.loads(authority.snapshot_json)
        jobs = [job for job in snapshot["jobs"] if job["jobId"] == claim.job_id]
        if (
            claim.project_id != inputs.project_id
            or claim.activity_type != ACTIVITY
            or claim.concurrency_class != "document"
            or claim.idempotency_key != inputs.idempotency_key
            or claim.command_fingerprint != inputs.configuration_hash
            or declared
            != definition(declared["workflowDefinitionId"], declared["definitionRevisionId"], declared["createdAt"])
            or workflow_snapshot_errors(declared, snapshot)
            or workflow_record_sha256(declared) != authority.definition_record_sha256
            or workflow_record_sha256(snapshot) != authority.snapshot_record_sha256
            or snapshot["projectId"] != inputs.project_id
            or snapshot["workflowRunId"] != claim.workflow_run_id
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
            raise ValueError("search-claim-authority-invalid")
        return inputs
    except ValueError, KeyError, IndexError, TypeError:
        raise ValueError("search-claim-authority-invalid") from None
