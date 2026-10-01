"""Portable corpus wire documents agree with strict Python model values."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from research_observatory_core.corpus.membership import CorpusDecision, CorpusItemRevision, DiscoveryPath
from research_observatory_core.corpus_contracts import (
    CORPUS_MEMBERSHIP_SCHEMA_SHA256,
    corpus_contract_errors,
    decode_corpus_document,
    encode_corpus_decision,
    encode_corpus_item_revision,
    encode_discovery_path,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "packages/contracts/corpus/fixtures"
SCHEMA = ROOT / "packages/contracts/corpus/corpus-membership.schema.json"


def fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def model_fields(document: dict[str, object]) -> dict[str, object]:
    fields = {
        re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower(): value
        for key, value in document.items()
        if key not in {"contractVersion", "documentType"}
    }
    for name in ("discovery_path_ids", "evidence_revision_ids"):
        if name in fields:
            values = fields[name]
            if not isinstance(values, list):
                raise AssertionError("fixture array is not a list")
            fields[name] = tuple(values)
    return fields


class CorpusContractTests(unittest.TestCase):
    def test_schema_hash_and_model_encoder_parity(self) -> None:
        schema_bytes = SCHEMA.read_bytes()
        self.assertEqual(hashlib.sha256(schema_bytes).hexdigest(), CORPUS_MEMBERSHIP_SCHEMA_SHA256)
        Draft202012Validator.check_schema(json.loads(schema_bytes))
        cases = (
            ("valid-corpus-item-revision.v1.json", CorpusItemRevision, encode_corpus_item_revision),
            ("valid-discovery-path.v1.json", DiscoveryPath, encode_discovery_path),
            ("valid-corpus-decision.v1.json", CorpusDecision, encode_corpus_decision),
        )
        for name, model_type, encoder in cases:
            document = fixture(name)
            model = model_type.model_validate(model_fields(document))
            self.assertEqual(encoder(model.model_dump(mode="json", by_alias=True)), document)
            self.assertEqual(corpus_contract_errors(document), ())
            self.assertEqual(decode_corpus_document(document), document)

    def test_denies_unknown_envelopes_and_model_semantic_substitution(self) -> None:
        item = fixture("valid-corpus-item-revision.v1.json")
        path = fixture("valid-discovery-path.v1.json")
        decision = fixture("valid-corpus-decision.v1.json")
        self.assertEqual(
            corpus_contract_errors(fixture("invalid-discovery-path-mixed-source.v1.json")),
            ("corpus-import-path-invalid",),
        )
        self.assertEqual(
            corpus_contract_errors(path | {"direction": "corpus-item-to-source"}),
            ("corpus-contract-schema-invalid",),
        )
        self.assertEqual(
            corpus_contract_errors(path | {"occurredAt": "2026-02-30T20:00:00.000Z"}),
            ("corpus-discovery-time-invalid",),
        )
        self.assertEqual(
            corpus_contract_errors(path | {"predecessorItemRevisionId": path["itemId"]}),
            ("corpus-discovery-identity-invalid",),
        )
        self.assertEqual(
            corpus_contract_errors(path | {"predecessorItemRevisionId": decision["previousRevisionId"]}), ()
        )
        self.assertEqual(
            corpus_contract_errors(fixture("invalid-corpus-decision-time.v1.json")),
            ("corpus-decision-time-invalid",),
        )
        self.assertEqual(
            corpus_contract_errors(
                path
                | {
                    "kind": "connector-record",
                    "ordinal": 0,
                    "recordKeySha256": None,
                    "queryRevisionId": decision["actorId"],
                }
            ),
            (),
        )
        self.assertEqual(
            corpus_contract_errors(
                path
                | {
                    "kind": "citation",
                    "ordinal": None,
                    "recordKeySha256": None,
                    "citingWorkRevisionId": decision["actorId"],
                }
            ),
            (),
        )
        self.assertEqual(
            corpus_contract_errors(item | {"contractVersion": "2.0.0"}), ("corpus-contract-schema-invalid",)
        )
        self.assertEqual(
            corpus_contract_errors(item | {"unexpected": "private data"}), ("corpus-contract-schema-invalid",)
        )
        self.assertEqual(corpus_contract_errors(item | {"membership": "included"}), ("corpus-initial-state-invalid",))
        self.assertEqual(
            corpus_contract_errors(fixture("invalid-corpus-item-unreasoned-availability.v1.json")),
            ("corpus-initial-state-invalid",),
        )
        self.assertEqual(corpus_contract_errors(item | {"review": "none"}), ("corpus-initial-state-invalid",))
        self.assertEqual(
            corpus_contract_errors(item | {"duplicateOfItemId": item["workId"]}),
            ("corpus-initial-state-invalid",),
        )
        self.assertEqual(corpus_contract_errors(path | {"recordKeySha256": None}), ("corpus-import-path-invalid",))
        self.assertEqual(
            corpus_contract_errors(decision | {"occurredAt": "2026-99-99T99:99:99.999Z"}),
            ("corpus-decision-time-invalid",),
        )
        self.assertEqual(
            corpus_contract_errors(decision | {"occurredAt": "0000-01-01T00:00:00.000Z"}),
            ("corpus-decision-time-invalid",),
        )
        aliased_fields = CorpusItemRevision.model_validate(model_fields(item)).model_dump(mode="json", by_alias=True)
        self.assertIsNone(encode_corpus_item_revision(aliased_fields | {"unexpected": "x"}))
        self.assertIsNone(decode_corpus_document(item | {"documentType": "research-observatory-discovery-path"}))
