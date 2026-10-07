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

from research_observatory_core.parsing.contracts import DocumentIR  # noqa: E402
from research_observatory_core.parsing.requests import ParseRequest, ParseResult  # noqa: E402
from research_observatory_core.parsing.selection import ParserSelection  # noqa: E402

OUTPUTS: dict[str, TypeAdapter[Any]] = {
    "document-ir.v1.schema.json": TypeAdapter(DocumentIR),
    "parser-selection.v1.schema.json": TypeAdapter(ParserSelection),
    "parse-request.v1.schema.json": TypeAdapter(ParseRequest),
    "parse-result.v1.schema.json": TypeAdapter(ParseResult),
}
SEMANTIC_RULES = [
    "ro-text-nfc-1-unicode-16-newline-fold-and-exact-raw-origin-mapping",
    "half-open-unicode-codepoint-ranges-not-byte-or-utf16-offsets",
    "ordered-unique-staged-identities-with-earlier-parent-and-valid-cross-references",
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
    result["x-research-observatory-semanticRules"] = SEMANTIC_RULES
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
