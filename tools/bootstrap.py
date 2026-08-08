#!/usr/bin/env python3
"""Prepare a deterministic local development checkout and run its smoke gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from runtime_check import declaration_errors, installed_errors, load_contract

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


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
        ("Foundation smoke gate", [python, "tools/verify.py", "--profile", "foundation"]),
    ]


def run_step(repo: Path, label: str, command: list[str], runner: CommandRunner) -> None:
    print(f"BOOTSTRAP: {label} - {subprocess.list2cmdline(command)}", flush=True)
    try:
        result = runner(command, cwd=repo, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise BootstrapError(f"{label} could not start: {exc}") from exc
    if result.returncode == 0:
        return
    details = (result.stderr or result.stdout).strip()
    suffix = f"\n{details}" if details else ""
    raise BootstrapError(f"{label} failed with exit code {result.returncode}.{suffix}")


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
