from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import quality_check  # noqa: E402
from quality_check import execute_quality, load_scope  # noqa: E402


class PythonQualityCheckTests(unittest.TestCase):
    def test_quality_scope_is_explicit_and_valid(self) -> None:
        files = load_scope(REPO)

        self.assertIn("tools/quality_check.py", files)
        self.assertEqual(len(files), len(set(files)))

    def test_unlisted_file_in_governed_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            tools = repo / "tools"
            tools.mkdir()
            (tools / "listed.py").write_text("pass\n", encoding="utf-8")
            (tools / "unlisted.py").write_text("pass\n", encoding="utf-8")
            (repo / "quality-scope.json").write_text(
                '{"schemaVersion":"1.0","documentType":"python-quality-scope",'
                '"governedRoots":["tools"],"pythonFiles":["tools/listed.py"]}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "governed Python files are unlisted: tools/unlisted.py"):
                load_scope(repo)

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

    def test_windows_large_scope_is_complete_in_chunks_and_one_mypy_context(self) -> None:
        files = [f"tools/space caf\u00e9 \U0001f600/{'segment ' * 8}/module{index}.py" for index in range(734)]
        seen: dict[str, list[str]] = {"format": [], "lint": [], "types": []}
        response_paths: list[Path] = []

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            units = len(subprocess.list2cmdline(command).encode("utf-16-le")) // 2 + 1
            self.assertLessEqual(units, 30_000)
            arguments = command[command.index("--") + 1 :]
            if "mypy" in command:
                self.assertEqual(1, len(arguments))
                self.assertTrue(arguments[0].startswith("@"))
                response = Path(arguments[0][1:])
                response_paths.append(response)
                seen["types"] = response.read_text(encoding="utf-8").splitlines()
            else:
                seen["format" if "format" in command else "lint"].extend(arguments)
            return subprocess.CompletedProcess(command, 0, "complete output\n", "")

        exit_code, report = execute_quality(REPO, files, runner=runner, platform_name="nt")

        self.assertEqual(0, exit_code)
        self.assertEqual(["format", "lint", "types"], [row["id"] for row in report["checks"]])
        for observed in seen.values():
            self.assertEqual(files, observed)
        self.assertEqual(1, len(response_paths))
        self.assertFalse(response_paths[0].exists())
        for row in report["checks"]:
            self.assertEqual("logical-whole-scope", row["argvRole"])
            self.assertEqual(row["stdout"], "".join(item["stdout"] for item in row["invocations"]))
        self.assertGreater(len(report["checks"][0]["invocations"]), 1)
        self.assertEqual(1, len(report["checks"][2]["invocations"]))
        self.assertEqual(734, report["checks"][2]["responseFile"]["argumentCount"])

    def test_windows_chunk_errors_preserve_outputs_and_continue_complete_scope(self) -> None:
        files = [f"tools/{'long_segment/' * 10}module{index}.py" for index in range(734)]
        seen: dict[str, list[str]] = {"format": [], "lint": [], "types": []}
        attempts: dict[str, int] = {"format": 0, "lint": 0, "types": 0}

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            check = "types" if "mypy" in command else "format" if "format" in command else "lint"
            attempts[check] += 1
            arguments = command[command.index("--") + 1 :]
            if check == "types":
                seen[check] = Path(arguments[0][1:]).read_text(encoding="utf-8").splitlines()
            else:
                seen[check].extend(arguments)
            if check == "format" and attempts[check] == 1:
                raise OSError("controlled first chunk launch failure")
            code = 9 if check == "lint" and attempts[check] == 1 else 0
            return subprocess.CompletedProcess(
                command, code, f"{check} output {attempts[check]}\n", "lint failure\n" if code else ""
            )

        exit_code, report = execute_quality(REPO, files, runner=runner, platform_name="nt")

        self.assertEqual(127, exit_code)
        self.assertEqual(["FAIL", "FAIL", "PASS"], [row["status"] for row in report["checks"]])
        self.assertIn("controlled first chunk launch failure", report["checks"][0]["stderr"])
        self.assertEqual(9, report["checks"][1]["exitCode"])
        self.assertIn("lint failure", report["checks"][1]["stderr"])
        for observed in seen.values():
            self.assertEqual(files, observed)
        self.assertEqual(1, attempts["types"])

    def test_mypy_response_file_is_removed_after_launch_error(self) -> None:
        files = [f"tools/{'long_segment/' * 10}module{index}.py" for index in range(734)]
        response_paths: list[Path] = []

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if "mypy" in command:
                response = Path(command[-1][1:])
                response_paths.append(response)
                self.assertEqual(files, response.read_text(encoding="utf-8").splitlines())
                raise OSError("controlled mypy launch failure")
            return subprocess.CompletedProcess(command, 0, "", "")

        exit_code, report = execute_quality(REPO, files, runner=runner, platform_name="nt")

        self.assertEqual(127, exit_code)
        self.assertEqual("controlled mypy launch failure", report["checks"][2]["stderr"])
        self.assertEqual(1, len(response_paths))
        self.assertFalse(response_paths[0].exists())

    def test_large_non_windows_calls_keep_original_arguments(self) -> None:
        files = [f"tools/{'long_segment/' * 10}module{index}.py" for index in range(734)]
        seen: list[list[str]] = []

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            seen.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        exit_code, report = execute_quality(REPO, files, runner=runner, platform_name="posix")

        self.assertEqual(0, exit_code)
        self.assertEqual(3, len(seen))
        for command in seen:
            self.assertEqual(files, command[command.index("--") + 1 :])
        self.assertTrue(all("transport" not in row for row in report["checks"]))

    def test_oversized_ruff_argument_fails_without_omitting_type_context(self) -> None:
        files = [f"tools/{'a' * 31_000}.py", "tools/regular.py"]
        seen: list[list[str]] = []

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            seen.append(command)
            self.assertIn("mypy", command)
            self.assertEqual(files, Path(command[-1][1:]).read_text(encoding="utf-8").splitlines())
            return subprocess.CompletedProcess(command, 0, "", "")

        exit_code, report = execute_quality(REPO, files, runner=runner, platform_name="nt")

        self.assertEqual(127, exit_code)
        self.assertEqual(["FAIL", "FAIL", "PASS"], [row["status"] for row in report["checks"]])
        self.assertEqual(1, len(seen))
        self.assertIn("single quality file argument", report["checks"][0]["stderr"])

    def test_response_file_rejects_argument_injection(self) -> None:
        for injected in ("tools/a\nother.py", "@another.args"):
            files = [f"tools/{'long_segment/' * 10}module{index}.py" for index in range(734)]
            files[0] = injected
            seen_types: list[list[str]] = []

            def runner(
                command: list[str], seen_types: list[list[str]] = seen_types, **_: object
            ) -> subprocess.CompletedProcess[str]:
                if "mypy" in command:
                    seen_types.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            with self.subTest(injected=injected):
                exit_code, report = execute_quality(REPO, files, runner=runner, platform_name="nt")

                self.assertEqual(127, exit_code)
                self.assertEqual([], seen_types)
                self.assertEqual("FAIL", report["checks"][2]["status"])
                self.assertIn("cannot inject", report["checks"][2]["stderr"])

    def test_small_negative_returncode_keeps_original_report_value(self) -> None:
        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            code = -9 if "format" in command else 0
            return subprocess.CompletedProcess(command, code, "", "terminated" if code else "")

        exit_code, report = execute_quality(REPO, ["tools/quality_check.py"], runner=runner, platform_name="nt")

        self.assertEqual(1, exit_code)
        self.assertEqual(-9, report["checks"][0]["exitCode"])
        self.assertEqual("terminated", report["checks"][0]["stderr"])
        self.assertEqual(["FAIL", "PASS", "PASS"], [row["status"] for row in report["checks"]])

    def test_windows_transport_uses_utf8_without_changing_parent_environment(self) -> None:
        files = [f"tools/{'long_segment/' * 10}module{index}.py" for index in range(734)]
        before = dict(os.environ)
        seen: list[list[str]] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual("utf-8", kwargs.get("encoding"))
            environment = kwargs.get("env")
            self.assertIsInstance(environment, dict)
            assert isinstance(environment, dict)
            self.assertEqual("utf-8", environment["PYTHONIOENCODING"])
            self.assertIsNot(environment, os.environ)
            seen.append(command)
            return subprocess.CompletedProcess(command, 0, "caf\u00e9 \U0001f600\n", "")

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            exit_code, report = execute_quality(REPO, files, runner=runner, platform_name="nt")

        self.assertEqual(0, exit_code)
        self.assertIn("caf\u00e9 \U0001f600", captured.getvalue())
        self.assertGreater(len(seen), 3)
        self.assertEqual(before, dict(os.environ))
        for row in report["checks"]:
            self.assertEqual("utf-8", row["stdioEncoding"])
            self.assertEqual({"PYTHONIOENCODING": "utf-8"}, row["childEnvironmentOverrides"])
            self.assertIn("caf\u00e9 \U0001f600", row["stdout"])

    def test_real_response_transport_preserves_spaces_unicode_and_cross_file_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "pyproject.toml").write_text(
                '[tool.ruff]\nline-length = 120\n[tool.mypy]\npython_version = "3.14"\n', encoding="utf-8"
            )
            folder = repo / ("space caf\u00e9 \U0001f600 " + "segment " * 5).rstrip()
            folder.mkdir()
            files: list[str] = []
            for index in range(8):
                path = folder / f"module{index}.py"
                path.write_text("value: int = 1\n", encoding="utf-8")
                files.append(path.relative_to(repo).as_posix())
            (folder / "module0.py").write_text("def number() -> int:\n    return 1\n", encoding="utf-8")
            (folder / "module1.py").write_text(
                "from module0 import number\n\nresult: str = number()\n", encoding="utf-8"
            )
            environment = dict(os.environ)
            environment["MYPY_CACHE_DIR"] = str(repo / "mypy-cache")
            environment["RUFF_CACHE_DIR"] = str(repo / "ruff-cache")

            def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
                child_environment = dict(kwargs.get("env", os.environ))
                child_environment["MYPY_CACHE_DIR"] = environment["MYPY_CACHE_DIR"]
                child_environment["RUFF_CACHE_DIR"] = environment["RUFF_CACHE_DIR"]
                kwargs["env"] = child_environment
                return subprocess.run(command, **kwargs)

            captured = io.StringIO()
            with (
                contextlib.redirect_stdout(captured),
                contextlib.redirect_stderr(captured),
                patch.object(quality_check, "WINDOWS_COMMAND_LIMIT", 600),
            ):
                exit_code, report = execute_quality(repo, files, runner=runner, platform_name="nt")

            self.assertEqual(1, exit_code)
            self.assertIn("Incompatible types in assignment", captured.getvalue())
            self.assertIn("caf\u00e9 \U0001f600", captured.getvalue())
            self.assertEqual(["PASS", "PASS", "FAIL"], [row["status"] for row in report["checks"]])
            self.assertEqual("mypy-response-file", report["checks"][2]["transport"])
            self.assertIn("Incompatible types in assignment", report["checks"][2]["stdout"])
            self.assertIn("checked 8 source files", report["checks"][2]["stdout"])
            self.assertNotIn("import-not-found", report["checks"][2]["stdout"])


if __name__ == "__main__":
    unittest.main()
