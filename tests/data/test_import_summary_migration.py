"""Frozen v11 predecessor and backup/rollback proof for preview summaries."""

from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]
from research_observatory_core import storage
from research_observatory_core.migrations import runner

from tests.data import test_import_preview_migration as predecessor
from tests.security import test_protected_database as protected_fixture

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/imports/schema-v11-authority.json"
V11_SCHEMA = "33f607dea1a2b20e0d1b451cafdbcaa5d1bb58e1b91499525adad40bc5a8f5c0"
V11_PROFILE = "c751146ae0301c14716e8fa1f0c29b9929a1dd4caa9a3b9fd6d98595a7888c91"
PREVIEW = "01900000-0000-7000-8000-000000000011"
SUMMARY_TABLES = (
    "import_summary_attempts",
    "import_summary_rows",
    "import_summary_groups",
    "import_summary_completions",
)


def create_version_11_fixture(database: Path) -> None:
    """Apply literal predecessor bytes captured before the v12 implementation."""
    authority = json.loads(FIXTURE.read_text("utf-8"))
    if authority["schemaSha256"] != V11_SCHEMA or authority["profileSha256"] != V11_PROFILE:
        raise AssertionError("historical-v11-authority-changed")
    predecessor.create_version_10_fixture(database)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        storage._configure_connection(connection, initialize=True)
        connection.execute("BEGIN IMMEDIATE")
        for statement in authority["previewDdl"]:
            connection.execute(statement)
        connection.execute("DROP TRIGGER schema_metadata_no_update")
        connection.execute("DROP TRIGGER schema_metadata_no_delete")
        connection.execute("ALTER TABLE schema_metadata RENAME TO schema_metadata_v10")
        connection.execute(authority["metadataDdl"])
        connection.execute(
            "INSERT INTO schema_metadata SELECT singleton, 11, database_profile, application_id, ?, ?, created_at "
            "FROM schema_metadata_v10",
            (V11_PROFILE, V11_SCHEMA),
        )
        connection.execute("DROP TABLE schema_metadata_v10")
        for statement in predecessor.predecessor.v0002_schema_history.SCHEMA_METADATA_TRIGGERS:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations VALUES ('0011_import_previews', 10, 11, ?, ?, ?, ?, 'alembic-1.18.5')",
            (predecessor.predecessor.CREATED_AT, "f" * 64, predecessor.V10_SCHEMA, V11_SCHEMA),
        )
        connection.execute(
            "INSERT INTO import_previews VALUES (?, ?, 'synthetic-preserved.csv', 'csv', 'utf-8', ?, ?, ?, ?)",
            (
                PREVIEW,
                predecessor.predecessor.PROJECT_ID,
                '{"store":{"value":"permitted","basis":"researcher-confirmed"},'
                '"inspect":{"value":"permitted","basis":"researcher-confirmed"}}',
                PREVIEW,
                "1" * 32,
                predecessor.predecessor.CREATED_AT,
            ),
        )
        connection.execute(
            "INSERT INTO import_preview_events VALUES (?, ?, 1, 'created', ?, ?, ?)",
            (PREVIEW, predecessor.predecessor.PROJECT_ID, PREVIEW, "1" * 32, predecessor.predecessor.CREATED_AT),
        )
        connection.execute("PRAGMA user_version=11")
        if storage._schema_fingerprint(connection) != V11_SCHEMA:
            raise AssertionError("historical-v11-fingerprint-changed")
        connection.execute("COMMIT")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()


class ImportSummaryMigrationTests(unittest.TestCase):
    setUp = predecessor.ImportPreviewMigrationTests.setUp
    tearDown = predecessor.ImportPreviewMigrationTests.tearDown
    database: Path
    project: Path

    def test_frozen_v11_fixture_is_exact(self):
        create_version_11_fixture(self.database)
        connection = sqlite3.connect(self.database)
        try:
            self.assertEqual(V11_SCHEMA, storage._schema_fingerprint(connection))
            self.assertEqual([], connection.execute("PRAGMA foreign_key_check").fetchall())
        finally:
            connection.close()

    def test_exact_v11_backup_preserves_rows_and_does_not_fabricate_summaries(self):
        create_version_11_fixture(self.database)
        identity = predecessor.predecessor.PROJECT_ID
        plan = runner.plan_database_migration(self.database, expected_project_id=identity)
        self.assertEqual(("0012_import_summaries",), plan.migration_ids)
        result = runner.migrate_database(self.database, expected_project_id=identity)
        self.assertEqual("migrated", result.status)
        self.assertIsNotNone(result.backup_relative_path)
        backup = sqlite3.connect(self.project / str(result.backup_relative_path))
        try:
            self.assertEqual(V11_SCHEMA, storage._schema_fingerprint(backup))
            self.assertEqual(11, backup.execute("PRAGMA user_version").fetchone()[0])
        finally:
            backup.close()
        current = storage.open_canonical_database(self.database, expected_project_id=identity)
        try:
            self.assertEqual(12, current.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(
                "synthetic-preserved.csv", current.execute("SELECT source_name FROM import_previews").fetchone()[0]
            )
            self.assertEqual("dark", current.execute("SELECT text_value FROM settings").fetchone()[0])
            for table in SUMMARY_TABLES:
                self.assertEqual(0, current.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            self.assertEqual([], current.execute("PRAGMA foreign_key_check").fetchall())
        finally:
            current.close()
        self.assertEqual("current", runner.migrate_database(self.database, expected_project_id=identity).status)
        from research_observatory_core.import_preview_repository import sqlite_import_preview_repository

        prior = sqlite_import_preview_repository(self.database, identity).read(PREVIEW)
        self.assertEqual("created", prior.state)
        self.assertEqual(",", prior.delimiter)
        self.assertTrue(prior.rights.permits("inspect"))
        self.assertFalse(prior.rights.permits("export"))

    def test_each_v12_step_rolls_back_to_exact_v11_and_retries(self):
        from research_observatory_core.migrations.versions import v0012_import_summaries as revision

        for index, failpoint in enumerate(revision.MATERIAL_MIGRATION_STEPS):
            with self.subTest(step=failpoint):
                database = self.project / f"summary-failure-{index}" / "state/project.sqlite3"
                create_version_11_fixture(database)

                def fail(completed: str, expected: str = failpoint) -> None:
                    if completed == expected:
                        raise RuntimeError("synthetic-summary-migration-interruption")

                with (
                    patch.object(revision, "_migration_step_completed", fail),
                    self.assertRaises(runner.MigrationProblem),
                ):
                    runner.migrate_database(database, expected_project_id=predecessor.predecessor.PROJECT_ID)
                plan = runner.plan_database_migration(database, expected_project_id=predecessor.predecessor.PROJECT_ID)
                self.assertEqual(11, plan.source_schema_version)
                self.assertEqual(V11_SCHEMA, plan.source_schema_sha256)
                self.assertEqual(
                    "migrated",
                    runner.migrate_database(database, expected_project_id=predecessor.predecessor.PROJECT_ID).status,
                )


class ProtectedImportSummaryMigrationTests(unittest.TestCase):
    setUp = protected_fixture.ProtectedDatabaseTests.setUp
    tearDown = protected_fixture.ProtectedDatabaseTests.tearDown

    def protected_source(self):
        legacy = self.root / "legacy/state/project.sqlite3"
        create_version_11_fixture(legacy)
        identity = predecessor.predecessor.PROJECT_ID
        with self.keys.active_key(identity, create=True) as lease:
            material = lease.use(bytes)
        source = sqlcipher.connect(legacy.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(self.database), f"x'{material.hex()}'"))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={storage.APPLICATION_ID}")
            source.execute("PRAGMA protected.user_version=11")
            self.assertEqual("wal", source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0])
            source.execute("DETACH DATABASE protected")
        finally:
            source.close()
        return identity

    def test_v11_sqlcipher_upgrade_keeps_verified_encrypted_backup(self):
        identity = self.protected_source()
        result = runner.migrate_database(self.database, expected_project_id=identity)
        self.assertEqual("migrated", result.status)
        self.assertEqual(11, result.source_schema_version)
        backup = self.root / str(result.backup_relative_path)
        self.assertNotEqual(b"SQLite format 3\x00", backup.read_bytes()[:16])
        with self.keys.active_key(identity, create=False) as lease:
            material = lease.use(bytes)
        saved = sqlcipher.connect(backup.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            saved.execute(f"PRAGMA key=\"x'{material.hex()}'\"")
            self.assertEqual(V11_SCHEMA, storage._schema_fingerprint(saved))
            self.assertEqual("ok", saved.execute("PRAGMA quick_check").fetchone()[0])
        finally:
            saved.close()
        current = storage.open_canonical_database(self.database, expected_project_id=identity)
        try:
            self.assertEqual(12, current.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(PREVIEW, current.execute("SELECT preview_id FROM import_previews").fetchone()[0])
        finally:
            current.close()

    def test_v11_sqlcipher_failed_upgrade_retains_source_then_retries(self):
        from research_observatory_core.migrations.versions import v0012_import_summaries as revision

        identity = self.protected_source()

        def fail(step):
            if step == "user-version-advance":
                raise RuntimeError("synthetic-encrypted-migration-interruption")

        with patch.object(revision, "_migration_step_completed", fail), self.assertRaises(runner.MigrationProblem):
            runner.migrate_database(self.database, expected_project_id=identity)
        plan = runner.plan_database_migration(self.database, expected_project_id=identity)
        self.assertEqual(11, plan.source_schema_version)
        self.assertEqual(V11_SCHEMA, plan.source_schema_sha256)
        self.assertNotEqual(b"SQLite format 3\x00", self.database.read_bytes()[:16])
        self.assertEqual("migrated", runner.migrate_database(self.database, expected_project_id=identity).status)
