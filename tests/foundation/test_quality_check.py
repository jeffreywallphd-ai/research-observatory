from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from quality_check import execute_quality, load_scope  # noqa: E402


class PythonQualityCheckTests(unittest.TestCase):
    def test_quality_scope_is_explicit_and_valid(self) -> None:
        files = load_scope(REPO)

        self.assertIn("tools/quality_check.py", files)
        self.assertEqual(len(files), len(set(files)))

    def test_expected_checks_report_success(self) -> None:
        seen: list[list[str]] = []

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            seen.append(command)
            return subprocess.CompletedProcess(command, 0, "ok", "")

        exit_code, report = execute_quality(REPO, ["tools/quality_check.py"], runner=runner)

        self.assertEqual(0, exit_code)
        self.assertEqual("PASS", report["status"])
        self.assertEqual(["format", "lint", "types"], [item["id"] for item in report["checks"]])
        self.assertEqual(3, len(seen))

    def test_lint_failure_is_retained_while_other_checks_continue(self) -> None:
        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            code = 9 if "check" in command else 0
            return subprocess.CompletedProcess(command, code, "", "unsafe boundary" if code else "")

        exit_code, report = execute_quality(REPO, ["tools/quality_check.py"], runner=runner)

        self.assertEqual(9, exit_code)
        self.assertEqual("FAIL", report["status"])
        self.assertEqual(3, len(report["checks"]))
        self.assertEqual("unsafe boundary", report["checks"][1]["stderr"])


if __name__ == "__main__":
    unittest.main()
