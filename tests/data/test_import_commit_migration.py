"""Frozen v12 predecessor, retained before import-commit schema changes."""

from __future__ import annotations

import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from research_observatory_core import storage

from tests.data import test_import_summary_migration as predecessor

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/imports/schema-v12-authority.json"
V12_SCHEMA = "42a9886d0b9d132071cebe3170d12b46a048148f9c69dcf624178d4f281840fa"
V12_PROFILE = "9d6ac8532068f3271c42140525a6c106208f92ca6f8362c36eee4e25b02d863f"


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


if __name__ == "__main__":
    unittest.main()
