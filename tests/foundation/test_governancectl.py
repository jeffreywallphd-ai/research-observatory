from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_stale_derived_timestamp_does_not_change_legacy_fingerprint(self) -> None:
        task = {
            "id": "CAP-01.S01.T01",
            "capability_id": "CAP-01",
            "slice_id": "CAP-01.S01",
            "title": "Fixture task",
            "status": "NOT_STARTED",
            "dependencies": [],
            "priority": "P1",
            "wave": "W1",
            "deployment_profiles": ["LOC"],
            "platform_targets": ["windows-x64"],
        }
        data = {
            "control_plane": {"recovery_holds": []},
            "wave_amendments": [],
            "waves": [
                {
                    "id": "W1",
                    "activation_gate": None,
                    "approval": {"status": "APPROVED"},
                    "campaign": {"status": "ACTIVE"},
                    "completion": {"status": "PENDING"},
                }
            ],
            "release_gates": [{"id": "G1", "after_wave": "W1", "status": "PENDING", "unlocks_waves": ["W2"]}],
            "capabilities": [
                {
                    "id": "CAP-01",
                    "slices": [
                        {
                            "id": "CAP-01.S01",
                            "wave": "W1",
                            "status": "NOT_STARTED",
                            "completion": {"status": "PENDING"},
                            "depends_on": [],
                            "tasks": [task],
                        }
                    ],
                }
            ],
        }

        with patch.object(
            governancectl.taskctl,
            "utc_now",
            side_effect=["2026-08-26T10:00:00+00:00", "2026-08-26T10:00:01+00:00"],
        ):
            first = governancectl.legacy_projection(
                REPO / "planning" / "backlog.yaml",
                governancectl.fresh_index(data),
                profile="LOC",
                platform="windows-x64",
            )
            second = governancectl.legacy_projection(
                REPO / "planning" / "backlog.yaml",
                governancectl.fresh_index(data),
                profile="LOC",
                platform="windows-x64",
            )

        self.assertEqual(first, second)

    def test_repository_root_rejects_junction_or_reparse_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            planning = root / "planning"
            (root / ".git").mkdir(parents=True)
            planning.mkdir()
            (planning / "backlog.yaml").write_text("schemaVersion: '1.0'\n", encoding="utf-8")
            real_isjunction = getattr(os.path, "isjunction", lambda _path: False)

            def redirected(path: os.PathLike[str] | str) -> bool:
                return Path(path) == planning or real_isjunction(path)

            with (
                patch.object(os.path, "isjunction", redirected, create=True),
                self.assertRaisesRegex(SystemExit, "redirected"),
            ):
                governancectl.repository_root(str(root))

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
