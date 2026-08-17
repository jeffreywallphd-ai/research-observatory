from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.storage import (  # noqa: E402
    APPLICATION_ID,
    DATABASE_SCHEMA_VERSION,
    EXPECTED_TABLES,
    EXPECTED_TRIGGERS,
    IMMUTABLE_ROW_TABLES,
    MUTABLE_STATE_TABLES,
    CanonicalConnection,
    StorageProblem,
    database_integrity_report,
    initialize_database,
    open_canonical_database,
    storage_profile_document,
)

PROJECT_ID = "123e4567-e89b-42d3-a456-426614174000"
SECOND_PROJECT_ID = "223e4567-e89b-42d3-a456-426614174000"
CREATED_AT = "2026-08-14T12:00:00.000Z"
AGGREGATE_ID = "01890f6e-6a40-7cc5-98b7-123456789abc"
REVISION_ID = "01890f6e-6a40-7cc5-98b7-123456789abd"
EVENT_ID = "01890f6e-6a40-7cc5-98b7-123456789abe"
SETTING_ID = "01890f6e-6a40-7cc5-98b7-123456789abf"
DOCUMENT_AGGREGATE_ID = "01890f6e-6a40-7cc5-98b7-123456789ad0"
DOCUMENT_REVISION_ID = "01890f6e-6a40-7cc5-98b7-123456789ad1"
OBJECT_SHA256 = "c" * 64


def insert_identity(connection: sqlite3.Connection | CanonicalConnection) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO aggregate_identities (
            aggregate_id, project_id, aggregate_kind, created_at
        ) VALUES (?, ?, 'record', ?)
        """,
        (AGGREGATE_ID, PROJECT_ID, CREATED_AT),
    )


def insert_revision(connection: sqlite3.Connection | CanonicalConnection) -> None:
    insert_identity(connection)
    connection.execute(
        """
        INSERT INTO aggregate_revisions (
            revision_id, aggregate_id, aggregate_kind, project_id, revision,
            contract_version, created_at, modified_at, display_label_observed,
            display_label_normalized, knowledge_status, rights_status
        ) VALUES (?, ?, 'record', ?, 0, '1.0.0', ?, ?, 'Observed title',
                  'Observed title', 'observed', 'unknown')
        """,
        (REVISION_ID, AGGREGATE_ID, PROJECT_ID, CREATED_AT, CREATED_AT),
    )


class SqliteSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-sqlite-schema-")
        self.root = Path(self.temporary.name).resolve(strict=True)
        self.database = self.root / "project.sqlite3"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def initialize(self) -> None:
        report = initialize_database(
            self.database,
            project_id=PROJECT_ID,
            project_created_at=CREATED_AT,
        )
        self.assertTrue(report.ok, report.errors)

    def test_portable_profile_is_exact_and_schema_valid(self) -> None:
        contract_root = REPO / "packages" / "contracts" / "storage"
        profile = json.loads((contract_root / "sqlite-profile.v1.json").read_text(encoding="utf-8"))
        schema = json.loads((contract_root / "sqlite-profile.schema.json").read_text(encoding="utf-8"))
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(profile)))
        self.assertEqual(storage_profile_document(), profile)
        self.assertEqual(DATABASE_SCHEMA_VERSION, profile["databaseSchemaVersion"])
        self.assertEqual(APPLICATION_ID, profile["applicationId"])
        self.assertEqual(list(EXPECTED_TABLES), profile["canonicalTables"])
        self.assertEqual(list(IMMUTABLE_ROW_TABLES), profile["immutableRowTables"])
        self.assertEqual(list(MUTABLE_STATE_TABLES), profile["mutableStateTables"])

        hostile = dict(profile)
        hostile["unexpectedOverride"] = True
        self.assertNotEqual([], list(Draft202012Validator(schema).iter_errors(hostile)))

    def test_initializes_exact_strict_wal_schema_and_reopens_after_restart(self) -> None:
        self.initialize()
        self.assertTrue(self.database.is_file())

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(1, connection.execute("PRAGMA foreign_keys").fetchone()[0])
            self.assertEqual("wal", connection.execute("PRAGMA journal_mode").fetchone()[0])
            self.assertEqual(2, connection.execute("PRAGMA synchronous").fetchone()[0])
            self.assertEqual(5_000, connection.execute("PRAGMA busy_timeout").fetchone()[0])
            self.assertEqual(0, connection.execute("PRAGMA trusted_schema").fetchone()[0])
            self.assertEqual(1_000, connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0])
            self.assertEqual(APPLICATION_ID, connection.execute("PRAGMA application_id").fetchone()[0])
            self.assertEqual(DATABASE_SCHEMA_VERSION, connection.execute("PRAGMA user_version").fetchone()[0])
            tables = {
                row[1]: row[5]
                for row in connection.execute("PRAGMA table_list")
                if row[2] == "table" and not row[1].startswith("sqlite_")
            }
            self.assertEqual(set(EXPECTED_TABLES), set(tables))
            self.assertTrue(all(tables[table] == 1 for table in EXPECTED_TABLES))
            triggers = tuple(
                sorted(row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='trigger'"))
            )
            self.assertEqual(EXPECTED_TRIGGERS, triggers)
            project = connection.execute("SELECT project_id, project_id_scheme, created_at FROM projects").fetchone()
            self.assertEqual((PROJECT_ID, "uuid4-bridge", CREATED_AT), tuple(project))
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("ATTACH DATABASE ? AS outside", (str(self.root / "outside.sqlite3"),))
        finally:
            connection.close()

        reopened = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            report = database_integrity_report(reopened, expected_project_id=PROJECT_ID)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(("ok",), report.quick_check)
            self.assertEqual((), report.foreign_key_violations)
        finally:
            reopened.close()

    def test_foreign_keys_identity_timestamps_kind_and_scalar_storage_fail_closed(self) -> None:
        self.initialize()
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            insert_identity(connection)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO aggregate_revisions (
                        revision_id, aggregate_id, aggregate_kind, project_id, revision,
                        contract_version, created_at, modified_at, display_label_observed,
                        knowledge_status, rights_status
                    ) VALUES (?, ?, 'record', ?, 0, '1.0.0', ?, ?, 'Title', 'observed', 'unknown')
                    """,
                    (REVISION_ID, AGGREGATE_ID, "00000000-0000-4000-8000-000000000000", CREATED_AT, CREATED_AT),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO aggregate_revisions (
                        revision_id, aggregate_id, aggregate_kind, project_id, revision,
                        contract_version, created_at, modified_at, display_label_observed,
                        knowledge_status, rights_status
                    ) VALUES ('not-a-uuid', ?, 'record', ?, 0, '1.0.0', ?, ?, 'Title', 'observed', 'unknown')
                    """,
                    (AGGREGATE_ID, PROJECT_ID, CREATED_AT, CREATED_AT),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO aggregate_revisions (
                        revision_id, aggregate_id, aggregate_kind, project_id, revision,
                        contract_version, created_at, modified_at, display_label_observed,
                        knowledge_status, rights_status
                    ) VALUES (?, ?, 'record', ?, 0, '1.0.0',
                              '2026-08-14T12:00:00Z', ?, 'Title', 'observed', 'unknown')
                    """,
                    (REVISION_ID, AGGREGATE_ID, PROJECT_ID, CREATED_AT),
                )
            for invalid_timestamp in (
                "2026-02-30T12:00:00.000Z",
                "2026-08-14T24:00:00.000Z",
                "0000-01-01T00:00:00.000Z",
            ):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO aggregate_revisions (
                            revision_id, aggregate_id, aggregate_kind, project_id, revision,
                            contract_version, created_at, modified_at, display_label_observed,
                            knowledge_status, rights_status
                        ) VALUES (?, ?, 'record', ?, 0, '1.0.0', ?, ?, 'Title', 'observed', 'unknown')
                        """,
                        (REVISION_ID, AGGREGATE_ID, PROJECT_ID, invalid_timestamp, invalid_timestamp),
                    )

            insert_revision(connection)
            connection.execute(
                "INSERT INTO scholarly_records (revision_id, aggregate_kind) VALUES (?, 'record')",
                (REVISION_ID,),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO documents (revision_id, aggregate_kind) VALUES (?, 'document')",
                    (REVISION_ID,),
                )
            connection.execute(
                """
                INSERT INTO object_records (
                    object_sha256, project_id, byte_length, media_type, rights_status,
                    protection_profile, retention_class, storage_state, created_at, verified_at
                ) VALUES (?, ?, 4096, 'application/pdf', 'allowed', 'encrypted-object-v1',
                          'project-lifetime', 'available', ?, ?)
                """,
                (OBJECT_SHA256, PROJECT_ID, CREATED_AT, CREATED_AT),
            )
            connection.execute(
                """
                INSERT INTO aggregate_identities (
                    aggregate_id, project_id, aggregate_kind, created_at
                ) VALUES (?, ?, 'document', ?)
                """,
                (DOCUMENT_AGGREGATE_ID, PROJECT_ID, CREATED_AT),
            )
            connection.execute(
                """
                INSERT INTO aggregate_revisions (
                    revision_id, aggregate_id, aggregate_kind, project_id, revision,
                    contract_version, created_at, modified_at, display_label_observed,
                    knowledge_status, rights_status
                ) VALUES (?, ?, 'document', ?, 0, '1.0.0', ?, ?, 'Article PDF', 'observed', 'allowed')
                """,
                (DOCUMENT_REVISION_ID, DOCUMENT_AGGREGATE_ID, PROJECT_ID, CREATED_AT, CREATED_AT),
            )
            connection.execute(
                """
                INSERT INTO documents (revision_id, aggregate_kind, project_id, object_sha256)
                VALUES (?, 'document', ?, ?)
                """,
                (DOCUMENT_REVISION_ID, PROJECT_ID, OBJECT_SHA256),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO projects (singleton, project_id, project_id_scheme, created_at)
                    VALUES (2, ?, 'uuid4-bridge', ?)
                    """,
                    (SECOND_PROJECT_ID, CREATED_AT),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO object_records (
                        object_sha256, project_id, byte_length, media_type, rights_status,
                        protection_profile, retention_class, storage_state, created_at
                    ) VALUES ('not-a-digest', ?, 1, 'application/pdf', 'unknown',
                              'encrypted-object-v1', 'project-lifetime', 'pending', ?)
                    """,
                    (PROJECT_ID, CREATED_AT),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO settings (
                        setting_id, project_id, setting_key, revision, value_type,
                        text_value, created_at, modified_at
                    ) VALUES (?, ?, 'privacy.mode', 0, 'text', ?, ?, ?)
                    """,
                    (SETTING_ID, PROJECT_ID, sqlite3.Binary(b"derived-blob"), CREATED_AT, CREATED_AT),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO settings (
                        setting_id, project_id, setting_key, revision, value_type,
                        integer_value, created_at, modified_at
                    ) VALUES (?, ?, 'invalid.unsafe-integer', 0, 'integer', ?, ?, ?)
                    """,
                    (
                        "01890f6e-6a40-7cc5-98b7-123456789ac2",
                        PROJECT_ID,
                        9_007_199_254_740_992,
                        CREATED_AT,
                        CREATED_AT,
                    ),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO settings (
                        setting_id, project_id, setting_key, revision, value_type,
                        real_value, created_at, modified_at
                    ) VALUES (?, ?, 'invalid.non-finite', 0, 'real', ?, ?, ?)
                    """,
                    (
                        "01890f6e-6a40-7cc5-98b7-123456789ac3",
                        PROJECT_ID,
                        float("inf"),
                        CREATED_AT,
                        CREATED_AT,
                    ),
                )

            declared_types = {
                row[2] for table in EXPECTED_TABLES for row in connection.execute(f'PRAGMA table_xinfo("{table}")')
            }
            self.assertFalse({"ANY", "BLOB"} & declared_types)
            columns = {
                row[1] for table in EXPECTED_TABLES for row in connection.execute(f'PRAGMA table_xinfo("{table}")')
            }
            self.assertNotIn("payload", columns)
            self.assertNotIn("payload_json", columns)
            self.assertNotIn("object_bytes", columns)
            self.assertNotIn("object_path", columns)
        finally:
            connection.close()

    def test_provenance_is_append_only_and_settings_are_typed(self) -> None:
        self.initialize()
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            insert_revision(connection)
            connection.execute(
                """
                INSERT INTO provenance_events (
                    event_id, project_id, revision_id, event_type, occurred_at,
                    trace_id, actor_type, record_sha256
                ) VALUES (?, ?, ?, 'record.observed', ?, ?, 'system', ?)
                """,
                (EVENT_ID, PROJECT_ID, REVISION_ID, CREATED_AT, "a" * 32, "b" * 64),
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                connection.execute("UPDATE provenance_events SET event_type='record.changed'")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                connection.execute("DELETE FROM provenance_events")

            connection.execute(
                """
                INSERT INTO settings (
                    setting_id, project_id, setting_key, revision, value_type,
                    boolean_value, created_at, modified_at
                ) VALUES (?, ?, 'privacy.local-only', 0, 'boolean', 1, ?, ?)
                """,
                (SETTING_ID, PROJECT_ID, CREATED_AT, CREATED_AT),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO settings (
                        setting_id, project_id, setting_key, revision, value_type,
                        text_value, integer_value, created_at, modified_at
                    ) VALUES (?, ?, 'invalid.multiple-values', 0, 'text', 'x', 1, ?, ?)
                    """,
                    ("01890f6e-6a40-7cc5-98b7-123456789ac0", PROJECT_ID, CREATED_AT, CREATED_AT),
                )
        finally:
            connection.close()

    def test_identity_revision_extension_and_setting_rows_are_immutable(self) -> None:
        self.initialize()
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "project identity is immutable"):
                connection.execute("UPDATE projects SET project_id=?", (SECOND_PROJECT_ID,))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "project identity is immutable"):
                connection.execute("DELETE FROM projects")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "schema metadata is immutable"):
                connection.execute("UPDATE schema_metadata SET created_at=created_at")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "schema metadata is immutable"):
                connection.execute("DELETE FROM schema_metadata")

            identities: dict[str, tuple[str, str]] = {}
            table_kinds = {
                "scholarly_records": "record",
                "documents": "document",
                "workflows": "workflow",
                "evidence": "evidence",
                "ontologies": "ontology",
                "decisions": "decision",
            }
            for offset, (table, kind) in enumerate(table_kinds.items(), start=1):
                aggregate_id = f"01890f6e-6a40-7cc5-98b7-{offset:012x}"
                revision_id = f"01890f6e-6a40-7cc5-98b7-{offset + 100:012x}"
                identities[table] = (aggregate_id, revision_id)
                connection.execute(
                    """
                    INSERT INTO aggregate_identities (
                        aggregate_id, project_id, aggregate_kind, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (aggregate_id, PROJECT_ID, kind, CREATED_AT),
                )
                connection.execute(
                    """
                    INSERT INTO aggregate_revisions (
                        revision_id, aggregate_id, aggregate_kind, project_id, revision,
                        contract_version, created_at, modified_at, display_label_observed,
                        knowledge_status, rights_status
                    ) VALUES (?, ?, ?, ?, 0, '1.0.0', ?, ?, ?, 'observed', 'unknown')
                    """,
                    (revision_id, aggregate_id, kind, PROJECT_ID, CREATED_AT, CREATED_AT, f"{kind} title"),
                )
                if table == "documents":
                    connection.execute(
                        "INSERT INTO documents (revision_id, project_id) VALUES (?, ?)",
                        (revision_id, PROJECT_ID),
                    )
                else:
                    connection.execute(f"INSERT INTO {table} (revision_id) VALUES (?)", (revision_id,))

            unreferenced_id = "01890f6e-6a40-7cc5-98b7-0000000000ff"
            connection.execute(
                """
                INSERT INTO aggregate_identities (
                    aggregate_id, project_id, aggregate_kind, created_at
                ) VALUES (?, ?, 'record', ?)
                """,
                (unreferenced_id, PROJECT_ID, CREATED_AT),
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "aggregate identities are immutable"):
                connection.execute(
                    "UPDATE aggregate_identities SET aggregate_id=? WHERE aggregate_id=?",
                    ("01890f6e-6a40-7cc5-98b7-0000000000fe", unreferenced_id),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "aggregate identities are immutable"):
                connection.execute("DELETE FROM aggregate_identities WHERE aggregate_id=?", (unreferenced_id,))

            record_revision = identities["scholarly_records"][1]
            with self.assertRaisesRegex(sqlite3.IntegrityError, "aggregate revisions are immutable"):
                connection.execute(
                    "UPDATE aggregate_revisions SET display_label_observed='changed' WHERE revision_id=?",
                    (record_revision,),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "aggregate revisions are immutable"):
                connection.execute("DELETE FROM aggregate_revisions WHERE revision_id=?", (record_revision,))

            for table, (_, revision_id) in identities.items():
                with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                    connection.execute(
                        f"UPDATE {table} SET revision_id=revision_id WHERE revision_id=?", (revision_id,)
                    )
                with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                    connection.execute(f"DELETE FROM {table} WHERE revision_id=?", (revision_id,))

            connection.execute(
                """
                INSERT INTO settings (
                    setting_id, project_id, setting_key, revision, value_type,
                    boolean_value, created_at, modified_at
                ) VALUES (?, ?, 'privacy.local-only', 0, 'boolean', 1, ?, ?)
                """,
                (SETTING_ID, PROJECT_ID, CREATED_AT, CREATED_AT),
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "settings history is append-only"):
                connection.execute("UPDATE settings SET boolean_value=0 WHERE setting_id=?", (SETTING_ID,))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "settings history is append-only"):
                connection.execute("DELETE FROM settings WHERE setting_id=?", (SETTING_ID,))

            connection.execute(
                """
                INSERT INTO object_records (
                    object_sha256, project_id, byte_length, media_type, rights_status,
                    protection_profile, retention_class, storage_state, created_at
                ) VALUES (?, ?, 1, 'application/pdf', 'allowed', 'encrypted-object-v1',
                          'project-lifetime', 'pending', ?)
                """,
                (OBJECT_SHA256, PROJECT_ID, CREATED_AT),
            )
            connection.execute(
                "UPDATE object_records SET storage_state='available', verified_at=? WHERE object_sha256=?",
                ("2026-08-14T12:00:01.000Z", OBJECT_SHA256),
            )
            self.assertEqual(
                ("available", "2026-08-14T12:00:01.000Z"),
                tuple(
                    connection.execute(
                        "SELECT storage_state, verified_at FROM object_records WHERE object_sha256=?",
                        (OBJECT_SHA256,),
                    ).fetchone()
                ),
            )

            outbox_id = "01890f6e-6a40-7cc5-98b7-000000000301"
            connection.execute(
                """
                INSERT INTO outbox_events (
                    outbox_id, project_id, revision_id, event_type, occurred_at,
                    available_at, state, idempotency_key, record_sha256
                ) VALUES (?, ?, ?, 'record.created', ?, ?, 'pending', 'record-created-1', ?)
                """,
                (outbox_id, PROJECT_ID, record_revision, CREATED_AT, CREATED_AT, "d" * 64),
            )
            connection.execute(
                "UPDATE outbox_events SET state='publishing', attempt_count=1 WHERE outbox_id=?",
                (outbox_id,),
            )
            self.assertEqual(
                ("publishing", 1),
                tuple(
                    connection.execute(
                        "SELECT state, attempt_count FROM outbox_events WHERE outbox_id=?",
                        (outbox_id,),
                    ).fetchone()
                ),
            )

            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("DROP TRIGGER settings_no_update")
        finally:
            connection.close()

    def test_ordinary_connection_is_a_sealed_non_migration_capability(self) -> None:
        self.initialize()
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertNotIsInstance(connection, sqlite3.Connection)
            for escape_hatch in (
                "backup",
                "create_aggregate",
                "create_collation",
                "create_function",
                "cursor",
                "deserialize",
                "enable_load_extension",
                "getconfig",
                "load_extension",
                "serialize",
                "set_authorizer",
                "set_progress_handler",
                "set_trace_callback",
                "setconfig",
            ):
                self.assertFalse(hasattr(connection, escape_hatch), escape_hatch)

            cursor = connection.execute("SELECT 1")
            self.assertFalse(hasattr(cursor, "connection"))
            self.assertEqual(1, cursor.fetchone()[0])

            connection.execute(
                """
                INSERT INTO settings (
                    setting_id, project_id, setting_key, revision, value_type,
                    boolean_value, created_at, modified_at
                ) VALUES (?, ?, 'privacy.local-only', 0, 'boolean', 1, ?, ?)
                """,
                (SETTING_ID, PROJECT_ID, CREATED_AT, CREATED_AT),
            )
            protected_writes = (
                f"PRAGMA application_id={APPLICATION_ID + 1}",
                f"PRAGMA user_version={DATABASE_SCHEMA_VERSION + 1}",
                "PRAGMA schema_version=999",
                "PRAGMA foreign_keys=OFF",
                "PRAGMA trusted_schema=ON",
                "PRAGMA recursive_triggers=OFF",
                "PRAGMA journal_mode=DELETE",
                "PRAGMA synchronous=OFF",
                "PRAGMA wal_autocheckpoint=1",
                "PRAGMA locking_mode=EXCLUSIVE",
                "PRAGMA busy_timeout=1",
                "PRAGMA writable_schema=ON",
                "PRAGMA ignore_check_constraints=ON",
                "PRAGMA defer_foreign_keys=ON",
            )
            for statement in protected_writes:
                with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(statement)

            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("DROP TRIGGER settings_no_update")
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("UPDATE settings SET boolean_value=0 WHERE setting_id=?", (SETTING_ID,))
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("SELECT load_extension('untrusted')")

            self.assertEqual(APPLICATION_ID, connection.execute("PRAGMA application_id").fetchone()[0])
            self.assertEqual(DATABASE_SCHEMA_VERSION, connection.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(1, connection.execute("PRAGMA foreign_keys").fetchone()[0])
            self.assertEqual(0, connection.execute("PRAGMA trusted_schema").fetchone()[0])
            self.assertEqual(1, connection.execute("PRAGMA recursive_triggers").fetchone()[0])
            self.assertEqual("wal", connection.execute("PRAGMA journal_mode").fetchone()[0])
            self.assertEqual(2, connection.execute("PRAGMA synchronous").fetchone()[0])
            self.assertEqual(1_000, connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0])
            self.assertEqual("normal", connection.execute("PRAGMA locking_mode").fetchone()[0])
            self.assertEqual(5_000, connection.execute("PRAGMA busy_timeout").fetchone()[0])
        finally:
            connection.close()

    def test_wal_reader_snapshot_and_busy_writer_wait_are_concurrent(self) -> None:
        self.initialize()
        reader = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        writer = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            reader.execute("BEGIN")
            self.assertEqual(0, reader.execute("SELECT count(*) FROM settings").fetchone()[0])
            writer.execute("BEGIN IMMEDIATE")
            writer.execute(
                """
                INSERT INTO settings (
                    setting_id, project_id, setting_key, revision, value_type,
                    text_value, created_at, modified_at
                ) VALUES (?, ?, 'display.theme', 0, 'text', 'dark', ?, ?)
                """,
                (SETTING_ID, PROJECT_ID, CREATED_AT, CREATED_AT),
            )
            writer.execute("COMMIT")
            self.assertEqual(0, reader.execute("SELECT count(*) FROM settings").fetchone()[0])
            reader.execute("ROLLBACK")
            self.assertEqual(1, reader.execute("SELECT count(*) FROM settings").fetchone()[0])

            writer.execute("BEGIN IMMEDIATE")
            started = threading.Event()
            finished = threading.Event()
            result: list[BaseException | str] = []

            def second_writer() -> None:
                concurrent = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
                try:
                    started.set()
                    concurrent.execute("BEGIN IMMEDIATE")
                    concurrent.execute(
                        """
                        INSERT INTO settings (
                            setting_id, project_id, setting_key, revision, value_type,
                            integer_value, created_at, modified_at
                        ) VALUES (?, ?, 'display.scale', 0, 'integer', 100, ?, ?)
                        """,
                        ("01890f6e-6a40-7cc5-98b7-123456789ac1", PROJECT_ID, CREATED_AT, CREATED_AT),
                    )
                    concurrent.execute("COMMIT")
                    result.append("committed")
                except Exception as error:
                    result.append(error)
                finally:
                    concurrent.close()
                    finished.set()

            thread = threading.Thread(target=second_writer, daemon=True)
            thread.start()
            self.assertTrue(started.wait(2))
            time.sleep(0.05)
            self.assertFalse(finished.is_set())
            writer.execute("COMMIT")
            self.assertTrue(finished.wait(2))
            thread.join(timeout=2)
            self.assertEqual(["committed"], result)
        finally:
            if writer.in_transaction:
                writer.execute("ROLLBACK")
            reader.close()
            writer.close()

    def test_existing_linked_or_mismatched_database_is_denied_without_overwrite(self) -> None:
        sentinel = b"not a database\n"
        self.database.write_bytes(sentinel)
        with self.assertRaises(StorageProblem):
            initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        self.assertEqual(sentinel, self.database.read_bytes())
        self.database.unlink()

        outside = self.root / "outside.bin"
        outside.write_bytes(sentinel)
        os.link(outside, self.database)
        with self.assertRaises(StorageProblem):
            initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        self.assertEqual(sentinel, outside.read_bytes())
        self.database.unlink()

        raw = sqlite3.connect(self.database, autocommit=True)
        raw.execute("CREATE TABLE unrelated(value TEXT)")
        raw.execute(f"PRAGMA application_id={APPLICATION_ID + 1}")
        raw.close()
        before = self.database.read_bytes()
        with self.assertRaises(StorageProblem):
            open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(before, self.database.read_bytes())
        inspection = sqlite3.connect(self.database, autocommit=True)
        self.assertEqual("delete", inspection.execute("PRAGMA journal_mode").fetchone()[0])
        inspection.close()
        self.database.unlink()

        self.initialize()
        raw = sqlite3.connect(self.database, autocommit=True)
        raw.execute(f"PRAGMA application_id={APPLICATION_ID + 1}")
        raw.close()
        before = self.database.read_bytes()
        with self.assertRaises(StorageProblem):
            open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(before, self.database.read_bytes())

    def test_forged_schema_sql_is_rejected_by_exact_fingerprint(self) -> None:
        self.initialize()
        raw = sqlite3.connect(self.database, autocommit=True)
        original = raw.execute("SELECT sql FROM sqlite_schema WHERE name='settings'").fetchone()[0]
        forged = original.replace("CHECK (text_value IS NULL OR length(text_value) <= 65536)", "CHECK (1)")
        self.assertNotEqual(original, forged)
        raw.execute("PRAGMA writable_schema=ON")
        raw.execute("UPDATE sqlite_schema SET sql=? WHERE type='table' AND name='settings'", (forged,))
        schema_version = raw.execute("PRAGMA schema_version").fetchone()[0]
        raw.execute(f"PRAGMA schema_version={schema_version + 1}")
        raw.execute("PRAGMA writable_schema=OFF")
        raw.close()

        before = self.database.read_bytes()
        with self.assertRaises(StorageProblem):
            open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(before, self.database.read_bytes())


if __name__ == "__main__":
    unittest.main()
