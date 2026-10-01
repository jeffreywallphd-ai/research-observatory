"""Literal, populated schema-v17 predecessor for action-rights migration checks.

The frozen documents were captured from actual T01 repository histories at
5e33b15f, before the v18 rights schema existed. Restore uses their schema SQL and
rows, never the current storage module's DDL.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any, TypedDict
from unittest.mock import patch

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator, FormatChecker
from research_observatory_core import storage
from research_observatory_core.migrations import runner
from research_observatory_core.migrations.versions import (
    v0018_rights_policy,
    v0019_corpus_reports,
    v0020_corpus_source_projection,
)

from tests.data import test_sqlite_migrations as migration_fixture
from tests.reconciliation import test_migration as protected_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parents[2]
SOURCE_COMMIT = "5e33b15f7e4267d27cadb46b288524872467b032"
SCHEMA_SHA256 = "bb068798493011b7b2300c076e9f129443fe15939aabdf16dc62af33ac6a7945"
PROFILE_SHA256 = "3b79e6e6c2fa5055041b6977a318d0fe335b88f8106b72c2d099131fc31a9fc3"
APPLICATION_ID = 0x524F4253
FIXTURE_SHA256 = {
    "schema-v17-authority.json": "ce7f7cd7fdddd4b37814271fdd814809d0218a2bbed3eba561b6e3c15f97ba16",
    "schema-v17-import-corpus-populated.json": "f119f7c2af63f45dc41a191d1152389a5317f42c50a456f51427fa465b8a4375",
    "schema-v17-connector-corpus-populated.json": "3967ba1bebe858f53f6ddb1ae5307d409ecf88f3a4edae8815a002902e142429",
}
ROWS_SHA256 = {
    "import-corpus": "ffe2dab5079ee5b35c41cc8d8276d064c6a9db2b6d348f79fd2bb1ecf8ddf76f",
    "connector-corpus": "660eb7d5f7560fb21935b22b6a17771bac5dcc34651b46c9ed38609b2b283863",
}
POPULATED_COUNTS = {
    "import-corpus": {
        "aggregate_revisions": 6,
        "corpus_items": 1,
        "corpus_discovery_paths": 1,
        "import_manifests": 1,
        "import_source_records": 1,
        "reconciliation_assertions": 1,
        "workflow_committed_outputs": 2,
        "provenance_events": 12,
        "outbox_events": 11,
    },
    "connector-corpus": {
        "aggregate_revisions": 6,
        "corpus_items": 1,
        "corpus_discovery_paths": 1,
        "import_manifests": 0,
        "import_source_records": 0,
        "reconciliation_assertions": 1,
        "workflow_committed_outputs": 1,
        "provenance_events": 11,
        "outbox_events": 9,
    },
}


class V17Inspection(TypedDict):
    projectId: str
    counts: dict[str, int]
    pathKind: str


def _document(name: str) -> dict[str, Any]:
    raw = (FIXTURES / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256[name]:
        raise AssertionError("v17-fixture-bytes-changed")
    document = json.loads(raw)
    if document["sourceCommit"] != SOURCE_COMMIT or document["schemaVersion"] != 17:
        raise AssertionError("v17-fixture-origin-changed")
    return document


def _schema_fingerprint(db: sqlite3.Connection) -> str:
    rows = [
        {"type": str(row[0]), "name": str(row[1]), "table": str(row[2]), "sql": str(row[3])}
        for row in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]
    raw = json.dumps(rows, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _row_fingerprint(db: sqlite3.Connection) -> str:
    tables = []
    for (name,) in db.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ):
        quoted = '"' + name.replace('"', '""') + '"'
        rows = [
            [{"blobHex": value.hex()} if isinstance(value, bytes) else value for value in row]
            for row in db.execute(f"SELECT * FROM {quoted}")
        ]
        rows.sort(key=lambda row: json.dumps(row, ensure_ascii=True, separators=(",", ":")))
        tables.append({"table": name, "rows": rows})
    raw = json.dumps(tables, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def inspect_v17(database: Path, kind: str) -> V17Inspection:
    """Verify exact frozen predecessor, including populated source and corpus rows."""

    populated = _document(f"schema-v17-{kind}-populated.json")
    project_id = populated["projectId"]
    if not isinstance(project_id, str):
        raise AssertionError("v17-project-id-invalid")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        if db.execute("PRAGMA user_version").fetchone() != (17,):
            raise AssertionError("v17-user-version-changed")
        if db.execute("PRAGMA application_id").fetchone() != (APPLICATION_ID,):
            raise AssertionError("v17-application-id-changed")
        if _schema_fingerprint(db) != SCHEMA_SHA256:
            raise AssertionError("v17-schema-changed")
        if _row_fingerprint(db) != ROWS_SHA256[kind]:
            raise AssertionError("v17-rows-changed")
        if db.execute(
            "SELECT schema_version,profile_sha256,schema_sha256 FROM schema_metadata WHERE singleton=1"
        ).fetchone() != (17, PROFILE_SHA256, SCHEMA_SHA256):
            raise AssertionError("v17-metadata-changed")
        if db.execute("SELECT project_id FROM projects WHERE singleton=1").fetchone() != (project_id,):
            raise AssertionError("v17-project-changed")
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise AssertionError("v17-integrity-failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise AssertionError("v17-foreign-keys-failed")
        counts = {
            table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in POPULATED_COUNTS[kind]
        }
        if counts != POPULATED_COUNTS[kind]:
            raise AssertionError("v17-populated-history-changed")
        path_kind = db.execute("SELECT kind FROM corpus_discovery_paths").fetchone()[0]
        if path_kind != ("import-member" if kind == "import-corpus" else "connector-record"):
            raise AssertionError("v17-source-path-changed")
        rights_status = db.execute(
            "SELECT r.rights_status FROM aggregate_revisions AS r JOIN corpus_items AS c ON c.revision_id=r.revision_id"
        ).fetchone()[0]
        if rights_status != "unknown":
            raise AssertionError("v17-corpus-rights-incorrectly-known")
    return {"projectId": project_id, "counts": counts, "pathKind": path_kind}


def restore_v17(database: Path, kind: str) -> V17Inspection:
    """Restore literal v17 schema and rows; never consult successor DDL."""

    authority = _document("schema-v17-authority.json")
    populated = _document(f"schema-v17-{kind}-populated.json")
    if authority["schemaSha256"] != SCHEMA_SHA256 or authority["profileSha256"] != PROFILE_SHA256:
        raise AssertionError("v17-schema-authority-changed")
    if kind not in ROWS_SHA256:
        raise AssertionError("v17-fixture-kind-unavailable")
    if database.exists():
        raise AssertionError("v17-restore-target-exists")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, autocommit=True)) as db:
        for obj in authority["schemaObjects"]:
            if obj["type"] == "table":
                db.execute(obj["sql"])
        for table, rows in populated["tables"].items():
            quoted = '"' + table.replace('"', '""') + '"'
            for row in rows:
                values = [bytes.fromhex(value["blobHex"]) if isinstance(value, dict) else value for value in row]
                db.execute(f"INSERT INTO {quoted} VALUES ({','.join('?' for _ in values)})", values)
        for obj in authority["schemaObjects"]:
            if obj["type"] != "table":
                db.execute(obj["sql"])
        db.execute(f"PRAGMA application_id={APPLICATION_ID}")
        db.execute("PRAGMA user_version=17")
        db.execute("PRAGMA foreign_keys=ON")
        if db.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
            raise AssertionError("v17-journal-mode-unavailable")
        if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() != (0, 0, 0):
            raise AssertionError("v17-checkpoint-failed")
    return inspect_v17(database, kind)


class LiteralV17PredecessorTests(unittest.TestCase):
    def test_populated_import_and_connector_histories_restore_without_current_ddl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for kind in ROWS_SHA256:
                with self.subTest(kind=kind):
                    database = Path(directory) / kind / "state/project.sqlite3"
                    original = restore_v17(database, kind)
                    self.assertEqual(original, inspect_v17(database, kind))
                    with self.assertRaisesRegex(AssertionError, "v17-restore-target-exists"):
                        restore_v17(database, kind)

    def test_v17_to_current_keeps_exact_history_and_verified_backup_for_both_source_paths(self) -> None:
        for kind in ROWS_SHA256:
            with self.subTest(kind=kind):
                fixture = migration_fixture.SqliteMigrationTests(methodName="runTest")
                fixture.setUp()
                self.addCleanup(fixture.tearDown)
                database = fixture.database
                project = restore_v17(database, kind)["projectId"]
                plan = runner.plan_database_migration(database, expected_project_id=project)
                self.assertEqual(17, plan.source_schema_version)
                self.assertEqual(20, plan.target_schema_version)
                self.assertEqual(
                    (
                        v0018_rights_policy.revision,
                        v0019_corpus_reports.revision,
                        v0020_corpus_source_projection.revision,
                    ),
                    plan.migration_ids,
                )
                self.assertEqual(SCHEMA_SHA256, plan.source_schema_sha256)
                result = runner.migrate_database(database, expected_project_id=project)
                self.assertEqual("migrated", result.status)
                self.assertEqual(
                    (
                        v0018_rights_policy.revision,
                        v0019_corpus_reports.revision,
                        v0020_corpus_source_projection.revision,
                    ),
                    result.migration_ids,
                )
                assert result.backup_relative_path is not None
                assert result.recovery_manifest_relative_path is not None
                backup = fixture.project / result.backup_relative_path
                self.assertEqual(project, inspect_v17(backup, kind)["projectId"])
                manifest_path = fixture.project / result.recovery_manifest_relative_path
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                schema = json.loads(
                    (REPO / "packages/contracts/storage/sqlite-migration-recovery.schema.json").read_text(
                        encoding="utf-8"
                    )
                )
                validator = Draft202012Validator(schema, format_checker=FormatChecker())
                self.assertEqual([], list(validator.iter_errors(manifest)))
                self.assertEqual(17, manifest["sourceSchemaVersion"])
                self.assertEqual(20, manifest["targetSchemaVersion"])
                self.assertEqual(
                    [
                        v0018_rights_policy.revision,
                        v0019_corpus_reports.revision,
                        v0020_corpus_source_projection.revision,
                    ],
                    manifest["migrationIds"],
                )
                self.assertEqual(SCHEMA_SHA256, manifest["sourceSchemaSha256"])
                self.assertEqual(storage.EXPECTED_SCHEMA_SHA256, manifest["targetSchemaSha256"])
                self.assertTrue(list(validator.iter_errors(manifest | {"migrationIds": []})))
                self.assertTrue(list(validator.iter_errors(manifest | {"targetSchemaSha256": SCHEMA_SHA256})))
                with (
                    closing(sqlite3.connect(backup)) as prior,
                    closing(sqlite3.connect(database)) as current,
                ):
                    for (table,) in prior.execute(
                        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ):
                        if table in {"schema_metadata", "schema_migrations"}:
                            continue
                        quoted = '"' + table.replace('"', '""') + '"'
                        self.assertCountEqual(
                            [tuple(row) for row in prior.execute(f"SELECT * FROM {quoted}")],
                            [tuple(row) for row in current.execute(f"SELECT * FROM {quoted}")],
                            table,
                        )
                    for table in (
                        "rights_policy_subjects",
                        "rights_policy_revisions",
                        "rights_policy_rechecks",
                        "rights_policy_recheck_scopes",
                        "rights_policy_recheck_completions",
                        "rights_policy_generic_rechecks",
                        "rights_use_decisions",
                    ):
                        self.assertEqual(0, current.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    expected_legacy = prior.execute(
                        "SELECT project_id,item_id,path_id,revision_id FROM corpus_item_discovery_paths"
                    ).fetchall()
                    observed_legacy = current.execute(
                        "SELECT project_id,item_id,path_id,output_revision_id,"
                        "source_assertion_revision_id,reason,disposition "
                        "FROM rights_legacy_output_rechecks"
                    ).fetchall()
                    self.assertCountEqual(expected_legacy, [tuple(row[:4]) for row in observed_legacy])
                    self.assertEqual(1, len(observed_legacy))
                    self.assertEqual(
                        prior.execute("SELECT revision_id FROM reconciliation_assertions").fetchone()[0],
                        observed_legacy[0][4],
                    )
                    self.assertEqual(("RIGHTS_POLICY", "requires-review"), tuple(observed_legacy[0][5:]))
                    self.assertEqual(
                        ("unknown",),
                        current.execute(
                            "SELECT r.rights_status FROM aggregate_revisions AS r JOIN corpus_items AS c "
                            "ON c.revision_id=r.revision_id"
                        ).fetchone(),
                    )
                for _ in range(2):
                    with closing(storage.open_canonical_database(database, expected_project_id=project)) as reopened:
                        report = storage.database_integrity_report(reopened, expected_project_id=project)
                        self.assertTrue(report.ok, report.errors)
                        self.assertEqual(20, report.schema_version)
                repeated = runner.migrate_database(database, expected_project_id=project)
                self.assertEqual("current", repeated.status)
                self.assertIsNone(repeated.backup_relative_path)

    def test_v17_recovery_contract_is_retained_for_prior_verified_backups(self) -> None:
        frozen = REPO / "packages/contracts/storage/sqlite-migration-recovery-v17.snapshot.json"
        raw = frozen.read_bytes()
        self.assertEqual(
            "4388b3b35df43204ead46972d4fff67670084a5f82d40b046a09bc6a6fdb4d2a",
            hashlib.sha256(raw).hexdigest(),
        )
        old = json.loads(raw)
        current = json.loads(
            (REPO / "packages/contracts/storage/sqlite-migration-recovery.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(17, old["properties"]["targetSchemaVersion"]["const"])
        self.assertEqual(20, current["properties"]["targetSchemaVersion"]["const"])
        self.assertEqual(SCHEMA_SHA256, old["properties"]["targetSchemaSha256"]["const"])
        self.assertEqual(storage.EXPECTED_SCHEMA_SHA256, current["properties"]["targetSchemaSha256"]["const"])
        # A structural historical witness remains interpretable by the frozen
        # contract and is rejected by the v18-only current contract.
        historical_shape = {
            "schemaVersion": "1.0",
            "documentType": "research-observatory-sqlite-migration-recovery",
            "attemptId": "a" * 32,
            "createdAt": "2026-09-30T00:00:00.000Z",
            "status": "backup-verified",
            "databaseRelativePath": "state/project.sqlite3",
            "projectId": "123e4567-e89b-42d3-a456-426614174000",
            "sourceSchemaVersion": 16,
            "targetSchemaVersion": 17,
            "migrationIds": ["0017_corpus_items"],
            "sourceSchemaSha256": "faa1dcd5823f086986ea3a86a8cc85369edd826f2a0c1d724f923bdff9f293f5",
            "targetSchemaSha256": SCHEMA_SHA256,
            "checkpoint": {"mode": "passive-under-writer-reservation", "logFrames": 0, "checkpointedFrames": 0},
            "backup": {
                "relativePath": f"state/migration-backups/v16-to-v17-{'a' * 32}/project.sqlite3",
                "sha256": "b" * 64,
                "sizeBytes": 1,
                "quickCheck": "ok",
            },
        }
        self.assertEqual([], list(Draft202012Validator(old).iter_errors(historical_shape)))
        self.assertTrue(list(Draft202012Validator(current).iter_errors(historical_shape)))

    def test_every_material_v18_interruption_retains_v17_and_allows_exact_retry(self) -> None:
        fixture = migration_fixture.SqliteMigrationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        for step in v0018_rights_policy.MATERIAL_MIGRATION_STEPS:
            with self.subTest(step=step):
                database = fixture.project / step / "state/project.sqlite3"
                project = restore_v17(database, "import-corpus")["projectId"]

                def fail(observed: str, expected: str = step) -> None:
                    if observed == expected:
                        raise ValueError("synthetic-rights-migration-interruption")

                with (
                    patch.object(v0018_rights_policy, "_migration_step_completed", side_effect=fail) as injected,
                    self.assertRaises(runner.MigrationProblem) as raised,
                ):
                    runner.migrate_database(database, expected_project_id=project)
                injected.assert_any_call(step)
                self.assertEqual(project, inspect_v17(database, "import-corpus")["projectId"])
                assert raised.exception.recovery_manifest_relative_path is not None
                manifest_path = database.parent.parent / raised.exception.recovery_manifest_relative_path
                self.assertTrue(manifest_path.is_file())
                failed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                backup = database.parent.parent / failed_manifest["backup"]["relativePath"]
                self.assertEqual(project, inspect_v17(backup, "import-corpus")["projectId"])
                result = runner.migrate_database(database, expected_project_id=project)
                self.assertEqual("migrated", result.status)
                with closing(storage.open_canonical_database(database, expected_project_id=project)) as reopened:
                    self.assertTrue(storage.database_integrity_report(reopened, expected_project_id=project).ok)

    def test_protected_v17_failure_backup_retry_and_reopen(self) -> None:
        fixture = protected_fixture.ProtectedReconciliationMigrationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        legacy = fixture.root / "legacy/state/project.sqlite3"
        project = restore_v17(legacy, "connector-corpus")["projectId"]
        with fixture.keys.active_key(project, create=True) as lease:
            material = lease.use(bytes)
        with closing(sqlcipher.connect(legacy.as_uri() + "?mode=ro", uri=True, isolation_level=None)) as source:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(fixture.database), f"x'{material.hex()}'"))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={APPLICATION_ID}")
            source.execute("PRAGMA protected.user_version=17")
            self.assertEqual("wal", source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0])
            source.execute("DETACH DATABASE protected")

        def fail(step: str) -> None:
            if step == "rights-revisions-create":
                raise ValueError("synthetic-encrypted-rights-migration-interruption")

        with (
            patch.object(v0018_rights_policy, "_migration_step_completed", side_effect=fail) as injected,
            self.assertRaises(runner.MigrationProblem) as raised,
        ):
            runner.migrate_database(fixture.database, expected_project_id=project)
        injected.assert_any_call("rights-revisions-create")
        self.assertEqual(
            17,
            runner.plan_database_migration(fixture.database, expected_project_id=project).source_schema_version,
        )
        assert raised.exception.recovery_manifest_relative_path is not None
        failed_manifest = json.loads(
            (fixture.root / raised.exception.recovery_manifest_relative_path).read_text(encoding="utf-8")
        )
        first_backup = fixture.root / failed_manifest["backup"]["relativePath"]
        for path in (fixture.database, first_backup):
            self.assertNotEqual(b"SQLite format 3\x00", path.read_bytes()[:16])
            with closing(sqlcipher.connect(path.as_uri() + "?mode=ro", uri=True)) as saved:
                saved.execute(f"PRAGMA key=\"x'{material.hex()}'\"")
                self.assertEqual(SCHEMA_SHA256, _schema_fingerprint(saved))
                self.assertEqual(ROWS_SHA256["connector-corpus"], _row_fingerprint(saved))
                self.assertEqual([], saved.execute("PRAGMA cipher_integrity_check").fetchall())
        result = runner.migrate_database(fixture.database, expected_project_id=project)
        self.assertEqual(
            (v0018_rights_policy.revision, v0019_corpus_reports.revision, v0020_corpus_source_projection.revision),
            result.migration_ids,
        )
        assert result.backup_relative_path is not None
        second_backup = fixture.root / result.backup_relative_path
        self.assertNotEqual(b"SQLite format 3\x00", second_backup.read_bytes()[:16])
        with closing(sqlcipher.connect(second_backup.as_uri() + "?mode=ro", uri=True)) as saved:
            saved.execute(f"PRAGMA key=\"x'{material.hex()}'\"")
            self.assertEqual(SCHEMA_SHA256, _schema_fingerprint(saved))
            self.assertEqual(ROWS_SHA256["connector-corpus"], _row_fingerprint(saved))
        for _ in range(2):
            with closing(storage.open_canonical_database(fixture.database, expected_project_id=project)) as current:
                report = storage.database_integrity_report(current, expected_project_id=project)
                self.assertTrue(report.ok, report.errors)
                self.assertEqual(20, report.schema_version)

    def test_import_history_can_be_exported_to_encrypted_sqlcipher_and_reopened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "plain/state/project.sqlite3"
            protected = root / "encrypted/state/project.sqlite3"
            restore_v17(source, "import-corpus")
            protected.parent.mkdir(parents=True)
            key = b"synthetic-ephemeral-v17-key".ljust(32, b"0")
            with closing(sqlcipher.connect(source.as_uri() + "?mode=ro", uri=True, isolation_level=None)) as db:
                db.execute("ATTACH DATABASE ? AS protected KEY ?", (str(protected), f"x'{key.hex()}'"))
                db.execute("SELECT sqlcipher_export('protected')").fetchone()
                db.execute(f"PRAGMA protected.application_id={APPLICATION_ID}")
                db.execute("PRAGMA protected.user_version=17")
                db.execute("DETACH DATABASE protected")
            self.assertNotEqual(b"SQLite format 3\x00", protected.read_bytes()[:16])
            with closing(sqlcipher.connect(protected.as_uri() + "?mode=ro", uri=True)) as reopened:
                reopened.execute(f"PRAGMA key=\"x'{key.hex()}'\"")
                self.assertEqual(SCHEMA_SHA256, _schema_fingerprint(reopened))
                self.assertEqual(ROWS_SHA256["import-corpus"], _row_fingerprint(reopened))
                self.assertEqual([], reopened.execute("PRAGMA cipher_integrity_check").fetchall())


class RightsV18SchemaBindingTests(unittest.TestCase):
    def test_legacy_marker_cannot_omit_a_unique_retained_source_assertion(self) -> None:
        fixture = migration_fixture.SqliteMigrationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        project = restore_v17(fixture.database, "import-corpus")["projectId"]
        runner.migrate_database(fixture.database, expected_project_id=project)
        with closing(sqlite3.connect(fixture.database, autocommit=True)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            marker = db.execute(
                "SELECT project_id,item_id,path_id,output_revision_id,detected_at FROM rights_legacy_output_rechecks"
            ).fetchone()
            assert marker is not None
            with self.assertRaisesRegex(sqlite3.IntegrityError, "legacy output recheck binding denied"):
                db.execute(
                    "INSERT INTO rights_legacy_output_rechecks "
                    "(project_id,item_id,path_id,output_revision_id,source_assertion_revision_id,"
                    "reason,disposition,detected_at) VALUES (?,?,?,?,NULL,'RIGHTS_POLICY',"
                    "'requires-review',?)",
                    (*marker[:4], marker[4]),
                )
            self.assertEqual(1, db.execute("SELECT count(*) FROM rights_legacy_output_rechecks").fetchone()[0])

    def test_retained_source_observation_cannot_be_substituted_by_direct_sql(self) -> None:
        from research_observatory_core.domain_contracts import new_uuid_v7

        from tests.rights.test_repository import RightsRepositoryTests

        fixture = RightsRepositoryTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        policy = fixture._policy()
        fixture._publish(policy)

        with closing(
            storage.open_canonical_database(fixture.corpus.database, expected_project_id=fixture.corpus.project)
        ) as db:
            saved = db.execute(
                "SELECT policy_json FROM rights_policy_revisions WHERE revision_id=?",
                (policy.revision_id,),
            ).fetchone()
            assert saved is not None
            forged = json.loads(saved[0])
            self.assertIsInstance(forged["sourceObservation"], dict)
            replacement_id = new_uuid_v7()
            forged["revisionId"] = replacement_id
            forged["predecessorRevisionId"] = policy.revision_id
            forged["sourceObservation"]["sourceSha256"] = "sha256:" + "0" * 64
            forged_json = json.dumps(forged, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO aggregate_revisions (revision_id,aggregate_id,aggregate_kind,project_id,revision,"
                "contract_version,created_at,modified_at,display_label_observed,display_label_normalized,"
                "knowledge_status,rights_status) "
                "SELECT ?,aggregate_id,aggregate_kind,project_id,revision+1,contract_version,created_at,"
                "modified_at,display_label_observed,display_label_normalized,knowledge_status,rights_status "
                "FROM aggregate_revisions WHERE revision_id=?",
                (replacement_id, policy.revision_id),
            )
            with self.assertRaises(sqlite3.DatabaseError) as denied:
                db.execute(
                    "INSERT INTO rights_policy_revisions (revision_id,policy_id,project_id,subject_sha256,"
                    "predecessor_revision_id,revision_number,policy_json,policy_sha256,command_id,"
                    "command_sha256,actor_id,occurred_at) "
                    "SELECT ?,policy_id,project_id,subject_sha256,revision_id,revision_number+1,?,?,?,?,"
                    "actor_id,occurred_at FROM rights_policy_revisions WHERE revision_id=?",
                    (
                        replacement_id,
                        forged_json,
                        hashlib.sha256(forged_json.encode("utf-8")).hexdigest(),
                        new_uuid_v7(),
                        "4" * 64,
                        policy.revision_id,
                    ),
                )
            self.assertIn(
                "rights policy revision binding denied",
                f"{denied.exception!r} {denied.exception.__cause__!r}",
            )
            db.rollback()
            self.assertEqual(
                1,
                db.execute(
                    "SELECT count(*) FROM rights_policy_revisions WHERE policy_id="
                    "(SELECT policy_id FROM rights_policy_revisions WHERE revision_id=?)",
                    (policy.revision_id,),
                ).fetchone()[0],
            )

    def test_use_decision_cannot_claim_a_substituted_policy_hash(self) -> None:
        from research_observatory_core.domain_contracts import new_uuid_v7

        from tests.rights.test_repository import RightsRepositoryTests

        fixture = RightsRepositoryTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        policy = fixture._policy()
        fixture._publish(policy)

        with closing(
            storage.open_canonical_database(fixture.corpus.database, expected_project_id=fixture.corpus.project)
        ) as db:
            row = db.execute(
                "SELECT subject_sha256 FROM rights_policy_revisions WHERE revision_id=?",
                (policy.revision_id,),
            ).fetchone()
            assert row is not None
            assertion_sha256 = db.execute(
                "SELECT payload_sha256 FROM reconciliation_assertions WHERE revision_id=?",
                (fixture.subject.source_assertion_revision_id,),
            ).fetchone()[0]
            with self.assertRaises(sqlite3.DatabaseError) as denied:
                db.execute(
                    "INSERT INTO rights_use_decisions (decision_id,event_kind,project_id,subject_sha256,"
                    "source_assertion_revision_id,source_assertion_sha256,authority_kind,policy_revision_id,"
                    "policy_sha256,actor_id,trace_id,use_action,use_sha256,decision_code,reason_code,occurred_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        new_uuid_v7(),
                        "evaluate",
                        fixture.corpus.project,
                        row[0],
                        fixture.subject.source_assertion_revision_id,
                        assertion_sha256,
                        "policy",
                        policy.revision_id,
                        "0" * 64,
                        fixture.corpus.actor.actor_id,
                        fixture.corpus.actor.trace_id,
                        fixture.use.action,
                        "a" * 64,
                        "deny",
                        "rights-denied",
                        fixture.corpus.actor.occurred_at,
                    ),
                )
            self.assertIn("rights use decision binding denied", repr(denied.exception))
            self.assertEqual(0, db.execute("SELECT count(*) FROM rights_use_decisions").fetchone()[0])

    def test_connector_source_cannot_forge_a_legacy_import_allow(self) -> None:
        from research_observatory_core.domain_contracts import new_uuid_v7

        fixture = migration_fixture.SqliteMigrationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        project = restore_v17(fixture.database, "connector-corpus")["projectId"]
        runner.migrate_database(fixture.database, expected_project_id=project)
        with closing(sqlite3.connect(fixture.database, autocommit=True)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            assertion_id, assertion_sha256 = db.execute(
                "SELECT revision_id,payload_sha256 FROM reconciliation_assertions"
            ).fetchone()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "rights use decision binding denied"):
                db.execute(
                    "INSERT INTO rights_use_decisions (decision_id,event_kind,project_id,subject_sha256,"
                    "source_assertion_revision_id,source_assertion_sha256,authority_kind,policy_revision_id,"
                    "policy_sha256,actor_id,trace_id,use_action,use_sha256,decision_code,reason_code,occurred_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        new_uuid_v7(),
                        "legacy-import-bridge",
                        project,
                        "a" * 64,
                        assertion_id,
                        assertion_sha256,
                        "legacy-import-bridge",
                        None,
                        None,
                        new_uuid_v7(),
                        "a" * 32,
                        "store",
                        "a" * 64,
                        "allow",
                        "rights-legacy-import-confirmed",
                        "2026-09-01T00:00:00.000Z",
                    ),
                )
            self.assertEqual(0, db.execute("SELECT count(*) FROM rights_use_decisions").fetchone()[0])

    def test_retained_confirmed_import_action_can_be_audited_as_legacy_bridge(self) -> None:
        from research_observatory_core.domain_contracts import new_uuid_v7

        fixture = migration_fixture.SqliteMigrationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        project = restore_v17(fixture.database, "import-corpus")["projectId"]
        runner.migrate_database(fixture.database, expected_project_id=project)
        with closing(sqlite3.connect(fixture.database, autocommit=True)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            assertion_id, assertion_sha256 = db.execute(
                "SELECT revision_id,payload_sha256 FROM reconciliation_assertions"
            ).fetchone()
            insert = (
                "INSERT INTO rights_use_decisions (decision_id,event_kind,project_id,subject_sha256,"
                "source_assertion_revision_id,source_assertion_sha256,authority_kind,policy_revision_id,"
                "policy_sha256,actor_id,trace_id,use_action,use_sha256,decision_code,reason_code,occurred_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            )
            values = (
                new_uuid_v7(),
                "legacy-import-bridge",
                project,
                "a" * 64,
                assertion_id,
                assertion_sha256,
                "legacy-import-bridge",
                None,
                None,
                new_uuid_v7(),
                "a" * 32,
                "store",
                "a" * 64,
                "allow",
                "rights-legacy-import-confirmed",
                "2026-09-01T00:00:00.000Z",
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "rights use decision binding denied"):
                db.execute(insert, (*values[:5], "0" * 64, *values[6:]))
            db.execute(insert, values)
            self.assertEqual(1, db.execute("SELECT count(*) FROM rights_use_decisions").fetchone()[0])
