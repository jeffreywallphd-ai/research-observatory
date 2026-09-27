"""Actual populated v14 history survives complete-membership migration and interruption."""

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]
from research_observatory_core import storage
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.migrations import runner
from research_observatory_core.ports.reconciliation import ReconciliationActor
from research_observatory_core.reconciliation.contracts import SourceAssertion
from research_observatory_core.reconciliation.decisions import ReviewCommand, ReviewPlan, SourcePartition, WorkState
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository

from tests.data import test_sqlite_migrations as migration_fixture
from tests.reconciliation import test_migration as protected_fixture
from tests.reconciliation.predecessor import SCHEMA_SHA, restore_v14


class ReviewMigrationTests(unittest.TestCase):
    def setUp(self):
        fixture = migration_fixture.SqliteMigrationTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.database = fixture.database
        self.before = restore_v14(self.database)
        self.identity = self.before["projectId"]

    def test_populated_history_membership_order_unassigned_and_backup(self):
        plan = runner.plan_database_migration(self.database, expected_project_id=self.identity)
        self.assertEqual(
            (
                "0015_reconciliation_review",
                "0016_work_versions",
            ),
            plan.migration_ids,
        )
        result = runner.migrate_database(self.database, expected_project_id=self.identity)
        self.assertEqual("migrated", result.status)
        assert result.backup_relative_path is not None
        with closing(sqlite3.connect(self.database.parent.parent / result.backup_relative_path)) as backup:
            self.assertEqual(SCHEMA_SHA, storage._schema_fingerprint(backup))
            self.assertEqual(14, backup.execute("PRAGMA user_version").fetchone()[0])
        for _ in range(2):
            with storage.open_canonical_database(self.database, expected_project_id=self.identity) as db:
                self.assertEqual(16, db.execute("PRAGMA user_version").fetchone()[0])
                for table, rows in self.before["tables"].items():
                    if table not in {"schema_metadata", "schema_migrations"}:
                        self.assertEqual(
                            rows, [list(row) for row in db.execute('SELECT * FROM "' + table + '"')], table
                        )
                expected: dict[str, list[str]] = {}
                prior: dict[str, str] = {}
                rows = db.execute(
                    "SELECT w.revision_id,w.work_id,w.assertion_revision_id,w.previous_revision_id "
                    "FROM reconciliation_work_revisions w JOIN aggregate_revisions r USING (revision_id) "
                    "ORDER BY w.work_id,r.revision"
                ).fetchall()
                self.assertEqual(3, len(rows))
                for revision, work, assertion, predecessor in rows:
                    self.assertEqual(prior.get(work), predecessor)
                    expected.setdefault(work, []).append(assertion)
                    members = tuple(sorted(expected[work]))
                    self.assertEqual(
                        members,
                        tuple(
                            row[0]
                            for row in db.execute(
                                "SELECT assertion_revision_id FROM reconciliation_work_members "
                                "WHERE work_revision_id=? ORDER BY ordinal",
                                (revision,),
                            )
                        ),
                    )
                    state = WorkState(
                        work_id=work,
                        revision_id=revision,
                        previous_revision_id=predecessor,
                        disposition="active",
                        alias_target=None,
                        assertion_revision_ids=members,
                        decision_revision_id=None,
                    )
                    self.assertEqual(
                        (len(members), state.fingerprint),
                        tuple(
                            db.execute(
                                "SELECT member_count,state_sha256 FROM reconciliation_work_seals "
                                "WHERE work_revision_id=?",
                                (revision,),
                            ).fetchone()
                        ),
                    )
                    prior[work] = revision
                unassigned = [
                    row[0]
                    for row in db.execute(
                        "SELECT revision_id FROM reconciliation_assertions "
                        "WHERE json_extract(result_json,'$.workId') IS NULL"
                    )
                ]
                self.assertEqual(1, len(unassigned))
                self.assertEqual(
                    0,
                    db.execute(
                        "SELECT COUNT(*) FROM reconciliation_work_members WHERE assertion_revision_id=?",
                        (unassigned[0],),
                    ).fetchone()[0],
                )
                self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
                self.assertEqual("ok", db.execute("PRAGMA quick_check").fetchone()[0])

    def test_each_material_interruption_restores_exact_predecessor_then_retry(self):
        from research_observatory_core.migrations.versions import v0015_reconciliation_review as revision

        for step in revision.MATERIAL_MIGRATION_STEPS:
            with self.subTest(step=step):
                database = self.database.parents[2] / step / "state/project.sqlite3"
                before = restore_v14(database)

                def fail(observed, expected=step):
                    if observed == expected:
                        raise ValueError("synthetic-review-migration-interruption")

                with (
                    patch.object(revision, "_migration_step_completed", side_effect=fail) as injected,
                    self.assertRaises(runner.MigrationProblem),
                ):
                    runner.migrate_database(database, expected_project_id=before["projectId"])
                injected.assert_any_call(step)
                with closing(sqlite3.connect(database)) as db:
                    self.assertEqual(SCHEMA_SHA, storage._schema_fingerprint(db))
                    self.assertEqual(14, db.execute("PRAGMA user_version").fetchone()[0])
                    for table, rows in before["tables"].items():
                        self.assertEqual(rows, [list(row) for row in db.execute('SELECT * FROM "' + table + '"')])
                self.assertEqual(
                    "migrated", runner.migrate_database(database, expected_project_id=before["projectId"]).status
                )

    def test_modified_predecessor_denied_without_publication(self):
        with closing(sqlite3.connect(self.database, autocommit=True)) as db:
            db.execute("DROP TRIGGER reconciliation_work_revisions_no_update")
        with self.assertRaises(runner.MigrationProblem):
            runner.migrate_database(self.database, expected_project_id=self.identity)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(14, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertIsNone(
                db.execute("SELECT name FROM sqlite_schema WHERE name='reconciliation_work_states'").fetchone()
            )

    def test_actual_unassigned_bridge_can_be_assigned_without_rewriting_adverse_receipt(self):
        runner.migrate_database(self.database, expected_project_id=self.identity)
        with storage.open_canonical_database(self.database, expected_project_id=self.identity) as db:
            rows = db.execute("SELECT revision_id,assertion_json,result_json FROM reconciliation_assertions").fetchall()
            work = db.execute("SELECT work_id FROM reconciliation_work_states ORDER BY work_id LIMIT 1").fetchone()[0]
        sources = [SourceAssertion.model_validate_json(row[1]) for row in rows]
        indexed = {source.address.model_dump_json(): source for source in sources}

        def resolve(address):
            return indexed[address.model_dump_json()]

        repo = SqliteReconciliationRepository(self.database, self.identity)
        unassigned = next(row for row in rows if repo.inspect(row[0], resolve=resolve).result.work_id is None)
        context = repo.review_context((work,), unassigned=(unassigned[0],), resolve=resolve)
        plan = ReviewPlan(
            action="assign",
            works=context.works,
            unassigned_assertion_revision_ids=(unassigned[0],),
            partitions=(
                SourcePartition(
                    group="assigned",
                    existing_work_id=work,
                    assertion_revision_ids=tuple(sorted((*context.works[0].assertion_revision_ids, unassigned[0]))),
                ),
            ),
            aliases=(),
            conflict_disposition="retain-all",
            evidence_sha256=context.fingerprint,
            rationale="Synthetic human resolution of disputed bridge",
        )
        actor = ReconciliationActor(new_uuid_v7(), "3" * 32, "2026-09-27T07:00:00.000Z", "4" * 64, "5" * 64)
        preview = repo.preview_review(plan, actor=actor, resolve=resolve)
        command = ReviewCommand(command_id=new_uuid_v7(), plan=plan, expected_preview_sha256=preview.preview_sha256)
        outcome = repo.review(command, actor=actor, resolve=resolve)
        self.assertEqual(outcome, repo.review(command, actor=actor, resolve=resolve))
        inspected = repo.inspect(unassigned[0], resolve=resolve)
        assert inspected.canonical_work is not None
        self.assertEqual(work, inspected.canonical_work.work_id)
        self.assertIsNone(inspected.result.work_id)
        self.assertEqual("review-required", inspected.result.disposition)
        self.assertIn("multiple-work-matches", inspected.result.flags)
        self.assertEqual(unassigned[2], inspected.result.model_dump_json(by_alias=True))


class ProtectedReviewMigrationTests(unittest.TestCase):
    """Actual populated v14 backfill through SQLCipher; keys are an in-memory fixture."""

    def test_populated_encrypted_backfill_rollback_backup_retry_and_reopen(self):
        from research_observatory_core.migrations.versions import v0015_reconciliation_review as revision

        fixture = protected_fixture.ProtectedReconciliationMigrationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        legacy = fixture.root / "legacy/state/project.sqlite3"
        before = restore_v14(legacy)
        identity = before["projectId"]
        with fixture.keys.active_key(identity, create=True) as lease:
            material = lease.use(bytes)
        with closing(sqlcipher.connect(legacy.as_uri() + "?mode=ro", uri=True, isolation_level=None)) as source:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(fixture.database), f"x'{material.hex()}'"))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={storage.APPLICATION_ID}")
            source.execute("PRAGMA protected.user_version=14")
            self.assertEqual("wal", source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0])
            source.execute("DETACH DATABASE protected")

        def fail(step):
            if step == "membership-backfill-complete":
                raise RuntimeError("synthetic-protected-membership-interruption")

        with (
            patch.object(revision, "_migration_step_completed", side_effect=fail) as injected,
            self.assertRaises(runner.MigrationProblem),
        ):
            runner.migrate_database(fixture.database, expected_project_id=identity)
        injected.assert_any_call("membership-backfill-complete")
        self.assertEqual(
            14, runner.plan_database_migration(fixture.database, expected_project_id=identity).source_schema_version
        )
        result = runner.migrate_database(fixture.database, expected_project_id=identity)
        self.assertEqual("migrated", result.status)
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
            with storage.open_canonical_database(fixture.database, expected_project_id=identity) as current:
                self.assertEqual(16, current.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual([], current.execute("PRAGMA foreign_key_check").fetchall())
                self.assertEqual("ok", current.execute("PRAGMA quick_check").fetchone()[0])
                self.assertEqual(3, current.execute("SELECT COUNT(*) FROM reconciliation_work_states").fetchone()[0])
                self.assertEqual(4, current.execute("SELECT COUNT(*) FROM reconciliation_work_members").fetchone()[0])
                for table, rows in before["tables"].items():
                    if table not in {"schema_metadata", "schema_migrations"}:
                        self.assertEqual(
                            rows, [list(row) for row in current.execute('SELECT * FROM "' + table + '"')], table
                        )
