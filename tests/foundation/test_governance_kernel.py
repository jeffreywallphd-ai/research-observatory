from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import governance_kernel  # noqa: E402


class PausedAmendmentCorrectionTests(unittest.TestCase):
    def pair(self) -> tuple[dict, dict]:
        parent: dict[str, Any] = {
            "id": "W2.A03",
            "target_wave": "W2",
            "change_request_id": "ECR-0100",
            "approval_reference": {
                "path": "planning/wave-amendment-approvals/W2.A03.json",
                "sha256": "a" * 64,
                "introduction_commit": "b" * 40,
            },
            "lifecycle": {"status": "PAUSED", "history": [{"id": "E01", "status": "PAUSED"}]},
            "campaign": {"status": "PAUSED", "lease": None},
            "tasks": [{"id": "W2.A03.T01", "status": "BLOCKED", "lease": None}],
        }
        binding = {
            "id": parent["id"],
            "changeRequestId": parent["change_request_id"],
            "status": "PAUSED",
            "packetCommit": "c" * 40,
            "approvalReference": {
                "path": parent["approval_reference"]["path"],
                "sha256": "a" * 64,
                "introductionCommit": "b" * 40,
            },
            "effectiveStateCommit": "d" * 40,
            "recordSha256": hashlib.sha256(
                json.dumps(parent, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "returnPolicy": "paused-predecessor",
        }
        child = {"id": "W2.A04", "target_wave": "W2", "correction": binding, "lifecycle": {"status": "APPROVED"}}
        return parent, child

    def test_pending_entry_execution_and_return_preserve_one_owner(self) -> None:
        parent, child = self.pair()
        before = copy.deepcopy([parent, child])
        projection = governance_kernel.project_paused_corrections([parent, child])
        self.assertEqual("W2.A03", projection[0]["holdOwner"])
        self.assertEqual("pending-entry", projection[0]["phase"])
        self.assertEqual(before, [parent, child])
        for status in ("MATERIALIZED", "ACTIVE", "PAUSED", "REVIEW", "BLOCKED"):
            child["lifecycle"]["status"] = status
            projection = governance_kernel.project_paused_corrections([parent, child])
            self.assertEqual("W2.A04", projection[0]["holdOwner"])
            self.assertTrue(projection[0]["parentFrozen"])
        child["lifecycle"]["status"] = "ADOPTED"
        projection = governance_kernel.project_paused_corrections([parent, child])
        self.assertEqual("W2.A03", projection[0]["holdOwner"])
        self.assertFalse(projection[0]["parentFrozen"])
        parent["lifecycle"]["status"] = "ACTIVE"
        self.assertEqual("W2.A03", governance_kernel.project_paused_corrections([parent, child])[0]["holdOwner"])
        parent["lifecycle"]["status"] = "ADOPTED"
        self.assertIsNone(governance_kernel.project_paused_corrections([parent, child])[0]["holdOwner"])

    def test_active_lease_review_and_changed_parent_fail_even_with_rehashed_state(self) -> None:
        for field, value in (("status", "IN_PROGRESS"), ("status", "REVIEW"), ("lease", {"claimed_by": "x"})):
            parent, child = self.pair()
            parent["tasks"][0][field] = value
            child["correction"]["recordSha256"] = hashlib.sha256(
                json.dumps(parent, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            with self.assertRaises(governance_kernel.KernelValidationError):
                governance_kernel.project_paused_corrections([parent, child])
        parent, child = self.pair()
        parent["tasks"][0]["status"] = "READY"
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "record"):
            governance_kernel.project_paused_corrections([parent, child])

    def test_wrong_parent_nested_relation_and_unsupported_disposal_fail(self) -> None:
        for mutation in ("wrong-parent", "nested", "disposal", "bad-approval", "bad-return"):
            parent, child = self.pair()
            if mutation == "wrong-parent":
                child["correction"]["id"] = "W2.A02"
            elif mutation == "nested":
                parent["correction"] = copy.deepcopy(child["correction"])
            elif mutation == "disposal":
                child["lifecycle"]["status"] = "WITHDRAWN"
            elif mutation == "bad-approval":
                child["correction"]["approvalReference"]["sha256"] = "f" * 64
            else:
                child["correction"]["returnPolicy"] = "wave"
            with self.subTest(mutation=mutation), self.assertRaises(governance_kernel.KernelValidationError):
                governance_kernel.project_paused_corrections([parent, child])

    def test_no_opt_in_relation_does_not_change_legacy_projection(self) -> None:
        parent, _ = self.pair()
        self.assertEqual([], governance_kernel.project_paused_corrections([parent]))


class GovernanceKernelTests(unittest.TestCase):
    def event(
        self,
        sequence: int,
        previous_hash: str,
        *,
        category: str = "task",
    ) -> governance_kernel.GovernanceEvent:
        action = "claim-wave-task" if category == "task" else "inspect-active-wave"
        risk_tier = 1 if category == "task" else 0
        return governance_kernel.build_next_action_event(
            sequence=sequence,
            previous_event_hash=previous_hash,
            subject=f"{category}/fixture",
            source={"path": "planning/backlog.yaml", "sha256": "1" * 64},
            program={
                "state": "ACTIVE_WAVE",
                "currentWave": "W1",
                "blockedWave": None,
                "nextGate": "G1",
            },
            decision={
                "category": category,
                "action": action,
                "target": "fixture",
                "summary": "Inspect the deterministic fixture.",
                "command": None,
                "riskTier": risk_tier,
                "executableNow": True,
                "approvalRequired": False,
                "effect": "read-only" if risk_tier == 0 else "mutation-template",
            },
            legacy_category=category,
            shadow_agreement=True,
        )

    def test_event_hash_and_projection_are_deterministic(self) -> None:
        first = self.event(1, governance_kernel.GENESIS_HASH)
        second = self.event(1, governance_kernel.GENESIS_HASH)

        self.assertEqual(first, second)
        self.assertEqual(governance_kernel.document_hash(first, "eventHash"), first["eventHash"])
        projection = governance_kernel.verify_and_project([first])
        self.assertEqual(1, projection["throughSequence"])
        self.assertEqual(first["eventHash"], projection["throughEventHash"])
        self.assertEqual(first["payload"]["decision"], projection["decision"])

    def test_canonical_domain_rejects_python_key_and_container_aliases(self) -> None:
        self.assertNotEqual(
            governance_kernel.canonical_bytes({"1": "string-key"}),
            governance_kernel.canonical_bytes({"1": "different-value"}),
        )
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "non-string key"):
            governance_kernel.canonical_bytes({1: "integer-key"})
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "non-JSON value"):
            governance_kernel.canonical_bytes({"items": ("tuple",)})

    def test_checkpoint_plus_tail_matches_full_replay(self) -> None:
        first = self.event(1, governance_kernel.GENESIS_HASH)
        second = self.event(2, first["eventHash"], category="wave")
        full = governance_kernel.verify_and_project([first, second])
        checkpoint = governance_kernel.build_checkpoint(governance_kernel.verify_and_project([first]))
        tail = governance_kernel.verify_and_project(
            [second],
            checkpoint=checkpoint,
            trusted_checkpoint_hash=checkpoint["checkpointHash"],
        )

        self.assertEqual(full, tail)
        self.assertEqual(2, tail["observationCount"])
        self.assertEqual("wave", tail["decision"]["category"])

    def test_tamper_unknown_capability_gap_and_fork_fail_closed(self) -> None:
        first = self.event(1, governance_kernel.GENESIS_HASH)

        tampered = copy.deepcopy(first)
        tampered["payload"]["decision"]["summary"] = "Changed without rehashing."
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "hash differs"):
            governance_kernel.validate_event(tampered)

        unsupported = copy.deepcopy(first)
        unsupported["capabilities"].append("unknown.protocol.v1")
        unsupported["eventHash"] = governance_kernel.document_hash(unsupported, "eventHash")
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "Unsupported"):
            governance_kernel.validate_event(unsupported)

        downgraded = copy.deepcopy(first)
        downgraded["capabilities"].remove("invariant.advisory-only.v1")
        downgraded["eventHash"] = governance_kernel.document_hash(downgraded, "eventHash")
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "missing required"):
            governance_kernel.validate_event(downgraded)

        gap = self.event(3, first["eventHash"])
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "sequence gap"):
            governance_kernel.verify_and_project([first, gap])

        fork = self.event(2, "f" * 64)
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "ancestry differs"):
            governance_kernel.verify_and_project([first, fork])

    def test_rehashed_nested_contract_substitution_fails_closed(self) -> None:
        event = self.event(1, governance_kernel.GENESIS_HASH)

        malformed_decision = copy.deepcopy(event)
        malformed_decision["payload"]["decision"].pop("target")
        malformed_decision["payload"]["decision"]["ordinaryExecutionAuthority"] = True
        malformed_decision["eventHash"] = governance_kernel.document_hash(malformed_decision, "eventHash")
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "decision fields differ"):
            governance_kernel.validate_event(malformed_decision)

        malformed_program = copy.deepcopy(event)
        malformed_program["payload"]["program"]["executionAuthority"] = "ordinary"
        malformed_program["eventHash"] = governance_kernel.document_hash(malformed_program, "eventHash")
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "program position fields differ"):
            governance_kernel.validate_event(malformed_program)

        invalid_action = copy.deepcopy(event)
        invalid_action["payload"]["decision"]["action"] = "execute-with-ordinary-authority"
        invalid_action["eventHash"] = governance_kernel.document_hash(invalid_action, "eventHash")
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "decision is invalid"):
            governance_kernel.validate_event(invalid_action)

        alternate_source = copy.deepcopy(event)
        alternate_source["source"]["path"] = "planning/untrusted-authority.json"
        alternate_source["eventHash"] = governance_kernel.document_hash(alternate_source, "eventHash")
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "source"):
            governance_kernel.validate_event(alternate_source)

        checkpoint = governance_kernel.build_checkpoint(governance_kernel.verify_and_project([event]))
        checkpoint["projection"]["decision"].pop("effect")
        checkpoint["projection"]["decision"]["unexpectedNestedContract"] = True
        checkpoint["projectionSha256"] = governance_kernel.sha256(
            governance_kernel.canonical_bytes(checkpoint["projection"])
        )
        checkpoint["checkpointHash"] = governance_kernel.document_hash(checkpoint, "checkpointHash")
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "decision fields differ"):
            governance_kernel.validate_checkpoint(checkpoint)

    def test_checkpoint_and_advisory_authority_tamper_fail_closed(self) -> None:
        event = self.event(1, governance_kernel.GENESIS_HASH)
        checkpoint = governance_kernel.build_checkpoint(governance_kernel.verify_and_project([event]))

        changed_checkpoint = copy.deepcopy(checkpoint)
        changed_checkpoint["projection"]["decision"]["riskTier"] = 3
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "binding is invalid"):
            governance_kernel.validate_checkpoint(changed_checkpoint)

        forged_checkpoint = copy.deepcopy(checkpoint)
        forged_checkpoint["projection"]["decision"]["summary"] = "A self-consistent but untrusted rebase."
        forged_checkpoint["projectionSha256"] = governance_kernel.sha256(
            governance_kernel.canonical_bytes(forged_checkpoint["projection"])
        )
        forged_checkpoint["checkpointHash"] = governance_kernel.document_hash(forged_checkpoint, "checkpointHash")
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "trusted checkpoint hash"):
            governance_kernel.verify_and_project(
                [],
                checkpoint=forged_checkpoint,
                trusted_checkpoint_hash=checkpoint["checkpointHash"],
            )
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "external trusted"):
            governance_kernel.verify_and_project([], checkpoint=checkpoint)

        authority = copy.deepcopy(event)
        authority["authority"] = "execution"
        authority["eventHash"] = governance_kernel.document_hash(authority, "eventHash")
        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "authority"):
            governance_kernel.validate_event(authority)

    def test_checkpoint_rejects_unsupported_reader_capability(self) -> None:
        event = self.event(1, governance_kernel.GENESIS_HASH)
        checkpoint = governance_kernel.build_checkpoint(governance_kernel.verify_and_project([event]))
        supported = governance_kernel.SUPPORTED_CAPABILITIES - {"projection.next-action.v1"}

        with self.assertRaisesRegex(governance_kernel.KernelValidationError, "Unsupported"):
            governance_kernel.verify_and_project(
                [],
                checkpoint=checkpoint,
                trusted_checkpoint_hash=checkpoint["checkpointHash"],
                supported_capabilities=supported,
            )


if __name__ == "__main__":
    unittest.main()
