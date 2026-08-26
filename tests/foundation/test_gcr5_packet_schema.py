from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path
from typing import Any, ClassVar

import yaml
from jsonschema import Draft202012Validator

from tools import taskctl

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = ROOT / "planning/governance-control-recovery/governance-control-recovery-runtime.v5.schema.json"
TRANSACTION_PATH = ROOT / "planning/governance-control-recovery/governance-control-recovery-transaction.v5.schema.json"
SEVEN_PATHS = [
    "docs/planning-implementation-plan.md",
    "planning/backlog.yaml",
    "planning/status-summary.md",
    "planning/review-site/manifest.json",
    "planning/review-site/recoveries/GRR-0002.html",
    "planning/review-site/recoveries/index.html",
    "planning/review-site/waves/W1.html",
]
ZERO_COMMIT = "0" * 40
ONE_COMMIT = "1" * 40
ZERO_SHA = "0" * 64


class Gcr5PacketSchemaTests(unittest.TestCase):
    runtime: ClassVar[Draft202012Validator]
    transaction: ClassVar[Draft202012Validator]

    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = Draft202012Validator(json.loads(RUNTIME_PATH.read_text(encoding="utf-8")))
        cls.transaction = Draft202012Validator(json.loads(TRANSACTION_PATH.read_text(encoding="utf-8")))

    def assert_rejected(self, validator: Draft202012Validator, document: dict[str, Any]) -> None:
        self.assertTrue(list(validator.iter_errors(document)))

    def valid_application_evidence(self) -> dict[str, Any]:
        return {
            "schemaVersion": "5.0-control-recovery-application-evidence",
            "documentType": "governance-control-recovery-review-transition-evidence",
            "controlRecoveryId": "GCR-0005",
            "bootstrapUnit": "GCR-0005.B00",
            "approvedStateCommit": ZERO_COMMIT,
            "applicationBaseCommit": ONE_COMMIT,
            "projectionTimestamp": "2026-08-26T02:15:00+00:00",
            "backlogBeforeRawSha256": "431ac0390c7aa1b1be229f741cea0b00fb73cfd24713fdcb0e8cc6a13595c7a1",
            "backlogBeforeCanonicalSha256": "3ffa93f894b5b63cbefd11d8b058eddf4deda96069aa03c9bb15bc116bc691cb",
            "backlogAfterRawSha256": "86c40fde359bd64f0979e0a5e982fdfa13de3823b5b77afd1e5341abcc726798",
            "backlogAfterCanonicalSha256": "86c40fde359bd64f0979e0a5e982fdfa13de3823b5b77afd1e5341abcc726798",
            "ledger": {
                "path": "planning/governance-recovery-approvals/GRR-0002.B02.review-R01.json",
                "sha256": "4b92f7b3a6a621e25c919f8571d7a87617966ae76a7dcbc4f3dcdd05af563e09",
                "commit": "8b784cabc5d5d996c00fd2fbcc8f22a1ad05b5bb",
                "reviewedStateCommit": "962f92ff831c9a3d87a7d6ba796c8194e70b6c2c",
                "candidateCommit": "d363c04c385251a5d789a0313e173342e7e0ae3e",
                "evidenceSha256": "77cdc545de58ef9d7237a8ba1c32969a449a87216479fd104e5649e6b5958595",
                "result": "changes-requested",
            },
            "ledgerBytePreserved": True,
            "openFindingIds": ["GRR-0002.B02-R01-F01"],
            "changedPaths": SEVEN_PATHS,
            "checks": [{"command": "fixture", "result": "passed", "summary": "exact"}],
            "unverifiedItems": [],
            "ordinaryExecutionAuthority": False,
        }

    def valid_state(self) -> dict[str, Any]:
        return {
            "schemaVersion": "5.0-control-recovery-state",
            "documentType": "governance-control-recovery-bootstrap-state",
            "controlRecoveryId": "GCR-0005",
            "bootstrapUnit": "GCR-0005.B00",
            "status": "REVIEW",
            "approval": {
                "path": "planning/governance-control-recovery/GCR-0005.approval.json",
                "sha256": ZERO_SHA,
                "commit": ZERO_COMMIT,
            },
            "attempts": [
                {
                    "submission": {
                        "attemptId": "R01",
                        "submittedBy": "codex",
                        "submittedAt": "2026-08-26T02:15:00+00:00",
                        "candidateCommit": ONE_COMMIT,
                        "baseCommit": ZERO_COMMIT,
                        "branch": "codex/w1-windows-local-runtime",
                        "evidence": {
                            "path": "artifacts/evidence/governance-control-recovery/GCR-0005.B00.R01.json",
                            "sha256": ZERO_SHA,
                            "commit": ONE_COMMIT,
                        },
                        "priorAttemptId": None,
                        "openFindingIds": [],
                        "rootCauseAnalysis": None,
                    },
                    "review": None,
                    "ledger": None,
                    "findings": [],
                    "closures": [],
                }
            ],
            "currentSubmission": {"attemptId": "R01", "candidateCommit": ONE_COMMIT, "evidenceSha256": ZERO_SHA},
            "application": None,
        }

    def valid_transaction(self) -> dict[str, Any]:
        reference = {
            "path": "planning/governance-control-recovery/GCR-0005.packet.json",
            "sha256": ZERO_SHA,
            "commit": ZERO_COMMIT,
        }
        return {
            "schemaVersion": "5.0-control-recovery-transaction",
            "documentType": "governance-control-recovery-review-transition-transaction",
            "controlRecoveryId": "GCR-0005",
            "bootstrapUnit": "GCR-0005.B00",
            "status": "PREPARED",
            "actor": "codex",
            "branch": "codex/w1-windows-local-runtime",
            "packetAuthority": reference,
            "approvalAuthority": {**reference, "path": "planning/governance-control-recovery/GCR-0005.approval.json"},
            "approvedStateAuthority": {
                **reference,
                "path": "planning/governance-control-recovery/GCR-0005.B00.state.json",
                "status": "APPROVED",
            },
            "applicationEvidenceAuthority": {
                **reference,
                "path": "artifacts/evidence/governance-control-recovery/GCR-0005.B00.application.json",
            },
            "hold": {"id": "HOLD-W1-GRR-0002", "status": "ACTIVE", "controlRevision": 11, "minimumToolRevision": 11},
            "witness": {
                "path": "artifacts/evidence/W1.A04.B00.json",
                "sha256": "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c",
                "untracked": True,
                "unstaged": True,
                "executionAuthority": False,
            },
            "reviewedSubmission": {
                "reviewedStateCommit": "962f92ff831c9a3d87a7d6ba796c8194e70b6c2c",
                "candidateCommit": "d363c04c385251a5d789a0313e173342e7e0ae3e",
                "evidenceSha256": "77cdc545de58ef9d7237a8ba1c32969a449a87216479fd104e5649e6b5958595",
                "attemptId": "R01",
                "status": "REVIEW",
            },
            "lockPath": "planning/governance-control-recovery/GCR-0005.B00.application.lock",
            "transactionPath": "planning/governance-control-recovery/GCR-0005.B00.application-transaction.json",
            "backlogPath": "planning/backlog.yaml",
            "backlogNextPath": "planning/governance-control-recovery/GCR-0005.B00.backlog.next",
            "backlogBeforeRawSha256": "431ac0390c7aa1b1be229f741cea0b00fb73cfd24713fdcb0e8cc6a13595c7a1",
            "backlogBeforeCanonicalSha256": "3ffa93f894b5b63cbefd11d8b058eddf4deda96069aa03c9bb15bc116bc691cb",
            "backlogAfterRawSha256": "86c40fde359bd64f0979e0a5e982fdfa13de3823b5b77afd1e5341abcc726798",
            "backlogAfterCanonicalSha256": "86c40fde359bd64f0979e0a5e982fdfa13de3823b5b77afd1e5341abcc726798",
            "ledger": {
                "path": "planning/governance-recovery-approvals/GRR-0002.B02.review-R01.json",
                "sha256": "4b92f7b3a6a621e25c919f8571d7a87617966ae76a7dcbc4f3dcdd05af563e09",
                "commit": "8b784cabc5d5d996c00fd2fbcc8f22a1ad05b5bb",
                "reviewedStateCommit": "962f92ff831c9a3d87a7d6ba796c8194e70b6c2c",
                "result": "changes-requested",
                "openFindingIds": ["GRR-0002.B02-R01-F01"],
                "bytePreserved": True,
            },
            "projectionTimestamp": "2026-08-26T02:15:00+00:00",
            "generatedPaths": [path for path in SEVEN_PATHS if path != "planning/backlog.yaml"],
            "cas": {"rawBytes": True, "canonicalContent": True, "staleWriterDenied": True, "exactSuccessorOnly": True},
            "durability": {
                "exclusiveLock": True,
                "flushSuccessor": True,
                "flushManifest": True,
                "replaceExistingWriteThrough": True,
                "flushBacklog": True,
                "flushGeneratedFiles": True,
                "flushDirectories": True,
            },
            "recovery": {
                "allowedTerminalStates": ["EXACT_PREDECESSOR", "EXACT_SUCCESSOR"],
                "dirtyWorkspaceDenied": True,
                "staleOrSubstitutedDenied": True,
                "idempotent": True,
                "cleanupAfterValidationOnly": True,
            },
            "finalization": {
                "directChildOfApplicationEvidence": True,
                "exactChangedPaths": SEVEN_PATHS,
                "ledgerUnchanged": True,
                "ordinaryExecutionStillDenied": True,
            },
            "publicationOrder": [
                "exclusive-lock",
                "durable-successor",
                "durable-manifest",
                "replace-backlog",
                "generate-views",
                "validate-exact-state",
                "flush",
                "commit-direct-child",
                "cleanup",
            ],
            "ordinaryExecutionAuthority": False,
        }

    def test_runtime_rejects_forged_history_and_application(self) -> None:
        state = self.valid_state()
        self.assertFalse(list(self.runtime.iter_errors(state)))
        forged = copy.deepcopy(state)
        forged["attempts"] = [{"forged": True}]
        self.assert_rejected(self.runtime, forged)
        forged = copy.deepcopy(state)
        forged["currentSubmission"] = {"candidateCommit": "wrong"}
        self.assert_rejected(self.runtime, forged)
        forged = copy.deepcopy(state)
        forged["application"] = {"ordinaryExecutionAuthority": True}
        self.assert_rejected(self.runtime, forged)

    def test_exact_ledger_derived_successor_hash_is_reproducible(self) -> None:
        backlog_path = ROOT / "planning/backlog.yaml"
        raw = backlog_path.read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "431ac0390c7aa1b1be229f741cea0b00fb73cfd24713fdcb0e8cc6a13595c7a1",
        )
        self.assertEqual(
            hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
            "3ffa93f894b5b63cbefd11d8b058eddf4deda96069aa03c9bb15bc116bc691cb",
        )
        data = yaml.safe_load(raw)
        hold = next(item for item in data["control_plane"]["recovery_holds"] if item["id"] == "HOLD-W1-GRR-0002")
        bootstrap = next(item for item in hold["supplements"] if item["id"] == "GRR-0002.S02")["bootstrap"]
        ledger_path = ROOT / "planning/governance-recovery-approvals/GRR-0002.B02.review-R01.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        review = {
            "reviewer": ledger["reviewer"],
            "result": ledger["result"],
            "reviewed_at": "2026-08-26T02:15:00+00:00",
            "notes": ledger["notes"],
        }
        bootstrap["attempts"].append(
            {
                "id": bootstrap["current_submission"]["attempt_id"],
                "implementer": bootstrap["implementer"],
                "implementation_commit": bootstrap["implementation_commit"],
                "submission_branch": bootstrap["submission_branch"],
                "evidence": copy.deepcopy(bootstrap["evidence"]),
                "review": review,
                "ledger": {
                    "path": "planning/governance-recovery-approvals/GRR-0002.B02.review-R01.json",
                    "sha256": "4b92f7b3a6a621e25c919f8571d7a87617966ae76a7dcbc4f3dcdd05af563e09",
                },
            }
        )
        bootstrap["status"] = "CHANGES_REQUESTED"
        bootstrap["review"] = review
        bootstrap["current_submission"] = None
        successor = yaml.safe_dump(
            taskctl.serializable_backlog(data),
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ).encode()
        self.assertEqual(
            hashlib.sha256(successor).hexdigest(),
            "86c40fde359bd64f0979e0a5e982fdfa13de3823b5b77afd1e5341abcc726798",
        )

    def test_application_evidence_rejects_substituted_authority_and_scope(self) -> None:
        evidence = self.valid_application_evidence()
        self.assertFalse(list(self.runtime.iter_errors(evidence)))
        for path, value in (
            (("ledger", "path"), "planning/backlog.yaml"),
            (("ledger", "sha256"), ZERO_SHA),
            (("ledger", "result"), "approved"),
            (("openFindingIds",), []),
            (("changedPaths",), ["tools/gcr5ctl.py"]),
            (("backlogBeforeCanonicalSha256",), ZERO_SHA),
            (("backlogAfterRawSha256",), ZERO_SHA),
        ):
            variant = copy.deepcopy(evidence)
            target = variant
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            self.assert_rejected(self.runtime, variant)

    def test_transaction_rejects_substituted_hashes_paths_and_safety_contracts(self) -> None:
        transaction = self.valid_transaction()
        self.assertFalse(list(self.transaction.iter_errors(transaction)))
        mutations: tuple[tuple[tuple[str, ...], Any], ...] = (
            (("backlogBeforeRawSha256",), ZERO_SHA),
            (("backlogBeforeCanonicalSha256",), ZERO_SHA),
            (("backlogAfterRawSha256",), ZERO_SHA),
            (("ledger", "path"), "planning/backlog.yaml"),
            (("ledger", "openFindingIds"), []),
            (("hold", "id"), "HOLD-W1-GRR-0001"),
            (("witness", "sha256"), ZERO_SHA),
            (("generatedPaths",), ["planning/status-summary.md"]),
            (("finalization", "exactChangedPaths"), ["planning/backlog.yaml"]),
            (("recovery", "dirtyWorkspaceDenied"), False),
            (("ordinaryExecutionAuthority",), True),
        )
        for path, value in mutations:
            variant = copy.deepcopy(transaction)
            target = variant
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            self.assert_rejected(self.transaction, variant)


if __name__ == "__main__":
    unittest.main()
