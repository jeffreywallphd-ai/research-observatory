"""Snapshot parser value shapes; semantic/use authority remains inside Core."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.document_revisions import (  # noqa: E402
    AcceptedDocumentRevision,
    CanonicalDocumentStructure,
    DocumentRevisionAcceptance,
    RetainedParseResultReceipt,
)
from research_observatory_core.parsing.contracts import DocumentIR  # noqa: E402
from research_observatory_core.parsing.native_contracts import NativeStructure  # noqa: E402
from research_observatory_core.parsing.requests import ParseRequest, ParseResult  # noqa: E402
from research_observatory_core.parsing.selection import ParserSelection  # noqa: E402

OUTPUTS: dict[str, TypeAdapter[Any]] = {
    "document-ir.v1.schema.json": TypeAdapter(DocumentIR),
    "parser-selection.v1.schema.json": TypeAdapter(ParserSelection),
    "parse-request.v1.schema.json": TypeAdapter(ParseRequest),
    "parse-result.v1.schema.json": TypeAdapter(ParseResult),
    "native-structure.v1.schema.json": TypeAdapter(NativeStructure),
    "document-structure.v1.schema.json": TypeAdapter(CanonicalDocumentStructure),
    "document-revision.v1.schema.json": TypeAdapter(AcceptedDocumentRevision),
    "document-revision-acceptance.v1.schema.json": TypeAdapter(DocumentRevisionAcceptance),
    "retained-parse-result.v1.schema.json": TypeAdapter(RetainedParseResultReceipt),
}
REVISION_SCHEMAS = set(OUTPUTS) - {
    "document-ir.v1.schema.json",
    "parser-selection.v1.schema.json",
    "parse-request.v1.schema.json",
    "parse-result.v1.schema.json",
    "native-structure.v1.schema.json",
}
REVISION_RULES = [
    "exact-source-producer-configuration-assets-job-physical-attempt-and-authenticated-raw-receipts",
    "successful-durable-output-required-before-explicit-trusted-human-structural-acceptance",
    "current-native-session-human-intent-privacy-inspect-and-derive-authority-on-read-and-replay",
    "acceptance-command-result-confirmation-and-expected-current-head-are-bound",
    "atomic-decision-revision-core-minted-elements-provenance-dependencies-and-outbox",
    "immutable-revision-scoped-uuidv7-identities-and-exact-graph-element-index",
    "raw-and-nfc-unicode16-codepoint-contributor-mapping-preserved-with-source-geometry",
    "incomplete-or-inspection-only-output-cannot-be-accepted-and-uncertainty-is-preserved",
    "structural-acceptance-does-not-establish-scholarly-verification",
    "strict-utf8-json-unique-fields-no-nonfinite-and-64-mib-wire-cap",
]
SEMANTIC_RULES = [
    "ro-text-nfc-1-unicode-16-newline-fold-and-exact-raw-origin-mapping",
    "half-open-unicode-codepoint-ranges-not-byte-or-utf16-offsets",
    "ordered-unique-staged-identities-with-earlier-parent-and-valid-cross-references",
    "reference-citation-cell-text-contained-in-the-linked-node-projection-and-text",
    "finite-unrotated-source-page-point-geometry-and-explicit-unavailable-locations",
    "reported-table-grid-has-no-overlap-ambiguous-grid-is-retained",
    "unknown-confidence-is-not-zero-and-quality-is-not-human-acceptance",
    "selection-is-a-record-not-source-or-runtime-authority",
    "parent-authenticated-producer-job-attempt-and-artifact-receipts-match-exact-binding",
    "current-protected-source-inspect-derive-intent-privacy-and-session-at-read-and-delivery",
    "failure-cancellation-and-inspection-only-output-cannot-advance-canonical-state",
    "strict-utf8-json-with-unique-fields-and-64-mib-wire-cap",
]


def schema(name: str) -> dict[str, object]:
    result = OUTPUTS[name].json_schema(by_alias=True)
    result["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    result["$id"] = f"https://research-observatory.local/contracts/documents/{name}"
    result["x-research-observatory-semanticRules"] = (
        REVISION_RULES
        if name in REVISION_SCHEMAS
        else (
            [
                "original-source-byte-anchors-distinct-from-decoded-codepoints",
                "unique-preorder-element-index-and-exact-nearest-source-parent",
                "nonoverlapping-markup-and-owned-text-runs-cover-decoded-text",
                "element-text-interval-equals-source-content-boundary-contributors",
                "exact-selected-source-format-digest-length-and-parent-authenticated-artifact",
                "no-worker-receipt-producer-attempt-storage-or-acceptance-authority",
                "strict-utf8-json-unique-fields-no-nonfinite-and-64-mib-wire-cap",
            ]
            if name == "native-structure.v1.schema.json"
            else SEMANTIC_RULES
        )
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name in OUTPUTS:
        target = Path(__file__).with_name(name)
        expected = json.dumps(schema(name), indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not target.is_file() or target.read_text(encoding="utf-8") != expected:
                print(f"Parser schema: STALE {name}")
                return 1
        else:
            target.write_text(expected, encoding="utf-8", newline="\n")
    print("Parser schemas: PASS" if args.check else "Parser schemas: UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
