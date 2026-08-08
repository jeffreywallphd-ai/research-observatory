from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from packaging_smoke_check import execute_packaging_smoke, static_errors  # noqa: E402


class PackagingSmokeCheckTests(unittest.TestCase):
    def test_locked_repository_inputs_pass_with_valid_cargo_metadata(self) -> None:
        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, '{"workspace_members": []}', "")

        exit_code, report = execute_packaging_smoke(REPO, runner=runner)

        self.assertEqual(0, exit_code)
        self.assertEqual("PASS", report["status"])
        self.assertIn("installer production and signing remain deferred", report["scope"])

    def test_missing_signing_boundary_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            for relative in ["Cargo.toml", "Cargo.lock", "pnpm-lock.yaml", "pyproject.toml", "uv.lock"]:
                (repo / relative).write_text("placeholder\n", encoding="utf-8")
            (repo / "package.json").write_text(
                '{"private": true, "packageManager": "pnpm@11.20.0"}\n', encoding="utf-8"
            )
            readme = repo / "packaging/windows/README.md"
            readme.parent.mkdir(parents=True)
            readme.write_text("Boundary: source inputs only.\n", encoding="utf-8")

            errors = static_errors(repo)

            self.assertTrue(any("signing" in error for error in errors))

    def test_cargo_metadata_failure_is_reported(self) -> None:
        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 12, "", "lockfile drift")

        exit_code, report = execute_packaging_smoke(REPO, runner=runner)

        self.assertEqual(1, exit_code)
        self.assertTrue(any("lockfile drift" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
