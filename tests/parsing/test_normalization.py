"""Independent raw-origin expectations, not offsets into an unstated string."""

import hashlib
import sys
import unittest
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.parsing.normalization import NormalizationProblem, normalize_text  # noqa: E402


class NormalizationTests(unittest.TestCase):
    def test_pinned_unicode_16_nfc_conformance_gold(self):
        path = REPO / "tests/fixtures/documents/normalization/NormalizationTest-16.0.0.txt"
        data = path.read_bytes()
        self.assertEqual(
            "d811971453e7075e1ad56fb1b301eece5aa80757b81f6156e74a1bfb3ae5ceb1", hashlib.sha256(data).hexdigest()
        )
        rows = 0
        for line_number, line in enumerate(data.decode("utf-8").splitlines(), 1):
            content = line.split("#", 1)[0].strip()
            if not content or content.startswith("@"):
                continue
            columns = ["".join(chr(int(point, 16)) for point in field.split()) for field in content.split(";")[:5]]
            for column, expected in (
                (0, columns[1]),
                (1, columns[1]),
                (2, columns[1]),
                (3, columns[3]),
                (4, columns[3]),
            ):
                actual = normalize_text(columns[column])
                self.assertEqual(
                    expected, actual.normalized_text, f"Unicode gold line {line_number} column {column + 1}"
                )
            rows += 1
        self.assertGreater(rows, 19000)

    def test_folding_composition_and_supplementary_offsets(self):
        raw = "A\r\n\u0044\u0307\u0323\U0001f642\r\ufb01 -  "
        result = normalize_text(raw)
        self.assertEqual("A\n\u1e0c\u0307\U0001f642\n\ufb01 -  ", result.normalized_text)
        self.assertEqual(raw, result.raw_text)
        self.assertEqual("ro-text-nfc-1", result.normalization_version)
        self.assertEqual("16.0.0", result.unicode_version)
        self.assertEqual(((1, 3),), result.raw_ranges_for(1, 2))
        self.assertEqual(((3, 4), (5, 6)), result.raw_ranges_for(2, 3))
        self.assertEqual(((4, 5),), result.raw_ranges_for(3, 4))
        self.assertEqual(((6, 7),), result.raw_ranges_for(4, 5))
        self.assertEqual(((3, 6),), result.raw_ranges_for(2, 4))

    def test_expansion_blocking_hangul_and_zero_class_composition(self):
        cases = (
            ("\u0344", "\u0308\u0301", (((0, 1),), ((0, 1),))),
            ("A\u0305\u0301", "A\u0305\u0301", (((0, 1),), ((1, 2),), ((2, 3),))),
            ("\u1100\u1161\u11a8", "\uac01", (((0, 3),),)),
            ("\u09c7\u09be", "\u09cb", (((0, 2),),)),
            ("\u0301\u0323", "\u0323\u0301", (((1, 2),), ((0, 1),))),
        )
        for raw, expected, origins in cases:
            with self.subTest(raw=ascii(raw)):
                actual = normalize_text(raw)
                self.assertEqual(expected, actual.normalized_text)
                self.assertEqual(origins, tuple(actual.raw_ranges_for(i, i + 1) for i in range(len(expected))))

    def test_identity_empty_and_invalid_scalars_or_ranges(self):
        self.assertEqual((), normalize_text("").mappings)
        result = normalize_text("\U0001f642\ufb01 -  " * 1024)
        self.assertEqual(1, len(result.mappings))
        self.assertEqual(((1, 4),), result.raw_ranges_for(1, 4))
        self.assertEqual((), result.raw_ranges_for(2, 2))
        for raw in ("\ud800", "\udfff", 42):
            with self.subTest(raw=ascii(raw)), self.assertRaises(NormalizationProblem):
                normalize_text(cast(str, raw))  # Deliberately challenge the runtime boundary with a non-string.
        for bounds in ((-1, 1), (1, 0), (0, len(result.normalized_text) + 1), (True, 2)):
            with self.subTest(bounds=bounds), self.assertRaises(NormalizationProblem):
                result.raw_ranges_for(*bounds)


if __name__ == "__main__":
    unittest.main()
