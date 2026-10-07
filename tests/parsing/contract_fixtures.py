"""Declared synthetic staged values; no worker/runtime qualification."""

from research_observatory_core.parsing.contracts import (
    ConfidenceObservation,
    DocumentIR,
    IRNode,
    LocalOrigin,
    ParseAttempt,
    ParseBinding,
    ParseQualityReport,
    ParserDescriptor,
    SourceIdentity,
    TextLocator,
    TextProjection,
    TextSpan,
)


def identity(number):
    return f"018f0000-0000-7000-8000-{number:012x}"


def source(format_name="plain-text", number=1):
    return SourceIdentity(
        project_id=identity(100),
        attachment_id=identity(number),
        document_id=identity(101),
        document_revision_id=identity(102),
        candidate_id=identity(number + 200),
        source_assertion_revision_id=identity(103),
        work_id=identity(104),
        work_revision_id=identity(105),
        version_id=identity(106),
        version_revision_id=identity(107),
        object_sha256="1" * 64,
        byte_length=3,
        format=format_name,
        provenance=LocalOrigin(kind="local-import"),
    )


def descriptor(parser_id="ro-native-structured", formats=("jats", "tei", "xml", "html")):
    return ParserDescriptor(
        parser_id=parser_id,
        version="1.0.0",
        kind="native",
        input_formats=formats,
        configuration_version="native-1",
        configuration_sha256="2" * 64,
        assets=(),
    )


def binding(selected=None, producer=None):
    return ParseBinding(
        source=selected or source(),
        attempt=ParseAttempt(job_id=identity(300), attempt_id=identity(301), activity_version="document-parse-1"),
        producer=producer or descriptor("ro-native-text", ("plain-text",)),
        selection_sha256="3" * 64,
    )


def ir(bound=None, raw="abc"):
    return DocumentIR(
        schema_version="1.0",
        disposition="staged",
        binding=bound or binding(),
        normalization_version="ro-text-nfc-1",
        unicode_version="16.0.0",
        text_projections=(TextProjection.from_raw("text-1", raw),),
        pages=(),
        nodes=(
            IRNode(
                staged_id="node-1",
                kind="paragraph",
                order=0,
                parent_id=None,
                text=TextSpan.model_validate(
                    {
                        "projectionId": "text-1",
                        "normalizedRange": {"start": 0, "end": len(raw)},
                        "rawRanges": [{"start": 0, "end": len(raw)}] if raw else [],
                    }
                ),
                locator=TextLocator.model_validate(
                    {
                        "kind": "text",
                        "projectionId": "text-1",
                        "rawRanges": [{"start": 0, "end": len(raw)}] if raw else [],
                    }
                ),
                confidence=ConfidenceObservation(state="unknown", value=None),
                warnings=(),
                source_element_type=None,
            ),
        ),
        references=(),
        citations=(),
        tables=(),
        figures=(),
        raw_artifacts=(),
        quality=ParseQualityReport(
            missing_text_pages=None,
            replacement_characters=None,
            reading_order="reported-order",
            anchor_coverage=ConfidenceObservation(state="unknown", value=None),
            unresolved_references=None,
            table_cell_confidence=(),
            warnings=(),
        ),
    )


def rich_ir_wire():
    """Synthetic gold, authored offsets/relationships rather than parser output."""
    value = ir().model_dump(mode="json", by_alias=True)
    raw = "Title\nText [1]\nRef one\nRef two\nA\nB\nCaption\nUnknown"
    value["textProjections"] = [TextProjection.from_raw("text-1", raw).model_dump(mode="json", by_alias=True)]
    value["nodes"] = []
    unknown = {"state": "unknown", "value": None}

    def span(start, end):
        return {
            "projectionId": "text-1",
            "normalizedRange": {"start": start, "end": end},
            "rawRanges": [{"start": start, "end": end}],
        }

    def node(key, kind, parent, bounds=None):
        text = span(*bounds) if bounds else None
        location = (
            {"kind": "text", "projectionId": "text-1", "rawRanges": text["rawRanges"]}
            if text
            else {"kind": "unavailable", "reason": "format-has-no-pages"}
        )
        value["nodes"].append(
            {
                "stagedId": key,
                "kind": kind,
                "order": len(value["nodes"]),
                "parentId": parent,
                "text": text,
                "locator": location,
                "confidence": unknown,
                "warnings": [],
                "sourceElementType": None,
            }
        )

    node("title", "title", None, (0, 5))
    node("section", "section", None)
    node("paragraph", "paragraph", "section", (6, 14))
    node("marker", "citation-marker", "paragraph", (11, 14))
    node("ref1", "reference", None, (15, 22))
    node("ref2", "reference", None, (23, 30))
    node("table", "table", "section")
    node("cell1", "table-cell", "table", (31, 32))
    node("cell2", "table-cell", "table", (33, 34))
    node("figure", "figure", "section")
    node("caption", "caption", "figure", (35, 42))
    node("unknown", "unknown", "section", (43, 50))
    value["nodes"][-1]["sourceElementType"] = "synthetic-unsupported-element"
    value["references"] = [
        {
            "stagedId": "ref-entry-1",
            "nodeId": "ref1",
            "order": 0,
            "rawText": span(15, 22),
            "identifiers": [{"scheme": "doi", "observed": "10.synthetic/one"}],
        },
        {"stagedId": "ref-entry-2", "nodeId": "ref2", "order": 1, "rawText": span(23, 30), "identifiers": []},
    ]
    value["citations"] = [
        {
            "stagedId": "citation-1",
            "nodeId": "marker",
            "marker": span(11, 14),
            "referenceCandidates": ["ref-entry-1", "ref-entry-2"],
            "resolution": "ambiguous",
        }
    ]
    value["tables"] = [
        {
            "nodeId": "table",
            "rows": 2,
            "columns": 2,
            "gridState": "reported",
            "cells": [
                {
                    "nodeId": "cell1",
                    "row": 0,
                    "column": 0,
                    "rowSpan": 2,
                    "columnSpan": 1,
                    "rawText": span(31, 32),
                    "confidence": unknown,
                },
                {
                    "nodeId": "cell2",
                    "row": 0,
                    "column": 1,
                    "rowSpan": 1,
                    "columnSpan": 1,
                    "rawText": span(33, 34),
                    "confidence": {"state": "reported", "value": 0.7},
                },
            ],
        }
    ]
    value["rawArtifacts"] = [
        {"stageId": identity(700), "objectSha256": "7" * 64, "byteLength": 4, "mediaType": "image/png"}
    ]
    value["figures"] = [
        {
            "nodeId": "figure",
            "caption": span(35, 42),
            "locator": {"kind": "unavailable", "reason": "format-has-no-pages"},
            "previewStageId": identity(700),
        }
    ]
    value["quality"]["readingOrder"] = "ambiguous"
    value["quality"]["tableCellConfidence"] = [{"nodeId": "cell1", "confidence": unknown}]
    value["quality"]["warnings"] = [
        {
            "code": "unsupported-element",
            "severity": "warning",
            "nodeId": "unknown",
            "detail": "Synthetic retained content; no inferred meaning.",
        }
    ]
    return value
