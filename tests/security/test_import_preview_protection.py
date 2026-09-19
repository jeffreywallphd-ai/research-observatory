"""Actual SQLCipher predecessor migration; synthetic in-memory key authority."""

from __future__ import annotations

import unittest
from pathlib import Path

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]
from research_observatory_core import storage
from research_observatory_core.migrations.runner import migrate_database

from tests.data.test_import_preview_migration import V10_SCHEMA, create_version_10_fixture
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider
from tests.security import test_protected_database as fixture


class ImportPreviewProtectionTests(unittest.TestCase):
    setUp = fixture.ProtectedDatabaseTests.setUp
    tearDown = fixture.ProtectedDatabaseTests.tearDown
    root: Path
    database: Path
    keys: InMemoryDatabaseKeyProvider

    def test_v10_to_v11_retains_encrypted_verified_backup_and_reopens(self):
        legacy = self.root / "legacy/state/project.sqlite3"
        create_version_10_fixture(legacy)
        with self.keys.active_key(fixture.PROJECT_ID, create=True) as lease:
            material = lease.use(bytes)
        source = sqlcipher.connect(legacy.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        key_literal = f"x'{material.hex()}'"
        try:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(self.database), key_literal))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={storage.APPLICATION_ID}")
            source.execute("PRAGMA protected.user_version=10")
            source.execute("PRAGMA protected.journal_mode=WAL")
            source.execute("DETACH DATABASE protected")
        finally:
            source.close()
        result = migrate_database(self.database, expected_project_id=fixture.PROJECT_ID)
        self.assertEqual("migrated", result.status)
        self.assertEqual(("0011_import_previews",), result.migration_ids)
        backup = self.root / str(result.backup_relative_path)
        self.assertNotEqual(b"SQLite format 3\x00", backup.read_bytes()[:16])
        self.assertNotEqual(b"SQLite format 3\x00", self.database.read_bytes()[:16])
        protected = sqlcipher.connect(backup.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            protected.execute(f'PRAGMA key = "{key_literal}"')
            self.assertEqual([], protected.execute("PRAGMA cipher_integrity_check").fetchall())
            self.assertEqual(V10_SCHEMA, storage._schema_fingerprint(protected))
            self.assertEqual(10, protected.execute("PRAGMA user_version").fetchone()[0])
        finally:
            protected.close()
            key_literal = ""
            material = b""
        for _ in range(2):
            current = storage.open_canonical_database(self.database, expected_project_id=fixture.PROJECT_ID)
            try:
                self.assertEqual(11, current.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual("dark", current.execute("SELECT text_value FROM settings").fetchone()[0])
                self.assertEqual([], current.execute("PRAGMA foreign_key_check").fetchall())
            finally:
                current.close()
        self.assertEqual("current", migrate_database(self.database, expected_project_id=fixture.PROJECT_ID).status)
