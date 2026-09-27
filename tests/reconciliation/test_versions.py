"""Portable version facts retain date precision, evidence and exact identities."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.reconciliation.versions import (
    UpdateRelationDraft,
    VersionCommand,
    VersionContext,
    VersionDate,
    VersionDefinition,
    VersionEvidence,
    VersionOutcome,
    VersionPlacement,
    VersionPlan,
    VersionPreference,
    VersionReference,
    WorkVersion,
    version_digest,
)


class VersionContractTests(unittest.TestCase):
    def test_portable_synthetic_history_preserves_warned_preference_and_exact_endpoints(self):
        root = Path(__file__).resolve().parents[2]
        fixture = json.loads((root / "tests/fixtures/scholarly-metadata/work-versions.v1.json").read_text())
        self.assertEqual("synthetic-version-history", fixture["fixtureKind"])
        for key, model in (("context", VersionContext), ("command", VersionCommand), ("outcome", VersionOutcome)):
            schema = json.loads((root / f"packages/contracts/scholarly-records/version-{key}.schema.json").read_text())
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            validator.validate(fixture[key])
            self.assertFalse(validator.is_valid(fixture[key] | {"rightsOverride": True}))
            document = dict(fixture[key])
            if key == "context":
                fingerprint = document.pop("contextSha256")
                self.assertEqual(fingerprint, version_digest(document))
            model.model_validate_json(json.dumps(document))
        context = fixture["context"]
        self.assertEqual("retracts", context["relations"][0]["assertion"]["kind"])
        preference = context["preferences"][0]
        standing = next(item for item in context["preferenceStates"] if item["workId"] == preference["workId"])
        self.assertEqual("requires-review", standing["state"])
        self.assertEqual(preference["selected"], context["relations"][0]["assertion"]["target"])

    def test_decoded_wire_arrays_round_trip_without_scalar_coercion(self):
        definition = VersionDefinition(
            kind="preprint", assertion_revision_ids=(new_uuid_v7(),), date=VersionDate(precision="unknown", value=None)
        )
        payload = definition.model_dump(mode="json", by_alias=True)
        self.assertEqual(definition, VersionDefinition.model_validate(payload))
        with self.assertRaises(ValidationError):
            VersionDefinition.model_validate({**payload, "assertionRevisionIds": [7]})

    def test_response_identity_and_placement_invariants_reject_impossible_history(self):
        identity, revision, decision = new_uuid_v7(), new_uuid_v7(), new_uuid_v7()
        definition = VersionDefinition(
            kind="preprint", assertion_revision_ids=(new_uuid_v7(),), date=VersionDate(precision="unknown", value=None)
        )
        with self.assertRaises(ValidationError):
            WorkVersion(
                version_id=identity,
                revision_id=revision,
                previous_revision_id=revision,
                definition=definition,
                decision_revision_id=decision,
                status_sha256="a" * 64,
            )
        with self.assertRaises(ValidationError):
            VersionPreference(
                decision_id=identity,
                revision_id=identity,
                previous_revision_id=identity,
                work_id=new_uuid_v7(),
                work_revision_id=new_uuid_v7(),
                command_decision_revision_id=new_uuid_v7(),
                selected=VersionReference(version_id=new_uuid_v7(), revision_id=new_uuid_v7()),
                membership_sha256="a" * 64,
                status_sha256="b" * 64,
            )
        for ids, state in (((new_uuid_v7(), new_uuid_v7()), "assigned"), ((new_uuid_v7(),), "requires-review")):
            with self.assertRaises(ValidationError):
                VersionPlacement.model_validate(dict(version_id=identity, work_ids=tuple(sorted(ids)), state=state))

    def test_dates_preserve_reported_precision_and_distinguish_missingness(self):
        for precision, value in (
            ("year", "2024"),
            ("month", "2024-02"),
            ("day", "2024-02-29"),
            ("unknown", None),
            ("not-reported", None),
        ):
            with self.subTest(precision=precision):
                date = VersionDate.model_validate(dict(precision=precision, value=value))
                self.assertEqual(value, date.value)
                self.assertEqual(date, VersionDate.model_validate_json(date.model_dump_json(by_alias=True)))
        for precision, value in (
            ("year", "0000"),
            ("year", "2024-01-01"),
            ("month", "2024-13"),
            ("day", "2023-02-29"),
            ("day", "2024-2-1"),
            ("unknown", "2024"),
            ("not-reported", "2024"),
            ("day", None),
        ):
            with self.subTest(precision=precision, value=value), self.assertRaises(ValidationError):
                VersionDate.model_validate(dict(precision=precision, value=value))

    def test_manifestations_use_exact_unique_sorted_assertion_revisions(self):
        identities = tuple(sorted((new_uuid_v7(), new_uuid_v7())))
        for kind in (
            "preprint",
            "accepted-manuscript",
            "version-of-record",
            "erratum",
            "correction",
            "expression-of-concern",
            "retraction",
            "not-reported",
        ):
            value = VersionDefinition(
                kind=kind, assertion_revision_ids=identities, date=VersionDate(precision="not-reported", value=None)
            )
            self.assertEqual(identities, value.assertion_revision_ids)
        for invalid in ((), identities[::-1], (identities[0], identities[0])):
            with self.assertRaises(ValidationError):
                VersionDefinition(
                    kind="preprint", assertion_revision_ids=invalid, date=VersionDate(precision="unknown", value=None)
                )

    def test_relationships_require_distinct_exact_endpoints_and_sourced_human_status(self):
        source = VersionReference(version_id=new_uuid_v7(), revision_id=new_uuid_v7())
        target = VersionReference(version_id=new_uuid_v7(), revision_id=new_uuid_v7())
        evidence = VersionEvidence(
            assertion_revision_id=new_uuid_v7(), category="field", selector="decision.fields.0", value_sha256="a" * 64
        )
        draft = UpdateRelationDraft(
            kind="retracts",
            source=source,
            target=target,
            evidence=(evidence,),
            date=VersionDate(precision="year", value="2024"),
            knowledge_status="adjudicated",
        )
        self.assertEqual(draft, UpdateRelationDraft.model_validate_json(draft.model_dump_json(by_alias=True)))
        for change in (
            {"target": source},
            {"target": target.model_copy(update={"version_id": source.version_id})},
            {"evidence": ()},
            {"evidence": (evidence, evidence)},
            {"knowledge_status": "observed"},
        ):
            with self.subTest(change=tuple(change)), self.assertRaises(ValidationError):
                UpdateRelationDraft.model_validate(draft.model_copy(update=change))

    def test_action_shapes_cannot_smuggle_unrelated_authority(self):
        reference = VersionReference(version_id=new_uuid_v7(), revision_id=new_uuid_v7())
        plan = VersionPlan(
            action="prefer",
            work_ids=(new_uuid_v7(),),
            context_sha256="b" * 64,
            rationale="Synthetic explicit citable preference",
            version=reference,
            previous_preference_revision_id=None,
        )
        self.assertEqual(plan, VersionPlan.model_validate_json(plan.model_dump_json(by_alias=True)))
        for change in (
            {"action": "register"},
            {"version": None},
            {"work_ids": tuple(sorted((new_uuid_v7(), new_uuid_v7())))},
        ):
            with self.subTest(change=tuple(change)), self.assertRaises(ValidationError):
                VersionPlan.model_validate(plan.model_copy(update=change))
        with self.assertRaises(ValidationError):
            VersionPlan.model_validate({**plan.model_dump(), "rights_override": True})
