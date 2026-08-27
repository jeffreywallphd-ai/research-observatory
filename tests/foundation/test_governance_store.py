from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import governance_kernel  # noqa: E402
import governance_receipt  # noqa: E402
import governance_store  # noqa: E402


class GovernanceStoreTests(unittest.TestCase):
    def event(
        self,
        sequence: int,
        previous_hash: str,
        *,
        subject: str = "task/CAP-01.S01.T01",
    ) -> governance_kernel.GovernanceEvent:
        return governance_kernel.build_next_action_event(
            sequence=sequence,
            previous_event_hash=previous_hash,
            subject=subject,
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
            shadow_agreement=True,
        )

    def binding(self) -> governance_receipt.GitBinding:
        return {
            "commit": "2" * 40,
            "branch": "codex/store-fixture",
            "trackedWorktreeClean": True,
        }

    def checks(self) -> dict[str, bool]:
        return {
            "event-envelope": True,
            "producer-git-binding": True,
            "projection-transition": True,
            "source-byte-stability": True,
        }

    def root(self, temporary: str) -> Path:
        root = Path(temporary) / "fixture-store"
        root.mkdir()
        return root

    def test_prepare_is_inert_and_commit_atomically_appends_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            genesis_hash = governance_store.initialize_store(root)
            event = self.event(1, governance_kernel.GENESIS_HASH)

            prepared = governance_store.prepare_append(
                root,
                expected_state_hash=genesis_hash,
                event=event,
                git_binding=self.binding(),
                check_results=self.checks(),
            )

            before_commit = governance_store.read_state(root)
            self.assertEqual(genesis_hash, before_commit["stateHash"])
            self.assertEqual([], before_commit["events"])
            self.assertTrue((root / governance_store.TRANSACTION_FILE).is_file())
            committed_hash = governance_store.commit_prepared(
                root,
                expected_transaction_hash=prepared["transactionHash"],
            )
            committed = governance_store.read_state(root)
            governance_store.validate_state(committed)
            self.assertEqual(prepared["successorStateHash"], committed_hash)
            self.assertEqual(event, committed["events"][0])
            self.assertEqual(prepared["receiptHash"], committed["receipts"][0]["receiptHash"])
            self.assertFalse((root / governance_store.TRANSACTION_FILE).exists())

    def test_compare_and_swap_pending_transaction_and_hash_substitution_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            genesis_hash = governance_store.initialize_store(root)
            event = self.event(1, governance_kernel.GENESIS_HASH)

            with self.assertRaisesRegex(governance_store.StoreError, "compare-and-swap"):
                governance_store.prepare_append(
                    root,
                    expected_state_hash="f" * 64,
                    event=event,
                    git_binding=self.binding(),
                    check_results=self.checks(),
                )
            prepared = governance_store.prepare_append(
                root,
                expected_state_hash=genesis_hash,
                event=event,
                git_binding=self.binding(),
                check_results=self.checks(),
            )
            with self.assertRaisesRegex(governance_store.StoreError, "already pending"):
                governance_store.prepare_append(
                    root,
                    expected_state_hash=genesis_hash,
                    event=event,
                    git_binding=self.binding(),
                    check_results=self.checks(),
                )
            with self.assertRaisesRegex(governance_store.StoreError, "expected hash"):
                governance_store.commit_prepared(root, expected_transaction_hash="e" * 64)
            self.assertEqual(genesis_hash, governance_store.read_state(root)["stateHash"])
            governance_store.commit_prepared(
                root,
                expected_transaction_hash=prepared["transactionHash"],
            )

    def test_recovery_completes_prepared_or_rolls_back_materialized_successor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            genesis_hash = governance_store.initialize_store(root)
            prepared = governance_store.prepare_append(
                root,
                expected_state_hash=genesis_hash,
                event=self.event(1, governance_kernel.GENESIS_HASH),
                git_binding=self.binding(),
                check_results=self.checks(),
            )
            completed = governance_store.recover_append(
                root,
                expected_transaction_hash=prepared["transactionHash"],
                action="complete",
            )
            self.assertEqual(prepared["successorStateHash"], completed)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            genesis_hash = governance_store.initialize_store(root)
            prepared = governance_store.prepare_append(
                root,
                expected_state_hash=genesis_hash,
                event=self.event(1, governance_kernel.GENESIS_HASH),
                git_binding=self.binding(),
                check_results=self.checks(),
            )
            rolled_back = governance_store.recover_append(
                root,
                expected_transaction_hash=prepared["transactionHash"],
                action="rollback",
            )
            self.assertEqual(genesis_hash, rolled_back)
            self.assertEqual([], governance_store.read_state(root)["events"])

        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            genesis_hash = governance_store.initialize_store(root)
            prepared = governance_store.prepare_append(
                root,
                expected_state_hash=genesis_hash,
                event=self.event(1, governance_kernel.GENESIS_HASH),
                git_binding=self.binding(),
                check_results=self.checks(),
            )
            with (
                patch.object(governance_store, "_remove_transaction", side_effect=OSError("simulated crash")),
                self.assertRaisesRegex(OSError, "simulated crash"),
            ):
                governance_store.commit_prepared(
                    root,
                    expected_transaction_hash=prepared["transactionHash"],
                )
            self.assertEqual(prepared["successorStateHash"], governance_store.read_state(root)["stateHash"])
            rolled_back = governance_store.recover_append(
                root,
                expected_transaction_hash=prepared["transactionHash"],
                action="rollback",
            )
            self.assertEqual(genesis_hash, rolled_back)
            self.assertEqual(genesis_hash, governance_store.read_state(root)["stateHash"])

        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            genesis_hash = governance_store.initialize_store(root)
            prepared = governance_store.prepare_append(
                root,
                expected_state_hash=genesis_hash,
                event=self.event(1, governance_kernel.GENESIS_HASH),
                git_binding=self.binding(),
                check_results=self.checks(),
            )
            with (
                patch.object(governance_store, "_remove_transaction", side_effect=OSError("simulated crash")),
                self.assertRaisesRegex(OSError, "simulated crash"),
            ):
                governance_store.commit_prepared(
                    root,
                    expected_transaction_hash=prepared["transactionHash"],
                )
            completed = governance_store.recover_append(
                root,
                expected_transaction_hash=prepared["transactionHash"],
                action="complete",
            )
            self.assertEqual(prepared["successorStateHash"], completed)
            self.assertEqual(1, len(governance_store.read_state(root)["events"]))

    def test_rehashed_transaction_rewrite_is_denied_by_expected_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            genesis_hash = governance_store.initialize_store(root)
            prepared = governance_store.prepare_append(
                root,
                expected_state_hash=genesis_hash,
                event=self.event(1, governance_kernel.GENESIS_HASH),
                git_binding=self.binding(),
                check_results=self.checks(),
            )
            transaction_path = root / governance_store.TRANSACTION_FILE
            transaction = json.loads(transaction_path.read_bytes())
            transaction["successor"]["receipts"][0]["gitBinding"]["branch"] = "codex/substituted"
            transaction["successor"]["receipts"][0]["receiptHash"] = governance_kernel.document_hash(
                transaction["successor"]["receipts"][0], "receiptHash"
            )
            transaction["successor"]["stateHash"] = governance_kernel.document_hash(
                transaction["successor"], "stateHash"
            )
            transaction["transactionHash"] = governance_kernel.document_hash(transaction, "transactionHash")
            transaction_path.write_bytes(governance_kernel.canonical_bytes(transaction))

            with self.assertRaisesRegex(governance_store.StoreError, "expected hash"):
                governance_store.recover_append(
                    root,
                    expected_transaction_hash=prepared["transactionHash"],
                    action="complete",
                )

    def test_invalid_action_and_off_boundary_state_fail_without_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            genesis_hash = governance_store.initialize_store(root)
            prepared = governance_store.prepare_append(
                root,
                expected_state_hash=genesis_hash,
                event=self.event(1, governance_kernel.GENESIS_HASH),
                git_binding=self.binding(),
                check_results=self.checks(),
            )
            with self.assertRaisesRegex(governance_store.StoreError, "complete or rollback"):
                governance_store.recover_append(
                    root,
                    expected_transaction_hash=prepared["transactionHash"],
                    action=cast(Any, "erase"),
                )

            alternate = Path(temporary) / "alternate-store"
            alternate.mkdir()
            alternate_genesis = governance_store.initialize_store(alternate)
            governance_store.append_event(
                alternate,
                expected_state_hash=alternate_genesis,
                event=self.event(
                    1,
                    governance_kernel.GENESIS_HASH,
                    subject="task/CAP-01.S01.T02",
                ),
                git_binding=self.binding(),
                check_results=self.checks(),
            )
            alternate_state = governance_store.read_state(alternate)
            (root / governance_store.STATE_FILE).write_bytes(governance_kernel.canonical_bytes(alternate_state))
            with self.assertRaisesRegex(governance_store.StoreError, "outside the pending"):
                governance_store.recover_append(
                    root,
                    expected_transaction_hash=prepared["transactionHash"],
                    action="complete",
                )

    def test_duplicate_json_and_redirected_store_path_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            governance_store.initialize_store(root)
            state_path = root / governance_store.STATE_FILE
            duplicated = state_path.read_bytes().replace(
                b"{",
                b'{"schemaVersion":"substituted",',
                1,
            )
            state_path.write_bytes(duplicated)
            with self.assertRaisesRegex(governance_store.StoreError, "duplicate key"):
                governance_store.read_state(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary)
            redirected = root / governance_store.STATE_FILE
            real_redirect_check = governance_store._is_redirected

            def redirect_fixture(path: Path) -> bool:
                return path == redirected or real_redirect_check(path)

            with (
                patch.object(governance_store, "_is_redirected", redirect_fixture),
                self.assertRaisesRegex(governance_store.StoreError, "redirected"),
            ):
                governance_store.initialize_store(root)

        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repository"
            repository.mkdir()
            (repository / ".git").mkdir()
            root = repository / "fixture-store"
            root.mkdir()
            with self.assertRaisesRegex(governance_store.StoreError, "outside every Git worktree"):
                governance_store.initialize_store(root)

    def test_store_has_no_cli_or_live_backlog_path(self) -> None:
        source = (REPO / "tools" / "governance_store.py").read_text(encoding="utf-8")
        self.assertNotIn("argparse", source)
        self.assertNotIn("planning/backlog.yaml", source)
        self.assertNotIn("def main(", source)


if __name__ == "__main__":
    unittest.main()
