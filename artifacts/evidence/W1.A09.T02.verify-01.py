"""Replay the risk-selected T02 checks and retain exact inputs and outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import tool_environment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    arguments = parser.parse_args()
    report_path = (REPO / arguments.report).resolve()
    if report_path.parent != REPO / "artifacts/evidence" or report_path.exists():
        raise ValueError("Use a new evidence report path; existing observations are immutable.")
    environment, _, cargo = tool_environment(REPO)
    # Existing Rust fixtures use process ID plus a counter and retain their
    # files. A unique namespace prevents an older PID's fixture contaminating
    # this run; it does not fix that existing test-isolation weakness.
    temporary = Path(tempfile.mkdtemp(prefix="project-qualification-", dir=REPO / "artifacts/tmp"))
    environment = {**environment, "TEMP": str(temporary), "TMP": str(temporary),
                   "MYPYPATH": str(REPO / "services/core-api/src")}
    python = str(REPO / ".venv/Scripts/python.exe")
    node = str(REPO / ".local/toolchains/node-v24.19.0-win-x64/node.exe")
    pnpm = str(REPO / ".local/toolchains/corepack/v1/pnpm/11.20.0/bin/pnpm.cjs")
    desktop = REPO / "apps/desktop"
    tracked = subprocess.check_output([
        "git", "ls-files", "--", "Cargo.toml", "Cargo.lock", "apps/desktop", "packages",
        "services/core-api/src", "tools/core_api_contract.py", "tools/desktop_app_check.py",
        "tests/desktop/test_desktop_app_check.py", "tests/security/test_application_lock_source.py",
        "tests/service/test_core_api.py", "tests/service/test_project_lifecycle.py",
        "tests/service/test_provenance.py", "tests/service/fixtures/native_integration_sidecar.py",
    ], cwd=REPO, text=True, encoding="utf-8").splitlines()
    inputs = sorted({
        *tracked,
        "apps/desktop/src-tauri/examples/project_contract_probe.rs",
        "tests/service/test_native_project_contract.py",
        "artifacts/evidence/W1.A09.T02.native-check-01.mjs",
        "artifacts/evidence/W1.A09.T02.verify-01.py",
    })

    def hashes() -> dict[str, str]:
        return {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in inputs}

    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    before = hashes()
    commands = [
        ("generated-contract", REPO, [python, "tools/core_api_contract.py", "--check"]),
        ("python-lint", REPO, [python, "-m", "ruff", "check", "tools/core_api_contract.py",
                              "tools/desktop_app_check.py",
                              "tests/service/test_native_project_contract.py",
                              "tests/desktop/test_desktop_app_check.py", str(Path(__file__))]),
        ("changed-generator-types", REPO, [python, "-m", "mypy", "--follow-imports=silent",
                                          "tools/core_api_contract.py"]),
        ("native-boundaries", REPO, [str(cargo), "test", "--locked", "-p",
                                    "research-observatory-desktop", "--lib"]),
        ("native-production-lint", REPO, [str(cargo), "clippy", "--locked", "-p",
                                         "research-observatory-desktop", "--lib", "--", "-D", "warnings"]),
        ("generated-client-tests", REPO, [node, "packages/contracts/node_modules/vitest/vitest.mjs",
                                         "run", "packages/contracts/core-api/generated.test.ts"]),
        ("renderer-tests", desktop, [node, "node_modules/vitest/vitest.mjs", "run",
                                     "src/app/ProjectsWorkspace.test.tsx",
                                     "src/app/LocalServiceBoundary.test.tsx",
                                     "src/app/ApplicationRuntime.test.tsx",
                                     "src/app/ApplicationLockBoundary.test.tsx"]),
        ("renderer-lint", desktop, [node, pnpm, "run", "lint"]),
        ("renderer-types", desktop, [node, pnpm, "run", "typecheck"]),
        ("contract-types", REPO / "packages/contracts", [node, pnpm, "run", "typecheck"]),
        ("protected-source", REPO, [python, "-m", "unittest", "discover", "-s", "tests/security",
                                    "-p", "test_application_lock_source.py", "-v"]),
        ("native-generated-core", REPO, [python, "-m", "unittest", "discover", "-s", "tests/service",
                                        "-p", "test_native_project_contract.py", "-v"]),
        ("renderer-recovery-security", REPO, [python, "-m", "unittest", "discover", "-s", "tests/desktop",
                                             "-p", "test_desktop_app_check.py", "-v",
                                             "-k", "ProjectRecoveryInteractionTests",
                                             "-k", "test_neutral_workspace_measurement",
                                             "-k", "test_product_style_qualification_contract_is_exact",
                                             "-k", "test_security_boundary_and_complete_command_plan",
                                             "-k", "test_external_development_url_and_privilege_fail_closed",
                                             "-k", "test_event_capability_rejects",
                                             "-k", "test_product_bundle_rejects",
                                             "-k", "test_built_product_exposes_only_implemented"]),
    ]
    report: dict[str, object] = {
        "schemaVersion": "1.0", "taskId": "W1.A09.T02", "testedCommit": commit,
        "startedAt": datetime.now(UTC).isoformat(), "sourceHashes": before,
        "temporaryNamespace": temporary.relative_to(REPO).as_posix(), "fixturesRetained": True,
        "checks": [],
    }
    checks: list[dict[str, object]] = []
    for label, directory, command in commands:
        print(f"Starting {label}", flush=True)
        started = time.monotonic()
        result = subprocess.run(command, cwd=directory, env=environment, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=240)
        checks.append({
            "name": label, "command": command, "cwd": directory.relative_to(REPO).as_posix(),
            "exitCode": result.returncode, "durationSeconds": round(time.monotonic() - started, 3),
            "stdout": result.stdout, "stderr": result.stderr,
        })
        report["checks"] = checks
        print(f"{label}: exit {result.returncode}", flush=True)
    after_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    report["inputsUnchanged"] = hashes() == before and after_commit == commit
    report["completedAt"] = datetime.now(UTC).isoformat()
    report["ok"] = all(check["exitCode"] == 0 for check in checks) and report["inputsUnchanged"]
    with report_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"ok": report["ok"], "report": report_path.relative_to(REPO).as_posix()}), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
