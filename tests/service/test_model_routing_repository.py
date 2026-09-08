from __future__ import annotations

import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.model_registry_contracts import canonical_bytes, canonical_hash  # noqa: E402
from research_observatory_core.model_registry_repository import SqliteModelRoutingRepository  # noqa: E402
from research_observatory_core.model_routing_contracts import (  # noqa: E402
    CircuitState,
    RoutingEvent,
    RoutingPolicy,
    RoutingRun,
)
from research_observatory_core.ports.repositories import RepositoryConflict, RepositoryTransactionFailed  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    CanonicalConnection,
    configure_protected_database_provider,
    initialize_database,
    open_canonical_database,
)

from tests.ai.test_model_registry import task  # noqa: E402
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402
from tests.service.test_model_registry_repository import PROJECT, STAMP  # noqa: E402


class ModelRoutingRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-routing-fixture-")
        self.root = Path(self.temporary.name).resolve()
        (self.root / "state").mkdir()
        (self.root / ".tmp").mkdir()
        self.database = self.root / "state/project.sqlite3"
        configure_protected_database_provider(InMemoryDatabaseKeyProvider())
        self.assertTrue(initialize_database(self.database, project_id=PROJECT, project_created_at=STAMP).ok)
        self.actor = new_uuid_v7()
        self.repository = SqliteModelRoutingRepository(self.database, PROJECT, self.actor)
        document = task()
        self.routing_run = RoutingRun(
            project_id=PROJECT,
            task_id=document["taskId"],
            task_hash=canonical_hash(document),
            task_json=canonical_bytes(document).decode(),
            policy=RoutingPolicy(project_id=PROJECT, revision=1),
            session_id=new_uuid_v7(),
            events=(RoutingEvent(event_id=new_uuid_v7(), kind="admitted", occurred_at_ms=1500),),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_protected_admission_and_history_survive_restart_without_rewriting_request(self):
        stored, admitted = self.repository.admit(self.routing_run)
        self.assertTrue(admitted)
        event = RoutingEvent(event_id=new_uuid_v7(), kind="routes", occurred_at_ms=1501)
        updated = self.repository.append(stored.task_id, expected_revision=1, event=event)
        restarted = SqliteModelRoutingRepository(self.database, PROJECT, self.actor)
        self.assertEqual(updated, restarted.read(stored.task_id))
        self.assertEqual((updated, False), restarted.admit(self.routing_run))
        self.assertEqual(self.routing_run.task_json, updated.task_json)
        self.assertNotEqual(b"SQLite format 3\0", self.database.read_bytes()[:16])
        connection = open_canonical_database(self.database, expected_project_id=PROJECT)
        try:
            for table in ("provenance_events", "outbox_events"):
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE event_type LIKE 'model.routing.%'"
                ).fetchone()[0]
                self.assertEqual(2, count)
        finally:
            connection.close()

    def test_duplicate_and_concurrent_admission_have_one_owner_and_changed_request_conflicts(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: self.repository.admit(self.routing_run), range(2)))
        self.assertEqual(1, sum(admitted for _, admitted in outcomes))
        changed = self.routing_run.model_copy(update={"policy": RoutingPolicy(project_id=PROJECT, revision=2)})
        with self.assertRaises(RepositoryConflict):
            self.repository.admit(changed)
        with self.assertRaises(RepositoryConflict):
            SqliteModelRoutingRepository(self.database, PROJECT, new_uuid_v7()).admit(self.routing_run)

    def test_atomic_failure_retains_predecessor_and_cas_rejects_stale_append(self):
        self.repository.admit(self.routing_run)
        event = RoutingEvent(event_id=new_uuid_v7(), kind="routes", occurred_at_ms=1501)
        with (
            patch.object(self.repository, "_append_audit", side_effect=OSError("synthetic fault")),
            self.assertRaises(RepositoryTransactionFailed),
        ):
            self.repository.append(self.routing_run.task_id, expected_revision=1, event=event)
        self.assertEqual(self.routing_run, self.repository.read(self.routing_run.task_id))
        self.repository.append(self.routing_run.task_id, expected_revision=1, event=event)
        with self.assertRaises(RepositoryConflict):
            self.repository.append(self.routing_run.task_id, expected_revision=1, event=event)

    def test_session_open_and_atomic_commit_failures_are_redacted_and_recoverable(self):
        with (
            patch(
                "research_observatory_core.model_registry_repository.open_canonical_database",
                side_effect=OSError("synthetic-sensitive-location"),
            ),
            self.assertRaisesRegex(RepositoryTransactionFailed, "model routing persistence failed"),
            self.repository.session(),
        ):
            self.fail("failed open must not enter the session")
        original = CanonicalConnection.execute

        def fail_commit(connection, statement, *args, **kwargs):
            if statement == "COMMIT":
                raise OSError("synthetic-sensitive-location")
            return original(connection, statement, *args, **kwargs)

        with self.repository.session():
            with (
                patch.object(CanonicalConnection, "execute", fail_commit),
                self.assertRaisesRegex(RepositoryTransactionFailed, "model routing persistence failed"),
                self.repository.atomic(),
            ):
                self.repository.admit(self.routing_run)
            self.assertIsNone(self.repository.read(self.routing_run.task_id))
            # A failed transaction must not leak its atomic/session state.
            with self.repository.atomic():
                self.repository.admit(self.routing_run)
        self.assertEqual(self.routing_run, self.repository.read(self.routing_run.task_id))

    def test_circuit_cas_and_pending_attempt_survive_restart(self):
        digest = "sha256:" + "1" * 64
        state = CircuitState(manifest_hash=digest, revision=1, active_attempt_id=new_uuid_v7(), trace_id="a" * 32)
        self.assertEqual(state, self.repository.change_circuit(state, expected_revision=0))
        restarted = SqliteModelRoutingRepository(self.database, PROJECT, self.actor)
        self.assertEqual(state, restarted.circuit(digest))
        with self.assertRaises(RepositoryConflict):
            restarted.change_circuit(state, expected_revision=0)

    def test_circuit_release_needs_exact_attempt_trace_and_admission_actor(self):
        digest = "sha256:" + "1" * 64
        attempt = new_uuid_v7()
        state = CircuitState(manifest_hash=digest, revision=1, active_attempt_id=attempt, trace_id="a" * 32)
        self.repository.change_circuit(state, expected_revision=0)
        released = CircuitState(manifest_hash=digest, revision=2, trace_id="a" * 32)
        with self.assertRaises(RepositoryConflict):
            self.repository.change_circuit(released, expected_revision=1, expected_attempt_id=new_uuid_v7())
        with self.assertRaises(RepositoryConflict):
            self.repository.change_circuit(
                released.model_copy(update={"trace_id": "b" * 32}), expected_revision=1, expected_attempt_id=attempt
            )
        with self.assertRaises(RepositoryConflict):
            SqliteModelRoutingRepository(self.database, PROJECT, new_uuid_v7()).change_circuit(
                released, expected_revision=1, expected_attempt_id=attempt
            )
        self.assertEqual(state, self.repository.circuit(digest))
        self.assertEqual(
            released, self.repository.change_circuit(released, expected_revision=1, expected_attempt_id=attempt)
        )

    def test_competing_circuit_reservations_have_only_one_winner(self):
        digest = "sha256:" + "2" * 64
        states = [
            CircuitState(manifest_hash=digest, revision=1, active_attempt_id=new_uuid_v7(), trace_id="c" * 32)
            for _ in range(2)
        ]

        def reserve(state):
            try:
                return self.repository.change_circuit(state, expected_revision=0)
            except RepositoryConflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(reserve, states))
        self.assertEqual(1, sum(outcome is not None for outcome in outcomes))
        self.assertIn(self.repository.circuit(digest), states)

    def test_large_valid_request_roundtrips_all_chunks(self):
        document = json.loads(self.routing_run.task_json)
        reference = document["input"]["context"][0]
        document["taskKind"] = "embedding"
        document["input"] = {
            "kind": "embedding",
            "items": [reference | {"revisionId": new_uuid_v7()} for _ in range(500)],
        }
        large = RoutingRun.model_validate(
            self.routing_run.model_dump()
            | {
                "task_json": canonical_bytes(document).decode(),
                "task_hash": canonical_hash(document),
            }
        )
        self.assertGreater(len(large.task_json), 65_536)
        self.repository.admit(large)
        self.assertEqual(large, self.repository.read(large.task_id))

    def test_corrupt_latest_journal_cannot_look_empty_or_replay_old_state(self):
        self.repository.admit(self.routing_run)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT)
        try:
            connection.execute(
                "INSERT INTO settings (setting_id, project_id, setting_key, revision, value_type, "
                "text_value, created_at, modified_at) VALUES (?, ?, ?, 2, 'text', '{}', ?, ?)",
                (new_uuid_v7(), PROJECT, f"routing.{self.routing_run.task_id}.events.head", STAMP, STAMP),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(RepositoryTransactionFailed):
            self.repository.read(self.routing_run.task_id)
        with self.assertRaises(RepositoryTransactionFailed):
            self.repository.admit(self.routing_run)

    def test_verified_run_reuse_stops_at_commit_and_rollback(self):
        event = RoutingEvent(event_id=new_uuid_v7(), kind="routes", occurred_at_ms=1501)
        with self.repository.session():
            with patch.object(self.repository, "_read_document", wraps=self.repository._read_document) as read:
                with self.repository.atomic():
                    self.repository.admit(self.routing_run)
                    stored = self.repository.append(self.routing_run.task_id, expected_revision=1, event=event)
                    self.assertEqual(stored, self.repository.read(self.routing_run.task_id))
                    self.assertEqual(0, read.call_count)
                self.assertIsNone(self.repository._transaction_runs.get())
                self.assertEqual(stored, self.repository.read(self.routing_run.task_id))
                self.assertGreater(read.call_count, 0)
            # A failed later operation cannot leave its uncommitted revision in
            # the memo consulted by the following transaction.
            with self.assertRaisesRegex(ValueError, "synthetic caller failure"), self.repository.atomic():
                self.repository.append(
                    self.routing_run.task_id,
                    expected_revision=2,
                    event=RoutingEvent(event_id=new_uuid_v7(), kind="routes", occurred_at_ms=1502),
                )
                raise ValueError("synthetic caller failure")
            self.assertIsNone(self.repository._transaction_runs.get())
            self.assertEqual(stored, self.repository.read(self.routing_run.task_id))
            connection = open_canonical_database(self.database, expected_project_id=PROJECT)
            try:
                connection.execute(
                    "INSERT INTO settings (setting_id, project_id, setting_key, revision, value_type, "
                    "text_value, created_at, modified_at) VALUES (?, ?, ?, 3, 'text', '{}', ?, ?)",
                    (new_uuid_v7(), PROJECT, f"routing.{self.routing_run.task_id}.events.head", STAMP, STAMP),
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(RepositoryTransactionFailed), self.repository.atomic():
                self.repository.read(self.routing_run.task_id)


if __name__ == "__main__":
    unittest.main()
