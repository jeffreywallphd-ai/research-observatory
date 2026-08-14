from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import tempfile
import unittest
from contextlib import nullcontext
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
        calibration_raw = (REPO / benchmark.CALIBRATION_PATH).read_bytes()
        self.assertEqual(benchmark.EXPECTED_CALIBRATION_SHA256, hashlib.sha256(calibration_raw).hexdigest())
        calibration = benchmark.load_calibration(REPO)
        raw = (REPO / benchmark.BASELINE_PATH).read_bytes()
        self.assertEqual(benchmark.EXPECTED_BASELINE_SHA256, hashlib.sha256(raw).hexdigest())
        baseline = benchmark.load_baseline(REPO, calibration)
        self.assertEqual(benchmark.EXPECTED_FIXTURE, baseline["fixture"])
        self.assertEqual(benchmark.EXPECTED_METHODOLOGY, baseline["methodology"])
        self.assertEqual(benchmark.calibration_summary(calibration), baseline["calibration"])

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
        calibration = benchmark.load_calibration(REPO)
        wrong_calibration = copy.deepcopy(baseline)
        wrong_calibration["calibration"]["runs"][0]["warmServiceReopenP95Ms"] = 499.0  # type: ignore[index]
        mutations.append(wrong_calibration)
        inflated = copy.deepcopy(baseline)
        inflated["measurements"]["freshServiceOpen"]["baselineP95Ms"] = 499.0  # type: ignore[index]
        mutations.append(inflated)
        non_finite = copy.deepcopy(baseline)
        non_finite["measurements"]["warmServiceReopen"]["baselineP95Ms"] = math.nan  # type: ignore[index]
        mutations.append(non_finite)
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                benchmark.validate_baseline_document(mutation, benchmark.EXPECTED_BASELINE_SHA256, calibration)
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            benchmark.validate_baseline_document(baseline, "0" * 64, calibration)

    def test_calibration_rejects_report_sample_hardware_and_source_laundering(self) -> None:
        raw = (REPO / benchmark.CALIBRATION_PATH).read_bytes()
        calibration = json.loads(raw.decode("utf-8"))
        mutations = []
        for section, field, value in (
            ("hardware", "processor", "substitute"),
            ("source", "measurementToolSha256", "0" * 64),
            ("measurements", "freshServiceOpen", None),
        ):
            changed = copy.deepcopy(calibration)
            if section == "hardware":
                changed[section][field] = value
            elif section == "source":
                changed["runs"][0][section][field] = value
            else:
                changed["runs"][0][section][field]["samplesMs"][0] = 499.0
            mutations.append(changed)
        for mutation in mutations:
            with self.subTest(), self.assertRaises(ValueError):
                benchmark.validate_calibration_document(mutation, benchmark.EXPECTED_CALIBRATION_SHA256)
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            benchmark.validate_calibration_document(calibration, "0" * 64)

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
        rounded_relative_false_green = benchmark.evaluated_measurement([20.1844] * benchmark.REPETITIONS, 16.82)
        self.assertEqual(20.184, rounded_relative_false_green["p95Ms"])
        self.assertFalse(rounded_relative_false_green["passesRegressionThreshold"])
        rounded_absolute_false_green = benchmark.evaluated_measurement([500.0004] * benchmark.REPETITIONS, 500.0)
        self.assertEqual(500.0, rounded_absolute_false_green["p95Ms"])
        self.assertFalse(rounded_absolute_false_green["passesAbsoluteBudget"])

    def test_measure_only_report_cannot_be_qualification_evidence(self) -> None:
        samples = {
            "freshServiceOpen": [10.0] * benchmark.REPETITIONS,
            "warmServiceReopen": [9.0] * benchmark.REPETITIONS,
        }
        fixture = {**benchmark.EXPECTED_FIXTURE, "manifestSha256": "a" * 64, "profileSha256": "b" * 64}
        calibration = benchmark.load_calibration(REPO)
        captured = {
            benchmark.TOOL_PATH: (REPO / benchmark.TOOL_PATH).read_bytes(),
            benchmark.IMPLEMENTATION_PATH: (REPO / benchmark.IMPLEMENTATION_PATH).read_bytes(),
        }
        with (
            patch.object(benchmark, "measure", return_value=(samples, fixture)),
            patch.object(benchmark, "hardware_record", return_value=calibration["hardware"]),
        ):
            report = benchmark._benchmark_under_snapshot(REPO, "c" * 40, captured, measure_only=True)
        self.assertFalse(report["ok"])
        self.assertFalse(report["qualified"])
        self.assertIn("not qualification evidence", report["errors"][0])

    def test_copied_tool_and_changed_state_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts" / "tmp") as temporary:
            copied = Path(temporary) / "copied.py"
            copied.write_bytes((REPO / benchmark.TOOL_PATH).read_bytes())
            with (
                patch.object(benchmark, "__file__", str(copied)),
                self.assertRaisesRegex(ValueError, "canonical"),
                benchmark.qualification_snapshot(REPO),
            ):
                self.fail("copied tool must not enter qualification")

        captured = {benchmark.IMPLEMENTATION_PATH: b"approved"}
        with (
            patch.object(benchmark, "clean_state_commit", return_value="a" * 40),
            patch.object(benchmark, "governed_snapshot", return_value=b"mutated"),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            benchmark.assert_committed_inputs(REPO, "a" * 40, captured)

    def test_failures_replace_stale_qualifying_report(self) -> None:
        captured = {
            benchmark.TOOL_PATH: b"tool",
            benchmark.IMPLEMENTATION_PATH: b"implementation",
        }
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts" / "tmp") as temporary:
            destination = Path(temporary) / "performance.json"
            destination.write_text('{"ok":true,"qualified":true}\n', encoding="utf-8")
            with (
                patch.object(benchmark, "qualification_snapshot", return_value=nullcontext(("c" * 40, captured))),
                patch.object(benchmark, "_benchmark_under_snapshot", side_effect=ValueError("measurement failed")),
            ):
                report, code = benchmark.run(REPO, destination)
            self.assertEqual(1, code)
            self.assertFalse(report["ok"])
            persisted = json.loads(destination.read_text(encoding="utf-8"))
            self.assertFalse(persisted["ok"])
            self.assertEqual("NONQUALIFYING", persisted["qualificationStatus"])
            self.assertIn("measurement failed", persisted["errors"])

    def test_persistent_final_publication_failure_leaves_initial_tombstone(self) -> None:
        captured = {
            benchmark.TOOL_PATH: b"tool",
            benchmark.IMPLEMENTATION_PATH: b"implementation",
        }
        passing = {"ok": True, "qualified": True, "sentinel": "new-pass"}
        original_writer = benchmark.guarded_atomic_write_json
        calls = 0

        def writer(repo: Path, destination: Path, value: object, scratch: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                original_writer(repo, destination, value, scratch)
                return
            raise OSError("permanent publication failure")

        with tempfile.TemporaryDirectory(dir=REPO / "artifacts" / "tmp") as temporary:
            destination = Path(temporary) / "performance.json"
            destination.write_text('{"ok":true,"qualified":true,"sentinel":"stale"}\n', encoding="utf-8")
            with (
                patch.object(benchmark, "qualification_snapshot", return_value=nullcontext(("c" * 40, captured))),
                patch.object(benchmark, "_benchmark_under_snapshot", return_value=passing),
                patch.object(benchmark, "guarded_atomic_write_json", side_effect=writer),
            ):
                report, code = benchmark.run(REPO, destination)
            self.assertEqual(1, code)
            self.assertFalse(report["ok"])
            self.assertEqual(3, calls)
            persisted = json.loads(destination.read_text(encoding="utf-8"))
            self.assertFalse(persisted["ok"])
            self.assertEqual("NONQUALIFYING", persisted["qualificationStatus"])
            self.assertEqual("IN_PROGRESS", persisted["qualificationPhase"])
            self.assertNotIn("stale", persisted.values())

    def test_success_replaces_initial_tombstone_with_pass(self) -> None:
        captured = {
            benchmark.TOOL_PATH: b"tool",
            benchmark.IMPLEMENTATION_PATH: b"implementation",
        }
        passing = {"ok": True, "qualified": True, "sentinel": "current-pass"}
        with tempfile.TemporaryDirectory(dir=REPO / "artifacts" / "tmp") as temporary:
            destination = Path(temporary) / "performance.json"
            destination.write_text('{"ok":true,"qualified":true,"sentinel":"stale"}\n', encoding="utf-8")
            with (
                patch.object(benchmark, "qualification_snapshot", return_value=nullcontext(("c" * 40, captured))),
                patch.object(benchmark, "_benchmark_under_snapshot", return_value=passing),
            ):
                report, code = benchmark.run(REPO, destination)
            self.assertEqual(0, code)
            self.assertEqual(passing, report)
            self.assertEqual(passing, json.loads(destination.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
