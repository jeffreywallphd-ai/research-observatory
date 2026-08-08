#!/usr/bin/env python3
"""Run dependency-light bootstrap verification profiles."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def foundation_commands(repo: Path) -> list[list[str]]:
    python = sys.executable
    return [
        [python, "tools/repository_structure_check.py", "--repo", str(repo)],
        [python, "tools/runtime_check.py", "--repo", str(repo)],
        [python, "tools/architecture_check.py", "--repo", str(repo)],
        [python, "tools/agent_protocol_check.py", "--repo", str(repo)],
        [python, "-m", "unittest", "discover", "-s", "tests/foundation", "-p", "test_*.py"],
        [python, "tools/taskctl.py", "--file", "planning/backlog.yaml", "validate"],
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()

    if args.profile != "foundation":
        print(
            f"ERROR: profile {args.profile!r} is not available in the bootstrap runner; "
            "CAP-00.S03.T01 installs the complete governed profile set.",
            file=sys.stderr,
        )
        return 2

    started = time.monotonic()
    for command in foundation_commands(repo):
        command_started = time.monotonic()
        printable = subprocess.list2cmdline(command)
        print(f"RUN {printable}", flush=True)
        result = subprocess.run(command, cwd=repo, check=False)
        duration = time.monotonic() - command_started
        if result.returncode != 0:
            print(f"FAIL ({duration:.2f}s, exit {result.returncode}): {printable}", file=sys.stderr)
            return result.returncode
        print(f"PASS ({duration:.2f}s): {printable}")

    print(f"Verification profile foundation: pass ({time.monotonic() - started:.2f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
