"""Frozen v12 predecessor, retained before import-commit schema changes."""

from __future__ import annotations

import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]
from research_observatory_core import storage
from research_observatory_core.migrations import runner

from tests.data import test_import_summary_migration as predecessor

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/imports/schema-v12-authority.json"
V12_SCHEMA = "42a9886d0b9d132071cebe3170d12b46a048148f9c69dcf624178d4f281840fa"
V12_PROFILE = "9d6ac8532068f3271c42140525a6c106208f92ca6f8362c36eee4e25b02d863f"
COMMIT_TABLES = (
    "import_commit_preparations",
    "import_commit_rows",
    "import_source_records",
    "import_manifests",
    "import_manifest_members",
    "import_manifest_seals",
)


def create_version_12_fixture(database: Path) -> None:
    authority = json.loads(FIXTURE.read_text("utf-8"))
    if authority["schemaSha256"] != V12_SCHEMA or authority["profileSha256"] != V12_PROFILE:
        raise AssertionError("historical-v12-authority-changed")
    predecessor.create_version_11_fixture(database)
    connection = sqlite3.connect(database, autocommit=True)
    try:
        storage._configure_connection(connection, initialize=True)
        connection.execute("BEGIN IMMEDIATE")
        for statement in authority["summaryDdl"]:
            connection.execute(statement)
        connection.execute("DROP TRIGGER schema_metadata_no_update")
        connection.execute("DROP TRIGGER schema_metadata_no_delete")
        connection.execute("ALTER TABLE schema_metadata RENAME TO schema_metadata_v11")
        connection.execute(authority["metadataDdl"])
        connection.execute(
            "INSERT INTO schema_metadata SELECT singleton, 12, database_profile, application_id, ?, ?, created_at "
            "FROM schema_metadata_v11",
            (V12_PROFILE, V12_SCHEMA),
        )
        connection.execute("DROP TABLE schema_metadata_v11")
        for statement in predecessor.predecessor.predecessor.v0002_schema_history.SCHEMA_METADATA_TRIGGERS:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations VALUES ('0012_import_summaries', 11, 12, ?, ?, ?, ?, 'alembic-1.18.5')",
            (predecessor.predecessor.predecessor.CREATED_AT, "f" * 64, predecessor.V11_SCHEMA, V12_SCHEMA),
        )
        connection.execute("PRAGMA user_version=12")
        if storage._schema_fingerprint(connection) != V12_SCHEMA:
            raise AssertionError("historical-v12-fingerprint-mismatch")
        connection.execute("COMMIT")
    finally:
        connection.close()


class ImportCommitMigrationTests(unittest.TestCase):
    setUp = predecessor.ImportSummaryMigrationTests.setUp
    tearDown = predecessor.ImportSummaryMigrationTests.tearDown
    database: Path

    def test_frozen_v12_fixture_is_exact_and_retains_existing_preview(self):
        create_version_12_fixture(self.database)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(V12_SCHEMA, storage._schema_fingerprint(connection))
            self.assertEqual(12, connection.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual([], connection.execute("PRAGMA foreign_key_check").fetchall())
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM import_previews").fetchone()[0])
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM import_summary_completions").fetchone()[0])

    def test_exact_v12_upgrade_keeps_verified_backup_and_no_invented_commits(self):
        create_version_12_fixture(self.database)
        project_id = predecessor.predecessor.predecessor.PROJECT_ID
        plan = runner.plan_database_migration(self.database, expected_project_id=project_id)
        self.assertEqual(("0013_import_commits",), plan.migration_ids)
        result = runner.migrate_database(self.database, expected_project_id=project_id)
        self.assertEqual("migrated", result.status)
        self.assertIsNotNone(result.backup_relative_path)
        with closing(sqlite3.connect(self.database.parent.parent / str(result.backup_relative_path))) as backup:
            self.assertEqual(V12_SCHEMA, storage._schema_fingerprint(backup))
            self.assertEqual(12, backup.execute("PRAGMA user_version").fetchone()[0])
        for _ in range(2):
            with storage.open_canonical_database(self.database, expected_project_id=project_id) as connection:
                self.assertEqual(13, connection.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM import_previews").fetchone()[0])
                for table in COMMIT_TABLES:
                    self.assertEqual(0, connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        self.assertEqual("current", runner.migrate_database(self.database, expected_project_id=project_id).status)

    def test_each_material_migration_failure_rolls_back_to_exact_v12(self):
        from research_observatory_core.migrations.versions import v0013_import_commits

        for step in v0013_import_commits.MATERIAL_MIGRATION_STEPS:
            with self.subTest(step=step):
                project = self.database.parent.parent.parent / step
                database = project / "state/project.sqlite3"
                create_version_12_fixture(database)

                def fail_at(observed, expected=step):
                    if observed == expected:
                        raise ValueError("synthetic-v13-interruption")

                with (
                    patch.object(v0013_import_commits, "_migration_step_completed", side_effect=fail_at),
                    self.assertRaises(runner.MigrationProblem),
                ):
                    runner.migrate_database(
                        database, expected_project_id=predecessor.predecessor.predecessor.PROJECT_ID
                    )
                with closing(sqlite3.connect(database)) as connection:
                    self.assertEqual(V12_SCHEMA, storage._schema_fingerprint(connection))
                    self.assertEqual(12, connection.execute("PRAGMA user_version").fetchone()[0])
                    self.assertEqual([], connection.execute("PRAGMA foreign_key_check").fetchall())


class ProtectedImportCommitMigrationTests(unittest.TestCase):
    """Real SQLCipher boundary with synthetic in-memory key authority, not DPAPI."""

    setUp = predecessor.protected_fixture.ProtectedDatabaseTests.setUp
    tearDown = predecessor.protected_fixture.ProtectedDatabaseTests.tearDown

    def protected_source(self):
        legacy = self.root / "legacy/state/project.sqlite3"
        create_version_12_fixture(legacy)
        identity = predecessor.predecessor.predecessor.PROJECT_ID
        with self.keys.active_key(identity, create=True) as lease:
            material = lease.use(bytes)
        source = sqlcipher.connect(legacy.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(self.database), f"x'{material.hex()}'"))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={storage.APPLICATION_ID}")
            source.execute("PRAGMA protected.user_version=12")
            self.assertEqual("wal", source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0])
            source.execute("DETACH DATABASE protected")
        finally:
            source.close()
        return identity

    def test_encrypted_rollback_retry_backup_and_reopen(self):
        from research_observatory_core.migrations.versions import v0013_import_commits as revision

        identity = self.protected_source()

        def fail(step):
            if step == "user-version-advance":
                raise RuntimeError("synthetic-encrypted-v13-interruption")

        with patch.object(revision, "_migration_step_completed", fail), self.assertRaises(runner.MigrationProblem):
            runner.migrate_database(self.database, expected_project_id=identity)
        plan = runner.plan_database_migration(self.database, expected_project_id=identity)
        self.assertEqual(12, plan.source_schema_version)
        self.assertEqual(V12_SCHEMA, plan.source_schema_sha256)
        result = runner.migrate_database(self.database, expected_project_id=identity)
        self.assertEqual("migrated", result.status)
        backup = self.root / str(result.backup_relative_path)
        for path in (self.database, backup):
            self.assertNotEqual(b"SQLite format 3\x00", path.read_bytes()[:16])
        with self.keys.active_key(identity, create=False) as lease:
            material = lease.use(bytes)
        saved = sqlcipher.connect(backup.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            saved.execute(f"PRAGMA key=\"x'{material.hex()}'\"")
            self.assertEqual(V12_SCHEMA, storage._schema_fingerprint(saved))
            self.assertEqual("ok", saved.execute("PRAGMA quick_check").fetchone()[0])
        finally:
            saved.close()
        for _ in range(2):
            with storage.open_canonical_database(self.database, expected_project_id=identity) as current:
                self.assertEqual(13, current.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual(
                    predecessor.PREVIEW, current.execute("SELECT preview_id FROM import_previews").fetchone()[0]
                )
                self.assertEqual([], current.execute("PRAGMA foreign_key_check").fetchall())
                for table in COMMIT_TABLES:
                    self.assertEqual(0, current.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
