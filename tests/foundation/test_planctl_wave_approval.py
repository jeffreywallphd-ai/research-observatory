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

from plan_review_site import build_site  # noqa: E402
from planctl import approve, approve_wave, frontmatter, write_plan  # noqa: E402


class PlanctlWaveApprovalTests(unittest.TestCase):
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

    def test_one_wave_approval_binds_every_capability_and_slice_at_one_commit(self) -> None:
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
                        "decisions": [],
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
            self.assertEqual(["CAP-02.S01", "CAP-03.S01"], wave_approval["slice_ids"])
            for capability_id in ("CAP-02", "CAP-03"):
                meta, _ = frontmatter(
                    root / "planning" / "slice-plans" / capability_id / f"{capability_id}.S01-slice.md"
                )
                self.assertEqual("approved", meta["status"])
                self.assertEqual(commit, meta["approval"]["approved_commit"])

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
