"""Fail-closed controls for CAP-04.S03 calibration and fresh qualification."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from research_observatory_core.reconciliation import candidates, feature_cache

from tests.reconciliation import performance_workload

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import reconciliation_performance_check as check  # noqa: E402


def sample():
    return {
        "kernel": {
            "fixtureVersion": "dblp-acm-benchmark-v1/qualification",
            "records": 2463,
            "comparisons": 105451,
            "returnedPairs": 1273,
            "crossSourceReturnedPairs": 1142,
            "truePositives": 1092,
            "goldPairs": 1115,
            "precision": 1092 / 1142,
            "recall": 1092 / 1115,
            "preparedEquivalent": True,
            "coldSeconds": 1.0,
            "preparationSeconds": 1.0,
            "preparedRetrievalSeconds": 1.0,
        },
        "protected": {
            "fixtureVersion": "synthetic-protected-reconciliation-202-v1",
            "acceptedImportRecords": 202,
            "retainedConnectorRecords": 1,
            "recordCount": 203,
            "candidateCount": 103,
            "candidateDigestSha256": "a" * 64,
            "coldWarmCandidateContentEqual": True,
            "batches": [
                {"phase": "cold", "seconds": 1.0, "newJob": True, "newRequest": True, "featureComputations": None},
                {"phase": "warm", "seconds": 1.0, "newJob": True, "newRequest": True, "featureComputations": 0},
            ],
            "pages": [{"after": 0, "items": 100, "seconds": 1.0}, {"after": 100, "items": 3, "seconds": 1.0}],
            "workerCapacitySubstitutedDuringSetup": True,
            "workerCapacitySubstitutedDuringMeasurement": False,
            "actualDPAPIAndSQLCipher": True,
            "providerNetworkDuringMeasurement": 0,
        },
        "memory": {"peakWorkingSetSize": 100000000},
    }


class ReconciliationPerformanceCheckTests(unittest.TestCase):
    def baseline(self):
        metrics = check.sample_metrics(sample())
        return {
            "method": check.METHOD,
            "maxima": metrics,
            "calibration": {"performanceQualifying": False, "rawMetrics": [metrics.copy() for _ in range(3)]},
        }

    def validate(self, value):
        raw = json.dumps(value).encode()
        with patch.object(check, "BASELINE_SHA256", hashlib.sha256(raw).hexdigest()):
            return check.validate_baseline(raw)

    def test_reviewed_baseline_binds_all_raw_samples_and_absolute_ceilings(self):
        value = self.baseline()
        self.assertEqual(value, self.validate(value))
        with self.assertRaisesRegex(ValueError, "reviewed bytes"):
            check.validate_baseline(json.dumps(value).encode())
        for mutate in (
            lambda item: item["maxima"].update({"laterPageSeconds": float("nan")}),
            lambda item: item["maxima"].update({"laterPageSeconds": 21}),
            lambda item: item["maxima"].update({"laterPageSeconds": 2}),
            lambda item: item["calibration"].update(rawMetrics=[]),
            lambda item: item["calibration"].update(performanceQualifying=True),
        ):
            changed = copy.deepcopy(value)
            mutate(changed)
            with self.assertRaises(ValueError):
                self.validate(changed)

    def test_sample_rejects_changed_corpus_incomplete_pages_and_false_warm_cache(self):
        value = sample()
        self.assertEqual(set(check.CEILINGS), set(check.sample_metrics(value)))
        for mutate in (
            lambda item: item["kernel"].update(comparisons=105450),
            lambda item: item["kernel"].update(precision=0.1),
            lambda item: item["protected"].update(recordCount=202),
            lambda item: item["protected"].update(pages=item["protected"]["pages"][:1]),
            lambda item: item["protected"]["batches"][1].update(featureComputations=202),
            lambda item: item["protected"]["batches"][1].update(newJob=False),
            lambda item: item["protected"].update(workerCapacitySubstitutedDuringMeasurement=True),
            lambda item: item["kernel"].update(coldSeconds=float("inf")),
        ):
            changed = copy.deepcopy(value)
            mutate(changed)
            with self.assertRaises(ValueError):
                check.sample_metrics(changed)

    def test_every_metric_of_every_sample_is_gated_without_averaging(self):
        baseline = self.baseline()
        metrics = check.sample_metrics(sample())
        check.validate_metrics(metrics, baseline)
        metrics["protectedWarmSeconds"] = 1.201
        with self.assertRaisesRegex(ValueError, "protectedWarmSeconds"):
            check.validate_metrics(metrics, baseline)

    def test_failed_prerequisite_replaces_stale_pass(self):
        @contextmanager
        def fail():
            raise ValueError("synthetic setup rejection")
            yield

        with tempfile.TemporaryDirectory(
            prefix="reconciliation-performance-control-", dir=REPO / "artifacts/tmp"
        ) as folder:
            destination = Path(folder) / "report.json"
            destination.write_text('{"status":"PASS","performanceQualifying":true}', encoding="utf-8")
            with patch.object(check, "fixed_inputs", fail), self.assertRaisesRegex(ValueError, "setup rejection"):
                check.run(destination)
            result = json.loads(destination.read_text("utf-8"))
            self.assertEqual("FAIL", result["status"])
            self.assertFalse(result["performanceQualifying"])

    def test_child_uses_fresh_bytecode_and_rejects_duplicate_sample_directory(self):
        with tempfile.TemporaryDirectory(
            prefix="reconciliation-performance-child-", dir=REPO / "artifacts/tmp"
        ) as folder:
            directory = Path(folder)
            captured: dict[str, Any] = {}

            def spawn(command, **kwargs):
                captured.update(command=command, environment=kwargs["env"])
                Path(command[-1]).write_text(json.dumps(sample()), encoding="utf-8")
                return Mock(wait=Mock(return_value=0), poll=Mock(return_value=0))

            with patch.object(check.subprocess, "Popen", side_effect=spawn):
                check.child(1, directory)
            self.assertIn("-B", captured["command"])
            self.assertEqual(
                directory / "sample-1/unused-bytecode", Path(captured["environment"]["PYTHONPYCACHEPREFIX"])
            )
            with self.assertRaises(FileExistsError):
                check.child(1, directory)

    def test_final_publication_fault_keeps_nonqualifying_status(self):
        baseline = self.baseline()
        with tempfile.TemporaryDirectory(
            prefix="reconciliation-performance-final-", dir=REPO / "artifacts/tmp"
        ) as folder:
            destination = Path(folder) / "report.json"

            @contextmanager
            def fixed():
                yield "a" * 40, {check.BASELINE: json.dumps(baseline).encode()}, {}, {}, lambda: None

            def fault(*_args):
                raise ValueError("synthetic final publication fault")

            with (
                patch.object(check, "fixed_inputs", fixed),
                patch.object(check, "validate_baseline", return_value=baseline),
                patch.object(check, "hardware_record", return_value={"physicalMemoryBytes": 1}),
                patch.object(check.subprocess, "run"),
                patch.object(check, "git_blob_sha256", return_value="b" * 64),
                patch.object(check, "child", return_value=(sample(), {})),
                patch.object(check, "guarded_final_publication", side_effect=fault),
                self.assertRaisesRegex(ValueError, "final publication fault"),
            ):
                baseline["hardware"] = {"physicalMemoryBytes": 1}
                baseline["calibration"].update(commit="a" * 40, toolSha256="b" * 64)
                check.run(destination)
            result = json.loads(destination.read_text("utf-8"))
            self.assertEqual("FAIL", result["status"])
            self.assertFalse(result["performanceQualifying"])

    def test_warm_observer_catches_computation_during_enqueue(self):
        record = candidates.CandidateRecord("synthetic:1", "revision-1", (("title", ("Synthetic title",)),))

        def post(route, **_body):
            if route == "batches/prepare":
                return {"requestId": "request-2"}
            if route == "batches/schedule":
                feature_cache.prepare_record(record)
                return {"jobId": "job-2"}
            return {"state": "succeeded", "setRevisionId": "set-2"}

        with self.assertRaisesRegex(AssertionError, "warm batch recomputed"):
            performance_workload._run_batch(post, Mock(run_pending=Mock()), "warm")

    def test_paged_output_rejects_repeats_and_substitution_at_exact_ordinal(self):
        expected = tuple(hashlib.sha256(str(index).encode()).hexdigest() for index in range(103))
        pages = ((0, expected[:100]), (100, expected[100:]))
        self.assertIsInstance(performance_workload._verify_page_digests(pages, expected), str)
        with self.assertRaisesRegex(AssertionError, "candidate page"):
            performance_workload._verify_page_digests(((0, expected[:100]), (100, expected[:3])), expected)
        with self.assertRaisesRegex(AssertionError, "candidate page"):
            performance_workload._verify_page_digests(
                ((0, expected[:100]), (100, (expected[100], expected[101], expected[0]))), expected
            )
