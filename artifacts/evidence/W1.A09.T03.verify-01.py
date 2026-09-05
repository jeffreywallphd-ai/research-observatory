"""Run bounded T03 regression checks with exact source and outcome bindings.

Actual Windows UI and default/Core proofs are separate, explicitly scoped reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from desktop_app_check import tool_environment  # noqa: E402


def native_tests_executed(output: str) -> bool:
    """An exit-zero filter that selected no tests proves no acceptance boundary."""
    return re.search(r"test result: ok\. [1-9][0-9]* passed; 0 failed;", output) is not None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    path = args.report if args.report.is_absolute() else REPO / args.report
    assert ".." not in path.parts and path.parent == REPO / "artifacts/evidence"
    assert re.fullmatch(r"W1\.A09\.T03\.verification-[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.json", path.name)
    assert not path.exists(), "Never replace an existing observation"
    environment, corepack, cargo = tool_environment(REPO)
    temporary = Path(tempfile.mkdtemp(prefix="t03-verification-", dir=REPO / "artifacts/tmp"))
    environment = {**environment, "TEMP": str(temporary), "TMP": str(temporary), "PYTHONDONTWRITEBYTECODE": "1"}
    python = str(REPO / ".venv/Scripts/python.exe")
    evidence = "artifacts/evidence/W1.A09.T03."
    harnesses = [
        evidence + name for name in (
            "verify-01.py", "renderer-check-01.py", "renderer-evidence-test-01.py",
            "default-core-check-01.py", "default-core-pin-test-01.py", "default-diagnostic-01.py",
            "default-failure-diagnostic-01.py", "runtime-principal-check-01.py",
            "runtime-token-check-01.py", "verification-evidence-test-01.py",
        )
    ]
    inputs = subprocess.check_output(
        ["git", "ls-files", "--", "Cargo.toml", "Cargo.lock", "apps/desktop", "packages/ui-components",
         "packages/contracts", "services/core-api/src", "tools/desktop_app_check.py",
         "tests/desktop/test_desktop_app_check.py", "tests/security/test_application_lock_source.py",
         "tests/service/test_project_lifecycle.py", "tests/service/test_native_project_contract.py"],
        cwd=REPO, text=True, encoding="utf-8",
    ).splitlines()
    inputs = sorted(set(inputs + harnesses + [
        "apps/desktop/src-tauri/src/directory_picker.rs", "apps/desktop/src/app/directoryPicker.ts",
        "apps/desktop/src/app/directoryPicker.test.ts", "packages/ui-components/src/DirectoryPickerField.tsx",
        "tests/service/test_project_probe_build.py",
    ]))

    def hashes() -> dict[str, str]:
        return {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in inputs}

    def redact(value: str) -> str:
        for source, replacement in ((str(REPO), "{repo}"), (os.environ.get("USERPROFILE", ""), "{user-profile}")):
            if source:
                value = value.replace(source, replacement).replace(source.replace("\\", "/"), replacement)
        return re.sub(r"(?i)[A-Z]:[\\/]Users[\\/][^\\/\s\"]+", "{user-profile}", value)

    def pnpm(directory: str, *args: str) -> list[str]:
        return [str(corepack), "pnpm", "--dir", directory, *args]

    native = [str(cargo), "test", "--locked", "--offline", "-p", "research-observatory-desktop", "--lib"]
    commands = [
        ("renderer-unit", pnpm("apps/desktop", "exec", "vitest", "run", "src/app/ProjectsWorkspace.test.tsx",
                               "src/app/directoryPicker.test.ts", "src/app/LocalServiceBoundary.test.tsx",
                               "src/app/ApplicationRuntime.test.tsx", "src/app/ApplicationLockBoundary.test.tsx")),
        ("shared-field-unit", pnpm("packages/ui-components", "exec", "vitest", "run", "tests/package.test.tsx")),
        ("renderer-types", pnpm("apps/desktop", "run", "typecheck")),
        ("shared-field-types", pnpm("packages/ui-components", "run", "typecheck")),
        ("renderer-lint", pnpm("apps/desktop", "run", "lint")),
        ("python-lint", [python, "-m", "ruff", "check", *harnesses, "tools/desktop_app_check.py",
                         "tests/desktop/test_desktop_app_check.py", "tests/service/test_native_project_contract.py",
                         "tests/service/test_project_probe_build.py",
                         "tests/security/test_application_lock_source.py"]),
        ("native-picker-production", [*native, "directory_picker"]),
        ("native-picker-harness", [*native, "--features", "integration-harness", "directory_picker"]),
        ("native-fixture-boundaries", [*native, "--features", "integration-harness",
                                       "directory_integration_harness::tests"]),
        ("native-production-lint", [str(cargo), "clippy", "--locked", "--offline", "-p",
                                    "research-observatory-desktop", "--lib", "--", "-D", "warnings"]),
        ("native-harness-lint", [str(cargo), "clippy", "--locked", "--offline", "-p",
                                 "research-observatory-desktop", "--features", "integration-harness", "--lib",
                                 "--example", "project_contract_probe", "--", "-D", "warnings"]),
        ("protected-source", [python, "-m", "unittest", "discover", "-s", "tests/security", "-p",
                              "test_application_lock_source.py", "-v"]),
        ("core-project-lifecycle", [python, "-m", "unittest", "discover", "-s", "tests/service", "-p",
                                    "test_project_lifecycle.py", "-v"]),
        ("default-proof-safeguards", [python, "-I", "-B", evidence + "default-core-pin-test-01.py"]),
        ("renderer-proof-publication", [python, "-I", "-B", evidence + "renderer-evidence-test-01.py"]),
        ("verification-proof-selection", [python, "-I", "-B", evidence + "verification-evidence-test-01.py"]),
        ("native-probe-build-binding", [python, "-m", "unittest", "discover", "-s", "tests/service", "-p",
                                        "test_project_probe_build.py", "-v"]),
        ("renderer-recovery", [python, "-m", "unittest", "discover", "-s", "tests/desktop", "-p",
                               "test_desktop_app_check.py", "-k", "ProjectRecoveryInteractionTests", "-v"]),
        ("backlog-views", [python, "tools/backlog_views.py", "--repo", ".", "--check"]),
    ]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    before = hashes()
    checks = []
    started_at = datetime.now(UTC).isoformat()
    for name, command in commands:
        print(f"Starting {name}", flush=True)
        started = time.monotonic()
        try:
            result = subprocess.run(command, cwd=REPO, env=environment, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=240)
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            code, stdout, stderr = -1, "", "Bounded command timed out; not a passing check."
        nonvacuous = name not in {
            "native-picker-production", "native-picker-harness", "native-fixture-boundaries",
        } or native_tests_executed(stdout)
        checks.append({"name": name, "command": [redact(arg) for arg in command], "exitCode": code,
                       "testSelectionSatisfied": nonvacuous,
                       "durationSeconds": round(time.monotonic() - started, 3),
                       "stdout": redact(stdout), "stderr": redact(stderr)})
        print(f"{name}: exit {code}", flush=True)
    stable = hashes() == before and subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip() == commit
    report = {"taskId": "W1.A09.T03", "testedCommit": commit, "sourceHashes": before,
              "startedAt": started_at, "completedAt": datetime.now(UTC).isoformat(), "checks": checks,
              "temporaryNamespace": temporary.relative_to(REPO).as_posix(), "fixturesRetained": True,
              "inputsUnchanged": stable,
              "ok": stable and all(item["exitCode"] == 0 and item["testSelectionSatisfied"] for item in checks),
              "scope": "Risk-selected deterministic T03 checks; separate real UI/default/Core reports are required."}
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"ok": report["ok"], "report": path.relative_to(REPO).as_posix()}), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
