from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import project_lifecycle_performance_check as benchmark  # noqa: E402


class ProjectLifecyclePerformanceCheckTests(unittest.TestCase):
    @classmethod
    def baseline(cls) -> dict[str, object]:
        return json.loads((REPO / benchmark.BASELINE_PATH).read_text(encoding="utf-8"))

    def test_reviewed_baseline_bytes_and_history_are_exact(self) -> None:
        raw = (REPO / benchmark.BASELINE_PATH).read_bytes()
        self.assertEqual(benchmark.EXPECTED_BASELINE_SHA256, hashlib.sha256(raw).hexdigest())
        baseline = benchmark.load_baseline(REPO)
        self.assertEqual(benchmark.EXPECTED_FIXTURE, baseline["fixture"])
        self.assertEqual(benchmark.EXPECTED_METHODOLOGY, baseline["methodology"])

    def test_baseline_rejects_identity_methodology_source_and_value_laundering(self) -> None:
        baseline = self.baseline()
        mutations = []
        wrong_profile = copy.deepcopy(baseline)
        wrong_profile["profile"] = "linux-x86_64"
        mutations.append(wrong_profile)
        wrong_method = copy.deepcopy(baseline)
        wrong_method["methodology"]["repetitions"] = 5  # type: ignore[index]
        mutations.append(wrong_method)
        wrong_source = copy.deepcopy(baseline)
        wrong_source["source"]["measurementToolPath"] = "tools/evil.py"  # type: ignore[index]
        mutations.append(wrong_source)
        inflated = copy.deepcopy(baseline)
        inflated["measurements"]["freshServiceOpen"]["baselineP95Ms"] = 499.0  # type: ignore[index]
        mutations.append(inflated)
        non_finite = copy.deepcopy(baseline)
        non_finite["measurements"]["warmServiceReopen"]["baselineP95Ms"] = math.nan  # type: ignore[index]
        mutations.append(non_finite)
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                benchmark.validate_baseline_document(mutation, benchmark.EXPECTED_BASELINE_SHA256)
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            benchmark.validate_baseline_document(baseline, "0" * 64)

    def test_distribution_retains_every_sample_and_uses_nearest_rank(self) -> None:
        samples = [float(index) for index in range(1, benchmark.REPETITIONS + 1)]
        result = benchmark.distribution(samples)
        self.assertEqual(samples, result["samplesMs"])
        self.assertEqual(10.0, result["p50Ms"])
        self.assertEqual(19.0, result["p95Ms"])
        with self.assertRaises(ValueError):
            benchmark.distribution(samples[:-1])

    def test_measurement_enforces_absolute_and_reviewed_relative_thresholds(self) -> None:
        passing = benchmark.evaluated_measurement([10.0] * benchmark.REPETITIONS, 10.0)
        self.assertTrue(passing["passesAbsoluteBudget"])
        self.assertTrue(passing["passesRegressionThreshold"])
        relative_failure = benchmark.evaluated_measurement([13.0] * benchmark.REPETITIONS, 10.0)
        self.assertTrue(relative_failure["passesAbsoluteBudget"])
        self.assertFalse(relative_failure["passesRegressionThreshold"])
        absolute_failure = benchmark.evaluated_measurement([501.0] * benchmark.REPETITIONS, 500.0)
        self.assertFalse(absolute_failure["passesAbsoluteBudget"])

    def test_measure_only_report_cannot_be_qualification_evidence(self) -> None:
        samples = {
            "freshServiceOpen": [10.0] * benchmark.REPETITIONS,
            "warmServiceReopen": [9.0] * benchmark.REPETITIONS,
        }
        fixture = {**benchmark.EXPECTED_FIXTURE, "manifestSha256": "a" * 64, "profileSha256": "b" * 64}
        with (
            patch.object(benchmark, "clean_state_commit", return_value="c" * 40),
            patch.object(benchmark, "measure", return_value=(samples, fixture)),
            patch.object(benchmark, "hardware_record", return_value={"machine": "AMD64"}),
        ):
            report = benchmark.benchmark(REPO, measure_only=True)
        self.assertFalse(report["ok"])
        self.assertFalse(report["qualified"])
        self.assertIn("not qualification evidence", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
