from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import gcrctl  # noqa: E402
import taskctl  # noqa: E402


class GcrctlTests(unittest.TestCase):
    def git(self, repo: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def write_json(self, repo: Path, relative: str, document: dict) -> Path:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return path

    def taskctl_at_commit(self, commit: str) -> types.ModuleType:
        payload = taskctl.git_blob(REPO, commit, "tools/taskctl.py")
        self.assertIsNotNone(payload)
        module = types.ModuleType(f"taskctl_{commit[:8]}")
        module.__file__ = str(REPO / "tools/taskctl.py")
        exec(compile(payload or b"", module.__file__, "exec"), module.__dict__)
        return module

    def fixture(self, temporary: str) -> tuple[Path, str, str, dict]:
        repo = Path(temporary)
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "gcr@example.test")
        self.git(repo, "config", "user.name", "GCR Test")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(repo, "checkout", "-b", gcrctl.BRANCH)
        shutil.copy2(REPO / ".gitignore", repo / ".gitignore")
        schema = repo / gcrctl.RUNTIME_SCHEMA_PATH
        schema.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / gcrctl.RUNTIME_SCHEMA_PATH, schema)
        shutil.copy2(REPO / gcrctl.TRANSACTION_SCHEMA_PATH, repo / gcrctl.TRANSACTION_SCHEMA_PATH)
        self.write_json(repo, gcrctl.APPROVAL_PATH, {"fixture": True})
        backlog: dict[str, Any] = {
            "control_plane": {
                "revision": 6,
                "minimum_tool_revision": 6,
                "active_amendment": None,
                "recovery_holds": [{"id": "HOLD-W1-GRR-0002", "status": "ACTIVE"}],
            }
        }
        (repo / "planning/backlog.yaml").write_text(yaml.safe_dump(backlog, sort_keys=False), encoding="utf-8")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "approval base")
        base = self.git(repo, "rev-parse", "HEAD")
        controller = repo / "tools/gcrctl.py"
        controller.parent.mkdir(parents=True, exist_ok=True)
        controller.write_text("# bounded implementation\n", encoding="utf-8")
        self.git(repo, "add", "tools/gcrctl.py")
        self.git(repo, "commit", "-m", "candidate")
        candidate = self.git(repo, "rev-parse", "HEAD")
        trigger = repo / gcrctl.TRIGGER_PATH
        trigger.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / gcrctl.TRIGGER_PATH, trigger)
        packet = {
            "activationBoundary": {"controlRevision": 6},
            "acceptanceCriteria": ["criterion"],
            "bootstrapUnit": {"authorizedPaths": ["tools/gcrctl.py"]},
        }
        return repo, base, candidate, packet

    def evidence(self, repo: Path, base: str, candidate: str, packet: dict) -> str:
        relative = gcrctl.evidence_path_for("R01")
        self.write_json(
            repo,
            relative,
            {
                "schemaVersion": "1.0-control-recovery-evidence",
                "documentType": "governance-control-recovery-bootstrap-evidence",
                "controlRecoveryId": gcrctl.GCR_ID,
                "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
                "attemptId": "R01",
                "commit": candidate,
                "baseCommit": base,
                "branch": gcrctl.BRANCH,
                "triggerWitness": gcrctl.trigger_witness(),
                "changedFiles": ["tools/gcrctl.py"],
                "checks": [{"id": "focused", "command": "focused", "exitCode": 0, "result": "passed"}],
                "acceptanceCriteria": [
                    {"index": 1, "statement": packet["acceptanceCriteria"][0], "evidence": ["proved"]}
                ],
                "findingClosures": [],
                "unverifiedItems": [],
                "verificationSelection": {
                    "riskAnalysis": "Controller state transition risk.",
                    "selectedChecks": ["focused"],
                    "deferredCoverage": ["Wave qualification"],
                },
            },
        )
        return relative

    def approved_fixture(
        self,
        temporary: str,
        *,
        hidden_stage: str | None = None,
    ) -> tuple[Path, dict, str, str]:
        repo, base, candidate, packet = self.fixture(temporary)
        evidence_relative = self.evidence(repo, base, candidate, packet)
        submit = argparse.Namespace(
            repo=repo,
            agent=gcrctl.ACTOR,
            approval_commit=base,
            implementation_commit=candidate,
            evidence=evidence_relative,
        )
        with (
            patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
            patch.object(gcrctl, "current_boundary", return_value=(b"backlog", {})),
        ):
            gcrctl.freeze_submission(submit, remediation=False)
        state = json.loads((repo / gcrctl.STATE_PATH).read_text(encoding="utf-8"))
        if hidden_stage == "reviewed":
            (repo / "planning/hidden-reviewed.txt").write_text("hidden\n", encoding="utf-8")
            self.git(repo, "add", "planning/hidden-reviewed.txt")
        self.git(repo, "add", gcrctl.STATE_PATH, evidence_relative)
        self.git(repo, "commit", "-m", "reviewed state")
        reviewed_state = self.git(repo, "rev-parse", "HEAD")
        review_relative = gcrctl.review_path_for("R01")
        self.write_json(
            repo,
            review_relative,
            {
                "schemaVersion": "1.0-control-recovery-review",
                "documentType": "governance-control-recovery-bootstrap-review",
                "controlRecoveryId": gcrctl.GCR_ID,
                "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
                "attemptId": "R01",
                "candidateCommit": candidate,
                "reviewedStateCommit": reviewed_state,
                "reviewer": "independent-reviewer",
                "result": "approved",
                "evidence": state["currentSubmission"]["evidence"],
                "findings": [],
                "closures": [],
                "notes": "Approved isolated lifecycle.",
            },
        )
        review = argparse.Namespace(repo=repo, reviewer="independent-reviewer", ledger=review_relative)
        with patch.object(gcrctl, "load_authority", return_value=({}, packet, base)):
            gcrctl.command_review(review)
        if hidden_stage == "approved":
            (repo / "planning/hidden-approved.txt").write_text("hidden\n", encoding="utf-8")
            self.git(repo, "add", "planning/hidden-approved.txt")
        self.git(repo, "add", gcrctl.STATE_PATH, review_relative)
        self.git(repo, "commit", "-m", "approved state")
        return repo, packet, base, self.git(repo, "rev-parse", "HEAD")

    def write_adoption_evidence(self, repo: Path, approved_state: str) -> str:
        relative = "artifacts/evidence/governance-control-recovery/GCR-0001.B00.adoption.json"
        self.write_json(
            repo,
            relative,
            {
                "schemaVersion": "1.0-control-recovery-adoption-evidence",
                "documentType": "governance-control-recovery-adoption-evidence",
                "controlRecoveryId": gcrctl.GCR_ID,
                "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
                "reviewedStateCommit": approved_state,
                "triggerWitness": gcrctl.trigger_witness(),
                "predecessorRevision": 6,
                "successorRevision": 7,
                "expectedChangedFiles": ["planning/backlog.yaml", gcrctl.STATE_PATH],
                "checks": [{"id": "adoption", "command": "adoption", "exitCode": 0, "result": "passed"}],
                "unverifiedItems": [],
            },
        )
        return relative

    def adopt_approved_fixture(
        self,
        repo: Path,
        packet: dict,
        base: str,
        approved_state: str,
    ) -> str:
        adoption_relative = self.write_adoption_evidence(repo, approved_state)
        self.git(repo, "add", adoption_relative)
        self.git(repo, "commit", "-m", "adoption evidence")
        evidence_commit = self.git(repo, "rev-parse", "HEAD")
        args = argparse.Namespace(
            repo=repo,
            approved_state_commit=approved_state,
            evidence=adoption_relative,
            agent=gcrctl.ACTOR,
        )
        backlog_payload = (repo / gcrctl.BACKLOG_PATH).read_bytes()
        backlog_document = yaml.safe_load(backlog_payload)
        with (
            patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
            patch.object(gcrctl, "current_boundary", return_value=(backlog_payload, backlog_document)),
            patch.object(taskctl, "backlog_schema_errors", return_value=[]),
            patch.object(taskctl, "validate", return_value=[]),
        ):
            gcrctl.command_adopt(args)
        return evidence_commit

    def test_current_exact_authority_is_approved_and_witness_is_non_authoritative(self) -> None:
        approval, packet, introduction = gcrctl.load_authority(REPO)
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual(gcrctl.GCR_ID, packet["controlRecoveryId"])
        self.assertEqual(gcrctl.PACKET_COMMIT, approval["packet"]["commit"])
        self.assertEqual(gcrctl.trigger_witness(), approval["triggerWitness"])
        self.assertEqual("c34f8398adc54b3703b94daf7482faf9c09cfdfc", introduction)
        self.assertFalse(approval["triggerWitness"]["executionAuthority"])

    def test_real_git_submit_review_and_direct_child_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, base, candidate, packet = self.fixture(temporary)
            evidence_relative = self.evidence(repo, base, candidate, packet)
            submit = argparse.Namespace(
                repo=repo,
                agent=gcrctl.ACTOR,
                approval_commit=base,
                implementation_commit=candidate,
                evidence=evidence_relative,
            )
            with (
                patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                patch.object(gcrctl, "current_boundary", return_value=(b"backlog", {})),
            ):
                gcrctl.freeze_submission(submit, remediation=False)
            state = json.loads((repo / gcrctl.STATE_PATH).read_text(encoding="utf-8"))
            self.assertEqual("REVIEW", state["status"])
            self.assertEqual(candidate, state["currentSubmission"]["candidateCommit"])
            self.git(repo, "add", gcrctl.STATE_PATH, evidence_relative)
            self.git(repo, "commit", "-m", "reviewed state")
            reviewed_state = self.git(repo, "rev-parse", "HEAD")

            review_relative = gcrctl.review_path_for("R01")
            self.write_json(
                repo,
                review_relative,
                {
                    "schemaVersion": "1.0-control-recovery-review",
                    "documentType": "governance-control-recovery-bootstrap-review",
                    "controlRecoveryId": gcrctl.GCR_ID,
                    "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
                    "attemptId": "R01",
                    "candidateCommit": candidate,
                    "reviewedStateCommit": reviewed_state,
                    "reviewer": "independent-reviewer",
                    "result": "approved",
                    "evidence": state["currentSubmission"]["evidence"],
                    "findings": [],
                    "closures": [],
                    "notes": "Approved isolated lifecycle.",
                },
            )
            review = argparse.Namespace(repo=repo, reviewer="independent-reviewer", ledger=review_relative)
            with patch.object(gcrctl, "load_authority", return_value=({}, packet, base)):
                gcrctl.command_review(review)
            state = json.loads((repo / gcrctl.STATE_PATH).read_text(encoding="utf-8"))
            self.assertEqual("APPROVED", state["status"])
            self.assertIsNone(state["currentSubmission"])
            self.git(repo, "add", gcrctl.STATE_PATH, review_relative)
            self.git(repo, "commit", "-m", "approved state")
            approved_state = self.git(repo, "rev-parse", "HEAD")

            adoption_relative = "artifacts/evidence/governance-control-recovery/GCR-0001.B00.adoption.json"
            self.write_json(
                repo,
                adoption_relative,
                {
                    "schemaVersion": "1.0-control-recovery-adoption-evidence",
                    "documentType": "governance-control-recovery-adoption-evidence",
                    "controlRecoveryId": gcrctl.GCR_ID,
                    "bootstrapUnit": gcrctl.BOOTSTRAP_ID,
                    "reviewedStateCommit": approved_state,
                    "triggerWitness": gcrctl.trigger_witness(),
                    "predecessorRevision": 6,
                    "successorRevision": 7,
                    "expectedChangedFiles": ["planning/backlog.yaml", gcrctl.STATE_PATH],
                    "checks": [{"id": "adoption", "command": "adoption", "exitCode": 0, "result": "passed"}],
                    "unverifiedItems": [],
                },
            )
            self.git(repo, "add", adoption_relative)
            self.git(repo, "commit", "-m", "adoption evidence")
            adoption = argparse.Namespace(
                repo=repo,
                approved_state_commit=approved_state,
                evidence=adoption_relative,
                agent=gcrctl.ACTOR,
            )
            backlog_payload = (repo / "planning/backlog.yaml").read_bytes()
            backlog_document = yaml.safe_load(backlog_payload)
            with (
                patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                patch.object(gcrctl, "current_boundary", return_value=(backlog_payload, backlog_document)),
                patch.object(taskctl, "backlog_schema_errors", return_value=[]),
                patch.object(taskctl, "validate", return_value=[]),
            ):
                gcrctl.command_adopt(adoption)
            adopted_backlog = yaml.safe_load((repo / "planning/backlog.yaml").read_text(encoding="utf-8"))
            adopted_state = json.loads((repo / gcrctl.STATE_PATH).read_text(encoding="utf-8"))
            self.assertEqual(7, adopted_backlog["control_plane"]["revision"])
            self.assertEqual(6, adopted_backlog["control_plane"]["control_generations"][0]["predecessor_revision"])
            self.assertEqual("ADOPTION_FINALIZATION", adopted_state["status"])
            self.assertEqual(
                sorted(["planning/backlog.yaml", gcrctl.STATE_PATH]),
                sorted(self.git(repo, "diff", "--name-only", "HEAD", "--").splitlines()),
            )
            self.assertTrue(
                any(
                    "pending its exact finalization commit" in error
                    for error in taskctl.governance_control_generation_errors(adopted_backlog, repo)
                )
            )
            with self.assertRaisesRegex(SystemExit, "pending its exact finalization commit"):
                gcrctl.validate_state_history(repo, adopted_state, packet)
            self.git(repo, "add", gcrctl.BACKLOG_PATH, gcrctl.STATE_PATH)
            self.git(repo, "commit", "-m", "exact adoption finalization")
            self.assertEqual(
                [],
                taskctl.governance_control_adoption_finalization_errors(
                    repo,
                    adopted_state["adoption"]["evidence"]["commit"],
                    (repo / gcrctl.STATE_PATH).read_bytes(),
                    adopted_backlog["control_plane"]["control_generations"][0],
                ),
            )
            self.assertFalse(
                any(
                    "adoption finalization" in error
                    for error in taskctl.governance_control_generation_errors(adopted_backlog, repo)
                )
            )
            gcrctl.validate_state_history(repo, adopted_state, packet)
            evolved_backlog = yaml.safe_load((repo / gcrctl.BACKLOG_PATH).read_text(encoding="utf-8"))
            evolved_backlog["control_plane"]["revision"] = 8
            evolved_backlog["control_plane"]["minimum_tool_revision"] = 8
            (repo / gcrctl.BACKLOG_PATH).write_text(
                yaml.safe_dump(evolved_backlog, sort_keys=False),
                encoding="utf-8",
            )
            self.git(repo, "add", gcrctl.BACKLOG_PATH)
            self.git(repo, "commit", "-m", "lawful later control evolution")
            self.assertEqual(
                [],
                taskctl.governance_control_adoption_finalization_errors(
                    repo,
                    adopted_state["adoption"]["evidence"]["commit"],
                    (repo / gcrctl.STATE_PATH).read_bytes(),
                    adopted_backlog["control_plane"]["control_generations"][0],
                ),
            )
            self.assertFalse(
                any(
                    "adoption finalization" in error
                    for error in taskctl.governance_control_generation_errors(evolved_backlog, repo)
                )
            )
            gcrctl.validate_state_history(repo, adopted_state, packet)

    def test_adoption_denies_hidden_finalization_commit_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, packet, base, approved_state = self.approved_fixture(temporary)
            evidence_commit = self.adopt_approved_fixture(repo, packet, base, approved_state)
            hidden = repo / "planning/hidden-final-adoption.txt"
            hidden.write_text("hidden\n", encoding="utf-8")
            self.git(repo, "add", gcrctl.BACKLOG_PATH, gcrctl.STATE_PATH, "planning/hidden-final-adoption.txt")
            self.git(repo, "commit", "-m", "adoption finalization with hidden path")
            adopted_backlog = yaml.safe_load((repo / gcrctl.BACKLOG_PATH).read_text(encoding="utf-8"))
            adopted_state = json.loads((repo / gcrctl.STATE_PATH).read_text(encoding="utf-8"))
            errors = taskctl.governance_control_adoption_finalization_errors(
                repo,
                evidence_commit,
                (repo / gcrctl.STATE_PATH).read_bytes(),
                adopted_backlog["control_plane"]["control_generations"][0],
            )
            self.assertEqual(
                ["GCR-0001 adoption finalization commit is not the exact two-path transition"],
                errors,
            )
            self.assertIn(
                "GCR-0001 adoption finalization commit is not the exact two-path transition",
                taskctl.governance_control_generation_errors(adopted_backlog, repo),
            )
            r02_taskctl = self.taskctl_at_commit("22f9b46dd6772d2df615d3324cd1797f585385f8")
            self.assertIn(
                "GCR-0001 live adoption state/evidence does not match the adopted generation",
                r02_taskctl.governance_control_generation_errors(adopted_backlog, repo),
            )
            with self.assertRaisesRegex(SystemExit, "exact two-path transition"):
                gcrctl.validate_state_history(repo, adopted_state, packet)

    def test_adoption_denies_substituted_finalization_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, packet, base, approved_state = self.approved_fixture(temporary)
            evidence_commit = self.adopt_approved_fixture(repo, packet, base, approved_state)
            intermediate = repo / "planning/intermediate-final-adoption.txt"
            intermediate.write_text("intermediate\n", encoding="utf-8")
            self.git(repo, "add", "planning/intermediate-final-adoption.txt")
            self.git(repo, "commit", "-m", "substitute finalization parent")
            self.git(repo, "add", gcrctl.BACKLOG_PATH, gcrctl.STATE_PATH)
            self.git(repo, "commit", "-m", "late exact adoption pair")
            adopted_state = json.loads((repo / gcrctl.STATE_PATH).read_text(encoding="utf-8"))
            self.assertEqual(
                ["GCR-0001 adoption finalization is not the direct child of its evidence commit"],
                taskctl.governance_control_adoption_finalization_errors(
                    repo,
                    evidence_commit,
                    (repo / gcrctl.STATE_PATH).read_bytes(),
                    yaml.safe_load((repo / gcrctl.BACKLOG_PATH).read_text(encoding="utf-8"))["control_plane"][
                        "control_generations"
                    ][0],
                ),
            )
            with self.assertRaisesRegex(SystemExit, "not the direct child"):
                gcrctl.validate_state_history(repo, adopted_state, packet)

    def test_adoption_denies_hidden_evidence_commit_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, packet, base, approved_state = self.approved_fixture(temporary)
            adoption_relative = self.write_adoption_evidence(repo, approved_state)
            hidden = repo / "planning/unauthorized-hidden.txt"
            hidden.write_text("hidden\n", encoding="utf-8")
            self.git(repo, "add", adoption_relative, "planning/unauthorized-hidden.txt")
            self.git(repo, "commit", "-m", "evidence with hidden path")
            before_backlog = (repo / gcrctl.BACKLOG_PATH).read_bytes()
            before_state = (repo / gcrctl.STATE_PATH).read_bytes()
            args = argparse.Namespace(
                repo=repo,
                approved_state_commit=approved_state,
                evidence=adoption_relative,
                agent=gcrctl.ACTOR,
            )
            with (
                patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                self.assertRaisesRegex(SystemExit, "exact single-parent path/status delta"),
            ):
                gcrctl.command_adopt(args)
            self.assertEqual(before_backlog, (repo / gcrctl.BACKLOG_PATH).read_bytes())
            self.assertEqual(before_state, (repo / gcrctl.STATE_PATH).read_bytes())
            self.assertEqual([], gcrctl.transaction_artifacts_present(repo))

    def test_adoption_denies_hidden_state_paths_and_substituted_parent(self) -> None:
        for stage in ("reviewed", "approved"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                repo, packet, base, approved_state = self.approved_fixture(temporary, hidden_stage=stage)
                adoption_relative = self.write_adoption_evidence(repo, approved_state)
                self.git(repo, "add", adoption_relative)
                self.git(repo, "commit", "-m", "adoption evidence")
                args = argparse.Namespace(
                    repo=repo,
                    approved_state_commit=approved_state,
                    evidence=adoption_relative,
                    agent=gcrctl.ACTOR,
                )
                with (
                    patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                    self.assertRaisesRegex(SystemExit, "exact single-parent path/status delta"),
                ):
                    gcrctl.command_adopt(args)
                self.assertEqual([], gcrctl.transaction_artifacts_present(repo))

        with tempfile.TemporaryDirectory() as temporary:
            repo, packet, base, approved_state = self.approved_fixture(temporary)
            intermediate = repo / "planning/intermediate.txt"
            intermediate.write_text("intermediate\n", encoding="utf-8")
            self.git(repo, "add", "planning/intermediate.txt")
            self.git(repo, "commit", "-m", "substituted approved parent")
            substituted = self.git(repo, "rev-parse", "HEAD")
            adoption_relative = self.write_adoption_evidence(repo, substituted)
            self.git(repo, "add", adoption_relative)
            self.git(repo, "commit", "-m", "adoption evidence")
            args = argparse.Namespace(
                repo=repo,
                approved_state_commit=substituted,
                evidence=adoption_relative,
                agent=gcrctl.ACTOR,
            )
            with (
                patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                self.assertRaisesRegex(SystemExit, "canonical latest ledger introduction"),
            ):
                gcrctl.command_adopt(args)
            self.assertEqual([], gcrctl.transaction_artifacts_present(repo))

    def test_adoption_transaction_recovers_every_abrupt_persistence_boundary(self) -> None:
        boundaries = [
            "backlog-next-durable",
            "state-next-durable",
            "transaction-published",
            "backlog-replaced",
            "state-replaced",
            "successor-validated",
            "transaction-removed",
        ]
        published = {
            "transaction-published",
            "backlog-replaced",
            "state-replaced",
            "successor-validated",
            "transaction-removed",
        }
        for boundary in boundaries:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary:
                repo, packet, _base, approved_state = self.approved_fixture(temporary)
                adoption_relative = self.write_adoption_evidence(repo, approved_state)
                self.git(repo, "add", adoption_relative)
                self.git(repo, "commit", "-m", "adoption evidence")
                evidence_commit = self.git(repo, "rev-parse", "HEAD")
                old_backlog = (repo / gcrctl.BACKLOG_PATH).read_bytes()
                old_state = (repo / gcrctl.STATE_PATH).read_bytes()
                child = "\n".join(
                    [
                        "import copy, hashlib, json, os, pathlib, sys, yaml",
                        "from unittest.mock import patch",
                        f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                        "import gcrctl, taskctl",
                        "repo = pathlib.Path(sys.argv[1])",
                        "boundary = sys.argv[2]",
                        "packet = json.loads(sys.argv[3])",
                        f"approved = {json.dumps(approved_state)}",
                        f"evidence_commit = {json.dumps(evidence_commit)}",
                        f"evidence_relative = {json.dumps(adoption_relative)}",
                        "old_backlog = (repo / gcrctl.BACKLOG_PATH).read_bytes()",
                        "old_state = (repo / gcrctl.STATE_PATH).read_bytes()",
                        "backlog = yaml.safe_load(old_backlog)",
                        "state = json.loads(old_state)",
                        "latest = state['attempts'][-1]",
                        "reviewed = latest['review']['reviewedStateCommit']",
                        "ledger = latest['ledger']",
                        "evidence_payload = (repo / evidence_relative).read_bytes()",
                        "backlog['control_plane']['revision'] = 7",
                        "backlog['control_plane']['minimum_tool_revision'] = 7",
                        "backlog['control_plane']['control_generations'] = [{",
                        "  'id': gcrctl.GCR_ID, 'bootstrap_id': gcrctl.BOOTSTRAP_ID,",
                        "  'hold_id': 'HOLD-W1-GRR-0002', 'predecessor_revision': 6, 'successor_revision': 7,",
                        "  'approval_reference': {",
                        "    'path': gcrctl.APPROVAL_PATH, 'sha256': '0' * 64,",
                        "    'introduction_commit': state['approval']['commit']},",
                        "  'review_reference': {",
                        "    'path': ledger['path'], 'sha256': ledger['sha256'],",
                        "    'reviewed_state_commit': reviewed, 'approved_state_commit': approved},",
                        "  'adopted_by': gcrctl.ACTOR, 'adopted_at': '2026-08-24T00:00:00+00:00'",
                        "}]",
                        "state['status'] = 'ADOPTION_FINALIZATION'",
                        "state['adoption'] = {",
                        "  'adoptedBy': gcrctl.ACTOR, 'adoptedAt': '2026-08-24T00:00:00+00:00',",
                        "  'predecessorRevision': 6, 'successorRevision': 7, 'reviewedStateCommit': approved,",
                        "  'evidence': {",
                        "    'path': evidence_relative,",
                        "    'sha256': hashlib.sha256(evidence_payload).hexdigest(),",
                        "    'commit': evidence_commit}",
                        "}",
                        "def crash(label):",
                        "    if label == boundary:",
                        "        os._exit(77)",
                        "gcrctl.adoption_fault_boundary = crash",
                        "with patch.object(taskctl, 'backlog_schema_errors', return_value=[]), \\",
                        "     patch.object(taskctl, 'validate', return_value=[]):",
                        "    gcrctl.atomic_adoption_write(",
                        "        repo, expected_backlog=old_backlog, expected_state=old_state,",
                        "        backlog_document=backlog, state_document=state, packet=packet,",
                        "        reviewed_state=reviewed, approved_state=approved, evidence_commit=evidence_commit,",
                        "        evidence_relative=evidence_relative, evidence_payload=evidence_payload)",
                    ]
                )
                result = subprocess.run(
                    [sys.executable, "-c", child, str(repo), boundary, json.dumps(packet)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(77, result.returncode, result.stdout + result.stderr)
                present = gcrctl.transaction_artifacts_present(repo)
                if boundary != "transaction-removed":
                    self.assertTrue(present)
                    backlog_document = yaml.safe_load((repo / gcrctl.BACKLOG_PATH).read_text(encoding="utf-8"))
                    self.assertTrue(
                        any(
                            "requires explicit gcrctl recovery" in error
                            for error in taskctl.governance_control_generation_errors(backlog_document, repo)
                        )
                    )
                    if boundary == "backlog-replaced":
                        saved_artifacts = {
                            relative: path.read_bytes()
                            for relative, path in gcrctl.transaction_artifacts(repo).items()
                            if path.is_file()
                        }
                        for relative in saved_artifacts:
                            (repo / relative).unlink()
                        split_errors = taskctl.governance_control_generation_errors(backlog_document, repo)
                        self.assertTrue(
                            any("live adoption state/evidence" in error for error in split_errors),
                            split_errors,
                        )
                        for relative, payload in saved_artifacts.items():
                            (repo / relative).write_bytes(payload)
                if boundary == "transaction-published":
                    canonical_before = {
                        gcrctl.BACKLOG_PATH: (repo / gcrctl.BACKLOG_PATH).read_bytes(),
                        gcrctl.STATE_PATH: (repo / gcrctl.STATE_PATH).read_bytes(),
                    }
                    artifacts_before = {
                        relative: path.read_bytes()
                        for relative, path in gcrctl.transaction_artifacts(repo).items()
                        if path.is_file()
                    }

                    unrelated = repo / "unrelated-untracked.tmp"
                    unrelated.write_text("unrelated\n", encoding="utf-8")
                    with self.assertRaisesRegex(SystemExit, "recovery untracked-path boundary differs"):
                        gcrctl.recover_adoption_transaction(repo, packet)
                    unrelated.unlink()

                    staged_relative = "planning/staged-recovery.txt"
                    (repo / staged_relative).write_text("staged\n", encoding="utf-8")
                    self.git(repo, "add", staged_relative)
                    with self.assertRaisesRegex(SystemExit, "recovery staged-path boundary differs"):
                        gcrctl.recover_adoption_transaction(repo, packet)
                    self.git(repo, "restore", "--staged", staged_relative)
                    (repo / staged_relative).unlink()

                    tracked_path = repo / "tools/gcrctl.py"
                    tracked_before = tracked_path.read_bytes()
                    tracked_path.write_bytes(tracked_before + b"# unrelated\n")
                    with self.assertRaisesRegex(SystemExit, "recovery tracked-path boundary differs"):
                        gcrctl.recover_adoption_transaction(repo, packet)
                    tracked_path.write_bytes(tracked_before)

                    self.assertEqual(
                        canonical_before,
                        {
                            gcrctl.BACKLOG_PATH: (repo / gcrctl.BACKLOG_PATH).read_bytes(),
                            gcrctl.STATE_PATH: (repo / gcrctl.STATE_PATH).read_bytes(),
                        },
                    )
                    self.assertEqual(
                        artifacts_before,
                        {
                            relative: path.read_bytes()
                            for relative, path in gcrctl.transaction_artifacts(repo).items()
                            if path.is_file()
                        },
                    )
                with (
                    patch.object(taskctl, "backlog_schema_errors", return_value=[]),
                    patch.object(taskctl, "validate", return_value=[]),
                ):
                    outcome = gcrctl.recover_adoption_transaction(repo, packet)
                if boundary in published:
                    self.assertEqual("ABSENT" if boundary == "transaction-removed" else "COMPLETED_SUCCESSOR", outcome)
                    self.assertNotEqual(old_backlog, (repo / gcrctl.BACKLOG_PATH).read_bytes())
                    self.assertNotEqual(old_state, (repo / gcrctl.STATE_PATH).read_bytes())
                else:
                    self.assertEqual("RESTORED_PREDECESSOR", outcome)
                    self.assertEqual(old_backlog, (repo / gcrctl.BACKLOG_PATH).read_bytes())
                    self.assertEqual(old_state, (repo / gcrctl.STATE_PATH).read_bytes())
                self.assertEqual([], gcrctl.transaction_artifacts_present(repo))
                self.assertEqual("ABSENT", gcrctl.recover_adoption_transaction(repo, packet))

    def test_adoption_transaction_denies_stale_bytes_and_competing_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, packet, base, approved_state = self.approved_fixture(temporary)
            adoption_relative = self.write_adoption_evidence(repo, approved_state)
            self.git(repo, "add", adoption_relative)
            self.git(repo, "commit", "-m", "adoption evidence")
            backlog_path = repo / gcrctl.BACKLOG_PATH
            state_path = repo / gcrctl.STATE_PATH
            backlog_payload = backlog_path.read_bytes()
            state_payload = state_path.read_bytes()
            backlog_document = yaml.safe_load(backlog_payload)

            def stale_boundary(_repo: Path, _packet: dict) -> tuple[bytes, dict]:
                backlog_path.write_bytes(backlog_payload + b"\n")
                return backlog_payload, backlog_document

            args = argparse.Namespace(
                repo=repo,
                approved_state_commit=approved_state,
                evidence=adoption_relative,
                agent=gcrctl.ACTOR,
            )
            with (
                patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                patch.object(gcrctl, "current_boundary", side_effect=stale_boundary),
                patch.object(taskctl, "backlog_schema_errors", return_value=[]),
                patch.object(taskctl, "validate", return_value=[]),
                self.assertRaisesRegex(SystemExit, "changed after validation"),
            ):
                gcrctl.command_adopt(args)
            self.assertEqual(state_payload, state_path.read_bytes())
            self.assertEqual([], gcrctl.transaction_artifacts_present(repo))
            backlog_path.write_bytes(backlog_payload)

            transaction_path = repo / gcrctl.TRANSACTION_PATH
            transaction_path.write_text("{}\n", encoding="utf-8")
            with (
                patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                self.assertRaisesRegex(SystemExit, "transaction exists"),
            ):
                gcrctl.command_adopt(args)
            self.assertEqual(backlog_payload, backlog_path.read_bytes())
            self.assertEqual(state_payload, state_path.read_bytes())
            self.assertEqual("RESTORED_PREDECESSOR", gcrctl.recover_adoption_transaction(repo, packet))
            self.assertEqual([], gcrctl.transaction_artifacts_present(repo))

    def test_submit_denies_wrong_actor_without_writing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, base, candidate, packet = self.fixture(temporary)
            evidence_relative = self.evidence(repo, base, candidate, packet)
            args = argparse.Namespace(
                repo=repo,
                agent="other-agent",
                approval_commit=base,
                implementation_commit=candidate,
                evidence=evidence_relative,
            )
            with (
                patch.object(gcrctl, "load_authority", return_value=({}, packet, base)),
                patch.object(gcrctl, "current_boundary", return_value=(b"backlog", {})),
                self.assertRaisesRegex(SystemExit, "exact actor codex"),
            ):
                gcrctl.freeze_submission(args, remediation=False)
            self.assertFalse((repo / gcrctl.STATE_PATH).exists())


if __name__ == "__main__":
    unittest.main()
