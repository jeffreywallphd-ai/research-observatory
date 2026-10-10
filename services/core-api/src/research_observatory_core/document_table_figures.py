"""Bounded table/figure observations over immutable accepted document v1.

No source mutation, dense grid allocation, image fetch, OCR or verification.
Retained parser bytes supply relationships, never a new authority grant.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from types import SimpleNamespace
from typing import Annotated, Literal, cast

from pydantic import Field, field_validator, model_validator

from .anchors.contracts import MAX_QUOTE_CODEPOINTS, AnchorSelection, SourceAnchorTarget, build_target
from .document_references import _name, _raw, extract_references
from .document_revisions import AcceptedDocumentRevision, Instant, canonicalize_structure, protected_json
from .parsing.contracts import (
    CodepointRange,
    ConfidenceObservation,
    Digest,
    Identity,
    IRValue,
    PageRegionLocator,
    ProjectIdentity,
    SourceIdentity,
    SourceLocator,
    TextSpan,
)
from .parsing.native_contracts import NativeStructure
from .parsing.requests import ParseRequest

TABLE_FIGURE_MEDIA = "application/vnd.research-observatory.document-table-figures+json"
TABLE_FIGURE_EXTRACTION_VERSION: Literal["document-table-figures/1.0.0"] = "document-table-figures/1.0.0"
MAX_TABLE_FIGURE_BYTES = 16 * 1024 * 1024
MAX_TABLE_FIGURES = 1000
MAX_TABLE_CELLS = 10000
MAX_STRUCTURE_TEXT = 65536
MAX_STRUCTURE_SECONDS = 5.0
CaptionState = Literal["reported", "ambiguous", "not-reported", "unavailable"]
HeaderState = Literal["reported-header", "reported-body", "not-reported"]
Relationships = tuple[
    Mapping[str, Sequence[str]], Mapping[str, Sequence[str]], Mapping[str, HeaderState], set[str], set[str]
]
Index = Annotated[int, Field(strict=True, ge=0, le=100000)]


class TableFigureProblem(ValueError):
    pass


class StructureText(IRValue):
    node_id: Identity
    text_span: TextSpan
    raw_text: Annotated[str, Field(strict=True, max_length=MAX_STRUCTURE_TEXT, repr=False)]
    normalized_text: Annotated[str, Field(strict=True, max_length=MAX_STRUCTURE_TEXT, repr=False)]
    text_offset: Index
    node_text_start: Index
    locator: SourceLocator
    anchor: SourceAnchorTarget | None
    anchor_truncated: bool
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def exact_span(self):
        span = self.text_span.normalized_range
        if len(self.normalized_text) != span.end - span.start or self.node_text_start + self.text_offset != span.start:
            raise ValueError("structure-text-span-invalid")
        if self.anchor is not None and (
            self.anchor.node_id != self.node_id
            or self.anchor.text_position is None
            or self.anchor.text_position.start != span.start
            or self.anchor.text_position.end != min(span.end, span.start + MAX_QUOTE_CODEPOINTS)
            or self.anchor.quote is None
            or self.anchor.quote.exact != self.normalized_text[:MAX_QUOTE_CODEPOINTS]
        ):
            raise ValueError("structure-text-anchor-invalid")
        if self.anchor_truncated != (len(self.normalized_text) > MAX_QUOTE_CODEPOINTS):
            raise ValueError("structure-text-anchor-invalid")
        return self


class TableFigureCell(StructureText):
    row: Index
    column: Index
    row_span: Annotated[int, Field(strict=True, ge=1, le=100000)]
    column_span: Annotated[int, Field(strict=True, ge=1, le=100000)]
    header_state: HeaderState
    confidence: ConfidenceObservation
    triage: Literal["low-confidence", "unknown-confidence", "reported-confidence"]

    @model_validator(mode="after")
    def confidence_label(self):
        expected = (
            "unknown-confidence"
            if self.confidence.value is None
            else "low-confidence"
            if self.confidence.value < 0.8
            else "reported-confidence"
        )
        if self.triage != expected:
            raise ValueError("structure-cell-confidence-invalid")
        return self


class OriginalStructurePreview(IRValue):
    kind: Literal["source-page-region"] = "source-page-region"
    source_revision_id: Identity
    object_sha256: Digest
    node_id: Identity
    locator: PageRegionLocator
    basis: Literal["object", "cell"]
    scholarly_verification: Literal["unverified"] = "unverified"


class UnavailableStructurePreview(IRValue):
    kind: Literal["unavailable"] = "unavailable"
    reason: Literal["format-has-no-pages", "not-reported", "unsupported-location"]


type StructurePreview = Annotated[OriginalStructurePreview | UnavailableStructurePreview, Field(discriminator="kind")]


class TableFigureEntry(IRValue):
    node_id: Identity
    kind: Literal["table", "figure"]
    order: Annotated[int, Field(strict=True, ge=0, lt=MAX_TABLE_FIGURES)]
    source_order: Index
    locator: SourceLocator
    anchor: SourceAnchorTarget | None
    caption_state: CaptionState
    captions: tuple[StructureText, ...] = Field(max_length=32, repr=False)
    labels: tuple[StructureText, ...] = Field(max_length=16, repr=False)
    rows: Index | None
    columns: Index | None
    grid_state: Literal["reported", "ambiguous"] | None
    cells: tuple[TableFigureCell, ...] = Field(max_length=MAX_TABLE_CELLS, repr=False)
    confidence: ConfidenceObservation
    preview: StructurePreview
    retained_preview_state: Literal["not-reported", "unavailable"]
    warnings: tuple[Annotated[str, Field(strict=True, max_length=128)], ...] = Field(max_length=32)
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def coherent(self):
        if (self.kind == "table") != (
            self.rows is not None and self.columns is not None and self.grid_state is not None
        ):
            raise ValueError("structure-grid-kind-invalid")
        if self.kind == "figure" and self.cells:
            raise ValueError("structure-grid-kind-invalid")
        if self.caption_state == "reported" and len(self.captions) != 1:
            raise ValueError("structure-caption-state-invalid")
        if self.caption_state in {"not-reported", "unavailable"} and self.captions:
            raise ValueError("structure-caption-state-invalid")
        if len({c.node_id for c in self.cells}) != len(self.cells):
            raise ValueError("structure-cell-identity-invalid")
        if self.kind == "table":
            rows, columns = self.rows, self.columns
            if (
                rows is None
                or columns is None
                or any(c.row + c.row_span > rows or c.column + c.column_span > columns for c in self.cells)
            ):
                raise ValueError("structure-grid-bounds-invalid")
        if self.preview.kind == "source-page-region":
            if self.preview.basis == "object":
                if self.preview.node_id != self.node_id or self.preview.locator != self.locator:
                    raise ValueError("structure-preview-binding-invalid")
            elif self.kind != "table" or not any(
                c.node_id == self.preview.node_id and c.locator == self.preview.locator for c in self.cells
            ):
                raise ValueError("structure-preview-binding-invalid")
        return self


class TableFigureCommand(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    command_id: Identity
    revision_id: Identity
    expected_collection_revision_id: Identity | None


class TableFigureExcludeCommand(TableFigureCommand):
    expected_collection_revision_id: Identity
    node_id: Identity
    rationale: Annotated[str, Field(strict=True, min_length=1, max_length=256, repr=False)]

    @field_validator("rationale")
    @classmethod
    def reason_required(cls, value):
        if not value.strip():
            raise ValueError("structure-exclusion-rationale-required")
        return value


class TableFigureExclusion(IRValue):
    node_id: Identity
    actor_id: Identity
    command_id: Identity
    rationale: Annotated[str, Field(strict=True, min_length=1, max_length=256, repr=False)]
    occurred_at: Instant

    @field_validator("rationale")
    @classmethod
    def reason_required(cls, value):
        return TableFigureExcludeCommand.reason_required(value)


class TableFigureCollection(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    collection_id: Identity
    collection_revision_id: Identity
    previous_collection_revision_id: Identity | None
    document_revision_id: Identity
    source: SourceIdentity
    content_sha256: Digest
    structure_sha256: Digest
    command_id: Identity
    command_sha256: Digest
    actor_id: Identity
    intent_sha256: Digest
    policy_sha256: Digest
    extracted_at: Instant
    extraction_version: Literal["document-table-figures/1.0.0"] = TABLE_FIGURE_EXTRACTION_VERSION
    change_kind: Literal["extraction", "exclusion"]
    entries: tuple[TableFigureEntry, ...] = Field(max_length=MAX_TABLE_FIGURES, repr=False)
    exclusions: tuple[TableFigureExclusion, ...] = Field(max_length=MAX_TABLE_FIGURES, repr=False)
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def coherent(self):
        ids = [e.node_id for e in self.entries]
        excluded = [e.node_id for e in self.exclusions]
        if (
            len(ids) != len(set(ids))
            or len(excluded) != len(set(excluded))
            or not set(excluded) <= set(ids)
            or [e.order for e in self.entries] != list(range(len(self.entries)))
            or [e.source_order for e in self.entries] != sorted(e.source_order for e in self.entries)
            or sum(len(e.cells) for e in self.entries) > MAX_TABLE_CELLS
        ):
            raise ValueError("structure-collection-identity-invalid")
        if self.change_kind == "exclusion" and not any(
            e.command_id == self.command_id and e.actor_id == self.actor_id and e.occurred_at == self.extracted_at
            for e in self.exclusions
        ):
            raise ValueError("structure-exclusion-binding-invalid")
        if self.source.project_id != self.project_id:
            raise ValueError("structure-collection-source-invalid")
        for entry in self.entries:
            targets = [entry.anchor] + [t.anchor for t in (*entry.captions, *entry.labels, *entry.cells)]
            for target in targets:
                if target is not None and (
                    target.project_id,
                    target.revision_id,
                    target.content_sha256,
                    target.structure_sha256,
                    target.source,
                ) != (
                    self.project_id,
                    self.document_revision_id,
                    self.content_sha256,
                    self.structure_sha256,
                    self.source,
                ):
                    raise ValueError("structure-collection-source-invalid")
            if entry.preview.kind == "source-page-region" and (
                entry.preview.source_revision_id,
                entry.preview.object_sha256,
            ) != (self.source.document_revision_id, self.source.object_sha256):
                raise ValueError("structure-preview-source-invalid")
        if len(protected_json(self)) > MAX_TABLE_FIGURE_BYTES:
            raise ValueError("structure-operation-limit")
        return self


def _docling_relationships(accepted, artifact, checkpoint) -> Relationships:
    """Authenticate the exact accepted normalization before using retained refs."""
    from .parsing.docling import DOCLING_MEDIA_TYPE, _build_ir, _nonfinite, _unique_object

    receipts = [r for r in accepted.structure.raw_artifacts if r.media_type == DOCLING_MEDIA_TYPE]
    if len(receipts) != 1 or (receipts[0].object_sha256, receipts[0].byte_length) != (
        hashlib.sha256(artifact).hexdigest(),
        len(artifact),
    ):
        raise TableFigureProblem("structure-parser-binding-invalid")
    raw = json.loads(artifact.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_nonfinite)
    # The pure adapter consumes only binding. This projection carries the
    # already accepted binding, without inventing parser-selection authority.
    binding_projection = cast(ParseRequest, SimpleNamespace(binding=accepted.structure.binding))
    ir = _build_ir(binding_projection, raw, receipts[0], lambda: checkpoint() or False)
    ids = iter(item.canonical_id for item in accepted.element_identities)
    recreated, mapping = canonicalize_structure(ir, identity_factory=lambda: next(ids))
    if recreated != accepted.structure or mapping != accepted.element_identities:
        raise TableFigureProblem("structure-parser-binding-invalid")
    checkpoint()
    document = raw["document"]
    records = {"#/body": document["body"], "#/furniture": document["furniture"]}
    for group in ("groups", "texts", "pictures", "tables", "key_value_items", "form_items"):
        records.update((f"#/{group}/{i}", item) for i, item in enumerate(document[group]))
    ordered = []
    stack = ["#/furniture", "#/body"]
    while stack:
        checkpoint()
        key = stack.pop()
        ordered.append(key)
        stack.extend(child["$ref"] for child in reversed(records[key]["children"]))
    lookup = {(item.role, item.staged_id): item.canonical_id for item in mapping}
    record_nodes = {}
    next_node = 0
    headers: dict[str, HeaderState] = {}
    for key in ordered:
        checkpoint()
        item = records[key]
        record_nodes[key] = lookup["node", f"docling-node-{next_node}"]
        next_node += 1
        if item["label"] == "table":
            for cell in item["data"]["table_cells"]:
                identity = lookup["node", f"docling-node-{next_node}"]
                next_node += 1
                flags = [cell.get("column_header"), cell.get("row_header")]
                headers[identity] = (
                    "reported-header"
                    if any(flag is True for flag in flags)
                    else "reported-body"
                    if all(flag is False for flag in flags)
                    else "not-reported"
                )
    captions, unavailable = {}, set()
    for key, identity in record_nodes.items():
        item = records[key]
        if item["label"] not in {"picture", "table"}:
            continue
        refs = item.get("captions", [])
        if (
            type(refs) is not list
            or len(refs) > 32
            or any(
                type(ref) is not dict
                or set(ref) != {"$ref"}
                or type(ref["$ref"]) is not str
                or ref["$ref"] not in record_nodes
                or records[ref["$ref"]]["label"] != "caption"
                for ref in refs
            )
        ):
            unavailable.add(identity)
            continue
        captions[identity] = tuple(dict.fromkeys(record_nodes[ref["$ref"]] for ref in refs))
    return captions, {}, headers, set(), unavailable


def _native_relationships(accepted, artifact, checkpoint) -> Relationships:
    # Reuse the existing exact source/name/order/parent/text/receipt validation.
    extract_references(accepted, native_artifact=artifact, cancelled=lambda: checkpoint() or False)
    native = NativeStructure.model_validate_json(artifact)
    nodes = accepted.structure.nodes
    objects = {n.order: n.node_id for n in nodes if n.kind in {"table", "figure"}}
    allowed = {
        "jats": {"", "http://jats.nlm.nih.gov"},
        "tei": {"", "http://www.tei-c.org/ns/1.0"},
        "html": {"", "http://www.w3.org/1999/xhtml"},
        "xml": {""},
    }[native.format]

    def table_wrapper(index):
        namespace, local = _name(nodes[index].source_element_type)
        # JATS table-wrap semantics are not granted to arbitrary foreign XML,
        # TEI or HTML elements merely because their local name happens to match.
        return native.format in {"jats", "xml"} and namespace in allowed and local == "table-wrap"

    owners: list[int | None] = []
    wrappers: list[int | None] = []
    groups: dict[int, list[int]] = {}
    for element in native.elements:
        checkpoint()
        parent = element.parent_index
        owners.append(parent if parent in objects else owners[parent] if parent is not None else None)
        wrappers.append(
            parent if parent is not None and table_wrapper(parent) else wrappers[parent] if parent is not None else None
        )
        wrapper = wrappers[-1]
        if element.index in objects and nodes[element.index].kind == "table" and wrapper is not None:
            groups.setdefault(wrapper, []).append(element.index)
    captions: dict[str, list[str]] = {identity: [] for identity in objects.values()}
    labels: dict[str, list[str]] = {identity: [] for identity in objects.values()}
    ambiguous = set()
    headers: dict[str, HeaderState] = {}
    for node, element in zip(nodes, native.elements, strict=True):
        checkpoint()
        namespace, local = _name(node.source_element_type)
        if namespace not in allowed:
            continue
        if node.kind == "table-cell":
            headers[node.node_id] = (
                "reported-header" if local == "th" else "reported-body" if local == "td" else "not-reported"
            )
        is_caption = node.kind == "caption" or (native.format == "html" and local == "caption")
        if (not is_caption and local != "label") or node.text is None:
            continue
        owner = owners[element.index]
        wrapper = wrappers[element.index]
        candidates = [owner] if owner is not None else groups.get(wrapper, []) if wrapper is not None else []
        for candidate in candidates:
            identity = objects[candidate]
            (captions if is_caption else labels)[identity].append(node.node_id)
            if is_caption and len(candidates) > 1:
                ambiguous.add(identity)
    return captions, labels, headers, ambiguous, set()


def extract_table_figures(
    accepted: AcceptedDocumentRevision,
    *,
    native_artifact: bytes | None = None,
    docling_artifact: bytes | None = None,
    source_lineage=None,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[TableFigureEntry, ...]:
    """Pure derivation; caller holds current source authority through delivery."""
    deadline = time.monotonic() + MAX_STRUCTURE_SECONDS

    def checkpoint():
        if cancelled():
            raise TableFigureProblem("structure-operation-cancelled")
        if time.monotonic() > deadline:
            raise TableFigureProblem("structure-operation-limit")

    checkpoint()
    structure = accepted.structure
    if (
        len(structure.tables) + len(structure.figures) > MAX_TABLE_FIGURES
        or sum(len(t.cells) for t in structure.tables) > MAX_TABLE_CELLS
    ):
        raise TableFigureProblem("structure-operation-limit")
    if any(
        type(raw) is not bytes or len(raw) > MAX_TABLE_FIGURE_BYTES
        for raw in (native_artifact, docling_artifact)
        if raw is not None
    ):
        raise TableFigureProblem("structure-operation-limit")
    if native_artifact is not None and docling_artifact is not None:
        raise TableFigureProblem("structure-parser-binding-invalid")
    relationships: Relationships | None = None
    relationship_base = accepted
    if source_lineage is not None:
        source_lineage.validate(accepted)
        relationship_base = source_lineage.machine_revision
    if native_artifact is not None:
        relationships = _native_relationships(relationship_base, native_artifact, checkpoint)
    elif docling_artifact is not None:
        relationships = _docling_relationships(relationship_base, docling_artifact, checkpoint)
    if relationships is not None and source_lineage is not None:
        old_captions, old_labels, old_headers, old_ambiguous, old_unavailable = relationships

        def lift(groups):
            result = {}
            for source, targets in groups.items():
                checkpoint()
                for current in source_lineage.retained_nodes(source):
                    result[current] = tuple(
                        dict.fromkeys(mapped for target in targets for mapped in source_lineage.retained_nodes(target))
                    )
            return result

        def lift_set(values):
            return {current for old in values for current in source_lineage.retained_nodes(old)}

        relationships = (
            lift(old_captions),
            lift(old_labels),
            {current: state for old, state in old_headers.items() for current in source_lineage.retained_nodes(old)},
            lift_set(old_ambiguous),
            lift_set(old_unavailable),
        )
    captions: Mapping[str, Sequence[str]]
    labels: Mapping[str, Sequence[str]]
    headers: Mapping[str, HeaderState]
    ambiguous: set[str]
    unavailable: set[str]
    captions, labels, headers, ambiguous, unavailable = relationships or ({}, {}, {}, set(), set())
    nodes = {n.node_id: n for n in structure.nodes}
    projections = {p.projection_id: p for p in structure.text_projections}
    # Conservative UTF-8/JSON and model scratch admission. Reused projection
    # spans are charged for every output member before slicing or constructing
    # it. Source-controlled sparse dimensions never expand into a dense grid.
    remaining = MAX_TABLE_FIGURE_BYTES - 2048

    def admit(size):
        nonlocal remaining
        checkpoint()
        if size > remaining:
            raise TableFigureProblem("structure-operation-limit")
        remaining -= size

    def anchor(identity, span):
        start, end = span.normalized_range.start, span.normalized_range.end
        # An anchor has bounded quote/context; no need to copy the entire
        # object's potentially long text just to construct its source jump.
        admit(32768)
        return (
            build_target(
                accepted,
                AnchorSelection(
                    revision_id=accepted.revision_id,
                    node_id=identity,
                    normalized_range=CodepointRange(start=start, end=min(end, start + MAX_QUOTE_CODEPOINTS)),
                ),
            )
            if start < end and not (source_lineage is not None and source_lineage.excludes_span(identity, span))
            else None
        )

    def text(identity, span=None):
        checkpoint()
        node = nodes[identity]
        span = span or node.text
        if span is None or node.text is None:
            raise TableFigureProblem("structure-text-unavailable")
        projection = projections[span.projection_id]
        start, end = span.normalized_range.start, span.normalized_range.end
        raw_size = sum(part.end - part.start for part in span.raw_ranges)
        if max(raw_size, end - start) > MAX_STRUCTURE_TEXT:
            raise TableFigureProblem("structure-operation-limit")
        # Six bytes cover the largest JSON escape per codepoint, including
        # both source strings; range/locator entries also receive a fixed cap.
        locator_ranges = len(node.locator.raw_ranges) if node.locator.kind == "text" else 0
        admit(2048 + 6 * (raw_size + end - start) + 96 * (len(span.raw_ranges) + locator_ranges))
        raw, normalized = _raw(projection, span), projection.normalized_text[start:end]
        if max(len(raw), len(normalized)) > MAX_STRUCTURE_TEXT:
            raise TableFigureProblem("structure-operation-limit")
        target = anchor(identity, span)
        return StructureText(
            node_id=identity,
            text_span=span,
            raw_text=raw,
            normalized_text=normalized,
            text_offset=start - node.text.normalized_range.start,
            node_text_start=node.text.normalized_range.start,
            locator=node.locator,
            anchor=target,
            anchor_truncated=end - start > MAX_QUOTE_CODEPOINTS,
        )

    entries: list[TableFigureEntry] = []
    total = 0
    tables = {t.node_id: t for t in structure.tables}
    figures = {f.node_id: f for f in structure.figures}
    for node in structure.nodes:
        checkpoint()
        table, figure = tables.get(node.node_id), figures.get(node.node_id)
        if table is None and figure is None:
            continue
        if node.kind not in {"table", "figure"}:
            raise TableFigureProblem("structure-object-kind-invalid")
        caption_ids = captions.get(node.node_id, ())
        label_ids = labels.get(node.node_id, ())
        if len(caption_ids) > 32 or len(label_ids) > 16:
            raise TableFigureProblem("structure-operation-limit")
        locator_ranges = len(node.locator.raw_ranges) if node.locator.kind == "text" else 0
        admit(4096 + 96 * locator_ranges)
        cells = []
        if table is not None:
            for cell in table.cells:
                item = text(cell.node_id, cell.raw_text)
                cells.append(
                    TableFigureCell(
                        **item.model_dump(),
                        row=cell.row,
                        column=cell.column,
                        row_span=cell.row_span,
                        column_span=cell.column_span,
                        header_state=headers.get(cell.node_id, "not-reported"),
                        confidence=cell.confidence,
                        triage="unknown-confidence"
                        if cell.confidence.value is None
                        else "low-confidence"
                        if cell.confidence.value < 0.8
                        else "reported-confidence",
                    )
                )
        associated = tuple(text(identity) for identity in dict.fromkeys(caption_ids))
        label_values = tuple(text(identity) for identity in dict.fromkeys(label_ids))
        state: CaptionState = (
            "unavailable"
            if relationships is None or node.node_id in unavailable
            else "ambiguous"
            if len(associated) > 1 or node.node_id in ambiguous
            else "reported"
            if associated
            else "not-reported"
        )
        region = node.locator if node.locator.kind == "page-region" else None
        preview_node = node.node_id
        basis: Literal["object", "cell"] = "object"
        if region is None and table is not None:
            candidate = next((c for c in cells if c.locator.kind == "page-region"), None)
            if candidate is not None and candidate.locator.kind == "page-region":
                region, preview_node, basis = candidate.locator, candidate.node_id, "cell"
        preview = (
            OriginalStructurePreview(
                source_revision_id=structure.binding.source.document_revision_id,
                object_sha256=structure.binding.source.object_sha256,
                node_id=preview_node,
                locator=region,
                basis=basis,
            )
            if region is not None
            else UnavailableStructurePreview(
                reason="format-has-no-pages"
                if not structure.pages
                else "unsupported-location"
                if node.locator.kind == "unavailable" and node.locator.reason == "unsupported-location"
                else "not-reported"
            )
        )
        entry = TableFigureEntry(
            node_id=node.node_id,
            kind=node.kind,
            order=len(entries),
            source_order=node.order,
            locator=node.locator,
            anchor=anchor(node.node_id, node.text) if node.text is not None else None,
            caption_state=state,
            captions=associated,
            labels=label_values,
            rows=table.rows if table else None,
            columns=table.columns if table else None,
            grid_state=table.grid_state if table else None,
            cells=tuple(cells),
            confidence=node.confidence,
            preview=preview,
            retained_preview_state="unavailable" if figure and figure.preview_stage_id is not None else "not-reported",
            warnings=tuple(dict.fromkeys(w.code for w in node.warnings)),
        )
        total += len(protected_json(entry))
        if total > MAX_TABLE_FIGURE_BYTES:
            raise TableFigureProblem("structure-operation-limit")
        entries.append(entry)
    checkpoint()
    return tuple(entries)
