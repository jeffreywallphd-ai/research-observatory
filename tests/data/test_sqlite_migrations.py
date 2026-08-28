from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core import storage  # noqa: E402
from research_observatory_core.migrations import runner  # noqa: E402
from research_observatory_core.migrations.runner import (  # noqa: E402
    MigrationProblem,
    migrate_database,
    plan_database_migration,
)
from research_observatory_core.migrations.versions import (  # noqa: E402
    v0002_schema_history,
    v0003_object_envelopes,
    v0004_object_envelope_upgrades,
    v0005_object_creation_source,
)

v0006_actor_identity = runner.v0006_actor_identity

PROJECT_ID = "123e4567-e89b-42d3-a456-426614174000"
CREATED_AT = "2026-08-14T12:00:00.000Z"
SETTING_ID = "01890f6e-6a40-7cc5-98b7-123456789abf"


def create_version_1_fixture(database: Path) -> None:
    """Materialize the exact supported T01 schema from its frozen DDL."""

    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        storage._configure_connection(connection, initialize=True)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={storage.OLDEST_DATABASE_SCHEMA_VERSION}")
        for statement in storage._V1_DDL_STATEMENTS:
            connection.execute(statement)
        self_fingerprint = storage._schema_fingerprint(connection)
        if self_fingerprint != storage.V1_SCHEMA_SHA256:
            raise AssertionError(self_fingerprint)
        connection.execute(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            ) VALUES (1, 1, ?, ?, ?, ?, ?)
            """,
            (
                storage.DATABASE_PROFILE,
                storage.APPLICATION_ID,
                storage.V1_PROFILE_SHA256,
                storage.V1_SCHEMA_SHA256,
                CREATED_AT,
            ),
        )
        connection.execute(
            """
            INSERT INTO projects (singleton, project_id, project_id_scheme, created_at)
            VALUES (1, ?, 'uuid4-bridge', ?)
            """,
            (PROJECT_ID, CREATED_AT),
        )
        connection.execute(
            """
            INSERT INTO settings (
                setting_id, project_id, setting_key, revision, value_type,
                text_value, created_at, modified_at
            ) VALUES (?, ?, 'display.theme', 0, 'text', 'dark', ?, ?)
            """,
            (SETTING_ID, PROJECT_ID, CREATED_AT, CREATED_AT),
        )
        connection.execute("COMMIT")
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise AssertionError(checkpoint)
    finally:
        connection.close()


def create_version_2_fixture(database: Path) -> None:
    """Materialize the exact immediately previous schema for the v2-to-v3 path."""

    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        storage._configure_connection(connection, initialize=True)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={storage.PREVIOUS_DATABASE_SCHEMA_VERSION}")
        statements = (
            v0002_schema_history.SCHEMA_METADATA_V2_DDL,
            *storage._V1_DDL_STATEMENTS[1:],
            v0002_schema_history.SCHEMA_MIGRATIONS_DDL,
            *v0002_schema_history.SCHEMA_MIGRATIONS_TRIGGERS,
        )
        for statement in statements:
            connection.execute(statement)
        self_fingerprint = storage._schema_fingerprint(connection)
        if self_fingerprint != storage.PREVIOUS_SCHEMA_SHA256:
            raise AssertionError(self_fingerprint)
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
            (PROJECT_ID, CREATED_AT),
        )
        connection.execute(
            """
            INSERT INTO object_records (
                object_sha256, project_id, byte_length, media_type, rights_status,
                protection_profile, retention_class, storage_state, created_at, verified_at
            ) VALUES (?, ?, 27, 'application/pdf', 'allowed', 'plaintext-fixture-v1',
                      'project-lifetime', 'available', ?, ?)
            """,
            ("e" * 64, PROJECT_ID, CREATED_AT, CREATED_AT),
        )
        connection.execute("COMMIT")
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise AssertionError(checkpoint)
    finally:
        connection.close()


def create_version_3_fixture(database: Path, *, legacy_object: bool) -> None:
    """Materialize the immutable committed v3 profile with optional v2-origin history."""

    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        storage._configure_connection(connection, initialize=True)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={storage.OBJECT_ENVELOPE_DATABASE_SCHEMA_VERSION}")
        for statement in (
            v0003_object_envelopes.SCHEMA_METADATA_V3_DDL,
            *storage._V1_DDL_STATEMENTS[1:],
            v0002_schema_history.SCHEMA_MIGRATIONS_DDL,
            *v0002_schema_history.SCHEMA_MIGRATIONS_TRIGGERS,
            *v0003_object_envelopes.OBJECT_ENVELOPE_COLUMNS,
            "UPDATE object_records SET ciphertext_byte_length=byte_length",
            *v0003_object_envelopes.OBJECT_ENVELOPE_TRIGGERS,
        ):
            connection.execute(statement)
        if storage._schema_fingerprint(connection) != storage.OBJECT_ENVELOPE_SCHEMA_SHA256:
            raise AssertionError(storage._schema_fingerprint(connection))
        connection.execute(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            ) VALUES (1, 3, ?, ?, ?, ?, ?)
            """,
            (
                storage.DATABASE_PROFILE,
                storage.APPLICATION_ID,
                storage.OBJECT_ENVELOPE_PROFILE_SHA256,
                storage.OBJECT_ENVELOPE_SCHEMA_SHA256,
                CREATED_AT,
            ),
        )
        connection.execute(
            """
            INSERT INTO projects (singleton, project_id, project_id_scheme, created_at)
            VALUES (1, ?, 'uuid4-bridge', ?)
            """,
            (PROJECT_ID, CREATED_AT),
        )
        if legacy_object:
            connection.execute(
                """
                INSERT INTO object_records (
                    object_sha256, project_id, byte_length, media_type, rights_status,
                    protection_profile, retention_class, storage_state, created_at, verified_at,
                    envelope_version, ciphertext_byte_length
                ) VALUES (?, ?, 27, 'application/pdf', 'allowed', 'plaintext-fixture-v1',
                          'project-lifetime', 'available', ?, ?, 'plaintext-fixture-v1', 27)
                """,
                ("e" * 64, PROJECT_ID, CREATED_AT, CREATED_AT),
            )
            connection.execute(
                """
                INSERT INTO schema_migrations (
                    migration_id, from_schema_version, to_schema_version, applied_at,
                    backup_manifest_sha256, source_schema_sha256, target_schema_sha256,
                    migration_tool
                ) VALUES ('0003_object_envelopes', 2, 3, ?, ?, ?, ?, 'alembic-1.18.5')
                """,
                (
                    CREATED_AT,
                    "a" * 64,
                    storage.PREVIOUS_SCHEMA_SHA256,
                    storage.OBJECT_ENVELOPE_SCHEMA_SHA256,
                ),
            )
        connection.execute("COMMIT")
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise AssertionError(checkpoint)
    finally:
        connection.close()


def create_version_4_fixture(database: Path) -> None:
    """Materialize the exact committed v4 profile with one unclassified object."""

    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        storage._configure_connection(connection, initialize=True)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={storage.OBJECT_ENVELOPE_UPGRADE_DATABASE_SCHEMA_VERSION}")
        for statement in (
            v0004_object_envelope_upgrades.SCHEMA_METADATA_V4_DDL,
            *storage._V1_DDL_STATEMENTS[1:],
            v0002_schema_history.SCHEMA_MIGRATIONS_DDL,
            *v0002_schema_history.SCHEMA_MIGRATIONS_TRIGGERS,
            *v0003_object_envelopes.OBJECT_ENVELOPE_COLUMNS,
            "UPDATE object_records SET ciphertext_byte_length=byte_length",
            *v0003_object_envelopes.OBJECT_ENVELOPE_TRIGGERS,
            v0004_object_envelope_upgrades.OBJECT_ENVELOPE_UPGRADES_DDL,
        ):
            connection.execute(statement)
        if storage._schema_fingerprint(connection) != storage.OBJECT_ENVELOPE_UPGRADE_SCHEMA_SHA256:
            raise AssertionError(storage._schema_fingerprint(connection))
        connection.execute(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            ) VALUES (1, 4, ?, ?, ?, ?, ?)
            """,
            (
                storage.DATABASE_PROFILE,
                storage.APPLICATION_ID,
                storage.OBJECT_ENVELOPE_UPGRADE_PROFILE_SHA256,
                storage.OBJECT_ENVELOPE_UPGRADE_SCHEMA_SHA256,
                CREATED_AT,
            ),
        )
        connection.execute(
            """
            INSERT INTO projects (singleton, project_id, project_id_scheme, created_at)
            VALUES (1, ?, 'uuid4-bridge', ?)
            """,
            (PROJECT_ID, CREATED_AT),
        )
        connection.execute(
            """
            INSERT INTO object_records (
                object_sha256, project_id, byte_length, media_type, rights_status,
                protection_profile, retention_class, storage_state, created_at, verified_at,
                envelope_version, ciphertext_byte_length
            ) VALUES (?, ?, 27, 'application/pdf', 'allowed', 'plaintext-fixture-v1',
                      'project-lifetime', 'available', ?, ?, 'plaintext-fixture-v1', 27)
            """,
            ("e" * 64, PROJECT_ID, CREATED_AT, CREATED_AT),
        )
        connection.execute("COMMIT")
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise AssertionError(checkpoint)
    finally:
        connection.close()


def create_version_5_fixture(database: Path) -> None:
    """Materialize the exact committed v5 profile with one legacy actor fact."""

    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        storage._configure_connection(connection, initialize=True)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={storage.OBJECT_CREATION_SOURCE_DATABASE_SCHEMA_VERSION}")
        for statement in (
            v0005_object_creation_source.SCHEMA_METADATA_V5_DDL,
            *storage._V1_DDL_STATEMENTS[1:],
            v0002_schema_history.SCHEMA_MIGRATIONS_DDL,
            *v0002_schema_history.SCHEMA_MIGRATIONS_TRIGGERS,
            *v0003_object_envelopes.OBJECT_ENVELOPE_COLUMNS,
            "UPDATE object_records SET ciphertext_byte_length=byte_length",
            *v0003_object_envelopes.OBJECT_ENVELOPE_TRIGGERS,
            v0004_object_envelope_upgrades.OBJECT_ENVELOPE_UPGRADES_DDL,
            v0005_object_creation_source.OBJECT_CREATION_SOURCE_COLUMN,
        ):
            connection.execute(statement)
        if storage._schema_fingerprint(connection) != storage.OBJECT_CREATION_SOURCE_SCHEMA_SHA256:
            raise AssertionError(storage._schema_fingerprint(connection))
        connection.execute(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            ) VALUES (1, 5, ?, ?, ?, ?, ?)
            """,
            (
                storage.DATABASE_PROFILE,
                storage.APPLICATION_ID,
                storage.OBJECT_CREATION_SOURCE_PROFILE_SHA256,
                storage.OBJECT_CREATION_SOURCE_SCHEMA_SHA256,
                CREATED_AT,
            ),
        )
        connection.execute(
            """
            INSERT INTO projects (singleton, project_id, project_id_scheme, created_at)
            VALUES (1, ?, 'uuid4-bridge', ?)
            """,
            (PROJECT_ID, CREATED_AT),
        )
        connection.execute(
            """
            INSERT INTO provenance_events (
                event_id, project_id, revision_id, event_type, occurred_at,
                trace_id, actor_type, actor_id, record_sha256
            ) VALUES (?, ?, NULL, 'legacy.actor.recorded', ?, ?, 'human', 'local.actor', ?)
            """,
            ("01890f6e-6a40-7cc5-98b7-123456789ac1", PROJECT_ID, CREATED_AT, "b" * 32, "c" * 64),
        )
        connection.execute("COMMIT")
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint != (0, 0, 0):
            raise AssertionError(checkpoint)
    finally:
        connection.close()


class SqliteMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_profile = storage.development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-sqlite-migrations-")
        self.project = Path(self.temporary.name).resolve(strict=True) / "project"
        self.state = self.project / "state"
        self.database = self.state / "project.sqlite3"

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
        try:
            self.temporary.cleanup()
        finally:
            self.database_profile.__exit__(None, None, None)

    def create_v1(self) -> None:
        create_version_1_fixture(self.database)

    def test_dry_run_is_exact_and_does_not_create_backup_or_change_source(self) -> None:
        self.create_v1()
        before = self.database.read_bytes()
        plan = plan_database_migration(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(1, plan.source_schema_version)
        self.assertEqual(6, plan.target_schema_version)
        self.assertTrue(plan.migration_required)
        self.assertEqual(
            (
                "0002_schema_history",
                "0003_object_envelopes",
                "0004_object_envelope_upgrades",
                "0005_object_creation_source",
                "0006_actor_identity",
            ),
            plan.migration_ids,
        )
        self.assertEqual(storage.V1_SCHEMA_SHA256, plan.source_schema_sha256)
        self.assertEqual(storage.EXPECTED_SCHEMA_SHA256, plan.target_schema_sha256)
        self.assertEqual(before, self.database.read_bytes())
        self.assertFalse((self.state / "migration-backups").exists())

    def test_migrates_exact_v1_fixture_with_verified_restorable_backup_and_history(self) -> None:
        self.create_v1()
        result = migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual("migrated", result.status)
        self.assertEqual(1, result.source_schema_version)
        self.assertEqual(6, result.target_schema_version)
        self.assertEqual(
            (
                "0002_schema_history",
                "0003_object_envelopes",
                "0004_object_envelope_upgrades",
                "0005_object_creation_source",
                "0006_actor_identity",
            ),
            result.migration_ids,
        )
        self.assertIsNotNone(result.backup_relative_path)
        self.assertIsNotNone(result.recovery_manifest_relative_path)
        backup = self.project / str(result.backup_relative_path)
        manifest = self.project / str(result.recovery_manifest_relative_path)
        self.assertTrue(backup.is_file())
        self.assertTrue(manifest.is_file())
        self.assertEqual(result.backup_sha256, hashlib.sha256(backup.read_bytes()).hexdigest())
        self.assertEqual(result.recovery_manifest_sha256, hashlib.sha256(manifest.read_bytes()).hexdigest())

        schema = json.loads(
            (REPO / "packages/contracts/storage/sqlite-migration-recovery.schema.json").read_text(encoding="utf-8")
        )
        document = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(
            [],
            list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document)),
        )
        self.assertEqual(result.backup_relative_path, document["backup"]["relativePath"])
        self.assertEqual(document["checkpoint"]["logFrames"], document["checkpoint"]["checkpointedFrames"])

        backup_plan = plan_database_migration(backup, expected_project_id=PROJECT_ID)
        self.assertEqual(1, backup_plan.source_schema_version)
        self.assertTrue(backup_plan.migration_required)
        current = storage.open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual("dark", current.execute("SELECT text_value FROM settings").fetchone()[0])
            history = current.execute(
                """
                SELECT migration_id, from_schema_version, to_schema_version,
                       backup_manifest_sha256, source_schema_sha256, target_schema_sha256,
                       migration_tool
                FROM schema_migrations ORDER BY to_schema_version
                """
            ).fetchall()
            self.assertEqual(
                (
                    (
                        "0002_schema_history",
                        1,
                        2,
                        result.recovery_manifest_sha256,
                        storage.V1_SCHEMA_SHA256,
                        storage.PREVIOUS_SCHEMA_SHA256,
                        "alembic-1.18.5",
                    ),
                    (
                        "0003_object_envelopes",
                        2,
                        3,
                        result.recovery_manifest_sha256,
                        storage.PREVIOUS_SCHEMA_SHA256,
                        storage.OBJECT_ENVELOPE_SCHEMA_SHA256,
                        "alembic-1.18.5",
                    ),
                    (
                        "0004_object_envelope_upgrades",
                        3,
                        4,
                        result.recovery_manifest_sha256,
                        storage.OBJECT_ENVELOPE_SCHEMA_SHA256,
                        storage.OBJECT_ENVELOPE_UPGRADE_SCHEMA_SHA256,
                        "alembic-1.18.5",
                    ),
                    (
                        "0005_object_creation_source",
                        4,
                        5,
                        result.recovery_manifest_sha256,
                        storage.OBJECT_ENVELOPE_UPGRADE_SCHEMA_SHA256,
                        storage.OBJECT_CREATION_SOURCE_SCHEMA_SHA256,
                        "alembic-1.18.5",
                    ),
                    (
                        "0006_actor_identity",
                        5,
                        6,
                        result.recovery_manifest_sha256,
                        storage.OBJECT_CREATION_SOURCE_SCHEMA_SHA256,
                        storage.EXPECTED_SCHEMA_SHA256,
                        "alembic-1.18.5",
                    ),
                ),
                tuple(tuple(row) for row in history),
            )
            with self.assertRaises(sqlite3.DatabaseError):
                current.execute("UPDATE schema_migrations SET migration_tool='forged'")
            with self.assertRaises(sqlite3.DatabaseError):
                current.execute("DELETE FROM schema_migrations")
            with self.assertRaises(sqlite3.DatabaseError):
                current.execute(
                    """
                    INSERT INTO schema_migrations (
                        migration_id, from_schema_version, to_schema_version, applied_at,
                        backup_manifest_sha256, source_schema_sha256, target_schema_sha256,
                        migration_tool
                    ) VALUES ('forged', 1, 2, ?, ?, ?, ?, 'alembic-1.18.5')
                    """,
                    (
                        CREATED_AT,
                        "a" * 64,
                        storage.PREVIOUS_SCHEMA_SHA256,
                        storage.EXPECTED_SCHEMA_SHA256,
                    ),
                )
        finally:
            current.close()

        backup_directories = tuple((self.state / "migration-backups").iterdir())
        repeated = migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual("current", repeated.status)
        self.assertIsNone(repeated.backup_relative_path)
        self.assertEqual(backup_directories, tuple((self.state / "migration-backups").iterdir()))

    def test_migrates_exact_v2_fixture_and_journals_plaintext_envelope_upgrade(self) -> None:
        create_version_2_fixture(self.database)
        plan = plan_database_migration(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(2, plan.source_schema_version)
        self.assertEqual(6, plan.target_schema_version)
        self.assertEqual(
            (
                "0003_object_envelopes",
                "0004_object_envelope_upgrades",
                "0005_object_creation_source",
                "0006_actor_identity",
            ),
            plan.migration_ids,
        )

        result = migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual("migrated", result.status)
        self.assertEqual(
            (
                "0003_object_envelopes",
                "0004_object_envelope_upgrades",
                "0005_object_creation_source",
                "0006_actor_identity",
            ),
            result.migration_ids,
        )
        current = storage.open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            envelope = current.execute(
                """
                SELECT envelope_version, key_version, wrapped_key, wrap_nonce,
                       byte_length, ciphertext_byte_length
                  FROM object_records WHERE object_sha256=?
                """,
                ("e" * 64,),
            ).fetchone()
            self.assertEqual(("plaintext-fixture-v1", None, None, None, 27, 27), tuple(envelope))
            self.assertEqual(
                ("legacy-detected", None),
                tuple(
                    current.execute(
                        """
                        SELECT phase, failure_code FROM object_envelope_upgrades
                         WHERE object_sha256=?
                        """,
                        ("e" * 64,),
                    ).fetchone()
                ),
            )
            history = current.execute(
                """
                SELECT migration_id, from_schema_version, to_schema_version,
                       source_schema_sha256, target_schema_sha256
                  FROM schema_migrations ORDER BY to_schema_version
                """
            ).fetchall()
            self.assertEqual(
                (
                    (
                        "0003_object_envelopes",
                        2,
                        3,
                        storage.PREVIOUS_SCHEMA_SHA256,
                        storage.OBJECT_ENVELOPE_SCHEMA_SHA256,
                    ),
                    (
                        "0004_object_envelope_upgrades",
                        3,
                        4,
                        storage.OBJECT_ENVELOPE_SCHEMA_SHA256,
                        storage.OBJECT_ENVELOPE_UPGRADE_SCHEMA_SHA256,
                    ),
                    (
                        "0005_object_creation_source",
                        4,
                        5,
                        storage.OBJECT_ENVELOPE_UPGRADE_SCHEMA_SHA256,
                        storage.OBJECT_CREATION_SOURCE_SCHEMA_SHA256,
                    ),
                    (
                        "0006_actor_identity",
                        5,
                        6,
                        storage.OBJECT_CREATION_SOURCE_SCHEMA_SHA256,
                        storage.EXPECTED_SCHEMA_SHA256,
                    ),
                ),
                tuple(tuple(row) for row in history),
            )
        finally:
            current.close()

    def test_preserves_committed_v3_history_and_only_journals_prior_plaintext(self) -> None:
        for index, legacy_object in enumerate((False, True)):
            with self.subTest(legacy_object=legacy_object):
                database = self.project / f"v3-{index}" / "state" / "project.sqlite3"
                create_version_3_fixture(database, legacy_object=legacy_object)
                plan = plan_database_migration(database, expected_project_id=PROJECT_ID)
                self.assertEqual(3, plan.source_schema_version)
                self.assertEqual(
                    ("0004_object_envelope_upgrades", "0005_object_creation_source", "0006_actor_identity"),
                    plan.migration_ids,
                )
                result = migrate_database(database, expected_project_id=PROJECT_ID)
                self.assertEqual(
                    ("0004_object_envelope_upgrades", "0005_object_creation_source", "0006_actor_identity"),
                    result.migration_ids,
                )
                current = storage.open_canonical_database(database, expected_project_id=PROJECT_ID)
                try:
                    rows = tuple(current.execute("SELECT object_sha256, phase FROM object_envelope_upgrades"))
                    self.assertEqual(
                        ((("e" * 64), "legacy-detected"),) if legacy_object else (),
                        tuple(tuple(row) for row in rows),
                    )
                    history = tuple(
                        str(row[0])
                        for row in current.execute(
                            "SELECT migration_id FROM schema_migrations ORDER BY to_schema_version"
                        )
                    )
                    self.assertEqual(
                        (
                            "0003_object_envelopes",
                            "0004_object_envelope_upgrades",
                            "0005_object_creation_source",
                            "0006_actor_identity",
                        )
                        if legacy_object
                        else (
                            "0004_object_envelope_upgrades",
                            "0005_object_creation_source",
                            "0006_actor_identity",
                        ),
                        history,
                    )
                finally:
                    current.close()

    def test_migrates_exact_v4_fixture_and_backfills_unreported_creation_source(self) -> None:
        create_version_4_fixture(self.database)
        plan = plan_database_migration(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(4, plan.source_schema_version)
        self.assertEqual(("0005_object_creation_source", "0006_actor_identity"), plan.migration_ids)

        result = migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(("0005_object_creation_source", "0006_actor_identity"), result.migration_ids)
        current = storage.open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(
                "legacy-unreported",
                current.execute(
                    "SELECT creation_source FROM object_records WHERE object_sha256=?",
                    ("e" * 64,),
                ).fetchone()[0],
            )
            migrated_fingerprint = storage._schema_fingerprint(current)
            self.assertEqual(storage.EXPECTED_SCHEMA_SHA256, migrated_fingerprint)
            history = tuple(
                tuple(row)
                for row in current.execute(
                    """
                    SELECT migration_id, from_schema_version, to_schema_version,
                           source_schema_sha256, target_schema_sha256
                      FROM schema_migrations ORDER BY to_schema_version
                    """
                )
            )
            self.assertEqual(
                (
                    (
                        "0005_object_creation_source",
                        4,
                        5,
                        storage.OBJECT_ENVELOPE_UPGRADE_SCHEMA_SHA256,
                        storage.OBJECT_CREATION_SOURCE_SCHEMA_SHA256,
                    ),
                    (
                        "0006_actor_identity",
                        5,
                        6,
                        storage.OBJECT_CREATION_SOURCE_SCHEMA_SHA256,
                        storage.EXPECTED_SCHEMA_SHA256,
                    ),
                ),
                history,
            )
        finally:
            current.close()

        fresh = self.project / "fresh" / "state" / "project.sqlite3"
        fresh.parent.mkdir(parents=True)
        report = storage.initialize_database(fresh, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        self.assertTrue(report.ok, report.errors)
        fresh_connection = storage.open_canonical_database(fresh, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(
                migrated_fingerprint,
                storage._schema_fingerprint(fresh_connection),
            )
        finally:
            fresh_connection.close()

    def test_migrates_exact_v5_fixture_and_preserves_legacy_and_uuid7_actor_authority(self) -> None:
        create_version_5_fixture(self.database)
        plan = plan_database_migration(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(5, plan.source_schema_version)
        self.assertEqual(("0006_actor_identity",), plan.migration_ids)

        result = migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(("0006_actor_identity",), result.migration_ids)
        current = storage.open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(
                "local.actor",
                current.execute("SELECT actor_id FROM provenance_events").fetchone()[0],
            )
            current.execute(
                """
                INSERT INTO provenance_events (
                    event_id, project_id, revision_id, event_type, occurred_at,
                    trace_id, actor_type, actor_id, record_sha256
                ) VALUES (?, ?, NULL, 'intent.draft.saved', ?, ?, 'human', ?, ?)
                """,
                (
                    "01890f6e-6a40-7cc5-98b7-123456789ac2",
                    PROJECT_ID,
                    CREATED_AT,
                    "d" * 32,
                    "018f0000-0000-7000-8000-000000000001",
                    "e" * 64,
                ),
            )
            self.assertEqual(
                ("local.actor", "018f0000-0000-7000-8000-000000000001"),
                tuple(row[0] for row in current.execute("SELECT actor_id FROM provenance_events ORDER BY event_id")),
            )
        finally:
            current.close()

    def test_every_material_revision_step_rolls_back_to_exact_v1_and_retries(self) -> None:
        failpoints = (
            tuple((v0002_schema_history, step) for step in v0002_schema_history.MATERIAL_MIGRATION_STEPS)
            + tuple((v0003_object_envelopes, step) for step in v0003_object_envelopes.MATERIAL_MIGRATION_STEPS)
            + tuple(
                (v0004_object_envelope_upgrades, step)
                for step in v0004_object_envelope_upgrades.MATERIAL_MIGRATION_STEPS
            )
            + tuple(
                (v0005_object_creation_source, step) for step in v0005_object_creation_source.MATERIAL_MIGRATION_STEPS
            )
            + tuple((v0006_actor_identity, step) for step in v0006_actor_identity.MATERIAL_MIGRATION_STEPS)
        )
        for index, (revision_module, failpoint) in enumerate(failpoints):
            with self.subTest(revision=revision_module.revision, failpoint=failpoint):
                project = self.project / f"failure-{index}"
                database = project / "state" / "project.sqlite3"
                create_version_1_fixture(database)

                def fail_at_step(completed: str, expected: str = failpoint) -> None:
                    if completed == expected:
                        raise RuntimeError(f"deterministic-failure-after-{expected}")

                with (
                    patch.object(revision_module, "_migration_step_completed", fail_at_step),
                    self.assertRaisesRegex(MigrationProblem, "migration-execution-failed") as raised,
                ):
                    migrate_database(database, expected_project_id=PROJECT_ID)
                self.assertIsNotNone(raised.exception.recovery_manifest_relative_path)
                plan = plan_database_migration(database, expected_project_id=PROJECT_ID)
                self.assertEqual(1, plan.source_schema_version)
                inspection = sqlite3.connect(database, autocommit=True)
                try:
                    self.assertEqual(storage.V1_SCHEMA_SHA256, storage._schema_fingerprint(inspection))
                    self.assertIsNone(
                        inspection.execute("SELECT name FROM sqlite_schema WHERE name='schema_migrations'").fetchone()
                    )
                    self.assertEqual("dark", inspection.execute("SELECT text_value FROM settings").fetchone()[0])
                finally:
                    inspection.close()
                manifest = project / str(raised.exception.recovery_manifest_relative_path)
                failure = manifest.parent / "failure.json"
                self.assertTrue(manifest.is_file())
                self.assertTrue((manifest.parent / "project.sqlite3").is_file())
                failure_bytes = failure.read_bytes()
                self.assertEqual("migration-failed", json.loads(failure_bytes)["status"])
                if os.name == "nt":
                    with self.assertRaises(PermissionError):
                        failure.write_bytes(b"changed")
                    with self.assertRaises(PermissionError):
                        failure.unlink()
                    self.assertEqual(failure_bytes, failure.read_bytes())

                recovered = migrate_database(database, expected_project_id=PROJECT_ID)
                self.assertEqual("migrated", recovered.status)

    def test_compatible_content_injection_before_working_lock_is_denied(self) -> None:
        self.create_v1()
        original_lock = runner._lock_descriptor_writes

        def inject_then_lock(descriptor: int) -> None:
            attempt = next((self.state / "migration-backups").iterdir())
            working = next(attempt.glob(".working-*.sqlite3"))
            attacker = sqlite3.connect(working, autocommit=True)
            try:
                attacker.execute(
                    """
                    INSERT INTO settings (
                        setting_id, project_id, setting_key, revision, value_type,
                        text_value, created_at, modified_at
                    ) VALUES ('01890f6e-6a40-7cc5-98b7-123456789ac0', ?,
                              'attacker.valid-setting', 0, 'text', 'forged', ?, ?)
                    """,
                    (PROJECT_ID, CREATED_AT, CREATED_AT),
                )
            finally:
                attacker.close()
            original_lock(descriptor)

        with (
            patch.object(runner, "_lock_descriptor_writes", inject_then_lock),
            self.assertRaisesRegex(MigrationProblem, "migration-backup-changed-before-lock"),
        ):
            migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(
            1, plan_database_migration(self.database, expected_project_id=PROJECT_ID).source_schema_version
        )
        source = sqlite3.connect(self.database, autocommit=True)
        try:
            self.assertEqual(
                0,
                source.execute("SELECT count(*) FROM settings WHERE setting_key='attacker.valid-setting'").fetchone()[
                    0
                ],
            )
        finally:
            source.close()

    def test_backup_and_manifest_hardlinks_at_creation_handoffs_are_denied(self) -> None:
        for protected_name in ("project.sqlite3", "recovery-manifest.json"):
            with self.subTest(protected_name=protected_name):
                project = self.project / protected_name.replace(".", "-")
                database = project / "state" / "project.sqlite3"
                create_version_1_fixture(database)
                outside = self.project / f"outside-{protected_name}"
                original_file = runner._create_exclusive_file
                original_copy = runner._copy_to_exclusive_file

                def alias_file(
                    path: Path,
                    payload: bytes,
                    original: object = original_file,
                    expected: str = protected_name,
                    alias: Path = outside,
                ) -> runner._HeldFileAuthority:
                    authority = original(path, payload)  # type: ignore[operator]
                    if expected == "recovery-manifest.json" and path.name == expected:
                        os.link(path, alias)
                    return authority

                def alias_copy(
                    path: Path,
                    descriptor: int,
                    original: object = original_copy,
                    expected: str = protected_name,
                    alias: Path = outside,
                ) -> runner._HeldFileAuthority:
                    authority = original(path, descriptor)  # type: ignore[operator]
                    if expected == "project.sqlite3" and path.name == expected:
                        os.link(path, alias)
                    return authority

                with (
                    patch.object(runner, "_create_exclusive_file", alias_file),
                    patch.object(runner, "_copy_to_exclusive_file", alias_copy),
                    self.assertRaisesRegex(MigrationProblem, "migration-backup-file-invalid"),
                ):
                    migrate_database(database, expected_project_id=PROJECT_ID)
                self.assertEqual(
                    1, plan_database_migration(database, expected_project_id=PROJECT_ID).source_schema_version
                )
                outside.unlink()

    @unittest.skipUnless(os.name == "nt", "Windows durable recovery ACL boundary")
    def test_recovery_acl_denies_links_after_final_validation_and_commit(self) -> None:
        self.create_v1()
        replacement = self.project / "outside-replacement.txt"
        replacement.write_text("replacement", encoding="utf-8")
        late_database = self.project / "outside-late-database.sqlite3"
        late_manifest = self.project / "outside-late-manifest.json"
        after_commit_database = self.project / "outside-committed-database.sqlite3"
        after_commit_manifest = self.project / "outside-committed-manifest.json"
        original_assert = runner._assert_verified_backup
        original_close = runner._VerifiedBackup.close
        final_checks = 0

        def check_then_link(verified: runner._VerifiedBackup) -> None:
            nonlocal final_checks
            original_assert(verified)
            final_checks += 1
            if final_checks == 3:
                with self.assertRaises(PermissionError):
                    os.link(verified.database, late_database)
                with self.assertRaises(PermissionError):
                    os.link(verified.manifest, late_manifest)
                with self.assertRaises(PermissionError):
                    verified.database.unlink()
                with self.assertRaises(PermissionError):
                    verified.manifest.unlink()
                with self.assertRaises(PermissionError):
                    os.replace(verified.database, self.project / "outside-late-moved.sqlite3")
                with self.assertRaises(PermissionError):
                    os.replace(verified.manifest, self.project / "outside-late-moved.json")
                with self.assertRaises(PermissionError):
                    os.replace(replacement, verified.database)
                with self.assertRaises(PermissionError):
                    os.replace(replacement, verified.manifest)

        def link_then_close(verified: runner._VerifiedBackup) -> None:
            with self.assertRaises(PermissionError):
                os.link(verified.database, after_commit_database)
            with self.assertRaises(PermissionError):
                os.link(verified.manifest, after_commit_manifest)
            with self.assertRaises(PermissionError):
                verified.database.unlink()
            with self.assertRaises(PermissionError):
                verified.manifest.unlink()
            with self.assertRaises(PermissionError):
                os.replace(verified.database, self.project / "outside-committed-moved.sqlite3")
            with self.assertRaises(PermissionError):
                os.replace(verified.manifest, self.project / "outside-committed-moved.json")
            with self.assertRaises(PermissionError):
                os.replace(replacement, verified.database)
            with self.assertRaises(PermissionError):
                os.replace(replacement, verified.manifest)
            original_close(verified)

        with (
            patch.object(runner, "_assert_verified_backup", check_then_link),
            patch.object(runner._VerifiedBackup, "close", link_then_close),
        ):
            migrated = migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual("migrated", migrated.status)
        self.assertEqual(3, final_checks)

        backup = self.project / str(migrated.backup_relative_path)
        manifest = self.project / str(migrated.recovery_manifest_relative_path)
        self.assertEqual([], list(manifest.parent.glob(".working-*.sqlite3")))
        backup_before = backup.read_bytes()
        manifest_before = manifest.read_bytes()
        with self.assertRaises(PermissionError):
            os.link(backup, self.project / "outside-released-database.sqlite3")
        with self.assertRaises(PermissionError):
            os.link(manifest, self.project / "outside-released-manifest.json")
        with self.assertRaises(PermissionError):
            backup.write_bytes(b"changed")
        with self.assertRaises(PermissionError):
            manifest.write_bytes(b"changed")
        with self.assertRaises(PermissionError):
            backup.unlink()
        with self.assertRaises(PermissionError):
            manifest.unlink()
        with self.assertRaises(PermissionError):
            os.replace(backup, self.project / "outside-released-moved.sqlite3")
        with self.assertRaises(PermissionError):
            os.replace(manifest, self.project / "outside-released-moved.json")
        with self.assertRaises(PermissionError):
            os.replace(replacement, backup)
        with self.assertRaises(PermissionError):
            os.replace(replacement, manifest)
        self.assertEqual(backup_before, backup.read_bytes())
        self.assertEqual(manifest_before, manifest.read_bytes())

        attempt = manifest.parent
        backup_root = attempt.parent
        with self.assertRaises(PermissionError):
            os.replace(attempt, self.project / "outside-released-attempt")
        with self.assertRaises(PermissionError):
            os.replace(backup_root, self.project / "outside-released-backup-root")
        self.assertTrue(backup.is_file())
        self.assertTrue(manifest.is_file())

        future_attempt = backup_root / "future-attempt"
        future_attempt.mkdir()
        self.assertTrue(future_attempt.is_dir())
        reopened = sqlite3.connect(self.database, autocommit=True)
        try:
            self.assertEqual((0, 0, 0), tuple(reopened.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()))
            self.assertEqual("ok", reopened.execute("PRAGMA quick_check").fetchone()[0])
        finally:
            reopened.close()

    def test_writer_reservation_spans_backup_through_migration(self) -> None:
        self.create_v1()
        entered = threading.Event()
        release = threading.Event()
        original = runner._create_verified_backup
        result: list[object] = []

        def delayed_backup(*args: object, **kwargs: object) -> object:
            entered.set()
            self.assertTrue(release.wait(5))
            return original(*args, **kwargs)  # type: ignore[arg-type]

        def migrate() -> None:
            try:
                result.append(migrate_database(self.database, expected_project_id=PROJECT_ID))
            except BaseException as error:
                result.append(error)

        with patch.object(runner, "_create_verified_backup", delayed_backup):
            thread = threading.Thread(target=migrate, daemon=True)
            thread.start()
            self.assertTrue(entered.wait(5))
            writer = sqlite3.connect(self.database, autocommit=True, timeout=0.1)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    writer.execute("BEGIN IMMEDIATE")
            finally:
                writer.close()
                release.set()
            thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(1, len(result))
        self.assertIsInstance(result[0], runner.MigrationResult)

    def test_invalid_backup_root_or_forged_source_fails_before_schema_mutation(self) -> None:
        self.create_v1()
        backup_root = self.state / "migration-backups"
        backup_root.write_bytes(b"not a directory\n")
        with self.assertRaisesRegex(MigrationProblem, "migration-backup-path-invalid"):
            migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(
            1,
            plan_database_migration(self.database, expected_project_id=PROJECT_ID).source_schema_version,
        )
        backup_root.unlink()

        raw = sqlite3.connect(self.database, autocommit=True)
        try:
            raw.execute("PRAGMA writable_schema=ON")
            sql = raw.execute("SELECT sql FROM sqlite_schema WHERE name='settings'").fetchone()[0]
            raw.execute(
                "UPDATE sqlite_schema SET sql=? WHERE name='settings'",
                (sql.replace("CHECK (text_value IS NULL OR length(text_value) <= 65536)", "CHECK (1)"),),
            )
            raw.execute("PRAGMA writable_schema=OFF")
        finally:
            raw.close()
        with self.assertRaisesRegex(MigrationProblem, "migration-source-profile-invalid"):
            plan_database_migration(self.database, expected_project_id=PROJECT_ID)
        self.assertFalse(backup_root.exists())

    @unittest.skipUnless(sys.platform == "win32", "Windows junction and write-lock boundary")
    def test_redirected_backup_root_and_concurrent_backup_tamper_are_denied(self) -> None:
        self.create_v1()
        backup_root = self.state / "migration-backups"
        outside = self.project.parent / "outside-backups"
        outside.mkdir()
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(backup_root), str(outside)],
            check=False,
            capture_output=True,
            text=True,
        )
        if junction.returncode != 0:
            self.skipTest(f"directory junctions unavailable: {junction.stderr!r}")
        try:
            with self.assertRaisesRegex(MigrationProblem, "migration-backup-path-invalid"):
                migrate_database(self.database, expected_project_id=PROJECT_ID)
            self.assertEqual([], list(outside.iterdir()))
            self.assertEqual(
                1,
                plan_database_migration(self.database, expected_project_id=PROJECT_ID).source_schema_version,
            )
        finally:
            backup_root.rmdir()

        original = runner._run_migrations

        def tamper_then_migrate(*args: object, **kwargs: object) -> None:
            attempt = next((self.state / "migration-backups").iterdir())
            for protected in (attempt / "project.sqlite3", attempt / "recovery-manifest.json"):
                with self.assertRaises(PermissionError):
                    protected.write_bytes(b"attacker")
            original(*args, **kwargs)  # type: ignore[arg-type]

        with patch.object(runner, "_run_migrations", tamper_then_migrate):
            result = migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual("migrated", result.status)

    def test_migration_authority_rejects_non_project_location_and_unknown_version(self) -> None:
        non_project = self.project / "project.sqlite3"
        create_version_1_fixture(non_project)
        with self.assertRaisesRegex(MigrationProblem, "migration-database-location-invalid"):
            migrate_database(non_project, expected_project_id=PROJECT_ID)
        self.assertFalse((self.project / "migration-backups").exists())

        self.create_v1()
        raw = sqlite3.connect(self.database, autocommit=True)
        try:
            raw.execute("PRAGMA user_version=99")
        finally:
            raw.close()
        with self.assertRaisesRegex(MigrationProblem, "migration-source-version-unsupported"):
            plan_database_migration(self.database, expected_project_id=PROJECT_ID)
        self.assertFalse((self.state / "migration-backups").exists())

    def test_fresh_current_database_is_idempotent_without_migration_authority_leak(self) -> None:
        self.state.mkdir(parents=True)
        report = storage.initialize_database(
            self.database,
            project_id=PROJECT_ID,
            project_created_at=CREATED_AT,
        )
        self.assertTrue(report.ok, report.errors)
        result = migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual("current", result.status)
        self.assertFalse((self.state / "migration-backups").exists())
        self.assertFalse(hasattr(result, "connection"))
        current = storage.open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(0, current.execute("SELECT count(*) FROM schema_migrations").fetchone()[0])
            self.assertFalse(hasattr(current, "set_authorizer"))
            with self.assertRaises(sqlite3.DatabaseError):
                current.execute("DROP TABLE schema_migrations")
        finally:
            current.close()


if __name__ == "__main__":
    unittest.main()
