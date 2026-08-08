#!/usr/bin/env python3
"""Run deterministic formatting, lint, and type checks over governed Python files."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
Clock = Callable[[], float]


def load_scope(repo: Path) -> list[str]:
    contract = json.loads((repo / "quality-scope.json").read_text(encoding="utf-8"))
    if contract.get("schemaVersion") != "1.0" or contract.get("documentType") != "python-quality-scope":
        raise ValueError("quality-scope.json must be a python-quality-scope with schemaVersion 1.0")
    files = contract.get("pythonFiles")
    if not isinstance(files, list) or not files or not all(isinstance(item, str) for item in files):
        raise ValueError("quality-scope.json pythonFiles must be a non-empty string array")
    if len(files) != len(set(files)):
        raise ValueError("quality-scope.json pythonFiles must be unique")
    roots = contract.get("governedRoots")
    if not isinstance(roots, list) or not roots or not all(isinstance(item, str) for item in roots):
        raise ValueError("quality-scope.json governedRoots must be a non-empty string array")
    discovered: set[str] = set()
    for relative_root in roots:
        root_path = PurePosixPath(relative_root)
        if root_path.is_absolute() or ".." in root_path.parts or "." in root_path.parts:
            raise ValueError(f"unsafe governed root: {relative_root}")
        absolute_root = repo.joinpath(*root_path.parts)
        if not absolute_root.is_dir():
            raise ValueError(f"governed root does not exist: {relative_root}")
        discovered.update(path.relative_to(repo).as_posix() for path in absolute_root.rglob("*.py") if path.is_file())
    for relative in files:
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
            raise ValueError(f"unsafe or non-Python quality path: {relative}")
        if not (repo / relative).is_file():
            raise ValueError(f"quality path does not exist: {relative}")
    declared = set(files)
    unlisted = sorted(discovered - declared)
    stale = sorted(declared - discovered)
    if unlisted:
        raise ValueError(f"governed Python files are unlisted: {', '.join(unlisted)}")
    if stale:
        raise ValueError(f"declared Python files are outside governed roots: {', '.join(stale)}")
    return sorted(files)


def execute_quality(
    repo: Path,
    files: list[str],
    runner: CommandRunner = subprocess.run,
    clock: Clock = time.monotonic,
) -> tuple[int, dict[str, Any]]:
    checks = [
        ("format", [sys.executable, "-m", "ruff", "format", "--check", "--config", "pyproject.toml", "--", *files]),
        ("lint", [sys.executable, "-m", "ruff", "check", "--config", "pyproject.toml", "--", *files]),
        ("types", [sys.executable, "-m", "mypy", "--config-file", "pyproject.toml", "--", *files]),
    ]
    results: list[dict[str, Any]] = []
    exit_code = 0
    for check_id, argv in checks:
        started = clock()
        try:
            completed = runner(argv, cwd=repo, capture_output=True, text=True, check=False)
            code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except OSError as exc:
            code, stdout, stderr = 127, "", str(exc)
        duration = clock() - started
        results.append(
            {
                "id": check_id,
                "argv": argv,
                "status": "PASS" if code == 0 else "FAIL",
                "exitCode": code,
                "durationSeconds": round(duration, 3),
                "stdout": stdout,
                "stderr": stderr,
            }
        )
        if stdout:
            print(stdout, end="" if stdout.endswith("\n") else "\n")
        if stderr:
            print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
        if code != 0 and exit_code == 0:
            exit_code = code if code > 0 else 1
    return exit_code, {
        "schemaVersion": "1.0",
        "documentType": "python-quality-report",
        "status": "PASS" if exit_code == 0 else "FAIL",
        "files": files,
        "checks": results,
    }


def write_report(repo: Path, report_path: Path | None, report: dict[str, Any]) -> None:
    if report_path is None:
        return
    destination = report_path if report_path.is_absolute() else repo / report_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    try:
        files = load_scope(repo)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "schemaVersion": "1.0",
            "documentType": "python-quality-report",
            "status": "FAIL",
            "failureCause": str(exc),
            "files": [],
            "checks": [],
        }
        print(f"ERROR: {exc}", file=sys.stderr)
        write_report(repo, args.report, report)
        return 2
    exit_code, report = execute_quality(repo, files)
    write_report(repo, args.report, report)
    print(f"Python quality: {report['status']} - {len(files)} governed files")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
