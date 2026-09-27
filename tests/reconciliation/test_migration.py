"""Exact committed v13 schema and actual synthetic import publication predecessor."""

import hashlib
import importlib
import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]
from research_observatory_core import storage
from research_observatory_core.migrations import runner

from tests.data import test_sqlite_migrations as migration_fixture

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/scholarly-metadata"
V13_SCHEMA = "13e54503130f8e40036beed26659c5bda2787928c56444987619366e4310b064"
V13_PROFILE = "9ef28bc5d42188c63b50f31eb714c69d040a685311c1dcc5aaf1e89faec42e0b"
POPULATED_SHA256 = "9e2a3941dd70c81a77532635b07354d43d6e545fd67c6c15b88f74cfe5d34f27"


def create_v13(database: Path) -> str:
    authority = json.loads((FIXTURES / "schema-v13-authority.json").read_text(encoding="utf-8"))
    raw = (FIXTURES / "schema-v13-populated.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != POPULATED_SHA256:
        raise AssertionError("v13-populated-authority-changed")
    data = json.loads(raw)
    if authority["schemaSha256"] != V13_SCHEMA or authority["profileSha256"] != V13_PROFILE:
        raise AssertionError("v13-schema-authority-changed")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, autocommit=True)) as db:
        # Restore literal pre-change schema/data. Triggers follow data restoration;
        # the complete resulting fingerprint and FKs must match before upgrade.
        for item in authority["schemaObjects"]:
            if item["type"] == "table":
                db.execute(item["sql"])
        for table, rows in data["tables"].items():
            for row in rows:
                db.execute('INSERT INTO "' + table + '" VALUES (' + ",".join("?" for _ in row) + ")", row)
        for item in authority["schemaObjects"]:
            if item["type"] != "table":
                db.execute(item["sql"])
        db.execute("PRAGMA user_version=13")
        db.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
        storage._configure_connection(db, initialize=True)
        if storage._schema_fingerprint(db) != V13_SCHEMA or db.execute("PRAGMA foreign_key_check").fetchall():
            raise AssertionError("v13-frozen-fixture-invalid")
    return data["projectId"]


class ReconciliationMigrationTests(unittest.TestCase):
    def setUp(self):
        fixture = migration_fixture.SqliteMigrationTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.database = fixture.database
        self.identity = create_v13(self.database)

    def test_exact_populated_predecessor_upgrade_preserves_sources_and_backup(self):
        before = json.loads((FIXTURES / "schema-v13-populated.json").read_text(encoding="utf-8"))["tables"]
        plan = runner.plan_database_migration(self.database, expected_project_id=self.identity)
        self.assertEqual(
            ("0014_scholarly_reconciliation", "0015_reconciliation_review", "0016_work_versions"), plan.migration_ids
        )
        result = runner.migrate_database(self.database, expected_project_id=self.identity)
        self.assertEqual("migrated", result.status)
        assert result.backup_relative_path is not None
        with closing(sqlite3.connect(self.database.parent.parent / result.backup_relative_path)) as backup:
            self.assertEqual(V13_SCHEMA, storage._schema_fingerprint(backup))
        for _ in range(2):
            with storage.open_canonical_database(self.database, expected_project_id=self.identity) as db:
                self.assertEqual(16, db.execute("PRAGMA user_version").fetchone()[0])
                for table in (
                    "aggregate_revisions",
                    "import_source_records",
                    "import_manifests",
                    "import_manifest_members",
                    "import_manifest_seals",
                    "provenance_events",
                    "outbox_events",
                ):
                    self.assertEqual(before[table], [list(row) for row in db.execute('SELECT * FROM "' + table + '"')])
                self.assertEqual(0, db.execute("SELECT COUNT(*) FROM reconciliation_assertions").fetchone()[0])

    def test_modified_predecessor_is_denied(self):
        with closing(sqlite3.connect(self.database, autocommit=True)) as db:
            db.execute("DROP TRIGGER import_source_records_no_update")
        with self.assertRaises(runner.MigrationProblem):
            runner.migrate_database(self.database, expected_project_id=self.identity)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(13, db.execute("PRAGMA user_version").fetchone()[0])

    def test_every_material_failure_rolls_back(self):
        from research_observatory_core.migrations.versions import v0014_scholarly_reconciliation

        for step in v0014_scholarly_reconciliation.MATERIAL_MIGRATION_STEPS:
            with self.subTest(step=step):
                database = self.database.parents[2] / step / "state/project.sqlite3"
                identity = create_v13(database)

                def fail(observed, expected=step):
                    if observed == expected:
                        raise ValueError("synthetic-reconciliation-migration-interruption")

                with (
                    patch.object(
                        v0014_scholarly_reconciliation, "_migration_step_completed", side_effect=fail
                    ) as injected,
                    self.assertRaises(runner.MigrationProblem),
                ):
                    runner.migrate_database(database, expected_project_id=identity)
                injected.assert_any_call(step)
                with closing(sqlite3.connect(database)) as db:
                    self.assertEqual(V13_SCHEMA, storage._schema_fingerprint(db))
                    self.assertEqual(13, db.execute("PRAGMA user_version").fetchone()[0])
                    self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())


class ProtectedReconciliationMigrationTests(unittest.TestCase):
    """Real SQLCipher migration and backup; key authority is an in-memory fixture."""

    def setUp(self):
        # Security tests use a namespace directory; import the existing fixture
        # explicitly without changing its discovery/package layout for this task.
        fixture = importlib.import_module("tests.security.test_protected_database").ProtectedDatabaseTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.root: Path = fixture.root
        self.database: Path = fixture.database
        self.keys = fixture.keys

    def test_encrypted_populated_v13_rollback_retry_backup_and_reopen(self):
        from research_observatory_core.migrations.versions import v0014_scholarly_reconciliation as revision

        legacy = self.root / "legacy/state/project.sqlite3"
        identity = create_v13(legacy)
        with self.keys.active_key(identity, create=True) as lease:
            material = lease.use(bytes)
        source = sqlcipher.connect(legacy.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(self.database), f"x'{material.hex()}'"))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={storage.APPLICATION_ID}")
            source.execute("PRAGMA protected.user_version=13")
            self.assertEqual("wal", source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0])
            source.execute("DETACH DATABASE protected")
        finally:
            source.close()

        def fail(step):
            if step == "user-version-advance":
                raise RuntimeError("synthetic-encrypted-v14-interruption")

        with (
            patch.object(revision, "_migration_step_completed", side_effect=fail) as injected,
            self.assertRaises(runner.MigrationProblem),
        ):
            runner.migrate_database(self.database, expected_project_id=identity)
        injected.assert_any_call("user-version-advance")
        plan = runner.plan_database_migration(self.database, expected_project_id=identity)
        self.assertEqual(13, plan.source_schema_version)
        self.assertEqual(V13_SCHEMA, plan.source_schema_sha256)
        result = runner.migrate_database(self.database, expected_project_id=identity)
        self.assertEqual("migrated", result.status)
        backup = self.root / str(result.backup_relative_path)
        for path in (self.database, backup):
            self.assertNotEqual(b"SQLite format 3\x00", path.read_bytes()[:16])
        saved = sqlcipher.connect(backup.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            saved.execute(f"PRAGMA key=\"x'{material.hex()}'\"")
            self.assertEqual(V13_SCHEMA, storage._schema_fingerprint(saved))
            self.assertEqual("ok", saved.execute("PRAGMA quick_check").fetchone()[0])
            self.assertEqual([], saved.execute("PRAGMA cipher_integrity_check").fetchall())
        finally:
            saved.close()
        before = json.loads((FIXTURES / "schema-v13-populated.json").read_text(encoding="utf-8"))["tables"]
        for _ in range(2):
            with storage.open_canonical_database(self.database, expected_project_id=identity) as current:
                self.assertEqual(16, current.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual([], current.execute("PRAGMA foreign_key_check").fetchall())
                for table in (
                    "import_source_records",
                    "import_manifest_members",
                    "aggregate_revisions",
                    "provenance_events",
                ):
                    self.assertEqual(
                        before[table], [list(row) for row in current.execute('SELECT * FROM "' + table + '"')]
                    )
