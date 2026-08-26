from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import gcr5ctl  # noqa: E402


class Gcr5ctlTests(unittest.TestCase):
    def git(self, repo: Path, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def init_repo(self, temporary: str) -> Path:
        repo = Path(temporary)
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "gcr5@example.test")
        self.git(repo, "config", "user.name", "GCR5 Test")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(repo, "checkout", "-b", gcr5ctl.BRANCH)
        return repo

    def commit_all(self, repo: Path, message: str) -> str:
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", message)
        return self.git(repo, "rev-parse", "HEAD")

    def commit_paths(self, repo: Path, message: str, *paths: str) -> str:
        self.git(repo, "add", "--", *paths)
        self.git(repo, "commit", "-m", message)
        return self.git(repo, "rev-parse", "HEAD")

    def protected_snapshot(self, repo: Path) -> dict[str, bytes]:
        return {
            relative: (repo / relative).read_bytes()
            for relative in [*gcr5ctl.FINAL_PATHS, gcr5ctl.LEDGER_PATH, gcr5ctl.TRIGGER_PATH]
        }

    def install_junction(self, repo: Path, relative: str, tag: str) -> tuple[Path, Path]:
        source = repo.joinpath(*Path(relative).parts)
        target = repo / ".git" / f"gcr5-junction-{tag}"
        source.rename(target)
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(source), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            target.rename(source)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return source, target

    def remove_junction(self, source: Path, target: Path) -> None:
        source.rmdir()
        target.rename(source)

    def valid_evidence(
        self,
        *,
        base: str,
        candidate: str,
        changed: list[str],
        attempt_id: str = "R01",
    ) -> dict[str, Any]:
        return {
            "schemaVersion": "5.0-control-recovery-evidence",
            "documentType": "governance-control-recovery-bootstrap-evidence",
            "controlRecoveryId": gcr5ctl.GCR_ID,
            "bootstrapUnit": gcr5ctl.BOOTSTRAP_ID,
            "attemptId": attempt_id,
            "agent": gcr5ctl.ACTOR,
            "approvalCommit": base,
            "baseCommit": base,
            "candidateCommit": candidate,
            "branch": gcr5ctl.BRANCH,
            "changedPaths": changed,
            "requiredOutcomes": [{"criterion": "outcome", "evidence": "proved"}],
            "acceptanceCriteria": [{"criterion": "criterion", "evidence": "proved"}],
            "checks": [{"command": "focused", "result": "passed", "summary": "passed"}],
            "closures": [],
            "unverifiedItems": [],
            "rootCauseAnalysis": None,
        }

    def real_history_fixture(self, temporary: str) -> tuple[Path, dict, dict, str]:
        repo = self.init_repo(temporary)
        for relative in (gcr5ctl.RUNTIME_SCHEMA_PATH, gcr5ctl.TRANSACTION_SCHEMA_PATH):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        approval_path = repo / gcr5ctl.APPROVAL_PATH
        approval_path.parent.mkdir(parents=True, exist_ok=True)
        approval_path.write_text('{"fixture":true}\n', encoding="utf-8")
        base = self.commit_all(repo, "approval base")
        implementation = repo / "tools/gcr5ctl.py"
        implementation.parent.mkdir(parents=True, exist_ok=True)
        implementation.write_text("# exact candidate\n", encoding="utf-8")
        candidate = self.commit_all(repo, "implementation candidate")
        evidence_relative = gcr5ctl.evidence_path("R01")
        evidence = self.valid_evidence(base=base, candidate=candidate, changed=["tools/gcr5ctl.py"])
        evidence_path = repo / evidence_relative
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes((json.dumps(evidence, indent=2) + "\n").encode())
        evidence_commit = self.commit_all(repo, "evidence only")
        submission: dict[str, Any] = {
            "attemptId": "R01",
            "submittedBy": gcr5ctl.ACTOR,
            "submittedAt": "2026-08-26T10:00:00+00:00",
            "candidateCommit": candidate,
            "baseCommit": base,
            "branch": gcr5ctl.BRANCH,
            "evidence": {
                "path": evidence_relative,
                "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                "commit": evidence_commit,
            },
            "priorAttemptId": None,
            "openFindingIds": [],
            "rootCauseAnalysis": None,
        }
        state: dict[str, Any] = {
            "schemaVersion": "5.0-control-recovery-state",
            "documentType": "governance-control-recovery-bootstrap-state",
            "controlRecoveryId": gcr5ctl.GCR_ID,
            "bootstrapUnit": gcr5ctl.BOOTSTRAP_ID,
            "status": "REVIEW",
            "approval": {
                "path": gcr5ctl.APPROVAL_PATH,
                "sha256": hashlib.sha256(approval_path.read_bytes()).hexdigest(),
                "commit": base,
            },
            "attempts": {},
            "currentSubmission": submission,
            "latestReviewResult": None,
            "openFindingIds": [],
            "application": None,
        }
        state_path = repo / gcr5ctl.STATE_PATH
        state_path.write_bytes((json.dumps(state, indent=2) + "\n").encode())
        reviewed_state = self.commit_all(repo, "state only")
        finding = {
            "id": "GCR-0005.B00-R01-F01",
            "severity": "high",
            "blocking": True,
            "criterionIndex": 1,
            "title": "fixture finding",
            "reproduction": "fixture reproduction",
            "requiredRemediation": "fixture remediation",
        }
        ledger = {
            "schemaVersion": "5.0-control-recovery-bootstrap-review",
            "documentType": "governance-control-recovery-bootstrap-review",
            "controlRecoveryId": gcr5ctl.GCR_ID,
            "bootstrapUnit": gcr5ctl.BOOTSTRAP_ID,
            "attemptId": "R01",
            "candidateCommit": candidate,
            "reviewedStateCommit": reviewed_state,
            "reviewer": "independent-reviewer",
            "result": "changes-requested",
            "evidence": copy.deepcopy(submission["evidence"]),
            "notes": "fixture",
            "findings": [finding],
            "closures": [],
        }
        ledger_path = repo / gcr5ctl.review_path("R01")
        ledger_path.write_bytes((json.dumps(ledger, indent=2) + "\n").encode())
        ledger_commit = self.commit_all(repo, "ledger only")
        attempt = {
            "submission": submission,
            "review": {
                "reviewer": "independent-reviewer",
                "result": "changes-requested",
                "reviewedAt": "2026-08-26T10:05:00+00:00",
                "reviewedStateCommit": reviewed_state,
                "notes": "fixture",
            },
            "ledger": {
                "path": gcr5ctl.review_path("R01"),
                "sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
                "commit": ledger_commit,
            },
            "findings": [finding],
            "closures": [],
        }
        state["attempts"] = {"R01": attempt}
        state["status"] = "CHANGES_REQUESTED"
        state["currentSubmission"] = None
        state["latestReviewResult"] = "changes-requested"
        state["openFindingIds"] = [finding["id"]]
        state_path.write_bytes((json.dumps(state, indent=2) + "\n").encode())
        self.commit_all(repo, "state projection only")
        packet = {
            "acceptanceCriteria": ["criterion"],
            "bootstrapUnit": {
                "requiredOutcomes": ["outcome"],
                "authorizedPaths": ["tools/gcr5ctl.py"],
            },
        }
        return repo, packet, state, base

    def approved_application_fixture(self, temporary: str) -> tuple[Path, str, str, dict[str, bytes]]:
        repo = Path(temporary) / "repo"
        bundle = Path(temporary) / "fixture.bundle"
        subprocess.run(
            ["git", "bundle", "create", str(bundle), "--all"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "clone", str(bundle), str(repo)],
            capture_output=True,
            text=True,
            check=True,
        )
        self.git(repo, "config", "user.email", "gcr5@example.test")
        self.git(repo, "config", "user.name", "GCR5 Test")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(repo, "checkout", "-B", gcr5ctl.BRANCH, gcr5ctl.APPROVAL_COMMIT)
        shutil.copy2(REPO / "tools/gcr5ctl.py", repo / "tools/gcr5ctl.py")
        candidate = self.commit_paths(repo, "candidate", "tools/gcr5ctl.py")
        packet = json.loads((repo / gcr5ctl.PACKET_PATH).read_bytes())
        evidence = {
            "schemaVersion": "5.0-control-recovery-evidence",
            "documentType": "governance-control-recovery-bootstrap-evidence",
            "controlRecoveryId": gcr5ctl.GCR_ID,
            "bootstrapUnit": gcr5ctl.BOOTSTRAP_ID,
            "attemptId": "R01",
            "agent": gcr5ctl.ACTOR,
            "approvalCommit": gcr5ctl.APPROVAL_COMMIT,
            "baseCommit": gcr5ctl.APPROVAL_COMMIT,
            "candidateCommit": candidate,
            "branch": gcr5ctl.BRANCH,
            "changedPaths": ["tools/gcr5ctl.py"],
            "requiredOutcomes": [
                {"criterion": criterion, "evidence": "real fixture"}
                for criterion in packet["bootstrapUnit"]["requiredOutcomes"]
            ],
            "acceptanceCriteria": [
                {"criterion": criterion, "evidence": "real fixture"} for criterion in packet["acceptanceCriteria"]
            ],
            "checks": [{"command": "real fixture", "result": "passed", "summary": "passed"}],
            "closures": [],
            "unverifiedItems": [],
            "rootCauseAnalysis": None,
        }
        evidence_relative = gcr5ctl.evidence_path("R01")
        evidence_path = repo / evidence_relative
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes((json.dumps(evidence, indent=2) + "\n").encode())
        evidence_commit = self.commit_paths(repo, "evidence", evidence_relative)
        evidence_payload = gcr5ctl.taskctl.git_blob(repo, evidence_commit, evidence_relative)
        assert evidence_payload is not None
        submission: dict[str, Any] = {
            "attemptId": "R01",
            "submittedBy": gcr5ctl.ACTOR,
            "submittedAt": "2026-08-26T10:00:00+00:00",
            "candidateCommit": candidate,
            "baseCommit": gcr5ctl.APPROVAL_COMMIT,
            "branch": gcr5ctl.BRANCH,
            "evidence": {
                "path": evidence_relative,
                "sha256": hashlib.sha256(evidence_payload).hexdigest(),
                "commit": evidence_commit,
            },
            "priorAttemptId": None,
            "openFindingIds": [],
            "rootCauseAnalysis": None,
        }
        approval_path = repo / gcr5ctl.APPROVAL_PATH
        state: dict[str, Any] = {
            "schemaVersion": "5.0-control-recovery-state",
            "documentType": "governance-control-recovery-bootstrap-state",
            "controlRecoveryId": gcr5ctl.GCR_ID,
            "bootstrapUnit": gcr5ctl.BOOTSTRAP_ID,
            "status": "REVIEW",
            "approval": {
                "path": gcr5ctl.APPROVAL_PATH,
                "sha256": hashlib.sha256(approval_path.read_bytes()).hexdigest(),
                "commit": gcr5ctl.APPROVAL_COMMIT,
            },
            "attempts": {},
            "currentSubmission": submission,
            "latestReviewResult": None,
            "openFindingIds": [],
            "application": None,
        }
        state_path = repo / gcr5ctl.STATE_PATH
        state_path.write_bytes((json.dumps(state, indent=2) + "\n").encode())
        reviewed_state = self.commit_paths(repo, "reviewed state", gcr5ctl.STATE_PATH)
        ledger: dict[str, Any] = {
            "schemaVersion": "5.0-control-recovery-bootstrap-review",
            "documentType": "governance-control-recovery-bootstrap-review",
            "controlRecoveryId": gcr5ctl.GCR_ID,
            "bootstrapUnit": gcr5ctl.BOOTSTRAP_ID,
            "attemptId": "R01",
            "candidateCommit": candidate,
            "reviewedStateCommit": reviewed_state,
            "reviewer": "independent-reviewer",
            "result": "approved",
            "evidence": copy.deepcopy(submission["evidence"]),
            "notes": "approved fixture",
            "findings": [],
            "closures": [],
        }
        ledger_relative = gcr5ctl.review_path("R01")
        ledger_path = repo / ledger_relative
        ledger_path.write_bytes((json.dumps(ledger, indent=2) + "\n").encode())
        ledger_commit = self.commit_paths(repo, "ledger", ledger_relative)
        ledger_payload = gcr5ctl.taskctl.git_blob(repo, ledger_commit, ledger_relative)
        assert ledger_payload is not None
        attempt: dict[str, Any] = {
            "submission": submission,
            "review": {
                "reviewer": "independent-reviewer",
                "result": "approved",
                "reviewedAt": "2026-08-26T10:05:00+00:00",
                "reviewedStateCommit": reviewed_state,
                "notes": "approved fixture",
            },
            "ledger": {
                "path": ledger_relative,
                "sha256": hashlib.sha256(ledger_payload).hexdigest(),
                "commit": ledger_commit,
            },
            "findings": [],
            "closures": [],
        }
        state["attempts"] = {"R01": attempt}
        state["status"] = "APPROVED"
        state["currentSubmission"] = None
        state["latestReviewResult"] = "approved"
        state_path.write_bytes((json.dumps(state, indent=2) + "\n").encode())
        approved = self.commit_paths(repo, "approved projection", gcr5ctl.STATE_PATH)
        application: dict[str, Any] = {
            "schemaVersion": "5.0-control-recovery-application-evidence",
            "documentType": "governance-control-recovery-review-transition-evidence",
            "controlRecoveryId": gcr5ctl.GCR_ID,
            "bootstrapUnit": gcr5ctl.BOOTSTRAP_ID,
            "approvedStateCommit": approved,
            "applicationBaseCommit": approved,
            "projectionTimestamp": gcr5ctl.PROJECTION_TIMESTAMP,
            "backlogBeforeRawSha256": gcr5ctl.BACKLOG_BEFORE_RAW,
            "backlogBeforeCanonicalSha256": gcr5ctl.BACKLOG_BEFORE_CANONICAL,
            "backlogAfterRawSha256": gcr5ctl.BACKLOG_AFTER,
            "backlogAfterCanonicalSha256": gcr5ctl.BACKLOG_AFTER,
            "ledger": gcr5ctl.application_ledger_reference(),
            "ledgerBytePreserved": True,
            "openFindingIds": ["GRR-0002.B02-R01-F01"],
            "changedPaths": gcr5ctl.FINAL_PATHS,
            "checks": [{"command": "real fixture", "result": "passed", "summary": "passed"}],
            "unverifiedItems": [],
            "ordinaryExecutionAuthority": False,
        }
        application_path = repo / gcr5ctl.APPLICATION_EVIDENCE_PATH
        application_path.parent.mkdir(parents=True, exist_ok=True)
        application_path.write_bytes((json.dumps(application, indent=2) + "\n").encode())
        application_commit = self.commit_paths(repo, "application evidence", gcr5ctl.APPLICATION_EVIDENCE_PATH)
        self.git(
            repo,
            "checkout-index",
            "-f",
            "--",
            evidence_relative,
            gcr5ctl.STATE_PATH,
            ledger_relative,
            gcr5ctl.APPLICATION_EVIDENCE_PATH,
        )
        predecessor: dict[str, bytes] = {}
        for relative in gcr5ctl.FINAL_PATHS:
            payload = (REPO / relative).read_bytes()
            (repo / relative).write_bytes(payload)
            predecessor[relative] = payload
        witness = repo / gcr5ctl.TRIGGER_PATH
        witness.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / gcr5ctl.TRIGGER_PATH, witness)
        self.assertEqual(
            [gcr5ctl.TRIGGER_PATH], self.git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        )
        self.assertEqual("", self.git(repo, "diff", "--name-only", "HEAD", "--"))
        return repo, approved, application_commit, predecessor

    def test_exact_approved_packet_authority_and_frozen_boundary_are_valid(self) -> None:
        approval, packet, introduction = gcr5ctl.load_authority(REPO)
        self.assertEqual(gcr5ctl.APPROVAL_COMMIT, introduction)
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual(gcr5ctl.BOOTSTRAP_ID, packet["bootstrapUnit"]["id"])

    def test_exact_ledger_derived_successor_is_reproducible(self) -> None:
        successor = gcr5ctl.derive_successor_backlog(REPO)
        self.assertEqual(gcr5ctl.BACKLOG_AFTER, hashlib.sha256(successor).hexdigest())
        self.assertEqual("CHANGES_REQUESTED", gcr5ctl._b02(__import__("yaml").safe_load(successor))["status"])

    def test_real_generator_stages_exactly_the_seven_authorized_successors(self) -> None:
        backlog = gcr5ctl.derive_successor_backlog(REPO)
        staged = gcr5ctl.stage_successor_files(REPO, self.git(REPO, "rev-parse", "HEAD"), backlog)
        self.assertEqual(set(gcr5ctl.FINAL_PATHS), set(staged))
        self.assertEqual(gcr5ctl.BACKLOG_AFTER, hashlib.sha256(staged[gcr5ctl.BACKLOG_PATH]).hexdigest())
        self.assertIn(
            b"latest GRR-0002.B02: CHANGES_REQUESTED",
            staged["planning/review-site/recoveries/index.html"],
        )

    def test_runtime_and_transaction_schemas_are_draft_2020_12(self) -> None:
        for relative in (gcr5ctl.RUNTIME_SCHEMA_PATH, gcr5ctl.TRANSACTION_SCHEMA_PATH):
            Draft202012Validator.check_schema(json.loads((REPO / relative).read_bytes()))

    def test_transaction_document_is_exact_schema_valid(self) -> None:
        transaction = gcr5ctl.transaction_document(
            REPO,
            approved_state="a" * 40,
            state_payload=b"exact state\n",
            application_commit="b" * 40,
            evidence_payload=b"exact evidence\n",
        )
        gcr5ctl.validate_transaction(REPO, transaction)
        transaction["ordinaryExecutionAuthority"] = True
        with self.assertRaisesRegex(SystemExit, "schema validation failed"):
            gcr5ctl.validate_transaction(REPO, transaction)

    def test_strict_json_rejects_duplicate_attempt_keys(self) -> None:
        with self.assertRaisesRegex(SystemExit, "duplicate object key: R01"):
            gcr5ctl.strict_json(b'{"attempts":{"R01":{},"R01":{}}}', "forged state")

    def test_attempt_map_rejects_reordered_skipped_and_mismatched_keys(self) -> None:
        attempts_cases: tuple[dict[str, dict[str, Any]], ...] = (
            {"R02": {}, "R01": {}},
            {"R01": {}, "R03": {}},
        )
        for attempts in attempts_cases:
            with self.subTest(attempts=list(attempts)), self.assertRaises(SystemExit):
                gcr5ctl._attempt_keys({"attempts": attempts})

    def test_finding_fold_rejects_invalid_closure_and_duplicate_finding(self) -> None:
        finding = {"id": "F01", "blocking": True}
        invalid_closure = {
            "attempts": {
                "R01": {"findings": [], "closures": [{"findingId": "F01"}]},
            }
        }
        with self.assertRaisesRegex(SystemExit, "closure targets no open"):
            gcr5ctl.fold_findings(invalid_closure)
        duplicated = {
            "attempts": {
                "R01": {"findings": [finding], "closures": []},
                "R02": {"findings": [finding], "closures": []},
            }
        }
        with self.assertRaisesRegex(SystemExit, "duplicated"):
            gcr5ctl.fold_findings(duplicated)

    def test_review_denies_approval_with_an_open_blocker(self) -> None:
        submission = {
            "attemptId": "R02",
            "candidateCommit": "a" * 40,
            "evidence": {"path": gcr5ctl.evidence_path("R02"), "sha256": "b" * 64, "commit": "c" * 40},
        }
        ledger = {
            "schemaVersion": "5.0-control-recovery-bootstrap-review",
            "documentType": "governance-control-recovery-bootstrap-review",
            "controlRecoveryId": gcr5ctl.GCR_ID,
            "bootstrapUnit": gcr5ctl.BOOTSTRAP_ID,
            "attemptId": "R02",
            "candidateCommit": "a" * 40,
            "reviewedStateCommit": "d" * 40,
            "reviewer": "independent",
            "result": "approved",
            "evidence": copy.deepcopy(submission["evidence"]),
            "notes": "",
            "findings": [],
            "closures": [],
        }
        prior = {"F01": {"id": "F01", "blocking": True}}
        with self.assertRaisesRegex(SystemExit, "open blocker"):
            gcr5ctl.validate_review_ledger(
                REPO,
                ledger,
                submission,
                reviewer="independent",
                reviewed_state="d" * 40,
                prior_open=prior,
                prior_ids={"F01"},
            )

    def test_real_git_history_validates_exact_c_e_s_l_p_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, packet, state, base = self.real_history_fixture(temporary)
            with patch.object(gcr5ctl, "APPROVAL_COMMIT", base):
                gcr5ctl.validate_history(repo, state, packet)

    def test_real_git_history_rejects_stale_result_and_key_submission_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, packet, state, base = self.real_history_fixture(temporary)
            with patch.object(gcr5ctl, "APPROVAL_COMMIT", base):
                stale = copy.deepcopy(state)
                stale["latestReviewResult"] = "approved"
                with self.assertRaises(SystemExit):
                    gcr5ctl.validate_history(repo, stale, packet)
                mismatch = copy.deepcopy(state)
                mismatch["attempts"]["R01"]["submission"]["attemptId"] = "R02"
                with self.assertRaisesRegex(SystemExit, "submission binding"):
                    gcr5ctl.validate_history(repo, mismatch, packet)

    def test_real_authority_transaction_recovery_and_exact_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, approved, application, predecessor = self.approved_application_fixture(temporary)
            labels: list[str] = []

            def interrupt(label: str) -> None:
                labels.append(label)
                if label.startswith("gcr5-successor-planning-implementation-plan"):
                    raise RuntimeError("injected publication interruption")

            arguments = Namespace(
                repo=repo,
                approved_state_commit=approved,
                agent=gcr5ctl.ACTOR,
                evidence=gcr5ctl.APPLICATION_EVIDENCE_PATH,
            )
            with (
                patch.object(gcr5ctl, "adoption_fault_boundary", side_effect=interrupt),
                self.assertRaisesRegex(RuntimeError, "publication interruption"),
            ):
                gcr5ctl.command_apply(arguments)
            self.assertTrue(gcr5ctl.present_transaction_artifacts(repo))
            self.assertEqual("COMPLETED_SUCCESSOR", gcr5ctl.recover_transaction(repo))
            self.assertEqual([], gcr5ctl.present_transaction_artifacts(repo))
            expected = gcr5ctl.stage_successor_files(repo, application, gcr5ctl.derive_successor_backlog(repo))
            self.assertTrue(
                any((repo / relative).read_bytes() != predecessor[relative] for relative in gcr5ctl.FINAL_PATHS)
            )
            self.assertEqual(expected, {relative: (repo / relative).read_bytes() for relative in gcr5ctl.FINAL_PATHS})
            final = self.commit_paths(repo, "exact finalization", *gcr5ctl.FINAL_PATHS)
            self.assertEqual(final, gcr5ctl.validate_finalization(repo))
            self.assertEqual(("APPLIED", gcr5ctl.APPROVAL_COMMIT), gcr5ctl.validate_current_boundary(repo))
            self.assertEqual(application, self.git(repo, "rev-parse", f"{final}^"))
            self.assertIn("gcr5-transaction-durable", labels)

    def test_generator_failure_denies_before_transaction_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, approved, _application, predecessor = self.approved_application_fixture(temporary)
            arguments = Namespace(
                repo=repo,
                approved_state_commit=approved,
                agent=gcr5ctl.ACTOR,
                evidence=gcr5ctl.APPLICATION_EVIDENCE_PATH,
            )
            with (
                patch.object(gcr5ctl, "stage_successor_files", side_effect=SystemExit("generator failed")),
                self.assertRaisesRegex(SystemExit, "generator failed"),
            ):
                gcr5ctl.command_apply(arguments)
            self.assertEqual([], gcr5ctl.present_transaction_artifacts(repo))
            self.assertEqual(
                predecessor, {relative: (repo / relative).read_bytes() for relative in gcr5ctl.FINAL_PATHS}
            )

    def test_authenticated_anchor_rejects_substituted_projection_application_and_successor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, approved, application, predecessor = self.approved_application_fixture(temporary)
            successor = gcr5ctl.stage_successor_files(repo, application, gcr5ctl.derive_successor_backlog(repo))
            anchor = gcr5ctl.application_anchor(
                approved_state=approved,
                application_commit=application,
                predecessor=predecessor,
                successor=successor,
            )
            gcr5ctl.validate_anchor(repo, anchor)
            substituted_projection = copy.deepcopy(anchor)
            substituted_projection["approvedStateCommit"] = gcr5ctl.APPROVAL_COMMIT
            with self.assertRaisesRegex(SystemExit, "canonical approved state"):
                gcr5ctl.validate_anchor(repo, substituted_projection)
            substituted_application = copy.deepcopy(anchor)
            substituted_application["applicationEvidenceCommit"] = approved
            with self.assertRaisesRegex(SystemExit, "HEAD binding"):
                gcr5ctl.validate_anchor(repo, substituted_application)
            substituted_successor = copy.deepcopy(anchor)
            record = substituted_successor["snapshots"][gcr5ctl.BACKLOG_PATH]
            forged = successor[gcr5ctl.BACKLOG_PATH] + b"# substituted\n"
            record["successorBase64"] = __import__("base64").b64encode(forged).decode("ascii")
            record["successorSha256"] = hashlib.sha256(forged).hexdigest()
            with self.assertRaisesRegex(SystemExit, "snapshot or application tree differs"):
                gcr5ctl.validate_anchor(repo, substituted_successor)

    def test_public_apply_and_recover_reject_real_parent_junctions_byte_stably(self) -> None:
        families = (
            ("docs", "docs"),
            ("planning", "planning"),
            ("review-site", "planning/review-site"),
            ("recoveries", "planning/review-site/recoveries"),
            ("waves", "planning/review-site/waves"),
        )
        for tag, relative in families:
            with self.subTest(family=tag), tempfile.TemporaryDirectory() as temporary:
                repo, approved, _application, _predecessor = self.approved_application_fixture(temporary)
                apply_arguments = Namespace(
                    repo=repo,
                    approved_state_commit=approved,
                    agent=gcr5ctl.ACTOR,
                    evidence=gcr5ctl.APPLICATION_EVIDENCE_PATH,
                )
                protected_before = self.protected_snapshot(repo)
                source, target = self.install_junction(repo, relative, f"apply-{tag}")
                try:
                    with self.assertRaisesRegex(SystemExit, "destination component is redirected"):
                        gcr5ctl.command_apply(apply_arguments)
                    self.assertEqual([], gcr5ctl.present_transaction_artifacts(repo))
                    for _attempt in range(2):
                        with self.assertRaisesRegex(SystemExit, "destination component is redirected"):
                            gcr5ctl.command_status(Namespace(repo=repo))
                    self.assertEqual(protected_before, self.protected_snapshot(repo))
                finally:
                    self.remove_junction(source, target)

                def interrupt(label: str) -> None:
                    if label == "gcr5-transaction-durable":
                        raise RuntimeError("prepared recovery junction fixture")

                with (
                    patch.object(gcr5ctl, "adoption_fault_boundary", side_effect=interrupt),
                    self.assertRaisesRegex(RuntimeError, "prepared recovery junction fixture"),
                ):
                    gcr5ctl.command_apply(apply_arguments)
                artifacts_before = {
                    relative_path: path.read_bytes()
                    for relative_path, path in gcr5ctl.transaction_artifacts(repo).items()
                }
                protected_before = self.protected_snapshot(repo)
                source, target = self.install_junction(repo, relative, f"recover-{tag}")
                try:
                    for _attempt in range(2):
                        with self.assertRaisesRegex(SystemExit, "destination component is redirected"):
                            gcr5ctl.command_recover(Namespace(repo=repo, agent=gcr5ctl.ACTOR))
                    self.assertEqual(protected_before, self.protected_snapshot(repo))
                    self.assertEqual(
                        artifacts_before,
                        {
                            relative_path: path.read_bytes()
                            for relative_path, path in gcr5ctl.transaction_artifacts(repo).items()
                        },
                    )
                finally:
                    self.remove_junction(source, target)

    def test_recovery_denies_manifest_dirt_and_redirects_without_mutating_protected_bytes(self) -> None:
        scenarios = ("manifest", "untracked", "tracked", "staged", "redirected")
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                repo, approved, application, predecessor = self.approved_application_fixture(temporary)
                successor = gcr5ctl.stage_successor_files(repo, application, gcr5ctl.derive_successor_backlog(repo))
                anchor = gcr5ctl.application_anchor(
                    approved_state=approved,
                    application_commit=application,
                    predecessor=predecessor,
                    successor=successor,
                )
                _state, state_payload, _approved, _evidence, evidence_payload = (
                    gcr5ctl.authenticate_application_authority(repo, expected_application=application)
                )
                transaction = gcr5ctl.transaction_document(
                    repo,
                    approved_state=approved,
                    state_payload=state_payload,
                    application_commit=application,
                    evidence_payload=evidence_payload,
                )
                artifacts = gcr5ctl.transaction_artifacts(repo)
                gcr5ctl.write_new_durable(
                    artifacts[gcr5ctl.LOCK_PATH],
                    (json.dumps(anchor, indent=2) + "\n").encode(),
                )
                gcr5ctl.write_new_durable(
                    artifacts[gcr5ctl.TRANSACTION_PATH],
                    (json.dumps(transaction, indent=2) + "\n").encode(),
                )
                gcr5ctl.write_new_durable(artifacts[gcr5ctl.BACKLOG_NEXT_PATH], successor[gcr5ctl.BACKLOG_PATH])
                if scenario == "manifest":
                    transaction["applicationEvidenceAuthority"]["commit"] = approved
                    artifacts[gcr5ctl.TRANSACTION_PATH].write_text(json.dumps(transaction), encoding="utf-8")
                elif scenario == "untracked":
                    (repo / "unexpected.txt").write_text("deny\n", encoding="utf-8")
                elif scenario == "tracked":
                    (repo / gcr5ctl.GENERATED_PATHS[0]).write_bytes(b"substituted\n")
                elif scenario == "staged":
                    (repo / "unexpected.txt").write_text("deny\n", encoding="utf-8")
                    self.git(repo, "add", "unexpected.txt")
                protected = {
                    relative: (repo / relative).read_bytes()
                    for relative in [*gcr5ctl.FINAL_PATHS, gcr5ctl.LEDGER_PATH, gcr5ctl.TRIGGER_PATH]
                }
                if scenario == "redirected":
                    redirected = artifacts[gcr5ctl.BACKLOG_NEXT_PATH]
                    with (
                        patch.object(
                            gcr5ctl.os.path,
                            "isjunction",
                            side_effect=lambda path, expected=redirected: Path(path) == expected,
                            create=True,
                        ),
                        self.assertRaisesRegex(SystemExit, "redirected"),
                    ):
                        gcr5ctl.recover_transaction(repo)
                else:
                    with self.assertRaises(SystemExit):
                        gcr5ctl.recover_transaction(repo)
                self.assertEqual(
                    protected,
                    {
                        relative: (repo / relative).read_bytes()
                        for relative in [*gcr5ctl.FINAL_PATHS, gcr5ctl.LEDGER_PATH, gcr5ctl.TRIGGER_PATH]
                    },
                )

    def test_status_and_validate_deny_noncanonical_current_boundaries(self) -> None:
        scenarios = (
            "dirty",
            "staged",
            "untracked",
            "transaction",
            "substituted-worktree-predecessor",
            "substituted-predecessor",
            "partial-successor",
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                repo, _approved, application, _predecessor = self.approved_application_fixture(temporary)
                if scenario == "dirty":
                    with (repo / "docs/README.md").open("ab") as stream:
                        stream.write(b"\nunauthorized dirt\n")
                elif scenario == "staged":
                    (repo / "unexpected.txt").write_text("staged\n", encoding="utf-8")
                    self.git(repo, "add", "unexpected.txt")
                elif scenario == "untracked":
                    (repo / "unexpected.txt").write_text("untracked\n", encoding="utf-8")
                elif scenario == "transaction":
                    artifact = gcr5ctl.transaction_artifacts(repo)[gcr5ctl.LOCK_PATH]
                    artifact.write_bytes(b"in-flight\n")
                elif scenario == "substituted-worktree-predecessor":
                    (repo / gcr5ctl.GENERATED_PATHS[0]).write_bytes(b"worktree substitution\n")
                elif scenario == "substituted-predecessor":
                    relative = gcr5ctl.GENERATED_PATHS[0]
                    (repo / relative).write_bytes(b"committed substitution\n")
                    self.commit_paths(repo, "substitute predecessor", relative)
                else:
                    successor = gcr5ctl.stage_successor_files(
                        repo,
                        application,
                        gcr5ctl.derive_successor_backlog(repo),
                    )
                    (repo / gcr5ctl.BACKLOG_PATH).write_bytes(successor[gcr5ctl.BACKLOG_PATH])
                before = {
                    relative: (repo / relative).read_bytes()
                    for relative in [*gcr5ctl.FINAL_PATHS, gcr5ctl.LEDGER_PATH, gcr5ctl.TRIGGER_PATH]
                }
                for command in (gcr5ctl.command_status, gcr5ctl.command_validate):
                    arguments = Namespace(repo=repo, require_approved=False)
                    with self.assertRaises(SystemExit):
                        command(arguments)
                self.assertEqual(
                    before,
                    {
                        relative: (repo / relative).read_bytes()
                        for relative in [*gcr5ctl.FINAL_PATHS, gcr5ctl.LEDGER_PATH, gcr5ctl.TRIGGER_PATH]
                    },
                )

    def test_child_process_fault_matrix_recovers_only_exact_terminal_snapshots(self) -> None:
        boundaries = (
            "gcr5-lock-durable",
            "gcr5-successor-durable",
            "gcr5-transaction-durable",
            "gcr5-successor-planning-implementation-plan.md",
            "gcr5-successor-backlog.yaml",
            "gcr5-successor-status-summary.md",
            "gcr5-successor-manifest.json",
            "gcr5-successor-GRR-0002.html",
            "gcr5-successor-index.html",
            "gcr5-successor-W1.html",
            "gcr5-seven-path-successor-durable",
            "gcr5-cleanup-GCR-0005.B00.application-transaction.json",
            "gcr5-cleanup-GCR-0005.B00.application.lock",
        )
        with tempfile.TemporaryDirectory() as temporary:
            repo, approved, application, predecessor = self.approved_application_fixture(temporary)
            successor = gcr5ctl.stage_successor_files(repo, application, gcr5ctl.derive_successor_backlog(repo))
            cached_successor = repo / ".git/gcr5-successor.json"
            cached_successor.write_text(
                json.dumps(
                    {relative: base64.b64encode(payload).decode("ascii") for relative, payload in successor.items()}
                ),
                encoding="utf-8",
            )
            for boundary in boundaries:
                with self.subTest(boundary=boundary):
                    for relative, payload in predecessor.items():
                        (repo / relative).write_bytes(payload)
                    self.assertEqual("", self.git(repo, "diff", "--name-only", "HEAD", "--"))
                    child = "\n".join(
                        [
                            "import base64, json, os, pathlib, sys",
                            "from argparse import Namespace",
                            f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                            "import gcr5ctl",
                            "repo = pathlib.Path(sys.argv[1])",
                            "approved = sys.argv[2]",
                            "boundary = sys.argv[3]",
                            "cached = json.loads((repo / '.git/gcr5-successor.json').read_text())",
                            "successor = {key: base64.b64decode(value) for key, value in cached.items()}",
                            "gcr5ctl.stage_successor_files = lambda *_args, **_kwargs: successor",
                            "def crash(label):",
                            "  if label == boundary: os._exit(77)",
                            "gcr5ctl.adoption_fault_boundary = crash",
                            "gcr5ctl.command_apply(Namespace(repo=repo, approved_state_commit=approved, "
                            "agent=gcr5ctl.ACTOR, evidence=gcr5ctl.APPLICATION_EVIDENCE_PATH))",
                        ]
                    )
                    result = subprocess.run(
                        [sys.executable, "-c", child, str(repo), approved, boundary],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(77, result.returncode, result.stdout + result.stderr)
                    present = gcr5ctl.present_transaction_artifacts(repo)
                    with patch.object(gcr5ctl, "stage_successor_files", return_value=successor):
                        disposition = gcr5ctl.recover_transaction(repo) if present else "ABSENT"
                    terminal = {relative: (repo / relative).read_bytes() for relative in gcr5ctl.FINAL_PATHS}
                    self.assertIn(disposition, {"ABSENT", "RESTORED_PREDECESSOR", "COMPLETED_SUCCESSOR"})
                    self.assertIn(terminal, (predecessor, successor))
                    if disposition == "ABSENT":
                        self.assertEqual(successor, terminal)
                    self.assertEqual([], gcr5ctl.present_transaction_artifacts(repo))
                    self.assertEqual("ABSENT", gcr5ctl.recover_transaction(repo))

    def test_child_process_no_manifest_rollback_fault_matrix_is_repeat_recoverable(self) -> None:
        boundaries = (
            ("gcr5-predecessor-planning-implementation-plan.md", "partial-successor"),
            ("gcr5-predecessor-backlog.yaml", "partial-successor"),
            ("gcr5-predecessor-status-summary.md", "partial-successor"),
            ("gcr5-predecessor-manifest.json", "partial-successor"),
            ("gcr5-predecessor-GRR-0002.html", "partial-successor"),
            ("gcr5-predecessor-index.html", "partial-successor"),
            ("gcr5-predecessor-W1.html", "partial-successor"),
            ("gcr5-cleanup-GCR-0005.B00.application.lock", "partial-successor"),
            ("gcr5-cleanup-GCR-0005.B00.backlog.next", "successor-scratch"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            repo, approved, application, predecessor = self.approved_application_fixture(temporary)
            successor = gcr5ctl.stage_successor_files(repo, application, gcr5ctl.derive_successor_backlog(repo))
            cached_successor = repo / ".git/gcr5-successor.json"
            cached_successor.write_text(
                json.dumps(
                    {relative: base64.b64encode(payload).decode("ascii") for relative, payload in successor.items()}
                ),
                encoding="utf-8",
            )
            bootstrap_child = "\n".join(
                [
                    "import base64, json, os, pathlib, sys",
                    "from argparse import Namespace",
                    f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                    "import gcr5ctl",
                    "repo = pathlib.Path(sys.argv[1])",
                    "approved = sys.argv[2]",
                    "cached = json.loads((repo / '.git/gcr5-successor.json').read_text())",
                    "successor = {key: base64.b64decode(value) for key, value in cached.items()}",
                    "gcr5ctl.stage_successor_files = lambda *_args, **_kwargs: successor",
                    "def crash(label):",
                    "  if label == 'gcr5-cleanup-GCR-0005.B00.application-transaction.json': os._exit(77)",
                    "gcr5ctl.adoption_fault_boundary = crash",
                    "gcr5ctl.command_apply(Namespace(repo=repo, approved_state_commit=approved, "
                    "agent=gcr5ctl.ACTOR, evidence=gcr5ctl.APPLICATION_EVIDENCE_PATH))",
                ]
            )
            scratch_child = bootstrap_child.replace(
                "gcr5-cleanup-GCR-0005.B00.application-transaction.json",
                "gcr5-successor-durable",
            )
            recover_child = "\n".join(
                [
                    "import base64, json, os, pathlib, sys",
                    "from argparse import Namespace",
                    f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                    "import gcr5ctl",
                    "repo = pathlib.Path(sys.argv[1])",
                    "boundary = sys.argv[2]",
                    "cached = json.loads((repo / '.git/gcr5-successor.json').read_text())",
                    "successor = {key: base64.b64decode(value) for key, value in cached.items()}",
                    "gcr5ctl.stage_successor_files = lambda *_args, **_kwargs: successor",
                    "def crash(label):",
                    "  if label == boundary: os._exit(78)",
                    "gcr5ctl.adoption_fault_boundary = crash",
                    "gcr5ctl.command_recover(Namespace(repo=repo, agent=gcr5ctl.ACTOR))",
                ]
            )
            for boundary, setup in boundaries:
                with self.subTest(boundary=boundary, setup=setup):
                    for relative, payload in predecessor.items():
                        (repo / relative).write_bytes(payload)
                    self.assertEqual([], gcr5ctl.present_transaction_artifacts(repo))
                    prepared = subprocess.run(
                        [
                            sys.executable,
                            "-c",
                            bootstrap_child if setup == "partial-successor" else scratch_child,
                            str(repo),
                            approved,
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(77, prepared.returncode, prepared.stdout + prepared.stderr)
                    self.assertNotIn(gcr5ctl.TRANSACTION_PATH, gcr5ctl.present_transaction_artifacts(repo))
                    interrupted = subprocess.run(
                        [sys.executable, "-c", recover_child, str(repo), boundary],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(78, interrupted.returncode, interrupted.stdout + interrupted.stderr)
                    with patch.object(gcr5ctl, "stage_successor_files", return_value=successor):
                        present = gcr5ctl.present_transaction_artifacts(repo)
                        disposition = gcr5ctl.recover_transaction(repo) if present else "ABSENT"
                        self.assertIn(disposition, {"ABSENT", "RESTORED_PREDECESSOR"})
                        self.assertEqual("ABSENT", gcr5ctl.recover_transaction(repo))
                    terminal = {relative: (repo / relative).read_bytes() for relative in gcr5ctl.FINAL_PATHS}
                    self.assertEqual(predecessor, terminal)
                    self.assertEqual([], gcr5ctl.present_transaction_artifacts(repo))

    def test_snapshot_publication_is_idempotent_after_an_injected_boundary_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.init_repo(temporary)
            backlog = repo / "planning/backlog.yaml"
            status = repo / "planning/status-summary.md"
            backlog.parent.mkdir(parents=True)
            backlog.write_bytes(b"before backlog\n")
            status.write_bytes(b"before status\n")
            self.commit_all(repo, "predecessor")
            predecessor = {
                "planning/backlog.yaml": b"before backlog\n",
                "planning/status-summary.md": b"before status\n",
            }
            successor = {
                "planning/backlog.yaml": b"after backlog\n",
                "planning/status-summary.md": b"after status\n",
            }
            calls = 0

            def fail_once(_label: str) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise RuntimeError("injected")

            with (
                patch.object(gcr5ctl, "FINAL_PATHS", list(predecessor)),
                patch.object(gcr5ctl, "adoption_fault_boundary", side_effect=fail_once),
                self.assertRaisesRegex(RuntimeError, "injected"),
            ):
                gcr5ctl._publish_snapshot(repo, successor, label="test")
            with patch.object(gcr5ctl, "FINAL_PATHS", list(predecessor)):
                gcr5ctl._validate_live_pair(repo, predecessor, successor)
                gcr5ctl._publish_snapshot(repo, successor, label="test")
            self.assertEqual(successor["planning/backlog.yaml"], backlog.read_bytes())
            self.assertEqual(successor["planning/status-summary.md"], status.read_bytes())

    def test_snapshot_post_publication_verification_rechecks_destination_components(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.init_repo(temporary)
            relative = "planning/backlog.yaml"
            destination = repo / relative
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"before\n")
            self.commit_all(repo, "predecessor")
            original_guard = gcr5ctl.guard_final_destination
            calls = 0

            def redirect_after_publication(guard_repo: Path, guard_relative: str) -> Path:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise SystemExit("redirected during publication verification")
                return original_guard(guard_repo, guard_relative)

            with (
                patch.object(gcr5ctl, "FINAL_PATHS", [relative]),
                patch.object(gcr5ctl, "guard_final_destination", side_effect=redirect_after_publication),
                self.assertRaisesRegex(SystemExit, "redirected during publication verification"),
            ):
                gcr5ctl._publish_snapshot(repo, {relative: b"after\n"}, label="verification")
            self.assertEqual(2, calls)
            self.assertEqual(b"after\n", destination.read_bytes())

    def test_snapshot_validation_rejects_substitution_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            path = repo / "planning/backlog.yaml"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"substituted\n")
            with (
                patch.object(gcr5ctl, "FINAL_PATHS", ["planning/backlog.yaml"]),
                self.assertRaisesRegex(SystemExit, "stale or substituted"),
            ):
                gcr5ctl._validate_live_pair(
                    repo,
                    {"planning/backlog.yaml": b"before\n"},
                    {"planning/backlog.yaml": b"after\n"},
                )


if __name__ == "__main__":
    unittest.main()
