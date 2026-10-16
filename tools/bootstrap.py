#!/usr/bin/env python3
"""Prepare a deterministic local development checkout and run its smoke gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from runtime_check import declaration_errors, installed_errors, load_contract

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


SMOKE_REPORT = "artifacts/tmp/bootstrap-smoke-report.json"


class BootstrapError(RuntimeError):
    """A prerequisite, install, or smoke gate failed."""


def local_python(repo: Path, platform_name: str) -> Path:
    if platform_name == "nt":
        return repo / ".venv" / "Scripts" / "python.exe"
    return repo / ".venv" / "bin" / "python"


def bootstrap_commands(repo: Path, platform_name: str) -> list[tuple[str, list[str]]]:
    corepack = "corepack.cmd" if platform_name == "nt" else "corepack"
    python = str(local_python(repo, platform_name))
    return [
        ("Node dependencies", [corepack, "pnpm", "install", "--frozen-lockfile"]),
        ("Python environment", ["uv", "sync", "--frozen", "--no-install-project"]),
        ("Security scanner", [python, "tools/install_trivy.py", "--repo", str(repo)]),
        ("Rust dependencies", ["cargo", "fetch", "--locked"]),
        (
            "Python dependency smoke",
            [
                python,
                "-B",
                "-s",
                "-u",
                "-c",
                "import fastapi, nacl.bindings, pydantic, yaml; "
                "from sqlcipher3 import dbapi2; connection=dbapi2.connect(':memory:'); "
                "version=connection.execute('PRAGMA cipher_version').fetchone(); connection.close(); "
                "assert version and version[0], 'SQLCipher backend unavailable'; "
                "print('Python dependency smoke: PASS (FastAPI, Pydantic, PyNaCl, YAML, SQLCipher)')",
            ],
        ),
        (
            "Desktop dependency smoke",
            [corepack, "pnpm", "--dir", "apps/desktop", "exec", "vite", "--version"],
        ),
        (
            "Locked workspace smoke",
            [python, "-B", "-s", "-u", "tools/packaging_smoke_check.py", "--repo", str(repo), "--report", SMOKE_REPORT],
        ),
    ]


def run_step(repo: Path, label: str, command: list[str], runner: CommandRunner) -> None:
    print(f"BOOTSTRAP: {label} - {subprocess.list2cmdline(command)}", flush=True)
    started = time.monotonic()
    try:
        # Inherit both streams so package-manager and smoke progress is visible immediately.
        result = runner(command, cwd=repo, text=True, check=False)
    except OSError as exc:
        raise BootstrapError(f"{label} could not start: {exc}") from exc
    duration = time.monotonic() - started
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"BOOTSTRAP: {label} - {status} ({duration:.2f}s)", flush=True)
    if result.returncode == 0:
        return
    details = "\n".join(
        f"{name}:\n{output.strip()}"
        for name, output in (("stdout", result.stdout), ("stderr", result.stderr))
        if output and output.strip()
    )
    if label == "Locked workspace smoke":
        report_note = f"Workspace smoke report path: {SMOKE_REPORT}"
        details = f"{details}\n{report_note}" if details else report_note
    suffix = f"\n{details}" if details else "\nSee the live command output above."
    raise BootstrapError(f"{label} failed with exit code {result.returncode} after {duration:.2f}s.{suffix}")


def development_config(repo: Path, contract: dict[str, object]) -> dict[str, object]:
    contract_bytes = (repo / "runtime-versions.json").read_bytes()
    return {
        "schemaVersion": "1.0",
        "profile": "LOC",
        "repositoryRoot": str(repo),
        "pythonEnvironment": ".venv",
        "runtimeContract": "runtime-versions.json",
        "runtimeContractSha256": hashlib.sha256(contract_bytes).hexdigest(),
        "runtimes": contract["runtimes"],
        "packageManagers": contract["package_managers"],
        "containsSecrets": False,
    }


def write_development_config(repo: Path, contract: dict[str, object]) -> Path:
    config_path = repo / ".local" / "development.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_path.with_suffix(".json.tmp")
    serialized = json.dumps(development_config(repo, contract), indent=2) + "\n"
    temporary.write_text(serialized, encoding="utf-8", newline="\n")
    temporary.replace(config_path)
    return config_path


def bootstrap(
    repo: Path,
    runner: CommandRunner = subprocess.run,
    platform_name: str = os.name,
) -> Path:
    repo = repo.resolve()
    contract = load_contract(repo)
    errors = declaration_errors(repo, contract)
    errors.extend(installed_errors(contract, runner=runner, platform_name=platform_name))
    if errors:
        raise BootstrapError("Prerequisite validation failed:\n- " + "\n- ".join(errors))

    for label, command in bootstrap_commands(repo, platform_name):
        run_step(repo, label, command, runner)
    return write_development_config(repo, contract)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    try:
        config_path = bootstrap(Path(args.repo))
    except (BootstrapError, KeyError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Bootstrap complete. Local configuration: {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
