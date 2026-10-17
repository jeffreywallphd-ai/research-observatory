"""Fixed Windows test process ownership; no product or generic command interface."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from io import TextIOWrapper
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]  # Same depth in tests/search after installation.
sys.path[:0] = [str(ROOT), str(ROOT / "services/core-api/src")]
from tests.service.test_native_project_contract import _RecoveryNativeJob  # noqa: E402

TEST = "supervisor::populated_search_integration::populated_generated_client_search_uses_current_native_authority"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def owned_run(argv: list[str], fixture: Path, label: str, seconds: int) -> dict:
    """Use the existing suspended, no-breakaway Windows Job launcher unchanged."""
    job = _RecoveryNativeJob()
    process = None
    reader = None
    reader_errors = []
    started = time.monotonic()
    record: dict[str, Any] = {
        "label": label,
        "status": "RUNNING",
        "forcedTermination": False,
        "startedAtUtc": dt.datetime.now(dt.UTC).isoformat(),
        "deadlineSeconds": seconds,
    }
    stdout_path, stderr_path = fixture / f"{label}.stdout.log", fixture / f"{label}.stderr.log"
    try:
        with stderr_path.open("xb") as stderr, stdout_path.open("xb") as stdout:
            process = job.launch(argv, dict(os.environ), stderr)
            # Existing launch() returns a TextIOWrapper. Read its untouched
            # binary buffer directly so CRLF and every original byte survive.
            assert process.stdout is not None and process.stdin is not None
            process.stdin.close()
            output = cast(TextIOWrapper, process.stdout).buffer

            def drain_bytes():
                try:
                    while chunk := output.read(65536):
                        stdout.write(chunk)
                    stdout.flush()
                except BaseException as error:
                    reader_errors.append(type(error).__name__)

            reader = threading.Thread(target=drain_bytes, daemon=True)
            reader.start()
            try:
                process.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                record["forcedTermination"] = True
                record["timeout"] = True
                record["forcedDrainObservation"] = job.terminate()
                process.wait(timeout=10)
            record["exitCode"] = process.returncode
            deadline = time.monotonic() + 10
            while True:
                observation = job.observe()
                if observation["active"] == 0 or time.monotonic() >= deadline:
                    break
                time.sleep(0.025)
            record["postProcessObservation"] = observation
            if observation["active"] != 0:
                record["forcedTermination"] = True
                record["forcedDrainObservation"] = job.terminate()
            if not record["forcedTermination"]:
                record["naturalDrainObservation"] = observation
            reader.join(timeout=10)
            record["binaryReaderCompleted"] = not reader.is_alive() and not reader_errors
            if not record["binaryReaderCompleted"]:
                record["binaryReaderErrors"] = reader_errors
            record["status"] = (
                "PASS"
                if process.returncode == 0
                and not record["forcedTermination"]
                and observation["active"] == 0
                and record["binaryReaderCompleted"]
                else "FAIL"
            )
    except BaseException as error:
        record["status"] = "FAIL"
        record["failureType"] = type(error).__name__
        if process is not None:
            record["forcedTermination"] = True
            try:
                record["forcedDrainObservation"] = job.terminate()
                process.wait(timeout=10)
                if reader is not None:
                    reader.join(timeout=10)
            except BaseException as cleanup_error:
                record["cleanupFailureType"] = type(cleanup_error).__name__
    finally:
        job.close()
        record["elapsedSeconds"] = time.monotonic() - started
        record["completedAtUtc"] = dt.datetime.now(dt.UTC).isoformat()
        for name, path in (("stdout", stdout_path), ("stderr", stderr_path)):
            if path.exists():
                record[name] = path.name
                record[f"{name}Sha256"] = sha(path)
    return record


def main() -> int:
    if os.name != "nt":
        raise RuntimeError("actual Windows Job ownership required")
    fixture = Path(sys.argv[1]).resolve(strict=True)
    scratch = (ROOT / "artifacts/tmp").resolve(strict=True)
    if fixture.parent != scratch or not fixture.name.startswith("search-populated-native-"):
        raise ValueError("fixed owned fixture required")
    for part in (fixture, *fixture.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("redirected fixture denied")
        if part == scratch:
            break
    cargo = Path(sys.argv[2]).resolve(strict=True)
    report_path = fixture / "owner-report.json"
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump({"status": "RUNNING"}, stream)
    report: dict[str, Any] = {
        "documentType": "fixed-populated-native-process-ownership",
        "status": "FAIL",
        "runs": [],
        "ownerSourceSha256": sha(Path(__file__)),
        "existingJobSourceSha256": sha(ROOT / "tests/service/test_native_project_contract.py"),
        "existingJobStructureSourceSha256": sha(ROOT / "workers/windows/lpac_launcher.py"),
        "cargoSha256": sha(cargo),
        "scope": "Actual compiler and Native-test descendants; no renderer, packaging or 100k result.",
    }
    try:
        build = owned_run(
            [
                str(cargo),
                "test",
                "--locked",
                "--offline",
                "--features",
                "integration-harness",
                "--lib",
                "--no-run",
                "--message-format=json",
                "--manifest-path",
                str(ROOT / "apps/desktop/src-tauri/Cargo.toml"),
            ],
            fixture,
            "compiler",
            360,
        )
        report["runs"].append(build)
        if build["status"] != "PASS":
            return 1
        events = [
            json.loads(line)
            for line in (fixture / "compiler.stdout.log").read_text("utf-8").splitlines()
            if line.strip()
        ]
        outputs = [
            Path(row["executable"]).resolve(strict=True)
            for row in events
            if row.get("reason") == "compiler-artifact"
            and row.get("target", {}).get("name") == "research_observatory_desktop_lib"
            and row.get("profile", {}).get("test") is True
            and row.get("executable")
        ]
        if len(outputs) != 1 or not outputs[0].is_relative_to((ROOT / "target/debug/deps").resolve(strict=True)):
            raise ValueError("exact Cargo test artifact required")
        executable = outputs[0]
        executable_hash = sha(executable)
        report["testExecutable"] = executable.relative_to(ROOT).as_posix()
        report["testExecutableSha256"] = executable_hash
        runtime = owned_run([str(executable), "--exact", TEST, "--ignored", "--nocapture"], fixture, "native-test", 240)
        report["runs"].append(runtime)
        report["testExecutableEqualityAfter"] = sha(executable) == executable_hash
        if runtime["status"] == "PASS" and report["testExecutableEqualityAfter"]:
            report["status"] = "PASS"
        return 0 if report["status"] == "PASS" else 1
    except BaseException as error:
        report["failureType"] = type(error).__name__
        return 1
    finally:
        report["completedAtUtc"] = dt.datetime.now(dt.UTC).isoformat()
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
