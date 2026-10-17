"""Readiness routing regressions; full real-repository readiness remains required.

Injection tests characterize orchestration, not approval/site validity. The real
Git fixture proves preservation of tracked/index/backlog bytes and actual clean
admission. Qualification additionally runs the unchanged generator and complete
checker against committed repository inputs and ordinary taskctl resume.
"""

from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import call, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import planctl  # noqa: E402
from taskctl import require_clean_repository  # noqa: E402


class ReadinessRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "planning/review-site").mkdir(parents=True)
        (self.root / "planning/backlog.yaml").write_text("waves: [{id: W7}]\ncapabilities: []\n")
        (self.root / ".gitignore").write_text("/.local/\n")
        self.published = self.root / "planning/review-site/index.html"
        self.published.write_text("committed reviewer-visible publication\n")

    def test_real_git_remains_clean_when_fresh_projection_differs(self) -> None:
        for args in (
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
                "Synthetic fixture",
            ],
        ):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        index = (self.root / ".git/index").read_bytes()
        backlog = (self.root / "planning/backlog.yaml").read_bytes()
        publication = self.published.read_bytes()
        observed = []

        def generate(root, capability=None, output=None):
            self.assertEqual(root, self.root)
            destination = output or root / "planning/review-site"
            (destination / "index.html").write_text("fresh generated projection\n")
            observed.append(destination)
            return 0

        def validate(root, wave, approved, site=None):
            self.assertTrue(approved)
            destination = site or root / "planning/review-site"
            self.assertEqual(destination, observed[-1])
            self.assertEqual((destination / "index.html").read_text(), "fresh generated projection\n")
            return 0

        with (
            patch.object(planctl, "generate_review", side_effect=generate),
            patch.object(planctl, "validate_wave", side_effect=validate),
            patch.object(sys, "argv", ["planctl", "--repo", str(self.root), "wave", "ready", "W7"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(0, planctl.main())
            # The predecessor reaches this real clean predicate with its tracked
            # canonical page modified; the failure is behavioral, not a missing API.
            require_clean_repository(self.root)
            self.assertEqual(0, planctl.main())
            require_clean_repository(self.root)
        self.assertTrue(all(site.parent == self.root / ".local" for site in observed))
        self.assertNotEqual(observed[0], observed[1])
        self.assertTrue(all(not site.exists() for site in observed))
        self.assertEqual(publication, self.published.read_bytes())
        self.assertEqual(backlog, (self.root / "planning/backlog.yaml").read_bytes())
        self.assertEqual(index, (self.root / ".git/index").read_bytes())
        require_clean_repository(self.root)
        self.published.write_text("unapproved tracked mutation\n")
        with self.assertRaises(SystemExit):
            require_clean_repository(self.root)
        subprocess.run(["git", "add", str(self.published)], cwd=self.root, check=True, capture_output=True)
        with self.assertRaises(SystemExit):
            require_clean_repository(self.root)

    def test_actual_clean_predicate_still_rejects_untracked_source(self) -> None:
        for args in (
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
                "Synthetic fixture",
            ],
        ):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        require_clean_repository(self.root)
        (self.root / "unexpected.py").write_text("# untracked fixture source\n")
        with self.assertRaisesRegex(SystemExit, "Untracked source exists"):
            require_clean_repository(self.root)

    def test_generator_failure_prevents_validation_and_canonical_write(self) -> None:
        before = self.published.read_bytes()
        with (
            patch.object(planctl, "generate_review", return_value=9) as generator,
            patch.object(planctl, "validate_wave") as validator,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(1, planctl.ready_wave(self.root, "W7"))
        validator.assert_not_called()
        site = generator.call_args.kwargs["output"]
        self.assertFalse(site.exists())
        self.assertEqual(before, self.published.read_bytes())

    def test_validator_denial_propagates_and_cleans_output(self) -> None:
        with (
            patch.object(planctl, "generate_review", return_value=0) as generator,
            patch.object(planctl, "validate_wave", return_value=1) as validator,
        ):
            self.assertEqual(1, planctl.ready_wave(self.root, "W7"))
        site = generator.call_args.kwargs["output"]
        validator.assert_called_once_with(self.root, "W7", True, site=site)
        self.assertFalse(site.exists())

    def test_ready_exception_never_regenerates_canonical_output(self) -> None:
        for stage in ("generation", "validation", "cleanup"):
            with self.subTest(stage=stage):
                before = self.published.read_bytes()
                with (
                    patch.object(sys, "argv", ["planctl", "--repo", str(self.root), "wave", "ready", "W7"]),
                    patch.object(
                        planctl,
                        "generate_review",
                        side_effect=OSError("injected generation") if stage == "generation" else None,
                        return_value=0,
                    ) as generator,
                    patch.object(
                        planctl,
                        "validate_wave",
                        side_effect=ValueError("injected validation") if stage == "validation" else None,
                        return_value=0,
                    ),
                    (
                        patch.object(
                            planctl.tempfile.TemporaryDirectory, "cleanup", side_effect=OSError("injected cleanup")
                        )
                        if stage == "cleanup"
                        else nullcontext()
                    ),
                    redirect_stdout(io.StringIO()),
                    redirect_stderr(io.StringIO()),
                ):
                    self.assertEqual(1, planctl.main())
                self.assertEqual(1, generator.call_count)
                self.assertIsNotNone(generator.call_args.kwargs.get("output"))
                self.assertEqual(before, self.published.read_bytes())

    def test_validate_wave_selects_same_complete_checker_and_explicit_site(self) -> None:
        # This protects argv orchestration only; actual plans and full checker
        # are separately exercised against the committed real repository.
        cap = {"id": "CAP-20", "slices": [{"id": "CAP-20.S01", "wave": "W7"}]}
        approval = {"status": "APPROVED", "capability_ids": ["CAP-20"], "decision_ids": [], "slice_ids": ["CAP-20.S01"]}
        data = {"waves": [{"id": "W7", "approval": approval}], "capabilities": [cap]}
        plan = self.root / "planning/capability-plans/CAP-20.md"
        plan.parent.mkdir()
        plan.write_text("---\ndecisions: []\n---\nSynthetic argv fixture\n")
        site = self.root / ".local/owned"
        with (
            patch.object(planctl, "load_backlog", return_value=(data, {"CAP-20": cap})),
            patch.object(planctl, "run_validator", return_value=0) as validator,
            patch.object(planctl, "wave_initiation_rollup_errors", return_value=[]),
            patch.object(planctl.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run,
        ):
            self.assertEqual(0, planctl.validate_wave(self.root, "W7", True, site=site))
            self.assertEqual(
                [
                    sys.executable,
                    str(self.root / "tools/plan_review_check.py"),
                    "--repo",
                    str(self.root),
                    "--site",
                    str(site),
                ],
                run.call_args.args[0],
            )
            self.assertEqual(
                [
                    call(self.root, "capability_plan_check.py", "CAP-20", True, "W7"),
                    call(self.root, "slice_plan_check.py", "CAP-20", True, "W7"),
                ],
                validator.call_args_list,
            )
            self.assertEqual(0, planctl.validate_wave(self.root, "W7", True))
            self.assertNotIn("--site", run.call_args.args[0])
            run.return_value = subprocess.CompletedProcess([], 1)
            self.assertEqual(1, planctl.validate_wave(self.root, "W7", True, site=site))
            run.return_value = subprocess.CompletedProcess([], 0)
            with redirect_stderr(io.StringIO()):
                for field, wrong in (
                    ("status", "PENDING"),
                    ("capability_ids", []),
                    ("decision_ids", ["UNAPPROVED-DECISION"]),
                    ("slice_ids", []),
                ):
                    original = approval[field]
                    approval[field] = wrong
                    with self.subTest(approval_field=field):
                        self.assertEqual(1, planctl.validate_wave(self.root, "W7", True, site=site))
                    approval[field] = original
                approval.update(
                    approved_by="synthetic-reviewer", approved_at="2026-10-17T00:00:00Z", approved_commit="a" * 40
                )
                slice_path = self.root / "planning/slice-plans/CAP-20/CAP-20.S01.md"
                slice_approval = {field: approval[field] for field in ("approved_by", "approved_at", "approved_commit")}
                meta = {"slice_id": "CAP-20.S01", "wave": "W7", "approval": slice_approval}
                planctl.write_plan(slice_path, meta, "Synthetic approval fixture\n")
                self.assertEqual(0, planctl.validate_wave(self.root, "W7", True, site=site))
                slice_approval["approved_commit"] = "b" * 40
                planctl.write_plan(slice_path, meta, "Synthetic approval fixture\n")
                self.assertEqual(1, planctl.validate_wave(self.root, "W7", True, site=site))

    def test_generate_destination_is_explicit_and_default_is_unchanged(self) -> None:
        site = self.root / ".local/owned"
        with patch.object(planctl.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout="")) as run:
            self.assertEqual(0, planctl.generate_review(self.root, output=site))
            self.assertEqual(["--output", str(site)], run.call_args.args[0][-2:])
            self.assertEqual(self.root, Path(run.call_args.args[0][3]))
            planctl.generate_review(self.root)
            self.assertNotIn("--output", run.call_args.args[0])
            self.assertNotIn("stdout", run.call_args.kwargs)
            run.return_value = subprocess.CompletedProcess([], 4, stdout="generation error context\n")
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertEqual(4, planctl.generate_review(self.root, output=site))
            self.assertIn("generation error context", error.getvalue())


if __name__ == "__main__":
    unittest.main()
