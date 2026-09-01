#!/usr/bin/env python3
"""Benchmark the packaged Core sidecar against S03 startup/resource budgets."""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import math
import os
import platform
import queue
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import IO, Any

from build_manifest import (
    destination_guard,
    guarded_atomic_write_json,
    held_file_renamer,
    path_identity,
    safe_output_path,
    validate_directory_guard,
    windows_path_locks,
)
from core_sidecar_build import SCHEMA_PATH, load_build_contract, verify_artifact

REPETITIONS = 7
REGRESSION_PERCENT = 20
READINESS_BUDGET_MS = 3_000.0
SHUTDOWN_BUDGET_MS = 5_000.0
IDLE_MEMORY_BUDGET_BYTES = 268_435_456
BASELINE_PATH = Path("verification/baselines/core-sidecar-performance.json")
BASELINE_HASH_PATH = Path("verification/baselines/core-sidecar-performance.sha256")
TARGET_TRIPLE = "x86_64-pc-windows-msvc"
ENTRYPOINT = f"research-observatory-core-{TARGET_TRIPLE}.exe"
ARTIFACT_PATH = Path("artifacts/tmp/core-sidecar-package/dist") / ENTRYPOINT.removesuffix(".exe") / ENTRYPOINT
ARTIFACT_ROOT_PATH = ARTIFACT_PATH.parent
PACKAGE_REPORT_PATH = Path("artifacts/tmp/core-sidecar-package.json")
CONTRACT_PATH = Path("services/core-api/packaging/sidecar-build.json")
TOOL_PATH = Path("tools/core_sidecar_performance_check.py")
PACKAGE_EVIDENCE_PATH = Path("artifacts/evidence/CAP-02.S02.T03.review-fix-2.json")
PACKAGE_EVIDENCE_SHA256 = "89da43c32339f6360710a03d86f13b83cb2ce4fdd3e61084947485d8bda7c6f4"


class ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("pageFaultCount", ctypes.c_ulong),
        ("peakWorkingSetSize", ctypes.c_size_t),
        ("workingSetSize", ctypes.c_size_t),
        ("quotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("quotaPagedPoolUsage", ctypes.c_size_t),
        ("quotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("quotaNonPagedPoolUsage", ctypes.c_size_t),
        ("pagefileUsage", ctypes.c_size_t),
        ("peakPagefileUsage", ctypes.c_size_t),
        ("privateUsage", ctypes.c_size_t),
    ]


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(len(ordered) * probability)) - 1]


def distribution(values: list[float]) -> dict[str, Any]:
    if len(values) != REPETITIONS or any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError(f"Core performance requires exactly {REPETITIONS} finite positive samples")
    return {
        # These values are qualification authority, not presentation-only
        # summaries. Retain their raw binary-float values so threshold checks
        # cannot admit a measurement that only rounds down to the boundary.
        "samples": list(values),
        "minimum": min(values),
        "p50": statistics.median(values),
        "p95": percentile(values, 0.95),
        "maximum": max(values),
    }


def hardware_record() -> dict[str, Any]:
    memory = MemoryStatusEx()
    memory.length = ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise ValueError("physical memory identity is unavailable")
    return {
        "operatingSystem": platform.platform(aliased=False, terse=False),
        "machine": platform.machine(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER") or "unreported",
        "logicalCpuCount": os.cpu_count(),
        "physicalMemoryBytes": int(memory.totalPhysicalBytes),
    }


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def exact_file(repo: Path, relative: Path) -> Path:
    candidate = repo / relative
    current = repo
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise ValueError(f"redirected benchmark input is not allowed: {relative.as_posix()}")
    resolved = candidate.resolve(strict=True)
    if resolved != candidate or not candidate.is_file():
        raise ValueError(f"benchmark input must be a canonical regular file: {relative.as_posix()}")
    return candidate


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value, payload


def expected_methodology() -> dict[str, Any]:
    return {
        "state": (
            "cold packaged process with no project open; one unmeasured filesystem warmup "
            "before seven measured process lifecycles"
        ),
        "repetitions": REPETITIONS,
        "distribution": "nearest-rank p50 and p95; no measured sample discarded",
        "memory": "root-process working set sampled after strict ready response and 100 ms idle stabilization",
        "regressionThresholdPercent": REGRESSION_PERCENT,
        "hardwareQualification": "representative measured Windows x64 workstation",
    }


def validate_baseline(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion",
        "documentType",
        "baselineSourceCommit",
        "profile",
        "provenance",
        "hardware",
        "fixture",
        "methodology",
        "rawMeasurements",
        "measurements",
    }:
        raise ValueError("Core performance baseline has unexpected or missing fields")
    if value.get("schemaVersion") != "1.0" or value.get("documentType") != "core-sidecar-performance-baseline":
        raise ValueError("Core performance baseline identity is invalid")
    commit = value.get("baselineSourceCommit")
    if not isinstance(commit, str) or len(commit) != 40 or any(item not in "0123456789abcdef" for item in commit):
        raise ValueError("Core performance baseline source commit is invalid")
    if value.get("profile") != "windows-x64":
        raise ValueError("Core performance baseline profile is invalid")
    provenance = value.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != {
        "measurementToolCommit",
        "measurementToolPath",
        "packageEvidencePath",
        "packageEvidenceSha256",
        "packageReportSha256",
        "artifactManifestSha256",
        "measurementToolSha256",
    }:
        raise ValueError("Core performance baseline provenance is invalid")
    if (
        provenance.get("measurementToolCommit") != commit
        or provenance.get("measurementToolPath") != TOOL_PATH.as_posix()
        or provenance.get("packageEvidencePath") != PACKAGE_EVIDENCE_PATH.as_posix()
        or provenance.get("packageEvidenceSha256") != PACKAGE_EVIDENCE_SHA256
    ):
        raise ValueError("Core performance baseline provenance identity is invalid")
    for field in ("packageReportSha256", "artifactManifestSha256", "measurementToolSha256"):
        digest = provenance.get(field)
        if not isinstance(digest, str) or len(digest) != 64 or any(item not in "0123456789abcdef" for item in digest):
            raise ValueError(f"Core performance baseline {field} is invalid")
    hardware = value.get("hardware")
    if not isinstance(hardware, dict) or set(hardware) != {
        "operatingSystem",
        "machine",
        "processor",
        "logicalCpuCount",
        "physicalMemoryBytes",
    }:
        raise ValueError("Core performance baseline hardware identity is invalid")
    if (
        not all(
            isinstance(hardware.get(field), str) and hardware[field]
            for field in ("operatingSystem", "machine", "processor")
        )
        or not isinstance(hardware.get("logicalCpuCount"), int)
        or isinstance(hardware.get("logicalCpuCount"), bool)
        or hardware["logicalCpuCount"] <= 0
        or not isinstance(hardware.get("physicalMemoryBytes"), int)
        or isinstance(hardware.get("physicalMemoryBytes"), bool)
        or hardware["physicalMemoryBytes"] <= 0
    ):
        raise ValueError("Core performance baseline hardware values are invalid")
    fixture = value.get("fixture")
    if not isinstance(fixture, dict) or set(fixture) != {
        "buildContractSha256",
        "targetTriple",
        "componentVersion",
        "entrypointSha256",
        "fileCount",
        "totalBytes",
    }:
        raise ValueError("Core performance baseline fixture is invalid")
    if fixture.get("targetTriple") != TARGET_TRIPLE or fixture.get("componentVersion") != "0.1.0":
        raise ValueError("Core performance baseline fixture identity is invalid")
    for field in ("buildContractSha256", "entrypointSha256"):
        digest = fixture.get(field)
        if not isinstance(digest, str) or len(digest) != 64 or any(item not in "0123456789abcdef" for item in digest):
            raise ValueError(f"Core performance baseline {field} is invalid")
    if (
        not isinstance(fixture.get("fileCount"), int)
        or isinstance(fixture.get("fileCount"), bool)
        or fixture["fileCount"] <= 0
        or not isinstance(fixture.get("totalBytes"), int)
        or isinstance(fixture.get("totalBytes"), bool)
        or fixture["totalBytes"] <= 0
    ):
        raise ValueError("Core performance baseline inventory identity is invalid")
    if value.get("methodology") != expected_methodology():
        raise ValueError("Core performance baseline methodology is invalid")
    raw = value.get("rawMeasurements")
    if not isinstance(raw, dict) or set(raw) != {"readinessMs", "shutdownMs", "idleWorkingSetBytes"}:
        raise ValueError("Core performance baseline raw measurement inventory is invalid")
    for name, item in raw.items():
        if not isinstance(item, dict) or set(item) != {"samples", "minimum", "p50", "p95", "maximum"}:
            raise ValueError(f"Core performance baseline raw {name} shape is invalid")
        samples = item.get("samples")
        if (
            not isinstance(samples, list)
            or len(samples) != REPETITIONS
            or any(
                isinstance(sample, bool)
                or not isinstance(sample, (int, float))
                or not math.isfinite(sample)
                or sample <= 0
                for sample in samples
            )
        ):
            raise ValueError(f"Core performance baseline raw {name} samples are invalid")
        if item != distribution([float(sample) for sample in samples]):
            raise ValueError(f"Core performance baseline raw {name} aggregates do not match retained samples")
    measurements = value.get("measurements")
    expected = {
        "readinessMs": ("baselineP50", "absoluteBudget", READINESS_BUDGET_MS),
        "shutdownMs": ("baselineP95", "absoluteBudget", SHUTDOWN_BUDGET_MS),
        "idleWorkingSetBytes": ("baselineP95", "absoluteBudget", IDLE_MEMORY_BUDGET_BYTES),
    }
    if not isinstance(measurements, dict) or set(measurements) != set(expected):
        raise ValueError("Core performance baseline measurement inventory is invalid")
    for name, (baseline_field, budget_field, budget) in expected.items():
        measurement = measurements.get(name)
        if not isinstance(measurement, dict) or set(measurement) != {baseline_field, budget_field}:
            raise ValueError(f"Core performance baseline {name} shape is invalid")
        baseline = measurement.get(baseline_field)
        if (
            isinstance(baseline, bool)
            or not isinstance(baseline, (int, float))
            or not math.isfinite(baseline)
            or baseline <= 0
            or measurement.get(budget_field) != budget
            or baseline > budget
        ):
            raise ValueError(f"Core performance baseline {name} values are invalid")
        statistic = "p50" if baseline_field == "baselineP50" else "p95"
        if float(baseline) != float(raw[name][statistic]):
            raise ValueError(f"Core performance baseline {name} does not match retained samples")
    return value


def load_baseline(repo: Path) -> tuple[dict[str, Any], str]:
    value, payload = load_json(exact_file(repo, BASELINE_PATH))
    digest = hashlib.sha256(payload).hexdigest()
    expected_hash_payload = exact_file(repo, BASELINE_HASH_PATH).read_bytes()
    try:
        expected_hash = expected_hash_payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Core performance baseline hash authority is not ASCII") from exc
    if (
        len(expected_hash_payload) != 65
        or not expected_hash.endswith("\n")
        or any(item not in "0123456789abcdef" for item in expected_hash[:-1])
    ):
        raise ValueError("Core performance baseline hash authority is invalid")
    if digest != expected_hash[:-1]:
        raise ValueError("Core performance baseline bytes do not match the immutable reviewed SHA-256")
    baseline = validate_baseline(value)
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline["baselineSourceCommit"], "HEAD"],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if ancestry.returncode:
        raise ValueError("Core performance baseline source commit is not an ancestor of HEAD")
    tool_at_source = subprocess.run(
        ["git", "show", f"{baseline['provenance']['measurementToolCommit']}:{TOOL_PATH.as_posix()}"],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if tool_at_source.returncode:
        raise ValueError("Core performance measurement tool is absent from its claimed source commit")
    if hashlib.sha256(tool_at_source.stdout).hexdigest() != baseline["provenance"]["measurementToolSha256"]:
        raise ValueError("Core performance measurement tool differs from its approved source bytes")
    return baseline, digest


def current_measurement_state(repo: Path) -> tuple[str, str]:
    commit = git_head(repo)
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=no"],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if status.returncode or status.stdout:
        raise ValueError("Core performance qualification requires a clean tracked Git state")
    tool = exact_file(repo, TOOL_PATH)
    tool_payload = tool.read_bytes()
    tool_hash = hashlib.sha256(tool_payload).hexdigest()
    committed_tool = subprocess.run(
        ["git", "show", f"{commit}:{TOOL_PATH.as_posix()}"],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if committed_tool.returncode or committed_tool.stdout != tool_payload:
        raise ValueError("The executing Core performance tool differs from the clean Git state")
    return commit, tool_hash


def clean_measurement_state(repo: Path, baseline: dict[str, Any]) -> tuple[str, str]:
    commit, tool_hash = current_measurement_state(repo)
    provenance = baseline["provenance"]
    if provenance["measurementToolPath"] != TOOL_PATH.as_posix() or provenance["measurementToolSha256"] != tool_hash:
        raise ValueError("The executing Core performance tool differs from the approved measurement tool")
    return commit, tool_hash


def git_blob(repo: Path, commit: str, path: Path) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path.as_posix()}"],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ValueError(f"Core performance governed input is absent from {commit}: {path.as_posix()}")
    return result.stdout


def qualification_paths() -> tuple[Path, ...]:
    return (
        TOOL_PATH,
        BASELINE_PATH,
        BASELINE_HASH_PATH,
        PACKAGE_EVIDENCE_PATH,
        CONTRACT_PATH,
        SCHEMA_PATH,
    )


def assert_qualification_inputs(repo: Path, snapshot: dict[str, Any]) -> None:
    commit = str(snapshot["stateCommit"])
    tool_hash = str(snapshot["toolSha256"])
    if current_measurement_state(repo) != (commit, tool_hash):
        raise ValueError("Core performance Git state changed during qualification")
    captured = snapshot["trackedInputs"]
    if not isinstance(captured, dict):
        raise ValueError("Core performance captured-input authority is invalid")
    for path, expected in captured.items():
        if not isinstance(path, Path) or not isinstance(expected, bytes):
            raise ValueError("Core performance captured-input authority is invalid")
        current = exact_file(repo, path).read_bytes()
        if current != expected or git_blob(repo, commit, path) != expected:
            raise ValueError(f"Core performance governed input changed: {path.as_posix()}")
    baseline, baseline_hash = load_baseline(repo)
    if baseline != snapshot["baseline"] or baseline_hash != snapshot["baselineSha256"]:
        raise ValueError("Core performance baseline changed during qualification")
    artifact_root, manifest, identity, report_payload = load_verified_package(repo)
    if (
        artifact_root != snapshot["artifactRoot"]
        or manifest != snapshot["manifest"]
        or identity != snapshot["identity"]
        or report_payload != snapshot["packageReportBytes"]
    ):
        raise ValueError("Core package identity changed during performance qualification")
    contract = load_build_contract(repo)
    schema, _schema_payload = load_json(exact_file(repo, SCHEMA_PATH))
    assert_package_snapshot(artifact_root, manifest, contract, schema)


@contextmanager
def qualification_snapshot(repo: Path) -> Iterator[dict[str, Any]]:
    """Hold every qualification authority through the final PASS replacement."""
    canonical_tool = (repo / TOOL_PATH).resolve(strict=True)
    if Path(__file__).resolve(strict=True) != canonical_tool:
        raise ValueError("the executing Core performance tool is not the canonical repository tool")

    # The first read discovers the exact package inventory. Everything is then
    # locked and reread before it becomes qualification authority.
    initial_root, initial_manifest, _initial_identity, _initial_report = load_verified_package(repo)
    artifact_files = [initial_root / str(item["path"]) for item in initial_manifest["files"]]
    governed_files = [repo / path for path in (*qualification_paths(), PACKAGE_REPORT_PATH)]
    with windows_path_locks([*governed_files, *artifact_files], directories=False):
        baseline, baseline_hash = load_baseline(repo)
        artifact_root, manifest, identity, report_payload = load_verified_package(repo)
        if artifact_root != initial_root:
            raise ValueError("Core package root changed before qualification locking")
        commit, tool_hash = clean_measurement_state(repo, baseline)
        captured = {path: exact_file(repo, path).read_bytes() for path in qualification_paths()}
        for path, payload in captured.items():
            if git_blob(repo, commit, path) != payload:
                raise ValueError(f"Core performance governed input differs from Git state: {path.as_posix()}")

        package_guard = immutable_package_snapshot(repo, artifact_root, manifest)
        package_guard.__enter__()
        snapshot: dict[str, Any] = {
            "stateCommit": commit,
            "toolSha256": tool_hash,
            "trackedInputs": captured,
            "baseline": baseline,
            "baselineSha256": baseline_hash,
            "artifactRoot": artifact_root,
            "manifest": manifest,
            "identity": identity,
            "packageReportBytes": report_payload,
        }
        try:
            assert_qualification_inputs(repo, snapshot)
            yield snapshot
        except BaseException:
            exception = sys.exc_info()
            with suppress(BaseException):
                package_guard.__exit__(*exception)
            raise
        else:
            # After an atomic PASS replacement, cleanup must not create a new
            # rejecting state. Handle/ACL cleanup is intentionally best effort.
            with suppress(BaseException):
                package_guard.__exit__(None, None, None)


def guarded_final_publication(
    repo: Path,
    destination: Path,
    value: Any,
    allowed_root: Path,
    before_replace: Callable[[], None],
) -> None:
    """Publish PASS with the atomic replacement as the last rejecting action."""
    repo = repo.resolve(strict=True)
    parent = destination.absolute().parent
    relative_parent = parent.relative_to(repo)
    directory_chain = [repo]
    cursor = repo
    for part in relative_parent.parts:
        cursor /= part
        directory_chain.append(cursor)
    temporary: Path | None = None
    replaced = False
    encoded = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with windows_path_locks(directory_chain, directories=True):
            guard = destination_guard(repo, destination, allowed_root)
            validate_directory_guard(guard)
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=destination.name, delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temporary_identity = path_identity(temporary)
            with held_file_renamer(temporary) as (replace_held, read_held):
                validate_directory_guard(guard)
                if path_identity(temporary) != temporary_identity or read_held() != encoded:
                    raise ValueError("temporary Core qualification JSON changed before publication")
                before_replace()
                replace_held(destination)
                replaced = True
    except OSError, ValueError:
        if not replaced and temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def current_user_sid() -> str:
    system_root = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    whoami = system_root / "System32" / "whoami.exe"
    result = subprocess.run(
        [str(whoami), "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        check=False,
        timeout=30,
    )
    try:
        row = next(csv.reader([result.stdout.decode("utf-8")]))
    except (UnicodeDecodeError, csv.Error, StopIteration) as exc:
        raise ValueError("Current Windows user SID is unavailable") from exc
    sid = row[1] if len(row) == 2 else ""
    parts = sid.split("-")
    if result.returncode or len(parts) < 4 or parts[0] != "S" or any(not item.isdigit() for item in parts[1:]):
        raise ValueError("Current Windows user SID is invalid")
    return sid


def icacls(repo: Path, arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
    system_root = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    executable = system_root / "System32" / "icacls.exe"
    return subprocess.run(
        [str(executable), *arguments],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=120,
    )


@contextmanager
def immutable_package_snapshot(repo: Path, root: Path, manifest: dict[str, Any]) -> Iterator[None]:
    """Deny snapshot mutation and hold every known path against replacement on Windows."""
    if os.name != "nt":
        raise ValueError("Core package snapshot immutability requires Windows")
    sid = current_user_sid()
    deny = f"*{sid}:(OI)(CI)(WD,AD,WEA,WA,DE,DC)"
    applied = icacls(repo, [str(root), "/deny", deny, "/t", "/c", "/q"])
    if applied.returncode:
        icacls(repo, [str(root), "/remove:d", f"*{sid}", "/t", "/c", "/q"])
        diagnostic = (applied.stderr or applied.stdout).decode("utf-8", errors="replace").strip()
        raise ValueError(f"Core package snapshot could not be made read-only: {diagnostic}")
    body_error: BaseException | None = None
    try:
        probe = root / ".ro-benchmark-write-probe"
        try:
            descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except PermissionError:
            pass
        else:
            os.close(descriptor)
            raise ValueError("Core package snapshot write denial is ineffective")
        files = [root / str(item["path"]) for item in manifest["files"]]
        directories = {root}
        for path in files:
            cursor = path.parent
            while cursor != root:
                directories.add(cursor)
                cursor = cursor.parent
        with (
            windows_path_locks(list(directories), directories=True),
            windows_path_locks(files, directories=False),
        ):
            yield
    except BaseException as exc:
        body_error = exc
        raise
    finally:
        restored = icacls(repo, [str(root), "/remove:d", f"*{sid}", "/t", "/c", "/q"])
        if restored.returncode and body_error is None:
            diagnostic = (restored.stderr or restored.stdout).decode("utf-8", errors="replace").strip()
            raise ValueError(f"Core package snapshot permissions could not be restored: {diagnostic}")


def package_configuration_identity() -> dict[str, Any]:
    return {
        "configuration": {
            "bindHost": "loopback",
            "bindPort": "ephemeral",
            "profile": "local",
            "schemaVersion": "1.0",
        },
        "schemaVersion": "1.0",
        "service": "research-observatory-core",
        "status": "configuration-valid",
    }


def load_verified_package(repo: Path) -> tuple[Path, dict[str, Any], dict[str, Any], bytes]:
    report_path = exact_file(repo, PACKAGE_REPORT_PATH)
    report, report_payload = load_json(report_path)
    if set(report) != {"ok", "artifactRoot", "manifest", "configurationCheck"} or report.get("ok") is not True:
        raise ValueError("Core package report identity is invalid")
    expected_root = ARTIFACT_ROOT_PATH.as_posix()
    if (
        report.get("artifactRoot") != expected_root
        or report.get("configurationCheck") != package_configuration_identity()
    ):
        raise ValueError("Core package report does not identify the approved artifact/configuration")
    manifest = report.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError("Core package report manifest is invalid")
    contract = load_build_contract(repo)
    schema, _payload = load_json(exact_file(repo, SCHEMA_PATH))
    artifact_root = (repo / ARTIFACT_ROOT_PATH).resolve(strict=True)
    if artifact_root != repo / ARTIFACT_ROOT_PATH:
        raise ValueError("Core package artifact root is redirected")
    errors = verify_artifact(artifact_root, manifest, schema=schema, contract=contract)
    if errors:
        raise ValueError("Core package inventory is invalid: " + "; ".join(errors))
    evidence = exact_file(repo, PACKAGE_EVIDENCE_PATH)
    if sha256(evidence) != PACKAGE_EVIDENCE_SHA256:
        raise ValueError("Core package evidence does not match its approved SHA-256")
    entry = next(
        (
            item
            for item in manifest["files"]
            if isinstance(item, dict) and item.get("path") == manifest.get("entrypoint")
        ),
        None,
    )
    if not isinstance(entry, dict):
        raise ValueError("Core package manifest omits its entrypoint identity")
    identity = {
        "packageReportSha256": hashlib.sha256(report_payload).hexdigest(),
        "artifactManifestSha256": canonical_json_sha256(manifest),
        "buildContractSha256": sha256(repo / CONTRACT_PATH),
        "entrypointSha256": entry["sha256"],
        "targetTriple": manifest["targetTriple"],
        "componentVersion": manifest["componentVersion"],
        "fileCount": len(manifest["files"]),
        "totalBytes": manifest["totalBytes"],
    }
    return artifact_root, manifest, identity, report_payload


def assert_package_snapshot(
    root: Path,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    errors = verify_artifact(root, manifest, schema=schema, contract=contract)
    if errors:
        raise ValueError("Core benchmark package snapshot changed: " + "; ".join(errors))


def validate_handshake(value: Any, pid: int) -> int:
    if not isinstance(value, dict) or set(value) != {
        "protocolVersion",
        "buildId",
        "pid",
        "host",
        "port",
        "nonce",
        "capabilities",
        "databaseCompatibility",
        "diagnosticCode",
    }:
        raise ValueError("Core benchmark received an invalid handshake shape")
    nonce = value.get("nonce")
    port = value.get("port")
    if (
        value.get("protocolVersion") != "1.0"
        or value.get("buildId") != "0.1.0"
        or value.get("pid") != pid
        or value.get("host") != "127.0.0.1"
        or not isinstance(port, int)
        or isinstance(port, bool)
        or not 1 <= port <= 65_535
        or not isinstance(nonce, str)
        or len(nonce) != 32
        or any(item not in "0123456789abcdef" for item in nonce)
        or value.get("capabilities")
        != [
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
            "provenance.lineage.read",
            "runtime.contract",
            "runtime.status",
            "workflows.cancel",
            "workflows.human-decisions",
            "workflows.read",
            "workflows.retry",
        ]
        or value.get("databaseCompatibility") != {"minimum": "0.1.0", "maximumExclusive": "0.2.0"}
        or value.get("diagnosticCode") != "RO-CORE-STARTING"
    ):
        raise ValueError("Core benchmark received an incompatible handshake")
    return port


def git_head(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    commit = result.stdout.decode("ascii", errors="replace").strip()
    if result.returncode or len(commit) != 40 or any(item not in "0123456789abcdef" for item in commit):
        raise ValueError("Core performance measurement Git state is unavailable")
    return commit


def read_line(source: IO[bytes], timeout: float) -> bytes:
    result: queue.Queue[bytes | BaseException] = queue.Queue(maxsize=1)

    def read() -> None:
        try:
            result.put(source.readline())
        except BaseException as exc:  # pragma: no cover - operating-system I/O boundary
            result.put(exc)

    threading.Thread(target=read, daemon=True).start()
    try:
        value = result.get(timeout=timeout)
    except queue.Empty as exc:
        raise ValueError("Core handshake timed out") from exc
    if isinstance(value, BaseException):
        raise ValueError("Core handshake read failed") from value
    return value


def working_set_bytes(pid: int) -> int:
    process = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
    if not process:
        raise ValueError("Core process memory could not be queried")
    try:
        counters = ProcessMemoryCountersEx()
        counters.cb = ctypes.sizeof(counters)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            raise ValueError("Core process memory counters are unavailable")
        return int(counters.workingSetSize)
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


def readiness_ok(port: int, capability_token: str) -> bool:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/readyz",
        headers={
            "Authorization": f"Bearer {capability_token}",
            "Host": f"127.0.0.1:{port}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=0.5) as response:
            value = json.loads(response.read(65_537).decode("utf-8"))
    except OSError, UnicodeError, json.JSONDecodeError:
        return False
    return value == {
        "schemaVersion": "1.0",
        "service": "research-observatory-core",
        "version": "0.1.0",
        "state": "ready",
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
            "provenance.lineage.read",
            "runtime.contract",
            "runtime.status",
            "workflows.cancel",
            "workflows.human-decisions",
            "workflows.read",
            "workflows.retry",
        ],
        "ready": True,
    }


def measure_once(executable: Path) -> tuple[float, float, float]:
    environment = {
        name: value for name in ("SystemRoot", "WINDIR", "TEMP", "TMP") if (value := os.environ.get(name)) is not None
    }
    environment.update(
        {
            "RO_CORE_PROFILE": "local",
            "RO_CORE_BIND_HOST": "127.0.0.1",
            "RO_CORE_BIND_PORT": "0",
            "RO_CORE_LOG_LEVEL": "INFO",
        }
    )
    started = time.perf_counter()
    process = subprocess.Popen(
        [str(executable), "--supervised"],
        cwd=executable.parent,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        if process.stdout is None or process.stdin is None:
            raise ValueError("Core control pipes are unavailable")
        capability_token = secrets.token_hex(32)
        process.stdin.write(f"auth {capability_token}\n".encode("ascii"))
        process.stdin.flush()
        handshake_line = read_line(process.stdout, 10)
        if not handshake_line or len(handshake_line) > 4_096 or not handshake_line.endswith(b"\n"):
            raise ValueError("Core benchmark received an invalid handshake record")
        handshake = json.loads(handshake_line.decode("utf-8"))
        port = validate_handshake(handshake, process.pid)
        deadline = time.perf_counter() + 10
        while not readiness_ok(port, capability_token):
            if process.poll() is not None:
                raise ValueError("Core exited before benchmark readiness")
            if time.perf_counter() >= deadline:
                raise ValueError("Core benchmark readiness timed out")
            time.sleep(0.02)
        readiness_ms = (time.perf_counter() - started) * 1_000
        time.sleep(0.1)
        memory_bytes = float(working_set_bytes(process.pid))
        stopping = time.perf_counter()
        process.stdin.write(b"shutdown\n")
        process.stdin.flush()
        process.wait(timeout=5)
        shutdown_ms = (time.perf_counter() - stopping) * 1_000
        return readiness_ms, memory_bytes, shutdown_ms
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def benchmark_snapshot(
    executable: Path,
    repetitions: int,
    snapshot_guard: Callable[[], None],
    measure: Callable[[Path], tuple[float, float, float]] = measure_once,
) -> dict[str, dict[str, Any]]:
    snapshot_guard()
    measure(executable)
    snapshot_guard()
    readiness: list[float] = []
    memory: list[float] = []
    shutdown: list[float] = []
    for _index in range(repetitions):
        snapshot_guard()
        ready_ms, memory_bytes, stop_ms = measure(executable)
        snapshot_guard()
        readiness.append(ready_ms)
        memory.append(memory_bytes)
        shutdown.append(stop_ms)
    return {
        "readinessMs": distribution(readiness),
        "idleWorkingSetBytes": distribution(memory),
        "shutdownMs": distribution(shutdown),
    }


def assert_approved_package_identity(identity: dict[str, Any], baseline: dict[str, Any]) -> None:
    expected_fixture = baseline["fixture"]
    fixture = {
        "buildContractSha256": identity["buildContractSha256"],
        "targetTriple": identity["targetTriple"],
        "componentVersion": identity["componentVersion"],
        "entrypointSha256": identity["entrypointSha256"],
        "fileCount": identity["fileCount"],
        "totalBytes": identity["totalBytes"],
    }
    if fixture != expected_fixture:
        raise ValueError("Core package fixture does not match the approved performance baseline")
    for field in ("packageReportSha256", "artifactManifestSha256"):
        if identity[field] != baseline["provenance"][field]:
            raise ValueError(f"Core package {field} does not match the approved performance baseline")


def measured_report(
    repo: Path,
    repetitions: int,
    approved_baseline: dict[str, Any] | None,
    qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("Core performance qualification requires Windows x64")
    if repetitions != REPETITIONS:
        raise ValueError(f"Core performance qualification requires exactly {REPETITIONS} repetitions")
    if qualification is None:
        artifact_root, manifest, identity, report_payload = load_verified_package(repo)
    else:
        artifact_root = qualification["artifactRoot"]
        manifest = qualification["manifest"]
        identity = qualification["identity"]
        report_payload = qualification["packageReportBytes"]
    if approved_baseline is None:
        measurement_commit, measurement_tool_hash = current_measurement_state(repo)
    elif qualification is not None:
        assert_approved_package_identity(identity, approved_baseline)
        measurement_commit = str(qualification["stateCommit"])
        measurement_tool_hash = str(qualification["toolSha256"])
    else:
        assert_approved_package_identity(identity, approved_baseline)
        measurement_commit, measurement_tool_hash = clean_measurement_state(repo, approved_baseline)
    contract = load_build_contract(repo)
    schema, _schema_payload = load_json(exact_file(repo, SCHEMA_PATH))
    scratch = repo / "artifacts" / "tmp"
    if scratch.resolve(strict=True) != scratch or scratch.is_symlink() or scratch.is_junction():
        raise ValueError("Core performance scratch root must be a canonical directory")
    with tempfile.TemporaryDirectory(prefix="core-sidecar-benchmark-", dir=scratch) as temporary:
        snapshot_root = Path(temporary) / "package"
        shutil.copytree(artifact_root, snapshot_root)

        def guard() -> None:
            assert_package_snapshot(snapshot_root, manifest, contract, schema)

        executable = snapshot_root / str(manifest["entrypoint"])
        with immutable_package_snapshot(repo, snapshot_root, manifest):
            guard()
            raw = benchmark_snapshot(executable, repetitions, guard)
            guard()
    if qualification is None:
        _root_after, manifest_after, identity_after, report_payload_after = load_verified_package(repo)
        if report_payload_after != report_payload or manifest_after != manifest or identity_after != identity:
            raise ValueError("Core package report or artifact changed during performance measurement")
        state_after = current_measurement_state(repo)
        if state_after != (measurement_commit, measurement_tool_hash):
            raise ValueError("Core performance measurement Git state changed during execution")
    else:
        assert_qualification_inputs(repo, qualification)
    return {
        "schemaVersion": "1.0",
        "documentType": "core-sidecar-performance-report",
        "profile": "windows-x64",
        "hardware": hardware_record(),
        "provenance": {
            "measurementStateCommit": measurement_commit,
            "measurementToolPath": TOOL_PATH.as_posix(),
            "measurementToolSha256": measurement_tool_hash,
            "packageEvidencePath": PACKAGE_EVIDENCE_PATH.as_posix(),
            "packageEvidenceSha256": PACKAGE_EVIDENCE_SHA256,
            "packageReportSha256": identity["packageReportSha256"],
            "artifactManifestSha256": identity["artifactManifestSha256"],
        },
        "fixture": {
            "buildContractSha256": identity["buildContractSha256"],
            "targetTriple": identity["targetTriple"],
            "componentVersion": identity["componentVersion"],
            "entrypointSha256": identity["entrypointSha256"],
            "fileCount": identity["fileCount"],
            "totalBytes": identity["totalBytes"],
        },
        "methodology": expected_methodology(),
        "rawMeasurements": raw,
    }


def evaluate(
    report: dict[str, Any], baseline: dict[str, Any], baseline_hash: str, measurement_state_commit: str
) -> dict[str, Any]:
    if report.get("hardware") != baseline["hardware"]:
        raise ValueError("Core benchmark hardware differs from the approved baseline hardware")
    if report.get("fixture") != baseline["fixture"]:
        raise ValueError("Core benchmark package fixture differs from the approved baseline")
    provenance = report.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != {
        "measurementStateCommit",
        "measurementToolPath",
        "measurementToolSha256",
        "packageEvidencePath",
        "packageEvidenceSha256",
        "packageReportSha256",
        "artifactManifestSha256",
    }:
        raise ValueError("Core benchmark provenance shape is invalid")
    if provenance.get("measurementStateCommit") != measurement_state_commit:
        raise ValueError("Core benchmark measurement state does not match the qualifying Git HEAD")
    for field in (
        "measurementToolPath",
        "measurementToolSha256",
        "packageEvidencePath",
        "packageEvidenceSha256",
        "packageReportSha256",
        "artifactManifestSha256",
    ):
        if provenance.get(field) != baseline["provenance"][field]:
            raise ValueError(f"Core benchmark {field} differs from the approved baseline")
    rules = {
        "readinessMs": ("p50", "baselineP50"),
        "shutdownMs": ("p95", "baselineP95"),
        "idleWorkingSetBytes": ("p95", "baselineP95"),
    }
    evaluated: dict[str, Any] = {}
    errors: list[str] = []
    for name, (observed_field, baseline_field) in rules.items():
        observed = float(report["rawMeasurements"][name][observed_field])
        baseline_value = float(baseline["measurements"][name][baseline_field])
        absolute = float(baseline["measurements"][name]["absoluteBudget"])
        regression = baseline_value * (1 + REGRESSION_PERCENT / 100)
        passes = observed <= absolute and observed <= regression
        evaluated[name] = {
            "observedStatistic": observed_field,
            "observed": observed,
            "absoluteBudget": absolute,
            "baseline": baseline_value,
            "maximumFutureValue": round(min(absolute, regression), 3),
            "passes": passes,
        }
        if not passes:
            errors.append(f"Core {name} exceeds its absolute or {REGRESSION_PERCENT}% regression boundary")
    return {
        **report,
        "baseline": {"path": BASELINE_PATH.as_posix(), "sha256": baseline_hash},
        "measurements": evaluated,
        "errors": errors,
        "ok": not errors,
    }


def nonqualifying_report(
    error: str, *, measurement_only: bool = False, qualification_phase: str = "COMPLETE"
) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "documentType": "core-sidecar-performance-nonqualification",
        "qualificationStatus": "NONQUALIFYING",
        "qualificationPhase": qualification_phase,
        "measurementOnly": measurement_only,
        "ok": False,
        "errors": [error],
    }


def run(
    repo: Path, destination: Path, *, measure_only: bool = False, proposal: bool = False
) -> tuple[dict[str, Any], int]:
    if measure_only and proposal:
        raise ValueError("--measure-only and --proposal are mutually exclusive")
    if measure_only:
        report = nonqualifying_report(
            "--measure-only cannot produce qualification evidence; use the reviewed baseline gate",
            measurement_only=True,
        )
        guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
        return report, 1
    if proposal:
        try:
            measured = measured_report(repo, REPETITIONS, None)
            report = {
                **measured,
                "documentType": "core-sidecar-performance-proposal",
                "qualificationStatus": "PROPOSAL",
                "proposalGenerated": True,
                "ok": False,
                "errors": ["Proposal measurements require independently reviewed committed baseline authority"],
            }
        except (
            OSError,
            UnicodeError,
            ValueError,
            RuntimeError,
            json.JSONDecodeError,
            subprocess.TimeoutExpired,
        ) as exc:
            report = nonqualifying_report(str(exc))
        guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
        return report, 0 if report.get("proposalGenerated") is True else 1
    tombstone = nonqualifying_report(
        "Core performance qualification has not completed",
        qualification_phase="IN_PROGRESS",
    )
    guarded_atomic_write_json(repo, destination, tombstone, repo / "artifacts" / "tmp")
    try:
        with qualification_snapshot(repo) as qualification:
            baseline = qualification["baseline"]
            baseline_hash = str(qualification["baselineSha256"])
            state_commit = str(qualification["stateCommit"])
            measured = measured_report(repo, REPETITIONS, baseline, qualification)
            report = evaluate(measured, baseline, baseline_hash, state_commit)
            if report.get("ok") is True:
                guarded_final_publication(
                    repo,
                    destination,
                    report,
                    repo / "artifacts" / "tmp",
                    lambda: assert_qualification_inputs(repo, qualification),
                )
            else:
                guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
    except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        report = nonqualifying_report(str(exc))
        try:
            guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
        except (OSError, UnicodeError, ValueError, RuntimeError) as publication_exc:
            report["errors"].append(
                f"final nonqualifying report publication failed; the IN_PROGRESS tombstone remains: {publication_exc}"
            )
    return report, 0 if report.get("ok") is True else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--measure-only", action="store_true")
    modes.add_argument("--proposal", action="store_true")
    args = parser.parse_args()
    report: dict[str, Any]
    try:
        repo = args.repo.resolve(strict=True)
        destination = safe_output_path(repo, args.report)
        report, return_code = run(repo, destination, measure_only=args.measure_only, proposal=args.proposal)
    except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        report = nonqualifying_report(str(exc), measurement_only=args.measure_only)
        return_code = 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
