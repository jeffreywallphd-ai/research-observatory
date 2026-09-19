"""Exact, replayable local import authority; no file paths or scholarly commits.

The trusted service supplies validated canonical Intent context and current
privacy authority. Draft Intent is context, never an invented human acceptance.
The native recovery epoch is not a renderer-selected continuation permission.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Annotated, Any, Literal, Protocol, Self

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from ..domain_contracts import new_uuid_v7
from ..models import IntentRevisionStatus
from ..ports.import_previews import PreviewProblem, PreviewState
from ..ports.workflow_executor import (
    WorkflowActor,
    WorkflowJobAuthority,
    WorkflowJobClaim,
    WorkflowJobSubmission,
    WorkflowOutputReference,
)
from ..workflow_contracts import workflow_record_sha256, workflow_snapshot_errors
from ..workflow_executor import prepare_workflow_job
from .import_drafts import Digest, DraftValue, Identity, ProjectIdentity
from .reference_imports import PARSER_VERSION, ImportLimits, ImportSource

type Fingerprint = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
type ResumeEpoch = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
ACTIVITY = "local-reference-preview"


def fingerprint(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode("ascii")).hexdigest()


class PreviewIntentContext(DraftValue):
    project_id: ProjectIdentity
    domain_project_id: Identity
    intent_id: Identity
    revision_id: Identity
    content_hash: Fingerprint
    status: IntentRevisionStatus

    def reference(self) -> dict[str, str]:
        return {"intentId": self.intent_id, "revisionId": self.revision_id, "contentHash": self.content_hash}


class _PreviewInput(DraftValue):
    schema_version: str = "1.0"
    project_id: ProjectIdentity
    preview_id: Identity
    source_sha256: Digest
    manifest_sha256: Digest
    source_name: str
    format_name: Literal["ris", "bibtex", "csl-json", "doi-list", "csv"]
    encoding: Literal["utf-8", "cp1252"]
    byte_length: Annotated[int, Field(ge=0, le=268435456)]
    chunk_count: Annotated[int, Field(ge=0, le=2048)]
    parser_version: Literal["local-reference-imports/1.0.0"] = "local-reference-imports/1.0.0"
    delimiter: str = ","
    parser_limits_hash: Fingerprint
    rights_hash: Fingerprint
    intent: PreviewIntentContext
    policy_hash: Fingerprint
    resume_epoch: ResumeEpoch

    @model_validator(mode="after")
    def exact_parser_and_project(self) -> Self:
        ImportSource(self.source_name, self.source_sha256, self.encoding)
        if self.project_id != self.intent.project_id or self.parser_limits_hash != fingerprint(asdict(ImportLimits())):
            raise ValueError("preview-parser-or-project-authority-invalid")
        return self

    @property
    def configuration_id(self) -> str:
        return f"import-preview.{self.preview_id}.{self.resume_epoch}"

    @property
    def configuration_hash(self) -> str:
        return fingerprint(self.model_dump(mode="json", by_alias=True))

    def policy_reference(self) -> dict[str, str]:
        return {"policyId": "local-import-preview-policy", "policyVersion": "1.0.0", "policyHash": self.policy_hash}

    @property
    def configuration_version(self) -> str:
        return "1.0.0" if self.schema_version == "1.0" else "1.1.0"


class PreviewJobInput(_PreviewInput):
    # Keep this exact model name, field order and schema for queued comma jobs.
    schema_version: Literal["1.0"] = "1.0"
    delimiter: Literal[","] = ","


class PreviewDelimitedJobInput(_PreviewInput):
    schema_version: Literal["1.1"] = "1.1"
    delimiter: Literal["\t", ";"]

    @model_validator(mode="after")
    def csv_only(self) -> Self:
        if self.format_name != "csv":
            raise ValueError("delimiter-requires-csv")
        return self


type PreviewInput = PreviewJobInput | PreviewDelimitedJobInput


def _validated_input(inputs: PreviewInput) -> PreviewInput:
    model = PreviewJobInput if inputs.schema_version == "1.0" else PreviewDelimitedJobInput
    return model.model_validate(inputs)


def preview_job_input(
    state: PreviewState, intent: PreviewIntentContext, policy_hash: str, resume_epoch: str
) -> PreviewInput:
    state, intent = PreviewState.model_validate(state), PreviewIntentContext.model_validate(intent)
    if (
        state.source_sha256 is None
        or state.manifest_sha256 is None
        or state.state in {"created", "cancelled", "failed", "security-interrupted"}
        or state.project_id != intent.project_id
        or not state.rights.permits("store")
        or not state.rights.permits("inspect")
    ):
        raise PreviewProblem("preview-workflow-authority-unavailable")
    model = PreviewJobInput if state.delimiter == "," else PreviewDelimitedJobInput
    return model.model_validate(
        dict(
            project_id=state.project_id,
            preview_id=state.preview_id,
            source_sha256=state.source_sha256,
            manifest_sha256=state.manifest_sha256,
            source_name=state.source_name,
            format_name=state.format_name,
            encoding=state.encoding,
            delimiter=state.delimiter,
            byte_length=state.byte_length,
            chunk_count=state.chunk_count,
            parser_version=PARSER_VERSION,
            parser_limits_hash=fingerprint(asdict(ImportLimits())),
            rights_hash=fingerprint(state.rights.model_dump(mode="json", by_alias=True)),
            intent=intent,
            policy_hash=policy_hash,
            resume_epoch=resume_epoch,
        )
    )


def _definition(
    definition_id: str,
    revision_id: str,
    now: str,
    input_type: type[PreviewJobInput] | type[PreviewDelimitedJobInput] = PreviewJobInput,
) -> dict[str, Any]:
    version = "1.0.0" if input_type is PreviewJobInput else "1.1.0"
    return local_import_definition(
        definition_id,
        revision_id,
        now,
        input_type=input_type,
        version=version,
        activity=ACTIVITY,
        step_key="parse-reference-source",
        schema_id="import-preview",
        key_scope="import-preview-source",
        scopes=["objects-read", "artifacts-write", "policy-read"],
    )


def local_import_definition(
    definition_id: str,
    revision_id: str,
    now: str,
    *,
    input_type: type[BaseModel],
    version: str,
    activity: str,
    step_key: str,
    schema_id: str,
    key_scope: str,
    scopes: list[str],
) -> dict[str, Any]:
    """Shared declarative single-activity shape; callers retain exact schema identity."""
    input_schema = {
        "schemaId": schema_id + "-input",
        "schemaVersion": version,
        "schemaHash": fingerprint(input_type.model_json_schema()),
    }
    output_schema = {
        "schemaId": schema_id + "-output",
        "schemaVersion": "1.0.0",
        "schemaHash": fingerprint(TypeAdapter(tuple[WorkflowOutputReference]).json_schema()),
    }
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-workflow-definition",
        "contractVersion": "1.0.0",
        "workflowDefinitionId": definition_id,
        "definitionRevisionId": revision_id,
        "definitionVersion": version,
        "workflowKey": activity,
        "createdAt": now,
        "inputSchema": input_schema,
        "outputSchema": output_schema,
        "compatibility": {
            "historyContractVersion": "1.0.0",
            "minimumExecutorContractVersion": "1.0.0",
            "maximumExecutorContractVersion": "1.0.0",
        },
        "steps": [
            {
                "stepKey": step_key,
                "kind": "activity",
                "activityType": activity,
                "dependsOn": [],
                "inputSchema": input_schema,
                "outputSchema": output_schema,
                "retryPolicy": {
                    "maxAttempts": 3,
                    "initialBackoffMs": 1000,
                    "maximumBackoffMs": 10000,
                    "multiplierBasisPoints": 20000,
                    "jitter": "deterministic",
                    "retryableErrorCodes": ["dependency-unavailable"],
                    "nonRetryableErrorCodes": ["rights-denied", "policy-denied", "stale-authority"],
                },
                "idempotency": {"mode": "required", "keyScope": key_scope},
                # Retry starts a fresh fenced attempt over immutable chunks; provisional
                # records are not a checkpoint or accepted output.
                "checkpointPolicy": {"mode": "forbidden", "maximumIntervalSeconds": None},
                "cancellationPolicy": {
                    "mode": "cooperative",
                    "gracePeriodMs": 5000,
                    "partialArtifactDisposition": "retained-incomplete",
                },
                "permissions": {
                    "network": "none",
                    "projectFiles": "read-write",
                    "model": "none",
                    "capabilityScopes": scopes,
                },
                "progress": {"unit": "records", "totalKind": "unknown", "totalUnits": None},
                "humanTask": None,
            }
        ],
    }


def build_preview_job(inputs: PreviewInput, *, actor: WorkflowActor, now: str) -> WorkflowJobSubmission:
    inputs = _validated_input(inputs)
    definition = _definition(new_uuid_v7(), new_uuid_v7(), now, type(inputs))
    return build_local_import_job(
        inputs,
        definition,
        actor=actor,
        now=now,
        step_key="parse-reference-source",
        idempotency_key=fingerprint(["import-preview/1", inputs.preview_id]),
    )


class LocalImportJobBinding(Protocol):
    @property
    def project_id(self) -> str: ...
    @property
    def intent(self) -> PreviewIntentContext: ...
    @property
    def configuration_id(self) -> str: ...
    @property
    def configuration_version(self) -> str: ...
    @property
    def configuration_hash(self) -> str: ...
    def policy_reference(self) -> dict[str, str]: ...


def build_local_import_job(
    inputs: LocalImportJobBinding,
    definition: dict[str, Any],
    *,
    actor: WorkflowActor,
    now: str,
    step_key: str,
    idempotency_key: str,
) -> WorkflowJobSubmission:
    run, snapshot_id, step, job = (new_uuid_v7() for _ in range(4))
    transitions = (
        ("workflow-run", run, None, "accepted", "command-accepted"),
        ("workflow-step", step, None, "pending", "step-created"),
        ("workflow-step", step, "pending", "runnable", "dependencies-satisfied"),
        ("job", job, None, "pending", "job-created"),
        ("job", job, "pending", "runnable", "job-ready"),
    )
    actor_reference = {"actorId": actor.actor_id, "actorType": actor.actor_type, "role": actor.role}
    history = [
        {
            "eventId": new_uuid_v7(),
            "sequence": index,
            "entityType": kind,
            "entityId": entity,
            "fromState": before,
            "toState": after,
            "occurredAt": now,
            "actor": actor_reference,
            "reasonCode": reason,
            "progress": None,
            "checkpointId": None,
            "decisionId": None,
            "interruptionKind": None,
        }
        for index, (kind, entity, before, after, reason) in enumerate(transitions, 1)
    ]
    progress = {"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None}
    cancellation = {"requestedAt": None, "reasonCode": None, "interruptionKind": None}
    snapshot = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-workflow-snapshot",
        "contractVersion": "1.0.0",
        "snapshotId": snapshot_id,
        "snapshotRevision": 1,
        "projectId": inputs.project_id,
        "workflowRunId": run,
        "definition": {
            "workflowDefinitionId": definition["workflowDefinitionId"],
            "definitionRevisionId": definition["definitionRevisionId"],
            "definitionVersion": definition["definitionVersion"],
            "contentHash": workflow_record_sha256(definition),
        },
        "intent": inputs.intent.reference(),
        "policy": inputs.policy_reference(),
        "configuration": {
            "configurationId": inputs.configuration_id,
            "configurationVersion": inputs.configuration_version,
            "configurationHash": inputs.configuration_hash,
        },
        "executor": {
            "profile": "local",
            "adapterId": "local-durable-workflow",
            "adapterVersion": "1.0.0",
            "contractVersion": "1.0.0",
        },
        "state": "accepted",
        "progress": progress,
        "cancellation": cancellation,
        "createdAt": now,
        "updatedAt": now,
        "sequence": 5,
        "stepRuns": [
            {
                "stepRunId": step,
                "stepKey": step_key,
                "state": "runnable",
                "sequence": 3,
                "progress": progress,
                "jobIds": [job],
                "humanTaskIds": [],
                "inputArtifactIds": [],
                "outputArtifactIds": [],
            }
        ],
        "jobs": [
            {
                "jobId": job,
                "stepRunId": step,
                "state": "runnable",
                "sequence": 5,
                "idempotencyKey": idempotency_key,
                "commandFingerprint": inputs.configuration_hash,
                "attemptIds": [],
                "currentAttemptId": None,
                "inputArtifactIds": [],
                "outputArtifactIds": [],
                "cancellation": cancellation,
            }
        ],
        "attempts": [],
        "checkpoints": [],
        "artifacts": [],
        "humanTasks": [],
        "history": history,
    }
    return prepare_workflow_job(
        definition, snapshot, job_id=job, concurrency_class="document", priority=0, available_at=now
    )


def bind_preview_claim(authority: WorkflowJobAuthority, claim: WorkflowJobClaim, inputs: PreviewInput) -> PreviewInput:
    """Reconstruct exact input after restart; a matching activity name is insufficient."""
    try:
        inputs = _validated_input(inputs)
        definition, snapshot = json.loads(authority.definition_json), json.loads(authority.snapshot_json)
        expected_definition = _definition(
            definition["workflowDefinitionId"],
            definition["definitionRevisionId"],
            definition["createdAt"],
            type(inputs),
        )
        jobs = [job for job in snapshot["jobs"] if job["jobId"] == claim.job_id]
        if (
            workflow_snapshot_errors(definition, snapshot)
            or definition != expected_definition
            or workflow_record_sha256(definition) != authority.definition_record_sha256
            or workflow_record_sha256(snapshot) != authority.snapshot_record_sha256
            or snapshot["projectId"] != inputs.project_id
            or claim.project_id != inputs.project_id
            or snapshot["workflowRunId"] != claim.workflow_run_id
            or claim.activity_type != ACTIVITY
            or claim.concurrency_class != "document"
            or claim.command_fingerprint != inputs.configuration_hash
            or claim.idempotency_key != fingerprint(["import-preview/1", inputs.preview_id])
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
            raise PreviewProblem("preview-job-authority-mismatch")
        return inputs
    except ValueError, KeyError, IndexError, TypeError:
        raise PreviewProblem("preview-job-authority-invalid") from None
