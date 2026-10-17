"""Observer-only calibrations; synthetic identity, no actual drain proof."""

import json
import os
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from research_observatory_core import windows_credentials
from research_observatory_core.ports.project_recovery import RecoveryProcessIdentity

from tests.service.fixtures import native_integration_sidecar as fixture
from workers.windows import connector_launcher, lpac_launcher, no_write_acl, recovery_guardian


class OwnedRoleZeroObservationCalibration(unittest.TestCase):
    """Fake identity/launch return values calibrate refusal; actual Native is separate."""

    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.fixture = Path(
            tempfile.mkdtemp(prefix="search-populated-native-unit-", dir=root / "artifacts/tmp")
        ).resolve()
        self.vault = self.fixture / "vault"
        self.vault.mkdir()
        (self.fixture / "core-owned-role-proof").mkdir()
        self.sequence = 1000
        self.marker = object()

    def probe(self, action=None, *, enumerate_threads=None, guardian=None) -> dict[str, Any]:
        self.sequence += 1
        identity = RecoveryProcessIdentity(self.sequence, "0000000000000001", "a" * 64)

        def original(*args: Any, **kwargs: Any) -> Any:
            return self.marker

        guardian = guardian or original
        originals = (
            (recovery_guardian, "start_guardian", guardian),
            (connector_launcher, "start_guardian", guardian),
            (connector_launcher, "_launch_signed_worker", original),
            (lpac_launcher, "_launch", original),
            (lpac_launcher, "_run_icacls", original),
            (no_write_acl, "_run_icacls", original),
        )
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"RO_W3_CORE_LIFETIME_PROBE": "1"}))
            stack.enter_context(
                patch.object(windows_credentials, "_recovery_current_process_identity", return_value=identity)
            )
            stack.enter_context(
                patch.object(
                    threading, "enumerate", side_effect=enumerate_threads or (lambda: [threading.main_thread()])
                )
            )
            for module, name, function in originals:
                stack.enter_context(patch.object(module, name, new=function))
            try:
                with fixture._owned_roles_probe(self.vault):
                    if action:
                        action()
            finally:
                proof = (
                    self.fixture
                    / "core-owned-role-proof"
                    / f"core-owned-roles-{identity.process_id}-{identity.creation_filetime}.json"
                )
                self.last_receipt = json.loads(proof.read_text(encoding="utf-8"))
        return self.last_receipt

    def test_synthetic_complete_no_invocation_calibration(self) -> None:
        receipt = self.probe()
        self.assertTrue(receipt["observedZeroRoleAttempts"])
        self.assertEqual(receipt["positiveWorkerGuardianDrain"], "NOT_OBSERVED")
        self.assertTrue(all(count == 0 for role in receipt["roles"].values() for count in role.values()))

    def test_any_attempt_forwards_same_result_and_denies_zero(self) -> None:
        cases = (
            (recovery_guardian, "start_guardian", "guardian"),
            (connector_launcher, "start_guardian", "guardian"),
            (connector_launcher, "_launch_signed_worker", "connector-worker"),
            (lpac_launcher, "_launch", "lpac-worker"),
            (lpac_launcher, "_run_icacls", "acl-utility"),
            (no_write_acl, "_run_icacls", "acl-utility"),
        )
        for module, name, role in cases:
            with self.subTest(name=f"{module.__name__}.{name}"):
                receipt = self.probe(
                    lambda module=module, name=name: self.assertIs(getattr(module, name)(), self.marker)
                )
                self.assertFalse(receipt["observedZeroRoleAttempts"])
                self.assertEqual(receipt["roles"][role], {"attempts": 1, "returns": 1, "errors": 0, "inflight": 0})

    def test_original_exception_identity_is_preserved_and_never_zero(self) -> None:
        error = RuntimeError("synthetic observer calibration")

        def original():
            raise error

        with self.assertRaises(RuntimeError) as caught:
            self.probe(lambda: connector_launcher.start_guardian(), guardian=original)
        self.assertIs(caught.exception, error)
        self.assertFalse(self.last_receipt["observedZeroRoleAttempts"])
        self.assertFalse(self.last_receipt["runtimeReturned"])
        self.assertEqual(
            self.last_receipt["roles"]["guardian"], {"attempts": 1, "returns": 0, "errors": 1, "inflight": 0}
        )

    def test_final_counter_snapshot_includes_late_entry_from_finished_thread(self) -> None:
        entered = threading.Event()
        done = threading.Event()
        failure: list[BaseException] = []

        def invoke():
            try:
                if not entered.wait(2):
                    raise TimeoutError("calibration entry barrier")
                connector_launcher.start_guardian()
            except BaseException as error:
                failure.append(error)
            finally:
                done.set()

        worker = threading.Thread(target=invoke, daemon=True)
        worker.start()

        def calibrated_enumerate():
            # Observer-only injected interleaving, not a production wait/drain.
            entered.set()
            self.assertTrue(done.wait(2))
            worker.join(2)
            self.assertFalse(worker.is_alive())
            return [threading.main_thread()]

        try:
            receipt = self.probe(enumerate_threads=calibrated_enumerate)
        finally:
            entered.set()
            worker.join(2)
        self.assertFalse(failure)
        self.assertFalse(receipt["observedZeroRoleAttempts"])
        self.assertEqual(receipt["roles"]["guardian"]["attempts"], 1)
        self.assertEqual(receipt["unexpectedLiveThreads"], [])

    def test_allowed_names_do_not_authorize_unknown_live_thread_targets(self) -> None:
        for name in ("MainThread", "supervisor-control", "project-native-writer"):
            with self.subTest(name=name):
                release = threading.Event()
                worker = threading.Thread(target=lambda release=release: release.wait(2), name=name, daemon=True)
                worker.start()
                try:
                    receipt = self.probe(enumerate_threads=lambda worker=worker: [threading.main_thread(), worker])
                finally:
                    release.set()
                    worker.join(2)
                self.assertFalse(receipt["observedZeroRoleAttempts"])
                self.assertIn(name, receipt["unexpectedLiveThreads"])

    def test_alias_change_after_install_invalidates_zero(self) -> None:
        def substituted_guardian(*args: Any, **kwargs: Any) -> Any:
            return None

        def change_alias():
            connector_launcher.start_guardian = substituted_guardian

        receipt = self.probe(change_alias)
        self.assertFalse(receipt["observedZeroRoleAttempts"])
        self.assertFalse(receipt["aliasesRetainedUntilFinalization"])


if __name__ == "__main__":
    unittest.main()
