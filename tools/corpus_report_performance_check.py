"""CAP-04.S04 protected source-overlap performance qualification.

Calibration is explicitly nonqualifying and never writes the baseline.
Qualification requires an independently reviewed immutable baseline, a clean
committed input snapshot, and three fresh Windows measurement processes.
The first report follows project reopen *and* an incremental update; neither
phase claims a flushed operating-system cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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
TOOL = Path("tools/corpus_report_performance_check.py")
WORKLOAD = Path("tests/corpus_reports/performance_workload.py")
BASELINE = Path("tests/fixtures/corpus-reports/performance-baseline.json")
# Replaced only after independent review of raw nonqualifying calibration.
BASELINE_SHA256 = "PENDING-INDEPENDENT-BASELINE-REVIEW"
REPETITIONS = 3
METHOD = {
    "fixtureVersion": "synthetic-protected-corpus-overlap-64-v1",
    "canonicalItems": 64,
    "discoveryPaths": 67,
    "sourceRoots": 4,
    "sourceOverlapPairs": 6,
    "repetitions": REPETITIONS,
    "timer": "time.perf_counter_ns",
    "firstReportState": "first report after project reopen and a measured incremental source-path update",
    "repeatReportState": "new command and snapshot over unchanged canonical corpus in same process",
    "measured": "Core corpus update; authenticated report seal, inspect and complete paged drill over DPAPI/SQLCipher",
    "excluded": "synthetic setup, project reopen/close, and post-timing verification",
    "memoryScope": "peak working set includes the entire child process and synthetic setup",
    "distribution": "min/median/max of three fresh processes; every raw sample must pass; no samples discarded",
    "regressionAllowance": 0.2,
    "osCacheFlushed": False,
    "providerNetworkDuringMeasurement": 0,
}
CEILINGS = {
    "incrementalUpdateSeconds": 30,
    "firstReportAfterReopenAndUpdateSeconds": 60,
    "repeatReportSeconds": 60,
    "inspectSeconds": 30,
    "firstDrillPageSeconds": 30,
    "laterDrillPageSeconds": 30,
    "peakWorkingSetBytes": 512 * 1024**2,
    "databaseGrowthBytes": 64 * 1024**2,
}
INPUTS = (
    "services/core-api/src",
    ":(glob)packages/contracts/**/*.json",
    ":(glob)tests/**/*.py",
    "pyproject.toml",
    "uv.lock",
    str(TOOL),
    str(BASELINE),
    "tools/import_performance_check.py",
    "tools/build_manifest.py",
    "tools/project_lifecycle_performance_check.py",
    "tools/verification_receipt.py",
)


def _nonnegative(value: Any) -> float:
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "non-finite or negative metric")
    return float(value)


def validate_baseline(raw: bytes) -> dict:
    require(BASELINE_SHA256 != "PENDING-INDEPENDENT-BASELINE-REVIEW", "baseline awaits independent review")
    require(hashlib.sha256(raw).hexdigest() == BASELINE_SHA256, "baseline differs from independent reviewed bytes")
    value = json.loads(raw)
    require(value["method"] == METHOD, "unreviewed benchmark method")
    require(set(value["maxima"]) == set(CEILINGS), "incomplete baseline workload inventory")
    require(value["calibration"]["performanceQualifying"] is False, "calibration mislabeled qualifying")
    workload_sha = value["calibration"]["workloadSha256"]
    require(
        isinstance(workload_sha, str)
        and len(workload_sha) == 64
        and all(char in "0123456789abcdef" for char in workload_sha),
        "calibration workload hash invalid",
    )
    raw_samples = value["calibration"]["rawMetrics"]
    require(len(raw_samples) == REPETITIONS, "baseline calibration samples missing")
    for key, hard_ceiling in CEILINGS.items():
        maximum = _nonnegative(value["maxima"][key])
        require(maximum <= hard_ceiling, "baseline exceeds bounded workload budget")
        require(
            all(set(row) == set(CEILINGS) for row in raw_samples)
            and max(_nonnegative(row[key]) for row in raw_samples) == maximum,
            "baseline differs from raw calibration",
        )
    return value


def verify_calibration_identity(head: str, captured: dict[Path, bytes], baseline: dict) -> None:
    prior = baseline["calibration"]
    subprocess.run(["git", "merge-base", "--is-ancestor", prior["commit"], head], cwd=REPO, check=True)
    require(git_blob_sha256(REPO, prior["commit"], TOOL) == prior["toolSha256"], "calibration producer mismatch")
    current_tool = captured[TOOL]
    current_assignment = f'BASELINE_SHA256 = "{BASELINE_SHA256}"'.encode()
    placeholder = b'BASELINE_SHA256 = "PENDING-INDEPENDENT-BASELINE-REVIEW"'
    require(current_tool.count(current_assignment) == 1, "current runner baseline assignment differs")
    require(
        hashlib.sha256(current_tool.replace(current_assignment, placeholder, 1)).hexdigest() == prior["toolSha256"],
        "current runner differs from calibration producer",
    )
    workload_sha = prior["workloadSha256"]
    require(git_blob_sha256(REPO, prior["commit"], WORKLOAD) == workload_sha, "calibration workload blob mismatch")
    require(
        hashlib.sha256(captured[WORKLOAD]).hexdigest() == workload_sha,
        "current workload differs from reviewed baseline",
    )


def sample_metrics(sample: dict) -> dict[str, float]:
    require(
        sample["fixtureVersion"] == METHOD["fixtureVersion"]
        and sample["itemCount"] == 64
        and sample["discoveryPathCount"] == 67
        and sample["sourceRootCount"] == 4
        and sample["sourcePairCount"] == 6
        and sample["actualDPAPIAndSQLCipher"] is True
        and sample["providerNetworkDuringMeasurement"] == 0
        and sample["pageSizes"] == [32, 32],
        "protected corpus workload differs",
    )
    timings = sample["timings"]
    require(
        set(timings)
        == {
            "incrementalUpdateSeconds",
            "firstReportAfterReopenAndUpdateSeconds",
            "repeatReportSeconds",
            "inspectSeconds",
            "firstDrillPageSeconds",
            "laterDrillPageSeconds",
        },
        "incomplete timing inventory",
    )
    sizes = sample["databaseBytes"]
    require(set(sizes) == {"before", "afterUpdate", "afterReport"}, "incomplete database size inventory")
    before, after_update, after_report = (_nonnegative(sizes[key]) for key in ("before", "afterUpdate", "afterReport"))
    require(before > 0, "protected database missing")
    result = {key: finite_positive(timings[key]) for key in timings}
    result["peakWorkingSetBytes"] = finite_positive(sample["memory"]["peakWorkingSetSize"])
    result["databaseGrowthBytes"] = max(before, after_update, after_report) - before
    return result


def validate_metrics(metrics: dict[str, float], baseline: dict) -> None:
    require(set(metrics) == set(CEILINGS), "incomplete qualifying metric inventory")
    for key, measured in metrics.items():
        ceiling = min(_nonnegative(baseline["maxima"][key]) * 1.2, CEILINGS[key])
        require(_nonnegative(measured) <= ceiling, f"{key} exceeds reviewed ceiling {ceiling}")


@contextmanager
def fixed_inputs():
    require(os.name == "nt" and Path(__file__).resolve() == REPO / TOOL, "canonical Windows runner required")
    require(sys.dont_write_bytecode and sys.pycache_prefix is not None, "fresh bytecode prefix required")
    assert sys.pycache_prefix is not None
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
    require(TOOL in paths and WORKLOAD in paths, "uncommitted benchmark producer or fixture")
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


def child(repetition: int, directory: Path) -> tuple[dict, dict]:
    folder = directory / f"sample-{repetition}"
    folder.mkdir()
    (folder / "fixture").mkdir()
    log, result = folder / "raw.log", folder / "result.json"
    environment = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "NUMBER_OF_PROCESSORS")
        if key in os.environ
    }
    executable = shutil.which("git")
    require(executable is not None, "Git unavailable")
    assert executable is not None
    environment.update(
        PATH=os.pathsep.join((str(Path(executable).parent), str(Path(os.environ["SYSTEMROOT"]) / "System32"))),
        TEMP=str(folder),
        TMP=str(folder),
        PYTHONPATH=os.pathsep.join(map(str, (REPO, REPO / "tools", REPO / "services/core-api/src"))),
        PYTHONPYCACHEPREFIX=str(folder / "unused-bytecode"),
    )
    script = (
        "import json,sys; from pathlib import Path; "
        "from tests.corpus_reports.performance_workload import run_workload; "
        "result=run_workload(Path(sys.argv[1])); "
        "Path(sys.argv[2]).write_text(json.dumps(result,sort_keys=True)+'\\n',encoding='utf-8')"
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
                str(result),
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
    require(code == 0, f"corpus report sample failed; retained {log.relative_to(REPO).as_posix()}")
    require(
        safe_output_path(REPO, result).resolve(strict=True) == result.absolute()
        and result.stat().st_nlink == 1
        and not result.is_symlink(),
        "missing or linked benchmark sample",
    )
    raw = result.read_bytes()
    return json.loads(raw), {
        "report": result.relative_to(REPO).as_posix(),
        "reportSha256": hashlib.sha256(raw).hexdigest(),
        "log": log.relative_to(REPO).as_posix(),
        "logSha256": digest(log),
    }


def run(destination: Path, calibration: bool = False) -> int:
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

    save()  # Invalidate a stale PASS before checking any prerequisite.
    started = time.monotonic()
    try:
        with fixed_inputs() as (head, captured, runtime, dependencies, unchanged):
            if not calibration:
                require(BASELINE in captured, "baseline awaits independent review")
            baseline = None if calibration else validate_baseline(captured[BASELINE])
            hardware = hardware_record()
            require(finite_positive(hardware["physicalMemoryBytes"]) > 0, "hardware unavailable")
            if baseline is not None:
                require(baseline["hardware"] == hardware, "hardware comparison requires review")
                verify_calibration_identity(head, captured, baseline)
            directory = Path(tempfile.mkdtemp(prefix="corpus-report-performance-", dir=output_root))
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
                for key in CEILINGS
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--calibrate", action="store_true", help="nonqualifying; never writes the baseline")
    args = parser.parse_args()
    destination = safe_output_path(REPO, args.report)
    try:
        return run(destination, args.calibrate)
    except Exception, KeyboardInterrupt:
        print(json.dumps({"status": "FAIL", "report": destination.relative_to(REPO).as_posix()}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
