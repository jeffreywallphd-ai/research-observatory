"""Exact local document parsing input; no renderer or project executable authority."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .document_revisions import protected_json
from .domain_contracts import new_uuid_v7
from .ingestion.preview_workflow import (
    PreviewIntentContext,
    build_local_import_job,
    fingerprint,
    local_import_definition,
)
from .parsing.contracts import Digest, Identity, IRValue, ParseAttempt, ParseBinding, ProjectIdentity, SourceIdentity
from .parsing.requests import ParseRequest
from .parsing.selection import ParserSelection, selected_values, selection_sha256
from .ports.workflow_executor import WorkflowActor, WorkflowJobClaim, WorkflowJobSubmission
from .workflow_contracts import workflow_record_sha256, workflow_snapshot_errors

ACTIVITY = "document-parse"
ACTIVITY_VERSION = "document-parse-1"


class DocumentParseInput(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    command_id: Identity
    actor_id: Identity
    session_id: Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$", repr=False)]
    source: SourceIdentity
    selection: ParserSelection
    intent: PreviewIntentContext
    policy_sha256: Digest

    @model_validator(mode="after")
    def exact_source(self) -> Self:
        if (
            selected_values(self.selection)[0] != self.source
            or self.project_id != self.source.project_id
            or self.project_id != self.intent.project_id
            or self.intent.status != "accepted"
        ):
            raise ValueError("document-parse-input-authority-invalid")
        return self

    @property
    def configuration_id(self) -> str:
        return "document-parse." + self.command_id

    @property
    def configuration_version(self) -> str:
        return "1.0.0"

    @property
    def configuration_hash(self) -> str:
        return fingerprint(self.model_dump(mode="json", by_alias=True))

    def policy_reference(self) -> dict[str, str]:
        return {
            "policyId": "local-document-parse-policy",
            "policyVersion": "1.0.0",
            "policyHash": "sha256:" + self.policy_sha256,
        }

    def request(self, claim: WorkflowJobClaim) -> ParseRequest:
        if (
            claim.project_id != self.project_id
            or claim.activity_type != ACTIVITY
            or claim.concurrency_class != "document"
            or claim.command_fingerprint != self.configuration_hash
            or claim.idempotency_key != fingerprint(["document-parse/1", self.command_id])
        ):
            raise ValueError("document-parse-claim-mismatch")
        return ParseRequest(
            schema_version="1.0",
            selection=self.selection,
            binding=ParseBinding(
                source=self.source,
                producer=selected_values(self.selection)[1],
                selection_sha256=selection_sha256(self.selection),
                attempt=ParseAttempt(
                    job_id=claim.job_id, attempt_id=claim.attempt_id, activity_version=ACTIVITY_VERSION
                ),
            ),
        )


def definition(definition_id: str, revision_id: str, now: str) -> dict:
    return local_import_definition(
        definition_id,
        revision_id,
        now,
        input_type=DocumentParseInput,
        version="1.0.0",
        activity=ACTIVITY,
        step_key="parse-document-source",
        schema_id="document-parse",
        key_scope="document-parse-command",
        scopes=["objects-read", "artifacts-write", "policy-read"],
    )


def submission(inputs: DocumentParseInput, *, now: str) -> WorkflowJobSubmission:
    inputs = DocumentParseInput.model_validate(inputs)
    protected_json(inputs)
    return build_local_import_job(
        inputs,
        definition(new_uuid_v7(), new_uuid_v7(), now),
        actor=WorkflowActor(inputs.actor_id, "human", "researcher"),
        now=now,
        step_key="parse-document-source",
        idempotency_key=fingerprint(["document-parse/1", inputs.command_id]),
    )


def bind_claim(authority, claim: WorkflowJobClaim, inputs: DocumentParseInput) -> DocumentParseInput:
    """Authenticate the complete persisted definition and current workflow snapshot."""
    import json

    try:
        inputs.request(claim)
        declared, snapshot = json.loads(authority.definition_json), json.loads(authority.snapshot_json)
        jobs = [job for job in snapshot["jobs"] if job["jobId"] == claim.job_id]
        if (
            declared
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
        ):
            raise ValueError("document-parse-claim-authority-invalid")
        return inputs
    except ValueError, KeyError, IndexError, TypeError:
        raise ValueError("document-parse-claim-authority-invalid") from None
