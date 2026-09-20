"""Production commit DDL against synthetic parent rows; not runtime authority proof."""

import sqlite3
import unittest

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.storage import IMPORT_COMMIT_DDL

NOW = "2026-08-30T12:03:00.000Z"
PROJECT = "01900000-0000-7000-8000-000000000001"


class ImportCommitConstraintTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", autocommit=True)
        self.addCleanup(self.db.close)
        self.db.execute("PRAGMA foreign_keys=ON")
        for sql in (
            "CREATE TABLE workflow_queue_jobs (job_id PRIMARY KEY, project_id, current_attempt_id, state, "
            "cancellation_requested_at, activity_type)",
            "CREATE TABLE workflow_job_attempts (attempt_id PRIMARY KEY, job_id, project_id, state)",
            "CREATE TABLE import_draft_revisions (preview_id, project_id, revision, attempt_id, "
            "UNIQUE(preview_id, project_id, revision, attempt_id))",
            "CREATE TABLE import_parse_records (preview_id, project_id, attempt_id, ordinal, record_key, "
            "UNIQUE(preview_id, project_id, attempt_id, ordinal, record_key))",
            "CREATE TABLE import_parse_completions (preview_id, project_id, attempt_id, source_sha256, record_count)",
            "CREATE TABLE aggregate_revisions (revision_id, project_id, aggregate_id, aggregate_kind, revision, "
            "UNIQUE(revision_id, project_id))",
            *IMPORT_COMMIT_DDL,
        ):
            self.db.execute(sql)

    def insert(self, table, values):
        self.db.execute(f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values)

    def prepare(self, previous=None):
        attempt, job, preview, parse = (new_uuid_v7() for _ in range(4))
        self.insert("workflow_queue_jobs", (job, PROJECT, attempt, "running", None, "local-import-commit"))
        self.insert("workflow_job_attempts", (attempt, job, PROJECT, "running"))
        self.insert("import_draft_revisions", (preview, PROJECT, 1, parse))
        self.insert("import_parse_records", (preview, PROJECT, parse, 1, "a" * 64))
        self.insert("import_parse_completions", (preview, PROJECT, parse, "b" * 64, 1))
        self.insert("import_commit_preparations", (PROJECT, attempt, job, preview, 1, parse, previous, NOW))
        return attempt, preview, parse

    def manifest(self, previous=None, included=1):
        attempt, preview, parse = self.prepare(previous)
        row = (attempt, PROJECT, preview, parse, 1, "a" * 64, included, "{}", "[]", "c" * 64, None)
        self.insert("import_commit_rows", row)
        source = self.db.execute("SELECT revision_id FROM import_source_records").fetchone()
        if source is None:
            revision, aggregate = new_uuid_v7(), new_uuid_v7()
            self.insert("aggregate_revisions", (revision, PROJECT, aggregate, "record", 0))
            self.insert("import_source_records", (PROJECT, "b" * 64, "a" * 64, aggregate, revision, preview, parse, 1))
        else:
            revision = source[0]
        manifest, aggregate = new_uuid_v7(), new_uuid_v7()
        self.insert("aggregate_revisions", (manifest, PROJECT, aggregate, "workflow", 0))
        identity = manifest.replace("-", "") * 2
        self.insert(
            "import_manifests",
            (
                PROJECT,
                manifest,
                aggregate,
                attempt,
                preview,
                parse,
                "b" * 64,
                identity,
                "d" * 64,
                1,
                included,
                included,
                0,
                NOW,
            ),
        )
        member = [
            manifest,
            PROJECT,
            preview,
            parse,
            1,
            "a" * 64,
            revision if included else None,
            included,
            "{}",
            "[]",
            "c" * 64,
            None,
            "not-compared",
            None,
        ]
        return manifest, member

    def seal(self, manifest, member):
        self.insert("import_manifest_members", member)
        self.insert("import_manifest_seals", (manifest, PROJECT, "e" * 64, NOW))

    def test_published_decisions_must_equal_prepared_bytes(self):
        manifest, member = self.manifest()
        for index, value in ((8, '{"changed":true}'), (9, '["changed"]'), (10, "f" * 64), (11, "f" * 64)):
            with self.subTest(index=index):
                changed = list(member)
                changed[index] = value
                self.db.execute("SAVEPOINT substitution")
                try:
                    with self.assertRaises(sqlite3.IntegrityError):
                        self.insert("import_manifest_members", changed)
                finally:
                    self.db.execute("ROLLBACK TO substitution")
                    self.db.execute("RELEASE substitution")
        self.seal(manifest, member)
        for table in ("import_commit_rows", "import_manifest_members", "import_manifest_seals"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(f"DELETE FROM {table}")
        self.assertEqual([], self.db.execute("PRAGMA foreign_key_check").fetchall())

    def test_excluded_prepared_row_cannot_become_selected(self):
        _, member = self.manifest(included=0)
        member[6] = self.db.execute("SELECT revision_id FROM import_source_records").fetchone()[0]
        member[7] = 1
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert("import_manifest_members", member)

    def test_predecessor_must_be_sealed(self):
        manifest, _ = self.manifest()
        with self.assertRaises(sqlite3.IntegrityError):
            self.prepare(manifest)

    def test_comparison_requires_included_predecessor_member(self):
        previous, old = self.manifest(included=0)
        self.seal(previous, old)
        _, member = self.manifest(previous)
        member[12:] = ["unchanged", member[6]]
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert("import_manifest_members", member)

    def test_sealed_included_predecessor_allows_comparison(self):
        previous, old = self.manifest()
        self.seal(previous, old)
        manifest, member = self.manifest(previous)
        member[12:] = ["unchanged", old[6]]
        self.seal(manifest, member)
        self.assertEqual([], self.db.execute("PRAGMA foreign_key_check").fetchall())

    def test_predecessor_lookup_is_indexed_by_exact_record(self):
        plan = self.db.execute(
            "EXPLAIN QUERY PLAN SELECT 1 FROM import_manifest_members "
            "WHERE project_id=? AND manifest_revision_id=? AND included=1 AND source_record_revision_id=?",
            (PROJECT, new_uuid_v7(), new_uuid_v7()),
        ).fetchall()
        self.assertTrue(any("source_record_revision_id=?" in row[3] for row in plan), plan)
