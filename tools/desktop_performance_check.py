#!/usr/bin/env python3
"""Benchmark the production desktop bundle against the approved S01 latency budgets."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from build_manifest import guarded_atomic_write_json, load_json, safe_output_path
from playwright.sync_api import Route, sync_playwright
from ui_conformance import inline_page, load_context

COLD_SHELL_PAINT_BUDGET_MS = 2_500.0
ROUTE_SKELETON_BUDGET_MS = 150.0
ROUTE_USABLE_BUDGET_MS = 1_000.0
DEFAULT_REPETITIONS = 12
CPU_THROTTLE_RATE = 1
RELATIVE_REGRESSION_PERCENT = 20
PERFORMANCE_BASELINE_PATH = "verification/baselines/desktop-performance.json"
EXPECTED_PERFORMANCE_BASELINE_SHA256 = "e85f168b4385a640f73bb6d871424e32d29583282fc741e54cb765bda92bac1a"
MEASUREMENT_BUDGETS = {
    "coldShellFirstContentfulPaint": COLD_SHELL_PAINT_BUDGET_MS,
    "warmRouteVisibleSkeleton": ROUTE_SKELETON_BUDGET_MS,
    "warmRouteUsable": ROUTE_USABLE_BUDGET_MS,
}
EXPECTED_BASELINE_P95_MS = {
    "coldShellFirstContentfulPaint": 96.0,
    "warmRouteVisibleSkeleton": 73.033,
    "warmRouteUsable": 77.622,
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
    processor = platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER") or "unreported"
    return {
        "operatingSystem": platform.platform(aliased=False, terse=False),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": processor,
        "logicalCpuCount": os.cpu_count(),
        "physicalMemoryBytes": physical_memory_bytes(),
    }


def percentile(samples: list[float], probability: float) -> float:
    if not samples or not 0 < probability <= 1:
        raise ValueError("percentile requires samples and a probability in (0, 1]")
    ordered = sorted(samples)
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[rank - 1]


def distribution(samples: list[float]) -> dict[str, Any]:
    if len(samples) < 5:
        raise ValueError("performance distributions require at least five repetitions")
    return {
        "samplesMs": [round(value, 3) for value in samples],
        "minimumMs": round(min(samples), 3),
        "p50Ms": round(percentile(samples, 0.50), 3),
        "p95Ms": round(percentile(samples, 0.95), 3),
        "maximumMs": round(max(samples), 3),
    }


def evaluated_measurement(samples: list[float], budget_ms: float, baseline_p95_ms: float) -> dict[str, Any]:
    measured = distribution(samples)
    p95 = float(measured["p95Ms"])
    relative_limit = round(min(budget_ms, baseline_p95_ms * (1 + RELATIVE_REGRESSION_PERCENT / 100)), 3)
    return {
        **measured,
        "absoluteBudgetMs": budget_ms,
        "passesAbsoluteBudget": p95 <= budget_ms,
        "passesRegressionThreshold": p95 <= relative_limit,
        "futureRegressionThreshold": {
            "baselineP95Ms": baseline_p95_ms,
            "maximumIncreasePercent": RELATIVE_REGRESSION_PERCENT,
            "maximumFutureP95Ms": relative_limit,
            "rule": "Future p95 must remain within both the absolute budget and 120% of this commit-bound baseline.",
        },
    }


def validate_regression_baseline(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("desktop performance baseline must be a JSON object")
    expected_keys = {
        "schemaVersion",
        "documentType",
        "baselineSourceCommit",
        "profile",
        "referenceId",
        "fixture",
        "methodology",
        "measurements",
    }
    if set(value) != expected_keys:
        raise ValueError("desktop performance baseline has unexpected or missing fields")
    if value.get("schemaVersion") != "1.0" or value.get("documentType") != "desktop-performance-baseline":
        raise ValueError("desktop performance baseline identity is invalid")
    source_commit = value.get("baselineSourceCommit")
    if (
        not isinstance(source_commit, str)
        or len(source_commit) != 40
        or any(character not in "0123456789abcdef" for character in source_commit)
    ):
        raise ValueError("desktop performance baseline source commit must be a full lowercase Git SHA")
    if value.get("profile") != "windows-x64" or value.get("referenceId") != "RO-UI-ACADEMIC-MINIMAL-1.3":
        raise ValueError("desktop performance baseline profile or reference identity is invalid")
    fixture = value.get("fixture")
    expected_fixture_keys = {
        "applicationManifestSha256",
        "runtimeSha256",
        "referencePackageSha256",
    }
    if not isinstance(fixture, dict) or set(fixture) != expected_fixture_keys:
        raise ValueError("desktop performance baseline fixture identity is invalid")
    if any(
        not isinstance(fixture.get(key), str)
        or len(fixture[key]) != 64
        or any(character not in "0123456789abcdef" for character in fixture[key])
        for key in expected_fixture_keys
    ):
        raise ValueError("desktop performance baseline fixture hashes must be lowercase SHA-256 values")
    methodology = value.get("methodology")
    expected_methodology = {
        "browserEngine": "chromium",
        "browserVersion": "145.0.7632.6",
        "playwrightVersion": "1.58.0",
        "cpuThrottleRate": CPU_THROTTLE_RATE,
        "hardwareQualification": "representative measured Windows x64 workstation",
        "repetitions": DEFAULT_REPETITIONS,
        "regressionThresholdPercent": RELATIVE_REGRESSION_PERCENT,
    }
    if methodology != expected_methodology:
        raise ValueError("desktop performance baseline methodology does not match the governed benchmark")
    measurements = value.get("measurements")
    if not isinstance(measurements, dict) or set(measurements) != set(MEASUREMENT_BUDGETS):
        raise ValueError("desktop performance baseline measurement inventory is invalid")
    for name, budget in MEASUREMENT_BUDGETS.items():
        measurement = measurements.get(name)
        if not isinstance(measurement, dict) or set(measurement) != {"absoluteBudgetMs", "baselineP95Ms"}:
            raise ValueError(f"desktop performance baseline {name} is invalid")
        baseline_p95 = measurement.get("baselineP95Ms")
        if (
            isinstance(baseline_p95, bool)
            or not isinstance(baseline_p95, (int, float))
            or not math.isfinite(baseline_p95)
            or baseline_p95 <= 0
        ):
            raise ValueError(f"desktop performance baseline {name} p95 must be positive and finite")
        if measurement.get("absoluteBudgetMs") != budget or baseline_p95 > budget:
            raise ValueError(f"desktop performance baseline {name} does not preserve its approved budget")
        if baseline_p95 != EXPECTED_BASELINE_P95_MS[name]:
            raise ValueError(f"desktop performance baseline {name} does not match its immutable reviewed p95")
    return value


def load_regression_baseline(repo: Path) -> tuple[dict[str, Any], str]:
    value, payload, error = load_json(repo, PERFORMANCE_BASELINE_PATH)
    if error or payload is None:
        raise ValueError(error or "desktop performance baseline could not be read")
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    if payload_sha256 != EXPECTED_PERFORMANCE_BASELINE_SHA256:
        raise ValueError("desktop performance baseline bytes do not match the immutable reviewed SHA-256")
    baseline = validate_regression_baseline(value)
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline["baselineSourceCommit"], "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if ancestry.returncode != 0:
        raise ValueError("desktop performance baseline source commit is not an ancestor of HEAD")
    return baseline, payload_sha256


def approved_document_name(raw_url: str, available: set[str]) -> str | None:
    parsed = urlsplit(raw_url)
    if parsed.scheme != "http" or parsed.netloc != "tauri.localhost" or parsed.query or parsed.fragment:
        return None
    if not parsed.path.startswith("/") or parsed.path.count("/") != 1:
        return None
    name = parsed.path[1:]
    return name if name in available else None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_record(repo: Path, allow_dirty: bool) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False, timeout=30
    )
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if commit.returncode or status.returncode:
        errors.append("desktop performance source identity requires an accessible Git worktree")
        return {"commit": None, "dirty": True}, errors
    dirty_paths = sorted(line[3:].replace("\\", "/") for line in status.stdout.splitlines() if len(line) > 3)
    if dirty_paths and not allow_dirty:
        errors.append("desktop performance evidence requires a clean exact commit")
    return {"commit": commit.stdout.strip(), "dirty": bool(dirty_paths), "dirtyPaths": dirty_paths}, errors


def benchmark(repo: Path, repetitions: int, allow_dirty: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    if repetitions < 5 or repetitions > 100:
        return {"ok": False, "errors": ["repetitions must be between 5 and 100"]}
    source, source_errors = source_record(repo, allow_dirty)
    errors.extend(source_errors)
    baseline, baseline_sha256 = load_regression_baseline(repo)
    context = load_context(repo)
    manifest_path = context.target / "application-manifest.json"
    runtime_path = context.target / "runtime" / "main.js"
    runtime = runtime_path.read_text(encoding="utf-8")
    documents = {
        page_name: inline_page(context, page_name).replace(
            "</body>", f'<script type="module">{runtime}</script></body>'
        )
        for page_name in ("index.html", "study-design.html")
    }
    cold_samples: list[float] = []
    route_skeleton_samples: list[float] = []
    route_usable_samples: list[float] = []
    unexpected_requests: list[str] = []
    browser_version = ""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser_version = browser.version
        try:
            for _ in range(repetitions):
                browser_context = browser.new_context()

                def serve(route: Route) -> None:
                    name = approved_document_name(route.request.url, set(documents))
                    document = documents.get(name) if name is not None else None
                    if document is None:
                        unexpected_requests.append(route.request.url)
                        route.abort()
                    else:
                        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=document)

                browser_context.route("**/*", serve)
                page = browser_context.new_page()
                cdp = browser_context.new_cdp_session(page)
                cdp.send("Emulation.setCPUThrottlingRate", {"rate": CPU_THROTTLE_RATE})
                page.goto("http://tauri.localhost/index.html", wait_until="load")
                page.wait_for_function("document.body.dataset.applicationFrame === 'ready'", timeout=5_000)
                paint_ready = page.evaluate(
                    """
                    async () => {
                      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                      const paints = performance.getEntriesByType("paint");
                      const fcp = paints.find((entry) => entry.name === "first-contentful-paint");
                      return {fcp: fcp?.startTime ?? null, readyAfterPaint: performance.now()};
                    }
                    """
                )
                fcp = paint_ready.get("fcp") if isinstance(paint_ready, dict) else None
                if not isinstance(fcp, (int, float)):
                    errors.append("Chromium did not expose first-contentful-paint for the production shell")
                else:
                    cold_samples.append(float(fcp))

                route_started = time.perf_counter()
                page.goto("http://tauri.localhost/study-design.html", wait_until="commit")
                page.locator("main#main-content").wait_for(state="visible", timeout=5_000)
                route_skeleton_samples.append((time.perf_counter() - route_started) * 1_000)
                page.wait_for_function("document.body.dataset.applicationFrame === 'ready'", timeout=5_000)
                route_usable_samples.append((time.perf_counter() - route_started) * 1_000)
                browser_context.close()
        finally:
            browser.close()

    if unexpected_requests:
        errors.append("desktop performance fixture attempted an unexpected request")
    measurements: dict[str, Any] = {}
    if len(cold_samples) == repetitions:
        measurements["coldShellFirstContentfulPaint"] = evaluated_measurement(
            cold_samples,
            COLD_SHELL_PAINT_BUDGET_MS,
            float(baseline["measurements"]["coldShellFirstContentfulPaint"]["baselineP95Ms"]),
        )
    if len(route_skeleton_samples) == repetitions:
        measurements["warmRouteVisibleSkeleton"] = evaluated_measurement(
            route_skeleton_samples,
            ROUTE_SKELETON_BUDGET_MS,
            float(baseline["measurements"]["warmRouteVisibleSkeleton"]["baselineP95Ms"]),
        )
    if len(route_usable_samples) == repetitions:
        measurements["warmRouteUsable"] = evaluated_measurement(
            route_usable_samples,
            ROUTE_USABLE_BUDGET_MS,
            float(baseline["measurements"]["warmRouteUsable"]["baselineP95Ms"]),
        )
    for name, measurement in measurements.items():
        if measurement["passesAbsoluteBudget"] is not True:
            errors.append(f"{name} p95 exceeds its approved absolute budget")
        if measurement["passesRegressionThreshold"] is not True:
            errors.append(f"{name} p95 exceeds its committed 20% regression threshold")

    return {
        "schemaVersion": "1.0",
        "documentType": "desktop-performance-report",
        "ok": not errors,
        "source": source,
        "regressionBaseline": {
            "path": PERFORMANCE_BASELINE_PATH,
            "sha256": baseline_sha256,
            "sourceCommit": baseline["baselineSourceCommit"],
        },
        "platform": hardware_record(),
        "fixture": {
            "profile": "windows-x64",
            "applicationManifest": "apps/desktop/dist/application-manifest.json",
            "applicationManifestSha256": sha256(manifest_path),
            "runtimeSha256": sha256(runtime_path),
            "referenceId": context.config["referenceId"],
            "referencePackageSha256": context.config["referencePackageSha256"],
            "coldRoute": "index.html",
            "warmRoute": "study-design.html",
        },
        "methodology": {
            "browserEngine": "chromium",
            "browserVersion": browser_version,
            "playwrightVersion": importlib.metadata.version("playwright"),
            "cpuThrottleRate": CPU_THROTTLE_RATE,
            "hardwareQualification": "representative measured Windows x64 workstation",
            "repetitions": repetitions,
            "coldState": (
                "new isolated browser context per repetition; browser process startup and installation excluded"
            ),
            "warmState": "route navigation after the production index shell is loaded in the same context",
            "distribution": "nearest-rank p50 and p95 over every measured repetition; no samples discarded",
            "visibleSkeleton": "elapsed host monotonic time from navigation start until main#main-content is visible",
            "usable": "elapsed host monotonic time from navigation start until data-application-frame=ready",
            "paint": "Chromium PerformancePaintTiming first-contentful-paint from navigation start",
        },
        "measurements": measurements,
        "unexpectedRequests": sorted(set(unexpected_requests)),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    try:
        report = benchmark(repo, args.repetitions, allow_dirty=args.allow_dirty)
        destination = safe_output_path(repo, args.report)
        guarded_atomic_write_json(repo, destination, report, repo / "artifacts" / "tmp")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "schemaVersion": "1.0",
            "documentType": "desktop-performance-report",
            "ok": False,
            "errors": [str(exc)],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
