"""Literal populated v25 preservation and material interrupted v26 steps."""

import sqlite3
import sys
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core import storage  # noqa: E402
from research_observatory_core.migrations import runner  # noqa: E402
from research_observatory_core.migrations.versions import v0026_document_revisions as migration  # noqa: E402

from tests.documents import test_acquisition_recovery_migration as predecessor  # noqa: E402


class DocumentRevisionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = predecessor.AcquisitionRecoveryMigrationTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_literal_populated_v25_rows_and_ciphertexts_survive_forward_migration(self):
        fixture = self.fixture
        manifest, project, database = fixture.load("v25-populated-predecessor")
        fixture.assert_predecessor_rows(database, manifest)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(25, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(manifest["schemaSha256"], storage._schema_fingerprint(db))
        plan = runner.plan_database_migration(database, expected_project_id=manifest["projectId"])
        self.assertEqual((migration.revision,), plan.migration_ids)
        result = runner.migrate_database(database, expected_project_id=manifest["projectId"])
        self.assertEqual("migrated", result.status)
        fixture.assert_predecessor_rows(database, manifest)
        fixture.assert_ciphertext(project, manifest)
        backup = project / result.backup_relative_path
        fixture.assert_predecessor_rows(backup, manifest)
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(25, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(manifest["schemaSha256"], storage._schema_fingerprint(db))
        with closing(storage.open_canonical_database(database, expected_project_id=manifest["projectId"])) as db:
            self.assertEqual(26, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertTrue(storage.database_integrity_report(db, expected_project_id=manifest["projectId"]).ok)
            for table in storage.DOCUMENT_REVISION_TABLES:
                self.assertEqual(0, db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        self.assertEqual("current", runner.migrate_database(database, expected_project_id=manifest["projectId"]).status)

    def test_every_material_step_rolls_back_exact_v25_and_retry_succeeds(self):
        for index, step in enumerate(migration.MATERIAL_MIGRATION_STEPS):
            with self.subTest(step=step):
                fixture = predecessor.AcquisitionRecoveryMigrationTests(methodName="runTest")
                fixture.setUp()
                try:
                    manifest, project, database = fixture.load("v25-populated-predecessor")
                    with closing(sqlite3.connect(database)) as db:
                        original_metadata = db.execute("SELECT * FROM schema_metadata").fetchall()
                        original_history = db.execute(
                            "SELECT * FROM schema_migrations ORDER BY migration_id"
                        ).fetchall()

                    def interrupt(completed, step=step, index=index):
                        if completed == step:
                            raise RuntimeError("synthetic-v26-interruption-" + str(index))

                    with (
                        patch.object(migration, "_migration_step_completed", side_effect=interrupt),
                        self.assertRaises(runner.MigrationProblem) as failure,
                    ):
                        runner.migrate_database(database, expected_project_id=manifest["projectId"])
                    self.assertEqual("migration-execution-failed", failure.exception.code)
                    self.assertIsInstance(failure.exception.__cause__, RuntimeError)
                    self.assertEqual("synthetic-v26-interruption-" + str(index), str(failure.exception.__cause__))
                    fixture.assert_predecessor_rows(database, manifest)
                    fixture.assert_ciphertext(project, manifest)
                    with closing(sqlite3.connect(database)) as db:
                        self.assertEqual(25, db.execute("PRAGMA user_version").fetchone()[0])
                        self.assertEqual(manifest["schemaSha256"], storage._schema_fingerprint(db))
                        self.assertEqual(original_metadata, db.execute("SELECT * FROM schema_metadata").fetchall())
                        self.assertEqual(
                            original_history,
                            db.execute("SELECT * FROM schema_migrations ORDER BY migration_id").fetchall(),
                        )
                    retry = runner.migrate_database(database, expected_project_id=manifest["projectId"])
                    self.assertEqual("migrated", retry.status)
                    fixture.assert_predecessor_rows(database, manifest)
                    fixture.assert_ciphertext(project, manifest)
                finally:
                    fixture.doCleanups()


if __name__ == "__main__":
    unittest.main(verbosity=2)
