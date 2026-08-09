from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_performance_check import (  # noqa: E402
    RELATIVE_REGRESSION_PERCENT,
    distribution,
    evaluated_measurement,
    hardware_record,
    percentile,
)


class DesktopPerformanceCheckTests(unittest.TestCase):
    def test_nearest_rank_distribution_retains_every_sample(self) -> None:
        samples = [10.0, 50.0, 20.0, 40.0, 30.0]

        self.assertEqual(30.0, percentile(samples, 0.5))
        self.assertEqual(50.0, percentile(samples, 0.95))
        self.assertEqual([10.0, 50.0, 20.0, 40.0, 30.0], distribution(samples)["samplesMs"])

    def test_measurement_enforces_budget_and_records_relative_threshold(self) -> None:
        measurement = evaluated_measurement([10.0, 11.0, 12.0, 13.0, 14.0], 20.0)

        self.assertTrue(measurement["passesAbsoluteBudget"])
        self.assertEqual(
            RELATIVE_REGRESSION_PERCENT, measurement["futureRegressionThreshold"]["maximumIncreasePercent"]
        )
        self.assertEqual(16.8, measurement["futureRegressionThreshold"]["maximumFutureP95Ms"])
        self.assertFalse(evaluated_measurement([10.0, 11.0, 12.0, 13.0, 21.0], 20.0)["passesAbsoluteBudget"])

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
