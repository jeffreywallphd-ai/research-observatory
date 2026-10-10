"""Versioned, bounded diagnostics over immutable retained parsing observations.

Coverage describes the retained representation, never source recall or scholarly
correctness. Only authenticated native elements establish expected blocks.
Confidence observations and human acceptance retain their separate authority.
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..ports.workflow_executor import WorkflowJobState
from .contracts import (
    ConfidenceObservation,
    Count,
    Digest,
    DocumentIR,
    Identity,
    IRValue,
    ParserDescriptor,
    SourceIdentity,
    Token,
)
from .native import _kind
from .native_contracts import NATIVE_MEDIA_TYPE, NativeStructure

DEFINITION_VERSION: Literal["parsing-quality-definitions-1"] = "parsing-quality-definitions-1"
RULE_VERSION: Literal["parsing-quality-triage-1"] = "parsing-quality-triage-1"
MAX_QUALITY_ITEMS = 10_000
OPERATION_SECONDS = 5.0
CONFIDENCE_TRIAGE_THRESHOLD = 0.8

type ObservationState = Literal["reported", "unknown", "not-reported", "not-applicable", "ambiguous", "unavailable"]
type Ratio = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class CoverageDimension(IRValue):
    state: ObservationState
    basis: Token
    observed_count: Count | None
    expected_count: Count | None
    missing_count: Count | None
    ratio: Ratio | None


class CountDimension(IRValue):
    state: ObservationState
    basis: Token
    count: Count | None


class StructureDimension(IRValue):
    state: ObservationState
    basis: Token
    observed_count: Count | None
    expected_count: Count | None
    missing_count: Count | None


class ConfidenceDimension(IRValue):
    state: ObservationState
    reported_count: Count | None
    unknown_count: Count | None
    not_reported_count: Count | None
    not_applicable_count: Count | None
    unavailable_count: Count | None
    low_reported_count: Count | None
    triage_threshold: Annotated[float, Field(strict=True, ge=0.8, le=0.8)] = 0.8


class AnchorDimension(IRValue):
    state: ObservationState
    basis: Literal["nonempty-text-node-locators"] = "nonempty-text-node-locators"
    observed_count: Count | None
    expected_count: Count | None
    missing_count: Count | None
    ambiguous_count: Count | None
    parser_observation: ConfidenceObservation


class ReadingOrderDimension(IRValue):
    state: Literal["reported-order", "ambiguous", "unavailable"]
    warning_count: Count | None
    basis: Literal["retained-parser-observation"] = "retained-parser-observation"


class WarningDimension(IRValue):
    state: ObservationState
    count: Count | None
    information_count: Count | None
    warning_count: Count | None
    error_count: Count | None
    codes: tuple[Token, ...] = Field(max_length=32)
    codes_truncated: bool


class QualityDimensions(IRValue):
    text_coverage: CoverageDimension
    page_text_coverage: CoverageDimension
    encoding: CountDimension
    reading_order: ReadingOrderDimension
    sections: StructureDimension
    references: StructureDimension
    expected_blocks: StructureDimension
    anchor_coverage: AnchorDimension
    unresolved_references: CountDimension
    extraction_confidence: ConfidenceDimension
    table_cell_confidence: ConfidenceDimension
    parser_table_cell_confidence: ConfidenceDimension
    table_geometry: CountDimension
    parser_warnings: WarningDimension


type ReviewReason = Literal[
    "missing-retained-text",
    "missing-page-text",
    "replacement-characters",
    "reading-order-ambiguous",
    "reading-order-warning",
    "missing-anchors",
    "missing-expected-blocks",
    "unresolved-references",
    "low-extraction-confidence",
    "low-table-cell-confidence",
    "low-anchor-coverage",
    "table-geometry",
    "parser-warnings",
    "parser-partial-output",
    "inspection-only-output",
    "parser-failure",
    "parse-cancelled",
]


class QualityAssessment(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    definition_version: Literal["parsing-quality-definitions-1"] = DEFINITION_VERSION
    rule_version: Literal["parsing-quality-triage-1"] = RULE_VERSION
    availability: Literal["available", "not-yet-available", "unavailable"]
    dimensions: QualityDimensions
    review_required: bool
    review_reasons: tuple[ReviewReason, ...] = Field(max_length=16)
    human_inspection_available: Literal[True] = True
    scholarly_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def review_relationship(self) -> Self:
        if self.review_required != bool(self.review_reasons) or len(set(self.review_reasons)) != len(
            self.review_reasons
        ):
            raise ValueError("parsing-quality-review-invalid")
        return self


class ParsingQualityReport(IRValue):
    schema_version: Literal["1.0"] = "1.0"
    source: SourceIdentity
    producer: ParserDescriptor
    selection_sha256: Digest
    input_sha256: Digest
    job_id: Identity
    attempt_id: Identity | None
    activity_version: Literal["document-parse-1"] = "document-parse-1"
    job_state: WorkflowJobState
    diagnostic_code: Token | None
    result_id: Identity | None
    result_revision_id: Identity | None
    result_sha256: Digest | None
    assessment: QualityAssessment

    @model_validator(mode="after")
    def exact_result_state(self) -> Self:
        result = (self.result_id, self.result_revision_id, self.result_sha256)
        if (
            (self.job_state == "succeeded") != all(item is not None for item in result)
            or (self.job_state != "succeeded" and any(item is not None for item in result))
            or (self.job_state == "succeeded" and self.attempt_id is None)
            or (self.assessment.availability == "available") != (self.job_state == "succeeded")
            or self.source.format not in self.producer.input_formats
        ):
            raise ValueError("parsing-quality-result-binding-invalid")
        return self


def _confidence(values: Iterable[ConfidenceObservation]) -> ConfidenceDimension:
    counts: Counter[str] = Counter()
    low = 0
    for item in values:
        counts[item.state] += 1
        low += item.state == "reported" and item.value is not None and item.value < CONFIDENCE_TRIAGE_THRESHOLD
    return ConfidenceDimension(
        state="reported" if counts else "not-applicable",
        reported_count=counts["reported"],
        unknown_count=counts["unknown"],
        not_reported_count=counts["not-reported"],
        not_applicable_count=counts["not-applicable"],
        unavailable_count=counts["unavailable"],
        low_reported_count=low,
    )


def _structure(observed: int, expected: int | None, basis: str) -> StructureDimension:
    return StructureDimension(
        state="unknown" if expected is None else "reported",
        basis=basis,
        observed_count=observed,
        expected_count=expected,
        missing_count=None if expected is None else max(0, expected - observed),
    )


def assess_ir(
    ir: DocumentIR,
    *,
    native_artifact: bytes | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> QualityAssessment:
    """Pure derived diagnostics; callers authenticate retained IR/raw and source.

    A native artifact is additionally bound to its exact retained receipt and
    source here. Synthetic fixture expectations cannot enter a Core command.
    This function does not rewrite parser observations or govern acceptance.
    """
    deadline = time.monotonic() + OPERATION_SECONDS

    def check():
        if cancelled():
            raise ValueError("parsing-quality-stopped")
        if time.monotonic() > deadline:
            raise ValueError("parsing-quality-resource-limit")

    check()
    item_count = sum(
        map(
            len,
            (
                ir.nodes,
                ir.text_projections,
                ir.references,
                ir.citations,
                ir.tables,
                ir.figures,
                ir.pages,
                ir.quality.warnings,
                ir.quality.table_cell_confidence,
            ),
        )
    )
    if item_count > MAX_QUALITY_ITEMS:
        raise ValueError("parsing-quality-resource-limit")
    # Admission precedes copying/flattening source-controlled collections.
    for node in ir.nodes:
        item_count += len(node.warnings)
        if item_count > MAX_QUALITY_ITEMS:
            raise ValueError("parsing-quality-resource-limit")
        check()
    for table in ir.tables:
        item_count += len(table.cells)
        if item_count > MAX_QUALITY_ITEMS:
            raise ValueError("parsing-quality-resource-limit")
        check()
    warnings = (*ir.quality.warnings, *(warning for node in ir.nodes for warning in node.warnings))
    cells = tuple(cell for table in ir.tables for cell in table.cells)
    projections = {item.projection_id: item for item in ir.text_projections}
    intervals: dict[str, list[tuple[int, int]]] = {}
    text_pages: set[int] = set()
    required_anchors = missing_anchors = 0
    kinds: Counter[str] = Counter()
    for node in ir.nodes:
        check()
        kinds[node.kind] += 1
        if node.text is None:
            continue
        span = node.text.normalized_range
        text = projections[node.text.projection_id].normalized_text
        intervals.setdefault(node.text.projection_id, []).append((span.start, span.end))
        if span.start == 0 and span.end == len(text):
            nonempty = bool(text) and not text.isspace()
        else:
            nonempty = False
            for position in range(span.start, span.end):
                if position % 1024 == 0:
                    check()
                if not text[position].isspace():
                    nonempty = True
                    break
        if not nonempty:
            continue
        required_anchors += 1
        if node.locator.kind == "unavailable":
            missing_anchors += 1
        elif node.locator.kind == "page-region":
            text_pages.add(node.locator.page_index)
    represented = 0
    for spans in intervals.values():
        end = 0
        for start, stop in sorted(spans):
            represented += max(0, stop - max(start, end))
            end = max(end, stop)
        check()
    total = sum(len(item.normalized_text) for item in ir.text_projections)
    text_coverage = CoverageDimension(
        state="reported",
        basis="normalized-projection-codepoints",
        observed_count=represented,
        expected_count=total,
        missing_count=max(0, total - represented),
        ratio=represented / total if total else None,
    )
    has_pages = ir.binding.source.format in {"pdf", "docx"}
    missing_pages = set(ir.quality.missing_text_pages or ()) | (set(range(len(ir.pages))) - text_pages)
    page_state: ObservationState = "reported" if ir.pages else ("unknown" if has_pages else "not-applicable")
    page_text = CoverageDimension(
        state=page_state,
        basis="retained-source-pages-with-nonempty-located-text",
        observed_count=len(ir.pages) - len(missing_pages) if ir.pages else None,
        expected_count=len(ir.pages) if ir.pages else None,
        missing_count=len(missing_pages) if ir.pages else None,
        ratio=(len(ir.pages) - len(missing_pages)) / len(ir.pages) if ir.pages else None,
    )
    expected: Counter[str] | None = None
    missing_by_kind: Counter[str] = Counter()
    if native_artifact is not None:
        receipt = [item for item in ir.raw_artifacts if item.media_type == NATIVE_MEDIA_TYPE]
        if len(receipt) != 1 or (receipt[0].object_sha256, receipt[0].byte_length) != (
            hashlib.sha256(native_artifact).hexdigest(),
            len(native_artifact),
        ):
            raise ValueError("parsing-quality-native-binding-invalid")
        native = NativeStructure.model_validate_json(native_artifact)
        if (native.format, native.source_sha256, native.source_byte_length) != (
            ir.binding.source.format,
            ir.binding.source.object_sha256,
            ir.binding.source.byte_length,
        ):
            raise ValueError("parsing-quality-native-binding-invalid")
        item_count += len(native.elements)
        if item_count > MAX_QUALITY_ITEMS:
            raise ValueError("parsing-quality-resource-limit")
        expected = Counter(_kind(native, element) for element in native.elements)
        nodes = {node.staged_id: node for node in ir.nodes}
        referenced_nodes = {item.node_id for item in ir.references}
        for element in native.elements:
            kind = _kind(native, element)
            source_node = nodes.get(f"native-node-{element.index}")
            if (
                source_node is None
                or source_node.kind != kind
                or (kind == "reference" and source_node.staged_id not in referenced_nodes)
            ):
                missing_by_kind[kind] += 1
        check()
    basis = "authenticated-native-elements" if expected is not None else "expected-structure-not-reported"
    block_kinds = {"title", "abstract", "section", "paragraph", "reference", "table", "table-cell", "figure", "caption"}
    sections = _structure(kinds["section"], None if expected is None else expected["section"], basis)
    references = _structure(len(ir.references), None if expected is None else expected["reference"], basis)
    expected_blocks = _structure(
        sum(kinds[kind] for kind in block_kinds),
        None if expected is None else sum(expected[kind] for kind in block_kinds),
        basis,
    )
    # Missing one kind cannot be cancelled out by extra nodes of another kind.
    if expected is not None:
        sections = sections.model_copy(update={"missing_count": missing_by_kind["section"]})
        references = references.model_copy(update={"missing_count": missing_by_kind["reference"]})
        expected_blocks = expected_blocks.model_copy(
            update={"missing_count": sum(missing_by_kind[kind] for kind in block_kinds)}
        )
    replacements = sum(item.raw_text.count("\ufffd") for item in ir.text_projections)
    # Native projections overlap; one source-text observation avoids double-counting.
    if native_artifact is not None:
        replacements = native.text.count("\ufffd")
    replacements = max(replacements, ir.quality.replacement_characters or 0)
    ambiguous_refs = sum(item.resolution != "candidate" for item in ir.citations)
    unresolved_state: ObservationState = (
        "reported" if ir.citations or ir.quality.unresolved_references is not None else "not-reported"
    )
    unresolved = max(ambiguous_refs, ir.quality.unresolved_references or 0) if unresolved_state == "reported" else None
    warning_codes = sorted({item.code for item in warnings})
    reading_warnings = sum("reading-order" in item.code for item in warnings)
    geometry = sum(table.grid_state == "ambiguous" for table in ir.tables) + sum(
        "geometry" in item.code or "table-grid" in item.code for item in warnings
    )
    extraction = _confidence(node.confidence for node in ir.nodes)
    table_confidence = _confidence(cell.confidence for cell in cells)
    # The parser may report a separate cell observation; retain a conservative
    # triage signal without replacing either unknown or reported cell values.
    parser_table_confidence = _confidence(item.confidence for item in ir.quality.table_cell_confidence)
    ambiguous_anchors = sum("anchor" in warning.code and "ambiguous" in warning.code for warning in warnings)
    dimensions = QualityDimensions(
        text_coverage=text_coverage,
        page_text_coverage=page_text,
        encoding=CountDimension(state="reported", basis="retained-raw-replacement-codepoints", count=replacements),
        reading_order=ReadingOrderDimension(state=ir.quality.reading_order, warning_count=reading_warnings),
        sections=sections,
        references=references,
        expected_blocks=expected_blocks,
        anchor_coverage=AnchorDimension(
            state="ambiguous" if ambiguous_anchors else ("reported" if required_anchors else "not-applicable"),
            observed_count=required_anchors - missing_anchors,
            expected_count=required_anchors,
            missing_count=missing_anchors,
            ambiguous_count=ambiguous_anchors,
            parser_observation=ir.quality.anchor_coverage,
        ),
        unresolved_references=CountDimension(
            state=unresolved_state, basis="retained-citation-resolution", count=unresolved
        ),
        extraction_confidence=extraction,
        table_cell_confidence=table_confidence,
        parser_table_cell_confidence=parser_table_confidence,
        table_geometry=CountDimension(
            state="reported" if ir.tables or geometry else "not-applicable",
            basis="retained-grid-ambiguity-and-geometry-warnings",
            count=geometry,
        ),
        parser_warnings=WarningDimension(
            state="reported",
            count=len(warnings),
            information_count=sum(w.severity == "information" for w in warnings),
            warning_count=sum(w.severity == "warning" for w in warnings),
            error_count=sum(w.severity == "error" for w in warnings),
            codes=tuple(warning_codes[:32]),
            codes_truncated=len(warning_codes) > 32,
        ),
    )
    reasons: list[ReviewReason] = []
    rules: tuple[tuple[bool, ReviewReason], ...] = (
        (
            not any(p.normalized_text and not p.normalized_text.isspace() for p in ir.text_projections)
            or represented < total,
            "missing-retained-text",
        ),
        (bool(missing_pages), "missing-page-text"),
        (bool(replacements), "replacement-characters"),
        (ir.quality.reading_order == "ambiguous", "reading-order-ambiguous"),
        (bool(reading_warnings), "reading-order-warning"),
        (bool(missing_anchors) or bool(ambiguous_anchors), "missing-anchors"),
        (
            bool(expected_blocks.missing_count) or bool(sections.missing_count) or bool(references.missing_count),
            "missing-expected-blocks",
        ),
        (bool(unresolved), "unresolved-references"),
        (bool(extraction.low_reported_count), "low-extraction-confidence"),
        (
            bool(table_confidence.low_reported_count) or bool(parser_table_confidence.low_reported_count),
            "low-table-cell-confidence",
        ),
        (
            ir.quality.anchor_coverage.state == "reported"
            and ir.quality.anchor_coverage.value is not None
            and ir.quality.anchor_coverage.value < CONFIDENCE_TRIAGE_THRESHOLD,
            "low-anchor-coverage",
        ),
        (bool(geometry), "table-geometry"),
        (any(w.severity in {"warning", "error"} for w in warnings), "parser-warnings"),
        ("parser-partial-output" in warning_codes, "parser-partial-output"),
        (ir.disposition == "inspection-only", "inspection-only-output"),
    )
    for condition, reason in rules:
        if condition:
            reasons.append(reason)
    check()
    return QualityAssessment(
        availability="available", dimensions=dimensions, review_required=bool(reasons), review_reasons=tuple(reasons)
    )


def unavailable_assessment(state: WorkflowJobState) -> QualityAssessment:
    """No invented IR, counts or confidence before a retained success exists."""
    coverage = CoverageDimension(
        state="unavailable",
        basis="no-retained-result",
        observed_count=None,
        expected_count=None,
        missing_count=None,
        ratio=None,
    )
    count = CountDimension(state="unavailable", basis="no-retained-result", count=None)
    structure = StructureDimension(
        state="unavailable", basis="no-retained-result", observed_count=None, expected_count=None, missing_count=None
    )
    confidence = ConfidenceDimension(
        state="unavailable",
        reported_count=None,
        unknown_count=None,
        not_reported_count=None,
        not_applicable_count=None,
        unavailable_count=None,
        low_reported_count=None,
    )
    reasons: tuple[ReviewReason, ...] = (
        ("parser-failure",)
        if state in {"failed", "retry-scheduled"}
        else ("parse-cancelled",)
        if state == "cancelled"
        else ()
    )
    return QualityAssessment(
        availability="unavailable" if reasons else "not-yet-available",
        review_required=bool(reasons),
        review_reasons=reasons,
        dimensions=QualityDimensions(
            text_coverage=coverage,
            page_text_coverage=coverage,
            encoding=count,
            reading_order=ReadingOrderDimension(state="unavailable", warning_count=None),
            sections=structure,
            references=structure,
            expected_blocks=structure,
            anchor_coverage=AnchorDimension(
                state="unavailable",
                observed_count=None,
                expected_count=None,
                missing_count=None,
                ambiguous_count=None,
                parser_observation=ConfidenceObservation(state="unavailable", value=None),
            ),
            unresolved_references=count,
            extraction_confidence=confidence,
            table_cell_confidence=confidence,
            parser_table_cell_confidence=confidence,
            table_geometry=count,
            parser_warnings=WarningDimension(
                state="unavailable",
                count=None,
                information_count=None,
                warning_count=None,
                error_count=None,
                codes=(),
                codes_truncated=False,
            ),
        ),
    )
