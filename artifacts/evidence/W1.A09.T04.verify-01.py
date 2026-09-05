"""Accumulated A09 checks; real native UI and package observations are separate."""

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


def selection_satisfied(kind: str, output: str) -> bool:
    patterns = {
        "native": r"test result: ok\. [1-9][0-9]* passed; 0 failed;",
        "python": r"Ran [1-9][0-9]* tests? in",
        "vitest": r"Tests\s+[1-9][0-9]* passed",
    }
    return kind == "command" or re.search(patterns[kind], output) is not None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=("units", "native", "integration"), required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"W1\.A09\.T04\.verification-[A-Za-z0-9_-]{1,64}\.json", args.report)
    destination = REPO / "artifacts/evidence" / args.report
    assert not destination.exists(), "Retain prior observations"
    environment, corepack, cargo = tool_environment(REPO)
    temporary = Path(tempfile.mkdtemp(prefix="t04-verification-", dir=REPO / "artifacts/tmp"))
    environment = {
        **environment,
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "PYTHONDONTWRITEBYTECODE": "1",
        "NO_COLOR": "1",
    }
    python = str(REPO / ".venv/Scripts/python.exe")

    def pnpm(directory: str, *arguments: str) -> list[str]:
        return [str(corepack), "pnpm", "--dir", directory, *arguments]

    def unittest(directory: str, pattern: str, *arguments: str) -> list[str]:
        return [python, "-m", "unittest", "discover", "-s", directory, "-p", pattern, *arguments, "-v"]

    commands = {
        "units": [
            ("generated-core-contract", "command", [python, "tools/core_api_contract.py", "--repo", ".", "--check"]),
            (
                "generated-client-and-workflow",
                "vitest",
                pnpm(
                    "packages/contracts",
                    "exec",
                    "vitest",
                    "run",
                    "core-api/generated.test.ts",
                    "project/project.test.ts",
                    "workflow-profile/workflow-profile.test.ts",
                ),
            ),
            (
                "renderer-affected-union",
                "vitest",
                pnpm(
                    "apps/desktop",
                    "exec",
                    "vitest",
                    "run",
                    "src/app/AuditLineageWorkspace.test.tsx",
                    "src/app/ProjectsWorkspace.test.tsx",
                    "src/app/directoryPicker.test.ts",
                    "src/app/LocalServiceBoundary.test.tsx",
                    "src/app/ApplicationRuntime.test.tsx",
                    "src/app/ApplicationLockBoundary.test.tsx",
                ),
            ),
            (
                "shared-fields",
                "vitest",
                pnpm("packages/ui-components", "exec", "vitest", "run", "tests/package.test.tsx"),
            ),
            (
                "semantic-predecessor-compatibility",
                "python",
                unittest("tests/contracts", "test_workflow_profile_contracts.py"),
            ),
            ("protected-source", "python", unittest("tests/security", "test_application_lock_source.py")),
            ("core-project-lifecycle", "python", unittest("tests/service", "test_project_lifecycle.py")),
            ("build-binding", "python", unittest("tests/service", "test_project_probe_build.py")),
            (
                "renderer-recovery",
                "python",
                unittest("tests/desktop", "test_desktop_app_check.py", "-k", "ProjectRecoveryInteractionTests"),
            ),
            (
                "default-proof-safeguards",
                "python",
                [python, "-I", "-B", "artifacts/evidence/W1.A09.T03.default-core-pin-test-01.py"],
            ),
            ("renderer-lint", "command", pnpm("apps/desktop", "run", "lint")),
            ("renderer-types", "command", pnpm("apps/desktop", "run", "typecheck")),
            ("contracts-types", "command", pnpm("packages/contracts", "run", "typecheck")),
            ("shared-types", "command", pnpm("packages/ui-components", "run", "typecheck")),
            ("backlog-views", "command", [python, "tools/backlog_views.py", "--repo", ".", "--check"]),
        ],
        "native": [
            (
                "native-production-lib",
                "native",
                [str(cargo), "test", "--locked", "--offline", "-p", "research-observatory-desktop", "--lib"],
            ),
            (
                "native-harness-lib",
                "native",
                [
                    str(cargo),
                    "test",
                    "--locked",
                    "--offline",
                    "-p",
                    "research-observatory-desktop",
                    "--features",
                    "integration-harness",
                    "--lib",
                ],
            ),
            (
                "native-production-all-test-lint",
                "command",
                [
                    str(cargo),
                    "clippy",
                    "--locked",
                    "--offline",
                    "-p",
                    "research-observatory-desktop",
                    "--lib",
                    "--tests",
                    "--",
                    "-D",
                    "warnings",
                ],
            ),
            (
                "native-harness-all-test-lint",
                "command",
                [
                    str(cargo),
                    "clippy",
                    "--locked",
                    "--offline",
                    "-p",
                    "research-observatory-desktop",
                    "--features",
                    "integration-harness",
                    "--lib",
                    "--tests",
                    "--example",
                    "project_contract_probe",
                    "--",
                    "-D",
                    "warnings",
                ],
            ),
        ],
        "integration": [
            ("actual-generated-native-core", "python", unittest("tests/service", "test_native_project_contract.py")),
            (
                "production-package-contract-failure-recovery",
                "python",
                unittest("tests/packaging", "test_core_sidecar_package.py"),
            ),
        ],
    }[args.group]
    regions = [
        "Cargo.toml",
        "Cargo.lock",
        "pyproject.toml",
        "uv.lock",
        "apps/desktop",
        "packages/contracts",
        "packages/ui-components",
        "services/core-api",
        "tests/service/test_native_project_contract.py",
        "tests/service/test_project_probe_build.py",
        "tests/service/test_project_lifecycle.py",
        "tests/contracts/test_workflow_profile_contracts.py",
        "tests/packaging/test_core_sidecar_package.py",
        "tests/security/test_application_lock_source.py",
        "tests/desktop/test_desktop_app_check.py",
        "tools/desktop_app_check.py",
        "tools/ui_conformance.py",
        "tools/core_api_contract.py",
        "tools/core_sidecar_build.py",
        "tools/backlog_views.py",
        "artifacts/evidence/W1.A09.T04.verify-01.py",
        "artifacts/evidence/W1.A09.T03.default-core-pin-test-01.py",
        "artifacts/evidence/W1.A09.T03.default-core-check-01.py",
    ]

    def hashes() -> dict[str, str]:
        # Include new nonignored inputs as well as tracked ones; never scan unrelated evidence.
        names = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", *regions],
            cwd=REPO,
            text=True,
            encoding="utf-8",
        ).splitlines()
        return {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in sorted(set(names))}

    def redact(value: str) -> str:
        for original, replacement in ((str(REPO), "{repo}"), (os.environ.get("USERPROFILE", ""), "{user-profile}")):
            if original:
                for spelling in (original.replace("\\", "\\\\"), original, original.replace("\\", "/")):
                    value = value.replace(spelling, replacement)
        value = re.sub(r"(?m)^\t[^\r\n]+ \(S-[0-9-]+\)", "\t{local-account} ({sid})", value)
        value = re.sub(r"\bS-1-[0-9-]+\b", "{sid}", value)
        return re.sub(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"']+", "{user-profile}", value)

    before = hashes()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    started_at = datetime.now(UTC).isoformat()
    checks = []
    for name, kind, command in commands:
        print(f"Starting {name}", flush=True)
        started = time.monotonic()
        try:
            result = subprocess.run(
                command,
                cwd=REPO,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            code, stdout, stderr = -1, "", "Timed out; not a passing check."
        selected = selection_satisfied(kind, stdout + stderr)
        checks.append(
            {
                "name": name,
                "kind": kind,
                "command": [redact(item) for item in command],
                "exitCode": code,
                "testSelectionSatisfied": selected,
                "durationSeconds": round(time.monotonic() - started, 3),
                "stdout": redact(stdout),
                "stderr": redact(stderr),
            }
        )
        print(f"{name}: exit {code}, selection {selected}", flush=True)
    unchanged = (
        before == hashes()
        and head == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    )
    report = {
        "taskId": "W1.A09.T04",
        "group": args.group,
        "observedHead": head,
        "sourceHashes": before,
        "startedAt": started_at,
        "completedAt": datetime.now(UTC).isoformat(),
        "checks": checks,
        "inputsUnchanged": unchanged,
        "temporaryNamespace": temporary.relative_to(REPO).as_posix(),
        "fixturesRetained": True,
        "ok": unchanged and all(item["exitCode"] == 0 and item["testSelectionSatisfied"] for item in checks),
        "scope": "Accumulated affected deterministic checks; not real UI or unmodified production startup proof.",
    }
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"ok": report["ok"], "report": destination.relative_to(REPO).as_posix()}), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
