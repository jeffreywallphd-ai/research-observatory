"""Actual protected v29 predecessor and additive SearchRun migration safety."""

import hashlib
import json
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

from tests.search import test_index_migration as fixtures  # noqa: E402

PREDECESSOR = ROOT / "tests/fixtures/search/v29-populated-predecessor"


class SearchRunMigrationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.IndexMigrationTests(methodName="runTest")
        with patch.object(fixtures, "FIXTURE", PREDECESSOR):
            self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_literal_v29_plans_only_the_additive_search_run_step(self):
        self.f.assert_preserved()
        plan = runner.plan_database_migration(self.f.database, expected_project_id=self.f.project)
        self.assertEqual(29, plan.source_schema_version)
        self.assertEqual(30, plan.target_schema_version)
        self.assertEqual(("0030_lexical_search_runs",), plan.migration_ids)

    def test_backup_and_migrated_database_preserve_every_old_cell_object_and_history(self):
        result = runner.migrate_database(self.f.database, expected_project_id=self.f.project)
        self.assertEqual("migrated", result.status)
        self.f.assert_preserved()
        self.assertIsNotNone(result.backup_relative_path)
        assert result.backup_relative_path is not None
        backup = self.f.root / result.backup_relative_path
        self.f.assert_preserved(backup)
        self.assertNotEqual(b"SQLite format 3\0", backup.read_bytes()[:16])
        self.assertIsNotNone(result.recovery_manifest_relative_path)
        assert result.recovery_manifest_relative_path is not None
        recovery = json.loads((self.f.root / result.recovery_manifest_relative_path).read_text())
        contract = json.loads((ROOT / "packages/contracts/storage/sqlite-migration-recovery.schema.json").read_text())
        validator = Draft202012Validator(contract, format_checker=FormatChecker())
        self.assertEqual([], list(validator.iter_errors(recovery)))
        wrong_chain = {**recovery, "migrationIds": ["0029_lexical_index_generations"]}
        self.assertTrue(list(validator.iter_errors(wrong_chain)))
        with closing(self.f.raw(backup)) as db:
            self.assertEqual(29, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(self.f.manifest["schemaSha256"], storage._schema_fingerprint(db))
        with closing(storage.open_canonical_database(self.f.database, expected_project_id=self.f.project)) as db:
            self.assertEqual(30, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertTrue(storage.database_integrity_report(db, expected_project_id=self.f.project).ok)
            for table in (
                "search_lexical_jobs",
                "search_input_manifests",
                "search_lexical_runs",
                "search_observation_events",
            ):
                self.assertEqual(0, db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        old_archive = ROOT / self.f.manifest["sourceFixture"]
        self.assertEqual(self.f.manifest["sourceFixtureSha256"], hashlib.sha256(old_archive.read_bytes()).hexdigest())

    def test_each_material_interruption_rolls_back_exact_v29_and_retries(self):
        from research_observatory_core.migrations.versions import v0030_lexical_search_runs as migration

        for step in migration.MATERIAL_MIGRATION_STEPS:
            with self.subTest(step=step):
                observed: list[str] = []

                def interrupt(completed, target=step, observed=observed):
                    if completed == target:
                        observed.append(completed)
                        raise RuntimeError("synthetic SearchRun migration interruption")

                with (
                    patch.object(migration, "_migration_step_completed", side_effect=interrupt),
                    self.assertRaises(runner.MigrationProblem) as failure,
                ):
                    runner.migrate_database(self.f.database, expected_project_id=self.f.project)
                self.assertEqual([step], observed)
                self.assertEqual("migration-execution-failed", failure.exception.code)
                self.f.assert_preserved()
                with closing(self.f.raw()) as db:
                    self.assertEqual(29, db.execute("PRAGMA user_version").fetchone()[0])
                    self.assertEqual(self.f.manifest["schemaSha256"], storage._schema_fingerprint(db))
        self.assertEqual(
            "migrated", runner.migrate_database(self.f.database, expected_project_id=self.f.project).status
        )
        self.f.assert_preserved()


if __name__ == "__main__":
    unittest.main()
