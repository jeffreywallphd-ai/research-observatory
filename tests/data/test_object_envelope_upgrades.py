from __future__ import annotations

import hashlib
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core import object_store, storage  # noqa: E402
from research_observatory_core.migrations.versions import v0002_schema_history  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.object_store import (  # noqa: E402
    ObjectCorrupt,
    ObjectKeyUnavailable,
    ObjectPutCommand,
    ObjectStoreProblem,
)
from research_observatory_core.ports.object_store_keys import ObjectMasterKey  # noqa: E402

PROJECT_ID = "01890f6e-6a40-4cc5-98b7-7f3f36b60210"
CREATED_AT = "2026-08-18T12:00:00.000Z"
MASTER_KEY = bytes.fromhex("31" * 32)


class MemoryKeyProvider:
    def __init__(self, keys: dict[str, bytes], active: str) -> None:
        self.keys = dict(keys)
        self.active = active

    def active_object_master_key(self) -> ObjectMasterKey:
        return ObjectMasterKey(self.active, self.keys[self.active])

    def object_master_key(self, key_version: str) -> ObjectMasterKey | None:
        key = self.keys.get(key_version)
        return None if key is None else ObjectMasterKey(key_version, key)


def command() -> ObjectPutCommand:
    return ObjectPutCommand(
        media_type="application/pdf",
        rights_status="allowed",
        protection_profile="project-encrypted-v1",
        retention_class="project-lifetime",
        created_at=CREATED_AT,
    )


def create_v2_project(
    root: Path,
    plaintext: bytes,
    *,
    project_id: str = PROJECT_ID,
) -> tuple[str, Path]:
    for relative in ("state", "objects", ".tmp"):
        (root / relative).mkdir(parents=True, mode=0o700, exist_ok=True)
    database = root / "state" / "project.sqlite3"
    digest = hashlib.sha256(plaintext).hexdigest()
    connection = sqlite3.connect(database, autocommit=True)
    try:
        storage._configure_connection(connection, initialize=True)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={storage.PREVIOUS_DATABASE_SCHEMA_VERSION}")
        for statement in (
            v0002_schema_history.SCHEMA_METADATA_V2_DDL,
            *storage._V1_DDL_STATEMENTS[1:],
            v0002_schema_history.SCHEMA_MIGRATIONS_DDL,
            *v0002_schema_history.SCHEMA_MIGRATIONS_TRIGGERS,
        ):
            connection.execute(statement)
        connection.execute(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            ) VALUES (1, 2, ?, ?, ?, ?, ?)
            """,
            (
                storage.DATABASE_PROFILE,
                storage.APPLICATION_ID,
                storage.PREVIOUS_PROFILE_SHA256,
                storage.PREVIOUS_SCHEMA_SHA256,
                CREATED_AT,
            ),
        )
        connection.execute(
            """
            INSERT INTO projects (singleton, project_id, project_id_scheme, created_at)
            VALUES (1, ?, 'uuid4-bridge', ?)
            """,
            (project_id, CREATED_AT),
        )
        connection.execute(
            """
            INSERT INTO object_records (
                object_sha256, project_id, byte_length, media_type, rights_status,
                protection_profile, retention_class, storage_state, created_at, verified_at
            ) VALUES (?, ?, ?, 'application/pdf', 'allowed', 'plaintext-fixture-v1',
                      'project-lifetime', 'available', ?, ?)
            """,
            (digest, project_id, len(plaintext), CREATED_AT, CREATED_AT),
        )
        connection.execute("COMMIT")
        self_fingerprint = storage._schema_fingerprint(connection)
        if self_fingerprint != storage.PREVIOUS_SCHEMA_SHA256:
            raise AssertionError(self_fingerprint)
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise AssertionError(checkpoint)
    finally:
        connection.close()
    opaque = object_store._opaque_name(project_id, digest)
    bucket = root / "objects" / opaque[:2] / opaque[2:4]
    bucket.mkdir(parents=True, mode=0o700)
    physical = bucket / f"{opaque}.blob"
    physical.write_bytes(plaintext)
    return digest, physical


class ObjectEnvelopeUpgradeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-object-upgrade-")
        self.root = Path(self.temporary.name).resolve(strict=True) / "project"
        self.provider = MemoryKeyProvider({"object-key-v1": MASTER_KEY}, "object-key-v1")

    def tearDown(self) -> None:
        if os.name == "nt":
            subprocess.run(
                [
                    str(Path(os.environ["SYSTEMROOT"]) / "System32" / "icacls.exe"),
                    self.temporary.name,
                    "/reset",
                    "/t",
                    "/c",
                    "/q",
                ],
                capture_output=True,
                check=False,
                timeout=30,
            )
        self.temporary.cleanup()

    def test_v2_plaintext_is_upgraded_before_store_returns_and_restart_opens_it(self) -> None:
        plaintext = b"supported prior plaintext object"
        digest, physical = create_v2_project(self.root, plaintext)

        store = create_local_object_store(self.root, PROJECT_ID, key_provider=self.provider)

        self.assertEqual(4, storage.DATABASE_SCHEMA_VERSION)
        self.assertNotEqual(plaintext, physical.read_bytes())
        self.assertNotIn(plaintext, physical.read_bytes())
        self.assertEqual((), tuple(self.root.rglob("*.upgrade-rollback")))
        self.assertEqual((), tuple(self.root.rglob("*.upgrade-replacement")))
        self.assertEqual((), tuple((self.root / ".tmp").rglob("*.partial")))
        with store.open(digest, purpose="document-analysis") as stream:
            self.assertEqual(plaintext, stream.read())
        restarted = create_local_object_store(self.root, PROJECT_ID, key_provider=self.provider)
        with restarted.open(digest, purpose="document-analysis") as stream:
            self.assertEqual(plaintext, stream.read())
        connection = storage.open_canonical_database(
            self.root / "state" / "project.sqlite3", expected_project_id=PROJECT_ID
        )
        try:
            self.assertEqual(
                ("complete", "secretstream-xchacha20poly1305-v1", "project-encrypted-v1"),
                tuple(
                    connection.execute(
                        """
                        SELECT upgrade.phase, object.envelope_version, object.protection_profile
                          FROM object_envelope_upgrades AS upgrade
                          JOIN object_records AS object USING (object_sha256, project_id)
                         WHERE upgrade.object_sha256=?
                        """,
                        (digest,),
                    ).fetchone()
                ),
            )
        finally:
            connection.close()

    def test_project_open_holds_the_session_lock_until_upgrade_and_verification_complete(self) -> None:
        from research_observatory_core.projects import ProjectLifecycleService

        parent = Path(self.temporary.name).resolve(strict=True) / "projects"
        parent.mkdir(mode=0o700)
        bootstrap = ProjectLifecycleService()
        project = bootstrap.create(
            parent_directory=str(parent),
            directory_name="legacy-project",
            display_name="Legacy project",
            template_id="theory-synthesis",
            trace_id="a" * 32,
        )
        root = Path(project.root)
        database = root / "state" / "project.sqlite3"
        database.unlink()
        plaintext = b"project-open legacy object"
        project_id = str(project.project_id)
        digest, physical = create_v2_project(root, plaintext, project_id=project_id)
        lifecycle = ProjectLifecycleService(
            object_upgrade=lambda candidate, identity: create_local_object_store(
                candidate,
                identity,
                key_provider=self.provider,
            )
        )

        opened = lifecycle.open(root=str(root), trace_id="b" * 32)

        self.assertEqual("read-write", opened.access_mode.value)
        self.assertTrue((root / ".locks" / "session.lock").is_file())
        self.assertNotEqual(plaintext, physical.read_bytes())
        store = create_local_object_store(root, project_id, key_provider=self.provider)
        with store.open(digest, purpose="document-analysis") as stream:
            self.assertEqual(plaintext, stream.read())
        lifecycle.shutdown()

    def test_every_upgrade_boundary_restarts_to_one_verified_encrypted_object(self) -> None:
        boundaries = (
            "legacy-detected",
            "replacement-writing",
            "replacement-verified",
            "swap-intent",
            "original-moved-to-rollback",
            "replacement-moved-to-canonical",
            "metadata-committed",
            "rollback-removed",
            "complete",
        )
        for index, boundary in enumerate(boundaries):
            with self.subTest(boundary=boundary):
                root = self.root / str(index)
                plaintext = f"restart boundary {boundary}".encode()
                digest, physical = create_v2_project(root, plaintext)

                def interrupt(completed: str, expected: str = boundary) -> None:
                    if completed == expected:
                        raise ObjectStoreProblem("deterministic upgrade interruption")

                with (
                    patch.object(object_store, "_upgrade_step_completed", interrupt),
                    self.assertRaises(ObjectStoreProblem),
                ):
                    create_local_object_store(root, PROJECT_ID, key_provider=self.provider)

                recovered = create_local_object_store(root, PROJECT_ID, key_provider=self.provider)
                with recovered.open(digest, purpose="document-analysis") as stream:
                    self.assertEqual(plaintext, stream.read())
                self.assertNotEqual(plaintext, physical.read_bytes())
                self.assertEqual((), tuple(root.rglob("*.upgrade-rollback")))
                self.assertEqual((), tuple(root.rglob("*.upgrade-replacement")))
                for candidate in (root / ".tmp").rglob("*"):
                    if candidate.is_file():
                        self.assertNotIn(plaintext, candidate.read_bytes())

    def test_missing_key_and_corrupt_source_preserve_the_only_plaintext_authority(self) -> None:
        plaintext = b"recoverable legacy source"
        digest, physical = create_v2_project(self.root, plaintext)
        unavailable = MemoryKeyProvider({}, "missing-key")

        with self.assertRaises(ObjectKeyUnavailable):
            create_local_object_store(self.root, PROJECT_ID, key_provider=unavailable)
        self.assertEqual(plaintext, physical.read_bytes())

        physical.write_bytes(b"corrupt legacy source")
        with self.assertRaises(ObjectCorrupt):
            create_local_object_store(self.root, PROJECT_ID, key_provider=self.provider)
        self.assertEqual(b"corrupt legacy source", physical.read_bytes())
        connection = storage.open_canonical_database(
            self.root / "state" / "project.sqlite3", expected_project_id=PROJECT_ID
        )
        try:
            self.assertEqual(
                ("replacement-writing", "source-corrupt"),
                tuple(
                    connection.execute(
                        "SELECT phase, failure_code FROM object_envelope_upgrades WHERE object_sha256=?",
                        (digest,),
                    ).fetchone()
                ),
            )
        finally:
            connection.close()

    def test_disk_rename_and_sqlite_failures_retain_a_verified_recovery_authority(self) -> None:
        for index, failure_kind in enumerate(("disk", "rename", "sqlite")):
            with self.subTest(failure_kind=failure_kind):
                root = self.root / f"failure-{index}"
                plaintext = f"recover after {failure_kind} failure".encode()
                digest, physical = create_v2_project(root, plaintext)
                context: AbstractContextManager[object]
                if failure_kind == "disk":
                    context = patch.object(
                        object_store,
                        "_stream_to_staging",
                        side_effect=OSError("insufficient disk"),
                    )
                elif failure_kind == "rename":
                    original_move = object_store._move_no_replace

                    def fail_rollback_move(
                        source: Path,
                        destination: Path,
                        move: object = original_move,
                    ) -> None:
                        if destination.name.endswith(".upgrade-rollback"):
                            raise OSError("rename denied")
                        if not callable(move):
                            raise AssertionError("move seam is not callable")
                        move(source, destination)

                    context = patch.object(object_store, "_move_no_replace", fail_rollback_move)
                else:
                    context = patch.object(
                        object_store,
                        "_commit_upgrade_metadata",
                        side_effect=sqlite3.OperationalError("database is locked"),
                    )
                with context, self.assertRaises(ObjectStoreProblem):
                    create_local_object_store(root, PROJECT_ID, key_provider=self.provider)

                recoverable_plaintext = physical.exists() and physical.read_bytes() == plaintext
                recoverable_plaintext = recoverable_plaintext or any(
                    candidate.read_bytes() == plaintext
                    for candidate in root.rglob("*.upgrade-rollback")
                    if candidate.is_file()
                )
                self.assertTrue(recoverable_plaintext)
                recovered = create_local_object_store(root, PROJECT_ID, key_provider=self.provider)
                with recovered.open(digest, purpose="document-analysis") as stream:
                    self.assertEqual(plaintext, stream.read())
                self.assertEqual((), tuple(root.rglob("*.upgrade-rollback")))
                self.assertEqual((), tuple(root.rglob("*.upgrade-replacement")))

    def test_envelope_and_wrapped_key_tamper_follow_the_approved_classification(self) -> None:
        corrupt_mutations = {
            "magic": lambda payload: payload.__setitem__(0, payload[0] ^ 0x80),
            "header": lambda payload: payload.__setitem__(4, payload[4] ^ 0x80),
            "frame-length": lambda payload: payload.__setitem__(28, 0xFF),
            "missing-final": lambda payload: payload.__delitem__(slice(-1, None)),
            "trailing": lambda payload: payload.extend(b"x"),
        }
        for index, (name, mutate) in enumerate(corrupt_mutations.items()):
            with self.subTest(kind=name):
                root = self.root / f"corrupt-{index}"
                for relative in ("state", "objects", ".tmp"):
                    (root / relative).mkdir(parents=True, mode=0o700)
                storage.initialize_database(
                    root / "state" / "project.sqlite3",
                    project_id=PROJECT_ID,
                    project_created_at=CREATED_AT,
                )
                store = create_local_object_store(root, PROJECT_ID, key_provider=self.provider)
                stored = store.put(io.BytesIO(b"tamper classification"), command())
                physical = next(path for path in (root / "objects").rglob("*") if path.is_file())
                payload = bytearray(physical.read_bytes())
                mutate(payload)
                physical.write_bytes(payload)
                with self.assertRaises(ObjectCorrupt):
                    store.open(stored.object_sha256, purpose="document-analysis")
                self.assertEqual("quarantined", store.metadata(stored.object_sha256).storage_state)

        for index, column in enumerate(("wrapped_key", "wrap_nonce", "key_version")):
            with self.subTest(column=column):
                root = self.root / f"key-{index}"
                for relative in ("state", "objects", ".tmp"):
                    (root / relative).mkdir(parents=True, mode=0o700)
                storage.initialize_database(
                    root / "state" / "project.sqlite3",
                    project_id=PROJECT_ID,
                    project_created_at=CREATED_AT,
                )
                store = create_local_object_store(root, PROJECT_ID, key_provider=self.provider)
                stored = store.put(io.BytesIO(b"wrapped key classification"), command())
                connection = storage.open_canonical_database(
                    root / "state" / "project.sqlite3", expected_project_id=PROJECT_ID
                )
                try:
                    if column == "key_version":
                        connection.execute(
                            "UPDATE object_records SET key_version='missing-key' WHERE object_sha256=?",
                            (stored.object_sha256,),
                        )
                    else:
                        value = str(
                            connection.execute(
                                f"SELECT {column} FROM object_records WHERE object_sha256=?",
                                (stored.object_sha256,),
                            ).fetchone()[0]
                        )
                        replacement = ("0" if value[0] != "0" else "1") + value[1:]
                        connection.execute(
                            f"UPDATE object_records SET {column}=? WHERE object_sha256=?",
                            (replacement, stored.object_sha256),
                        )
                finally:
                    connection.close()
                with self.assertRaises(ObjectKeyUnavailable):
                    store.open(stored.object_sha256, purpose="document-analysis")
                self.assertEqual("available", store.metadata(stored.object_sha256).storage_state)


if __name__ == "__main__":
    unittest.main()
