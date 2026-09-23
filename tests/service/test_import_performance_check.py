"""Focused acceptance controls; these do not execute the scale workloads."""

from __future__ import annotations

import copy
import json
import math
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "services/core-api/src")]

import import_performance_check as check  # noqa: E402


def sample(kind, baseline, head="synthetic-head"):
    return {
        "outcome": "functional-checks-passed-performance-diagnostic-only",
        "headBefore": head,
        "headAfter": head,
        "headUnchanged": True,
        "sourceInputsUnchanged": True,
        "fixtureVersion": baseline["fixtureVersion"],
        "source": baseline["source"],
        "bibliographicRecords": 100000,
        "lastJob": {"state": "succeeded", "attemptCount": 1, "diagnosticCode": None, "interruptionKind": None},
        "durableFacts": {
            "encryptedHeader": True,
            "canonicalRecords": 0 if kind == "review" else 100000,
            "parseRows": 100001,
            "summaryRows": 100001 if kind == "review" else 0,
            "summaryCompletions": 1 if kind == "review" else 0,
            "acceptedOutputs": 2,
        },
        "pageCoverage": (
            {
                "/projects/imports/records": {"pages": 1001, "records": 100001, "complete": True},
                "/projects/imports/summary/members": {"pages": 1000, "records": 100000, "complete": True},
            }
            if kind == "review"
            else {"/projects/imports/manifest/members": {"pages": 1001, "records": 100001, "complete": True}}
        ),
        "commitFacts": {
            "acceptedCommitOutputs": 1,
            "attempts": [{"attempt": 1, "state": "succeeded", "diagnosticCode": None}],
            "counts": {
                "import_commit_rows": 100001,
                "import_source_records": 100000,
                "import_manifests": 1,
                "import_manifest_members": 100001,
                "import_manifest_seals": 1,
            },
        },
        "stages": {
            "parse-worker" if kind == "review" else "parse-prerequisite": {"state": "passed", "seconds": 50},
            "summary-worker" if kind == "review" else "commit-worker": {"state": "passed", "seconds": 100},
        },
        "elapsedSeconds": 200,
        "memoryMaxObserved": {"peakWorkingSetSize": 100000000},
    }


def parser_sample():
    return {
        "fixtureVersion": "synthetic-repeated-metadata-v1",
        "measurements": [
            {"format": name, "repetition": repetition, "records": 100000, "seconds": 1, "peakTracedBytes": 10000}
            for name in ("ris", "bibtex", "csv")
            for repetition in (1, 2)
        ],
    }


class ImportPerformanceControlTests(unittest.TestCase):
    def setUp(self):
        self.raw = (check.REPO / check.BASELINE).read_bytes()
        self.baseline = check.baseline_document(self.raw)

    def test_baseline_is_immutable_and_ceilings_do_not_relax_observation_limits(self):
        with self.assertRaisesRegex(ValueError, "reviewed bytes"):
            check.baseline_document(self.raw + b" ")
        limits = check.ceilings(self.baseline, "commit")
        self.assertEqual((1200, 900, 184939315), tuple(limits.values()))
        for value in (float("nan"), float("inf"), -1, 0, True, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check.finite_positive(value)

    def test_each_sample_must_pass_not_just_the_median(self):
        for kind in ("review", "commit"):
            valid = sample(kind, self.baseline)
            check.validate_sample(kind, valid, self.baseline, "synthetic-head")
            for metric in ("elapsedSeconds", "workerSeconds", "peakWorkingSetBytes"):
                bad = copy.deepcopy(valid)
                value = check.ceilings(self.baseline, kind)[metric] + 1
                if metric == "workerSeconds":
                    bad["stages"]["summary-worker" if kind == "review" else "commit-worker"]["seconds"] = value
                elif metric == "peakWorkingSetBytes":
                    bad["memoryMaxObserved"]["peakWorkingSetSize"] = value
                else:
                    bad[metric] = value
                with self.subTest(kind=kind, metric=metric), self.assertRaisesRegex(ValueError, "exceeds"):
                    check.validate_sample(kind, bad, self.baseline, "synthetic-head")

    def test_drift_retry_missing_facts_and_partial_pages_fail(self):
        changes: tuple[dict[str, Any], ...] = (
            {"headAfter": "other"},
            {"sourceInputsUnchanged": False},
            {"retryObserved": True},
            {"durableFactsUnavailable": "synthetic failure"},
            {"durableFacts": {}},
            {"pageCoverage": {}},
            {"elapsedSeconds": math.nan},
            {"commitFacts": {}},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                check.validate_sample(
                    "commit", {**sample("commit", self.baseline), **change}, self.baseline, "synthetic-head"
                )

    def test_parser_inventory_and_exclusive_memory_ceiling(self):
        value = parser_sample()
        self.assertEqual(6, len(check.validate_parser(value, self.baseline)))
        for measurements in (
            value["measurements"][:-1],
            value["measurements"] + [value["measurements"][0]],
            [value["measurements"][0]] * 6,
        ):
            with self.assertRaises(ValueError):
                check.validate_parser({**value, "measurements": measurements}, self.baseline)
        value["measurements"][0]["peakTracedBytes"] = 16777216
        with self.assertRaisesRegex(ValueError, "memory overage"):
            check.validate_parser(value, self.baseline)

    def test_success_log_requires_one_unskipped_case_and_one_result(self):
        result = json.dumps(parser_sample()) + "\n"
        good = (result + "Ran 1 test in 1.234s\n\nOK\n").encode()
        self.assertEqual(parser_sample(), check.result_from_log(good, "parser"))
        for bad in (
            good.replace(b"OK", b"OK (skipped=1)"),
            good.replace(b"1 test", b"0 tests"),
            (result + result + "Ran 1 test in 1.234s\nOK\n").encode(),
            b"Ran 1 test in 1s\nOK\n",
        ):
            with self.assertRaises(ValueError):
                check.result_from_log(bad, "parser")

    def test_review_workload_rejects_retry_even_if_the_job_succeeded(self):
        from tests.service import test_import_review_scale_windows as scale

        case = scale.ImportReviewScaleWindowsTests(methodName="runTest")
        case.project_root, case.project_id, case.report = Path("synthetic"), "synthetic", {}
        job = SimpleNamespace(state="succeeded", attempt_count=2, diagnostic_code=None, interruption_kind=None)
        with patch.object(scale, "sqlite_workflow_queue_repository") as queue:
            queue.return_value.get.return_value = job
            with self.assertRaisesRegex(AssertionError, "retry observed"):
                case._wait_job("synthetic-job", timeout=1)
        self.assertTrue(case.report["retryObserved"])

    def test_failure_or_interrupt_invalidates_previous_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts/tmp").mkdir(parents=True)
            output = root / "artifacts/tmp/result.json"
            for failure in (ValueError("synthetic drift"), KeyboardInterrupt()):
                output.write_text('{"status":"PASS","performanceQualifying":true}')
                with (
                    patch.object(check, "REPO", root),
                    patch.object(check, "fixed_inputs", side_effect=failure),
                    self.assertRaises(type(failure)),
                ):
                    check.run(output)
                value = json.loads(output.read_text())
                self.assertEqual("FAIL", value["status"])
                self.assertFalse(value["performanceQualifying"])

    def test_final_input_drift_cannot_publish_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts/tmp").mkdir(parents=True)
            output = root / "artifacts/tmp/result.json"

            @contextmanager
            def fixed():
                def unchanged():
                    raise ValueError("synthetic final drift")

                yield "synthetic-head", {check.BASELINE: self.raw}, {}, {}, unchanged

            hardware = {
                "operatingSystem": self.baseline["hardware"]["system"],
                "machine": "AMD64",
                "logicalCpuCount": 20,
                "physicalMemoryBytes": 1000000000,
            }
            with (
                patch.object(check, "REPO", root),
                patch.object(check, "fixed_inputs", fixed),
                patch.object(check, "hardware_record", return_value=hardware),
                patch.object(check.platform, "python_version", return_value="3.14.6"),
                patch.object(check.subprocess, "run"),
                patch.object(check, "digest", return_value="synthetic"),
                patch.object(
                    check, "git_blob_sha256", side_effect=[x["toolSha256"] for x in self.baseline["samples"].values()]
                ),
                patch.object(
                    check,
                    "child",
                    side_effect=lambda kind, *_: (
                        parser_sample() if kind == "parser" else sample(kind, self.baseline),
                        {},
                    ),
                ),
                self.assertRaisesRegex(ValueError, "final drift"),
            ):
                check.run(output)
            value = json.loads(output.read_text())
            self.assertEqual("FAIL", value["status"])
            self.assertFalse(value["performanceQualifying"])

    @unittest.skipUnless(os.name == "nt", "Windows file-sharing boundary")
    def test_selected_file_cannot_be_changed_while_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.py"
            path.write_bytes(b"original")
            with check.windows_path_locks([path], directories=False), self.assertRaises(PermissionError):
                path.write_bytes(b"transient mutation")
            self.assertEqual(b"original", path.read_bytes())

    def test_report_destination_cannot_escape_confined_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts/tmp").mkdir(parents=True)
            with self.assertRaises(ValueError):
                check.safe_output_path(root, root / "outside.json")

    def test_installed_fingerprint_binds_actual_file_bytes_and_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "Lib/site-packages"
            site.mkdir(parents=True)
            source = site / "synthetic.py"
            source.write_bytes(b"first")
            with patch.object(check.sys, "prefix", str(root)):
                paths, first = check.installed_inputs()
                self.assertEqual([source.resolve()], paths)
                self.assertEqual(1, first["files"])
                self.assertEqual(64, len(first["rootBindingSha256"]))
                source.write_bytes(b"second")
                _, second = check.installed_inputs()
                self.assertNotEqual(first["sha256"], second["sha256"])
                self.assertEqual(first["rootBindingSha256"], second["rootBindingSha256"])


if __name__ == "__main__":
    unittest.main()
