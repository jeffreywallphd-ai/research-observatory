"""Freeze Core's report DTOs into a portable versioned JSON Schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-api" / "src"))

from research_observatory_core.corpus_report_model import (  # noqa: E402
    CorpusReportDrillPage,
    CorpusReportMember,
    CorpusReportSnapshot,
)

SCHEMA = ROOT / "packages" / "contracts" / "corpus-reports" / "corpus-report.schema.json"
SEMANTIC_RULES = [
    "snapshot-denominator-is-one-current-revision-per-canonical-item",
    "report-member-rows-are-strictly-ordered-by-item-id",
    "source-and-route-contributions-count-distinct-member-items-not-paths",
    "source-and-route-overlap-count-distinct-items-in-pair-intersection",
    "unattributed-paths-never-invent-source-roots",
    "all-seven-dimensions-classify-every-member-once",
    "known-values-require-exact-retained-rights-authorized-witness",
    "missing-values-are-not-zero-or-imputed",
    "summary-overflow-is-explicit-and-member-drill-stays-exact",
    "report-creation-and-current-read-authority-remain-core-responsibilities",
]


def normalize(value: object) -> object:
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: normalize(item) for key, item in value.items() if key not in {"title", "description", "default"}}
    if result.get("type") == "object":
        properties = result.get("properties")
        if not isinstance(properties, dict):
            raise ValueError("corpus-report-contract-properties-missing")
        result["additionalProperties"] = False
        result["required"] = list(properties)
    return result


def schema() -> dict[str, object]:
    definitions: dict[str, object] = {}
    models = (
        ("CorpusReportSnapshot", CorpusReportSnapshot),
        ("CorpusReportMember", CorpusReportMember),
        ("CorpusReportDrillPage", CorpusReportDrillPage),
    )
    for name, model in models:
        raw = model.model_json_schema(by_alias=True)
        nested = raw.pop("$defs")
        for key, node in nested.items():
            normalized = normalize(node)
            if key in definitions and definitions[key] != normalized:
                raise ValueError(f"corpus-report-contract-definition-drift:{key}")
            definitions[key] = normalized
        definitions[name] = normalize(raw)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://research-observatory.local/contracts/corpus-reports/corpus-report.schema.json",
        "title": "Research Observatory corpus report snapshot, member and drill page",
        "description": (
            "Immutable canonical-item report values. Core rechecks project, Intent, source, "
            "rights and current read authority in protected storage."
        ),
        "x-research-observatory-semanticRules": SEMANTIC_RULES,
        "oneOf": [{"$ref": f"#/$defs/{name}"} for name, _ in models],
        "$defs": definitions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = json.dumps(schema(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not SCHEMA.exists() or SCHEMA.read_text(encoding="utf-8") != expected:
            print("Corpus report schema: STALE")
            return 1
        print("Corpus report schema: PASS")
        return 0
    SCHEMA.write_text(expected, encoding="utf-8", newline="\n")
    print("Corpus report schema: UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
