from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from ui_component_performance_check import (  # noqa: E402
    BASELINE_PATH,
    BATCH_BUDGET_MS,
    EXPECTED_BASELINE_METHODOLOGY,
    EXPECTED_BASELINE_P95_MS,
    EXPECTED_BASELINE_SHA256,
    EXPECTED_FIXTURE,
    EXPECTED_SAMPLE_METHODOLOGY,
    validate_baseline,
    validate_samples,
)

VALID_BASELINE: dict[str, Any] = {
    "schemaVersion": "1.0",
    "documentType": "ui-component-performance-baseline",
    "baselineSourceCommit": "a" * 40,
    "profile": "windows-x64",
    "componentContractVersion": "1.2.0",
    "fixture": {
        **EXPECTED_FIXTURE,
        "benchmarkEntrySha256": "b" * 64,
        "benchmarkRunnerSha256": "c" * 64,
    },
    "methodology": EXPECTED_BASELINE_METHODOLOGY,
    "measurements": {
        "warmPaginatedRenderBatch": {
            "absoluteBudgetMs": BATCH_BUDGET_MS,
            "baselineP95Ms": EXPECTED_BASELINE_P95_MS,
        }
    },
}

VALID_SAMPLES: dict[str, Any] = {
    "schemaVersion": "1.0",
    "documentType": "ui-component-performance-samples",
    "fixture": {
        **EXPECTED_FIXTURE,
        "firstPageMarkupBytes": 4_879,
        "lastPageMarkupBytes": 4_997,
    },
    "methodology": EXPECTED_SAMPLE_METHODOLOGY,
    "samplesMs": [40.0] * 20,
}


class UiComponentPerformanceCheckTests(unittest.TestCase):
    def test_baseline_is_strict_and_immutably_pinned(self) -> None:
        self.assertEqual(VALID_BASELINE, validate_baseline(copy.deepcopy(VALID_BASELINE)))
        self.assertEqual(
            EXPECTED_BASELINE_SHA256,
            hashlib.sha256((REPO / BASELINE_PATH).read_bytes()).hexdigest(),
        )

        for field, replacement in (
            ("schemaVersion", "2.0"),
            ("baselineSourceCommit", "short"),
            ("profile", "cloud"),
            ("componentContractVersion", "1.3.0"),
        ):
            invalid = copy.deepcopy(VALID_BASELINE)
            invalid[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_baseline(invalid)

    def test_baseline_rejects_laundered_budget_p95_and_methodology(self) -> None:
        invalid_budget = copy.deepcopy(VALID_BASELINE)
        invalid_budget["measurements"]["warmPaginatedRenderBatch"]["absoluteBudgetMs"] = 101.0
        with self.assertRaisesRegex(ValueError, "approved budget"):
            validate_baseline(invalid_budget)

        for replacement in (90.0, float("nan"), float("inf"), 0.0):
            invalid_p95 = copy.deepcopy(VALID_BASELINE)
            invalid_p95["measurements"]["warmPaginatedRenderBatch"]["baselineP95Ms"] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                validate_baseline(invalid_p95)

        invalid_method = copy.deepcopy(VALID_BASELINE)
        invalid_method["methodology"]["rendersPerSample"] = 1
        with self.assertRaisesRegex(ValueError, "methodology"):
            validate_baseline(invalid_method)

    def test_samples_bind_all_rows_to_a_bounded_window_and_complete_distribution(self) -> None:
        self.assertEqual([40.0] * 20, validate_samples(copy.deepcopy(VALID_SAMPLES)))

        for field, replacement in (
            ("totalRows", 9_999),
            ("pageSize", 51),
            ("pageCount", 199),
            ("maximumRenderedRows", 51),
        ):
            invalid = copy.deepcopy(VALID_SAMPLES)
            invalid["fixture"][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_samples(invalid)

        incomplete = copy.deepcopy(VALID_SAMPLES)
        incomplete["samplesMs"] = [40.0] * 19
        with self.assertRaisesRegex(ValueError, "every governed repetition"):
            validate_samples(incomplete)

        nonfinite = copy.deepcopy(VALID_SAMPLES)
        nonfinite["samplesMs"][0] = float("nan")
        with self.assertRaisesRegex(ValueError, "positive finite"):
            validate_samples(nonfinite)

    def test_samples_reject_methodology_and_output_shape_drift(self) -> None:
        invalid_method = copy.deepcopy(VALID_SAMPLES)
        invalid_method["methodology"]["warmupBatches"] = 0
        with self.assertRaisesRegex(ValueError, "methodology"):
            validate_samples(invalid_method)

        unexpected = copy.deepcopy(VALID_SAMPLES)
        unexpected["unreviewedOverride"] = True
        with self.assertRaisesRegex(ValueError, "unexpected or missing"):
            validate_samples(unexpected)


if __name__ == "__main__":
    unittest.main()
