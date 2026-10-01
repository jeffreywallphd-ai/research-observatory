from __future__ import annotations

import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
GATE_BOUND_PERFORMANCE = [
    "desktop:performance",
    "data:project-lifecycle-performance",
    "data:storage-maintenance-performance",
]
W2_PROFILES = [
    "data",
    "desktop",
    "documents",
    "e2e-local",
    "foundation",
    "graph",
    "search",
    "security-local",
    "service",
]
sys.path.insert(0, str(REPO / "tools"))

from corpus_report_test_check import main as corpus_report_test_main  # noqa: E402
from corpus_test_check import main as corpus_test_main  # noqa: E402
from verify import (  # noqa: E402
    active_profile_commands,
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

    def test_unittest_commands_report_case_ids_and_skip_reasons(self) -> None:
        commands = [command["argv"] for command in self.contract["commands"].values() if "unittest" in command["argv"]]
        self.assertTrue(commands)
        for argv in commands:
            with self.subTest(argv=argv):
                self.assertIn("-v", argv)

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

    def test_corpus_command_activation_and_w2_union(self) -> None:
        self.assertEqual(
            ["{python}", "tools/corpus_test_check.py"],
            self.contract["commands"]["service:corpus"]["argv"],
        )
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            inactive, skipped = active_profile_commands(repo, self.contract, "service")
            self.assertNotIn("service:corpus", inactive)
            self.assertIn("service:corpus", [item["command"] for item in skipped])

            test_file = repo / "tests" / "corpus" / "test_example.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("import unittest\n", encoding="utf-8")
            active, skipped = active_profile_commands(repo, self.contract, "service")
            self.assertEqual(1, active.count("service:corpus"))
            self.assertNotIn("service:corpus", [item["command"] for item in skipped])
            w2, _ = resolve_wave_exit_selection(repo, self.contract, self.policy, "W2")
            self.assertEqual(1, w2["selectedCommandIds"].count("service:corpus"))
            self.assertEqual([], w2["deferredCommandIds"])

    def test_corpus_launcher_sets_only_checkout_import_paths_and_preserves_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, redirect_stderr(io.StringIO()):
            repo = Path(temporary)
            test_file = repo / "tests" / "corpus" / "test_example.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("import unittest\n", encoding="utf-8")
            self.assertEqual(2, corpus_test_main(repo))
            test_file.unlink()
            (repo / "services" / "core-api" / "src").mkdir(parents=True)
            self.assertEqual(2, corpus_test_main(repo))
        with patch("corpus_test_check.subprocess.run") as runner:
            runner.return_value.returncode = 19
            self.assertEqual(19, corpus_test_main(REPO))
        command = runner.call_args.args[0]
        self.assertEqual(sys.executable, command[0])
        self.assertEqual(
            ["-B", "-s", "-m", "unittest", "discover", "-v", "-s", "tests/corpus", "-p", "test_*.py"],
            command[1:],
        )
        options = runner.call_args.kwargs
        self.assertEqual(REPO, options["cwd"])
        self.assertFalse(options["check"])
        self.assertEqual(
            os.pathsep.join((str(REPO / "services" / "core-api" / "src"), str(REPO))),
            options["env"]["PYTHONPATH"],
        )

    def test_corpus_report_command_is_required_in_service_and_w2_union(self) -> None:
        self.assertEqual(
            ["{python}", "tools/corpus_report_test_check.py"],
            self.contract["commands"]["service:corpus-reports"]["argv"],
        )
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            active, skipped = active_profile_commands(repo, self.contract, "service")
            self.assertEqual(1, active.count("service:corpus-reports"))
            self.assertNotIn("service:corpus-reports", [item["command"] for item in skipped])
            w2, _ = resolve_wave_exit_selection(repo, self.contract, self.policy, "W2")
            self.assertEqual(1, w2["selectedCommandIds"].count("service:corpus-reports"))
            self.assertEqual([], w2["deferredCommandIds"])

    def test_corpus_report_launcher_requires_both_suites_and_preserves_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, redirect_stderr(io.StringIO()):
            repo = Path(temporary)
            (repo / "services" / "core-api" / "src").mkdir(parents=True)
            for present_suite in ("corpus_reports", "reports"):
                with self.subTest(present_suite=present_suite):
                    test_file = repo / "tests" / present_suite / "test_example.py"
                    test_file.parent.mkdir(parents=True, exist_ok=True)
                    test_file.write_text("import unittest\n", encoding="utf-8")
                    w2, skipped = resolve_wave_exit_selection(repo, self.contract, self.policy, "W2")
                    self.assertEqual(1, w2["selectedCommandIds"].count("service:corpus-reports"))
                    self.assertNotIn("service:corpus-reports", [item["command"] for item in skipped])
                    self.assertEqual(2, corpus_report_test_main(repo))
                    test_file.unlink()

        with patch("corpus_report_test_check.subprocess.run") as runner:
            runner.side_effect = [
                subprocess.CompletedProcess([], 0),
                subprocess.CompletedProcess([], 19),
            ]
            self.assertEqual(19, corpus_report_test_main(REPO))
        self.assertEqual(2, runner.call_count)
        for call, suite in zip(runner.call_args_list, ("corpus_reports", "reports"), strict=True):
            command = call.args[0]
            self.assertEqual(sys.executable, command[0])
            self.assertEqual(
                ["-B", "-s", "-m", "unittest", "discover", "-v", "-s", str(REPO / "tests" / suite), "-p", "test_*.py"],
                command[1:],
            )
            self.assertEqual(REPO, call.kwargs["cwd"])
            self.assertFalse(call.kwargs["check"])
            self.assertEqual(
                os.pathsep.join((str(REPO / "services" / "core-api" / "src"), str(REPO))),
                call.kwargs["env"]["PYTHONPATH"],
            )

    def test_direct_full_profile_cli_warns_without_blocking_execution(self) -> None:
        error_output = io.StringIO()
        argv = ["verify.py", "--repo", str(REPO), "--profile", "service"]
        passing_report = {"profile": "service", "status": "PASS", "commands": []}

        with (
            patch.object(sys, "argv", argv),
            patch("verify.execute_profile", return_value=(0, passing_report)) as execute,
            redirect_stdout(io.StringIO()),
            redirect_stderr(error_output),
        ):
            self.assertEqual(0, verify_main())

        execute.assert_called_once()
        advisory = error_output.getvalue()
        self.assertIn("complete qualification inventory", advisory)
        self.assertIn("foundation:benchmark-registry", advisory)
        self.assertIn("foundation:unit", advisory)
        self.assertIn("does not block execution", advisory)

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
        cases = (
            ("ordinary mapped path", ["foundation"], "tests/data/test_storage.py"),
            ("security boundary", ["foundation"], "tools/security_check.py"),
            (
                "migration boundary",
                ["data"],
                "services/core-api/src/research_observatory_core/migrations/v9999.py",
            ),
            ("threshold boundary", ["desktop"], "verification/baselines/desktop-performance.json"),
        )
        for label, profiles, path in cases:
            with self.subTest(case=label), self.assertRaisesRegex(ValueError, "outside the requested profiles"):
                select_affected_commands(
                    REPO,
                    self.contract,
                    self.policy,
                    profiles,
                    [path],
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

    def test_corpus_affected_selection_keeps_test_changes_narrow(self) -> None:
        for path in (
            "services/core-api/src/research_observatory_core/corpus_service.py",
            "services/core-api/src/research_observatory_core/app.py",
            "packages/contracts/corpus/corpus-membership.schema.json",
            "packages/contracts/core-api/openapi.json",
        ):
            with self.subTest(path=path):
                selection, _ = select_affected_commands(
                    REPO, self.contract, self.policy, ["service"], [path], "W2-exit"
                )
                self.assertEqual("none", selection["fallback"])
                self.assertIn("core-api-and-portable-contracts", selection["matchedRuleIds"])
                self.assertIn("service:corpus", selection["selectedCommandIds"])

        corpus, _ = select_affected_commands(
            REPO, self.contract, self.policy, ["service"], ["tests/corpus/test_service.py"], "W2-exit"
        )
        self.assertEqual("none", corpus["fallback"])
        self.assertIn("corpus-tests", corpus["matchedRuleIds"])
        self.assertEqual(["foundation:quality", "service:corpus"], corpus["selectedCommandIds"])
        launcher, _ = select_affected_commands(
            REPO, self.contract, self.policy, ["service"], ["tools/corpus_test_check.py"], "W2-exit"
        )
        self.assertEqual("none", launcher["fallback"])
        self.assertIn("corpus-tests", launcher["matchedRuleIds"])
        self.assertIn("service:corpus", launcher["selectedCommandIds"])
        for path in ("tests/service/test_import_preview_service.py", "docs/automation/verification-profiles.md"):
            with self.subTest(unrelated=path):
                selection, _ = select_affected_commands(
                    REPO, self.contract, self.policy, ["service"], [path], "W2-exit"
                )
                self.assertEqual("none", selection["fallback"])
                self.assertNotIn("service:corpus", selection["selectedCommandIds"])

        with tempfile.TemporaryDirectory() as temporary:
            inactive, skipped = select_affected_commands(
                Path(temporary), self.contract, self.policy, ["service"], ["tests/corpus/test_service.py"], "W2-exit"
            )
        self.assertIn("service:corpus", [item["command"] for item in skipped])
        self.assertNotIn("service:corpus", inactive["selectedCommandIds"])
        self.assertNotIn("service:corpus", inactive["deferredCommandIds"])

    def test_corpus_report_affected_selection_keeps_test_changes_narrow(self) -> None:
        for path in (
            "services/core-api/src/research_observatory_core/corpus_report_repository.py",
            "packages/contracts/corpus-reports/corpus-report.schema.json",
        ):
            with self.subTest(path=path):
                selection, _ = select_affected_commands(
                    REPO, self.contract, self.policy, ["service"], [path], "W2-exit"
                )
                self.assertEqual("none", selection["fallback"])
                self.assertIn("core-api-and-portable-contracts", selection["matchedRuleIds"])
                self.assertIn("service:corpus-reports", selection["selectedCommandIds"])

        for path in ("tests/corpus_reports/test_model.py", "tests/reports/test_repository.py"):
            with self.subTest(path=path):
                selection, _ = select_affected_commands(
                    REPO, self.contract, self.policy, ["service"], [path], "W2-exit"
                )
                self.assertEqual("none", selection["fallback"])
                self.assertIn("corpus-report-tests", selection["matchedRuleIds"])
                self.assertEqual(["foundation:quality", "service:corpus-reports"], selection["selectedCommandIds"])

        launcher, _ = select_affected_commands(
            REPO, self.contract, self.policy, ["service"], ["tools/corpus_report_test_check.py"], "W2-exit"
        )
        self.assertEqual("none", launcher["fallback"])
        self.assertIn("corpus-report-tests", launcher["matchedRuleIds"])
        self.assertIn("service:corpus-reports", launcher["selectedCommandIds"])

        unrelated, _ = select_affected_commands(
            REPO, self.contract, self.policy, ["service"], ["tests/corpus/test_service.py"], "W2-exit"
        )
        self.assertNotIn("service:corpus-reports", unrelated["selectedCommandIds"])

        with tempfile.TemporaryDirectory() as temporary:
            selected, skipped = select_affected_commands(
                Path(temporary),
                self.contract,
                self.policy,
                ["service"],
                ["tests/reports/test_repository.py"],
                "W2-exit",
            )
        self.assertNotIn("service:corpus-reports", [item["command"] for item in skipped])
        self.assertIn("service:corpus-reports", selected["selectedCommandIds"])
        self.assertNotIn("service:corpus-reports", selected["deferredCommandIds"])

    def test_rights_affected_selection_activates_focused_boundary_checks(self) -> None:
        for path in (
            "services/core-api/src/research_observatory_core/rights_repository.py",
            "packages/contracts/rights/rights-policy.schema.json",
            "tests/rights/test_repository.py",
        ):
            with self.subTest(path=path):
                selection, _ = select_affected_commands(
                    REPO, self.contract, self.policy, ["service"], [path], "W2-exit"
                )
                self.assertEqual("none", selection["fallback"])
                self.assertIn("source-specific-rights", selection["matchedRuleIds"])
                self.assertIn("service:rights", selection["selectedCommandIds"])

        unrelated, _ = select_affected_commands(
            REPO, self.contract, self.policy, ["service"], ["docs/README.md"], "W2-exit"
        )
        self.assertNotIn("service:rights", unrelated["selectedCommandIds"])

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
        for unauthorized in ("G2", "slice-review"):
            with self.subTest(gate=unauthorized), self.assertRaisesRegex(ValueError, "not authorized"):
                select_affected_commands(
                    REPO,
                    self.contract,
                    self.policy,
                    ["foundation"],
                    ["docs/README.md"],
                    unauthorized,
                )

    def test_gate_bound_performance_is_always_deferred_in_affected_mode(self) -> None:
        for path, expected_fallback in (
            ("tools/verify.py", "safety-sensitive"),
            ("unknown/new-surface.xyz", "unknown-path"),
        ):
            with self.subTest(path=path):
                selection, _ = select_affected_commands(
                    REPO,
                    self.contract,
                    self.policy,
                    ["data", "desktop"],
                    [path],
                    "W1-exit",
                )
                self.assertEqual(expected_fallback, selection["fallback"])
                self.assertEqual(GATE_BOUND_PERFORMANCE, selection["gateBoundDeferredCommandIds"])
                for command_id in GATE_BOUND_PERFORMANCE:
                    self.assertNotIn(command_id, selection["selectedCommandIds"])
                    self.assertIn(command_id, selection["deferredCommandIds"])

        targeted, _ = select_affected_commands(
            REPO,
            self.contract,
            self.policy,
            ["data"],
            ["tests/data/test_storage.py"],
            "W1-exit",
        )
        self.assertEqual(GATE_BOUND_PERFORMANCE[1:], targeted["gateBoundDeferredCommandIds"])
        for command_id in GATE_BOUND_PERFORMANCE[1:]:
            self.assertNotIn(command_id, targeted["selectedCommandIds"])
            self.assertIn(command_id, targeted["deferredCommandIds"])

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

            invalid_argv = ["G2" if value == "W1-exit" else value for value in argv]
            error_output = io.StringIO()
            with patch.object(sys, "argv", invalid_argv), redirect_stdout(io.StringIO()), redirect_stderr(error_output):
                self.assertEqual(2, verify_main())
            self.assertIn("not authorized", error_output.getvalue())

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
        self.assertEqual(GATE_BOUND_PERFORMANCE, selection["gateBoundSelectedCommandIds"])
        for command_id in GATE_BOUND_PERFORMANCE:
            self.assertEqual(1, selection["selectedCommandIds"].count(command_id))
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

    def test_w2_union_includes_all_active_commands_and_preserves_inventory(self) -> None:
        before_bytes = (REPO / "verification-profiles.json").read_bytes()
        before_contract = copy.deepcopy(self.contract)
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            inactive, _ = resolve_wave_exit_selection(repo, self.contract, self.policy, "W2")
            self.assertIn("documents:unit", inactive["inactiveOptionalCommands"])
            self.assertNotIn("documents:unit", inactive["selectedCommandIds"])
            expected: set[str] = set()
            for name in W2_PROFILES:
                expected.update(expand_profile(self.contract, name))
                for optional in self.contract["profiles"][name].get("optionalCommands", []):
                    activation = optional.get("activationPath") or optional["activationGlob"].replace("*", "fixture")
                    path = repo / activation
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("{}\n", encoding="utf-8")
                    expected.add(optional["command"])
            selection, skipped = resolve_wave_exit_selection(repo, self.contract, self.policy, "W2")

        self.assertEqual(W2_PROFILES, selection["requestedProfiles"])
        self.assertEqual(
            [command_id for command_id in self.contract["commands"] if command_id in expected],
            selection["selectedCommandIds"],
        )
        self.assertEqual([], selection["deferredCommandIds"])
        self.assertEqual([], skipped)
        self.assertEqual(GATE_BOUND_PERFORMANCE, selection["gateBoundSelectedCommandIds"])
        for command_id in (
            "service:reconciliation",
            "service:corpus",
            "service:corpus-reports",
            "search:connectors",
            "documents:unit",
        ):
            self.assertEqual(1, selection["selectedCommandIds"].count(command_id))
        self.assertEqual(before_contract, self.contract)
        self.assertEqual(before_bytes, (REPO / "verification-profiles.json").read_bytes())

    def test_w2_affected_partition_matches_w1_without_changing_coverage(self) -> None:
        for path, fallback in (
            ("tests/data/test_storage.py", "none"),
            ("unknown/new-surface.xyz", "unknown-path"),
            ("tools/verify.py", "safety-sensitive"),
        ):
            with self.subTest(path=path):
                arguments = (REPO, self.contract, self.policy, ["data", "desktop", "service"], [path])
                w1, _ = select_affected_commands(*arguments, "W1-exit")
                w2, _ = select_affected_commands(*arguments, "W2-exit")
                self.assertEqual(json.loads(json.dumps(w1).replace("W1-exit", "W2-exit")), w2)
                self.assertEqual(fallback, w2["fallback"])
                self.assertFalse(set(w2["selectedCommandIds"]) & set(w2["deferredCommandIds"]))
                self.assertEqual(GATE_BOUND_PERFORMANCE, w2["gateBoundDeferredCommandIds"])
        with self.assertRaisesRegex(ValueError, "outside the requested profiles"):
            select_affected_commands(
                REPO, self.contract, self.policy, ["foundation"], ["tools/security_check.py"], "W2-exit"
            )

    def test_w2_task_preview_and_exit_cli_select_without_executing(self) -> None:
        from taskctl import task_check_guidance

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            base, head = self.git_diff_fixture(repo, include_contract=True)
            task = {"verification_profiles": ["foundation"], "base_sha": base, "wave": "W2"}
            command = next(line for line in task_check_guidance(task) if line.startswith("python tools/verify.py"))
            preview = ["verify.py", *command.split()[2:]]
            for mode, arguments in (
                ("affected", preview),
                ("wave-exit", ["verify.py", "--wave-exit", "W2", "--selection-only"]),
            ):
                with self.subTest(mode=mode):
                    report_path = repo / f"{mode}.json"
                    argv = [*arguments, "--repo", str(repo), "--report", str(report_path)]
                    with (
                        patch.object(sys, "argv", argv),
                        patch("verify.execute_command_set") as execute,
                        redirect_stdout(io.StringIO()),
                        redirect_stderr(io.StringIO()),
                    ):
                        self.assertEqual(0, verify_main())
                    execute.assert_not_called()
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    self.assertEqual(mode, report["mode"])
                    self.assertTrue(report["selectionOnly"])
                    if mode == "affected":
                        self.assertEqual("W2-exit", report["selection"]["deferredOwner"])
                        self.assertEqual(base, report["selection"]["baseCommit"])
                        self.assertEqual(head, report["selection"]["headCommit"])
                    else:
                        self.assertEqual(W2_PROFILES, report["selection"]["requestedProfiles"])
                        self.assertEqual([], report["selection"]["deferredCommandIds"])

    def test_w2_exit_cannot_be_narrowed_or_replaced_with_unauthorized_gate(self) -> None:
        for extra in (["--profile", "service"], ["--affected-base", "1" * 40, "--deferred-gate", "W2-exit"]):
            with (
                self.subTest(extra=extra),
                patch.object(sys, "argv", ["verify.py", "--wave-exit", "W2", *extra]),
                patch("verify.execute_command_set") as execute,
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                verify_main()
            execute.assert_not_called()
        for wave in ("G2", "W3"):
            with self.subTest(wave=wave), self.assertRaisesRegex(ValueError, "no governed"):
                resolve_wave_exit_selection(REPO, self.contract, self.policy, wave)
        for owner in ("G2", "W3-exit"):
            with self.subTest(owner=owner), self.assertRaisesRegex(ValueError, "not authorized"):
                select_affected_commands(REPO, self.contract, self.policy, ["foundation"], ["docs/README.md"], owner)

    def test_w2_policy_corruption_fails_closed(self) -> None:
        for key, value in (
            ("affectedDeferredOwners", ["W1-exit"]),
            ("affectedDeferredOwners", ["W1-exit", "W2-exit", "W2-exit"]),
            ("affectedDeferredOwners", ["W1-exit", "G2"]),
            ("gateBoundCommandIds", {"W1-exit": GATE_BOUND_PERFORMANCE}),
            ("waveExitProfiles", {"W1": self.policy["waveExitProfiles"]["W1"]}),
        ):
            with self.subTest(key=key, value=value):
                policy = copy.deepcopy(self.policy)
                policy[key] = value
                self.assertTrue(validate_selection_policy(policy, self.contract))
        for key, name, values in (
            ("waveExitProfiles", "W2", (W2_PROFILES[:-1], [*W2_PROFILES, "service"], ["cloud"], ["unknown"], None)),
            (
                "gateBoundCommandIds",
                "W2-exit",
                (GATE_BOUND_PERFORMANCE[:-1], [*GATE_BOUND_PERFORMANCE, "graph:dependency-impact-performance"], None),
            ),
        ):
            for nested_value in values:
                with self.subTest(key=key, value=nested_value):
                    policy = copy.deepcopy(self.policy)
                    policy[key][name] = nested_value
                    self.assertTrue(validate_selection_policy(policy, self.contract))
        for alteration in ("missing-profile", "disabled-profile", "missing-command"):
            with self.subTest(alteration=alteration):
                contract = copy.deepcopy(self.contract)
                if alteration == "missing-profile":
                    del contract["profiles"]["documents"]
                elif alteration == "disabled-profile":
                    contract["profiles"]["documents"]["enabled"] = False
                else:
                    del contract["commands"]["desktop:performance"]
                self.assertTrue(validate_selection_policy(self.policy, contract))

    def test_malformed_affected_policy_is_rejected(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["rules"][0]["commands"].append("unknown:command")

        errors = validate_selection_policy(policy, self.contract)

        self.assertTrue(any("unknown command" in error for error in errors), errors)

        policy = copy.deepcopy(self.policy)
        policy["affectedDeferredOwners"].append("G2")
        self.assertTrue(any("exactly W1-exit" in error for error in validate_selection_policy(policy, self.contract)))

        policy = copy.deepcopy(self.policy)
        policy["gateBoundCommandIds"]["W1-exit"].pop()
        self.assertTrue(any("gate-bound" in error for error in validate_selection_policy(policy, self.contract)))


if __name__ == "__main__":
    unittest.main()
