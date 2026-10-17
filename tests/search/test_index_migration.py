"""Literal populated protected v28 predecessor; public synthetic fixture key."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import sqlcipher3.dbapi2 as cipher  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core import storage  # noqa: E402
from research_observatory_core.migrations import runner  # noqa: E402
from research_observatory_core.ports.database_keys import DatabaseKeyProvider  # noqa: E402

from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402

FIXTURE = ROOT / "tests/fixtures/search/v28-populated-predecessor"
PUBLIC_FIXTURE_KEY = hashlib.sha256(b"Research Observatory synthetic v28 migration fixture key v1").digest()


class IndexMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-index-v28-")
        self.addCleanup(self.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.manifest = json.loads(FIXTURE.with_suffix(".json").read_text())
        archive = FIXTURE.with_suffix(".zip")
        self.assertEqual(self.manifest["archiveSha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        with ZipFile(archive) as zipfile:
            for name in ("state/project.sqlite3", *(row["relativePath"] for row in self.manifest["ciphertext"])):
                path = self.root / name
                self.assertTrue(path.resolve().is_relative_to(self.root))
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as target:
                    target.write(zipfile.read(name))
        self.database = self.root / "state/project.sqlite3"
        self.assertEqual(self.manifest["databaseSha256"], hashlib.sha256(self.database.read_bytes()).hexdigest())
        self.project = self.manifest["projectId"]
        keys = InMemoryDatabaseKeyProvider()
        keys._active[self.project] = ("f" * 32, PUBLIC_FIXTURE_KEY)
        self.keys: DatabaseKeyProvider = keys
        with storage._DATABASE_PROTECTION_LOCK:
            self.previous_protection = storage._DATABASE_PROTECTION
        storage.configure_protected_database_provider(self.keys)
        self.addCleanup(self.restore_protection)

    def cleanup(self):
        # Immutable migration backups intentionally deny ordinary mutation.
        # Reset only this owned fixture's ACL before deleting its temp tree.
        target = Path(self.temporary.name).resolve()
        if not target.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not target.name.startswith(
            "ro-index-v28-"
        ):
            raise RuntimeError("fixture cleanup target is outside its scratch")
        if os.name == "nt":
            result = subprocess.run(
                [str(Path(os.environ["SYSTEMROOT"]) / "System32/icacls.exe"), str(target), "/reset", "/t", "/c", "/q"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, result.returncode, "owned migration fixture ACL reset failed")
        self.temporary.cleanup()

    def restore_protection(self):
        with storage._DATABASE_PROTECTION_LOCK:
            storage._DATABASE_PROTECTION = self.previous_protection

    def raw(self, path=None):
        db = cipher.connect(str(path or self.database), isolation_level=None)
        with self.keys.active_key(self.project, create=False) as key:
            key.use(lambda material: storage._key_sqlcipher_connection(db, material))
        return db

    def assert_preserved(self, path=None):
        with closing(self.raw(path)) as db:
            for table, count in self.manifest["counts"].items():
                if table in {"schema_metadata", "schema_migrations"}:
                    continue
                columns = [row[1] for row in db.execute(f'PRAGMA table_info("{table}")')]
                order = ",".join('"' + column + '"' for column in columns)
                rows = db.execute(f'SELECT * FROM "{table}" ORDER BY {order}').fetchall()
                self.assertEqual(count, len(rows), table)
                digest = hashlib.sha256(json.dumps(rows, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
                self.assertEqual(self.manifest["rowSha256"][table], digest, table)
            actual_history = db.execute("SELECT * FROM schema_migrations ORDER BY migration_id").fetchall()
            old_history = [tuple(row) for row in self.manifest["schemaMigrationRows"]]
            self.assertEqual(old_history, actual_history[: len(old_history)])
        for item in self.manifest["ciphertext"]:
            self.assertEqual(
                item["sha256"], hashlib.sha256((self.root / item["relativePath"]).read_bytes()).hexdigest()
            )

    def test_exact_v28_is_recognized_as_predecessor(self):
        self.assertGreater(self.manifest["counts"]["document_enrichments"], 0)
        self.assert_preserved()
        plan = runner.plan_database_migration(self.database, expected_project_id=self.project)
        self.assertEqual(28, plan.source_schema_version)
        self.assertEqual(30, plan.target_schema_version)
        self.assertEqual(("0029_lexical_index_generations", "0030_lexical_search_runs"), plan.migration_ids)

    def test_protected_backup_all_old_cells_objects_and_change_backfill(self):
        result = runner.migrate_database(self.database, expected_project_id=self.project)
        self.assertEqual("migrated", result.status)
        assert result.backup_relative_path is not None
        assert result.recovery_manifest_relative_path is not None
        self.assert_preserved()
        backup = self.root / result.backup_relative_path
        self.assert_preserved(backup)
        self.assertNotEqual(b"SQLite format 3\0", backup.read_bytes()[:16])
        recovery = json.loads((self.root / result.recovery_manifest_relative_path).read_text())
        schema = json.loads((ROOT / "packages/contracts/storage/sqlite-migration-recovery.schema.json").read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertEqual([], list(validator.iter_errors(recovery)))
        with closing(self.raw(backup)) as db:
            self.assertEqual(28, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(self.manifest["schemaSha256"], storage._schema_fingerprint(db))
        with closing(storage.open_canonical_database(self.database, expected_project_id=self.project)) as db:
            self.assertTrue(storage.database_integrity_report(db, expected_project_id=self.project).ok)
            self.assertEqual(30, db.execute("PRAGMA user_version").fetchone()[0])
            before = db.execute(
                "SELECT outbox_id,project_id,revision_id,event_type,occurred_at,record_sha256 FROM outbox_events "
                "ORDER BY outbox_id"
            ).fetchall()
            after = db.execute(
                "SELECT outbox_id,project_id,revision_id,event_type,occurred_at,record_sha256 FROM "
                "search_changes ORDER BY sequence"
            ).fetchall()
            self.assertEqual([tuple(row) for row in before], [tuple(row) for row in after])
            for table in (
                "search_generations",
                "search_generation_leases",
                "search_generation_events",
                "search_selections",
            ):
                self.assertEqual(0, db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])

    def test_each_material_interruption_rolls_back_literal_v28_and_retries(self):
        from research_observatory_core.migrations.versions import v0029_lexical_index_generations as migration

        for step in migration.MATERIAL_MIGRATION_STEPS:
            with self.subTest(step=step):
                observed: list[str] = []

                def interrupt(completed, target=step, observed=observed):
                    if completed == target:
                        observed.append(completed)
                        raise RuntimeError("synthetic index migration interruption")

                with (
                    patch.object(migration, "_migration_step_completed", side_effect=interrupt),
                    self.assertRaises(runner.MigrationProblem) as failure,
                ):
                    runner.migrate_database(self.database, expected_project_id=self.project)
                self.assertEqual([step], observed)
                self.assertEqual("migration-execution-failed", failure.exception.code)
                self.assert_preserved()
                with closing(self.raw()) as db:
                    self.assertEqual(28, db.execute("PRAGMA user_version").fetchone()[0])
                    self.assertEqual(self.manifest["schemaSha256"], storage._schema_fingerprint(db))
        self.assertEqual("migrated", runner.migrate_database(self.database, expected_project_id=self.project).status)
        self.assert_preserved()

    @unittest.skipUnless(os.name == "nt", "W3 current-user DPAPI migration boundary")
    def test_actual_dpapi_reprotected_exact_v28_migrates_and_preserves_backup(self):
        from research_observatory_core.windows_credentials import WindowsCredentialStore, WindowsDatabaseKeyProvider

        vault_scratch = tempfile.TemporaryDirectory(prefix="ro-index-migration-vault-")
        self.addCleanup(vault_scratch.cleanup)
        actual_keys = WindowsDatabaseKeyProvider(
            WindowsCredentialStore(Path(vault_scratch.name) / "vault", audit_sink=lambda _event: None),
            profile_id="fixture",
        )
        target = self.root / "dpapi-reprotected.sqlite3"
        with closing(self.raw()) as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
            with actual_keys.active_key(self.project, create=True) as key:
                key.use(
                    lambda material: db.execute(
                        "ATTACH DATABASE ? AS dpapi KEY ?", (str(target), "x'" + material.hex() + "'")
                    )
                )
            db.execute("SELECT sqlcipher_export('dpapi')").fetchone()
            db.execute(f"PRAGMA dpapi.application_id={storage.APPLICATION_ID}")
            db.execute("PRAGMA dpapi.user_version=28")
            db.execute("PRAGMA dpapi.journal_mode=WAL").fetchone()
            db.execute("DETACH DATABASE dpapi")
        self.assertTrue(target.resolve().is_relative_to(self.root))
        target.replace(self.database)
        self.keys = actual_keys
        storage.configure_protected_database_provider(actual_keys)
        self.assert_preserved()
        with closing(self.raw()) as db:
            self.assertEqual(self.manifest["schemaSha256"], storage._schema_fingerprint(db))
        result = runner.migrate_database(self.database, expected_project_id=self.project)
        self.assertEqual("migrated", result.status)
        self.assert_preserved()
        assert result.backup_relative_path is not None
        self.assert_preserved(self.root / result.backup_relative_path)
        with closing(storage.open_canonical_database(self.database, expected_project_id=self.project)) as db:
            self.assertTrue(storage.database_integrity_report(db, expected_project_id=self.project).ok)


if __name__ == "__main__":
    unittest.main()
