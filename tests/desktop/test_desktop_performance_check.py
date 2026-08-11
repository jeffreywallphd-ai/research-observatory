from __future__ import annotations

import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_performance_check import (  # noqa: E402
    EXPECTED_PERFORMANCE_BASELINE_SHA256,
    EXPECTED_UI_COMPONENT_BASELINE_METHODOLOGY,
    EXPECTED_UI_COMPONENT_BASELINE_P95_MS,
    EXPECTED_UI_COMPONENT_BASELINE_SHA256,
    EXPECTED_UI_COMPONENT_FIXTURE,
    EXPECTED_UI_COMPONENT_SAMPLE_METHODOLOGY,
    PERFORMANCE_BASELINE_PATH,
    RELATIVE_REGRESSION_PERCENT,
    UI_COMPONENT_BASELINE_PATH,
    UI_COMPONENT_BATCH_BUDGET_MS,
    approved_document_name,
    canonical_text_sha256,
    distribution,
    evaluated_measurement,
    hardware_record,
    percentile,
    validate_regression_baseline,
    validate_ui_component_baseline,
    validate_ui_component_samples,
)

VALID_BASELINE: dict[str, Any] = {
    "schemaVersion": "1.0",
    "documentType": "desktop-performance-baseline",
    "baselineSourceCommit": "a" * 40,
    "profile": "windows-x64",
    "referenceId": "RO-UI-ACADEMIC-MINIMAL-1.3",
    "fixture": {
        "applicationManifestSha256": "b" * 64,
        "runtimeSha256": "c" * 64,
        "referencePackageSha256": "d" * 64,
    },
    "methodology": {
        "browserEngine": "chromium",
        "browserVersion": "145.0.7632.6",
        "playwrightVersion": "1.58.0",
        "cpuThrottleRate": 1,
        "hardwareQualification": "representative measured Windows x64 workstation",
        "repetitions": 12,
        "regressionThresholdPercent": 20,
    },
    "measurements": {
        "coldShellFirstContentfulPaint": {"absoluteBudgetMs": 2500.0, "baselineP95Ms": 96.0},
        "warmRouteVisibleSkeleton": {"absoluteBudgetMs": 150.0, "baselineP95Ms": 73.033},
        "warmRouteUsable": {"absoluteBudgetMs": 1000.0, "baselineP95Ms": 77.622},
    },
}

VALID_UI_COMPONENT_BASELINE: dict[str, Any] = {
    "schemaVersion": "1.0",
    "documentType": "ui-component-performance-baseline",
    "baselineSourceCommit": "a" * 40,
    "profile": "windows-x64",
    "componentContractVersion": "1.2.0",
    "fixture": {
        **EXPECTED_UI_COMPONENT_FIXTURE,
        "benchmarkEntrySha256": "b" * 64,
        "benchmarkRunnerSha256": "c" * 64,
    },
    "methodology": EXPECTED_UI_COMPONENT_BASELINE_METHODOLOGY,
    "measurements": {
        "warmPaginatedRenderBatch": {
            "absoluteBudgetMs": UI_COMPONENT_BATCH_BUDGET_MS,
            "baselineP95Ms": EXPECTED_UI_COMPONENT_BASELINE_P95_MS,
        }
    },
}

VALID_UI_COMPONENT_SAMPLES: dict[str, Any] = {
    "schemaVersion": "1.0",
    "documentType": "ui-component-performance-samples",
    "fixture": {
        **EXPECTED_UI_COMPONENT_FIXTURE,
        "firstPageMarkupBytes": 4_879,
        "lastPageMarkupBytes": 4_997,
    },
    "methodology": EXPECTED_UI_COMPONENT_SAMPLE_METHODOLOGY,
    "samplesMs": [40.0] * 20,
}


class DesktopPerformanceCheckTests(unittest.TestCase):
    def test_governed_text_hash_is_stable_across_clean_windows_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fixture.tsx"
            fixture.write_bytes(b"export const rows = 10000;\n")
            lf_hash = canonical_text_sha256(fixture)
            fixture.write_bytes(b"export const rows = 10000;\r\n")
            self.assertEqual(lf_hash, canonical_text_sha256(fixture))

            fixture.write_bytes(b"export const rows = 9999;\r\n")
            self.assertNotEqual(lf_hash, canonical_text_sha256(fixture))
            fixture.write_bytes(b"export const rows = 10000;\r")
            with self.assertRaisesRegex(ValueError, "bare carriage return"):
                canonical_text_sha256(fixture)

    def test_nearest_rank_distribution_retains_every_sample(self) -> None:
        samples = [10.0, 50.0, 20.0, 40.0, 30.0]

        self.assertEqual(30.0, percentile(samples, 0.5))
        self.assertEqual(50.0, percentile(samples, 0.95))
        self.assertEqual([10.0, 50.0, 20.0, 40.0, 30.0], distribution(samples)["samplesMs"])

    def test_measurement_enforces_budget_and_records_relative_threshold(self) -> None:
        measurement = evaluated_measurement([10.0, 11.0, 12.0, 13.0, 14.0], 20.0, 14.0)

        self.assertTrue(measurement["passesAbsoluteBudget"])
        self.assertTrue(measurement["passesRegressionThreshold"])
        self.assertEqual(
            RELATIVE_REGRESSION_PERCENT, measurement["futureRegressionThreshold"]["maximumIncreasePercent"]
        )
        self.assertEqual(16.8, measurement["futureRegressionThreshold"]["maximumFutureP95Ms"])
        self.assertFalse(evaluated_measurement([10.0, 11.0, 12.0, 13.0, 21.0], 20.0, 14.0)["passesAbsoluteBudget"])

    def test_measurement_rejects_regression_below_absolute_budget(self) -> None:
        measurement = evaluated_measurement([200.0] * 5, 2500.0, 96.0)

        self.assertTrue(measurement["passesAbsoluteBudget"])
        self.assertFalse(measurement["passesRegressionThreshold"])
        self.assertEqual(96.0, measurement["futureRegressionThreshold"]["baselineP95Ms"])
        self.assertEqual(115.2, measurement["futureRegressionThreshold"]["maximumFutureP95Ms"])

    def test_route_guard_requires_exact_local_origin_and_path(self) -> None:
        available = {"index.html", "study-design.html"}

        self.assertEqual("index.html", approved_document_name("http://tauri.localhost/index.html", available))
        self.assertEqual(
            "study-design.html",
            approved_document_name("http://tauri.localhost/study-design.html", available),
        )
        for attack in (
            "https://evil.invalid/index.html",
            "http://evil.invalid/study-design.html",
            "http://tauri.localhost.evil.invalid/index.html",
            "http://tauri.localhost@evil.invalid/index.html",
            "http://tauri.localhost:80/index.html",
            "http://tauri.localhost/nested/index.html",
            "http://tauri.localhost/%69ndex.html",
            "http://tauri.localhost/index.html?external=true",
        ):
            with self.subTest(attack=attack):
                self.assertIsNone(approved_document_name(attack, available))

    def test_regression_baseline_is_strict_and_preserves_budgets(self) -> None:
        self.assertEqual(VALID_BASELINE, validate_regression_baseline(copy.deepcopy(VALID_BASELINE)))
        self.assertEqual(
            EXPECTED_PERFORMANCE_BASELINE_SHA256,
            hashlib.sha256((REPO / PERFORMANCE_BASELINE_PATH).read_bytes()).hexdigest(),
        )

        for field, replacement in (
            ("schemaVersion", "2.0"),
            ("baselineSourceCommit", "short"),
            ("profile", "cloud"),
        ):
            invalid = copy.deepcopy(VALID_BASELINE)
            invalid[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_regression_baseline(invalid)

        invalid_budget = copy.deepcopy(VALID_BASELINE)
        invalid_budget["measurements"]["coldShellFirstContentfulPaint"]["absoluteBudgetMs"] = 2501.0
        with self.assertRaisesRegex(ValueError, "approved budget"):
            validate_regression_baseline(invalid_budget)

        for numeric_value in (2000.0, float("nan"), float("inf")):
            invalid_p95 = copy.deepcopy(VALID_BASELINE)
            invalid_p95["measurements"]["coldShellFirstContentfulPaint"]["baselineP95Ms"] = numeric_value
            with self.subTest(replacement=numeric_value), self.assertRaises(ValueError):
                validate_regression_baseline(invalid_p95)

        unexpected = copy.deepcopy(VALID_BASELINE)
        unexpected["unreviewedOverride"] = True
        with self.assertRaisesRegex(ValueError, "unexpected or missing"):
            validate_regression_baseline(unexpected)

    def test_invalid_distribution_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least five"):
            distribution([1.0, 2.0, 3.0, 4.0])
        with self.assertRaisesRegex(ValueError, "probability"):
            percentile([1.0], 0.0)

    def test_hardware_record_is_actionable_without_host_identity(self) -> None:
        observed = hardware_record()

        self.assertEqual("Windows", observed["system"])
        self.assertEqual("AMD64", observed["machine"])
        self.assertGreater(observed["logicalCpuCount"], 0)
        self.assertGreater(observed["physicalMemoryBytes"], 0)
        self.assertNotIn("host", " ".join(observed).lower())

    def test_ui_component_baseline_is_strict_and_immutably_pinned(self) -> None:
        self.assertEqual(
            VALID_UI_COMPONENT_BASELINE,
            validate_ui_component_baseline(copy.deepcopy(VALID_UI_COMPONENT_BASELINE)),
        )
        self.assertEqual(
            EXPECTED_UI_COMPONENT_BASELINE_SHA256,
            hashlib.sha256((REPO / UI_COMPONENT_BASELINE_PATH).read_bytes()).hexdigest(),
        )

        for field, replacement in (
            ("schemaVersion", "2.0"),
            ("baselineSourceCommit", "short"),
            ("profile", "cloud"),
            ("componentContractVersion", "1.3.0"),
        ):
            invalid = copy.deepcopy(VALID_UI_COMPONENT_BASELINE)
            invalid[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_ui_component_baseline(invalid)

    def test_ui_component_baseline_rejects_laundered_budget_p95_and_methodology(self) -> None:
        invalid_budget = copy.deepcopy(VALID_UI_COMPONENT_BASELINE)
        invalid_budget["measurements"]["warmPaginatedRenderBatch"]["absoluteBudgetMs"] = 101.0
        with self.assertRaisesRegex(ValueError, "approved budget"):
            validate_ui_component_baseline(invalid_budget)

        for replacement in (90.0, float("nan"), float("inf"), 0.0):
            invalid_p95 = copy.deepcopy(VALID_UI_COMPONENT_BASELINE)
            invalid_p95["measurements"]["warmPaginatedRenderBatch"]["baselineP95Ms"] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                validate_ui_component_baseline(invalid_p95)

        invalid_method = copy.deepcopy(VALID_UI_COMPONENT_BASELINE)
        invalid_method["methodology"]["rendersPerSample"] = 1
        with self.assertRaisesRegex(ValueError, "methodology"):
            validate_ui_component_baseline(invalid_method)

    def test_ui_component_samples_bind_all_rows_to_a_bounded_window(self) -> None:
        self.assertEqual(
            [40.0] * 20,
            validate_ui_component_samples(copy.deepcopy(VALID_UI_COMPONENT_SAMPLES)),
        )

        for field, replacement in (
            ("totalRows", 9_999),
            ("pageSize", 51),
            ("pageCount", 199),
            ("maximumRenderedRows", 51),
        ):
            invalid = copy.deepcopy(VALID_UI_COMPONENT_SAMPLES)
            invalid["fixture"][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_ui_component_samples(invalid)

        incomplete = copy.deepcopy(VALID_UI_COMPONENT_SAMPLES)
        incomplete["samplesMs"] = [40.0] * 19
        with self.assertRaisesRegex(ValueError, "every governed repetition"):
            validate_ui_component_samples(incomplete)

        nonfinite = copy.deepcopy(VALID_UI_COMPONENT_SAMPLES)
        nonfinite["samplesMs"][0] = float("nan")
        with self.assertRaisesRegex(ValueError, "positive finite"):
            validate_ui_component_samples(nonfinite)

    def test_ui_component_samples_reject_methodology_and_output_shape_drift(self) -> None:
        invalid_method = copy.deepcopy(VALID_UI_COMPONENT_SAMPLES)
        invalid_method["methodology"]["warmupBatches"] = 0
        with self.assertRaisesRegex(ValueError, "methodology"):
            validate_ui_component_samples(invalid_method)

        unexpected = copy.deepcopy(VALID_UI_COMPONENT_SAMPLES)
        unexpected["unreviewedOverride"] = True
        with self.assertRaisesRegex(ValueError, "unexpected or missing"):
            validate_ui_component_samples(unexpected)


if __name__ == "__main__":
    unittest.main()
