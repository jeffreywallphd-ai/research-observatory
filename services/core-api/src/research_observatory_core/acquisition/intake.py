"""Exact, single-attempt product workflow authority for document intake."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..domain_contracts import new_uuid_v7
from ..ingestion.import_drafts import Digest, DraftValue, Identity
from ..ingestion.preview_workflow import (
    PreviewIntentContext,
    build_local_import_job,
    fingerprint,
    local_import_definition,
)
from ..ports.workflow_executor import WorkflowActor, WorkflowJobSubmission


class DocumentIntakeInput(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["local-import", "remote-download"]
    operation_id: Identity
    session_id: str = Field(pattern=r"^[0-9a-f]{32}$", repr=False)
    actor_id: Identity
    intent: PreviewIntentContext
    privacy_sha256: Digest
    selection_sha256: Digest
    confirmation_sha256: Digest

    @property
    def project_id(self) -> str:
        return self.intent.project_id

    @property
    def configuration_id(self) -> str:
        return "document-intake." + self.operation_id

    @property
    def configuration_version(self) -> str:
        return "1.0.0"

    @property
    def configuration_hash(self) -> str:
        return fingerprint(self.model_dump(mode="json", by_alias=True))

    def policy_reference(self) -> dict[str, str]:
        return {
            "policyId": "document-intake-policy",
            "policyVersion": "1.0.0",
            "policyHash": "sha256:" + self.privacy_sha256,
        }


def build_document_intake(inputs: DocumentIntakeInput, *, now: str) -> WorkflowJobSubmission:
    inputs = DocumentIntakeInput.model_validate(inputs)
    if inputs.intent.status != "accepted":
        raise ValueError("document intake requires accepted current Intent")
    activity = "document-intake-remote" if inputs.kind == "remote-download" else "document-intake-local"
    definition = local_import_definition(
        new_uuid_v7(),
        new_uuid_v7(),
        now,
        input_type=DocumentIntakeInput,
        version="1.0.0",
        activity=activity,
        step_key="inspect-document-copy",
        schema_id=activity,
        key_scope=activity,
        scopes=["objects-read", "artifacts-write", "policy-read"],
    )
    step = definition["steps"][0]
    step["permissions"]["network"] = "policy-controlled" if inputs.kind == "remote-download" else "none"
    step["retryPolicy"]["maxAttempts"] = 1
    step["retryPolicy"]["retryableErrorCodes"] = []
    # Stream bytes cannot be checkpointed as plaintext or concatenated after
    # consent changes. A fresh explicit attempt gets a separate operation.
    step["cancellationPolicy"]["partialArtifactDisposition"] = "discarded"
    return build_local_import_job(
        inputs,
        definition,
        actor=WorkflowActor(inputs.actor_id, "human", "researcher"),
        now=now,
        step_key="inspect-document-copy",
        idempotency_key=fingerprint([activity, inputs.operation_id]),
    )
