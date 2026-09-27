"""Normalization challenges use synthetic values and official checksum examples."""

import unittest

from research_observatory_core.reconciliation.identifiers import normalize_identifier


class IdentifierTests(unittest.TestCase):
    def test_equivalent_forms_preserve_observed_value(self):
        cases = (
            ("doi", " DOI:10.1234/ABC.(x) ", "10.1234/abc.(x)", "work"),
            ("doi", "10.500.100/A B ", "10.500.100/a b", "work"),
            ("doi", "https://doi.org/10.1234/A%20", "10.1234/a ", "work"),
            ("doi", "10.1234567890123/A", "10.1234567890123/a", "work"),
            ("doi", "https://doi.org/10.1234/AbC%3Fx%23y", "10.1234/abc?x#y", "work"),
            ("pmid", "PMID: 00123456", "123456", "work"),
            ("pmid", "https://pubmed.ncbi.nlm.nih.gov/123456/", "123456", "work"),
            ("arxiv", "arXiv:2301.01234v2", "2301.01234v2", "work-version"),
            ("arxiv", "https://arxiv.org/abs/math.CA/0611800v2", "math/0611800v2", "work-version"),
            ("isbn", "ISBN 978-92-95055-02-5", "9789295055025", "work-version"),
            ("orcid", "0000-0002-1825-0097", "https://orcid.org/0000-0002-1825-0097", "person"),
            ("openalex", "https://openalex.org/works/w123", "W123", "work"),
            ("openalex", "https://openalex.org/A123", "A123", "person"),
            ("s2-paper", "ABCDEF" + "0" * 34, "abcdef" + "0" * 34, "work"),
            ("s2-corpus", "CorpusId:00123", "123", "work"),
            ("url", "HTTPS://EXAMPLE.ORG:443/A/%7eb?x=1#Part", "https://example.org/A/~b?x=1#Part", "location"),
            ("title", "  An EXAMPLE\tTitle  ", "an example title", "heuristic"),
        )
        for scheme, observed, canonical, scope in cases:
            with self.subTest(scheme=scheme, observed=observed):
                result = normalize_identifier(scheme, observed)
                self.assertEqual(observed, result.observed)
                self.assertEqual(canonical, result.canonical)
                self.assertEqual(scope, result.scope)
                self.assertEqual("valid", result.status)
                self.assertEqual("scholarly-identifiers/1.0.0", result.normalizer_version)
                self.assertFalse(result.registry_verified)

    def test_invalid_and_unsupported_are_explicit_without_a_match_key(self):
        cases = (
            ("doi", "10.1234/"),
            ("doi", "https://doi.org/10.1234/x?different=1"),
            ("doi", "https://doi.org.evil.invalid/10.1234/x"),
            ("doi", "10.1234/a\x00b"),
            # A fabricated URL userinfo component, not an email address.
            ("doi", "https://synthetic-user" + "@doi.org/10.1234/x"),
            ("doi", "10.1234/a\u2028b"),
            ("pmid", "0"),
            ("pmid", "\uff11\uff12\uff13"),
            ("pmid", "PMC123"),
            ("arxiv", "2300.01234"),
            ("arxiv", "2301.1234"),
            ("arxiv", "2301.00000"),
            ("arxiv", "2301.01234v0"),
            ("arxiv", "math/2301123"),
            ("isbn", "9789295055026"),
            ("isbn", "9779295055026"),
            ("orcid", "0000-0002-1825-0098"),
            ("orcid", "https://orcid.org.evil/0000-0002-1825-0097"),
            ("openalex", "https://openalex.org/authors/W123"),
            ("openalex", "W0"),
            ("s2-paper", "0" * 39),
            ("s2-corpus", "0"),
            ("url", "javascript:alert(1)"),
            ("url", "https://example.org/%zz"),
            ("url", "https://user:password@example.org/"),
            ("url", "https://example.org/\nprivate"),
            ("unknown-provider", "123"),
        )
        for scheme, observed in cases:
            with self.subTest(scheme=scheme, observed=observed):
                result = normalize_identifier(scheme, observed)
                self.assertIn(result.status, {"invalid", "unsupported"})
                self.assertIsNone(result.canonical)
                self.assertTrue(result.issues)
                self.assertEqual(observed, result.observed)

    def test_no_lossy_collisions_or_invented_person_work_equivalence(self):
        for scheme, first, second in (
            ("doi", "10.1234/Á", "10.1234/á"),
            ("doi", "10.1234/a.", "10.1234/a"),
            ("doi", "https://doi.org/10.1234/a%20", "10.1234/a"),
            ("doi", "10.1234/straße", "10.1234/strasse"),
            ("arxiv", "2301.01234", "2301.01234v1"),
            ("arxiv", "2301.01234v1", "2301.01234v2"),
            ("url", "https://example.org/A", "https://example.org/a"),
            ("url", "https://example.org/?a=1&b=2", "https://example.org/?b=2&a=1"),
            ("url", "https://example.org/a%2Fb", "https://example.org/a/b"),
        ):
            with self.subTest(scheme=scheme, first=first):
                a, b = normalize_identifier(scheme, first), normalize_identifier(scheme, second)
                self.assertEqual(("valid", "valid"), (a.status, b.status))
                self.assertNotEqual(a.canonical, b.canonical)
        self.assertEqual("person", normalize_identifier("orcid", "0000-0002-1825-0097").scope)
        self.assertEqual("organization", normalize_identifier("openalex", "I123").scope)

    def test_bounded_input_and_redacted_repr(self):
        result = normalize_identifier("doi", "10.1234/private-research-token")
        self.assertNotIn("private-research-token", repr(result))
        with self.assertRaises(ValueError):
            normalize_identifier("doi", "x" * 65537)


if __name__ == "__main__":
    unittest.main()
