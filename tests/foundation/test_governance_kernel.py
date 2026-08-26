from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import governance_kernel  # noqa: E402


class GovernanceKernelTests(unittest.TestCase):
    def event(
        self,
        sequence: int,
        previous_hash: str,
        *,
        category: str = "task",
    ) -> governance_kernel.GovernanceEvent:
        return governance_kernel.build_next_action_event(
            sequence=sequence,
            previous_event_hash=previous_hash,
            subject=f"{category}/fixture",
            source={"path": "planning/backlog.yaml", "sha256": "1" * 64},
            program={"state": "ACTIVE_WAVE", "currentWave": "W1"},
            decision={
                "category": category,
                "action": "inspect",
                "target": "fixture",
                "summary": "Inspect the deterministic fixture.",
                "command": None,
                "riskTier": 0,
                "executableNow": True,
                "approvalRequired": False,
                "effect": "read-only",
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
