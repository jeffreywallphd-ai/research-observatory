from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from typing import Any, cast

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import governance_kernel  # noqa: E402
import governance_receipt  # noqa: E402


class GovernanceReceiptTests(unittest.TestCase):
    def transition(
        self, *, tracked_clean: bool = True, agreement: bool = True
    ) -> tuple[
        governance_kernel.GovernanceEvent,
        dict[str, object],
        dict[str, object],
        governance_receipt.GitBinding,
        dict[str, bool],
    ]:
        event = governance_kernel.build_next_action_event(
            sequence=1,
            previous_event_hash=governance_kernel.GENESIS_HASH,
            subject="task/CAP-01.S01.T01",
            source={"path": "planning/backlog.yaml", "sha256": "1" * 64},
            program={
                "state": "ACTIVE_WAVE",
                "currentWave": "W1",
                "blockedWave": None,
                "nextGate": "G1",
            },
            decision={
                "category": "task",
                "action": "claim-wave-task",
                "target": "CAP-01.S01.T01",
                "summary": "Claim the next dependency-eligible task.",
                "command": "python tools/taskctl.py claim CAP-01.S01.T01",
                "riskTier": 1,
                "executableNow": True,
                "approvalRequired": False,
                "effect": "mutation-template",
            },
            legacy_category="task",
            shadow_agreement=agreement,
        )
        before = governance_kernel.initial_projection()
        after = governance_kernel.verify_and_project([event])
        binding: governance_receipt.GitBinding = {
            "commit": "2" * 40,
            "branch": "codex/receipt-fixture",
            "trackedWorktreeClean": tracked_clean,
        }
        checks = {
            "event-envelope": True,
            "legacy-category-agreement": agreement,
            "producer-git-binding": tracked_clean,
            "projection-transition": True,
            "source-byte-stability": True,
        }
        return event, before, after, binding, checks

    def build(self, *, tracked_clean: bool = True, agreement: bool = True) -> governance_receipt.TransitionReceipt:
        event, before, after, binding, checks = self.transition(
            tracked_clean=tracked_clean,
            agreement=agreement,
        )
        return governance_receipt.build_receipt(
            event=event,
            before_projection=before,
            after_projection=after,
            git_binding=binding,
            check_results=checks,
        )

    def test_receipt_is_deterministic_and_binds_exact_projection_delta(self) -> None:
        event, before, after, binding, checks = self.transition()
        inputs = copy.deepcopy((event, before, after, binding, checks))
        first = governance_receipt.build_receipt(
            event=event,
            before_projection=before,
            after_projection=after,
            git_binding=binding,
            check_results=checks,
        )
        second = governance_receipt.build_receipt(
            event=event,
            before_projection=before,
            after_projection=after,
            git_binding=binding,
            check_results=checks,
        )

        self.assertEqual(first, second)
        self.assertEqual(inputs, (event, before, after, binding, checks))
        self.assertEqual("evidence-only", first["authority"])
        self.assertFalse(first["mutationPerformed"])
        self.assertEqual("producer-asserted", first["verification"]["trust"])
        self.assertEqual("passed", first["verification"]["overallStatus"])
        changed = [item["field"] for item in first["projectionBinding"]["changedFields"]]
        self.assertEqual(sorted(changed), changed)
        self.assertNotIn("documentType", changed)
        self.assertNotIn("schemaVersion", changed)
        governance_receipt.validate_receipt(
            first,
            event=event,
            before_projection=before,
            after_projection=after,
            expected_git_binding=binding,
        )

    def test_failed_producer_or_agreement_check_is_truthful_not_authority(self) -> None:
        for tracked_clean, agreement in ((False, True), (True, False)):
            with self.subTest(tracked_clean=tracked_clean, agreement=agreement):
                receipt = self.build(tracked_clean=tracked_clean, agreement=agreement)
                self.assertEqual("failed", receipt["verification"]["overallStatus"])
                self.assertEqual("evidence-only", receipt["authority"])
                self.assertFalse(receipt["mutationPerformed"])

    def test_omitted_bound_fact_checks_cannot_turn_adverse_facts_into_pass(self) -> None:
        for tracked_clean, agreement, adverse_fact in (
            (False, True, "dirty producer"),
            (True, False, "shadow disagreement"),
        ):
            with self.subTest(adverse_fact=adverse_fact):
                event, before, after, binding, checks = self.transition(
                    tracked_clean=tracked_clean,
                    agreement=agreement,
                )
                receipt = governance_receipt.build_receipt(
                    event=event,
                    before_projection=before,
                    after_projection=after,
                    git_binding=binding,
                    check_results=checks,
                )
                receipt["verification"] = {
                    "selectedChecks": ["event-envelope"],
                    "results": [{"id": "event-envelope", "status": "passed"}],
                    "overallStatus": "passed",
                    "trust": "producer-asserted",
                }
                receipt["receiptHash"] = governance_kernel.document_hash(receipt, "receiptHash")
                with self.assertRaisesRegex(governance_receipt.ReceiptValidationError, "status or trust"):
                    governance_receipt.validate_receipt(
                        receipt,
                        event=event,
                        before_projection=before,
                        after_projection=after,
                        expected_git_binding=binding,
                    )

                receipt["verification"]["overallStatus"] = "failed"
                receipt["receiptHash"] = governance_kernel.document_hash(receipt, "receiptHash")
                governance_receipt.validate_receipt(
                    receipt,
                    event=event,
                    before_projection=before,
                    after_projection=after,
                    expected_git_binding=binding,
                )

    def test_source_divergence_is_rejected_before_receipt_status(self) -> None:
        event, before, after, binding, checks = self.transition()
        receipt = governance_receipt.build_receipt(
            event=event,
            before_projection=before,
            after_projection=after,
            git_binding=binding,
            check_results=checks,
        )
        divergent_after = cast(dict[str, Any], copy.deepcopy(after))
        divergent_after["source"]["sha256"] = "9" * 64
        with self.assertRaisesRegex(governance_receipt.ReceiptValidationError, "transition differs"):
            governance_receipt.validate_receipt(
                receipt,
                event=event,
                before_projection=before,
                after_projection=divergent_after,
                expected_git_binding=binding,
            )

    def test_rehashed_projection_check_and_git_substitution_fail_closed(self) -> None:
        event, before, after, binding, checks = self.transition()
        receipt = governance_receipt.build_receipt(
            event=event,
            before_projection=before,
            after_projection=after,
            git_binding=binding,
            check_results=checks,
        )

        delta = copy.deepcopy(receipt)
        delta["projectionBinding"]["changedFields"].pop()
        delta["receiptHash"] = governance_kernel.document_hash(delta, "receiptHash")
        with self.assertRaisesRegex(governance_receipt.ReceiptValidationError, "projection binding differs"):
            governance_receipt.validate_receipt(
                delta,
                event=event,
                before_projection=before,
                after_projection=after,
                expected_git_binding=binding,
            )

        result = copy.deepcopy(receipt)
        result["verification"]["results"][0]["status"] = "failed"
        result["verification"]["overallStatus"] = "failed"
        result["receiptHash"] = governance_kernel.document_hash(result, "receiptHash")
        with self.assertRaisesRegex(governance_receipt.ReceiptValidationError, "contradicts"):
            governance_receipt.validate_receipt(
                result,
                event=event,
                before_projection=before,
                after_projection=after,
                expected_git_binding=binding,
            )

        git = copy.deepcopy(receipt)
        git["gitBinding"]["commit"] = "3" * 40
        git["receiptHash"] = governance_kernel.document_hash(git, "receiptHash")
        with self.assertRaisesRegex(governance_receipt.ReceiptValidationError, "expected producer"):
            governance_receipt.validate_receipt(
                git,
                event=event,
                before_projection=before,
                after_projection=after,
                expected_git_binding=binding,
            )

    def test_capability_empty_check_selection_and_event_binding_fail_closed(self) -> None:
        event, before, after, binding, checks = self.transition()
        receipt = governance_receipt.build_receipt(
            event=event,
            before_projection=before,
            after_projection=after,
            git_binding=binding,
            check_results=checks,
        )

        capability = copy.deepcopy(receipt)
        capability["capabilities"] = []
        capability["receiptHash"] = governance_kernel.document_hash(capability, "receiptHash")
        with self.assertRaisesRegex(governance_receipt.ReceiptValidationError, "capabilities"):
            governance_receipt.validate_receipt(
                capability,
                event=event,
                before_projection=before,
                after_projection=after,
                expected_git_binding=binding,
            )

        missing_checks: dict[str, bool] = {}
        with self.assertRaisesRegex(governance_receipt.ReceiptValidationError, "check selection"):
            governance_receipt.build_receipt(
                event=event,
                before_projection=before,
                after_projection=after,
                git_binding=binding,
                check_results=missing_checks,
            )

        event_binding = copy.deepcopy(receipt)
        event_binding["eventBinding"]["subject"] = "task/substituted"
        event_binding["receiptHash"] = governance_kernel.document_hash(event_binding, "receiptHash")
        with self.assertRaisesRegex(governance_receipt.ReceiptValidationError, "event binding differs"):
            governance_receipt.validate_receipt(
                event_binding,
                event=event,
                before_projection=before,
                after_projection=after,
                expected_git_binding=binding,
            )

        authority = copy.deepcopy(receipt)
        authority["authority"] = "execution"
        authority["receiptHash"] = governance_kernel.document_hash(authority, "receiptHash")
        with self.assertRaisesRegex(governance_receipt.ReceiptValidationError, "identity or authority"):
            governance_receipt.validate_receipt(
                authority,
                event=event,
                before_projection=before,
                after_projection=after,
                expected_git_binding=binding,
            )


if __name__ == "__main__":
    unittest.main()
