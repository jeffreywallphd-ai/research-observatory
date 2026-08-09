from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_performance_check import (  # noqa: E402
    RELATIVE_REGRESSION_PERCENT,
    approved_document_name,
    distribution,
    evaluated_measurement,
    hardware_record,
    percentile,
    validate_regression_baseline,
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


class DesktopPerformanceCheckTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
