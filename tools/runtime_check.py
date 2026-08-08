#!/usr/bin/env python3
"""Validate pinned runtime declarations and, optionally, installed tools."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

VERSION_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)")


def load_contract(repo: Path) -> dict[str, Any]:
    return json.loads((repo / "runtime-versions.json").read_text(encoding="utf-8"))


def declaration_errors(repo: Path, contract: dict[str, Any]) -> list[str]:
    runtimes = contract["runtimes"]
    managers = contract["package_managers"]
    node = runtimes["node"]["version"]
    python = runtimes["python"]["version"]
    rust = runtimes["rust"]["version"]
    pnpm = managers["pnpm"]["version"]
    errors: list[str] = []

    expected_text = {
        ".node-version": node,
        ".nvmrc": node,
        ".python-version": python,
    }
    for relative, expected in expected_text.items():
        actual = (repo / relative).read_text(encoding="utf-8").strip()
        if actual != expected:
            errors.append(f"{relative} declares {actual!r}; expected {expected!r}")

    package = json.loads((repo / "package.json").read_text(encoding="utf-8"))
    if package.get("packageManager") != f"pnpm@{pnpm}":
        errors.append("package.json packageManager does not match runtime-versions.json")
    if package.get("engines", {}).get("pnpm") != pnpm:
        errors.append("package.json pnpm engine does not match runtime-versions.json")

    rust_toolchain = (repo / "rust-toolchain.toml").read_text(encoding="utf-8")
    if f'channel = "{rust}"' not in rust_toolchain:
        errors.append("rust-toolchain.toml does not match runtime-versions.json")

    pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    if 'requires-python = ">=3.14,<3.15"' not in pyproject:
        errors.append("pyproject.toml must constrain Python to the pinned 3.14 series")

    required_lockfiles = ["pnpm-lock.yaml", "uv.lock", "Cargo.lock"]
    for relative in required_lockfiles:
        if not (repo / relative).is_file():
            errors.append(f"Missing deterministic lockfile: {relative}")
    return errors


def extract_version(output: str) -> str | None:
    match = VERSION_PATTERN.search(output)
    return match.group(1) if match else None


def installed_errors(
    contract: dict[str, Any],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    platform_name: str | None = None,
) -> list[str]:
    errors: list[str] = []
    effective_platform = os.name if platform_name is None else platform_name
    tools = {**contract["runtimes"], **contract["package_managers"]}
    for name, specification in tools.items():
        command = specification["command"]
        if effective_platform == "nt" and command[0] == "corepack":
            command = ["corepack.cmd", *command[1:]]
        expected = specification["version"]
        try:
            result = runner(command, capture_output=True, text=True, check=False)
        except OSError:
            result = subprocess.CompletedProcess(command, 127, "", "command not found")
        output = f"{result.stdout}\n{result.stderr}".strip()
        actual = extract_version(output)
        if result.returncode != 0 or actual is None:
            errors.append(f"{name} is unavailable. {specification['install_hint']}")
        elif actual != expected:
            errors.append(f"{name} {actual} is unsupported; expected {expected}. {specification['install_hint']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--check-installed", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    contract = load_contract(repo)
    errors = declaration_errors(repo, contract)
    if args.check_installed:
        errors.extend(installed_errors(contract))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    mode = "declarations and installed tools" if args.check_installed else "declarations"
    print(f"Runtime contract: pass - {mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
