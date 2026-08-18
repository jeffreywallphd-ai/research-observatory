from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import storage_maintenance_performance_check as benchmark  # noqa: E402


class StorageMaintenancePerformanceCheckTests(unittest.TestCase):
    @classmethod
    def baseline(cls) -> dict[str, object]:
        return json.loads((REPO / benchmark.BASELINE_PATH).read_text(encoding="utf-8"))

    def test_reviewed_baseline_retains_three_exact_calibration_distributions(self) -> None:
        raw = (REPO / benchmark.BASELINE_PATH).read_bytes()
        self.assertEqual(benchmark.EXPECTED_BASELINE_SHA256, hashlib.sha256(raw).hexdigest())

        baseline = benchmark.load_baseline(REPO)

        self.assertEqual(benchmark.EXPECTED_FIXTURE, baseline["fixture"])
        self.assertEqual(benchmark.EXPECTED_METHODOLOGY, baseline["methodology"])
        self.assertEqual(benchmark.CALIBRATION_CONTEXTS, tuple(run["context"] for run in baseline["calibrationRuns"]))
        for run in baseline["calibrationRuns"]:
            self.assertEqual(run["recordSha256"], benchmark.calibration_record_hash(run))
            for name, retained in run["measurements"].items():
                benchmark.validate_retained_distribution(name, retained)

    def test_baseline_rejects_source_sample_and_threshold_laundering(self) -> None:
        mutations = []
        wrong_source = copy.deepcopy(self.baseline())
        wrong_source["source"]["implementationSha256"] = "0" * 64  # type: ignore[index]
        mutations.append(wrong_source)
        changed_sample = copy.deepcopy(self.baseline())
        changed_sample["calibrationRuns"][0]["measurements"]["cleanup"]["samplesMs"][0] = 1.0  # type: ignore[index]
        mutations.append(changed_sample)
        relaxed_latency = copy.deepcopy(self.baseline())
        relaxed_latency["measurements"]["cleanup"]["absoluteBudgetMs"] = 10_000.0  # type: ignore[index]
        mutations.append(relaxed_latency)
        relaxed_throughput = copy.deepcopy(self.baseline())
        relaxed_throughput["measurements"]["putPdf"]["absoluteBudgetMiBPerSecond"] = 1.0  # type: ignore[index]
        mutations.append(relaxed_throughput)

        for index, mutation in enumerate(mutations):
            with tempfile.TemporaryDirectory(dir=REPO / "artifacts" / "tmp") as temporary:
                candidate = Path(temporary) / f"baseline-{index}.json"
                raw = (json.dumps(mutation, indent=2) + "\n").encode()
                candidate.write_bytes(raw)
                with (
                    self.subTest(index=index),
                    patch.object(benchmark, "BASELINE_PATH", candidate.relative_to(REPO)),
                    patch.object(benchmark, "EXPECTED_BASELINE_SHA256", hashlib.sha256(raw).hexdigest()),
                    self.assertRaises(ValueError),
                ):
                    benchmark.load_baseline(REPO)

    def test_distributions_retain_all_samples_and_use_nearest_rank(self) -> None:
        samples = [float(index) for index in range(1, benchmark.REPETITIONS + 1)]

        latency = benchmark.distribution(samples, unit="Ms")
        throughput = benchmark.distribution(samples, unit="MiBPerSecond")

        self.assertEqual(samples, latency["samplesMs"])
        self.assertEqual(5.0, latency["p50Ms"])
        self.assertEqual(10.0, latency["p95Ms"])
        self.assertEqual(samples, throughput["samplesMiBPerSecond"])
        with self.assertRaises(ValueError):
            benchmark.distribution(samples[:-1], unit="Ms")
        with self.assertRaises(ValueError):
            benchmark.distribution(samples, unit="seconds")

    def test_latency_and_throughput_use_unrounded_gate_values(self) -> None:
        latency = benchmark.evaluated_latency([120.0004] * benchmark.REPETITIONS, 100.0, 500.0)
        throughput = benchmark.evaluated_throughput([79.9996] * benchmark.REPETITIONS, 100.0, 5.0)

        self.assertEqual(120.0, latency["p95Ms"])
        self.assertFalse(latency["passesRegressionThreshold"])
        self.assertEqual(80.0, throughput["p50MiBPerSecond"])
        self.assertFalse(throughput["passesRegressionThreshold"])
        absolute_latency = benchmark.evaluated_latency([500.0004] * benchmark.REPETITIONS, 1_000.0, 500.0)
        absolute_throughput = benchmark.evaluated_throughput([4.9996] * benchmark.REPETITIONS, 1.0, 5.0)
        self.assertFalse(absolute_latency["passesAbsoluteBudget"])
        self.assertFalse(absolute_throughput["passesAbsoluteBudget"])

    def test_measure_only_report_is_explicitly_nonqualifying(self) -> None:
        samples = {name: [10.0] * benchmark.REPETITIONS for name in benchmark.MEASUREMENT_KINDS}

        report = benchmark.build_report(REPO, "c" * 40, samples, measure_only=True)

        self.assertFalse(report["ok"])
        self.assertFalse(report["qualified"])
        self.assertIn("not qualification evidence", report["errors"][0])

    def test_qualification_applies_every_absolute_and_relative_gate(self) -> None:
        baseline = benchmark.load_baseline(REPO)
        samples: dict[str, list[float]] = {}
        for name, kind in benchmark.MEASUREMENT_KINDS.items():
            field = "baselineP95Ms" if kind == "maximum-latency" else "baselineP50MiBPerSecond"
            samples[name] = [float(baseline["measurements"][name][field])] * benchmark.REPETITIONS

        with patch.object(benchmark, "load_baseline", return_value=baseline):
            passing = benchmark.build_report(REPO, "c" * 40, samples, measure_only=False)
            failing_samples = copy.deepcopy(samples)
            failing_samples["cleanup"] = [10_000.0] * benchmark.REPETITIONS
            failing = benchmark.build_report(REPO, "c" * 40, failing_samples, measure_only=False)

        self.assertTrue(passing["ok"])
        self.assertTrue(passing["qualified"])
        self.assertFalse(failing["ok"])
        self.assertFalse(failing["qualified"])

    def test_measurement_failure_replaces_a_stale_qualifying_report(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts" / "tmp") as temporary:
            destination = Path(temporary) / "performance.json"
            destination.write_text('{"ok":true,"qualified":true,"sentinel":"stale"}\n', encoding="utf-8")
            with (
                patch.object(benchmark, "clean_state_commit", return_value="c" * 40),
                patch.object(benchmark, "measure", side_effect=ValueError("measurement failed")),
            ):
                report, code = benchmark.run(REPO, destination, measure_only=True)

            self.assertEqual(1, code)
            self.assertFalse(report["ok"])
            persisted = json.loads(destination.read_text(encoding="utf-8"))
            self.assertFalse(persisted["qualified"])
            self.assertNotIn("stale", persisted.values())


if __name__ == "__main__":
    unittest.main()
