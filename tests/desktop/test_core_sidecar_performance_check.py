from __future__ import annotations

import copy
import json
import math
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import core_sidecar_performance_check as benchmark  # noqa: E402


class CoreSidecarPerformanceContractTests(unittest.TestCase):
    baseline: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = json.loads((ROOT / benchmark.BASELINE_PATH).read_text(encoding="utf-8"))

    def test_committed_baseline_is_exact_and_immutable(self) -> None:
        validated = benchmark.validate_baseline(self.baseline)
        self.assertEqual("windows-x64", validated["profile"])
        self.assertEqual(
            benchmark.EXPECTED_BASELINE_SHA256,
            benchmark.sha256(ROOT / benchmark.BASELINE_PATH),
        )

    def test_baseline_rejects_nonfinite_or_laundered_measurements(self) -> None:
        for measurement, field, value in (
            ("readinessMs", "baselineP50", math.nan),
            ("readinessMs", "baselineP50", 3_001.0),
            ("shutdownMs", "baselineP95", math.inf),
            ("idleWorkingSetBytes", "baselineP95", 268_435_457),
        ):
            with self.subTest(measurement=measurement, value=value):
                invalid = copy.deepcopy(self.baseline)
                invalid["measurements"][measurement][field] = value
                with self.assertRaises(ValueError):
                    benchmark.validate_baseline(invalid)

    def test_evaluation_enforces_absolute_and_relative_boundaries(self) -> None:
        report = {
            "fixture": {"buildContractSha256": self.baseline["fixture"]["buildContractSha256"]},
            "rawMeasurements": {
                "readinessMs": {"p50": 997.0},
                "shutdownMs": {"p95": 200.0},
                "idleWorkingSetBytes": {"p95": 60_000_000.0},
            },
        }
        evaluated = benchmark.evaluate(report, self.baseline, benchmark.EXPECTED_BASELINE_SHA256)
        self.assertFalse(evaluated["ok"])
        self.assertFalse(evaluated["measurements"]["readinessMs"]["passes"])
        self.assertTrue(evaluated["measurements"]["shutdownMs"]["passes"])


if __name__ == "__main__":
    unittest.main()
