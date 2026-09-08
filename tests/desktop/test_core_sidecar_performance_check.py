from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
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


class CurrentPackageApprovalTests(unittest.TestCase):
    """Temporary Git authority fixtures only; never launch the packaged Core."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "artifacts" / "tmp")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name).resolve()
        self.evidence_path = Path("artifacts/evidence/current-package.json")
        self.review_path = Path("artifacts/evidence/current-package.review.json")
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture producer")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        for path in (
            benchmark.TOOL_PATH,
            benchmark.CONTRACT_PATH,
            benchmark.SCHEMA_PATH,
            Path("tools/core_sidecar_build.py"),
            Path("tools/build_manifest.py"),
            Path("services/core-api/sidecar_entry.py"),
            Path("services/core-api/src/fixture.py"),
            Path("pyproject.toml"),
            Path("uv.lock"),
            Path(".gitattributes"),
        ):
            self.write(path, b"{}\n" if path.suffix == ".json" else b"# fixture input\n")
        self.candidate = self.commit()
        self.baseline = sample_baseline()
        self.baseline_hash = "9" * 64
        identity = {
            **self.baseline["fixture"],
            "entrypointSha256": "0" * 64,
            "packageReportSha256": "1" * 64,
            "artifactManifestSha256": "2" * 64,
            "buildContractSha256": benchmark.sha256(self.repo / benchmark.CONTRACT_PATH),
        }
        rows = [
            {
                "path": path.as_posix(),
                "sha256": benchmark.sha256(self.repo / path),
                "gitBlobSha256": hashlib.sha256(benchmark.git_blob(self.repo, self.candidate, path)).hexdigest(),
            }
            for path in benchmark.current_package_input_paths(self.repo, self.candidate)
        ]
        self.evidence: dict[str, Any] = {
            "schemaVersion": "1.0",
            "documentType": "core-sidecar-current-package-evidence",
            "producer": "fixture-producer",
            "buildCandidateCommit": self.candidate,
            "profile": "windows-x64",
            "baseline": {"path": benchmark.BASELINE_PATH.as_posix(), "sha256": self.baseline_hash},
            "methodology": benchmark.expected_methodology(),
            "measurementTool": next(row for row in rows if row["path"] == benchmark.TOOL_PATH.as_posix()),
            "package": {
                "artifactRoot": benchmark.ARTIFACT_ROOT_PATH.as_posix(),
                "report": {"path": benchmark.PACKAGE_REPORT_PATH.as_posix(), "sha256": identity["packageReportSha256"]},
                "identity": identity,
            },
            "committedInputs": rows,
        }
        self.review: dict[str, Any] = {
            "schemaVersion": "1.0",
            "documentType": "core-sidecar-current-package-review",
            "reviewer": "fixture-independent-reviewer",
            "candidateCommit": self.candidate,
            "disposition": "APPROVED",
            "evidence": {"path": self.evidence_path.as_posix(), "sha256": "pending"},
            "blockingFindings": [],
        }

    def git(self, *args: str) -> str:
        return (
            subprocess.run(["git", *args], cwd=self.repo, capture_output=True, check=True, timeout=30)
            .stdout.decode("utf-8")
            .strip()
        )

    def write(self, path: Path, payload: bytes) -> None:
        destination = self.repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    def commit(self) -> str:
        self.git("add", ".")
        self.git("commit", "-qm", "Synthetic test authority")
        return self.git("rev-parse", "HEAD")

    def publish(self) -> None:
        self.write(self.evidence_path, (json.dumps(self.evidence, indent=2) + "\n").encode())
        self.commit()
        self.review["evidence"]["sha256"] = benchmark.sha256(self.repo / self.evidence_path)
        self.write(self.review_path, (json.dumps(self.review, indent=2) + "\n").encode())
        self.commit()

    def admit(self) -> dict[str, Any]:
        return benchmark.load_current_package_approval(
            self.repo, self.evidence_path, self.review_path, self.baseline_hash
        )

    def test_current_candidate_and_metadata_descendant_are_admitted_without_old_identity_substitution(self) -> None:
        self.publish()
        self.write(Path("planning/status-summary.md"), b"fixture metadata\n")
        self.commit()
        admitted = self.admit()
        self.assertEqual(self.candidate, admitted["evidence"]["buildCandidateCommit"])
        self.assertNotEqual(self.baseline["fixture"], benchmark.current_package_fixture(admitted))
        report = {
            "hardware": self.baseline["hardware"],
            "fixture": benchmark.current_package_fixture(admitted),
            "provenance": benchmark.current_package_provenance(admitted, self.git("rev-parse", "HEAD")),
            "currentPackageApproval": admitted["references"],
            "methodology": benchmark.expected_methodology(),
            "rawMeasurements": self.baseline["rawMeasurements"],
        }
        evaluated = benchmark.evaluate(
            report, self.baseline, self.baseline_hash, self.git("rev-parse", "HEAD"), admitted
        )
        self.assertTrue(evaluated["ok"])
        self.assertEqual(self.baseline["rawMeasurements"], evaluated["rawMeasurements"])
        with self.assertRaises(ValueError):
            benchmark.evaluate(report, self.baseline, self.baseline_hash, self.git("rev-parse", "HEAD"))
        for field in self.evidence["package"]["identity"]:
            with self.subTest(field=field):
                identity = copy.deepcopy(self.evidence["package"]["identity"])
                identity[field] = "substitute"
                with self.assertRaises(ValueError):
                    benchmark.assert_current_package_identity(identity, admitted)
        for section, field in (
            ("hardware", "processor"),
            ("fixture", "entrypointSha256"),
            ("methodology", "repetitions"),
        ):
            invalid = copy.deepcopy(report)
            invalid[section][field] = "substitute"
            with self.assertRaises(ValueError):
                benchmark.evaluate(invalid, self.baseline, self.baseline_hash, self.git("rev-parse", "HEAD"), admitted)
        invalid = copy.deepcopy(report)
        invalid["rawMeasurements"]["readinessMs"]["p50"] = 1
        with self.assertRaises(ValueError):
            benchmark.evaluate(invalid, self.baseline, self.baseline_hash, self.git("rev-parse", "HEAD"), admitted)

    def test_review_denials_precede_measurement(self) -> None:
        for field, invalid in (
            ("reviewer", "fixture-producer"),
            ("disposition", "CHANGES_REQUIRED"),
            ("candidateCommit", "0" * 40),
            ("blockingFindings", ["open"]),
        ):
            with self.subTest(field=field):
                self.review[field] = invalid
                self.publish()
                with self.assertRaises(ValueError):
                    self.admit()
                self.git("switch", "--detach", self.candidate)
                self.review.update(
                    reviewer="fixture-independent-reviewer",
                    disposition="APPROVED",
                    candidateCommit=self.candidate,
                    blockingFindings=[],
                )

    def test_missing_extra_or_substituted_inventory_is_denied(self) -> None:
        original = copy.deepcopy(self.evidence)
        for mutation in ("omit", "extra", "raw", "blob", "tool", "baseline", "method"):
            with self.subTest(mutation=mutation):
                self.evidence = copy.deepcopy(original)
                if mutation == "omit":
                    self.evidence["committedInputs"].pop()
                elif mutation == "extra":
                    self.evidence["committedInputs"].append(self.evidence["committedInputs"][0])
                elif mutation in {"raw", "blob"}:
                    self.evidence["committedInputs"][0]["sha256" if mutation == "raw" else "gitBlobSha256"] = "0" * 64
                elif mutation == "tool":
                    self.evidence["measurementTool"]["sha256"] = "0" * 64
                elif mutation == "baseline":
                    self.evidence["baseline"]["sha256"] = "0" * 64
                else:
                    self.evidence["methodology"]["repetitions"] = 1
                self.publish()
                with self.assertRaises(ValueError):
                    self.admit()
                self.git("switch", "--detach", self.candidate)

    def test_source_add_revert_and_record_rewrite_are_not_metadata_only(self) -> None:
        self.publish()
        approved = self.git("rev-parse", "HEAD")
        path = Path("services/core-api/src/fixture.py")
        self.write(path, b"# changed\n")
        self.commit()
        self.write(path, b"# fixture input\n")
        self.commit()
        with self.assertRaises(ValueError):
            self.admit()
        self.git("switch", "--detach", approved)
        self.write(self.evidence_path, (self.repo / self.evidence_path).read_bytes() + b"\n")
        self.commit()
        with self.assertRaises(ValueError):
            self.admit()

    def test_uncommitted_dirty_wrong_digest_and_unsafe_references_are_denied(self) -> None:
        self.publish()
        approved = self.git("rev-parse", "HEAD")
        for path in (self.evidence_path, self.review_path, benchmark.TOOL_PATH):
            payload = (self.repo / path).read_bytes()
            self.write(path, payload + b"\n")
            with self.assertRaises(ValueError):
                self.admit()
            self.write(path, payload)
        self.review["evidence"]["sha256"] = "0" * 64
        self.write(self.review_path, (json.dumps(self.review) + "\n").encode())
        self.commit()
        with self.assertRaises(ValueError):
            self.admit()
        self.git("switch", "--detach", approved)
        for unsafe in (
            Path("../outside.json"),
            Path("artifacts/tmp/not-authority.json"),
            Path("artifacts/evidence/W1.A04.B00.json"),
        ):
            with self.assertRaises(ValueError):
                benchmark.load_current_package_approval(self.repo, unsafe, self.review_path, self.baseline_hash)

    def test_untracked_review_and_nonancestor_candidate_are_denied(self) -> None:
        self.write(self.evidence_path, (json.dumps(self.evidence) + "\n").encode())
        self.commit()
        self.review["evidence"]["sha256"] = benchmark.sha256(self.repo / self.evidence_path)
        self.write(self.review_path, (json.dumps(self.review) + "\n").encode())
        with self.assertRaises(ValueError):
            self.admit()
        self.commit()
        self.git("switch", "--detach", self.candidate)
        self.evidence["buildCandidateCommit"] = "0" * 40
        self.review["candidateCommit"] = "0" * 40
        self.publish()
        with self.assertRaises(ValueError):
            self.admit()

    def test_authority_is_recaptured_under_lock_and_again_before_publication(self) -> None:
        self.publish()
        admission = self.admit()
        root = self.repo / benchmark.ARTIFACT_ROOT_PATH
        root.mkdir(parents=True)
        identity = self.evidence["package"]["identity"]
        package: tuple[Path, dict[str, Any], dict[str, Any], bytes] = (root, {"files": []}, identity, b"fixture report")
        changed = copy.deepcopy(admission)
        changed["references"]["review"]["sha256"] = "0" * 64
        with (
            mock.patch.object(benchmark, "__file__", str(self.repo / benchmark.TOOL_PATH)),
            mock.patch.object(benchmark, "load_baseline", return_value=(self.baseline, self.baseline_hash)),
            mock.patch.object(benchmark, "load_verified_package", return_value=package),
            mock.patch.object(benchmark, "load_current_package_approval", side_effect=[admission, changed]),
            mock.patch.object(benchmark, "windows_path_locks", return_value=nullcontext()),
            mock.patch.object(benchmark, "measure_once") as measurement,
            self.assertRaisesRegex(ValueError, "before qualification locking"),
            benchmark.qualification_snapshot(self.repo, self.evidence_path, self.review_path),
        ):
            self.fail("substituted approval cannot reach a measurement")
        measurement.assert_not_called()
        snapshot = {
            "stateCommit": self.git("rev-parse", "HEAD"),
            "toolSha256": benchmark.sha256(self.repo / benchmark.TOOL_PATH),
            "trackedInputs": {},
            "baseline": self.baseline,
            "baselineSha256": self.baseline_hash,
            "currentPackage": admission,
        }
        with (
            mock.patch.object(benchmark, "load_baseline", return_value=(self.baseline, self.baseline_hash)),
            mock.patch.object(benchmark, "load_current_package_approval", return_value=changed),
            self.assertRaisesRegex(ValueError, "approval changed during qualification"),
        ):
            benchmark.assert_qualification_inputs(self.repo, snapshot)

    def test_partial_or_nonqualifying_modes_invalidate_stale_pass_without_measurement(self) -> None:
        destination = self.repo / "artifacts/tmp/result.json"
        destination.parent.mkdir(parents=True)
        for options in (
            {"current_package_evidence": self.evidence_path},
            {"current_package_review": self.review_path},
            {
                "current_package_evidence": self.evidence_path,
                "current_package_review": self.review_path,
                "proposal": True,
            },
            {
                "current_package_evidence": self.evidence_path,
                "current_package_review": self.review_path,
                "measure_only": True,
            },
        ):
            with self.subTest(options=options):
                destination.write_text('{"ok":true}\n', encoding="utf-8")
                with mock.patch.object(benchmark, "measured_report") as measurement:
                    report, code = benchmark.run(self.repo, destination, **options)
                measurement.assert_not_called()
                self.assertEqual(1, code)
                self.assertFalse(report["ok"])
                self.assertFalse(json.loads(destination.read_bytes())["ok"])

    def test_only_honest_text_checkout_representation_can_differ_from_git(self) -> None:
        self.assertTrue(benchmark.committed_source_bytes_match(Path("input.py"), b"# text\r\n", b"# text\n"))
        for path, raw in (("input.bin", b"# text\r\n"), ("input.py", b"# changed\r\n"), ("input.py", b"\xff\r\n")):
            self.assertFalse(benchmark.committed_source_bytes_match(Path(path), raw, b"# text\n"))

    def test_current_qualified_run_routes_through_locked_approval_and_final_guard(self) -> None:
        self.publish()
        admission = self.admit()
        root = self.repo / benchmark.ARTIFACT_ROOT_PATH
        root.mkdir(parents=True)
        self.write(benchmark.PACKAGE_REPORT_PATH, b"fixture report")
        destination = self.repo / "artifacts/tmp/result.json"
        state = self.git("rev-parse", "HEAD")
        measured = {
            "hardware": self.baseline["hardware"],
            "fixture": benchmark.current_package_fixture(admission),
            "provenance": benchmark.current_package_provenance(admission, state),
            "currentPackageApproval": admission["references"],
            "methodology": benchmark.expected_methodology(),
            "rawMeasurements": self.baseline["rawMeasurements"],
        }
        with (
            mock.patch.object(benchmark, "__file__", str(self.repo / benchmark.TOOL_PATH)),
            mock.patch.object(
                benchmark,
                "qualification_paths",
                return_value=(benchmark.TOOL_PATH, benchmark.CONTRACT_PATH, benchmark.SCHEMA_PATH),
            ),
            mock.patch.object(benchmark, "load_baseline", return_value=(self.baseline, self.baseline_hash)),
            mock.patch.object(
                benchmark,
                "load_verified_package",
                return_value=(root, {"files": []}, self.evidence["package"]["identity"], b"fixture report"),
            ),
            mock.patch.object(benchmark, "load_build_contract", return_value={}),
            mock.patch.object(benchmark, "assert_package_snapshot"),
            mock.patch.object(benchmark, "immutable_package_snapshot", return_value=nullcontext()),
            mock.patch.object(benchmark, "measured_report", return_value=measured) as measurement,
            mock.patch.object(benchmark, "measure_once") as lifecycle,
            mock.patch.object(
                benchmark, "assert_qualification_inputs", wraps=benchmark.assert_qualification_inputs
            ) as guard,
        ):
            report, code = benchmark.run(
                self.repo,
                destination,
                current_package_evidence=self.evidence_path,
                current_package_review=self.review_path,
            )
        self.assertEqual(0, code, report)
        self.assertTrue(report["ok"])
        self.assertEqual(2, guard.call_count)
        measurement.assert_called_once()
        lifecycle.assert_not_called()
        self.assertEqual(admission, measurement.call_args.args[3]["currentPackage"])
        self.assertEqual(admission["references"], json.loads(destination.read_bytes())["currentPackageApproval"])


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

    def test_unchanged_method_has_one_warmup_seven_retained_samples(self) -> None:
        calls = 0

        def measure(_path: Path) -> tuple[float, float, float]:
            nonlocal calls
            calls += 1
            return (float(calls), float(calls), float(calls))

        raw = benchmark.benchmark_snapshot(
            Path("synthetic-not-executed.exe"), benchmark.REPETITIONS, lambda: None, measure
        )
        self.assertEqual(8, calls)
        for item in raw.values():
            self.assertEqual([2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], item["samples"])

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
                "intent.workflow-profiles",
                "intent.workflow-progress",
                "models.catalog.read",
                "models.catalog.refresh",
                "operations.cancel",
                "operations.events",
                "operations.read",
                "privacy.cache-cleanup",
                "privacy.policy",
                "projects.lifecycle",
                "provenance.lineage.read",
                "runtime.contract",
                "runtime.status",
                "workflows.cancel",
                "workflows.human-decisions",
                "workflows.read",
                "workflows.retry",
            ],
            "databaseCompatibility": {"minimum": "0.1.0", "maximumExclusive": "0.2.0"},
            "diagnosticCode": "RO-CORE-STARTING",
        }
        self.assertEqual(49152, benchmark.validate_handshake(value, 42))
        supervisor_source = (ROOT / "apps" / "desktop" / "src-tauri" / "src" / "supervisor.rs").read_text(
            encoding="utf-8"
        )
        capability_block = supervisor_source.split("const EXPECTED_CORE_CAPABILITIES: &[&str] = &[", 1)[1].split(
            "];", 1
        )[0]
        supervisor_capabilities = tuple(
            line.strip().removeprefix('"').removesuffix('",')
            for line in capability_block.splitlines()
            if line.strip().startswith('"')
        )
        capabilities = value["capabilities"]
        self.assertIsInstance(capabilities, list)
        assert isinstance(capabilities, list)
        self.assertEqual(tuple(capabilities), supervisor_capabilities)
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
