from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import taskctl  # noqa: E402
import ui_change_gate as ui_gate  # noqa: E402
from ui_change_gate import (  # noqa: E402
    APPLICATION_INVENTORY_HARDENING_ENVELOPE,
    additive_preimplementation_quality_scope_errors,
    application_activation_errors,
    automatic_base,
    immutable_record,
    independent_identity,
    independent_review_hardening_errors,
    provenance_reference_handoff_errors,
    require_resumed_hold,
    restoration_classification_errors,
    restoration_segments,
    reviewed_historical_hardening_errors,
    validate,
)


class UiChangeGateTests(unittest.TestCase):
    def intentional_git_fixture(self, temporary: str) -> tuple[Path, str, str, str, dict[str, Any]]:
        """Extend the real approved ECR history in an isolated Git clone."""
        root = Path(temporary) / "intentional-fixture"
        protected_config = Path(temporary) / "fixture-gitconfig"
        protected_config.write_text(f"[safe]\n\tdirectory = {(REPO / '.git').as_posix()}\n", encoding="utf-8")
        clone = subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--shared",
                "--no-checkout",
                str(REPO),
                str(root),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_CONFIG_GLOBAL": str(protected_config)},
        )
        self.assertEqual(0, clone.returncode, clone.stderr)
        self.git(root, "config", "user.name", "UI Gate Test")
        self.git(root, "config", "user.email", "ui-gate@example.invalid")
        self.git(root, "config", "core.autocrlf", "false")
        self.git(root, "switch", "-c", "fixture", "042de15c")
        backlog_path = root / "planning/backlog.yaml"
        backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
        amendment = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A01")
        t01, t02 = amendment["tasks"]
        control_base = t01["base_sha"]
        for relative in ui_gate.INTENTIONAL_AMENDMENT_CONTROL_PATHS:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, target)
            if relative == "docs/adr/index.json":
                reviewed_index = json.loads(target.read_text(encoding="utf-8"))
                reviewed_index["records"] = [
                    record for record in reviewed_index["records"] if record["id"] != "ADR-0036"
                ]
                self.write_json(target, reviewed_index)
        candidate = self.commit(root, "synthetic T01 gate/schema/ADR candidate")
        evidence_path = "artifacts/evidence/W2.A01.T01.json"
        reviewed_paths = sorted(ui_gate.changed_paths(root, control_base, candidate))
        selection = {
            "riskAnalysis": "Fixture checks the exact amendment control and immutable Git review lineage.",
            "deferred": ["full Wave exit"],
            "selectedCommandIds": ["foundation:unit"],
        }
        manifest = {
            "taskId": "W2.A01.T01",
            "commit": candidate,
            "baseCommit": control_base,
            "branch": "fixture",
            "changedFiles": reviewed_paths,
            "checks": [{"command": "synthetic focused Git fixture", "exitCode": 0}],
            "acceptanceCriteria": [
                {"criterion_index": index, "evidence": ["synthetic control review fixture"]}
                for index, _criterion in enumerate(t01["acceptance_criteria"], start=1)
            ],
            "unverifiedItems": [],
            "verificationSelection": selection,
        }
        self.write_json(root / evidence_path, manifest)
        evidence_sha = hashlib.sha256((root / evidence_path).read_bytes()).hexdigest()
        evidence_ref = {
            "type": "criterion-manifest",
            "path": evidence_path,
            "sha256": evidence_sha,
            "commit": candidate,
            "recorded_at": "2026-10-02T20:00:00Z",
        }
        self.commit(root, "synthetic T01 evidence delivery")
        submission = {
            "id": "R01",
            "submitted_by": t01["owner"],
            "submitted_at": "2026-10-02T20:00:00Z",
            "candidate_commit": candidate,
            "base_commit": control_base,
            "branch": "fixture",
            "evidence_reference": evidence_ref,
            "acceptance_criteria_sha256": taskctl.canonical_json_sha256(t01["acceptance_criteria"]),
            "changed_paths": reviewed_paths,
            "selected_checks": ["synthetic focused Git fixture"],
            "selected_command_ids": ["foundation:unit"],
            "deferred_checks": ["full Wave exit"],
            "selection_rationale": selection["riskAnalysis"],
            "selection_sha256": taskctl.canonical_json_sha256(selection),
            "prior_attempt_id": None,
            "open_finding_ids": [],
            "root_cause_analysis": None,
        }
        submission["packet_sha256"] = taskctl.task_submission_packet_sha256(submission)
        t01.update(
            status="REVIEW",
            evidence=[evidence_ref],
            review_control={"version": 1, "attempts": [], "current_submission": submission},
        )
        self.write_yaml(backlog_path, backlog)
        self.commit(root, "freeze synthetic T01 submission")
        reviewer = "agent:/root/fixture-independent-review"
        review = {
            "reviewer": reviewer,
            "result": "approved",
            "reviewed_at": "2026-10-02T20:01:00Z",
            "notes": "Synthetic committed-git fixture: no product approval claim.",
        }
        ledger_path = "artifacts/evidence/W2.A01.T01.review-R01.json"
        self.write_json(
            root / ledger_path,
            {
                "task_id": "W2.A01.T01",
                "attempt_id": "R01",
                "candidate_commit": candidate,
                "reviewer": reviewer,
                "result": "approved",
                "notes": review["notes"],
                "findings": [],
                "closures": [],
            },
        )
        ledger_sha = hashlib.sha256((root / ledger_path).read_bytes()).hexdigest()
        attempt = {
            "submission": submission,
            "review": review,
            "ledger": {"path": ledger_path, "sha256": ledger_sha},
            "findings": [],
            "closures": [],
        }
        attempt["telemetry"] = taskctl.build_task_review_telemetry_event(t01, attempt)
        t01.update(
            status="DONE",
            lease=None,
            verification_state="passed",
            evidence=[evidence_ref],
            review=review,
            completed_at="2026-10-02T20:01:00Z",
            review_control={
                "version": 1,
                "attempts": [attempt],
                "current_submission": None,
            },
        )
        t02["status"] = "READY"
        amendment["campaign"]["branch"] = "fixture"
        self.write_yaml(backlog_path, backlog)
        self.commit(root, "synthetic independent T01 disposition")
        later_index_path = root / "docs/adr/index.json"
        later_index = json.loads(later_index_path.read_text(encoding="utf-8"))
        later_index["records"].append(
            {
                "id": "ADR-0036",
                "path": "docs/adr/ADR-0036-synthetic-verifier-maintenance.md",
                "title": "Synthetic append-only index probe after T01 review",
                "status": "Proposed",
                "linkedTasks": ["W2.A01.T01"],
            }
        )
        self.write_json(later_index_path, later_index)
        (root / "docs/adr/ADR-0036-synthetic-verifier-maintenance.md").write_text(
            "# Synthetic independent verifier maintenance\n", encoding="utf-8"
        )
        self.commit(root, "append independent ADR-0036 after T01 review")
        (root / "artifacts/evidence/W2.A01.T01.fixture-boundary.txt").write_text(
            "Separate reviewed-control and next-task base.\n", encoding="utf-8"
        )
        base = self.commit(root, "exact T02 claim base")
        t02.update(
            status="IN_PROGRESS",
            owner="codex-w2-implementation",
            branch="fixture",
            worktree=".",
            base_sha=base,
            started_at="2026-10-02T20:02:00Z",
            lease={
                "claimed_by": "codex-w2-implementation",
                "claimed_at": "2026-10-02T20:02:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )
        self.write_yaml(backlog_path, backlog)
        self.commit(root, "exact T02 claim")

        approval = json.loads((root / "planning/wave-amendment-approvals/W2.A01.json").read_text(encoding="utf-8"))
        proposal_root = root / "planning/W2-reference-1.8"
        proposed_manifest = yaml.safe_load((proposal_root / "REFERENCE_MANIFEST.yaml").read_text(encoding="utf-8"))
        proposal_package_sha = hashlib.sha256(
            json.dumps(
                proposed_manifest["file_hashes"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        design_approval_path = "planning/reference-approvals/RO-UI-ACADEMIC-MINIMAL-1.8.json"
        self.write_json(
            root / design_approval_path,
            {
                "schemaVersion": "1.0",
                "kind": "ui-reference-design-approval",
                "referenceId": "RO-UI-ACADEMIC-MINIMAL-1.8",
                "approvedBy": approval["approvedBy"],
                "approvedAt": approval["approvedAt"],
                "scope": "reference-publication-and-plan-binding-only",
                "proposal": {
                    "commit": approval["packet"]["commit"],
                    "path": "planning/W2-reference-1.8",
                    "packageSha256": proposal_package_sha,
                },
                "amendmentApproval": {
                    "path": "planning/wave-amendment-approvals/W2.A01.json",
                    "sha256": amendment["approval_reference"]["sha256"],
                    "introductionCommit": amendment["approval_reference"]["introduction_commit"],
                },
                "basis": "ECR-0009 exact human W2.A01 approval; synthetic committed-git fixture.",
            },
        )
        target_root = root / "design/ui-reference"
        for path in target_root.rglob("*"):
            if (
                path.is_file()
                and path.relative_to(target_root).as_posix()
                not in [
                    *proposed_manifest["governed_files"],
                    "REFERENCE_MANIFEST.yaml",
                    *ui_gate.REFERENCE_EXCLUSIONS,
                ]
                and not path.relative_to(target_root).as_posix().startswith("previews/")
            ):
                path.unlink()
        for relative in proposed_manifest["governed_files"]:
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            shutil.copyfile(proposal_root / relative, target)
        published_approval = yaml.safe_load((target_root / "APPROVAL.yaml").read_text(encoding="utf-8"))
        published_approval.update(
            status="approved",
            approved_by=approval["approvedBy"],
            approved_at=approval["approvedAt"],
            approval_basis="ECR-0009 exact owner decision and new 1.8 reference approval record.",
            authority={
                "amendment_id": "W2.A01",
                "change_request_id": "ECR-0009",
                "approval_record": "planning/wave-amendment-approvals/W2.A01.json",
                "approval_record_sha256": amendment["approval_reference"]["sha256"],
                "approval_record_introduction_commit": amendment["approval_reference"]["introduction_commit"],
            },
        )
        self.write_yaml(target_root / "APPROVAL.yaml", published_approval)
        published_manifest = copy.deepcopy(proposed_manifest)
        published_manifest["status"] = "approved"
        published_manifest["file_hashes"]["APPROVAL.yaml"] = hashlib.sha256(
            ui_gate.canonical_payload("APPROVAL.yaml", (target_root / "APPROVAL.yaml").read_bytes())
        ).hexdigest()
        self.write_yaml(target_root / "REFERENCE_MANIFEST.yaml", published_manifest)
        publication = self.commit(root, "publish exact approved 1.8 reference")
        state, reference_errors = ui_gate.reference_state(
            root, publication, json.loads((root / "ui-change-policy.json").read_text())
        )
        self.assertEqual([], reference_errors)
        ui_path = "apps/desktop/src/app/ImportReviewPane.tsx"
        with (root / ui_path).open("a", encoding="utf-8") as stream:
            stream.write("\n// Synthetic W2.A01.T02 renderer lineage fixture.\n")
        contract: dict[str, Any] = self.contract(
            "intentional-design-change",
            state["packageSha256"],
            publication,
            approved_by=approval["approvedBy"],
            previous="RO-UI-ACADEMIC-MINIMAL-1.7",
            reference_id="RO-UI-ACADEMIC-MINIMAL-1.8",
            version="1.8",
            implementation_agent="agent:codex-w2-implementation",
            task_id="W2.A01.T02",
        )
        contract["schemaVersion"] = "1.2"
        contract["changedFiles"] = [ui_path]
        contract["intentionalAmendmentAuthority"] = {
            "amendmentId": "W2.A01",
            "changeRequestId": "ECR-0009",
            "controlTaskId": "W2.A01.T01",
            "referenceApprovalPath": design_approval_path,
        }
        self.write_json(root / "artifacts/evidence/ui-change/W2.A01.T02.json", contract)
        head = self.commit(root, "render exact approved 1.8 interaction")
        return root, base, head, candidate, contract

    def adopted_continuation_git_fixture(
        self, temporary: str, *, inject_unapproved_control_source: bool = False
    ) -> tuple[Path, str, str, dict[str, Any], dict[str, Any]]:
        """Extend real W2 history with test-only reviewed/adopted control records."""
        root = Path(temporary) / "adopted-continuation-fixture"
        protected_config = Path(temporary) / "fixture-gitconfig"
        protected_config.write_text(f"[safe]\n\tdirectory = {(REPO / '.git').as_posix()}\n", encoding="utf-8")
        clone = subprocess.run(
            ["git", "clone", "--quiet", "--shared", "--no-checkout", str(REPO), str(root)],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_CONFIG_GLOBAL": str(protected_config)},
        )
        self.assertEqual(0, clone.returncode, clone.stderr)
        self.git(root, "config", "user.name", "UI Gate Test")
        self.git(root, "config", "user.email", "ui-gate@example.invalid")
        self.git(root, "config", "core.autocrlf", "false")
        self.git(root, "switch", "-C", "codex/w2-implementation", "23b019825f944e75edb6420b742e82f1216be7c6")
        backlog_path = root / "planning/backlog.yaml"
        backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
        amendment = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A02")
        control_task = amendment["tasks"][0]
        owner = "codex-w2-implementation"
        branch = "codex/w2-implementation"
        control_base = self.git(root, "rev-parse", "HEAD")
        control_task.update(
            status="IN_PROGRESS",
            owner=owner,
            branch=branch,
            worktree=".",
            base_sha=control_base,
            started_at="2026-10-03T11:43:44+00:00",
            updated_at="2026-10-03T11:43:44+00:00",
            lease={
                "claimed_by": owner,
                "claimed_at": "2026-10-03T11:43:44+00:00",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )
        self.write_yaml(backlog_path, backlog)
        self.commit(root, "synthetic control task claim")
        for relative in (
            "design/ui-change.schema.json",
            "tools/ui_change_gate.py",
            "tests/foundation/test_ui_change_gate.py",
            "docs/automation/design-first-ui-changes.md",
            "docs/adr/ADR-0037-authenticate-adopted-attachment-ui-continuation.md",
            "docs/adr/index.json",
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, target)
        if inject_unapproved_control_source:
            injected = root / "workers/document/injected_control.py"
            self.assertFalse(injected.exists())
            injected.write_text("INJECTED_CONTROL = True\n", encoding="utf-8")
        control_candidate = self.commit(root, "synthetic W2.A02.T01 control candidate")
        changed = sorted(ui_gate.changed_paths(root, control_base, control_candidate))
        evidence_path = "artifacts/evidence/W2.A02.T01.json"
        selection = {
            "riskAnalysis": "Synthetic real-Git authority fixture; no production approval claim.",
            "deferred": ["real product qualification"],
            "selectedCommandIds": ["foundation:unit"],
        }
        self.write_json(
            root / evidence_path,
            {
                "taskId": "W2.A02.T01",
                "commit": control_candidate,
                "baseCommit": control_base,
                "branch": branch,
                "changedFiles": changed,
                "checks": [{"command": "synthetic real-Git fixture", "exitCode": 0}],
                "acceptanceCriteria": [
                    {"criterion_index": index, "evidence": ["synthetic fixture boundary"]}
                    for index, _ in enumerate(control_task["acceptance_criteria"], start=1)
                ],
                "unverifiedItems": [],
                "verificationSelection": selection,
            },
        )
        evidence_sha = hashlib.sha256((root / evidence_path).read_bytes()).hexdigest()
        evidence_ref = {
            "type": "criterion-manifest",
            "path": evidence_path,
            "sha256": evidence_sha,
            "commit": control_candidate,
            "recorded_at": "2026-10-03T12:00:00Z",
        }
        self.commit(root, "synthetic control evidence delivery")
        submission = {
            "id": "R01",
            "submitted_by": owner,
            "submitted_at": "2026-10-03T12:00:00Z",
            "candidate_commit": control_candidate,
            "base_commit": control_base,
            "branch": branch,
            "evidence_reference": evidence_ref,
            "acceptance_criteria_sha256": taskctl.canonical_json_sha256(control_task["acceptance_criteria"]),
            "changed_paths": changed,
            "selected_checks": ["synthetic real-Git fixture"],
            "selected_command_ids": ["foundation:unit"],
            "deferred_checks": selection["deferred"],
            "selection_rationale": selection["riskAnalysis"],
            "selection_sha256": taskctl.canonical_json_sha256(selection),
            "prior_attempt_id": None,
            "open_finding_ids": [],
            "root_cause_analysis": None,
        }
        submission["packet_sha256"] = taskctl.task_submission_packet_sha256(submission)
        control_task.update(
            status="REVIEW",
            verification_state="passed",
            evidence=[evidence_ref],
            review_control={"version": 1, "attempts": [], "current_submission": submission},
        )
        self.write_yaml(backlog_path, backlog)
        self.commit(root, "freeze synthetic W2.A02.T01 submission")
        reviewer = "agent:/root/synthetic-independent-control-review"
        notes = "Test-only Git fixture; no product or owner approval claim."
        ledger_path = "artifacts/evidence/W2.A02.T01.review-R01.json"
        self.write_json(
            root / ledger_path,
            {
                "task_id": "W2.A02.T01",
                "attempt_id": "R01",
                "candidate_commit": control_candidate,
                "reviewer": reviewer,
                "result": "approved",
                "notes": notes,
                "findings": [],
                "closures": [],
            },
        )
        review = {"reviewer": reviewer, "result": "approved", "reviewed_at": "2026-10-03T12:01:00Z", "notes": notes}
        attempt = {
            "submission": submission,
            "review": review,
            "ledger": {"path": ledger_path, "sha256": hashlib.sha256((root / ledger_path).read_bytes()).hexdigest()},
            "findings": [],
            "closures": [],
        }
        attempt["telemetry"] = taskctl.build_task_review_telemetry_event(control_task, attempt)
        control_task.update(
            status="DONE",
            lease=None,
            completed_at=review["reviewed_at"],
            updated_at=review["reviewed_at"],
            review=review,
            review_control={"version": 1, "attempts": [attempt], "current_submission": None},
        )
        self.write_yaml(backlog_path, backlog)
        self.commit(root, "synthetic independent W2.A02.T01 disposition")

        # A separate test-only contribution record precedes the exit request.
        contribution_path = "artifacts/evidence/W2.A02.S01.review-01.json"
        self.write_json(
            root / contribution_path,
            {
                "schemaVersion": "1.0",
                "documentType": "amendment-contribution-independent-review",
                "sliceId": "W2.A02.S01",
                "amendmentId": "W2.A02",
                "capabilityId": "CAP-05",
                "reviewer": "agent:/root/synthetic-independent-slice-review",
                "result": "approved",
                "taskBindings": [{"taskId": "W2.A02.T01", "candidateCommit": control_candidate}],
                "findings": [],
                "openFindingIds": [],
                "notes": "Synthetic fixture only; no production slice disposition.",
            },
        )
        contribution_commit = self.commit(root, "synthetic independent W2.A02.S01 contribution")
        packet = json.loads(
            (root / "planning/enabler-change-requests/ECR-0010.packet.json").read_text(encoding="utf-8")
        )
        exit_path = "artifacts/evidence/W2.A02.exit.json"
        wave = next(item for item in backlog["waves"] if item["id"] == "W2")
        self.write_json(
            root / exit_path,
            {
                "schemaVersion": "1.0",
                "documentType": "wave-amendment-exit-evidence",
                "amendmentId": "W2.A02",
                "changeRequestId": "ECR-0010",
                "targetWave": "W2",
                "branch": branch,
                "candidateCommit": contribution_commit,
                "outcome": "ready-for-independent-amendment-exit-review",
                "waveCampaign": {
                    "status": wave["campaign"]["status"],
                    "scope": wave["campaign"]["scope"],
                    "pauseReason": wave["campaign"]["pause_reason"],
                },
                "amendmentCampaign": {"status": "ACTIVE", "scope": "wave-amendment", "pauseReason": None},
                "requiredNextTransition": "independent amendment exit review",
                "acceptanceClosure": [
                    {
                        "criterionIndex": index,
                        "criterion": criterion,
                        "status": "ready-for-independent-exit-disposition",
                    }
                    for index, criterion in enumerate(packet["acceptanceCriteria"], start=1)
                ],
                "checks": [{"command": "synthetic real-Git authority fixture", "result": "passed"}],
            },
        )
        exit_evidence_commit = self.commit(root, "synthetic W2.A02 exit evidence")
        exit_submission = taskctl.build_amendment_exit_submission(
            Namespace(file=str(backlog_path), amendment="W2.A02", agent=owner),
            backlog,
            amendment,
            str(root / exit_path),
        )
        amendment["lifecycle"]["status"] = "REVIEW"
        amendment["lifecycle"]["history"].append(
            {
                "id": "E04",
                "status": "REVIEW",
                "actor": owner,
                "at": "2026-10-03T12:02:00Z",
                "rationale": "Synthetic exit submission.",
            }
        )
        amendment["campaign"].update(status="REVIEW", lease=None)
        amendment["completion"].update(
            status="REVIEW",
            evidence=[exit_path],
            exit_review_control={"version": 1, "attempts": [], "current_submission": exit_submission},
        )
        self.write_yaml(backlog_path, backlog)
        reviewed_state = self.commit(root, "freeze synthetic W2.A02 exit submission")
        exit_reviewer = "agent:/root/synthetic-independent-exit-review"
        exit_ledger_path = "artifacts/evidence/W2.A02.exit-review-R01.json"
        exit_ledger = {
            "amendment_id": "W2.A02",
            "attempt_id": "R01",
            "reviewed_state_commit": reviewed_state,
            "candidate_commit": exit_evidence_commit,
            "reviewer": exit_reviewer,
            "result": "approved",
            "notes": "Test-only review of synthetic committed history.",
            "evidence": {
                "path": exit_path,
                "sha256": exit_submission["evidence_reference"]["sha256"],
            },
            "findings": [],
            "closures": [],
        }
        self.write_json(root / exit_ledger_path, exit_ledger)
        exit_attempt = taskctl.prepare_amendment_exit_attempt(
            amendment,
            exit_submission,
            exit_ledger_path,
            (root / exit_ledger_path).read_bytes(),
            exit_ledger,
            reviewer=exit_reviewer,
            result="approved",
        )
        amendment["campaign"].update(status="COMPLETE", lease=None)
        amendment["completion"].update(
            status="APPROVED",
            reviewer=exit_reviewer,
            reviewed_at=exit_attempt["review"]["reviewed_at"],
            notes="Synthetic fixture only.",
            exit_review_control={"version": 1, "attempts": [exit_attempt], "current_submission": None},
        )
        self.write_yaml(backlog_path, backlog)
        approved_completion_commit = self.commit(root, "synthetic independent W2.A02 exit disposition")
        adoption_path = "artifacts/evidence/W2.A02.adoption.json"
        self.write_json(
            root / adoption_path,
            {
                "schemaVersion": "1.0",
                "documentType": "wave-amendment-adoption-evidence",
                "amendmentId": "W2.A02",
                "targetWave": "W2",
                "branch": branch,
                "candidateCommit": approved_completion_commit,
                "reviewedCompletionCommit": approved_completion_commit,
                "approvedExitAttempt": "R01",
                "notes": "Synthetic fixture only; no production adoption claim.",
            },
        )
        adoption_evidence_sha = hashlib.sha256((root / adoption_path).read_bytes()).hexdigest()
        adoption_evidence_commit = self.commit(root, "synthetic W2.A02 checkpoint evidence")
        wave.setdefault("checkpoints", []).append(
            {
                "id": "W2.CP03",
                "kind": "security",
                "recorded_by": owner,
                "recorded_at": "2026-10-03T12:04:00Z",
                "evidence": [
                    {
                        "type": "amendment-adoption-evidence",
                        "amendment_id": "W2.A02",
                        "path": adoption_path,
                        "sha256": adoption_evidence_sha,
                        "commit": adoption_evidence_commit,
                    }
                ],
                "notes": "Synthetic W2.A02 control/security checkpoint.",
            }
        )
        amendment["lifecycle"]["status"] = "ADOPTED"
        amendment["lifecycle"]["history"].append(
            {
                "id": "E05",
                "status": "ADOPTED",
                "actor": owner,
                "at": "2026-10-03T12:05:00Z",
                "rationale": "Synthetic test-only adoption.",
            }
        )
        backlog["control_plane"]["active_amendment"] = None
        wave["campaign"]["scope"] = "wave"
        self.write_yaml(backlog_path, backlog)
        adoption = self.commit(root, "synthetic W2.A02 adoption transition")
        return root, adoption, branch, backlog, amendment

    def approve_activation_fixture_task(
        self,
        root: Path,
        backlog: dict[str, Any],
        task: dict[str, Any],
        candidate: str,
        *,
        result: str = "approved",
        findings: list[dict[str, Any]] | None = None,
        closures: list[dict[str, Any]] | None = None,
    ) -> str:
        """Record a test-only, commit-bound independent task disposition."""
        identity = str(task["id"])
        owner = "codex-w2-implementation"
        branch = "codex/w2-implementation"
        attempts = (task.get("review_control") or {}).get("attempts") or []
        findings, closures = findings or [], closures or []
        round_id = f"R{len(attempts) + 1:02d}"
        prior = attempts[-1]["submission"] if attempts else None
        base = str(prior["candidate_commit"] if prior else task["base_sha"])
        changed = sorted(ui_gate.changed_paths(root, base, candidate))
        evidence_path = f"artifacts/evidence/{identity}{'-' + round_id if prior else ''}.json"
        selection = {
            "riskAnalysis": "Disposable real-Git activation authority fixture; no product qualification claim.",
            "deferred": ["real desktop capture and Wave qualification"],
            "selectedCommandIds": ["foundation:unit"],
        }
        self.write_json(
            root / evidence_path,
            {
                **(
                    {"supersedes": {key: prior["evidence_reference"][key] for key in ("path", "sha256", "commit")}}
                    if prior
                    else {}
                ),
                "taskId": identity,
                "commit": candidate,
                "baseCommit": base,
                "branch": branch,
                "changedFiles": changed,
                "checks": [{"command": "synthetic Git lineage fixture", "exitCode": 0}],
                "acceptanceCriteria": [
                    {"criterion_index": index, "evidence": ["test-only authority fixture"]}
                    for index, _ in enumerate(task["acceptance_criteria"], start=1)
                ],
                "unverifiedItems": [],
                "verificationSelection": selection,
            },
        )
        evidence_sha = hashlib.sha256((root / evidence_path).read_bytes()).hexdigest()
        evidence_ref = {
            "type": "criterion-manifest",
            "path": evidence_path,
            "sha256": evidence_sha,
            "commit": candidate,
            "recorded_at": "2026-10-03T22:00:00Z",
        }
        self.commit(root, f"synthetic {identity} criterion evidence")
        submission = {
            "id": round_id,
            "submitted_by": owner,
            "submitted_at": "2026-10-03T22:00:00Z",
            "candidate_commit": candidate,
            "base_commit": base,
            "branch": branch,
            "evidence_reference": evidence_ref,
            "acceptance_criteria_sha256": taskctl.canonical_json_sha256(task["acceptance_criteria"]),
            "changed_paths": changed,
            "selected_checks": ["synthetic Git lineage fixture"],
            "selected_command_ids": ["foundation:unit"],
            "deferred_checks": selection["deferred"],
            "selection_rationale": selection["riskAnalysis"],
            "selection_sha256": taskctl.canonical_json_sha256(selection),
            "prior_attempt_id": prior["id"] if prior else None,
            "open_finding_ids": sorted(str(item["id"]) for attempt in attempts for item in attempt["findings"]),
            "root_cause_analysis": None,
        }
        submission["packet_sha256"] = taskctl.task_submission_packet_sha256(submission)
        task.update(
            status="REVIEW",
            verification_state="passed",
            evidence=[*task.get("evidence", []), evidence_ref],
            review_control={"version": 1, "attempts": attempts, "current_submission": submission},
        )
        self.write_yaml(root / "planning/backlog.yaml", backlog)
        self.commit(root, f"synthetic {identity} frozen submission")
        reviewer = "agent:/root/synthetic-independent-activation-review"
        notes = "Test-only Git authority fixture; no actual task approval or desktop qualification."
        ledger_path = f"artifacts/evidence/{identity}.review-{round_id}.json"
        self.write_json(
            root / ledger_path,
            {
                "task_id": identity,
                "attempt_id": round_id,
                "candidate_commit": candidate,
                "reviewer": reviewer,
                "result": result,
                "notes": notes,
                "findings": findings,
                "closures": closures,
            },
        )
        review = {"reviewer": reviewer, "result": result, "reviewed_at": "2026-10-03T22:01:00Z", "notes": notes}
        attempt = {
            "submission": submission,
            "review": review,
            "ledger": {"path": ledger_path, "sha256": hashlib.sha256((root / ledger_path).read_bytes()).hexdigest()},
            "findings": findings,
            "closures": closures,
        }
        attempt["telemetry"] = taskctl.build_task_review_telemetry_event(task, attempt)
        task.update(
            status="DONE" if result == "approved" else "IN_PROGRESS",
            lease=None if result == "approved" else task["lease"],
            completed_at=review["reviewed_at"] if result == "approved" else None,
            updated_at=review["reviewed_at"],
            review=review,
            review_control={"version": 1, "attempts": [*attempts, attempt], "current_submission": None},
        )
        if identity == "W2.A03.T01":
            next_task = next(item for item in backlog["wave_amendments"][-1]["tasks"] if item["id"] == "W2.A03.T02")
            next_task["status"] = "READY"
        self.write_yaml(root / "planning/backlog.yaml", backlog)
        return self.commit(root, f"synthetic {identity} independent disposition")

    @staticmethod
    def activation_fixture_finding(identity: str) -> dict[str, Any]:
        return {
            "id": identity,
            "severity": "high",
            "blocking": True,
            "criterion_index": 4,
            "title": "Synthetic append-only remediation",
            "required_remediation": "Preserve and close in a descendant.",
            "reproduction": "Disposable fixture only.",
        }

    def reference_activation_git_fixture(
        self,
        temporary: str,
        *,
        inject_unapproved_site_asset: bool = False,
        correction: bool = False,
        correction_attack: str | None = None,
        correction_remediation: bool = False,
    ) -> tuple[Path, str, dict[str, Any], str, str, str]:
        """Extend actual GOV26/C10/A03 Git ancestry with test-only future adoption."""
        root = Path(temporary) / "reference-activation-fixture"
        protected_config = Path(temporary) / "fixture-gitconfig"
        protected_config.write_text(f"[safe]\n\tdirectory = {(REPO / '.git').as_posix()}\n", encoding="utf-8")
        clone = subprocess.run(
            ["git", "clone", "--quiet", "--shared", "--no-checkout", str(REPO), str(root)],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_CONFIG_GLOBAL": str(protected_config)},
        )
        self.assertEqual(0, clone.returncode, clone.stderr)
        self.git(root, "config", "user.name", "UI Gate Test")
        self.git(root, "config", "user.email", "ui-gate@example.invalid")
        self.git(root, "config", "core.autocrlf", "false")
        self.git(
            root,
            "switch",
            "-C",
            "codex/w2-implementation",
            "53d510464e2f9a2ab64bc9e78d09ae7b3996bba7" if correction else "9824e2ba",
        )
        backlog_path = root / "planning/backlog.yaml"
        backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
        amendment = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A03")
        t01, t02 = amendment["tasks"]
        if correction:
            self.assertFalse(inject_unapproved_site_asset)
            self.assertEqual("DONE", t01["status"])
            self.assertEqual("BLOCKED", t02["status"])
            frozen_parent = copy.deepcopy(amendment)
            child = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A04")
            child_task = child["tasks"][0]
            self.assertEqual("IN_PROGRESS", child_task["status"])
            # Test-only persisted renewal keeps the fixture independent of wall
            # time without changing the real claim or mocking lease checks.
            child_task["lease"]["expires_at"] = "2099-01-01T00:00:00Z"
            child["campaign"]["lease"]["expires_at"] = "2099-01-01T00:00:00Z"
            self.write_yaml(backlog_path, backlog)
            self.commit(root, "test-only persisted A04 task and campaign renewal")
            correction_source = {
                "tools/ui_change_gate.py",
                "tests/foundation/test_ui_change_gate.py",
                "docs/automation/design-first-ui-changes.md",
                "docs/adr/index.json",
                "docs/adr/ADR-0040-document-protected-desktop-activation-correction.md",
            }
            for relative in correction_source:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((REPO / relative).read_bytes())
                if relative == "docs/adr/index.json":
                    target.write_bytes(ui_gate.blob(REPO, "a8f864b847170c62b1e03422911eee862fa4a50d", relative))
                # Touch an unchanged Python input during the test-first pass.
                if (
                    relative.endswith(".py")
                    and ui_gate.tree_entry(root, "HEAD", relative) is not None
                    and target.read_bytes() == ui_gate.blob(root, "HEAD", relative)
                ):
                    target.write_bytes(target.read_bytes() + b"\n# Test-only correction source touch.\n")
            if correction_attack == "hidden-source":
                extra = root / "tools/undeclared_activation_source.py"
                extra.write_bytes(b"# Unapproved intermediate source, later removed.\n")
                self.commit(root, "test-only unapproved hidden correction source")
                extra.unlink()
            if correction_attack == "mixed-consumer":
                consumer_path = root / "apps/desktop/scripts/assemble-reference.mjs"
                consumer_path.write_bytes(consumer_path.read_bytes() + b"\n// Unapproved mixed consumer delivery.\n")
            if correction_attack == "extra-adr-index":
                registry_path = root / "docs/adr/index.json"
                registry = json.loads(registry_path.read_bytes())
                registry["records"].append({"id": "ADR-0041", "status": "Proposed"})
                self.write_json(registry_path, registry)
            if correction_attack == "nonregular-source":
                self.git(root, "add", "docs/automation/design-first-ui-changes.md")
                self.git(root, "update-index", "--chmod=+x", "docs/automation/design-first-ui-changes.md")
            if correction_attack == "changed-ordinary":
                original = ui_gate.backlog_task(backlog, "CAP-05.S01.T01")
                assert original is not None
                frozen_notes = original["implementation_notes"]
                original["implementation_notes"] = "Unapproved intermediate change to original W2 task."
                self.write_yaml(backlog_path, backlog)
                self.commit(root, "test-only intermediate ordinary task tampering")
                original["implementation_notes"] = frozen_notes
                self.write_yaml(backlog_path, backlog)
            if correction_attack == "unbound-task-evidence":
                self.write_json(root / "artifacts/evidence/W2.A04.T01-R02.json", {"unbound": True})
            child_candidate = self.commit(root, "test-only A04 five-source correction candidate")
            if correction_remediation:
                finding = self.activation_fixture_finding("SYN-T01-F01")
                self.approve_activation_fixture_task(
                    root, backlog, child_task, child_candidate, result="changes-requested", findings=[finding]
                )
                procedure = root / "docs/automation/design-first-ui-changes.md"
                procedure.write_bytes(procedure.read_bytes() + b"\nTest-only append-only remediation evidence.\n")
                child_candidate = self.commit(root, "synthetic reviewed-task remediation candidate")
                self.approve_activation_fixture_task(
                    root,
                    backlog,
                    child_task,
                    child_candidate,
                    closures=[
                        {"finding_id": finding["id"], "disposition": "fixed", "evidence": "synthetic descendant"}
                    ],
                )
            else:
                self.approve_activation_fixture_task(root, backlog, child_task, child_candidate)
            if correction_attack == "missing-return":
                t02["status"] = "READY"
            self.complete_activation_fixture_amendment(
                root,
                backlog,
                child,
                {child_task["id"]: child_candidate},
                remediation=correction_remediation,
                security_attack=correction_attack,
            )
            if correction_attack == "missing-return":
                t02["status"] = "BLOCKED"
            self.assertEqual(frozen_parent, amendment)
            if correction_attack == "unbound-exit-evidence":
                self.write_json(root / "artifacts/evidence/W2.A04.exit-R02.json", {"unbound": True})
                self.commit(root, "test-only unbound correction exit artifact")
            if correction_attack == "premature-consumer":
                consumer_path = root / "apps/desktop/scripts/assemble-reference.mjs"
                consumer_path.write_bytes(consumer_path.read_bytes() + b"\n// Consumer before A03 activation/reopen.\n")
                self.commit(root, "test-only premature consumer after correction return")
            lease = {
                "claimed_by": t02["owner"],
                "claimed_at": "2026-10-04T14:10:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
            }
            amendment["campaign"].update(
                status="ACTIVE",
                base_sha=self.git(root, "rev-parse", "HEAD"),
                pause_reason=None,
                lease=lease,
                updated_at="2026-10-04T14:10:00Z",
            )
            if correction_attack == "foreign-activation":
                amendment["campaign"]["owner"] = "foreign-agent"
            amendment["lifecycle"]["status"] = "ACTIVE"
            amendment["lifecycle"]["history"].append(
                {
                    "id": f"E{len(amendment['lifecycle']['history']) + 1:02d}",
                    "status": "ACTIVE",
                    "actor": t02["owner"],
                    "at": "2026-10-04T14:10:00Z",
                    "rationale": "Test-only separate A03 activation; T02 remains blocked.",
                }
            )
            backlog["control_plane"]["active_amendment"] = "W2.A03"
            self.write_yaml(backlog_path, backlog)
            self.commit(root, "test-only A03 activation after exact paused return")
            self.assertEqual("BLOCKED", t02["status"])
            t02.update(status="IN_PROGRESS", blocker=None, lease=lease, updated_at="2026-10-04T14:11:00Z")
            self.write_yaml(backlog_path, backlog)
            self.commit(root, "test-only retained-base T02 reopen after separate activation")
            if correction_attack == "adopted-correction-tamper":
                child["campaign"]["status"] = "ACTIVE"
                self.write_yaml(backlog_path, backlog)
                self.commit(root, "test-only transient reactivation of adopted A04 during consumer delivery")
                # Restore only the in-memory record: the attack stays committed
                # through both consumer source commits, then submission saves it.
                child["campaign"]["status"] = "COMPLETE"
            control_candidate = t01["review_control"]["attempts"][-1]["submission"]["candidate_commit"]
        else:
            self.assertEqual("IN_PROGRESS", t01["status"])
            self.assertEqual("cd61bae9681690f92b754e443cd61f2c62026288", t01["base_sha"])
            # Preserve the old uncorrected lane with exact historical T01 bytes.
            # Current A04 source must never be laundered into a synthetic old T01.
            for relative in ui_gate.REFERENCE_ACTIVATION_CONTROL_SOURCE:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(ui_gate.blob(REPO, "aa09664678ca3ca8fa7a428cb60f3565d2c0e9bd", relative))
            if inject_unapproved_site_asset:
                asset = root / "planning/review-site/assets/unreviewed-activation.css"
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_text("body { display: none; }\n", encoding="utf-8")
            control_candidate = self.commit(root, "synthetic reviewed 1.8 witness and v1.4 control candidate")
            control_disposition = self.approve_activation_fixture_task(root, backlog, t01, control_candidate)

            owner = "codex-w2-implementation"
            branch = "codex/w2-implementation"
            lease = {
                "claimed_by": owner,
                "claimed_at": "2026-10-03T22:02:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
            }
            t02.update(
                status="IN_PROGRESS",
                owner=owner,
                branch=branch,
                worktree=".",
                base_sha=control_disposition,
                started_at="2026-10-03T22:02:00Z",
                updated_at="2026-10-03T22:02:00Z",
                lease=lease,
            )
            amendment["campaign"]["lease"] = lease
            self.write_yaml(backlog_path, backlog)
            self.commit(root, "synthetic W2.A03.T02 claim after independent T01 review")

        approved_id = "RO-UI-ACADEMIC-MINIMAL-1.8"
        approved_package = "cd8995fdcea2fe44452eaa1fdd258b6f9fab5714cbd443a81a8e5b4251220b94"
        old_id = "RO-UI-ACADEMIC-MINIMAL-1.7"
        old_package = "dcf31147ee386d48e8ac95725d648ee2b08c74ef0dd42c139c5f78508a90f878"
        extension_path = root / "verification/extensions/desktop-ui.json"
        extension = json.loads(extension_path.read_text(encoding="utf-8"))
        extension.update(referenceId=approved_id, referencePackageSha256=approved_package)
        self.write_json(extension_path, extension)
        for relative in (
            "apps/desktop/scripts/assemble-reference.mjs",
            "apps/desktop/scripts/assemble-application.mjs",
        ):
            path = root / relative
            current = path.read_text(encoding="utf-8")
            self.assertEqual(1, current.count(old_id))
            self.assertEqual(1, current.count(old_package))
            path.write_text(
                current.replace(old_id, approved_id).replace(old_package, approved_package), encoding="utf-8"
            )
        activation_commit = self.commit(root, "synthetic committed 1.8 extension and assembler inputs")
        baseline_path = root / "verification/baselines/desktop-ui.json"
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline.update(
            referenceId=approved_id,
            referencePackageSha256=approved_package,
            referenceApprovalCommit="acdc67b616f5ecdec448f57a7efe46e4f359aa9f",
        )
        self.assertEqual(66, len(baseline["entries"]))
        self.write_json(baseline_path, baseline)
        consumer_candidate = self.commit(
            root, "synthetic 66-entry baseline after committed inputs; PNG hashes unproven"
        )
        if correction_attack == "adopted-correction-after-consumer":
            child["campaign"]["status"] = "ACTIVE"
            self.write_yaml(backlog_path, backlog)
            self.commit(root, "test-only transient adopted A04 change after consumer candidate")
            child["campaign"]["status"] = "COMPLETE"
        self.approve_activation_fixture_task(root, backlog, t02, consumer_candidate)

        adoption = self.complete_activation_fixture_amendment(
            root, backlog, amendment, {t01["id"]: control_candidate, t02["id"]: consumer_candidate}
        )
        return root, adoption, backlog, control_candidate, consumer_candidate, activation_commit

    def write_activation_security_review(
        self,
        root: Path,
        amendment: dict[str, Any],
        manifest_commit: str,
        *,
        remediation: bool = False,
        attack: str | None = None,
    ) -> str:
        """Separate disposable review of the already committed checkpoint manifest."""
        identity = str(amendment["id"])
        path = f"artifacts/evidence/{identity}.adoption.json"
        payload = ui_gate.blob(root, manifest_commit, path)
        manifest = json.loads(payload)
        latest = amendment["completion"]["exit_review_control"]["attempts"][-1]
        for number in range(1, 3 if remediation else 2):
            adverse = remediation and number == 1
            record: dict[str, Any] = {
                "schemaVersion": "1.0",
                "documentType": "wave-amendment-adoption-security-independent-review",
                "amendmentId": identity,
                "targetWave": "W2",
                "reviewer": "agent:/root/synthetic-independent-security-review",
                "result": "changes-requested" if adverse else "approved",
                "reviewedManifest": {
                    "path": path,
                    "introductionCommit": manifest_commit,
                    "gitBlob": self.git(root, "rev-parse", f"{manifest_commit}:{path}"),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                },
                "approvedExit": {
                    "attemptId": latest["submission"]["id"],
                    "reviewedCompletionCommit": manifest["reviewedCompletionCommit"],
                },
                "findings": [self.activation_fixture_finding("SYN-SEC-F01")] if adverse else [],
                "closures": [
                    {"finding_id": "SYN-SEC-F01", "disposition": "fixed", "evidence": "synthetic checkpoint replay"}
                ]
                if number == 2
                else [],
                "transitionTruth": "Disposable pre-adoption security disposition only, not actual approval.",
            }
            if attack == "self-security-review":
                record["reviewer"] = amendment["campaign"]["owner"]
            if attack == "forged-security-review":
                record["reviewedManifest"]["sha256"] = "0" * 64
            self.write_json(root / f"artifacts/evidence/{identity}.adoption.review-{number:02d}.json", record)
            reviewed = self.commit(root, "synthetic independent pre-adoption security checkpoint review")
        return reviewed

    def complete_activation_fixture_amendment(
        self,
        root: Path,
        backlog: dict[str, Any],
        amendment: dict[str, Any],
        candidates: dict[str, str],
        *,
        remediation: bool = False,
        security_attack: str | None = None,
        preserve_slice_review: bool = False,
        security_required: bool = False,
    ) -> str:
        """Disposable integrated slice/exit/checkpoint/adoption, never actual approval."""
        identity = str(amendment["id"])
        change_request = str(amendment["change_request_id"])
        backlog_path = root / "planning/backlog.yaml"
        owner = "codex-w2-implementation"
        branch = "codex/w2-implementation"
        contribution_commit = self.git(root, "rev-parse", "HEAD")
        for number in () if preserve_slice_review else range(1, 3 if remediation else 2):
            adverse = remediation and number == 1
            self.write_json(
                root / f"artifacts/evidence/{identity}.S01.review-{number:02d}.json",
                {
                    "schemaVersion": "1.0",
                    "documentType": "amendment-contribution-independent-review",
                    "sliceId": f"{identity}.S01",
                    "amendmentId": identity,
                    "capabilityId": "CAP-05",
                    "reviewer": "agent:/root/synthetic-independent-slice-review",
                    "result": "changes-requested" if adverse else "approved",
                    "taskBindings": [
                        {"taskId": task["id"], "candidateCommit": candidates[task["id"]]} for task in amendment["tasks"]
                    ],
                    "findings": [self.activation_fixture_finding("SYN-S01-F01")] if adverse else [],
                    "openFindingIds": ["SYN-S01-F01"] if adverse else [],
                    **(
                        {
                            "closures": [
                                {
                                    "finding_id": "SYN-S01-F01",
                                    "disposition": "fixed",
                                    "evidence": "synthetic slice replay",
                                }
                            ]
                        }
                        if number == 2
                        else {}
                    ),
                    "notes": "Disposable authority fixture; prior 1.7 image hashes are not 1.8 capture proof.",
                },
            )
            contribution_commit = self.commit(root, "synthetic W2.A03.S01 independent contribution")
        packet = json.loads(
            (root / f"planning/enabler-change-requests/{change_request}.packet.json").read_text(encoding="utf-8")
        )
        wave = next(item for item in backlog["waves"] if item["id"] == "W2")
        exit_attempts: list[dict[str, Any]] = []
        for number in range(1, 3 if remediation else 2):
            adverse = remediation and number == 1
            exit_path = f"artifacts/evidence/{identity}.exit{'-R02' if number == 2 else ''}.json"
            self.write_json(
                root / exit_path,
                {
                    "schemaVersion": "1.0",
                    "documentType": "wave-amendment-exit-evidence",
                    "amendmentId": identity,
                    "changeRequestId": change_request,
                    "targetWave": "W2",
                    "branch": branch,
                    "candidateCommit": contribution_commit,
                    "outcome": "ready-for-independent-amendment-exit-review",
                    "waveCampaign": {
                        "status": wave["campaign"]["status"],
                        "scope": wave["campaign"]["scope"],
                        "pauseReason": wave["campaign"]["pause_reason"],
                    },
                    "amendmentCampaign": {"status": "ACTIVE", "scope": "wave-amendment", "pauseReason": None},
                    "requiredNextTransition": "independent amendment exit review",
                    "acceptanceClosure": [
                        {
                            "criterionIndex": index,
                            "criterion": criterion,
                            "status": "ready-for-independent-exit-disposition",
                        }
                        for index, criterion in enumerate(packet["acceptanceCriteria"], start=1)
                    ],
                    "checks": [{"command": "synthetic Git authority fixture", "result": "passed"}],
                },
            )
            exit_evidence_commit = self.commit(root, "synthetic W2.A03 exit evidence")
            exit_submission = taskctl.build_amendment_exit_submission(
                Namespace(file=str(backlog_path), amendment=identity, agent=owner),
                backlog,
                amendment,
                str(root / exit_path),
            )
            amendment["lifecycle"]["status"] = "REVIEW"
            amendment["lifecycle"]["history"].append(
                {
                    "id": f"E{len(amendment['lifecycle']['history']) + 1:02d}",
                    "status": "REVIEW",
                    "actor": owner,
                    "at": "2026-10-03T22:04:00Z",
                    "rationale": "Synthetic exit submission.",
                }
            )
            amendment["campaign"].update(status="REVIEW", lease=None)
            amendment["completion"].update(
                status="REVIEW",
                evidence=[exit_path],
                exit_review_control={"version": 1, "attempts": exit_attempts, "current_submission": exit_submission},
            )
            self.write_yaml(backlog_path, backlog)
            reviewed_state = self.commit(root, "synthetic W2.A03 exit submission")
            exit_reviewer = "agent:/root/synthetic-independent-exit-review"
            exit_ledger_path = f"artifacts/evidence/{identity}.exit-review-R{number:02d}.json"
            exit_ledger = {
                "amendment_id": identity,
                "attempt_id": f"R{number:02d}",
                "reviewed_state_commit": reviewed_state,
                "candidate_commit": exit_evidence_commit,
                "reviewer": exit_reviewer,
                "result": "changes-requested" if adverse else "approved",
                "notes": "Test-only independent exit disposition; no real capture qualification.",
                "evidence": {"path": exit_path, "sha256": exit_submission["evidence_reference"]["sha256"]},
                "findings": [self.activation_fixture_finding("SYN-EXIT-F01")] if adverse else [],
                "closures": [
                    {"finding_id": "SYN-EXIT-F01", "disposition": "fixed", "evidence": "synthetic exit replay"}
                ]
                if number == 2
                else [],
            }
            self.write_json(root / exit_ledger_path, exit_ledger)
            exit_attempt = taskctl.prepare_amendment_exit_attempt(
                amendment,
                exit_submission,
                exit_ledger_path,
                (root / exit_ledger_path).read_bytes(),
                exit_ledger,
                reviewer=exit_reviewer,
                result="changes-requested" if adverse else "approved",
            )
            amendment["campaign"].update(
                status="ACTIVE" if adverse else "COMPLETE",
                lease={"claimed_by": owner, "claimed_at": "2026-10-03T22:00:00Z", "expires_at": "2099-01-01T00:00:00Z"}
                if adverse
                else None,
            )
            amendment["completion"].update(
                status="CHANGES_REQUESTED" if adverse else "APPROVED",
                reviewer=exit_reviewer,
                reviewed_at=exit_attempt["review"]["reviewed_at"],
                notes="Synthetic fixture only.",
                exit_review_control={
                    "version": 1,
                    "attempts": [*exit_attempts, exit_attempt],
                    "current_submission": None,
                },
            )
            self.write_yaml(backlog_path, backlog)
            approved_completion = self.commit(root, "synthetic W2.A03 independent exit review")
            exit_attempts.append(exit_attempt)
            if adverse:
                amendment["lifecycle"]["status"] = "ACTIVE"
                self.write_yaml(backlog_path, backlog)
                self.commit(root, "synthetic supported amendment exit remediation activation")
        adoption_path = f"artifacts/evidence/{identity}.adoption.json"
        self.write_json(
            root / adoption_path,
            {
                "schemaVersion": "1.0",
                "documentType": "wave-amendment-adoption-evidence",
                "amendmentId": identity,
                "targetWave": "W2",
                "branch": branch,
                "candidateCommit": approved_completion,
                "reviewedCompletionCommit": approved_completion,
                "approvedExitAttempt": exit_attempts[-1]["submission"]["id"],
                "notes": "Synthetic authority fixture, not a real amendment adoption.",
            },
        )
        if amendment.get("correction"):
            record = json.loads((root / adoption_path).read_bytes())
            record["correctionReturn"] = amendment["correction"]
            self.write_json(root / adoption_path, record)
        adoption_sha = hashlib.sha256((root / adoption_path).read_bytes()).hexdigest()
        adoption_evidence_commit = self.commit(root, "synthetic W2.A03 security checkpoint evidence")
        if (identity in {"W2.A04", "W2.A05"} or security_required) and security_attack not in {
            "missing-security-review",
            "late-security-review",
        }:
            adoption_evidence_commit = self.write_activation_security_review(
                root, amendment, adoption_evidence_commit, remediation=remediation, attack=security_attack
            )
        wave.setdefault("checkpoints", []).append(
            {
                "id": f"W2.CP{len(wave.get('checkpoints', [])) + 1:02d}",
                "kind": "security",
                "recorded_by": owner,
                "recorded_at": "2026-10-03T22:05:00Z",
                "evidence": [
                    {
                        "type": "amendment-adoption-evidence",
                        "amendment_id": identity,
                        "path": adoption_path,
                        "sha256": adoption_sha,
                        "commit": adoption_evidence_commit,
                    }
                ],
                "notes": "Synthetic A03 control/security checkpoint; capture qualification unproven.",
            }
        )
        amendment["lifecycle"]["status"] = "ADOPTED"
        amendment["lifecycle"]["history"].append(
            {
                "id": f"E{len(amendment['lifecycle']['history']) + 1:02d}",
                "status": "ADOPTED",
                "actor": owner,
                "at": "2026-10-03T22:06:00Z",
                "rationale": "Synthetic fixture only.",
            }
        )
        backlog["control_plane"]["active_amendment"] = None
        wave["campaign"]["scope"] = "amendment-hold" if amendment.get("correction") else "wave"
        self.write_yaml(backlog_path, backlog)
        adoption = self.commit(root, "synthetic W2.A03 adoption with ordinary W2 still paused")
        if (identity in {"W2.A04", "W2.A05"} or security_required) and security_attack == "late-security-review":
            adoption = self.write_activation_security_review(root, amendment, adoption_evidence_commit)
        return adoption

    def reactivate_adopted_continuation(
        self, root: Path, adoption: str, backlog: dict[str, Any], *, activation: bool = False
    ) -> str:
        """Create a test-only ordinary Wave resume and original-base T01 claim."""
        wave = next(item for item in backlog["waves"] if item["id"] == "W2")
        original = next(
            task
            for capability in backlog["capabilities"]
            for slice_ in capability["slices"]
            for task in slice_["tasks"]
            if task["id"] == "CAP-05.S01.T01"
        )
        prior_campaign = copy.deepcopy(wave["campaign"])
        owner = "codex-w2-implementation"
        claimed = "2026-10-04T01:00:00Z" if activation else "2026-10-03T12:06:00Z"
        reopened_at = "2026-10-04T01:01:00Z" if activation else "2026-10-03T12:07:00Z"
        lease = {"claimed_by": owner, "claimed_at": claimed, "expires_at": "2099-01-01T00:00:00Z"}
        wave["campaign"].update(
            status="ACTIVE",
            scope="wave",
            owner=owner,
            branch="codex/w2-implementation",
            worktree=".",
            base_sha=adoption,
            updated_at=claimed,
            pause_reason=None,
            pause_category=None,
            lease=lease,
        )
        records = wave["campaign"].setdefault("resume_records", [])
        records.append(
            {
                "id": f"W2.R{len(records) + 1:02d}",
                "wave_id": "W2",
                "control_revision": backlog["control_plane"]["revision"],
                "prior_status": "PAUSED",
                "pre_resume_commit": adoption,
                "prior_campaign_sha256": taskctl.canonical_json_sha256(prior_campaign),
                "branch": "codex/w2-implementation",
                "worktree": ".",
                "profile": "LOC",
                "platform": "windows-x64",
                "actor": owner,
                "resumed_at": claimed,
            }
        )
        self.write_yaml(root / "planning/backlog.yaml", backlog)
        self.commit(root, "synthetic explicit W2 resume with T01 still blocked")
        self.assertEqual("6506c68461144747b0ee9be10853211717aa381d", original["base_sha"])
        original.update(
            status="IN_PROGRESS",
            blocker=None,
            owner=owner,
            branch="codex/w2-implementation",
            worktree=".",
            updated_at=reopened_at,
            lease=lease,
        )
        self.write_yaml(root / "planning/backlog.yaml", backlog)
        return self.commit(root, "synthetic original-base T01 reactivation after Wave resume")

    def classified_adopted_continuation_fixture(
        self,
        temporary: str,
        *,
        inject_unapproved_control_source: bool = False,
        activation: bool = False,
        correction: bool = False,
        repair: bool = False,
    ) -> tuple[Path, str, str, dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Build a test-only current classification atop authenticated historical Git."""
        if activation:
            self.assertFalse(inject_unapproved_control_source)
            if repair:
                root, _head = self.activation_repair_future_fixture(temporary)
                backlog = yaml.safe_load((root / "planning/backlog.yaml").read_bytes())
                parent = next(a for a in backlog["wave_amendments"] if a["id"] == "W2.A03")
                candidates = {
                    t["id"]: t["review_control"]["attempts"][-1]["submission"]["candidate_commit"]
                    for t in parent["tasks"]
                }
                previous = json.loads((root / "artifacts/evidence/W2.A03.S01.review-01.json").read_bytes())
                self.write_json(
                    root / "artifacts/evidence/W2.A03.S01.review-02.json",
                    {
                        "schemaVersion": "1.0",
                        "documentType": "amendment-contribution-independent-review",
                        "amendmentId": "W2.A03",
                        "sliceId": "W2.A03.S01",
                        "capabilityId": "CAP-05",
                        "reviewer": "agent:/root/synthetic-independent-parent-replay",
                        "result": "approved",
                        "taskBindings": previous["taskBindings"],
                        "findings": [],
                        "openFindingIds": [],
                        "closures": [
                            {
                                "finding_id": "W2.A03.S01-R01-F01",
                                "disposition": "fixed",
                                "evidence": "Synthetic exact-history replay; no actual closure approval.",
                            }
                        ],
                        "notes": "Synthetic future parent replay only; retained adverse round is unchanged.",
                    },
                )
                self.commit(root, "synthetic parent S01 review-02 preserving actual adverse review-01")
                adoption = self.complete_activation_fixture_amendment(
                    root, backlog, parent, candidates, preserve_slice_review=True, security_required=True
                )
                consumer_candidate = candidates["W2.A03.T02"]
                activation_commits = [
                    c
                    for c in self.git(
                        root, "rev-list", "--reverse", f"{parent['tasks'][1]['base_sha']}..{consumer_candidate}"
                    ).splitlines()
                    if ui_gate.commit_paths(root, c) & ui_gate.REFERENCE_ACTIVATION_CONSUMER_SOURCE
                ]
            else:
                root, adoption, backlog, _control_candidate, consumer_candidate, activation_commit = (
                    self.reference_activation_git_fixture(temporary, correction=correction)
                )
                activation_commits = [activation_commit, consumer_candidate]
            prior_adoption = "04d6ae3fb29a133e6e31c8191ba1d6b80fa0b0cf"
            prior_reactivation = "f18a037b96d43392599f7779a668fb1928f74475"
        else:
            root, adoption, _branch, backlog, _amendment = self.adopted_continuation_git_fixture(
                temporary, inject_unapproved_control_source=inject_unapproved_control_source
            )
            prior_adoption = adoption
        reactivation = self.reactivate_adopted_continuation(root, adoption, backlog, activation=activation)
        if not activation:
            prior_reactivation = reactivation
        base = "6506c68461144747b0ee9be10853211717aa381d"
        policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
        inherited_candidate = "988ee4789f2004cce83187f971760d5b5f3e02ca"
        inherited_contract = json.loads(
            (root / "artifacts/evidence/ui-change/W2.A01.T02.json").read_text(encoding="utf-8")
        )
        inherited_commits = [
            commit
            for commit in self.git(root, "rev-list", "--reverse", f"{base}..{inherited_candidate}").splitlines()
            if any(ui_gate.is_implementation_path(path, policy) for path in ui_gate.commit_paths(root, commit))
        ]
        resumed_commit = "9727f1b195e7dee300e7f3df3c289e7739fb0fdc"
        resumed_files = sorted(
            path for path in ui_gate.commit_paths(root, resumed_commit) if ui_gate.is_implementation_path(path, policy)
        )
        changed_files = sorted(
            path
            for path in ui_gate.changed_paths(root, base, reactivation)
            if ui_gate.is_implementation_path(path, policy)
        )
        classification_path = "artifacts/evidence/CAP-05.S01.T01.ui-classification-R01.json"
        contract: dict[str, Any] = self.contract(
            "defect-restoration",
            inherited_contract["reference"]["packageSha256"],
            inherited_contract["reference"]["approvalCommit"],
            approved_by=inherited_contract["reference"]["approvedBy"],
            previous="RO-UI-ACADEMIC-MINIMAL-1.7",
            reference_id="RO-UI-ACADEMIC-MINIMAL-1.8",
            version="1.8",
            implementation_agent="agent:codex-w2-implementation",
            task_id="CAP-05.S01.T01",
        )
        contract.update(
            schemaVersion="1.4" if activation else "1.3",
            changedFiles=changed_files,
            adoptedContinuationAuthority={
                "amendmentId": "W2.A02",
                "changeRequestId": "ECR-0010",
                "controlTaskId": "W2.A02.T01",
                "inheritedAmendmentId": "W2.A01",
                "inheritedTaskId": "W2.A01.T02",
                "inheritedContractPath": "artifacts/evidence/ui-change/W2.A01.T02.json",
                "adoptionCommit": prior_adoption,
                "reactivationCommit": prior_reactivation,
                "inheritedUiFiles": inherited_contract["changedFiles"],
                "inheritedUiCommits": inherited_commits,
                "resumedUiFiles": resumed_files,
                "resumedUiCommits": [resumed_commit],
                "classification": {"path": classification_path, "sha256": "0" * 64, "commit": "0" * 40},
            },
        )
        if activation:
            contract["referenceActivationAuthority"] = {
                "amendmentId": "W2.A03",
                "changeRequestId": "ECR-0011",
                "controlTaskId": "W2.A03.T01",
                "consumerTaskId": "W2.A03.T02",
                "referenceApprovalPath": "planning/reference-approvals/RO-UI-ACADEMIC-MINIMAL-1.8.json",
                "witnessPath": "packages/contracts/workflow-profile/presentation-compatibility-1.8.json",
                "publicationCommit": "acdc67b616f5ecdec448f57a7efe46e4f359aa9f",
                "witnessCommit": "9824e2baad59705bd985a33624fc3e27837e7bc1",
                "adoptionCommit": adoption,
                "reactivationCommit": reactivation,
                "activationUiFiles": sorted(ui_gate.REFERENCE_ACTIVATION_CONSUMER_FILES),
                "activationUiCommits": activation_commits,
            }
        # Construct expected input closure from committed task state and paths,
        # before invoking the gate under test. Only product edits made while
        # the original T01 claim and W2 campaign are active belong to T01.
        product_roots = ("apps/", "services/", "workers/", "tests/", "modules/", "packages/", "verification/")
        product_tools = {"tools/architecture_check.py", "tools/core_sidecar_build.py", "Cargo.lock"}
        product_paths: set[str] = set()
        state_cache: dict[str, dict[str, Any]] = {}
        for row in self.git(root, "rev-list", "--reverse", "--parents", f"{base}..{reactivation}").splitlines():
            commit, parent = row.split()
            changed = ui_gate.commit_paths(root, commit)
            if changed & {
                "tools/ui_change_gate.py",
                "tools/taskctl.py",
                "tools/planctl.py",
                "design/ui-change.schema.json",
                "docs/adr/index.json",
            }:
                continue  # Separately reviewed control source is not T01 product groundwork.
            paths = {path for path in changed if path.startswith(product_roots) or path in product_tools}
            if not paths:
                continue
            active_on_both_sides = True
            for state_commit in (parent, commit):
                state_blob = self.git(root, "rev-parse", f"{state_commit}:planning/backlog.yaml")
                if state_blob not in state_cache:
                    state_cache[state_blob] = yaml.load(
                        ui_gate.blob(root, state_commit, "planning/backlog.yaml").decode("utf-8"),
                        Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader),
                    )
                state = state_cache[state_blob]
                original = next(
                    task
                    for capability in state["capabilities"]
                    for slice_ in capability["slices"]
                    for task in slice_["tasks"]
                    if task["id"] == "CAP-05.S01.T01"
                )
                wave = next(item for item in state["waves"] if item["id"] == "W2")
                if (
                    original["status"] not in {"IN_PROGRESS", "REVIEW"}
                    or original["base_sha"] != base
                    or wave["campaign"]["status"] != "ACTIVE"
                    or wave["campaign"]["scope"] != "wave"
                ):
                    active_on_both_sides = False
                    break
            if active_on_both_sides:
                product_paths.update(paths)
        frozen = yaml.load(
            ui_gate.blob(root, "c85a59f3a293f8e3f2eaf6454682c9a14b1efa55", "planning/backlog.yaml").decode("utf-8"),
            Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader),
        )
        frozen_task = next(
            task
            for capability in frozen["capabilities"]
            for slice_ in capability["slices"]
            for task in slice_["tasks"]
            if task["id"] == "CAP-05.S01.T01"
        )
        scope: dict[str, Any] = {
            "taskDefinitionSha256": taskctl.canonical_json_sha256(taskctl.corrective_contract(frozen, frozen_task)),
            "inheritedUiFiles": inherited_contract["changedFiles"],
            "inheritedUiCommits": inherited_commits,
            "resumedUiFiles": resumed_files,
            "resumedUiCommits": [resumed_commit],
            "reactivationCommit": reactivation,
            "t01ProductPaths": sorted(product_paths),
        }
        producer_blobs = {path: self.git(root, "rev-parse", f"{reactivation}:{path}") for path in resumed_files}
        producer = {
            "producerCommit": reactivation,
            "referencePackageSha256": contract["reference"]["packageSha256"],
            "inputGitBlobs": producer_blobs,
        }
        capture_path = "artifacts/evidence/CAP-05.S01.T01.captures-01/manifest.json"
        manifest = {
            "schemaVersion": "1.0",
            "documentType": "product-style-capture-bundle",
            "producer": producer,
            "report": {"fixtureOnly": True},
        }
        self.write_json(root / capture_path, manifest)
        capture_commit = self.commit(root, "synthetic current product/reference capture delivery")
        capture_sha = hashlib.sha256((root / capture_path).read_bytes()).hexdigest()
        visual_path = "artifacts/evidence/CAP-05.S01.T01.visual-review-01.json"
        self.write_json(
            root / visual_path,
            {
                "documentType": "independent-product-visual-disposition",
                "taskId": "CAP-05.S01.T01",
                "reviewer": "agent:/root/synthetic-independent-visual-review",
                "disposition": "approved",
                "findings": [],
                "bindings": {
                    "producerCommit": reactivation,
                    "manifest": capture_path,
                    "manifestSha256": capture_sha,
                    "captureDeliveryCommit": capture_commit,
                    "referencePackageSha256": contract["reference"]["packageSha256"],
                },
            },
        )
        visual_commit = self.commit(root, "synthetic independent visual disposition")
        dependent = sorted(set(scope["t01ProductPaths"]) - set(producer_blobs))
        self.write_json(
            root / classification_path,
            {
                "schemaVersion": "1.0",
                "documentType": "independent-ui-restoration-disposition",
                "taskId": "CAP-05.S01.T01",
                "baseCommit": base,
                "candidateCommit": reactivation,
                "reviewer": "agent:/root/synthetic-independent-classification",
                "disposition": "approved",
                "taskDefinitionSha256": scope["taskDefinitionSha256"],
                "referencePackageSha256": contract["reference"]["packageSha256"],
                "resumedUiFiles": scope["resumedUiFiles"],
                "resumedUiCommits": scope["resumedUiCommits"],
                "approvedTaskAllowsRestoration": True,
                "authorityPreserved": True,
                "formalTaskApproval": False,
                "normativeRationale": "Synthetic independent classification of fixture history only.",
                "dependentInputFiles": dependent,
                "dependentInputGitBlobs": {
                    path: self.git(root, "rev-parse", f"{reactivation}:{path}") for path in dependent
                },
                "captures": {"path": capture_path, "sha256": capture_sha, "deliveryCommit": capture_commit},
                "visualReview": {
                    "path": visual_path,
                    "sha256": hashlib.sha256((root / visual_path).read_bytes()).hexdigest(),
                    "commit": visual_commit,
                },
            },
        )
        classification_commit = self.commit(root, "synthetic independent current T01 classification")
        contract["adoptedContinuationAuthority"]["classification"] = {
            "path": classification_path,
            "sha256": hashlib.sha256((root / classification_path).read_bytes()).hexdigest(),
            "commit": classification_commit,
        }
        self.write_json(root / "artifacts/evidence/ui-change/CAP-05.S01.T01.json", contract)
        head = self.commit(
            root, "synthetic T01 v1.4 evidence contract" if activation else "synthetic T01 v1.3 evidence contract"
        )
        return root, base, head, contract, manifest, scope

    def linked_fixture(
        self,
        temporary: str,
        review_gate: str = "human-and-agent-review",
        changed_paths: list[str] | None = None,
        *,
        adr_registry: bool = False,
    ) -> tuple[Path, str, dict[str, Any], dict[str, Any]]:
        root, approval, package = self.prepare(temporary, adr_registry=adr_registry)
        origin = {
            "id": "CAP-01.S01.T01",
            "wave": "W1",
            "title": "Approved route",
            "objective": "Preserve the approved route",
            "dependencies": [],
            "acceptance_criteria": ["Approved route works"],
            "verification_commands": ["test View"],
            "deployment_profiles": ["LOC"],
            "platform_targets": ["windows-x64"],
            "status": "DONE",
            "owner": "prior-owner",
            "review_gate": review_gate,
            "review": {"reviewer": "prior-reviewer", "result": "approved"},
            "evidence": [{"path": "artifacts/evidence/origin.json"}],
        }
        data: dict[str, Any] = {
            "capabilities": [{"id": "CAP-01", "slices": [{"id": "CAP-01.S01", "tasks": [origin]}]}],
            "waves": [
                {
                    "id": "W1",
                    "approval": {"status": "APPROVED", "commit": approval},
                    "campaign": {"status": "PAUSED", "scope": "wave", "lease": None},
                    "completion": {"status": "IN_PROGRESS"},
                }
            ],
            "release_gates": [{"id": "G1", "after_wave": "W1", "status": "PENDING"}],
        }
        self.write_yaml(root / "planning/backlog.yaml", data)
        origin_commit = self.commit(root, "completed independently reviewed origin")
        spec = {
            "schemaVersion": "1.0",
            "kind": "authority-preserving-correction",
            "origin": {
                "taskId": origin["id"],
                "commit": origin_commit,
                "sha256": taskctl.canonical_json_sha256(origin),
            },
            "reproduction": "Approved route drifts",
            "changedPaths": changed_paths if changed_paths is not None else ["apps/desktop/src/View.tsx"],
            "impactAnalysis": "Restore the unchanged approved route and retain all review obligations",
        }
        spec_path = "artifacts/evidence/W1.C01.T01.spec.json"
        self.write_json(root / spec_path, spec)
        base = self.commit(root, "publish bounded correction spec")
        reference = {
            "path": spec_path,
            "commit": base,
            "sha256": taskctl.evidence_sha256((root / spec_path).read_bytes()),
        }
        indexed = taskctl.index_backlog(data)
        task = taskctl.build_corrective_task(
            data,
            indexed[3],
            origin,
            spec,
            reference,
            Namespace(
                agent="codex", branch="main", base_sha=base, profile="LOC", platform="windows-x64", lease_hours=8
            ),
        )
        data["waves"][0]["campaign"]["corrective_tasks"] = [task]
        contract = self.contract("defect-restoration", package, approval, task_id=task["id"])
        self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
        self.commit(root, "claim linked correction without experience metadata")
        return root, base, data, contract

    def linked_candidate(self, root: Path, data: dict[str, Any], contract: dict[str, Any]) -> str:
        self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
        self.write_json(root / str(contract["contractPath"]), contract)
        (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'restored';\n", encoding="utf-8")
        return self.commit(root, "restore approved route with focused evidence")

    def test_linked_correction_authenticates_without_mutating_origin_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary)
            original = copy.deepcopy(data["capabilities"])
            head = self.linked_candidate(root, data, contract)
            result = validate(root, base, head)
            self.assertTrue(result["ok"], result["errors"])
            self.assertEqual(original, data["capabilities"])
            self.assertNotIn("experience_change", data["waves"][0]["campaign"]["corrective_tasks"][0])
            self.assertNotIn("review_gate", data["waves"][0]["campaign"]["corrective_tasks"][0])

    def test_linked_automatic_base_precedes_missing_contract_and_evidence_only_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary)
            self.assertEqual(base, automatic_base(root, "HEAD"))
            (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'restored';\n", encoding="utf-8")
            self.commit(root, "UI implementation before missing evidence")
            self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": "evidence only"})
            self.commit(root, "later evidence-only commit")
            self.assertEqual(base, automatic_base(root, "HEAD"))
            self.assertFalse(validate(root, automatic_base(root, "HEAD"))["ok"])
            self.linked_candidate(root, data, contract)
            self.assertTrue(validate(root, automatic_base(root, "HEAD"))["ok"])

    def test_linked_interruption_note_is_nonauthorizing_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary)
            self.linked_candidate(root, data, contract)
            task = data["waves"][0]["campaign"]["corrective_tasks"][0]
            note = root / "artifacts/evidence/W1.resume-20990101-01.md"
            note.write_text("# Interrupted synthetic check\nNo approval or scope authority.\n", encoding="utf-8")
            head = self.commit(root, "retain an immutable interruption checkpoint")
            result = validate(root, base, head)
            self.assertTrue(result["ok"], result["errors"])
            manifest = {
                "taskId": task["id"],
                "branch": task["branch"],
                "commit": head,
                "baseCommit": base,
                "changedFiles": sorted(ui_gate.changed_paths(root, base, head)),
                "checks": [{"command": "synthetic scope boundary", "exitCode": 0}],
                "acceptanceCriteria": [{"criterion_index": 1, "evidence": ["synthetic fixture only"]}],
                "unverifiedItems": [],
                "correctiveIntegration": {
                    "originSha256": task["correction"]["origin_sha256"],
                    "authorityPreserved": True,
                    "affectedChecks": ["synthetic scope boundary"],
                    "reusedEvidence": [],
                    "rationale": "Same-wave checkpoint does not authorize implementation or approval.",
                },
            }
            self.assertEqual([], taskctl.validate_task_evidence(task, manifest, repo=root))
            self.assertTrue(taskctl.validate_task_evidence(task, manifest))  # Git provenance is mandatory.

    def test_linked_interruption_note_cannot_hide_invalid_paths_or_history(self) -> None:
        for mutation in (
            "wrong-wave",
            "rewrite",
            "remove",
            "executable",
            "symlink",
            "mixed-product",
            "hidden-product",
            "authority",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, base, data, contract = self.linked_fixture(temporary)
                self.linked_candidate(root, data, contract)
                task = data["waves"][0]["campaign"]["corrective_tasks"][0]
                relative = "artifacts/evidence/W1.resume-20990101-01.md"
                if mutation == "wrong-wave":
                    relative = relative.replace("W1", "W2")
                note = root / relative
                note.write_text("# Synthetic interruption\nNo authority.\n", encoding="utf-8")
                if mutation in {"executable", "symlink"}:
                    mode = "100755" if mutation == "executable" else "120000"
                    self.git(root, "add", "--", relative)
                    blob_id = self.git(root, "rev-parse", f":{relative}")
                    self.git(root, "update-index", "--cacheinfo", f"{mode},{blob_id},{relative}")
                    self.git(root, "commit", "-m", "nonregular checkpoint addition")
                else:
                    self.commit(root, "add interruption note")
                if mutation == "rewrite":
                    note.write_text("Rewritten historical checkpoint\n", encoding="utf-8")
                elif mutation == "remove":
                    note.unlink()
                elif mutation in {"mixed-product", "hidden-product"}:
                    target = root / "apps/desktop/src/Extra.tsx"
                    target.write_text("unadmitted product change\n", encoding="utf-8")
                    if mutation == "hidden-product":
                        self.commit(root, "hidden product touch")
                        target.unlink()
                elif mutation == "authority":
                    (root / "design/ui-reference/assets/tokens.css").write_text("unapproved tokens\n", encoding="utf-8")
                if mutation not in {"wrong-wave", "executable", "symlink"}:
                    self.commit(root, "retain inadmissible history")
                head = self.git(root, "rev-parse", "HEAD")
                scope_errors = ui_gate.corrective_scope_errors(root, task, head)
                self.assertTrue(scope_errors)
                if mutation in {"executable", "symlink"}:
                    self.assertTrue(any("regular non-executable" in error for error in scope_errors))
                self.assertFalse(validate(root, base, head)["ok"])

    def test_linked_interruption_note_cannot_rewrite_preexisting_note(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _base, data, _contract = self.linked_fixture(temporary)
            task = copy.deepcopy(data["waves"][0]["campaign"]["corrective_tasks"][0])
            note = root / "artifacts/evidence/W1.resume-20990101-01.md"
            note.write_text("Existing synthetic checkpoint\n", encoding="utf-8")
            task["base_sha"] = self.commit(root, "scope fixture base contains an older note")
            note.write_text("Rewritten checkpoint\n", encoding="utf-8")
            head = self.commit(root, "change older note after scope fixture base")
            errors = ui_gate.corrective_scope_errors(root, task, head)
            self.assertTrue(any("must add regular" in error for error in errors), errors)

    def test_linked_interruption_note_namespace_is_exact(self) -> None:
        task = {"wave": "W2"}
        self.assertTrue(ui_gate.corrective_interruption_note(task, "artifacts/evidence/W2.resume-20990101-01.md"))
        for path in (
            None,
            "artifacts/evidence/W1.resume-20990101-01.md",
            "artifacts/evidence/W2.resume-20990230-01.md",
            "artifacts/evidence/W2.resume-20990101.md",
            "artifacts/evidence/W2.resume-20990101-1.md",
            "artifacts/evidence/W2.resume-20990101-01.json",
            "artifacts/evidence/W2.resume-20990101-01.md.py",
            "artifacts/evidence/W2.resume-20990101-01.md/child.md",
            "artifacts/evidence/nested/W2.resume-20990101-01.md",
            "artifacts/evidence/../W2.resume-20990101-01.md",
            "artifacts/evidence/W2.approval.md",
        ):
            with self.subTest(path=path):
                self.assertFalse(ui_gate.corrective_interruption_note(task, path))
        self.assertFalse(
            ui_gate.corrective_interruption_note({"wave": "W."}, "artifacts/evidence/W2.resume-20990101-01.md")
        )

    def test_linked_rejects_authority_and_live_claim_substitutions(self) -> None:
        for mutation in (
            "origin",
            "history",
            "authority",
            "spec-hash",
            "spec-content",
            "scope",
            "expired",
            "lease-owner",
            "owner",
            "branch",
            "worktree",
            "base",
            "experience",
            "review-gate",
            "ordinary-masquerade",
            "duplicate",
            "historical",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, base, data, contract = self.linked_fixture(temporary)
                task = data["waves"][0]["campaign"]["corrective_tasks"][0]
                origin = data["capabilities"][0]["slices"][0]["tasks"][0]
                if mutation == "origin":
                    origin["objective"] = "Substituted purpose"
                elif mutation == "history":
                    task["correction"]["origin_history_sha256"] = "0" * 64
                elif mutation == "authority":
                    task["correction"]["authority_sha256"] = "0" * 64
                elif mutation == "spec-hash":
                    task["correction"]["spec"]["sha256"] = "0" * 64
                elif mutation == "spec-content":
                    task["correction"]["reproduction"] = "Substituted reproduction"
                elif mutation == "scope":
                    task["correction"]["changed_paths"] = ["apps/desktop/src/Other.tsx"]
                elif mutation == "expired":
                    task["lease"]["expires_at"] = "2000-01-01T00:00:00+00:00"
                elif mutation == "lease-owner":
                    task["lease"]["claimed_by"] = "other"
                elif mutation == "owner":
                    task["owner"] = "other"
                elif mutation == "branch":
                    task["branch"] = "codex/other"
                elif mutation == "worktree":
                    task["worktree"] = "other"
                elif mutation == "base":
                    task["base_sha"] = self.git(root, "rev-parse", "HEAD")
                elif mutation == "experience":
                    task["experience_change"] = {"kind": "defect-restoration"}
                elif mutation == "review-gate":
                    origin["review_gate"] = "agent-review"
                elif mutation == "ordinary-masquerade":
                    data["waves"][0]["campaign"]["corrective_tasks"] = []
                    data["capabilities"][0]["slices"][0]["tasks"].append(task)
                elif mutation == "duplicate":
                    data["waves"][0]["campaign"]["corrective_tasks"].append(copy.deepcopy(task))
                head = self.linked_candidate(root, data, contract)
                if mutation == "historical":
                    self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": "later"})
                    self.commit(root, "later live head")
                self.assertFalse(validate(root, base, head)["ok"])

    def test_linked_rejects_ambiguous_and_invalid_automatic_bases(self) -> None:
        for mutation in ("duplicate", "missing", "abbreviated", "nonancestor", "expired"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, _base, data, _contract = self.linked_fixture(temporary)
                task = data["waves"][0]["campaign"]["corrective_tasks"][0]
                if mutation == "duplicate":
                    data["waves"][0]["campaign"]["corrective_tasks"].append(copy.deepcopy(task))
                elif mutation == "expired":
                    task["lease"]["expires_at"] = "2000-01-01T00:00:00+00:00"
                else:
                    task["base_sha"] = {"missing": None, "abbreviated": "abc123", "nonancestor": "0" * 40}[mutation]
                self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
                self.commit(root, "invalid claim")
                with self.assertRaises(ValueError):
                    automatic_base(root, "HEAD")

    def test_linked_rejects_reverted_ui_reference_and_spec_touches(self) -> None:
        for path in (
            "apps/desktop/src/Extra.tsx",
            "design/ui-reference/assets/tokens.css",
            "artifacts/evidence/W1.C01.T01.spec.json",
        ):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                root, base, data, contract = self.linked_fixture(temporary)
                target = root / path
                original = target.read_bytes() if target.exists() else None
                target.write_text("unadmitted intermediate content\n", encoding="utf-8")
                self.commit(root, "unadmitted intermediate touch")
                if original is None:
                    target.unlink()
                else:
                    target.write_bytes(original)
                self.commit(root, "revert intermediate touch")
                head = self.linked_candidate(root, data, contract)
                self.assertFalse(validate(root, base, head)["ok"])

    def test_linked_schema_limits_correction_ids_to_v1_restoration(self) -> None:
        schema = json.loads((REPO / "design/ui-change.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        contract = self.contract("defect-restoration", "a" * 64, "b" * 40, task_id="W1.C03.T01")
        self.assertEqual([], list(validator.iter_errors(contract)))
        for mutation in ("kind", "version", "task-number", "id"):
            candidate = copy.deepcopy(contract)
            if mutation == "kind":
                candidate.update(
                    changeKind="approved-reference-implementation", implementationScope="not a restoration"
                )
            elif mutation == "version":
                candidate["schemaVersion"] = "1.1"
            else:
                candidate["taskId"] = "W1.C03.T02" if mutation == "task-number" else "W1.C3.T01"
                candidate["contractPath"] = f"artifacts/evidence/ui-change/{candidate['taskId']}.json"
            with self.subTest(mutation=mutation):
                self.assertTrue(list(validator.iter_errors(candidate)))

    def test_linked_explicit_short_base_cannot_hide_evidence_only_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary)
            candidate = self.linked_candidate(root, data, contract)
            self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": "later evidence"})
            head = self.commit(root, "evidence-only head")
            self.assertTrue(validate(root, base, head)["ok"])
            result = validate(root, candidate, head)
            self.assertFalse(result["ok"], result)
            self.assertTrue(any("full claim base" in error for error in result["errors"]), result)

    def test_linked_no_ui_range_still_authenticates_claim(self) -> None:
        for mutation in ("none", "expired", "duplicate", "reverted-ui", "reference"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, base, data, _contract = self.linked_fixture(temporary)
                task = data["waves"][0]["campaign"]["corrective_tasks"][0]
                if mutation == "expired":
                    task["lease"]["expires_at"] = "2000-01-01T00:00:00+00:00"
                elif mutation == "duplicate":
                    data["waves"][0]["campaign"]["corrective_tasks"].append(copy.deepcopy(task))
                elif mutation == "reverted-ui":
                    target = root / "apps/desktop/src/View.tsx"
                    original = target.read_bytes()
                    target.write_text("unreviewed intermediate UI\n", encoding="utf-8")
                    self.commit(root, "intermediate UI")
                    target.write_bytes(original)
                elif mutation == "reference":
                    (root / "design/ui-reference/assets/tokens.css").write_text("unapproved tokens\n", encoding="utf-8")
                self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
                self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": mutation})
                head = self.commit(root, "no net UI implementation")
                result = validate(root, base, head)
                self.assertEqual(mutation == "none", result["ok"], result)

    def test_linked_rejects_rebinding_base_after_admission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _base, data, contract = self.linked_fixture(temporary)
            rebased = self.git(root, "rev-parse", "HEAD")
            task = data["waves"][0]["campaign"]["corrective_tasks"][0]
            task["base_sha"] = rebased
            task["correction"]["spec"]["commit"] = rebased
            head = self.linked_candidate(root, data, contract)
            result = validate(root, rebased, head)
            self.assertFalse(result["ok"])
            self.assertTrue(any("precede its admission" in error for error in result["errors"]), result)

    def test_linked_rejects_authenticated_origin_without_required_review_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary, review_gate="agent-review")
            head = self.linked_candidate(root, data, contract)
            result = validate(root, base, head)
            self.assertFalse(result["ok"])
            self.assertTrue(any("inherited human-and-agent-review" in error for error in result["errors"]), result)

    def test_linked_conformance_authenticates_real_completed_wave_authority(self) -> None:
        # Read-only historical authority, not a live correction admission or a
        # claim that this repository's product currently passes conformance.
        live_head = self.git(REPO, "rev-parse", "HEAD")
        live_data = yaml.safe_load(ui_gate.blob(REPO, live_head, "planning/backlog.yaml").decode("utf-8"))
        wave = next(item for item in live_data["waves"] if item["id"] == "W2")
        packet = wave["approval"]["approved_commit"]
        later_references = self.git(
            REPO, "rev-list", "--reverse", f"{packet}..{live_head}", "--", "design/ui-reference"
        ).splitlines()
        head = self.git(REPO, "rev-parse", f"{later_references[0]}^") if later_references else live_head
        data = yaml.safe_load(ui_gate.blob(REPO, head, "planning/backlog.yaml").decode("utf-8"))
        origin = taskctl.index_backlog(copy.deepcopy(data))[3]["CAP-04.S02.T03"]
        task: dict[str, Any] = {
            "id": "W2.C02.T01",
            "wave": "W2",
            "correction": {
                "origin_commit": head,
                "origin_sha256": taskctl.canonical_json_sha256(taskctl.corrective_origin_snapshot(origin)),
                "origin_amendment_id": None,
            },
        }
        self.assertEqual([], ui_gate.linked_conformance_origin_errors(REPO, head, data, task, origin))
        if later_references:
            live_origin = taskctl.index_backlog(copy.deepcopy(live_data))[3]["CAP-04.S02.T03"]
            live_task = copy.deepcopy(task)
            live_task["correction"]["origin_commit"] = live_head
            live_task["correction"]["origin_sha256"] = taskctl.canonical_json_sha256(
                taskctl.corrective_origin_snapshot(live_origin)
            )
            self.assertIn(
                "conformance origin cannot borrow a later changed reference",
                ui_gate.linked_conformance_origin_errors(REPO, live_head, live_data, live_task, live_origin),
            )
        for mutation in (
            "approver",
            "human-approver",
            "packet",
            "scope",
            "verifier",
            "review",
            "amendment",
            "experience",
            "early-claim",
        ):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(data)
                altered = copy.deepcopy(origin)
                wave = next(item for item in changed["waves"] if item["id"] == "W2")
                if mutation == "approver":
                    wave["approval"]["approved_by"] = "agent:owner"
                elif mutation == "human-approver":
                    wave["approval"]["approved_by"] = "human:unapproved"
                elif mutation == "packet":
                    wave["approval"]["approved_commit"] = head
                elif mutation == "scope":
                    altered["objective"] = "Unapproved scope"
                elif mutation == "verifier":
                    taskctl.index_backlog(changed)[3]["CAP-00.S06.T04"]["status"] = "NOT_STARTED"
                elif mutation == "review":
                    altered["review"]["reviewer"] = altered["owner"]
                elif mutation == "amendment":
                    altered["amendment_id"] = "W2.A99"
                elif mutation == "early-claim":
                    altered["base_sha"] = wave["approval"]["approved_commit"]
                else:
                    altered["experience_change"] = {"kind": "intentional-design-change"}
                altered_task = copy.deepcopy(task)
                altered_task["correction"]["origin_sha256"] = taskctl.canonical_json_sha256(
                    taskctl.corrective_origin_snapshot(altered)
                )
                self.assertTrue(ui_gate.linked_conformance_origin_errors(REPO, head, changed, altered_task, altered))

    def test_linked_classification_schema_does_not_admit_other_lanes(self) -> None:
        schema = json.loads((REPO / "design/ui-change.schema.json").read_text(encoding="utf-8"))
        contract = self.contract("defect-restoration", "a" * 64, "b" * 40, task_id="W2.C02.T01")
        contract["restorationClassification"] = {
            "path": "artifacts/evidence/W2.C02.T01.ui-classification-R01.json",
            "commit": "c" * 40,
            "sha256": "d" * 64,
        }
        validator = Draft202012Validator(schema)
        self.assertEqual([], list(validator.iter_errors(contract)))
        for task_id in ("CAP-04.S02.T03", "W2.A01.T01"):
            self.assertTrue(list(validator.iter_errors({**contract, "taskId": task_id})))
        self.assertTrue(list(validator.iter_errors({**contract, "schemaVersion": "1.1"})))

    def test_linked_conformance_real_git_approval_must_precede_claim(self) -> None:
        for initial_status in ("NOT_STARTED", "IN_PROGRESS", "DONE"):
            with self.subTest(status=initial_status), tempfile.TemporaryDirectory() as temporary:
                root, _, _ = self.prepare(temporary)
                origin: dict[str, Any] = {
                    "id": "CAP-01.S01.T01",
                    "status": initial_status,
                    "wave": "W1",
                    "review_gate": "agent-review",
                    "title": "Approved route",
                    "objective": "Restore route",
                    "dependencies": [],
                    "acceptance_criteria": ["Approved route"],
                    "verification_commands": [],
                }
                data: dict[str, Any] = {
                    "capabilities": [
                        {
                            "id": "CAP-01",
                            "slices": [
                                {
                                    "id": "CAP-01.S01",
                                    "wave": "W1",
                                    "tasks": [origin],
                                }
                            ],
                        }
                    ],
                    "waves": [{"id": "W1", "approval": {"status": "PENDING"}}],
                }
                self.write_yaml(root / "planning/backlog.yaml", data)
                packet = self.commit(root, "proposed Wave packet")
                data["waves"][0]["approval"] = {
                    "status": "APPROVED",
                    "approved_by": "human:fixture-owner",
                    "approved_commit": packet,
                    "capability_ids": ["CAP-01"],
                    "slice_ids": ["CAP-01.S01"],
                }
                self.write_yaml(root / "planning/backlog.yaml", data)
                self.commit(root, "separate Wave approval")
                origin.update(
                    {
                        "status": "DONE",
                        "owner": "owner",
                        "base_sha": packet,
                        "review": {"reviewer": "agent:independent", "result": "approved"},
                    }
                )
                self.write_yaml(root / "planning/backlog.yaml", data)
                head = self.commit(root, "late completed-task delivery cannot authorize early execution")
                task = {
                    "wave": "W1",
                    "correction": {
                        "origin_commit": head,
                        "origin_amendment_id": None,
                        "origin_sha256": taskctl.canonical_json_sha256(origin),
                    },
                }
                errors = ui_gate.linked_conformance_origin_errors(root, head, data, task, origin)
                self.assertTrue(
                    any(
                        ("precede the original claim" if initial_status == "NOT_STARTED" else "scope differs") in error
                        for error in errors
                    ),
                    errors,
                )

    def test_ordinary_origin_delivery_preserves_contract_and_claim_identity(self) -> None:
        head = self.git(REPO, "rev-parse", "HEAD")
        data = yaml.safe_load(ui_gate.blob(REPO, head, "planning/backlog.yaml").decode("utf-8"))
        origin = taskctl.index_backlog(data)[3]["CAP-04.S02.T03"]
        reference = origin["review_control"]["attempts"][-1]["ledger"]
        _, introduction = ui_gate.immutable_record(REPO, head, reference["path"], reference["sha256"], evidence=True)
        previous = ui_gate.resolve_commit(REPO, f"{introduction}^")
        before = yaml.safe_load(ui_gate.blob(REPO, previous, "planning/backlog.yaml").decode("utf-8"))
        self.assertTrue(ui_gate.correction_submission_ranges(REPO, head, {"tasks": [origin]}, ordinary_origin=True))
        with self.assertRaisesRegex(ValueError, "frozen-submission transition"):
            ui_gate.correction_submission_ranges(REPO, head, {"tasks": [origin]})
        original_blob = ui_gate.blob
        for field in ("branch", "objective", "worktree", "platform_targets"):
            with self.subTest(field=field):
                changed = copy.deepcopy(before)
                altered = taskctl.index_backlog(changed)[3][origin["id"]]
                altered[field] = ["unsupported-platform"] if field == "platform_targets" else "substituted"
                payload = yaml.safe_dump(taskctl.serializable_backlog(changed)).encode("utf-8")

                def substitute(repo: Path, commit: str, path: str, payload: bytes = payload) -> bytes:
                    if commit == previous and path == "planning/backlog.yaml":
                        return payload
                    return original_blob(repo, commit, path)

                with (
                    patch("ui_change_gate.blob", side_effect=substitute),
                    self.assertRaisesRegex(ValueError, "frozen-submission transition"),
                ):
                    ui_gate.correction_submission_ranges(REPO, head, {"tasks": [origin]}, ordinary_origin=True)

    def test_ordinary_submission_lineage_uses_actual_git_ancestry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            (root / "candidate.txt").write_text("one", encoding="utf-8")
            candidate = self.commit(root, "first candidate")
            (root / "delivery.txt").write_text("evidence", encoding="utf-8")
            delivery = self.commit(root, "evidence and review")
            task = {"base_sha": base, "branch": "main"}
            packet = {"base_commit": base, "candidate_commit": candidate, "branch": "main"}
            ui_gate.require_ordinary_submission_lineage(root, task, packet, None, delivery, delivery)
            unrelated = self.git(
                root, "commit-tree", self.git(root, "rev-parse", f"{candidate}^{{tree}}"), "-m", "unrelated"
            )
            for changed, evidence, review in (
                ({**packet, "base_commit": candidate}, delivery, delivery),
                ({**packet, "branch": "other"}, delivery, delivery),
                ({**packet, "candidate_commit": base}, delivery, delivery),
                ({**packet, "candidate_commit": unrelated}, delivery, delivery),
                (packet, candidate, delivery),
                (packet, delivery, candidate),
            ):
                with self.subTest(packet=changed, evidence=evidence), self.assertRaises(ValueError):
                    ui_gate.require_ordinary_submission_lineage(root, task, changed, None, evidence, review)
            (root / "candidate.txt").write_text("two", encoding="utf-8")
            second = self.commit(root, "remediation candidate")
            (root / "delivery.txt").write_text("second evidence", encoding="utf-8")
            final = self.commit(root, "second evidence and review")
            remediation = {"base_commit": candidate, "candidate_commit": second, "branch": "main"}
            ui_gate.require_ordinary_submission_lineage(root, task, remediation, packet, final, final)
            with self.assertRaises(ValueError):
                ui_gate.require_ordinary_submission_lineage(
                    root, task, {**remediation, "base_commit": base}, packet, final, final
                )

    def test_linked_conformance_eligibility_never_substitutes_for_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary, review_gate="agent-review")
            head = self.linked_candidate(root, data, contract)
            # Only the separately covered origin-authority boundary is stubbed.
            # The real gate must still reject missing independent product proof.
            with patch("ui_change_gate.linked_conformance_origin_errors", return_value=[]):
                self.assertEqual(base, automatic_base(root, "HEAD"))
                result = validate(root, base, head)
            self.assertFalse(result["ok"], result)
            self.assertTrue(any("independent classification" in error for error in result["errors"]), result)

    def test_ordinary_no_ui_historical_range_still_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            self.write_json(root / "artifacts/evidence/ordinary.json", {"note": "non-UI evidence"})
            historical = self.commit(root, "ordinary evidence-only candidate")
            (root / "planning/backlog.yaml").unlink()
            head = self.commit(root, "minimal repository without a task ledger")
            self.assertTrue(validate(root, base, historical)["ok"])
            self.assertTrue(validate(root, historical, head)["ok"])

    def linked_hidden_scope_fixture(self, temporary: str, paths: list[str]) -> tuple[Path, str, str, str]:
        root, base, data, _contract = self.linked_fixture(temporary)
        (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'unreviewed';\n", encoding="utf-8")
        ui_commit = self.commit(root, "real UI change without its required contract")
        data["waves"][0]["campaign"]["corrective_tasks"][0]["correction"]["changed_paths"] = paths
        self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
        self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": "substituted scope"})
        head = self.commit(root, "evidence-only head with substituted current scope")
        return root, base, ui_commit, head

    def test_linked_discovery_authenticates_before_scope_filtering(self) -> None:
        for paths in ([], ["tests/desktop/test_view.py"]):
            with self.subTest(paths=paths), tempfile.TemporaryDirectory() as temporary:
                root, _base, _ui_commit, _head = self.linked_hidden_scope_fixture(temporary, paths)
                with self.assertRaisesRegex(ValueError, "corrective spec content differs from admission"):
                    automatic_base(root, "HEAD")

    def test_linked_explicit_no_ui_authenticates_before_scope_filtering(self) -> None:
        for paths in ([], ["tests/desktop/test_view.py"]):
            with self.subTest(paths=paths), tempfile.TemporaryDirectory() as temporary:
                root, base, ui_commit, head = self.linked_hidden_scope_fixture(temporary, paths)
                self.assertFalse(validate(root, base, head)["ok"])
                result = validate(root, ui_commit, head)
                self.assertFalse(result["ok"], result)
                self.assertTrue(
                    any("corrective spec content differs from admission" in error for error in result["errors"]), result
                )

    def test_linked_public_cli_rejects_scope_disappearance(self) -> None:
        for paths in ([], ["tests/desktop/test_view.py"]):
            with tempfile.TemporaryDirectory() as temporary:
                root, _base, ui_commit, _head = self.linked_hidden_scope_fixture(temporary, paths)
                for explicit_base in ([], ["--base", ui_commit]):
                    with self.subTest(paths=paths, explicit_base=bool(explicit_base)):
                        completed = subprocess.run(
                            [
                                sys.executable,
                                "-B",
                                str(REPO / "tools/ui_change_gate.py"),
                                "--repo",
                                str(root),
                                *explicit_base,
                            ],
                            cwd=REPO,
                            capture_output=True,
                            text=True,
                            timeout=45,
                            check=False,
                        )
                        self.assertEqual(1, completed.returncode, completed.stdout + completed.stderr)
                        result = json.loads(completed.stdout)
                        self.assertFalse(result["ok"], result)
                        self.assertTrue(
                            any(
                                "corrective spec content differs from admission" in error for error in result["errors"]
                            ),
                            result,
                        )

    def test_linked_genuinely_admitted_non_ui_correction_keeps_parent_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _data, _contract = self.linked_fixture(
                temporary, review_gate="agent-review", changed_paths=["tests/desktop/test_view.py"]
            )
            target = root / "tests/desktop/test_view.py"
            target.parent.mkdir(parents=True)
            target.write_text("# admitted non-UI correction fixture\n", encoding="utf-8")
            head = self.commit(root, "genuinely admitted non-UI correction")
            self.assertEqual("HEAD^", automatic_base(root, "HEAD"))
            self.assertTrue(validate(root, base, head)["ok"])
            self.assertTrue(validate(root, "HEAD^", head)["ok"])
            completed = subprocess.run(
                [sys.executable, "-B", str(REPO / "tools/ui_change_gate.py"), "--repo", str(root)],
                cwd=REPO,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertTrue(json.loads(completed.stdout)["ok"])

    def linked_relocated_correction_fixture(self, temporary: str, shape: str = "both") -> tuple[Path, str, str, str]:
        root, base, data, contract = self.linked_fixture(temporary)
        ui_commit = self.linked_candidate(root, data, contract)
        task = data["waves"][0]["campaign"]["corrective_tasks"].pop()
        if shape == "id-only":
            task.pop("correction")
        elif shape == "binding-only":
            task["id"] = "CAP-01.S01.T99"
        data["capabilities"][0]["slices"][0]["tasks"].append(task)
        self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
        self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": "relocated correction"})
        head = self.commit(root, "relocate correction into ordinary inventory after UI work")
        return root, base, ui_commit, head

    def test_linked_public_cli_rejects_relocated_correction_on_short_no_ui_range(self) -> None:
        for shape in ("both", "id-only", "binding-only"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as temporary:
                root, _base, ui_commit, _head = self.linked_relocated_correction_fixture(temporary, shape)
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(REPO / "tools/ui_change_gate.py"),
                        "--repo",
                        str(root),
                        "--base",
                        ui_commit,
                    ],
                    cwd=REPO,
                    capture_output=True,
                    text=True,
                    timeout=45,
                    check=False,
                )
                self.assertEqual(1, completed.returncode, completed.stdout + completed.stderr)
                result = json.loads(completed.stdout)
                self.assertFalse(result["ok"], result)
                self.assertTrue(
                    any("must be an admitted campaign corrective task" in error for error in result["errors"]), result
                )

    def test_linked_relocated_correction_is_denied_before_all_range_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, ui_commit, head = self.linked_relocated_correction_fixture(temporary)
            with self.assertRaisesRegex(ValueError, "must be an admitted campaign corrective task"):
                automatic_base(root, "HEAD")
            self.assertFalse(validate(root, base, head)["ok"])
            result = validate(root, ui_commit, head)
            self.assertFalse(result["ok"], result)
            self.assertTrue(
                any("must be an admitted campaign corrective task" in error for error in result["errors"]), result
            )

    def legacy_control_fixture(
        self, temporary: str, mutation: str = "", *, existing_root: Path | None = None
    ) -> tuple[Path, str, str, str]:
        if existing_root is None:
            root, predecessor, _ = self.prepare(temporary, adr_registry=mutation.startswith("adr-"))
        else:
            root, predecessor = existing_root, self.git(existing_root, "rev-parse", "HEAD")
        stem = "artifacts/evidence/fixture-control"
        contract_path, evidence_path, review_path = (
            stem + ".maintenance-01.md",
            stem + ".evidence-01.json",
            stem + ".review-01.json",
        )
        sources = [contract_path, "tools/ui_conformance.py"]
        if mutation == "product":
            sources.append("apps/desktop/src-tauri/src/lib.rs")
        elif mutation == "build-tool":
            sources.append("tools/core_sidecar_build.py")
        for path in sources:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# Bounded synthetic control fixture\n", encoding="utf-8")
        if mutation.startswith("adr-"):
            index_path = "docs/adr/index.json"
            adr_path = "docs/adr/ADR-0002-document-existing-control-association.md"
            index = json.loads((root / index_path).read_text("utf-8"))
            metadata: dict[str, Any] = {
                "id": "ADR-0002",
                "title": "Document existing control association",
                "status": "Proposed",
                "date": "2026-09-27",
                "deciders": [],
                "linked_tasks": ["CAP-01.S01.T01"],
                "decision_scope": "Document existing authority without conferring any decision",
                "affected_paths": ["tools/ui_conformance.py"],
                "supersedes": [],
                "superseded_by": None,
            }
            if mutation == "adr-state":
                metadata["status"] = "Accepted"
            elif mutation == "adr-decider":
                metadata["deciders"] = ["human:synthetic-owner"]
            elif mutation == "adr-supersedes":
                metadata["supersedes"] = ["ADR-0001"]
            elif mutation == "adr-successor":
                metadata["superseded_by"] = "ADR-0001"
            elif mutation == "adr-authority-field":
                metadata["approval"] = "synthetic authority"
            elif mutation == "adr-unknown-task":
                metadata["linked_tasks"] = ["CAP-99.S99.T99"]
            elif mutation == "adr-wildcard":
                metadata["affected_paths"] = ["tools/**"]
            elif mutation == "adr-traversal":
                metadata["affected_paths"] = ["tools/../tools/ui_conformance.py"]
            elif mutation == "adr-unrelated":
                metadata["affected_paths"] = ["tools/ui_change_gate.py"]
            elif mutation == "adr-duplicate":
                metadata["affected_paths"] *= 2
            entry = {
                "id": metadata["id"],
                "path": adr_path,
                "title": metadata["title"],
                "status": metadata["status"],
                "linkedTasks": metadata["linked_tasks"],
            }
            index["records"].append(entry)
            if mutation == "adr-old-index":
                index["records"][0]["title"] = "changed prior authority"
            elif mutation == "adr-index-metadata":
                index["schemaVersion"] = "2.0"
            elif mutation == "adr-index-mismatch":
                entry["title"] = "different title"
            elif mutation == "adr-index-reorder":
                index["records"].reverse()
            self.write_json(root / index_path, index)
            sections = ["Context", "Candidates", "Decision", "Consequences", "Verification", "Task links"]
            if mutation == "adr-sections":
                sections.remove("Decision")
            (root / adr_path).write_text(
                "---\n"
                + yaml.safe_dump(metadata, sort_keys=False)
                + "---\n"
                + "\n".join(f"## {section}\nSynthetic association; existing authority only.\n" for section in sections),
                encoding="utf-8",
            )
            sources.extend([index_path, adr_path])
            if mutation == "adr-old-document":
                previous = "docs/adr/ADR-0001-existing-authority.md"
                (root / previous).write_text("rewritten accepted authority\n", encoding="utf-8")
                sources.append(previous)
            if mutation == "adr-missing-index":
                (root / index_path).write_bytes(ui_gate.blob(root, predecessor, index_path))
                sources.remove(index_path)
            if mutation == "adr-executable":
                self.git(root, "add", adr_path)
                self.git(root, "update-index", "--chmod=+x", adr_path)
        candidate = self.commit(root, "legacy control candidate")

        def source_binding(commit: str) -> dict[str, Any]:
            return {
                "commit": commit,
                "changedFiles": [
                    {
                        "path": path,
                        "gitBlob": self.git(root, "rev-parse", f"{commit}:{path}"),
                        "sha256": hashlib.sha256(ui_gate.blob(root, commit, path)).hexdigest(),
                    }
                    for path in sorted(ui_gate.commit_paths(root, commit))
                ],
            }

        source_commits = None
        if mutation.startswith("source-") or mutation in {"adr-rewrite-revert", "adr-old-rewrite-revert"}:
            source_commits = [source_binding(candidate)]
            if mutation in {"adr-rewrite-revert", "adr-old-rewrite-revert"}:
                document_path = (
                    "docs/adr/ADR-0001-existing-authority.md"
                    if mutation == "adr-old-rewrite-revert"
                    else "docs/adr/ADR-0002-document-existing-control-association.md"
                )
                document = root / document_path
                if document_path not in sources:
                    sources.append(document_path)
                original_adr = document.read_bytes()
                document.write_bytes(original_adr + b"\nintermediate rewrite\n")
                source_commits.append(source_binding(self.commit(root, "rewrite associated ADR")))
                document.write_bytes(original_adr)
            if mutation == "source-hidden-product":
                product = root / "apps/desktop/src/View.tsx"
                original = product.read_bytes()
                product.write_text("export const View = () => 'hidden product edit';\n", encoding="utf-8")
                source_commits.append(source_binding(self.commit(root, "hidden intermediate product")))
                product.write_bytes(original)
            (root / "tools/ui_conformance.py").write_text("# Remediated control fixture\n", encoding="utf-8")
            candidate = self.commit(root, "correct bounded source candidate")
            source_commits.append(source_binding(candidate))
            if mutation == "source-merge":
                self.git(root, "switch", "-c", "source-side", source_commits[0]["commit"])
                (root / contract_path).write_text("# Side control note\n", encoding="utf-8")
                self.commit(root, "side source history")
                self.git(root, "switch", "main")
                self.git(root, "merge", "--no-ff", "source-side", "-m", "merged source history")
                candidate = self.git(root, "rev-parse", "HEAD")
                sequence = self.git(root, "rev-list", "--reverse", f"{predecessor}..{candidate}").splitlines()
                source_commits = [source_binding(item) for item in sequence[:-1]]
                source_commits.append({"commit": candidate, "changedFiles": []})
            if mutation == "source-omitted":
                source_commits = source_commits[1:]
            elif mutation == "source-reordered":
                source_commits.reverse()
            elif mutation == "source-hash":
                source_commits[0]["changedFiles"][0]["sha256"] = "0" * 64
            elif mutation == "source-inventory":
                source_commits[0]["changedFiles"] = []
        bindings = [
            {
                "path": path,
                "blob": self.git(root, "rev-parse", candidate + ":" + path),
                "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest(),
            }
            for path in sorted(sources)
        ]
        evidence = {
            "schemaVersion": "1.0",
            "documentType": "bounded-governance-maintenance-evidence",
            "candidateCommit": candidate,
            "predecessorCommit": predecessor,
            "implementer": "agent:codex",
            "riskTier": 2,
            "contract": contract_path,
            "selectedChecksStatus": "PASS",
            "independentReviewStatus": "PENDING",
            "changedFiles": bindings,
        }
        if mutation == "missing-implementer":
            evidence.pop("implementer")
        elif mutation == "invalid-implementer":
            evidence["implementer"] = "not an agent"
        if source_commits is not None:
            evidence["sourceCommits"] = source_commits
        if mutation == "source-union":
            evidence["changedFiles"] = bindings[:-1]
        self.write_json(root / evidence_path, evidence)
        if mutation == "mixed-evidence":
            (root / "extra.txt").write_text("extra delivery\n", encoding="utf-8")
        delivery = self.commit(root, "legacy evidence delivery")
        review: dict[str, Any] = {
            "schemaVersion": "1.0",
            "documentType": "bounded-governance-maintenance-independent-review",
            "reviewId": "fixture-control.review-01",
            "reviewedCommit": candidate,
            "predecessorCommit": predecessor,
            "reviewedAt": "2026-09-01T00:00:00Z",
            "reviewer": "agent:independent-reviewer",
            "independence": {"implementer": "agent:codex", "implementationAuthoredByReviewer": False},
            "disposition": "ACCEPTED",
            "findings": [],
            "evidence": {
                "path": evidence_path,
                "introductionCommit": delivery,
                "gitBlob": self.git(root, "rev-parse", delivery + ":" + evidence_path),
                "sha256": hashlib.sha256((root / evidence_path).read_bytes()).hexdigest(),
            },
            "reviewedArtifacts": [
                {"path": item["path"], "gitBlob": item["blob"], "sha256": item["sha256"]} for item in bindings
            ],
        }
        if mutation == "self-review":
            review["reviewer"] = "agent:co_dex"
        elif mutation == "missing-implementer":
            review["independence"].pop("implementer")
        elif mutation == "invalid-implementer":
            review["independence"]["implementer"] = "not an agent"
        elif mutation == "wrong-candidate":
            review["reviewedCommit"] = predecessor
        elif mutation == "wrong-predecessor":
            review["predecessorCommit"] = candidate
        elif mutation == "evidence-hash":
            review["evidence"]["sha256"] = "0" * 64
        elif mutation == "source-hash":
            review["reviewedArtifacts"][0]["sha256"] = "0" * 64
        elif mutation == "adverse":
            review["findings"] = [{"id": "OPEN"}]
        if source_commits is not None:
            review["sourceCommits"] = copy.deepcopy(source_commits)
        if mutation == "source-mismatch":
            review["sourceCommits"] = []
        self.write_json(root / review_path, review)
        if mutation == "mixed-review":
            (root / "extra-review.txt").write_text("extra delivery\n", encoding="utf-8")
        self.commit(root, "legacy independent review")
        if mutation == "rewrite-revert":
            self.write_json(root / review_path, {**review, "findings": [{"id": "changed"}]})
            self.commit(root, "rewrite historical review")
            self.write_json(root / review_path, review)
            self.commit(root, "restore historical review bytes")
        if existing_root is None:
            (root / "claim-marker.txt").write_text("later correction start\n", encoding="utf-8")
            cutoff = self.commit(root, "correction task start")
        else:
            cutoff = self.git(root, "rev-parse", "HEAD")
        return root, candidate, cutoff, review_path

    def test_linked_source_remediation_preserves_exact_intermediate_control_history(self) -> None:
        for mutation in (
            "source-valid",
            "source-omitted",
            "source-reordered",
            "source-hash",
            "source-inventory",
            "source-union",
            "source-mismatch",
            "source-hidden-product",
            "source-merge",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, candidate, head, _ = self.legacy_control_fixture(temporary, mutation)
                errors = ui_gate.legacy_control_maintenance_errors(root, candidate, head, head)
                self.assertEqual(mutation != "source-valid", bool(errors), errors)

    def test_linked_public_scope_rejects_unattributed_control_contract_and_delivery(self) -> None:
        for path in (
            "tools/taskctl.py",
            "artifacts/evidence/fixture-control.maintenance-01.md",
            "artifacts/evidence/unrelated.json",
        ):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                root, base, data, contract = self.linked_fixture(temporary)
                self.linked_candidate(root, data, contract)
                if path != "tools/taskctl.py":
                    self.legacy_control_fixture(temporary, existing_root=root)
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("unreviewed change\n", encoding="utf-8")
                head = self.commit(root, "unattributed out-of-scope change")
                result = validate(root, base, head)
                self.assertFalse(result["ok"], result)

    def test_linked_control_maintenance_requires_exact_reviewed_commit_attribution(self) -> None:
        for mutation in (
            "",
            "source-valid",
            "self-review",
            "product",
            "mixed-evidence",
            "adverse",
            "later",
            "later-revert",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, base, data, contract = self.linked_fixture(temporary)
                self.linked_candidate(root, data, contract)
                _, _, head, _ = self.legacy_control_fixture(temporary, mutation, existing_root=root)
                if mutation.startswith("later"):
                    source = root / "tools/ui_conformance.py"
                    original = source.read_bytes()
                    source.write_text("# unreviewed later change\n", encoding="utf-8")
                    head = self.commit(root, "later unreviewed same control path")
                    if mutation == "later-revert":
                        source.write_bytes(original)
                        head = self.commit(root, "hide unreviewed control change")
                result = validate(root, base, head)
                self.assertEqual(mutation in {"", "source-valid"}, result["ok"], result["errors"])
                task = data["waves"][0]["campaign"]["corrective_tasks"][0]
                manifest = {
                    "commit": head,
                    "baseCommit": base,
                    "changedFiles": sorted(ui_gate.changed_paths(root, base, head)),
                }
                errors = taskctl.validate_task_evidence(task, manifest, repo=root)
                scope_errors = [error for error in errors if "scope" in error or "maintenance" in error]
                self.assertEqual(mutation not in {"", "source-valid"}, bool(scope_errors), errors)

    def test_linked_amendment_origin_uses_existing_approved_contract_not_a_new_review_field(self) -> None:
        # Read only the existing named approval/packet/UI contract and Git origin.
        # This is authority proof, not fresh product or native qualification.
        head = self.git(REPO, "rev-parse", "HEAD")
        data = yaml.safe_load(ui_gate.blob(REPO, head, "planning/backlog.yaml"))
        indexed = taskctl.index_backlog(data)
        origin = indexed[3]["W1.A05.T04"]
        correction = indexed[3]["W1.C04.T01"]
        self.assertNotIn("review_gate", origin)
        self.assertEqual([], ui_gate.linked_amendment_origin_errors(REPO, head, data, correction, origin))
        for mutation in ("origin-id", "kind", "contract", "amendment", "candidate"):
            altered = copy.deepcopy(origin)
            bound = copy.deepcopy(correction)
            if mutation == "origin-id":
                altered["id"] = "W1.A05.T03"
            elif mutation == "kind":
                altered["experience_change"]["kind"] = "defect-restoration"
            elif mutation == "contract":
                altered["experience_change"]["contract_path"] = "artifacts/evidence/ui-change/other.json"
            elif mutation == "amendment":
                bound["correction"]["origin_amendment_id"] = "W1.A04"
            else:
                altered["review_control"]["attempts"][-1]["submission"]["candidate_commit"] = head
            with self.subTest(mutation=mutation):
                self.assertTrue(ui_gate.linked_amendment_origin_errors(REPO, head, data, bound, altered))

    def test_legacy_control_maintenance_authenticates_existing_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, candidate, cutoff, _ = self.legacy_control_fixture(temporary)
            self.assertEqual([], ui_gate.legacy_control_maintenance_errors(root, candidate, cutoff, cutoff))

    def test_maintenance_proposed_adr_association_preserves_prior_authority(self) -> None:
        for mutation in (
            "adr-valid",
            "adr-state",
            "adr-decider",
            "adr-supersedes",
            "adr-successor",
            "adr-authority-field",
            "adr-unknown-task",
            "adr-wildcard",
            "adr-traversal",
            "adr-unrelated",
            "adr-duplicate",
            "adr-old-index",
            "adr-index-metadata",
            "adr-index-mismatch",
            "adr-index-reorder",
            "adr-sections",
            "adr-old-document",
            "adr-missing-index",
            "adr-executable",
            "adr-rewrite-revert",
            "adr-old-rewrite-revert",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, candidate, head, _ = self.legacy_control_fixture(temporary, mutation)
                errors = ui_gate.legacy_control_maintenance_errors(root, candidate, head, head)
                self.assertEqual(mutation != "adr-valid", bool(errors), errors)

    def test_linked_correction_accepts_only_review_bound_proposed_adr_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary, adr_registry=True)
            self.linked_candidate(root, data, contract)
            _, _, head, _ = self.legacy_control_fixture(temporary, "adr-valid", existing_root=root)
            result = validate(root, base, head)
            self.assertTrue(result["ok"], result["errors"])
            task = data["waves"][0]["campaign"]["corrective_tasks"][0]
            self.assertEqual([], ui_gate.corrective_scope_errors(root, task, head))
            # The new document does not become an ordinary task-writable path.
            adr_path = "docs/adr/ADR-0002-document-existing-control-association.md"
            self.assertFalse(ui_gate.corrective_path_admitted(task, adr_path))
            original = (root / adr_path).read_bytes()
            (root / adr_path).write_bytes(original + b"\nunreviewed follow-up\n")
            self.commit(root, "unreviewed associated ADR rewrite")
            (root / adr_path).write_bytes(original)
            reverted = self.commit(root, "revert associated ADR rewrite")
            self.assertTrue(ui_gate.corrective_scope_errors(root, task, reverted))

    def test_legacy_control_maintenance_rejects_false_or_late_authority(self) -> None:
        for mutation in (
            "self-review",
            "wrong-candidate",
            "wrong-predecessor",
            "evidence-hash",
            "source-hash",
            "adverse",
            "product",
            "build-tool",
            "mixed-evidence",
            "mixed-review",
            "rewrite-revert",
            "late",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, candidate, cutoff, _ = self.legacy_control_fixture(temporary, mutation)
                boundary = candidate if mutation == "late" else cutoff
                self.assertTrue(ui_gate.legacy_control_maintenance_errors(root, candidate, cutoff, boundary))

    def test_legacy_control_maintenance_requires_valid_implementer_identity(self) -> None:
        for mutation in ("missing-implementer", "invalid-implementer"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, candidate, cutoff, _ = self.legacy_control_fixture(temporary, mutation)
                self.assertTrue(ui_gate.legacy_control_maintenance_errors(root, candidate, cutoff, cutoff))

    def test_inherited_control_admission_requires_exact_complete_linear_range(self) -> None:
        for mutation in ("", "extra-path", "hidden-extra-revert", "overlap", "outside", "merge", "later-revert"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, base, _ = self.prepare(temporary)
                policy = json.loads((root / "ui-change-policy.json").read_text())
                source = root / "tools/ui_conformance.py"
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("CHECK = True\n", encoding="utf-8")
                (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'inherited';\n")
                if mutation in {"extra-path", "hidden-extra-revert"}:
                    (root / "extra.txt").write_text("not reviewed\n")
                candidate = self.commit(root, "reviewed correction control and UI")
                if mutation == "hidden-extra-revert":
                    self.git(root, "rm", "extra.txt")
                    candidate = self.commit(root, "remove undeclared intermediate path")
                paths = ["apps/desktop/src/View.tsx", "tools/ui_conformance.py"]
                ranges = [{"base": base, "candidate": candidate, "paths": paths}]
                if mutation == "overlap":
                    ranges *= 2
                elif mutation == "outside":
                    ranges = []
                if mutation == "merge":
                    self.git(root, "switch", "-c", "side")
                    (root / "side.txt").write_text("side\n")
                    self.commit(root, "side history")
                    self.git(root, "switch", "main")
                    self.git(root, "merge", "--no-ff", "side", "-m", "merge ambiguity")
                (root / "activation.txt").write_text("returned parent\n")
                activation = self.commit(root, "parent activation")
                if mutation == "later-revert":
                    source.write_text("CHECK = False\n")
                    self.commit(root, "unreviewed later control")
                    source.write_text("CHECK = True\n")
                    self.commit(root, "restore later control bytes")
                (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'restored';\n")
                head = self.commit(root, "resumed UI")
                scope = {"correctionSubmissionRanges": ranges, "reactivationCommit": activation}
                errors = application_activation_errors(
                    root,
                    base,
                    head,
                    ["tools/ui_conformance.py"],
                    {"schemaVersion": "1.1", "changeKind": "defect-restoration", "amendmentAuthority": {}},
                    policy,
                    resumed_scope=scope,
                )
                self.assertEqual(bool(mutation), bool(errors), errors)

    def test_public_resumed_control_dispatch_authenticates_once_before_admission(self) -> None:
        for invalid_authority in (False, True):
            with self.subTest(invalid_authority=invalid_authority), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'restored';\n")
                (root / "tools").mkdir(exist_ok=True)
                (root / "tools/ui_conformance.py").write_text("CHECK = True\n")
                contract = self.contract("defect-restoration", package, base, task_id="W1.A08.T02")
                contract.update(
                    {
                        "schemaVersion": "1.1",
                        "amendmentAuthority": {
                            "correctionId": "W1.A09",
                            "adoptionCommit": "c" * 40,
                            "reactivationCommit": "d" * 40,
                            "inheritedCorrectionUiFiles": ["apps/desktop/src/View.tsx"],
                            "resumedUiFiles": ["apps/desktop/src/View.tsx"],
                            "classification": {
                                "path": "artifacts/evidence/W1.A08.T02.ui-classification-R01.json",
                                "sha256": "e" * 64,
                                "commit": "f" * 40,
                            },
                        },
                    }
                )
                self.install_contract(root, contract, base_sha=base)
                backlog_path = root / "planning/backlog.yaml"
                backlog = yaml.safe_load(backlog_path.read_text())
                task = backlog["wave_amendments"][0]["tasks"][0]
                task.update({"branch": "main", "lease": {"claimed_by": "codex"}})
                self.write_yaml(backlog_path, backlog)
                head = self.commit(root, "synthetic resumed public boundary")
                calls: list[str] = []
                scope = {"correctionSubmissionRanges": [], "reactivationCommit": "d" * 40}

                # Stub only authenticated authority/classification for this
                # public dispatch test; real Git range/review checks are separate.
                def authenticate(
                    *_args: object,
                    recorded: list[str] = calls,
                    invalid: bool = invalid_authority,
                    bound_scope: dict[str, Any] = scope,
                ) -> dict[str, Any]:
                    recorded.append("authenticate")
                    if invalid:
                        raise ValueError("unadopted or unreviewed correction")
                    return bound_scope

                def admit(
                    *_args: object,
                    recorded: list[str] = calls,
                    bound_scope: dict[str, Any] = scope,
                    **kwargs: object,
                ) -> list[str]:
                    recorded.append("admit")
                    self.assertIs(bound_scope, kwargs.get("resumed_scope"))
                    return []

                with (
                    patch("ui_change_gate.resumed_amendment_authority", side_effect=authenticate) as authority,
                    patch("ui_change_gate.application_activation_errors", side_effect=admit),
                    patch("ui_change_gate.restoration_classification_errors", return_value=[]),
                ):
                    result = validate(root, base, head)
                self.assertEqual(not invalid_authority, result["ok"], result["errors"])
                self.assertEqual(["authenticate"] if invalid_authority else ["authenticate", "admit"], calls)
                authority.assert_called_once()

    def test_resumed_hold_rejects_inconsistent_current_authority(self) -> None:
        parent: dict[str, Any] = {
            "id": "W1.A08",
            "lifecycle": {"status": "ACTIVE"},
            "campaign": {
                "status": "ACTIVE",
                "scope": "wave-amendment",
                "owner": "codex",
                "lease": {"claimed_by": "codex"},
            },
        }
        backlog: dict[str, Any] = {"control_plane": {"active_amendment": "W1.A08"}, "wave_amendments": [parent]}
        projections = [
            {
                "parentId": "W1.A08",
                "correctionId": "W1.A09",
                "phase": "returned",
                "holdOwner": "W1.A08",
                "parentFrozen": False,
            }
        ]
        require_resumed_hold(backlog, parent, "W1.A09", "codex", projections)
        mutations: tuple[tuple[tuple[str, ...], object], ...] = (
            (("lifecycle", "status"), "ADOPTED"),
            (("lifecycle", "status"), "PAUSED"),
            (("campaign", "status"), "REVIEW"),
            (("campaign", "scope"), "wave"),
            (("campaign", "owner"), "other"),
            (("campaign", "lease", "claimed_by"), "other"),
            (("campaign", "lease"), None),
        )
        for path, value in mutations:
            with self.subTest(path=path, value=value):
                mutated = copy.deepcopy(parent)
                node = mutated
                for part in path[:-1]:
                    node = node[part]
                node[path[-1]] = value
                with self.assertRaisesRegex(ValueError, "current lifecycle"):
                    require_resumed_hold(
                        {**backlog, "wave_amendments": [mutated]}, mutated, "W1.A09", "codex", projections
                    )
        for relation in (
            [],
            projections * 2,
            [{**projections[0], "holdOwner": None}],
            [{**projections[0], "parentFrozen": True}],
            [{**projections[0], "phase": "executing"}],
        ):
            with self.subTest(relation=relation), self.assertRaisesRegex(ValueError, "derived hold"):
                require_resumed_hold(backlog, parent, "W1.A09", "codex", relation)
        for document in (
            {**backlog, "control_plane": {"active_amendment": "W1.A09"}},
            {**backlog, "wave_amendments": [parent, {"id": "W1.A10", "campaign": {"status": "ACTIVE"}}]},
        ):
            with self.subTest(document=document), self.assertRaisesRegex(ValueError, "derived hold"):
                require_resumed_hold(document, parent, "W1.A09", "codex", projections)

    def test_classification_real_git_binding_and_stale_or_adverse_denials(self) -> None:
        # The capture reader has its own real PNG/producer suite. Stub only that
        # boundary here; this fixture tests actual Git records and classification,
        # not pixels, renderer behavior, or a complete product qualification.
        for identity, finding in (
            (identity, finding)
            for identity in ("W1.A08.T02", "W2.C02.T01")
            for finding in (None, {"blockingVisualAcceptance": True}, {"blockingVisualAcceptance": 0}, {})
        ):
            with self.subTest(identity=identity, finding=finding), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
                source_path = "apps/desktop/src/View.tsx"
                (root / source_path).write_text("export const View = () => 'restored';\n", encoding="utf-8")
                candidate = self.commit(root, "restoration candidate")
                capture_path = f"artifacts/evidence/{identity}.captures-01/manifest.json"
                manifest = {
                    "schemaVersion": "1.0",
                    "documentType": "product-style-capture-bundle",
                    "producer": {
                        "producerCommit": candidate,
                        "referencePackageSha256": package,
                        "inputGitBlobs": {source_path: self.git(root, "rev-parse", f"{candidate}:{source_path}")},
                    },
                    "report": {"fixtureOnly": True},
                }
                self.write_json(root / capture_path, manifest)
                capture_commit = self.commit(root, "synthetic capture boundary")
                capture_sha = hashlib.sha256((root / capture_path).read_bytes()).hexdigest()
                visual_path = f"artifacts/evidence/{identity}.visual-review-01.json"
                self.write_json(
                    root / visual_path,
                    {
                        "documentType": "independent-product-visual-disposition",
                        "taskId": identity,
                        "reviewer": "agent:/root/fixture_review",
                        "disposition": "approved",
                        "findings": [] if finding is None else [finding],
                        "bindings": {
                            "producerCommit": candidate,
                            "manifest": capture_path,
                            "manifestSha256": capture_sha,
                            "captureDeliveryCommit": capture_commit,
                            "referencePackageSha256": package,
                        },
                    },
                )
                visual_commit = self.commit(root, "synthetic independent visual record")
                scope = {
                    "taskDefinitionSha256": "d" * 64,
                    "resumedUiFiles": [source_path],
                    "resumedUiCommits": [candidate],
                    "reactivationCommit": base,
                }
                classification_path = f"artifacts/evidence/{identity}.ui-classification-R01.json"
                self.write_json(
                    root / classification_path,
                    {
                        "schemaVersion": "1.0",
                        "documentType": "independent-ui-restoration-disposition",
                        "taskId": identity,
                        "baseCommit": base,
                        "candidateCommit": candidate,
                        "reviewer": "agent:/root/fixture_review",
                        "disposition": "approved",
                        "taskDefinitionSha256": scope["taskDefinitionSha256"],
                        "referencePackageSha256": package,
                        "resumedUiFiles": [source_path],
                        "resumedUiCommits": [candidate],
                        "approvedTaskAllowsRestoration": True,
                        "authorityPreserved": True,
                        "formalTaskApproval": False,
                        "normativeRationale": "Synthetic authority fixture, not an actual visual observation.",
                        "captures": {"path": capture_path, "sha256": capture_sha, "deliveryCommit": capture_commit},
                        "visualReview": {
                            "path": visual_path,
                            "commit": visual_commit,
                            "sha256": hashlib.sha256((root / visual_path).read_bytes()).hexdigest(),
                        },
                    },
                )
                head = self.commit(root, "synthetic independent classification")
                contract = {
                    "taskId": identity,
                    "implementationAgent": "agent:codex",
                    "reference": {"packageSha256": package},
                    "amendmentAuthority": {
                        "classification": {
                            "path": classification_path,
                            "commit": head,
                            "sha256": hashlib.sha256((root / classification_path).read_bytes()).hexdigest(),
                        }
                    },
                }
                linked_contract = {key: value for key, value in contract.items() if key != "amendmentAuthority"}
                authority = contract["amendmentAuthority"]
                assert isinstance(authority, dict)
                linked_contract["restorationClassification"] = authority["classification"]
                linked_task: dict[str, Any] = {
                    "id": identity,
                    "correction": {"origin_sha256": "d" * 64, "changed_paths": [source_path]},
                }
                with (
                    patch("product_style_check.read_capture_bundle", return_value=manifest) as capture_reader,
                    patch("desktop_app_check.qualification_capture_contract", return_value=[]),
                    patch("desktop_app_check.qualification_report_errors", return_value=[]),
                    patch("product_style_check.capture_producer_snapshot", return_value=manifest["producer"]),
                    patch("product_style_check.capture_source_identity", return_value={}),
                ):
                    errors = restoration_classification_errors(root, base, head, contract, scope, policy)
                    if finding is not None:
                        self.assertTrue(any("findings" in error for error in errors), errors)
                        capture_reader.assert_not_called()
                    else:
                        self.assertEqual([], errors)
                        capture_reader.assert_called_once()
                        # Same immutable record/capture reader also serves the
                        # new contract reference. It does not classify authority
                        # from a producer's focusedEvidence strings.
                        self.assertEqual(
                            [], restoration_classification_errors(root, base, head, linked_contract, scope, policy)
                        )
                        if identity == "W2.C02.T01":
                            self.assertEqual(
                                [],
                                ui_gate.linked_conformance_classification_errors(
                                    root, base, head, linked_contract, linked_task, policy
                                ),
                            )
                            with patch("desktop_app_check.qualification_report_errors", return_value=["bad focus"]):
                                self.assertTrue(
                                    ui_gate.linked_conformance_classification_errors(
                                        root, base, head, linked_contract, linked_task, policy
                                    )
                                )
                            bad_contract = copy.deepcopy(linked_contract)
                            bad_contract["implementationAgent"] = "agent:/root/fixture_review"
                            self.assertTrue(
                                ui_gate.linked_conformance_classification_errors(
                                    root, base, head, bad_contract, linked_task, policy
                                )
                            )
                            with patch("product_style_check.capture_producer_snapshot", return_value={"stale": True}):
                                self.assertTrue(
                                    ui_gate.linked_conformance_classification_errors(
                                        root, base, head, linked_contract, linked_task, policy
                                    )
                                )
                            added_path = "services/core-api/src/telemetry.py"
                            linked_task["correction"]["changed_paths"].append(added_path)
                            added = root / added_path
                            added.parent.mkdir(parents=True)
                            added.write_text("unreviewed = True\n", encoding="utf-8")
                            changed = self.commit(root, "later non-UI product input")
                            self.assertTrue(
                                ui_gate.linked_conformance_classification_errors(
                                    root, base, changed, linked_contract, linked_task, policy
                                )
                            )
                            added.unlink()
                            changed = self.commit(root, "revert non-UI product input")
                            self.assertTrue(
                                ui_gate.linked_conformance_classification_errors(
                                    root, base, changed, linked_contract, linked_task, policy
                                )
                            )
                        original = (root / source_path).read_bytes()
                        (root / source_path).write_text("export const View = () => 'unreviewed';\n", encoding="utf-8")
                        self.commit(root, "unreviewed UI edit")
                        (root / source_path).write_bytes(original)
                        reverted = self.commit(root, "hide edit by restoring final bytes")
                        errors = restoration_classification_errors(root, base, reverted, contract, scope, policy)
                        self.assertTrue(any("stale" in error for error in errors), errors)

    def test_restoration_judgment_requires_booleans_not_numeric_lookalikes(self) -> None:
        base, candidate, introduction = "a" * 40, "b" * 40, "c" * 40
        identity = "W1.A08.T02"
        scope = {
            "taskDefinitionSha256": "d" * 64,
            "resumedUiFiles": ["apps/desktop/src/View.tsx"],
            "resumedUiCommits": [candidate],
            "reactivationCommit": base,
        }
        contract = {
            "taskId": identity,
            "implementationAgent": "agent:codex",
            "reference": {"packageSha256": "e" * 64},
            "amendmentAuthority": {
                "classification": {
                    "path": f"artifacts/evidence/{identity}.ui-classification-R01.json",
                    "sha256": "f" * 64,
                    "commit": introduction,
                }
            },
        }
        record = {
            "schemaVersion": "1.0",
            "documentType": "independent-ui-restoration-disposition",
            "taskId": identity,
            "baseCommit": base,
            "candidateCommit": candidate,
            "reviewer": "agent:/root/independent_review",
            "disposition": "approved",
            "taskDefinitionSha256": scope["taskDefinitionSha256"],
            "referencePackageSha256": "e" * 64,
            "resumedUiFiles": scope["resumedUiFiles"],
            "resumedUiCommits": [candidate],
            "approvedTaskAllowsRestoration": True,
            "authorityPreserved": True,
            "formalTaskApproval": False,
            "normativeRationale": "Restore approved geometry.",
        }
        for field, value in (
            ("approvedTaskAllowsRestoration", 1),
            ("authorityPreserved", 1),
            ("formalTaskApproval", 0),
        ):
            with (
                self.subTest(field=field),
                patch("ui_change_gate.immutable_record", return_value=({**record, field: value}, introduction)),
                patch("ui_change_gate.is_ancestor", return_value=True),
                patch("ui_change_gate.git") as git_read,
            ):
                errors = restoration_classification_errors(REPO, base, introduction, contract, scope, {})
                self.assertTrue(any("independent approved-task/source classification" in error for error in errors))
                git_read.assert_not_called()

    def test_immutable_authority_record_rejects_rewrite_even_when_reverted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _base, _package = self.prepare(temporary)
            path = "artifacts/evidence/fixture-review.json"
            record = {"disposition": "approved"}
            self.write_json(root / path, record)
            introduction = self.commit(root, "independent record")
            self.assertEqual((record, introduction), immutable_record(root, introduction, path))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                immutable_record(root, introduction, path, "0" * 64)
            self.write_json(root / path, {"disposition": "changes-requested"})
            self.commit(root, "rewrite record")
            self.write_json(root / path, record)
            reverted = self.commit(root, "restore bytes but not history")
            with self.assertRaisesRegex(ValueError, "immutable introduction"):
                immutable_record(root, reverted, path)

    def test_resumed_amendment_schema_is_opt_in_and_cannot_authorize_ordinary_tasks(self) -> None:
        schema = json.loads((REPO / "design/ui-change.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        contract = self.contract("defect-restoration", "a" * 64, "b" * 40, task_id="W1.A08.T02")
        contract.update(
            {
                "schemaVersion": "1.1",
                "amendmentAuthority": {
                    "correctionId": "W1.A09",
                    "adoptionCommit": "c" * 40,
                    "reactivationCommit": "d" * 40,
                    "inheritedCorrectionUiFiles": ["apps/desktop/src/View.tsx"],
                    "resumedUiFiles": ["apps/desktop/src/View.tsx"],
                    "classification": {
                        "path": "artifacts/evidence/W1.A08.T02.ui-classification-R01.json",
                        "sha256": "e" * 64,
                        "commit": "f" * 40,
                    },
                },
            }
        )
        self.assertEqual([], list(validator.iter_errors(contract)))
        invalid_fields: tuple[dict[str, Any], ...] = (
            {"schemaVersion": "1.0"},
            {"taskId": "CAP-01.S01.T01"},
            {"changeKind": "approved-reference-implementation"},
            {"amendmentAuthority": {}},
            {"review_gate": "human-and-agent-review"},
        )
        for fields in invalid_fields:
            with self.subTest(fields=fields):
                self.assertTrue(list(validator.iter_errors({**contract, **fields})))
        self.assertTrue(independent_identity("agent:/root/independent_review", "codex"))
        for reviewer in ("codex", "agent:codex", "agent:co_dex", "human:owner", "agent:../../codex"):
            self.assertFalse(independent_identity(reviewer, "codex"))

    def test_intentional_amendment_schema_is_exact_and_cannot_extend_legacy_lanes(self) -> None:
        schema = json.loads((REPO / "design/ui-change.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        contract: dict[str, Any] = self.contract(
            "intentional-design-change",
            "a" * 64,
            "b" * 40,
            approved_by="human:repository-owner",
            previous="RO-UI-ACADEMIC-MINIMAL-1.7",
            reference_id="RO-UI-ACADEMIC-MINIMAL-1.8",
            version="1.8",
            task_id="W2.A01.T02",
        )
        contract["schemaVersion"] = "1.2"
        contract["intentionalAmendmentAuthority"] = {
            "amendmentId": "W2.A01",
            "changeRequestId": "ECR-0009",
            "controlTaskId": "W2.A01.T01",
            "referenceApprovalPath": "planning/reference-approvals/RO-UI-ACADEMIC-MINIMAL-1.8.json",
        }
        self.assertEqual([], list(validator.iter_errors(contract)))
        for field, altered in (
            ("schemaVersion", "1.0"),
            ("schemaVersion", "1.1"),
            ("taskId", "W2.A01.T01"),
            ("taskId", "CAP-05.S01.T01"),
            ("changeKind", "approved-reference-implementation"),
        ):
            with self.subTest(field=field, altered=altered):
                self.assertTrue(list(validator.iter_errors({**contract, field: altered})))
        for field, altered in (
            ("referenceId", "RO-UI-ACADEMIC-MINIMAL-1.7"),
            ("version", "1.7"),
            ("previousReferenceId", "RO-UI-ACADEMIC-MINIMAL-1.6"),
        ):
            with self.subTest(reference_field=field):
                invalid = {**contract, "reference": {**contract["reference"], field: altered}}
                self.assertTrue(list(validator.iter_errors(invalid)))
        authority = contract["intentionalAmendmentAuthority"]
        for key in authority:
            with self.subTest(missing=key):
                invalid = {
                    **contract,
                    "intentionalAmendmentAuthority": {k: v for k, v in authority.items() if k != key},
                }
                self.assertTrue(list(validator.iter_errors(invalid)))
            with self.subTest(substituted=key):
                invalid = {**contract, "intentionalAmendmentAuthority": {**authority, key: "other"}}
                self.assertTrue(list(validator.iter_errors(invalid)))
        for extra in ("restoration", "restorationClassification", "amendmentAuthority"):
            with self.subTest(extra=extra):
                self.assertTrue(list(validator.iter_errors({**contract, extra: {}})))

    def test_adopted_continuation_schema_is_closed_and_exact_to_original_t01(self) -> None:
        schema = json.loads((REPO / "design/ui-change.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        contract: dict[str, Any] = self.contract(
            "defect-restoration",
            "a" * 64,
            "b" * 40,
            previous="RO-UI-ACADEMIC-MINIMAL-1.7",
            reference_id="RO-UI-ACADEMIC-MINIMAL-1.8",
            version="1.8",
            task_id="CAP-05.S01.T01",
        )
        contract["schemaVersion"] = "1.3"
        authority: dict[str, Any] = {
            "amendmentId": "W2.A02",
            "changeRequestId": "ECR-0010",
            "controlTaskId": "W2.A02.T01",
            "inheritedAmendmentId": "W2.A01",
            "inheritedTaskId": "W2.A01.T02",
            "inheritedContractPath": "artifacts/evidence/ui-change/W2.A01.T02.json",
            "adoptionCommit": "c" * 40,
            "reactivationCommit": "d" * 40,
            "inheritedUiFiles": ["apps/desktop/src/app/ImportReviewPane.tsx"],
            "inheritedUiCommits": ["e" * 40],
            "resumedUiFiles": ["apps/desktop/src/app/DocumentAttachmentPane.tsx"],
            "resumedUiCommits": ["f" * 40],
            "classification": {
                "path": "artifacts/evidence/CAP-05.S01.T01.ui-classification-R01.json",
                "sha256": "0" * 64,
                "commit": "1" * 40,
            },
        }
        contract["adoptedContinuationAuthority"] = authority
        self.assertEqual([], list(validator.iter_errors(contract)))
        for field in authority:
            with self.subTest(missing=field):
                invalid = copy.deepcopy(contract)
                del invalid["adoptedContinuationAuthority"][field]
                self.assertTrue(list(validator.iter_errors(invalid)))

        for field, value in (
            ("amendmentId", "W2.A01"),
            ("changeRequestId", "ECR-0009"),
            ("controlTaskId", "W2.A01.T01"),
            ("inheritedAmendmentId", "W2.A02"),
            ("inheritedTaskId", "CAP-05.S01.T01"),
            ("inheritedContractPath", "artifacts/evidence/ui-change/CAP-05.S01.T01.json"),
            ("adoptionCommit", "short"),
            ("reactivationCommit", "short"),
            ("inheritedUiFiles", []),
            ("inheritedUiCommits", []),
            ("resumedUiFiles", []),
            ("resumedUiCommits", []),
            ("classification", {"path": "artifacts/evidence/W2.A02.T01.ui-classification-R01.json"}),
        ):
            with self.subTest(substituted=field):
                invalid = copy.deepcopy(contract)
                invalid["adoptedContinuationAuthority"][field] = value
                self.assertTrue(list(validator.iter_errors(invalid)))
        for field, value in (
            ("schemaVersion", "1.0"),
            ("schemaVersion", "1.1"),
            ("schemaVersion", "1.2"),
            ("taskId", "CAP-05.S01.T02"),
            ("changeKind", "approved-reference-implementation"),
        ):
            with self.subTest(top_level=field, value=value):
                self.assertTrue(list(validator.iter_errors({**contract, field: value})))
        for field, value in (
            ("referenceId", "RO-UI-ACADEMIC-MINIMAL-1.7"),
            ("version", "1.7"),
            ("previousReferenceId", "RO-UI-ACADEMIC-MINIMAL-1.6"),
        ):
            with self.subTest(reference=field):
                invalid = copy.deepcopy(contract)
                invalid["reference"][field] = value
                self.assertTrue(list(validator.iter_errors(invalid)))
        for extra in ("restorationClassification", "amendmentAuthority", "intentionalAmendmentAuthority"):
            with self.subTest(extra=extra):
                self.assertTrue(list(validator.iter_errors({**contract, extra: {}})))
        for field in ("classification", "adoptedContinuationAuthority"):
            with self.subTest(extra_nested=field):
                invalid = copy.deepcopy(contract)
                if field == "classification":
                    invalid["adoptedContinuationAuthority"][field]["extra"] = True
                else:
                    invalid[field]["extra"] = True
                self.assertTrue(list(validator.iter_errors(invalid)))

    def test_reference_activation_v14_schema_requires_both_closed_authorities(self) -> None:
        schema = json.loads((REPO / "design/ui-change.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        contract: dict[str, Any] = self.contract(
            "defect-restoration",
            "a" * 64,
            "b" * 40,
            previous="RO-UI-ACADEMIC-MINIMAL-1.7",
            reference_id="RO-UI-ACADEMIC-MINIMAL-1.8",
            version="1.8",
            task_id="CAP-05.S01.T01",
        )
        contract["schemaVersion"] = "1.4"
        contract["adoptedContinuationAuthority"] = {
            "amendmentId": "W2.A02",
            "changeRequestId": "ECR-0010",
            "controlTaskId": "W2.A02.T01",
            "inheritedAmendmentId": "W2.A01",
            "inheritedTaskId": "W2.A01.T02",
            "inheritedContractPath": "artifacts/evidence/ui-change/W2.A01.T02.json",
            "adoptionCommit": "c" * 40,
            "reactivationCommit": "d" * 40,
            "inheritedUiFiles": ["apps/desktop/src/app/ImportReviewPane.tsx"],
            "inheritedUiCommits": ["e" * 40],
            "resumedUiFiles": ["apps/desktop/src/app/DocumentAttachmentPane.tsx"],
            "resumedUiCommits": ["f" * 40],
            "classification": {
                "path": "artifacts/evidence/CAP-05.S01.T01.ui-classification-R01.json",
                "sha256": "0" * 64,
                "commit": "1" * 40,
            },
        }
        activation = {
            "amendmentId": "W2.A03",
            "changeRequestId": "ECR-0011",
            "controlTaskId": "W2.A03.T01",
            "consumerTaskId": "W2.A03.T02",
            "referenceApprovalPath": "planning/reference-approvals/RO-UI-ACADEMIC-MINIMAL-1.8.json",
            "witnessPath": "packages/contracts/workflow-profile/presentation-compatibility-1.8.json",
            "publicationCommit": "2" * 40,
            "witnessCommit": "3" * 40,
            "adoptionCommit": "4" * 40,
            "reactivationCommit": "5" * 40,
            "activationUiFiles": ["apps/desktop/src/app/ImportReviewPane.tsx"],
            "activationUiCommits": ["6" * 40],
        }
        contract["referenceActivationAuthority"] = activation
        self.assertEqual([], list(validator.iter_errors(contract)))
        for field in activation:
            with self.subTest(missing=field):
                invalid = copy.deepcopy(contract)
                del invalid["referenceActivationAuthority"][field]
                self.assertTrue(list(validator.iter_errors(invalid)))
        for field, value in (
            ("amendmentId", "W2.A02"),
            ("changeRequestId", "ECR-0010"),
            ("controlTaskId", "W2.A03.T02"),
            ("consumerTaskId", "CAP-05.S01.T01"),
            ("referenceApprovalPath", "planning/reference-approvals/RO-UI-ACADEMIC-MINIMAL-1.7.json"),
            ("witnessPath", "packages/contracts/workflow-profile/presentation-compatibility-1.7.json"),
            ("publicationCommit", "short"),
            ("witnessCommit", "short"),
            ("adoptionCommit", "short"),
            ("reactivationCommit", "short"),
            ("activationUiFiles", []),
            ("activationUiCommits", []),
        ):
            with self.subTest(substituted=field):
                invalid = copy.deepcopy(contract)
                invalid["referenceActivationAuthority"][field] = value
                self.assertTrue(list(validator.iter_errors(invalid)))
        for field, value in (
            ("schemaVersion", "1.0"),
            ("schemaVersion", "1.1"),
            ("schemaVersion", "1.2"),
            ("schemaVersion", "1.3"),
            ("taskId", "CAP-05.S01.T02"),
            ("changeKind", "approved-reference-implementation"),
        ):
            with self.subTest(top_level=field):
                self.assertTrue(list(validator.iter_errors({**contract, field: value})))
        for absent in ("adoptedContinuationAuthority", "referenceActivationAuthority"):
            with self.subTest(absent=absent):
                invalid = copy.deepcopy(contract)
                del invalid[absent]
                self.assertTrue(list(validator.iter_errors(invalid)))
        invalid = copy.deepcopy(contract)
        invalid["referenceActivationAuthority"]["unreviewed"] = True
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_reference_activation_historical_gov26_and_c10_are_exact_reviewed_ranges(self) -> None:
        head = self.git(REPO, "rev-parse", "HEAD")
        backlog = yaml.safe_load((REPO / "planning/backlog.yaml").read_text(encoding="utf-8"))
        admitted = ui_gate.reference_activation_historical_authority(REPO, head, backlog)
        self.assertEqual(
            {
                "planning/governance-migrations/GOV-MAINT-0026.json",
                "quality-scope.json",
            },
            admitted["6e396c5e18fefb255334e1ddeeea02eb4b6bdb2c"],
        )
        self.assertEqual(
            {
                "services/core-api/src/research_observatory_core/plugin_worker.py",
                "tests/connectors/test_plugin_grant_migration.py",
                "tests/connectors/test_plugin_worker_submission.py",
            },
            admitted["3dde91238b0be11847f68845a52b9785048dc8cd"],
        )

    def test_reference_activation_historical_t03_binds_reviewed_protected_source_commits(self) -> None:
        head = self.git(REPO, "rev-parse", "HEAD")
        backlog = yaml.safe_load(ui_gate.blob(REPO, head, "planning/backlog.yaml"))
        quality = "33333d0f990ba6a01b7cec2fab1e9af7b2f7aee9"
        product = "63cd40222c110fbe748137190df15cf14f958b94"
        adr = "9176dce55dcec315dad28c6e314bc7bfdad8652a"
        admitted = ui_gate.reference_activation_historical_t03_authority(REPO, head, backlog)
        self.assertEqual({quality, product, adr}, set(admitted))
        self.assertEqual(ui_gate.commit_paths(REPO, quality), admitted[quality])
        self.assertEqual(ui_gate.commit_paths(REPO, product), admitted[product])
        self.assertEqual(ui_gate.commit_paths(REPO, adr), admitted[adr])

        missing_review = copy.deepcopy(backlog)
        task = ui_gate.backlog_task(missing_review, "CAP-04.S05.T03")
        self.assertIsNotNone(task)
        assert task is not None
        task["review_control"]["attempts"].pop()
        with self.assertRaisesRegex(ValueError, "T03|review|submission|ledger"):
            ui_gate.reference_activation_historical_t03_authority(REPO, head, missing_review)

    def test_reference_activation_actual_a02_adoption_accepts_stable_ancestor_evidence_only(self) -> None:
        head = self.git(REPO, "rev-parse", "HEAD")
        backlog = yaml.safe_load(ui_gate.blob(REPO, head, "planning/backlog.yaml"))
        amendment = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A02")
        packet = json.loads(ui_gate.blob(REPO, head, "planning/enabler-change-requests/ECR-0010.packet.json"))
        wave = next(item for item in backlog["waves"] if item["id"] == "W2")
        checkpoint = taskctl.amendment_adoption_checkpoints(wave, "W2.A02")[0]
        reference = next(item for item in checkpoint["evidence"] if item.get("amendment_id") == "W2.A02")
        evidence, introduction = immutable_record(REPO, head, reference["path"], reference["sha256"], evidence=True)
        self.assertEqual("W2.A02", evidence["amendmentId"])
        self.assertEqual("7730a060ce0e92184c56f7d7f291652c3a35003d", introduction)
        self.assertEqual("db7edd6c6021ed78afd9084b37d2ef48e1fc12cb", reference["commit"])
        self.assertEqual("ADOPTED", amendment["lifecycle"]["status"])
        adoption = ui_gate.adopted_continuation_adoption(REPO, head, backlog, amendment, packet)
        self.assertNotEqual(introduction, adoption)
        self.assertTrue(ui_gate.is_ancestor(REPO, reference["commit"], adoption))

        before_introduction = copy.deepcopy(backlog)
        prior_wave = next(item for item in before_introduction["waves"] if item["id"] == "W2")
        prior_checkpoint = taskctl.amendment_adoption_checkpoints(prior_wave, "W2.A02")[0]
        prior_reference = next(item for item in prior_checkpoint["evidence"] if item.get("amendment_id") == "W2.A02")
        prior_reference["commit"] = "6506c68461144747b0ee9be10853211717aa381d"
        self.assertFalse(ui_gate.is_ancestor(REPO, introduction, prior_reference["commit"]))
        self.assertTrue(taskctl.amendment_adoption_reference_errors(REPO, prior_reference, amendment))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "rewritten-a02-adoption"
            protected_config = Path(temporary) / "fixture-gitconfig"
            protected_config.write_text(f"[safe]\n\tdirectory = {(REPO / '.git').as_posix()}\n", encoding="utf-8")
            clone = subprocess.run(
                ["git", "clone", "--quiet", "--shared", "--no-checkout", str(REPO), str(root)],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "GIT_CONFIG_GLOBAL": str(protected_config)},
            )
            self.assertEqual(0, clone.returncode, clone.stderr)
            self.git(root, "config", "user.name", "UI Gate Test")
            self.git(root, "config", "user.email", "ui-gate@example.invalid")
            self.git(root, "config", "core.autocrlf", "false")
            self.git(root, "switch", "-C", "fixture", head)
            evidence_path = root / reference["path"]
            evidence_path.write_bytes(evidence_path.read_bytes() + b"\n")
            rewritten = self.commit(root, "synthetic adverse rewrite of A02 adoption evidence")
            with self.assertRaisesRegex(ValueError, "hash mismatch|immutable introduction"):
                immutable_record(root, rewritten, reference["path"], reference["sha256"], evidence=True)

    def test_reviewed_activation_inert_history_preserves_actual_net_inventory(self) -> None:
        head = self.git(REPO, "rev-parse", "HEAD")
        frozen = yaml.safe_load(ui_gate.blob(REPO, "771e54a3657cdc5ff308d3a53d7b71eb48bb9214", "planning/backlog.yaml"))
        task = ui_gate.backlog_task(frozen, "W2.A03.T02")
        assert task is not None
        with self.assertRaisesRegex(ValueError, "hidden or overlapping"):
            ui_gate.adopted_continuation_reviewed_task_commits(REPO, head, task)
        projections = ui_gate.reference_activation_inert_projection_map(REPO, head)
        self.assertEqual(6, len(projections))
        self.assertEqual({"planning/review-site/waves/W2.html"}, set().union(*projections.values()))
        ranges, commits = ui_gate.adopted_continuation_reviewed_task_commits(
            REPO, head, task, inert_outputs=projections
        )
        self.assertEqual("ca8b1448e094b637bbd06c3129b69a78df792619", ranges[0]["base"])
        self.assertEqual("06a69348c5de5c60cccecde400ab2271200ec50d", ranges[-1]["candidate"])
        self.assertEqual(118, len(ranges[0]["paths"]))
        self.assertNotIn("planning/review-site/waves/W2.html", ranges[0]["paths"])
        self.assertTrue(set(projections).issubset(commits))
        self.assertEqual(39, len(commits))
        forged = copy.deepcopy(projections)
        forged[next(iter(forged))].add("tools/ui_change_gate.py")
        with self.assertRaisesRegex(ValueError, "inert projection"):
            ui_gate.adopted_continuation_reviewed_task_commits(REPO, head, task, inert_outputs=forged)

    def activation_repair_clone(self, temporary: str, *, source: Path = REPO) -> Path:
        root = Path(temporary) / "activation-repair-fixture"
        protected_config = Path(temporary) / "fixture-gitconfig"
        protected_config.write_text(f"[safe]\n\tdirectory = {(source / '.git').as_posix()}\n", encoding="utf-8")
        result = subprocess.run(
            ["git", "clone", "--quiet", "--shared", "--no-checkout", str(source), str(root)],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "GIT_CONFIG_GLOBAL": str(protected_config)},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.git(root, "config", "user.name", "UI Gate Test")
        self.git(root, "config", "user.email", "ui-gate@example.invalid")
        self.git(root, "config", "core.autocrlf", "false")
        self.git(root, "switch", "-C", "codex/w2-implementation", self.git(source, "rev-parse", "HEAD"))
        self.assertEqual("", self.git(root, "status", "--porcelain"), "Disposable checkout must preserve all blobs")
        return root

    def test_reviewed_activation_inert_map_rejects_rewritten_bindings_and_predecessors(self) -> None:
        for attack in ("missing-preflight", "forged-preflight", "changed-a03", "changed-a04", "missing-b00-review"):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                root = self.activation_repair_clone(temporary)
                if attack in {"missing-preflight", "forged-preflight"}:
                    target = root / "planning/enabler-change-requests/ECR-0013.preflight-01.json"
                    if attack == "missing-preflight":
                        target.unlink()
                    else:
                        value = json.loads(target.read_bytes())
                        value["historicalProjectionRows"][0]["afterBlobSha256"] = "0" * 64
                        self.write_json(target, value)
                else:
                    backlog = yaml.safe_load((root / "planning/backlog.yaml").read_bytes())
                    identity = (
                        "W2.A03" if attack == "changed-a03" else "W2.A04" if attack == "changed-a04" else "W2.A05"
                    )
                    record = next(a for a in backlog["wave_amendments"] if a["id"] == identity)
                    if attack == "missing-b00-review":
                        record["bootstrap"]["review"] = None
                    else:
                        record["tasks"][0]["implementation_notes"] += "synthetic unauthenticated rewrite"
                    self.write_yaml(root / "planning/backlog.yaml", backlog)
                head = self.commit(root, f"synthetic {attack}")
                with self.assertRaises(ValueError):
                    ui_gate.reference_activation_inert_projection_map(root, head)

    def test_reviewed_activation_inert_map_does_not_hide_new_source_or_same_name_output(self) -> None:
        for path in (
            "workers/document/inert_projection_attack.py",
            "tools/ui_change_gate.py",
            "planning/review-site/waves/W2.html",
        ):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                root = self.activation_repair_clone(temporary)
                backlog = yaml.safe_load((root / "planning/backlog.yaml").read_bytes())
                task = ui_gate.backlog_task(backlog, "W2.A05.T01")
                assert task is not None
                target = root / path
                before = target.read_bytes() if target.exists() else None
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((before or b"") + b"\n# Synthetic unreviewed intermediate source.\n")
                self.commit(root, "synthetic hidden add/revert first half")
                if before is None:
                    target.unlink()
                else:
                    target.write_bytes(before)
                document = root / "docs/automation/design-first-ui-changes.md"
                document.write_bytes(document.read_bytes() + b"\nSynthetic task fixture only.\n")
                candidate = self.commit(root, "synthetic net candidate retaining hidden history")
                head = self.approve_activation_fixture_task(root, backlog, task, candidate)
                projections = ui_gate.reference_activation_inert_projection_map(root, head)
                with self.assertRaisesRegex(ValueError, "hidden or overlapping"):
                    ui_gate.adopted_continuation_reviewed_task_commits(root, head, task, inert_outputs=projections)

    def test_reviewed_activation_preceding_sources_preserve_adverse_history_and_deny_substitution(self) -> None:
        head = self.git(REPO, "rev-parse", "HEAD")
        admitted = ui_gate.reference_activation_repair_preceding_sources(REPO, head)
        self.assertEqual(5, len(admitted))
        self.assertIn("57f5c3f264611f59cd2778ff13b5082b2726e24b", admitted)
        for path in (
            "tools/governance_kernel.py",
            "tools/taskctl.py",
            "planning/governance-migrations/GOV-MAINT-0027.review-R01.json",
            "planning/governance-migrations/GOV-MAINT-0027.review-R02.json",
            "planning/enabler-change-requests/ECR-0013.maintenance-binding.json",
            "planning/wave-amendment-approvals/W2.A05.B00.addendum-01.json",
        ):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                root = self.activation_repair_clone(temporary)
                target = root / path
                target.write_bytes(target.read_bytes() + b"\n")
                attack = self.commit(root, "synthetic preceding authority byte substitution")
                with self.assertRaises(ValueError):
                    ui_gate.reference_activation_repair_preceding_sources(root, attack)

    def test_reviewed_activation_preceding_sources_deny_modes_omissions_and_extra_history(self) -> None:
        attacks = (
            "executable-import",
            "source-add-revert",
            "omitted-binding-row",
            "extra-binding-row",
            "missing-r02",
            "forged-r02",
            "edited-adverse-check",
            "changed-approved-header",
        )
        for attack in attacks:
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                root = self.activation_repair_clone(temporary)
                source = root / "tools/governance_kernel.py"
                if attack == "executable-import":
                    self.git(root, "update-index", "--chmod=+x", "tools/governance_kernel.py")
                elif attack == "source-add-revert":
                    original = source.read_bytes()
                    source.write_bytes(original + b"\n# Synthetic unapproved imported authority.\n")
                    self.commit(root, "synthetic imported-source add/revert first half")
                    source.write_bytes(original)
                elif attack in {"omitted-binding-row", "extra-binding-row"}:
                    target = root / "planning/enabler-change-requests/ECR-0013.maintenance-binding.json"
                    binding = json.loads(target.read_bytes())
                    if attack == "omitted-binding-row":
                        binding["history"].pop(1)
                    else:
                        binding["history"].append(copy.deepcopy(binding["history"][-1]))
                    self.write_json(target, binding)
                elif attack == "changed-approved-header":
                    target = root / "planning/backlog.yaml"
                    document = yaml.safe_load(target.read_bytes())
                    child = next(a for a in document["wave_amendments"] if a["id"] == "W2.A05")
                    child["contributions"][0]["capability_id"] = "CAP-04"
                    self.write_yaml(target, document)
                else:
                    relative = (
                        "planning/governance-migrations/GOV-MAINT-0027.checks-01.json"
                        if attack == "edited-adverse-check"
                        else "planning/governance-migrations/GOV-MAINT-0027.review-R02.json"
                    )
                    target = root / relative
                    if attack == "missing-r02":
                        target.unlink()
                    else:
                        value = json.loads(target.read_bytes())
                        value["disposition"] = "synthetic-forged-approval"
                        self.write_json(target, value)
                if attack == "executable-import":
                    self.git(root, "commit", "-m", "synthetic executable imported authority")
                    head = self.git(root, "rev-parse", "HEAD")
                else:
                    head = self.commit(root, f"synthetic preceding-history {attack}")
                with self.assertRaises(ValueError):
                    ui_gate.reference_activation_repair_preceding_sources(root, head)

    def test_reviewed_activation_repair_rejects_changed_task_and_slice_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as prefix_directory:
            prefix, _head = self.activation_repair_future_fixture(prefix_directory)
            for attack in (
                "missing-task-review",
                "forged-task-review",
                "malformed-slice-binding",
                "replayed-slice-review",
            ):
                with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                    root = self.activation_repair_clone(temporary, source=prefix)
                    relative = (
                        "artifacts/evidence/W2.A05.T01.review-R01.json"
                        if "task-review" in attack
                        else "artifacts/evidence/W2.A05.S01.review-01.json"
                    )
                    target = root / relative
                    if attack == "missing-task-review":
                        target.unlink()
                    else:
                        value = json.loads(target.read_bytes())
                        if attack == "forged-task-review":
                            value["candidate_commit"] = "0" * 40
                        elif attack == "malformed-slice-binding":
                            value["taskBindings"][0]["candidateCommit"] = {"unhashable": True}
                        else:
                            value["amendmentId"] = "W2.A04"
                        self.write_json(target, value)
                    head = self.commit(root, f"synthetic {attack}")
                    with self.assertRaises(ValueError):
                        ui_gate.reference_activation_repair_authority(root, head)

    def test_reviewed_activation_repair_full_original_base_requires_current_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, head, contract, manifest, _scope = self.classified_adopted_continuation_fixture(
                temporary, activation=True, repair=True
            )
            self.assertEqual("6506c68461144747b0ee9be10853211717aa381d", base)
            with (
                patch("product_style_check.read_capture_bundle", return_value=manifest),
                patch("desktop_app_check.qualification_capture_contract", return_value=[]),
                patch("desktop_app_check.qualification_report_errors", return_value=[]),
                patch("product_style_check.capture_producer_snapshot", return_value=manifest["producer"]),
            ):
                report = validate(root, base, head)
                self.assertTrue(report["ok"], report["errors"])
                self.assertFalse(validate(root, "771e54a3657cdc5ff308d3a53d7b71eb48bb9214", head)["ok"])
                reference = contract["adoptedContinuationAuthority"]["classification"]
                target = root / reference["path"]
                value = json.loads(target.read_bytes())
                value["authorityPreserved"] = False
                self.write_json(target, value)
                changed = self.commit(root, "synthetic current classification substitution")
                # The real full-root positive above supplies the authenticated
                # scope. Only this Git classification blob changed; challenge
                # the unchanged classification boundary without rescanning it.
                policy = json.loads((root / "ui-change-policy.json").read_bytes())
                with self.assertRaises(ValueError) as denial:
                    ui_gate.adopted_continuation_classification_errors(
                        root, base, changed, contract, report["rangeAuthority"], policy
                    )
                self.assertEqual(f"authority record hash mismatch: {reference['path']}", str(denial.exception))

    def activation_repair_future_fixture(
        self, temporary: str, *, security_attack: str | None = None
    ) -> tuple[Path, str]:
        """Actual prefix plus explicitly synthetic future task/adoption/return records."""
        root = self.activation_repair_clone(temporary)
        backlog = yaml.safe_load((root / "planning/backlog.yaml").read_bytes())
        child = next(a for a in backlog["wave_amendments"] if a["id"] == "W2.A05")
        t01, t02 = child["tasks"]
        self.assertEqual("IN_PROGRESS", t01["status"])
        child["campaign"]["lease"]["expires_at"] = "2099-01-01T00:00:00Z"
        t01["lease"]["expires_at"] = "2099-01-01T00:00:00Z"
        for relative in ui_gate.REFERENCE_ACTIVATION_REPAIR_SOURCE[0]:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPO / relative).read_bytes())
        self.write_yaml(root / "planning/backlog.yaml", backlog)
        control_candidate = self.commit(root, "synthetic future T01 qualification lease")
        t02["status"] = "READY"
        self.approve_activation_fixture_task(root, backlog, t01, control_candidate)
        consumer_base = self.git(root, "rev-parse", "HEAD")
        t02.update(
            status="IN_PROGRESS",
            owner=t01["owner"],
            branch=t01["branch"],
            worktree=".",
            base_sha=consumer_base,
            started_at="2026-10-05T03:45:00Z",
            updated_at="2026-10-05T03:45:00Z",
            lease={
                "claimed_by": t01["owner"],
                "claimed_at": "2026-10-05T03:21:19Z",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )
        self.write_yaml(root / "planning/backlog.yaml", backlog)
        self.commit(root, "synthetic separate T02 claim after independent T01 approval")
        for path in (
            "tools/ui_conformance.py",
            "tests/desktop/test_ui_conformance.py",
            "docs/automation/ui-conformance-verification.md",
        ):
            target = root / path
            target.write_bytes(
                target.read_bytes() + b"\n# Synthetic future checker source touch; no accessibility qualification.\n"
            )
        companion = root / "docs/adr/ADR-0041-authenticate-reviewed-activation-control-repairs.md"
        companion.write_bytes(
            companion.read_bytes()
            + b"\n## T02 implementation and verification\n\nSynthetic bounded body append only.\n"
        )
        consumer_candidate = self.commit(root, "synthetic future exact T02 source and ADR body append")
        self.approve_activation_fixture_task(root, backlog, t02, consumer_candidate)
        adoption = self.complete_activation_fixture_amendment(
            root,
            backlog,
            child,
            {t01["id"]: control_candidate, t02["id"]: consumer_candidate},
            security_attack=security_attack,
        )
        parent = next(a for a in backlog["wave_amendments"] if a["id"] == "W2.A03")
        self.assertEqual(["DONE", "DONE"], [t["status"] for t in parent["tasks"]])
        parent["lifecycle"]["status"] = "ACTIVE"
        parent["lifecycle"]["history"].append(
            {
                "id": f"E{len(parent['lifecycle']['history']) + 1:02d}",
                "status": "ACTIVE",
                "actor": t01["owner"],
                "at": "2026-10-05T03:46:00Z",
                "rationale": "Synthetic separate activation; no original task reopen.",
            }
        )
        parent["campaign"].update(
            status="ACTIVE",
            owner=t01["owner"],
            branch=t01["branch"],
            worktree=".",
            base_sha=adoption,
            profile="LOC",
            platform="windows-x64",
            pause_reason=None,
            lease={
                "claimed_by": t01["owner"],
                "claimed_at": "2026-10-05T03:21:19Z",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )
        backlog["control_plane"]["active_amendment"] = "W2.A03"
        self.write_yaml(root / "planning/backlog.yaml", backlog)
        return root, self.commit(root, "synthetic separate A03 activation retaining both DONE tasks")

    def test_reviewed_activation_repair_denies_frozen_parent_history_rewrite_and_restoration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, activation = self.activation_repair_future_fixture(temporary)
            target = root / "planning/backlog.yaml"
            original = target.read_bytes()
            state = yaml.safe_load(original)
            parent = next(a for a in state["wave_amendments"] if a["id"] == "W2.A03")
            event = next(e for e in parent["lifecycle"]["history"] if e["id"] == "E06")
            event["rationale"] = "Synthetic unauthorized replacement of preserved adverse history."
            self.write_yaml(target, state)
            self.commit(root, "synthetic frozen A03 pause-history rewrite after lawful activation")
            target.write_bytes(original)
            restored = self.commit(root, "synthetic frozen A03 pause-history restoration")
            self.assertEqual(
                ui_gate.blob(root, activation, "planning/backlog.yaml"),
                ui_gate.blob(root, restored, "planning/backlog.yaml"),
            )
            with self.assertRaisesRegex(ValueError, "history"):
                ui_gate.reference_activation_repair_authority(root, restored)

    def test_reviewed_activation_repair_future_return_keeps_original_tasks_and_source_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, head = self.activation_repair_future_fixture(temporary)
            authority = ui_gate.reference_activation_repair_authority(root, head)
            backlog = yaml.safe_load(ui_gate.blob(root, head, "planning/backlog.yaml"))
            parent = next(a for a in backlog["wave_amendments"] if a["id"] == "W2.A03")
            admitted, consumers, _witness = ui_gate.reference_activation_reviewed_tasks(root, head, parent)
            self.assertTrue(set(authority["commits"]).issubset(admitted))
            self.assertFalse(set(authority["commits"]) & consumers)
            self.assertEqual(["DONE", "DONE"], [t["status"] for t in parent["tasks"]])
            self.assertEqual("ca8b1448e094b637bbd06c3129b69a78df792619", parent["tasks"][1]["base_sha"])
            self.assertEqual("ADR-0041", authority["index"]["records"][-1]["id"])

    def test_reviewed_activation_repair_denies_incomplete_actual_delivery(self) -> None:
        with self.assertRaises(ValueError):
            ui_gate.reference_activation_repair_authority(REPO, self.git(REPO, "rev-parse", "HEAD"))

    def test_reviewed_activation_repair_future_security_review_is_required_before_adoption(self) -> None:
        for attack in (
            "missing-security-review",
            "late-security-review",
            "self-security-review",
            "forged-security-review",
        ):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                root, head = self.activation_repair_future_fixture(temporary, security_attack=attack)
                with self.assertRaises(ValueError):
                    ui_gate.reference_activation_repair_authority(root, head)

    def test_reviewed_activation_repair_denies_reopened_original_task_and_registry_rewrite(self) -> None:
        for attack in ("reopen-original", "registry-rewrite", "alter-adopted-a04", "foreign-return"):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                root, head = self.activation_repair_future_fixture(temporary)
                if attack == "registry-rewrite":
                    path = root / "docs/adr/index.json"
                    registry = json.loads(path.read_bytes())
                    registry["records"][0]["title"] += " synthetic rewrite"
                    self.write_json(path, registry)
                else:
                    backlog = yaml.safe_load((root / "planning/backlog.yaml").read_bytes())
                    parent = next(a for a in backlog["wave_amendments"] if a["id"] == "W2.A03")
                    if attack == "reopen-original":
                        parent["tasks"][1]["status"] = "IN_PROGRESS"
                    elif attack == "foreign-return":
                        parent["campaign"]["owner"] = "foreign-owner"
                    else:
                        sibling = next(a for a in backlog["wave_amendments"] if a["id"] == "W2.A04")
                        sibling["completion"]["notes"] += " synthetic rewrite"
                    self.write_yaml(root / "planning/backlog.yaml", backlog)
                head = self.commit(root, f"synthetic {attack}")
                with self.assertRaises(ValueError):
                    ui_gate.reference_activation_repair_authority(root, head)

    def test_reference_activation_reviewed_task_cannot_launder_site_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, adoption, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(
                temporary, inject_unapproved_site_asset=True
            )
            amendment = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A03")
            with self.assertRaisesRegex(ValueError, "outside its ECR-0011 packet envelope"):
                ui_gate.reference_activation_reviewed_tasks(root, adoption, amendment)

    def test_reference_activation_correction_partitions_combined_history_and_retained_adr(self) -> None:
        # The prefix is real approved/claimed Git; later reviews and adoption are
        # disposable test-only states, not an actual A04 or desktop qualification.
        with tempfile.TemporaryDirectory() as temporary:
            root, adoption, backlog, _control, consumer_candidate, _activation = self.reference_activation_git_fixture(
                temporary, correction=True
            )
            parent = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A03")
            child = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A04")
            admitted, consumer_commits, _witness = ui_gate.reference_activation_reviewed_tasks(root, adoption, parent)
            correction_candidate = child["tasks"][0]["review_control"]["attempts"][-1]["submission"]["candidate_commit"]
            self.assertIn(correction_candidate, admitted)
            self.assertNotIn(correction_candidate, consumer_commits)
            self.assertEqual("ca8b1448e094b637bbd06c3129b69a78df792619", parent["tasks"][1]["base_sha"])
            adr = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools/adr_check.py"),
                    "--repo",
                    str(root),
                    "--base",
                    parent["tasks"][1]["base_sha"],
                    "--head",
                    consumer_candidate,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, adr.returncode, adr.stdout + adr.stderr)

    def test_reference_activation_correction_exact_predecessor_and_claim_denials(self) -> None:
        head = self.git(REPO, "rev-parse", "HEAD")
        document = yaml.load(
            ui_gate.blob(REPO, "53d510464e2f9a2ab64bc9e78d09ae7b3996bba7", "planning/backlog.yaml"),
            Loader=yaml.CSafeLoader,
        )
        parent = ui_gate.amendment_record(document, "W2.A03")
        binding = ui_gate.amendment_record(document, "W2.A04")["correction"]
        self.assertEqual(parent, ui_gate.reference_activation_correction_predecessor(REPO, head, binding, parent))
        for field, value in (
            ("effectiveStateCommit", parent["tasks"][1]["base_sha"]),
            ("recordSha256", "0" * 64),
            ("packetCommit", head),
        ):
            with self.subTest(binding=field):
                changed = copy.deepcopy(binding)
                changed[field] = value
                with self.assertRaises(ValueError):
                    ui_gate.reference_activation_correction_predecessor(REPO, head, changed, parent)
        for task_index, field, value in (
            (0, "implementation_notes", "Altered completed task"),
            (1, "base_sha", head),
            (1, "owner", "foreign-agent"),
            (1, "packet_task_sha256", "0" * 64),
            (1, "worktree", "other"),
        ):
            with self.subTest(task=task_index, field=field):
                changed = copy.deepcopy(parent)
                changed["tasks"][task_index][field] = value
                with self.assertRaises(ValueError):
                    ui_gate.reference_activation_correction_predecessor(REPO, head, binding, changed)
        task = ui_gate.backlog_task(document, "W2.A04.T01")
        assert task is not None
        args = (
            "W2.A04.T01",
            task["base_sha"],
            "850cf16281779c09691e566ac453547338eb16a3",
            task["owner"],
            task["branch"],
        )
        observed = int(self.git(REPO, "show", "-s", "--format=%ct", "53d510464e2f9a2ab64bc9e78d09ae7b3996bba7"))
        self.assertTrue(ui_gate.reference_activation_correction_active(document, *args, observed_at=observed))
        for target, field, value in (
            ("task", "status", "READY"),
            ("task", "base_sha", head),
            ("task", "branch", "codex/foreign"),
            ("task", "worktree", "elsewhere"),
            ("campaign", "owner", "foreign-agent"),
            ("campaign", "base_sha", head),
        ):
            with self.subTest(target=target, field=field):
                changed = copy.deepcopy(document)
                record = (
                    ui_gate.backlog_task(changed, "W2.A04.T01")
                    if target == "task"
                    else ui_gate.amendment_record(changed, "W2.A04")["campaign"]
                )
                assert record is not None
                record[field] = value
                self.assertFalse(ui_gate.reference_activation_correction_active(changed, *args, observed_at=observed))
        for target in ("task", "campaign"):
            with self.subTest(expired=target):
                changed = copy.deepcopy(document)
                record = (
                    ui_gate.backlog_task(changed, "W2.A04.T01")
                    if target == "task"
                    else ui_gate.amendment_record(changed, "W2.A04")["campaign"]
                )
                assert record is not None
                record["lease"]["expires_at"] = "2020-01-01T00:00:00Z"
                self.assertFalse(ui_gate.reference_activation_correction_active(changed, *args, observed_at=observed))

    def test_reference_activation_correction_denies_hidden_mixed_and_premature_source(self) -> None:
        expected = {
            "hidden-source": "hidden or overlapping",
            "mixed-consumer": "five-path envelope",
            "premature-consumer": "preceded reopen",
        }
        for attack, message in expected.items():
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                root, adoption, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(
                    temporary, correction=True, correction_attack=attack
                )
                parent = ui_gate.amendment_record(backlog, "W2.A03")
                with self.assertRaisesRegex(ValueError, message):
                    ui_gate.reference_activation_reviewed_tasks(root, adoption, parent)

    def test_reference_activation_correction_denies_registry_ordinary_and_foreign_activation(self) -> None:
        expected = {
            "extra-adr-index": "one jointly introduced appended entry",
            "nonregular-source": "executable or redirected",
            "changed-ordinary": "ordinary records or checkpoint history",
            "missing-return": "did not return the exact paused predecessor",
            "foreign-activation": "premature or foreign A03 activation",
        }
        for attack, message in expected.items():
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                root, adoption, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(
                    temporary, correction=True, correction_attack=attack
                )
                parent = ui_gate.amendment_record(backlog, "W2.A03")
                with self.assertRaisesRegex(ValueError, message):
                    ui_gate.reference_activation_reviewed_tasks(root, adoption, parent)

    def test_reference_activation_correction_requires_slice_and_clean_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, adoption, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(
                temporary, correction=True
            )
            parent = ui_gate.amendment_record(backlog, "W2.A03")
            source = root / "docs/adr/ADR-0040-document-protected-desktop-activation-correction.md"
            frozen = source.read_bytes()
            source.write_bytes(frozen + b"\nUnreviewed working source.\n")
            with self.assertRaisesRegex(ValueError, "dirty or redirected"):
                ui_gate.reference_activation_reviewed_tasks(root, adoption, parent)
            source.write_bytes(frozen)
            review_path = root / "artifacts/evidence/W2.A04.S01.review-01.json"
            record = json.loads(review_path.read_bytes())
            record["taskBindings"][0]["candidateCommit"] = parent["tasks"][1]["base_sha"]
            self.write_json(review_path, record)
            attack = self.commit(root, "test-only replaced S01 independent review")
            with self.assertRaisesRegex(ValueError, "immutable introduction"):
                ui_gate.reference_activation_reviewed_tasks(root, attack, parent)

    def test_reference_activation_correction_preserves_adopted_record_through_consumer_delivery(self) -> None:
        for attack in ("adopted-correction-tamper", "adopted-correction-after-consumer"):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                root, adoption, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(
                    temporary, correction=True, correction_attack=attack
                )
                parent = ui_gate.amendment_record(backlog, "W2.A03")
                with self.assertRaisesRegex(ValueError, "changed adopted correction history"):
                    ui_gate.reference_activation_reviewed_tasks(root, adoption, parent)

    def test_reference_activation_correction_authenticates_append_only_remediation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, head, backlog, _control, consumer, _activation = self.reference_activation_git_fixture(
                temporary, correction=True, correction_remediation=True
            )
            child = ui_gate.amendment_record(backlog, "W2.A04")
            self.assertEqual("R02", child["tasks"][0]["review_control"]["attempts"][-1]["submission"]["id"])
            self.assertEqual("R02", child["completion"]["exit_review_control"]["attempts"][-1]["submission"]["id"])
            ui_gate.reference_activation_reviewed_tasks(root, head, ui_gate.amendment_record(backlog, "W2.A03"))
            parent = ui_gate.amendment_record(backlog, "W2.A03")
            adr = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools/adr_check.py"),
                    "--repo",
                    str(root),
                    "--base",
                    parent["tasks"][1]["base_sha"],
                    "--head",
                    consumer,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, adr.returncode, adr.stdout + adr.stderr)
            for substitution in ("foreign-path", "forged-digest"):
                with self.subTest(substitution=substitution):
                    forged = copy.deepcopy(child)
                    reference = forged["tasks"][0]["review_control"]["attempts"][-1]["ledger"]
                    if substitution == "foreign-path":
                        reference["path"] = "artifacts/evidence/W2.A03.T02.review-R02.json"
                    else:
                        reference["sha256"] = "0" * 64
                    with self.assertRaises(ValueError):
                        ui_gate.correction_submission_ranges(root, head, forged)

    def test_reference_activation_correction_rejects_unbound_remediation_outputs(self) -> None:
        for attack, message in (
            ("unbound-task-evidence", "exact five-path envelope"),
            ("unbound-exit-evidence", "outside its ECR-0011 packet envelope"),
        ):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                root, head, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(
                    temporary, correction=True, correction_attack=attack
                )
                with self.assertRaisesRegex(ValueError, message):
                    ui_gate.reference_activation_reviewed_tasks(root, head, ui_gate.amendment_record(backlog, "W2.A03"))

    def test_reference_activation_correction_replays_slice_findings_and_canonical_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, head, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(
                temporary, correction=True, correction_remediation=True
            )
            task = ui_gate.amendment_record(backlog, "W2.A04")["tasks"][0]
            final = json.loads((root / "artifacts/evidence/W2.A04.S01.review-02.json").read_bytes())
            for attack, message in (
                ("unknown-closure", "evidenced open finding"),
                ("reused-finding", "missing or reused"),
                ("malformed-binding", "integrated independent"),
                ("missing-round", "contiguous canonical"),
                ("malformed-round", "contiguous canonical"),
            ):
                with self.subTest(attack=attack):
                    # Only this disposable clone changes checkout; the shared
                    # campaign and its verification inputs remain fixed.
                    self.git(root, "checkout", "--quiet", "--detach", head)
                    record = copy.deepcopy(final)
                    record["closures"] = []
                    relative = "artifacts/evidence/W2.A04.S01.review-03.json"
                    if attack == "unknown-closure":
                        record["closures"] = [
                            {"finding_id": "SYN-UNKNOWN", "disposition": "fixed", "evidence": "forged"}
                        ]
                    elif attack == "reused-finding":
                        record["findings"] = [self.activation_fixture_finding("SYN-S01-F01")]
                    elif attack == "malformed-binding":
                        record["taskBindings"] = [None]
                    elif attack == "missing-round":
                        relative = "artifacts/evidence/W2.A04.S01.review-04.json"
                    else:
                        relative = "artifacts/evidence/W2.A04.S01.review-03-extra.json"
                    self.write_json(root / relative, record)
                    attacked = self.commit(root, "test-only malformed appended contribution review")
                    with self.assertRaisesRegex(ValueError, message):
                        ui_gate.reference_activation_correction_slice_history(
                            root, attacked, task, task["owner"], attacked
                        )

    def test_reference_activation_correction_requires_separate_checkpoint_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, head, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(
                temporary, correction=True
            )
            ui_gate.reference_activation_reviewed_tasks(root, head, ui_gate.amendment_record(backlog, "W2.A03"))

    def test_reference_activation_correction_denies_missing_forged_self_and_late_checkpoint_review(self) -> None:
        for attack in (
            "missing-security-review",
            "forged-security-review",
            "self-security-review",
            "late-security-review",
        ):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                root, head, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(
                    temporary, correction=True, correction_attack=attack
                )
                with self.assertRaisesRegex(ValueError, "checkpoint review"):
                    ui_gate.reference_activation_reviewed_tasks(root, head, ui_gate.amendment_record(backlog, "W2.A03"))

    def test_reference_activation_corrected_v14_authenticates_full_original_base(self) -> None:
        # Real historical prefix plus synthetic future reviews and capture mocks;
        # this proves the control route, not actual desktop/native qualification.
        with tempfile.TemporaryDirectory() as temporary:
            root, base, head, _contract, manifest, _scope = self.classified_adopted_continuation_fixture(
                temporary, activation=True, correction=True
            )
            with (
                patch("product_style_check.read_capture_bundle", return_value=manifest),
                patch("desktop_app_check.qualification_capture_contract", return_value=[]),
                patch("desktop_app_check.qualification_report_errors", return_value=[]),
                patch("product_style_check.capture_producer_snapshot", return_value=manifest["producer"]),
            ):
                report = validate(root, base, head)
            self.assertTrue(report["ok"], report["errors"])

    def test_reference_activation_v14_authenticates_future_full_base_git(self) -> None:
        # The clone extends real approved history with disposable, synthetic
        # future task reviews/adoption. Its retargeted 1.7 image hashes are not
        # visual qualification for the actual W2.A03.T02 delivery.
        with tempfile.TemporaryDirectory() as temporary:
            root, base, head, contract, manifest, _scope = self.classified_adopted_continuation_fixture(
                temporary, activation=True
            )
            self.assertEqual("6506c68461144747b0ee9be10853211717aa381d", base)
            self.assertEqual(
                "f18a037b96d43392599f7779a668fb1928f74475",
                contract["adoptedContinuationAuthority"]["reactivationCommit"],
            )
            self.assertNotEqual(
                contract["adoptedContinuationAuthority"]["reactivationCommit"],
                contract["referenceActivationAuthority"]["reactivationCommit"],
            )
            with (
                patch("product_style_check.read_capture_bundle", return_value=manifest),
                patch("desktop_app_check.qualification_capture_contract", return_value=[]),
                patch("desktop_app_check.qualification_report_errors", return_value=[]),
                patch("product_style_check.capture_producer_snapshot", return_value=manifest["producer"]),
            ):
                report = validate(root, base, head)
            self.assertTrue(report["ok"], report["errors"])
            self.assertEqual(
                sorted(ui_gate.REFERENCE_ACTIVATION_CONSUMER_FILES),
                contract["referenceActivationAuthority"]["activationUiFiles"],
            )

    def test_reference_activation_v14_rejects_short_base_and_extra_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, head, _contract, manifest, _scope = self.classified_adopted_continuation_fixture(
                temporary, activation=True
            )
            with (
                patch("product_style_check.read_capture_bundle", return_value=manifest),
                patch("desktop_app_check.qualification_capture_contract", return_value=[]),
                patch("desktop_app_check.qualification_report_errors", return_value=[]),
                patch("product_style_check.capture_producer_snapshot", return_value=manifest["producer"]),
            ):
                self.assertFalse(validate(root, "9824e2baad59705bd985a33624fc3e27837e7bc1", head)["ok"])
                self.write_json(root / "artifacts/evidence/ui-change/EXTRA.json", {"schemaVersion": "1.4"})
                extra_head = self.commit(root, "synthetic unapproved third UI contract")
                result = validate(root, base, extra_head)
            self.assertFalse(result["ok"])
            self.assertTrue(any("two-contract" in error or "exactly" in error for error in result["errors"]), result)

    def test_reference_activation_rejects_unreviewed_source_between_adoption_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, adoption, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(temporary)
            path = root / "docs/automation/ui-conformance-verification.md"
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write("\nSynthetic unreviewed post-adoption control-source edit.\n")
            attack = self.commit(root, "unreviewed A03 source after adoption before ordinary resume")
            reactivation = self.reactivate_adopted_continuation(root, attack, backlog, activation=True)
            amendment = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A03")
            admitted, _consumer_commits, _witness = ui_gate.reference_activation_reviewed_tasks(
                root, reactivation, amendment
            )
            base = "6506c68461144747b0ee9be10853211717aa381d"
            ordered = self.git(root, "rev-list", "--reverse", f"{base}..{reactivation}").splitlines()
            positions = {commit: index for index, commit in enumerate([base, *ordered])}
            original_claim = (base, "codex-w2-implementation", "codex/w2-implementation", "LOC", "windows-x64")
            with self.assertRaisesRegex(ValueError, "outside its reviewed task range"):
                ui_gate.reference_activation_source_history(
                    root, ordered, positions, adoption, reactivation, admitted, original_claim
                )

    def test_reference_activation_allows_only_shared_tests_under_reactivated_original_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, adoption, backlog, _control, _consumer, _activation = self.reference_activation_git_fixture(temporary)
            reactivation = self.reactivate_adopted_continuation(root, adoption, backlog, activation=True)
            original_claim = (
                "6506c68461144747b0ee9be10853211717aa381d",
                "codex-w2-implementation",
                "codex/w2-implementation",
                "LOC",
                "windows-x64",
            )
            amendment = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A03")
            path = root / "tests/desktop/test_ui_conformance.py"
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write("\n# Synthetic current original-T01 test follow-up.\n")
            shared_test = self.commit(root, "synthetic original T01 shared desktop test update")
            admitted, _consumer_commits, _witness = ui_gate.reference_activation_reviewed_tasks(
                root, shared_test, amendment
            )
            base = original_claim[0]
            ordered = self.git(root, "rev-list", "--reverse", f"{base}..{shared_test}").splitlines()
            positions = {commit: index for index, commit in enumerate([base, *ordered])}
            ui_gate.reference_activation_source_history(
                root, ordered, positions, adoption, reactivation, admitted, original_claim
            )
            assembler = root / "apps/desktop/scripts/assemble-reference.mjs"
            with assembler.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write("\n// Synthetic unreviewed post-reactivation assembler edit.\n")
            attack = self.commit(root, "synthetic post-reactivation protected consumer edit")
            ordered = self.git(root, "rev-list", "--reverse", f"{base}..{attack}").splitlines()
            positions = {commit: index for index, commit in enumerate([base, *ordered])}
            with self.assertRaisesRegex(ValueError, "outside its reviewed task range"):
                ui_gate.reference_activation_source_history(
                    root, ordered, positions, adoption, reactivation, admitted, original_claim
                )

    def test_resumed_amendment_selects_original_base_without_a_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            self.write_yaml(
                root / "planning/backlog.yaml",
                {
                    "capabilities": [],
                    "wave_amendments": [
                        {
                            "id": "W1.A08",
                            "tasks": [
                                {
                                    "id": "W1.A08.T02",
                                    "amendment_id": "W1.A08",
                                    "status": "IN_PROGRESS",
                                    "base_sha": base,
                                }
                            ],
                        },
                        {"id": "W1.A09", "correction": {"id": "W1.A08"}, "lifecycle": {"status": "ADOPTED"}},
                    ],
                },
            )
            self.commit(root, "explicit resumed task")
            (root / "only-evidence.txt").write_text("no product edit\n", encoding="utf-8")
            head = self.commit(root, "later evidence")
            self.assertEqual(base, automatic_base(root, head))

    def test_restoration_segments_authenticate_each_real_git_commit(self) -> None:
        policy = {
            "implementationRoots": ["apps/desktop/src"],
            "implementationExtensions": [".css"],
            "ignoredImplementationSuffixes": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Gate Test")
            self.git(root, "config", "user.email", "ui-gate@example.invalid")
            self.git(root, "config", "core.autocrlf", "false")
            source = root / "apps/desktop/src/app.css"
            source.parent.mkdir(parents=True)
            source.write_text("a { color: black; }\n", encoding="utf-8")
            base = self.commit(root, "original claim")
            source.write_text("a { color: blue; }\n", encoding="utf-8")
            inherited = self.commit(root, "approved correction candidate")
            (root / "activation.txt").write_text("explicit activation\n", encoding="utf-8")
            activation = self.commit(root, "reactivation")
            source.write_text("a { color: blue; margin: 0; }\n", encoding="utf-8")
            head = self.commit(root, "resumed restoration")
            path = "apps/desktop/src/app.css"
            ranges = [{"base": base, "candidate": inherited, "paths": [path]}]
            expected = {
                "inheritedCorrectionUiFiles": [path],
                "resumedUiFiles": [path],
                "inheritedUiCommits": [inherited],
                "resumedUiCommits": [head],
            }
            self.assertEqual(expected, restoration_segments(root, base, head, activation, ranges, policy))
            for label, invalid in (("gap", []), ("overlap", ranges * 2), ("omission", [{**ranges[0], "paths": []}])):
                with self.subTest(label=label), self.assertRaises(ValueError):
                    restoration_segments(root, base, head, activation, invalid, policy)
            hidden = source.with_name("hidden.css")
            hidden.write_text(".hidden { color: red; }\n", encoding="utf-8")
            self.commit(root, "unattributed add")
            hidden.unlink()
            reverted = self.commit(root, "hide addition in net diff")
            with self.assertRaisesRegex(ValueError, "net inventory"):
                restoration_segments(root, base, reverted, activation, ranges, policy)
            self.git(root, "switch", "-c", "side", head)
            (root / "side.txt").write_text("side\n", encoding="utf-8")
            self.commit(root, "side history")
            self.git(root, "switch", "main")
            self.git(root, "merge", "--no-ff", "side", "-m", "ambiguous history")
            merged = self.git(root, "rev-parse", "HEAD").strip()
            with self.assertRaisesRegex(ValueError, "linear"):
                restoration_segments(root, base, merged, activation, ranges, policy)

    def test_intentional_amendment_segments_reject_hidden_and_mixed_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            reference = "design/ui-reference/assets/tokens.css"
            ui_path = "apps/desktop/src/View.tsx"
            contract_path = "artifacts/evidence/ui-change/W2.A01.T02.json"
            (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
            publication = self.commit(root, "publish approved reference")
            self.write_json(root / contract_path, {"synthetic": "contract mode test"})
            (root / ui_path).write_text("export const View = () => 'approved';\n", encoding="utf-8")
            head = self.commit(root, "implement after publication")
            segments = ui_gate.intentional_amendment_segments(
                root, base, head, publication, contract_path, {reference}, policy
            )
            self.assertEqual([ui_path], segments["uiFiles"])
            self.assertEqual([head], segments["uiCommits"])
            self.assertEqual([reference], segments["referenceFiles"])

            hidden = root / "apps/desktop/src/Temporary.tsx"
            hidden.write_text("export const Temporary = true;\n", encoding="utf-8")
            self.commit(root, "add hidden renderer")
            hidden.unlink()
            reverted = self.commit(root, "erase hidden renderer")
            with self.assertRaisesRegex(ValueError, "hidden add/revert"):
                ui_gate.intentional_amendment_segments(
                    root, base, reverted, publication, contract_path, {reference}, policy
                )

        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            reference = "design/ui-reference/assets/tokens.css"
            (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
            publication = self.commit(root, "publish approved reference")
            (root / "tools").mkdir(exist_ok=True)
            (root / "tools/ui_change_gate.py").write_text("GATE = False\n", encoding="utf-8")
            (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'changed';\n", encoding="utf-8")
            mixed = self.commit(root, "mix gate and renderer")
            with self.assertRaisesRegex(ValueError, "control"):
                ui_gate.intentional_amendment_segments(
                    root, base, mixed, publication, "artifacts/evidence/ui-change/W2.A01.T02.json", {reference}, policy
                )

    def test_intentional_amendment_segments_separate_backlog_from_product_commits(self) -> None:
        reference = "design/ui-reference/assets/tokens.css"
        ui_path = "apps/desktop/src/View.tsx"
        contract_path = "artifacts/evidence/ui-change/W2.A01.T02.json"
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            backlog_path = root / "planning/backlog.yaml"
            self.write_yaml(backlog_path, {"capabilities": [], "control_plane": {"active_amendment": "W2.A01"}})
            self.commit(root, "stand-alone taskctl claim transition")
            (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
            publication = self.commit(root, "separate reference publication")
            self.write_json(root / contract_path, {"synthetic": "regular"})
            (root / ui_path).write_text("export const View = () => 'approved';\n", encoding="utf-8")
            head = self.commit(root, "separate renderer implementation")
            self.assertEqual(
                [ui_path],
                ui_gate.intentional_amendment_segments(
                    root, base, head, publication, contract_path, {reference}, policy
                )["uiFiles"],
            )
            self.write_yaml(
                backlog_path, {"capabilities": [], "control_plane": {"active_amendment": "W2.A01"}, "status": "REVIEW"}
            )
            (root / ui_path).write_text("export const View = () => 'mixed';\n", encoding="utf-8")
            mixed_renderer = self.commit(root, "mix taskctl review transition and renderer")
            with self.assertRaisesRegex(ValueError, "backlog.*product"):
                ui_gate.intentional_amendment_segments(
                    root, base, mixed_renderer, publication, contract_path, {reference}, policy
                )

        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            self.write_yaml(root / "planning/backlog.yaml", {"capabilities": [], "status": "IN_PROGRESS"})
            (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
            mixed_publication = self.commit(root, "mix taskctl claim and reference publication")
            self.write_json(root / contract_path, {"synthetic": "regular"})
            (root / ui_path).write_text("export const View = () => 'approved';\n", encoding="utf-8")
            head = self.commit(root, "later renderer implementation")
            with self.assertRaisesRegex(ValueError, "backlog.*product"):
                ui_gate.intentional_amendment_segments(
                    root, base, head, mixed_publication, contract_path, {reference}, policy
                )

    def test_intentional_amendment_segments_deny_typed_product_bypasses(self) -> None:
        reference = "design/ui-reference/assets/tokens.css"
        ui_path = "apps/desktop/src/View.tsx"
        typed_path = "apps/desktop/src/native-attachment.d.ts"
        contract_path = "artifacts/evidence/ui-change/W2.A01.T02.json"
        for kind in ("before-publication", "mixed-backlog"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root, base, _package = self.prepare(temporary)
                policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
                self.assertTrue(ui_gate.intentional_amendment_delivery_path(typed_path, contract_path, policy))
                self.assertFalse(ui_gate.is_implementation_path(typed_path, policy))
                if kind == "before-publication":
                    (root / typed_path).write_text(
                        "export interface AttachmentIntent { id: string }\n", encoding="utf-8"
                    )
                    self.commit(root, "typed product contract before reference")
                (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
                publication = self.commit(root, "publish approved reference")
                self.write_json(root / contract_path, {"synthetic": "regular"})
                (root / ui_path).write_text("export const View = () => 'approved';\n", encoding="utf-8")
                self.commit(root, "renderer and evidence")
                if kind == "mixed-backlog":
                    self.write_yaml(root / "planning/backlog.yaml", {"capabilities": [], "status": "REVIEW"})
                    (root / typed_path).write_text(
                        "export interface AttachmentIntent { id: string }\n", encoding="utf-8"
                    )
                    self.commit(root, "mix taskctl review transition and typed product contract")
                head = self.git(root, "rev-parse", "HEAD")
                expected = "reference.*product" if kind == "before-publication" else "backlog.*product"
                with self.assertRaisesRegex(ValueError, expected):
                    ui_gate.intentional_amendment_segments(
                        root, base, head, publication, contract_path, {reference}, policy
                    )

    def test_intentional_amendment_segments_report_separate_typed_product_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            reference = "design/ui-reference/assets/tokens.css"
            ui_path = "apps/desktop/src/View.tsx"
            typed_path = "apps/desktop/src/native-attachment.d.ts"
            contract_path = "artifacts/evidence/ui-change/W2.A01.T02.json"
            self.assertFalse(
                ui_gate.intentional_amendment_delivery_path(
                    "packages/ui-components/src/native-attachment.d.ts", contract_path, policy
                )
            )
            (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
            publication = self.commit(root, "publish approved reference")
            (root / typed_path).write_text("export interface AttachmentIntent { id: string }\n", encoding="utf-8")
            typed_commit = self.commit(root, "freeze typed product contract after reference")
            self.write_json(root / contract_path, {"synthetic": "regular"})
            (root / ui_path).write_text("export const View = () => 'approved';\n", encoding="utf-8")
            head = self.commit(root, "render approved interaction")
            segments = ui_gate.intentional_amendment_segments(
                root, base, head, publication, contract_path, {reference}, policy
            )
            self.assertEqual([ui_path], segments["uiFiles"])
            self.assertEqual([head], segments["uiCommits"])
            self.assertEqual([typed_path], segments["typedProductFiles"])
            self.assertEqual([typed_commit], segments["typedProductCommits"])
            (root / typed_path).unlink()
            hidden = self.commit(root, "erase typed product contract")
            with self.assertRaisesRegex(ValueError, "hidden add/revert"):
                ui_gate.intentional_amendment_segments(
                    root, base, hidden, publication, contract_path, {reference}, policy
                )

    def test_intentional_amendment_segments_reject_extra_and_redirected_history(self) -> None:
        reference = "design/ui-reference/assets/tokens.css"
        contract_path = "artifacts/evidence/ui-change/W2.A01.T02.json"
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
            publication = self.commit(root, "publish approved reference")
            self.write_json(root / contract_path, {"synthetic": "regular"})
            (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'approved';\n", encoding="utf-8")
            self.commit(root, "renderer and regular evidence")

            extra = root / "artifacts/evidence/ui-change/CAP-05.S01.T01.json"
            self.write_json(extra, {"synthetic": "extra"})
            self.commit(root, "add extra contract")
            extra.unlink()
            hidden_extra = self.commit(root, "revert extra contract")
            with self.assertRaisesRegex(ValueError, "extra UI contract"):
                ui_gate.intentional_amendment_segments(
                    root, base, hidden_extra, publication, contract_path, {reference}, policy
                )

        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
            publication = self.commit(root, "publish approved reference")
            self.write_json(root / contract_path, {"synthetic": "redirect"})
            self.git(root, "add", "--all")
            object_id = self.git(root, "hash-object", "-w", contract_path)
            self.git(root, "update-index", "--add", "--cacheinfo", "120000", object_id, contract_path)
            self.git(root, "commit", "-m", "redirect evidence contract")
            self.write_json(root / contract_path, {"synthetic": "regular"})
            (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'approved';\n", encoding="utf-8")
            restored = self.commit(root, "restore regular contract and implement renderer")
            with self.assertRaisesRegex(ValueError, "delivery path is redirected"):
                ui_gate.intentional_amendment_segments(
                    root, base, restored, publication, contract_path, {reference}, policy
                )

        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
            publication = self.commit(root, "publish approved reference")
            ui_path = "apps/desktop/src/View.tsx"
            (root / ui_path).write_text("design/ui-reference/APPROVAL.yaml\n", encoding="utf-8")
            self.git(root, "add", "--all")
            object_id = self.git(root, "hash-object", "-w", ui_path)
            self.git(root, "update-index", "--add", "--cacheinfo", "120000", object_id, ui_path)
            self.git(root, "commit", "-m", "redirect intermediate renderer")
            self.write_json(root / contract_path, {"synthetic": "regular"})
            (root / ui_path).write_text("export const View = () => 'approved';\n", encoding="utf-8")
            restored = self.commit(root, "restore regular renderer")
            with self.assertRaisesRegex(ValueError, "redirected"):
                ui_gate.intentional_amendment_segments(
                    root, base, restored, publication, contract_path, {reference}, policy
                )

        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            self.write_json(root / contract_path, {"synthetic": "same commit"})
            (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
            (root / "apps/desktop/src/View.tsx").write_text(
                "export const View = () => 'premature';\n", encoding="utf-8"
            )
            simultaneous = self.commit(root, "reference and renderer in one commit")
            with self.assertRaisesRegex(ValueError, "strictly precede"):
                ui_gate.intentional_amendment_segments(
                    root, base, simultaneous, simultaneous, contract_path, {reference}, policy
                )

        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
            publication = self.commit(root, "publish approved reference")
            self.write_json(root / contract_path, {"synthetic": "regular"})
            (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'approved';\n", encoding="utf-8")
            self.commit(root, "renderer and evidence")
            (root / reference).write_text(":root { --surface: green; }\n", encoding="utf-8")
            rewritten = self.commit(root, "rewrite approved reference after renderer")
            with self.assertRaisesRegex(ValueError, "only in its separate publication"):
                ui_gate.intentional_amendment_segments(
                    root, base, rewritten, publication, contract_path, {reference}, policy
                )

    def test_intentional_amendment_segments_deny_non_renderer_product_and_security_files(self) -> None:
        for path in (
            "apps/desktop/src-tauri/capabilities/default.json",
            "services/core-api/src/attachment.py",
            "docs/adr/ADR-0003-protect-design-first-ui-change-controls-and-immutable-lineage.md",
            "tools/planctl.py",
            "planning/review-site/waves/W3.html",
        ):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                root, base, _package = self.prepare(temporary)
                policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
                reference = "design/ui-reference/assets/tokens.css"
                contract_path = "artifacts/evidence/ui-change/W2.A01.T02.json"
                (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
                publication = self.commit(root, "publish approved reference")
                self.write_json(root / contract_path, {"synthetic": "regular"})
                (root / "apps/desktop/src/View.tsx").write_text(
                    "export const View = () => 'approved';\n", encoding="utf-8"
                )
                self.commit(root, "renderer and evidence")
                extra = root / path
                extra.parent.mkdir(parents=True, exist_ok=True)
                extra.write_text("hostile non-UI change\n", encoding="utf-8")
                self.commit(root, "hide unrelated product or security edit")
                extra.unlink()
                reverted = self.commit(root, "revert unrelated edit")
                with self.assertRaisesRegex(ValueError, "out-of-scope"):
                    ui_gate.intentional_amendment_segments(
                        root, base, reverted, publication, contract_path, {reference}, policy
                    )

    def test_intentional_amendment_segments_deny_redirected_ancillary_delivery(self) -> None:
        for path in ("artifacts/evidence/W2.A01.T02.extra.json", "planning/review-site/waves/W2.html"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                root, base, _package = self.prepare(temporary)
                policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
                reference = "design/ui-reference/assets/tokens.css"
                contract_path = "artifacts/evidence/ui-change/W2.A01.T02.json"
                (root / reference).write_text(":root { --surface: blue; }\n", encoding="utf-8")
                publication = self.commit(root, "publish approved reference")
                self.write_json(root / contract_path, {"synthetic": "regular"})
                (root / "apps/desktop/src/View.tsx").write_text(
                    "export const View = () => 'approved';\n", encoding="utf-8"
                )
                self.commit(root, "renderer and evidence")
                redirected = root / path
                redirected.parent.mkdir(parents=True, exist_ok=True)
                redirected.write_text("design/ui-reference/APPROVAL.yaml\n", encoding="utf-8")
                self.git(root, "add", "--all")
                object_id = self.git(root, "hash-object", "-w", path)
                self.git(root, "update-index", "--add", "--cacheinfo", "120000", object_id, path)
                self.git(root, "commit", "-m", "redirect allowed ancillary path")
                head = self.git(root, "rev-parse", "HEAD")
                with self.assertRaisesRegex(ValueError, "delivery path is redirected"):
                    ui_gate.intentional_amendment_segments(
                        root, base, head, publication, contract_path, {reference}, policy
                    )

    def test_intentional_amendment_accepts_only_exact_published_reference_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _initial, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            page_path = "planning/review-site/enablers/ECR-0005.html"
            page = root / page_path
            page.parent.mkdir(parents=True)
            original = (
                "<p>Historical approval remains unchanged. The current published reference is "
                "<code>REF-1</code>; publication does not retroactively change this packet.</p>\n"
            )
            page.write_text(original, encoding="utf-8", newline="\n")
            base = self.commit(root, "existing historic ECR projection")

            approval = root / "design/ui-reference/APPROVAL.yaml"
            record = yaml.safe_load(approval.read_text(encoding="utf-8"))
            record["reference_id"] = "REF-2"
            record["supersedes"] = "REF-1"
            self.write_yaml(approval, record)
            publication = self.commit(root, "publish approved successor reference")
            contract_path = "artifacts/evidence/ui-change/W2.A01.T02.json"
            self.write_json(root / contract_path, {"synthetic": "regular"})
            (root / "apps/desktop/src/View.tsx").write_text(
                "export const View = () => 'approved';\n", encoding="utf-8", newline="\n"
            )
            renderer = self.commit(root, "renderer after publication")
            page.write_text(
                original.replace("<code>REF-1</code>", "<code>REF-2</code>"), encoding="utf-8", newline="\n"
            )
            projection = self.commit(root, "refresh historic ECR current-reference projection")
            segments = ui_gate.intentional_amendment_segments(
                root,
                base,
                projection,
                publication,
                contract_path,
                {"design/ui-reference/APPROVAL.yaml"},
                policy,
            )
            self.assertEqual(["apps/desktop/src/View.tsx"], segments["uiFiles"])
            for label, hostile_path, hostile_text in (
                (
                    "extra-content",
                    page_path,
                    original.replace("Historical", "Rewritten").replace("REF-1</code>;", "REF-2</code>;"),
                ),
                ("wrong-reference", page_path, original.replace("REF-1</code>;", "REF-X</code>;")),
                (
                    "new-page",
                    "planning/review-site/enablers/ECR-0006.html",
                    original.replace("REF-1</code>;", "REF-2</code>;"),
                ),
                (
                    "nested-page",
                    "planning/review-site/enablers/nested/ECR-0006.html",
                    original.replace("REF-1</code>;", "REF-2</code>;"),
                ),
            ):
                with self.subTest(label=label):
                    self.git(root, "reset", "--hard", renderer)
                    hostile = root / hostile_path
                    hostile.parent.mkdir(parents=True, exist_ok=True)
                    hostile.write_text(hostile_text, encoding="utf-8", newline="\n")
                    head = self.commit(root, f"hostile {label} projection")
                    with self.assertRaisesRegex(ValueError, "out-of-scope files"):
                        ui_gate.intentional_amendment_segments(
                            root,
                            base,
                            head,
                            publication,
                            contract_path,
                            {"design/ui-reference/APPROVAL.yaml"},
                            policy,
                        )

    def test_intentional_amendment_automatic_base_uses_live_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            backlog = {
                "capabilities": [],
                "wave_amendments": [
                    {
                        "id": "W2.A01",
                        "tasks": [
                            {
                                "id": "W2.A01.T02",
                                "amendment_id": "W2.A01",
                                "status": "IN_PROGRESS",
                                "base_sha": base,
                            }
                        ],
                    }
                ],
            }
            self.write_yaml(root / "planning/backlog.yaml", backlog)
            self.commit(root, "claim exact intentional amendment task")
            (root / "evidence.txt").write_text("later evidence\n", encoding="utf-8")
            self.commit(root, "later evidence-only commit")
            self.assertEqual(base, automatic_base(root, "HEAD"))

    def test_intentional_amendment_live_claim_rejects_foreign_or_expired_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _initial, _package = self.prepare(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            task: dict[str, Any] = {
                "id": "W2.A01.T02",
                "amendment_id": "W2.A01",
                "title": "Exact reference and renderer",
                "objective": "Bounded synthetic claim",
                "dependencies": ["W2.A01.T01"],
                "acceptance_criteria": ["Approved proof"],
                "verification_commands": ["test"],
                "packet_task_sha256": "a" * 64,
                "status": "READY",
                "owner": None,
                "base_sha": None,
                "lease": None,
            }
            amendment: dict[str, Any] = {
                "id": "W2.A01",
                "change_request_id": "ECR-0009",
                "target_wave": "W2",
                "lifecycle": {"status": "ACTIVE"},
                "campaign": {
                    "status": "ACTIVE",
                    "scope": "wave-amendment",
                    "owner": "codex",
                    "branch": "main",
                    "worktree": ".",
                    "lease": {"claimed_by": "codex", "expires_at": "2099-01-01T00:00:00Z"},
                },
                "tasks": [task],
            }
            backlog: dict[str, Any] = {
                "capabilities": [],
                "waves": [{"id": "W2", "campaign": {"status": "PAUSED", "scope": "amendment-hold", "lease": None}}],
                "wave_amendments": [amendment],
                "control_plane": {"active_amendment": "W2.A01"},
            }
            self.write_yaml(root / "planning/backlog.yaml", backlog)
            base = self.commit(root, "exact ready claim base")
            task.update(
                status="IN_PROGRESS",
                owner="codex",
                branch="main",
                worktree=".",
                base_sha=base,
                lease={"claimed_by": "codex", "expires_at": "2099-01-01T00:00:00Z"},
                started_at="2026-10-02T00:00:00Z",
            )
            self.write_yaml(root / "planning/backlog.yaml", backlog)
            self.commit(root, "exact taskctl claim shape")
            contract: dict[str, Any] = {
                "schemaVersion": "1.2",
                "taskId": "W2.A01.T02",
                "changeKind": "intentional-design-change",
                "implementationAgent": "agent:codex",
                "intentionalAmendmentAuthority": {
                    "amendmentId": "W2.A01",
                    "changeRequestId": "ECR-0009",
                    "controlTaskId": "W2.A01.T01",
                    "referenceApprovalPath": "planning/reference-approvals/RO-UI-ACADEMIC-MINIMAL-1.8.json",
                },
            }
            valid = ui_gate.intentional_amendment_live_claim(
                root, base, self.git(root, "rev-parse", "HEAD"), contract, policy
            )
            self.assertEqual("codex", valid["owner"])
            for field, invalid in (
                ("branch", "foreign"),
                ("worktree", "C:/foreign"),
                ("base_sha", "b" * 40),
                ("owner", "foreign"),
                ("lease", {"claimed_by": "foreign", "expires_at": "2099-01-01T00:00:00Z"}),
                ("lease", {"claimed_by": "codex", "expires_at": "2000-01-01T00:00:00Z"}),
            ):
                with self.subTest(field=field, invalid=invalid):
                    original = task[field]
                    task[field] = invalid
                    self.write_yaml(root / "planning/backlog.yaml", backlog)
                    candidate = self.commit(root, f"hostile {field}")
                    with self.assertRaises(ValueError):
                        ui_gate.intentional_amendment_live_claim(root, base, candidate, contract, policy)
                    task[field] = original
                    self.write_yaml(root / "planning/backlog.yaml", backlog)
                    self.commit(root, f"restore {field}")
            for field, invalid in (
                ("status", "ACTIVE"),
                ("scope", "wave"),
                ("lease", {"claimed_by": "codex", "expires_at": "2099-01-01T00:00:00Z"}),
            ):
                with self.subTest(ordinary_campaign_field=field):
                    ordinary = backlog["waves"][0]["campaign"]
                    original = ordinary[field]
                    ordinary[field] = invalid
                    self.write_yaml(root / "planning/backlog.yaml", backlog)
                    candidate = self.commit(root, f"competing ordinary W2 {field}")
                    with self.assertRaisesRegex(ValueError, "exclusive paused W2"):
                        ui_gate.intentional_amendment_live_claim(root, base, candidate, contract, policy)
                    ordinary[field] = original
                    self.write_yaml(root / "planning/backlog.yaml", backlog)
                    self.commit(root, f"restore ordinary W2 {field}")
            backlog["capabilities"].append(
                {"slices": [{"tasks": [{"id": "CAP-05.S01.T01", "wave": "W2", "status": "IN_PROGRESS"}]}]}
            )
            self.write_yaml(root / "planning/backlog.yaml", backlog)
            competing = self.commit(root, "competing ordinary W2 task")
            with self.assertRaisesRegex(ValueError, "exclusive paused W2"):
                ui_gate.intentional_amendment_live_claim(root, base, competing, contract, policy)
            altered = copy.deepcopy(contract)
            altered["intentionalAmendmentAuthority"]["changeRequestId"] = "ECR-0010"
            with self.assertRaisesRegex(ValueError, "selector"):
                ui_gate.intentional_amendment_live_claim(
                    root, base, self.git(root, "rev-parse", "HEAD"), altered, policy
                )

    def test_completed_amendment_control_accepts_reviewed_second_round_evidence(self) -> None:
        head = self.git(REPO, "rev-parse", "HEAD")
        backlog = yaml.safe_load(ui_gate.blob(REPO, head, "planning/backlog.yaml"))
        amendment = ui_gate.amendment_record(backlog, "W2.A01")
        task = next(item for item in amendment["tasks"] if item["id"] == "W2.A01.T01")
        attempts = task["review_control"]["attempts"]
        self.assertEqual(
            "artifacts/evidence/W2.A01.T01-R02.json", attempts[1]["submission"]["evidence_reference"]["path"]
        )
        ranges = ui_gate.correction_submission_ranges(REPO, head, {"tasks": [task]})
        self.assertEqual(
            [attempt["submission"]["candidate_commit"] for attempt in attempts], [item["candidate"] for item in ranges]
        )

    def test_correction_evidence_namespace_keeps_round_and_task_boundaries(self) -> None:
        identity = "W2.A01.T01"
        for path in (
            "artifacts/evidence/W2.A01.T01.json",
            "artifacts/evidence/W2.A01.T01-R02.json",
            "artifacts/evidence/W2.A01.T01-R02.detail.json",
        ):
            with self.subTest(accepted=path):
                self.assertTrue(ui_gate.canonical_correction_evidence_path(identity, path))
        for path in (
            "artifacts/evidence/W2.A01.T02-R02.json",
            "artifacts/evidence/W2.A01.T01-R00.json",
            "artifacts/evidence/W2.A01.T01-R2.json",
            "artifacts/evidence/W2.A01.T01-R002.json",
            "artifacts/evidence/W2.A01.T01-r02.json",
            "artifacts/evidence/W2.A01.T01-R02-R03.json",
            "artifacts/evidence/W2.A01.T01-R02.json/child.json",
            "artifacts/evidence/../W2.A01.T01-R02.json",
            "artifacts/evidence/nested/W2.A01.T01-R02.json",
            "artifacts/evidence/W2.A01.T01-R02.md",
        ):
            with self.subTest(rejected=path):
                self.assertFalse(ui_gate.canonical_correction_evidence_path(identity, path))

    def test_intentional_amendment_exact_approved_packet_to_renderer_git_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, head, candidate, _contract = self.intentional_git_fixture(temporary)
            control_base = self.git(root, "rev-parse", "468cb3902f5b3ea9c1ad9769c969c581f68cd1c2")
            self.assertTrue(
                ui_gate.INTENTIONAL_AMENDMENT_CONTROL_PATHS.issubset(
                    ui_gate.changed_paths(root, control_base, candidate)
                )
            )
            report = validate(root, base, head)
            self.assertTrue(report["ok"], report["errors"])
            self.assertEqual("RO-UI-ACADEMIC-MINIMAL-1.8", report["referenceId"])
            for kind in ("remove", "rewrite", "duplicate-id", "duplicate-path"):
                self.git(root, "switch", "-c", f"hostile-index-{kind}", head)
                index_path = root / "docs/adr/index.json"
                index = json.loads(index_path.read_text(encoding="utf-8"))
                if kind == "remove":
                    index["records"] = [record for record in index["records"] if record["id"] != "ADR-0035"]
                elif kind == "rewrite":
                    next(record for record in index["records"] if record["id"] == "ADR-0035")["title"] = (
                        "Unauthorized rewrite of reviewed decision"
                    )
                else:
                    duplicate = copy.deepcopy(next(record for record in index["records"] if record["id"] == "ADR-0035"))
                    if kind == "duplicate-id":
                        duplicate["path"] = "docs/adr/ADR-0037-conflicting-entry.md"
                    else:
                        duplicate["id"] = "ADR-0037"
                    index["records"].append(duplicate)
                self.write_json(index_path, index)
                hostile_head = self.commit(root, f"{kind} reviewed ADR-0035 index entry")
                hostile_backlog = yaml.safe_load((root / "planning/backlog.yaml").read_text(encoding="utf-8"))
                hostile_amendment = ui_gate.amendment_record(hostile_backlog, "W2.A01")
                with self.assertRaisesRegex(ValueError, "post-review ADR index"):
                    ui_gate.intentional_amendment_control_predecessor(root, hostile_head, base, hostile_amendment)
                self.git(root, "switch", "fixture")
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            for kind, path, expected in (
                ("packet", "planning/enabler-change-requests/ECR-0009.packet.json", "packet authentication"),
                ("proposal", "planning/W2-reference-1.8/STYLE_GUIDE.md", "proposal source|packet authentication"),
                ("human-approval", "planning/wave-amendment-approvals/W2.A01.json", "hash mismatch"),
                (
                    "design-approval",
                    "planning/reference-approvals/RO-UI-ACADEMIC-MINIMAL-1.8.json",
                    "immutable introduction",
                ),
                ("publication-chronology", "artifacts/evidence/ui-change/W2.A01.T02.json", "publication|reference"),
            ):
                with self.subTest(kind=kind):
                    self.assertEqual(head, self.git(root, "rev-parse", "HEAD"))
                    target = root / path
                    if kind == "proposal":
                        with target.open("a", encoding="utf-8") as stream:
                            stream.write("\nUnauthorized proposal rewrite.\n")
                    else:
                        payload = json.loads(target.read_text(encoding="utf-8"))
                        if kind == "packet":
                            payload["targetWave"] = "W3"
                        elif kind in {"human-approval", "design-approval"}:
                            payload["approvedBy"] = "human:forged-owner"
                        else:
                            payload["reference"]["approvalCommit"] = head
                        self.write_json(target, payload)
                    hostile_head = self.commit(root, f"hostile {kind} substitution")
                    hostile_contract = json.loads(
                        (root / "artifacts/evidence/ui-change/W2.A01.T02.json").read_text(encoding="utf-8")
                    )
                    self.assertTrue(root.is_relative_to(Path(temporary)))
                    try:
                        with self.assertRaisesRegex(ValueError, expected):
                            ui_gate.intentional_amendment_authority(root, base, hostile_head, hostile_contract, policy)
                    finally:
                        self.git(root, "reset", "--hard", head)

    def test_current_w1_amendment_ui_range_accepts_reviewed_historical_maintenance(self) -> None:
        result = validate(
            REPO,
            "bd8d752a0fcec1f40b1a8abe59b793c783946e4e",
            "6c5757659ecbca11f1469e1ab3dfec330fe0d74f",
        )

        self.assertTrue(result["ok"], result["errors"])

    def test_cumulative_additive_pre_ui_inventory_then_ui_implementation_passes(self) -> None:
        result = validate(
            REPO,
            "bfb8797398707bece9e0662c0d995fabaced9979",
            "59079efccc122a7d56a9f18efc20030851bf32a9",
        )

        self.assertTrue(result["ok"], result["errors"])

    def test_pre_ui_quality_inventory_is_only_additive_same_commit_non_ui_python(self) -> None:
        policy = {
            "implementationRoots": ["apps/desktop/src"],
            "implementationExtensions": [".css", ".tsx"],
            "ignoredImplementationSuffixes": [".test.tsx"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Gate Test")
            self.git(root, "config", "user.email", "ui-gate@example.invalid")
            self.git(root, "config", "core.autocrlf", "false")
            self.write_json(
                root / "quality-scope.json",
                {
                    "schemaVersion": "1.0",
                    "documentType": "python-quality-scope",
                    "governedRoots": ["services", "tests", "tools"],
                    "pythonFiles": ["services/core/existing.py"],
                },
            )
            existing = root / "services/core/existing.py"
            existing.parent.mkdir(parents=True)
            existing.write_text("EXISTING = True\n", encoding="utf-8")
            self.commit(root, "baseline quality scope")

            source = root / "services/core/projects.py"
            test = root / "tests/service/test_projects.py"
            source.write_text("PROJECTS = True\n", encoding="utf-8")
            test.parent.mkdir(parents=True)
            test.write_text("def test_projects(): pass\n", encoding="utf-8")
            scope = json.loads((root / "quality-scope.json").read_text(encoding="utf-8"))
            scope["pythonFiles"].extend(["services/core/projects.py", "tests/service/test_projects.py"])
            self.write_json(root / "quality-scope.json", scope)
            additive = self.commit(root, "add service quality inventory before UI")
            self.assertEqual([], additive_preimplementation_quality_scope_errors(root, additive, policy))

            scope["pythonFiles"].remove("services/core/existing.py")
            self.write_json(root / "quality-scope.json", scope)
            removal = self.commit(root, "remove existing inventory")
            self.assertTrue(additive_preimplementation_quality_scope_errors(root, removal, policy))

            gate = root / "tools/ui_change_gate.py"
            gate.parent.mkdir(parents=True)
            gate.write_text("GATE = True\n", encoding="utf-8")
            scope["pythonFiles"].append("tools/ui_change_gate.py")
            self.write_json(root / "quality-scope.json", scope)
            gate_addition = self.commit(root, "attempt gate inventory addition")
            self.assertTrue(additive_preimplementation_quality_scope_errors(root, gate_addition, policy))

    def inventory_fixture(self, temporary: str) -> tuple[Path, str, dict[str, Any], dict[str, Any]]:
        root, _, _ = self.prepare(temporary)
        scope: dict[str, Any] = {
            "schemaVersion": "1.0",
            "documentType": "python-quality-scope",
            "governedRoots": ["services", "tests", "tools"],
            "pythonFiles": ["services/existing.py", "tests/existing.py"],
        }
        for path in [*scope["pythonFiles"], "tools/already_present.py"]:
            source = root / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("EXISTING = True\n", encoding="utf-8")
        self.write_json(root / "quality-scope.json", scope)
        base = self.commit(root, "inventory baseline")
        (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'UI';\n", encoding="utf-8")
        self.commit(root, "earlier UI implementation")
        policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
        return root, base, scope, policy

    def test_late_additive_python_inventory_does_not_change_ui_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, scope, policy = self.inventory_fixture(temporary)
            for path in ["tools/new_check.py", "services/new.py", "tests/new.py"]:
                (root / path).write_text("NEW = True\n", encoding="utf-8")
                scope["pythonFiles"].append(path)
            self.write_json(root / "quality-scope.json", scope)
            head = self.commit(root, "add new non-UI Python inventory after UI")
            self.assertEqual([], additive_preimplementation_quality_scope_errors(root, head, policy))
            self.assertEqual(
                [],
                application_activation_errors(
                    root,
                    base,
                    head,
                    ["quality-scope.json"],
                    {"changeKind": "approved-reference-implementation"},
                    policy,
                ),
            )

    def test_adopted_continuation_inventory_exception_is_one_historical_commit(self) -> None:
        exact = "9727f1b195e7dee300e7f3df3c289e7739fb0fdc"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "real-history"
            protected_config = Path(temporary) / "fixture-gitconfig"
            protected_config.write_text(f"[safe]\n\tdirectory = {(REPO / '.git').as_posix()}\n", encoding="utf-8")
            clone = subprocess.run(
                ["git", "clone", "--quiet", "--shared", "--no-checkout", str(REPO), str(root)],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "GIT_CONFIG_GLOBAL": str(protected_config)},
            )
            self.assertEqual(0, clone.returncode, clone.stderr)
            self.git(root, "config", "user.name", "UI Gate Test")
            self.git(root, "config", "user.email", "ui-gate@example.invalid")
            policy = json.loads((REPO / "ui-change-policy.json").read_text(encoding="utf-8"))
            self.assertEqual([], ui_gate.adopted_continuation_quality_scope_errors(root, exact, policy))
            # The legacy generic rule still rejects inventory mixed with UI work.
            self.assertTrue(additive_preimplementation_quality_scope_errors(root, exact, policy))
            parent = self.git(root, "rev-parse", f"{exact}^")
            tree = self.git(root, "rev-parse", f"{exact}^{{tree}}")
            lookalike = self.git(root, "commit-tree", tree, "-p", parent, "-m", "same tree, foreign commit")
            self.assertNotEqual(exact, lookalike)
            self.assertTrue(ui_gate.adopted_continuation_quality_scope_errors(root, lookalike, policy))
            self.assertTrue(ui_gate.adopted_continuation_quality_scope_errors(root, parent, policy))

    def test_adopted_continuation_automatic_base_uses_live_original_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, adoption, _branch, backlog, _amendment = self.adopted_continuation_git_fixture(temporary)
            reactivation = self.reactivate_adopted_continuation(root, adoption, backlog)
            self.assertNotEqual("6506c68461144747b0ee9be10853211717aa381d", reactivation)
            self.assertEqual("6506c68461144747b0ee9be10853211717aa381d", automatic_base(root, "HEAD"))

    def test_adopted_continuation_a02_adoption_rejects_rewritten_independent_task_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, adoption, _branch, backlog, amendment = self.adopted_continuation_git_fixture(temporary)
            packet = json.loads(
                (root / "planning/enabler-change-requests/ECR-0010.packet.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                adoption, ui_gate.adopted_continuation_adoption(root, adoption, backlog, amendment, packet)
            )
            ledger_path = root / "artifacts/evidence/W2.A02.T01.review-R01.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["result"] = "changes-requested"
            self.write_json(ledger_path, ledger)
            rewritten = self.commit(root, "synthetic adverse rewrite of independent A02 control review")
            with self.assertRaisesRegex(ValueError, "review|ledger|immutable"):
                ui_gate.adopted_continuation_adoption(root, rewritten, backlog, amendment, packet)

    def test_adopted_continuation_short_base_cannot_hide_no_net_ui_or_reverted_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, adoption, _branch, backlog, _amendment = self.adopted_continuation_git_fixture(temporary)
            reactivation = self.reactivate_adopted_continuation(root, adoption, backlog)
            path = root / "apps/desktop/src/app/DocumentAttachmentPane.tsx"
            original = path.read_bytes()
            evidence = root / "artifacts/evidence/CAP-05.S01.T01.fixture-only.txt"
            evidence.write_text("Test-only evidence delivery; no UI contract.\n", encoding="utf-8")
            evidence_only = self.commit(root, "synthetic evidence-only T01 head")
            self.assertFalse(validate(root, reactivation, evidence_only)["ok"])
            with path.open("ab") as stream:
                stream.write(b"\n// Synthetic intermediate governed UI edit.\n")
            self.commit(root, "synthetic hidden UI edit")
            path.write_bytes(original)
            reverted = self.commit(root, "synthetic UI revert with no task contract")
            self.assertFalse(validate(root, reactivation, reverted)["ok"])

    def test_adopted_continuation_public_gate_authenticates_two_contracts_and_current_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, head, contract, manifest, scope = self.classified_adopted_continuation_fixture(temporary)
            self.assertEqual(
                [
                    "artifacts/evidence/ui-change/CAP-05.S01.T01.json",
                    "artifacts/evidence/ui-change/W2.A01.T02.json",
                ],
                sorted(
                    path
                    for path in ui_gate.changed_paths(root, base, head)
                    if path.startswith("artifacts/evidence/ui-change/")
                ),
            )
            self.assertEqual("6506c68461144747b0ee9be10853211717aa381d", automatic_base(root, head))
            self.assertEqual(["9727f1b195e7dee300e7f3df3c289e7739fb0fdc"], scope["resumedUiCommits"])
            authority = contract["adoptedContinuationAuthority"]
            resume = self.git(root, "rev-parse", f"{authority['reactivationCommit']}^")
            self.assertEqual(authority["adoptionCommit"], self.git(root, "rev-parse", f"{resume}^"))
            classification = json.loads(
                (root / "artifacts/evidence/CAP-05.S01.T01.ui-classification-R01.json").read_text(encoding="utf-8")
            )
            for groundwork in (
                "tests/fixtures/documents/v21-predecessor.zip",
                "workers/document/inspection.py",
                "tools/architecture_check.py",
                "tools/core_sidecar_build.py",
            ):
                with self.subTest(groundwork=groundwork):
                    self.assertIn(groundwork, scope["t01ProductPaths"])
                    self.assertIn(groundwork, classification["dependentInputFiles"])
                    self.assertEqual(
                        self.git(root, "rev-parse", f"{classification['candidateCommit']}:{groundwork}"),
                        classification["dependentInputGitBlobs"][groundwork],
                    )
            with (
                patch("product_style_check.read_capture_bundle", return_value=manifest),
                patch("desktop_app_check.qualification_capture_contract", return_value=[]),
                patch("desktop_app_check.qualification_report_errors", return_value=[]),
                patch("product_style_check.capture_producer_snapshot", return_value=manifest["producer"]),
            ):
                result = validate(root, base, head)
            self.assertTrue(result["ok"], result["errors"])
            self.assertEqual("CAP-05.S01.T01", contract["taskId"])

    def test_adopted_continuation_classification_closes_dependent_git_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, head, contract, manifest, scope = self.classified_adopted_continuation_fixture(temporary)
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            reference = contract["adoptedContinuationAuthority"]["classification"]
            record_path = root / reference["path"]
            original_record = json.loads(record_path.read_text(encoding="utf-8"))
            dependent = "workers/document/inspection.py"
            self.assertIn(dependent, original_record["dependentInputFiles"])

            # Exercise the actual confined capture reader once. This fixture's
            # manifest deliberately has no PNG inventory and must fail closed.
            with self.assertRaisesRegex(ValueError, "invalid capture manifest fields"):
                ui_gate.adopted_continuation_classification_errors(root, base, head, contract, scope, policy)

            original = (root / dependent).read_bytes()
            (root / dependent).write_bytes(original + b"\n# unreviewed post-classification touch\n")
            self.commit(root, "synthetic dependent input touched after classification")
            (root / dependent).write_bytes(original)
            reverted = self.commit(root, "synthetic dependent input reverted after classification")
            with (
                patch("product_style_check.read_capture_bundle", return_value=manifest),
                patch("desktop_app_check.qualification_capture_contract", return_value=[]),
                patch("desktop_app_check.qualification_report_errors", return_value=[]),
                patch("product_style_check.capture_producer_snapshot", return_value=manifest["producer"]),
            ):
                errors = ui_gate.adopted_continuation_classification_errors(
                    root, base, reverted, contract, scope, policy
                )
            self.assertTrue(any("stale after a product/reference change" in error for error in errors), errors)

            parent = self.git(root, "rev-parse", f"{reference['commit']}^")
            for case in ("omitted dependent file", "wrong dependent Git blob"):
                with self.subTest(case=case):
                    self.git(root, "reset", "--hard", parent)
                    revised = copy.deepcopy(original_record)
                    if case == "omitted dependent file":
                        revised["dependentInputFiles"].remove(dependent)
                        del revised["dependentInputGitBlobs"][dependent]
                        expected = "omits or adds dependent T01 product inputs"
                    else:
                        revised["dependentInputGitBlobs"][dependent] = "0" * 40
                        expected = "dependent product input changed after classification"
                    self.write_json(record_path, revised)
                    introduction = self.commit(root, f"synthetic classification with {case}")
                    bad_contract = copy.deepcopy(contract)
                    bad_contract["adoptedContinuationAuthority"]["classification"] = {
                        "path": reference["path"],
                        "sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
                        "commit": introduction,
                    }
                    self.write_json(root / "artifacts/evidence/ui-change/CAP-05.S01.T01.json", bad_contract)
                    bad_head = self.commit(root, f"synthetic current contract citing {case}")
                    with (
                        patch("product_style_check.read_capture_bundle", return_value=manifest),
                        patch("desktop_app_check.qualification_capture_contract", return_value=[]),
                        patch("desktop_app_check.qualification_report_errors", return_value=[]),
                        patch("product_style_check.capture_producer_snapshot", return_value=manifest["producer"]),
                    ):
                        errors = ui_gate.adopted_continuation_classification_errors(
                            root, base, bad_head, bad_contract, scope, policy
                        )
                    self.assertTrue(any(expected in error for error in errors), errors)

            self.git(root, "reset", "--hard", head)
            self.write_json(root / "artifacts/evidence/ui-change/FOREIGN.json", {"taskId": "FOREIGN"})
            foreign = self.commit(root, "synthetic unapproved extra UI contract")
            result = validate(root, base, foreign)
            self.assertTrue(any("exactly inherited T02 and current T01" in error for error in result["errors"]), result)

            self.git(root, "reset", "--hard", head)
            with self.assertRaisesRegex(ValueError, "selector/head/base"):
                ui_gate.adopted_continuation_live_claim(
                    root, contract["adoptedContinuationAuthority"]["reactivationCommit"], head, contract, policy
                )
            self.git(root, "switch", "-c", "codex/foreign-fixture")
            with self.assertRaisesRegex(ValueError, "sole active W2/T01 claim"):
                ui_gate.adopted_continuation_live_claim(root, base, head, contract, policy)
            self.git(root, "switch", "codex/w2-implementation")

            backlog_path = root / "planning/backlog.yaml"
            backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            task = next(
                task
                for capability in backlog["capabilities"]
                for slice_ in capability["slices"]
                for task in slice_["tasks"]
                if task["id"] == "CAP-05.S01.T01"
            )
            task["lease"]["claimed_by"] = "foreign-owner"
            self.write_yaml(backlog_path, backlog)
            foreign_lease = self.commit(root, "synthetic foreign original T01 lease")
            with self.assertRaisesRegex(ValueError, "lease is stale or foreign"):
                ui_gate.adopted_continuation_live_claim(root, base, foreign_lease, contract, policy)

            self.git(root, "reset", "--hard", head)
            backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            wave = next(item for item in backlog["waves"] if item["id"] == "W2")
            wave["campaign"]["resume_records"].pop()
            self.write_yaml(backlog_path, backlog)
            forged_resume = self.commit(root, "synthetic active W2 projection without its resume record")
            with self.assertRaisesRegex(ValueError, "W2 resume history is invalid"):
                automatic_base(root, forged_resume)

    def test_adopted_continuation_rejects_unreviewed_imported_authority_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _head, contract, _manifest, _scope = self.classified_adopted_continuation_fixture(temporary)
            path = root / "tools/taskctl.py"
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write("\n# Synthetic unreviewed post-classification authority edit.\n")
            attack = self.commit(root, "synthetic unreviewed taskctl authority edit")
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "imported authority code changed without exact approval"):
                ui_gate.adopted_continuation_authority(root, base, attack, contract, policy)

    def test_adopted_continuation_rejects_reviewed_a02_source_outside_six_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, head, contract, _manifest, _scope = self.classified_adopted_continuation_fixture(
                temporary, inject_unapproved_control_source=True
            )
            injected = "workers/document/injected_control.py"
            backlog = yaml.safe_load((root / "planning/backlog.yaml").read_text(encoding="utf-8"))
            control = next(item for item in backlog["wave_amendments"] if item["id"] == "W2.A02")["tasks"][0]
            self.assertIn(injected, control["review_control"]["attempts"][0]["submission"]["changed_paths"])
            policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "W2.A02.T01 source paths differ from approved six-file scope"):
                ui_gate.adopted_continuation_authority(root, base, head, contract, policy)

    def test_late_inventory_rejects_control_or_nonadditive_or_noncanonical_changes(self) -> None:
        cases = (
            "metadata",
            "roots",
            "removal",
            "reorder",
            "duplicate",
            "missing-source",
            "existing-source",
            "gate-source",
            "ui-source",
            "mixed-gate",
            "mixed-ui",
            "non-python",
            "outside-root",
            "dot-segment",
            "double-slash",
            "symlink",
            "merge",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root, _, scope, policy = self.inventory_fixture(temporary)
                source_path = {
                    "existing-source": "tools/already_present.py",
                    "gate-source": "tools/ui_change_gate.py",
                    "ui-source": "apps/desktop/src/extra.py",
                    "non-python": "tools/new.txt",
                    "outside-root": "other/new.py",
                    "dot-segment": "tools/../tools/new.py",
                    "double-slash": "tools//new.py",
                }.get(case, "tools/new_check.py")
                scope["pythonFiles"].append(source_path)
                if case != "missing-source":
                    source = root / source_path
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_text("NEW = True\n", encoding="utf-8")
                if case == "metadata":
                    scope["extra"] = True
                elif case == "roots":
                    scope["governedRoots"].append("other")
                elif case == "removal":
                    scope["pythonFiles"].pop(0)
                elif case == "reorder":
                    scope["pythonFiles"][:2] = reversed(scope["pythonFiles"][:2])
                elif case == "duplicate":
                    scope["pythonFiles"].append(source_path)
                elif case == "mixed-gate":
                    (root / "tools/ui_change_gate.py").write_text("GATE = True\n", encoding="utf-8")
                elif case == "mixed-ui":
                    (root / "apps/desktop/src/View.tsx").write_text(
                        "export const View = () => 'more';\n", encoding="utf-8"
                    )
                self.write_json(root / "quality-scope.json", scope)
                if case == "symlink":
                    self.git(root, "add", "--all")
                    oid = self.git(root, "hash-object", "-w", source_path)
                    self.git(root, "update-index", "--add", "--cacheinfo", "120000", oid, source_path)
                    self.git(root, "commit", "-m", "redirected inventory source")
                    head = self.git(root, "rev-parse", "HEAD")
                elif case == "merge":
                    self.git(root, "switch", "-c", "side")
                    self.commit(root, "side inventory")
                    self.git(root, "switch", "main")
                    self.git(root, "merge", "--no-ff", "side", "-m", "merge inventory")
                    head = self.git(root, "rev-parse", "HEAD")
                else:
                    head = self.commit(root, "invalid inventory " + case)
                self.assertTrue(additive_preimplementation_quality_scope_errors(root, head, policy))

    def test_late_inventory_add_revert_cannot_hide_invalid_intermediate_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, scope, policy = self.inventory_fixture(temporary)
            original = copy.deepcopy(scope)
            scope["governedRoots"].append("ungoverned")
            self.write_json(root / "quality-scope.json", scope)
            self.commit(root, "invalid intermediate roots")
            self.write_json(root / "quality-scope.json", original)
            head = self.commit(root, "restore inventory net bytes")
            self.assertTrue(
                application_activation_errors(
                    root,
                    base,
                    head,
                    ["quality-scope.json"],
                    {"changeKind": "approved-reference-implementation"},
                    policy,
                )
            )

    def test_public_validation_rejects_inventory_control_change_even_after_exact_revert(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, scope, _ = self.inventory_fixture(temporary)
            approval = self.git(root, "rev-parse", base + "^")
            contract = self.contract("approved-reference-implementation", self.reference_package(root), approval)
            self.install_contract(root, contract, base_sha=base)
            valid = self.commit(root, "valid public UI contract")
            result = validate(root, base, valid)
            self.assertTrue(result["ok"], result["errors"])
            original = copy.deepcopy(scope)
            scope["governedRoots"].append("ungoverned")
            self.write_json(root / "quality-scope.json", scope)
            self.commit(root, "invalid intermediate public control change")
            self.write_json(root / "quality-scope.json", original)
            head = self.commit(root, "restore public control net bytes")
            result = validate(root, base, head)
            self.assertFalse(result["ok"], result["errors"])
            self.assertTrue(any("gate" in error for error in result["errors"]), result)

    def test_historical_quality_scope_hardening_requires_exact_immutable_approval(self) -> None:
        hardening = "1cd9deebe94fa2b667ad6b0030bd07ec45d1c6bb"
        approval = "43bcdec4eba110f994a540f0a1e625a6d44aff4b"
        paths = {"quality-scope.json"}
        self.assertEqual(
            [],
            reviewed_historical_hardening_errors(REPO, hardening, approval, "CAP-01.S04.T03", paths),
        )
        for label, commit, head, task_id, changed in (
            ("commit", "0" * 40, approval, "CAP-01.S04.T03", paths),
            ("head", hardening, hardening, "CAP-01.S04.T03", paths),
            ("task", hardening, approval, "CAP-01.S04.T02", paths),
            ("scope", hardening, approval, "CAP-01.S04.T03", paths | {"tools/ui_change_gate.py"}),
        ):
            with self.subTest(label=label):
                self.assertTrue(reviewed_historical_hardening_errors(REPO, commit, head, task_id, changed))

    def test_application_inventory_hardening_uses_the_exact_reviewed_envelope(self) -> None:
        self.assertEqual(
            {
                "tests/desktop/test_ui_conformance.py",
                "tests/foundation/test_ui_change_gate.py",
                "tools/ui_change_gate.py",
                "tools/ui_conformance.py",
            },
            APPLICATION_INVENTORY_HARDENING_ENVELOPE,
        )

    def test_post_implementation_hardening_requires_independent_changes_requested_record(self) -> None:
        paths = {
            "tests/desktop/test_desktop_app_check.py",
            "tools/ui_change_gate.py",
            "tools/ui_conformance.py",
            "tests/desktop/test_ui_conformance.py",
            "tests/foundation/test_ui_change_gate.py",
            "tools/desktop_app_check.py",
        }
        review = {
            "reviewer": "agent:descartes",
            "result": "changes-requested",
            "reviewed_at": "2026-08-09T08:02:53+00:00",
        }
        backlog: dict[str, Any] = {
            "capabilities": [
                {
                    "slices": [
                        {
                            "tasks": [
                                {
                                    "id": "CAP-01.S01.T01",
                                    "status": "IN_PROGRESS",
                                    "owner": "codex",
                                    "updated_at": "2026-08-09T08:02:53+00:00",
                                    "review": review,
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        previous_backlog = json.loads(json.dumps(backlog))
        previous_task = previous_backlog["capabilities"][0]["slices"][0]["tasks"][0]
        previous_task["status"] = "REVIEW"
        previous_task["review"]["reviewed_at"] = None

        self.assertEqual([], independent_review_hardening_errors(backlog, previous_backlog, "CAP-01.S01.T01", paths))
        review["reviewer"] = "agent:codex"
        self.assertTrue(independent_review_hardening_errors(backlog, previous_backlog, "CAP-01.S01.T01", paths))
        review["reviewer"] = "agent:co-dex"
        self.assertTrue(independent_review_hardening_errors(backlog, previous_backlog, "CAP-01.S01.T01", paths))
        review["reviewer"] = "agent:descartes"
        self.assertTrue(
            independent_review_hardening_errors(
                backlog, previous_backlog, "CAP-01.S01.T01", paths | {"verification-profiles.json"}
            )
        )
        self.assertTrue(
            independent_review_hardening_errors(
                backlog, previous_backlog, "CAP-01.S01.T01", paths | {"tools/taskctl.py"}
            )
        )
        self.assertTrue(
            independent_review_hardening_errors(
                backlog, previous_backlog, "CAP-01.S01.T01", paths | {"apps/desktop/src/App.tsx"}
            )
        )
        previous_task["review"]["reviewed_at"] = review["reviewed_at"]
        self.assertTrue(independent_review_hardening_errors(backlog, previous_backlog, "CAP-01.S01.T01", paths))

    def test_later_ui_task_accepts_only_exact_independently_reviewed_hardening_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            view = root / "apps" / "desktop" / "src" / "View.tsx"
            view.write_text("export const View = () => 'implemented';\n", encoding="utf-8", newline="\n")
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            backlog_path = root / "planning" / "backlog.yaml"
            backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            task = backlog["capabilities"][0]["slices"][0]["tasks"][0]
            task.update(
                {
                    "status": "REVIEW",
                    "updated_at": "2026-08-09T08:00:00+00:00",
                    "review": {"reviewer": None, "result": None, "reviewed_at": None},
                }
            )
            self.write_yaml(backlog_path, backlog)
            self.commit(root, "implement UI")

            task.update(
                {
                    "status": "IN_PROGRESS",
                    "updated_at": "2026-08-09T08:02:53+00:00",
                    "review": {
                        "reviewer": "agent:descartes",
                        "result": "changes-requested",
                        "reviewed_at": "2026-08-09T08:02:53+00:00",
                    },
                }
            )
            self.write_yaml(backlog_path, backlog)
            (root / "docs" / "planning-implementation-plan.md").parent.mkdir(parents=True)
            (root / "docs" / "planning-implementation-plan.md").write_text("reviewed\n", encoding="utf-8")
            (root / "planning" / "status-summary.md").write_text("reviewed\n", encoding="utf-8")
            self.commit(root, "record independent review")

            for relative in (
                "tests/desktop/test_desktop_app_check.py",
                "tests/desktop/test_ui_conformance.py",
                "tests/foundation/test_ui_change_gate.py",
                "tools/desktop_app_check.py",
                "tools/ui_change_gate.py",
                "tools/ui_conformance.py",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("hardened\n", encoding="utf-8", newline="\n")
            head = self.commit(root, "harden reviewed UI boundary")

            result = validate(root, base, head)

        self.assertTrue(result["ok"], result["errors"])

    def git(self, root: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")

    def write_yaml(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8", newline="\n")

    def commit(self, root: Path, message: str) -> str:
        self.git(root, "add", "--all")
        self.git(root, "commit", "-m", message)
        return self.git(root, "rev-parse", "HEAD")

    def reference_package(self, root: Path) -> str:
        manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        hashes = {
            relative: hashlib.sha256((root / "design" / "ui-reference" / relative).read_bytes()).hexdigest()
            for relative in manifest["governed_files"]
        }
        manifest["file_hashes"] = hashes
        self.write_yaml(manifest_path, manifest)
        return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def prepare(self, temporary: str, *, adr_registry: bool = False) -> tuple[Path, str, str]:
        root = Path(temporary) / "repo"
        root.mkdir()
        self.git(root, "init", "-b", "main")
        self.git(root, "config", "user.name", "UI Gate Test")
        self.git(root, "config", "user.email", "ui-gate@example.invalid")
        self.git(root, "config", "core.autocrlf", "false")
        (root / "design").mkdir()
        shutil.copy2(REPO / "design" / "ui-change.schema.json", root / "design" / "ui-change.schema.json")
        shutil.copy2(REPO / "ui-change-policy.json", root / "ui-change-policy.json")
        approval = {
            "reference_id": "REF-1",
            "version": "1",
            "status": "approved",
            "approved_by": "Project-owner direction",
            "approved_at": "2026-08-08",
            "supersedes": "REF-0",
        }
        self.write_yaml(root / "design" / "ui-reference" / "APPROVAL.yaml", approval)
        tokens = root / "design" / "ui-reference" / "assets" / "tokens.css"
        tokens.parent.mkdir(parents=True)
        tokens.write_text(":root { --surface: white; }\n", encoding="utf-8", newline="\n")
        self.write_yaml(
            root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml",
            {
                "reference_id": "REF-1",
                "version": "1",
                "status": "approved",
                "governed_files": ["APPROVAL.yaml", "assets/tokens.css"],
                "file_hashes": {},
            },
        )
        package = self.reference_package(root)
        view = root / "apps" / "desktop" / "src" / "View.tsx"
        view.parent.mkdir(parents=True)
        view.write_text("export const View = () => null;\n", encoding="utf-8", newline="\n")
        self.write_yaml(root / "planning" / "backlog.yaml", {"capabilities": []})
        if adr_registry:
            self.write_yaml(
                root / "planning/backlog.yaml",
                {
                    "capabilities": [
                        {
                            "slices": [
                                {
                                    "tasks": [
                                        {"id": "CAP-01.S01.T01"},
                                    ]
                                }
                            ]
                        }
                    ]
                },
            )
            self.write_json(
                root / "docs/adr/index.json",
                {
                    "schemaVersion": "1.0",
                    "documentType": "architecture-decision-index",
                    "allowedStates": ["Proposed", "Accepted", "Rejected", "Superseded"],
                    "records": [
                        {
                            "id": "ADR-0001",
                            "path": "docs/adr/ADR-0001-existing-authority.md",
                            "title": "Existing authority",
                            "status": "Accepted",
                            "linkedTasks": ["CAP-01.S01.T01"],
                        }
                    ],
                },
            )
            (root / "docs/adr/ADR-0001-existing-authority.md").write_text(
                "# Immutable synthetic accepted authority\n",
                encoding="utf-8",
            )
            shutil.copy2(REPO / "architecture-protected-paths.json", root / "architecture-protected-paths.json")
        base = self.commit(root, "baseline")
        return root, base, package

    def contract(
        self,
        kind: str,
        package: str,
        approval_commit: str,
        approved_by: str = "Project-owner direction",
        previous: str = "REF-0",
        reference_id: str = "REF-1",
        version: str = "1",
        implementation_agent: str = "agent:codex",
        task_id: str = "CAP-01.S01.T01",
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "schemaVersion": "1.0",
            "documentType": "ui-change-evidence",
            "taskId": task_id,
            "changeKind": kind,
            "contractPath": f"artifacts/evidence/ui-change/{task_id}.json",
            "implementationAgent": implementation_agent,
            "changedFiles": ["apps/desktop/src/View.tsx"],
            "reference": {
                "referenceId": reference_id,
                "version": version,
                "packageSha256": package,
                "approvalCommit": approval_commit,
                "approvedBy": approved_by,
                "previousReferenceId": previous,
            },
            "focusedEvidence": [{"command": "test View", "result": "passed", "scope": "approved route behavior"}],
        }
        if kind == "defect-restoration":
            value["restoration"] = {"defect": "route drift", "expectedBehavior": "approved route"}
        else:
            value["implementationScope"] = "approved shell route"
        return value

    def install_contract(
        self,
        root: Path,
        contract: dict[str, object],
        review_gate: str = "agent-review",
        base_sha: str | None = None,
    ) -> None:
        if base_sha is None:
            base_sha = self.git(root, "rev-parse", "HEAD")
        task_id = str(contract["taskId"])
        path = root / "artifacts" / "evidence" / "ui-change" / f"{task_id}.json"
        self.write_json(path, contract)
        reference = contract["reference"]
        assert isinstance(reference, dict)
        experience = {
            "kind": contract["changeKind"],
            "contract_path": contract["contractPath"],
            "reference_id": reference["referenceId"],
            "reference_version": reference["version"],
            "reference_package_sha256": reference["packageSha256"],
            "reference_approval_commit": reference["approvalCommit"],
            "previous_reference_id": reference["previousReferenceId"],
            "implementation_agent": contract["implementationAgent"],
        }
        task = {
            "id": task_id,
            "owner": str(contract["implementationAgent"]).split(":", 1)[1],
            "status": "IN_PROGRESS",
            "review_gate": review_gate,
            "base_sha": base_sha,
            "experience_change": experience,
        }
        backlog = (
            {"capabilities": [], "wave_amendments": [{"id": "W1.A05", "tasks": [task]}]}
            if task_id.startswith("W")
            else {"capabilities": [{"slices": [{"tasks": [task]}]}], "wave_amendments": []}
        )
        self.write_yaml(root / "planning" / "backlog.yaml", backlog)

    def install_reviewed_maintenance(
        self,
        root: Path,
        predecessor: str,
        *,
        reviewer: str = "agent:independent-reviewer",
        implementation_agent: str = "codex",
        mixed_product_path: str | None = None,
    ) -> str:
        maintenance_id = "GOV-MAINT-0001"
        record_path = f"planning/governance-migrations/{maintenance_id}.json"
        review_path = f"planning/governance-migrations/{maintenance_id}.review-R01.json"
        schema_path = root / "design" / "ui-change.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["$comment"] = "reviewed generic pre-implementation maintenance"
        self.write_json(schema_path, schema)
        changed_paths = ["design/ui-change.schema.json", record_path]
        if mixed_product_path is not None:
            view = root / mixed_product_path
            view.parent.mkdir(parents=True, exist_ok=True)
            view.write_text(
                "export const View = () => { throw new Error('laundered'); };\n", encoding="utf-8", newline="\n"
            )
            changed_paths.append(mixed_product_path)
        changed_paths = sorted(changed_paths)
        record: dict[str, Any] = {
            "schemaVersion": "1.0",
            "documentType": "governance-control-maintenance",
            "maintenanceId": maintenance_id,
            "title": "Fixture pre-implementation gate maintenance",
            "status": "candidate",
            "riskTier": 2,
            "humanApprovalRequired": False,
            "implementationAgent": implementation_agent,
            "predecessor": {"commit": predecessor},
            "trigger": {"diagnosis": "fixture control grammar gap"},
            "authority": "Preserve the approved reference and task authority.",
            "intendedDelta": {"changedPaths": changed_paths},
            "verification": {"results": [{"check": "fixture", "result": "passed"}]},
            "rollback": "Return to the frozen predecessor.",
            "reviewAttempts": [],
            "review": None,
        }
        self.write_json(root / record_path, record)
        candidate = self.commit(root, "candidate gate maintenance")
        reviewed_at = "2026-08-30T20:00:00+00:00"
        review_record = {
            "schemaVersion": "1.0",
            "documentType": "governance-control-maintenance-review",
            "maintenanceId": maintenance_id,
            "reviewId": f"{maintenance_id}.R01",
            "reviewedCommit": candidate,
            "reviewer": reviewer,
            "reviewedAt": reviewed_at,
            "disposition": "APPROVED",
            "authorityPreserved": True,
            "candidateChangedPaths": changed_paths,
            "findings": [],
        }
        self.write_json(root / review_path, review_record)
        review_sha = hashlib.sha256((root / review_path).read_bytes()).hexdigest()
        review = {
            "reviewId": f"{maintenance_id}.R01",
            "reviewedCommit": candidate,
            "reviewer": reviewer,
            "reviewedAt": reviewed_at,
            "disposition": "APPROVED",
            "findings": [],
            "path": review_path,
            "sha256": review_sha,
        }
        record.update(status="adopted", reviewAttempts=[review], review=review)
        self.write_json(root / record_path, record)
        self.commit(root, "record independent maintenance review")
        return candidate

    def install_remediated_maintenance(self, root: Path, predecessor: str) -> None:
        maintenance_id = "GOV-MAINT-0001"
        record_path = f"planning/governance-migrations/{maintenance_id}.json"
        schema_path = root / "design" / "ui-change.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["$comment"] = "candidate generic pre-implementation maintenance"
        self.write_json(schema_path, schema)
        changed_paths = sorted(["design/ui-change.schema.json", record_path])
        record: dict[str, Any] = {
            "schemaVersion": "1.0",
            "documentType": "governance-control-maintenance",
            "maintenanceId": maintenance_id,
            "title": "Fixture remediated gate maintenance",
            "status": "candidate",
            "riskTier": 2,
            "humanApprovalRequired": False,
            "implementationAgent": "agent:codex",
            "predecessor": {"commit": predecessor},
            "trigger": {"diagnosis": "fixture control grammar gap"},
            "authority": "Preserve the approved reference and task authority.",
            "intendedDelta": {"changedPaths": changed_paths},
            "verification": {"results": [{"check": "fixture", "result": "passed"}]},
            "rollback": "Return to the frozen predecessor.",
            "reviewAttempts": [],
            "review": None,
        }
        self.write_json(root / record_path, record)
        candidate = self.commit(root, "candidate gate maintenance")

        first_review_path = f"planning/governance-migrations/{maintenance_id}.review-R01.json"
        first_finding = {
            "id": f"{maintenance_id}-R01-F01",
            "severity": "HIGH",
            "blocking": True,
            "title": "Fixture defect",
            "reproduction": "The candidate permits a forbidden identity.",
            "requiredResolution": "Normalize both identities symmetrically.",
        }
        first_review = {
            "schemaVersion": "1.0",
            "documentType": "governance-control-maintenance-review",
            "maintenanceId": maintenance_id,
            "reviewId": f"{maintenance_id}.R01",
            "reviewedCommit": candidate,
            "reviewer": "agent:independent-reviewer",
            "reviewedAt": "2026-08-30T20:00:00+00:00",
            "disposition": "CHANGES_REQUESTED",
            "authorityPreserved": False,
            "candidateChangedPaths": changed_paths,
            "findings": [first_finding],
        }
        self.write_json(root / first_review_path, first_review)
        first_attempt = {
            "reviewId": f"{maintenance_id}.R01",
            "reviewedCommit": candidate,
            "reviewer": "agent:independent-reviewer",
            "reviewedAt": "2026-08-30T20:00:00+00:00",
            "disposition": "CHANGES_REQUESTED",
            "findings": [f"{maintenance_id}-R01-F01"],
            "path": first_review_path,
            "sha256": hashlib.sha256((root / first_review_path).read_bytes()).hexdigest(),
        }
        record.update(status="changes-requested", reviewAttempts=[first_attempt])
        self.write_json(root / record_path, record)
        self.commit(root, "record adverse maintenance review")

        schema["$comment"] = "remediated generic pre-implementation maintenance"
        self.write_json(schema_path, schema)
        record["remediation"] = {
            "resolvedFindingIds": [f"{maintenance_id}-R01-F01"],
            "rootCause": "The candidate normalized only one identity form.",
            "resolution": "Both identity forms now use one canonicalizer.",
            "recurrenceControl": "The real-Git fixture replays the adverse identity.",
        }
        self.write_json(root / record_path, record)
        remediation = self.commit(root, "remediate gate maintenance")

        second_review_path = f"planning/governance-migrations/{maintenance_id}.review-R02.json"
        remediation_paths = sorted(["design/ui-change.schema.json", record_path])
        second_review = {
            "schemaVersion": "1.0",
            "documentType": "governance-control-maintenance-review",
            "maintenanceId": maintenance_id,
            "reviewId": f"{maintenance_id}.R02",
            "reviewedCommit": remediation,
            "reviewer": "agent:second-independent-reviewer",
            "reviewedAt": "2026-08-30T20:05:00+00:00",
            "disposition": "APPROVED",
            "authorityPreserved": True,
            "candidateChangedPaths": remediation_paths,
            "findings": [],
        }
        self.write_json(root / second_review_path, second_review)
        second_attempt = {
            "reviewId": f"{maintenance_id}.R02",
            "reviewedCommit": remediation,
            "reviewer": "agent:second-independent-reviewer",
            "reviewedAt": "2026-08-30T20:05:00+00:00",
            "disposition": "APPROVED",
            "findings": [],
            "path": second_review_path,
            "sha256": hashlib.sha256((root / second_review_path).read_bytes()).hexdigest(),
        }
        record.update(status="adopted", reviewAttempts=[first_attempt, second_attempt], review=second_attempt)
        self.write_json(root / record_path, record)
        self.commit(root, "adopt remediated maintenance")

    def install_provenance_reference_handoff(self, root: Path) -> tuple[str, str]:
        marker = root / "planning" / "review-marker.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("adverse review\n", encoding="utf-8", newline="\n")
        prior_review = self.commit(root, "record adverse review marker")

        approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
        manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
        approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
        proposal_authority = {
            "wave_id": "W1",
            "slice_id": "CAP-03.S05",
            "approved_wave_commit": "1" * 40,
            "slice_plan": "planning/slice-plans/CAP-03/CAP-03.S05-fixture.md",
        }
        approval.update(
            {
                "status": "proposed",
                "approval_kind": "pending-human",
                "approved_by": None,
                "approved_at": None,
                "authority": proposal_authority,
            }
        )
        self.write_yaml(approval_path, approval)
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "proposed"
        self.write_yaml(manifest_path, manifest)
        self.reference_package(root)
        proposal = self.commit(root, "propose corrected reference provenance")

        approval.update(
            {
                "status": "approved",
                "approval_kind": "human",
                "approved_by": "human:repository-owner",
                "approved_at": "2026-09-03T12:00:00+00:00",
                "authority": {**proposal_authority, "proposal_commit": proposal},
            }
        )
        self.write_yaml(approval_path, approval)
        manifest["status"] = "approved"
        self.write_yaml(manifest_path, manifest)
        self.reference_package(root)
        self.commit(root, "approve corrected reference provenance")

        schema_path = root / "design" / "ui-change.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["$comment"] = "remediated after corrected reference provenance"
        self.write_json(schema_path, schema)
        remediation = self.commit(root, "remediate reviewed control")
        return prior_review, remediation

    def test_provenance_reference_handoff_accepts_exact_human_approval_between_review_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, _ = self.prepare(temporary)
            prior_review, remediation = self.install_provenance_reference_handoff(root)

            errors = provenance_reference_handoff_errors(root, prior_review, remediation)

        self.assertEqual([], errors)

    def test_provenance_reference_handoff_rejects_non_governance_intervening_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, _ = self.prepare(temporary)
            marker = root / "planning" / "review-marker.txt"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("adverse review\n", encoding="utf-8", newline="\n")
            prior_review = self.commit(root, "record adverse review marker")
            token = root / "design" / "ui-reference" / "assets" / "tokens.css"
            token.write_text(":root { --surface: red; }\n", encoding="utf-8", newline="\n")
            self.commit(root, "mutate governed product reference")
            schema_path = root / "design" / "ui-change.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["$comment"] = "attempt remediation after unrelated mutation"
            self.write_json(schema_path, schema)
            remediation = self.commit(root, "attempt reviewed control remediation")

            errors = provenance_reference_handoff_errors(root, prior_review, remediation)

        self.assertTrue(any("unauthorized intervening commit" in error for error in errors), errors)

    def test_approved_reference_implementation_and_defect_restoration_pass(self) -> None:
        for kind in ("approved-reference-implementation", "defect-restoration"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                    f"export const View = () => '{kind}';\n", encoding="utf-8", newline="\n"
                )
                contract = self.contract(kind, package, base)
                review_gate = "human-and-agent-review" if kind == "defect-restoration" else "agent-review"
                self.install_contract(root, contract, review_gate=review_gate, base_sha=base)
                head = self.commit(root, kind)

                result = validate(root, base, head)

            self.assertTrue(result["ok"], result["errors"])

    def test_amendment_task_identity_uses_the_same_ui_lineage_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved amendment UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract(
                "approved-reference-implementation",
                package,
                base,
                task_id="W1.A05.T04",
            )
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "implement approved amendment UI")

            result = validate(root, base, head)
            inferred_base = automatic_base(root, head)

        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(base, inferred_base)

    def test_amendment_task_identity_rejects_out_of_range_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'unapproved task namespace';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract(
                "approved-reference-implementation",
                package,
                base,
                task_id="W12.A05.T04",
            )
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "attempt out-of-range amendment UI")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("taskId" in error or "contractPath" in error for error in result["errors"]))

    def test_independently_reviewed_preimplementation_maintenance_can_precede_ui(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            self.install_reviewed_maintenance(root, base)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI after reviewed maintenance';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "implement UI after reviewed maintenance")

            result = validate(root, base, head)

        self.assertTrue(result["ok"], result["errors"])

    def test_independently_reviewed_maintenance_can_repair_the_gate_after_ui(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI before reviewed maintenance';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            self.install_reviewed_maintenance(root, implemented)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertTrue(result["ok"], result["errors"])

    def test_postimplementation_maintenance_still_rejects_self_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI before self-reviewed maintenance';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            self.install_reviewed_maintenance(root, implemented, reviewer="agent:codex")
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("independent" in error for error in result["errors"]))

    def test_postimplementation_maintenance_rejects_mixed_product_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            self.install_reviewed_maintenance(root, implemented, mixed_product_path="apps/desktop/src/View.tsx")
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and "View.tsx" in error for error in result["errors"]), result)

    def test_postimplementation_maintenance_rejects_build_script_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            path = "apps/desktop/scripts/assemble-application.mjs"
            self.install_reviewed_maintenance(root, implemented, mixed_product_path=path)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and path in error for error in result["errors"]), result)

    def test_postimplementation_maintenance_rejects_non_ui_runtime_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            path = "services/runtime/src/session.ts"
            self.install_reviewed_maintenance(root, implemented, mixed_product_path=path)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and path in error for error in result["errors"]), result)

    def test_postimplementation_maintenance_rejects_root_launcher_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            path = "dev.cmd"
            self.install_reviewed_maintenance(root, implemented, mixed_product_path=path)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and path in error for error in result["errors"]), result)

    def test_postimplementation_maintenance_rejects_product_build_tool_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            path = "tools/core_sidecar_build.py"
            self.install_reviewed_maintenance(root, implemented, mixed_product_path=path)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and path in error for error in result["errors"]), result)

    def test_postimplementation_maintenance_rejects_unrelated_maintenance_record_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            path = "planning/governance-migrations/GOV-MAINT-9999.json"
            self.write_json(
                root / path,
                {
                    "schemaVersion": "1.0",
                    "documentType": "governance-control-maintenance",
                    "maintenanceId": "GOV-MAINT-9999",
                    "status": "adopted",
                },
            )
            self.commit(root, "record unrelated adopted maintenance")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            self.install_reviewed_maintenance(root, implemented, mixed_product_path=path)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and path in error for error in result["errors"]), result)

    def test_remediated_preimplementation_maintenance_preserves_adverse_review_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            self.install_remediated_maintenance(root, base)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI after remediated maintenance';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "implement UI after remediated maintenance")

            result = validate(root, base, head)

        self.assertTrue(result["ok"], result["errors"])

    def test_remediated_preimplementation_maintenance_rejects_post_approval_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            self.install_remediated_maintenance(root, base)
            record_path = root / "planning" / "governance-migrations" / "GOV-MAINT-0001.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["remediation"]["resolution"] = "Substituted after approval."
            self.write_json(record_path, record)
            self.commit(root, "substitute approved remediation")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI after substituted maintenance';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "attempt UI after substituted maintenance")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("changed after its final review" in error for error in result["errors"]))

    def test_preimplementation_maintenance_rejects_self_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            self.install_reviewed_maintenance(root, base, reviewer="agent:codex")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI after self review';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "attempt UI after self-reviewed maintenance")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("independent" in error for error in result["errors"]))

    def test_preimplementation_maintenance_rejects_namespaced_implementer_self_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            self.install_reviewed_maintenance(
                root,
                base,
                reviewer="agent:codex",
                implementation_agent="agent:codex",
            )
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI after namespaced self review';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "attempt UI after namespaced self-reviewed maintenance")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("independent" in error for error in result["errors"]))

    def test_ui_change_requires_exact_contract_task_and_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'changed';\n", encoding="utf-8", newline="\n"
            )
            head = self.commit(root, "uncontracted UI")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("exactly one changed UI evidence contract" in error for error in result["errors"]))

    def test_ui_implementation_cannot_weaken_gate_controls_in_same_range(self) -> None:
        for control_path in ("ui-change-policy.json", "architecture-protected-paths.json", "tools/ci_check.py"):
            with self.subTest(control_path=control_path), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                target = root / control_path
                target.parent.mkdir(parents=True, exist_ok=True)
                if control_path != "ui-change-policy.json":
                    target.write_text("governed control\n", encoding="utf-8", newline="\n")
                    base = self.commit(root, f"install {control_path}")
                (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                    "export const View = () => 'changed';\n", encoding="utf-8", newline="\n"
                )
                contract = self.contract("approved-reference-implementation", package, base)
                self.install_contract(root, contract)
                if control_path == "ui-change-policy.json":
                    policy = json.loads(target.read_text(encoding="utf-8"))
                    policy["implementationRoots"] = list(reversed(policy["implementationRoots"]))
                    self.write_json(target, policy)
                else:
                    target.write_text("weakened control\n", encoding="utf-8", newline="\n")
                head = self.commit(root, "weaken gate with UI")

                result = validate(root, base, head)

            self.assertFalse(result["ok"])
            self.assertTrue(any("cannot change its own" in error for error in result["errors"]))

    def test_intentional_change_requires_new_human_approval_before_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
            approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
            approval.update(
                {
                    "reference_id": "REF-2",
                    "version": "2",
                    "approval_kind": "human",
                    "approved_by": "human:owner",
                    "supersedes": "REF-1",
                }
            )
            self.write_yaml(approval_path, approval)
            manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"reference_id": "REF-2", "version": "2"})
            self.write_yaml(manifest_path, manifest)
            package = self.reference_package(root)
            approval_commit = self.commit(root, "human approved reference")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'new design';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract(
                "intentional-design-change",
                package,
                approval_commit,
                approved_by="human:owner",
                previous="REF-1",
                reference_id="REF-2",
                version="2",
            )
            self.install_contract(root, contract, review_gate="human-and-agent-review", base_sha=base)
            head = self.commit(root, "implement approved reference")

            result = validate(root, base, head)
            inferred_base = automatic_base(root, head)

        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(base, inferred_base)

    def test_intentional_change_rejects_same_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'intentional';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract("intentional-design-change", package, base)
            self.install_contract(root, contract, review_gate="human-and-agent-review")
            head = self.commit(root, "intentional without new reference")
            same_reference = validate(root, base, head)

        self.assertFalse(same_reference["ok"])
        self.assertTrue(any("newer approved reference" in error for error in same_reference["errors"]))

    def test_intentional_change_rejects_self_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
            approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
            approval.update(
                {
                    "reference_id": "REF-2",
                    "version": "2",
                    "approval_kind": "human",
                    "approved_by": "human:owner",
                    "supersedes": "REF-1",
                }
            )
            self.write_yaml(approval_path, approval)
            manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"reference_id": "REF-2", "version": "2"})
            self.write_yaml(manifest_path, manifest)
            package = self.reference_package(root)
            approval_commit = self.commit(root, "self approval record")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'self approved';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract(
                "intentional-design-change",
                package,
                approval_commit,
                approved_by="human:owner",
                previous="REF-1",
                reference_id="REF-2",
                version="2",
                implementation_agent="agent:owner",
            )
            self.install_contract(root, contract, review_gate="human-and-agent-review", base_sha=base)
            head = self.commit(root, "implement self-approved design")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("cannot approve its own" in error for error in result["errors"]))

    def test_intentional_change_rejects_approval_and_implementation_in_same_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
            approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
            approval.update(
                {
                    "reference_id": "REF-2",
                    "version": "2",
                    "approval_kind": "human",
                    "approved_by": "human:owner",
                    "supersedes": "REF-1",
                }
            )
            self.write_yaml(approval_path, approval)
            manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"reference_id": "REF-2", "version": "2"})
            self.write_yaml(manifest_path, manifest)
            package = self.reference_package(root)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'same commit';\n", encoding="utf-8", newline="\n"
            )
            approval_commit = self.commit(root, "approve and implement together")
            contract = self.contract(
                "intentional-design-change",
                package,
                approval_commit,
                approved_by="human:owner",
                previous="REF-1",
                reference_id="REF-2",
                version="2",
            )
            self.install_contract(root, contract, review_gate="human-and-agent-review", base_sha=base)
            head = self.commit(root, "record UI lineage")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("strictly precede" in error for error in result["errors"]))

    def test_governed_ui_path_must_be_a_regular_git_blob(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            view = root / "apps" / "desktop" / "src" / "View.tsx"
            view.write_text("design/ui-reference/index.html\n", encoding="utf-8", newline="\n")
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            self.git(root, "add", "--all")
            object_id = self.git(root, "hash-object", "-w", "apps/desktop/src/View.tsx")
            self.git(root, "update-index", "--add", "--cacheinfo", "120000", object_id, "apps/desktop/src/View.tsx")
            self.git(root, "commit", "-m", "redirect UI implementation")
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("regular Git blob" in error for error in result["errors"]))

    def test_automatic_base_rejects_ambiguous_active_experience_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            backlog_path = root / "planning" / "backlog.yaml"
            backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            first = backlog["capabilities"][0]["slices"][0]["tasks"][0]
            second = dict(first)
            second["id"] = "CAP-01.S01.T02"
            backlog["capabilities"][0]["slices"][0]["tasks"].append(second)
            self.write_yaml(backlog_path, backlog)
            head = self.commit(root, "ambiguous UI tasks")

            with self.assertRaisesRegex(ValueError, "ambiguous active UI experience tasks"):
                automatic_base(root, head)

    def test_contract_task_must_be_active_and_bound_to_validated_base(self) -> None:
        for field, value, expected in (
            ("base_sha", None, "base_sha must exactly equal"),
            ("status", "DONE", "must be active"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                view = root / "apps" / "desktop" / "src" / "View.tsx"
                view.write_text("export const View = () => 'changed';\n", encoding="utf-8", newline="\n")
                contract = self.contract("approved-reference-implementation", package, base)
                self.install_contract(root, contract, base_sha=base)
                backlog_path = root / "planning" / "backlog.yaml"
                backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
                backlog["capabilities"][0]["slices"][0]["tasks"][0][field] = value
                self.write_yaml(backlog_path, backlog)
                head = self.commit(root, f"unbound task {field}")

                result = validate(root, base, head)

            self.assertFalse(result["ok"])
            self.assertTrue(any(expected in error for error in result["errors"]))

    def test_self_approval_rejects_trailing_separator_lookalike(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
            approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
            approval.update(
                {
                    "reference_id": "REF-2",
                    "version": "2",
                    "approval_kind": "human",
                    "approved_by": "human:owner.",
                    "supersedes": "REF-1",
                }
            )
            self.write_yaml(approval_path, approval)
            manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"reference_id": "REF-2", "version": "2"})
            self.write_yaml(manifest_path, manifest)
            package = self.reference_package(root)
            approval_commit = self.commit(root, "lookalike approval")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'lookalike';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract(
                "intentional-design-change",
                package,
                approval_commit,
                approved_by="human:owner.",
                previous="REF-1",
                reference_id="REF-2",
                version="2",
                implementation_agent="agent:owner",
            )
            self.install_contract(root, contract, review_gate="human-and-agent-review", base_sha=base)
            head = self.commit(root, "implement lookalike-approved design")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("does not match" in error or "explicit human" in error for error in result["errors"]))

    def test_defect_restoration_requires_human_classification_until_conformance_gate_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'arbitrary new behavior';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract("defect-restoration", package, base)
            self.install_contract(root, contract, review_gate="agent-review", base_sha=base)
            head = self.commit(root, "self-asserted restoration")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("requires human-and-agent-review" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
