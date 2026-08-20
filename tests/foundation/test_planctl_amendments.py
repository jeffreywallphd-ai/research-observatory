from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from planctl import approve_ecr, ecr_validation_errors  # noqa: E402


class PlanctlAmendmentTests(unittest.TestCase):
    def _copy_ecr_fixture(self, root: Path, *, include_approval: bool) -> Path:
        shutil.copytree(
            REPO / "planning" / "enabler-change-requests",
            root / "planning" / "enabler-change-requests",
        )
        approvals = root / "planning" / "wave-amendment-approvals"
        approvals.mkdir(parents=True)
        shutil.copy2(
            REPO / "planning" / "wave-amendment-approvals" / "wave-amendment-approval.schema.json",
            approvals / "wave-amendment-approval.schema.json",
        )
        shutil.copy2(
            REPO / "planning" / "wave-amendment-approvals" / "W1.A01.json",
            approvals / "W1.A01.json",
        )
        draft = root / "approval-draft.json"
        shutil.copy2(REPO / "planning" / "wave-amendment-approvals" / "W1.A02.json", draft)
        if include_approval:
            shutil.copy2(draft, approvals / "W1.A02.json")
        return draft

    def test_repository_ecr_approval_is_exact_commit_and_history_bound(self) -> None:
        self.assertEqual([], ecr_validation_errors(REPO, "ECR-0001", require_approved=True))

    def test_committed_approval_rewrite_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy_ecr_fixture(root, include_approval=True)
            approval_path = root / "planning" / "wave-amendment-approvals" / "W1.A02.json"
            introduced_payload = approval_path.read_bytes()
            record = json.loads(introduced_payload)
            record["decision"] = "Rewritten after approval."
            approval_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

            def fake_blob(_root: Path, _commit: str, relative: str) -> bytes | None:
                if relative == "planning/wave-amendment-approvals/W1.A02.json":
                    return introduced_payload
                path = root.joinpath(*Path(relative).parts)
                return path.read_bytes() if path.exists() else None

            with (
                patch("planctl._authority_history_errors", return_value=[]),
                patch("planctl._git_commit_exists", return_value=True),
                patch("planctl._git_is_ancestor", return_value=True),
                patch("planctl._approval_introduction_commit", return_value="6" * 40),
                patch("planctl._git_blob", side_effect=fake_blob),
            ):
                errors = ecr_validation_errors(root, "ECR-0001", require_approved=True)

            self.assertTrue(any("changed after its introduction commit" in error for error in errors), errors)

    def test_future_approval_is_exclusive_create_and_duplicate_is_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = self._copy_ecr_fixture(root, include_approval=False)
            packet_commit = "57d73bcf314ea6aab38b8056ead118d6ef270921"

            def fake_blob(_root: Path, _commit: str, relative: str) -> bytes | None:
                path = root.joinpath(*Path(relative).parts)
                return path.read_bytes() if path.exists() else None

            def fake_run(command, **_kwargs):
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return subprocess.CompletedProcess(command, 0, stdout=packet_commit + "\n", stderr="")
                if command[:3] == ["git", "status", "--porcelain"]:
                    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
                raise AssertionError(f"unexpected subprocess: {command}")

            with (
                patch("planctl._authority_history_errors", return_value=[]),
                patch("planctl._git_commit_exists", return_value=True),
                patch("planctl._git_blob", side_effect=fake_blob),
                patch("planctl.subprocess.run", side_effect=fake_run),
            ):
                destination = approve_ecr(
                    root,
                    "ECR-0001",
                    record_path=draft,
                    approver="repository-owner",
                    commit=packet_commit,
                )
                created = destination.read_bytes()
                with self.assertRaisesRegex(ValueError, "duplicate approval is forbidden"):
                    approve_ecr(
                        root,
                        "ECR-0001",
                        record_path=draft,
                        approver="repository-owner",
                        commit=packet_commit,
                    )

            self.assertEqual(draft.read_bytes(), created)
            self.assertEqual(created, destination.read_bytes())

    def test_approved_validation_rejects_missing_append_only_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy_ecr_fixture(root, include_approval=False)
            with patch("planctl._authority_history_errors", return_value=[]):
                errors = ecr_validation_errors(root, "ECR-0001", require_approved=True)
            self.assertIn(
                "ECR has no immutable approval record: planning/wave-amendment-approvals/W1.A02.json",
                errors,
            )


if __name__ == "__main__":
    unittest.main()
