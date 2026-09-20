"""Exact predecessor and rollback proof for protected import-preview storage."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from research_observatory_core import storage
from research_observatory_core.migrations import runner

from tests.data import test_sqlite_migrations as predecessor

V10_SCHEMA = "49459b9ca8e54d27ad45abf16615946107a8d73e1ba8e211f1c45bc8fa230187"
V10_PROFILE = "0641cf38a63226c98c9df55093f4c696687b14a2baddfb17f7986aa85efad8fb"
PREVIEW_TABLES = (
    "import_previews",
    "import_source_chunks",
    "import_source_seals",
    "import_parse_attempts",
    "import_parse_records",
    "import_parse_completions",
    "import_draft_revisions",
    "import_record_decisions",
    "import_preview_events",
)


def create_version_10_fixture(database: Path) -> None:
    """Reproduce the exact committed v10 schema, not current bootstrap DDL."""
    predecessor.create_version_9_fixture(database)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        storage._configure_connection(connection, initialize=True)
        connection.execute("BEGIN IMMEDIATE")
        for statement in storage.DEPENDENCY_IMPACT_DDL:
            connection.execute(statement)
        connection.execute("DROP TRIGGER schema_metadata_no_update")
        connection.execute("DROP TRIGGER schema_metadata_no_delete")
        connection.execute("ALTER TABLE schema_metadata RENAME TO schema_metadata_v9")
        connection.execute(storage.SCHEMA_METADATA_V10_DDL)
        connection.execute(
            "INSERT INTO schema_metadata SELECT singleton, 10, database_profile, application_id, ?, ?, created_at "
            "FROM schema_metadata_v9",
            (V10_PROFILE, V10_SCHEMA),
        )
        connection.execute("DROP TABLE schema_metadata_v9")
        for statement in predecessor.v0002_schema_history.SCHEMA_METADATA_TRIGGERS:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations VALUES ('0010_dependency_impacts', 9, 10, ?, ?, ?, ?, 'alembic-1.18.5')",
            (predecessor.CREATED_AT, "f" * 64, storage.MATERIAL_DEPENDENCY_SCHEMA_SHA256, V10_SCHEMA),
        )
        connection.execute("PRAGMA user_version=10")
        connection.execute(
            "INSERT INTO settings (setting_id, project_id, setting_key, revision, value_type, "
            "text_value, created_at, modified_at) VALUES (?, ?, 'preview-migration-fixture', 0, 'text', 'dark', ?, ?)",
            (
                "01890f6e-6a40-7cc5-98b7-123456789aff",
                predecessor.PROJECT_ID,
                predecessor.CREATED_AT,
                predecessor.CREATED_AT,
            ),
        )
        if storage._schema_fingerprint(connection) != V10_SCHEMA:
            raise AssertionError("historical-v10-fingerprint-changed")
        connection.execute("COMMIT")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()


class ImportPreviewMigrationTests(unittest.TestCase):
    setUp = predecessor.SqliteMigrationTests.setUp
    tearDown = predecessor.SqliteMigrationTests.tearDown
    database: Path
    project: Path

    def test_exact_v10_is_backed_up_and_preserved_without_fabricated_previews(self):
        create_version_10_fixture(self.database)
        plan = runner.plan_database_migration(self.database, expected_project_id=predecessor.PROJECT_ID)
        self.assertEqual(("0011_import_previews", "0012_import_summaries", "0013_import_commits"), plan.migration_ids)
        result = runner.migrate_database(self.database, expected_project_id=predecessor.PROJECT_ID)
        self.assertEqual("migrated", result.status)
        self.assertIsNotNone(result.backup_relative_path)
        backup = sqlite3.connect(self.project / str(result.backup_relative_path), autocommit=True)
        try:
            self.assertEqual(V10_SCHEMA, storage._schema_fingerprint(backup))
            self.assertEqual(10, backup.execute("PRAGMA user_version").fetchone()[0])
        finally:
            backup.close()
        current = storage.open_canonical_database(self.database, expected_project_id=predecessor.PROJECT_ID)
        try:
            self.assertEqual(13, current.execute("PRAGMA user_version").fetchone()[0])
            for table in PREVIEW_TABLES:
                self.assertEqual(0, current.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            self.assertEqual("dark", current.execute("SELECT text_value FROM settings").fetchone()[0])
            self.assertEqual(
                "legacy-unreported", current.execute("SELECT coverage FROM material_dependency_outputs").fetchone()[0]
            )
            self.assertEqual([], current.execute("PRAGMA foreign_key_check").fetchall())
        finally:
            current.close()
        self.assertEqual(
            "current", runner.migrate_database(self.database, expected_project_id=predecessor.PROJECT_ID).status
        )

    def test_every_v11_step_rolls_back_to_v10_and_retries(self):
        from research_observatory_core.migrations.versions import v0011_import_previews as revision

        for index, failpoint in enumerate(revision.MATERIAL_MIGRATION_STEPS):
            with self.subTest(step=failpoint):
                database = self.project / f"failure-{index}" / "state/project.sqlite3"
                create_version_10_fixture(database)

                def fail(completed: str, expected: str = failpoint) -> None:
                    if completed == expected:
                        raise RuntimeError("synthetic-migration-interruption")

                with (
                    patch.object(revision, "_migration_step_completed", fail),
                    self.assertRaises(runner.MigrationProblem),
                ):
                    runner.migrate_database(database, expected_project_id=predecessor.PROJECT_ID)
                plan = runner.plan_database_migration(database, expected_project_id=predecessor.PROJECT_ID)
                self.assertEqual(10, plan.source_schema_version)
                self.assertEqual(V10_SCHEMA, plan.source_schema_sha256)
                self.assertEqual(
                    "migrated", runner.migrate_database(database, expected_project_id=predecessor.PROJECT_ID).status
                )
