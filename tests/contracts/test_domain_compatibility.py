from __future__ import annotations

import hashlib
import json
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.domain_compatibility import (  # noqa: E402
    CURRENT_DOMAIN_RELEASE_SHA256,
    DOMAIN_COMPATIBILITY_POLICY_SHA256,
    DOMAIN_COMPATIBILITY_SCHEMA_SHA256,
    PRIOR_DOMAIN_RELEASE_SHA256,
    DomainCompatibilityProblem,
    assess_domain_change,
    contract_releases,
    domain_compatibility_negotiation_errors,
    domain_compatibility_policy,
    negotiate_domain_compatibility,
    read_compatibility,
)


def advertisement(role: str, versions: list[str] | None = None) -> dict[str, object]:
    supported = ["0.1.0", "1.0.0"] if versions is None else versions
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-domain-compatibility-advertisement",
        "role": role,
        "componentVersion": "1.0.0",
        "contractFamily": "research-observatory-domain",
        "supportedContractVersions": supported,
        "supportedEventVersions": list(supported),
        "schemaSetId": contract_releases()[1]["schemaSetId"],
    }


def proposal(kind: str, from_version: str = "1.0.0", to_version: str = "1.1.0") -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-domain-change-proposal",
        "fromVersion": from_version,
        "toVersion": to_version,
        "changeKind": kind,
        "artifactId": "domain.aggregate",
        "adrId": None,
        "migration": None,
        "deprecation": None,
    }


class DomainCompatibilityContractTests(unittest.TestCase):
    root = REPO / "packages" / "contracts" / "domain"

    def test_sources_are_schema_valid_hash_bound_and_current_plus_prior(self) -> None:
        paths = (
            ("domain-compatibility.schema.json", DOMAIN_COMPATIBILITY_SCHEMA_SHA256),
            ("domain-compatibility.v1.json", DOMAIN_COMPATIBILITY_POLICY_SHA256),
            ("fixtures/domain-contract-release.prior.v0.1.json", PRIOR_DOMAIN_RELEASE_SHA256),
            ("fixtures/domain-contract-release.current.v1.json", CURRENT_DOMAIN_RELEASE_SHA256),
        )
        for relative, expected in paths:
            self.assertEqual(expected, hashlib.sha256((self.root / relative).read_bytes()).hexdigest())

        schema = json.loads((self.root / "domain-compatibility.schema.json").read_bytes())
        policy = json.loads((self.root / "domain-compatibility.v1.json").read_bytes())
        prior = json.loads((self.root / "fixtures/domain-contract-release.prior.v0.1.json").read_bytes())
        current = json.loads((self.root / "fixtures/domain-contract-release.current.v1.json").read_bytes())
        Draft202012Validator.check_schema(schema)
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(policy)))
        for definition, value in (("ContractRelease", prior), ("ContractRelease", current)):
            validator = Draft202012Validator(
                {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{definition}"}
            )
            self.assertEqual([], list(validator.iter_errors(value)))
        self.assertEqual(("0.1.0", "1.0.0"), tuple(item["contractVersion"] for item in contract_releases()))

    def test_read_compatibility_is_native_bridge_or_unsupported(self) -> None:
        self.assertEqual("native", read_compatibility("1.0.0")["mode"])
        prior = read_compatibility("0.1.0")
        self.assertEqual("bridge-required", prior["mode"])
        self.assertEqual("legacy-project-uuidv4-to-canonical-uuidv7", prior["bridgeId"])
        self.assertEqual("compatibility-read-unsupported", read_compatibility("0.0.9")["diagnosticCode"])

    def test_change_rules_accept_additive_and_gate_breaking_evolution(self) -> None:
        self.assertTrue(assess_domain_change(proposal("add-optional-field"))["allowed"])
        deprecated = proposal("deprecate-field")
        deprecated["deprecation"] = {
            "since": "1.1.0",
            "removalNotBefore": "1.2.0",
            "replacement": "domain.new-field",
        }
        self.assertTrue(assess_domain_change(deprecated)["allowed"])

        breaking = proposal("change-identity-format", "1.0.0", "2.0.0")
        denied = assess_domain_change(breaking)
        self.assertEqual(
            ("compatibility-breaking-adr-required", "compatibility-breaking-migration-required"),
            denied["errors"],
        )
        breaking["adrId"] = "ADR-0013"
        breaking["migration"] = {
            "id": "legacy-project-uuidv4-to-canonical-uuidv7",
            "fromVersion": "1.0.0",
            "toVersion": "2.0.0",
            "strategy": "reader-bridge",
            "sourceRetention": "preserved",
            "testFixture": "packages/contracts/project/fixtures/valid-project-manifest.v1.json",
        }
        self.assertTrue(assess_domain_change(breaking)["allowed"])
        errors = cast(tuple[str, ...], assess_domain_change(proposal("remove-field"))["errors"])
        self.assertIn("compatibility-breaking-major-required", errors)

    def test_negotiation_is_exact_highest_common_and_deterministic(self) -> None:
        desktop = advertisement("desktop")
        sidecar = advertisement("sidecar")
        first = negotiate_domain_compatibility([desktop, sidecar])
        second = negotiate_domain_compatibility([sidecar, desktop])
        self.assertEqual(first, second)
        self.assertEqual("1.0.0", first["contractVersion"])
        self.assertEqual("1.0.0", first["eventVersion"])
        self.assertEqual(("desktop", "sidecar"), first["roles"])

        prior_set = contract_releases()[0]["schemaSetId"]
        items = [
            advertisement("server", ["0.1.0"]),
            advertisement("desktop", ["0.1.0"]),
            advertisement("sidecar", ["0.1.0"]),
        ]
        for item in items:
            item["schemaSetId"] = prior_set
        prior = negotiate_domain_compatibility(items)
        self.assertEqual("0.1.0", prior["contractVersion"])
        self.assertEqual(("desktop", "sidecar", "server"), prior["roles"])

    def test_invalid_inputs_fail_closed_with_content_free_codes(self) -> None:
        self.assertEqual(
            ("compatibility-role-duplicate",),
            domain_compatibility_negotiation_errors([advertisement("desktop"), advertisement("desktop")]),
        )
        self.assertEqual(
            ("compatibility-required-role-missing",),
            domain_compatibility_negotiation_errors([advertisement("desktop"), advertisement("server")]),
        )
        drifted = advertisement("sidecar")
        drifted["schemaSetId"] = contract_releases()[0]["schemaSetId"]
        self.assertEqual(
            ("compatibility-schema-set-mismatch",),
            domain_compatibility_negotiation_errors([advertisement("desktop"), drifted]),
        )
        hostile = advertisement("sidecar")
        hostile["researchText"] = "private manuscript"
        self.assertEqual(
            ("compatibility-advertisement-invalid",),
            domain_compatibility_negotiation_errors([advertisement("desktop"), hostile]),
        )
        with self.assertRaises(DomainCompatibilityProblem) as denied:
            negotiate_domain_compatibility([advertisement("desktop", ["1.0.0"]), advertisement("sidecar", ["0.1.0"])])
        self.assertEqual(("compatibility-contract-version-no-overlap",), denied.exception.codes)
        self.assertNotIn("manuscript", str(denied.exception))

    def test_outputs_are_owned_and_immutable(self) -> None:
        policy = domain_compatibility_policy()
        assessment = assess_domain_change(proposal("add-optional-field"))
        negotiated = negotiate_domain_compatibility([advertisement("desktop"), advertisement("sidecar")])
        self.assertIsInstance(policy, MappingProxyType)
        self.assertIsInstance(cast(Mapping[str, Any], policy)["eventPolicy"], MappingProxyType)
        self.assertIsInstance(assessment, MappingProxyType)
        self.assertIsInstance(negotiated, MappingProxyType)
        with self.assertRaises(TypeError):
            cast(dict[str, object], negotiated)["contractVersion"] = "9.9.9"


if __name__ == "__main__":
    unittest.main()
