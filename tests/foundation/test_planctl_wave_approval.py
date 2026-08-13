from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from planctl import approve, frontmatter, write_plan  # noqa: E402


class PlanctlWaveApprovalTests(unittest.TestCase):
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
