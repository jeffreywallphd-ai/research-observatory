"""Persisted candidate explanation preserves frozen scoring and exact identities."""

import unittest

from pydantic import ValidationError
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.reconciliation.candidate_sets import (
    CandidateExplanation,
    CandidateMember,
    CandidateSetContent,
    content_digest,
    prioritize_candidates,
)
from research_observatory_core.reconciliation.candidates import CandidateRecord, generate_candidates
from research_observatory_core.reconciliation.contracts import CanonicalWorkReference


class CandidateSetContractTests(unittest.TestCase):
    def test_review_priority_uses_uncertainty_then_preserves_retrieval_ties(self):
        keys = tuple(new_uuid_v7() for _ in range(5))
        records = (
            CandidateRecord(
                keys[0], new_uuid_v7(), (("title", ("Synthetic marine study",)), ("authors", ("Ada One", "Bea Two")))
            ),
            CandidateRecord(
                keys[1], new_uuid_v7(), (("title", ("Synthetic marine study",)), ("authors", ("Ada One",)))
            ),
            CandidateRecord(
                keys[2], new_uuid_v7(), (("title", ("Synthetic marine study",)), ("authors", ("Ada One",)))
            ),
            CandidateRecord(keys[3], new_uuid_v7(), (("title", ("Synthetic marine study",)),)),
            CandidateRecord(
                keys[4], new_uuid_v7(), (("title", ("Synthetic marine study",)), ("authors", ("Ada One",)))
            ),
        )
        pairs = tuple(CandidateExplanation.from_kernel(pair) for pair in generate_candidates(records).pairs)

        def find(left, right):
            return next(pair for pair in pairs if {pair.left, pair.right} == {keys[left], keys[right]})

        disputed, plain, missing, same = find(0, 1), find(1, 2), find(2, 3), find(2, 4)
        self.assertGreater(sum(item.state == "disputed" for item in disputed.features), 0)
        self.assertEqual(0, sum(item.state == "disputed" for item in plain.features))
        self.assertGreater(
            sum(item.state == "not-reported" for item in missing.features),
            sum(item.state == "not-reported" for item in plain.features),
        )
        memberships: dict[str, tuple[str, ...]] = {key: (key,) for key in keys}
        self.assertEqual(
            (disputed, missing, plain, same), prioritize_candidates((plain, missing, disputed, same), memberships)
        )
        self.assertEqual((same, plain), prioritize_candidates((same, plain), memberships))

    def test_review_priority_can_place_lower_similarity_above_low_impact_pair(self):
        titles = (
            "Synthetic marine cell study",
            "Synthetic marine cell study",
            "Synthetic marine cells study",
            "Synthetic marine cells study",
        )
        keys = tuple(new_uuid_v7() for _ in titles)
        records = tuple(
            CandidateRecord(keys[index], new_uuid_v7(), (("title", (title,)),)) for index, title in enumerate(titles)
        )
        retrieved = tuple(CandidateExplanation.from_kernel(pair) for pair in generate_candidates(records).pairs)
        lower = next(pair for pair in retrieved if {pair.left, pair.right} == {keys[0], keys[2]})
        higher = next(pair for pair in retrieved if {pair.left, pair.right} == {keys[2], keys[3]})
        self.assertLess(lower.score, higher.score)
        self.assertLess(retrieved.index(higher), retrieved.index(lower))
        memberships: dict[str, tuple[str, ...]] = {key: (key,) for key in keys}
        memberships[keys[0]] = tuple(sorted((keys[0], new_uuid_v7(), new_uuid_v7())))

        ordered = prioritize_candidates(retrieved, memberships)

        self.assertLess(ordered.index(lower), ordered.index(higher))
        self.assertEqual(set(retrieved), set(ordered))
        self.assertEqual(len(retrieved), len(ordered))
        self.assertEqual({content_digest(pair) for pair in retrieved}, {content_digest(pair) for pair in ordered})

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
