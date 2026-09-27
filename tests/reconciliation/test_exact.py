"""Exact matching must not turn overlapping assertions into transitive merges."""

import unittest
from itertools import permutations

from research_observatory_core.reconciliation.exact import IdentifierAssertion, assess_match, select_field


def identifier(scheme, observed, **kwargs):
    return IdentifierAssertion(scheme=scheme, observed=observed, **kwargs)


class ExactMatchTests(unittest.TestCase):
    def test_unique_valid_match_is_deterministic_and_does_not_verify_registry(self):
        old = (identifier("doi", "10.1234/alpha"),)
        new = (identifier("doi", "HTTPS://DOI.ORG/10.1234/ALPHA"),)
        result = assess_match(new, {"work-a": old})
        self.assertEqual("exact-linked", result.disposition)
        self.assertEqual("work-a", result.target)
        self.assertEqual("unverified", new[0].verification_state)
        self.assertFalse(new[0].normalized.registry_verified)

    def test_multi_target_bridge_and_one_target_conflict_never_merge(self):
        works = {"work-a": (identifier("doi", "10.1234/a"),), "work-b": (identifier("pmid", "123"),)}
        incoming = (identifier("doi", "10.1234/a"), identifier("pmid", "123"))
        for order in permutations(works):
            result = assess_match(incoming, {key: works[key] for key in order})
            self.assertEqual("review-required", result.disposition)
            self.assertIsNone(result.target)
            self.assertEqual(("work-a", "work-b"), result.candidates)
            self.assertIn("multiple-work-matches", result.flags)
        result = assess_match(
            (identifier("doi", "10.1234/a"), identifier("pmid", "456")),
            {"work-a": incoming},
        )
        self.assertIn("conflicting-identifiers", result.flags)
        self.assertIsNone(result.target)

    def test_entity_scope_and_heuristics_cannot_link_works(self):
        for item in (
            identifier("orcid", "0000-0002-1825-0097"),
            identifier("openalex", "A123"),
            identifier("openalex", "I123"),
            identifier("isbn", "9789295055025", role="container"),
            identifier("title", "Identical title"),
            identifier("url", "https://example.org/publication"),
        ):
            with self.subTest(scheme=item.scheme):
                self.assertEqual("new-work", assess_match((item,), {"work-a": (item,)}).disposition)

    def test_invalid_disputed_reassigned_and_duplicate_keys_remain_visible(self):
        valid = identifier("doi", "10.1234/a")
        for item in (
            identifier("doi", "not-a-doi"),
            identifier("doi", "10.1234/a", verification_state="disputed"),
            identifier("doi", "10.1234/a", reassignment_observed=True),
        ):
            result = assess_match((item,), {"work-a": (valid,)})
            self.assertEqual("review-required", result.disposition)
            self.assertTrue(result.flags)
        self.assertEqual("exact-linked", assess_match((valid, valid), {"work-a": (valid,)}).disposition)
        conflict = assess_match((valid, identifier("doi", "10.1234/b")), {})
        self.assertIn("conflicting-identifiers", conflict.flags)

    def test_reused_provider_identity_with_incompatible_doi_is_flagged(self):
        result = assess_match(
            (identifier("openalex", "W123"), identifier("doi", "10.1234/new")),
            {"work-a": (identifier("openalex", "W123"), identifier("doi", "10.1234/old"))},
        )
        self.assertIsNone(result.target)
        self.assertIn("identifier-reassignment-suspected", result.flags)

    def test_source_precedence_preserves_conflicts_and_human_correction_reason(self):
        result = select_field((("source-a", "Alpha", "observed"), ("source-b", "Beta", "observed")))
        self.assertEqual("disputed", result.status)
        self.assertIsNone(result.selected)
        self.assertEqual(2, len(result.assertions))
        result = select_field((("source-a", "Alpha", "observed"), ("source-b", "Beta", "correction")))
        self.assertEqual("Beta", result.selected)
        self.assertEqual("accepted-correction", result.reason)
        self.assertEqual(2, len(result.assertions))
        result = select_field((("source-a", "Alpha", "correction"), ("source-b", "Beta", "correction")))
        self.assertEqual("disputed", result.status)


if __name__ == "__main__":
    unittest.main()
