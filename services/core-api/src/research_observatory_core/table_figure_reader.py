"""One sparse object and eight cell previews; full observations stay encrypted."""

from typing import Literal

from pydantic import Field, model_validator

from .document_revisions import protected_json
from .document_table_figures import (
    CaptionState,
    HeaderState,
    StructurePreview,
    TableFigureExclusion,
    TableFigureProblem,
)
from .parsing.contracts import (
    CodepointRange,
    ConfidenceObservation,
    Digest,
    Identity,
    IRValue,
    NodeKind,
    ProjectIdentity,
    SourceIdentity,
)


class StructureJump(IRValue):
    node_id: Identity
    node_kind: NodeKind
    text_offset: int = Field(strict=True, ge=0)
    node_text_start: int = Field(strict=True, ge=0)
    normalized_range: CodepointRange | None
    page_number: int | None = Field(strict=True, ge=1, le=500)

    @model_validator(mode="after")
    def coherent(self):
        if self.normalized_range is not None and self.normalized_range.start != self.node_text_start + self.text_offset:
            raise ValueError("structure-reader-offset-invalid")
        return self


class StructureTextPreview(IRValue):
    node_id: Identity
    text_preview: str = Field(strict=True, max_length=512, repr=False)
    text_length: int = Field(strict=True, ge=0, le=65536)
    truncated: bool
    jump: StructureJump

    @model_validator(mode="after")
    def coherent(self):
        span = self.jump.normalized_range
        if (
            self.node_id != self.jump.node_id
            or self.text_length < len(self.text_preview)
            or self.truncated != (self.text_length > len(self.text_preview))
            or (span is None or span.end - span.start != min(512, self.text_length))
        ):
            raise ValueError("structure-reader-text-invalid")
        return self


class TableCellPreview(StructureTextPreview):
    cell_order: int = Field(strict=True, ge=0, lt=10000)
    row: int = Field(strict=True, ge=0, le=100000)
    column: int = Field(strict=True, ge=0, le=100000)
    row_span: int = Field(strict=True, ge=1, le=100000)
    column_span: int = Field(strict=True, ge=1, le=100000)
    header_state: HeaderState
    confidence: ConfidenceObservation
    triage: Literal["low-confidence", "unknown-confidence", "reported-confidence"]

    @model_validator(mode="after")
    def quality(self):
        expected = (
            "unknown-confidence"
            if self.confidence.value is None
            else "low-confidence"
            if self.confidence.value < 0.8
            else "reported-confidence"
        )
        if self.triage != expected or self.jump.node_kind != "table-cell":
            raise ValueError("structure-reader-quality-invalid")
        return self


class TableFigureReaderEntry(IRValue):
    node_id: Identity
    kind: Literal["table", "figure"]
    order: int = Field(strict=True, ge=0, lt=1000)
    jump: StructureJump
    caption_state: CaptionState
    caption_count: int = Field(strict=True, ge=0, le=32)
    captions: tuple[StructureTextPreview, ...] = Field(max_length=4, repr=False)
    label_count: int = Field(strict=True, ge=0, le=16)
    labels: tuple[StructureTextPreview, ...] = Field(max_length=4, repr=False)
    rows: int | None = Field(strict=True, ge=0, le=100000)
    columns: int | None = Field(strict=True, ge=0, le=100000)
    grid_state: Literal["reported", "ambiguous"] | None
    cell_count: int = Field(strict=True, ge=0, le=10000)
    after_cell: int | None = Field(strict=True, ge=0, lt=10000)
    next_after_cell: int | None = Field(strict=True, ge=0, lt=10000)
    cells: tuple[TableCellPreview, ...] = Field(max_length=8, repr=False)
    confidence: ConfidenceObservation
    preview: StructurePreview
    retained_preview_state: Literal["not-reported", "unavailable"]
    warnings: tuple[str, ...] = Field(max_length=32)
    excluded: bool
    exclusion: TableFigureExclusion | None = Field(repr=False)

    @model_validator(mode="after")
    def coherent(self):
        start = 0 if self.after_cell is None else self.after_cell + 1
        count = min(8, max(0, self.cell_count - start))
        if (
            self.node_id != self.jump.node_id
            or self.kind != self.jump.node_kind
            or (
                len(self.captions) != min(4, self.caption_count)
                or len(self.labels) != min(4, self.label_count)
                or len(self.cells) != count
                or len({c.node_id for c in self.cells}) != count
                or [c.cell_order for c in self.cells] != list(range(start, start + count))
                or self.next_after_cell != (start + count - 1 if count and start + count < self.cell_count else None)
                or self.excluded != (self.exclusion is not None)
                or (self.exclusion is not None and self.exclusion.node_id != self.node_id)
                or (self.kind == "table")
                != (self.rows is not None and self.columns is not None and self.grid_state is not None)
                or (self.kind == "figure" and self.cell_count != 0)
                or (self.caption_state == "reported" and self.caption_count != 1)
                or (self.caption_state in {"not-reported", "unavailable"} and self.caption_count != 0)
            )
        ):
            raise ValueError("structure-reader-entry-invalid")
        rows, columns = self.rows, self.columns
        if self.cells and (
            rows is None
            or columns is None
            or any(c.row + c.row_span > rows or c.column + c.column_span > columns for c in self.cells)
        ):
            raise ValueError("structure-reader-entry-invalid")
        if self.preview.kind == "source-page-region" and (
            (self.preview.basis == "object" and self.preview.node_id != self.node_id)
            or (self.preview.basis == "cell" and (self.kind != "table" or self.preview.node_id == self.node_id))
        ):
            raise ValueError("structure-reader-preview-invalid")
        return self


class TableFigureReaderPage(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    source: SourceIdentity
    document_revision_id: Identity
    collection_id: Identity
    collection_revision_id: Identity
    content_sha256: Digest
    structure_sha256: Digest
    total: int = Field(strict=True, ge=0, le=1000)
    after_order: int | None = Field(strict=True, ge=0, lt=1000)
    next_after_order: int | None = Field(strict=True, ge=0, lt=1000)
    entries: tuple[TableFigureReaderEntry, ...] = Field(max_length=1, repr=False)
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def coherent(self):
        start = 0 if self.after_order is None else self.after_order + 1
        count = min(1, max(0, self.total - start))
        if (
            self.source.project_id != self.project_id
            or self.source.document_revision_id == self.document_revision_id
            or self.collection_id == self.collection_revision_id
            or (
                len(self.entries) != count
                or self.next_after_order != (start if count and start + 1 < self.total else None)
                or any(e.order != start for e in self.entries)
            )
        ):
            raise ValueError("structure-reader-page-invalid")
        for entry in self.entries:
            if entry.preview.kind == "source-page-region" and (
                entry.preview.source_revision_id,
                entry.preview.object_sha256,
            ) != (self.source.document_revision_id, self.source.object_sha256):
                raise ValueError("structure-reader-source-invalid")
        if len(protected_json(self)) > 65536:
            raise ValueError("structure-reader-limit")
        return self


class TableFigureReaderNotice(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    source: SourceIdentity
    document_revision_id: Identity
    collection_id: Identity
    collection_revision_id: Identity
    status: Literal["unavailable"] = "unavailable"
    reason_code: Literal["viewer-resource-limit", "table-figures-unavailable"]
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def coherent(self):
        if (
            self.source.project_id != self.project_id
            or self.source.document_revision_id == self.document_revision_id
            or self.collection_id == self.collection_revision_id
        ):
            raise ValueError("structure-reader-source-invalid")
        return self


def reader_page(collection, source, accepted, *, after_order=None, after_cell=None, cell_object_id=None):
    if (source, accepted.revision_id, accepted.content_sha256, accepted.structure_sha256) != (
        collection.source,
        collection.document_revision_id,
        collection.content_sha256,
        collection.structure_sha256,
    ):
        raise TableFigureProblem("structure-reader-source-changed")
    if after_order is not None and (type(after_order) is not int or not 0 <= after_order < len(collection.entries)):
        raise TableFigureProblem("structure-reader-page-invalid")
    start = 0 if after_order is None else after_order + 1
    selected = collection.entries[start : start + 1]
    if (after_cell is None) != (cell_object_id is None) or (
        after_cell is not None
        and (
            type(after_cell) is not int
            or not selected
            or cell_object_id != selected[0].node_id
            or not 0 <= after_cell < len(selected[0].cells)
        )
    ):
        raise TableFigureProblem("structure-reader-cell-page-invalid")
    nodes = {n.node_id: n for n in accepted.structure.nodes}

    def jump(node_id, span=None, target=None):
        node = nodes[node_id]
        span = span or node.text
        text_start = node.text.normalized_range.start if node.text is not None else 0
        normalized = (
            None
            if span is None
            else CodepointRange(
                start=span.normalized_range.start, end=min(span.normalized_range.end, span.normalized_range.start + 512)
            )
        )
        page = (
            target.page_region.page_number
            if target is not None and target.page_region is not None
            else node.locator.page_index + 1
            if node.locator.kind == "page-region"
            else None
        )
        return StructureJump(
            node_id=node_id,
            node_kind=node.kind,
            text_offset=normalized.start - text_start if normalized else 0,
            node_text_start=text_start,
            normalized_range=normalized,
            page_number=page,
        )

    def text(item):
        return StructureTextPreview(
            node_id=item.node_id,
            text_preview=item.normalized_text[:512],
            text_length=len(item.normalized_text),
            truncated=len(item.normalized_text) > 512,
            jump=jump(item.node_id, item.text_span, item.anchor),
        )

    exclusions = {e.node_id: e for e in collection.exclusions}
    previews = []
    for entry in selected:
        cell_start = 0 if after_cell is None else after_cell + 1
        cells = tuple(
            TableCellPreview(
                **text(cell).model_dump(),
                cell_order=index,
                row=cell.row,
                column=cell.column,
                row_span=cell.row_span,
                column_span=cell.column_span,
                header_state=cell.header_state,
                confidence=cell.confidence,
                triage=cell.triage,
            )
            for index, cell in enumerate(entry.cells[cell_start : cell_start + 8], cell_start)
        )
        previews.append(
            TableFigureReaderEntry(
                node_id=entry.node_id,
                kind=entry.kind,
                order=entry.order,
                jump=jump(entry.node_id, target=entry.anchor),
                caption_state=entry.caption_state,
                caption_count=len(entry.captions),
                captions=tuple(text(c) for c in entry.captions[:4]),
                label_count=len(entry.labels),
                labels=tuple(text(c) for c in entry.labels[:4]),
                rows=entry.rows,
                columns=entry.columns,
                grid_state=entry.grid_state,
                cell_count=len(entry.cells),
                after_cell=after_cell,
                next_after_cell=cell_start + len(cells) - 1
                if cells and cell_start + len(cells) < len(entry.cells)
                else None,
                cells=cells,
                confidence=entry.confidence,
                preview=entry.preview,
                retained_preview_state=entry.retained_preview_state,
                warnings=entry.warnings,
                excluded=entry.node_id in exclusions,
                exclusion=exclusions.get(entry.node_id),
            )
        )
    return TableFigureReaderPage(
        project_id=collection.project_id,
        source=source,
        document_revision_id=accepted.revision_id,
        collection_id=collection.collection_id,
        collection_revision_id=collection.collection_revision_id,
        content_sha256=collection.content_sha256,
        structure_sha256=collection.structure_sha256,
        total=len(collection.entries),
        after_order=after_order,
        next_after_order=start if start + 1 < len(collection.entries) else None,
        entries=tuple(previews),
    )
