from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPO / "packages" / "contracts" / "intent"
sys.path.insert(0, str(REPO / "services" / "core-api" / "src"))

from research_observatory_core.research_intent_contracts import (  # noqa: E402
    decode_research_intent_reference,
    decode_research_intent_revision,
    governing_research_intent_reference,
    research_intent_reference_errors,
    research_intent_revision_errors,
    research_intent_snapshot_json,
)


def fixture(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((CONTRACT_ROOT / "fixtures" / name).read_text(encoding="utf-8")))


class ResearchIntentContractTests(unittest.TestCase):
    def test_schema_and_generated_python_accept_expected_revision_and_reference(self) -> None:
        schema = json.loads((CONTRACT_ROOT / "research-intent.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        revision = fixture("valid-systematic-intent.v1.json")
        self.assertEqual([], list(validator.iter_errors(revision)))
        decoded = decode_research_intent_revision(revision)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        before = research_intent_snapshot_json(decoded)
        revision["researchQuestion"]["value"] = "mutated"
        self.assertEqual(before, research_intent_snapshot_json(decoded))
        self.assertEqual(
            decode_research_intent_reference(fixture("valid-systematic-reference.v1.json")),
            governing_research_intent_reference(decoded),
        )

    def test_all_epistemic_modes_have_distinct_valid_requirements_and_stopping_rules(self) -> None:
        cases: tuple[tuple[str, str, dict[str, Any], list[str]], ...] = (
            (
                "theory",
                "theory-synthesis",
                {"kind": "theory", "synthesisApproach": "integrative", "theoreticalLenses": ["institutional theory"]},
                ["interpretive-saturation"],
            ),
            (
                "technical",
                "technical-landscape",
                {
                    "kind": "technical",
                    "evaluationTargets": ["local inference runtime"],
                    "benchmarkDimensions": ["latency"],
                },
                ["benchmark-complete"],
            ),
            (
                "hermeneutic",
                "hermeneutic-inquiry",
                {
                    "kind": "hermeneutic",
                    "interpretiveTradition": "hermeneutic circle",
                    "iterationLogic": "Reading revises search and interpretation.",
                },
                ["interpretive-saturation"],
            ),
            (
                "critical",
                "critical-problematization",
                {
                    "kind": "critical",
                    "criticalTradition": "critical information systems",
                    "affectedStakeholders": ["research participants"],
                    "reflexivityCommitment": "Retain standpoint and exclusion memos.",
                },
                ["researcher-decision"],
            ),
            (
                "novelty",
                "novelty-audit",
                {"kind": "novelty", "opportunityTypes": ["theory-gap"], "nearestPriorWorkChallenge": True},
                ["nearest-prior-work-challenged"],
            ),
            (
                "empirical",
                "empirical-study-design",
                {"kind": "empirical", "studyType": "mixed-methods", "designConstraints": ["local ethics review"]},
                ["protocol-complete"],
            ),
        )
        for mode, use_case, requirements, conditions in cases:
            with self.subTest(mode=mode):
                revision = fixture("valid-systematic-intent.v1.json")
                revision["epistemicMode"] = mode
                revision["primaryUseCase"] = use_case
                revision["modeRequirements"] = requirements
                revision["stoppingRule"]["conditions"] = conditions
                self.assertEqual((), research_intent_revision_errors(revision))

        theory = fixture("valid-systematic-intent.v1.json")
        theory["epistemicMode"] = "theory"
        theory["primaryUseCase"] = "theory-synthesis"
        theory["modeRequirements"] = {
            "kind": "theory",
            "synthesisApproach": "conceptual",
            "theoreticalLenses": ["practice theory"],
        }
        theory["unitOfAnalysis"] = {"state": "not-applicable", "rationale": "The synthesis is construct-centered."}
        theory["levelOfAnalysis"] = {
            "state": "not-applicable",
            "rationale": "No single empirical level governs the synthesis.",
        }
        theory["stoppingRule"]["conditions"] = ["researcher-decision"]
        self.assertEqual((), research_intent_revision_errors(theory))
        theory["epistemicMode"] = "systematic"
        theory["primaryUseCase"] = "systematic-review"
        theory["modeRequirements"] = {
            "kind": "systematic",
            "protocol": "systematic-review",
            "inclusionLogic": "Predeclared.",
            "comprehensivenessTarget": "bounded",
        }
        theory["stoppingRule"]["conditions"] = ["coverage-threshold"]
        self.assertIn("accepted-revision-is-decision-complete", research_intent_revision_errors(theory))

    def test_generated_python_rejects_unsafe_unknown_and_mode_mismatch(self) -> None:
        unknown = fixture("valid-systematic-intent.v1.json")
        unknown["credential"] = "secret"
        self.assertIsNone(decode_research_intent_revision(unknown))
        hostile = json.loads(
            json.dumps(fixture("valid-systematic-intent.v1.json")).replace(
                "{", '{"__proto__":{"credential":"secret"},', 1
            )
        )
        self.assertIsNone(decode_research_intent_revision(hostile))
        mismatch = fixture("valid-systematic-intent.v1.json")
        mismatch["modeRequirements"]["kind"] = "critical"
        self.assertIn("mode-requirements-match-epistemic-mode", research_intent_revision_errors(mismatch))

    def test_lineage_stopping_and_human_authority_are_semantic_boundaries(self) -> None:
        lineage = fixture("valid-systematic-intent.v1.json")
        lineage["revision"] = 3
        lineage["parentRevision"] = {
            "revisionId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a5",
            "revision": 1,
            "revisionContentHash": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
        }
        self.assertIn("revision-lineage-is-immediate", research_intent_revision_errors(lineage))
        stopping = fixture("valid-systematic-intent.v1.json")
        stopping["stoppingRule"]["conditions"] = ["researcher-decision"]
        self.assertIn("stopping-rule-matches-epistemic-mode", research_intent_revision_errors(stopping))
        authority = fixture("valid-systematic-intent.v1.json")
        authority["decision"]["actorType"] = "model"
        authority["autonomy"]["mayAcceptIntent"] = True
        authority["autonomy"]["mayChangeScope"] = True
        errors = research_intent_revision_errors(authority)
        self.assertIn("intent-acceptance-is-human", errors)
        self.assertIn("autonomy-retains-researcher-authority", errors)

    def test_later_revision_retains_predecessor_identity_hash_and_rationale(self) -> None:
        revision = fixture("valid-systematic-intent.v1.json")
        revision["revision"] = 2
        revision["revisionId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a5"
        revision["revisionContentHash"] = "sha256:3333333333333333333333333333333333333333333333333333333333333333"
        revision["parentRevision"] = {
            "revisionId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a2",
            "revision": 1,
            "revisionContentHash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
        }
        revision["revisionRationale"] = "Refine the source boundary without rewriting revision one."
        self.assertEqual((), research_intent_revision_errors(revision))
        reference = governing_research_intent_reference(revision)
        assert reference is not None
        self.assertEqual(2, reference["revision"])

    def test_accepted_revision_must_be_complete_before_downstream_reference(self) -> None:
        incomplete = fixture("valid-systematic-intent.v1.json")
        incomplete["researchQuestion"] = {"state": "unknown", "rationale": "Not resolved."}
        incomplete["unresolvedDecisions"] = ["research-question"]
        self.assertIn("accepted-revision-is-decision-complete", research_intent_revision_errors(incomplete))
        self.assertIsNone(governing_research_intent_reference(incomplete))
        reference = fixture("valid-systematic-reference.v1.json")
        self.assertEqual((), research_intent_reference_errors(reference))
        reference["revision"] = 0
        self.assertIsNone(decode_research_intent_reference(reference))

    def test_incomplete_draft_is_valid_but_never_governing(self) -> None:
        draft = fixture("valid-systematic-intent.v1.json")
        draft["status"] = "draft"
        draft["decision"] = None
        draft["researchQuestion"] = {"state": "unknown", "rationale": "The researcher is refining it."}
        draft["sourceScope"] = {"state": "unknown", "rationale": "Source boundaries are not decided."}
        draft["noveltyStandard"] = {"state": "unknown", "rationale": "No novelty claim is ready."}
        draft["evidenceTypes"] = []
        draft["unresolvedDecisions"] = ["research-question", "source-scope", "novelty-standard"]
        self.assertEqual((), research_intent_revision_errors(draft))
        self.assertIsNone(governing_research_intent_reference(draft))

    def test_use_case_temporal_scope_and_egress_are_consistent(self) -> None:
        revision = fixture("valid-systematic-intent.v1.json")
        revision["primaryUseCase"] = "critical-problematization"
        revision["sourceScope"]["temporalCoverage"] = {"kind": "bounded", "startYear": 2026, "endYear": 2000}
        revision["egressPolicy"] = {"mode": "approved-redacted", "approvedDestinationIds": []}
        errors = research_intent_revision_errors(revision)
        self.assertIn("primary-use-case-matches-epistemic-mode", errors)
        self.assertIn("source-temporal-range-is-ordered", errors)
        self.assertIn("egress-policy-is-consistent", errors)

    def test_calendar_control_scope_and_predecessor_hash_substitutions_fail(self) -> None:
        timestamp = fixture("valid-systematic-intent.v1.json")
        timestamp["createdAt"] = "2026-02-31T12:00:00Z"
        self.assertIn("$/createdAt: format", research_intent_revision_errors(timestamp))
        control = fixture("valid-systematic-intent.v1.json")
        control["revisionRationale"] = "unsafe\x00text"
        self.assertIsNone(decode_research_intent_revision(control))
        undecided = fixture("valid-systematic-intent.v1.json")
        undecided["sourceScope"]["privateReports"] = "undecided"
        self.assertIn("accepted-revision-is-decision-complete", research_intent_revision_errors(undecided))
        reused = fixture("valid-systematic-intent.v1.json")
        reused["revision"] = 2
        reused["revisionId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a5"
        reused["parentRevision"] = {
            "revisionId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a2",
            "revision": 1,
            "revisionContentHash": reused["revisionContentHash"],
        }
        self.assertIn("revision-lineage-is-immediate", research_intent_revision_errors(reused))

    def test_input_is_owned_and_deeply_immutable(self) -> None:
        source = fixture("valid-systematic-intent.v1.json")
        decoded = decode_research_intent_revision(source)
        assert decoded is not None
        view = cast(Any, decoded)
        source["sourceScope"]["languages"].append("de")
        self.assertEqual(("en",), view["sourceScope"]["languages"])
        with self.assertRaises(TypeError):
            view["researchQuestion"]["value"] = "forbidden"
        with self.assertRaises(AttributeError):
            view["unresolvedDecisions"].append("bypass")


if __name__ == "__main__":
    unittest.main()
