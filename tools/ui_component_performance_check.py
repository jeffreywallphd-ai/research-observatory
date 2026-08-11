#!/usr/bin/env python3
"""Benchmark bounded UI-component behavior against the approved S02 budget."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from build_manifest import guarded_atomic_write_json, load_json, safe_output_path
from desktop_performance_check import (
    RELATIVE_REGRESSION_PERCENT,
    evaluated_measurement,
    hardware_record,
    source_record,
)

BASELINE_PATH = "verification/baselines/ui-components-data-table-performance.json"
EXPECTED_BASELINE_SHA256 = "6d98a0bb457a35cf548e71d9c41eb9c680488cf45678571e7066fbe3706294ee"
EXPECTED_BASELINE_P95_MS = 43.169
BATCH_BUDGET_MS = 100.0
BENCHMARK_ENTRY = "packages/ui-components/benchmarks/data-table-10000.tsx"
BENCHMARK_RUNNER = "packages/ui-components/scripts/data-table-performance.mjs"
NODE_RUNTIME = ".local/toolchains/node-v24.19.0-win-x64/node.exe"
EXPECTED_FIXTURE = {
    "version": "data-table-10000-v1",
    "totalRows": 10_000,
    "columns": 3,
    "pageSize": 50,
    "pageCount": 200,
    "maximumRenderedRows": 50,
}
EXPECTED_SAMPLE_METHODOLOGY = {
    "state": "warm after five unmeasured render batches; the immutable dataset is constructed before timing",
    "operation": "alternating first/last accessible server-rendered pagination windows",
    "repetitions": 20,
    "rendersPerSample": 1_000,
    "warmupBatches": 5,
    "distribution": "nearest-rank p50 and p95 over every measured batch; no samples discarded",
}
EXPECTED_BASELINE_METHODOLOGY = {
    "runtime": "Node 24.19.0, React 19.2.8 production SSR, Vite 8.2.1",
    **EXPECTED_SAMPLE_METHODOLOGY,
    "hardwareQualification": "representative measured Windows x64 workstation",
    "regressionThresholdPercent": RELATIVE_REGRESSION_PERCENT,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_baseline(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("UI component performance baseline must be a JSON object")
    expected_keys = {
        "schemaVersion",
        "documentType",
        "baselineSourceCommit",
        "profile",
        "componentContractVersion",
        "fixture",
        "methodology",
        "measurements",
    }
    if set(value) != expected_keys:
        raise ValueError("UI component performance baseline has unexpected or missing fields")
    if value.get("schemaVersion") != "1.0" or value.get("documentType") != "ui-component-performance-baseline":
        raise ValueError("UI component performance baseline identity is invalid")
    source_commit = value.get("baselineSourceCommit")
    if (
        not isinstance(source_commit, str)
        or len(source_commit) != 40
        or any(character not in "0123456789abcdef" for character in source_commit)
    ):
        raise ValueError("UI component baseline source commit must be a full lowercase Git SHA")
    if value.get("profile") != "windows-x64" or value.get("componentContractVersion") != "1.2.0":
        raise ValueError("UI component baseline profile or contract version is invalid")

    fixture = value.get("fixture")
    expected_fixture_keys = {*EXPECTED_FIXTURE, "benchmarkEntrySha256", "benchmarkRunnerSha256"}
    if not isinstance(fixture, dict) or set(fixture) != expected_fixture_keys:
        raise ValueError("UI component baseline fixture identity is invalid")
    if any(fixture.get(key) != expected for key, expected in EXPECTED_FIXTURE.items()):
        raise ValueError("UI component baseline fixture dimensions are invalid")
    for key in ("benchmarkEntrySha256", "benchmarkRunnerSha256"):
        digest = fixture.get(key)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("UI component baseline fixture hashes must be lowercase SHA-256 values")

    if value.get("methodology") != EXPECTED_BASELINE_METHODOLOGY:
        raise ValueError("UI component baseline methodology does not match the governed benchmark")
    measurements = value.get("measurements")
    if not isinstance(measurements, dict) or set(measurements) != {"warmPaginatedRenderBatch"}:
        raise ValueError("UI component baseline measurement inventory is invalid")
    measurement = measurements["warmPaginatedRenderBatch"]
    if not isinstance(measurement, dict) or set(measurement) != {"absoluteBudgetMs", "baselineP95Ms"}:
        raise ValueError("UI component baseline measurement is invalid")
    baseline_p95 = measurement.get("baselineP95Ms")
    if (
        isinstance(baseline_p95, bool)
        or not isinstance(baseline_p95, (int, float))
        or not math.isfinite(baseline_p95)
        or baseline_p95 <= 0
    ):
        raise ValueError("UI component baseline p95 must be positive and finite")
    if measurement.get("absoluteBudgetMs") != BATCH_BUDGET_MS or baseline_p95 > BATCH_BUDGET_MS:
        raise ValueError("UI component baseline does not preserve its approved budget")
    if baseline_p95 != EXPECTED_BASELINE_P95_MS:
        raise ValueError("UI component baseline does not match its immutable reviewed p95")
    return value


def load_baseline(repo: Path) -> tuple[dict[str, Any], str]:
    value, payload, error = load_json(repo, BASELINE_PATH)
    if error or payload is None:
        raise ValueError(error or "UI component performance baseline could not be read")
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    if payload_sha256 != EXPECTED_BASELINE_SHA256:
        raise ValueError("UI component baseline bytes do not match the immutable reviewed SHA-256")
    baseline = validate_baseline(value)
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline["baselineSourceCommit"], "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if ancestry.returncode != 0:
        raise ValueError("UI component baseline source commit is not an ancestor of HEAD")
    fixture = baseline["fixture"]
    if sha256(repo / BENCHMARK_ENTRY) != fixture["benchmarkEntrySha256"]:
        raise ValueError("UI component benchmark entry changed without a reviewed rebaseline")
    if sha256(repo / BENCHMARK_RUNNER) != fixture["benchmarkRunnerSha256"]:
        raise ValueError("UI component benchmark runner changed without a reviewed rebaseline")
    return baseline, payload_sha256


def validate_samples(value: Any) -> list[float]:
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion",
        "documentType",
        "fixture",
        "methodology",
        "samplesMs",
    }:
        raise ValueError("UI component benchmark samples have unexpected or missing fields")
    if value.get("schemaVersion") != "1.0" or value.get("documentType") != "ui-component-performance-samples":
        raise ValueError("UI component benchmark sample identity is invalid")
    fixture = value.get("fixture")
    if not isinstance(fixture, dict):
        raise ValueError("UI component benchmark fixture is invalid")
    for key, expected in EXPECTED_FIXTURE.items():
        if fixture.get(key) != expected:
            raise ValueError(f"UI component benchmark fixture {key} is invalid")
    if set(fixture) != {*EXPECTED_FIXTURE, "firstPageMarkupBytes", "lastPageMarkupBytes"}:
        raise ValueError("UI component benchmark fixture has unexpected fields")
    if any(
        isinstance(fixture.get(key), bool) or not isinstance(fixture.get(key), int) or fixture[key] <= 0
        for key in ("firstPageMarkupBytes", "lastPageMarkupBytes")
    ):
        raise ValueError("UI component benchmark markup sizes must be positive integers")
    if value.get("methodology") != EXPECTED_SAMPLE_METHODOLOGY:
        raise ValueError("UI component benchmark methodology is invalid")
    samples = value.get("samplesMs")
    if not isinstance(samples, list) or len(samples) != EXPECTED_SAMPLE_METHODOLOGY["repetitions"]:
        raise ValueError("UI component benchmark must retain every governed repetition")
    if any(
        isinstance(sample, bool) or not isinstance(sample, (int, float)) or not math.isfinite(sample) or sample <= 0
        for sample in samples
    ):
        raise ValueError("UI component benchmark samples must be positive finite numbers")
    return [float(sample) for sample in samples]


def benchmark(repo: Path, allow_dirty: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    source, source_errors = source_record(repo, allow_dirty)
    errors.extend(source_errors)
    baseline, baseline_sha256 = load_baseline(repo)
    node = repo / NODE_RUNTIME
    if not node.is_file():
        raise ValueError("repository-pinned Node 24.19.0 runtime is unavailable; run bootstrap.cmd")
    execution = subprocess.run(
        [str(node), str(repo / BENCHMARK_RUNNER)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if execution.returncode != 0:
        raise ValueError(f"UI component benchmark runner failed: {execution.stderr.strip()}")
    samples_payload = json.loads(execution.stdout)
    samples = validate_samples(samples_payload)
    measurement = evaluated_measurement(samples, BATCH_BUDGET_MS, EXPECTED_BASELINE_P95_MS)
    if measurement["passesAbsoluteBudget"] is not True:
        errors.append("warmPaginatedRenderBatch p95 exceeds its approved absolute budget")
    if measurement["passesRegressionThreshold"] is not True:
        errors.append("warmPaginatedRenderBatch p95 exceeds its committed 20% regression threshold")
    package = json.loads((repo / "packages" / "ui-components" / "package.json").read_text(encoding="utf-8"))
    if package.get("version") != baseline["componentContractVersion"]:
        errors.append("UI component package version does not match the benchmarked contract")

    return {
        "schemaVersion": "1.0",
        "documentType": "ui-component-performance-report",
        "ok": not errors,
        "source": source,
        "regressionBaseline": {
            "path": BASELINE_PATH,
            "sha256": baseline_sha256,
            "sourceCommit": baseline["baselineSourceCommit"],
        },
        "platform": hardware_record(),
        "fixture": {
            **samples_payload["fixture"],
            "benchmarkEntry": BENCHMARK_ENTRY,
            "benchmarkEntrySha256": sha256(repo / BENCHMARK_ENTRY),
            "benchmarkRunner": BENCHMARK_RUNNER,
            "benchmarkRunnerSha256": sha256(repo / BENCHMARK_RUNNER),
            "componentContractVersion": package.get("version"),
        },
        "methodology": EXPECTED_BASELINE_METHODOLOGY,
        "measurements": {"warmPaginatedRenderBatch": measurement},
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    try:
        report = benchmark(repo, allow_dirty=args.allow_dirty)
        destination = safe_output_path(repo, args.report)
        guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        report = {
            "schemaVersion": "1.0",
            "documentType": "ui-component-performance-report",
            "ok": False,
            "errors": [str(exc)],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
