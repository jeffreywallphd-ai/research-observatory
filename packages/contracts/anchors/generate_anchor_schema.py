"""Portable anchor value shapes; schema validity does not confer source authority."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.anchors.contracts import (  # noqa: E402
    AnchorSelection,
    CitationLinkResolution,
    DocumentReaderOutline,
    DocumentReaderRevisions,
    NormalizedPageRegion,
    SourceAnchorReceipt,
    SourceAnchorResolution,
    SourceAnchorTarget,
)

OUTPUTS = {
    "source-anchor.v1.schema.json": SourceAnchorReceipt,
    "source-anchor-target.v1.schema.json": SourceAnchorTarget,
    "anchor-selection.v1.schema.json": AnchorSelection,
    "page-region.v1.schema.json": NormalizedPageRegion,
    "reader-outline.v1.schema.json": DocumentReaderOutline,
    "reader-revisions.v1.schema.json": DocumentReaderRevisions,
    "anchor-resolution.v1.schema.json": SourceAnchorResolution,
    "citation-links.v1.schema.json": CitationLinkResolution,
}
RULES = [
    "core-mints-anchor-and-revision-ids-on-existing-canonical-document-aggregate",
    "exact-accepted-revision-project-copy-and-structural-projection-identities-are-authoritative",
    "quote-position-context-and-selected-node-agree-without-fuzzy-relocation",
    "ro-text-nfc-1-unicode16-half-open-codepoint-offsets-with-explicit-utf16-renderer-conversion",
    "normalized-rectangle-unrotated-source-page-top-left-with-explicit-page-dimensions-and-rotation",
    "page-number-is-one-based-display-of-zero-based-page-index-and-block-granularity-is-explicit",
    "missing-coordinates-and-unknown-confidence-remain-distinct-visible-states",
    "current-native-human-session-intent-privacy-inspect-and-derive-authority-on-replay-and-delivery",
    "encrypted-retained-context-has-canonical-provenance-dependency-and-outbox-integrity",
    "context-authentication-does-not-establish-current-original-byte-integrity",
    "same-command-same-actor-same-selection-replays-and-conflicting-retries-deny",
    "selection-and-parser-confidence-do-not-confer-human-scholarly-verification",
]


def schema(name):
    result = OUTPUTS[name].model_json_schema(by_alias=True)
    result["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    result["$id"] = "https://research-observatory.local/contracts/anchors/" + name
    result["x-research-observatory-semanticRules"] = RULES
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name in OUTPUTS:
        path = Path(__file__).with_name(name)
        expected = json.dumps(schema(name), indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                print("Anchor schema: STALE " + name)
                return 1
        else:
            path.write_text(expected, encoding="utf-8", newline="\n")
    print("Anchor schemas: PASS" if args.check else "Anchor schemas: UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
