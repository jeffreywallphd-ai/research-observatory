"""Populated v15 candidate, identity and unfinished impact history survives v16."""

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]
from research_observatory_core import storage
from research_observatory_core.migrations import runner
from research_observatory_core.reconciliation.contracts import SourceAssertion
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
from research_observatory_core.repositories import sqlite_dependency_impact_repository

from tests.data import test_sqlite_migrations as fixtures
from tests.reconciliation import test_migration as protected_fixture
from tests.reconciliation.version_predecessor import SCHEMA_SHA, restore_v15


class VersionMigrationTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.SqliteMigrationTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.database = fixture.database
        self.before = restore_v15(self.database)
        self.project = self.before["projectId"]

    def test_literal_predecessor_contains_real_candidate_review_and_pending_history(self):
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(SCHEMA_SHA, storage._schema_fingerprint(db))
            self.assertEqual(70, db.execute("SELECT COUNT(*) FROM sqlite_schema WHERE type='table'").fetchone()[0])
            self.assertEqual(2, db.execute("SELECT COUNT(*) FROM reconciliation_review_decisions").fetchone()[0])
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM reconciliation_candidate_pairs").fetchone()[0])
            self.assertGreater(db.execute("SELECT COUNT(*) FROM reconciliation_exact_impacts").fetchone()[0], 0)
            self.assertEqual(102, len(self.before["dependentRevisionIds"]))
            self.assertEqual("ok", db.execute("PRAGMA quick_check").fetchone()[0])

    def test_migration_preserves_every_prior_row_and_backup_then_resumes_pending_impacts(self):
        plan = runner.plan_database_migration(self.database, expected_project_id=self.project)
        self.assertEqual(("0016_work_versions",), plan.migration_ids)
        result = runner.migrate_database(self.database, expected_project_id=self.project)
        self.assertEqual("migrated", result.status)
        assert result.backup_relative_path is not None
        with closing(sqlite3.connect(self.database.parent.parent / result.backup_relative_path)) as backup:
            self.assertEqual(SCHEMA_SHA, storage._schema_fingerprint(backup))
            for table, rows in self.before["tables"].items():
                self.assertEqual(rows, [list(row) for row in backup.execute('SELECT * FROM "' + table + '"')], table)
        for _ in range(2):
            with storage.open_canonical_database(self.database, expected_project_id=self.project) as db:
                self.assertEqual(16, db.execute("PRAGMA user_version").fetchone()[0])
                for table, rows in self.before["tables"].items():
                    if table not in {"schema_metadata", "schema_migrations"}:
                        self.assertEqual(
                            rows, [list(row) for row in db.execute('SELECT * FROM "' + table + '"')], table
                        )
                self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
                self.assertEqual("ok", db.execute("PRAGMA quick_check").fetchone()[0])
                sources = tuple(
                    SourceAssertion.model_validate_json(row[0])
                    for row in db.execute("SELECT assertion_json FROM reconciliation_assertions")
                )
        indexed = {source.address.model_dump_json(): source for source in sources}
        repository = SqliteReconciliationRepository(self.database, self.project)
        candidate = repository.candidate_set(
            self.before["candidateRevisionId"], resolve=lambda address: indexed[address.model_dump_json()]
        )
        self.assertEqual(2, len(candidate.members))
        for _ in range(10):
            if not repository.advance_review_impacts():
                break
        self.assertFalse(repository.advance_review_impacts())
        impacts = sqlite_dependency_impact_repository(self.database.parent.parent, self.project)
        self.assertTrue(
            set(self.before["dependentRevisionIds"]) <= {item.output_revision_id for item in impacts.stale_states()}
        )

    def test_each_interruption_restores_exact_predecessor_and_allows_retry(self):
        from research_observatory_core.migrations.versions import v0016_work_versions as migration

        for step in migration.MATERIAL_MIGRATION_STEPS:
            with self.subTest(step=step):
                database = self.database.parents[2] / step / "state/project.sqlite3"
                before = restore_v15(database)

                def fail(observed, expected=step):
                    if observed == expected:
                        raise ValueError("synthetic-version-migration-interruption")

                with (
                    patch.object(migration, "_migration_step_completed", side_effect=fail) as injected,
                    self.assertRaises(runner.MigrationProblem),
                ):
                    runner.migrate_database(database, expected_project_id=self.project)
                injected.assert_any_call(step)
                with closing(sqlite3.connect(database)) as db:
                    self.assertEqual(SCHEMA_SHA, storage._schema_fingerprint(db))
                    self.assertEqual(15, db.execute("PRAGMA user_version").fetchone()[0])
                    for table, rows in before["tables"].items():
                        self.assertEqual(
                            rows, [list(row) for row in db.execute('SELECT * FROM "' + table + '"')], table
                        )
                self.assertEqual("migrated", runner.migrate_database(database, expected_project_id=self.project).status)


class ProtectedVersionMigrationTests(unittest.TestCase):
    def test_encrypted_v15_failure_backup_retry_and_reopen_preserves_every_row(self):
        from research_observatory_core.migrations.versions import v0016_work_versions as migration

        fixture = protected_fixture.ProtectedReconciliationMigrationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        legacy = fixture.root / "legacy/state/project.sqlite3"
        before = restore_v15(legacy)
        identity = before["projectId"]
        with fixture.keys.active_key(identity, create=True) as lease:
            material = lease.use(bytes)
        with closing(sqlcipher.connect(legacy.as_uri() + "?mode=ro", uri=True, isolation_level=None)) as source:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(fixture.database), f"x'{material.hex()}'"))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={storage.APPLICATION_ID}")
            source.execute("PRAGMA protected.user_version=15")
            self.assertEqual("wal", source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0])
            source.execute("DETACH DATABASE protected")

        def fail(step):
            if step == "user-version-advance":
                raise ValueError("synthetic-encrypted-version-interruption")

        with (
            patch.object(migration, "_migration_step_completed", side_effect=fail) as injected,
            self.assertRaises(runner.MigrationProblem),
        ):
            runner.migrate_database(fixture.database, expected_project_id=identity)
        injected.assert_any_call("user-version-advance")
        self.assertEqual(
            15, runner.plan_database_migration(fixture.database, expected_project_id=identity).source_schema_version
        )
        result = runner.migrate_database(fixture.database, expected_project_id=identity)
        backup = fixture.root / str(result.backup_relative_path)
        for path in (fixture.database, backup):
            self.assertNotEqual(b"SQLite format 3\x00", path.read_bytes()[:16])
        with closing(sqlcipher.connect(backup.as_uri() + "?mode=ro", uri=True, isolation_level=None)) as saved:
            saved.execute(f"PRAGMA key=\"x'{material.hex()}'\"")
            self.assertEqual(SCHEMA_SHA, storage._schema_fingerprint(saved))
            self.assertEqual([], saved.execute("PRAGMA cipher_integrity_check").fetchall())
            for table, rows in before["tables"].items():
                self.assertEqual(rows, [list(row) for row in saved.execute('SELECT * FROM "' + table + '"')], table)
        for _ in range(2):
            with storage.open_canonical_database(fixture.database, expected_project_id=identity) as db:
                self.assertEqual(16, db.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
                self.assertEqual("ok", db.execute("PRAGMA quick_check").fetchone()[0])
                for table, rows in before["tables"].items():
                    if table not in {"schema_metadata", "schema_migrations"}:
                        self.assertEqual(
                            rows, [list(row) for row in db.execute('SELECT * FROM "' + table + '"')], table
                        )
