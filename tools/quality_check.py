#!/usr/bin/env python3
"""Run deterministic formatting, lint, and type checks over governed Python files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from typing import Any

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
Clock = Callable[[], float]
WINDOWS_COMMAND_LIMIT = 30_000


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
        for directory, subdirectories, filenames in os.walk(absolute_root, followlinks=False):
            current = Path(directory)
            subdirectories[:] = [
                name
                for name in subdirectories
                if name != "node_modules"
                and not (current / name).is_symlink()
                and not getattr(current / name, "is_junction", lambda: False)()
            ]
            discovered.update(
                (current / name).relative_to(repo).as_posix()
                for name in filenames
                if name.endswith(".py") and (current / name).is_file()
            )
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


def _windows_command_units(argv: list[str]) -> int:
    return len(subprocess.list2cmdline(argv).encode("utf-16-le")) // 2 + 1


def _ruff_file_chunks(prefix: list[str], files: list[str]) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    for path in files:
        if _windows_command_units([*prefix, *current, path]) > WINDOWS_COMMAND_LIMIT:
            if current:
                chunks.append([*prefix, *current])
                current = []
            if _windows_command_units([*prefix, path]) > WINDOWS_COMMAND_LIMIT:
                raise ValueError("A single quality file argument exceeds the Windows command-line budget")
        current.append(path)
    if current:
        chunks.append([*prefix, *current])
    return chunks


def execute_quality(
    repo: Path,
    files: list[str],
    runner: CommandRunner = subprocess.run,
    clock: Clock = time.monotonic,
    platform_name: str | None = None,
) -> tuple[int, dict[str, Any]]:
    checks = [
        ("format", [sys.executable, "-m", "ruff", "format", "--check", "--config", "pyproject.toml", "--", *files]),
        ("lint", [sys.executable, "-m", "ruff", "check", "--config", "pyproject.toml", "--", *files]),
        (
            "types",
            [
                sys.executable,
                "-m",
                "mypy",
                "--config-file",
                "pyproject.toml",
                "--no-namespace-packages",
                "--",
                *files,
            ],
        ),
    ]
    results: list[dict[str, Any]] = []
    exit_code = 0
    effective_platform = os.name if platform_name is None else platform_name
    with ExitStack() as cleanup:
        for check_id, argv in checks:
            started = clock()
            invocations = [argv]
            transport: str | None = None
            response_metadata: dict[str, Any] | None = None
            attempted: list[dict[str, Any]] = []
            try:
                if effective_platform == "nt" and _windows_command_units(argv) > WINDOWS_COMMAND_LIMIT:
                    prefix = argv[: argv.index("--") + 1]
                    if check_id == "types":
                        if any("\r" in path or "\n" in path or path.startswith("@") for path in files):
                            raise ValueError("Quality paths cannot inject lines or response files into mypy arguments")
                        response = cleanup.enter_context(
                            tempfile.NamedTemporaryFile(
                                mode="w", encoding="utf-8", newline="\n", suffix=".args", delete_on_close=False
                            )
                        )
                        content = "\n".join(files) + "\n"
                        response.write(content)
                        response.close()
                        invocations = [[*prefix, f"@{response.name}"]]
                        if _windows_command_units(invocations[0]) > WINDOWS_COMMAND_LIMIT:
                            raise ValueError("The mypy response-file command exceeds the Windows command-line budget")
                        transport = "mypy-response-file"
                        response_metadata = {
                            "encoding": "utf-8",
                            "argumentCount": len(files),
                            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        }
                    else:
                        invocations = _ruff_file_chunks(prefix, files)
                        transport = "windows-file-chunks"
                code = 0
                stdout_parts: list[str] = []
                stderr_parts: list[str] = []
                for invocation in invocations:
                    try:
                        options: dict[str, Any] = {
                            "cwd": repo,
                            "capture_output": True,
                            "text": True,
                            "check": False,
                        }
                        if transport is not None:
                            child_environment = dict(os.environ)
                            child_environment["PYTHONIOENCODING"] = "utf-8"
                            options.update(env=child_environment, encoding="utf-8")
                        completed = runner(invocation, **options)
                        invocation_code = completed.returncode
                        invocation_stdout = completed.stdout or ""
                        invocation_stderr = completed.stderr or ""
                    except OSError as exc:
                        invocation_code, invocation_stdout, invocation_stderr = 127, "", str(exc)
                    attempted.append(
                        {
                            "argv": invocation,
                            "exitCode": invocation_code,
                            "stdout": invocation_stdout,
                            "stderr": invocation_stderr,
                        }
                    )
                    stdout_parts.append(invocation_stdout)
                    stderr_parts.append(invocation_stderr)
                    if invocation_code != 0 and code == 0:
                        code = invocation_code
                stdout, stderr = "".join(stdout_parts), "".join(stderr_parts)
            except (OSError, ValueError) as exc:
                code, stdout, stderr = 127, "", str(exc)
            duration = clock() - started
            result: dict[str, Any] = {
                "id": check_id,
                "argv": argv,
                "status": "PASS" if code == 0 else "FAIL",
                "exitCode": code,
                "durationSeconds": round(duration, 3),
                "stdout": stdout,
                "stderr": stderr,
            }
            if transport is not None:
                result.update(
                    argvRole="logical-whole-scope",
                    transport=transport,
                    invocations=attempted,
                    stdioEncoding="utf-8",
                    childEnvironmentOverrides={"PYTHONIOENCODING": "utf-8"},
                )
                if response_metadata is not None:
                    result["responseFile"] = response_metadata
            results.append(result)
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
