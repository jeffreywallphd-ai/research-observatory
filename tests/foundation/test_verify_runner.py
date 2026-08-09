from __future__ import annotations

import copy
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from verify import execute_profile, expand_profile, load_contract, validate_contract  # noqa: E402


class VerificationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_contract(REPO)

    def test_profile_contract_defines_every_task_facing_profile(self) -> None:
        self.assertEqual([], validate_contract(self.contract))
        self.assertEqual(
            {
                "foundation",
                "desktop",
                "service",
                "data",
                "documents",
                "search",
                "ai",
                "evidence",
                "graph",
                "novelty",
                "e2e-local",
                "security-local",
                "server",
                "cloud",
            },
            set(self.contract["profiles"]),
        )

    def test_profile_expansion_is_independent_and_deduplicated(self) -> None:
        commands = expand_profile(self.contract, "service")

        self.assertEqual("foundation:repository-structure", commands[0])
        self.assertIn(
            "service:unit",
            [item["command"] for item in self.contract["profiles"]["service"]["optionalCommands"]],
        )
        self.assertEqual(len(commands), len(set(commands)))

    def test_unknown_profile_fails_safely(self) -> None:
        exit_code, report = execute_profile(REPO, self.contract, "unknown")

        self.assertEqual(2, exit_code)
        self.assertEqual("ERROR", report["status"])
        self.assertIn("unknown verification profile", report["failureCause"])

    def test_malformed_optional_command_is_rejected_without_crash(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["profiles"]["desktop"]["optionalCommands"] = ["invalid"]

        errors = validate_contract(contract)

        self.assertIn("profile 'desktop' optional commands must be objects", errors)

    def test_release_gated_profile_reports_blocker(self) -> None:
        exit_code, report = execute_profile(REPO, self.contract, "cloud")

        self.assertEqual(3, exit_code)
        self.assertEqual("BLOCKED", report["status"])
        self.assertIn("W11", report["failureCause"])

    def test_command_failure_reports_exit_duration_and_diagnostic(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["profiles"]["foundation"]["commands"] = ["foundation:runtime"]

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 17, "", "controlled failure")

        ticks = iter([10.0, 10.1, 10.6, 10.7])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            exit_code, report = execute_profile(REPO, contract, "foundation", runner=runner, clock=lambda: next(ticks))

        self.assertEqual(17, exit_code)
        self.assertEqual("FAIL", report["status"])
        self.assertEqual(0.5, report["commands"][0]["durationSeconds"])
        self.assertIn("controlled failure", report["failureCause"])

    def test_desktop_extensions_activate_without_changing_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            activation = repo / "verification" / "extensions" / "desktop-ui.json"
            activation.parent.mkdir(parents=True)
            activation.write_text("{}\n", encoding="utf-8")
            contract = copy.deepcopy(self.contract)
            contract["profiles"]["foundation"]["commands"] = []
            contract["profiles"]["desktop"]["commands"] = []
            seen: list[list[str]] = []

            def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                seen.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code, report = execute_profile(repo, contract, "desktop", runner=runner)

            self.assertEqual(0, exit_code)
            self.assertEqual(6, len(seen))
            self.assertEqual(
                ["desktop:application", "desktop:performance", "desktop:unit"],
                [item["command"] for item in report["skippedOptionalCommands"]],
            )


if __name__ == "__main__":
    unittest.main()
