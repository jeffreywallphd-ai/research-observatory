"""Fresh CAP-04.S01 scale qualification over the existing bounded workloads.

Windows only. No new product deadlines, retry policy, package execution or cache.
The historical diagnostics remain diagnostics; only this reviewed comparison of
fresh, complete samples can produce a passing performance report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
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
TOOL = Path("tools/import_performance_check.py")
BASELINE = Path("tests/fixtures/imports/performance-baseline.json")
BASELINE_SHA256 = "6b5a7f196046423ce3fbc07f8d79af642a15b0ce353994b4f7ea0e4a11a34a92"
CASES = {
    "parser": "tests.service.test_reference_import_streaming.ReferenceImportStreamingTests",
    "review": "tests.service.test_import_review_scale_windows.ImportReviewScaleWindowsTests",
    "commit": "tests.service.test_import_commit_scale_windows.ImportCommitScaleWindowsTests",
}
INPUTS = (
    "services/core-api/src",
    ":(glob)packages/contracts/**/*.json",
    "pyproject.toml",
    "uv.lock",
    str(BASELINE),
    str(TOOL),
    "tools/build_manifest.py",
    "tools/project_lifecycle_performance_check.py",
    "tools/verification_receipt.py",
    "tests/__init__.py",
    "tests/service/__init__.py",
    "tests/service/test_reference_import_streaming.py",
    "tests/service/test_import_review_scale_windows.py",
    "tests/service/test_import_commit_scale_windows.py",
)


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite_positive(value):
    require(type(value) in (int, float) and math.isfinite(value) and value > 0, "invalid positive measurement")
    return value


def baseline_document(raw):
    require(hashlib.sha256(raw).hexdigest() == BASELINE_SHA256, "baseline differs from reviewed bytes")
    value = json.loads(raw)
    require(value["repetitions"] == 2 and value["regressionAllowance"] == 0.2, "unreviewed methodology")
    for sample in value["samples"].values():
        require(
            finite_positive(sample["elapsedSeconds"]) <= sample["absoluteElapsedSeconds"] <= 1200,
            "baseline exceeds observation budget",
        )
        require(
            finite_positive(sample["workerSeconds"]) <= sample["absoluteWorkerSeconds"] <= 900,
            "baseline exceeds worker budget",
        )
        finite_positive(sample["peakWorkingSetBytes"])
    return value


def ceilings(baseline, kind):
    sample = baseline["samples"][kind]
    factor = 1 + baseline["regressionAllowance"]
    return {
        "elapsedSeconds": min(sample["elapsedSeconds"] * factor, sample["absoluteElapsedSeconds"]),
        "workerSeconds": min(sample["workerSeconds"] * factor, sample["absoluteWorkerSeconds"]),
        "peakWorkingSetBytes": math.floor(sample["peakWorkingSetBytes"] * factor),
    }


def validate_sample(kind, value, baseline, head):
    require(value["outcome"] == "functional-checks-passed-performance-diagnostic-only", "workload failed")
    require(
        value["headBefore"] == value["headAfter"] == head and value["headUnchanged"] is True, "sample candidate drift"
    )
    require(value["sourceInputsUnchanged"] is True, "sample input drift")
    require(
        value["fixtureVersion"] == baseline["fixtureVersion"]
        and value["source"] == baseline["source"]
        and value["bibliographicRecords"] == 100000,
        "fixture mismatch",
    )
    require(not value.get("retryObserved") and "durableFactsUnavailable" not in value, "incomplete or retried sample")
    require(
        value["lastJob"] == {"state": "succeeded", "attemptCount": 1, "diagnosticCode": None, "interruptionKind": None},
        "incomplete worker",
    )
    expected_facts = {
        "encryptedHeader": True,
        "canonicalRecords": 0 if kind == "review" else 100000,
        "parseRows": 100001,
        "summaryRows": 100001 if kind == "review" else 0,
        "summaryCompletions": 1 if kind == "review" else 0,
        "acceptedOutputs": 2,
    }
    require(value["durableFacts"] == expected_facts, "durable facts mismatch")
    coverage = (
        {"/projects/imports/records": (1001, 100001), "/projects/imports/summary/members": (1000, 100000)}
        if kind == "review"
        else {"/projects/imports/manifest/members": (1001, 100001)}
    )
    require(
        value["pageCoverage"]
        == {
            route: {"pages": pages, "records": records, "complete": True}
            for route, (pages, records) in coverage.items()
        },
        "incomplete traversal",
    )
    if kind == "commit":
        require(
            value["commitFacts"]
            == {
                "acceptedCommitOutputs": 1,
                "attempts": [{"attempt": 1, "state": "succeeded", "diagnosticCode": None}],
                "counts": {
                    "import_commit_rows": 100001,
                    "import_source_records": 100000,
                    "import_manifests": 1,
                    "import_manifest_members": 100001,
                    "import_manifest_seals": 1,
                },
            },
            "commit facts mismatch",
        )
    require(all(stage["state"] == "passed" for stage in value["stages"].values()), "unfinished phase")
    parse = "parse-worker" if kind == "review" else "parse-prerequisite"
    require(finite_positive(value["stages"][parse]["seconds"]) <= 180, "parse observation budget exceeded")
    metrics = {
        "elapsedSeconds": finite_positive(value["elapsedSeconds"]),
        "workerSeconds": finite_positive(
            value["stages"]["summary-worker" if kind == "review" else "commit-worker"]["seconds"]
        ),
        "peakWorkingSetBytes": finite_positive(value["memoryMaxObserved"]["peakWorkingSetSize"]),
    }
    for key, limit in ceilings(baseline, kind).items():
        require(metrics[key] <= limit, f"{kind} {key} exceeds {limit}")
    return metrics


def validate_parser(value, baseline):
    expected = baseline["parser"]
    require(value["fixtureVersion"] == expected["fixtureVersion"], "parser fixture mismatch")
    samples = value["measurements"]
    require(
        len(samples) == 6
        and {(row["format"], row["repetition"]) for row in samples}
        == {(name, repetition) for name in expected["formats"] for repetition in (1, 2)},
        "parser sample inventory",
    )
    for row in samples:
        require(row["records"] == 100000, "parser record coverage")
        finite_positive(row["seconds"])
        require(finite_positive(row["peakTracedBytes"]) < expected["peakTracedBytesExclusive"], "parser memory overage")
    return samples


def result_from_log(raw, kind):
    text = raw.decode("utf-8", errors="strict")
    require(
        re.search(r"(?m)^Ran 1 test in [0-9.]+s\s*$", text) is not None
        and re.search(r"(?m)^OK\s*$", text) is not None
        and not re.search(r"(?i)skipped|expected failure|unexpected success", text),
        "not one unskipped passing test",
    )
    values = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
    finals = [value for value in values if ("measurements" if kind == "parser" else "fixtureDirectory") in value]
    require(len(finals) == 1, "missing or duplicate final workload report")
    return finals[0]


def installed_inputs():
    # Campaigns reuse the configured environment through a .venv junction.
    # Bind and lock its actual files, rather than treating that launcher alias
    # as a second runtime or silently omitting installed dependency identity.
    site = (Path(sys.prefix) / "Lib/site-packages").resolve(strict=True)
    require(site.is_dir(), "installed dependencies unavailable")
    paths = sorted(
        path
        for path in site.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo")
    )
    require(
        paths and all(path.resolve() == path.absolute() and not path.is_symlink() for path in paths),
        "linked installed dependency",
    )
    hashes = {path.relative_to(site).as_posix(): digest(path) for path in paths}
    return paths, {
        "files": len(paths),
        "rootBindingSha256": hashlib.sha256(str(site).encode()).hexdigest(),
        "sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
    }


@contextmanager
def fixed_inputs():
    require(os.name == "nt" and Path(__file__).resolve() == REPO / TOOL, "canonical Windows runner required")
    names = str(git(REPO, "ls-files", "--", *INPUTS)).splitlines()
    paths = [Path(name) for name in names]
    require(TOOL in paths and BASELINE in paths, "uncommitted benchmark inputs")
    installed, _ = installed_inputs()
    with windows_path_locks([REPO / path for path in paths] + installed, directories=False):
        head = clean_state_commit(REPO)
        captured = {path: governed_snapshot(REPO, path) for path in paths}
        assert_committed_inputs(REPO, head, captured)
        _, dependencies = installed_inputs()
        runtime = runtime_identity()

        def unchanged():
            assert_committed_inputs(REPO, head, captured)
            require(runtime == runtime_identity() and dependencies == installed_inputs()[1], "runtime drift")

        yield head, captured, runtime, dependencies, unchanged


def child(kind, repetition, fixture):
    log = fixture / f"{kind}-{repetition}.log"
    environment = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "NUMBER_OF_PROCESSORS")
        if key in os.environ
    }
    git_executable = shutil.which("git")
    if git_executable is None:
        raise ValueError("Git unavailable")
    environment.update(
        PATH=os.pathsep.join((str(Path(git_executable).parent), str(Path(os.environ["SYSTEMROOT"]) / "System32"))),
        TEMP=str(fixture / "temp"),
        TMP=str(fixture / "temp"),
        PYTHONPATH=os.pathsep.join(map(str, (REPO, REPO / "tools", REPO / "services/core-api/src"))),
        PYTHONPYCACHEPREFIX=str(fixture / "unused-bytecode"),
        RO_RUN_IMPORT_REVIEW_SCALE="1",
        RO_RUN_IMPORT_COMMIT_SCALE="1",
        RO_IMPORT_COMMIT_RECORDS="100000",
    )
    before = set((REPO / "artifacts/tmp").glob(f"import-{kind}-scale-windows-*"))
    print(json.dumps({"workload": kind, "repetition": repetition, "state": "running"}), flush=True)
    with log.open("xb") as stream:
        process = subprocess.Popen(
            [str(Path(sys.executable).resolve(strict=True)), "-B", "-s", "-P", "-m", "unittest", CASES[kind], "-v"],
            cwd=REPO,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            code = process.wait(timeout=3700 if kind == "parser" else 1250)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    require(code == 0, f"{kind} child failed; retained {log.relative_to(REPO).as_posix()}")
    value = result_from_log(log.read_bytes(), kind)
    binding = {"log": log.relative_to(REPO).as_posix(), "logSha256": digest(log)}
    if kind != "parser":
        directory = REPO / value["fixtureDirectory"]
        require(
            directory.parent == REPO / "artifacts/tmp"
            and directory not in before
            and directory.name.startswith(f"import-{kind}-scale-windows-"),
            "stale or unconfined workload fixture",
        )
        path = safe_output_path(REPO, directory / "diagnostic.json")
        require(path.resolve(strict=True) == path.absolute() and path.stat().st_nlink == 1, "linked workload report")
        raw = path.read_bytes()
        value = json.loads(raw)
        binding.update(report=path.relative_to(REPO).as_posix(), reportSha256=hashlib.sha256(raw).hexdigest())
    return value, binding


def run(destination):
    output_root = REPO / "artifacts/tmp"
    report: dict[str, Any] = {
        "status": "RUNNING",
        "performanceQualifying": False,
        "samples": [],
        "evidenceReuse": "disabled",
    }

    def save():
        guarded_atomic_write_json(REPO, destination, report, output_root)

    save()  # Invalidate a previous PASS before any prerequisite can fail.
    started = time.monotonic()
    try:
        with fixed_inputs() as (head, captured, runtime, dependencies, unchanged):
            baseline = baseline_document(captured[BASELINE])
            hardware = hardware_record()
            for name, actual in {
                "system": hardware["operatingSystem"],
                "machine": hardware["machine"],
                "logicalCpuCount": hardware["logicalCpuCount"],
                "python": platform.python_version(),
            }.items():
                require(baseline["hardware"][name] == actual, "hardware/runtime comparison requires review")
            require(finite_positive(hardware["physicalMemoryBytes"]) > 0, "RAM unavailable")
            for sample in baseline["samples"].values():
                subprocess.run(["git", "merge-base", "--is-ancestor", sample["commit"], head], cwd=REPO, check=True)
                require(
                    git_blob_sha256(REPO, sample["commit"], Path(sample["tool"])) == sample["toolSha256"],
                    "historical tool identity mismatch",
                )
            fixture = Path(tempfile.mkdtemp(prefix="import-performance-", dir=output_root))
            (fixture / "temp").mkdir()
            report.update(
                head=head,
                toolSha256=digest(REPO / TOOL),
                baselineSha256=BASELINE_SHA256,
                inputHashes={path.as_posix(): hashlib.sha256(raw).hexdigest() for path, raw in captured.items()},
                hardware=hardware,
                runtime=runtime,
                installedDependencies=dependencies,
                fixture=fixture.relative_to(REPO).as_posix(),
                method=baseline["method"],
                ceilings={kind: ceilings(baseline, kind) for kind in ("review", "commit")},
                limitations=baseline["limitations"],
                fixturesRetained=True,
            )
            save()
            parser, binding = child("parser", 1, fixture)
            report["parser"] = {**binding, "measurements": validate_parser(parser, baseline)}
            save()
            for kind in ("review", "commit"):
                for repetition in (1, 2):
                    value, binding = child(kind, repetition, fixture)
                    item = {"workload": kind, "repetition": repetition, **binding, "rawSample": value}
                    report["samples"].append(item)
                    save()  # Preserve an adverse sample even if its thresholds fail.
                    item["metrics"] = validate_sample(kind, value, baseline, head)
                    save()
            report["distributions"] = {
                kind: {
                    metric: {"min": min(values), "median": statistics.median(values), "max": max(values)}
                    for metric in ceilings(baseline, kind)
                    for values in [[item["metrics"][metric] for item in report["samples"] if item["workload"] == kind]]
                }
                for kind in ("review", "commit")
            }
            report.update(status="PASS", performanceQualifying=True, elapsedSeconds=time.monotonic() - started)
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
    args = parser.parse_args()
    destination = safe_output_path(REPO, args.report)
    try:
        return run(destination)
    except Exception, KeyboardInterrupt:
        print(json.dumps({"status": "FAIL", "report": destination.relative_to(REPO).as_posix()}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
