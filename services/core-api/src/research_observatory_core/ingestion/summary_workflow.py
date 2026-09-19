"""Exact fixed-draft workflow authority, separate from historical parser jobs."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import Field

from ..domain_contracts import new_uuid_v7
from ..ports.import_previews import PreviewDraft, PreviewProblem, PreviewState
from ..ports.workflow_executor import (
    WorkflowActor,
    WorkflowJobAuthority,
    WorkflowJobClaim,
    WorkflowJobRecord,
    WorkflowJobSubmission,
)
from ..workflow_contracts import workflow_record_sha256, workflow_snapshot_errors
from .import_drafts import DraftValue, Identity, Revision
from .import_summaries import SUMMARY_ACTIVITY
from .preview_workflow import (
    Fingerprint,
    PreviewInput,
    PreviewIntentContext,
    build_local_import_job,
    fingerprint,
    local_import_definition,
    preview_job_input,
)


class SummaryJobInput(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    preview: PreviewInput
    draft_revision: Revision
    parse_attempt_id: Identity
    authority_hash: Fingerprint
    record_count: Annotated[int, Field(ge=0, le=200000)]
    algorithm: Literal["draft-summary/1"] = "draft-summary/1"

    @property
    def project_id(self) -> str:
        return self.preview.project_id

    @property
    def intent(self) -> PreviewIntentContext:
        return self.preview.intent

    @property
    def configuration_id(self) -> str:
        return f"import-summary.{self.preview.preview_id}.{self.draft_revision}.{self.preview.resume_epoch}"

    @property
    def configuration_version(self) -> str:
        return "1.0.0"

    @property
    def configuration_hash(self) -> str:
        return fingerprint(self.model_dump(mode="json", by_alias=True))

    @property
    def idempotency_key(self) -> str:
        return fingerprint(["import-summary-job/1", self.configuration_hash])

    def policy_reference(self) -> dict[str, str]:
        return self.preview.policy_reference()


def summary_job_input(
    state: PreviewState, draft: PreviewDraft, intent: PreviewIntentContext, policy_hash: str, resume_epoch: str
) -> SummaryJobInput:
    draft = PreviewDraft.model_validate(draft)
    parsed = preview_job_input(state, intent, policy_hash, resume_epoch)
    if (
        draft.authority.project_id != state.project_id
        or draft.authority.preview_id != state.preview_id
        or draft.authority.source_sha256 != state.source_sha256
        or draft.authority.rights != state.rights
        or draft.authority.delimiter != state.delimiter
    ):
        raise PreviewProblem("preview-summary-draft-authority-mismatch")
    return SummaryJobInput(
        preview=parsed,
        draft_revision=draft.revision,
        parse_attempt_id=draft.attempt_id,
        authority_hash=fingerprint(draft.authority.model_dump(mode="json", by_alias=True)),
        record_count=draft.record_count,
    )


def _definition(definition_id: str, revision_id: str, now: str) -> dict[str, Any]:
    return local_import_definition(
        definition_id,
        revision_id,
        now,
        input_type=SummaryJobInput,
        version="1.0.0",
        activity=SUMMARY_ACTIVITY,
        step_key="summarize-import-draft",
        schema_id="import-draft-summary",
        key_scope="import-draft-summary",
        scopes=["artifacts-read", "artifacts-write", "policy-read"],
    )


def build_summary_job(inputs: SummaryJobInput, *, actor: WorkflowActor, now: str) -> WorkflowJobSubmission:
    inputs = SummaryJobInput.model_validate(inputs)
    return build_local_import_job(
        inputs,
        _definition(new_uuid_v7(), new_uuid_v7(), now),
        actor=actor,
        now=now,
        step_key="summarize-import-draft",
        idempotency_key=inputs.idempotency_key,
    )


def bind_summary_claim(
    authority: WorkflowJobAuthority,
    claim: WorkflowJobClaim,
    inputs: SummaryJobInput,
    *,
    predecessor: tuple[WorkflowJobRecord, WorkflowJobAuthority] | None = None,
) -> SummaryJobInput:
    """Reconstruct current scientific authority; continuations retain their source."""
    try:
        inputs = SummaryJobInput.model_validate(inputs)
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
            or claim.activity_type != SUMMARY_ACTIVITY
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
            raise PreviewProblem("preview-summary-job-authority-mismatch")
        continuation = snapshot.get("continuation")
        if continuation is None:
            if (
                predecessor is not None
                or claim.idempotency_key != inputs.idempotency_key
                or claim.command_fingerprint != inputs.configuration_hash
            ):
                raise PreviewProblem("preview-summary-job-authority-mismatch")
        else:
            if predecessor is None:
                raise PreviewProblem("preview-summary-predecessor-unavailable")
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
                raise PreviewProblem("preview-summary-predecessor-mismatch")
        return inputs
    except ValueError, KeyError, IndexError, TypeError:
        raise PreviewProblem("preview-summary-job-authority-invalid") from None
