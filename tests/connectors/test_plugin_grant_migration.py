"""Exact encrypted v20 predecessor through current grant-authority migrations."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core import storage  # noqa: E402
from research_observatory_core.migrations.runner import (  # noqa: E402
    MigrationProblem,
    migrate_database,
    plan_database_migration,
)
from research_observatory_core.migrations.versions import (  # noqa: E402
    v0021_plugin_grants,
    v0022_document_attachments,
    v0023_attachment_operations,
)

from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402

PROJECT_ID = "01890f6e-6a40-4cc5-98b7-7f3f36b60210"
CREATED_AT = "2026-10-01T12:00:00.000Z"
MIGRATION_IDS = (
    v0021_plugin_grants.revision,
    v0022_document_attachments.revision,
    v0023_attachment_operations.revision,
)


class PluginGrantMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-plugin-grant-migration-")
        self.addCleanup(self._cleanup)
        root = Path(self.temporary.name).resolve()
        self.state = root / "project/state"
        self.state.mkdir(parents=True)
        self.database = self.state / "project.sqlite3"
        storage.configure_protected_database_provider(InMemoryDatabaseKeyProvider())
        self._create_exact_v20()

    def _cleanup(self) -> None:
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

    def _create_exact_v20(self) -> None:
        # The first grant DDL statement is the stable v20 boundary. Later
        # v22/v23 statements must not enter this frozen predecessor fixture.
        self.database.touch(exist_ok=False)
        connection = storage._connect_held(self.database, project_id=PROJECT_ID, create_key=True)
        try:
            storage._configure_connection(connection, initialize=True, protected=True)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(f"PRAGMA application_id={storage.APPLICATION_ID}")
            connection.execute("PRAGMA user_version=20")
            grant_start = storage._DDL_STATEMENTS.index(storage.PLUGIN_GRANT_DDL[0])
            self.assertEqual(
                storage.PLUGIN_GRANT_DDL,
                storage._DDL_STATEMENTS[grant_start : grant_start + len(storage.PLUGIN_GRANT_DDL)],
            )
            for statement in (
                storage.SCHEMA_METADATA_V20_DDL,
                *storage._DDL_STATEMENTS[1:grant_start],
            ):
                connection.execute(statement)
            self.assertEqual(storage.PLUGIN_GRANT_PREDECESSOR_SCHEMA_SHA256, storage._schema_fingerprint(connection))
            connection.execute(
                "INSERT INTO schema_metadata (singleton,schema_version,database_profile,application_id,"
                "profile_sha256,schema_sha256,created_at) VALUES (1,20,?,?,?,?,?)",
                (
                    storage.DATABASE_PROFILE,
                    storage.APPLICATION_ID,
                    storage.PLUGIN_GRANT_PREDECESSOR_PROFILE_SHA256,
                    storage.PLUGIN_GRANT_PREDECESSOR_SCHEMA_SHA256,
                    CREATED_AT,
                ),
            )
            connection.execute(
                "INSERT INTO projects (singleton,project_id,project_id_scheme,created_at) "
                "VALUES (1,?,'uuid4-bridge',?)",
                (PROJECT_ID, CREATED_AT),
            )
            connection.execute("COMMIT")
            self.assertEqual((0, 0, 0), tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()))
        finally:
            connection.close()
        self.assertNotEqual(b"SQLite format 3\x00", self.database.read_bytes()[:16])

    def _assert_current_v23_history(self) -> None:
        current = storage.open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(23, current.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(v0023_attachment_operations.TARGET_SCHEMA_SHA256, storage._schema_fingerprint(current))
            self.assertEqual(storage.EXPECTED_SCHEMA_SHA256, storage._schema_fingerprint(current))
            self.assertEqual(0, current.execute("SELECT count(*) FROM plugin_grant_events").fetchone()[0])
            self.assertEqual(
                [
                    (
                        v0021_plugin_grants.revision,
                        20,
                        21,
                        storage.PLUGIN_GRANT_PREDECESSOR_SCHEMA_SHA256,
                        v0021_plugin_grants.TARGET_SCHEMA_SHA256,
                    ),
                    (
                        v0022_document_attachments.revision,
                        21,
                        22,
                        v0021_plugin_grants.TARGET_SCHEMA_SHA256,
                        v0022_document_attachments.TARGET_SCHEMA_SHA256,
                    ),
                    (
                        v0023_attachment_operations.revision,
                        22,
                        23,
                        v0022_document_attachments.TARGET_SCHEMA_SHA256,
                        v0023_attachment_operations.TARGET_SCHEMA_SHA256,
                    ),
                ],
                [
                    tuple(row)
                    for row in current.execute(
                        "SELECT migration_id,from_schema_version,to_schema_version,source_schema_sha256,"
                        "target_schema_sha256 FROM schema_migrations ORDER BY from_schema_version"
                    ).fetchall()
                ],
            )
        finally:
            current.close()

    def test_exact_encrypted_v20_migrates_with_verified_backup_and_reopens(self) -> None:
        plan = plan_database_migration(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual(20, plan.source_schema_version)
        self.assertEqual(MIGRATION_IDS, plan.migration_ids)
        self.assertEqual(storage.PLUGIN_GRANT_PREDECESSOR_SCHEMA_SHA256, plan.source_schema_sha256)
        result = migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual("migrated", result.status)
        self.assertEqual(MIGRATION_IDS, result.migration_ids)
        self.assertEqual("current", migrate_database(self.database, expected_project_id=PROJECT_ID).status)
        self._assert_current_v23_history()
        assert result.recovery_manifest_relative_path is not None
        manifest_path = self.state.parent / result.recovery_manifest_relative_path
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        backup_path = self.state.parent / manifest["backup"]["relativePath"]
        self.assertEqual(hashlib.sha256(backup_path.read_bytes()).hexdigest(), manifest["backup"]["sha256"])
        self.assertEqual(20, manifest["sourceSchemaVersion"])
        self.assertEqual(23, manifest["targetSchemaVersion"])
        self.assertEqual(list(MIGRATION_IDS), manifest["migrationIds"])

    def test_each_v21_step_failure_rolls_back_exact_v20_and_retries(self) -> None:
        # Exercise every material step because schema replacement and history
        # insertion must share one transaction after the verified backup.
        for step in v0021_plugin_grants.MATERIAL_MIGRATION_STEPS:
            with self.subTest(step=step):

                def fail(completed: str, target: str = step) -> None:
                    if completed == target:
                        raise RuntimeError("synthetic v21 interruption")

                with (
                    patch.object(v0021_plugin_grants, "_migration_step_completed", side_effect=fail),
                    self.assertRaises(MigrationProblem) as raised,
                ):
                    migrate_database(self.database, expected_project_id=PROJECT_ID)
                self.assertEqual("migration-execution-failed", raised.exception.code)
                self.assertIsNotNone(raised.exception.recovery_manifest_relative_path)
                plan = plan_database_migration(self.database, expected_project_id=PROJECT_ID)
                self.assertEqual(20, plan.source_schema_version)
                self.assertEqual(MIGRATION_IDS, plan.migration_ids)
                self.assertEqual(storage.PLUGIN_GRANT_PREDECESSOR_SCHEMA_SHA256, plan.source_schema_sha256)
        result = migrate_database(self.database, expected_project_id=PROJECT_ID)
        self.assertEqual("migrated", result.status)
        self.assertEqual(MIGRATION_IDS, result.migration_ids)
        self._assert_current_v23_history()
        assert result.recovery_manifest_relative_path is not None
        manifest_path = self.state.parent / result.recovery_manifest_relative_path
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        backup_path = self.state.parent / manifest["backup"]["relativePath"]
        self.assertEqual(hashlib.sha256(backup_path.read_bytes()).hexdigest(), manifest["backup"]["sha256"])
        self.assertEqual(20, manifest["sourceSchemaVersion"])
        self.assertEqual(23, manifest["targetSchemaVersion"])
        self.assertEqual(list(MIGRATION_IDS), manifest["migrationIds"])
