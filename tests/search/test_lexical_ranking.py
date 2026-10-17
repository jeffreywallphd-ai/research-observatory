"""Protected FTS rank and exact snippet behavior; synthetic keys, not Native proof."""

import hashlib
import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.search import parse_query  # noqa: E402

from tests.search import test_protected_lexical_store as fixtures  # noqa: E402
from tests.search.fixture_support import ProtectedIndexFixture  # noqa: E402

row = fixtures.row


class LexicalRankingTests(ProtectedIndexFixture):
    def install(self, store, values):
        store.apply(tuple(values), (), expected_checkpoint=0, checkpoint=1)
        return tuple(value.entry_id for value in values), tuple(sorted({value.item_id for value in values}))

    def test_boolean_membership_spans_rows_and_repeated_leaves_do_not_multiply_rank(self):
        title = row(text="alpha")
        passage = replace(title, entry_id="b" * 64, title="", full_text="beta")
        with self.store(create=True) as store:
            entries, items = self.install(store, (title, passage))
            result = store.rank(parse_query("title:alpha AND full-text:beta"), entries, items)
            self.assertEqual(items, tuple(hit.item_id for hit in result))
            self.assertEqual(2, len(result[0].components))
            self.assertGreater(result[0].score, 0)
            self.assertTrue(math.isfinite(result[0].score))
            single = store.rank(parse_query("alpha"), entries, items)
            repeated = store.rank(parse_query("alpha OR alpha"), entries, items)
            self.assertEqual(single, repeated)
            neutral = store.rank(parse_query("NOT missing AND year:2024"), entries, items)
            self.assertEqual(0.0, neutral[0].score)
            self.assertEqual((), neutral[0].components)

    def test_field_weight_and_exact_tie_order_are_independent_of_input_order(self):
        first, second, third = sorted(new_uuid_v7() for _ in range(3))
        values = (
            row(first, "alpha", entry_id="a" * 64),
            row(second, "alpha", entry_id="b" * 64),
            row(third, "", abstract="alpha", entry_id="c" * 64),
        )
        with self.store(create=True) as store:
            entries, items = self.install(store, values)
            ranked = store.rank(parse_query("alpha"), tuple(reversed(entries)), tuple(reversed(items)))
            self.assertEqual((first, second, third), tuple(hit.item_id for hit in ranked))
            self.assertEqual(ranked[0].score, ranked[1].score)
            self.assertGreater(ranked[1].score, ranked[2].score)
            self.assertEqual(ranked, store.rank(parse_query("alpha"), entries, items))

    def test_verified_snippet_keeps_original_unicode_and_never_uses_markup_as_html(self):
        text = "📚 prefix\r\nCafé <script>alert(1)</script> cafe\u0301 suffix"
        value = row(text="", full_text=text)
        with self.store(create=True) as store:
            entries, items = self.install(store, (value,))
            hit = store.rank(parse_query("full-text:cafe"), entries, items)[0]
            preview = store.snippet(parse_query("full-text:cafe"), hit.components[0], field="full-text")
            self.assertEqual(text[preview.start : preview.end], preview.text)
            self.assertEqual("Café", preview.text[preview.highlights[0][0] : preview.highlights[0][1]])
            self.assertIn("<script>", preview.text)
            self.assertLessEqual(len(preview.text), 384)
            self.assertFalse(preview.truncated)

    def test_all_scores_are_returned_but_explanations_are_bounded_to_one_page(self):
        values = tuple(row(new_uuid_v7(), "alpha") for _ in range(64))
        with self.store(create=True) as store:
            entries, items = self.install(store, values)
            ranked = store.rank(parse_query("alpha"), entries, items)
            self.assertEqual(64, len(ranked))
            self.assertEqual(50, sum(bool(hit.components) for hit in ranked))
            bare = store.rank(parse_query("alpha"), entries, items, explain_limit=0)
            self.assertFalse(any(hit.components for hit in bare))
            self.assertEqual(
                tuple((hit.item_id, hit.score) for hit in ranked), tuple((hit.item_id, hit.score) for hit in bare)
            )

    def test_long_phrase_is_truthfully_truncated_and_highlights_stay_inside_slice(self):
        text = "prefix alpha " + "!" * 70000 + " beta suffix"
        value = row(text="", full_text=text)
        with self.store(create=True) as store:
            entries, items = self.install(store, (value,))
            query = parse_query('full-text:"alpha beta"')
            component = store.rank(query, entries, items)[0].components[0]
            preview = store.snippet(query, component, field="full-text")
            self.assertEqual(text[preview.start : preview.end], preview.text)
            self.assertTrue(preview.truncated)
            self.assertLessEqual(len(preview.text), 384)
            self.assertTrue(all(0 <= start < end <= len(preview.text) for start, end in preview.highlights))

    def test_held_out_fixture_is_unchanged_before_implementation_comparison(self):
        path = ROOT / "tests/search/fixtures/synthetic-known-items.v1.json"
        self.assertEqual(
            "62f37a7259351dfa82c9ea1f2de8148d9e299c6c6db27cad16a903ee45a9ae32",
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
