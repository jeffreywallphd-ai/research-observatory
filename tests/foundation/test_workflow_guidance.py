"""Bounded friction contracts; mocks prove routing, not actual plan validity."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from functools import partial
from pathlib import Path
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import planctl  # noqa: E402
import taskctl  # noqa: E402


class WorkflowGuidanceTests(unittest.TestCase):
    def task(self, wave: str) -> dict:
        return {
            "wave": wave,
            "base_sha": "a" * 40,
            "verification_profiles": ["foundation"],
            "verification_commands": ["python -m unittest named_focused_case"],
        }

    def test_supported_previews_and_w3_manual_route_preserve_inventory(self) -> None:
        for wave in ("W1", "W2"):
            with self.subTest(wave=wave):
                output = "\n".join(taskctl.task_check_guidance(self.task(wave), repo=REPO))
                self.assertIn(f"--deferred-gate {wave}-exit --selection-only", output)
        for wave in ("W3", "W12", "unbound"):
            with self.subTest(wave=wave):
                output = "\n".join(taskctl.task_check_guidance(self.task(wave), repo=REPO))
                self.assertNotIn("--deferred-gate", output)
                self.assertIn("Select named focused checks manually", output)
                self.assertIn("fresh full Wave qualification", output)
                self.assertIn("python -m unittest named_focused_case", output)

    def test_missing_corrupt_or_unadmitted_policy_cannot_print_invalid_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "verification").mkdir()
            for text in (None, "{broken", json.dumps({"affectedDeferredOwners": ["W3-exit"]})):
                with self.subTest(text=text):
                    if text is not None:
                        (repo / "verification/affected-selection.json").write_text(text, encoding="utf-8")
                    output = "\n".join(taskctl.task_check_guidance(self.task("W3"), repo=repo))
                    self.assertNotIn("--deferred-gate", output)
                    self.assertIn("no preview is emitted", output)

    def test_actual_checks_cli_uses_selected_repository_policy_and_preserves_raw_inventory(self) -> None:
        original = (REPO / "planning/backlog.yaml").read_bytes()
        data = yaml.safe_load(original)
        task = next(
            task
            for capability in data["capabilities"]
            for slice_ in capability["slices"]
            for task in slice_["tasks"]
            if task.get("wave") in {"W1", "W2"} and task.get("base_sha") and task.get("verification_profiles")
        )
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "planning").mkdir()
            backlog = repo / "planning/backlog.yaml"
            backlog.write_bytes(original)
            for arguments in (
                ["init"],
                ["add", "."],
                [
                    "-c",
                    "user.name=Synthetic Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "commit",
                    "-m",
                    "Synthetic checks fixture",
                ],
            ):
                subprocess.run(["git", *arguments], cwd=repo, capture_output=True, check=True)
            index = (repo / ".git/index").read_bytes()
            argv = [sys.executable, "-B", str(REPO / "tools/taskctl.py"), "--file", str(backlog), "checks", task["id"]]
            for policy in (None, "{broken"):
                with self.subTest(policy=policy):
                    if policy is not None:
                        (repo / "verification").mkdir()
                        (repo / "verification/affected-selection.json").write_text(policy, encoding="utf-8")
                    completed = subprocess.run(argv, cwd=repo, capture_output=True, text=True, check=True)
                    self.assertNotIn("--deferred-gate", completed.stdout)
                    self.assertIn("Select named focused checks manually", completed.stdout)
            raw = subprocess.run([*argv, "--raw"], cwd=repo, capture_output=True, text=True, check=True)
            self.assertEqual("".join(f"{command}\n" for command in task["verification_commands"]), raw.stdout)
            self.assertEqual(original, backlog.read_bytes())
            self.assertEqual(index, (repo / ".git/index").read_bytes())

    def test_each_normal_admission_owns_one_fresh_full_readiness_call(self) -> None:
        args = argparse.Namespace(file=str(REPO / "planning/backlog.yaml"))
        result = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(taskctl.subprocess, "run", return_value=result) as run:
            taskctl.require_wave_planning_ready(args, "W3")
            self.assertEqual(1, run.call_count)
            self.assertEqual(["wave", "ready", "W3", "--require-approved"], run.call_args.args[0][-4:])
            taskctl.require_wave_planning_ready(args, "W3")
            self.assertEqual(2, run.call_count)
        failure = subprocess.CompletedProcess([], 1, "actual failed prerequisite", "denial")
        with patch.object(taskctl.subprocess, "run", return_value=failure) as run:
            with self.assertRaisesRegex(SystemExit, "actual failed prerequisite"):
                taskctl.require_wave_planning_ready(args, "W3")
            run.assert_called_once()

    def test_normal_documented_sequence_has_no_standalone_duplicate(self) -> None:
        text = (REPO / "docs/automation/codex-tracking-guide.md").read_text(encoding="utf-8")
        normal = text.split("## Command sequence", 1)[1].split("```bash", 1)[1].split("```", 1)[0]
        self.assertNotIn("wave ready WN", normal)
        self.assertIn("taskctl.py --file planning/backlog.yaml wave resume WN", normal)
        self.assertNotIn("wave review WN", normal)

    def test_timing_reports_real_exit_and_exception_without_changing_results(self) -> None:
        for result in (0, 7):
            stream = io.StringIO()
            with redirect_stdout(stream), patch.object(planctl.time, "monotonic", side_effect=[10.0, 12.5]):
                self.assertEqual(result, planctl.readiness_stage("synthetic-routing-calibration", partial(int, result)))
            report = json.loads(stream.getvalue().removeprefix("READINESS_TIMING "))
            self.assertEqual(result, report["exitCode"])
            self.assertEqual(2.5, report["elapsedSeconds"])
        stream = io.StringIO()
        with redirect_stdout(stream), self.assertRaisesRegex(ValueError, "calibrated"):
            planctl.readiness_stage(
                "synthetic-routing-calibration", lambda: (_ for _ in ()).throw(ValueError("calibrated"))
            )
        self.assertIsNone(json.loads(stream.getvalue().removeprefix("READINESS_TIMING "))["exitCode"])

    def test_diagnostic_sink_failure_preserves_the_real_result_and_exception(self) -> None:
        for error in (OSError("closed diagnostic pipe"), ValueError("closed diagnostic sink")):
            with self.subTest(error=type(error).__name__), patch("builtins.print", side_effect=error):
                self.assertEqual(7, planctl.readiness_stage("synthetic-sink-denial", lambda: 7))
                with self.assertRaisesRegex(RuntimeError, "real prerequisite failure"):
                    planctl.readiness_stage(
                        "synthetic-sink-denial",
                        lambda: (_ for _ in ()).throw(RuntimeError("real prerequisite failure")),
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
