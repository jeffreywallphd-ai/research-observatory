from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import core_sidecar_performance_check as benchmark  # noqa: E402


def sample_baseline() -> dict[str, Any]:
    samples = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
    raw = {name: benchmark.distribution(samples) for name in ("readinessMs", "shutdownMs", "idleWorkingSetBytes")}
    return {
        "schemaVersion": "1.0",
        "documentType": "core-sidecar-performance-baseline",
        "baselineSourceCommit": "a" * 40,
        "profile": "windows-x64",
        "provenance": {
            "measurementToolCommit": "a" * 40,
            "measurementToolPath": benchmark.TOOL_PATH.as_posix(),
            "measurementToolSha256": "b" * 64,
            "packageEvidencePath": benchmark.PACKAGE_EVIDENCE_PATH.as_posix(),
            "packageEvidenceSha256": benchmark.PACKAGE_EVIDENCE_SHA256,
            "packageReportSha256": "c" * 64,
            "artifactManifestSha256": "d" * 64,
        },
        "hardware": {
            "operatingSystem": "Windows-test",
            "machine": "AMD64",
            "processor": "Test CPU",
            "logicalCpuCount": 8,
            "physicalMemoryBytes": 16_000_000_000,
        },
        "fixture": {
            "buildContractSha256": "e" * 64,
            "targetTriple": benchmark.TARGET_TRIPLE,
            "componentVersion": "0.1.0",
            "entrypointSha256": "f" * 64,
            "fileCount": 644,
            "totalBytes": 31_569_506,
        },
        "methodology": benchmark.expected_methodology(),
        "rawMeasurements": raw,
        "measurements": {
            "readinessMs": {"baselineP50": 13.0, "absoluteBudget": benchmark.READINESS_BUDGET_MS},
            "shutdownMs": {"baselineP95": 16.0, "absoluteBudget": benchmark.SHUTDOWN_BUDGET_MS},
            "idleWorkingSetBytes": {
                "baselineP95": 16.0,
                "absoluteBudget": benchmark.IDLE_MEMORY_BUDGET_BYTES,
            },
        },
    }


class CoreSidecarPerformanceContractTests(unittest.TestCase):
    def test_strict_baseline_binds_raw_samples_hardware_tool_and_package(self) -> None:
        baseline = sample_baseline()
        self.assertIs(baseline, benchmark.validate_baseline(baseline))
        mutations = (
            ("raw aggregate", lambda item: item["rawMeasurements"]["readinessMs"].__setitem__("p50", 999.0)),
            ("raw sample", lambda item: item["rawMeasurements"]["shutdownMs"]["samples"].__setitem__(0, math.nan)),
            ("hardware", lambda item: item["hardware"].__setitem__("processor", "")),
            ("tool", lambda item: item["provenance"].__setitem__("measurementToolSha256", "wrong")),
            ("package", lambda item: item["fixture"].__setitem__("entrypointSha256", "wrong")),
            ("baseline", lambda item: item["measurements"]["readinessMs"].__setitem__("baselineP50", 14.0)),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                invalid = copy.deepcopy(baseline)
                mutate(invalid)
                with self.assertRaises(ValueError):
                    benchmark.validate_baseline(invalid)

    def test_package_identity_must_match_before_execution(self) -> None:
        baseline = sample_baseline()
        identity = {
            "buildContractSha256": baseline["fixture"]["buildContractSha256"],
            "targetTriple": baseline["fixture"]["targetTriple"],
            "componentVersion": baseline["fixture"]["componentVersion"],
            "entrypointSha256": baseline["fixture"]["entrypointSha256"],
            "fileCount": baseline["fixture"]["fileCount"],
            "totalBytes": baseline["fixture"]["totalBytes"],
            "packageReportSha256": baseline["provenance"]["packageReportSha256"],
            "artifactManifestSha256": baseline["provenance"]["artifactManifestSha256"],
        }
        benchmark.assert_approved_package_identity(identity, baseline)
        for field in ("entrypointSha256", "fileCount", "totalBytes", "packageReportSha256", "artifactManifestSha256"):
            with self.subTest(field=field):
                substitute = copy.deepcopy(identity)
                substitute[field] = 1 if isinstance(substitute[field], int) else "0" * 64
                with self.assertRaises(ValueError):
                    benchmark.assert_approved_package_identity(substitute, baseline)

    def test_snapshot_is_checked_before_and_after_every_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts" / "tmp") as temporary:
            executable = Path(temporary) / "fixture.exe"
            executable.write_bytes(b"approved")
            expected = benchmark.sha256(executable)
            calls = 0

            def guard() -> None:
                if benchmark.sha256(executable) != expected:
                    raise ValueError("snapshot changed")

            def measure(_path: Path) -> tuple[float, float, float]:
                nonlocal calls
                calls += 1
                if calls == 2:
                    executable.write_bytes(b"substitute")
                return (10.0, 10.0, 10.0)

            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                benchmark.benchmark_snapshot(executable, benchmark.REPETITIONS, guard, measure)

    def test_handshake_requires_the_complete_supervisor_contract(self) -> None:
        value = {
            "protocolVersion": "1.0",
            "buildId": "0.1.0",
            "pid": 42,
            "host": "127.0.0.1",
            "port": 49152,
            "nonce": "a" * 32,
            "capabilities": ["runtime.status"],
            "databaseCompatibility": {"minimum": "0.1.0", "maximumExclusive": "0.2.0"},
            "diagnosticCode": "RO-CORE-STARTING",
        }
        self.assertEqual(49152, benchmark.validate_handshake(value, 42))
        for field, invalid in (("buildId", "9.9.9"), ("pid", 41), ("host", "localhost"), ("port", 0)):
            with self.subTest(field=field):
                changed = copy.deepcopy(value)
                changed[field] = invalid
                with self.assertRaises(ValueError):
                    benchmark.validate_handshake(changed, 42)

    def test_evaluation_binds_hardware_package_and_relative_boundaries(self) -> None:
        baseline = sample_baseline()
        report = {
            "hardware": copy.deepcopy(baseline["hardware"]),
            "fixture": copy.deepcopy(baseline["fixture"]),
            "provenance": {
                **copy.deepcopy(baseline["provenance"]),
                "measurementStateCommit": "1" * 40,
            },
            "rawMeasurements": {
                "readinessMs": {"p50": 16.0},
                "shutdownMs": {"p95": 16.0},
                "idleWorkingSetBytes": {"p95": 16.0},
            },
        }
        evaluated = benchmark.evaluate(report, baseline, "9" * 64)
        self.assertFalse(evaluated["ok"])
        self.assertFalse(evaluated["measurements"]["readinessMs"]["passes"])
        for section, field in (("hardware", "processor"), ("fixture", "entrypointSha256")):
            with self.subTest(section=section):
                changed = copy.deepcopy(report)
                changed[section][field] = "substitute"
                with self.assertRaises(ValueError):
                    benchmark.evaluate(changed, baseline, "9" * 64)

    def test_measure_only_and_failures_replace_stale_pass_reports(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts" / "tmp") as temporary:
            destination = Path(temporary) / "performance.json"
            destination.write_text('{"ok":true}\n', encoding="utf-8")
            report, code = benchmark.run(ROOT, destination, measure_only=True)
            self.assertEqual(1, code)
            self.assertFalse(report["ok"])
            self.assertEqual(
                "NONQUALIFYING", json.loads(destination.read_text(encoding="utf-8"))["qualificationStatus"]
            )

            destination.write_text('{"ok":true}\n', encoding="utf-8")
            with mock.patch.object(benchmark, "load_baseline", side_effect=ValueError("baseline rejected")):
                report, code = benchmark.run(ROOT, destination)
            self.assertEqual(1, code)
            self.assertFalse(report["ok"])
            persisted = json.loads(destination.read_text(encoding="utf-8"))
            self.assertFalse(persisted["ok"])
            self.assertIn("baseline rejected", persisted["errors"][0])


if __name__ == "__main__":
    unittest.main()
