from __future__ import annotations

import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from verify import (  # noqa: E402
    changed_paths_from_git,
    execute_profile,
    expand_profile,
    load_contract,
    load_selection_policy,
    normalize_changed_paths,
    resolve_wave_exit_selection,
    select_affected_commands,
    validate_contract,
    validate_selection_policy,
)
from verify import (  # noqa: E402
    main as verify_main,
)


class VerificationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_contract(REPO)
        self.policy = load_selection_policy(REPO)

    def git(self, repo: Path, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-c", "user.name=Verification Tests", "-c", "user.email=verify@example.invalid", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    def git_diff_fixture(self, root: Path, *, include_contract: bool = False) -> tuple[str, str]:
        self.git(root, "init")
        if include_contract:
            (root / "verification-profiles.json").write_bytes((REPO / "verification-profiles.json").read_bytes())
            policy_path = root / "verification" / "affected-selection.json"
            policy_path.parent.mkdir(parents=True)
            policy_path.write_bytes((REPO / "verification" / "affected-selection.json").read_bytes())
        tool = root / "tools" / "backlog_views.py"
        guide = root / "docs" / "automation" / "verification-profiles.md"
        tool.parent.mkdir(parents=True)
        guide.parent.mkdir(parents=True)
        tool.write_text("before = True\n", encoding="utf-8")
        guide.write_text("before\n", encoding="utf-8")
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "base")
        base = self.git(root, "rev-parse", "HEAD")
        tool.write_text("after = True\n", encoding="utf-8")
        guide.write_text("after\n", encoding="utf-8")
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "head")
        return base, self.git(root, "rev-parse", "HEAD")

    def test_profile_contract_defines_every_task_facing_profile(self) -> None:
        self.assertEqual([], validate_contract(self.contract))
        self.assertEqual([], validate_selection_policy(self.policy, self.contract))
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

    def test_affected_selection_is_deterministic_complete_and_contract_immutable(self) -> None:
        before_bytes = (REPO / "verification-profiles.json").read_bytes()
        before_contract = copy.deepcopy(self.contract)
        paths = ["tools/backlog_views.py", "docs/automation/verification-profiles.md"]

        first, _ = select_affected_commands(REPO, self.contract, self.policy, ["foundation"], paths, "W1-exit")
        second, _ = select_affected_commands(
            REPO,
            self.contract,
            self.policy,
            ["foundation", "foundation"],
            [*reversed(paths), paths[0]],
            "W1-exit",
        )

        self.assertEqual(first, second)
        selected = first["selectedCommandIds"]
        deferred = first["deferredCommandIds"]
        self.assertTrue(selected)
        self.assertFalse(set(selected) & set(deferred))
        self.assertEqual(set(expand_profile(self.contract, "foundation")), set(selected) | set(deferred))
        self.assertEqual(
            [command_id for command_id in self.contract["commands"] if command_id in set(selected)],
            selected,
        )
        self.assertEqual(
            [command_id for command_id in self.contract["commands"] if command_id in set(deferred)],
            deferred,
        )
        self.assertEqual(["python-quality", "foundation-governance-and-tests"], first["matchedRuleIds"])
        self.assertEqual("none", first["fallback"])
        self.assertEqual("W1-exit", first["deferredOwner"])
        self.assertEqual(before_contract, self.contract)
        self.assertEqual(before_bytes, (REPO / "verification-profiles.json").read_bytes())

    def test_unknown_or_safety_sensitive_path_selects_full_requested_inventory(self) -> None:
        active = expand_profile(self.contract, "foundation")
        for path, expected_fallback in (
            ("unmapped/new-surface.xyz", "unknown-path"),
            ("tools/verify.py", "safety-sensitive"),
            ("verification-profiles.json", "safety-sensitive"),
        ):
            with self.subTest(path=path):
                selection, _ = select_affected_commands(
                    REPO,
                    self.contract,
                    self.policy,
                    ["foundation"],
                    ["docs/README.md", path],
                    "W1-exit",
                )
                self.assertEqual(expected_fallback, selection["fallback"])
                self.assertEqual(active, selection["selectedCommandIds"])
                self.assertEqual([], selection["deferredCommandIds"])

    def test_mapped_command_outside_requested_profiles_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the requested profiles"):
            select_affected_commands(
                REPO,
                self.contract,
                self.policy,
                ["foundation"],
                ["tests/data/test_storage.py"],
                "W1-exit",
            )

    def test_domain_rules_are_bounded_and_multi_profile_order_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ai_selection, _ = select_affected_commands(
                Path(temporary),
                self.contract,
                self.policy,
                ["ai"],
                ["tests/ai/test_policy.py"],
                "W1-exit",
            )
        self.assertEqual("none", ai_selection["fallback"])
        self.assertIn("ai-tests", ai_selection["matchedRuleIds"])
        self.assertNotIn("documents:unit", ai_selection["selectedCommandIds"])

        first, _ = select_affected_commands(
            REPO,
            self.contract,
            self.policy,
            ["data", "service"],
            ["services/core-api/src/example.py"],
            "W1-exit",
        )
        second, _ = select_affected_commands(
            REPO,
            self.contract,
            self.policy,
            ["service", "data", "service"],
            ["services/core-api/src/example.py"],
            "W1-exit",
        )
        self.assertEqual(first, second)

    def test_unsafe_or_empty_changed_paths_and_gate_are_rejected(self) -> None:
        for paths in (
            [],
            ["../secret"],
            ["C:/user/data.txt"],
            ["/absolute"],
            ["tools\\verify.py"],
            [" x"],
            ["tools/control\nname.py"],
        ):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                normalize_changed_paths(paths)
        with self.assertRaisesRegex(ValueError, "controlled non-empty"):
            select_affected_commands(
                REPO,
                self.contract,
                self.policy,
                ["foundation"],
                ["docs/README.md"],
                "Wave exit with spaces",
            )

    def test_inactive_optional_commands_are_skipped_not_deferred(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            selection, skipped = select_affected_commands(
                Path(temporary),
                self.contract,
                self.policy,
                ["desktop"],
                ["apps/desktop/src/new-surface.ts"],
                "W1-exit",
            )

        inactive = [item["command"] for item in skipped]
        self.assertIn("desktop:application", inactive)
        self.assertNotIn("desktop:application", selection["selectedCommandIds"])
        self.assertNotIn("desktop:application", selection["deferredCommandIds"])
        self.assertEqual(inactive, selection["inactiveOptionalCommands"])

    def test_git_derived_paths_are_exact_and_empty_diff_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            base, head = self.git_diff_fixture(repo)

            resolved_base, resolved_head, paths = changed_paths_from_git(repo, base, head)

            self.assertEqual(base, resolved_base)
            self.assertEqual(head, resolved_head)
            self.assertEqual(
                ["docs/automation/verification-profiles.md", "tools/backlog_views.py"],
                paths,
            )
            with self.assertRaisesRegex(ValueError, "non-empty Git-derived"):
                changed_paths_from_git(repo, head, head)
            with self.assertRaisesRegex(ValueError, "full 40-character"):
                changed_paths_from_git(repo, base[:12], head)

    def test_selection_only_cli_uses_git_diff_and_has_no_path_subset_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            base, head = self.git_diff_fixture(repo, include_contract=True)
            report_path = repo / "affected.json"
            argv = [
                "verify.py",
                "--repo",
                str(repo),
                "--profile",
                "foundation",
                "--affected-base",
                base,
                "--affected-head",
                head,
                "--deferred-gate",
                "W1-exit",
                "--selection-only",
                "--report",
                str(report_path),
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(0, verify_main())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual("affected", report["mode"])
            self.assertTrue(report["selectionOnly"])
            self.assertEqual(base, report["selection"]["baseCommit"])
            self.assertEqual(head, report["selection"]["headCommit"])
            self.assertEqual(
                ["docs/automation/verification-profiles.md", "tools/backlog_views.py"],
                report["selection"]["changedPaths"],
            )

        with (
            patch.object(sys, "argv", ["verify.py", "--changed-path", "tools/verify.py"]),
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            verify_main()

    def test_w1_wave_exit_resolves_complete_deduplicated_enabled_union(self) -> None:
        selection, _ = resolve_wave_exit_selection(REPO, self.contract, self.policy, "W1")

        self.assertEqual(
            ["ai", "data", "desktop", "e2e-local", "foundation", "graph", "security-local", "service"],
            selection["requestedProfiles"],
        )
        self.assertEqual(len(selection["selectedCommandIds"]), len(set(selection["selectedCommandIds"])))
        self.assertEqual([], selection["deferredCommandIds"])
        self.assertNotIn("server", selection["requestedProfiles"])
        self.assertNotIn("cloud", selection["requestedProfiles"])

    def test_wave_exit_selection_only_cli_uses_governed_union(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "verification-profiles.json").write_bytes((REPO / "verification-profiles.json").read_bytes())
            policy_path = repo / "verification" / "affected-selection.json"
            policy_path.parent.mkdir(parents=True)
            policy_path.write_bytes((REPO / "verification" / "affected-selection.json").read_bytes())
            report_path = repo / "wave-exit.json"
            argv = [
                "verify.py",
                "--repo",
                str(repo),
                "--wave-exit",
                "W1",
                "--selection-only",
                "--report",
                str(report_path),
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(0, verify_main())
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual("wave-exit", report["mode"])
        self.assertEqual("W1", report["selection"]["wave"])
        self.assertEqual([], report["selection"]["deferredCommandIds"])

    def test_malformed_affected_policy_is_rejected(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["rules"][0]["commands"].append("unknown:command")

        errors = validate_selection_policy(policy, self.contract)

        self.assertTrue(any("unknown command" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
