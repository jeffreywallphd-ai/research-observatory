"""Typed observation classification invariants; in-memory DDL, not Native proof."""

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from tests.search import test_search_run_values as fixtures  # noqa: E402

PROJECT = "0199e895-0000-7000-8000-000000000001"
JOB = "0199e895-0000-7000-8000-000000000020"
REVISION = "0199e895-0000-7000-8000-000000000021"
AGGREGATE = "0199e895-0000-7000-8000-000000000022"
OUTBOX = "0199e895-0000-7000-8000-000000000023"
NOW = "2026-10-16T00:00:00.000Z"


class SearchRunSchemaTests(unittest.TestCase):
    def setUp(self):
        from research_observatory_core.search.run_schema import DDL

        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.executescript(
            "PRAGMA foreign_keys=ON; PRAGMA trusted_schema=OFF;"
            "CREATE TABLE projects(project_id TEXT PRIMARY KEY);"
            "CREATE TABLE workflow_queue_jobs(job_id TEXT PRIMARY KEY,project_id TEXT,activity_type TEXT);"
            "CREATE TABLE aggregate_revisions(revision_id TEXT PRIMARY KEY,aggregate_kind TEXT,project_id TEXT,"
            "aggregate_id TEXT, UNIQUE(revision_id,aggregate_kind,project_id));"
            "CREATE TABLE outbox_events(outbox_id TEXT PRIMARY KEY,project_id TEXT,revision_id TEXT,event_type TEXT,"
            "occurred_at TEXT,record_sha256 TEXT);"
            "CREATE TABLE workflow_committed_outputs(job_id TEXT PRIMARY KEY,project_id TEXT,outbox_id TEXT,"
            "output_manifest_json TEXT);"
            "CREATE TABLE search_changes(sequence INTEGER PRIMARY KEY,project_id TEXT,outbox_id TEXT,"
            "revision_id TEXT,event_type TEXT,record_sha256 TEXT);"
            "CREATE TABLE import_draft_revisions(project_id TEXT,preview_id TEXT);"
            "CREATE TABLE import_record_decisions(project_id TEXT,preview_id TEXT);"
            "CREATE TABLE import_preview_events(project_id TEXT,preview_id TEXT);"
            "CREATE TABLE object_records(project_id TEXT,object_sha256 TEXT,byte_length INTEGER,media_type TEXT,"
            "rights_status TEXT,protection_profile TEXT,retention_class TEXT,storage_state TEXT,envelope_version TEXT,"
            "key_version TEXT,wrapped_key TEXT,wrap_nonce TEXT,ciphertext_byte_length INTEGER,verified_at TEXT);"
        )
        for statement in DDL:
            self.db.execute(statement)
        self.db.execute("INSERT INTO projects VALUES(?)", (PROJECT,))
        self.db.execute("INSERT INTO workflow_queue_jobs VALUES(?,?,'lexical-search')", (JOB, PROJECT))
        self.db.execute("INSERT INTO aggregate_revisions VALUES(?,'workflow',?,?)", (REVISION, PROJECT, AGGREGATE))
        self.request = fixtures.SearchRunValueTests().request()
        self.db.execute(
            "INSERT INTO search_lexical_jobs VALUES(?,?,?,?,?,?,?,?)",
            (
                JOB,
                PROJECT,
                self.request.command_id,
                self.request.model_dump_json(by_alias=True),
                self.request.configuration_hash[7:],
                self.request.actor_id,
                self.request.session_id,
                NOW,
            ),
        )

    def run_node(self):
        from research_observatory_core.search.run_values import SearchRunContent, content_sha256

        identity = {
            "projectId": PROJECT,
            "generationId": "0199e895-0000-7000-8000-000000000030",
            "selectionId": "0199e895-0000-7000-8000-000000000031",
            "generationEventId": "0199e895-0000-7000-8000-000000000032",
            "generationConfigurationSha256": "a" * 64,
            "projectionSha256": "b" * 64,
            "sourceWatermark": 0,
            "sourceAuthorityEpoch": 0,
            "rightsTimePartition": 0,
            "validatedAt": NOW,
            "authoritySha256": "c" * 64,
            "actorSha256": "d" * 64,
            "lifecycleSha256": "e" * 64,
            "canonicalKeyVersion": "1" * 32,
            "derivativeKeyVersion": "2" * 32,
            "earliestRightsExpiry": None,
            "inputSha256": "f" * 64,
            "sourceSetSha256": "0" * 64,
        }
        content = SearchRunContent.model_validate_json(
            json.dumps(
                {
                    "searchRunId": AGGREGATE,
                    "projectId": PROJECT,
                    "jobId": JOB,
                    "attemptId": "0199e895-0000-7000-8000-000000000033",
                    "requestSha256": self.request.configuration_hash[7:],
                    "request": self.request.model_dump(mode="json", by_alias=True),
                    "inputs": identity,
                    "sourceRoots": [],
                    "resultCount": 1,
                    "resultSha256": "9" * 64,
                    "executedAt": NOW,
                }
            )
        )
        digest = content_sha256(content)
        self.db.execute(
            "INSERT INTO search_lexical_runs(revision_id,project_id,job_id,search_run_id,payload_sha256,run_json) "
            "VALUES(?,?,?,?,?,?)",
            (REVISION, PROJECT, JOB, AGGREGATE, digest, content.model_dump_json(by_alias=True)),
        )
        return digest

    def event(self, sequence, outbox, kind):
        self.db.execute(
            "INSERT INTO outbox_events VALUES(?,?,?,?,?,?)", (outbox, PROJECT, REVISION, kind, NOW, "a" * 64)
        )
        self.db.execute(
            "INSERT INTO search_changes VALUES(?,?,?,?,?,?)", (sequence, PROJECT, outbox, REVISION, kind, "a" * 64)
        )

    def test_actual_run_and_single_search_output_completion_preserve_raw_history_without_input_drift(self):
        from research_observatory_core.lexical_input_repository import lexical_watermark

        digest = self.run_node()
        self.event(1, OUTBOX, "org.research-observatory.workflow.revision-recorded.v1")
        self.assertEqual(1, lexical_watermark(self.db, PROJECT))
        self.db.execute(
            "INSERT INTO search_observation_events VALUES(?,?,?,?,?,'node-created')",
            (OUTBOX, PROJECT, REVISION, "a" * 64, digest),
        )
        self.assertEqual(0, lexical_watermark(self.db, PROJECT))
        completed = "0199e895-0000-7000-8000-000000000024"
        self.event(2, completed, "org.research-observatory.workflow.job-succeeded.v1")
        output = {
            "artifactId": AGGREGATE,
            "revisionId": REVISION,
            "provenanceEntityId": AGGREGATE,
            "mediaType": "application/vnd.research-observatory.lexical-search-run+json",
            "contentHash": "sha256:" + "b" * 64,
        }
        self.db.execute(
            "INSERT INTO workflow_committed_outputs VALUES(?,?,?,?)",
            (JOB, PROJECT, completed, json.dumps({"outputs": [output]})),
        )
        self.db.execute(
            "INSERT INTO search_observation_events VALUES(?,?,?,?,?,'job-completed')",
            (completed, PROJECT, REVISION, "a" * 64, digest),
        )
        self.assertEqual(0, lexical_watermark(self.db, PROJECT))
        self.assertEqual(2, self.db.execute("SELECT count(*) FROM search_changes").fetchone()[0])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM search_observation_events")
        # The read predicate authenticates the exact completion too. A mixed
        # output or corrupted binding cannot inherit the typed run exclusion.
        self.db.execute(
            "UPDATE workflow_committed_outputs SET output_manifest_json=?",
            (json.dumps({"outputs": [output, {**output, "artifactId": completed}]}),),
        )
        self.assertEqual(2, lexical_watermark(self.db, PROJECT))

    def test_mixed_completion_cannot_be_classified_as_observation(self):
        digest = self.run_node()
        self.event(1, OUTBOX, "org.research-observatory.workflow.job-succeeded.v1")
        output = {
            "artifactId": AGGREGATE,
            "revisionId": REVISION,
            "provenanceEntityId": AGGREGATE,
            "mediaType": "application/vnd.research-observatory.lexical-search-run+json",
        }
        self.db.execute(
            "INSERT INTO workflow_committed_outputs VALUES(?,?,?,?)",
            (JOB, PROJECT, OUTBOX, json.dumps({"outputs": [output, output]})),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO search_observation_events VALUES(?,?,?,?,?,'job-completed')",
                (OUTBOX, PROJECT, REVISION, "a" * 64, digest),
            )

    def test_unknown_or_forged_observation_cannot_hide_a_source_change(self):
        from research_observatory_core.lexical_input_repository import lexical_watermark

        self.db.execute(
            "INSERT INTO outbox_events VALUES(?,?,?,'record.updated',?,?)", (OUTBOX, PROJECT, REVISION, NOW, "a" * 64)
        )
        self.db.execute(
            "INSERT INTO search_changes VALUES(1,?,?,?,'record.updated',?)", (PROJECT, OUTBOX, REVISION, "a" * 64)
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO search_observation_events VALUES(?,?,?,?,?,'node-created')",
                (OUTBOX, PROJECT, REVISION, "a" * 64, "b" * 64),
            )
        self.assertEqual(1, lexical_watermark(self.db, PROJECT))
        self.assertEqual(1, self.db.execute("SELECT count(*) FROM search_changes").fetchone()[0])

    def test_request_is_strict_immutable_and_bound_to_actual_activity_and_principal(self):
        for command in ("UPDATE search_lexical_jobs SET actor_id='forged'", "DELETE FROM search_lexical_jobs"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(command)
        self.db.execute("INSERT INTO workflow_queue_jobs VALUES(?,?,'different-activity')", (OUTBOX, PROJECT))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO search_lexical_jobs VALUES(?,?,?,?,?,?,?,?)",
                (
                    OUTBOX,
                    PROJECT,
                    OUTBOX,
                    self.request.model_dump_json(by_alias=True),
                    self.request.configuration_hash[7:],
                    self.request.actor_id,
                    self.request.session_id,
                    NOW,
                ),
            )


if __name__ == "__main__":
    unittest.main()
