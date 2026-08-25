from __future__ import annotations

import argparse
import base64
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import gcr2ctl  # noqa: E402
import taskctl  # noqa: E402


class Gcr2ctlTests(unittest.TestCase):
    def git(self, repo: Path, *arguments: str) -> str:
        return subprocess.run(["git", *arguments], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()

    def write_json(self, repo: Path, relative: str, document: dict) -> Path:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return path

    def fixture(self, temporary: str) -> tuple[Path, str, str, dict]:
        repo = Path(temporary)
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "gcr2@example.test")
        self.git(repo, "config", "user.name", "GCR2 Test")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(repo, "checkout", "-b", gcr2ctl.BRANCH)
        shutil.copy2(REPO / ".gitignore", repo / ".gitignore")
        for relative in (gcr2ctl.RUNTIME_SCHEMA_PATH, gcr2ctl.TRANSACTION_SCHEMA_PATH):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        self.write_json(repo, gcr2ctl.APPROVAL_PATH, {"fixture": True})
        backlog = {
            "control_plane": {
                "revision": 8,
                "minimum_tool_revision": 8,
                "active_amendment": None,
                "recovery_holds": [{"id": "HOLD-W1-GRR-0002", "status": "ACTIVE"}],
                "control_generations": [],
            }
        }
        (repo / gcr2ctl.BACKLOG_PATH).write_text(yaml.safe_dump(backlog, sort_keys=False), encoding="utf-8")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "approval base")
        base = self.git(repo, "rev-parse", "HEAD")
        controller = repo / "tools/gcr2ctl.py"
        controller.parent.mkdir(parents=True, exist_ok=True)
        controller.write_text("# bounded GCR-0002 implementation\n", encoding="utf-8")
        self.git(repo, "add", "tools/gcr2ctl.py")
        self.git(repo, "commit", "-m", "implementation candidate")
        candidate = self.git(repo, "rev-parse", "HEAD")
        trigger = repo / gcr2ctl.TRIGGER_PATH
        trigger.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / gcr2ctl.TRIGGER_PATH, trigger)
        packet = {
            "activationBoundary": {"controlRevision": 8},
            "acceptanceCriteria": ["criterion"],
            "bootstrapUnit": {"authorizedPaths": ["tools/gcr2ctl.py"]},
        }
        return repo, base, candidate, packet

    def evidence(self, repo: Path, base: str, candidate: str, packet: dict) -> str:
        relative = gcr2ctl.evidence_path("R01")
        self.write_json(
            repo,
            relative,
            {
                "schemaVersion": "2.0-control-recovery-evidence",
                "documentType": "governance-control-recovery-bootstrap-evidence",
                "controlRecoveryId": gcr2ctl.GCR_ID,
                "bootstrapUnit": gcr2ctl.BOOTSTRAP_ID,
                "attemptId": "R01",
                "commit": candidate,
                "baseCommit": base,
                "branch": gcr2ctl.BRANCH,
                "triggerWitness": gcr2ctl.trigger_witness(),
                "changedFiles": ["tools/gcr2ctl.py"],
                "checks": [{"id": "focused", "command": "focused", "exitCode": 0, "result": "passed"}],
                "acceptanceCriteria": [
                    {"index": 1, "statement": packet["acceptanceCriteria"][0], "evidence": ["proved"]}
                ],
                "findingClosures": [],
                "unverifiedItems": [],
                "verificationSelection": {
                    "riskAnalysis": "Exact controller state and transaction risk.",
                    "selectedChecks": ["focused"],
                    "deferredCoverage": ["Wave qualification"],
                },
            },
        )
        return relative

    def submitted_fixture(self, temporary: str) -> tuple[Path, dict, str, str, str]:
        repo, base, candidate, packet = self.fixture(temporary)
        evidence = self.evidence(repo, base, candidate, packet)
        args = argparse.Namespace(
            repo=repo,
            agent=gcr2ctl.ACTOR,
            approval_commit=base,
            implementation_commit=candidate,
            evidence=evidence,
        )
        with patch.object(gcr2ctl, "load_authority", return_value=({}, packet, base)):
            gcr2ctl.freeze_submission(args, remediation=False)
        return repo, packet, base, candidate, evidence

    def recovery_fixture(
        self, temporary: str, *, coherent_substitution: bool = False
    ) -> tuple[Path, bytes, bytes, bytes, bytes, dict, dict, tuple[dict, dict, str]]:
        repo = Path(temporary)
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "gcr2@example.test")
        self.git(repo, "config", "user.name", "GCR2 Test")
        self.git(repo, "config", "core.autocrlf", "true")
        self.git(repo, "checkout", "-b", gcr2ctl.BRANCH)
        for relative in (
            ".gitignore",
            ".gitattributes",
            gcr2ctl.RUNTIME_SCHEMA_PATH,
            gcr2ctl.TRANSACTION_SCHEMA_PATH,
            gcr2ctl.BACKLOG_PATH,
        ):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        approval_path = repo / gcr2ctl.APPROVAL_PATH
        approval_path.parent.mkdir(parents=True, exist_ok=True)
        approval_path.write_bytes(b'{"fixture": true}\n')
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "approval base")
        approval_base = self.git(repo, "rev-parse", "HEAD")
        candidate_path = repo / "tools/gcr2ctl.py"
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_bytes(b"# synthetic candidate\n")
        self.git(repo, "add", "tools/gcr2ctl.py")
        self.git(repo, "commit", "-m", "synthetic candidate")
        candidate = self.git(repo, "rev-parse", "HEAD")
        # Preserve the release-authoritative worktree bytes while Git retains
        # the normalized LF blob. Git considers this CRLF worktree clean.
        shutil.copy2(REPO / gcr2ctl.BACKLOG_PATH, repo / gcr2ctl.BACKLOG_PATH)
        self.assertEqual("", self.git(repo, "status", "--short"))
        state_path = repo / gcr2ctl.STATE_PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        attempt_id = "R01"
        evidence_relative = gcr2ctl.evidence_path(attempt_id)
        evidence_payload = (json.dumps({"fixture": "canonical R01 evidence"}, indent=2) + "\n").encode()
        evidence_path = repo / evidence_relative
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes(evidence_payload)
        submission: dict[str, Any] = {
            "attemptId": attempt_id,
            "submittedBy": gcr2ctl.ACTOR,
            "candidateCommit": candidate,
            "baseCommit": approval_base,
            "branch": gcr2ctl.BRANCH,
            "evidence": {
                "path": evidence_relative,
                "sha256": gcr2ctl.sha256(evidence_payload),
                "commit": candidate,
            },
            "submittedAt": "2026-08-25T00:00:00+00:00",
            "priorAttemptId": None,
            "openFindingIds": [],
            "rootCauseAnalysis": None,
        }
        state: dict[str, Any] = {
            "schemaVersion": "2.0-control-recovery-state",
            "documentType": "governance-control-recovery-bootstrap-state",
            "controlRecoveryId": gcr2ctl.GCR_ID,
            "bootstrapUnit": gcr2ctl.BOOTSTRAP_ID,
            "status": "REVIEW",
            "approval": {
                "path": gcr2ctl.APPROVAL_PATH,
                "sha256": gcr2ctl.sha256(approval_path.read_bytes()),
                "commit": approval_base,
            },
            "triggerWitness": gcr2ctl.trigger_witness(),
            "attempts": [],
            "currentSubmission": submission,
            "adoption": None,
        }
        state_path.write_bytes((json.dumps(state, indent=2) + "\n").encode())
        self.git(repo, "add", evidence_relative, gcr2ctl.STATE_PATH)
        self.git(repo, "commit", "-m", "freeze synthetic R01 submission")
        reviewed_state = self.git(repo, "rev-parse", "HEAD")
        authority: tuple[dict, dict, str] = ({}, {}, approval_base)
        gcr2ctl.validate_history(repo, state, authority[1])
        closures: list[dict[str, str]] = []
        ledger_relative = gcr2ctl.review_path(attempt_id)
        ledger = {
            "schemaVersion": "2.0-control-recovery-review",
            "documentType": "governance-control-recovery-bootstrap-review",
            "controlRecoveryId": gcr2ctl.GCR_ID,
            "bootstrapUnit": gcr2ctl.BOOTSTRAP_ID,
            "attemptId": attempt_id,
            "candidateCommit": candidate,
            "reviewedStateCommit": reviewed_state,
            "reviewer": "independent-test-reviewer",
            "result": "approved",
            "evidence": submission["evidence"],
            "findings": [],
            "closures": closures,
            "notes": "Synthetic canonical approval for recovery tests.",
        }
        ledger_payload = (json.dumps(ledger, indent=2) + "\n").encode()
        ledger_path = repo / ledger_relative
        ledger_path.write_bytes(ledger_payload)
        state["attempts"].append(
            {
                "submission": submission,
                "review": {
                    "reviewer": "independent-test-reviewer",
                    "result": "approved",
                    "reviewedAt": "2026-08-25T00:00:00+00:00",
                    "reviewedStateCommit": reviewed_state,
                    "notes": "Synthetic canonical approval for recovery tests.",
                },
                "ledger": {
                    "path": ledger_relative,
                    "sha256": gcr2ctl.sha256(ledger_payload),
                    "commit": reviewed_state,
                },
                "findings": [],
                "closures": closures,
            }
        )
        state["status"] = "APPROVED"
        state["currentSubmission"] = None
        state_path.write_bytes((json.dumps(state, indent=2) + "\n").encode())
        self.git(repo, "add", ledger_relative, gcr2ctl.STATE_PATH)
        self.git(repo, "commit", "-m", "approve synthetic R01")
        approved_state = self.git(repo, "rev-parse", "HEAD")
        if coherent_substitution:
            state["approval"]["sha256"] = "f" * 64
            state_path.write_bytes((json.dumps(state, indent=2) + "\n").encode())
            self.git(repo, "add", gcr2ctl.STATE_PATH)
            self.git(repo, "commit", "-m", "substitute approved authority")
            approved_state = self.git(repo, "rev-parse", "HEAD")
        evidence = {
            "schemaVersion": "2.0-control-recovery-adoption-evidence",
            "documentType": "governance-control-recovery-adoption-evidence",
            "controlRecoveryId": gcr2ctl.GCR_ID,
            "bootstrapUnit": gcr2ctl.BOOTSTRAP_ID,
            "reviewedStateCommit": approved_state,
            "triggerWitness": gcr2ctl.trigger_witness(),
            "predecessorRevision": 8,
            "successorRevision": 9,
            "expectedChangedFiles": [gcr2ctl.BACKLOG_PATH, gcr2ctl.STATE_PATH],
            "checks": [{"id": "recovery", "command": "recovery", "exitCode": 0, "result": "passed"}],
            "unverifiedItems": [],
        }
        adoption_evidence_path = repo / gcr2ctl.ADOPTION_EVIDENCE_PATH
        adoption_evidence_path.parent.mkdir(parents=True, exist_ok=True)
        adoption_evidence_path.write_bytes((json.dumps(evidence, indent=2) + "\n").encode())
        self.git(repo, "add", gcr2ctl.ADOPTION_EVIDENCE_PATH)
        self.git(repo, "commit", "-m", "adoption evidence")
        evidence_commit = self.git(repo, "rev-parse", "HEAD")
        trigger = repo / gcr2ctl.TRIGGER_PATH
        trigger.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / gcr2ctl.TRIGGER_PATH, trigger)
        predecessor_backlog = (repo / gcr2ctl.BACKLOG_PATH).read_bytes()
        predecessor_state = state_path.read_bytes()
        self.assertEqual(gcr2ctl.BACKLOG_SHA256, gcr2ctl.sha256(predecessor_backlog))
        self.assertNotEqual(
            gcr2ctl.sha256(predecessor_backlog),
            gcr2ctl.sha256(taskctl.git_blob(repo, approved_state, gcr2ctl.BACKLOG_PATH) or b""),
        )
        successor_backlog_document = yaml.safe_load(predecessor_backlog)
        control = successor_backlog_document["control_plane"]
        control["revision"] = 9
        control["minimum_tool_revision"] = 9
        control["control_generations"].append(
            {
                "id": gcr2ctl.GCR_ID,
                "bootstrap_id": gcr2ctl.BOOTSTRAP_ID,
                "hold_id": "HOLD-W1-GRR-0002",
                "predecessor_revision": 8,
                "successor_revision": 9,
                "approval_reference": {
                    "path": gcr2ctl.APPROVAL_PATH,
                    "sha256": gcr2ctl.sha256((repo / gcr2ctl.APPROVAL_PATH).read_bytes()),
                    "introduction_commit": state["approval"]["commit"],
                },
                "review_reference": {
                    "path": ledger_relative,
                    "sha256": gcr2ctl.sha256(ledger_payload),
                    "reviewed_state_commit": reviewed_state,
                    "approved_state_commit": approved_state,
                },
                "adopted_by": gcr2ctl.ACTOR,
                "adopted_at": "2026-08-25T00:00:00+00:00",
            }
        )
        successor_backlog = yaml.safe_dump(successor_backlog_document, sort_keys=False).encode()
        successor_state_document = copy.deepcopy(state)
        successor_state_document["status"] = "ADOPTION_FINALIZATION"
        successor_state_document["adoption"] = {
            "adoptedBy": gcr2ctl.ACTOR,
            "adoptedAt": "2026-08-25T00:00:00+00:00",
            "predecessorRevision": 8,
            "successorRevision": 9,
            "reviewedStateCommit": approved_state,
            "evidence": {
                "path": gcr2ctl.ADOPTION_EVIDENCE_PATH,
                "sha256": gcr2ctl.sha256(adoption_evidence_path.read_bytes()),
                "commit": evidence_commit,
            },
        }
        successor_state = (json.dumps(successor_state_document, indent=2) + "\n").encode()
        transaction = gcr2ctl.transaction_document(
            predecessor_backlog=predecessor_backlog,
            predecessor_state=predecessor_state,
            successor_backlog=successor_backlog,
            successor_state=successor_state,
            reviewed_state=approved_state,
            evidence_commit=evidence_commit,
        )
        anchor = gcr2ctl.recovery_anchor_document(
            transaction=transaction,
            predecessor_backlog=predecessor_backlog,
            predecessor_state=predecessor_state,
        )
        if not coherent_substitution:
            gcr2ctl.validate_recovery_anchor(repo, anchor, authority)
        gcr2ctl.validate_successor_pair(repo, successor_backlog, successor_state)
        return (
            repo,
            predecessor_backlog,
            predecessor_state,
            successor_backlog,
            successor_state,
            transaction,
            anchor,
            authority,
        )

    def test_repository_authority_is_valid_at_revision_eight(self) -> None:
        approval, packet, base = gcr2ctl.load_authority(REPO)
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual(gcr2ctl.GCR_ID, packet["controlRecoveryId"])
        self.assertEqual("c029ba348a8bd0abee23e11c078aff4b8fd0b02b", base)
        _payload, backlog = gcr2ctl.current_boundary(REPO, packet, revision=8)
        self.assertEqual(8, backlog["control_plane"]["revision"])

    def test_third_remediation_review_projection_requires_root_cause_analysis(self) -> None:
        _approval, packet, _base = gcr2ctl.load_authority(REPO)
        state = json.loads((REPO / gcr2ctl.STATE_PATH).read_bytes())
        self.assertEqual(2, len(state["attempts"]))
        candidate = gcr2ctl.git(REPO, "rev-parse", "HEAD")
        state["status"] = "REVIEW"
        state["currentSubmission"] = {
            "attemptId": "R03",
            "submittedBy": gcr2ctl.ACTOR,
            "candidateCommit": candidate,
            "baseCommit": state["approval"]["commit"],
            "branch": gcr2ctl.BRANCH,
            "evidence": {
                "path": gcr2ctl.evidence_path("R03"),
                "sha256": "0" * 64,
                "commit": candidate,
            },
            "submittedAt": "2026-08-25T00:00:00+00:00",
            "priorAttemptId": "R02",
            "openFindingIds": sorted(gcr2ctl.open_findings(state)),
            "rootCauseAnalysis": gcr2ctl.R03_ROOT_CAUSE_ANALYSIS,
        }
        gcr2ctl.validate_history(REPO, state, packet)
        state["currentSubmission"]["rootCauseAnalysis"] = None
        with self.assertRaisesRegex(SystemExit, "current remediation submission"):
            gcr2ctl.validate_history(REPO, state, packet)

    def test_v3_schemas_are_exactly_revision_eight_to_nine(self) -> None:
        packet_schema = json.loads(
            (REPO / "planning/governance-recovery-requests/governance-recovery-supplement.v3.schema.json").read_text(
                encoding="utf-8"
            )
        )
        approval_schema = json.loads(
            (
                REPO / "planning/governance-recovery-requests/governance-recovery-supplement-approval.v3.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(packet_schema)
        Draft202012Validator.check_schema(approval_schema)
        transition = packet_schema["properties"]["controlTransition"]["properties"]
        self.assertEqual(8, transition["predecessorRevision"]["const"])
        self.assertEqual(9, transition["successorRevision"]["const"])
        self.assertEqual("GRR-0002.S02", packet_schema["properties"]["supplementId"]["const"])
        self.assertEqual("GRR-0002.B02", approval_schema["properties"]["supplementalBootstrapUnit"]["const"])

    def test_submit_freezes_exact_real_git_candidate_and_witness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _packet, _base, candidate, evidence = self.submitted_fixture(temporary)
            state = json.loads((repo / gcr2ctl.STATE_PATH).read_text(encoding="utf-8"))
            self.assertEqual("REVIEW", state["status"])
            self.assertEqual(candidate, state["currentSubmission"]["candidateCommit"])
            self.assertEqual(gcr2ctl.trigger_witness(), state["triggerWitness"])
            before = (repo / gcr2ctl.STATE_PATH).read_bytes()
            extra = repo / "unrelated.tmp"
            extra.write_text("denied\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "untracked-path boundary"):
                gcr2ctl.require_workspace(repo, extra_untracked={evidence, gcr2ctl.STATE_PATH})
            self.assertEqual(before, (repo / gcr2ctl.STATE_PATH).read_bytes())

    def test_transaction_schema_rejects_crossed_canonical_bindings(self) -> None:
        predecessor_backlog = yaml.safe_dump({"control_plane": {"revision": 8}}).encode()
        predecessor_state = json.dumps({"status": "APPROVED"}).encode()
        successor_backlog = yaml.safe_dump({"control_plane": {"revision": 9}}).encode()
        successor_state = json.dumps({"status": "ADOPTION_FINALIZATION"}).encode()
        transaction = gcr2ctl.transaction_document(
            predecessor_backlog=predecessor_backlog,
            predecessor_state=predecessor_state,
            successor_backlog=successor_backlog,
            successor_state=successor_state,
            reviewed_state="1" * 40,
            evidence_commit="2" * 40,
        )
        gcr2ctl.validate_transaction(REPO, transaction)
        crossed = copy.deepcopy(transaction)
        crossed["predecessor"]["backlog"]["path"] = gcr2ctl.STATE_PATH
        with self.assertRaisesRegex(SystemExit, "schema validation failed"):
            gcr2ctl.validate_transaction(REPO, crossed)
        redirected = copy.deepcopy(transaction)
        redirected["paths"]["state"] = "planning/other.json"
        with self.assertRaisesRegex(SystemExit, "schema validation failed"):
            gcr2ctl.validate_transaction(REPO, redirected)

    def test_unpublished_transaction_restores_exact_predecessor_and_cleans_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (
                repo,
                predecessor_backlog,
                predecessor_state,
                _successor_backlog,
                _successor_state,
                _transaction,
                anchor,
                authority,
            ) = self.recovery_fixture(temporary)
            artifacts = gcr2ctl.transaction_artifacts(repo)
            with gcr2ctl.transaction_lock(repo, anchor=anchor, authority=authority):
                pass
            gcr2ctl.write_new_durable(artifacts[gcr2ctl.BACKLOG_NEXT_PATH], b"substituted\n")
            (repo / gcr2ctl.BACKLOG_PATH).write_bytes(b"partial\n")
            self.assertEqual("RESTORED_PREDECESSOR", gcr2ctl.recover_transaction(repo, authority))
            self.assertEqual(predecessor_backlog, (repo / gcr2ctl.BACKLOG_PATH).read_bytes())
            self.assertEqual(predecessor_state, (repo / gcr2ctl.STATE_PATH).read_bytes())
            self.assertEqual([], gcr2ctl.present_transaction_artifacts(repo))
            self.assertEqual("ABSENT", gcr2ctl.recover_transaction(repo, authority))

    def test_invalid_manifest_restores_but_stale_head_and_substituted_anchor_fail_closed(self) -> None:
        for scenario in ("invalid-manifest", "stale-head", "substituted-anchor"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                (
                    repo,
                    predecessor_backlog,
                    predecessor_state,
                    _successor_backlog,
                    _successor_state,
                    _transaction,
                    anchor,
                    authority,
                ) = self.recovery_fixture(temporary)
                artifacts = gcr2ctl.transaction_artifacts(repo)
                with gcr2ctl.transaction_lock(repo, anchor=anchor, authority=authority):
                    pass
                if scenario == "invalid-manifest":
                    gcr2ctl.write_new_durable(artifacts[gcr2ctl.TRANSACTION_PATH], b"not-json\n")
                elif scenario == "stale-head":
                    unrelated = repo / "unrelated.txt"
                    unrelated.write_text("new head\n", encoding="utf-8")
                    self.git(repo, "add", "unrelated.txt")
                    self.git(repo, "commit", "-m", "unrelated head")
                else:
                    changed = copy.deepcopy(anchor)
                    changed_state = json.dumps({"status": "APPROVED"}).encode()
                    changed["predecessorPayloads"]["stateBase64"] = base64.b64encode(changed_state).decode("ascii")
                    changed["predecessor"]["state"] = gcr2ctl.binding(
                        gcr2ctl.STATE_PATH, changed_state, json.loads(changed_state)
                    )
                    artifacts[gcr2ctl.LOCK_PATH].write_bytes((json.dumps(changed, indent=2) + "\n").encode())
                (repo / gcr2ctl.BACKLOG_PATH).write_bytes(b"partial backlog\n")
                (repo / gcr2ctl.STATE_PATH).write_bytes(b"partial state\n")
                before = {
                    path: (repo / path).read_bytes()
                    for path in (gcr2ctl.BACKLOG_PATH, gcr2ctl.STATE_PATH, gcr2ctl.LOCK_PATH)
                }
                if scenario == "invalid-manifest":
                    self.assertEqual("RESTORED_PREDECESSOR", gcr2ctl.recover_transaction(repo, authority))
                    self.assertEqual(predecessor_backlog, (repo / gcr2ctl.BACKLOG_PATH).read_bytes())
                    self.assertEqual(predecessor_state, (repo / gcr2ctl.STATE_PATH).read_bytes())
                    self.assertEqual([], gcr2ctl.present_transaction_artifacts(repo))
                else:
                    with self.assertRaisesRegex(SystemExit, "recovery anchor"):
                        gcr2ctl.recover_transaction(repo, authority)
                    after = {
                        path: (repo / path).read_bytes()
                        for path in (gcr2ctl.BACKLOG_PATH, gcr2ctl.STATE_PATH, gcr2ctl.LOCK_PATH)
                    }
                    self.assertEqual(before, after)

    def test_coherent_substituted_approved_parent_fails_closed_without_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (
                repo,
                _predecessor_backlog,
                _predecessor_state,
                successor_backlog,
                successor_state,
                transaction,
                anchor,
                authority,
            ) = self.recovery_fixture(temporary, coherent_substitution=True)
            artifacts = gcr2ctl.transaction_artifacts(repo)
            gcr2ctl.write_new_durable(artifacts[gcr2ctl.LOCK_PATH], (json.dumps(anchor, indent=2) + "\n").encode())
            gcr2ctl.write_new_durable(artifacts[gcr2ctl.BACKLOG_NEXT_PATH], successor_backlog)
            gcr2ctl.write_new_durable(artifacts[gcr2ctl.STATE_NEXT_PATH], successor_state)
            gcr2ctl.write_new_durable(
                artifacts[gcr2ctl.TRANSACTION_PATH], (json.dumps(transaction, indent=2) + "\n").encode()
            )
            (repo / gcr2ctl.BACKLOG_PATH).write_bytes(b"partial backlog\n")
            (repo / gcr2ctl.STATE_PATH).write_bytes(b"partial state\n")
            protected = [
                gcr2ctl.BACKLOG_PATH,
                gcr2ctl.STATE_PATH,
                gcr2ctl.LOCK_PATH,
                gcr2ctl.TRANSACTION_PATH,
                gcr2ctl.BACKLOG_NEXT_PATH,
                gcr2ctl.STATE_NEXT_PATH,
            ]
            before = {path: (repo / path).read_bytes() for path in protected}
            with self.assertRaisesRegex(SystemExit, "approval reference is not canonical"):
                gcr2ctl.recover_transaction(repo, authority)
            after = {path: (repo / path).read_bytes() for path in protected}
            self.assertEqual(before, after)

    def test_taskctl_revision_eight_reader_fails_closed_on_revision_nine(self) -> None:
        backlog = yaml.safe_load((REPO / gcr2ctl.BACKLOG_PATH).read_text(encoding="utf-8"))
        backlog["control_plane"]["revision"] = 9
        backlog["control_plane"]["minimum_tool_revision"] = 9
        with patch.object(taskctl, "CONTROL_TOOL_REVISION", 8):
            errors = taskctl.wave_authority_errors(backlog, None)
        self.assertTrue(
            any(
                message in errors
                for message in (
                    "this taskctl revision is too old for the active control plane",
                    "control plane revision is missing or unsupported",
                )
            ),
            errors,
        )

    def test_child_process_crashes_recover_to_one_exact_pair(self) -> None:
        boundaries = [
            "lock-durable",
            "backlog-next-durable",
            "state-next-durable",
            "transaction-published",
            "backlog-published",
            "state-published",
            "successor-directories-durable",
            "cleanup-GCR-0002.B00.adoption-transaction.json",
            "cleanup-GCR-0002.B00.adoption.lock",
        ]
        for boundary in boundaries:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary:
                (
                    repo,
                    predecessor_backlog,
                    predecessor_state,
                    successor_backlog,
                    successor_state,
                    transaction,
                    anchor,
                    authority,
                ) = self.recovery_fixture(temporary)
                (repo / ".git/gcr2-transaction.json").write_bytes((json.dumps(transaction, indent=2) + "\n").encode())
                (repo / ".git/gcr2-anchor.json").write_bytes((json.dumps(anchor, indent=2) + "\n").encode())
                (repo / ".git/gcr2-authority-base").write_text(authority[2], encoding="ascii")
                (repo / ".git/gcr2-successor-backlog").write_bytes(successor_backlog)
                (repo / ".git/gcr2-successor-state").write_bytes(successor_state)
                child = "\n".join(
                    [
                        "import json, os, pathlib, sys, yaml",
                        f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                        "import gcr2ctl, taskctl",
                        "repo = pathlib.Path(sys.argv[1])",
                        "boundary = sys.argv[2]",
                        "new_backlog = (repo / '.git/gcr2-successor-backlog').read_bytes()",
                        "new_state = (repo / '.git/gcr2-successor-state').read_bytes()",
                        "transaction = json.loads((repo / '.git/gcr2-transaction.json').read_bytes())",
                        "anchor = json.loads((repo / '.git/gcr2-anchor.json').read_bytes())",
                        "authority = ({}, {}, (repo / '.git/gcr2-authority-base').read_text(encoding='ascii'))",
                        "def crash(label):",
                        "  if label == boundary: os._exit(77)",
                        "gcr2ctl.adoption_fault_boundary = crash",
                        "artifacts = gcr2ctl.transaction_artifacts(repo)",
                        (
                            "with taskctl.exclusive_backlog_lock(repo / gcr2ctl.BACKLOG_PATH), "
                            "gcr2ctl.transaction_lock(repo, anchor=anchor, authority=authority):"
                        ),
                        "  gcr2ctl.write_new_durable(artifacts[gcr2ctl.BACKLOG_NEXT_PATH], new_backlog)",
                        "  crash('backlog-next-durable')",
                        "  gcr2ctl.write_new_durable(artifacts[gcr2ctl.STATE_NEXT_PATH], new_state)",
                        "  crash('state-next-durable')",
                        (
                            "  gcr2ctl.write_new_durable(artifacts[gcr2ctl.TRANSACTION_PATH], "
                            "(json.dumps(transaction, indent=2) + '\\n').encode())"
                        ),
                        "  crash('transaction-published')",
                        "  gcr2ctl.complete_transaction(repo, transaction)",
                    ]
                )
                result = subprocess.run(
                    [sys.executable, "-c", child, str(repo), boundary],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(77, result.returncode, result.stdout + result.stderr)
                if gcr2ctl.present_transaction_artifacts(repo):
                    outcome = gcr2ctl.recover_transaction(repo, authority)
                    self.assertIn(outcome, {"RESTORED_PREDECESSOR", "COMPLETED_SUCCESSOR"})
                live = (
                    (repo / gcr2ctl.BACKLOG_PATH).read_bytes(),
                    (repo / gcr2ctl.STATE_PATH).read_bytes(),
                )
                self.assertIn(
                    live,
                    {
                        (predecessor_backlog, predecessor_state),
                        (successor_backlog, successor_state),
                    },
                )
                self.assertEqual([], gcr2ctl.present_transaction_artifacts(repo))
                self.assertEqual("ABSENT", gcr2ctl.recover_transaction(repo, authority))


if __name__ == "__main__":
    unittest.main()
