#!/usr/bin/env python3
"""Run portable report-model and protected persistence checks against Core source."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main(repo: Path | None = None) -> int:
    repo = repo if repo is not None else Path(__file__).resolve().parents[1]
    source = repo / "services" / "core-api" / "src"
    suites = (repo / "tests" / "corpus_reports", repo / "tests" / "reports")
    if not source.is_dir() or any(not suite.is_dir() or not any(suite.glob("test_*.py")) for suite in suites):
        print("ERROR: Core source or corpus report tests are unavailable", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(source), str(repo)))
    command = [sys.executable, "-B", "-s", "-m", "unittest", "discover", "-v"]
    for suite in suites:
        discovered = subprocess.run(
            [*command, "-s", str(suite), "-p", "test_*.py"],
            cwd=repo,
            env=env,
            check=False,
        )
        if discovered.returncode != 0:
            return discovered.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
