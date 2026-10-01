"""The seven named corpus conditions retain their distinct meanings."""

from __future__ import annotations

import unittest

from pydantic import ValidationError
from research_observatory_core.corpus.membership import (
    CorpusDecision,
    CorpusItemRevision,
    CorpusProblem,
    Dimension,
    DiscoveryPath,
    append_discovery_path,
    apply_decision,
    rebind_work,
)

PROJECT = "02e2e404-5b49-438e-9b59-ed562626b658"
ITEM = "01a0f503-65f9-763e-af00-aacc9aca6494"
WORK = "01a0f503-663c-77d1-b0a7-445355a0d8ab"
WORK_REVISION = "01a0f503-6680-7ab3-a4ab-b29f2fe10c31"
FIRST_REVISION = "01a0f503-66b0-731c-8e38-3266c225a178"
SECOND_REVISION = "01a0f503-66b1-70aa-98cb-578709242ce8"
THIRD_REVISION = "01a0f503-66b2-7443-9caa-46f39ec00f23"
PATH = "01a0f503-66b3-7040-a811-bc2673c290b0"
SOURCE = "01a0f503-66b4-7d41-aa2c-37d912c84004"
PROTOCOL = "01a0f503-66b5-72f6-8d29-e2d56fecad94"
ACTOR = "01a0f503-66b6-781e-b85b-e74baa2dcf8e"
DECISION = "01a0f503-66b7-77ef-a2e1-179131d50cd8"
OTHER = "01a0f503-66b8-7c94-b890-31202a63db20"
SECOND_DECISION = "01a0f503-66b9-75b2-9e29-e435120b0fb6"
NEXT_WORK_REVISION = "01a0f503-66ba-7d58-867e-033918829f64"


def command_for(dimension: Dimension, previous_value: str, next_value: str) -> str:
    if dimension == "membership":
        return {
            "included": "include",
            "excluded": "exclude",
            "withdrawn": "withdraw",
            "candidate": "reconsider",
        }[next_value]
    if dimension == "review":
        return "queue-review" if next_value == "pending" else "resolve-review"
    if dimension == "availability":
        return "mark-" + next_value
    if dimension == "duplicate":
        return "clear-duplicate" if next_value == "none" else "mark-duplicate"
    return {"discovery": "add-discovery", "work-reference": "rebind-work"}[dimension]


def candidate() -> CorpusItemRevision:
    return CorpusItemRevision(
        project_id=PROJECT,
        item_id=ITEM,
        revision_id=FIRST_REVISION,
        previous_revision_id=None,
        work_id=WORK,
        work_revision_id=WORK_REVISION,
        membership="candidate",
        review="pending",
        duplicate_of_item_id=None,
        availability="unknown",
        discovery_path_ids=(PATH,),
        decision_revision_id=None,
    )


def decision(
    *,
    dimension: Dimension,
    previous_value: str,
    next_value: str,
    previous_revision_id: str = FIRST_REVISION,
    next_revision_id: str = SECOND_REVISION,
    decision_id: str = DECISION,
    previous_decision_revision_id: str | None = None,
    supersedes_decision_revision_id: str | None = None,
    next_work_id: str | None = None,
    evidence_revision_ids: tuple[str, ...] = (SOURCE,),
) -> CorpusDecision:
    return CorpusDecision(
        decision_id=decision_id,
        project_id=PROJECT,
        item_id=ITEM,
        previous_revision_id=previous_revision_id,
        next_revision_id=next_revision_id,
        dimension=dimension,
        command=command_for(dimension, previous_value, next_value),
        previous_value=previous_value,
        next_value=next_value,
        previous_decision_revision_id=previous_decision_revision_id,
        supersedes_decision_revision_id=supersedes_decision_revision_id,
        next_work_id=next_work_id,
        actor_id=ACTOR,
        reason_code="criterion-met",
        protocol_revision_id=PROTOCOL,
        evidence_revision_ids=evidence_revision_ids,
        occurred_at="2026-09-30T20:00:00.000Z",
    )


class CorpusMembershipModelTests(unittest.TestCase):
    def test_initial_candidate_cannot_skip_reasoned_review_or_availability_change(self) -> None:
        initial = candidate().model_dump()
        for changed in (
            {"review": "none"},
            {"duplicate_of_item_id": OTHER},
            {"availability": "available"},
            {"membership": "included"},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValidationError):
                CorpusItemRevision.model_validate(initial | changed)

    def test_independent_conditions_do_not_erase_inclusion(self) -> None:
        included = apply_decision(
            candidate(), decision(dimension="membership", previous_value="candidate", next_value="included")
        )
        unavailable = apply_decision(
            included,
            decision(
                dimension="availability",
                previous_value="unknown",
                next_value="unavailable",
                previous_revision_id=SECOND_REVISION,
                next_revision_id=THIRD_REVISION,
                decision_id=SECOND_DECISION,
                previous_decision_revision_id=DECISION,
            ),
        )
        self.assertEqual("included", unavailable.membership)
        self.assertEqual(("included", "pending", "unavailable"), unavailable.conditions)
        self.assertEqual(FIRST_REVISION, included.previous_revision_id)
        self.assertEqual(SECOND_REVISION, unavailable.previous_revision_id)

    def test_duplicate_is_a_relationship_not_a_membership_overwrite(self) -> None:
        duplicate = apply_decision(
            candidate(),
            decision(dimension="duplicate", previous_value="none", next_value=OTHER),
        )
        self.assertEqual("candidate", duplicate.membership)
        self.assertEqual(OTHER, duplicate.duplicate_of_item_id)
        self.assertEqual(("candidate", "pending", "duplicate"), duplicate.conditions)

    def test_v1_lifecycle_requires_reconsideration_and_preserves_withdrawal(self) -> None:
        included = apply_decision(
            candidate(), decision(dimension="membership", previous_value="candidate", next_value="included")
        )
        with self.assertRaisesRegex(CorpusProblem, "corpus-transition-invalid"):
            apply_decision(
                included,
                decision(
                    dimension="membership",
                    previous_value="included",
                    next_value="excluded",
                    previous_revision_id=SECOND_REVISION,
                    next_revision_id=THIRD_REVISION,
                    decision_id=SECOND_DECISION,
                    previous_decision_revision_id=DECISION,
                ),
            )
        withdrawn = apply_decision(
            candidate(), decision(dimension="membership", previous_value="candidate", next_value="withdrawn")
        )
        with self.assertRaisesRegex(CorpusProblem, "corpus-withdrawn-terminal"):
            apply_decision(
                withdrawn,
                decision(
                    dimension="review",
                    previous_value="pending",
                    next_value="none",
                    previous_revision_id=SECOND_REVISION,
                    next_revision_id=THIRD_REVISION,
                    decision_id=SECOND_DECISION,
                    previous_decision_revision_id=DECISION,
                ),
            )

    def test_stale_or_forged_prior_value_is_denied(self) -> None:
        with self.assertRaisesRegex(CorpusProblem, "corpus-predecessor-stale"):
            apply_decision(
                candidate(),
                decision(
                    dimension="membership",
                    previous_value="candidate",
                    next_value="included",
                    previous_revision_id=OTHER,
                ),
            )
        with self.assertRaisesRegex(CorpusProblem, "corpus-prior-value-mismatch"):
            apply_decision(
                candidate(), decision(dimension="membership", previous_value="excluded", next_value="included")
            )

    def test_discovery_path_requires_exact_source_and_decision_authority_is_bounded(self) -> None:
        path = DiscoveryPath(
            path_id=PATH,
            project_id=PROJECT,
            item_id=ITEM,
            kind="import-member",
            source_revision_id=SOURCE,
            direction="source-to-corpus-item",
            occurred_at="2026-09-30T20:00:00.000Z",
            predecessor_item_revision_id=None,
            context_id=OTHER,
            context_revision_id=PROTOCOL,
            ordinal=1,
            record_key_sha256="a" * 64,
        )
        self.assertEqual("import-member", path.kind)
        self.assertIsNone(path.predecessor_item_revision_id)
        with self.assertRaises(ValidationError):
            DiscoveryPath.model_validate({key: value for key, value in path.model_dump().items() if key != "direction"})
        with self.assertRaises(ValidationError):
            DiscoveryPath.model_validate(path.model_dump() | {"direction": "corpus-item-to-source"})
        with self.assertRaises(ValidationError):
            DiscoveryPath.model_validate(path.model_dump() | {"occurred_at": "2026-02-30T20:00:00.000Z"})
        with self.assertRaises(ValidationError):
            DiscoveryPath.model_validate(path.model_dump() | {"predecessor_item_revision_id": ITEM})
        with self.assertRaises(ValidationError):
            DiscoveryPath.model_validate(path.model_dump() | {"ordinal": 0})
        with self.assertRaises(ValidationError):
            CorpusDecision.model_validate(
                decision(dimension="membership", previous_value="candidate", next_value="included").model_dump()
                | {"reason_code": ""}
            )
        with self.assertRaises(ValidationError):
            CorpusDecision.model_validate(
                decision(dimension="membership", previous_value="candidate", next_value="included").model_dump()
                | {"occurred_at": "2026-99-99T99:99:99.999Z"}
            )
        with self.assertRaises(ValidationError):
            DiscoveryPath.model_validate(path.model_dump() | {"kind": "connector-record", "record_key_sha256": None})
        connector = DiscoveryPath.model_validate(
            path.model_dump()
            | {"kind": "connector-record", "ordinal": 0, "record_key_sha256": None, "query_revision_id": OTHER}
        )
        self.assertEqual(OTHER, connector.query_revision_id)
        citation = DiscoveryPath.model_validate(
            path.model_dump()
            | {"kind": "citation", "ordinal": None, "record_key_sha256": None, "citing_work_revision_id": OTHER}
        )
        self.assertEqual(OTHER, citation.citing_work_revision_id)

    def test_later_discovery_edge_requires_exact_prior_set_and_source_evidence(self) -> None:
        current = candidate()
        path = DiscoveryPath(
            path_id=OTHER,
            project_id=PROJECT,
            item_id=ITEM,
            kind="citation",
            source_revision_id=SOURCE,
            direction="source-to-corpus-item",
            occurred_at="2026-09-30T20:00:00.000Z",
            predecessor_item_revision_id=current.revision_id,
            context_id=WORK,
            context_revision_id=WORK_REVISION,
            citing_work_revision_id=WORK_REVISION,
        )
        add = decision(
            dimension="discovery",
            previous_value=current.discovery_fingerprint,
            next_value=path.path_id,
        )
        updated = append_discovery_path(current, path, add)
        self.assertEqual(tuple(sorted((PATH, OTHER))), updated.discovery_path_ids)
        with self.assertRaisesRegex(CorpusProblem, "corpus-discovery-item-predecessor-stale"):
            append_discovery_path(current, path.model_copy(update={"predecessor_item_revision_id": None}), add)
        with self.assertRaisesRegex(CorpusProblem, "corpus-discovery-time-mismatch"):
            append_discovery_path(current, path.model_copy(update={"occurred_at": "2026-09-30T20:00:01.000Z"}), add)
        with self.assertRaisesRegex(CorpusProblem, "corpus-predecessor-stale"):
            append_discovery_path(updated, path, add)
        with self.assertRaisesRegex(CorpusProblem, "corpus-discovery-scope-mismatch"):
            append_discovery_path(
                current, path.model_copy(update={"project_id": "02e2e404-5b49-438e-9b59-ed562626b659"}), add
            )

    def test_work_rebind_requires_explicit_prior_revision_and_evidence(self) -> None:
        current = candidate()
        change = decision(
            dimension="work-reference",
            previous_value=WORK_REVISION,
            next_value=NEXT_WORK_REVISION,
            next_work_id=OTHER,
            evidence_revision_ids=(NEXT_WORK_REVISION,),
        )
        rebound = rebind_work(current, change)
        self.assertEqual((OTHER, NEXT_WORK_REVISION), (rebound.work_id, rebound.work_revision_id))
        with self.assertRaisesRegex(CorpusProblem, "corpus-predecessor-stale"):
            rebind_work(rebound, change)
        with self.assertRaises(ValidationError):
            CorpusDecision.model_validate(change.model_dump() | {"dimension": "membership"})


if __name__ == "__main__":
    unittest.main()
