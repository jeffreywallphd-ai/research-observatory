"""v17 migration proof against the literal populated v16 database authority."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid7

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator, FormatChecker
from research_observatory_core import storage
from research_observatory_core.migrations import runner
from research_observatory_core.migrations.versions import v0017_corpus_items

from tests.data import test_sqlite_migrations as migration_fixture
from tests.reconciliation import test_migration as protected_fixture
from tests.reconciliation.v16_predecessor import (
    POPULATED_COUNTS,
    PROJECT_ID,
    SCHEMA_SHA256,
    inspect_v16,
    restore_v16,
)

_TIME = "2026-09-30T00:00:00.000Z"


def _id() -> str:
    return str(uuid7())


def _common_revision(db: sqlite3.Connection, kind: str, item: str, revision: str, number: int) -> None:
    if number == 0:
        db.execute(
            "INSERT INTO aggregate_identities (aggregate_id,project_id,aggregate_kind,created_at) VALUES (?,?,?,?)",
            (item, PROJECT_ID, kind, _TIME),
        )
    db.execute(
        "INSERT INTO aggregate_revisions (revision_id,aggregate_id,aggregate_kind,project_id,revision,"
        "contract_version,created_at,modified_at,display_label_observed,knowledge_status,rights_status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            revision,
            item,
            kind,
            PROJECT_ID,
            number,
            "2.0.0" if kind == "corpus-item" else "1.0.0",
            _TIME,
            _TIME,
            "test item",
            "observed",
            "unknown",
        ),
    )
    if kind == "corpus-item":
        db.execute("INSERT INTO corpus_items (revision_id) VALUES (?)", (revision,))


def _initial_corpus_state(db: sqlite3.Connection) -> tuple[str, str, str, str, str]:
    work_id, work_revision_id, item_id, item_revision_id, path_id = (_id() for _ in range(5))
    _common_revision(db, "record", work_id, work_revision_id, 0)
    _common_revision(db, "corpus-item", item_id, item_revision_id, 0)
    db.execute(
        "INSERT INTO corpus_discovery_paths (path_id,project_id,item_id,direction,occurred_at,"
        "predecessor_item_revision_id,kind,source_revision_id,context_id,context_revision_id,"
        "manual_decision_revision_id) "
        "VALUES (?,?,?,'source-to-corpus-item',?,NULL,'manual',?,?,?,?)",
        (path_id, PROJECT_ID, item_id, _TIME, _id(), _id(), _id(), _id()),
    )
    fingerprint = hashlib.sha256(json.dumps((path_id,), separators=(",", ":")).encode()).hexdigest()
    db.execute(
        "INSERT INTO corpus_item_states (revision_id,project_id,item_id,previous_revision_id,work_id,"
        "work_revision_id,membership,review,availability,primary_discovery_path_id,discovery_fingerprint) "
        "VALUES (?,?,?,NULL,?,?,'candidate','pending','unknown',?,?)",
        (item_revision_id, PROJECT_ID, item_id, work_id, work_revision_id, path_id, fingerprint),
    )
    db.execute(
        "INSERT INTO corpus_item_discovery_paths (revision_id,project_id,item_id,path_id) VALUES (?,?,?,?)",
        (item_revision_id, PROJECT_ID, item_id, path_id),
    )
    return work_id, work_revision_id, item_id, item_revision_id, path_id


class CorpusMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = migration_fixture.SqliteMigrationTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.fixture = fixture
        self.database = fixture.database
        restore_v16(self.database)

    def test_populated_v16_backup_rows_and_reopen_survive_common_table_rebuild(self) -> None:
        plan = runner.plan_database_migration(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual((v0017_corpus_items.revision,), plan.migration_ids)
        self.assertEqual(SCHEMA_SHA256, plan.source_schema_sha256)
        result = runner.migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual((v0017_corpus_items.revision,), result.migration_ids)
        assert result.backup_relative_path is not None
        assert result.recovery_manifest_relative_path is not None
        backup = self.database.parent.parent / result.backup_relative_path
        self.assertEqual(POPULATED_COUNTS, inspect_v16(backup)["counts"])
        manifest_path = self.database.parent.parent / result.recovery_manifest_relative_path
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema_path = (
            Path(__file__).resolve().parents[2] / "packages/contracts/storage/sqlite-migration-recovery.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertEqual([], list(validator.iter_errors(manifest)))
        self.assertEqual([v0017_corpus_items.revision], manifest["migrationIds"])
        self.assertEqual(storage.EXPECTED_SCHEMA_SHA256, manifest["targetSchemaSha256"])
        self.assertTrue(list(validator.iter_errors(manifest | {"migrationIds": []})))
        self.assertTrue(
            list(validator.iter_errors(manifest | {"targetSchemaSha256": storage.WORK_VERSION_SCHEMA_SHA256}))
        )
        with closing(sqlite3.connect(backup)) as prior, closing(sqlite3.connect(self.database)) as current:
            for (table,) in prior.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ):
                if table in {"schema_metadata", "schema_migrations"}:
                    continue
                self.assertEqual(
                    prior.execute(f'SELECT * FROM "{table}"').fetchall(),
                    current.execute(f'SELECT * FROM "{table}"').fetchall(),
                    table,
                )
            self.assertIsNone(current.execute("PRAGMA foreign_key_check").fetchone())
            self.assertEqual(("ok",), current.execute("PRAGMA quick_check").fetchone())
            self.assertEqual(5, current.execute("SELECT COUNT(*) FROM dependency_impact_items").fetchone()[0])
        # Isolate the widened CHECK without manufacturing an impact-run history:
        # the probe is rollback-only, with FK checks suspended on this test handle.
        with closing(sqlite3.connect(self.database, isolation_level=None)) as probe:
            probe.execute("PRAGMA foreign_keys=OFF")
            probe.execute("BEGIN IMMEDIATE")
            impact_sql = (
                "INSERT INTO dependency_impact_items (item_id,run_id,item_sequence,project_id,"
                "output_revision_id,output_kind,disposition,depth,relation_type,path_json,path_sha256,"
                "path_length,path_truncated,confidence,review_required,created_at) "
                "VALUES (?,?,?,?,? ,?,'stale',1,'direct',? ,?,1,0,'confirmed',0,?)"
            )
            probe.execute(
                impact_sql,
                (_id(), _id(), 1, PROJECT_ID, _id(), "corpus-item", json.dumps([_id()]), "sha256:" + "a" * 64, _TIME),
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "output_kind IN"):
                probe.execute(
                    impact_sql,
                    (
                        _id(),
                        _id(),
                        1,
                        PROJECT_ID,
                        _id(),
                        "unrelated-kind",
                        json.dumps([_id()]),
                        "sha256:" + "b" * 64,
                        _TIME,
                    ),
                )
            probe.execute("ROLLBACK")
        for _ in range(2):
            with closing(storage.open_canonical_database(self.database, expected_project_id=PROJECT_ID)) as current:
                report = storage.database_integrity_report(current, expected_project_id=PROJECT_ID)
                self.assertTrue(report.ok, report.errors)
                self.assertEqual(17, report.schema_version)
                self.assertEqual(1, current.execute("PRAGMA foreign_keys").fetchone()[0])
                self.assertEqual(
                    "1.0.0",
                    current.execute(
                        "SELECT contract_version FROM aggregate_revisions ORDER BY revision_id LIMIT 1"
                    ).fetchone()[0],
                )

    def test_material_failpoints_preserve_exact_v16_and_verified_recovery(self) -> None:
        for step in (
            "common-v16-drop",
            "common-v17-copy",
            "impact-v16-drop",
            "impact-v17-copy",
            "corpus-authority-create",
            "metadata-v17-copy",
            "user-version-advance",
        ):
            with self.subTest(step=step):
                database = self.fixture.project / step / "state" / "project.sqlite3"
                restore_v16(database)

                def fail(observed: str, expected: str = step) -> None:
                    if observed == expected:
                        raise ValueError("synthetic-corpus-migration-interruption")

                with (
                    patch.object(v0017_corpus_items, "_migration_step_completed", side_effect=fail) as injected,
                    self.assertRaises(runner.MigrationProblem) as raised,
                ):
                    runner.migrate_database(database, expected_project_id=PROJECT_ID)
                injected.assert_any_call(step)
                self.assertEqual(POPULATED_COUNTS, inspect_v16(database)["counts"])
                assert raised.exception.recovery_manifest_relative_path is not None
                self.assertTrue((database.parent.parent / raised.exception.recovery_manifest_relative_path).is_file())
                self.assertEqual("migrated", runner.migrate_database(database, expected_project_id=PROJECT_ID).status)
                with closing(storage.open_canonical_database(database, expected_project_id=PROJECT_ID)) as reopened:
                    self.assertTrue(storage.database_integrity_report(reopened, expected_project_id=PROJECT_ID).ok)

    def test_fresh_v17_has_corpus_tables_and_exact_profile(self) -> None:
        database = self.fixture.project / "fresh" / "state" / "project.sqlite3"
        database.parent.mkdir(parents=True)
        report = storage.initialize_database(
            database, project_id=PROJECT_ID, project_created_at="2026-09-30T00:00:00.000Z"
        )
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(17, report.schema_version)
        self.assertEqual(set(storage.EXPECTED_TABLES), set(report.strict_tables))
        with closing(storage.open_canonical_database(database, expected_project_id=PROJECT_ID)) as reopened:
            self.assertEqual(storage.EXPECTED_SCHEMA_SHA256, storage._schema_fingerprint(reopened))

    def test_initial_state_check_rejects_forged_review_duplicate_and_availability(self) -> None:
        database = self.fixture.project / "initial-state" / "state" / "project.sqlite3"
        database.parent.mkdir(parents=True)
        storage.initialize_database(database, project_id=PROJECT_ID, project_created_at=_TIME)
        with closing(sqlite3.connect(database, isolation_level=None)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            work_id, work_revision_id, item_id, item_revision_id, path_id, other_item_id = (_id() for _ in range(6))
            _common_revision(db, "record", work_id, work_revision_id, 0)
            _common_revision(db, "corpus-item", item_id, item_revision_id, 0)
            db.execute(
                "INSERT INTO aggregate_identities (aggregate_id,project_id,aggregate_kind,created_at) "
                "VALUES (?,?,'corpus-item',?)",
                (other_item_id, PROJECT_ID, _TIME),
            )
            db.execute(
                "INSERT INTO corpus_discovery_paths (path_id,project_id,item_id,direction,occurred_at,"
                "predecessor_item_revision_id,kind,source_revision_id,context_id,context_revision_id,"
                "manual_decision_revision_id) "
                "VALUES (?,?,?,'source-to-corpus-item',?,NULL,'manual',?,?,?,?)",
                (path_id, PROJECT_ID, item_id, _TIME, _id(), _id(), _id(), _id()),
            )
            fingerprint = hashlib.sha256(json.dumps((path_id,), separators=(",", ":")).encode()).hexdigest()
            sql = (
                "INSERT INTO corpus_item_states (revision_id,project_id,item_id,work_id,work_revision_id,"
                "membership,review,duplicate_of_item_id,availability,primary_discovery_path_id,"
                "discovery_fingerprint) VALUES (?,?,?,?,?,'candidate',?,?,?,?,?)"
            )
            for review, duplicate, availability in (
                ("none", None, "unknown"),
                ("pending", other_item_id, "unknown"),
                ("pending", None, "available"),
            ):
                with (
                    self.subTest(review=review, duplicate=duplicate, availability=availability),
                    self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK constraint failed"),
                ):
                    db.execute(
                        sql,
                        (
                            item_revision_id,
                            PROJECT_ID,
                            item_id,
                            work_id,
                            work_revision_id,
                            review,
                            duplicate,
                            availability,
                            path_id,
                            fingerprint,
                        ),
                    )
            db.execute(
                sql,
                (
                    item_revision_id,
                    PROJECT_ID,
                    item_id,
                    work_id,
                    work_revision_id,
                    "pending",
                    None,
                    "unknown",
                    path_id,
                    fingerprint,
                ),
            )
            db.execute(
                "INSERT INTO corpus_item_discovery_paths (revision_id,project_id,item_id,path_id) VALUES (?,?,?,?)",
                (item_revision_id, PROJECT_ID, item_id, path_id),
            )
            db.execute("COMMIT")

    def test_corpus_marker_and_partial_decision_cannot_commit(self) -> None:
        database = self.fixture.project / "partial" / "state" / "project.sqlite3"
        database.parent.mkdir(parents=True)
        storage.initialize_database(database, project_id=PROJECT_ID, project_created_at=_TIME)
        with closing(sqlite3.connect(database, isolation_level=None)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            _common_revision(db, "corpus-item", _id(), _id(), 0)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("COMMIT")  # Marker requires a matching full state.
            db.execute("ROLLBACK")

            db.execute("BEGIN IMMEDIATE")
            work_id, work_revision_id, item_id, prior_revision, path_id = _initial_corpus_state(db)
            db.execute("COMMIT")
            db.execute("BEGIN IMMEDIATE")
            next_revision, decision_id = _id(), _id()
            _common_revision(db, "corpus-item", item_id, next_revision, 1)
            fingerprint = hashlib.sha256(json.dumps((path_id,), separators=(",", ":")).encode()).hexdigest()
            db.execute(
                "INSERT INTO corpus_item_states (revision_id,project_id,item_id,previous_revision_id,work_id,"
                "work_revision_id,membership,review,availability,primary_discovery_path_id,"
                "discovery_fingerprint,decision_revision_id) "
                "VALUES (?,?,?,?,?,?,'included','pending','unknown',?,?,?)",
                (
                    next_revision,
                    PROJECT_ID,
                    item_id,
                    prior_revision,
                    work_id,
                    work_revision_id,
                    path_id,
                    fingerprint,
                    decision_id,
                ),
            )
            db.execute(
                "INSERT INTO corpus_item_discovery_paths (revision_id,project_id,item_id,path_id) VALUES (?,?,?,?)",
                (next_revision, PROJECT_ID, item_id, path_id),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("COMMIT")  # Noninitial state requires its decision row.
            db.execute("ROLLBACK")

    def test_discovery_path_requires_direction_time_and_exact_current_predecessor(self) -> None:
        database = self.fixture.project / "path-predecessor" / "state" / "project.sqlite3"
        database.parent.mkdir(parents=True)
        storage.initialize_database(database, project_id=PROJECT_ID, project_created_at=_TIME)
        with closing(sqlite3.connect(database, isolation_level=None)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            work_id, work_revision_id, item_id, prior_revision, path_id = _initial_corpus_state(db)
            db.execute("COMMIT")
            db.execute("BEGIN IMMEDIATE")
            current_revision, decision_id = _id(), _id()
            _common_revision(db, "corpus-item", item_id, current_revision, 1)
            fingerprint = hashlib.sha256(json.dumps((path_id,), separators=(",", ":")).encode()).hexdigest()
            db.execute(
                "INSERT INTO corpus_item_states (revision_id,project_id,item_id,previous_revision_id,work_id,"
                "work_revision_id,membership,review,availability,primary_discovery_path_id,"
                "discovery_fingerprint,decision_revision_id) "
                "VALUES (?,?,?,?,?,?,'included','pending','unknown',?,?,?)",
                (
                    current_revision,
                    PROJECT_ID,
                    item_id,
                    prior_revision,
                    work_id,
                    work_revision_id,
                    path_id,
                    fingerprint,
                    decision_id,
                ),
            )
            db.execute(
                "INSERT INTO corpus_item_discovery_paths (revision_id,project_id,item_id,path_id) VALUES (?,?,?,?)",
                (current_revision, PROJECT_ID, item_id, path_id),
            )
            db.execute(
                "INSERT INTO corpus_decisions (decision_id,project_id,item_id,previous_revision_id,"
                "next_revision_id,dimension,command,previous_value,next_value,actor_id,reason_code,"
                "protocol_revision_id,occurred_at) "
                "VALUES (?,?,?,? ,?,'membership','include','candidate','included',?,'screened',?,?)",
                (decision_id, PROJECT_ID, item_id, prior_revision, current_revision, _id(), _id(), _TIME),
            )
            db.execute("COMMIT")
            sql = (
                "INSERT INTO corpus_discovery_paths (path_id,project_id,item_id,direction,occurred_at,"
                "predecessor_item_revision_id,kind,source_revision_id,context_id,context_revision_id,"
                "manual_decision_revision_id) VALUES (?,?,?,?,?,?,'manual',?,?,?,?)"
            )

            def values(direction: str, occurred_at: str, predecessor: str | None) -> tuple[str | None, ...]:
                return (_id(), PROJECT_ID, item_id, direction, occurred_at, predecessor, _id(), _id(), _id(), _id())

            db.execute("BEGIN IMMEDIATE")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "direction"):
                db.execute(sql, values("corpus-item-to-source", _TIME, current_revision))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "occurred_at"):
                db.execute(sql, values("source-to-corpus-item", "2026-09-30T00:00:00Z", current_revision))
            for predecessor in (None, _id(), prior_revision):
                with (
                    self.subTest(predecessor=predecessor),
                    self.assertRaisesRegex(sqlite3.IntegrityError, "corpus discovery predecessor binding denied"),
                ):
                    db.execute(sql, values("source-to-corpus-item", _TIME, predecessor))
            db.execute(sql, values("source-to-corpus-item", _TIME, current_revision))
            db.execute("ROLLBACK")

    def test_false_prior_state_value_is_denied_by_decision_trigger(self) -> None:
        database = self.fixture.project / "decision-binding" / "state" / "project.sqlite3"
        database.parent.mkdir(parents=True)
        storage.initialize_database(database, project_id=PROJECT_ID, project_created_at=_TIME)
        with closing(sqlite3.connect(database, isolation_level=None)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            work_id, work_revision_id, item_id, prior_revision, path_id = _initial_corpus_state(db)
            db.execute("COMMIT")
            db.execute("BEGIN IMMEDIATE")
            next_revision, decision_id = _id(), _id()
            _common_revision(db, "corpus-item", item_id, next_revision, 1)
            fingerprint = hashlib.sha256(json.dumps((path_id,), separators=(",", ":")).encode()).hexdigest()
            db.execute(
                "INSERT INTO corpus_item_states (revision_id,project_id,item_id,previous_revision_id,work_id,"
                "work_revision_id,membership,review,availability,primary_discovery_path_id,"
                "discovery_fingerprint,decision_revision_id) "
                "VALUES (?,?,?,?,?,?,'included','pending','unknown',?,?,?)",
                (
                    next_revision,
                    PROJECT_ID,
                    item_id,
                    prior_revision,
                    work_id,
                    work_revision_id,
                    path_id,
                    fingerprint,
                    decision_id,
                ),
            )
            db.execute(
                "INSERT INTO corpus_item_discovery_paths (revision_id,project_id,item_id,path_id) VALUES (?,?,?,?)",
                (next_revision, PROJECT_ID, item_id, path_id),
            )
            sql = (
                "INSERT INTO corpus_decisions (decision_id,project_id,item_id,previous_revision_id,"
                "next_revision_id,dimension,command,previous_value,next_value,actor_id,reason_code,"
                "protocol_revision_id,occurred_at) "
                "VALUES (?,?,?,? ,?,'membership','include',?,'included',?,'screened',?,?)"
            )
            values = (decision_id, PROJECT_ID, item_id, prior_revision, next_revision)
            tail = (_id(), _id(), _TIME)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "corpus decision chain binding denied"):
                db.execute(sql, (*values, "excluded", *tail))
            db.execute(sql, (*values, "candidate", *tail))
            db.execute("COMMIT")

    def test_decision_trigger_requires_latest_same_dimension_supersession(self) -> None:
        database = self.fixture.project / "supersession-binding" / "state" / "project.sqlite3"
        database.parent.mkdir(parents=True)
        storage.initialize_database(database, project_id=PROJECT_ID, project_created_at=_TIME)
        with closing(sqlite3.connect(database, isolation_level=None)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            work_id, work_revision_id, item_id, initial_revision, path_id = _initial_corpus_state(db)
            fingerprint = hashlib.sha256(json.dumps((path_id,), separators=(",", ":")).encode()).hexdigest()

            def state(prior: str, number: int, membership: str, availability: str) -> tuple[str, str]:
                revision_id, decision_id = _id(), _id()
                _common_revision(db, "corpus-item", item_id, revision_id, number)
                db.execute(
                    "INSERT INTO corpus_item_states (revision_id,project_id,item_id,previous_revision_id,work_id,"
                    "work_revision_id,membership,review,availability,primary_discovery_path_id,"
                    "discovery_fingerprint,decision_revision_id) VALUES (?,?,?,?,?, ?,?,'pending',?,?,?,?)",
                    (
                        revision_id,
                        PROJECT_ID,
                        item_id,
                        prior,
                        work_id,
                        work_revision_id,
                        membership,
                        availability,
                        path_id,
                        fingerprint,
                        decision_id,
                    ),
                )
                db.execute(
                    "INSERT INTO corpus_item_discovery_paths (revision_id,project_id,item_id,path_id) VALUES (?,?,?,?)",
                    (revision_id, PROJECT_ID, item_id, path_id),
                )
                return revision_id, decision_id

            def decision(
                prior: str,
                next_revision: str,
                decision_id: str,
                previous_decision_id: str | None,
                dimension: str,
                command: str,
                previous_value: str,
                next_value: str,
                supersedes: str | None,
            ) -> None:
                db.execute(
                    "INSERT INTO corpus_decisions (decision_id,project_id,item_id,previous_revision_id,"
                    "next_revision_id,dimension,command,previous_value,next_value,previous_decision_revision_id,"
                    "supersedes_decision_revision_id,actor_id,reason_code,protocol_revision_id,occurred_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        decision_id,
                        PROJECT_ID,
                        item_id,
                        prior,
                        next_revision,
                        dimension,
                        command,
                        previous_value,
                        next_value,
                        previous_decision_id,
                        supersedes,
                        _id(),
                        "synthetic-review",
                        _id(),
                        _TIME,
                    ),
                )

            first_revision, first_decision = state(initial_revision, 1, "included", "unknown")
            decision(
                initial_revision,
                first_revision,
                first_decision,
                None,
                "membership",
                "include",
                "candidate",
                "included",
                None,
            )
            second_revision, second_decision = state(first_revision, 2, "included", "unavailable")
            decision(
                first_revision,
                second_revision,
                second_decision,
                first_decision,
                "availability",
                "mark-unavailable",
                "unknown",
                "unavailable",
                None,
            )
            third_revision, third_decision = state(second_revision, 3, "candidate", "unavailable")
            args = (
                second_revision,
                third_revision,
                third_decision,
                second_decision,
                "membership",
                "reconsider",
                "included",
                "candidate",
            )
            for wrong in (None, second_decision):
                with (
                    self.subTest(supersedes=wrong),
                    self.assertRaisesRegex(sqlite3.IntegrityError, "corpus decision chain binding denied"),
                ):
                    decision(*args, wrong)
            decision(*args, first_decision)
            self.assertEqual(
                first_decision,
                db.execute(
                    "SELECT supersedes_decision_revision_id FROM corpus_decisions WHERE decision_id=?",
                    (third_decision,),
                ).fetchone()[0],
            )
            db.execute("COMMIT")

    def test_work_reference_trigger_denies_unrelated_work_relabeling(self) -> None:
        database = self.fixture.project / "unrelated-work-binding" / "state" / "project.sqlite3"
        database.parent.mkdir(parents=True)
        storage.initialize_database(database, project_id=PROJECT_ID, project_created_at=_TIME)
        with closing(sqlite3.connect(database, isolation_level=None)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            _work_id, work_revision_id, item_id, prior_revision, path_id = _initial_corpus_state(db)
            unrelated_work_id, unrelated_work_revision_id = _id(), _id()
            _common_revision(db, "record", unrelated_work_id, unrelated_work_revision_id, 0)
            next_revision, decision_id = _id(), _id()
            _common_revision(db, "corpus-item", item_id, next_revision, 1)
            fingerprint = hashlib.sha256(json.dumps((path_id,), separators=(",", ":")).encode()).hexdigest()
            db.execute(
                "INSERT INTO corpus_item_states (revision_id,project_id,item_id,previous_revision_id,work_id,"
                "work_revision_id,membership,review,availability,primary_discovery_path_id,"
                "discovery_fingerprint,decision_revision_id) "
                "VALUES (?,?,?,?,?,?,'candidate','pending','unknown',?,?,?)",
                (
                    next_revision,
                    PROJECT_ID,
                    item_id,
                    prior_revision,
                    unrelated_work_id,
                    unrelated_work_revision_id,
                    path_id,
                    fingerprint,
                    decision_id,
                ),
            )
            db.execute(
                "INSERT INTO corpus_item_discovery_paths (revision_id,project_id,item_id,path_id) VALUES (?,?,?,?)",
                (next_revision, PROJECT_ID, item_id, path_id),
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "corpus decision chain binding denied"):
                db.execute(
                    "INSERT INTO corpus_decisions (decision_id,project_id,item_id,previous_revision_id,"
                    "next_revision_id,dimension,command,previous_value,next_value,next_work_id,"
                    "actor_id,reason_code,protocol_revision_id,occurred_at) "
                    "VALUES (?,?,?,? ,?,'work-reference','rebind-work',?,?,?,?,?,?,?)",
                    (
                        decision_id,
                        PROJECT_ID,
                        item_id,
                        prior_revision,
                        next_revision,
                        work_revision_id,
                        unrelated_work_revision_id,
                        unrelated_work_id,
                        _id(),
                        "unrelated-work",
                        _id(),
                        _TIME,
                    ),
                )
            db.execute("ROLLBACK")

    def test_decision_cannot_hide_another_state_change_or_misname_transition(self) -> None:
        database = self.fixture.project / "one-dimension" / "state" / "project.sqlite3"
        database.parent.mkdir(parents=True)
        storage.initialize_database(database, project_id=PROJECT_ID, project_created_at=_TIME)
        with closing(sqlite3.connect(database, isolation_level=None)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            work_id, work_revision_id, item_id, prior_revision, path_id = _initial_corpus_state(db)
            db.execute("COMMIT")
            fingerprint = hashlib.sha256(json.dumps((path_id,), separators=(",", ":")).encode()).hexdigest()
            for hidden_change in ("availability", "review", "work", "discovery-fingerprint", "command"):
                with self.subTest(hidden_change=hidden_change):
                    db.execute("BEGIN IMMEDIATE")
                    next_work_id, next_work_revision_id = work_id, work_revision_id
                    if hidden_change == "work":
                        next_work_id, next_work_revision_id = _id(), _id()
                        _common_revision(db, "record", next_work_id, next_work_revision_id, 0)
                    next_revision, decision_id = _id(), _id()
                    _common_revision(db, "corpus-item", item_id, next_revision, 1)
                    db.execute(
                        "INSERT INTO corpus_item_states (revision_id,project_id,item_id,previous_revision_id,"
                        "work_id,work_revision_id,membership,review,availability,primary_discovery_path_id,"
                        "discovery_fingerprint,decision_revision_id) "
                        "VALUES (?,?,?,?,? ,?,'included',?,?,?, ?,?)",
                        (
                            next_revision,
                            PROJECT_ID,
                            item_id,
                            prior_revision,
                            next_work_id,
                            next_work_revision_id,
                            "none" if hidden_change == "review" else "pending",
                            "unavailable" if hidden_change == "availability" else "unknown",
                            path_id,
                            "f" * 64 if hidden_change == "discovery-fingerprint" else fingerprint,
                            decision_id,
                        ),
                    )
                    db.execute(
                        "INSERT INTO corpus_item_discovery_paths (revision_id,project_id,item_id,path_id) "
                        "VALUES (?,?,?,?)",
                        (next_revision, PROJECT_ID, item_id, path_id),
                    )
                    with self.assertRaisesRegex(sqlite3.IntegrityError, "corpus decision chain binding denied"):
                        db.execute(
                            "INSERT INTO corpus_decisions (decision_id,project_id,item_id,previous_revision_id,"
                            "next_revision_id,dimension,command,previous_value,next_value,actor_id,reason_code,"
                            "protocol_revision_id,occurred_at) "
                            "VALUES (?,?,?,? ,?,'membership',?,'candidate','included',?,'screened',?,?)",
                            (
                                decision_id,
                                PROJECT_ID,
                                item_id,
                                prior_revision,
                                next_revision,
                                "exclude" if hidden_change == "command" else "include",
                                _id(),
                                _id(),
                                _TIME,
                            ),
                        )
                    db.execute("ROLLBACK")

    def test_command_result_binding_is_append_only(self) -> None:
        database = self.fixture.project / "command-binding" / "state" / "project.sqlite3"
        database.parent.mkdir(parents=True)
        storage.initialize_database(database, project_id=PROJECT_ID, project_created_at=_TIME)
        with closing(sqlite3.connect(database, isolation_level=None)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            _, _, item_id, revision_id, path_id = _initial_corpus_state(db)
            command_id = _id()
            sql = (
                "INSERT INTO corpus_commands (project_id,command_id,semantic_sha256,"
                "result_item_id,result_revision_id,result_path_id) VALUES (?,?,?,?,?,?)"
            )
            db.execute(sql, (PROJECT_ID, command_id, "a" * 64, item_id, revision_id, path_id))
            db.execute("COMMIT")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(sql, (PROJECT_ID, command_id, "b" * 64, item_id, revision_id, path_id))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(sql, (PROJECT_ID, _id(), "c" * 64, item_id, revision_id, _id()))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                db.execute("UPDATE corpus_commands SET semantic_sha256=? WHERE command_id=?", ("d" * 64, command_id))


class ProtectedCorpusMigrationTests(unittest.TestCase):
    def test_encrypted_v16_failure_backup_retry_and_reopen(self) -> None:
        fixture = protected_fixture.ProtectedReconciliationMigrationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        legacy = fixture.root / "legacy/state/project.sqlite3"
        restore_v16(legacy)
        with fixture.keys.active_key(PROJECT_ID, create=True) as lease:
            material = lease.use(bytes)
        with closing(sqlcipher.connect(legacy.as_uri() + "?mode=ro", uri=True, isolation_level=None)) as source:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(fixture.database), f"x'{material.hex()}'"))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={storage.APPLICATION_ID}")
            source.execute("PRAGMA protected.user_version=16")
            self.assertEqual("wal", source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0])
            source.execute("DETACH DATABASE protected")

        def fail(step: str) -> None:
            if step == "common-v17-copy":
                raise ValueError("synthetic-encrypted-corpus-interruption")

        with (
            patch.object(v0017_corpus_items, "_migration_step_completed", side_effect=fail),
            self.assertRaises(runner.MigrationProblem),
        ):
            runner.migrate_database(fixture.database, expected_project_id=PROJECT_ID)
        self.assertEqual(
            16, runner.plan_database_migration(fixture.database, expected_project_id=PROJECT_ID).source_schema_version
        )
        result = runner.migrate_database(fixture.database, expected_project_id=PROJECT_ID)
        assert result.backup_relative_path is not None
        backup = fixture.root / result.backup_relative_path
        for path in (fixture.database, backup):
            self.assertNotEqual(b"SQLite format 3\x00", path.read_bytes()[:16])
        with closing(sqlcipher.connect(backup.as_uri() + "?mode=ro", uri=True, isolation_level=None)) as saved:
            saved.execute(f"PRAGMA key=\"x'{material.hex()}'\"")
            self.assertEqual(SCHEMA_SHA256, storage._schema_fingerprint(saved))
            self.assertEqual([], saved.execute("PRAGMA cipher_integrity_check").fetchall())
        for _ in range(2):
            with closing(storage.open_canonical_database(fixture.database, expected_project_id=PROJECT_ID)) as current:
                self.assertTrue(storage.database_integrity_report(current, expected_project_id=PROJECT_ID).ok)
