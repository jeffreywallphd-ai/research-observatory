from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import governancectl  # noqa: E402


class GovernancectlTests(unittest.TestCase):
    def test_recovery_hold_has_read_only_precedence(self) -> None:
        data = {
            "control_plane": {
                "recovery_holds": [
                    {
                        "id": "HOLD-W1-TEST",
                        "status": "ACTIVE",
                        "recovery_request_id": "GRR-TEST",
                        "target_wave": "W1",
                        "bootstrap": {"id": "GRR-TEST.B00", "status": "APPROVED"},
                    }
                ]
            },
            "waves": [],
            "wave_amendments": [],
            "release_gates": [],
        }

        action, program = governancectl.project_next_action(
            data,
            {},
            {},
            {},
            {},
            profile="LOC",
            platform="windows-x64",
        )

        self.assertEqual("RECOVERY_INTERRUPTED", program["state"])
        self.assertEqual("recovery-hold", action["category"])
        self.assertEqual("inspect-recovery", action["action"])
        self.assertEqual(0, action["riskTier"])
        self.assertEqual("read-only", action["effect"])
        self.assertFalse(action["approvalRequired"])
        self.assertIn("recoveryctl.py --repo . status GRR-TEST", action["command"])

    def test_legacy_categories_are_small_and_stable(self) -> None:
        cases = {
            "STOPPED AT GOVERNANCE RECOVERY GRR-1": "recovery-hold",
            "STOPPED AT WAVE AMENDMENT W1.A01": "amendment",
            "STOPPED AT RELEASE GATE G1": "release-gate",
            "STOPPED AT PRE-WAVE APPROVAL: W1": "wave-approval",
            "WAVE IMPLEMENTATION COMPLETE: W1": "wave",
            "id: CAP-02.S04.T03\nstatus: READY": "task",
        }
        for output, expected in cases.items():
            with self.subTest(output=output):
                self.assertEqual(expected, governancectl.legacy_category(output))

    def test_current_repository_shadow_command_is_read_only_json(self) -> None:
        backlog = REPO / "planning" / "backlog.yaml"
        before = backlog.read_bytes()
        before_mtime = backlog.stat().st_mtime_ns

        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "tools" / "governancectl.py"),
                "--repo",
                str(REPO),
                "next",
                "--shadow",
                "--json",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
        document = json.loads(result.stdout)

        self.assertEqual("governance-next-action-shadow", document["documentType"])
        self.assertEqual("shadow", document["mode"])
        self.assertEqual("advisory-only", document["authority"])
        self.assertFalse(document["mutationPerformed"])
        self.assertEqual(hashlib.sha256(before).hexdigest(), document["source"]["sha256"])
        self.assertTrue(document["source"]["unchanged"])
        self.assertIn(document["decision"]["riskTier"], range(4))
        self.assertIn("category", document["shadowAgreement"])
        self.assertEqual(before, backlog.read_bytes())
        self.assertEqual(before_mtime, backlog.stat().st_mtime_ns)

    def test_command_requires_explicit_shadow_json_contract(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "tools" / "governancectl.py"),
                "--repo",
                str(REPO),
                "next",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("next --shadow --json", result.stderr)


if __name__ == "__main__":
    unittest.main()
