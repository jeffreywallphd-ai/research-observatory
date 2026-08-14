from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPO / "packages" / "contracts" / "domain"
sys.path.insert(0, str(REPO / "services" / "core-api" / "src"))

from research_observatory_core.domain_contracts import (  # noqa: E402
    CORE_DOMAIN_SCHEMA_SHA256,
    core_aggregate_snapshot_json,
    decode_core_aggregate,
    domain_contract_errors,
    is_uuid_v7,
    new_uuid_v7,
)


def fixture(name: str) -> object:
    return json.loads((CONTRACT_ROOT / "fixtures" / name).read_text(encoding="utf-8"))


class CoreDomainContractTests(unittest.TestCase):
    def test_schema_and_generated_python_accept_expected_and_disputed_aggregates(self) -> None:
        schema_path = CONTRACT_ROOT / "domain-core.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())

        for name in ("valid-core-aggregate.v1.json", "disputed-core-aggregate.v1.json"):
            value = fixture(name)
            self.assertEqual([], list(validator.iter_errors(value)), name)
            self.assertIsNotNone(decode_core_aggregate(value), name)

        disputed = decode_core_aggregate(fixture("disputed-core-aggregate.v1.json"))
        assert disputed is not None
        disputed_view = cast(Any, disputed)
        self.assertEqual("may contribute to", disputed_view["displayLabel"]["observed"])
        self.assertEqual(
            ["is associated with", "causes"],
            [item["value"] for item in disputed_view["displayLabel"]["alternatives"]],
        )

    def test_schema_and_generated_python_fail_closed_on_material_boundaries(self) -> None:
        schema = json.loads((CONTRACT_ROOT / "domain-core.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for name in (
            "invalid-uuidv4-aggregate.json",
            "invalid-path-bearing-source-reference.json",
            "invalid-disputed-without-alternative.json",
        ):
            value = fixture(name)
            self.assertTrue(list(validator.iter_errors(value)), name)
            self.assertIsNone(decode_core_aggregate(value), name)
            self.assertTrue(domain_contract_errors(value), name)

        unknown = copy.deepcopy(fixture("valid-core-aggregate.v1.json"))
        assert isinstance(unknown, dict)
        unknown["credential"] = "secret"
        self.assertTrue(list(validator.iter_errors(unknown)))
        self.assertIsNone(decode_core_aggregate(unknown))
        prototype_key = json.loads(
            json.dumps(fixture("valid-core-aggregate.v1.json")).replace("{", '{"__proto__":{"credential":"secret"},', 1)
        )
        self.assertIsNone(decode_core_aggregate(prototype_key))

        semantic = copy.deepcopy(fixture("valid-core-aggregate.v1.json"))
        assert isinstance(semantic, dict)
        semantic["revisionId"] = semantic["aggregateId"]
        self.assertIn("revision-identity-distinct", domain_contract_errors(semantic))
        semantic["revisionId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a2"
        semantic["modifiedAt"] = "2026-08-14T11:59:59Z"
        self.assertIn("modified-at-not-before-created-at", domain_contract_errors(semantic))
        semantic["modifiedAt"] = semantic["createdAt"]
        rights = semantic["rights"]
        assert isinstance(rights, dict) and isinstance(rights["deniedUses"], list)
        rights["deniedUses"].append("view")
        self.assertIn("rights-allowed-and-denied-disjoint", domain_contract_errors(semantic))

    def test_python_types_are_bound_to_exact_schema_and_uuidv7_representation(self) -> None:
        schema_bytes = (CONTRACT_ROOT / "domain-core.schema.json").read_bytes()
        self.assertEqual(hashlib.sha256(schema_bytes).hexdigest(), CORE_DOMAIN_SCHEMA_SHA256)
        self.assertTrue(is_uuid_v7("017f22e2-79b0-7cc3-98c4-dc0c0c07398f"))
        self.assertFalse(is_uuid_v7("018f47a2-4d6b-4f78-9f2e-7fb76c86d9a1"))
        self.assertFalse(is_uuid_v7("017F22E2-79B0-7CC3-98C4-DC0C0C07398F"))

    def test_trusted_generator_reproduces_the_rfc_9562_uuidv7_vector_and_denies_bad_entropy(self) -> None:
        random = bytes.fromhex("0cc318c4dc0c0c07398f")
        self.assertEqual(
            "017f22e2-79b0-7cc3-98c4-dc0c0c07398f",
            new_uuid_v7(timestamp_ms=1_645_557_742_000, random_source=lambda size: random if size == 10 else b""),
        )
        with self.assertRaises(ValueError):
            new_uuid_v7(timestamp_ms=-1)
        with self.assertRaises(ValueError):
            new_uuid_v7(timestamp_ms=1, random_source=lambda _size: b"short")

    def test_portable_identifiers_and_text_deny_local_paths_and_trailing_controls(self) -> None:
        base = fixture("valid-core-aggregate.v1.json")
        assert isinstance(base, dict)
        schema = json.loads((CONTRACT_ROOT / "domain-core.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for local in (
            r"C:\private\paper.pdf",
            r"C:private\paper.pdf",
            r"\\server\paper.pdf",
            "/home/private/paper.pdf",
            "~/private/paper.pdf",
            "../private/paper.pdf",
            "private/paper.pdf",
            r"private\paper.pdf",
            "file:///private/paper.pdf",
        ):
            for field in ("observedValue", "normalizedValue"):
                value = copy.deepcopy(base)
                value["externalIdentifiers"][0][field] = local
                self.assertTrue(list(validator.iter_errors(value)), f"{field}: {local}")
                self.assertIsNone(decode_core_aggregate(value), f"{field}: {local}")
        for text in ("word\n", "word\r"):
            observed = copy.deepcopy(base)
            observed["displayLabel"]["observed"] = text
            self.assertTrue(list(validator.iter_errors(observed)))
            self.assertIsNone(decode_core_aggregate(observed))
            confidence = copy.deepcopy(base)
            confidence["confidence"] = {"kind": "quantified", "value": 0.5, "basis": text}
            self.assertTrue(list(validator.iter_errors(confidence)))
            self.assertIsNone(decode_core_aggregate(confidence))

        web = copy.deepcopy(base)
        web["externalIdentifiers"][0] = {
            "scheme": "url",
            "observedValue": "HTTPS://example.org/article/7",
            "normalizedValue": "https://example.org/article/7",
            "verificationState": "verified",
            "sourceReference": base["externalIdentifiers"][0]["sourceReference"],
        }
        self.assertIsNotNone(decode_core_aggregate(web))

    def test_python_decoder_owns_freezes_and_normalizes_the_revision_snapshot(self) -> None:
        value = fixture("valid-integral-float-core-aggregate.v1.json")
        assert isinstance(value, dict)
        schema = json.loads((CONTRACT_ROOT / "domain-core.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertEqual([], list(validator.iter_errors(value)))
        decoded = decode_core_aggregate(value)
        assert decoded is not None
        decoded_view = cast(Any, decoded)
        self.assertIsNot(decoded, value)
        self.assertIsInstance(decoded_view["revision"], int)
        self.assertIsInstance(decoded_view["sourceReferences"][0]["sourceRevision"], int)
        before = core_aggregate_snapshot_json(decoded)
        value["displayLabel"]["observed"] = "mutated after validation"
        value["sourceReferences"][0]["sourceLabel"] = "mutated source"
        self.assertEqual(before, core_aggregate_snapshot_json(decoded))
        with self.assertRaises(TypeError):
            decoded_view["displayLabel"]["observed"] = "forbidden"
        with self.assertRaises(TypeError):
            dict.__setitem__(decoded_view["displayLabel"], "observed", "base-class-bypass")
        with self.assertRaises(TypeError):
            list.append(decoded_view["sourceReferences"], {"bypass": True})


if __name__ == "__main__":
    unittest.main()
