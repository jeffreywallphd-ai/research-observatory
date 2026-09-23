"""Portable commit execution boundary; no storage handles or paths."""

from collections.abc import Callable
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from ..ingestion.commit_workflow import CommitJobInput
from ..ingestion.import_drafts import (
    Digest,
    DraftValue,
    Identity,
    MappingProfile,
    ProjectIdentity,
    RecordDecision,
    Revision,
)
from .import_previews import ImportActionGuard, ImportPreviewRepository, PreviewActor
from .workflow_executor import WorkflowJobClaim, WorkflowOutputReference


class ImportCommitRequest(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    inputs: CommitJobInput
    configuration_hash: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    actor: PreviewActor

    @model_validator(mode="after")
    def exact_configuration(self) -> Self:
        if self.configuration_hash != self.inputs.configuration_hash:
            raise ValueError("import-commit-request-hash-mismatch")
        return self


class ImportManifest(DraftValue):
    project_id: ProjectIdentity
    revision_id: Identity
    aggregate_id: Identity
    preview_id: Identity
    draft_revision: Revision
    source_sha256: Digest
    identity_sha256: Digest
    effective_draft_sha256: Digest
    parser_version: str
    mapping: MappingProfile
    previous_manifest_revision_id: Identity | None
    record_count: Annotated[int, Field(ge=0, le=200000)]
    selected_count: Annotated[int, Field(ge=0, le=200000)]
    created_count: Annotated[int, Field(ge=0, le=200000)]
    reused_count: Annotated[int, Field(ge=0, le=200000)]
    members_sha256: Digest
    created_at: str

    @model_validator(mode="after")
    def coherent_counts(self) -> Self:
        if self.selected_count > self.record_count or self.created_count + self.reused_count != self.selected_count:
            raise ValueError("import-manifest-count-mismatch")
        return self


class ImportManifestMember(DraftValue):
    ordinal: Annotated[int, Field(ge=1, le=200000)]
    record_key: Digest
    source_record_revision_id: Identity | None
    decision: RecordDecision
    warnings: tuple[str, ...]
    comparison: Literal["not-compared", "added", "unchanged", "updated", "ambiguous"]
    previous_record_revision_id: Identity | None

    @model_validator(mode="after")
    def coherent_identity(self) -> Self:
        if (
            self.ordinal != self.decision.ordinal
            or self.record_key != self.decision.record_key
            or self.decision.included != (self.source_record_revision_id is not None)
            or (self.comparison in {"unchanged", "updated"}) != (self.previous_record_revision_id is not None)
        ):
            raise ValueError("import-manifest-member-mismatch")
        return self


class ImportPublicationInterrupted(RuntimeError):
    """Stop-only request: rollback is not a durable cancellation disposition."""


class ImportCommitRepository(Protocol):
    def save_commit_request(self, inputs: CommitJobInput, *, actor: PreviewActor) -> ImportCommitRequest: ...

    def commit_request(self, request_id: str) -> ImportCommitRequest | None: ...

    def latest_commit_request(self, preview_id: str) -> ImportCommitRequest | None: ...

    def manifest(self, revision_id: str) -> ImportManifest: ...

    def manifest_for_job(self, job_id: str) -> ImportManifest | None: ...

    def latest_manifest(self, preview_id: str) -> ImportManifest | None: ...

    def manifest_members(self, revision_id: str, *, after: int, limit: int) -> tuple[ImportManifestMember, ...]: ...

    def begin_commit(self, inputs: CommitJobInput, *, claim: WorkflowJobClaim, actor: PreviewActor) -> None: ...

    def append_commit_page(
        self, inputs: CommitJobInput, *, after: int, claim: WorkflowJobClaim, actor: PreviewActor
    ) -> int: ...

    def publish_commit(
        self,
        inputs: CommitJobInput,
        *,
        claim: WorkflowJobClaim,
        actor: PreviewActor,
        now: Callable[[], str],
        poll: Callable[[bool], None] | None = None,
        guard: ImportActionGuard | None = None,
        lease_duration_ms: int | None = None,
        interrupted: Callable[[], bool] | None = None,
    ) -> WorkflowOutputReference: ...


class ImportRepository(ImportPreviewRepository, ImportCommitRepository, Protocol):
    """One project adapter combining intake/review and canonical commit ports."""
