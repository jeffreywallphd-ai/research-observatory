#!/usr/bin/env python3
"""Validate locked packaging inputs without producing or signing an installer."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
Clock = Callable[[], float]
FORBIDDEN_SUFFIXES = {".dll", ".exe", ".msi", ".msix", ".pdb", ".sig"}


def static_errors(repo: Path) -> list[str]:
    errors: list[str] = []
    required = ["Cargo.toml", "Cargo.lock", "package.json", "pnpm-lock.yaml", "pyproject.toml", "uv.lock"]
    for relative in required:
        path = repo / relative
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing or empty packaging input: {relative}")
    try:
        package = json.loads((repo / "package.json").read_text(encoding="utf-8"))
        if package.get("private") is not True:
            errors.append("package.json must remain private")
        if package.get("packageManager") != "pnpm@11.20.0":
            errors.append("package.json must use the pinned pnpm@11.20.0")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read package.json: {exc}")
    try:
        windows_readme = (repo / "packaging/windows/README.md").read_text(encoding="utf-8")
        required_text = ["Boundary:", "Generated installers", "signing", "must never be committed"]
        for fragment in required_text:
            if fragment not in windows_readme:
                errors.append(f"Windows packaging boundary is missing {fragment!r}")
    except OSError as exc:
        errors.append(f"cannot read Windows packaging boundary: {exc}")
    packaging_root = repo / "packaging/windows"
    if packaging_root.is_dir():
        for path in packaging_root.rglob("*"):
            if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
                errors.append(f"generated or signing output is forbidden in source packaging: {path.relative_to(repo)}")
    return errors


def cargo_executable(repo: Path) -> str:
    local = repo / ".local" / "toolchains" / "cargo" / "bin" / "cargo.exe"
    return str(local) if local.is_file() else "cargo"


def execute_packaging_smoke(
    repo: Path,
    runner: CommandRunner = subprocess.run,
    clock: Clock = time.monotonic,
) -> tuple[int, dict[str, Any]]:
    errors = static_errors(repo)
    started = clock()
    argv = [cargo_executable(repo), "metadata", "--locked", "--no-deps", "--format-version", "1"]
    try:
        completed = runner(argv, cwd=repo, capture_output=True, text=True, check=False)
        command_error = completed.stderr.strip() if completed.returncode else ""
        if completed.returncode == 0:
            try:
                metadata = json.loads(completed.stdout)
                if not isinstance(metadata.get("workspace_members"), list):
                    errors.append("cargo metadata did not return workspace_members")
            except json.JSONDecodeError as exc:
                errors.append(f"cargo metadata returned invalid JSON: {exc}")
        else:
            errors.append(f"cargo metadata --locked failed: {command_error or completed.stdout.strip()}")
        command_exit = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except OSError as exc:
        command_exit, stdout, stderr = 127, "", str(exc)
        errors.append(f"cargo metadata is unavailable: {exc}")
    duration = clock() - started
    status = "PASS" if not errors else "FAIL"
    report = {
        "schemaVersion": "1.0",
        "documentType": "packaging-smoke-report",
        "status": status,
        "scope": "locked source inputs only; installer production and signing remain deferred",
        "errors": errors,
        "command": {
            "argv": argv,
            "exitCode": command_exit,
            "durationSeconds": round(duration, 3),
            "stdout": stdout,
            "stderr": stderr,
        },
    }
    return (0 if not errors else 1), report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    exit_code, report = execute_packaging_smoke(repo)
    if args.report:
        destination = args.report if args.report.is_absolute() else repo / args.report
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    for error in report["errors"]:
        print(f"ERROR: {error}")
    print(f"Packaging smoke: {report['status']} - locked source inputs")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
