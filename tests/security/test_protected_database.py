from __future__ import annotations

import base64
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "services" / "core-api" / "src"
sys.path.insert(0, str(CORE_SRC))

from research_observatory_core import storage as storage_module  # noqa: E402
from research_observatory_core.migrations.runner import migrate_database  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    DATABASE_SCHEMA_VERSION,
    SQLCIPHER_PROFILE,
    StorageProblem,
    configure_protected_database_provider,
    create_protected_database_backup,
    database_protection_profile,
    development_plaintext_database_fixture,
    initialize_database,
    migrate_plaintext_database_to_protected,
    open_canonical_database,
    recover_plaintext_database_migration,
    recover_protected_database_rekey,
    rekey_protected_database,
    restore_protected_database_backup,
)

from tests.data.test_sqlite_migrations import create_version_4_fixture  # noqa: E402
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402

PROJECT_ID = "123e4567-e89b-42d3-a456-426614174000"
CREATED_AT = "2026-08-27T00:00:00.000Z"


class ProtectedDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.state = self.root / "state"
        self.state.mkdir()
        (self.root / ".tmp").mkdir()
        self.database = self.state / "project.sqlite3"
        self.keys = InMemoryDatabaseKeyProvider()
        configure_protected_database_provider(self.keys)

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

    def test_production_profile_encrypts_header_and_reopens_with_vault_key(self) -> None:
        report = initialize_database(
            self.database,
            project_id=PROJECT_ID,
            project_created_at=CREATED_AT,
        )

        self.assertTrue(report.ok, report.errors)
        self.assertEqual(database_protection_profile(), SQLCIPHER_PROFILE)
        self.assertNotEqual(self.database.read_bytes()[:16], b"SQLite format 3\x00")

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(connection.execute("SELECT project_id FROM projects").fetchone()[0], PROJECT_ID)
        finally:
            connection.close()
        plaintext = sqlite3.connect(self.database)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                plaintext.execute("SELECT project_id FROM projects").fetchone()
        finally:
            plaintext.close()

    def test_missing_active_key_fails_closed_without_replacing_database(self) -> None:
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        before = self.database.read_bytes()
        self.keys.forget_active(PROJECT_ID)

        with self.assertRaises(StorageProblem):
            open_canonical_database(self.database, expected_project_id=PROJECT_ID)

        self.assertEqual(self.database.read_bytes(), before)

    def test_rekey_rotates_vault_authority_and_survives_restart(self) -> None:
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        previous = self.keys.active_version(PROJECT_ID)

        report = rekey_protected_database(
            self.database,
            project_id=PROJECT_ID,
            operation_id="1" * 32,
        )

        self.assertEqual(report.outcome, "rekeyed")
        self.assertEqual(report.previous_key_version, previous)
        self.assertNotEqual(report.active_key_version, previous)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        connection.close()
        self.assertFalse(tuple((self.root / ".tmp").glob("database-rekey-*")))

    def test_interrupted_rekey_activates_staged_vault_key_on_recovery(self) -> None:
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)

        with self.assertRaisesRegex(RuntimeError, "injected rekey interruption"):
            rekey_protected_database(
                self.database,
                project_id=PROJECT_ID,
                operation_id="2" * 32,
                failure_hook=lambda boundary: (
                    (_ for _ in ()).throw(RuntimeError("injected rekey interruption"))
                    if boundary == "after-database-rekeyed"
                    else None
                ),
            )

        report = recover_protected_database_rekey(
            self.database,
            project_id=PROJECT_ID,
            operation_id="2" * 32,
        )
        self.assertEqual(report.outcome, "staged-key-activated")
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        connection.close()

    def create_plaintext_legacy_database(self) -> bytes:
        with development_plaintext_database_fixture():
            initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        before = self.database.read_bytes()
        self.assertEqual(before[:16], b"SQLite format 3\x00")
        return before

    def test_plaintext_migration_requires_consent_and_publishes_only_protected_database(self) -> None:
        before = self.create_plaintext_legacy_database()
        with self.assertRaises(StorageProblem):
            migrate_plaintext_database_to_protected(
                self.database,
                project_id=PROJECT_ID,
                operation_id="3" * 32,
                approval_token="",
            )

        report = migrate_plaintext_database_to_protected(
            self.database,
            project_id=PROJECT_ID,
            operation_id="3" * 32,
            approval_token="approve-plaintext-to-protected-v1",
        )

        self.assertEqual(report.outcome, "protected")
        self.assertNotEqual(self.database.read_bytes()[:16], before[:16])
        self.assertFalse(tuple((self.root / ".tmp").glob("*.plaintext-rollback")))
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        connection.close()

    def test_interrupted_plaintext_publication_recovers_without_writable_plaintext_canonical(self) -> None:
        self.create_plaintext_legacy_database()
        with self.assertRaisesRegex(RuntimeError, "injected migration interruption"):
            migrate_plaintext_database_to_protected(
                self.database,
                project_id=PROJECT_ID,
                operation_id="4" * 32,
                approval_token="approve-plaintext-to-protected-v1",
                failure_hook=lambda boundary: (
                    (_ for _ in ()).throw(RuntimeError("injected migration interruption"))
                    if boundary == "after-source-staged"
                    else None
                ),
            )
        self.assertFalse(self.database.exists())

        report = recover_plaintext_database_migration(
            self.database,
            project_id=PROJECT_ID,
            operation_id="4" * 32,
        )

        self.assertEqual(report.outcome, "protected-recovered")
        self.assertNotEqual(self.database.read_bytes()[:16], b"SQLite format 3\x00")
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        connection.close()

    def test_encrypted_backup_restores_consistent_state_and_rejects_corruption(self) -> None:
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            connection.execute(
                """
                INSERT INTO settings (
                    setting_id, project_id, setting_key, revision, value_type,
                    text_value, created_at, modified_at
                ) VALUES (?, ?, 'privacy.mode', 0, 'text', 'offline', ?, ?)
                """,
                ("01890f6e-6a40-7cc5-98b7-123456789ab1", PROJECT_ID, CREATED_AT, CREATED_AT),
            )
        finally:
            connection.close()
        backup = self.root / "protected-backup.sqlite3"
        report = create_protected_database_backup(self.database, backup, project_id=PROJECT_ID)
        self.assertEqual(report.protection_profile, SQLCIPHER_PROFILE)
        self.assertNotEqual(backup.read_bytes()[:16], b"SQLite format 3\x00")

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            connection.execute(
                """
                INSERT INTO settings (
                    setting_id, project_id, setting_key, revision, value_type,
                    text_value, created_at, modified_at
                ) VALUES (?, ?, 'privacy.mode', 1, 'text', 'remote-approved', ?, ?)
                """,
                ("01890f6e-6a40-7cc5-98b7-123456789ab2", PROJECT_ID, CREATED_AT, CREATED_AT),
            )
        finally:
            connection.close()
        restore = restore_protected_database_backup(
            backup,
            self.database,
            project_id=PROJECT_ID,
            operation_id="5" * 32,
        )
        self.assertEqual(restore.outcome, "restored")
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM settings").fetchone()[0], 1)
        finally:
            connection.close()

        corrupt = self.root / "corrupt-backup.sqlite3"
        corrupt.write_bytes(backup.read_bytes())
        payload = bytearray(corrupt.read_bytes())
        payload[min(128, len(payload) - 1)] ^= 0xFF
        corrupt.write_bytes(payload)
        before = self.database.read_bytes()
        with self.assertRaises(StorageProblem):
            restore_protected_database_backup(
                corrupt,
                self.database,
                project_id=PROJECT_ID,
                operation_id="6" * 32,
            )
        self.assertEqual(self.database.read_bytes(), before)

    def test_corruption_and_key_loss_fail_closed_without_replacement(self) -> None:
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        payload = bytearray(self.database.read_bytes())
        payload[min(128, len(payload) - 1)] ^= 0x80
        self.database.write_bytes(payload)
        corrupted = self.database.read_bytes()

        with self.assertRaises(StorageProblem):
            open_canonical_database(self.database, expected_project_id=PROJECT_ID)

        self.assertEqual(self.database.read_bytes(), corrupted)

    def test_restore_publication_failure_rolls_back_the_exact_encrypted_database(self) -> None:
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        backup = self.root / "rollback-backup.sqlite3"
        create_protected_database_backup(self.database, backup, project_id=PROJECT_ID)
        before = self.database.read_bytes()
        original_replace = os.replace

        def fail_candidate_publication(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
            source_path = Path(source)
            if ".candidate.sqlite3" in source_path.name and Path(destination) == self.database:
                raise OSError("injected restore publication failure")
            original_replace(source, destination)

        with (
            patch.object(storage_module.os, "replace", side_effect=fail_candidate_publication),
            self.assertRaises(StorageProblem),
        ):
            restore_protected_database_backup(
                backup,
                self.database,
                project_id=PROJECT_ID,
                operation_id="7" * 32,
            )

        self.assertEqual(self.database.read_bytes(), before)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        connection.close()

    def test_key_material_is_absent_from_project_backup_process_and_diagnostics(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
            backup = self.root / "disclosure-scan-backup.sqlite3"
            create_protected_database_backup(self.database, backup, project_id=PROJECT_ID)
        material = self.keys.active_material_for_test(PROJECT_ID)
        patterns = (material, material.hex().encode("ascii"), base64.b64encode(material))
        for candidate in self.root.rglob("*"):
            if candidate.is_file():
                content = candidate.read_bytes()
                for pattern in patterns:
                    self.assertNotIn(pattern, content, candidate)
        process_projection = "\n".join((*sys.argv, *(f"{key}={value}" for key, value in os.environ.items()))).encode()
        diagnostics = output.getvalue().encode()
        for pattern in patterns:
            self.assertNotIn(pattern, process_projection)
            self.assertNotIn(pattern, diagnostics)

    def test_prior_protected_schema_migrates_with_an_encrypted_verified_backup(self) -> None:
        legacy = self.root / "legacy" / "state" / "project.sqlite3"
        create_version_4_fixture(legacy)
        with self.keys.active_key(PROJECT_ID, create=True) as lease:
            material = lease.use(bytes)
        source = sqlcipher.connect(legacy.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        key_literal = f"x'{material.hex()}'"
        try:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(self.database), key_literal))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={0x524F4253}")
            source.execute("PRAGMA protected.user_version=4")
            self.assertEqual(source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0], "wal")
            source.execute("DETACH DATABASE protected")
        finally:
            key_literal = ""
            source.close()
        legacy.unlink()

        result = migrate_database(self.database, expected_project_id=PROJECT_ID)

        self.assertEqual(result.status, "migrated")
        self.assertEqual(result.source_schema_version, 4)
        self.assertEqual(result.target_schema_version, DATABASE_SCHEMA_VERSION)
        self.assertIsNotNone(result.backup_relative_path)
        backup = self.root / str(result.backup_relative_path)
        self.assertNotEqual(backup.read_bytes()[:16], b"SQLite format 3\x00")
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], DATABASE_SCHEMA_VERSION)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
