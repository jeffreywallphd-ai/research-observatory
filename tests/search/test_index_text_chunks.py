"""Pure source-range boundary proof; actual FTS integration is tested separately."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.lexical_source_repository import _text_ranges  # noqa: E402


class IndexTextChunkTests(unittest.TestCase):
    def test_term_and_maximum_query_phrase_crossing_chunk_boundary_remain_whole(self):
        prefix = "x " * 32765
        phrase = "transboundary phrase " + "tail " * 1200
        text = prefix + phrase + " suffix" * 12000
        ranges = tuple(_text_ranges(text, 0, len(text)))
        self.assertEqual(((0, len(text)),), ranges)
        self.assertTrue(any(phrase in text[start:end] for start, end in ranges))
        self.assertEqual(0, ranges[0][0])
        self.assertEqual(len(text), ranges[-1][1])
        for start, end in ranges:
            self.assertLess(start, end)
            self.assertTrue(start == 0 or text[start - 1].isspace())
            self.assertTrue(end == len(text) or text[end - 1].isspace())


if __name__ == "__main__":
    unittest.main()
