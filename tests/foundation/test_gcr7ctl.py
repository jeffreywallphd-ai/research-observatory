from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import gcr7ctl  # noqa: E402


class Gcr7ctlTests(unittest.TestCase):
    def git(self, repo: Path, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def write(self, repo: Path, relative: str, payload: bytes) -> Path:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def write_json(self, repo: Path, relative: str, document: dict) -> Path:
        return self.write(repo, relative, gcr7ctl.json_bytes(document))

    def init_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir(parents=True)
        self.git(repo, "init", "-b", gcr7ctl.BRANCH)
        self.git(repo, "config", "user.email", "gcr7@example.test")
        self.git(repo, "config", "user.name", "GCR7 Test")
        self.git(repo, "config", "core.autocrlf", "false")
        for relative in (gcr7ctl.RUNTIME_SCHEMA_PATH, gcr7ctl.TRANSACTION_SCHEMA_PATH):
            self.write(repo, relative, (REPO / relative).read_bytes())
        self.write(repo, gcr7ctl.APPROVAL_PATH, (REPO / gcr7ctl.APPROVAL_PATH).read_bytes())
        return repo

    def clone_authority_repo(self, root: Path, *, commit: str = gcr7ctl.APPROVAL_COMMIT) -> Path:
        repo = root / "authority"
        bundle = root / "authority.bundle"
        subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={REPO.as_posix()}",
                "-C",
                str(REPO),
                "bundle",
                "create",
                str(bundle),
                gcr7ctl.BRANCH,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "clone", "--branch", gcr7ctl.BRANCH, "--single-branch", str(bundle), str(repo)],
            capture_output=True,
            text=True,
            check=True,
        )
        self.git(repo, "config", "user.email", "gcr7@example.test")
        self.git(repo, "config", "user.name", "GCR7 Test")
        self.git(repo, "config", "core.autocrlf", "true")
        self.git(repo, "checkout", "-B", gcr7ctl.BRANCH, commit)
        (repo / gcr7ctl.BACKLOG_PATH).write_bytes((REPO / gcr7ctl.BACKLOG_PATH).read_bytes())
        self.write(repo, gcr7ctl.TRIGGER_PATH, (REPO / gcr7ctl.TRIGGER_PATH).read_bytes())
        return repo

    def adoption_evidence(self, approved_state: str) -> dict:
        return {
            "schemaVersion": "7.0-control-recovery-adoption-evidence",
            "documentType": "governance-control-recovery-noncircular-adoption-evidence",
            "controlRecoveryId": gcr7ctl.GCR_ID,
            "bootstrapUnit": gcr7ctl.BOOTSTRAP_ID,
            "approvedStateCommit": approved_state,
            "predecessorRevision": 11,
            "successorRevision": 11,
            "supportedControlCeiling": 12,
            "generationNeutral": True,
            "expectedFinalizationPaths": list(gcr7ctl.FINAL_PATHS),
            "checks": [
                {
                    "command": "synthetic P-to-A-to-F construction",
                    "result": "passed",
                    "evidence": "The real Git fixture derives A and F from exact direct-child deltas.",
                }
            ],
            "unverifiedItems": [],
            "ordinaryExecutionAuthority": False,
        }

    def successor_state(self, approved_state: str, evidence_commit: str) -> dict:
        return {
            "schemaVersion": "7.0-control-recovery-state",
            "documentType": "governance-control-recovery-successor-bootstrap-state",
            "controlRecoveryId": gcr7ctl.GCR_ID,
            "bootstrapUnit": gcr7ctl.BOOTSTRAP_ID,
            "status": "HEADROOM_ACTIVATION_FINALIZATION",
            "approval": {
                "path": gcr7ctl.APPROVAL_PATH,
                "sha256": "1" * 64,
                "commit": gcr7ctl.APPROVAL_COMMIT,
            },
            "attempts": {},
            "currentSubmission": None,
            "latestReviewResult": "approved",
            "openFindingIds": [],
            "activation": {
                "approvedStateCommit": approved_state,
                "adoptionEvidence": {
                    "path": gcr7ctl.ADOPTION_EVIDENCE_PATH,
                    "sha256": "2" * 64,
                    "commit": evidence_commit,
                },
                "predecessorRevision": 11,
                "successorRevision": 11,
                "supportedControlCeiling": 12,
                "generationNeutral": True,
                "changedPaths": list(gcr7ctl.FINAL_PATHS),
                "ordinaryExecutionAuthority": False,
            },
        }

    def successor_backlog(self) -> dict:
        document = copy.deepcopy(yaml.safe_load((REPO / gcr7ctl.BACKLOG_PATH).read_bytes()))
        document["control_plane"]["control_generations"].append(
            {
                "id": gcr7ctl.GCR_ID,
                "bootstrap_id": gcr7ctl.BOOTSTRAP_ID,
                "hold_id": gcr7ctl.HOLD_ID,
                "predecessor_revision": 11,
                "successor_revision": 11,
                "supported_control_ceiling": 12,
                "generation_neutral": True,
                "approval_reference": {
                    "path": gcr7ctl.APPROVAL_PATH,
                    "sha256": "1" * 64,
                    "introduction_commit": gcr7ctl.APPROVAL_COMMIT,
                },
                "review_reference": {
                    "path": gcr7ctl.review_path("R01"),
                    "sha256": "2" * 64,
                    "reviewed_state_commit": "3" * 40,
                    "approved_state_commit": "4" * 40,
                },
                "adopted_by": gcr7ctl.ACTOR,
                "adopted_at": "2026-08-26T12:00:00Z",
            }
        )
        return document

    def test_exact_approval_authority_is_ready_and_gcr6_is_inert(self) -> None:
        _approval, packet, introduction = gcr7ctl.load_authority(REPO)
        self.assertEqual(gcr7ctl.APPROVAL_COMMIT, introduction)
        self.assertEqual(gcr7ctl.GCR_ID, packet["controlRecoveryId"])
        self.assertFalse((REPO / "tools/gcr6ctl.py").exists())
        self.assertFalse((REPO / "planning/governance-control-recovery/GCR-0006.B00.state.json").exists())

    def test_runtime_v7_requires_only_p_and_rejects_circular_commit_fields(self) -> None:
        schema = json.loads((REPO / gcr7ctl.RUNTIME_SCHEMA_PATH).read_bytes())
        validator = Draft202012Validator(schema)
        evidence = self.adoption_evidence("a" * 40)
        self.assertEqual([], list(validator.iter_errors(evidence)))
        for forbidden in ("adoptionEvidenceCommit", "finalizationCommit"):
            substituted = copy.deepcopy(evidence)
            substituted[forbidden] = "b" * 40
            self.assertTrue(list(validator.iter_errors(substituted)), forbidden)

    def test_real_git_c_e_s_l_p_a_f_is_externally_derived(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.init_repo(Path(temporary))
            self.write(repo, gcr7ctl.BACKLOG_PATH, b"predecessor: true\n")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "C implementation candidate")
            candidate = self.git(repo, "rev-parse", "HEAD")

            bootstrap_evidence_path = gcr7ctl.evidence_path("R01")
            self.write(repo, bootstrap_evidence_path, b'{"attemptId":"R01"}\n')
            self.git(repo, "add", bootstrap_evidence_path)
            self.git(repo, "commit", "-m", "E bootstrap evidence only")
            bootstrap_evidence = self.git(repo, "rev-parse", "HEAD")
            gcr7ctl.require_exact_commit_delta(
                repo,
                parent=candidate,
                commit=bootstrap_evidence,
                expected={bootstrap_evidence_path: "A"},
                label="synthetic E",
            )

            self.write(repo, gcr7ctl.STATE_PATH, b'{"status":"REVIEW"}\n')
            self.git(repo, "add", gcr7ctl.STATE_PATH)
            self.git(repo, "commit", "-m", "S frozen review state only")
            reviewed_state = self.git(repo, "rev-parse", "HEAD")
            gcr7ctl.require_exact_commit_delta(
                repo,
                parent=bootstrap_evidence,
                commit=reviewed_state,
                expected={gcr7ctl.STATE_PATH: "A"},
                label="synthetic S",
            )

            ledger_path = gcr7ctl.review_path("R01")
            self.write(repo, ledger_path, b'{"result":"approved"}\n')
            self.git(repo, "add", ledger_path)
            self.git(repo, "commit", "-m", "L immutable review ledger only")
            ledger_commit = self.git(repo, "rev-parse", "HEAD")
            gcr7ctl.require_exact_commit_delta(
                repo,
                parent=reviewed_state,
                commit=ledger_commit,
                expected={ledger_path: "A"},
                label="synthetic L",
            )

            self.write(repo, gcr7ctl.STATE_PATH, b'{"status":"APPROVED"}\n')
            self.git(repo, "add", gcr7ctl.STATE_PATH)
            self.git(repo, "commit", "-m", "P approved state projection only")
            approved_state = self.git(repo, "rev-parse", "HEAD")
            gcr7ctl.require_exact_commit_delta(
                repo,
                parent=ledger_commit,
                commit=approved_state,
                expected={gcr7ctl.STATE_PATH: "M"},
                label="synthetic P",
            )

            evidence = self.adoption_evidence(approved_state)
            evidence_payload = gcr7ctl.json_bytes(evidence)
            self.write(repo, gcr7ctl.ADOPTION_EVIDENCE_PATH, evidence_payload)
            self.git(repo, "add", gcr7ctl.ADOPTION_EVIDENCE_PATH)
            self.git(repo, "commit", "-m", "A adoption evidence only")
            evidence_commit = self.git(repo, "rev-parse", "HEAD")
            gcr7ctl.validate_adoption_evidence(
                repo,
                evidence,
                evidence_payload,
                approved_state=approved_state,
                evidence_commit=evidence_commit,
            )

            successor_backlog = self.successor_backlog()
            review_reference = successor_backlog["control_plane"]["control_generations"][-1]["review_reference"]
            review_reference["reviewed_state_commit"] = reviewed_state
            review_reference["approved_state_commit"] = approved_state
            backlog_payload = yaml.safe_dump(successor_backlog, sort_keys=False, width=120).encode()
            state = self.successor_state(approved_state, evidence_commit)
            state["activation"]["adoptionEvidence"]["sha256"] = gcr7ctl.sha256(evidence_payload)
            state_payload = gcr7ctl.json_bytes(state)
            self.write(repo, gcr7ctl.BACKLOG_PATH, backlog_payload)
            self.write(repo, gcr7ctl.STATE_PATH, state_payload)
            self.git(repo, "add", gcr7ctl.BACKLOG_PATH, gcr7ctl.STATE_PATH)
            self.git(repo, "commit", "-m", "F exact two-path finalization")
            finalization = self.git(repo, "rev-parse", "HEAD")

            self.assertNotIn("adoptionEvidenceCommit", evidence)
            self.assertNotIn("finalizationCommit", evidence)
            self.assertNotIn("finalizationCommit", state["activation"])
            self.assertEqual(reviewed_state, review_reference["reviewed_state_commit"])
            self.assertEqual(approved_state, review_reference["approved_state_commit"])
            self.assertNotEqual(ledger_commit, review_reference["approved_state_commit"])
            self.assertEqual(
                finalization,
                gcr7ctl.derive_finalization(
                    repo,
                    evidence_commit=evidence_commit,
                    successor={"backlog": backlog_payload, "state": state_payload},
                ),
            )

    def test_transaction_binds_a_but_never_embeds_f(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.init_repo(Path(temporary))
            predecessor_backlog = b"revision: 11\n"
            predecessor_state = b'{"status":"APPROVED"}\n'
            successor_backlog = b"revision: 11\nheadroom: 12\n"
            successor_state = b'{"status":"HEADROOM_ACTIVATION_FINALIZATION"}\n'
            evidence_reference = {
                "path": gcr7ctl.ADOPTION_EVIDENCE_PATH,
                "sha256": "a" * 64,
                "commit": "b" * 40,
            }
            transaction = gcr7ctl.transaction_document(
                repo,
                predecessor_backlog=predecessor_backlog,
                predecessor_state=predecessor_state,
                successor_backlog=successor_backlog,
                successor_state=successor_state,
                approved_state="c" * 40,
                evidence_reference=evidence_reference,
            )
            gcr7ctl.validate_transaction(repo, transaction)
            self.assertEqual(evidence_reference, transaction["adoptionEvidenceAuthority"])
            self.assertEqual(evidence_reference, transaction["successor"]["adoptionEvidence"])
            self.assertNotIn("finalizationCommit", json.dumps(transaction))

    def test_old_reader_rejects_exact_fourth_generation(self) -> None:
        gcr7ctl.prove_old_reader_fails_closed(REPO, self.successor_backlog())

    def test_neutral_generation_rejects_direct_revision_change_and_gcr6_substitution(self) -> None:
        successor = self.successor_backlog()
        gcr7ctl.validate_boundary(successor, successor=True)
        gcr7ctl.exact_generation(successor)
        for mutation in ("successor_revision", "id"):
            substituted = copy.deepcopy(successor)
            generation = substituted["control_plane"]["control_generations"][-1]
            generation[mutation] = 12 if mutation == "successor_revision" else "GCR-0006"
            with self.assertRaises(SystemExit):
                gcr7ctl.validate_boundary(substituted, successor=True)
            with self.assertRaises(SystemExit):
                gcr7ctl.exact_generation(substituted)

    def test_successor_validation_does_not_schema_check_index_metadata(self) -> None:
        successor = self.successor_backlog()
        state = self.successor_state("a" * 40, "b" * 40)

        gcr7ctl.validate_successor_documents(
            REPO,
            yaml.safe_dump(successor, sort_keys=False).encode(),
            gcr7ctl.json_bytes(state),
        )

        for amendment in successor["wave_amendments"]:
            for task in amendment.get("tasks", []):
                self.assertFalse(any(key.startswith("_") for key in task))

    def test_failed_pre_activation_adoption_is_immutable_and_attempt_scoped(self) -> None:
        failed_evidence_commit = "78fe299fefbee1eaea406e53fed7a5f05a4c18ab"
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.clone_authority_repo(Path(temporary), commit=failed_evidence_commit)
            _approval, packet, _base = gcr7ctl.load_authority(repo)
            state, payload = gcr7ctl.load_state(repo, packet, required=True)

            self.assertIsNotNone(state)
            self.assertIsNotNone(payload)
            self.assertTrue(gcr7ctl.authenticated_failed_pre_activation_adoption(repo, state or {}, payload or b""))

        self.assertEqual(gcr7ctl.ADOPTION_EVIDENCE_PATH, gcr7ctl.adoption_evidence_path("R02"))
        self.assertEqual(
            "artifacts/evidence/governance-control-recovery/GCR-0007.B00.adoption-R03.json",
            gcr7ctl.adoption_evidence_path("R03"),
        )
        with self.assertRaisesRegex(SystemExit, "attempt is invalid"):
            gcr7ctl.adoption_evidence_path("R3")

    def test_failed_pre_activation_resubmit_denies_every_partial_boundary(self) -> None:
        failed_evidence_commit = "78fe299fefbee1eaea406e53fed7a5f05a4c18ab"

        def resubmit_args(repo: Path) -> argparse.Namespace:
            return argparse.Namespace(
                repo=repo,
                agent=gcr7ctl.ACTOR,
                implementation_commit="f" * 40,
                evidence=gcr7ctl.evidence_path("R03"),
            )

        mutations = ("backlog-only", "state-only", "transaction-present", "substituted-evidence", "wrong-path")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                repo = self.clone_authority_repo(Path(temporary), commit=failed_evidence_commit)
                backlog_path = repo / gcr7ctl.BACKLOG_PATH
                state_path = repo / gcr7ctl.STATE_PATH
                evidence_path = repo / gcr7ctl.ADOPTION_EVIDENCE_PATH

                if mutation == "backlog-only":
                    successor = yaml.safe_dump(
                        self.successor_backlog(), sort_keys=False, allow_unicode=True, width=120
                    ).encode()
                    self.write(repo, gcr7ctl.BACKLOG_PATH, successor)
                    self.git(repo, "add", gcr7ctl.BACKLOG_PATH)
                    self.git(repo, "commit", "-m", "partial backlog publication")
                    gcr7ctl.load_authority(repo)
                elif mutation == "state-only":
                    state = json.loads(state_path.read_bytes())
                    state_path.write_bytes((json.dumps(state, indent=4) + "\n").encode())
                    self.git(repo, "add", gcr7ctl.STATE_PATH)
                    self.git(repo, "commit", "-m", "partial state publication")
                elif mutation == "transaction-present":
                    self.write(repo, gcr7ctl.LOCK_PATH, b"partial transaction\n")
                elif mutation == "substituted-evidence":
                    evidence = json.loads(evidence_path.read_bytes())
                    evidence["checks"][0]["evidence"] = "Substituted after the immutable failed attempt."
                    self.write_json(repo, gcr7ctl.ADOPTION_EVIDENCE_PATH, evidence)
                    self.git(repo, "add", gcr7ctl.ADOPTION_EVIDENCE_PATH)
                    self.git(repo, "commit", "-m", "substitute failed adoption evidence")
                else:
                    self.git(
                        repo,
                        "mv",
                        gcr7ctl.ADOPTION_EVIDENCE_PATH,
                        gcr7ctl.adoption_evidence_path("R03"),
                    )
                    self.git(repo, "commit", "-m", "move evidence to wrong attempt path")

                before = {"backlog": backlog_path.read_bytes(), "state": state_path.read_bytes()}
                with self.assertRaises(SystemExit):
                    gcr7ctl.freeze_submission(resubmit_args(repo), remediation=True)
                self.assertEqual(before["backlog"], backlog_path.read_bytes())
                self.assertEqual(before["state"], state_path.read_bytes())

    def test_redirected_parent_is_denied_for_all_controller_reads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            target = repo / "planning"
            target.mkdir()
            child = target / "backlog.yaml"
            child.write_text("safe: true\n", encoding="utf-8")
            real_isjunction = getattr(os.path, "isjunction", lambda _path: False)

            def redirected(path: os.PathLike[str] | str) -> bool:
                return Path(path) == target or real_isjunction(path)

            with (
                patch.object(os.path, "isjunction", redirected, create=True),
                self.assertRaisesRegex(SystemExit, "redirected"),
            ):
                gcr7ctl.guard_repo_path(repo, gcr7ctl.BACKLOG_PATH)

    def test_cleanup_crash_with_committed_f_completes_instead_of_rolling_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            predecessor = {"backlog": b"old backlog\n", "state": b"old state\n"}
            successor = {"backlog": b"new backlog\n", "state": b"new state\n"}
            self.write(repo, gcr7ctl.BACKLOG_PATH, successor["backlog"])
            self.write(repo, gcr7ctl.STATE_PATH, successor["state"])
            self.write(repo, gcr7ctl.LOCK_PATH, b"durable anchor\n")
            with (
                patch.object(gcr7ctl, "require_workspace"),
                patch.object(gcr7ctl.taskctl, "exclusive_backlog_lock", return_value=nullcontext()),
                patch.object(
                    gcr7ctl,
                    "load_anchor",
                    return_value=(predecessor, successor, "p" * 40, "a" * 40),
                ),
                patch.object(gcr7ctl, "derive_finalization", return_value="f" * 40),
            ):
                result = gcr7ctl.recover_transaction(repo, {})
            self.assertEqual(f"COMPLETED_SUCCESSOR:{'f' * 40}", result)
            self.assertEqual([], gcr7ctl.present_transaction_artifacts(repo))
            self.assertEqual(successor["backlog"], (repo / gcr7ctl.BACKLOG_PATH).read_bytes())
            self.assertEqual(successor["state"], (repo / gcr7ctl.STATE_PATH).read_bytes())

    def test_finding_history_is_gapless_and_closures_are_chronological(self) -> None:
        finding = {
            "id": "GCR-0007.B00-R01-F01",
            "severity": "HIGH",
            "criterion": "exact recovery",
            "description": "A blocker.",
            "reproduction": "Reproduce it.",
            "blocking": True,
        }
        state = {
            "attempts": {
                "R01": {"review": {"findings": [finding], "closures": []}},
                "R02": {
                    "review": {
                        "findings": [],
                        "closures": [
                            {
                                "findingId": finding["id"],
                                "disposition": "closed",
                                "evidence": "Replayed and passed.",
                            }
                        ],
                    }
                },
            }
        }
        self.assertEqual(({}, {finding["id"]}), gcr7ctl.fold_findings(state))
        state["attempts"]["R04"] = state["attempts"].pop("R02")
        with self.assertRaisesRegex(SystemExit, "gapped"):
            gcr7ctl.fold_findings(state)

    def test_status_boundary_denies_dirt_transaction_and_substituted_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.clone_authority_repo(Path(temporary))
            _approval, packet, _base = gcr7ctl.load_authority(repo)
            self.assertEqual((None, None), gcr7ctl.validate_current_boundary(repo, packet, state_required=False))

            dirty_path = repo / "docs/README.md"
            original = dirty_path.read_bytes()
            dirty_path.write_bytes(original + b"\nsubstituted\n")
            with self.assertRaisesRegex(SystemExit, "tracked dirt"):
                gcr7ctl.validate_current_boundary(repo, packet, state_required=False)
            dirty_path.write_bytes(original)

            self.write(repo, gcr7ctl.LOCK_PATH, b"partial transaction\n")
            with self.assertRaisesRegex(SystemExit, "explicit recovery"):
                gcr7ctl.validate_current_boundary(repo, packet, state_required=False)
            (repo / gcr7ctl.LOCK_PATH).unlink()

            backlog = repo / gcr7ctl.BACKLOG_PATH
            backlog.write_bytes(backlog.read_bytes() + b"\n# substituted predecessor\n")
            self.git(repo, "add", gcr7ctl.BACKLOG_PATH)
            self.git(repo, "commit", "-m", "substitute predecessor")
            with self.assertRaisesRegex(SystemExit, "neither the exact predecessor nor successor"):
                gcr7ctl.load_authority(repo)

    def test_status_boundary_accepts_exact_frozen_review_state(self) -> None:
        reviewed_state_commit = "04296b53573e940e046259fea589d3c351368cf7"
        with tempfile.TemporaryDirectory() as temporary:
            repo = self.clone_authority_repo(Path(temporary), commit=reviewed_state_commit)
            _approval, packet, _base = gcr7ctl.load_authority(repo)
            state, finalization = gcr7ctl.validate_current_boundary(repo, packet, state_required=True)

        self.assertIsNotNone(state)
        self.assertEqual("REVIEW", (state or {}).get("status"))
        self.assertIsNone(finalization)

    def test_child_process_no_manifest_rollback_faults_are_repeat_recoverable(self) -> None:
        boundaries = (
            "gcr7-backlog-predecessor-restored",
            "gcr7-state-predecessor-restored",
            f"gcr7-cleanup-{Path(gcr7ctl.LOCK_PATH).name}",
        )
        predecessor = {"backlog": b"old backlog\n", "state": b"old state\n"}
        successor = {"backlog": b"new backlog\n", "state": b"new state\n"}
        child = "\n".join(
            [
                "import os, pathlib, sys",
                "from contextlib import nullcontext",
                f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                "import gcr7ctl",
                "repo = pathlib.Path(sys.argv[1])",
                "boundary = sys.argv[2]",
                "predecessor = {'backlog': b'old backlog\\n', 'state': b'old state\\n'}",
                "successor = {'backlog': b'new backlog\\n', 'state': b'new state\\n'}",
                "gcr7ctl.require_workspace = lambda *_args, **_kwargs: None",
                "gcr7ctl.taskctl.exclusive_backlog_lock = lambda *_args, **_kwargs: nullcontext()",
                "gcr7ctl.load_anchor = lambda *_args, **_kwargs: (predecessor, successor, 'p' * 40, 'a' * 40)",
                "gcr7ctl.derive_finalization = lambda *_args, **_kwargs: None",
                "gcr7ctl.git = lambda *_args, **_kwargs: 'a' * 40",
                "def crash(label):",
                "    if label == boundary: os._exit(77)",
                "gcr7ctl.adoption_fault_boundary = crash",
                "gcr7ctl.recover_transaction(repo, {})",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            for boundary in boundaries:
                with self.subTest(boundary=boundary):
                    self.write(repo, gcr7ctl.BACKLOG_PATH, successor["backlog"])
                    self.write(repo, gcr7ctl.STATE_PATH, successor["state"])
                    self.write(repo, gcr7ctl.LOCK_PATH, b"durable anchor\n")
                    result = subprocess.run(
                        [sys.executable, "-c", child, str(repo), boundary],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(77, result.returncode, result.stdout + result.stderr)
                    with (
                        patch.object(gcr7ctl, "require_workspace"),
                        patch.object(gcr7ctl.taskctl, "exclusive_backlog_lock", return_value=nullcontext()),
                        patch.object(
                            gcr7ctl,
                            "load_anchor",
                            return_value=(predecessor, successor, "p" * 40, "a" * 40),
                        ),
                        patch.object(gcr7ctl, "derive_finalization", return_value=None),
                        patch.object(gcr7ctl, "git", return_value="a" * 40),
                    ):
                        disposition = (
                            gcr7ctl.recover_transaction(repo, {})
                            if gcr7ctl.present_transaction_artifacts(repo)
                            else "ABSENT"
                        )
                        self.assertEqual("ABSENT", gcr7ctl.recover_transaction(repo, {}))
                    self.assertIn(disposition, {"ABSENT", "RESTORED_PREDECESSOR"})
                    self.assertEqual(predecessor["backlog"], (repo / gcr7ctl.BACKLOG_PATH).read_bytes())
                    self.assertEqual(predecessor["state"], (repo / gcr7ctl.STATE_PATH).read_bytes())
                    self.assertEqual([], gcr7ctl.present_transaction_artifacts(repo))

    def test_child_process_forward_publication_faults_recover_to_exact_successor(self) -> None:
        boundaries = (
            "gcr7-backlog-published",
            "gcr7-state-published",
            "gcr7-successor-validated",
            "gcr7-successor-directories-durable",
        )
        predecessor = {"backlog": b"old: backlog\n", "state": b'{"old":"state"}\n'}
        successor = {"backlog": b"new: backlog\n", "state": b'{"new":"state"}\n'}
        child = "\n".join(
            [
                "import base64, json, os, pathlib, sys",
                "from contextlib import nullcontext",
                f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                "import gcr7ctl",
                "repo = pathlib.Path(sys.argv[1])",
                "boundary = sys.argv[2]",
                "snapshots = json.loads((repo / '.snapshots.json').read_text())",
                "predecessor = {k: base64.b64decode(v) for k, v in snapshots['predecessor'].items()}",
                "successor = {k: base64.b64decode(v) for k, v in snapshots['successor'].items()}",
                "gcr7ctl.require_workspace = lambda *_args, **_kwargs: None",
                "gcr7ctl.taskctl.exclusive_backlog_lock = lambda *_args, **_kwargs: nullcontext()",
                "gcr7ctl.load_anchor = lambda *_args, **_kwargs: (predecessor, successor, 'p' * 40, 'a' * 40)",
                "gcr7ctl.validate_transaction = lambda *_args, **_kwargs: None",
                "gcr7ctl.validate_successor_documents = lambda *_args, **_kwargs: None",
                "gcr7ctl.derive_finalization = lambda *_args, **_kwargs: None",
                "def crash(label):",
                "    if label == boundary: os._exit(77)",
                "gcr7ctl.adoption_fault_boundary = crash",
                "gcr7ctl.recover_transaction(repo, {})",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, boundary in enumerate(boundaries):
                with self.subTest(boundary=boundary):
                    repo = self.init_repo(root / f"case-{index}")
                    self.write(repo, gcr7ctl.BACKLOG_PATH, predecessor["backlog"])
                    self.write(repo, gcr7ctl.STATE_PATH, predecessor["state"])
                    self.write(repo, gcr7ctl.LOCK_PATH, b"durable anchor\n")
                    evidence_reference = {
                        "path": gcr7ctl.ADOPTION_EVIDENCE_PATH,
                        "sha256": "1" * 64,
                        "commit": "a" * 40,
                    }
                    transaction = gcr7ctl.transaction_document(
                        repo,
                        predecessor_backlog=predecessor["backlog"],
                        predecessor_state=predecessor["state"],
                        successor_backlog=successor["backlog"],
                        successor_state=successor["state"],
                        approved_state="p" * 40,
                        evidence_reference=evidence_reference,
                    )
                    self.write_json(repo, gcr7ctl.TRANSACTION_PATH, transaction)
                    self.write(repo, gcr7ctl.BACKLOG_NEXT_PATH, successor["backlog"])
                    self.write(repo, gcr7ctl.STATE_NEXT_PATH, successor["state"])
                    snapshots = {
                        "predecessor": {
                            key: base64.b64encode(value).decode("ascii") for key, value in predecessor.items()
                        },
                        "successor": {key: base64.b64encode(value).decode("ascii") for key, value in successor.items()},
                    }
                    (repo / ".snapshots.json").write_text(json.dumps(snapshots), encoding="utf-8")
                    result = subprocess.run(
                        [sys.executable, "-c", child, str(repo), boundary],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(77, result.returncode, result.stdout + result.stderr)
                    with (
                        patch.object(gcr7ctl, "require_workspace"),
                        patch.object(gcr7ctl.taskctl, "exclusive_backlog_lock", return_value=nullcontext()),
                        patch.object(
                            gcr7ctl,
                            "load_anchor",
                            return_value=(predecessor, successor, "p" * 40, "a" * 40),
                        ),
                        patch.object(gcr7ctl, "validate_transaction"),
                        patch.object(gcr7ctl, "validate_successor_documents"),
                        patch.object(gcr7ctl, "derive_finalization", return_value=None),
                    ):
                        disposition = gcr7ctl.recover_transaction(repo, {})
                    self.assertEqual("AWAITING_EXACT_FINALIZATION_F", disposition)
                    self.assertEqual(successor["backlog"], (repo / gcr7ctl.BACKLOG_PATH).read_bytes())
                    self.assertEqual(successor["state"], (repo / gcr7ctl.STATE_PATH).read_bytes())

    def test_child_process_preparation_faults_recover_to_an_exact_terminal_pair(self) -> None:
        boundaries = (
            "gcr7-lock-durable",
            "gcr7-backlog-next-durable",
            "gcr7-state-next-durable",
            "gcr7-transaction-durable",
        )
        predecessor = {"backlog": b"old: backlog\n", "state": b'{"old":"state"}\n'}
        successor = {"backlog": b"new: backlog\n", "state": b'{"new":"state"}\n'}
        child = "\n".join(
            [
                "import base64, json, os, pathlib, sys",
                "from contextlib import nullcontext",
                f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                "import gcr7ctl",
                "repo = pathlib.Path(sys.argv[1])",
                "boundary = sys.argv[2]",
                "snapshots = json.loads((repo / '.snapshots.json').read_text())",
                "predecessor = {k: base64.b64decode(v) for k, v in snapshots['predecessor'].items()}",
                "successor = {k: base64.b64decode(v) for k, v in snapshots['successor'].items()}",
                "transaction = json.loads((repo / '.transaction.json').read_text())",
                "gcr7ctl.taskctl.exclusive_backlog_lock = lambda *_args, **_kwargs: nullcontext()",
                "gcr7ctl.validate_transaction = lambda *_args, **_kwargs: None",
                "gcr7ctl.validate_successor_documents = lambda *_args, **_kwargs: None",
                "def crash(label):",
                "    if label == boundary: os._exit(77)",
                "gcr7ctl.adoption_fault_boundary = crash",
                "gcr7ctl.prepare_transaction(repo, anchor={'fixture': True}, transaction=transaction, "
                "predecessor=predecessor, successor=successor)",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, boundary in enumerate(boundaries):
                with self.subTest(boundary=boundary):
                    repo = self.init_repo(root / f"case-{index}")
                    self.write(repo, gcr7ctl.BACKLOG_PATH, predecessor["backlog"])
                    self.write(repo, gcr7ctl.STATE_PATH, predecessor["state"])
                    transaction = gcr7ctl.transaction_document(
                        repo,
                        predecessor_backlog=predecessor["backlog"],
                        predecessor_state=predecessor["state"],
                        successor_backlog=successor["backlog"],
                        successor_state=successor["state"],
                        approved_state="p" * 40,
                        evidence_reference={
                            "path": gcr7ctl.ADOPTION_EVIDENCE_PATH,
                            "sha256": "1" * 64,
                            "commit": "a" * 40,
                        },
                    )
                    snapshots = {
                        name: {key: base64.b64encode(value).decode("ascii") for key, value in pair.items()}
                        for name, pair in (("predecessor", predecessor), ("successor", successor))
                    }
                    (repo / ".snapshots.json").write_text(json.dumps(snapshots), encoding="utf-8")
                    (repo / ".transaction.json").write_text(json.dumps(transaction), encoding="utf-8")
                    result = subprocess.run(
                        [sys.executable, "-c", child, str(repo), boundary],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(77, result.returncode, result.stdout + result.stderr)
                    with (
                        patch.object(gcr7ctl, "require_workspace"),
                        patch.object(gcr7ctl.taskctl, "exclusive_backlog_lock", return_value=nullcontext()),
                        patch.object(
                            gcr7ctl,
                            "load_anchor",
                            return_value=(predecessor, successor, "p" * 40, "a" * 40),
                        ),
                        patch.object(gcr7ctl, "validate_transaction"),
                        patch.object(gcr7ctl, "validate_successor_documents"),
                        patch.object(gcr7ctl, "derive_finalization", return_value=None),
                        patch.object(gcr7ctl, "git", return_value="a" * 40),
                    ):
                        disposition = gcr7ctl.recover_transaction(repo, {})
                    terminal = {
                        "backlog": (repo / gcr7ctl.BACKLOG_PATH).read_bytes(),
                        "state": (repo / gcr7ctl.STATE_PATH).read_bytes(),
                    }
                    self.assertIn(terminal, (predecessor, successor))
                    if boundary == "gcr7-transaction-durable":
                        self.assertEqual("AWAITING_EXACT_FINALIZATION_F", disposition)
                        self.assertEqual(successor, terminal)
                    else:
                        self.assertEqual("RESTORED_PREDECESSOR", disposition)
                        self.assertEqual(predecessor, terminal)

    def test_child_process_cleanup_faults_preserve_committed_successor(self) -> None:
        boundaries = tuple(
            f"gcr7-cleanup-{Path(relative).name}"
            for relative in (
                gcr7ctl.TRANSACTION_PATH,
                gcr7ctl.BACKLOG_NEXT_PATH,
                gcr7ctl.STATE_NEXT_PATH,
                gcr7ctl.LOCK_PATH,
            )
        )
        predecessor = {"backlog": b"old: backlog\n", "state": b'{"old":"state"}\n'}
        successor = {"backlog": b"new: backlog\n", "state": b'{"new":"state"}\n'}
        child = "\n".join(
            [
                "import base64, json, os, pathlib, sys",
                "from contextlib import nullcontext",
                f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                "import gcr7ctl",
                "repo = pathlib.Path(sys.argv[1])",
                "boundary = sys.argv[2]",
                "snapshots = json.loads((repo / '.snapshots.json').read_text())",
                "predecessor = {k: base64.b64decode(v) for k, v in snapshots['predecessor'].items()}",
                "successor = {k: base64.b64decode(v) for k, v in snapshots['successor'].items()}",
                "gcr7ctl.require_workspace = lambda *_args, **_kwargs: None",
                "gcr7ctl.taskctl.exclusive_backlog_lock = lambda *_args, **_kwargs: nullcontext()",
                "gcr7ctl.load_anchor = lambda *_args, **_kwargs: (predecessor, successor, 'p' * 40, 'a' * 40)",
                "gcr7ctl.validate_transaction = lambda *_args, **_kwargs: None",
                "gcr7ctl.validate_successor_documents = lambda *_args, **_kwargs: None",
                "gcr7ctl.derive_finalization = lambda *_args, **_kwargs: 'f' * 40",
                "def crash(label):",
                "    if label == boundary: os._exit(77)",
                "gcr7ctl.adoption_fault_boundary = crash",
                "gcr7ctl.recover_transaction(repo, {})",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, boundary in enumerate(boundaries):
                with self.subTest(boundary=boundary):
                    repo = self.init_repo(root / f"case-{index}")
                    self.write(repo, gcr7ctl.BACKLOG_PATH, successor["backlog"])
                    self.write(repo, gcr7ctl.STATE_PATH, successor["state"])
                    self.write(repo, gcr7ctl.LOCK_PATH, b"durable anchor\n")
                    transaction = gcr7ctl.transaction_document(
                        repo,
                        predecessor_backlog=predecessor["backlog"],
                        predecessor_state=predecessor["state"],
                        successor_backlog=successor["backlog"],
                        successor_state=successor["state"],
                        approved_state="p" * 40,
                        evidence_reference={
                            "path": gcr7ctl.ADOPTION_EVIDENCE_PATH,
                            "sha256": "1" * 64,
                            "commit": "a" * 40,
                        },
                    )
                    self.write_json(repo, gcr7ctl.TRANSACTION_PATH, transaction)
                    self.write(repo, gcr7ctl.BACKLOG_NEXT_PATH, successor["backlog"])
                    self.write(repo, gcr7ctl.STATE_NEXT_PATH, successor["state"])
                    snapshots = {
                        name: {key: base64.b64encode(value).decode("ascii") for key, value in pair.items()}
                        for name, pair in (("predecessor", predecessor), ("successor", successor))
                    }
                    (repo / ".snapshots.json").write_text(json.dumps(snapshots), encoding="utf-8")
                    result = subprocess.run(
                        [sys.executable, "-c", child, str(repo), boundary],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(77, result.returncode, result.stdout + result.stderr)
                    with (
                        patch.object(gcr7ctl, "require_workspace"),
                        patch.object(gcr7ctl.taskctl, "exclusive_backlog_lock", return_value=nullcontext()),
                        patch.object(
                            gcr7ctl,
                            "load_anchor",
                            return_value=(predecessor, successor, "p" * 40, "a" * 40),
                        ),
                        patch.object(gcr7ctl, "derive_finalization", return_value="f" * 40),
                    ):
                        disposition = (
                            gcr7ctl.recover_transaction(repo, {})
                            if gcr7ctl.present_transaction_artifacts(repo)
                            else "ABSENT"
                        )
                    self.assertIn(disposition, {"ABSENT", f"COMPLETED_SUCCESSOR:{'f' * 40}"})
                    self.assertEqual(successor["backlog"], (repo / gcr7ctl.BACKLOG_PATH).read_bytes())
                    self.assertEqual(successor["state"], (repo / gcr7ctl.STATE_PATH).read_bytes())
                    self.assertEqual([], gcr7ctl.present_transaction_artifacts(repo))


if __name__ == "__main__":
    unittest.main()
