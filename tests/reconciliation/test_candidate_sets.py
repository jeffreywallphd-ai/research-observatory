"""Persisted candidate explanation preserves frozen scoring and exact identities."""

import unittest

from pydantic import ValidationError
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.reconciliation.candidate_sets import (
    CandidateExplanation,
    CandidateMember,
    CandidateSetContent,
    content_digest,
)
from research_observatory_core.reconciliation.candidates import CandidateRecord, generate_candidates
from research_observatory_core.reconciliation.contracts import CanonicalWorkReference


class CandidateSetContractTests(unittest.TestCase):
    def test_kernel_explanation_round_trip_and_substitution_denials(self):
        records = tuple(
            CandidateRecord(new_uuid_v7(), new_uuid_v7(), (("title", ("Synthetic duplicate study",)),))
            for _ in range(2)
        )
        pair = generate_candidates(records).pairs[0]
        explanation = CandidateExplanation.from_kernel(pair)
        self.assertEqual(
            explanation, CandidateExplanation.model_validate_json(explanation.model_dump_json(by_alias=True))
        )
        self.assertEqual(pair.score, explanation.score)
        self.assertEqual(tuple(item.name for item in pair.features), tuple(item.name for item in explanation.features))
        for change in (
            {"score": pair.score - 1},
            {"configuration_fingerprint": "0" * 64},
            {"left": pair.right},
            {"features": explanation.features[:-1]},
            {"disposition": "auto-merge"},
        ):
            with self.subTest(change=tuple(change)), self.assertRaises(ValidationError):
                CandidateExplanation.model_validate(explanation.model_copy(update=change))

    def test_set_binds_pairs_to_exact_members_and_final_work_heads(self):
        records = tuple(
            CandidateRecord(new_uuid_v7(), new_uuid_v7(), (("title", ("Synthetic duplicate study",)),))
            for _ in range(2)
        )
        pair = CandidateExplanation.from_kernel(generate_candidates(records).pairs[0])
        work = CanonicalWorkReference(work_id=new_uuid_v7(), revision_id=new_uuid_v7())
        members = (
            CandidateMember(
                assertion_revision_id=pair.left,
                source_revision_id=pair.left_revision,
                input_sha256=pair.left_fingerprint,
                canonical_work=work,
            ),
            CandidateMember(
                assertion_revision_id=pair.right,
                source_revision_id=pair.right_revision,
                input_sha256=pair.right_fingerprint,
                canonical_work=work,
            ),
        )
        content = CandidateSetContent(
            project_id=new_uuid_v7(),
            request_id=new_uuid_v7(),
            request_sha256="a" * 64,
            inventory_sha256="b" * 64,
            members=members,
            compared_pairs=1,
            pair_sha256=(content_digest(pair),),
        )
        content.validate_pair(0, pair)
        with self.assertRaises(ValueError):
            content.validate_pair(0, pair.model_copy(update={"left_fingerprint": "c" * 64}))
        for change in (
            {"members": members[::-1]},
            {"compared_pairs": 0},
            {
                "members": (
                    members[0],
                    members[1].model_copy(
                        update={"canonical_work": work.model_copy(update={"revision_id": new_uuid_v7()})}
                    ),
                )
            },
        ):
            with self.subTest(change=tuple(change)), self.assertRaises(ValidationError):
                CandidateSetContent.model_validate(content.model_copy(update=change))
