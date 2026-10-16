"""Canonical sequence and generation invariants; in-memory DDL proof only."""

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.search.canonical_schema import DDL  # noqa: E402

PROJECT = "0199e895-0000-7000-8000-000000000001"
EVENT = "0199e895-0000-7000-8000-000000000002"


class IndexCanonicalSchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA trusted_schema=OFF")
        self.db.executescript(
            "CREATE TABLE projects(project_id TEXT PRIMARY KEY);"
            "CREATE TABLE outbox_events(outbox_id TEXT PRIMARY KEY,project_id TEXT,revision_id TEXT,event_type "
            "TEXT,occurred_at TEXT,record_sha256 TEXT);"
        )
        self.db.execute("INSERT INTO projects VALUES(?)", (PROJECT,))
        for statement in DDL:
            self.db.execute(statement)

    def outbox(self, event=EVENT):
        self.db.execute(
            "INSERT INTO outbox_events VALUES(?,?,NULL,'synthetic.changed','2026-10-16T00:00:00.000Z',?)",
            (event, PROJECT, "a" * 64),
        )

    def test_commit_rollback_and_immutable_explicit_sequence(self):
        self.db.execute("BEGIN")
        self.outbox()
        self.assertEqual((1, EVENT), self.db.execute("SELECT sequence,outbox_id FROM search_changes").fetchone())
        self.db.execute("ROLLBACK")
        self.assertEqual(0, self.db.execute("SELECT count(*) FROM search_changes").fetchone()[0])
        self.outbox()
        self.outbox("0199e895-0000-7000-8000-000000000003")
        self.assertEqual(
            [(1,), (2,)], self.db.execute("SELECT sequence FROM search_changes ORDER BY sequence").fetchall()
        )
        for statement in ("DELETE FROM search_changes", "UPDATE search_changes SET sequence=100"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(statement)

    def test_change_record_cannot_substitute_source_authority(self):
        self.outbox()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO search_changes(project_id,outbox_id,revision_id,event_type,occurred_at,record_sha256) "
                "VALUES(?,?,NULL,'substituted','2026-10-16T00:00:00.000Z',?)",
                (PROJECT, "0199e895-0000-7000-8000-000000000099", "a" * 64),
            )

    def generation(self):
        self.outbox()
        self.db.execute(
            "INSERT INTO search_generations VALUES(?,?,'lexical-fts5-v1','ro-unicode61-diacritics2-1',1,?,?,?,?,?,?,?)",
            (EVENT, PROJECT, "1" * 32, "2" * 32, "a" * 64, 1, "a" * 64, "b" * 64, "2026-10-16T00:00:00.000Z"),
        )
        self.db.execute(
            "INSERT INTO search_generation_leases VALUES(?,?,?,?,?,?,?)",
            (
                EVENT,
                PROJECT,
                "a" * 64,
                1,
                "2026-10-16T00:00:00.000Z",
                "2026-10-16T00:00:00.000Z",
                "2026-10-16T00:00:30.000Z",
            ),
        )

    def event(self, number, stage, checkpoint, previous=None, owner="a", epoch=1):
        identity = f"0199e895-0000-7000-8000-{number:012d}"
        self.db.execute(
            "INSERT INTO search_generation_events(event_id,generation_id,project_id,previous_event_id,stage,checkpoint,"
            "cursor_item_id,owner_sha256,lease_epoch,authority_sha256,projection_sha256,entry_count,record_sha256"
            ",occurred_at) VALUES(?,?,?,?,?,?,NULL,?,?,?,?,?,?,?)",
            (
                identity,
                EVENT,
                PROJECT,
                previous,
                stage,
                checkpoint,
                owner * 64,
                epoch,
                "a" * 64,
                "c" * 64 if stage == "Ready" else None,
                0 if stage == "Ready" else None,
                "b" * 64,
                "2026-10-16T00:00:05.000Z",
            ),
        )
        return identity

    def test_generation_stale_owner_and_illegal_ready_checkpoint_denied(self):
        self.generation()
        first = self.event(10, "Building", 0)
        with self.assertRaises(sqlite3.IntegrityError):
            self.event(11, "Ready", 0, first)
        second = self.event(12, "Incomplete", 0, first)
        self.db.execute(
            "UPDATE search_generation_leases SET owner_sha256=?,epoch=2,issued_at=?,renewed_at=?,expires_at=? "
            "WHERE generation_id=?",
            ("b" * 64, "2026-10-16T00:00:05.000Z", "2026-10-16T00:00:05.000Z", "2026-10-16T00:00:40.000Z", EVENT),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.event(13, "Building", 1, second)
        resumed = self.event(14, "Building", 1, second, owner="b", epoch=2)
        self.event(15, "Ready", 1, resumed, owner="b", epoch=2)

    def test_only_ready_head_and_expected_selection_chain_can_be_promoted(self):
        self.generation()
        first = self.event(10, "Building", 0)
        insert = "INSERT INTO search_selections VALUES(?,?,0,NULL,?,?,?,?,?,?)"
        values = (
            "0199e895-0000-7000-8000-000000000020",
            PROJECT,
            EVENT,
            first,
            0,
            "a" * 64,
            "b" * 64,
            "2026-10-16T00:00:06.000Z",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(insert, values)
        ready = self.event(11, "Ready", 1, first)
        values = (*values[:3], ready, 1, *values[5:])
        self.db.execute(insert, values)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(insert, ("0199e895-0000-7000-8000-000000000021", *values[1:]))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM search_selections")

    def test_live_generation_lease_cannot_be_stolen_before_expiry(self):
        self.generation()
        self.event(10, "Building", 0)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE search_generation_leases SET "
                "owner_sha256=?,epoch=2,issued_at=?,renewed_at=?,expires_at=? WHERE generation_id=?",
                ("b" * 64, "2026-10-16T00:00:04.000Z", "2026-10-16T00:00:04.000Z", "2026-10-16T00:00:40.000Z", EVENT),
            )

    def test_replace_cannot_resequence_history_even_when_recursive_triggers_off(self):
        self.db.execute("PRAGMA recursive_triggers=OFF")
        self.outbox()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT OR REPLACE INTO search_changes(sequence,project_id,outbox_id,revision_id,event_type,occur"
                "red_at,record_sha256) "
                "SELECT 99,project_id,outbox_id,revision_id,event_type,occurred_at,record_sha256 FROM search_changes"
            )
        self.assertEqual((1,), self.db.execute("SELECT sequence FROM search_changes").fetchone())

    def test_lease_identity_cannot_be_deleted_and_reinserted(self):
        self.generation()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM search_generation_leases")

    def test_generation_event_time_cannot_move_backwards(self):
        self.generation()
        first = self.event(10, "Building", 0)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO search_generation_events(event_id,generation_id,project_id,previous_event_id,stage,c"
                "heckpoint,"
                "cursor_item_id,owner_sha256,lease_epoch,authority_sha256,record_sha256,occurred_at) "
                "VALUES(?,?,?,?,?,?,NULL,?,?,?,?,?)",
                (
                    "0199e895-0000-7000-8000-000000000099",
                    EVENT,
                    PROJECT,
                    first,
                    "Building",
                    0,
                    "a" * 64,
                    1,
                    "a" * 64,
                    "b" * 64,
                    "2026-10-16T00:00:01.000Z",
                ),
            )

    def test_lease_cannot_be_renewed_after_expiry_or_replaced(self):
        self.generation()
        for statement in (
            "UPDATE search_generation_leases SET "
            "renewed_at='2026-10-16T00:00:31.000Z',expires_at='2026-10-16T00:01:00.000Z'",
            "INSERT OR REPLACE INTO search_generation_leases SELECT * FROM search_generation_leases",
        ):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(statement)

    def test_exact_control_events_do_not_self_schedule_but_scholarly_changes_do(self):
        values = (PROJECT, "2026-10-16T00:00:00.000Z", "a" * 64)
        self.db.execute("INSERT INTO outbox_events VALUES(?, ?,NULL,'search.index-checkpoint',?,?)", (EVENT, *values))
        self.assertEqual(0, self.db.execute("SELECT count(*) FROM search_changes").fetchone()[0])
        self.db.execute(
            "INSERT INTO outbox_events VALUES(?, ?,?,'search.index-checkpoint',?,?)",
            ("0199e895-0000-7000-8000-000000000003", PROJECT, EVENT, *values[1:]),
        )
        self.assertEqual(1, self.db.execute("SELECT count(*) FROM search_changes").fetchone()[0])

    def test_new_source_change_prevents_promotion_of_old_ready_watermark(self):
        self.generation()
        building = self.event(10, "Building", 0)
        ready = self.event(11, "Ready", 1, building)
        self.outbox("0199e895-0000-7000-8000-000000000003")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO search_selections VALUES(?,?,0,NULL,?,?,?,?,?,?)",
                (
                    "0199e895-0000-7000-8000-000000000020",
                    PROJECT,
                    EVENT,
                    ready,
                    1,
                    "a" * 64,
                    "b" * 64,
                    "2026-10-16T00:00:06.000Z",
                ),
            )


if __name__ == "__main__":
    unittest.main()
