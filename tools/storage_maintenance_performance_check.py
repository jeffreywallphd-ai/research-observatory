#!/usr/bin/env python3
"""Qualify project storage accounting/GC pauses on the W1 Windows fixture."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from build_manifest import guarded_atomic_write_json, safe_output_path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_SRC = REPO_ROOT / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.object_store import (  # noqa: E402
    ObjectPutCommand,
    ObjectStore,
    StorageCleanupRequest,
    StoragePolicy,
)
from research_observatory_core.ports.object_store_keys import ObjectMasterKey  # noqa: E402
from research_observatory_core.storage import initialize_database  # noqa: E402

TOOL_PATH = Path("tools/storage_maintenance_performance_check.py")
IMPLEMENTATION_PATH = Path("services/core-api/src/research_observatory_core/object_store.py")
BASELINE_PATH = Path("verification/baselines/storage-maintenance-performance.json")
EXPECTED_BASELINE_SHA256 = "a79cd4f1697ab9e69572f380e182935b8ebd27adf6b30529b067ff835b6d3f98"
REPETITIONS = 10
CACHE_FILE_COUNT = 2_000
DERIVED_OBJECT_COUNT = 100
ITEM_BYTES = 64
REGRESSION_PERCENT = 20
STREAM_FIXTURES: dict[str, int] = {
    "pdf": 1 * 1024 * 1024,
    "report": 4 * 1024 * 1024,
    "model": 16 * 1024 * 1024,
}
LATENCY_BUDGET_MS = {"usagePreview": 2_000.0, "cleanup": 5_000.0}
THROUGHPUT_BUDGET_MIB_PER_SECOND = {
    f"{operation}{fixture.title()}": 5.0 for fixture in STREAM_FIXTURES for operation in ("put", "open")
}
MEASUREMENT_KINDS = {
    **{name: "maximum-latency" for name in LATENCY_BUDGET_MS},
    **{name: "minimum-throughput" for name in THROUGHPUT_BUDGET_MIB_PER_SECOND},
}
CALIBRATION_CONTEXTS = (
    "standalone measurement-only run 1",
    "standalone measurement-only run 2",
    "standalone measurement-only run 3",
)
EXPECTED_FIXTURE: dict[str, Any] = {
    "version": "encrypted-storage-and-maintenance-windows-v1",
    "streaming": {
        "protectionProfile": "project-encrypted-v1",
        "sizesBytes": STREAM_FIXTURES,
    },
    "maintenance": {
        "cacheFileCount": CACHE_FILE_COUNT,
        "derivedObjectCount": DERIVED_OBJECT_COUNT,
        "itemBytes": ITEM_BYTES,
        "reclaimableItemCount": CACHE_FILE_COUNT + DERIVED_OBJECT_COUNT,
        "reclaimablePlaintextBytes": (CACHE_FILE_COUNT + DERIVED_OBJECT_COUNT) * ITEM_BYTES,
    },
}
EXPECTED_METHODOLOGY = {
    "timer": "time.perf_counter_ns",
    "operations": {
        "putThroughput": "encrypted streaming put including fsync, guarded publication, and SQLite metadata commit",
        "openThroughput": "production encrypted open, full authentication, and controlled-stream read to EOF",
        "usagePreview": "categorized usage scan followed by one-time cleanup preview",
        "cleanup": "execute preview across project-cache and unreferenced derived objects",
    },
    "excluded": "payload and fixture construction, project initialization, and cleanup preview before execution timing",
    "state": "operating-system filesystem cache is not flushed; each cleanup sample receives a fresh fixture",
    "repetitions": REPETITIONS,
    "distribution": (
        "nearest-rank p50 and p95 over every sample; latency gates p95 and throughput gates p50; no samples discarded"
    ),
    "regressionThresholdPercent": REGRESSION_PERCENT,
    "hardwareQualification": "release-authoritative Windows x64 workstation",
}
CREATED_AT = "2026-08-18T16:00:00.000Z"
TRACE_ID = "0123456789abcdef0123456789abcdef"


class MemoryKeyProvider:
    """Deterministic benchmark-only master-key provider."""

    def __init__(self) -> None:
        self._key = ObjectMasterKey("benchmark-object-key-v1", bytes.fromhex("11" * 32))

    def active_object_master_key(self) -> ObjectMasterKey:
        return self._key

    def object_master_key(self, key_version: str) -> ObjectMasterKey | None:
        return self._key if key_version == self._key.key_version else None


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


def git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=text, check=False)
    if completed.returncode:
        diagnostic = completed.stderr if text else completed.stderr.decode("utf-8", errors="replace")
        raise ValueError(f"git {' '.join(args)} failed: {diagnostic.strip()}")
    output = completed.stdout
    if not isinstance(output, (str, bytes)):
        raise ValueError("git returned an unexpected output type")
    return output


def clean_state_commit(repo: Path) -> str:
    if str(git(repo, "status", "--porcelain=v1", "--untracked-files=all")):
        raise ValueError("storage maintenance performance qualification requires a clean repository")
    commit = str(git(repo, "rev-parse", "HEAD")).strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise ValueError("storage maintenance performance state commit is invalid")
    return commit


def committed_bytes(repo: Path, commit: str, path: Path) -> bytes:
    payload = git(repo, "show", f"{commit}:{path.as_posix()}", text=False)
    if not isinstance(payload, bytes):
        raise ValueError("governed Git input unexpectedly decoded as text")
    return payload


def percentile(samples: list[float], probability: float) -> float:
    if not samples or not 0 < probability <= 1 or any(not math.isfinite(value) or value < 0 for value in samples):
        raise ValueError("percentile requires finite non-negative samples")
    ordered = sorted(samples)
    return ordered[max(1, math.ceil(probability * len(ordered))) - 1]


def distribution(samples: list[float], *, unit: str) -> dict[str, Any]:
    if len(samples) != REPETITIONS:
        raise ValueError(f"storage maintenance performance requires exactly {REPETITIONS} samples")
    if unit not in {"Ms", "MiBPerSecond"}:
        raise ValueError("storage maintenance performance distribution unit is invalid")
    return {
        f"samples{unit}": [round(value, 3) for value in samples],
        f"minimum{unit}": round(min(samples), 3),
        f"p50{unit}": round(percentile(samples, 0.50), 3),
        f"p95{unit}": round(percentile(samples, 0.95), 3),
        f"maximum{unit}": round(max(samples), 3),
    }


def cleanup_request() -> StorageCleanupRequest:
    return StorageCleanupRequest(
        categories=("derived-objects", "project-cache"),
        requested_at=CREATED_AT,
        trace_id=TRACE_ID,
        actor_id="system.storage-performance",
    )


def create_project_root(parent: Path, index: int) -> tuple[Path, str]:
    root = parent / f"project-{index:03d}-{uuid.uuid4().hex}"
    for relative in (
        "state",
        "objects",
        "indexes",
        "cache",
        "models",
        "config",
        "exports",
        "logs",
        ".locks",
        ".tmp",
    ):
        (root / relative).mkdir(parents=True, mode=0o700)
    project_id = str(uuid.uuid4())
    initialize_database(root / "state" / "project.sqlite3", project_id=project_id, project_created_at=CREATED_AT)
    return root, project_id


def create_maintenance_fixture(parent: Path, index: int) -> ObjectStore:
    root, project_id = create_project_root(parent, index)
    cache = root / "cache"
    payload = bytes([index % 251]) * ITEM_BYTES
    for item in range(CACHE_FILE_COUNT):
        bucket = cache / f"{item % 20:02d}"
        bucket.mkdir(exist_ok=True)
        (bucket / f"{item:05d}.cache").write_bytes(payload)
    store = create_local_object_store(
        root,
        project_id,
        allow_plaintext_fixture=True,
        storage_policy=StoragePolicy(minimum_free_bytes=0),
    )
    for item in range(DERIVED_OBJECT_COUNT):
        content = item.to_bytes(4, "big") + bytes([index % 251]) * (ITEM_BYTES - 4)
        store.put(
            io.BytesIO(content),
            ObjectPutCommand(
                media_type="application/octet-stream",
                rights_status="not-applicable",
                protection_profile="plaintext-fixture-v1",
                retention_class="derived-rebuildable",
                created_at=CREATED_AT,
            ),
        )
    return store


def streaming_payload(fixture: str, index: int) -> bytes:
    size = STREAM_FIXTURES[fixture]
    prefix = f"research-observatory:{fixture}:{index}:".encode()
    return prefix + bytes([index % 251]) * (size - len(prefix))


def measure_streaming(parent: Path) -> dict[str, list[float]]:
    samples: dict[str, list[float]] = {name: [] for name in THROUGHPUT_BUDGET_MIB_PER_SECOND}
    root, project_id = create_project_root(parent, 100)
    store = create_local_object_store(root, project_id, key_provider=MemoryKeyProvider())
    command = ObjectPutCommand(
        media_type="application/octet-stream",
        rights_status="not-applicable",
        protection_profile="project-encrypted-v1",
        retention_class="project-lifetime",
        created_at=CREATED_AT,
    )
    for fixture, size in STREAM_FIXTURES.items():
        put_name = f"put{fixture.title()}"
        open_name = f"open{fixture.title()}"
        for index in range(REPETITIONS):
            payload = streaming_payload(fixture, index)
            started = time.perf_counter_ns()
            stored = store.put(io.BytesIO(payload), command)
            put_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
            samples[put_name].append((size / (1024 * 1024)) / put_seconds)
            opened = bytearray()
            started = time.perf_counter_ns()
            with store.open(stored.object_sha256, purpose="storage-performance") as stream:
                while chunk := stream.read(1024 * 1024):
                    opened.extend(chunk)
            open_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
            if opened != payload:
                raise ValueError("encrypted streaming benchmark returned different plaintext bytes")
            samples[open_name].append((size / (1024 * 1024)) / open_seconds)
    return samples


def measure_maintenance(parent: Path) -> dict[str, list[float]]:
    samples: dict[str, list[float]] = {"usagePreview": [], "cleanup": []}
    preview_store = create_maintenance_fixture(parent, 0)
    for _ in range(REPETITIONS):
        started = time.perf_counter_ns()
        usage = preview_store.usage()
        preview = preview_store.preview_cleanup(cleanup_request())
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        if preview.reclaimable_item_count != EXPECTED_FIXTURE["maintenance"]["reclaimableItemCount"]:
            raise ValueError("storage preview item count differs from the representative fixture")
        if usage.project_byte_count <= 0:
            raise ValueError("storage accounting returned an empty representative project")
        samples["usagePreview"].append(elapsed)
    for index in range(1, REPETITIONS + 1):
        store = create_maintenance_fixture(parent, index)
        preview = store.preview_cleanup(cleanup_request())
        started = time.perf_counter_ns()
        result = store.cleanup(preview.preview_token)
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        if (
            result.reclaimed_item_count != EXPECTED_FIXTURE["maintenance"]["reclaimableItemCount"]
            or result.skipped_item_count != 0
        ):
            raise ValueError("storage cleanup result differs from the representative fixture")
        samples["cleanup"].append(elapsed)
    return samples


def measure(repo: Path) -> dict[str, list[float]]:
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("storage performance qualification requires Windows x64")
    temporary_root = repo / "artifacts" / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ro-storage-performance-", dir=temporary_root) as temporary:
        parent = Path(temporary)
        return {**measure_streaming(parent), **measure_maintenance(parent)}


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode()


def valid_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def valid_commit(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def measurement_distribution(name: str, samples: list[float]) -> dict[str, Any]:
    unit = "Ms" if MEASUREMENT_KINDS[name] == "maximum-latency" else "MiBPerSecond"
    return distribution(samples, unit=unit)


def calibration_record_hash(run: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes({key: item for key, item in run.items() if key != "recordSha256"}))


def validate_retained_distribution(name: str, value: Any) -> None:
    unit = "Ms" if MEASUREMENT_KINDS[name] == "maximum-latency" else "MiBPerSecond"
    keys = {
        f"samples{unit}",
        f"minimum{unit}",
        f"p50{unit}",
        f"p95{unit}",
        f"maximum{unit}",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"storage performance calibration {name} distribution shape is invalid")
    samples = value[f"samples{unit}"]
    if (
        not isinstance(samples, list)
        or len(samples) != REPETITIONS
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in samples)
        or any(not math.isfinite(float(item)) or float(item) <= 0 for item in samples)
        or measurement_distribution(name, [float(item) for item in samples]) != value
    ):
        raise ValueError(f"storage performance calibration {name} distribution is invalid")


def load_baseline(repo: Path) -> dict[str, Any]:
    raw = (repo / BASELINE_PATH).read_bytes()
    if sha256_bytes(raw) != EXPECTED_BASELINE_SHA256:
        raise ValueError("storage performance baseline bytes differ from the reviewed authority")
    value = json.loads(raw.decode("utf-8"))
    required = {
        "schemaVersion",
        "documentType",
        "baselineSourceCommit",
        "profile",
        "fixture",
        "methodology",
        "hardware",
        "source",
        "calibrationRuns",
        "measurements",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("storage performance baseline shape is invalid")
    if (
        value["schemaVersion"] != "1.0"
        or value["documentType"] != "object-storage-performance-baseline"
        or value["profile"] != "windows-x64"
        or value["fixture"] != EXPECTED_FIXTURE
        or value["methodology"] != EXPECTED_METHODOLOGY
    ):
        raise ValueError("storage performance baseline identity is invalid")
    source_commit = value["baselineSourceCommit"]
    if not valid_commit(source_commit):
        raise ValueError("storage performance baseline source commit is invalid")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if ancestor.returncode:
        raise ValueError("storage performance baseline source is not reachable from HEAD")
    source = value["source"]
    if not isinstance(source, dict) or set(source) != {
        "measurementToolPath",
        "measurementToolSha256",
        "implementationPath",
        "implementationSha256",
    }:
        raise ValueError("storage performance baseline source is invalid")
    expected_sources = ((TOOL_PATH, "measurementTool"), (IMPLEMENTATION_PATH, "implementation"))
    for path, prefix in expected_sources:
        if source[f"{prefix}Path"] != path.as_posix():
            raise ValueError("storage performance baseline source path is invalid")
        expected_sha = sha256_bytes(committed_bytes(repo, source_commit, path))
        if source[f"{prefix}Sha256"] != expected_sha:
            raise ValueError("storage performance baseline source bytes are invalid")
    runs = value["calibrationRuns"]
    if not isinstance(runs, list) or len(runs) != len(CALIBRATION_CONTEXTS):
        raise ValueError("storage performance calibration inventory is invalid")
    for index, run in enumerate(runs):
        if not isinstance(run, dict) or set(run) != {
            "context",
            "stateCommit",
            "recordSha256",
            "source",
            "measurements",
        }:
            raise ValueError("storage performance calibration record shape is invalid")
        if (
            run["context"] != CALIBRATION_CONTEXTS[index]
            or run["stateCommit"] != source_commit
            or run["source"]
            != {
                "dirty": False,
                "stateCommit": source_commit,
                **source,
            }
            or not valid_digest(run["recordSha256"])
            or run["recordSha256"] != calibration_record_hash(run)
        ):
            raise ValueError("storage performance calibration record identity is invalid")
        retained = run["measurements"]
        if not isinstance(retained, dict) or set(retained) != set(MEASUREMENT_KINDS):
            raise ValueError("storage performance calibration measurement inventory is invalid")
        for name, distribution_value in retained.items():
            validate_retained_distribution(name, distribution_value)
    measurements = value["measurements"]
    if not isinstance(measurements, dict) or set(measurements) != set(MEASUREMENT_KINDS):
        raise ValueError("storage performance baseline measurement inventory is invalid")
    for name, kind in MEASUREMENT_KINDS.items():
        measurement = measurements[name]
        if kind == "maximum-latency":
            retained_values = [run["measurements"][name]["p95Ms"] for run in runs]
            expected_measurement = {
                "kind": kind,
                "absoluteBudgetMs": LATENCY_BUDGET_MS[name],
                "baselineP95Ms": max(retained_values),
            }
        else:
            retained_values = [run["measurements"][name]["p50MiBPerSecond"] for run in runs]
            expected_measurement = {
                "kind": kind,
                "absoluteBudgetMiBPerSecond": THROUGHPUT_BUDGET_MIB_PER_SECOND[name],
                "baselineP50MiBPerSecond": min(retained_values),
            }
        if measurement != expected_measurement:
            raise ValueError("storage performance baseline selection is invalid")
    if value["hardware"] != hardware_record():
        raise ValueError("storage performance hardware differs from the reviewed Windows workstation")
    return value


def evaluated_latency(samples: list[float], baseline_p95_ms: float, absolute_budget_ms: float) -> dict[str, Any]:
    measured = distribution(samples, unit="Ms")
    raw_p95 = percentile(samples, 0.95)
    relative_limit = min(absolute_budget_ms, baseline_p95_ms * (1 + REGRESSION_PERCENT / 100))
    return {
        **measured,
        "rawP95Ms": raw_p95,
        "absoluteBudgetMs": absolute_budget_ms,
        "passesAbsoluteBudget": raw_p95 <= absolute_budget_ms,
        "passesRegressionThreshold": raw_p95 <= relative_limit,
        "regressionThreshold": {
            "baselineP95Ms": baseline_p95_ms,
            "maximumIncreasePercent": REGRESSION_PERCENT,
            "maximumP95Ms": round(relative_limit, 3),
        },
    }


def evaluated_throughput(
    samples: list[float], baseline_p50_mib_per_second: float, absolute_budget_mib_per_second: float
) -> dict[str, Any]:
    measured = distribution(samples, unit="MiBPerSecond")
    raw_p50 = percentile(samples, 0.50)
    relative_limit = max(
        absolute_budget_mib_per_second,
        baseline_p50_mib_per_second * (1 - REGRESSION_PERCENT / 100),
    )
    return {
        **measured,
        "rawP50MiBPerSecond": raw_p50,
        "absoluteBudgetMiBPerSecond": absolute_budget_mib_per_second,
        "passesAbsoluteBudget": raw_p50 >= absolute_budget_mib_per_second,
        "passesRegressionThreshold": raw_p50 >= relative_limit,
        "regressionThreshold": {
            "baselineP50MiBPerSecond": baseline_p50_mib_per_second,
            "maximumDecreasePercent": REGRESSION_PERCENT,
            "minimumP50MiBPerSecond": round(relative_limit, 3),
        },
    }


def build_report(repo: Path, commit: str, samples: dict[str, list[float]], *, measure_only: bool) -> dict[str, Any]:
    source = {
        "dirty": False,
        "stateCommit": commit,
        "measurementToolPath": TOOL_PATH.as_posix(),
        "measurementToolSha256": sha256_bytes((repo / TOOL_PATH).read_bytes()),
        "implementationPath": IMPLEMENTATION_PATH.as_posix(),
        "implementationSha256": sha256_bytes((repo / IMPLEMENTATION_PATH).read_bytes()),
    }
    if set(samples) != set(MEASUREMENT_KINDS):
        raise ValueError("storage performance measurement inventory is invalid")
    distributions = {name: measurement_distribution(name, values) for name, values in samples.items()}
    report: dict[str, Any] = {
        "schemaVersion": "1.0",
        "documentType": "object-storage-performance-report",
        "profile": "windows-x64",
        "measureOnly": measure_only,
        "qualified": False,
        "ok": not measure_only,
        "errors": ["measurement-only report is calibration input, not qualification evidence"] if measure_only else [],
        "fixture": EXPECTED_FIXTURE,
        "methodology": EXPECTED_METHODOLOGY,
        "hardware": hardware_record(),
        "source": source,
        "measurements": distributions,
    }
    if measure_only:
        return report
    baseline = load_baseline(repo)
    evaluated: dict[str, dict[str, Any]] = {}
    for name, kind in MEASUREMENT_KINDS.items():
        if kind == "maximum-latency":
            evaluated[name] = evaluated_latency(
                samples[name],
                float(baseline["measurements"][name]["baselineP95Ms"]),
                LATENCY_BUDGET_MS[name],
            )
        else:
            evaluated[name] = evaluated_throughput(
                samples[name],
                float(baseline["measurements"][name]["baselineP50MiBPerSecond"]),
                THROUGHPUT_BUDGET_MIB_PER_SECOND[name],
            )
    report["baseline"] = {
        "path": BASELINE_PATH.as_posix(),
        "sourceCommit": baseline["baselineSourceCommit"],
        "sha256": sha256_bytes((repo / BASELINE_PATH).read_bytes()),
    }
    report["measurements"] = evaluated
    report["qualified"] = all(
        item["passesAbsoluteBudget"] and item["passesRegressionThreshold"] for item in evaluated.values()
    )
    report["ok"] = report["qualified"]
    if not report["qualified"]:
        report["errors"].append("storage performance exceeded an absolute or regression threshold")
    return report


def run(repo: Path, destination: Path, *, measure_only: bool) -> tuple[dict[str, Any], int]:
    tombstone = {
        "schemaVersion": "1.0",
        "documentType": "object-storage-performance-report",
        "ok": False,
        "qualified": False,
        "qualificationPhase": "IN_PROGRESS",
        "errors": ["storage maintenance qualification did not complete"],
    }
    guarded_atomic_write_json(repo, destination, tombstone, repo / "artifacts" / "tmp")
    commit = clean_state_commit(repo)
    governed = {path: (repo / path).read_bytes() for path in (TOOL_PATH, IMPLEMENTATION_PATH)}
    if not measure_only:
        governed[BASELINE_PATH] = (repo / BASELINE_PATH).read_bytes()
    try:
        samples = measure(repo)
        if clean_state_commit(repo) != commit or any(
            (repo / path).read_bytes() != payload for path, payload in governed.items()
        ):
            raise ValueError("storage maintenance governed state changed during qualification")
        report = build_report(repo, commit, samples, measure_only=measure_only)
        code = 0 if measure_only or report["ok"] else 1
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        report = {**tombstone, "qualificationPhase": "NONQUALIFYING", "errors": [str(error)]}
        code = 1
    guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
    return report, code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--measure-only", action="store_true")
    args = parser.parse_args()
    try:
        repo = args.repo.resolve(strict=True)
        if Path(__file__).resolve(strict=True) != (repo / TOOL_PATH).resolve(strict=True):
            raise ValueError("storage maintenance performance tool is not the canonical repository tool")
        destination = safe_output_path(repo, args.report)
        report, code = run(repo, destination, measure_only=args.measure_only)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        report = {"ok": False, "qualified": False, "errors": [str(error)]}
        code = 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
