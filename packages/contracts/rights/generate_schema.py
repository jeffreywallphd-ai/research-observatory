"""Freeze the Core rights value shapes into a portable JSON Schema snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "core-api" / "src"))

from research_observatory_core.rights_policy import RightsDecision, RightsPolicyRevision  # noqa: E402

SCHEMA = Path(__file__).with_name("rights-policy.schema.json")
SEMANTIC_RULES = [
    "one-exact-project-source-address-copy-resource-per-policy",
    "unique-assertion-and-evidence-identities",
    "action-purpose-destination-context-is-exact",
    "source-observation-is-not-permission",
    "reported-license-access-and-terms-are-non-granting-source-observations",
    "source-observation-binds-the-exact-record-assertion-and-hash",
    "entitlement-and-confirmation-provenance",
    "canonical-real-utc-millisecond-time-and-expiry",
    "decision-is-a-historical-fact-not-use-authority",
    "legacy-import-bridge-requires-exact-retained-assertion-hash-and-local-metadata-scope",
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
            raise ValueError("rights-contract-properties-missing")
        result["additionalProperties"] = False
        result["required"] = list(properties)
    return result


def schema() -> dict[str, object]:
    definitions: dict[str, object] = {}
    for name, model in (("RightsPolicyRevision", RightsPolicyRevision), ("RightsDecision", RightsDecision)):
        raw = model.model_json_schema(by_alias=True)
        nested = raw.pop("$defs")
        for key, node in nested.items():
            normalized = normalize(node)
            if key in definitions and definitions[key] != normalized:
                raise ValueError(f"rights-contract-definition-drift:{key}")
            definitions[key] = normalized
        definitions[name] = normalize(raw)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://research-observatory.local/contracts/rights/rights-policy.schema.json",
        "title": "Research Observatory rights policy and decision documents",
        "description": (
            "Versioned source/copy-specific values; Core rechecks current policy and independent actor, "
            "Intent, privacy and project authority at use time."
        ),
        "x-research-observatory-semanticRules": SEMANTIC_RULES,
        "oneOf": [
            {"$ref": "#/$defs/RightsPolicyRevision"},
            {"$ref": "#/$defs/RightsDecision"},
        ],
        "$defs": definitions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = json.dumps(schema(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not SCHEMA.exists() or SCHEMA.read_text(encoding="utf-8") != expected:
            print("Rights schema: STALE")
            return 1
        print("Rights schema: PASS")
        return 0
    SCHEMA.write_text(expected, encoding="utf-8", newline="\n")
    print("Rights schema: UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
