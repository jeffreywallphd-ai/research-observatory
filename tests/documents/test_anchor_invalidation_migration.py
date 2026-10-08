"""Literal populated v26 preservation and interrupted output-free invalidation migration."""

import json
import sqlite3
import sys
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core import storage  # noqa: E402
from research_observatory_core.migrations import runner  # noqa: E402
from research_observatory_core.migrations.versions import v0027_revision_invalidations as migration  # noqa: E402
from research_observatory_core.repositories import _SqliteDependencyImpactRepository  # noqa: E402

from tests.documents import test_acquisition_recovery_migration as predecessor  # noqa: E402


class AnchorInvalidationMigrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = predecessor.AcquisitionRecoveryMigrationTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_literal_populated_v26_records_runs_and_ciphertexts_survive_migration_and_reopen(self):
        fixture = self.fixture
        manifest, project, database = fixture.load("v26-populated-predecessor")
        fixture.assert_predecessor_rows(database, manifest)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(26, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(manifest["schemaSha256"], storage._schema_fingerprint(db))
            run_ids = [r[0] for r in db.execute("SELECT run_id FROM dependency_impact_runs ORDER BY run_id")]
        self.assertTrue(run_ids)
        plan = runner.plan_database_migration(database, expected_project_id=manifest["projectId"])
        self.assertEqual((migration.revision,), plan.migration_ids)
        result = runner.migrate_database(database, expected_project_id=manifest["projectId"])
        self.assertEqual("migrated", result.status)
        recovery = json.loads((project / result.recovery_manifest_relative_path).read_text())
        recovery_schema = json.loads(
            (ROOT / "packages/contracts/storage/sqlite-migration-recovery.schema.json").read_text()
        )
        validator = Draft202012Validator(recovery_schema, format_checker=FormatChecker())
        self.assertEqual([], list(validator.iter_errors(recovery)))
        wrong = dict(recovery, migrationIds=["0026_document_revisions"])
        self.assertTrue(list(validator.iter_errors(wrong)))
        wrong = dict(recovery, sourceSchemaSha256=storage.EXPECTED_SCHEMA_SHA256)
        self.assertTrue(list(validator.iter_errors(wrong)))
        fixture.assert_predecessor_rows(database, manifest)
        fixture.assert_ciphertext(project, manifest)
        backup = project / result.backup_relative_path
        fixture.assert_predecessor_rows(backup, manifest)
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(26, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(manifest["schemaSha256"], storage._schema_fingerprint(db))
        with closing(storage.open_canonical_database(database, expected_project_id=manifest["projectId"])) as db:
            self.assertEqual(27, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertTrue(storage.database_integrity_report(db, expected_project_id=manifest["projectId"]).ok)
        repository = _SqliteDependencyImpactRepository(database, manifest["projectId"])
        before = tuple(repository.run(run_id) for run_id in run_ids)
        reopened = _SqliteDependencyImpactRepository(database, manifest["projectId"])
        self.assertEqual(before, tuple(reopened.run(run_id) for run_id in run_ids))
        fixture.assert_predecessor_rows(database, manifest)
        self.assertEqual("current", runner.migrate_database(database, expected_project_id=manifest["projectId"]).status)

    def test_each_material_step_rolls_back_exact_v26_rows_schema_history_and_retry_succeeds(self):
        for index, step in enumerate(migration.MATERIAL_MIGRATION_STEPS):
            with self.subTest(step=step):
                fixture = predecessor.AcquisitionRecoveryMigrationTests(methodName="runTest")
                fixture.setUp()
                try:
                    manifest, project, database = fixture.load("v26-populated-predecessor")
                    with closing(sqlite3.connect(database)) as db:
                        metadata = db.execute("SELECT * FROM schema_metadata").fetchall()
                        history = db.execute("SELECT * FROM schema_migrations ORDER BY migration_id").fetchall()

                    def interrupt(completed, step=step, index=index):
                        if completed == step:
                            raise RuntimeError("synthetic-v27-interruption-" + str(index))

                    with (
                        patch.object(migration, "_migration_step_completed", side_effect=interrupt),
                        self.assertRaises(runner.MigrationProblem) as failure,
                    ):
                        runner.migrate_database(database, expected_project_id=manifest["projectId"])
                    self.assertEqual("migration-execution-failed", failure.exception.code)
                    self.assertIsInstance(failure.exception.__cause__, RuntimeError)
                    self.assertEqual("synthetic-v27-interruption-" + str(index), str(failure.exception.__cause__))
                    fixture.assert_predecessor_rows(database, manifest)
                    fixture.assert_ciphertext(project, manifest)
                    with closing(sqlite3.connect(database)) as db:
                        self.assertEqual(26, db.execute("PRAGMA user_version").fetchone()[0])
                        self.assertEqual(manifest["schemaSha256"], storage._schema_fingerprint(db))
                        self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
                        self.assertEqual(metadata, db.execute("SELECT * FROM schema_metadata").fetchall())
                        self.assertEqual(
                            history, db.execute("SELECT * FROM schema_migrations ORDER BY migration_id").fetchall()
                        )
                    retry = runner.migrate_database(database, expected_project_id=manifest["projectId"])
                    self.assertEqual("migrated", retry.status)
                    fixture.assert_predecessor_rows(database, manifest)
                    fixture.assert_ciphertext(project, manifest)
                finally:
                    fixture.doCleanups()


if __name__ == "__main__":
    unittest.main(verbosity=2)
