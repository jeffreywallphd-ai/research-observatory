"""Fail-closed controls for the CAP-04.S04 protected benchmark."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import corpus_report_performance_check as check  # noqa: E402


def sample() -> dict:
    return {
        "fixtureVersion": check.METHOD["fixtureVersion"],
        "itemCount": 64,
        "discoveryPathCount": 67,
        "sourceRootCount": 4,
        "sourcePairCount": 6,
        "actualDPAPIAndSQLCipher": True,
        "providerNetworkDuringMeasurement": 0,
        "timings": {
            "incrementalUpdateSeconds": 1.0,
            "firstReportAfterReopenAndUpdateSeconds": 1.0,
            "repeatReportSeconds": 1.0,
            "inspectSeconds": 1.0,
            "firstDrillPageSeconds": 1.0,
            "laterDrillPageSeconds": 1.0,
        },
        "pageSizes": [32, 32],
        "databaseBytes": {"before": 1_000_000, "afterUpdate": 1_010_000, "afterReport": 1_020_000},
        "memory": {"peakWorkingSetSize": 200_000_000},
    }


class CorpusReportPerformanceControls(unittest.TestCase):
    def baseline(self) -> dict:
        metrics = check.sample_metrics(sample())
        return {
            "method": check.METHOD,
            "maxima": metrics,
            "calibration": {
                "performanceQualifying": False,
                "workloadSha256": "a" * 64,
                "rawMetrics": [metrics.copy() for _ in range(3)],
            },
        }

    def validated(self, value: dict) -> dict:
        raw = json.dumps(value).encode()
        with patch.object(check, "BASELINE_SHA256", hashlib.sha256(raw).hexdigest()):
            return check.validate_baseline(raw)

    def test_baseline_binds_reviewed_bytes_every_raw_sample_and_hard_ceiling(self) -> None:
        value = self.baseline()
        self.assertEqual(value, self.validated(value))
        with self.assertRaisesRegex(ValueError, "baseline differs"):
            check.validate_baseline(json.dumps(value).encode())
        for mutate in (
            lambda item: item["maxima"].update(repeatReportSeconds=float("nan")),
            lambda item: item["maxima"].update(repeatReportSeconds=61),
            lambda item: item["maxima"].update(repeatReportSeconds=2),
            lambda item: item["calibration"].update(rawMetrics=[]),
            lambda item: item["calibration"].update(performanceQualifying=True),
        ):
            changed = copy.deepcopy(value)
            mutate(changed)
            with self.assertRaises(ValueError):
                self.validated(changed)

    def test_sample_rejects_fixture_substitution_incomplete_drill_and_nonfinite_metrics(self) -> None:
        original = sample()
        self.assertEqual(set(check.CEILINGS), set(check.sample_metrics(original)))
        for mutate in (
            lambda item: item.update(itemCount=63),
            lambda item: item.update(sourcePairCount=1),
            lambda item: item.update(pageSizes=[32, 31]),
            lambda item: item.update(providerNetworkDuringMeasurement=1),
            lambda item: item["timings"].update(repeatReportSeconds=float("inf")),
            lambda item: item["databaseBytes"].update(before=-1),
        ):
            changed = copy.deepcopy(original)
            mutate(changed)
            with self.assertRaises(ValueError):
                check.sample_metrics(changed)

    def test_every_metric_of_every_sample_is_gated(self) -> None:
        baseline = self.baseline()
        metrics = check.sample_metrics(sample())
        check.validate_metrics(metrics, baseline)
        metrics["repeatReportSeconds"] = 1.201
        with self.assertRaisesRegex(ValueError, "repeatReportSeconds"):
            check.validate_metrics(metrics, baseline)

    def test_qualification_binds_calibration_and_current_workload_bytes(self) -> None:
        raw = b"reviewed synthetic workload"
        digest = hashlib.sha256(raw).hexdigest()
        placeholder = b'BASELINE_SHA256 = "PENDING-INDEPENDENT-BASELINE-REVIEW"'
        current = (REPO / check.TOOL).read_bytes()
        current_assignment = f'BASELINE_SHA256 = "{check.BASELINE_SHA256}"'.encode()
        producer = current.replace(current_assignment, placeholder, 1)
        pinned = producer.replace(placeholder, b'BASELINE_SHA256 = "' + b"f" * 64 + b'"', 1)
        tool_sha = hashlib.sha256(producer).hexdigest()
        baseline = {"calibration": {"commit": "a" * 40, "toolSha256": tool_sha, "workloadSha256": digest}}

        def committed(_repo, _commit, path):
            return tool_sha if path == check.TOOL else digest

        with (
            patch.object(check, "BASELINE_SHA256", "f" * 64),
            patch.object(check.subprocess, "run"),
            patch.object(check, "git_blob_sha256", side_effect=committed),
        ):
            captured = {check.TOOL: pinned, check.WORKLOAD: raw}
            check.verify_calibration_identity("c" * 40, captured, baseline)
            with self.assertRaisesRegex(ValueError, "current workload differs"):
                check.verify_calibration_identity("c" * 40, {**captured, check.WORKLOAD: b"changed"}, baseline)
            with self.assertRaisesRegex(ValueError, "current runner differs"):
                check.verify_calibration_identity("c" * 40, {**captured, check.TOOL: pinned + b"# changed"}, baseline)
        with (
            patch.object(check, "BASELINE_SHA256", "f" * 64),
            patch.object(check.subprocess, "run"),
            patch.object(check, "git_blob_sha256", return_value=tool_sha),
            self.assertRaisesRegex(ValueError, "calibration workload blob mismatch"),
        ):
            check.verify_calibration_identity("c" * 40, {check.TOOL: pinned, check.WORKLOAD: raw}, baseline)

    def test_failed_prerequisite_invalidates_stale_pass(self) -> None:
        @contextmanager
        def fail():
            raise ValueError("synthetic setup rejection")
            yield

        with tempfile.TemporaryDirectory(
            prefix="corpus-report-performance-control-", dir=REPO / "artifacts/tmp"
        ) as folder:
            destination = Path(folder) / "report.json"
            destination.write_text('{"status":"PASS","performanceQualifying":true}', encoding="utf-8")
            with patch.object(check, "fixed_inputs", fail), self.assertRaisesRegex(ValueError, "setup rejection"):
                check.run(destination)
            report = json.loads(destination.read_text("utf-8"))
            self.assertEqual("FAIL", report["status"])
            self.assertFalse(report["performanceQualifying"])

    def test_calibration_without_baseline_remains_nonqualifying(self) -> None:
        @contextmanager
        def fixed():
            yield "a" * 40, {}, {}, {}, lambda: None

        with tempfile.TemporaryDirectory(
            prefix="corpus-report-calibration-control-", dir=REPO / "artifacts/tmp"
        ) as folder:
            destination = Path(folder) / "report.json"
            with (
                patch.object(check, "fixed_inputs", fixed),
                patch.object(check, "hardware_record", return_value={"physicalMemoryBytes": 1}),
                patch.object(check, "child", return_value=(sample(), {})),
            ):
                self.assertEqual(0, check.run(destination, calibration=True))
            report = json.loads(destination.read_text("utf-8"))
            self.assertEqual("MEASURED", report["status"])
            self.assertFalse(report["performanceQualifying"])
            self.assertIsNone(report["baselineSha256"])
            self.assertEqual(3, len(report["samples"]))

    def test_final_publication_fault_cannot_leave_qualifying_pass(self) -> None:
        @contextmanager
        def fixed():
            yield "a" * 40, {}, {}, {}, lambda: None

        with tempfile.TemporaryDirectory(
            prefix="corpus-report-publication-control-", dir=REPO / "artifacts/tmp"
        ) as folder:
            destination = Path(folder) / "report.json"
            with (
                patch.object(check, "fixed_inputs", fixed),
                patch.object(check, "hardware_record", return_value={"physicalMemoryBytes": 1}),
                patch.object(check, "child", return_value=(sample(), {})),
                patch.object(check, "guarded_final_publication", side_effect=ValueError("publication fault")),
                self.assertRaisesRegex(ValueError, "publication fault"),
            ):
                check.run(destination, calibration=True)
            report = json.loads(destination.read_text("utf-8"))
            self.assertEqual("FAIL", report["status"])
            self.assertFalse(report["performanceQualifying"])
