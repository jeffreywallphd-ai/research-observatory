#!/usr/bin/env python3
"""Benchmark the packaged Core sidecar against S03 startup/resource budgets."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import queue
import statistics
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import IO, Any

from build_manifest import guarded_atomic_write_json, safe_output_path

REPETITIONS = 7
REGRESSION_PERCENT = 20
READINESS_BUDGET_MS = 3_000.0
SHUTDOWN_BUDGET_MS = 5_000.0
IDLE_MEMORY_BUDGET_BYTES = 268_435_456
BASELINE_PATH = Path("verification/baselines/core-sidecar-performance.json")
EXPECTED_BASELINE_SHA256 = "19884a848a54fc0ba1e5ef3381575e6ec63d5b78c33c9ed33320f49eff111215"
TARGET_TRIPLE = "x86_64-pc-windows-msvc"
ENTRYPOINT = f"research-observatory-core-{TARGET_TRIPLE}.exe"
ARTIFACT_PATH = Path("artifacts/tmp/core-sidecar-package/dist") / ENTRYPOINT.removesuffix(".exe") / ENTRYPOINT
CONTRACT_PATH = Path("services/core-api/packaging/sidecar-build.json")


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
    return {
        "samples": [round(value, 3) for value in values],
        "minimum": round(min(values), 3),
        "p50": round(statistics.median(values), 3),
        "p95": round(percentile(values, 0.95), 3),
        "maximum": round(max(values), 3),
    }


def hardware_record() -> dict[str, Any]:
    return {
        "operatingSystem": platform.platform(aliased=False, terse=False),
        "machine": platform.machine(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER") or "unreported",
        "logicalCpuCount": os.cpu_count(),
    }


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
        "fixture",
        "methodology",
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
    fixture = value.get("fixture")
    if not isinstance(fixture, dict) or set(fixture) != {"buildContractSha256", "targetTriple", "componentVersion"}:
        raise ValueError("Core performance baseline fixture is invalid")
    if fixture.get("targetTriple") != TARGET_TRIPLE or fixture.get("componentVersion") != "0.1.0":
        raise ValueError("Core performance baseline fixture identity is invalid")
    contract_hash = fixture.get("buildContractSha256")
    if not isinstance(contract_hash, str) or len(contract_hash) != 64:
        raise ValueError("Core performance baseline contract hash is invalid")
    if value.get("methodology") != expected_methodology():
        raise ValueError("Core performance baseline methodology is invalid")
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
    return value


def load_baseline(repo: Path) -> tuple[dict[str, Any], str]:
    value, payload = load_json(exact_file(repo, BASELINE_PATH))
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_BASELINE_SHA256:
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
    return baseline, digest


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


def readiness_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/readyz", timeout=0.5) as response:
            value = json.loads(response.read(65_537).decode("utf-8"))
    except OSError, UnicodeError, json.JSONDecodeError:
        return False
    return value == {
        "schemaVersion": "1.0",
        "service": "research-observatory-core",
        "version": "0.1.0",
        "state": "ready",
        "capabilities": ["runtime.status"],
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
        handshake = json.loads(read_line(process.stdout, 10).decode("utf-8"))
        if (
            set(handshake)
            != {
                "protocolVersion",
                "buildId",
                "pid",
                "host",
                "port",
                "nonce",
                "capabilities",
                "databaseCompatibility",
                "diagnosticCode",
            }
            or handshake.get("pid") != process.pid
            or handshake.get("host") != "127.0.0.1"
        ):
            raise ValueError("Core benchmark received an incompatible handshake")
        deadline = time.perf_counter() + 10
        while not readiness_ok(int(handshake["port"])):
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


def measured_report(repo: Path, repetitions: int) -> dict[str, Any]:
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("Core performance qualification requires Windows x64")
    if repetitions != REPETITIONS:
        raise ValueError(f"Core performance qualification requires exactly {REPETITIONS} repetitions")
    executable = exact_file(repo, ARTIFACT_PATH)
    contract = exact_file(repo, CONTRACT_PATH)
    # One unreported lifecycle warms filesystem and antivirus caches while every
    # measured lifecycle still starts a new packaged process.
    measure_once(executable)
    readiness: list[float] = []
    memory: list[float] = []
    shutdown: list[float] = []
    for _index in range(repetitions):
        ready_ms, memory_bytes, stop_ms = measure_once(executable)
        readiness.append(ready_ms)
        memory.append(memory_bytes)
        shutdown.append(stop_ms)
    return {
        "schemaVersion": "1.0",
        "documentType": "core-sidecar-performance-report",
        "profile": "windows-x64",
        "hardware": hardware_record(),
        "fixture": {
            "artifactSha256": sha256(executable),
            "buildContractSha256": sha256(contract),
            "targetTriple": TARGET_TRIPLE,
            "componentVersion": "0.1.0",
        },
        "methodology": expected_methodology(),
        "rawMeasurements": {
            "readinessMs": distribution(readiness),
            "idleWorkingSetBytes": distribution(memory),
            "shutdownMs": distribution(shutdown),
        },
    }


def evaluate(report: dict[str, Any], baseline: dict[str, Any], baseline_hash: str) -> dict[str, Any]:
    contract_hash = report["fixture"]["buildContractSha256"]
    if contract_hash != baseline["fixture"]["buildContractSha256"]:
        raise ValueError("Core benchmark build contract differs from the approved baseline")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--measure-only", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    try:
        report = measured_report(repo, REPETITIONS)
        if args.measure_only:
            report = {**report, "ok": True, "errors": []}
        else:
            baseline, baseline_hash = load_baseline(repo)
            report = evaluate(report, baseline, baseline_hash)
        destination = safe_output_path(repo, args.report)
        guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        report = {
            "schemaVersion": "1.0",
            "documentType": "core-sidecar-performance-report",
            "ok": False,
            "errors": [str(exc)],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
