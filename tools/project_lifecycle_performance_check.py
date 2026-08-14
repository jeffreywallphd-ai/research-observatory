#!/usr/bin/env python3
"""Qualify ordinary local-project open latency against the approved S01 budget."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from build_manifest import guarded_atomic_write_json, safe_output_path, safe_snapshot, windows_path_locks

TOOL_PATH = Path("tools/project_lifecycle_performance_check.py")
IMPLEMENTATION_PATH = Path("services/core-api/src/research_observatory_core/projects.py")
BASELINE_PATH = Path("verification/baselines/project-lifecycle-performance.json")
CALIBRATION_PATH = Path("verification/baselines/project-lifecycle-performance-calibration.json")
EXPECTED_BASELINE_SHA256 = "89d2d0aad25a3ab1a69c5afb4d1d9300094c47df9ecfb4b560f2d005ef11126d"
EXPECTED_CALIBRATION_SHA256 = "aeaa90c55d9529b238d4eeac399543a880e772426303f068ecda27a5ad55beb5"
EXPECTED_BASELINE_P95_MS = {
    "freshServiceOpen": 16.82,
    "warmServiceReopen": 19.734,
}
CALIBRATION_SELECTION_RULE = "maximum per-run nearest-rank p95 across three clean 20-sample calibration runs"
CALIBRATION_CONTEXTS = (
    "standalone measurement-only",
    "standalone qualification",
    "immediately after the full foundation profile",
)
EXPECTED_CALIBRATION_HARDWARE = {
    "operatingSystem": "Windows-11-10.0.26200-SP0",
    "system": "Windows",
    "release": "11",
    "version": "10.0.26200",
    "machine": "AMD64",
    "processor": "Intel64 Family 6 Model 183 Stepping 1, GenuineIntel",
    "logicalCpuCount": 20,
    "physicalMemoryBytes": 16984227840,
}
ABSOLUTE_BUDGET_MS = 500.0
REGRESSION_PERCENT = 20
REPETITIONS = 20
WARMUP_REPETITIONS = 3
OBJECT_FILE_COUNT = 2_000
OBJECT_FILE_BYTES = 64
EXPECTED_FIXTURE = {
    "version": "ordinary-project-2000-objects-v1",
    "templateId": "theory-synthesis",
    "packageFormatVersion": "1.0.0",
    "objectFileCount": OBJECT_FILE_COUNT,
    "objectBytes": OBJECT_FILE_COUNT * OBJECT_FILE_BYTES,
}
EXPECTED_METHODOLOGY = {
    "timer": "time.perf_counter_ns",
    "operation": "ProjectLifecycleService.open through returned manifest/compatibility projection",
    "excluded": "fixture construction, credential prompt, database integrity checks, close, and shutdown",
    "freshState": "new service instance for every measured open; operating-system filesystem cache is not flushed",
    "warmState": "same service instance after three unmeasured open/close cycles",
    "repetitions": REPETITIONS,
    "warmupRepetitions": WARMUP_REPETITIONS,
    "distribution": "nearest-rank p50 and p95 over every measured sample; no samples discarded",
    "regressionThresholdPercent": REGRESSION_PERCENT,
    "hardwareQualification": "release-authoritative Windows x64 workstation",
}


class MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("memoryLoad", ctypes.c_ulong),
        ("totalPhysicalBytes", ctypes.c_ulonglong),
        ("availablePhysicalBytes", ctypes.c_ulonglong),
        ("totalPageFileBytes", ctypes.c_ulonglong),
        ("availablePageFileBytes", ctypes.c_ulonglong),
        ("totalVirtualBytes", ctypes.c_ulonglong),
        ("availableVirtualBytes", ctypes.c_ulonglong),
        ("availableExtendedVirtualBytes", ctypes.c_ulonglong),
    ]


def physical_memory_bytes() -> int | None:
    if os.name != "nt":
        return None
    status = MemoryStatusEx()
    status.length = ctypes.sizeof(MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.totalPhysicalBytes)


def hardware_record() -> dict[str, Any]:
    return {
        "operatingSystem": platform.platform(aliased=False, terse=False),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER") or "unreported",
        "logicalCpuCount": os.cpu_count(),
        "physicalMemoryBytes": physical_memory_bytes(),
    }


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=text,
        check=False,
    )
    if completed.returncode:
        diagnostic = completed.stderr if text else completed.stderr.decode("utf-8", errors="replace")
        raise ValueError(f"git {' '.join(args)} failed: {diagnostic.strip()}")
    return completed.stdout


def clean_state_commit(repo: Path) -> str:
    status = str(git(repo, "status", "--porcelain=v1", "--untracked-files=all"))
    if status:
        raise ValueError("project lifecycle performance qualification requires a clean tracked and untracked state")
    commit = str(git(repo, "rev-parse", "HEAD")).strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise ValueError("project lifecycle performance state commit is invalid")
    return commit


def git_blob_sha256(repo: Path, commit: str, path: Path) -> str:
    value = git(repo, "show", f"{commit}:{path.as_posix()}", text=False)
    if not isinstance(value, bytes):
        raise ValueError("git blob reader returned text unexpectedly")
    return sha256_bytes(value)


def governed_snapshot(repo: Path, path: Path) -> bytes:
    lexical = repo / path
    try:
        metadata = lexical.lstat()
    except OSError as exc:
        raise ValueError(f"governed performance input is unavailable: {path.as_posix()}: {exc}") from exc
    if metadata.st_nlink != 1:
        raise ValueError(f"governed performance input must have exactly one filesystem link: {path.as_posix()}")
    payload, error = safe_snapshot(repo, path.as_posix())
    if error or payload is None:
        raise ValueError(f"governed performance input is unsafe: {path.as_posix()}: {error}")
    return payload


def assert_committed_inputs(repo: Path, commit: str, captured: dict[Path, bytes]) -> None:
    if clean_state_commit(repo) != commit:
        raise ValueError("project lifecycle performance Git state changed during qualification")
    for path, expected in captured.items():
        if governed_snapshot(repo, path) != expected:
            raise ValueError(f"governed performance input changed during qualification: {path.as_posix()}")
        if git_blob_sha256(repo, commit, path) != sha256_bytes(expected):
            raise ValueError(f"governed performance input differs from its state commit: {path.as_posix()}")


@contextmanager
def qualification_snapshot(repo: Path) -> Iterator[tuple[str, dict[Path, bytes]]]:
    canonical_tool = (repo / TOOL_PATH).resolve(strict=True)
    if Path(__file__).resolve(strict=True) != canonical_tool:
        raise ValueError("the executing performance tool is not the canonical repository tool")
    paths = [TOOL_PATH, IMPLEMENTATION_PATH, BASELINE_PATH, CALIBRATION_PATH]
    lexical_paths = [repo / path for path in paths]
    with windows_path_locks(lexical_paths, directories=False):
        commit = clean_state_commit(repo)
        captured = {path: governed_snapshot(repo, path) for path in paths}
        assert_committed_inputs(repo, commit, captured)
        try:
            yield commit, captured
        finally:
            assert_committed_inputs(repo, commit, captured)


def percentile(samples: list[float], probability: float) -> float:
    if not samples or not 0 < probability <= 1 or any(not math.isfinite(value) or value < 0 for value in samples):
        raise ValueError("percentile requires finite non-negative samples and a probability in (0, 1]")
    ordered = sorted(samples)
    return ordered[max(1, math.ceil(probability * len(ordered))) - 1]


def distribution(samples: list[float]) -> dict[str, Any]:
    if len(samples) != REPETITIONS:
        raise ValueError(f"project lifecycle performance requires exactly {REPETITIONS} measured samples")
    return {
        "samplesMs": [round(value, 3) for value in samples],
        "minimumMs": round(min(samples), 3),
        "p50Ms": round(percentile(samples, 0.50), 3),
        "p95Ms": round(percentile(samples, 0.95), 3),
        "maximumMs": round(max(samples), 3),
    }


def evaluated_measurement(samples: list[float], baseline_p95_ms: float) -> dict[str, Any]:
    if not math.isfinite(baseline_p95_ms) or baseline_p95_ms <= 0:
        raise ValueError("baseline p95 must be a finite positive number")
    measured = distribution(samples)
    raw_p95 = percentile(samples, 0.95)
    raw_relative_limit = min(ABSOLUTE_BUDGET_MS, baseline_p95_ms * (1 + REGRESSION_PERCENT / 100))
    return {
        **measured,
        "rawP95Ms": raw_p95,
        "absoluteBudgetMs": ABSOLUTE_BUDGET_MS,
        "passesAbsoluteBudget": raw_p95 <= ABSOLUTE_BUDGET_MS,
        "passesRegressionThreshold": raw_p95 <= raw_relative_limit,
        "regressionThreshold": {
            "baselineP95Ms": baseline_p95_ms,
            "maximumIncreasePercent": REGRESSION_PERCENT,
            "maximumP95Ms": round(raw_relative_limit, 3),
        },
    }


def valid_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def validate_hardware(value: Any) -> dict[str, Any]:
    fields = {
        "operatingSystem",
        "system",
        "release",
        "version",
        "machine",
        "processor",
        "logicalCpuCount",
        "physicalMemoryBytes",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("project lifecycle calibration hardware shape is invalid")
    text_fields = fields - {"logicalCpuCount", "physicalMemoryBytes"}
    if not all(isinstance(value[field], str) and value[field] for field in text_fields):
        raise ValueError("project lifecycle calibration hardware identity is invalid")
    for field in ("logicalCpuCount", "physicalMemoryBytes"):
        if isinstance(value[field], bool) or not isinstance(value[field], int) or value[field] <= 0:
            raise ValueError("project lifecycle calibration hardware capacity is invalid")
    if value != EXPECTED_CALIBRATION_HARDWARE:
        raise ValueError("project lifecycle calibration hardware differs from the reviewed workstation")
    return value


def calibration_report_hash(run: dict[str, Any]) -> str:
    payload = {key: item for key, item in run.items() if key != "reportSha256"}
    return sha256_bytes(canonical_json_bytes(payload))


def validate_calibration_document(value: Any, raw_sha256: str) -> dict[str, Any]:
    if raw_sha256 != EXPECTED_CALIBRATION_SHA256:
        raise ValueError("project lifecycle calibration bytes differ from the reviewed authority")
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion",
        "documentType",
        "profile",
        "selectionRule",
        "fixture",
        "methodology",
        "hardware",
        "runs",
    }:
        raise ValueError("project lifecycle calibration shape is invalid")
    if (
        value.get("schemaVersion") != "1.0"
        or value.get("documentType") != "project-lifecycle-performance-calibration"
        or value.get("profile") != "windows-x64"
        or value.get("selectionRule") != CALIBRATION_SELECTION_RULE
        or value.get("fixture") != EXPECTED_FIXTURE
        or value.get("methodology") != EXPECTED_METHODOLOGY
    ):
        raise ValueError("project lifecycle calibration identity is invalid")
    validate_hardware(value.get("hardware"))
    runs = value.get("runs")
    if not isinstance(runs, list) or len(runs) != len(CALIBRATION_CONTEXTS):
        raise ValueError("project lifecycle calibration run inventory is invalid")
    for index, run in enumerate(runs):
        if not isinstance(run, dict) or set(run) != {
            "context",
            "stateCommit",
            "reportSha256",
            "source",
            "fixture",
            "measurements",
        }:
            raise ValueError("project lifecycle calibration run shape is invalid")
        if run.get("context") != CALIBRATION_CONTEXTS[index]:
            raise ValueError("project lifecycle calibration context ordering is invalid")
        commit = run.get("stateCommit")
        if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ValueError("project lifecycle calibration state commit is invalid")
        if not valid_digest(run.get("reportSha256")) or run["reportSha256"] != calibration_report_hash(run):
            raise ValueError("project lifecycle calibration report bytes do not match their SHA-256")
        source = run.get("source")
        if not isinstance(source, dict) or set(source) != {
            "dirty",
            "measurementToolPath",
            "measurementToolSha256",
            "implementationPath",
            "implementationSha256",
        }:
            raise ValueError("project lifecycle calibration source shape is invalid")
        if (
            source.get("dirty") is not False
            or source.get("measurementToolPath") != TOOL_PATH.as_posix()
            or source.get("implementationPath") != IMPLEMENTATION_PATH.as_posix()
            or not valid_digest(source.get("measurementToolSha256"))
            or not valid_digest(source.get("implementationSha256"))
        ):
            raise ValueError("project lifecycle calibration source identity is invalid")
        fixture = run.get("fixture")
        if (
            not isinstance(fixture, dict)
            or set(fixture) != {*EXPECTED_FIXTURE, "manifestSha256", "profileSha256"}
            or any(fixture.get(field) != expected for field, expected in EXPECTED_FIXTURE.items())
            or not valid_digest(fixture.get("manifestSha256"))
            or not valid_digest(fixture.get("profileSha256"))
        ):
            raise ValueError("project lifecycle calibration fixture is invalid")
        measurements = run.get("measurements")
        if not isinstance(measurements, dict) or set(measurements) != set(EXPECTED_BASELINE_P95_MS):
            raise ValueError("project lifecycle calibration measurement inventory is invalid")
        for name, measurement in measurements.items():
            if not isinstance(measurement, dict) or set(measurement) != {
                "samplesMs",
                "minimumMs",
                "p50Ms",
                "p95Ms",
                "maximumMs",
            }:
                raise ValueError(f"project lifecycle calibration {name} shape is invalid")
            samples = measurement.get("samplesMs")
            if (
                not isinstance(samples, list)
                or len(samples) != REPETITIONS
                or any(isinstance(sample, bool) or not isinstance(sample, (int, float)) for sample in samples)
            ):
                raise ValueError(f"project lifecycle calibration {name} samples are invalid")
            if distribution([float(sample) for sample in samples]) != measurement:
                raise ValueError(f"project lifecycle calibration {name} statistics do not match retained samples")
    return value


def calibration_summary(calibration: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": CALIBRATION_PATH.as_posix(),
        "sha256": EXPECTED_CALIBRATION_SHA256,
        "selectionRule": CALIBRATION_SELECTION_RULE,
        "runs": [
            {
                "context": run["context"],
                "stateCommit": run["stateCommit"],
                "reportSha256": run["reportSha256"],
                "freshServiceOpenP95Ms": run["measurements"]["freshServiceOpen"]["p95Ms"],
                "warmServiceReopenP95Ms": run["measurements"]["warmServiceReopen"]["p95Ms"],
            }
            for run in calibration["runs"]
        ],
    }


def validate_baseline_document(value: Any, raw_sha256: str, calibration: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion",
        "documentType",
        "baselineSourceCommit",
        "profile",
        "fixture",
        "methodology",
        "source",
        "calibration",
        "measurements",
    }:
        raise ValueError("project lifecycle performance baseline shape is invalid")
    if value.get("schemaVersion") != "1.0" or value.get("documentType") != "project-lifecycle-performance-baseline":
        raise ValueError("project lifecycle performance baseline identity is invalid")
    if raw_sha256 != EXPECTED_BASELINE_SHA256:
        raise ValueError("project lifecycle performance baseline bytes differ from the reviewed authority")
    commit = value.get("baselineSourceCommit")
    if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("project lifecycle performance baseline source commit is invalid")
    if value.get("profile") != "windows-x64" or value.get("fixture") != EXPECTED_FIXTURE:
        raise ValueError("project lifecycle performance baseline profile or fixture is invalid")
    if value.get("methodology") != EXPECTED_METHODOLOGY:
        raise ValueError("project lifecycle performance baseline methodology is invalid")
    if value.get("calibration") != calibration_summary(calibration):
        raise ValueError("project lifecycle performance baseline calibration is invalid")
    source = value.get("source")
    if not isinstance(source, dict) or set(source) != {
        "measurementToolPath",
        "measurementToolSha256",
        "implementationPath",
        "implementationSha256",
    }:
        raise ValueError("project lifecycle performance baseline source identity is invalid")
    if (
        source.get("measurementToolPath") != TOOL_PATH.as_posix()
        or source.get("implementationPath") != IMPLEMENTATION_PATH.as_posix()
    ):
        raise ValueError("project lifecycle performance baseline source paths are invalid")
    if any(
        not isinstance(source.get(field), str)
        or len(source[field]) != 64
        or any(character not in "0123456789abcdef" for character in source[field])
        for field in ("measurementToolSha256", "implementationSha256")
    ):
        raise ValueError("project lifecycle performance baseline source hashes are invalid")
    measurements = value.get("measurements")
    if not isinstance(measurements, dict) or set(measurements) != set(EXPECTED_BASELINE_P95_MS):
        raise ValueError("project lifecycle performance baseline measurement inventory is invalid")
    for name, expected_p95 in EXPECTED_BASELINE_P95_MS.items():
        measurement = measurements.get(name)
        if not isinstance(measurement, dict) or set(measurement) != {"absoluteBudgetMs", "baselineP95Ms"}:
            raise ValueError(f"project lifecycle performance baseline {name} shape is invalid")
        if (
            measurement.get("absoluteBudgetMs") != ABSOLUTE_BUDGET_MS
            or measurement.get("baselineP95Ms") != expected_p95
        ):
            raise ValueError(f"project lifecycle performance baseline {name} values are invalid")
        calibration_field = f"{name}P95Ms"
        selected_p95 = max(float(run[calibration_field]) for run in calibration_summary(calibration)["runs"])
        if expected_p95 != selected_p95:
            raise ValueError(f"project lifecycle performance baseline {name} is not the maximum calibrated p95")
    return value


def load_calibration(repo: Path) -> dict[str, Any]:
    raw = governed_snapshot(repo, CALIBRATION_PATH)
    calibration = validate_calibration_document(json.loads(raw.decode("utf-8")), sha256_bytes(raw))
    for run in calibration["runs"]:
        source_commit = run["stateCommit"]
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
            cwd=repo,
            capture_output=True,
            check=False,
        )
        if ancestor.returncode:
            raise ValueError("project lifecycle calibration state is not reachable from HEAD")
        source = run["source"]
        if git_blob_sha256(repo, source_commit, TOOL_PATH) != source["measurementToolSha256"]:
            raise ValueError("project lifecycle calibration tool does not match its state commit")
        if git_blob_sha256(repo, source_commit, IMPLEMENTATION_PATH) != source["implementationSha256"]:
            raise ValueError("project lifecycle calibration implementation does not match its state commit")
    return calibration


def load_baseline(repo: Path, calibration: dict[str, Any]) -> dict[str, Any]:
    raw = governed_snapshot(repo, BASELINE_PATH)
    value = json.loads(raw.decode("utf-8"))
    baseline = validate_baseline_document(value, sha256_bytes(raw), calibration)
    source_commit = str(baseline["baselineSourceCommit"])
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if ancestor.returncode:
        raise ValueError("project lifecycle performance baseline source is not reachable from HEAD")
    source = baseline["source"]
    if git_blob_sha256(repo, source_commit, TOOL_PATH) != source["measurementToolSha256"]:
        raise ValueError("project lifecycle performance baseline tool does not match its source commit")
    if git_blob_sha256(repo, source_commit, IMPLEMENTATION_PATH) != source["implementationSha256"]:
        raise ValueError("project lifecycle performance baseline implementation does not match its source commit")
    return baseline


def add_representative_objects(root: Path) -> None:
    objects = root / "objects"
    payload = b"x" * OBJECT_FILE_BYTES
    for index in range(OBJECT_FILE_COUNT):
        bucket = objects / f"{index % 20:02d}"
        bucket.mkdir(exist_ok=True)
        (bucket / f"object-{index:04d}.bin").write_bytes(payload)


def verify_projection(projection: Any) -> None:
    if (
        projection.open is not True
        or str(projection.access_mode) != "read-write"
        or str(projection.compatibility_state) != "compatible"
        or projection.package_format_version != "1.0.0"
    ):
        raise ValueError("project lifecycle benchmark did not reach the compatible read-write projection")


def timed_open(service: Any, root: Path) -> float:
    started = time.perf_counter_ns()
    projection = service.open(root=str(root), trace_id="a" * 32)
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    verify_projection(projection)
    return elapsed_ms


def measure(repo: Path) -> tuple[dict[str, list[float]], dict[str, Any]]:
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("project lifecycle performance qualification requires Windows x64")
    service_src = repo / "services" / "core-api" / "src"
    sys.path.insert(0, str(service_src))
    try:
        from research_observatory_core.projects import ProjectLifecycleService
    finally:
        sys.path.pop(0)

    scratch = repo / "artifacts" / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="project-lifecycle-performance-", dir=scratch) as temporary:
        parent = Path(temporary) / "projects"
        parent.mkdir()
        creator = ProjectLifecycleService()
        created = creator.create(
            parent_directory=str(parent),
            directory_name="ordinary-study",
            display_name="Ordinary Study",
            template_id="theory-synthesis",
            trace_id="a" * 32,
        )
        creator.shutdown()
        root = Path(created.root)
        add_representative_objects(root)
        manifest = root / "project.ro.json"
        profile = root / "config" / "project-profile.json"
        manifest_before = manifest.read_bytes()
        profile_before = profile.read_bytes()

        fresh: list[float] = []
        for _ in range(REPETITIONS):
            service = ProjectLifecycleService()
            try:
                fresh.append(timed_open(service, root))
                service.close(root=str(root), trace_id="a" * 32)
            finally:
                service.shutdown()

        warm_service = ProjectLifecycleService()
        try:
            for _ in range(WARMUP_REPETITIONS):
                timed_open(warm_service, root)
                warm_service.close(root=str(root), trace_id="a" * 32)
            warm: list[float] = []
            for _ in range(REPETITIONS):
                warm.append(timed_open(warm_service, root))
                warm_service.close(root=str(root), trace_id="a" * 32)
        finally:
            warm_service.shutdown()

        if manifest.read_bytes() != manifest_before or profile.read_bytes() != profile_before:
            raise ValueError("project lifecycle benchmark mutated the governed manifest or profile")
        object_files = list((root / "objects").glob("*/*.bin"))
        if (
            len(object_files) != OBJECT_FILE_COUNT
            or sum(path.stat().st_size for path in object_files) != EXPECTED_FIXTURE["objectBytes"]
        ):
            raise ValueError("project lifecycle benchmark fixture inventory changed during measurement")
        fixture = {
            **EXPECTED_FIXTURE,
            "manifestSha256": sha256_bytes(manifest_before),
            "profileSha256": sha256_bytes(profile_before),
        }
        return {"freshServiceOpen": fresh, "warmServiceReopen": warm}, fixture


def _benchmark_under_snapshot(
    repo: Path, state_commit: str, captured: dict[Path, bytes], *, measure_only: bool = False
) -> dict[str, Any]:
    calibration = load_calibration(repo)
    baseline = load_baseline(repo, calibration)
    measured_hardware = hardware_record()
    if measured_hardware != calibration["hardware"]:
        raise ValueError("project lifecycle performance hardware differs from the reviewed calibration hardware")
    samples, fixture = measure(repo)
    source = {
        "stateCommit": state_commit,
        "dirty": False,
        "measurementToolPath": TOOL_PATH.as_posix(),
        "measurementToolSha256": sha256_bytes(captured[TOOL_PATH]),
        "implementationPath": IMPLEMENTATION_PATH.as_posix(),
        "implementationSha256": sha256_bytes(captured[IMPLEMENTATION_PATH]),
    }
    if measure_only:
        measurements = {name: distribution(values) for name, values in samples.items()}
        return {
            "schemaVersion": "1.0",
            "documentType": "project-lifecycle-performance-report",
            "ok": False,
            "qualified": False,
            "profile": "windows-x64",
            "source": source,
            "hardware": measured_hardware,
            "fixture": fixture,
            "methodology": EXPECTED_METHODOLOGY,
            "measurements": measurements,
            "errors": ["measurement-only reports are not qualification evidence"],
        }
    measurements = {
        name: evaluated_measurement(values, EXPECTED_BASELINE_P95_MS[name]) for name, values in samples.items()
    }
    errors = [
        f"{name} exceeded its absolute or reviewed regression threshold"
        for name, measurement in measurements.items()
        if not measurement["passesAbsoluteBudget"] or not measurement["passesRegressionThreshold"]
    ]
    return {
        "schemaVersion": "1.0",
        "documentType": "project-lifecycle-performance-report",
        "ok": not errors,
        "qualified": not errors,
        "profile": "windows-x64",
        "source": source,
        "baseline": {
            "path": BASELINE_PATH.as_posix(),
            "sha256": EXPECTED_BASELINE_SHA256,
            "sourceCommit": baseline["baselineSourceCommit"],
        },
        "hardware": measured_hardware,
        "fixture": fixture,
        "methodology": EXPECTED_METHODOLOGY,
        "measurements": measurements,
        "errors": errors,
    }


def benchmark(repo: Path, *, measure_only: bool = False) -> dict[str, Any]:
    with qualification_snapshot(repo) as (state_commit, captured):
        return _benchmark_under_snapshot(repo, state_commit, captured, measure_only=measure_only)


def nonqualifying_report(
    error: str, *, measure_only: bool = False, qualification_phase: str = "COMPLETE"
) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "documentType": "project-lifecycle-performance-nonqualification",
        "qualificationStatus": "NONQUALIFYING",
        "qualificationPhase": qualification_phase,
        "measurementOnly": measure_only,
        "ok": False,
        "qualified": False,
        "errors": [error],
    }


def run(repo: Path, destination: Path, *, measure_only: bool = False) -> tuple[dict[str, Any], int]:
    tombstone = nonqualifying_report(
        "project lifecycle performance qualification has not completed",
        measure_only=measure_only,
        qualification_phase="IN_PROGRESS",
    )
    guarded_atomic_write_json(repo, destination, tombstone, repo / "artifacts" / "tmp")
    try:
        with qualification_snapshot(repo) as (state_commit, captured):
            report = _benchmark_under_snapshot(repo, state_commit, captured, measure_only=measure_only)
            guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
    except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        report = nonqualifying_report(str(exc), measure_only=measure_only)
        try:
            guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
        except (OSError, UnicodeError, ValueError, RuntimeError) as publication_exc:
            report["errors"].append(
                f"final nonqualifying report publication failed; the IN_PROGRESS tombstone remains: {publication_exc}"
            )
    return report, 0 if report.get("ok") is True and report.get("qualified") is True else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--measure-only", action="store_true")
    args = parser.parse_args()
    report: dict[str, Any]
    try:
        repo = args.repo.resolve(strict=True)
        destination = safe_output_path(repo, args.report)
        report, return_code = run(repo, destination, measure_only=args.measure_only)
    except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        report = nonqualifying_report(str(exc), measure_only=args.measure_only)
        return_code = 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
