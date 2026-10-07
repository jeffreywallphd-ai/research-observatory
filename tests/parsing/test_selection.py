"""Selection authority is supplied by Core, never by a document or worker echo."""

import sys
import unittest
from itertools import permutations
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.parsing.contracts import ParserAsset  # noqa: E402
from research_observatory_core.parsing.selection import (  # noqa: E402
    Availability,
    ParserRegistry,
    RegisteredParser,
    SelectionBasis,
    SelectionProblem,
    SelectionSource,
    select_parser,
)

from tests.parsing.contract_fixtures import descriptor, source  # noqa: E402


class SelectionTests(unittest.TestCase):
    def registry(self):
        native = descriptor()
        docling = descriptor("ro-docling-cpu", ("pdf", "docx")).model_copy(
            update={
                "version": "2.126.0",
                "kind": "docling-cpu",
                "assets": (ParserAsset(component="docling-assets", version="synthetic-fixture-1", sha256="4" * 64),),
            }
        )
        return ParserRegistry((RegisteredParser(native, "available"), RegisteredParser(docling, "available")))

    def test_native_first_and_recorded_decision_are_permutation_invariant(self):
        primary, native, second = source("pdf", 1), source("jats", 2), source("html", 3)
        sources = (
            SelectionSource(primary, "available", "primary"),
            SelectionSource(native, "available", "explicit-alternative"),
            SelectionSource(second, "available", "explicit-alternative"),
        )
        expected = None
        for order in permutations(sources):
            result = select_parser(order, self.registry(), primary_attachment_id=primary.attachment_id)
            self.assertEqual(native.attachment_id, result.selected_attachment_id)
            self.assertEqual("ro-native-structured", result.selected_parser_id)
            self.assertEqual("ro-parser-policy-1", result.policy_version)
            if expected is None:
                expected = result.model_dump_json(by_alias=True)
            self.assertEqual(expected, result.model_dump_json(by_alias=True))

    def test_same_work_or_digest_is_not_equivalence_or_current_rights(self):
        primary, native = source("pdf", 1), source("jats", 2)
        cases: tuple[tuple[Availability, SelectionBasis, str], ...] = (
            ("available", "unproven", "equivalence-unproven"),
            ("rights-denied", "explicit-alternative", "rights-denied"),
        )
        for availability, basis, expected_reason in cases:
            result = select_parser(
                (SelectionSource(primary, "available", "primary"), SelectionSource(native, availability, basis)),
                self.registry(),
                primary_attachment_id=primary.attachment_id,
            )
            self.assertEqual(primary.attachment_id, result.selected_attachment_id)
            excluded = next(value for value in result.candidates if value.source.attachment_id == native.attachment_id)
            self.assertEqual(expected_reason, excluded.disposition)

    def test_ties_duplicates_unavailable_and_unregistered_parsers(self):
        primary, a, b = source("pdf", 1), source("jats", 2), source("jats", 3)
        candidates = (
            SelectionSource(primary, "unavailable", "primary"),
            SelectionSource(b, "available", "explicit-alternative"),
            SelectionSource(a, "available", "explicit-alternative"),
        )
        result = select_parser(candidates, self.registry(), primary_attachment_id=primary.attachment_id)
        self.assertEqual(a.attachment_id, result.selected_attachment_id)
        with self.assertRaises(SelectionProblem):
            select_parser(
                (
                    *candidates,
                    SelectionSource(
                        a.model_copy(update={"object_sha256": "f" * 64}), "available", "explicit-alternative"
                    ),
                ),
                self.registry(),
                primary_attachment_id=primary.attachment_id,
            )
        unavailable = ParserRegistry((RegisteredParser(descriptor(), "unavailable"),))
        result = select_parser(
            (SelectionSource(a, "available", "primary"),), unavailable, primary_attachment_id=a.attachment_id
        )
        self.assertEqual("unavailable", result.outcome)
        self.assertIsNone(result.selected_parser_id)
        with self.assertRaises(SelectionProblem):
            ParserRegistry((RegisteredParser(descriptor("document-provided-code"), "available"),))
        with self.assertRaises(SelectionProblem):
            ParserRegistry(
                (
                    RegisteredParser(
                        self.registry().entries[0].descriptor.model_copy(update={"assets": ()}), "available"
                    ),
                )
            )

    def test_fallback_is_separate_and_inspection_only(self):
        primary = source("pdf", 1)
        fallback = descriptor("ro-page-text-fallback", ("pdf",)).model_copy(update={"kind": "degraded-inspection"})
        registry = ParserRegistry((*self.registry().entries, RegisteredParser(fallback, "available")))
        initial = select_parser(
            (SelectionSource(primary, "available", "primary"),), registry, primary_attachment_id=primary.attachment_id
        )
        result = select_parser(
            (SelectionSource(primary, "available", "primary"),),
            registry,
            primary_attachment_id=primary.attachment_id,
            fallback_from=("018f0000-0000-7000-8000-000000000999", "parser-failed", initial),
        )
        self.assertEqual("inspection-only", result.outcome)
        self.assertEqual("ro-page-text-fallback", result.selected_parser_id)
        self.assertEqual("018f0000-0000-7000-8000-000000000999", result.fallback_from_attempt_id)
        for code in ("cancelled", "rights-denied", "source-unavailable"):
            with self.subTest(code=code), self.assertRaises(SelectionProblem):
                select_parser(
                    (SelectionSource(primary, "available", "primary"),),
                    registry,
                    primary_attachment_id=primary.attachment_id,
                    fallback_from=("018f0000-0000-7000-8000-000000000999", code, initial),
                )


if __name__ == "__main__":
    unittest.main()
