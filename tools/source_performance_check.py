"""Fresh four-provider protected-page/cache qualification, with a fixed baseline.

Calibration is explicitly nonqualifying. Synthetic transport is used; no live
provider, desktop installer, minimum-hardware or OS cold-cache claim is made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from build_manifest import guarded_atomic_write_json, safe_output_path, windows_path_locks
from import_performance_check import digest, finite_positive, installed_inputs, require
from project_lifecycle_performance_check import (
    assert_committed_inputs,
    clean_state_commit,
    git,
    git_blob_sha256,
    governed_snapshot,
    guarded_final_publication,
    hardware_record,
)
from verification_receipt import runtime_identity

REPO = Path(__file__).resolve().parents[1]
TOOL = Path("tools/source_performance_check.py")
BASELINE = Path("tests/fixtures/scholarly-metadata/source-performance-baseline.json")
BASELINE_SHA256 = "d21fc40e3fedb71ecf0e0b274055d047b2fec4bb4278a1642894534d3c323822"
PROVIDERS = ("openalex", "crossref", "unpaywall", "semantic-scholar")
REPETITIONS = 3
METHOD = {
    "fixtureVersion": "four-scholarly-sources-page-v1",
    "recordsPerPage": 100,
    "repetitions": REPETITIONS,
    "timer": "time.perf_counter",
    "cold": "fresh protected project/process, uncached synthetic provider page",
    "warm": "same scientific page, fresh invocation/confirmation, protected cache hit, no network",
    "measured": (
        "public API preview/confirmation through terminal durable workflow status; includes real DPAPI and SQLCipher"
    ),
    "excluded": "fixture/configuration/Intent setup, extra repository reads, inspection and normal-close restart",
    "rateWait": "separate concurrent shared-broker probe with real clock/sleep and synthetic authority/store/HTTP",
    "distribution": "min/median/max of three repetitions; every raw sample must pass; no discarded samples",
    "regressionAllowance": 0.2,
    "osCacheFlushed": False,
}
INPUTS = (
    "services/core-api/src",
    ":(glob)packages/contracts/**/*.json",
    ":(glob)tests/**/*.py",
    ":(glob)tests/fixtures/**/*.json",
    "pyproject.toml",
    "uv.lock",
    str(TOOL),
    "tools/import_performance_check.py",
    "tools/build_manifest.py",
    "tools/project_lifecycle_performance_check.py",
    "tools/verification_receipt.py",
)


def validate_baseline(raw):
    require(hashlib.sha256(raw).hexdigest() == BASELINE_SHA256, "baseline differs from independent reviewed bytes")
    value = json.loads(raw)
    require(value["method"] == METHOD, "unreviewed benchmark method")
    expected = {f"{provider}:{phase}" for provider in PROVIDERS for phase in ("cold", "cache")} | {
        "rateWait",
        "peakWorkingSetBytes",
    }
    require(set(value["maxima"]) == expected, "incomplete baseline workload inventory")
    for key, metric in value["maxima"].items():
        require(
            finite_positive(metric) <= (512 * 1024**2 if key == "peakWorkingSetBytes" else 30),
            "baseline exceeds bounded workload budget",
        )
    require(value["calibration"]["performanceQualifying"] is False, "calibration mislabeled qualifying")
    raw_samples = value["calibration"]["rawMetrics"]
    require(
        len(raw_samples) == REPETITIONS and all(set(row) == expected for row in raw_samples),
        "baseline calibration samples missing",
    )
    for key, maximum in value["maxima"].items():
        require(
            max(finite_positive(row[key]) for row in raw_samples) == maximum, "baseline differs from raw calibration"
        )
    return value


def sample_metrics(sample):
    require(
        sample["fixtureVersion"] == METHOD["fixtureVersion"] and sample["recordsPerPage"] == 100, "wrong source fixture"
    )
    require(
        sample["restartPreserved"] is True and sample["boundariesExercised"] is False, "unexpected workload boundary"
    )
    require(sample["networkCalls"] == 4, "cache dispatched network")
    values = sample["samples"]
    expected = {(provider, phase) for provider in PROVIDERS for phase in ("cold", "cache")}
    require(
        len(values) == len(expected) and {(row["provider"], row["phase"]) for row in values} == expected,
        "source sample inventory",
    )
    result = {}
    for row in values:
        require(row["records"] == (1 if row["provider"] == "unpaywall" else 100), "incomplete source page")
        require(row["networkCalls"] == (1 if row["phase"] == "cold" else 0), "source cache outcome")
        result[f"{row['provider']}:{row['phase']}"] = finite_positive(row["seconds"])
    rate = sample["rateWait"]
    require(rate["networkCalls"] == 2 and rate["maximumConcurrentRequests"] == 1, "shared provider lane not serialized")
    require(finite_positive(rate["wireStartIntervalSeconds"]) >= 1, "provider requests started too early")
    require(
        rate["waits"]
        and all(
            finite_positive(row["actualSeconds"]) >= finite_positive(row["requestedSeconds"]) * 0.99
            for row in rate["waits"]
        ),
        "no completed actual rate wait",
    )
    result["rateWait"] = finite_positive(rate["seconds"])
    result["peakWorkingSetBytes"] = finite_positive(sample["memory"]["peakWorkingSetSize"])
    return result


def validate_metrics(metrics, baseline):
    for key, measured in metrics.items():
        limit = min(baseline["maxima"][key] * 1.2, 512 * 1024**2 if key == "peakWorkingSetBytes" else 30)
        require(measured <= limit, f"{key} exceeds reviewed ceiling {limit}")


@contextmanager
def fixed_inputs():
    require(os.name == "nt" and Path(__file__).resolve() == REPO / TOOL, "canonical Windows runner required")
    if not sys.dont_write_bytecode or sys.pycache_prefix is None:
        raise ValueError("launch with -B and a fresh -X pycache_prefix")
    cache_prefix = Path(sys.pycache_prefix).absolute()
    require(
        cache_prefix.is_relative_to(REPO / "artifacts/tmp") and not cache_prefix.exists(),
        "bytecode prefix must be fresh and confined",
    )
    for name in (
        "build_manifest",
        "import_performance_check",
        "project_lifecycle_performance_check",
        "verification_receipt",
    ):
        module_path = sys.modules[name].__file__
        require(
            module_path is not None and Path(module_path).resolve() == REPO / "tools" / f"{name}.py",
            "noncanonical measurement helper",
        )
    names = str(git(REPO, "ls-files", "--", *INPUTS)).splitlines()
    paths = [Path(name) for name in names]
    require(
        TOOL in paths and Path("tests/connectors/test_source_slice_runtime.py") in paths,
        "uncommitted benchmark producer",
    )
    installed, _ = installed_inputs()
    with windows_path_locks([REPO / path for path in paths] + installed, directories=False):
        head = clean_state_commit(REPO)
        captured = {path: governed_snapshot(REPO, path) for path in paths}
        assert_committed_inputs(REPO, head, captured)
        _, dependencies = installed_inputs()
        runtime = runtime_identity()

        def unchanged():
            assert_committed_inputs(REPO, head, captured)
            require(runtime == runtime_identity() and dependencies == installed_inputs()[1], "installed runtime drift")
            require(not cache_prefix.exists(), "unexpected bytecode cache creation")

        yield head, captured, runtime, dependencies, unchanged


def child(repetition, directory):
    folder = directory / f"sample-{repetition}"
    folder.mkdir()
    log, report = folder / "raw.log", folder / "result.json"
    environment = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "NUMBER_OF_PROCESSORS")
        if key in os.environ
    }
    executable = shutil.which("git")
    if executable is None:
        raise ValueError("Git unavailable")
    environment.update(
        PATH=os.pathsep.join((str(Path(executable).parent), str(Path(os.environ["SYSTEMROOT"]) / "System32"))),
        TEMP=str(folder),
        TMP=str(folder),
        PYTHONPATH=os.pathsep.join(map(str, (REPO, REPO / "tools", REPO / "services/core-api/src"))),
        PYTHONPYCACHEPREFIX=str(folder / "unused-bytecode"),
    )
    script = (
        "import json,sys,unittest; from pathlib import Path; "
        "from tests.connectors.test_source_slice_runtime import run_workload; "
        "from tests.service.test_import_review_scale_windows import _memory; "
        "result=run_workload(unittest.TestCase(),Path(sys.argv[1]),count=100,boundaries=False); "
        "result['memory']=_memory(); "
        "Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\\n',encoding='utf-8')"
    )
    with log.open("xb") as stream:
        process = subprocess.Popen(
            [
                str(Path(sys.executable).resolve(strict=True)),
                "-B",
                "-s",
                "-P",
                "-c",
                script,
                str(folder / "fixture"),
                str(report),
            ],
            cwd=REPO,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            code = process.wait(timeout=300)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    require(code == 0, f"source sample failed; retained {log.relative_to(REPO).as_posix()}")
    require(
        safe_output_path(REPO, report).resolve(strict=True) == report.absolute()
        and report.stat().st_nlink == 1
        and not report.is_symlink(),
        "missing/linked sample",
    )
    raw = report.read_bytes()
    return json.loads(raw), {
        "report": report.relative_to(REPO).as_posix(),
        "reportSha256": hashlib.sha256(raw).hexdigest(),
        "log": log.relative_to(REPO).as_posix(),
        "logSha256": digest(log),
    }


def run(destination, calibration=False):
    output_root = REPO / "artifacts/tmp"
    report: dict[str, Any] = {
        "status": "RUNNING",
        "performanceQualifying": False,
        "samples": [],
        "evidenceReuse": "disabled",
        "mode": "calibration" if calibration else "qualification",
    }

    def save():
        guarded_atomic_write_json(REPO, destination, report, output_root)

    save()
    started = time.monotonic()
    try:
        with fixed_inputs() as (head, captured, runtime, dependencies, unchanged):
            baseline = None if calibration else validate_baseline(captured[BASELINE])
            hardware = hardware_record()
            require(finite_positive(hardware["physicalMemoryBytes"]) > 0, "hardware unavailable")
            if baseline is not None:
                require(baseline["hardware"] == hardware, "hardware comparison requires review")
                prior = baseline["calibration"]
                subprocess.run(["git", "merge-base", "--is-ancestor", prior["commit"], head], cwd=REPO, check=True)
                require(
                    git_blob_sha256(REPO, prior["commit"], TOOL) == prior["toolSha256"], "calibration producer mismatch"
                )
            directory = Path(tempfile.mkdtemp(prefix="source-performance-", dir=output_root))
            report.update(
                head=head,
                toolSha256=digest(REPO / TOOL),
                inputHashes={path.as_posix(): hashlib.sha256(raw).hexdigest() for path, raw in captured.items()},
                runtime=runtime,
                installedDependencies=dependencies,
                hardware=hardware,
                method=METHOD,
                baselineSha256=None if calibration else BASELINE_SHA256,
            )
            save()
            for repetition in range(1, REPETITIONS + 1):
                print(json.dumps({"repetition": repetition, "state": "running"}), flush=True)
                sample, binding = child(repetition, directory)
                row = {"repetition": repetition, "rawSample": sample, **binding}
                report["samples"].append(row)
                save()
                row["metrics"] = sample_metrics(sample)
                if baseline is not None:
                    validate_metrics(row["metrics"], baseline)
                save()
            report["distributions"] = {
                key: {"min": min(values), "median": statistics.median(values), "max": max(values)}
                for key in report["samples"][0]["metrics"]
                for values in [[row["metrics"][key] for row in report["samples"]]]
            }
            report.update(
                status="MEASURED" if calibration else "PASS",
                performanceQualifying=not calibration,
                elapsedSeconds=time.monotonic() - started,
            )
            guarded_final_publication(REPO, destination, report, output_root, unchanged)
        return 0
    except BaseException as error:
        report.update(
            status="FAIL",
            performanceQualifying=False,
            failureType=type(error).__name__,
            reason=str(error),
            elapsedSeconds=time.monotonic() - started,
        )
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--calibrate", action="store_true", help="nonqualifying measurements; never writes the baseline"
    )
    args = parser.parse_args()
    destination = safe_output_path(REPO, args.report)
    try:
        return run(destination, args.calibrate)
    except Exception, KeyboardInterrupt:
        print(json.dumps({"status": "FAIL", "report": destination.relative_to(REPO).as_posix()}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
