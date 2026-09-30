"""Fresh CAP-04.S03 kernel/protected-project performance qualification.

Calibration is nonqualifying. Qualification requires an independently reviewed
immutable baseline, unchanged committed inputs, and three new Windows processes.
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
TOOL = Path("tools/reconciliation_performance_check.py")
BASELINE = Path("tests/fixtures/scholarly-duplicates/reconciliation-performance-baseline.json")
BASELINE_SHA256 = "PENDING-INDEPENDENT-BASELINE-REVIEW"
REPETITIONS = 3
METHOD = {
    "fixtureVersion": "dblp-acm-benchmark-v1/qualification+synthetic-protected-reconciliation-202-v1",
    "repetitions": REPETITIONS,
    "timer": "time.perf_counter",
    "kernelCold": "all 2463 frozen records; feature preparation plus candidate retrieval",
    "kernelPrepared": "separate feature preparation and exact prepared-input candidate retrieval",
    "protectedCold": "fresh protected project/process, 202 accepted import and one retained connector record",
    "protectedWarm": "new request and worker job over unchanged sources; revision-bound feature cache reuse",
    "protectedPages": "fresh authorized first and later <=100-item candidate pages",
    "measured": (
        "public batch prepare/schedule through durable worker status, real DPAPI/SQLCipher and worker admission"
    ),
    "excluded": "synthetic project/import/connector setup and project reopen/close; memory includes entire child",
    "setupSubstitution": "synthetic Crossref transport and ASGI/native context; setup alone patches worker capacity",
    "distribution": "min/median/max of three repetitions; every raw sample must pass; no discarded samples",
    "regressionAllowance": 0.2,
    "osCacheFlushed": False,
}
CEILINGS = {
    "kernelColdSeconds": 30,
    "kernelPreparationSeconds": 30,
    "kernelPreparedRetrievalSeconds": 30,
    "protectedColdSeconds": 120,
    "protectedWarmSeconds": 120,
    "firstPageSeconds": 20,
    "laterPageSeconds": 20,
    "peakWorkingSetBytes": 512 * 1024**2,
}
INPUTS = (
    "services/core-api/src",
    ":(glob)packages/contracts/**/*.json",
    ":(glob)tests/**/*.py",
    ":(glob)tests/fixtures/**/*.json",
    ":(glob)tests/fixtures/scholarly-duplicates/*.csv",
    "pyproject.toml",
    "uv.lock",
    str(TOOL),
    "tools/import_performance_check.py",
    "tools/build_manifest.py",
    "tools/project_lifecycle_performance_check.py",
    "tools/verification_receipt.py",
)


def validate_baseline(raw: bytes) -> dict:
    require(hashlib.sha256(raw).hexdigest() == BASELINE_SHA256, "baseline differs from independent reviewed bytes")
    value = json.loads(raw)
    require(value["method"] == METHOD, "unreviewed benchmark method")
    require(set(value["maxima"]) == set(CEILINGS), "incomplete baseline workload inventory")
    require(value["calibration"]["performanceQualifying"] is False, "calibration mislabeled qualifying")
    raw_samples = value["calibration"]["rawMetrics"]
    require(len(raw_samples) == REPETITIONS, "baseline calibration samples missing")
    for key, limit in CEILINGS.items():
        maximum = finite_positive(value["maxima"][key])
        require(maximum <= limit, "baseline exceeds bounded workload budget")
        require(
            all(set(row) == set(CEILINGS) for row in raw_samples)
            and max(finite_positive(row[key]) for row in raw_samples) == maximum,
            "baseline differs from raw calibration",
        )
    return value


def sample_metrics(sample: dict) -> dict[str, float]:
    kernel, protected = sample["kernel"], sample["protected"]
    require(
        kernel["fixtureVersion"] == "dblp-acm-benchmark-v1/qualification"
        and kernel["records"] == 2463
        and kernel["comparisons"] == 105451
        and kernel["returnedPairs"] == 1273
        and kernel["crossSourceReturnedPairs"] == 1142
        and (kernel["truePositives"], kernel["goldPairs"]) == (1092, 1115)
        and kernel["preparedEquivalent"] is True
        and kernel["precision"] >= 0.90
        and kernel["recall"] >= 0.95,
        "frozen kernel workload or accuracy differs",
    )
    require(
        protected["fixtureVersion"] == "synthetic-protected-reconciliation-202-v1"
        and (protected["acceptedImportRecords"], protected["retainedConnectorRecords"]) == (202, 1)
        and (protected["recordCount"], protected["candidateCount"]) == (203, 103)
        and protected["actualDPAPIAndSQLCipher"] is True
        and protected["providerNetworkDuringMeasurement"] == 0
        and protected["workerCapacitySubstitutedDuringSetup"] is True
        and protected["workerCapacitySubstitutedDuringMeasurement"] is False,
        "protected workload boundary differs",
    )
    batches = protected["batches"]
    pages = protected["pages"]
    require(
        len(batches) == 2
        and [row["phase"] for row in batches] == ["cold", "warm"]
        and all(row["newJob"] is True and row["newRequest"] is True for row in batches)
        and batches[0]["featureComputations"] is None
        and batches[1]["featureComputations"] == 0,
        "protected warm batch must be a new cached job",
    )
    require(
        len(pages) == 2 and [(row["after"], row["items"]) for row in pages] == [(0, 100), (100, 3)],
        "protected pagination incomplete",
    )
    return {
        "kernelColdSeconds": finite_positive(kernel["coldSeconds"]),
        "kernelPreparationSeconds": finite_positive(kernel["preparationSeconds"]),
        "kernelPreparedRetrievalSeconds": finite_positive(kernel["preparedRetrievalSeconds"]),
        "protectedColdSeconds": finite_positive(batches[0]["seconds"]),
        "protectedWarmSeconds": finite_positive(batches[1]["seconds"]),
        "firstPageSeconds": finite_positive(pages[0]["seconds"]),
        "laterPageSeconds": finite_positive(pages[1]["seconds"]),
        "peakWorkingSetBytes": finite_positive(sample["memory"]["peakWorkingSetSize"]),
    }


def validate_metrics(metrics: dict[str, float], baseline: dict) -> None:
    require(set(metrics) == set(CEILINGS), "incomplete qualifying metric inventory")
    for key, measured in metrics.items():
        ceiling = min(finite_positive(baseline["maxima"][key]) * 1.2, CEILINGS[key])
        require(finite_positive(measured) <= ceiling, f"{key} exceeds reviewed ceiling {ceiling}")


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
    require(
        TOOL in paths
        and Path("tests/reconciliation/performance_workload.py") in paths
        and Path("tests/reconciliation/native_fixture.py") in paths
        and Path("tests/fixtures/scholarly-duplicates/DBLP-ACM_perfectMapping.csv") in paths,
        "uncommitted benchmark producer or incomplete fixture inventory",
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


def child(repetition: int, directory: Path) -> tuple[dict, dict]:
    folder = directory / f"sample-{repetition}"
    folder.mkdir()
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
        "from tests.reconciliation.performance_workload import run_workload; "
        "from tests.service.test_import_review_scale_windows import _memory; "
        "result=run_workload(Path(sys.argv[1])); "
        "result['memory']=_memory(); "
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
    require(code == 0, f"reconciliation sample failed; retained {log.relative_to(REPO).as_posix()}")
    require(
        safe_output_path(REPO, result).resolve(strict=True) == result.absolute()
        and result.stat().st_nlink == 1
        and not result.is_symlink(),
        "missing/linked sample",
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
            directory = Path(tempfile.mkdtemp(prefix="reconciliation-performance-", dir=output_root))
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
