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
from pathlib import Path
from typing import Any

from build_manifest import guarded_atomic_write_json, safe_output_path

TOOL_PATH = Path("tools/project_lifecycle_performance_check.py")
IMPLEMENTATION_PATH = Path("services/core-api/src/research_observatory_core/projects.py")
BASELINE_PATH = Path("verification/baselines/project-lifecycle-performance.json")
EXPECTED_BASELINE_SHA256 = "67f3fd35d56fb38a37481ee87a4eb41e7ff2dca632b37c54bf54cf0ffdfa4a72"
EXPECTED_BASELINE_P95_MS = {
    "freshServiceOpen": 14.389,
    "warmServiceReopen": 13.238,
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


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


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
    p95 = float(measured["p95Ms"])
    relative_limit = round(min(ABSOLUTE_BUDGET_MS, baseline_p95_ms * 1.2), 3)
    return {
        **measured,
        "absoluteBudgetMs": ABSOLUTE_BUDGET_MS,
        "passesAbsoluteBudget": p95 <= ABSOLUTE_BUDGET_MS,
        "passesRegressionThreshold": p95 <= relative_limit,
        "regressionThreshold": {
            "baselineP95Ms": baseline_p95_ms,
            "maximumIncreasePercent": REGRESSION_PERCENT,
            "maximumP95Ms": relative_limit,
        },
    }


def validate_baseline_document(value: Any, raw_sha256: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion",
        "documentType",
        "baselineSourceCommit",
        "profile",
        "fixture",
        "methodology",
        "source",
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
    return value


def load_baseline(repo: Path) -> dict[str, Any]:
    path = repo / BASELINE_PATH
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    baseline = validate_baseline_document(value, sha256_bytes(raw))
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


def benchmark(repo: Path, *, measure_only: bool = False) -> dict[str, Any]:
    state_commit = clean_state_commit(repo)
    samples, fixture = measure(repo)
    source = {
        "stateCommit": state_commit,
        "dirty": False,
        "measurementToolPath": TOOL_PATH.as_posix(),
        "measurementToolSha256": file_sha256(repo / TOOL_PATH),
        "implementationPath": IMPLEMENTATION_PATH.as_posix(),
        "implementationSha256": file_sha256(repo / IMPLEMENTATION_PATH),
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
            "hardware": hardware_record(),
            "fixture": fixture,
            "methodology": EXPECTED_METHODOLOGY,
            "measurements": measurements,
            "errors": ["measurement-only reports are not qualification evidence"],
        }
    baseline = load_baseline(repo)
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
        "hardware": hardware_record(),
        "fixture": fixture,
        "methodology": EXPECTED_METHODOLOGY,
        "measurements": measurements,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--measure-only", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    try:
        destination = safe_output_path(repo, args.report)
        report = benchmark(repo, measure_only=args.measure_only)
        guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        report = {
            "schemaVersion": "1.0",
            "documentType": "project-lifecycle-performance-report",
            "ok": False,
            "qualified": False,
            "errors": [str(exc)],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") is True and report.get("qualified") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
