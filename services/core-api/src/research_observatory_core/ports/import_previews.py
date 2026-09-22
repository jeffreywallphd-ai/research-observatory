"""Project-bound import-preview values and persistence port; no I/O authority."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from ..ingestion.import_drafts import (
    CsvDelimiter,
    Digest,
    DraftAuthority,
    DraftValue,
    Identity,
    ImportOptions,
    ImportRights,
    MappingProfile,
    ProjectIdentity,
    RecordDecision,
    Revision,
)
from ..ingestion.import_summaries import SummaryResult, SummaryRow
from ..ingestion.reference_imports import ImportRecord, ImportSession, ImportSource
from ..ingestion.source_chunks import SourceChunk
from .workflow_executor import WorkflowJobClaim, WorkflowOutputReference


class ImportActionGuard(Protocol):
    """Retain current project and launch authority for one bounded operation."""

    def __call__[Result](self, action: Callable[[], Result]) -> Result: ...


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
    delimiter: CsvDelimiter = ","
    rights: ImportRights
    actor: PreviewActor

    @model_validator(mode="after")
    def source_basename(self) -> Self:
        ImportSource(self.source_name, "0" * 64, self.encoding)
        if self.format_name != "csv" and self.delimiter != ",":
            raise ValueError("delimiter-requires-csv")
        return self


class PreviewState(DraftValue):
    project_id: ProjectIdentity
    preview_id: Identity
    source_name: str
    format_name: Literal["ris", "bibtex", "csl-json", "doi-list", "csv"]
    encoding: Literal["utf-8", "cp1252"]
    delimiter: CsvDelimiter = ","
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

    @model_validator(mode="after")
    def csv_delimiter(self) -> Self:
        if self.format_name != "csv" and self.delimiter != ",":
            raise ValueError("delimiter-requires-csv")
        return self


class PreviewDraftChange(DraftValue):
    expected_revision: Annotated[int, Field(ge=0, le=2147483646)]
    actor: PreviewActor
    mapping: MappingProfile | None = None
    rights: ImportRights | None = None
    options: ImportOptions | None = None
    decisions: Annotated[tuple[RecordDecision, ...], Field(max_length=100)] = ()
    restore_revision: Revision | None = None

    @model_validator(mode="after")
    def bounded_change(self) -> Self:
        if len({item.ordinal for item in self.decisions}) != len(self.decisions):
            raise ValueError("duplicate-record-decision")
        if self.restore_revision is not None and (
            self.mapping is not None
            or self.rights is not None
            or self.options is not None
            or self.decisions
            or self.restore_revision > self.expected_revision
        ):
            raise ValueError("draft-restore-must-stand-alone")
        return self


class PreviewDraft(DraftValue):
    revision: Revision
    predecessor_revision: Revision | None
    restore_revision: Revision | None
    undo_target_revision: Revision | None
    attempt_id: Identity
    record_count: Annotated[int, Field(ge=0, le=200000)]
    authority: DraftAuthority


@dataclass(frozen=True, slots=True)
class PreviewDraftRecord:
    record: ImportRecord
    decision: RecordDecision
    warnings: tuple[str, ...]


class PreviewSummary(DraftValue):
    project_id: ProjectIdentity
    preview_id: Identity
    draft_revision: Revision
    parse_attempt_id: Identity
    summary_attempt_id: Identity
    job_id: Identity
    receipt_revision_id: Identity
    result: SummaryResult


class SummaryGroup(DraftValue):
    reason: Literal["raw", "doi"]
    group_key: Digest
    member_count: Annotated[int, Field(ge=2, le=200000)]
    first_ordinal: Annotated[int, Field(ge=1, le=200000)]


class ImportPreviewRepository(Protocol):
    def create(self, command: PreviewCreate) -> PreviewState: ...
    def read(self, preview_id: str) -> PreviewState: ...
    def previews_page(self, *, after: str | None, limit: int) -> tuple[PreviewState, ...]: ...
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
    def revise_draft(self, preview_id: str, change: PreviewDraftChange) -> PreviewDraft: ...
    def draft(self, preview_id: str, *, revision: int | None = None) -> PreviewDraft: ...
    def mapping_high_water(self, preview_id: str) -> int: ...
    def draft_page(
        self, preview_id: str, *, revision: int, after: int, limit: int
    ) -> tuple[PreviewDraftRecord, ...]: ...
    def draft_digest(self, preview_id: str, *, revision: int) -> str: ...
    def draft_selection(
        self, preview_id: str, *, revision: int, ordinals: tuple[int, ...]
    ) -> tuple[PreviewDraftRecord, ...]: ...
    def diagnostic_report(self, preview_id: str, *, revision: int) -> Iterator[str]: ...
    def begin_summary(
        self, preview_id: str, *, revision: int, claim: WorkflowJobClaim, actor: PreviewActor
    ) -> None: ...
    def append_summary_page(
        self, preview_id: str, *, revision: int, after: int, claim: WorkflowJobClaim, actor: PreviewActor
    ) -> tuple[SummaryRow, ...]: ...
    def summary_result(self, preview_id: str, *, claim: WorkflowJobClaim, actor: PreviewActor) -> SummaryResult: ...
    def finish_summary(
        self,
        preview_id: str,
        *,
        claim: WorkflowJobClaim,
        result: SummaryResult,
        receipt_revision_id: str,
        actor: PreviewActor,
    ) -> WorkflowOutputReference: ...
    def summary(self, preview_id: str, *, revision: int) -> PreviewSummary | None: ...
    def summary_groups(
        self, preview_id: str, *, revision: int, reason: Literal["raw", "doi"], after: str | None, limit: int
    ) -> tuple[SummaryGroup, ...]: ...
    def summary_members(
        self, preview_id: str, *, revision: int, reason: Literal["raw", "doi"], group_key: str, after: int, limit: int
    ) -> tuple[int, ...]: ...
