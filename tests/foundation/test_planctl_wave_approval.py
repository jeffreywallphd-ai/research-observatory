from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import time
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from capability_plan_check import (  # noqa: E402
    initiation_assessment_errors,
    wave_initiation_rollup_errors,
)
from plan_review_site import build_site, delivery_status, status_stack  # noqa: E402
from planctl import (  # noqa: E402
    approve,
    approve_wave,
    frontmatter,
    scaffold_capability,
    scaffold_slice,
    validate_wave,
    write_plan,
)


def valid_initiation_assessment() -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    task = {"id": "CAP-20.S01.T01", "title": "Build product work"}
    capability = {
        "id": "CAP-20",
        "title": "New capability",
        "slices": [{"id": "CAP-20.S01", "title": "First product slice", "wave": "W2", "tasks": [task]}],
    }
    meta: dict[str, Any] = {
        "planning_policy_version": "initiation-assessment-1.0",
        "initiation_assessment": {
            "policy_version": "1.0",
            "assessed_at": "2026-08-29T18:00:00Z",
            "estimation_unit": "relative-work-unit",
            "implementation_baseline": "The tested boundary works but needs bounded hardening",
            "vision_architecture_best_practice_fit": "The proposed outcome remains aligned with the Vision",
            "planned_items": [{"work_id": task["id"], "effort": 10}],
            "refactoring_items": [
                {
                    "id": "CAP-20.S01.T01/refactor-01",
                    "work_id": task["id"],
                    "effort": 1,
                    "changes_existing_implementation": True,
                    "introduced_in_wave": "W2",
                    "major_refactor": False,
                    "disposition": "included",
                    "description": "Strengthen an existing boundary needed by the new product work",
                }
            ],
            "major_refactor_disposition": "None identified",
            "wave_refreshes": [
                {
                    "wave": "W2",
                    "assessed_at": "2026-08-29T18:00:00Z",
                    "material_changes": "Initial capability assessment",
                    "plan_adaptations": "No adaptation required",
                    "support_improvements": "Strengthen the existing boundary",
                    "major_refactor_disposition": "None identified",
                }
            ],
        },
    }
    body = "# CAP-20\n\n## 0A. Initiation assessment and planning adaptation\n\nAssessment.\n"
    backlog = {
        "waves": [{"id": "W2", "approval": {"status": "PENDING"}}],
        "capabilities": [capability],
    }
    return meta, body, capability, backlog


class PlanctlWaveApprovalTests(unittest.TestCase):
    def test_new_plans_include_prospective_initiation_assessment_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            slice_ = {
                "id": "CAP-20.S01",
                "title": "First product slice",
                "wave": "W2",
                "tasks": [{"id": "CAP-20.S01.T01", "title": "Build product work"}],
            }
            capability = {"id": "CAP-20", "title": "New capability", "slices": [slice_]}

            capability_path = scaffold_capability(root, capability)
            slice_path = scaffold_slice(root, capability, slice_)
            capability_body = capability_path.read_text(encoding="utf-8")
            slice_body = slice_path.read_text(encoding="utf-8")
            capability_meta, _ = frontmatter(capability_path)

            self.assertIn("## 0A. Initiation assessment and planning adaptation", capability_body)
            self.assertIn("recomputes the capability and deduplicated Wave R <= 0.15 * P bounds", capability_body)
            self.assertIn("route major refactoring outside initiation planning", capability_body)
            self.assertIn("applicable capability/Wave initiation assessment", slice_body)
            self.assertIn("major refactoring is outside initiation planning", slice_body)
            self.assertEqual("initiation-assessment-1.0", capability_meta["planning_policy_version"])
            self.assertIsNone(capability_meta["initiation_assessment"])

    def test_structured_initiation_assessment_recomputes_bounded_budget(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        self.assertEqual([], initiation_assessment_errors(meta, body, capability, "W2"))
        self.assertEqual([], wave_initiation_rollup_errors([(capability["id"], meta, capability)], "W2"))

    def test_missing_assessment_or_wave_refresh_is_rejected_prospectively(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        missing = initiation_assessment_errors({}, body, capability, "W2")
        self.assertTrue(any("initiation_assessment must be completed" in error for error in missing))

        meta["initiation_assessment"]["wave_refreshes"] = []
        missing_refresh = initiation_assessment_errors(meta, body, capability, "W2")
        self.assertTrue(any("missing initiation assessment refresh for W2" in error for error in missing_refresh))

    def test_initial_assessment_requires_baseline_and_product_fit_narratives(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        assessment = meta["initiation_assessment"]
        assessment["implementation_baseline"] = ""
        assessment["vision_architecture_best_practice_fit"] = ""

        errors = initiation_assessment_errors(meta, body, capability, "W2")
        self.assertTrue(any("implementation_baseline is required" in error for error in errors))
        self.assertTrue(any("vision_architecture_best_practice_fit is required" in error for error in errors))

    def test_refactoring_over_fifteen_percent_is_rejected_at_capability_and_wave_scope(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        assessment = meta["initiation_assessment"]
        assessment["refactoring_items"][0]["effort"] = 2

        errors = initiation_assessment_errors(meta, body, capability, "W2")
        self.assertTrue(any("capability refactoring budget exceeds 15%" in error for error in errors))
        self.assertTrue(any("refactoring budget exceeds 15%" in error for error in errors))

    def test_fifteen_percent_boundary_is_exact_without_prescribing_estimate_precision(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        assessment = meta["initiation_assessment"]
        assessment["refactoring_items"][0]["effort"] = "1.5"
        self.assertEqual([], initiation_assessment_errors(meta, body, capability, "W2"))

        assessment["refactoring_items"][0]["effort"] = "1.5000001"
        errors = initiation_assessment_errors(meta, body, capability, "W2")
        self.assertTrue(any("capability refactoring budget exceeds 15%" in error for error in errors))
        self.assertTrue(any("W2 refactoring budget exceeds 15%" in error for error in errors))

    def test_included_refactoring_cannot_be_shifted_to_an_unrelated_wave_denominator(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        capability["slices"].append(
            {
                "id": "CAP-20.S02",
                "title": "Later product slice",
                "wave": "W3",
                "tasks": [{"id": "CAP-20.S02.T01", "title": "Later product work"}],
            }
        )
        assessment = meta["initiation_assessment"]
        assessment["planned_items"].append({"work_id": "CAP-20.S02.T01", "effort": 100})
        assessment["refactoring_items"][0]["effort"] = 10
        assessment["refactoring_items"][0]["introduced_in_wave"] = "W3"
        assessment["wave_refreshes"].append(
            {
                "wave": "W3",
                "assessed_at": "2026-08-29T18:00:00Z",
                "material_changes": "Later slice is now being planned",
                "plan_adaptations": "No adaptation required",
                "support_improvements": "None",
                "major_refactor_disposition": "None identified",
            }
        )

        w2_errors = initiation_assessment_errors(meta, body, capability, "W2")
        w3_errors = initiation_assessment_errors(meta, body, capability, "W3")
        self.assertTrue(any("must be charged to the Wave containing work_id" in error for error in w2_errors))
        self.assertTrue(any("must be charged to the Wave containing work_id" in error for error in w3_errors))

    def test_major_refactor_requires_disposition_and_cannot_be_included(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        assessment = meta["initiation_assessment"]
        assessment.pop("major_refactor_disposition")
        assessment["refactoring_items"][0]["major_refactor"] = True

        errors = initiation_assessment_errors(meta, body, capability, "W2")
        self.assertTrue(any("major_refactor_disposition is required" in error for error in errors))
        self.assertTrue(any("major refactor cannot be included" in error for error in errors))

    def test_refresh_requires_planning_narrative_and_rollup_rejects_duplicate_allocation(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        refresh = meta["initiation_assessment"]["wave_refreshes"][0]
        refresh["plan_adaptations"] = ""
        errors = initiation_assessment_errors(meta, body, capability, "W2")
        self.assertTrue(any("plan_adaptations is required" in error for error in errors))

        second_meta = deepcopy(meta)
        second_capability = deepcopy(capability)
        second_capability["id"] = "CAP-21"
        rollup = wave_initiation_rollup_errors(
            [("CAP-20", meta, capability), ("CAP-21", second_meta, second_capability)], "W2"
        )
        self.assertTrue(
            any("refactoring allocation CAP-20.S01.T01/refactor-01 is counted more than once" in e for e in rollup)
        )

    def test_historical_approved_wave_compatibility_does_not_require_backfill(self) -> None:
        _meta, _body, capability, _backlog = valid_initiation_assessment()
        self.assertEqual([], initiation_assessment_errors({}, "", capability, "W1"))
        self.assertEqual([], wave_initiation_rollup_errors([], "W1"))

    def test_assessment_uses_reviewed_packet_without_a_second_git_history_controller(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        assessment = meta["initiation_assessment"]
        self.assertNotIn("baseline_commit", assessment)
        self.assertNotIn("scope_sha256", assessment)
        self.assertEqual([], initiation_assessment_errors(meta, body, capability, "W2"))

    def test_atomic_task_granularity_and_positive_effort_prevent_double_counting(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        assessment = meta["initiation_assessment"]
        assessment["planned_items"].append({"work_id": "CAP-20.S01", "effort": 10})
        assessment["refactoring_items"][0]["effort"] = 0

        errors = initiation_assessment_errors(meta, body, capability, "W2")
        self.assertTrue(any("work_id must name an atomic task" in error for error in errors))
        self.assertTrue(any("effort must be a positive finite number" in error for error in errors))

    def test_existing_wave_validation_requires_the_prospective_assessment_rollup(self) -> None:
        meta, body, capability, _backlog = valid_initiation_assessment()
        meta.update(
            decisions=[{"id": "CAP-20-D01", "binding_waves": ["W2"]}],
            capability_id="CAP-20",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "planning").mkdir()
            backlog = {
                "waves": [{"id": "W2", "approval": {"status": "PENDING"}}],
                "capabilities": [capability],
            }
            (root / "planning" / "backlog.yaml").write_text(yaml.safe_dump(backlog, sort_keys=False), encoding="utf-8")
            plan_path = root / "planning" / "capability-plans" / "CAP-20.md"
            write_plan(plan_path, meta, body)

            successful_check = subprocess.CompletedProcess([], 0, stdout="", stderr="")
            with (
                patch("planctl.run_validator", return_value=0),
                patch("planctl.subprocess.run", return_value=successful_check),
            ):
                self.assertEqual(0, validate_wave(root, "W2", False))
                missing_meta = deepcopy(meta)
                missing_meta.pop("initiation_assessment")
                write_plan(plan_path, missing_meta, body)
                with patch("planctl.sys.stderr"):
                    self.assertEqual(1, validate_wave(root, "W2", False))

    def test_review_site_stacks_plan_decision_and_authoritative_delivery_status(self) -> None:
        self.assertEqual("not-started", delivery_status([{"status": "READY"}, {"status": "NOT_STARTED"}]))
        self.assertEqual("in-progress", delivery_status([{"status": "DONE"}, {"status": "IN_PROGRESS"}]))
        self.assertEqual("completed", delivery_status([{"status": "DONE"}, {"status": "DONE"}]))
        self.assertEqual("completed", delivery_status([], {"status": "APPROVED"}))
        badges = status_stack("approved", "in-progress")
        self.assertIn('class="status-stack"', badges)
        self.assertLess(badges.index("Approved"), badges.index("In Progress"))

    def test_review_site_rebuilds_are_serialized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "planning" / "review-site"
            active = 0
            maximum_active = 0
            counter_lock = threading.Lock()

            def fake_build(_repo, _output, _selected_capability=None):
                nonlocal active, maximum_active
                with counter_lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                time.sleep(0.1)
                with counter_lock:
                    active -= 1
                return {}

            with patch("plan_review_site._build_site_unlocked", side_effect=fake_build):
                first = threading.Thread(target=build_site, args=(root, output))
                second = threading.Thread(target=build_site, args=(root, output))
                first.start()
                second.start()
                first.join(timeout=5)
                second.join(timeout=5)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(1, maximum_active)
            self.assertFalse((output.parent / ".review-site.generation.lock").exists())

    def test_one_wave_approval_binds_exact_wave_decisions_and_slices_at_one_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "planning").mkdir()
            commit = "a" * 40
            backlog: dict[str, Any] = {
                "waves": [
                    {
                        "id": "W1",
                        "approval": {
                            "status": "PENDING",
                            "approved_by": None,
                            "approved_at": None,
                            "approved_commit": None,
                            "capability_ids": [],
                            "decision_ids": [],
                            "slice_ids": [],
                            "notes": None,
                        },
                    }
                ],
                "capabilities": [],
            }
            pending = {"status": "pending", "approved_by": None, "approved_at": None, "approved_commit": None}
            for number in ("02", "03"):
                capability_id = f"CAP-{number}"
                slice_id = f"{capability_id}.S01"
                backlog["capabilities"].append(
                    {"id": capability_id, "slices": [{"id": slice_id, "wave": "W1", "title": "Slice"}]}
                )
                write_plan(
                    root / "planning" / "capability-plans" / f"{capability_id}.md",
                    {
                        "capability_id": capability_id,
                        "status": "proposed",
                        "decision_completion": "complete",
                        "open_blocking_decisions": [],
                        "decisions": [
                            {
                                "id": f"{capability_id}-D01",
                                "status": "accepted",
                                "selected_option": "Selected",
                                "binding_waves": ["W1"],
                            }
                        ],
                        "approval": dict(pending),
                    },
                    "# Capability\n",
                )
                write_plan(
                    root / "planning" / "slice-plans" / capability_id / f"{slice_id}-slice.md",
                    {
                        "capability_id": capability_id,
                        "slice_id": slice_id,
                        "wave": "W1",
                        "status": "proposed",
                        "approval": dict(pending),
                    },
                    "# Slice\n",
                )
            (root / "planning" / "backlog.yaml").write_text(yaml.safe_dump(backlog, sort_keys=False), encoding="utf-8")

            def fake_run(command, **_kwargs):
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return subprocess.CompletedProcess(command, 0, stdout=commit + "\n", stderr="")
                if command[:3] == ["git", "status", "--porcelain"]:
                    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with (
                patch("planctl.subprocess.run", side_effect=fake_run),
                patch("planctl.generate_review", return_value=0),
                patch("planctl.validate_wave", return_value=0),
            ):
                approve_wave(root, "W1", "human:reviewer", commit, "whole Wave reviewed")

            approved = yaml.safe_load((root / "planning" / "backlog.yaml").read_text(encoding="utf-8"))
            wave_approval = approved["waves"][0]["approval"]
            self.assertEqual("APPROVED", wave_approval["status"])
            self.assertEqual(["CAP-02", "CAP-03"], wave_approval["capability_ids"])
            self.assertEqual(["CAP-02-D01", "CAP-03-D01"], wave_approval["decision_ids"])
            self.assertEqual(["CAP-02.S01", "CAP-03.S01"], wave_approval["slice_ids"])
            for capability_id in ("CAP-02", "CAP-03"):
                capability_meta, _ = frontmatter(root / "planning" / "capability-plans" / f"{capability_id}.md")
                self.assertEqual("proposed", capability_meta["status"])
                meta, _ = frontmatter(
                    root / "planning" / "slice-plans" / capability_id / f"{capability_id}.S01-slice.md"
                )
                self.assertEqual("approved", meta["status"])
                self.assertEqual(commit, meta["approval"]["approved_commit"])

    def test_wave_approval_rejects_unclassified_capability_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "planning").mkdir()
            commit = "a" * 40
            backlog = {
                "waves": [{"id": "W1", "approval": {"status": "PENDING"}}],
                "capabilities": [{"id": "CAP-02", "slices": [{"id": "CAP-02.S01", "wave": "W1", "title": "Slice"}]}],
            }
            write_plan(
                root / "planning" / "capability-plans" / "CAP-02.md",
                {
                    "capability_id": "CAP-02",
                    "status": "proposed",
                    "decision_completion": "complete",
                    "open_blocking_decisions": [],
                    "decisions": [{"id": "CAP-02-D01", "status": "accepted", "selected_option": "Selected"}],
                },
                "# Capability\n",
            )
            write_plan(
                root / "planning" / "slice-plans" / "CAP-02" / "CAP-02.S01-slice.md",
                {"capability_id": "CAP-02", "slice_id": "CAP-02.S01", "wave": "W1", "status": "proposed"},
                "# Slice\n",
            )
            (root / "planning" / "backlog.yaml").write_text(yaml.safe_dump(backlog, sort_keys=False), encoding="utf-8")

            def fake_run(command, **_kwargs):
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return subprocess.CompletedProcess(command, 0, stdout=commit + "\n", stderr="")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with (
                patch("planctl.subprocess.run", side_effect=fake_run),
                self.assertRaisesRegex(ValueError, "lack explicit Wave classification"),
            ):
                approve_wave(root, "W1", "human:reviewer", commit)

    def test_repeated_wave_approval_fails_before_git_and_preserves_every_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            planning = root / "planning"
            planning.mkdir()
            backlog_path = planning / "backlog.yaml"
            capability_path = planning / "capability-plans" / "CAP-02.md"
            slice_path = planning / "slice-plans" / "CAP-02" / "CAP-02.S01-slice.md"
            approval = {
                "status": "APPROVED",
                "approved_by": "human:original",
                "approved_at": "2026-08-01T00:00:00+00:00",
                "approved_commit": "1" * 40,
                "capability_ids": ["CAP-02"],
                "decision_ids": ["CAP-02-D01"],
                "slice_ids": ["CAP-02.S01"],
                "notes": None,
            }
            backlog = {
                "waves": [{"id": "W1", "approval": approval}],
                "capabilities": [{"id": "CAP-02", "slices": [{"id": "CAP-02.S01", "wave": "W1", "title": "Slice"}]}],
            }
            backlog_path.write_text(yaml.safe_dump(backlog, sort_keys=False), encoding="utf-8")
            write_plan(capability_path, {"capability_id": "CAP-02"}, "# Capability\n")
            write_plan(slice_path, {"slice_id": "CAP-02.S01", "wave": "W1"}, "# Slice\n")
            before = {path: path.read_bytes() for path in (backlog_path, capability_path, slice_path)}

            with (
                patch("planctl.subprocess.run") as run,
                self.assertRaisesRegex(ValueError, "already approved.*append-only ECR/Wave-amendment"),
            ):
                approve_wave(root, "W1", "human:second", "2" * 40)

            run.assert_not_called()
            self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_capability_decisions_are_approved_once_and_slice_plans_progress_by_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capability = root / "planning" / "capability-plans" / "CAP-07.md"
            wave_one = root / "planning" / "slice-plans" / "CAP-07" / "CAP-07.S01-first.md"
            wave_three = root / "planning" / "slice-plans" / "CAP-07" / "CAP-07.S02-later.md"
            pending = {"status": "pending", "approved_by": None, "approved_at": None, "approved_commit": None}
            write_plan(
                capability,
                {
                    "capability_id": "CAP-07",
                    "status": "proposed",
                    "decision_completion": "complete",
                    "open_blocking_decisions": [],
                    "decisions": [],
                    "approval": dict(pending),
                },
                "# Capability\n",
            )
            for path, wave in ((wave_one, "W1"), (wave_three, "W3")):
                write_plan(
                    path,
                    {
                        "capability_id": "CAP-07",
                        "slice_id": path.name.split("-first")[0].split("-later")[0],
                        "wave": wave,
                        "status": "proposed",
                        "approval": dict(pending),
                    },
                    "# Slice\n",
                )

            with patch("planctl.generate_review", return_value=0), patch("planctl.validate", return_value=0):
                approve(root, "CAP-07", None, "human:reviewer", "1" * 40, "W1")

            capability_meta, _ = frontmatter(capability)
            wave_one_meta, _ = frontmatter(wave_one)
            wave_three_meta, _ = frontmatter(wave_three)
            self.assertEqual("approved", capability_meta["status"])
            self.assertEqual("1" * 40, capability_meta["approval"]["approved_commit"])
            self.assertEqual("approved", wave_one_meta["status"])
            self.assertEqual("proposed", wave_three_meta["status"])

            with patch("planctl.generate_review", return_value=0), patch("planctl.validate", return_value=0):
                approve(root, "CAP-07", None, "human:reviewer", "3" * 40, "W3")

            capability_meta, _ = frontmatter(capability)
            wave_three_meta, _ = frontmatter(wave_three)
            self.assertEqual("1" * 40, capability_meta["approval"]["approved_commit"])
            self.assertEqual("approved", wave_three_meta["status"])
            self.assertEqual("3" * 40, wave_three_meta["approval"]["approved_commit"])


if __name__ == "__main__":
    unittest.main()
