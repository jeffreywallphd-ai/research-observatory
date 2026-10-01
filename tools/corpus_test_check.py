#!/usr/bin/env python3
"""Run the complete corpus suite against this checkout's Core source."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main(repo: Path | None = None) -> int:
    repo = repo if repo is not None else Path(__file__).resolve().parents[1]
    core_source = repo / "services" / "core-api" / "src"
    corpus_tests = repo / "tests" / "corpus"
    if not core_source.is_dir() or not any(corpus_tests.glob("test_*.py")):
        print("ERROR: Core source or corpus test modules are unavailable", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(core_source), str(repo)))
    command = [
        sys.executable,
        "-B",
        "-s",
        "-m",
        "unittest",
        "discover",
        "-v",
        "-s",
        "tests/corpus",
        "-p",
        "test_*.py",
    ]
    return subprocess.run(command, cwd=repo, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
