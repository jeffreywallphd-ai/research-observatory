"""Action-specific rights decisions preserve source and copy boundaries."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from research_observatory_core.connectors.contracts import SourceTerms
from research_observatory_core.reconciliation.contracts import SourceAddress
from research_observatory_core.rights_policy import (
    RightsDecision,
    RightsPermission,
    RightsPolicyRevision,
    RightsRequest,
    RightsSourceObservation,
    RightsSubject,
    RightsUse,
    evaluate_rights,
)

PROJECT = "02e2e404-5b49-438e-9b59-ed562626b658"
OTHER_PROJECT = "02e2e404-5b49-438e-9b59-ed562626b659"
ASSERTION = "01a0f503-66b4-7d41-aa2c-37d912c84004"
OTHER_ASSERTION = "01a0f503-66b5-72f6-8d29-e2d56fecad94"
COPY = "01a0f503-66b6-711c-8e38-3266c225a178"
OTHER_COPY = "01a0f503-66b7-77ef-a2e1-179131d50cd8"
POLICY = "01a0f503-66b8-7c94-b890-31202a63db20"
ACTOR = "01a0f503-66b9-75b2-9e29-e435120b0fb6"
EVIDENCE = "01a0f503-66ba-7d58-867e-033918829f64"
PERMISSION = "01a0f503-66bb-7d58-867e-033918829f64"
OTHER_PERMISSION = "01a0f503-66bc-7d58-867e-033918829f64"
NOW = datetime(2026, 9, 30, 20, 0, 0, tzinfo=UTC)


def address(*, ordinal: int = 0) -> SourceAddress:
    # Sibling records share a connector page revision; ordinal is record-specific.
    return SourceAddress(
        kind="connector-record",
        context_id="01a0f503-66bd-7d58-867e-033918829f64",
        revision_id="01a0f503-66be-7d58-867e-033918829f64",
        ordinal=ordinal,
        record_key=None,
    )


def subject(**changes: object) -> RightsSubject:
    values: dict[str, object] = {
        "project_id": PROJECT,
        "source_assertion_revision_id": ASSERTION,
        "address": address(),
        "copy_id": COPY,
        "copy_location": "local-project-object",
        "resource_class": "metadata",
    }
    values.update(changes)
    return RightsSubject.model_validate(values)


def use(action: str = "inspect", **changes: object) -> RightsUse:
    values: dict[str, object] = {
        "action": action,
        "purpose": "scholarly-screening",
        "destination_kind": "local-project",
        "provider": None,
        "region": None,
        "share_group": None,
    }
    values.update(changes)
    return RightsUse.model_validate(values)


def permission(
    action: str = "inspect",
    *,
    permission_id: str = PERMISSION,
    value: str = "permitted",
    basis: str = "researcher-confirmed",
    selected_subject: RightsSubject | None = None,
    selected_use: RightsUse | None = None,
    expires_at: str | None = "2026-10-01T20:00:00.000Z",
    confirmation_required: bool = False,
    grantee_actor_id: str | None = None,
) -> RightsPermission:
    return RightsPermission.model_validate(
        {
            "assertion_id": permission_id,
            "subject": selected_subject or subject(),
            "use": selected_use or use(action),
            "value": value,
            "basis": basis,
            "asserted_by_actor_id": ACTOR if basis != "source-observation" else None,
            "grantee_actor_id": grantee_actor_id,
            "evidence_revision_ids": (EVIDENCE,),
            "entitlement_revision_id": EVIDENCE if basis == "verified-entitlement" else None,
            "license_observation_revision_id": None,
            "confidence": "confirmed"
            if basis == "researcher-confirmed"
            else ("verified" if basis == "verified-entitlement" else "reported"),
            "recorded_at": "2026-09-30T19:00:00.000Z",
            "expires_at": expires_at,
            "confirmation_required": confirmation_required,
        }
    )


def policy(*permissions: RightsPermission, selected_subject: RightsSubject | None = None) -> RightsPolicyRevision:
    return RightsPolicyRevision(
        revision_id=POLICY,
        predecessor_revision_id=None,
        subject=selected_subject or subject(),
        permissions=permissions,
    )


def source_observation(**changes: object) -> RightsSourceObservation:
    values: dict[str, object] = {
        "project_id": PROJECT,
        "source_assertion_revision_id": ASSERTION,
        "address": address(),
        "source_revision_id": address().revision_id,
        "source_sha256": "a" * 64,
        "provider": "openalex",
        "terms": SourceTerms.model_validate(
            {
                "license": {"state": "reported", "value": "CC BY 4.0"},
                "terms": {"state": "not-reported", "value": None},
                "access": "open",
            }
        ),
        "retrieved_at": "2026-09-30T18:00:00.000Z",
    }
    values.update(changes)
    return RightsSourceObservation.model_validate(values)


def decide(
    current_policy: RightsPolicyRevision | None,
    *,
    selected_subject: RightsSubject | None = None,
    selected_use: RightsUse | None = None,
    now: datetime = NOW,
):
    return evaluate_rights(
        current_policy,
        RightsRequest(actor_id=ACTOR, subject=selected_subject or subject(), use=selected_use or use()),
        now=now,
    )


class RightsPolicyTests(unittest.TestCase):
    def test_reported_license_and_open_access_observation_never_grant_use(self) -> None:
        current = RightsPolicyRevision(
            revision_id=POLICY,
            predecessor_revision_id=None,
            subject=subject(),
            source_observation=source_observation(),
            permissions=(),
        )
        self.assertEqual("unknown", decide(current).code)
        assert current.source_observation is not None
        self.assertEqual("CC BY 4.0", current.source_observation.terms.license.value)
        self.assertEqual("open", current.source_observation.terms.access)

    def test_import_without_typed_license_remains_explicitly_unknown(self) -> None:
        import_address = SourceAddress(
            kind="import-member",
            context_id=address().context_id,
            revision_id=address().revision_id,
            ordinal=1,
            record_key="b" * 64,
        )
        import_subject = subject(address=import_address)
        observed = source_observation(
            address=import_address,
            source_revision_id=OTHER_ASSERTION,
            provider="local-import",
            terms=SourceTerms.model_validate(
                {
                    "license": {"state": "not-reported", "value": None},
                    "terms": {"state": "not-reported", "value": None},
                    "access": "unknown",
                }
            ),
            retrieved_at=None,
        )
        current = RightsPolicyRevision(
            revision_id=POLICY,
            predecessor_revision_id=None,
            subject=import_subject,
            source_observation=observed,
            permissions=(),
        )
        assert current.source_observation is not None
        self.assertEqual("not-reported", current.source_observation.terms.license.state)
        self.assertEqual("unknown", decide(current, selected_subject=import_subject).code)

    def test_source_observation_binds_exact_record_and_rejects_bad_terms(self) -> None:
        current = policy(permission())
        for changes in (
            {"project_id": OTHER_PROJECT},
            {"source_assertion_revision_id": OTHER_ASSERTION},
            {"address": address(ordinal=1)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                RightsPolicyRevision.model_validate(
                    current.model_dump() | {"source_observation": source_observation(**changes)}
                )
        with self.assertRaises(ValidationError):
            source_observation(source_revision_id=OTHER_ASSERTION)
        with self.assertRaises(ValidationError):
            source_observation(retrieved_at="2026-02-30T18:00:00.000Z")
        with self.assertRaises(ValidationError):
            source_observation(
                terms={
                    "license": {"state": "reported", "value": None},
                    "terms": {"state": "not-reported", "value": None},
                    "access": "open",
                }
            )

    def test_all_eight_actions_require_independent_grants(self) -> None:
        actions = ("store", "inspect", "index", "derive", "model-use", "quote", "export", "share")
        uses = {
            "model-use": use(
                "model-use", destination_kind="remote-model", provider="model-provider", region="us-east-1"
            ),
            "export": use("export", destination_kind="local-export"),
            "share": use("share", destination_kind="collaboration", share_group="research-team"),
        }
        for action in actions:
            with self.subTest(action=action):
                action_use = uses[action] if action in uses else use(action)
                grant = permission(action, selected_use=action_use)
                matching = decide(policy(grant), selected_use=action_use)
                self.assertEqual("allow", matching.code)
                self.assertEqual("policy", matching.authority_kind)
                self.assertIsNone(matching.source_assertion_sha256)
                self.assertEqual((PERMISSION,), matching.governing_assertion_ids)
                self.assertEqual(POLICY, matching.policy_revision_id)
                for other_action in actions:
                    if other_action == action:
                        continue
                    other_use = uses[other_action] if other_action in uses else use(other_action)
                    self.assertNotEqual("allow", decide(policy(grant), selected_use=other_use).code)

    def test_missing_policy_and_unknown_permission_restrict_use(self) -> None:
        absent = decide(None)
        self.assertEqual("unknown", absent.code)
        self.assertEqual("none", absent.authority_kind)
        self.assertEqual("unknown", decide(policy(permission(value="unknown"))).code)

    def test_legacy_import_bridge_allow_requires_one_exact_bounded_witness(self) -> None:
        import_address = SourceAddress(
            kind="import-member",
            context_id=address().context_id,
            revision_id=address().revision_id,
            ordinal=1,
            record_key="b" * 64,
        )
        import_subject = subject(
            address=import_address,
            copy_id=ASSERTION,
            copy_location="local-source",
        )
        bridge = RightsDecision(
            code="allow",
            reason_code="rights-legacy-import-confirmed",
            authority_kind="legacy-import-bridge",
            actor_id=ACTOR,
            subject=import_subject,
            use=use("store", purpose="corpus-membership"),
            policy_revision_id=None,
            governing_assertion_ids=(ASSERTION,),
            source_assertion_sha256="a" * 64,
            evaluated_at="2026-09-30T20:00:00.000Z",
            expires_at=None,
        )
        self.assertEqual("allow", bridge.code)
        self.assertEqual("legacy-import-bridge", bridge.authority_kind)
        self.assertEqual("a" * 64, bridge.source_assertion_sha256)
        for action in ("store", "inspect", "derive", "index"):
            with self.subTest(action=action):
                self.assertEqual(
                    "allow",
                    RightsDecision.model_validate(
                        bridge.model_dump() | {"use": use(action, purpose="corpus-membership")}
                    ).code,
                )
        for change in (
            {"authority_kind": "none"},
            {"authority_kind": "policy"},
            {"source_assertion_sha256": None},
            {"source_assertion_sha256": "A" * 64},
            {"governing_assertion_ids": (PERMISSION,)},
            {"governing_assertion_ids": (ASSERTION, PERMISSION)},
            {"policy_revision_id": POLICY},
            {"reason_code": "rights-explicit-permission"},
            {"subject": import_subject.model_copy(update={"resource_class": "full-text"})},
            {"subject": import_subject.model_copy(update={"copy_location": "provider-hosted"})},
            {"subject": import_subject.model_copy(update={"copy_id": OTHER_COPY})},
            {"subject": import_subject.model_copy(update={"address": address()})},
            {"use": use("quote", purpose="corpus-membership")},
            {"use": use("store", purpose="manuscript-drafting")},
            {"use": use("export", purpose="corpus-membership", destination_kind="local-export")},
        ):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                RightsDecision.model_validate(bridge.model_dump() | change)

    def test_policy_or_unknown_decision_may_carry_protected_source_hash(self) -> None:
        for decision in (decide(None), decide(policy(permission()))):
            with self.subTest(code=decision.code):
                enriched = RightsDecision.model_validate(decision.model_dump() | {"source_assertion_sha256": "a" * 64})
                self.assertEqual("a" * 64, enriched.source_assertion_sha256)

    def test_source_observation_is_not_an_entitlement(self) -> None:
        observed = permission(basis="source-observation")
        self.assertEqual("unknown", decide(policy(observed)).code)
        disputed = RightsPermission.model_validate(
            observed.model_dump() | {"assertion_id": OTHER_PERMISSION, "confidence": "disputed"}
        )
        self.assertEqual("require-confirmation", decide(policy(permission(), disputed)).code)

    def test_exact_record_assertion_and_address_prevent_sibling_page_substitution(self) -> None:
        granted = policy(permission())
        self.assertEqual("unknown", decide(granted, selected_subject=subject(address=address(ordinal=1))).code)
        self.assertEqual(
            "unknown", decide(granted, selected_subject=subject(source_assertion_revision_id=OTHER_ASSERTION)).code
        )

    def test_project_copy_resource_and_purpose_are_exact(self) -> None:
        granted = policy(permission())
        for altered in (
            subject(project_id=OTHER_PROJECT),
            subject(copy_id=OTHER_COPY),
            subject(resource_class="full-text"),
        ):
            with self.subTest(altered=altered):
                self.assertEqual("unknown", decide(granted, selected_subject=altered).code)
        self.assertEqual("unknown", decide(granted, selected_use=use(purpose="manuscript-drafting")).code)
        other_subject = subject(project_id=OTHER_PROJECT)
        self.assertEqual(
            "unknown", decide(policy(permission(selected_subject=other_subject), selected_subject=other_subject)).code
        )
        self.assertEqual("unknown", decide(granted, selected_subject=subject(copy_location="provider-hosted")).code)

    def test_local_model_permission_cannot_grant_remote_egress(self) -> None:
        local_use = use("model-use")
        remote_use = use("model-use", destination_kind="remote-model", provider="model-provider", region="us-east-1")
        granted = policy(permission("model-use", selected_use=local_use))
        self.assertEqual("allow", decide(granted, selected_use=local_use).code)
        self.assertEqual("unknown", decide(granted, selected_use=remote_use).code)

    def test_remote_destination_provider_region_and_share_group_are_exact(self) -> None:
        remote = use("model-use", destination_kind="remote-model", provider="model-provider", region="us-east-1")
        granted = policy(permission("model-use", selected_use=remote))
        self.assertEqual(
            "unknown", decide(granted, selected_use=remote.model_copy(update={"provider": "another-provider"})).code
        )
        self.assertEqual(
            "unknown", decide(granted, selected_use=remote.model_copy(update={"region": "eu-west-1"})).code
        )
        share = use("share", destination_kind="collaboration", share_group="research-team")
        self.assertEqual(
            "unknown",
            decide(
                policy(permission("share", selected_use=share)),
                selected_use=share.model_copy(update={"share_group": "others"}),
            ).code,
        )

    def test_principal_specific_entitlement_does_not_transfer_to_another_actor(self) -> None:
        entitlement = permission(basis="verified-entitlement", grantee_actor_id=ACTOR)
        current = policy(entitlement)
        self.assertEqual("allow", decide(current).code)
        another = RightsRequest(
            actor_id=OTHER_ASSERTION,
            subject=subject(),
            use=use(),
        )
        self.assertEqual("unknown", evaluate_rights(current, another, now=NOW).code)

    def test_policy_revision_is_versioned_and_one_exact_subject(self) -> None:
        with self.assertRaises(ValidationError):
            RightsPolicyRevision.model_validate(policy(permission()).model_dump() | {"contract_version": "2.0.0"})
        with self.assertRaises(ValidationError):
            policy(permission(selected_subject=subject(copy_id=OTHER_COPY)))
        with self.assertRaises(ValidationError):
            RightsPolicyRevision.model_validate(policy(permission()).model_dump() | {"predecessor_revision_id": POLICY})

    def test_denial_conflict_and_confirmation_are_non_allow(self) -> None:
        denied = permission(value="denied")
        self.assertEqual("deny", decide(policy(denied)).code)
        conflict = policy(permission(), permission(permission_id=OTHER_PERMISSION, value="denied"))
        decision = decide(conflict)
        self.assertEqual("deny", decision.code)
        self.assertEqual((PERMISSION, OTHER_PERMISSION), decision.governing_assertion_ids)
        review = policy(permission(confirmation_required=True))
        self.assertEqual("require-confirmation", decide(review).code)

    def test_expiry_at_trusted_instant_and_invalid_chronology(self) -> None:
        at_expiry = permission(expires_at="2026-09-30T20:00:00.000Z")
        self.assertEqual("deny", decide(policy(at_expiry)).code)
        before_expiry = NOW.replace(second=0, microsecond=0)
        self.assertEqual("allow", decide(policy(at_expiry), now=before_expiry.replace(minute=59, hour=19)).code)
        with self.assertRaises(ValidationError):
            RightsPermission.model_validate(permission().model_dump() | {"expires_at": "2026-09-30T18:00:00.000Z"})

    def test_schema_rejects_malformed_and_contradictory_values(self) -> None:
        for altered in (
            {"action": "acquire"},
            {"action": "model-use", "destination_kind": "remote-model"},
            {
                "action": "inspect",
                "destination_kind": "remote-model",
                "provider": "model-provider",
                "region": "us-east-1",
            },
            {"destination_kind": "local-project", "provider": "model-provider"},
        ):
            with self.subTest(altered=altered), self.assertRaises(ValidationError):
                RightsUse.model_validate(use().model_dump() | altered)
        with self.assertRaises(ValidationError):
            policy(permission(), permission(value="denied"))
        with self.assertRaises(ValidationError):
            RightsSubject.model_validate(subject().model_dump() | {"copy_id": "C:/private/file.pdf"})
        with self.assertRaises(ValidationError):
            RightsPermission.model_validate(
                permission().model_dump()
                | {"value": "permitted", "basis": "source-observation", "asserted_by_actor_id": ACTOR}
            )

    def test_untrusted_request_cannot_claim_current_policy_or_time(self) -> None:
        with self.assertRaises(ValidationError):
            RightsRequest.model_validate(
                {
                    "actor_id": ACTOR,
                    "subject": subject(),
                    "use": use(),
                    "policy_revision_id": POLICY,
                    "evaluated_at": "2099-01-01T00:00:00.000Z",
                }
            )
        with self.assertRaises(ValueError):
            decide(policy(permission()), now=NOW.replace(tzinfo=None))

    def test_versioned_portable_fixtures_match_python_values(self) -> None:
        fixture_root = Path(__file__).resolve().parents[2] / "packages" / "contracts" / "rights" / "fixtures"
        current_policy = policy(permission())
        policy_bytes = (fixture_root / "valid-policy.v1.json").read_text(encoding="utf-8")
        decision_bytes = (fixture_root / "valid-decision.v1.json").read_text(encoding="utf-8")
        stored_decision = json.loads(decision_bytes)
        self.assertEqual(current_policy, RightsPolicyRevision.model_validate_json(policy_bytes))
        self.assertEqual(decide(current_policy), RightsDecision.model_validate_json(decision_bytes))
        for forged in (
            stored_decision | {"policyRevisionId": None},
            stored_decision | {"authorityKind": "none"},
            stored_decision | {"authorityKind": "legacy-import-bridge"},
            stored_decision | {"governingAssertionIds": []},
            stored_decision | {"expiresAt": stored_decision["evaluatedAt"]},
        ):
            with self.subTest(forged=forged), self.assertRaises(ValidationError):
                RightsDecision.model_validate_json(json.dumps(forged))


if __name__ == "__main__":
    unittest.main()
