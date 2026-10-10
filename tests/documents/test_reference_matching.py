"""Declared synthetic Work snapshots; current authority is tested at the adapter."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.document_references import (  # noqa: E402
    ReferenceWorkSnapshot,
    extract_references,
    match_reference_entries,
)
from research_observatory_core.reconciliation.candidates import CandidateRecord  # noqa: E402
from research_observatory_core.reconciliation.contracts import CanonicalWorkReference  # noqa: E402
from research_observatory_core.reconciliation.exact import IdentifierAssertion, assess_match  # noqa: E402

from tests.documents.test_reference_entries import JATS, accepted_native  # noqa: E402
from tests.parsing.contract_fixtures import identity  # noqa: E402


def snapshot(number, *, doi="10.99999/synthetic-a", title="Synthetic reference alpha"):
    target = CanonicalWorkReference(work_id=identity(number), revision_id=identity(number + 100))
    return ReferenceWorkSnapshot(
        target,
        CandidateRecord(
            target.work_id,
            target.revision_id,
            (("title", (title,)), ("year", ("2024",))),
            (IdentifierAssertion(scheme="doi", observed=doi),) if doi else (),
        ),
    )


class ReferenceMatchingTests(unittest.TestCase):
    def entries(self):
        return extract_references(accepted_native(JATS))

    def assess(self, entries, catalog):
        return tuple(
            assess_match(
                tuple(i.assertion for i in e.identifiers),
                {work.target.work_id: work.record.identifiers for work in catalog},
            )
            for e in entries
        )

    def test_unique_valid_identifier_links_exact_work_revision_without_verification(self):
        entries, catalog = self.entries(), (snapshot(901),)
        matched = match_reference_entries(entries, catalog, self.assess(entries, catalog))
        self.assertEqual("exact-linked", matched[0].link_state)
        self.assertEqual(catalog[0].target, matched[0].target)
        self.assertFalse(matched[0].candidates)
        self.assertEqual("unverified", matched[0].scholarly_verification)
        self.assertEqual("unverified", matched[0].identifiers[0].assertion.verification_state)

    def test_duplicate_exact_targets_remain_ambiguous_scored_review_candidates(self):
        entries, catalog = self.entries(), (snapshot(901), snapshot(902))
        matched = match_reference_entries(entries, catalog, self.assess(entries, catalog))
        self.assertEqual("ambiguous", matched[0].link_state)
        self.assertIsNone(matched[0].target)
        self.assertEqual(2, len(matched[0].candidates))
        self.assertIn("multiple-work-matches", matched[0].match_flags)
        for candidate in matched[0].candidates:
            self.assertEqual("human-review-required", candidate.review_state)
            self.assertTrue(candidate.features)
            self.assertGreater(candidate.score, 0)

    def test_title_similarity_never_auto_links_even_at_perfect_score(self):
        entries, catalog = self.entries(), (snapshot(901, doi=""),)
        matched = match_reference_entries(entries, catalog, self.assess(entries, catalog))
        self.assertEqual("candidate", matched[0].link_state)
        self.assertIsNone(matched[0].target)
        self.assertEqual(10000, matched[0].candidates[0].score)
        self.assertEqual("human-review-required", matched[0].candidates[0].review_state)

    def test_missing_values_remain_unresolved_and_raw_is_unchanged(self):
        entries, catalog = self.entries(), (snapshot(901),)
        matched = match_reference_entries(entries, catalog, self.assess(entries, catalog))
        self.assertEqual("unresolved", matched[1].link_state)
        self.assertFalse(matched[1].fields)
        self.assertFalse(matched[1].candidates)
        self.assertEqual(entries[1].raw_text, matched[1].raw_text)

    def test_incomplete_exact_target_snapshot_is_rejected(self):
        entries, catalog = self.entries(), (snapshot(901),)
        with self.assertRaisesRegex(ValueError, "reference-match-snapshot-invalid"):
            match_reference_entries(entries, (), self.assess(entries, catalog))

    def test_cancellation_does_not_return_partial_matches(self):
        entries, catalog = self.entries(), (snapshot(901),)
        with self.assertRaisesRegex(ValueError, "reference-operation-cancelled"):
            match_reference_entries(entries, catalog, self.assess(entries, catalog), cancelled=lambda: True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
