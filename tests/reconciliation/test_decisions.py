"""Complete human partitions, exact predecessors, and aliases retain identity."""

import unittest

from pydantic import ValidationError
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.reconciliation.decisions import (
    AliasPlan,
    ReviewPlan,
    SourcePartition,
    WorkState,
)


def work(*assertions):
    return WorkState(
        work_id=new_uuid_v7(),
        revision_id=new_uuid_v7(),
        previous_revision_id=None,
        disposition="active",
        alias_target=None,
        assertion_revision_ids=tuple(sorted(assertions)),
        decision_revision_id=None,
    )


class ReviewPlanTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.c = new_uuid_v7(), new_uuid_v7(), new_uuid_v7()
        self.first, self.second = work(self.a), work(self.b)

    def merge(self):
        return ReviewPlan(
            action="merge",
            works=(self.first, self.second),
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(
                    group="retained",
                    existing_work_id=self.first.work_id,
                    assertion_revision_ids=tuple(sorted((self.a, self.b))),
                ),
            ),
            aliases=(
                AliasPlan(work_id=self.second.work_id, revision_id=self.second.revision_id, target_group="retained"),
            ),
            conflict_disposition="retain-all",
            evidence_sha256="1" * 64,
            rationale="Synthetic researcher merge decision",
        )

    def test_merge_binds_complete_partition_survivor_alias_and_predecessors(self):
        plan = self.merge()
        self.assertEqual(plan, ReviewPlan.model_validate_json(plan.model_dump_json(by_alias=True)))
        document = plan.model_dump()
        document["works"] = (self.first.model_copy(update={"revision_id": new_uuid_v7()}), self.second)
        self.assertNotEqual(plan.fingerprint, ReviewPlan.model_validate(document).fingerprint)
        self.assertEqual("retain-all", plan.conflict_disposition)

    def test_missing_or_substituted_member_cannot_disappear_during_merge(self):
        for members in ((self.a,), (self.a, self.c), (self.a, self.a, self.b)):
            with self.subTest(members=members), self.assertRaises(ValidationError):
                document = self.merge().model_dump()
                document["partitions"] = [
                    dict(
                        group="retained",
                        existing_work_id=self.first.work_id,
                        assertion_revision_ids=tuple(sorted(members)),
                    )
                ]
                ReviewPlan.model_validate(document)

    def test_alias_is_mandatory_and_cannot_point_to_itself_or_unknown_partition(self):
        plan = self.merge().model_dump()
        for aliases in (
            (),
            (dict(work_id=self.first.work_id, revision_id=self.first.revision_id, target_group="retained"),),
            (dict(work_id=self.second.work_id, revision_id=self.second.revision_id, target_group="missing"),),
        ):
            with self.subTest(aliases=aliases), self.assertRaises(ValidationError):
                ReviewPlan.model_validate({**plan, "aliases": aliases})

    def test_split_restores_complete_nonoverlapping_sources_and_new_identity_request(self):
        original = work(self.a, self.b)
        plan = ReviewPlan(
            action="split",
            works=(original,),
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(group="retained", existing_work_id=original.work_id, assertion_revision_ids=(self.a,)),
                SourcePartition(group="separated", existing_work_id=None, assertion_revision_ids=(self.b,)),
            ),
            aliases=(),
            conflict_disposition="retain-all",
            evidence_sha256="2" * 64,
            rationale="Synthetic reversal retaining original history",
        )
        self.assertIsNone(plan.partitions[1].existing_work_id)
        values = plan.model_dump()
        values["partitions"][1]["assertion_revision_ids"] = (self.a, self.b)
        with self.assertRaises(ValidationError):
            ReviewPlan.model_validate(values)

    def test_unassigned_disputed_assertion_needs_explicit_human_partition(self):
        plan = ReviewPlan(
            action="assign",
            works=(),
            unassigned_assertion_revision_ids=(self.c,),
            partitions=(SourcePartition(group="assigned", existing_work_id=None, assertion_revision_ids=(self.c,)),),
            aliases=(),
            conflict_disposition="retain-all",
            evidence_sha256="3" * 64,
            rationale="Synthetic explicit identity decision",
        )
        self.assertEqual((self.c,), plan.unassigned_assertion_revision_ids)
        with self.assertRaises(ValidationError):
            ReviewPlan.model_validate({**plan.model_dump(), "unassigned_assertion_revision_ids": ()})

    def test_alias_state_has_no_current_members_and_preserves_prior_identity(self):
        state = WorkState(
            work_id=self.first.work_id,
            revision_id=new_uuid_v7(),
            previous_revision_id=self.first.revision_id,
            disposition="alias",
            alias_target=self.second.work_id,
            assertion_revision_ids=(),
            decision_revision_id=new_uuid_v7(),
        )
        with self.assertRaises(ValidationError):
            WorkState.model_validate({**state.model_dump(), "assertion_revision_ids": (self.a,)})
        with self.assertRaises(ValidationError):
            WorkState.model_validate({**state.model_dump(), "alias_target": state.work_id})


if __name__ == "__main__":
    unittest.main()
