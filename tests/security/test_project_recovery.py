"""Recovery-copy tests: unit fixtures do not qualify Native or DPAPI boundaries."""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO, Literal, cast
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "core-api" / "src"))

from research_observatory_core import object_store as object_store_module  # noqa: E402
from research_observatory_core import projects as projects_module  # noqa: E402
from research_observatory_core import windows_credentials as windows_credentials_module  # noqa: E402
from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.import_preview_service import ImportPreviewService  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.object_store import ObjectPutCommand  # noqa: E402
from research_observatory_core.ports.object_store_keys import ObjectMasterKey  # noqa: E402
from research_observatory_core.ports.project_recovery import (  # noqa: E402
    RecoveryCopyVerificationRequest,
    RecoveryLocalReadAuthority,
    RecoveryNativeInspection,
    RecoveryNativeSession,
    RecoveryOwnershipWitness,
    RecoveryProcessIdentity,
    RecoveryVerificationProblem,
)
from research_observatory_core.ports.repositories import AggregateRevisionDraft, AtomicRepositoryEvent  # noqa: E402
from research_observatory_core.privacy import ProjectPrivacyService  # noqa: E402
from research_observatory_core.projects import ProjectLifecycleProblem, ProjectLifecycleService  # noqa: E402
from research_observatory_core.repositories import (  # noqa: E402
    create_sqlite_unit_of_work_factory,
    sqlite_privacy_policy_repository,
)
from research_observatory_core.storage import (  # noqa: E402
    EXPECTED_TABLES,
    development_plaintext_database_fixture,
    initialize_database,
    open_canonical_database,
)
from research_observatory_core.windows_credentials import WindowsProjectRecoveryWitnessStore  # noqa: E402

PROJECT_ID = "01890f6e-6a40-4cc5-98b7-7f3f36b60210"
CREATED_AT = "2026-08-18T12:00:00.000Z"


class FixtureKeys:
    def __init__(self, key: bytes = bytes.fromhex("11" * 32)) -> None:
        self.key = key

    def active_object_master_key(self) -> ObjectMasterKey:
        return ObjectMasterKey("object-key-v1", self.key)

    def object_master_key(self, key_version: str) -> ObjectMasterKey | None:
        return self.active_object_master_key() if key_version == "object-key-v1" else None


def byte_inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def canonical_facts(root: Path, project_id: str = PROJECT_ID) -> dict[str, tuple[tuple[object, ...], ...]]:
    connection = open_canonical_database(root / "state" / "project.sqlite3", expected_project_id=project_id)
    try:
        return {
            table: tuple(tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"'))
            for table in EXPECTED_TABLES
        }
    finally:
        connection.close()


class RecoveryInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_fixture = development_plaintext_database_fixture()
        self.database_fixture.__enter__()
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-recovery-unit-")
        self.addCleanup(self.database_fixture.__exit__, None, None, None)
        self.addCleanup(self.temporary.cleanup)
        self.original = Path(self.temporary.name).resolve() / "original"
        self.stage = self.original.parent / "stage"
        for name in ("state", "objects", ".tmp"):
            (self.original / name).mkdir(parents=True)
        initialize_database(
            self.original / "state" / "project.sqlite3",
            project_id=PROJECT_ID,
            project_created_at=CREATED_AT,
        )
        self.keys = FixtureKeys()

    def put_referenced_object(self) -> str:
        store = create_local_object_store(self.original, PROJECT_ID, key_provider=self.keys)
        stored = store.put(
            io.BytesIO(b"synthetic protected recovery fixture" * 100),
            ObjectPutCommand(
                media_type="application/pdf",
                rights_status="allowed",
                protection_profile="project-encrypted-v1",
                retention_class="project-lifetime",
                creation_source="test-fixture",
                created_at=CREATED_AT,
            ),
        )
        factory = create_sqlite_unit_of_work_factory(self.original / "state" / "project.sqlite3", PROJECT_ID)
        with factory() as unit:
            unit.aggregates.append(
                AggregateRevisionDraft(
                    revision_id="01890f6e-6a40-7cc5-98b7-000000000001",
                    aggregate_id="01890f6e-6a40-7cc5-98b7-000000000100",
                    aggregate_kind="document",
                    created_at=CREATED_AT,
                    modified_at="2026-08-18T12:00:01.000Z",
                    display_label_observed="Synthetic recovery document",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="allowed",
                    dependency_coverage="not-applicable",
                    object_sha256=stored.object_sha256,
                ),
                AtomicRepositoryEvent(
                    event_id="01890f6e-6a40-7cc5-98b7-000000000101",
                    outbox_id="01890f6e-6a40-7cc5-98b7-000000000201",
                    event_type="document.created",
                    occurred_at="2026-08-18T12:01:01.000Z",
                    available_at="2026-08-18T12:01:01.000Z",
                    trace_id=f"{2:032x}",
                    actor_type="human",
                    actor_id="01890f6e-6a40-7cc5-98b7-000000000301",
                    idempotency_key="recovery-fixture-document",
                ),
                expected_revision=None,
            )
            unit.commit()
        return stored.object_sha256

    def verify_copy(
        self,
        *,
        keys: FixtureKeys | None = None,
        cancel: bool = False,
        network_policy: Literal["offline", "metadata-only", "approved-providers"] = "offline",
    ):
        return object_store_module.verify_recovery_working_copy(
            RecoveryCopyVerificationRequest(
                root=self.stage,
                project_id=PROJECT_ID,
                local_read=RecoveryLocalReadAuthority(PROJECT_ID, 0, network_policy),
                key_provider=self.keys if keys is None else keys,
                cancellation_requested=lambda: cancel,
            )
        )

    def test_database_referenced_ciphertext_missing_from_copy_denies_without_original_change(self) -> None:
        self.put_referenced_object()
        original_before = byte_inventory(self.original)
        shutil.copytree(self.original, self.stage)
        encrypted_files = list((self.stage / "objects").rglob("*.blob"))
        self.assertEqual(1, len(encrypted_files))
        encrypted_files[0].unlink()
        verifier = getattr(object_store_module, "verify_recovery_working_copy", None)
        self.assertTrue(callable(verifier), "complete recovery-copy verification is missing")
        assert callable(verifier)
        with self.assertRaises(RecoveryVerificationProblem):
            verifier(
                RecoveryCopyVerificationRequest(
                    root=self.stage,
                    project_id=PROJECT_ID,
                    local_read=RecoveryLocalReadAuthority(PROJECT_ID, 0, "offline"),
                    key_provider=self.keys,
                    cancellation_requested=lambda: False,
                )
            )
        self.assertEqual(original_before, byte_inventory(self.original))

    def test_valid_copy_authenticates_every_object_and_preserves_all_canonical_facts(self) -> None:
        self.put_referenced_object()
        original_before = byte_inventory(self.original)
        shutil.copytree(self.original, self.stage)
        facts_before = canonical_facts(self.stage)
        result = self.verify_copy()
        self.assertEqual(1, result.available_object_count)
        self.assertGreater(result.canonical_row_count, 0)
        self.assertEqual(len(b"synthetic protected recovery fixture" * 100), result.authenticated_plaintext_byte_count)
        self.assertEqual(facts_before, canonical_facts(self.stage))
        self.assertEqual(original_before, byte_inventory(self.original))

    def test_empty_copy_is_valid_under_every_valid_local_privacy_network_mode(self) -> None:
        shutil.copytree(self.original, self.stage)
        modes: tuple[Literal["offline", "metadata-only", "approved-providers"], ...] = (
            "offline",
            "metadata-only",
            "approved-providers",
        )
        for mode in modes:
            with self.subTest(mode=mode):
                self.assertEqual(0, self.verify_copy(network_policy=mode).available_object_count)

    def test_unknown_local_privacy_or_wrong_project_authority_denies(self) -> None:
        shutil.copytree(self.original, self.stage)
        with self.assertRaises(RecoveryVerificationProblem):
            # Deliberately violate the typed authority to exercise runtime denial.
            self.verify_copy(network_policy=cast(Literal["offline", "metadata-only", "approved-providers"], "unknown"))
        with self.assertRaises(RecoveryVerificationProblem):
            object_store_module.verify_recovery_working_copy(
                RecoveryCopyVerificationRequest(
                    self.stage,
                    PROJECT_ID,
                    RecoveryLocalReadAuthority("123e4567-e89b-42d3-a456-426614174000", 0, "offline"),
                    self.keys,
                    lambda: False,
                )
            )

    def test_wrong_retained_key_denies_without_metadata_quarantine(self) -> None:
        self.put_referenced_object()
        shutil.copytree(self.original, self.stage)
        before = canonical_facts(self.stage)
        with self.assertRaises(RecoveryVerificationProblem):
            self.verify_copy(keys=FixtureKeys(bytes.fromhex("22" * 32)))
        self.assertEqual(before, canonical_facts(self.stage))

    def test_corrupt_ciphertext_and_unexplained_file_each_deny_without_repair(self) -> None:
        self.put_referenced_object()
        shutil.copytree(self.original, self.stage)
        ciphertext = next((self.stage / "objects").rglob("*.blob"))
        original = ciphertext.read_bytes()
        ciphertext.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        before = canonical_facts(self.stage)
        with self.assertRaises(RecoveryVerificationProblem):
            self.verify_copy()
        self.assertEqual(before, canonical_facts(self.stage))
        ciphertext.write_bytes(original)
        unexpected = self.stage / "objects" / "unexplained.blob"
        unexpected.write_bytes(b"unknown ciphertext")
        with self.assertRaises(RecoveryVerificationProblem):
            self.verify_copy()
        self.assertTrue(unexpected.exists())

    def test_hardlinked_object_denies_before_publication(self) -> None:
        self.put_referenced_object()
        shutil.copytree(self.original, self.stage)
        ciphertext = next((self.stage / "objects").rglob("*.blob"))
        os.link(ciphertext, self.stage.parent / "linked-ciphertext")
        with self.assertRaises(RecoveryVerificationProblem):
            self.verify_copy()

    def test_cancelled_verification_never_changes_canonical_data(self) -> None:
        self.put_referenced_object()
        shutil.copytree(self.original, self.stage)
        before = canonical_facts(self.stage)
        with self.assertRaises(RecoveryVerificationProblem) as raised:
            self.verify_copy(cancel=True)
        self.assertEqual("cancelled", raised.exception.reason_code)
        self.assertEqual(before, canonical_facts(self.stage))

    def test_valid_deleted_tombstone_is_retained_and_not_resurrected(self) -> None:
        store = create_local_object_store(self.original, PROJECT_ID, key_provider=self.keys)
        stored = store.put(
            io.BytesIO(b"deleted fixture"),
            ObjectPutCommand(
                "application/pdf", "allowed", "project-encrypted-v1", "project-lifetime", "test-fixture", CREATED_AT
            ),
        )
        store.delete(stored.object_sha256)
        shutil.copytree(self.original, self.stage)
        before = canonical_facts(self.stage)
        result = self.verify_copy()
        self.assertEqual(1, result.deleted_object_count)
        self.assertEqual(0, result.available_object_count)
        self.assertEqual(before, canonical_facts(self.stage))

    def test_concurrent_canonical_change_during_authentication_denies(self) -> None:
        self.put_referenced_object()
        shutil.copytree(self.original, self.stage)
        original_scan = object_store_module._scan_regular_files
        changed = False

        def change_during_scan(root: Path, **kwargs):
            nonlocal changed
            result = original_scan(root, **kwargs)
            if not changed:
                changed = True
                connection = open_canonical_database(
                    self.stage / "state" / "project.sqlite3", expected_project_id=PROJECT_ID
                )
                try:
                    connection.execute("UPDATE object_records SET verified_at=?", (CREATED_AT,))
                    connection.commit()
                finally:
                    connection.close()
            return result

        with (
            patch.object(object_store_module, "_scan_regular_files", change_during_scan),
            self.assertRaises(RecoveryVerificationProblem) as raised,
        ):
            self.verify_copy()
        self.assertEqual("canonical-facts-changed", raised.exception.reason_code)

    def test_unavailable_cancellation_on_empty_copy_fails_closed(self) -> None:
        shutil.copytree(self.original, self.stage)
        before = canonical_facts(self.stage)

        def unavailable():
            raise OSError("synthetic unavailable stop signal")

        for cancel in (lambda: None, unavailable):
            with self.subTest(cancel=cancel):
                with self.assertRaises(RecoveryVerificationProblem) as raised:
                    object_store_module.verify_recovery_working_copy(
                        RecoveryCopyVerificationRequest(
                            self.stage,
                            PROJECT_ID,
                            RecoveryLocalReadAuthority(PROJECT_ID, 0, "offline"),
                            self.keys,
                            # Deliberately unavailable or malformed cancellation signal.
                            cast(Callable[[], bool], cancel),
                        )
                    )
                self.assertEqual("cancelled", raised.exception.reason_code)
                self.assertEqual(before, canonical_facts(self.stage))


@unittest.skipUnless(os.name == "nt", "actual Windows DPAPI and file security are required")
class WindowsWitnessStoreTests(unittest.TestCase):
    """Real DPAPI/ACL/sharing tests with explicitly synthetic process bindings.

    The anonymous denial case uses a real thread principal. These do not
    qualify shipping Native ownership, another logged-in user, foreign-host
    wrapping or actual whole-pair death.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-witness-unit-")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name).resolve() / "protected-parent"
        sid = windows_credentials_module._recovery_current_sid()
        with windows_credentials_module._recovery_security_attributes(sid) as attributes:
            self.assertTrue(
                windows_credentials_module._recovery_windows_api()["CreateDirectoryW"](str(self.parent), attributes)
            )
        self.store = WindowsProjectRecoveryWitnessStore(self.parent / "private-witnesses")
        self.instance = str(uuid.uuid4())
        fixture_process = RecoveryProcessIdentity(os.getpid(), "0" * 16, "0" * 64)
        self.witness = RecoveryOwnershipWitness(
            "1.0",
            "project-session-recovery",
            secrets.token_hex(32),
            PROJECT_ID,
            str(self.parent),
            "00000001:0000000000000001",
            self.instance,
            "1" * 64,
            CREATED_AT,
            "2" * 64,
            RecoveryNativeSession(self.store.principal_reference, "3" * 64, fixture_process, fixture_process),
            "created",
            0,
            hashlib.sha256(b"").hexdigest(),
        )

    def test_persistent_exclusion_denies_second_store_and_reopens_same_resource_after_release(self) -> None:
        first = self.store.acquire_project(PROJECT_ID)
        try:
            first_identity = first.identity
            second_store = WindowsProjectRecoveryWitnessStore(self.store.root)
            with self.assertRaises(RecoveryVerificationProblem):
                second_store.acquire_project(PROJECT_ID)
            first.validate()
        finally:
            first.close()
        second = self.store.acquire_project(PROJECT_ID)
        try:
            self.assertEqual(first_identity, second.identity)
            second.validate()
        finally:
            second.close()
        self.assertTrue((self.store.root / f"{PROJECT_ID}.exclusion").exists())

    def test_dual_scope_issuance_round_trip_and_fresh_store_readback(self) -> None:
        exclusion = self.store.acquire_project(PROJECT_ID)
        try:
            self.store.issue(self.witness)
            self.assertEqual(
                self.witness,
                self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256),
            )
        finally:
            exclusion.close()
        fresh = WindowsProjectRecoveryWitnessStore(self.store.root)
        self.assertEqual(
            self.witness,
            fresh.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256),
        )
        sealed = next(self.store.root.glob("*.sealed")).read_bytes()
        self.assertNotIn(PROJECT_ID.encode("ascii"), sealed)
        self.assertNotIn(str(self.parent).encode("utf-8"), sealed)

    def test_issuance_without_owned_exclusion_and_reissuance_both_deny(self) -> None:
        with self.assertRaises(RecoveryVerificationProblem):
            self.store.issue(self.witness)
        exclusion = self.store.acquire_project(PROJECT_ID)
        try:
            self.store.issue(self.witness)
            with self.assertRaises(RecoveryVerificationProblem):
                self.store.issue(replace(self.witness, witness_id=secrets.token_hex(32)))
            self.assertEqual(
                self.witness,
                self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256),
            )
        finally:
            exclusion.close()

    def test_actual_anonymous_principal_denies_private_witness_and_user_dpapi(self) -> None:
        """Real anonymous thread boundary; no other-machine/login claim."""
        exclusion = self.store.acquire_project(PROJECT_ID)
        try:
            self.store.issue(self.witness)
        finally:
            exclusion.close()
        before = byte_inventory(self.parent)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-s",
                str(Path(__file__).resolve()),
                "--anonymous-witness-denial",
                str(self.store.root),
                PROJECT_ID,
                self.instance,
                self.witness.recovery_token_sha256,
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            {
                "anonymousPrivateAclDenied": True,
                "anonymousUserDpapiDenied": True,
                "ownerReadbackAfterRevert": True,
                "foreignHostTest": False,
            },
            json.loads(result.stdout),
        )
        self.assertEqual(before, byte_inventory(self.parent))
        self.assertEqual(
            self.witness,
            self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256),
        )

    def test_concurrent_close_cannot_release_exclusion_during_issuance(self) -> None:
        exclusion = self.store.acquire_project(PROJECT_ID)
        entered, release, close_started, closed = (threading.Event() for _ in range(4))
        errors: list[BaseException] = []
        protect = windows_credentials_module._recovery_machine_protect

        def blocked_protect(material):
            entered.set()
            if not release.wait(timeout=3):
                raise TimeoutError("unit issuance barrier did not release")
            return protect(material)

        def issue():
            try:
                self.store.issue(self.witness)
            except BaseException as error:
                errors.append(error)

        def close():
            close_started.set()
            exclusion.close()
            closed.set()

        with patch.object(windows_credentials_module, "_recovery_machine_protect", blocked_protect):
            issuer = threading.Thread(target=issue)
            closer = threading.Thread(target=close)
            try:
                issuer.start()
                self.assertTrue(entered.wait(timeout=2))
                closer.start()
                self.assertTrue(close_started.wait(timeout=2))
                self.assertFalse(closed.wait(timeout=0.05))
                with self.assertRaises(RecoveryVerificationProblem):
                    WindowsProjectRecoveryWitnessStore(self.store.root).acquire_project(PROJECT_ID)
            finally:
                release.set()
                issuer.join(timeout=3)
                if closer.ident is not None:
                    closer.join(timeout=3)
                exclusion.close()
            self.assertFalse(issuer.is_alive())
            self.assertFalse(closer.is_alive())
            self.assertEqual([], errors)
            self.assertTrue(closed.is_set())
        self.assertEqual(
            self.witness,
            self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256),
        )

    def test_failed_exclusion_read_closes_the_actual_opened_handle(self) -> None:
        read = windows_credentials_module._RecoveryHeldFile._read

        def failed_read(held):
            if held.path.name.endswith(".exclusion"):
                raise RecoveryVerificationProblem("synthetic-read-failure")
            return read(held)

        with (
            patch.object(windows_credentials_module._RecoveryHeldFile, "_read", failed_read),
            self.assertRaises(RecoveryVerificationProblem),
        ):
            self.store.acquire_project(PROJECT_ID)
        # A leaked SHARE_NONE handle would prevent this actual second open.
        fresh = WindowsProjectRecoveryWitnessStore(self.store.root)
        held = fresh.acquire_project(PROJECT_ID)
        try:
            held.validate()
        finally:
            held.close()

    def test_float_receipt_lengths_and_deep_json_are_typed_denials(self) -> None:
        exclusion = self.store.acquire_project(PROJECT_ID)
        try:
            self.store.issue(self.witness)
        finally:
            exclusion.close()
        anchor = next(self.store.root.glob("*.issuance.json"))
        original = anchor.read_bytes()
        receipt = json.loads(original)
        for field in ("innerBytes", "sealedBytes"):
            changed = dict(receipt)
            changed[field] = float(changed[field])
            anchor.write_bytes(json.dumps(changed).encode())
            with self.assertRaises(RecoveryVerificationProblem):
                self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256)
        anchor.write_bytes(b"[" * 1100 + b"0" + b"]" * 1100)
        with self.assertRaises(RecoveryVerificationProblem):
            self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256)
        anchor.write_bytes(original)
        self.assertEqual(
            self.witness,
            self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256),
        )

    def test_new_acquisition_in_same_core_instance_uses_immutable_distinct_token_binding(self) -> None:
        exclusion = self.store.acquire_project(PROJECT_ID)
        try:
            self.store.issue(self.witness)
            self.store.check_nonterminal(PROJECT_ID, self.instance, token_sha256=self.witness.recovery_token_sha256)
            self.store.issue(replace(self.witness, disposition="closed", witness_id=secrets.token_hex(32)))
            with self.assertRaises(RecoveryVerificationProblem):
                self.store.check_nonterminal(PROJECT_ID, self.instance, token_sha256=self.witness.recovery_token_sha256)
            next_session = replace(self.witness, recovery_token_sha256="4" * 64, witness_id=secrets.token_hex(32))
            self.store.issue(next_session)
            self.store.check_nonterminal(PROJECT_ID, self.instance, token_sha256=next_session.recovery_token_sha256)
            self.assertEqual(next_session, self.store.read(PROJECT_ID, self.instance, "created", token_sha256="4" * 64))
            self.assertEqual(self.witness, self.store.read(PROJECT_ID, self.instance, "created", token_sha256="1" * 64))
        finally:
            exclusion.close()

    def test_missing_or_modified_issuance_never_backfills_from_decode_success(self) -> None:
        exclusion = self.store.acquire_project(PROJECT_ID)
        try:
            self.store.issue(self.witness)
        finally:
            exclusion.close()
        anchor = next(self.store.root.glob("*.issuance.json"))
        original = anchor.read_bytes()
        anchor.write_bytes(b"{}")
        with self.assertRaises(RecoveryVerificationProblem):
            self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256)
        self.assertEqual(b"{}", anchor.read_bytes())
        anchor.write_bytes(original)
        anchor.unlink()
        with self.assertRaises(RecoveryVerificationProblem):
            self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256)
        self.assertFalse(anchor.exists())

    def test_tampered_sealed_record_and_hardlinked_anchor_deny(self) -> None:
        exclusion = self.store.acquire_project(PROJECT_ID)
        try:
            self.store.issue(self.witness)
        finally:
            exclusion.close()
        sealed = next(self.store.root.glob("*.sealed"))
        original = sealed.read_bytes()
        sealed.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaises(RecoveryVerificationProblem):
            self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256)
        sealed.write_bytes(original)
        anchor = next(self.store.root.glob("*.issuance.json"))
        os.link(anchor, self.parent / "linked-anchor")
        with self.assertRaises(RecoveryVerificationProblem):
            self.store.read(PROJECT_ID, self.instance, "created", token_sha256=self.witness.recovery_token_sha256)


@unittest.skipUnless(os.name == "nt", "Windows recovery filesystem and DPAPI fixtures")
class RecoveryCoordinatorTests(unittest.TestCase):
    """Actual copy/DPAPI fixtures with explicitly synthetic old-owner death.

    Unit Native responses never qualify shipping restart/principal boundaries.
    """

    def setUp(self) -> None:
        self.database_profile = development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.addCleanup(self.database_profile.__exit__, None, None, None)
        temporary = tempfile.TemporaryDirectory(prefix="ro-recovery-coordinator-")
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name).resolve() / "protected-parent"
        sid = windows_credentials_module._recovery_current_sid()
        with windows_credentials_module._recovery_security_attributes(sid) as attributes:
            self.assertTrue(
                windows_credentials_module._recovery_windows_api()["CreateDirectoryW"](str(self.parent), attributes)
            )
        self.store = WindowsProjectRecoveryWitnessStore(self.parent / "private-witnesses")
        principal = self.store.principal_reference

        class SyntheticNative:
            state: Literal["dead", "live", "pid-reused", "unknown"] = "dead"

            def current_session(inner):
                return RecoveryNativeSession(
                    principal,
                    "3" * 64,
                    RecoveryProcessIdentity(1, "0" * 16, "0" * 64),
                    RecoveryProcessIdentity(os.getpid(), "0" * 16, "0" * 64),
                )

            def inspect(inner, witness, source, destination):
                return RecoveryNativeInspection(
                    "3" * 64,
                    principal,
                    inner.state,
                    inner.state,
                    projects_module._recovery_file_identity(source),
                    projects_module._recovery_file_identity(destination.parent),
                )

        self.native = SyntheticNative()
        self.keys = FixtureKeys()
        first = ProjectLifecycleService(recovery_witness_store=self.store, recovery_native_authority=self.native)
        self.addCleanup(first.shutdown)
        created = first.create(
            parent_directory=str(self.parent),
            directory_name="original",
            display_name="Original study",
            template_id="theory-synthesis",
            trace_id="a" * 32,
        )
        self.root = Path(created.root)
        self.project_id = created.project_id
        objects = create_local_object_store(self.root, self.project_id, key_provider=self.keys)
        objects.put(
            io.BytesIO(b"synthetic encrypted recovery object"),
            ObjectPutCommand(
                "application/pdf",
                "allowed",
                "project-encrypted-v1",
                "project-lifetime",
                "test-fixture",
                CREATED_AT,
            ),
        )
        first.open(root=str(self.root), trace_id="a" * 32)
        self.assertIsNotNone(first._owned_sessions[self.root].witness)
        # Simulated abrupt death is isolated to this test-owned session. The
        # actual task still requires whole shipping Native AND Core death.
        owned = first._owned_sessions[self.root]
        owned.stop.set()
        assert owned.heartbeat is not None
        owned.heartbeat.join(timeout=2)
        owned.exclusion.close()
        first._owned_sessions.clear()
        first._opened.clear()
        first._owned_locks.clear()
        self.facts_before = canonical_facts(self.root, self.project_id)
        self.original_before = byte_inventory(self.root)
        self.service = ProjectLifecycleService(recovery_witness_store=self.store, recovery_native_authority=self.native)
        self.addCleanup(self.service.shutdown)
        privacy = ProjectPrivacyService(self.service, sqlite_privacy_policy_repository)

        def verify(root, identity, scope, cancel):
            policy = privacy.get(str(root), project_scope=scope)
            return object_store_module.verify_recovery_working_copy(
                RecoveryCopyVerificationRequest(
                    root,
                    identity,
                    RecoveryLocalReadAuthority(identity, policy.revision, policy.network_policy.value),
                    self.keys,
                    cancel,
                )
            )

        self.verify = verify
        self.service.configure_recovery_verifier(verify, key_access=lambda identity: None)
        self.destination = self.parent / "recovered"

    def preview(self):
        return self.service.preview_recovery(
            root=str(self.root), destination_root=str(self.destination), trace_id="b" * 32
        )

    def confirm(self, preview):
        self.service.confirm_recovery(
            root=str(self.root), preview_id=preview.preview_id, confirmation="recover-working-copy", trace_id="b" * 32
        )
        worker = self.service._recovery_previews[preview.preview_id].worker
        assert worker is not None
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        return self.service.recovery_status(root=str(self.root), preview_id=preview.preview_id)

    def test_synthetic_dead_owner_copy_preserves_raw_original_and_all_canonical_facts(self) -> None:
        preview = self.preview()
        self.assertEqual("preview-ready", preview.state, preview.reason_codes)
        result = self.confirm(preview)
        self.assertEqual("verified-copy-ready", result.state, result.reason_codes)
        self.assertEqual(self.original_before, byte_inventory(self.root))
        self.assertEqual(self.facts_before, canonical_facts(self.destination, self.project_id))
        self.assertFalse((self.destination / ".locks/session.lock").exists())
        archived = next((self.destination / "logs").glob("recovery-original-session-*.json"))
        self.assertEqual((self.root / ".locks/session.lock").read_bytes(), archived.read_bytes())
        self.assertFalse(self.service._opened)

    def test_authenticated_recovery_api_rejects_caller_proof_and_projects_only_public_fields(self) -> None:
        token = "0123456789abcdef" * 4
        authority = "127.0.0.1:49152"
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(token),
            expected_authority=authority,
            projects=self.service,
        )
        with TestClient(
            app,
            base_url=f"http://{authority}",
            client=("127.0.0.1", 50000),
            headers={"Authorization": f"Bearer {token}", "X-Trace-Id": "b" * 32},
        ) as client:
            command = {"root": str(self.root), "destinationRoot": str(self.destination)}
            self.assertEqual(
                401,
                client.post(
                    "/projects/recovery/preview", json=command, headers={"Authorization": "Bearer " + "0" * 64}
                ).status_code,
            )
            self.assertEqual(
                403,
                client.post(
                    "/projects/recovery/preview", json=command, headers={"Origin": "https://untrusted.example"}
                ).status_code,
            )
            self.assertEqual(
                422,
                client.post(
                    "/projects/recovery/preview", json={**command, "witness": {"ownerDead": True, "processId": 1}}
                ).status_code,
            )
            self.assertFalse(self.destination.exists())
            self.assertEqual(self.original_before, byte_inventory(self.root))
            response = client.post("/projects/recovery/preview", json=command)
            self.assertEqual(200, response.status_code, response.text)
            preview = response.json()
            self.assertEqual("preview-ready", preview["state"])
            self.assertEqual(
                {
                    "previewId",
                    "state",
                    "reasonCodes",
                    "requiresConfirmation",
                    "sourceDisplayLabel",
                    "destinationDisplayLabel",
                    "verifiedFactSummary",
                },
                set(preview),
            )
            self.assertNotIn(str(self.root), response.text)
            self.assertNotIn(self.project_id, response.text)
            address = {"root": str(self.root), "previewId": preview["previewId"]}
            self.assertEqual(
                422,
                client.post("/projects/recovery/confirm", json={**address, "confirmation": "take-over"}).status_code,
            )
            self.assertEqual(
                422, client.post("/projects/recovery/status", json={**address, "ownerDead": True}).status_code
            )
            self.assertEqual(405, client.get("/projects/recovery/status").status_code)
            cancelled = client.post("/projects/recovery/cancel", json=address)
            self.assertEqual(200, cancelled.status_code, cancelled.text)
            self.assertEqual("cancelled", cancelled.json()["state"])
            self.assertEqual("cancelled", client.post("/projects/recovery/status", json=address).json()["state"])
            self.assertFalse(self.destination.exists())
            self.assertEqual(self.original_before, byte_inventory(self.root))

    def test_api_attachment_failure_keeps_verified_copy_open_failed_until_explicit_retry(self) -> None:
        # This checks real API/coordinator composition, with a synthetic worker
        # attachment failure. Shipping workers remain a separate principal proof.
        preview = self.preview()
        self.assertEqual("verified-copy-ready", self.confirm(preview).state)
        imports = Mock(spec=ImportPreviewService)
        imports.attach.side_effect = RuntimeError("synthetic attachment failure")
        token = "0123456789abcdef" * 4
        authority = "127.0.0.1:49152"
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(token),
            expected_authority=authority,
            projects=self.service,
            imports=cast(ImportPreviewService, imports),
        )
        with TestClient(
            app,
            base_url=f"http://{authority}",
            client=("127.0.0.1", 50000),
            headers={"Authorization": f"Bearer {token}", "X-Trace-Id": "b" * 32},
        ) as client:
            with self.assertRaisesRegex(RuntimeError, "synthetic attachment failure"):
                client.post("/projects/open", json={"root": str(self.destination)})
            address = {"root": str(self.root), "previewId": preview.preview_id}
            failed = client.post("/projects/recovery/status", json=address)
            self.assertEqual("open-failed", failed.json()["state"])
            self.assertFalse((self.destination / ".locks/session.lock").exists())
            self.assertTrue(self.destination.exists())
            self.assertEqual(self.original_before, byte_inventory(self.root))
            imports.attach.side_effect = None
            opened = client.post("/projects/open", json={"root": str(self.destination)})
            self.assertEqual(200, opened.status_code, opened.text)
            self.assertEqual(self.project_id, opened.json()["projectId"])
            self.assertEqual("recovered", client.post("/projects/recovery/status", json=address).json()["state"])
            self.assertEqual(self.facts_before, canonical_facts(self.destination, self.project_id))
            self.assertEqual(self.original_before, byte_inventory(self.root))

    def test_api_completion_guard_failure_releases_attached_workers_and_new_lock(self) -> None:
        preview = self.preview()
        self.assertEqual("verified-copy-ready", self.confirm(preview).state)
        imports = Mock(spec=ImportPreviewService)
        authority = "127.0.0.1:49152"
        token = "1" * 64
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(token),
            expected_authority=authority,
            projects=self.service,
            imports=cast(ImportPreviewService, imports),
        )
        actual_completion = self.service.record_recovery_open

        def deny_completion(*, root, succeeded):
            if succeeded:
                raise self.service._recovery_problem()
            return actual_completion(root=root, succeeded=succeeded)

        with (
            patch.object(self.service, "record_recovery_open", deny_completion),
            TestClient(
                app,
                base_url=f"http://{authority}",
                client=("127.0.0.1", 50000),
                headers={"Authorization": f"Bearer {token}", "X-Trace-Id": "b" * 32},
            ) as client,
        ):
            response = client.post("/projects/open", json={"root": str(self.destination)})
            self.assertEqual(409, response.status_code)
            self.assertFalse(self.service._opened)
            self.assertFalse((self.destination / ".locks/session.lock").exists())
            imports.attach.assert_called_once_with(str(self.destination))
            imports.detach.assert_called_once_with(str(self.destination))
            status = self.service.recovery_status(root=str(self.root), preview_id=preview.preview_id)
            self.assertEqual("open-failed", status.state)
        self.assertEqual(self.original_before, byte_inventory(self.root))

    def test_live_unknown_and_reused_owner_responses_deny_without_copy(self) -> None:
        states: tuple[Literal["dead", "live", "pid-reused", "unknown"], ...] = ("live", "unknown", "pid-reused")
        for state in states:
            with self.subTest(state=state):
                self.native.state = state
                preview = self.preview()
                self.assertEqual("denied", preview.state)
                self.assertIn("owner-death-unproven", preview.reason_codes)
                self.assertFalse(self.destination.exists())
                self.assertEqual(self.original_before, byte_inventory(self.root))

    def test_target_collision_and_source_change_after_preview_each_deny(self) -> None:
        preview = self.preview()
        self.destination.mkdir()
        result = self.confirm(preview)
        self.assertEqual("verification-failed", result.state)
        self.assertTrue(self.destination.is_dir())
        self.assertEqual([], list(self.destination.iterdir()))
        self.assertEqual(self.original_before, byte_inventory(self.root))
        self.destination.rmdir()  # Exact empty test-owned collision fixture only.
        preview = self.preview()
        profile = self.root / "config/project-profile.json"
        record = json.loads(profile.read_bytes())
        record["displayName"] = "Changed study"
        profile.write_bytes(json.dumps(record).encode())
        after_operator_change = byte_inventory(self.root)
        result = self.confirm(preview)
        self.assertEqual("verification-failed", result.state)
        self.assertIn("source-inventory-changed", result.reason_codes)
        self.assertFalse(self.destination.exists())
        self.assertEqual(after_operator_change, byte_inventory(self.root))

    def test_status_and_cancel_remain_available_during_staged_verification(self) -> None:
        entered, release = threading.Event(), threading.Event()

        def bounded_verify(*arguments):
            entered.set()
            if not release.wait(timeout=3):
                raise RecoveryVerificationProblem("synthetic-timeout")
            return self.verify(*arguments)

        self.service._recovery_verifier = bounded_verify
        preview = self.preview()
        self.service.confirm_recovery(
            root=str(self.root), preview_id=preview.preview_id, confirmation="recover-working-copy", trace_id="b" * 32
        )
        worker = self.service._recovery_previews[preview.preview_id].worker
        assert worker is not None
        try:
            self.assertTrue(entered.wait(timeout=2))
            start = time.perf_counter()
            self.assertEqual(
                "copying", self.service.recovery_status(root=str(self.root), preview_id=preview.preview_id).state
            )
            self.service.cancel_recovery(root=str(self.root), preview_id=preview.preview_id)
            self.assertLess(time.perf_counter() - start, 0.5)
            with self.assertRaises(ProjectLifecycleProblem):
                self.service.confirm_recovery(
                    root=str(self.root),
                    preview_id=preview.preview_id,
                    confirmation="recover-working-copy",
                    trace_id="b" * 32,
                )
        finally:
            release.set()
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        result = self.service.recovery_status(root=str(self.root), preview_id=preview.preview_id)
        self.assertEqual("cancelled", result.state, result.reason_codes)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.original_before, byte_inventory(self.root))
        self.assertTrue(list(self.parent.glob(".recovered.ro-recovery-failed-*")))

    def test_simultaneous_confirms_publish_one_verified_copy_only(self) -> None:
        preview = self.preview()
        start = threading.Barrier(3)
        outcomes: list[str] = []

        def confirm() -> None:
            start.wait(timeout=3)
            try:
                self.service.confirm_recovery(
                    root=str(self.root),
                    preview_id=preview.preview_id,
                    confirmation="recover-working-copy",
                    trace_id="b" * 32,
                )
                outcomes.append("accepted")
            except ProjectLifecycleProblem:
                outcomes.append("denied")

        callers = [threading.Thread(target=confirm) for _ in range(2)]
        for caller in callers:
            caller.start()
        start.wait(timeout=3)
        for caller in callers:
            caller.join(timeout=4)
            self.assertFalse(caller.is_alive())
        self.assertEqual(["accepted", "denied"], sorted(outcomes))
        worker = self.service._recovery_previews[preview.preview_id].worker
        assert worker is not None
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(
            "verified-copy-ready",
            self.service.recovery_status(root=str(self.root), preview_id=preview.preview_id).state,
        )
        self.assertEqual(self.original_before, byte_inventory(self.root))
        self.assertEqual(self.facts_before, canonical_facts(self.destination, self.project_id))
        self.assertFalse(list(self.parent.glob(".recovered.ro-recovery-*")))

    def test_interrupted_staging_flush_preserves_source_and_quarantines_partial_copy(self) -> None:
        preview = self.preview()
        with patch.object(projects_module.os, "fsync", side_effect=OSError("synthetic staged disk failure")):
            result = self.confirm(preview)
        self.assertEqual("verification-failed", result.state)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.original_before, byte_inventory(self.root))
        quarantine = list(self.parent.glob(".recovered.ro-recovery-failed-*"))
        self.assertEqual(1, len(quarantine))
        self.assertTrue(any(path.is_file() for path in quarantine[0].rglob("*")))
        self.assertFalse(self.service._opened)

    def test_ordinary_owned_close_and_reopen_retains_distinct_eligible_witnesses(self) -> None:
        # Resume this fixture's original as a normal closed project, preserving
        # the test-owned retained old bytes separately before this deliberate edit.
        (self.root / ".locks/session.lock").unlink()
        first = self.service.open(root=str(self.root), trace_id="c" * 32)
        token = self.service._owned_sessions[self.root].record["recoveryToken"]
        self.assertTrue(first.open)
        self.service.close(root=str(self.root), trace_id="c" * 32)
        self.assertFalse((self.root / ".locks/session.lock").exists())
        self.service.open(root=str(self.root), trace_id="d" * 32)
        next_owner = self.service._owned_sessions[self.root]
        self.assertNotEqual(token, next_owner.record["recoveryToken"])
        self.assertIsNotNone(next_owner.witness)
        self.service.close(root=str(self.root), trace_id="d" * 32)

    def _open_fixture(self):
        # Only this synthetic-death fixture is deliberately changed for normal
        # lifecycle regression tests. Product recovery never deletes an old lock.
        (self.root / ".locks/session.lock").unlink()
        self.service.open(root=str(self.root), trace_id="e" * 32)
        owner = self.service._owned_sessions[self.root]
        owner.stop.set()
        assert owner.heartbeat is not None
        owner.heartbeat.join(timeout=2)
        return owner

    def test_close_preserves_changed_owned_lock_and_exclusion(self) -> None:
        owner = self._open_fixture()
        lock = self.root / ".locks/session.lock"
        original = lock.read_bytes()
        substitutions = {
            "projectId": str(uuid.uuid4()),
            "processId": owner.record["processId"] + 1,
            "recoveryToken": "f" * 64,
            "heartbeatAt": "invalid",
        }
        for field, value in substitutions.items():
            with self.subTest(field=field):
                lock.write_bytes(json.dumps({**owner.record, field: value}).encode())
                changed = lock.read_bytes()
                try:
                    with self.assertRaises(ProjectLifecycleProblem):
                        self.service.close(root=str(self.root), trace_id="e" * 32)
                    self.assertEqual(changed, lock.read_bytes())
                    with self.assertRaises(RecoveryVerificationProblem):
                        WindowsProjectRecoveryWitnessStore(self.store.root).acquire_project(self.project_id)
                finally:
                    lock.write_bytes(original)

    def test_shutdown_preserves_changed_same_instance_lock(self) -> None:
        owner = self._open_fixture()
        lock = self.root / ".locks/session.lock"
        lock.write_bytes(json.dumps({**owner.record, "recoveryToken": "f" * 64}).encode())
        changed = lock.read_bytes()
        self.service.shutdown()
        self.assertEqual(changed, lock.read_bytes())

    def test_failed_open_preserves_changed_lock_and_exclusion(self) -> None:
        lock = self.root / ".locks/session.lock"
        lock.unlink()  # Deliberate edit of the synthetic-death test fixture only.
        changed = []

        def failed_audit(*_arguments):
            record = json.loads(lock.read_bytes())
            record["recoveryToken"] = "f" * 64
            lock.write_bytes(json.dumps(record).encode())
            changed.append(lock.read_bytes())
            raise ProjectLifecycleProblem.rollback_failed()

        with (
            patch.object(self.service, "_audit", side_effect=failed_audit),
            self.assertRaises(ProjectLifecycleProblem),
        ):
            self.service.open(root=str(self.root), trace_id="e" * 32)
        self.assertEqual(changed[0], lock.read_bytes())
        with self.assertRaises(RecoveryVerificationProblem):
            WindowsProjectRecoveryWitnessStore(self.store.root).acquire_project(self.project_id)

    def test_invalid_heartbeat_returns_typed_denial_without_changing_source(self) -> None:
        lock = self.root / ".locks/session.lock"
        record = json.loads(lock.read_bytes())
        for heartbeat in ("invalid", "2026-02-30T00:00:00.000Z"):
            with self.subTest(heartbeat=heartbeat):
                lock.write_bytes(json.dumps({**record, "heartbeatAt": heartbeat}).encode())
                before = byte_inventory(self.root)
                preview = self.preview()
                self.assertEqual("denied", preview.state)
                self.assertIn("source-lock-invalid", preview.reason_codes)
                self.assertFalse(self.destination.exists())
                self.assertEqual(before, byte_inventory(self.root))

    def test_post_publish_probe_failure_quarantines_only_owned_target(self) -> None:
        preview = self.preview()
        actual = projects_module._path_identity
        failed: list[bool] = []

        def fail_once(path):
            if path == self.destination and path.exists() and not failed:
                failed.append(True)
                raise OSError("synthetic owned publication probe failure")
            return actual(path)

        with patch.object(projects_module, "_path_identity", side_effect=fail_once):
            result = self.confirm(preview)
        self.assertTrue(failed)
        self.assertEqual("verification-failed", result.state)
        self.assertFalse(self.destination.exists())
        self.assertTrue(list(self.parent.glob(".recovered.ro-recovery-failed-*")))
        self.assertEqual(self.original_before, byte_inventory(self.root))

    def test_verified_copy_becomes_recovered_only_after_normal_open_and_attachment(self) -> None:
        preview = self.preview()
        result = self.confirm(preview)
        self.assertEqual("verified-copy-ready", result.state)
        with self.assertRaises(ProjectLifecycleProblem):
            self.service.record_recovery_open(root=str(self.destination), succeeded=True)
        opened = self.service.open(root=str(self.destination), trace_id="e" * 32)
        self.assertTrue(opened.open)
        self.assertEqual(self.project_id, opened.project_id)
        self.assertEqual(
            "verified-copy-ready",
            self.service.recovery_status(root=str(self.root), preview_id=preview.preview_id).state,
        )
        self.service.record_recovery_open(root=str(self.destination), succeeded=True)
        self.assertEqual(
            "recovered", self.service.recovery_status(root=str(self.root), preview_id=preview.preview_id).state
        )
        self.assertEqual(self.original_before, byte_inventory(self.root))

    def test_replaced_verified_copy_is_denied_by_normal_open_without_mutation(self) -> None:
        preview = self.preview()
        self.assertEqual("verified-copy-ready", self.confirm(preview).state)
        self.destination.rename(self.parent / "preserved-verified-copy")
        self.service.create(
            parent_directory=str(self.parent),
            directory_name=self.destination.name,
            display_name="Replacement fixture",
            template_id="theory-synthesis",
            trace_id="f" * 32,
        )
        before = byte_inventory(self.destination)
        with self.assertRaises(ProjectLifecycleProblem):
            self.service.open(root=str(self.destination), trace_id="e" * 32)
        self.assertEqual(before, byte_inventory(self.destination))
        self.assertEqual(
            "open-failed", self.service.recovery_status(root=str(self.root), preview_id=preview.preview_id).state
        )
        self.assertEqual(self.original_before, byte_inventory(self.root))

    def test_close_audit_rollback_retains_ownership_and_restarts_heartbeat(self) -> None:
        owner = self._open_fixture()
        with (
            patch.object(self.service, "_audit", side_effect=ProjectLifecycleProblem.rollback_failed()),
            self.assertRaises(ProjectLifecycleProblem),
        ):
            self.service.close(root=str(self.root), trace_id="e" * 32)
        self.assertTrue(owner.heartbeat.is_alive())
        self.assertFalse(owner.stop.is_set())
        record, _material = projects_module._recovery_lock(self.root / ".locks/session.lock")
        self.assertEqual(owner.record, record)
        with self.assertRaises(RecoveryVerificationProblem):
            WindowsProjectRecoveryWitnessStore(self.store.root).acquire_project(self.project_id)
        self.service.close(root=str(self.root), trace_id="e" * 32)

    def test_actual_owned_heartbeat_refreshes_within_ten_second_cadence(self) -> None:
        owner = self._open_fixture()
        owner.stop = threading.Event()
        previous = dict(owner.record)
        self.service._start_heartbeat(self.root, owner)
        deadline = time.monotonic() + 12
        while owner.record == previous and time.monotonic() < deadline and not owner.stop.is_set():
            threading.Event().wait(timeout=0.05)
        self.assertFalse(owner.stop.is_set(), "owned heartbeat must not fail silently")
        self.assertNotEqual(previous["heartbeatAt"], owner.record["heartbeatAt"])
        record, _material = projects_module._recovery_lock(self.root / ".locks/session.lock")
        self.assertEqual(owner.record, record)
        for name in projects_module._LOCK_KEYS - {"heartbeatAt"}:
            self.assertEqual(previous[name], record[name])
        self.service.close(root=str(self.root), trace_id="e" * 32)

    def test_terminal_denied_previews_do_not_exhaust_admission(self) -> None:
        for _index in range(64):
            result = self.service.preview_recovery(
                root=str(self.parent / "missing-source"),
                destination_root=str(self.destination),
                trace_id="b" * 32,
            )
            self.assertIn(result.state, ("denied", "unavailable-proof"))
        result = self.preview()
        self.assertEqual("preview-ready", result.state, result.reason_codes)
        self.assertLessEqual(len(self.service._recovery_previews), 64)
        self.assertEqual(self.original_before, byte_inventory(self.root))

    def test_post_verifier_copy_mutation_never_publishes_verified_copy(self) -> None:
        for changed_kind in ("ciphertext", "canonical-database", "new-file", "derived-file", "audit"):
            with self.subTest(changed_kind=changed_kind):
                self.destination = self.parent / ("recovered-" + changed_kind)
                attempted = threading.Event()

                def mutate_after_verification(root, identity, scope, cancel, *, kind=changed_kind, signal=attempted):
                    facts = self.verify(root, identity, scope, cancel)
                    signal.set()
                    if kind == "ciphertext":
                        ciphertext = next((root / "objects").rglob("*.blob"))
                        material = bytearray(ciphertext.read_bytes())
                        material[-1] ^= 1
                        ciphertext.write_bytes(material)
                    elif kind == "canonical-database":
                        connection = open_canonical_database(
                            root / "state/project.sqlite3", expected_project_id=identity
                        )
                        try:
                            connection.execute("UPDATE object_records SET verified_at=?", (CREATED_AT,))
                            connection.commit()
                        finally:
                            connection.close()
                    elif kind == "new-file":
                        (root / "config/unverified.txt").write_bytes(b"synthetic unverified post-verifier addition")
                    elif kind == "derived-file":
                        (root / "cache/unverified.bin").write_bytes(b"synthetic unverified derived addition")
                    else:
                        with (root / "logs/project-lifecycle.jsonl").open("ab") as output:
                            output.write(b'{"synthetic":"unverified audit addition"}\n')
                    return facts

                with patch.object(self.service, "_recovery_verifier", mutate_after_verification):
                    preview = self.preview()
                    result = self.confirm(preview)
                self.assertTrue(attempted.is_set())
                self.assertEqual("verification-failed", result.state, result.reason_codes)
                self.assertFalse(self.destination.exists())
                self.assertFalse(self.service._opened)
                self.assertEqual(self.original_before, byte_inventory(self.root))
                self.assertTrue(list(self.parent.glob(f".{self.destination.name}.ro-recovery-failed-*")))

    def test_publication_gap_mutation_is_quarantined_before_ready_or_open(self) -> None:
        actual = projects_module._held_directory_renamer
        mutated = threading.Event()

        @contextmanager
        def mutate_during_publication(source):
            with actual(source) as publish:

                def inject(destination):
                    publish(destination)
                    if destination == self.destination:
                        with self.assertRaises(ProjectLifecycleProblem):
                            self.service.open(root=str(destination), trace_id="b" * 32)
                        ciphertext = next((destination / "objects").rglob("*.blob"))
                        material = bytearray(ciphertext.read_bytes())
                        material[-1] ^= 1
                        ciphertext.write_bytes(material)
                        mutated.set()

                yield inject

        preview = self.preview()
        with patch.object(projects_module, "_held_directory_renamer", mutate_during_publication):
            result = self.confirm(preview)
        self.assertTrue(mutated.is_set())
        self.assertEqual("verification-failed", result.state, result.reason_codes)
        self.assertIn("published-content-changed", result.reason_codes)
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.service._opened)
        self.assertEqual(self.original_before, byte_inventory(self.root))
        self.assertTrue(list(self.parent.glob(".recovered.ro-recovery-failed-*")))

    def test_failed_published_copy_denies_open_when_quarantine_is_unavailable(self) -> None:
        actual = projects_module._held_directory_renamer
        mutated = threading.Event()

        @contextmanager
        def fail_quarantine(source):
            if source == self.destination:
                raise OSError("synthetic quarantine unavailable")
            with actual(source) as publish:

                def inject(destination):
                    publish(destination)
                    if destination == self.destination:
                        (destination / "config/unverified.txt").write_bytes(b"synthetic published unverified bytes")
                        mutated.set()

                yield inject

        preview = self.preview()
        with patch.object(projects_module, "_held_directory_renamer", fail_quarantine):
            result = self.confirm(preview)
        self.assertTrue(mutated.is_set())
        self.assertEqual("verification-failed", result.state, result.reason_codes)
        self.assertTrue(self.destination.exists(), "failed quarantine must retain the actual destination")
        before_open = byte_inventory(self.destination)
        with self.assertRaises(ProjectLifecycleProblem):
            self.service.open(root=str(self.destination), trace_id="b" * 32)
        # A fresh Core has no in-memory preview authority. The retained copy
        # must still deny ordinary open without altering its incomplete bytes.
        fresh = ProjectLifecycleService(recovery_witness_store=self.store, recovery_native_authority=self.native)
        self.addCleanup(fresh.shutdown)
        with self.assertRaises(ProjectLifecycleProblem):
            fresh.open(root=str(self.destination), trace_id="b" * 32)
        self.assertEqual(before_open, byte_inventory(self.destination))
        self.assertFalse(self.service._opened)
        self.assertEqual(self.original_before, byte_inventory(self.root))

    def test_completion_marker_removal_failure_never_reports_ready(self) -> None:
        actual_unlink = Path.unlink
        attempted = threading.Event()

        def deny_marker_removal(path, *args, **kwargs):
            if path == self.destination / ".ro-recovery-incomplete":
                attempted.set()
                raise OSError("synthetic completion marker removal unavailable")
            return actual_unlink(path, *args, **kwargs)

        preview = self.preview()
        with patch.object(Path, "unlink", deny_marker_removal):
            result = self.confirm(preview)
        self.assertTrue(attempted.is_set())
        self.assertEqual("verification-failed", result.state, result.reason_codes)
        self.assertIsNone(result.verified_fact_summary)
        self.assertFalse(self.destination.exists())
        quarantined = list(self.parent.glob(".recovered.ro-recovery-failed-*"))
        self.assertEqual(1, len(quarantined))
        self.assertTrue((quarantined[0] / ".ro-recovery-incomplete").is_file())
        before_open = byte_inventory(quarantined[0])
        fresh = ProjectLifecycleService()
        self.addCleanup(fresh.shutdown)
        with self.assertRaises(ProjectLifecycleProblem):
            fresh.open(root=str(quarantined[0]), trace_id="b" * 32)
        self.assertEqual(before_open, byte_inventory(quarantined[0]))
        self.assertEqual(self.original_before, byte_inventory(self.root))

    def test_valid_timestamp_change_after_owned_audit_append_denies_publication(self) -> None:
        actual_audit = self.service._audit
        mutated = threading.Event()

        def rewrite_owned_append(root, event, state, trace_id):
            owned = actual_audit(root, event, state, trace_id)
            if event == "project.recovery-copy-verified":
                path = root / "logs/project-lifecycle.jsonl"
                lines = path.read_bytes().splitlines(keepends=True)
                record = json.loads(lines[-1])
                record["recordedAt"] = "2001-01-01T00:00:00Z"
                lines[-1] = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
                path.write_bytes(b"".join(lines))
                mutated.set()
            return owned

        preview = self.preview()
        with patch.object(self.service, "_audit", rewrite_owned_append):
            result = self.confirm(preview)
        self.assertTrue(mutated.is_set())
        self.assertEqual("verification-failed", result.state, result.reason_codes)
        self.assertIn("staging-audit-changed", result.reason_codes)
        self.assertFalse(self.destination.exists())
        self.assertIsNone(result.verified_fact_summary)
        self.assertEqual(self.original_before, byte_inventory(self.root))


class NativeControlWriterTests(unittest.TestCase):
    def test_close_with_full_queue_discards_unsent_frames_and_stops_writer(self) -> None:
        entered, release = threading.Event(), threading.Event()
        records = []

        class BlockedOutput:
            def write(inner, record):
                entered.set()
                if not release.wait(timeout=3):
                    raise OSError("synthetic pipe deadline")
                records.append(bytes(record))

            def flush(inner):
                pass

        # Only write/flush are used; this deliberately blocking pipe fixture
        # exercises cancellation without implementing unrelated file methods.
        client = windows_credentials_module.WindowsRecoveryNativeAuthority(cast(BinaryIO, BlockedOutput()))
        self.addCleanup(client.close)
        try:
            client.announce()
            self.assertTrue(entered.wait(timeout=1))
            for _index in range(8):
                client.announce()
            client.close()
            with self.assertRaises(RecoveryVerificationProblem):
                client.announce()
        finally:
            release.set()
        client._writer.join(timeout=1)
        self.assertFalse(client._writer.is_alive())
        self.assertEqual(1, len(records))


def _anonymous_witness_denial(root: str, project_id: str, instance: str, token_hash: str) -> None:
    """Isolated child keeps any failed impersonation reversion out of the runner."""
    import ctypes
    from ctypes import wintypes

    store = WindowsProjectRecoveryWitnessStore(Path(root))
    owner = store.read(project_id, instance, "created", token_sha256=token_hash)
    sealed = (store.root / (store._name(project_id, instance, "created", token_hash) + ".sealed")).read_bytes()
    protector = windows_credentials_module.WindowsCurrentUserDataProtector()
    inner = protector.unprotect(sealed)
    owner_plaintext = protector.unprotect(bytes(inner))
    windows_credentials_module._zero(owner_plaintext)
    # Load the needed APIs while still the owner; no library/path changes while impersonating.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentThread.restype = wintypes.HANDLE
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.ImpersonateAnonymousToken.argtypes = [wintypes.HANDLE]
    advapi.ImpersonateAnonymousToken.restype = wintypes.BOOL
    advapi.RevertToSelf.argtypes = []
    advapi.RevertToSelf.restype = wintypes.BOOL
    if not advapi.ImpersonateAnonymousToken(kernel.GetCurrentThread()):
        windows_credentials_module._zero(inner)
        raise AssertionError("Anonymous-principal test setup failed")
    acl_denied = dpapi_denied = False
    try:
        try:
            store.read(project_id, instance, "created", token_sha256=token_hash)
        except RecoveryVerificationProblem:
            acl_denied = True
        try:
            unexpected = protector.unprotect(bytes(inner))
        except windows_credentials_module.SecretUnavailable:
            dpapi_denied = True
        else:
            windows_credentials_module._zero(unexpected)
    finally:
        windows_credentials_module._zero(inner)
        if not advapi.RevertToSelf():
            os._exit(70)  # Only this isolated test child; never keep an unexpected security context.
    assert acl_denied and dpapi_denied, "Actual anonymous ACL/current-user DPAPI denial was not established"
    assert store.read(project_id, instance, "created", token_sha256=token_hash) == owner
    print(
        json.dumps(
            {
                "anonymousPrivateAclDenied": acl_denied,
                "anonymousUserDpapiDenied": dpapi_denied,
                "ownerReadbackAfterRevert": True,
                "foreignHostTest": False,
            }
        )
    )


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[1] == "--anonymous-witness-denial":
        _anonymous_witness_denial(*sys.argv[2:])
    else:
        unittest.main()
