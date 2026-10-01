"""Focused candidate v2/v1 bridge checks; no process-negotiation authority."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPO / "packages" / "contracts" / "domain"
sys.path.insert(0, str(REPO / "services" / "core-api" / "src"))

from research_observatory_core.domain_contracts import (  # noqa: E402
    CORE_DOMAIN_SCHEMA_SHA256,
    core_aggregate_snapshot_json,
    decode_core_aggregate,
)
from research_observatory_core.domain_contracts_v2 import (  # noqa: E402
    CORE_DOMAIN_SCHEMA_SHA256 as CORE_DOMAIN_V2_SCHEMA_SHA256,
)
from research_observatory_core.domain_contracts_v2 import (  # noqa: E402
    decode_core_aggregate as decode_core_aggregate_v2,
)


def fixture(name: str) -> object:
    return json.loads((CONTRACT_ROOT / "fixtures" / name).read_text(encoding="utf-8"))


class DomainContractsV2Tests(unittest.TestCase):
    def test_exact_v1_rejection_and_v2_corpus_item_acceptance(self) -> None:
        v1 = fixture("valid-core-aggregate.v1.json")
        v2 = fixture("valid-core-aggregate.corpus-item.v2.json")
        schema = json.loads((CONTRACT_ROOT / "domain-core.v2.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual([], list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(v2)))
        self.assertIsNotNone(decode_core_aggregate(v1))
        self.assertIsNone(decode_core_aggregate(v2))
        self.assertIsNone(decode_core_aggregate_v2(v1))
        accepted = decode_core_aggregate_v2(v2)
        assert accepted is not None
        self.assertEqual(accepted["aggregateKind"], "corpus-item")

    def test_generated_reader_hashes_bind_exact_v1_and_v2_schema_bytes(self) -> None:
        self.assertEqual(
            hashlib.sha256((CONTRACT_ROOT / "domain-core.schema.json").read_bytes()).hexdigest(),
            CORE_DOMAIN_SCHEMA_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((CONTRACT_ROOT / "domain-core.v2.schema.json").read_bytes()).hexdigest(),
            CORE_DOMAIN_V2_SCHEMA_SHA256,
        )

    def test_v1_reader_retains_exact_source_values(self) -> None:
        source = fixture("valid-core-aggregate.v1.json")
        snapshot = decode_core_aggregate(source)
        assert snapshot is not None
        self.assertEqual(json.loads(core_aggregate_snapshot_json(snapshot)), source)
        self.assertEqual(snapshot["contractVersion"], "1.0.0")
        self.assertEqual(snapshot["aggregateKind"], "evidence")


if __name__ == "__main__":
    unittest.main()
