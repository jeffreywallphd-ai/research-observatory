"""Actual literal v27, additive v28 and each material rollback/retry boundary."""

import json
import sqlite3
import sys
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]
from research_observatory_core import storage  # noqa: E402
from research_observatory_core.migrations import runner  # noqa: E402
from research_observatory_core.migrations.versions import v0028_document_enrichments as migration  # noqa: E402
from research_observatory_core.migrations.versions import v0029_lexical_index_generations as lexical  # noqa: E402

from tests.documents import test_acquisition_recovery_migration as predecessor  # noqa: E402


class ReferenceMigrationTests(unittest.TestCase):
    def fixture(self):
        fixture = predecessor.AcquisitionRecoveryMigrationTests(methodName="runTest")
        fixture.setUp()
        return fixture

    def test_exact_populated_v27_and_ciphertext_survive_backed_up_v28(self):
        fixture = self.fixture()
        try:
            manifest, project, database = fixture.load("v27-populated-predecessor")
            fixture.assert_predecessor_rows(database, manifest)
            plan = runner.plan_database_migration(database, expected_project_id=manifest["projectId"])
            self.assertEqual((migration.revision, lexical.revision), plan.migration_ids)
            result = runner.migrate_database(database, expected_project_id=manifest["projectId"])
            self.assertEqual("migrated", result.status)
            recovery = json.loads((project / result.recovery_manifest_relative_path).read_text())
            schema = json.loads((ROOT / "packages/contracts/storage/sqlite-migration-recovery.schema.json").read_text())
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            self.assertEqual([], list(validator.iter_errors(recovery)))
            for invalid in (
                dict(recovery, migrationIds=["0027_revision_invalidations"]),
                dict(recovery, sourceSchemaSha256=storage.EXPECTED_SCHEMA_SHA256),
                dict(recovery, targetSchemaVersion=27, targetSchemaSha256=manifest["schemaSha256"]),
            ):
                self.assertTrue(list(validator.iter_errors(invalid)))
            fixture.assert_predecessor_rows(database, manifest)
            fixture.assert_ciphertext(project, manifest)
            backup = project / result.backup_relative_path
            fixture.assert_predecessor_rows(backup, manifest)
            with closing(sqlite3.connect(backup)) as db:
                self.assertEqual(27, db.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual(manifest["schemaSha256"], storage._schema_fingerprint(db))
            with closing(storage.open_canonical_database(database, expected_project_id=manifest["projectId"])) as db:
                self.assertEqual(29, db.execute("PRAGMA user_version").fetchone()[0])
                self.assertTrue(storage.database_integrity_report(db, expected_project_id=manifest["projectId"]).ok)
                for table in migration.TABLES:
                    self.assertEqual(0, db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            self.assertEqual(
                "current", runner.migrate_database(database, expected_project_id=manifest["projectId"]).status
            )
        finally:
            fixture.doCleanups()

    def test_each_material_step_rolls_back_exact_v27_and_retry_preserves_rows(self):
        for step in migration.MATERIAL_MIGRATION_STEPS:
            with self.subTest(step=step):
                fixture = self.fixture()
                try:
                    manifest, project, database = fixture.load("v27-populated-predecessor")
                    with closing(sqlite3.connect(database)) as db:
                        metadata = db.execute("SELECT * FROM schema_metadata").fetchall()
                        history = db.execute("SELECT * FROM schema_migrations ORDER BY migration_id").fetchall()

                    def interrupt(completed, step=step):
                        if completed == step:
                            raise RuntimeError("synthetic-reference-migration-interruption")

                    with (
                        patch.object(migration, "_migration_step_completed", side_effect=interrupt),
                        self.assertRaises(runner.MigrationProblem) as failure,
                    ):
                        runner.migrate_database(database, expected_project_id=manifest["projectId"])
                    self.assertEqual("migration-execution-failed", failure.exception.code)
                    fixture.assert_predecessor_rows(database, manifest)
                    fixture.assert_ciphertext(project, manifest)
                    with closing(sqlite3.connect(database)) as db:
                        self.assertEqual(27, db.execute("PRAGMA user_version").fetchone()[0])
                        self.assertEqual(manifest["schemaSha256"], storage._schema_fingerprint(db))
                        self.assertEqual(metadata, db.execute("SELECT * FROM schema_metadata").fetchall())
                        self.assertEqual(
                            history, db.execute("SELECT * FROM schema_migrations ORDER BY migration_id").fetchall()
                        )
                    self.assertEqual(
                        "migrated", runner.migrate_database(database, expected_project_id=manifest["projectId"]).status
                    )
                    fixture.assert_predecessor_rows(database, manifest)
                    fixture.assert_ciphertext(project, manifest)
                finally:
                    fixture.doCleanups()


if __name__ == "__main__":
    unittest.main(verbosity=2)
