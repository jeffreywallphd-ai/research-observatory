"""Bounded review transport over protected repository ports, never canonical imports.

JSON lists are a transport concern. Immutable domain tuples and their strict
validation remain unchanged. Every mutation uses an exact predecessor; a lost
response requires an authoritative reread, not a replay against a newer draft.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from .ingestion.import_drafts import (
    CsvDelimiter,
    Digest,
    DraftValue,
    FieldIndex,
    FieldMapping,
    Identity,
    ImportOptions,
    ImportRights,
    MappedField,
    MappedName,
    MappingProfile,
    RecordDecision,
    Revision,
    TextValue,
    review_record,
    spreadsheet_cell,
)
from .ingestion.import_summaries import SummaryCounts
from .ingestion.preview_records import WarningCode
from .ingestion.reference_imports import import_field_target
from .ports.import_previews import (
    ImportPreviewRepository,
    PreviewActor,
    PreviewDraft,
    PreviewDraftChange,
    PreviewDraftRecord,
    PreviewProblem,
    PreviewState,
    PreviewSummary,
)
from .ports.workflow_executor import WorkflowJobRecord, WorkflowJobState

# Includes the JSON envelope; leave headroom for the native 1 MiB HTTP limit.
RESPONSE_BYTES = 900_000
type Ordinal = Annotated[int, Field(strict=True, ge=1, le=200000)]
type Cursor = Annotated[int, Field(strict=True, ge=0, le=200000)]
type PageLimit = Annotated[int, Field(strict=True, ge=1, le=100)]
type MutationRevision = Annotated[int, Field(strict=True, ge=1, le=2147483646)]
type Section = Literal["raw", "candidates", "effective"]


class ReviewPageRequest(DraftValue):
    revision: Revision
    after: Cursor = 0
    limit: PageLimit = 25


class ColumnSelection(DraftValue):
    index: FieldIndex
    target: MappedName


class MappingEdit(DraftValue):
    expected_revision: MutationRevision
    columns: Annotated[list[ColumnSelection], Field(max_length=256)]
    mode: Literal["automatic", "columns"] = "columns"

    @model_validator(mode="after")
    def selectors(self) -> Self:
        if len({item.index for item in self.columns}) != len(self.columns):
            raise ValueError("duplicate-column-selection")
        if self.mode == "automatic" and self.columns:
            raise ValueError("automatic-mapping-has-bindings")
        return self


class RecordSelection(DraftValue):
    ordinal: Ordinal
    record_key: Digest


class FieldCorrection(DraftValue):
    name: MappedName
    value: TextValue


class GroupEdit(DraftValue):
    expected_revision: MutationRevision
    records: Annotated[list[RecordSelection], Field(min_length=1, max_length=100)]
    included: bool | None = None
    corrections: Annotated[list[FieldCorrection], Field(max_length=64)] = Field(default_factory=list)

    @model_validator(mode="after")
    def operation(self) -> Self:
        if len({item.ordinal for item in self.records}) != len(self.records):
            raise ValueError("duplicate-record-selection")
        if self.included is None and not self.corrections:
            raise ValueError("empty-group-edit")
        return self


class ReviewSummary(DraftValue):
    preview_id: Identity
    revision: Revision
    predecessor_revision: Revision | None
    attempt_id: Identity
    record_count: Cursor
    mapping_id: Identity
    mapping_revision: Revision
    mapping_high_water: Revision
    mapping_mode: Literal["automatic", "columns"]
    rights: ImportRights
    options: ImportOptions
    delimiter: CsvDelimiter
    undo_target_revision: Revision | None


class ShortValue(DraftValue):
    text: Annotated[str, Field(max_length=256)]
    truncated: bool


class RecordSummary(DraftValue):
    ordinal: Ordinal
    record_key: Digest
    kind: Literal["record", "header", "directive"]
    status: Literal["parsed", "malformed"]
    included: bool
    title: ShortValue | None
    doi: ShortValue | None
    field_count: Annotated[int, Field(ge=0, le=4096)]
    warnings: Annotated[list[WarningCode], Field(max_length=64)]


class ReviewPage(DraftValue):
    revision: Revision
    records: Annotated[list[RecordSummary], Field(max_length=100)]
    next_after: Cursor
    complete: bool


type DuplicateReason = Literal["raw", "doi"]


class ImportSummaryStatus(DraftValue):
    preview_id: Identity
    revision: Revision
    algorithm: Literal["draft-summary/1"] = "draft-summary/1"
    job_id: Identity | None
    job_state: WorkflowJobState | None
    diagnostic_code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9.-]{0,95}$")] | None
    counts: SummaryCounts | None


class ImportDuplicateGroup(DraftValue):
    group_key: Digest
    member_count: Annotated[int, Field(strict=True, ge=2, le=200000)]
    first_ordinal: Ordinal


class ImportDuplicateGroups(DraftValue):
    preview_id: Identity
    revision: Revision
    reason: DuplicateReason
    groups: Annotated[list[ImportDuplicateGroup], Field(max_length=100)]
    next_after: Digest | None
    complete: bool


class ImportDuplicateMembers(DraftValue):
    preview_id: Identity
    revision: Revision
    reason: DuplicateReason
    group_key: Digest
    records: Annotated[list[RecordSummary], Field(max_length=100)]
    next_after: Cursor
    complete: bool


class ReviewField(DraftValue):
    index: FieldIndex
    name: Annotated[str, Field(max_length=65536)]
    value: Annotated[str, Field(max_length=65536)]
    source_field_index: FieldIndex | None
    origin: Literal["raw", "candidate", "mapping", "correction"]
    target: MappedName | None = None
    warnings: Annotated[list[WarningCode], Field(max_length=32)] = Field(default_factory=list)


class ReviewDetail(DraftValue):
    revision: Revision
    ordinal: Ordinal
    record_key: Digest
    section: Section
    fields: Annotated[list[ReviewField], Field(max_length=100)]
    next_index: Annotated[int, Field(ge=0, le=4096)]
    complete: bool


class DiagnosticPage(DraftValue):
    revision: Revision
    csv: Annotated[str, Field(max_length=RESPONSE_BYTES)]
    next_after: Cursor
    complete: bool


class PreviewProgress(DraftValue):
    preview_id: Identity
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
    byte_length: Annotated[int, Field(strict=True, ge=0, le=268435456)]
    chunk_count: Annotated[int, Field(strict=True, ge=0, le=2048)]
    job_id: Identity | None
    job_state: WorkflowJobState | None


class ImportPreviewItem(PreviewProgress):
    source_name: Annotated[str, Field(min_length=1, max_length=255)]
    format_name: Literal["ris", "bibtex", "csl-json", "doi-list", "csv"]
    encoding: Literal["utf-8", "cp1252"]


class ImportPreviewPage(DraftValue):
    items: Annotated[list[ImportPreviewItem], Field(max_length=25)]
    next_after: Identity | None
    complete: bool


def preview_item(state: PreviewState, job: WorkflowJobRecord | None) -> ImportPreviewItem:
    if not state.rights.permits("inspect"):
        raise PreviewProblem("preview-rights-denied")
    return ImportPreviewItem(
        preview_id=state.preview_id,
        state=state.state,
        source_name=state.source_name,
        format_name=state.format_name,
        encoding=state.encoding,
        byte_length=state.byte_length,
        chunk_count=state.chunk_count,
        job_id=job.job_id if job else None,
        job_state=job.state if job else None,
    )


def encoded_size(value: DraftValue) -> int:
    # ASCII escaping is conservative relative to the actual UTF-8 JSON transport.
    return len(
        json.dumps(
            value.model_dump(mode="json", by_alias=True), ensure_ascii=True, separators=(",", ":"), allow_nan=False
        ).encode("ascii")
    )


def bounded[Value: DraftValue](value: Value) -> Value:
    if encoded_size(value) > RESPONSE_BYTES:
        raise PreviewProblem("preview-response-limit")
    return value


def summary_status_item(
    preview: str, revision: int, summary: PreviewSummary | None, job: WorkflowJobRecord | None
) -> ImportSummaryStatus:
    if summary is not None and (job is None or job.job_id != summary.job_id or job.state != "succeeded"):
        raise PreviewProblem("preview-summary-job-authority-mismatch")
    return ImportSummaryStatus(
        preview_id=preview,
        revision=revision,
        job_id=job.job_id if job else None,
        job_state=job.state if job else None,
        diagnostic_code=job.diagnostic_code if job else None,
        counts=summary.result.counts if summary else None,
    )


class ImportReview:
    def __init__(self, repository: ImportPreviewRepository):
        self._repository = repository

    def _summary(self, preview: str, draft: PreviewDraft) -> ReviewSummary:
        return bounded(
            ReviewSummary(
                preview_id=preview,
                revision=draft.revision,
                predecessor_revision=draft.predecessor_revision,
                attempt_id=draft.attempt_id,
                record_count=draft.record_count,
                mapping_id=draft.authority.mapping.profile_id,
                mapping_revision=draft.authority.mapping.revision,
                mapping_high_water=self._repository.mapping_high_water(preview),
                mapping_mode=draft.authority.mapping.mode,
                rights=draft.authority.rights,
                options=draft.authority.options,
                delimiter=draft.authority.delimiter,
                undo_target_revision=draft.undo_target_revision,
            )
        )

    def summary(self, preview: str) -> ReviewSummary:
        return self._summary(preview, self._repository.draft(preview))

    def begin(self, preview: str, *, actor: PreviewActor) -> ReviewSummary:
        draft = self._repository.revise_draft(preview, PreviewDraftChange(expected_revision=0, actor=actor))
        return self._summary(preview, draft)

    def duplicate_groups(
        self, preview: str, *, revision: int, reason: DuplicateReason, after: str | None, limit: int
    ) -> ImportDuplicateGroups:
        groups = self._repository.summary_groups(preview, revision=revision, reason=reason, after=after, limit=limit)
        cursor = groups[-1].group_key if groups else after
        more = bool(groups) and bool(
            self._repository.summary_groups(preview, revision=revision, reason=reason, after=cursor, limit=1)
        )
        self._base(preview, revision)
        return bounded(
            ImportDuplicateGroups(
                preview_id=preview,
                revision=revision,
                reason=reason,
                groups=[
                    ImportDuplicateGroup(
                        group_key=g.group_key, member_count=g.member_count, first_ordinal=g.first_ordinal
                    )
                    for g in groups
                ],
                next_after=cursor,
                complete=not more,
            )
        )

    def duplicate_members(
        self, preview: str, *, revision: int, reason: DuplicateReason, group_key: str, after: int, limit: int
    ) -> ImportDuplicateMembers:
        ordinals = self._repository.summary_members(
            preview, revision=revision, reason=reason, group_key=group_key, after=after, limit=limit
        )
        rows = self._repository.draft_selection(preview, revision=revision, ordinals=ordinals) if ordinals else ()
        cursor = after
        records: list[RecordSummary] = []
        for row in rows:
            item = self._record_summary(row)
            candidate = ImportDuplicateMembers(
                preview_id=preview,
                revision=revision,
                reason=reason,
                group_key=group_key,
                records=[*records, item],
                next_after=item.ordinal,
                complete=False,
            )
            if encoded_size(candidate) > RESPONSE_BYTES:
                if not records:
                    raise PreviewProblem("preview-response-limit")
                break
            records.append(item)
            cursor = item.ordinal
        if ordinals and not records:
            raise PreviewProblem("preview-draft-incomplete")
        more = bool(ordinals) and bool(
            self._repository.summary_members(
                preview, revision=revision, reason=reason, group_key=group_key, after=cursor, limit=1
            )
        )
        self._base(preview, revision)
        return bounded(
            ImportDuplicateMembers(
                preview_id=preview,
                revision=revision,
                reason=reason,
                group_key=group_key,
                records=records,
                next_after=cursor,
                complete=not more,
            )
        )

    def _base(self, preview: str, expected: int) -> PreviewDraft:
        draft = self._repository.draft(preview)
        if draft.revision != expected:
            raise PreviewProblem("preview-draft-revision-conflict")
        return draft

    def _record(self, preview: str, revision: int, ordinal: int, record_key: str) -> PreviewDraftRecord:
        selected = RecordSelection(ordinal=ordinal, record_key=record_key)
        rows = self._repository.draft_page(preview, revision=revision, after=selected.ordinal - 1, limit=1)
        if not rows or rows[0].record.record_key != selected.record_key:
            raise PreviewProblem("preview-draft-record-mismatch")
        return rows[0]

    def page(self, preview: str, request: ReviewPageRequest) -> ReviewPage:
        request = ReviewPageRequest.model_validate(request)
        draft = self._repository.draft(preview, revision=request.revision)
        if request.after > draft.record_count:
            raise PreviewProblem("preview-cursor-invalid")
        result = ReviewPage(
            revision=request.revision,
            records=[],
            next_after=request.after,
            complete=request.after == draft.record_count,
        )
        rows = self._repository.draft_page(preview, revision=request.revision, after=request.after, limit=request.limit)
        if request.after < draft.record_count and not rows:
            raise PreviewProblem("preview-draft-incomplete")
        for row in rows:
            ordinal = row.record.ordinal

            item = self._record_summary(row)
            candidate = ReviewPage(
                revision=request.revision,
                records=[*result.records, item],
                next_after=ordinal,
                complete=ordinal == draft.record_count,
            )
            if encoded_size(candidate) > RESPONSE_BYTES:
                if not result.records:
                    raise PreviewProblem("preview-response-limit")
                break
            result = candidate
        return bounded(result)

    @staticmethod
    def _record_summary(row: PreviewDraftRecord) -> RecordSummary:
        def short(name: str) -> ShortValue | None:
            value = next((field.value for field in row.decision.fields if field.name == name), None)
            return None if value is None else ShortValue(text=value[:256], truncated=len(value) > 256)

        return RecordSummary.model_validate(
            {
                "ordinal": row.record.ordinal,
                "recordKey": row.record.record_key,
                "kind": row.record.kind,
                "status": row.record.status,
                "included": row.decision.included,
                "title": short("title"),
                "doi": short("doi"),
                "fieldCount": len(row.record.fields),
                "warnings": list(row.warnings),
            }
        )

    def detail(
        self,
        preview: str,
        *,
        revision: int,
        ordinal: int,
        record_key: str,
        section: Section,
        start: int = 0,
        limit: int = 25,
    ) -> ReviewDetail:
        request = ReviewPageRequest(revision=revision, after=start, limit=limit)
        row = self._record(preview, request.revision, ordinal, record_key)
        draft = self._repository.draft(preview, revision=revision)
        if section not in {"raw", "candidates", "effective"}:
            raise PreviewProblem("preview-detail-section-invalid")
        values = (
            row.record.fields
            if section == "raw"
            else row.record.candidates
            if section == "candidates"
            else row.decision.fields
        )
        if start > len(values):
            raise PreviewProblem("preview-cursor-invalid")
        targets = {(item.source_name, item.occurrence): item.target for item in draft.authority.mapping.bindings}
        occurrences: dict[str, int] = {}
        column_targets = {}
        for index, raw in enumerate(row.record.fields):
            occurrence = occurrences.get(raw.name, 0)
            column_targets[index] = (
                cast(MappedName | None, import_field_target(raw.name))
                if draft.authority.mapping.mode == "automatic"
                else targets.get((raw.name, occurrence))
            )
            occurrences[raw.name] = occurrence + 1
        result = ReviewDetail(
            revision=revision,
            ordinal=ordinal,
            record_key=record_key,
            section=section,
            fields=[],
            next_index=start,
            complete=start == len(values),
        )
        for index in range(start, min(len(values), start + limit)):
            if section == "raw":
                raw = row.record.fields[index]
                field = ReviewField(
                    index=index,
                    name=raw.name,
                    value=raw.raw_value,
                    source_field_index=index,
                    origin="raw",
                    warnings=list(raw.warnings),
                    target=column_targets[index],
                )
            elif section == "candidates":
                candidate = row.record.candidates[index]
                field = ReviewField(
                    index=index,
                    name=candidate.name,
                    value=candidate.value,
                    source_field_index=candidate.source_field_index,
                    origin="candidate",
                )
            else:
                mapped = row.decision.fields[index]
                field = ReviewField(
                    index=index,
                    name=mapped.name,
                    value=mapped.value,
                    source_field_index=mapped.source_field_index,
                    origin=mapped.origin,
                )
            page = ReviewDetail(
                revision=revision,
                ordinal=ordinal,
                record_key=record_key,
                section=section,
                fields=[*result.fields, field],
                next_index=index + 1,
                complete=index + 1 == len(values),
            )
            if encoded_size(page) > RESPONSE_BYTES:
                # One maximum-size field's escaped name/value fit this budget.
                # Never silently truncate an accepted or editable value.
                if not result.fields:
                    raise PreviewProblem("preview-response-limit")
                break
            result = page
        return bounded(result)

    def map(self, preview: str, edit: MappingEdit, *, actor: PreviewActor) -> ReviewSummary:
        edit = MappingEdit.model_validate(edit)
        draft = self._base(preview, edit.expected_revision)
        bindings = []
        if edit.mode == "columns":
            rows = self._repository.draft_page(preview, revision=draft.revision, after=0, limit=1)
            if (
                not rows
                or rows[0].record.format_name != "csv"
                or rows[0].record.kind != "header"
                or rows[0].record.status != "parsed"
            ):
                raise PreviewProblem("preview-column-header-unavailable")
            fields = rows[0].record.fields
            for selection in edit.columns:
                if selection.index >= len(fields):
                    raise PreviewProblem("preview-column-index-invalid")
                name = fields[selection.index].name
                occurrence = sum(item.name == name for item in fields[: selection.index])
                bindings.append(FieldMapping(source_name=name, occurrence=occurrence, target=selection.target))
        high_water = self._repository.mapping_high_water(preview)
        mapping = MappingProfile(
            profile_id=draft.authority.mapping.profile_id,
            revision=high_water + 1,
            predecessor_revision=high_water,
            mode=edit.mode,
            bindings=tuple(bindings),
        )
        changed = self._repository.revise_draft(
            preview, PreviewDraftChange(expected_revision=edit.expected_revision, actor=actor, mapping=mapping)
        )
        return self._summary(preview, changed)

    def edit(self, preview: str, edit: GroupEdit, *, actor: PreviewActor) -> ReviewSummary:
        edit = GroupEdit.model_validate(edit)
        self._base(preview, edit.expected_revision)
        corrections = tuple(
            MappedField(name=item.name, value=item.value, source_field_index=None, origin="correction")
            for item in edit.corrections
        )
        names = {item.name for item in corrections}
        decisions: list[RecordDecision] = []
        size = len(
            PreviewDraftChange(expected_revision=edit.expected_revision, actor=actor)
            .model_dump_json(by_alias=True)
            .encode("utf-8")
        )
        for selection in edit.records:
            row = self._record(preview, edit.expected_revision, selection.ordinal, selection.record_key)
            fields = tuple(item for item in row.decision.fields if item.name not in names) + corrections
            decision = review_record(
                row.record,
                included=row.decision.included if edit.included is None else edit.included,
                fields=fields,
                rights=row.decision.rights,
            )
            size += len(decision.model_dump_json(by_alias=True).encode("utf-8")) + bool(decisions)
            if size > 8 * 1024 * 1024:
                raise PreviewProblem("preview-draft-change-limit")
            decisions.append(decision)
        change = PreviewDraftChange(expected_revision=edit.expected_revision, actor=actor, decisions=tuple(decisions))
        # Repository applies its expanded group-size bound atomically too.
        changed = self._repository.revise_draft(preview, change)
        return self._summary(preview, changed)

    def undo(self, preview: str, *, expected_revision: int, actor: PreviewActor) -> ReviewSummary:
        draft = self._base(preview, expected_revision)
        if draft.undo_target_revision is None:
            raise PreviewProblem("preview-undo-unavailable")
        changed = self._repository.revise_draft(
            preview,
            PreviewDraftChange(
                expected_revision=expected_revision, restore_revision=draft.undo_target_revision, actor=actor
            ),
        )
        return self._summary(preview, changed)

    def report(self, preview: str, request: ReviewPageRequest) -> DiagnosticPage:
        request = ReviewPageRequest.model_validate(request)
        draft = self._repository.draft(preview, revision=request.revision)
        if request.after > draft.record_count:
            raise PreviewProblem("preview-cursor-invalid")
        output = io.StringIO(newline="")
        if request.after == 0:
            output.write("ordinal,line_start,line_end,status,diagnostic\r\n")
        writer = csv.writer(output)
        after = request.after
        # Advance from the cursor, never rescan or skip from the start of a report.
        rows = self._repository.draft_page(preview, revision=request.revision, after=after, limit=request.limit)
        if after < draft.record_count and not rows:
            raise PreviewProblem("preview-draft-incomplete")
        for row in rows:
            for warning in row.warnings or ("none",):
                writer.writerow(
                    (
                        row.record.ordinal,
                        row.record.line_start,
                        row.record.line_end,
                        row.record.status,
                        spreadsheet_cell(warning),
                    )
                )
            after = row.record.ordinal
        return bounded(
            DiagnosticPage(
                revision=request.revision, csv=output.getvalue(), next_after=after, complete=after == draft.record_count
            )
        )
