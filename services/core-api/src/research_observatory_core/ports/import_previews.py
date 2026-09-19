"""Project-bound import-preview values and persistence port; no I/O authority."""

from __future__ import annotations

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from ..ingestion.import_drafts import Digest, DraftValue, Identity, ImportRights, ProjectIdentity
from ..ingestion.reference_imports import ImportRecord, ImportSession, ImportSource
from ..ingestion.source_chunks import SourceChunk
from .workflow_executor import WorkflowJobClaim, WorkflowOutputReference


class PreviewProblem(RuntimeError):
    """Content-free denial or persistence failure."""


class PreviewActor(DraftValue):
    actor_id: Identity
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    occurred_at: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")]


class PreviewCreate(DraftValue):
    preview_id: Identity
    source_name: str
    format_name: Literal["ris", "bibtex", "csl-json", "doi-list", "csv"]
    encoding: Literal["utf-8", "cp1252"] = "utf-8"
    rights: ImportRights
    actor: PreviewActor

    @model_validator(mode="after")
    def source_basename(self) -> Self:
        ImportSource(self.source_name, "0" * 64, self.encoding)
        return self


class PreviewState(DraftValue):
    project_id: ProjectIdentity
    preview_id: Identity
    source_name: str
    format_name: Literal["ris", "bibtex", "csl-json", "doi-list", "csv"]
    encoding: Literal["utf-8", "cp1252"]
    rights: ImportRights
    state: Literal[
        "created",
        "source-sealed",
        "parse-started",
        "parse-completed",
        "draft-revised",
        "cancelled",
        "failed",
        "security-interrupted",
    ]
    source_sha256: Digest | None
    manifest_sha256: Digest | None
    byte_length: Annotated[int, Field(ge=0, le=268435456)]
    chunk_count: Annotated[int, Field(ge=0, le=2048)]


class ImportPreviewRepository(Protocol):
    def create(self, command: PreviewCreate) -> PreviewState: ...
    def read(self, preview_id: str) -> PreviewState: ...
    def append_chunk(self, preview_id: str, *, ordinal: int, chunk: SourceChunk) -> None: ...
    def source_chunks(self, preview_id: str) -> tuple[SourceChunk, ...]: ...
    def seal(
        self, preview_id: str, *, source_sha256: str, byte_length: int, chunk_count: int, actor: PreviewActor
    ) -> PreviewState: ...
    def cancel(self, preview_id: str, *, actor: PreviewActor, security_interruption: bool = False) -> None: ...
    def begin_parse(self, preview_id: str, *, claim: WorkflowJobClaim, actor: PreviewActor) -> None: ...
    def append_records(
        self, preview_id: str, *, claim: WorkflowJobClaim, records: tuple[ImportRecord, ...], actor: PreviewActor
    ) -> None: ...
    def finish_parse(
        self,
        preview_id: str,
        *,
        claim: WorkflowJobClaim,
        session: ImportSession,
        receipt_revision_id: str,
        actor: PreviewActor,
    ) -> WorkflowOutputReference: ...
    def records_page(self, preview_id: str, *, after: int, limit: int) -> tuple[ImportRecord, ...]: ...
