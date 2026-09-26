"""Fail-closed controls for source calibration and fresh qualification."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import source_performance_check as check  # noqa: E402


def sample():
    return {
        "fixtureVersion": check.METHOD["fixtureVersion"],
        "recordsPerPage": 100,
        "restartPreserved": True,
        "boundariesExercised": False,
        "networkCalls": 4,
        "samples": [
            {
                "provider": provider,
                "phase": phase,
                "records": 1 if provider == "unpaywall" else 100,
                "networkCalls": 1 if phase == "cold" else 0,
                "seconds": 1.0,
            }
            for provider in check.PROVIDERS
            for phase in ("cold", "cache")
        ],
        "rateWait": {
            "networkCalls": 2,
            "maximumConcurrentRequests": 1,
            "wireStartIntervalSeconds": 1.1,
            "seconds": 1.2,
            "waits": [{"requestedSeconds": 1.0, "actualSeconds": 1.01}],
        },
        "memory": {"peakWorkingSetSize": 100000000},
    }


class SourcePerformanceCheckTests(unittest.TestCase):
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

    def test_baseline_bytes_and_raw_samples_bind_every_ceiling(self):
        value = self.baseline()
        self.assertEqual(value, self.validate(value))
        with self.assertRaisesRegex(ValueError, "reviewed bytes"):
            check.validate_baseline(json.dumps(value).encode())
        for mutate in (
            lambda value: value["maxima"].update({"rateWait": float("nan")}),
            lambda value: value["maxima"].update({"rateWait": 31}),
            lambda value: value["maxima"].update({"rateWait": 2}),
            lambda value: value["calibration"].update(rawMetrics=[]),
            lambda value: value["calibration"].update(performanceQualifying=True),
        ):
            changed = copy.deepcopy(value)
            mutate(changed)
            with self.assertRaises(ValueError):
                self.validate(changed)

    def test_sample_inventory_cache_restart_and_completed_real_wait_are_required(self):
        value = sample()
        self.assertEqual(10, len(check.sample_metrics(value)))
        for mutate in (
            lambda value: value.update(samples=value["samples"][:-1]),
            lambda value: value.update(networkCalls=5),
            lambda value: value.update(restartPreserved=False),
            lambda value: value["rateWait"].update(waits=[]),
            lambda value: value["rateWait"].update(maximumConcurrentRequests=2),
            lambda value: value["rateWait"]["waits"][0].update(actualSeconds=0.1),
            lambda value: value["samples"][0].update(seconds=float("inf")),
            lambda value: value["samples"][0].update(records=99),
        ):
            changed = copy.deepcopy(value)
            mutate(changed)
            with self.assertRaises(ValueError):
                check.sample_metrics(changed)

    def test_every_sample_is_gated_without_averaging_out_regressions(self):
        baseline = self.baseline()
        metrics = check.sample_metrics(sample())
        check.validate_metrics(metrics, baseline)
        metrics["openalex:cold"] = 1.201
        with self.assertRaisesRegex(ValueError, "openalex:cold"):
            check.validate_metrics(metrics, baseline)

    def test_prerequisite_failure_invalidates_previous_pass(self):
        @contextmanager
        def fail():
            raise ValueError("synthetic setup rejection")
            yield

        with tempfile.TemporaryDirectory(prefix="source-performance-control-", dir=REPO / "artifacts/tmp") as folder:
            destination = Path(folder) / "report.json"
            destination.write_text('{"status":"PASS","performanceQualifying":true}', encoding="utf-8")
            with patch.object(check, "fixed_inputs", fail), self.assertRaisesRegex(ValueError, "setup rejection"):
                check.run(destination)
            result = json.loads(destination.read_text("utf-8"))
            self.assertEqual("FAIL", result["status"])
            self.assertFalse(result["performanceQualifying"])

    def test_child_cannot_consume_existing_default_bytecode(self):
        with tempfile.TemporaryDirectory(prefix="source-performance-child-", dir=REPO / "artifacts/tmp") as folder:
            directory = Path(folder)
            captured: dict[str, Any] = {}

            def spawn(command, **kwargs):
                captured.update(command=command, environment=kwargs["env"])
                report = Path(command[-1])
                report.write_text(json.dumps(sample()), encoding="utf-8")
                return Mock(wait=Mock(return_value=0), poll=Mock(return_value=0))

            with patch.object(check.subprocess, "Popen", side_effect=spawn):
                check.child(1, directory)
            self.assertIn("-B", captured["command"])
            prefix = Path(captured["environment"]["PYTHONPYCACHEPREFIX"])
            self.assertEqual(directory / "sample-1/unused-bytecode", prefix)
            self.assertFalse(prefix.exists())
            # A reused sample directory cannot replace a prior sample or consume its cache.
            with self.assertRaises(FileExistsError):
                check.child(1, directory)

    def test_fresh_prefix_rejects_timestamp_valid_poisoned_bytecode(self):
        with tempfile.TemporaryDirectory(prefix="source-bytecode-control-", dir=REPO / "artifacts/tmp") as folder:
            directory = Path(folder)
            module = directory / "synthetic_cached_module.py"
            module.write_text("VALUE = 'poisoned'\n", encoding="utf-8")
            original = module.stat()
            cached = directory / "__pycache__" / f"synthetic_cached_module.{sys.implementation.cache_tag}.pyc"
            py_compile.compile(str(module), cfile=str(cached), doraise=True)
            module.write_text("VALUE = 'expected'\n", encoding="utf-8")
            os.utime(module, ns=(original.st_atime_ns, original.st_mtime_ns))
            command = [sys.executable, "-B", "-s"]
            script = ["-c", "import synthetic_cached_module; print(synthetic_cached_module.VALUE)"]
            environment = {"SystemRoot": os.environ["SYSTEMROOT"], "PYTHONPATH": str(directory)}
            poisoned = subprocess.check_output(command + script, cwd=directory, env=environment, text=True).strip()
            self.assertEqual("poisoned", poisoned, "fixture must prove -B alone still reads old bytecode")
            prefix = directory / "fresh-prefix"
            clean = subprocess.check_output(
                [*command, "-X", f"pycache_prefix={prefix}", *script], cwd=directory, env=environment, text=True
            ).strip()
            self.assertEqual("expected", clean)
            self.assertFalse(prefix.exists())
