"""Explainable candidate retrieval must never adjudicate scholarly identity."""

import unittest

from research_observatory_core.reconciliation.candidates import (
    CandidateConfig,
    CandidateRecord,
    compare_records,
    generate_candidates,
    generate_prepared_candidates,
    prepare_record,
)
from research_observatory_core.reconciliation.contracts import ReconciliationProblem
from research_observatory_core.reconciliation.exact import IdentifierAssertion


def record(key, *, title="", authors="", year="", venue="", pages="", abstract="", identifiers=(), revision=None):
    values = {"title": title, "authors": authors, "year": year, "venue": venue, "pages": pages, "abstract": abstract}
    return CandidateRecord(
        key=key,
        revision=revision or key + "-revision",
        fields=tuple((name, (value,)) for name, value in values.items() if value),
        identifiers=identifiers,
    )


class CandidateTests(unittest.TestCase):
    def test_prepared_input_path_matches_uncached_retrieval_and_polls_during_preparation(self):
        records = (
            record("a", title="Synthetic evidence", authors="Jane Doe"),
            record("b", title="Synthetic evidence!", authors="Doe, Jane"),
        )
        polls = []
        direct = generate_candidates(records, checkpoint=lambda: polls.append(True))
        prepared = tuple(prepare_record(item) for item in records)
        self.assertEqual(direct, generate_prepared_candidates(tuple(reversed(prepared))))
        self.assertGreaterEqual(len(polls), 2 * len(records))
        with self.assertRaisesRegex(ReconciliationProblem, "duplicate-record-identity-conflict"):
            generate_prepared_candidates((prepared[0], prepared[0]))

    def test_identical_title_with_punctuation_and_author_order_is_a_review_candidate(self):
        left = record("a", title="A café: records and evidence", authors="Doe, Jane; Lee, Sam", year="2020")
        right = record("b", title="A cafe — records and evidence!", authors="Sam Lee; Jane Doe", year="2020")
        candidate = compare_records(prepare_record(left), prepare_record(right))
        self.assertGreaterEqual(candidate.score, 9000)
        self.assertEqual("human-review-required", candidate.disposition)
        self.assertEqual(
            ("a", "b", "a-revision", "b-revision"),
            (candidate.left, candidate.right, candidate.left_revision, candidate.right_revision),
        )
        features = {item.name: item for item in candidate.features}
        self.assertEqual(10000, features["title"].score)
        self.assertEqual(10000, features["authors"].score)
        self.assertEqual({"title", "authors", "year", "venue", "pages", "abstract", "identifiers"}, set(features))

    def test_absent_features_stay_absent_and_do_not_create_perfect_agreement(self):
        candidate = compare_records(prepare_record(record("a")), prepare_record(record("b")))
        self.assertEqual(0, candidate.score)
        self.assertTrue(all(item.score is None and item.state == "not-reported" for item in candidate.features))
        self.assertEqual((), generate_candidates((record("a"), record("b"))).pairs)

    def test_pages_abstract_and_year_contribute_with_visible_disagreement(self):
        left = record(
            "a",
            title="Synthetic quantum coding",
            authors="Jane Doe",
            year="2020",
            pages="11\u201319",
            abstract="A finite synthetic description of evidence.",
        )
        right = record(
            "b",
            title=left.fields[0][1][0],
            authors="Jane Doe",
            year="2024",
            pages="11-19",
            abstract="A finite synthetic description of evidence.",
        )
        features = {item.name: item for item in compare_records(prepare_record(left), prepare_record(right)).features}
        self.assertEqual((10000, "available"), (features["pages"].score, features["pages"].state))
        self.assertEqual(10000, features["abstract"].score)
        self.assertEqual(0, features["year"].score)
        self.assertTrue(features["year"].conflict)

    def test_conflicting_identifiers_and_fields_are_visible_even_for_same_title(self):
        left = record(
            "a", title="Synthetic same title", identifiers=(IdentifierAssertion(scheme="doi", observed="10.1234/a"),)
        )
        right = record(
            "b", title="Synthetic same title", identifiers=(IdentifierAssertion(scheme="doi", observed="10.1234/b"),)
        )
        candidate = compare_records(prepare_record(left), prepare_record(right))
        self.assertIn("conflicting-identifiers", candidate.flags)
        self.assertEqual("human-review-required", candidate.disposition)
        disputed = CandidateRecord(
            key="c",
            revision="c-revision",
            fields=(("title", ("First competing title", "Second competing title")),),
            identifiers=(),
        )
        feature = next(
            item
            for item in compare_records(prepare_record(disputed), prepare_record(left)).features
            if item.name == "title"
        )
        self.assertEqual("disputed", feature.state)
        self.assertTrue(feature.conflict)

    def test_namespaced_identifiers_can_block_missing_title_but_person_ids_cannot(self):
        doi = IdentifierAssertion(scheme="doi", observed="10.1234/synthetic")
        a, b = record("a", identifiers=(doi,)), record("b", identifiers=(doi,))
        result = generate_candidates((a, b))
        self.assertEqual(1, len(result.pairs))
        orcid = IdentifierAssertion(scheme="orcid", observed="0000-0002-1825-0097", role="person")
        self.assertEqual(
            (), generate_candidates((record("c", identifiers=(orcid,)), record("d", identifiers=(orcid,)))).pairs
        )

    def test_ranking_is_deterministic_and_transitive_bridge_remains_individual_evidence(self):
        inputs = (
            record(
                "a",
                title="Synthetic shared title",
                year="2020",
                identifiers=(IdentifierAssertion(scheme="doi", observed="10.1234/a"),),
            ),
            record("b", title="Synthetic shared title", year="2020"),
            record(
                "c",
                title="Synthetic shared title",
                year="2020",
                identifiers=(IdentifierAssertion(scheme="doi", observed="10.1234/c"),),
            ),
        )
        first = generate_candidates(inputs, config=CandidateConfig(minimum_score=0))
        second = generate_candidates(tuple(reversed(inputs)), config=CandidateConfig(minimum_score=0))
        self.assertEqual(first, second)
        self.assertEqual(3, len(first.pairs))
        self.assertTrue(all(item.disposition == "human-review-required" for item in first.pairs))
        ac = next(item for item in first.pairs if (item.left, item.right) == ("a", "c"))
        self.assertIn("conflicting-identifiers", ac.flags)

    def test_changed_revision_binds_new_feature_identity_without_cross_record_alias(self):
        original = prepare_record(record("a", title="Synthetic original"))
        changed = prepare_record(record("a", title="Synthetic changed", revision="a-next"))
        self.assertNotEqual(original.fingerprint, changed.fingerprint)
        self.assertEqual(original, prepare_record(record("a", title="Synthetic original")))
        with self.assertRaises(ReconciliationProblem):
            generate_candidates((record("a", title="First"), record("a", title="Second")))

    def test_resource_limits_fail_closed_instead_of_silently_losing_candidates(self):
        records = tuple(record(str(index), title="Synthetic common title") for index in range(5))
        with self.assertRaisesRegex(ReconciliationProblem, "duplicate-comparison-limit"):
            generate_candidates(records, config=CandidateConfig(max_comparisons=2))
        with self.assertRaises(ReconciliationProblem):
            prepare_record(record("a", title="x" * 65537))

    def test_blocking_reduces_comparisons_without_all_pairs(self):
        records = tuple(record(str(index), title=f"quasar{index} evidence{index}") for index in range(100))
        result = generate_candidates(records)
        self.assertEqual(0, result.compared_pairs)
        self.assertEqual((), result.pairs)


if __name__ == "__main__":
    unittest.main()
