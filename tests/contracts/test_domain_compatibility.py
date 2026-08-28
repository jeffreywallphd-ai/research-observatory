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
    DOMAIN_COMPATIBILITY_AUTHORITY_SHA256,
    DOMAIN_COMPATIBILITY_POLICY_SHA256,
    DOMAIN_COMPATIBILITY_SCHEMA_SHA256,
    DOMAIN_EVENT_CATALOG_SHA256,
    PRIOR_DOMAIN_RELEASE_SHA256,
    DomainCompatibilityProblem,
    assess_domain_change,
    assess_domain_event,
    breaking_authority_catalog,
    breaking_authority_catalog_errors,
    contract_releases,
    domain_compatibility_negotiation_errors,
    domain_compatibility_policy,
    domain_event_catalog,
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
        "authorityId": None,
        "migration": None,
        "deprecation": None,
    }


def lifecycle_payload() -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-domain-lifecycle-transition",
        "profileVersion": "1.0.0",
        "subjectKind": "project",
        "aggregateId": "018f47f2-4c75-7b7f-8000-000000000001",
        "fromState": "draft",
        "toState": "active",
        "command": "activate",
        "transitionKind": "normal",
        "priorRevision": 0,
        "revision": 1,
        "actor": {"actorType": "human", "actorId": "researcher"},
        "reason": {"reasonCode": "approved", "detail": None},
        "occurredAt": "2026-08-28T12:00:00.000Z",
        "idempotencyKey": "transition-1",
    }


def event_envelope(event_type: str = "domain.lifecycle-transition", event_version: str = "1.0.0") -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-domain-event-envelope",
        "eventType": event_type,
        "eventVersion": event_version,
        "payload": lifecycle_payload(),
    }


class DomainCompatibilityContractTests(unittest.TestCase):
    root = REPO / "packages" / "contracts" / "domain"

    def test_sources_are_schema_valid_hash_bound_and_current_plus_prior(self) -> None:
        paths = (
            ("domain-compatibility.schema.json", DOMAIN_COMPATIBILITY_SCHEMA_SHA256),
            ("domain-compatibility.v1.json", DOMAIN_COMPATIBILITY_POLICY_SHA256),
            ("fixtures/domain-contract-release.prior.v0.1.json", PRIOR_DOMAIN_RELEASE_SHA256),
            ("fixtures/domain-contract-release.current.v1.json", CURRENT_DOMAIN_RELEASE_SHA256),
            ("domain-compatibility-authorities.v1.json", DOMAIN_COMPATIBILITY_AUTHORITY_SHA256),
            ("domain-event-catalog.v1.json", DOMAIN_EVENT_CATALOG_SHA256),
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

        breaking = proposal("change-identity-format", "0.1.0", "1.0.0")
        denied = assess_domain_change(breaking)
        self.assertEqual(
            (
                "compatibility-breaking-adr-required",
                "compatibility-breaking-migration-required",
                "compatibility-breaking-authority-required",
            ),
            denied["errors"],
        )
        breaking["adrId"] = "ADR-0013"
        breaking["authorityId"] = "authority.uuidv4-project-to-uuidv7-domain"
        breaking["migration"] = {
            "id": "legacy-project-uuidv4-to-canonical-uuidv7",
            "fromVersion": "0.1.0",
            "toVersion": "1.0.0",
            "strategy": "reader-bridge",
            "sourceRetention": "preserved",
            "testFixture": "packages/contracts/project/fixtures/valid-project-manifest.v1.json",
        }
        self.assertTrue(assess_domain_change(breaking)["allowed"])
        fabricated_adr = json.loads(json.dumps(breaking))
        fabricated_adr["adrId"] = "ADR-9999"
        fabricated_errors = cast(tuple[str, ...], assess_domain_change(fabricated_adr)["errors"])
        self.assertIn("compatibility-breaking-authority-mismatch", fabricated_errors)
        absent_fixture = json.loads(json.dumps(breaking))
        cast(dict[str, object], absent_fixture["migration"])["testFixture"] = "fixtures/does-not-exist.json"
        absent_errors = cast(tuple[str, ...], assess_domain_change(absent_fixture)["errors"])
        self.assertIn("compatibility-breaking-authority-mismatch", absent_errors)
        unknown_authority = json.loads(json.dumps(breaking))
        unknown_authority["authorityId"] = "authority.fabricated"
        unknown_errors = cast(tuple[str, ...], assess_domain_change(unknown_authority)["errors"])
        self.assertIn("compatibility-breaking-authority-unknown", unknown_errors)
        errors = cast(tuple[str, ...], assess_domain_change(proposal("remove-field"))["errors"])
        self.assertIn("compatibility-breaking-major-required", errors)

    def test_authority_catalog_rejects_wrong_evidence_status_and_scope(self) -> None:
        source = json.loads((self.root / "domain-compatibility-authorities.v1.json").read_bytes())
        self.assertEqual((), breaking_authority_catalog_errors(source))
        wrong_hash = json.loads(json.dumps(source))
        wrong_hash["authorities"][0]["adr"]["sha256"] = "0" * 64
        self.assertEqual(
            ("compatibility-breaking-authority-evidence-mismatch",), breaking_authority_catalog_errors(wrong_hash)
        )
        wrong_status = json.loads(json.dumps(source))
        wrong_status["authorities"][0]["adr"]["status"] = "Proposed"
        self.assertEqual(
            ("compatibility-breaking-authority-status-not-accepted",), breaking_authority_catalog_errors(wrong_status)
        )
        wrong_scope = json.loads(json.dumps(source))
        wrong_scope["authorities"][0]["applicableTask"] = "CAP-99.S99.T99"
        self.assertEqual(
            ("compatibility-breaking-authority-scope-mismatch",), breaking_authority_catalog_errors(wrong_scope)
        )
        self.assertIsInstance(breaking_authority_catalog(), MappingProxyType)

    def test_event_boundary_denies_unknown_input_and_audits_once(self) -> None:
        audit: list[Mapping[str, object]] = []
        self.assertTrue(assess_domain_event(event_envelope(), audit.append)["allowed"])
        self.assertEqual([], audit)

        denied = assess_domain_event(event_envelope("private.manuscript-secret"), audit.append)
        self.assertEqual(("compatibility-unknown-event",), denied["errors"])
        self.assertEqual(1, len(audit))
        self.assertNotIn("private", str(audit[0]))
        self.assertIsInstance(audit[0], MappingProxyType)

        unknown_field = event_envelope()
        cast(dict[str, object], unknown_field["payload"])["privateText"] = "unpublished manuscript"
        self.assertEqual(
            ("compatibility-event-payload-unknown-field",), assess_domain_event(unknown_field, audit.append)["errors"]
        )
        self.assertEqual(1, len(audit))
        self.assertEqual(
            ("compatibility-event-version-unsupported",),
            assess_domain_event(event_envelope(event_version="2.0.0"), audit.append)["errors"],
        )
        self.assertEqual(2, len(audit))
        with self.assertRaises(DomainCompatibilityProblem) as failed:
            assess_domain_event(
                event_envelope("domain.unknown"), lambda _fact: (_ for _ in ()).throw(RuntimeError("offline"))
            )
        self.assertEqual(("compatibility-audit-publication-failed",), failed.exception.codes)
        self.assertEqual(2, len(cast(tuple[object, ...], domain_event_catalog()["events"])))

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
