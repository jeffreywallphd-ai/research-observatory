from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from bootstrap import BootstrapError, bootstrap  # noqa: E402

DECLARATION_FILES = [
    ".node-version",
    ".nvmrc",
    ".python-version",
    "Cargo.lock",
    "package.json",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "runtime-versions.json",
    "rust-toolchain.toml",
    "uv.lock",
]


class ControlledRunner:
    def __init__(self, failing_step: str | None = None) -> None:
        self.failing_step = failing_step
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if "--version" in command:
            version_output = {
                "node": "v24.19.0",
                "python": "Python 3.14.6",
                "rustc": "rustc 1.96.1",
                "corepack.cmd": "11.20.0",
                "corepack": "11.20.0",
                "uv": "uv 0.12.2",
            }
            return subprocess.CompletedProcess(command, 0, version_output[command[0]], "")
        if self.failing_step and self.failing_step in command:
            return subprocess.CompletedProcess(command, 19, "", "controlled install failure")
        return subprocess.CompletedProcess(command, 0, "", "")


def seed_checkout(destination: Path) -> None:
    for relative in DECLARATION_FILES:
        source = REPO / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


class DeveloperBootstrapTests(unittest.TestCase):
    def test_clean_windows_checkout_runs_frozen_steps_and_writes_only_documented_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            seed_checkout(checkout)
            files_before = {path.relative_to(checkout) for path in checkout.rglob("*") if path.is_file()}
            runner = ControlledRunner()

            config_path = bootstrap(checkout, runner=runner, platform_name="nt")

            files_after = {path.relative_to(checkout) for path in checkout.rglob("*") if path.is_file()}
            self.assertEqual({Path(".local/development.json")}, files_after - files_before)
            self.assertEqual(checkout / ".local" / "development.json", config_path)
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual("LOC", config["profile"])
            self.assertFalse(config["containsSecrets"])
            self.assertIn(["corepack.cmd", "pnpm", "install", "--frozen-lockfile"], runner.commands)
            self.assertIn(["uv", "sync", "--frozen", "--no-install-project"], runner.commands)
            self.assertIn(["cargo", "fetch", "--locked"], runner.commands)
            self.assertTrue(any(command[0].endswith(".venv\\Scripts\\python.exe") for command in runner.commands))

    def test_failed_install_does_not_publish_development_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            seed_checkout(checkout)
            runner = ControlledRunner(failing_step="fetch")

            with self.assertRaisesRegex(BootstrapError, "(?s)Rust dependencies failed.*controlled install failure"):
                bootstrap(checkout, runner=runner, platform_name="nt")

            self.assertFalse((checkout / ".local" / "development.json").exists())


if __name__ == "__main__":
    unittest.main()
