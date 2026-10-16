from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from bootstrap import BootstrapError, bootstrap, bootstrap_commands  # noqa: E402

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
    "security-toolchain.json",
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
    def test_default_setup_selects_only_dependency_and_workspace_smoke(self) -> None:
        commands = bootstrap_commands(Path("checkout"), "nt")
        self.assertEqual(7, len(commands))
        flattened = [argument for _, command in commands for argument in command]
        for broad in ("tools/verify.py", "foundation", "discover", "tools/benchmark_registry.py", "tools/taskctl.py"):
            self.assertNotIn(broad, flattened)
        self.assertEqual("Python dependency smoke", commands[4][0])
        self.assertEqual("Desktop dependency smoke", commands[5][0])
        self.assertEqual(["corepack.cmd", "pnpm", "--dir", "apps/desktop", "exec", "vite", "--version"], commands[5][1])
        self.assertEqual("Locked workspace smoke", commands[6][0])
        self.assertIn("tools/packaging_smoke_check.py", commands[6][1])

    def test_real_step_streams_progress_before_child_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            released = checkout / "progress-observed"
            child = (
                "from pathlib import Path; import sys,time; print('LIVE-SMOKE-PROGRESS',flush=True); "
                "deadline=time.monotonic()+4; "
                "\nwhile not Path(sys.argv[1]).exists() and time.monotonic()<deadline: time.sleep(.01)"
                "\nsys.exit(0 if Path(sys.argv[1]).exists() else 41)"
            )
            harness = (
                f"import sys; from pathlib import Path; sys.path.insert(0,{str(REPO / 'tools')!r}); "
                "from bootstrap import run_step; import subprocess; "
                f"run_step(Path({str(checkout)!r}), 'Progress smoke', "
                f"[sys.executable,'-B','-s','-u','-c',{child!r},{str(released)!r}],subprocess.run)"
            )
            with subprocess.Popen(
                [sys.executable, "-B", "-s", "-u", "-c", harness],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ) as process:
                assert process.stdout is not None
                lines = []
                for line in process.stdout:
                    lines.append(line)
                    if line.strip() == "LIVE-SMOKE-PROGRESS":
                        released.touch()
                        break
                remaining, errors = process.communicate(timeout=10)
                output = "".join(lines) + remaining + errors
                self.assertTrue(released.exists(), output)
                self.assertEqual(0, process.returncode, output)

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
            self.assertTrue(any("tools/install_trivy.py" in command for command in runner.commands))
            self.assertTrue(any(command[0].endswith(".venv\\Scripts\\python.exe") for command in runner.commands))

    def test_real_failed_step_preserves_stdout_and_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            child = (
                "import sys; print('actual check failure'); "
                "print('broad profile advisory', file=sys.stderr); sys.exit(23)"
            )
            harness = (
                f"import sys; from pathlib import Path; sys.path.insert(0,{str(REPO / 'tools')!r}); "
                "from bootstrap import run_step; import subprocess; "
                f"run_step(Path({str(checkout)!r}), 'Controlled diagnostic', "
                f"[sys.executable,'-B','-s','-c',{child!r}],subprocess.run)"
            )
            result = subprocess.run(
                [sys.executable, "-B", "-s", "-c", harness],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Controlled diagnostic failed with exit code 23", result.stderr)
            self.assertIn("actual check failure", result.stdout)
            self.assertIn("broad profile advisory", result.stderr)
            self.assertIn("BOOTSTRAP: Controlled diagnostic - FAIL (", result.stdout)

    def test_failed_workspace_smoke_requests_report_and_does_not_publish_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            seed_checkout(checkout)
            runner = ControlledRunner(failing_step="tools/packaging_smoke_check.py")

            with self.assertRaises(BootstrapError) as failure:
                bootstrap(checkout, runner=runner, platform_name="nt")

            self.assertIn("Locked workspace smoke failed with exit code 19", str(failure.exception))
            self.assertIn(
                "Workspace smoke report path: artifacts/tmp/bootstrap-smoke-report.json",
                str(failure.exception),
            )
            self.assertEqual(
                [
                    str(checkout / ".venv" / "Scripts" / "python.exe"),
                    "-B",
                    "-s",
                    "-u",
                    "tools/packaging_smoke_check.py",
                    "--repo",
                    str(checkout),
                    "--report",
                    "artifacts/tmp/bootstrap-smoke-report.json",
                ],
                runner.commands[-1],
            )
            self.assertFalse((checkout / ".local" / "development.json").exists())

    def test_failed_install_does_not_publish_development_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            seed_checkout(checkout)
            runner = ControlledRunner(failing_step="fetch")

            with self.assertRaisesRegex(BootstrapError, "(?s)Rust dependencies failed.*controlled install failure"):
                bootstrap(checkout, runner=runner, platform_name="nt")

            self.assertFalse((checkout / ".local" / "development.json").exists())


@unittest.skipUnless(os.name == "nt", "Windows CMD and PowerShell entrypoints")
class WindowsSetupEntrypointTests(unittest.TestCase):
    def seed_setup(self, checkout: Path, *, contract: bool = True) -> None:
        checkout.mkdir(parents=True)
        for relative in ("setup.cmd", "setup-pinned-runtimes.cmd", "tools/setup-pinned-runtimes.ps1"):
            target = checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, target)
        if contract:
            for relative in ("runtime-versions.json", ".node-version", ".python-version", "package.json"):
                shutil.copy2(REPO / relative, checkout / relative)
            (checkout / "tools/bootstrap.py").write_text("# Not executed by plan-only checks.\n", encoding="utf-8")
            (checkout / "bootstrap.cmd").write_text(
                '@echo off\n> "%~dp0bootstrap-ran.txt" echo unexpected\nexit /b 91\n', encoding="utf-8"
            )

    def invoke_setup(self, checkout: Path, caller: Path, arguments: str) -> subprocess.CompletedProcess[str]:
        windows = Path(os.environ["SYSTEMROOT"])
        environment = dict(os.environ)
        environment["PATH"] = os.pathsep.join(
            (str(windows / "System32"), str(windows / "System32/WindowsPowerShell/v1.0"))
        )
        return subprocess.run(
            f'"{windows / "System32/cmd.exe"}" /d /c call "{checkout / "setup.cmd"}" {arguments}',
            cwd=caller,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def test_wrapper_uses_own_root_forwards_arguments_and_preserves_failure_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            checkout = parent / "fork with spaces"
            self.seed_setup(checkout)
            (checkout / "setup-pinned-runtimes.cmd").write_text(
                '@echo off\n> "%~dp0received-args.txt" echo %*\nexit /b 37\n', encoding="utf-8"
            )

            result = self.invoke_setup(checkout, parent, '-PlanOnly "argument with spaces"')

            self.assertEqual(37, result.returncode, result.stdout + result.stderr)
            arguments = (checkout / "received-args.txt").read_text(encoding="utf-8")
            self.assertIn(f'-RepoRoot "{checkout}\\." -RunBootstrap', arguments)
            self.assertIn('-PlanOnly "argument with spaces"', arguments)

    def test_real_plan_only_from_unrelated_directory_does_not_install_or_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            checkout = parent / "fork with spaces"
            self.seed_setup(checkout)
            before = {path.relative_to(checkout): path.read_bytes() for path in checkout.rglob("*") if path.is_file()}

            result = self.invoke_setup(checkout, parent, "-PlanOnly")

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("PLAN ONLY", result.stdout)
            self.assertIn("Node 24.19.0", result.stdout)
            self.assertIn("Python 3.14.6", result.stdout)
            self.assertIn("pnpm 11.20.0", result.stdout)
            after = {path.relative_to(checkout): path.read_bytes() for path in checkout.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertFalse((checkout / ".local").exists())
            self.assertFalse((checkout / ".venv").exists())
            self.assertFalse((checkout / "bootstrap-ran.txt").exists())

    def test_nonproject_root_fails_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            checkout = parent / "not a project"
            self.seed_setup(checkout, contract=False)
            before = {path.relative_to(checkout) for path in checkout.rglob("*")}

            result = self.invoke_setup(checkout, parent, "-PlanOnly")

            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("missing runtime-versions.json", result.stderr)
            self.assertEqual(before, {path.relative_to(checkout) for path in checkout.rglob("*")})

    def test_changed_runtime_contract_fails_before_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            checkout = parent / "fork with spaces"
            self.seed_setup(checkout)
            declaration = checkout / "runtime-versions.json"
            contract = json.loads(declaration.read_text(encoding="utf-8"))
            contract["runtimes"]["node"]["version"] = "20.20.1"
            declaration.write_text(json.dumps(contract), encoding="utf-8")
            before = {path.relative_to(checkout): path.read_bytes() for path in checkout.rglob("*") if path.is_file()}

            result = self.invoke_setup(checkout, parent, "-PlanOnly")

            self.assertEqual(1, result.returncode, result.stdout + result.stderr)
            self.assertIn("supports only the reviewed", result.stderr)
            after = {path.relative_to(checkout): path.read_bytes() for path in checkout.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertFalse((checkout / ".local").exists())
            self.assertFalse((checkout / ".venv").exists())


if __name__ == "__main__":
    unittest.main()
