from __future__ import annotations

import copy
import json
import math
import sys
import tempfile
import threading
import time
import unittest
from contextlib import nullcontext
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
    def test_committed_baseline_is_exact_valid_and_reproducibly_sourced(self) -> None:
        baseline, digest = benchmark.load_baseline(ROOT)
        expected = (ROOT / benchmark.BASELINE_HASH_PATH).read_text(encoding="ascii").strip()
        self.assertEqual(expected, digest)
        self.assertEqual("9697487eafe804c92380d5607fd1ec932014b0aa", baseline["baselineSourceCommit"])

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
            "capabilities": [
                "intent.acceptance",
                "intent.drafts",
                "intent.impact-preview",
                "intent.policy-evaluation",
                "intent.read",
                "operations.cancel",
                "operations.events",
                "operations.read",
                "privacy.cache-cleanup",
                "privacy.policy",
                "projects.lifecycle",
                "runtime.contract",
                "runtime.status",
            ],
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
                "measurementStateCommit": "1" * 40,
                "measurementToolPath": baseline["provenance"]["measurementToolPath"],
                "measurementToolSha256": baseline["provenance"]["measurementToolSha256"],
                "packageEvidencePath": baseline["provenance"]["packageEvidencePath"],
                "packageEvidenceSha256": baseline["provenance"]["packageEvidenceSha256"],
                "packageReportSha256": baseline["provenance"]["packageReportSha256"],
                "artifactManifestSha256": baseline["provenance"]["artifactManifestSha256"],
            },
            "rawMeasurements": {
                "readinessMs": {"p50": 16.0},
                "shutdownMs": {"p95": 16.0},
                "idleWorkingSetBytes": {"p95": 16.0},
            },
        }
        evaluated = benchmark.evaluate(report, baseline, "9" * 64, "1" * 40)
        self.assertFalse(evaluated["ok"])
        self.assertFalse(evaluated["measurements"]["readinessMs"]["passes"])

        precision_boundary = copy.deepcopy(report)
        precision_baseline = copy.deepcopy(baseline)
        precision_baseline["measurements"]["readinessMs"]["baselineP50"] = 1017.191
        precision_boundary["rawMeasurements"]["readinessMs"]["p50"] = 1220.6294
        precision = benchmark.evaluate(precision_boundary, precision_baseline, "9" * 64, "1" * 40)
        self.assertFalse(precision["ok"])
        self.assertFalse(precision["measurements"]["readinessMs"]["passes"])
        self.assertGreater(1220.6294, 1017.191 * 1.2)
        for section, field in (("hardware", "processor"), ("fixture", "entrypointSha256")):
            with self.subTest(section=section):
                changed = copy.deepcopy(report)
                changed[section][field] = "substitute"
                with self.assertRaises(ValueError):
                    benchmark.evaluate(changed, baseline, "9" * 64, "1" * 40)

        for field, value in (
            ("measurementToolPath", "evil.py"),
            ("measurementToolSha256", "0" * 64),
            ("measurementStateCommit", "0" * 40),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(report)
                changed["provenance"][field] = value
                with self.assertRaises(ValueError):
                    benchmark.evaluate(changed, baseline, "9" * 64, "1" * 40)

    @unittest.skipUnless(sys.platform == "win32", "Windows ACL boundary")
    def test_snapshot_acl_denies_transient_concurrent_create_write_and_delete(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts" / "tmp") as temporary:
            snapshot = Path(temporary) / "package"
            snapshot.mkdir()
            executable = snapshot / "fixture.exe"
            executable.write_bytes(b"approved")
            manifest = {"files": [{"path": "fixture.exe"}]}
            attempts = 0
            successes: list[str] = []
            stop = threading.Event()

            def attack() -> None:
                nonlocal attempts
                injected = snapshot / "unapproved-runtime-injection.dll"
                while not stop.is_set():
                    attempts += 1
                    try:
                        injected.write_bytes(b"attacker")
                        executable.write_bytes(b"attacker")
                        injected.unlink()
                        successes.append("mutation")
                    except OSError:
                        pass

            with benchmark.immutable_package_snapshot(ROOT, snapshot, manifest):
                worker = threading.Thread(target=attack)
                worker.start()
                time.sleep(0.1)
                stop.set()
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive())
                self.assertGreater(attempts, 0)
                self.assertEqual([], successes)
                self.assertEqual(b"approved", executable.read_bytes())
            executable.write_bytes(b"restored-write-access")

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

    def test_interruption_after_initial_invalidation_leaves_nonqualifying_tombstone(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts" / "tmp") as temporary:
            destination = Path(temporary) / "performance.json"
            destination.write_text('{"ok":true,"sentinel":"stale"}\n', encoding="utf-8")
            with (
                mock.patch.object(benchmark, "qualification_snapshot", side_effect=KeyboardInterrupt),
                self.assertRaises(KeyboardInterrupt),
            ):
                benchmark.run(ROOT, destination)
            persisted = json.loads(destination.read_text(encoding="utf-8"))
            self.assertFalse(persisted["ok"])
            self.assertEqual("NONQUALIFYING", persisted["qualificationStatus"])
            self.assertEqual("IN_PROGRESS", persisted["qualificationPhase"])
            self.assertNotIn("stale", persisted.values())

    def test_late_state_change_is_rejected_before_pass_replacement(self) -> None:
        qualification = {
            "baseline": sample_baseline(),
            "baselineSha256": "9" * 64,
            "stateCommit": "1" * 40,
        }
        measured = {"measurement": True}
        passing = {"ok": True, "sentinel": "candidate-pass"}

        def publish(
            _repo: Path,
            _destination: Path,
            _value: object,
            _root: Path,
            before_replace: Any,
        ) -> None:
            before_replace()
            self.fail("PASS must not replace the tombstone after final state rejection")

        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts" / "tmp") as temporary:
            destination = Path(temporary) / "performance.json"
            destination.write_text('{"ok":true,"sentinel":"stale"}\n', encoding="utf-8")
            with (
                mock.patch.object(benchmark, "qualification_snapshot", return_value=nullcontext(qualification)),
                mock.patch.object(benchmark, "measured_report", return_value=measured),
                mock.patch.object(benchmark, "evaluate", return_value=passing),
                mock.patch.object(
                    benchmark,
                    "assert_qualification_inputs",
                    side_effect=ValueError("post-measure input changed"),
                ),
                mock.patch.object(benchmark, "guarded_final_publication", side_effect=publish),
            ):
                report, code = benchmark.run(ROOT, destination)
            self.assertEqual(1, code)
            self.assertFalse(report["ok"])
            persisted = json.loads(destination.read_text(encoding="utf-8"))
            self.assertFalse(persisted["ok"])
            self.assertIn("post-measure input changed", persisted["errors"][0])

    def test_persistent_pass_and_demotion_publication_failure_leaves_tombstone(self) -> None:
        qualification = {
            "baseline": sample_baseline(),
            "baselineSha256": "9" * 64,
            "stateCommit": "1" * 40,
        }
        original_writer = benchmark.guarded_atomic_write_json
        generic_calls = 0

        def generic_writer(repo: Path, destination: Path, value: object, root: Path) -> None:
            nonlocal generic_calls
            generic_calls += 1
            if generic_calls == 1:
                original_writer(repo, destination, value, root)
                return
            raise OSError("persistent demotion publication failure")

        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts" / "tmp") as temporary:
            destination = Path(temporary) / "performance.json"
            destination.write_text('{"ok":true,"sentinel":"stale"}\n', encoding="utf-8")
            with (
                mock.patch.object(benchmark, "qualification_snapshot", return_value=nullcontext(qualification)),
                mock.patch.object(benchmark, "measured_report", return_value={"measurement": True}),
                mock.patch.object(benchmark, "evaluate", return_value={"ok": True}),
                mock.patch.object(
                    benchmark,
                    "guarded_final_publication",
                    side_effect=OSError("persistent PASS publication failure"),
                ),
                mock.patch.object(benchmark, "guarded_atomic_write_json", side_effect=generic_writer),
            ):
                report, code = benchmark.run(ROOT, destination)
            self.assertEqual(1, code)
            self.assertFalse(report["ok"])
            persisted = json.loads(destination.read_text(encoding="utf-8"))
            self.assertFalse(persisted["ok"])
            self.assertEqual("IN_PROGRESS", persisted["qualificationPhase"])
            self.assertEqual(2, generic_calls)

    def test_proposal_retains_measurements_but_cannot_qualify(self) -> None:
        measured = {
            "schemaVersion": "1.0",
            "documentType": "core-sidecar-performance-report",
            "profile": "windows-x64",
            "hardware": sample_baseline()["hardware"],
            "provenance": {"measurementStateCommit": "a" * 40},
            "fixture": sample_baseline()["fixture"],
            "methodology": benchmark.expected_methodology(),
            "rawMeasurements": sample_baseline()["rawMeasurements"],
        }
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts" / "tmp") as temporary:
            destination = Path(temporary) / "proposal.json"
            with mock.patch.object(benchmark, "measured_report", return_value=measured) as measurement:
                report, code = benchmark.run(ROOT, destination, proposal=True)
        measurement.assert_called_once_with(ROOT, benchmark.REPETITIONS, None)
        self.assertEqual(0, code)
        self.assertFalse(report["ok"])
        self.assertTrue(report["proposalGenerated"])
        self.assertEqual("PROPOSAL", report["qualificationStatus"])
        self.assertEqual(measured["rawMeasurements"], report["rawMeasurements"])


if __name__ == "__main__":
    unittest.main()
