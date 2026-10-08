"""Literal populated and inherited v24 preservation through interrupted v25."""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))
from research_observatory_core import storage  # noqa: E402
from research_observatory_core.migrations import runner  # noqa: E402
from research_observatory_core.migrations.versions import v0025_document_intake_recovery as migration  # noqa: E402
from research_observatory_core.migrations.versions import v0026_document_revisions as current_migration  # noqa: E402
from research_observatory_core.migrations.versions import v0027_revision_invalidations as invalidation  # noqa: E402


class AcquisitionRecoveryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-intake-v24-")
        self.addCleanup(self.cleanup)
        self.profile = storage.development_plaintext_database_fixture()
        self.profile.__enter__()
        self.addCleanup(self.profile.__exit__, None, None, None)

    def cleanup(self):
        if os.name == "nt":
            subprocess.run(
                [
                    str(Path(os.environ["SYSTEMROOT"]) / "System32/icacls.exe"),
                    self.temporary.name,
                    "/reset",
                    "/t",
                    "/c",
                    "/q",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
        self.temporary.cleanup()

    def load(self, fixture_name):
        base = ROOT / "tests/fixtures/documents" / fixture_name
        manifest = json.loads(base.with_suffix(".json").read_text())
        archive = base.with_suffix(".zip")
        self.assertEqual(manifest["archiveSha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        project = Path(self.temporary.name) / fixture_name
        with ZipFile(archive) as z:
            for name in ("state/project.sqlite3", *(x["relativePath"] for x in manifest["ciphertext"])):
                destination = project / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(z.read(name))
        database = project / "state/project.sqlite3"
        self.assertEqual(manifest["databaseSha256"], hashlib.sha256(database.read_bytes()).hexdigest())
        return manifest, project, database

    def row_hashes(self, database, manifest):
        with closing(sqlite3.connect(database)) as db:
            values = {}
            for table in manifest["counts"]:
                if table in {"schema_metadata", "schema_migrations"}:
                    continue
                columns = [r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]
                order = ",".join('"' + c + '"' for c in columns)
                rows = db.execute(f'SELECT * FROM "{table}" ORDER BY {order}').fetchall()
                self.assertEqual(manifest["counts"][table], len(rows), table)
                values[table] = hashlib.sha256(
                    json.dumps(rows, ensure_ascii=True, separators=(",", ":")).encode()
                ).hexdigest()
        return values

    def assert_predecessor_rows(self, database, manifest):
        actual = self.row_hashes(database, manifest)
        self.assertEqual({t: manifest["rowSha256"][t] for t in actual}, actual)

    def assert_ciphertext(self, project, manifest):
        for item in manifest["ciphertext"]:
            self.assertEqual(item["sha256"], hashlib.sha256((project / item["relativePath"]).read_bytes()).hexdigest())

    def test_literal_v24_populated_and_inherited_rows_survive_with_verified_backup(self):
        for fixture_name in ("v24-populated-predecessor", "v24-predecessor"):
            with self.subTest(fixture=fixture_name):
                manifest, project, database = self.load(fixture_name)
                self.assert_predecessor_rows(database, manifest)
                plan = runner.plan_database_migration(database, expected_project_id=manifest["projectId"])
                self.assertEqual(
                    (migration.revision, current_migration.revision, invalidation.revision), plan.migration_ids
                )
                result = runner.migrate_database(database, expected_project_id=manifest["projectId"])
                self.assertEqual("migrated", result.status)
                self.assert_predecessor_rows(database, manifest)
                self.assert_ciphertext(project, manifest)
                with closing(sqlite3.connect(project / result.backup_relative_path)) as db:
                    self.assertEqual(24, db.execute("PRAGMA user_version").fetchone()[0])
                    self.assertEqual(manifest["schemaSha256"], storage._schema_fingerprint(db))
                self.assert_predecessor_rows(project / result.backup_relative_path, manifest)
                with closing(
                    storage.open_canonical_database(database, expected_project_id=manifest["projectId"])
                ) as db:
                    self.assertTrue(storage.database_integrity_report(db, expected_project_id=manifest["projectId"]).ok)
                    self.assertEqual(storage.DATABASE_SCHEMA_VERSION, db.execute("PRAGMA user_version").fetchone()[0])
                    for table in storage.DOCUMENT_INTAKE_TABLES:
                        self.assertEqual(0, db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                self.assertEqual(
                    "current", runner.migrate_database(database, expected_project_id=manifest["projectId"]).status
                )

    def test_each_v25_interruption_retains_populated_v24_then_restarts(self):
        manifest, project, database = self.load("v24-populated-predecessor")
        self.assertTrue(all(manifest["counts"][t] for t in storage.ACQUISITION_TABLES))
        for target in migration.MATERIAL_MIGRATION_STEPS:

            def interrupt(step, target=target):
                if step == target:
                    raise RuntimeError("synthetic v25 interruption")

            with (
                self.subTest(step=target),
                patch.object(migration, "_migration_step_completed", side_effect=interrupt),
                self.assertRaises(RuntimeError),
            ):
                runner.migrate_database(database, expected_project_id=manifest["projectId"])
            self.assert_predecessor_rows(database, manifest)
            self.assert_ciphertext(project, manifest)
            with closing(sqlite3.connect(database)) as db:
                self.assertEqual(24, db.execute("PRAGMA user_version").fetchone()[0])
                self.assertEqual(manifest["schemaSha256"], storage._schema_fingerprint(db))
        self.assertEqual(
            "migrated", runner.migrate_database(database, expected_project_id=manifest["projectId"]).status
        )
        self.assert_predecessor_rows(database, manifest)
        self.assert_ciphertext(project, manifest)


if __name__ == "__main__":
    unittest.main()
