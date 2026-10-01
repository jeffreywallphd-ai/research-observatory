"""Literal populated v18 predecessor and additive protected report migration."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from research_observatory_core import storage
from research_observatory_core.migrations import runner
from research_observatory_core.migrations.versions import (
    v0002_schema_history,
    v0019_corpus_reports,
    v0020_corpus_source_projection,
)
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from tests.data import test_sqlite_migrations as migration_fixture

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SOURCE_COMMIT = "77fe987e16c9bb4b5878538ddf25cce5f24d68c9"
SCHEMA_SHA256 = "a9812a5fad0394652a070b3fd8466961eb3e88a928965d56e89d57008b89b503"
PROFILE_SHA256 = "4617f88a662f50b6286f399158ca4477e2cad34bad68033be99149cbdfb4ed30"
FILE_SHA256 = {
    "schema-v18-authority.json": "657740df06dc04ca7574e0b08e3a9e07fa2fc3488512f686df9d4164c3843c01",
    "schema-v18-import-corpus-populated.json": "a643a561c0340f6b4b3d5ec9613bedb20b6fb5418aba53f4c3f1d4082cad4493",
    "schema-v18-connector-corpus-populated.json": "3b80af94fd4ce63c9d9b2e4839e1229cfec7e8fdf74c5ed061756c9de5734b70",
}


def _document(name: str) -> dict[str, Any]:
    raw = (FIXTURES / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != FILE_SHA256[name]:
        raise AssertionError("v18-fixture-bytes-changed")
    document = json.loads(raw)
    if document["sourceCommit"] != SOURCE_COMMIT or document["schemaVersion"] != 18:
        raise AssertionError("v18-fixture-origin-changed")
    return document


def _schema_sha256(db: sqlite3.Connection) -> str:
    rows = [
        {"type": row[0], "name": row[1], "table": row[2], "sql": row[3]}
        for row in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def restore_v18(database: Path, kind: str) -> tuple[str, dict[str, list[list[Any]]]]:
    """Restore frozen v18 schema and populated rows without consulting current DDL."""

    if kind not in ("import-corpus", "connector-corpus"):
        raise AssertionError("v18-fixture-kind-invalid")
    authority = _document("schema-v18-authority.json")
    populated = _document(f"schema-v18-{kind}-populated.json")
    if authority["schemaSha256"] != SCHEMA_SHA256 or authority["profileSha256"] != PROFILE_SHA256:
        raise AssertionError("v18-schema-authority-changed")
    if database.exists():
        raise AssertionError("v18-restore-target-exists")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, autocommit=True)) as db:
        for obj in authority["schemaObjects"]:
            if obj["type"] == "table":
                db.execute(obj["sql"])
        for name, rows in populated["tables"].items():
            for row in rows:
                values = [bytes.fromhex(value["blobHex"]) if isinstance(value, dict) else value for value in row]
                db.execute(f'INSERT INTO "{name}" VALUES ({",".join("?" for _ in values)})', values)
        for obj in authority["schemaObjects"]:
            if obj["type"] != "table":
                db.execute(obj["sql"])
        db.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        db.execute("PRAGMA user_version=18")
        db.execute("PRAGMA foreign_keys=ON")
        if db.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
            raise AssertionError("v18-wal-unavailable")
        if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() != (0, 0, 0):
            raise AssertionError("v18-checkpoint-failed")
        if _schema_sha256(db) != SCHEMA_SHA256:
            raise AssertionError("v18-schema-changed")
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",) or db.execute("PRAGMA foreign_key_check").fetchall():
            raise AssertionError("v18-integrity-failed")
        if db.execute(
            "SELECT schema_version,profile_sha256,schema_sha256 FROM schema_metadata WHERE singleton=1"
        ).fetchone() != (18, PROFILE_SHA256, SCHEMA_SHA256):
            raise AssertionError("v18-profile-changed")
        if db.execute("SELECT project_id FROM projects WHERE singleton=1").fetchone() != (populated["projectId"],):
            raise AssertionError("v18-project-changed")
    return str(populated["projectId"]), populated["tables"]


def promote_to_frozen_v19(database: Path, project: str) -> None:
    """Apply the unmodified v19 migration alone to a frozen populated v18 database."""

    raw = sqlite3.connect(database, autocommit=True)
    engine = create_engine("sqlite://", creator=lambda: raw, poolclass=StaticPool)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            v0019_corpus_reports.apply(
                Operations(MigrationContext.configure(connection, opts={"transactional_ddl": False})),
                {
                    "migration_id": v0019_corpus_reports.revision,
                    "applied_at": "2026-10-01T00:00:00.000Z",
                    "backup_manifest_sha256": "a" * 64,
                    "source_schema_sha256": storage.RIGHTS_SCHEMA_SHA256,
                    "target_schema_sha256": storage.CORPUS_REPORT_SCHEMA_SHA256,
                    "targetSchemaSha256": storage.CORPUS_REPORT_SCHEMA_SHA256,
                    "targetProfileSha256": storage.CORPUS_REPORT_PROFILE_SHA256,
                    "reportAuthority": storage.CORPUS_REPORT_DDL,
                    "schemaMetadataDdl": storage.SCHEMA_METADATA_V19_DDL,
                    "schemaMetadataTriggers": v0002_schema_history.SCHEMA_METADATA_TRIGGERS,
                },
            )
            connection.exec_driver_sql("COMMIT")
    finally:
        engine.dispose()
    with closing(sqlite3.connect(database)) as predecessor:
        self_schema = _schema_sha256(predecessor)
        if self_schema != storage.CORPUS_REPORT_SCHEMA_SHA256:
            raise AssertionError("frozen-v19-schema-changed")
        if predecessor.execute("PRAGMA user_version").fetchone() != (19,):
            raise AssertionError("frozen-v19-version-changed")
        if predecessor.execute("SELECT project_id FROM projects").fetchone() != (project,):
            raise AssertionError("frozen-v19-project-changed")


def assert_populated_projection_exact(
    test: unittest.TestCase,
    connection: sqlite3.Connection | storage.CanonicalConnection,
    project: str,
    old: dict[str, list[list[Any]]],
) -> None:
    """Compare v20 backfill with independent frozen predecessor rows."""

    path = old["corpus_discovery_paths"][0]
    if path[7] == "import-member":
        source_key = "import:" + path[10]
    else:
        test.assertEqual("connector-record", path[7])
        source_key = "connector:" + json.loads(old["reconciliation_assertions"][0][7])["provider"]
    item = old["corpus_item_states"][0]
    heads = connection.execute(
        "SELECT item_id,revision_id,work_revision_id,included_in_report,source_counts_json "
        "FROM corpus_source_item_heads WHERE project_id=?",
        (project,),
    ).fetchall()
    test.assertEqual(1, len(heads))
    test.assertEqual((item[2], item[0], item[6], 1), tuple(heads[0][:4]))
    test.assertEqual({source_key: 1}, json.loads(heads[0][4]))
    test.assertEqual(
        [(source_key, 1, 1)],
        [
            tuple(row)
            for row in connection.execute(
                "SELECT source_key,item_count,discovery_path_count FROM corpus_source_totals WHERE project_id=?",
                (project,),
            )
        ],
    )
    test.assertEqual(
        [],
        connection.execute("SELECT * FROM corpus_source_overlap_totals WHERE project_id=?", (project,)).fetchall(),
    )


class CorpusReportMigrationTests(unittest.TestCase):
    def test_populated_v19_projection_backfill_interruption_and_backup_recovery(self) -> None:
        fixture = migration_fixture.SqliteMigrationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        for failpoint in ("projection-authority-create", "projection-backfill", "user-version-advance"):
            with self.subTest(failpoint=failpoint):
                database = fixture.project / failpoint / "state/project.sqlite3"
                project, old = restore_v18(database, "import-corpus")
                promote_to_frozen_v19(database, project)
                planned = runner.plan_database_migration(database, expected_project_id=project)
                self.assertEqual(19, planned.source_schema_version)
                self.assertEqual((v0020_corpus_source_projection.revision,), planned.migration_ids)

                def interrupt(step: str, expected: str = failpoint) -> None:
                    if step == expected:
                        raise ValueError("synthetic-projection-migration-interruption")

                with (
                    patch.object(v0020_corpus_source_projection, "_migration_step_completed", side_effect=interrupt),
                    self.assertRaises(runner.MigrationProblem),
                ):
                    runner.migrate_database(database, expected_project_id=project)
                with closing(sqlite3.connect(database)) as predecessor:
                    self.assertEqual(storage.CORPUS_REPORT_SCHEMA_SHA256, _schema_sha256(predecessor))
                    self.assertEqual((19,), predecessor.execute("PRAGMA user_version").fetchone())
                completed = runner.migrate_database(database, expected_project_id=project)
                self.assertEqual((v0020_corpus_source_projection.revision,), completed.migration_ids)
                assert completed.backup_relative_path is not None
                with closing(sqlite3.connect(database.parent.parent / completed.backup_relative_path)) as backup:
                    self.assertEqual(storage.CORPUS_REPORT_SCHEMA_SHA256, _schema_sha256(backup))
                    self.assertEqual((19,), backup.execute("PRAGMA user_version").fetchone())
                with closing(storage.open_canonical_database(database, expected_project_id=project)) as current:
                    assert_populated_projection_exact(self, current, project, old)

    def test_frozen_v18_recovery_contract_survives_successor(self) -> None:
        frozen_path = REPO / "packages/contracts/storage/sqlite-migration-recovery-v18.snapshot.json"
        raw = frozen_path.read_bytes()
        self.assertEqual(
            "95472000d9b20b6a25d503ef4b842bc2b7b822e6530e0fd73f0211d64472041e",
            hashlib.sha256(raw).hexdigest(),
        )
        frozen = json.loads(raw)
        v19_raw = (REPO / "packages/contracts/storage/sqlite-migration-recovery-v19.snapshot.json").read_bytes()
        self.assertEqual(
            "f58f50d884456e24ba7ac55af5bf5bb1216e1aa9924a3dc704f1a718f0766511",
            hashlib.sha256(v19_raw).hexdigest(),
        )
        frozen_v19 = json.loads(v19_raw)
        current = json.loads(
            (REPO / "packages/contracts/storage/sqlite-migration-recovery.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(18, frozen["properties"]["targetSchemaVersion"]["const"])
        self.assertEqual(19, frozen_v19["properties"]["targetSchemaVersion"]["const"])
        self.assertEqual(20, current["properties"]["targetSchemaVersion"]["const"])
        self.assertEqual(SCHEMA_SHA256, frozen["properties"]["targetSchemaSha256"]["const"])
        self.assertEqual(storage.CORPUS_REPORT_SCHEMA_SHA256, frozen_v19["properties"]["targetSchemaSha256"]["const"])
        self.assertEqual(storage.EXPECTED_SCHEMA_SHA256, current["properties"]["targetSchemaSha256"]["const"])

    def test_populated_v18_import_and_connector_histories_survive_v19_with_verified_backup(self) -> None:
        for kind in ("import-corpus", "connector-corpus"):
            with self.subTest(kind=kind):
                fixture = migration_fixture.SqliteMigrationTests(methodName="runTest")
                fixture.setUp()
                self.addCleanup(fixture.tearDown)
                project, old = restore_v18(fixture.database, kind)
                planned = runner.plan_database_migration(fixture.database, expected_project_id=project)
                self.assertEqual(18, planned.source_schema_version)
                self.assertEqual(
                    (v0019_corpus_reports.revision, v0020_corpus_source_projection.revision),
                    planned.migration_ids,
                )
                completed = runner.migrate_database(fixture.database, expected_project_id=project)
                self.assertEqual("migrated", completed.status)
                assert completed.backup_relative_path is not None
                backup = fixture.project / completed.backup_relative_path
                with closing(sqlite3.connect(backup)) as predecessor:
                    self.assertEqual(SCHEMA_SHA256, _schema_sha256(predecessor))
                    self.assertEqual((18,), predecessor.execute("PRAGMA user_version").fetchone())
                    self.assertEqual((project,), predecessor.execute("SELECT project_id FROM projects").fetchone())
                with closing(sqlite3.connect(fixture.database)) as current:
                    for name, rows in old.items():
                        if name in {"schema_metadata", "schema_migrations"}:
                            continue
                        actual = [
                            [{"blobHex": value.hex()} if isinstance(value, bytes) else value for value in row]
                            for row in current.execute(f'SELECT * FROM "{name}"')
                        ]
                        self.assertCountEqual(
                            [json.dumps(row, sort_keys=True) for row in rows],
                            [json.dumps(row, sort_keys=True) for row in actual],
                            name,
                        )
                    for name in ("corpus_report_snapshots", "corpus_report_members"):
                        self.assertEqual(0, current.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
                    assert_populated_projection_exact(self, current, project, old)
                with closing(
                    storage.open_canonical_database(fixture.database, expected_project_id=project)
                ) as reopened:
                    self.assertTrue(storage.database_integrity_report(reopened, expected_project_id=project).ok)

    def test_interrupted_v19_keeps_exact_v18_and_can_retry(self) -> None:
        fixture = migration_fixture.SqliteMigrationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        for failpoint in ("report-members-create", "user-version-advance"):
            with self.subTest(failpoint=failpoint):
                database = fixture.project / failpoint / "state/project.sqlite3"
                project, _ = restore_v18(database, "import-corpus")

                def interrupt(step: str, expected: str = failpoint) -> None:
                    if step == expected:
                        raise ValueError("synthetic-report-migration-interruption")

                with (
                    patch.object(v0019_corpus_reports, "_migration_step_completed", side_effect=interrupt),
                    self.assertRaises(runner.MigrationProblem),
                ):
                    runner.migrate_database(database, expected_project_id=project)
                with closing(sqlite3.connect(database)) as old:
                    self.assertEqual(SCHEMA_SHA256, _schema_sha256(old))
                    self.assertEqual((18,), old.execute("PRAGMA user_version").fetchone())
                completed = runner.migrate_database(database, expected_project_id=project)
                self.assertEqual("migrated", completed.status)
