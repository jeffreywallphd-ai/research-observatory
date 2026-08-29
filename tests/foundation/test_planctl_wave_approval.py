from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from plan_review_site import build_site, delivery_status, status_stack  # noqa: E402
from planctl import approve, approve_wave, frontmatter, scaffold_capability, scaffold_slice, write_plan  # noqa: E402


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

            self.assertIn("## 0A. Initiation assessment and planning adaptation", capability_body)
            self.assertIn("15% technical-debt refactoring limit", capability_body)
            self.assertIn("route major refactoring outside initiation planning", capability_body)
            self.assertIn("applicable capability/Wave initiation assessment", slice_body)
            self.assertIn("major refactoring is outside initiation planning", slice_body)

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
