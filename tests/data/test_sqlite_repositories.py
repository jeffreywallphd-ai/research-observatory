from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
TOOLS = REPO / "tools"
sys.path.insert(0, str(SERVICE_SRC))
sys.path.insert(0, str(TOOLS))

from architecture_check import core_data_boundary_errors  # noqa: E402
from research_observatory_core.ports.repositories import (  # noqa: E402
    AggregateKind,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    RepositoryConflict,
    RepositoryNotFound,
    RepositoryProblem,
    RepositoryTransactionFailed,
)
from research_observatory_core.projects import ProjectLifecycleService  # noqa: E402
from research_observatory_core.repositories import create_sqlite_unit_of_work_factory  # noqa: E402
from research_observatory_core.storage import initialize_database, open_canonical_database  # noqa: E402

PROJECT_ID = "01890f6e-6a40-4cc5-98b7-123456789abc"
CREATED_AT = "2026-08-18T01:00:00.000Z"


def draft(index: int, *, aggregate_id: str = "01890f6e-6a40-7cc5-98b7-000000000101") -> AggregateRevisionDraft:
    return AggregateRevisionDraft(
        revision_id=f"01890f6e-6a40-7cc5-98b7-{index:012x}",
        aggregate_id=aggregate_id,
        aggregate_kind="record",
        created_at=CREATED_AT,
        modified_at=f"2026-08-18T01:00:{index:02d}.000Z",
        display_label_observed=f"Record revision {index}",
        display_label_normalized=None,
        knowledge_status="observed",
        rights_status="unknown",
    )


def event(index: int, *, key: str | None = None) -> AtomicRepositoryEvent:
    return AtomicRepositoryEvent(
        event_id=f"01890f6e-6a40-7cc5-98b7-{index + 100:012x}",
        outbox_id=f"01890f6e-6a40-7cc5-98b7-{index + 200:012x}",
        event_type="record.revised" if index else "record.created",
        occurred_at=f"2026-08-18T01:01:{index:02d}.000Z",
        available_at=f"2026-08-18T01:01:{index:02d}.000Z",
        trace_id=f"{index + 1:032x}",
        actor_type="human",
        actor_id="human.repository-test",
        idempotency_key=key or f"record-write-{index}",
    )


class SqliteRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.state = self.root / "state"
        self.state.mkdir()
        self.database = self.state / "project.sqlite3"
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        self.factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_revision_provenance_and_outbox_commit_atomically_and_survive_reopen(self) -> None:
        with self.factory() as unit:
            created = unit.aggregates.append(draft(1), event(0), expected_revision=None)
            self.assertEqual(0, created.revision)
            unit.commit()

        with self.factory() as unit:
            loaded = unit.aggregates.get(created.aggregate_id)
            self.assertEqual(created, loaded)
            revised = unit.aggregates.append(draft(2), event(1), expected_revision=0)
            self.assertEqual(1, revised.revision)
            unit.commit()

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(2, connection.execute("SELECT count(*) FROM aggregate_revisions").fetchone()[0])
            self.assertEqual(2, connection.execute("SELECT count(*) FROM provenance_events").fetchone()[0])
            self.assertEqual(2, connection.execute("SELECT count(*) FROM outbox_events").fetchone()[0])
            digests = connection.execute("SELECT record_sha256 FROM provenance_events ORDER BY occurred_at").fetchall()
            outbox_digests = connection.execute(
                "SELECT record_sha256 FROM outbox_events ORDER BY occurred_at"
            ).fetchall()
            self.assertEqual([row[0] for row in digests], [row[0] for row in outbox_digests])
        finally:
            connection.close()

    def test_project_creation_relocation_restart_and_repository_port_handoff(self) -> None:
        projects = self.root / "projects"
        projects.mkdir()
        lifecycle = ProjectLifecycleService()
        created_project = lifecycle.create(
            parent_directory=str(projects),
            directory_name="portable-study",
            display_name="Portable Study",
            template_id="theory-synthesis",
            trace_id="a" * 32,
        )
        original_root = Path(created_project.root)
        factory = create_sqlite_unit_of_work_factory(
            original_root / "state" / "project.sqlite3", created_project.project_id
        )
        with factory() as unit:
            created_revision = unit.aggregates.append(draft(1), event(0), expected_revision=None)
            unit.commit()

        relocated_root = projects / "relocated-study"
        original_root.rename(relocated_root)
        restarted = ProjectLifecycleService()
        opened_project = restarted.open(root=str(relocated_root), trace_id="b" * 32)
        self.assertEqual(created_project.project_id, opened_project.project_id)

        restarted_factory = create_sqlite_unit_of_work_factory(
            relocated_root / "state" / "project.sqlite3", opened_project.project_id
        )
        with restarted_factory() as unit:
            self.assertEqual(created_revision, unit.aggregates.get(created_revision.aggregate_id))
            unit.rollback()
        restarted.close(root=str(relocated_root), trace_id="c" * 32)
        self.assertFalse((relocated_root / ".locks" / "session.lock").exists())

    def test_critical_lookup_and_idempotency_replay_use_governed_indexes(self) -> None:
        with self.factory() as unit:
            unit.aggregates.append(draft(1), event(0), expected_revision=None)
            unit.commit()

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            latest_plan = connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT revisions.revision_id
                FROM aggregate_revisions AS revisions
                LEFT JOIN documents
                  ON revisions.revision_id = documents.revision_id
                 AND revisions.project_id = documents.project_id
                WHERE revisions.aggregate_id = ? AND revisions.project_id = ?
                ORDER BY revisions.revision DESC
                LIMIT 1
                """,
                (draft(1).aggregate_id, PROJECT_ID),
            ).fetchall()
            replay_plan = connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT record_sha256, revision_id
                FROM outbox_events
                WHERE project_id = ? AND idempotency_key = ?
                """,
                (PROJECT_ID, event(0).idempotency_key),
            ).fetchall()
        finally:
            connection.close()
        latest_details = tuple(str(row[3]) for row in latest_plan)
        replay_details = tuple(str(row[3]) for row in replay_plan)
        self.assertTrue(
            any(
                "SEARCH revisions USING INDEX sqlite_autoindex_aggregate_revisions_2" in item for item in latest_details
            ),
            latest_details,
        )
        self.assertTrue(
            any("SEARCH outbox_events USING INDEX sqlite_autoindex_outbox_events_2" in item for item in replay_details),
            replay_details,
        )

    def test_optimistic_conflict_and_not_found_are_bounded(self) -> None:
        with self.factory() as unit:
            aggregate = unit.aggregates.append(draft(1), event(0), expected_revision=None)
            unit.commit()

        with self.factory() as unit:
            with self.assertRaises(RepositoryNotFound) as missing:
                unit.aggregates.get("01890f6e-6a40-7cc5-98b7-000000000999")
            self.assertEqual("RO-CORE-REPOSITORY-NOT-FOUND", missing.exception.code)
            unit.rollback()

        with self.factory() as unit:
            with self.assertRaises(RepositoryConflict) as conflict:
                unit.aggregates.append(draft(2), event(1), expected_revision=9)
            self.assertEqual("RO-CORE-REPOSITORY-CONFLICT", conflict.exception.code)
            with self.assertRaises(RepositoryTransactionFailed):
                unit.commit()

        with self.factory() as unit:
            regressed = replace(draft(2), modified_at=CREATED_AT)
            with self.assertRaises(RepositoryConflict):
                unit.aggregates.append(regressed, event(1), expected_revision=0)
            with self.assertRaises(RepositoryTransactionFailed):
                unit.commit()

        with self.factory() as unit:
            self.assertEqual(aggregate, unit.aggregates.get(aggregate.aggregate_id))
            unit.rollback()

    def test_late_outbox_failure_rolls_back_every_aggregate_fact(self) -> None:
        first_event = event(0, key="first-key")
        with self.factory() as unit:
            first = unit.aggregates.append(draft(1), first_event, expected_revision=None)
            unit.commit()

        second_id = "01890f6e-6a40-7cc5-98b7-000000000202"
        late_failure = replace(event(2, key="second-key"), outbox_id=first_event.outbox_id)
        with self.factory() as unit:
            with self.assertRaises(RepositoryProblem) as adapter_failure:
                unit.aggregates.append(
                    draft(2, aggregate_id=second_id),
                    late_failure,
                    expected_revision=None,
                )
            self.assertIsNone(adapter_failure.exception.__cause__)
            self.assertIsNone(adapter_failure.exception.__context__)
            with self.assertRaises(RepositoryTransactionFailed):
                unit.commit()

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(1, connection.execute("SELECT count(*) FROM aggregate_identities").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT count(*) FROM aggregate_revisions").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT count(*) FROM provenance_events").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT count(*) FROM outbox_events").fetchone()[0])
            self.assertEqual(
                first.aggregate_id, connection.execute("SELECT aggregate_id FROM aggregate_identities").fetchone()[0]
            )
        finally:
            connection.close()

    def test_idempotency_replays_exact_command_and_rejects_changed_payload_or_precondition(self) -> None:
        command = draft(1)
        command_event = event(0, key="stable-command-key")
        with self.factory() as unit:
            original = unit.aggregates.append(command, command_event, expected_revision=None)
            unit.commit()

        with self.factory() as unit:
            replay = unit.aggregates.append(command, command_event, expected_revision=None)
            self.assertEqual(original, replay)
            unit.commit()

        changed = replace(command, display_label_observed="Changed payload")
        with self.factory() as unit, self.assertRaises(RepositoryConflict):
            unit.aggregates.append(changed, command_event, expected_revision=None)

        with self.factory() as unit, self.assertRaises(RepositoryConflict):
            unit.aggregates.append(command, command_event, expected_revision=0)

        changed_events = (
            replace(command_event, available_at="2026-08-09T12:00:03.000Z"),
            replace(command_event, outbox_id="01890f6e-6a40-7cc5-98b7-000000000299"),
        )
        for changed_event in changed_events:
            with (
                self.subTest(changed_event=changed_event),
                self.factory() as unit,
                self.assertRaises(RepositoryConflict),
            ):
                unit.aggregates.append(command, changed_event, expected_revision=None)

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            for table in (
                "aggregate_identities",
                "aggregate_revisions",
                "scholarly_records",
                "provenance_events",
                "outbox_events",
            ):
                with self.subTest(table=table):
                    self.assertEqual(1, connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        finally:
            connection.close()

    def test_incompatible_authority_and_busy_writer_are_bounded_and_retryable(self) -> None:
        wrong_factory = create_sqlite_unit_of_work_factory(
            self.database,
            "11890f6e-6a40-4cc5-98b7-123456789abc",
        )
        with self.assertRaises(RepositoryTransactionFailed) as incompatible, wrong_factory():
            pass
        self.assertNotIn(str(self.database), str(incompatible.exception))
        self.assertIsNone(incompatible.exception.__cause__)
        self.assertIsNone(incompatible.exception.__context__)

        first = self.factory()
        entered = first.__enter__()
        started = time.monotonic()
        try:
            with self.assertRaises(RepositoryTransactionFailed) as busy, self.factory():
                pass
            self.assertGreaterEqual(time.monotonic() - started, 4.5)
            self.assertIsNone(busy.exception.__cause__)
            self.assertIsNone(busy.exception.__context__)
            self.assertNotIn("locked", str(busy.exception).casefold())
        finally:
            entered.rollback()
            entered.__exit__(None, None, None)

        with self.factory() as retry:
            retry.aggregates.append(draft(1), event(0), expected_revision=None)
            retry.commit()

    def test_document_fk_failure_and_uncommitted_context_leave_no_partial_rows(self) -> None:
        document = replace(draft(1), aggregate_kind="document", object_sha256="a" * 64)
        with self.factory() as unit, self.assertRaises(RepositoryProblem):
            unit.aggregates.append(document, event(0), expected_revision=None)

        with self.factory() as unit:
            unit.aggregates.append(draft(2), event(1), expected_revision=None)

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(0, connection.execute("SELECT count(*) FROM aggregate_identities").fetchone()[0])
            self.assertEqual(0, connection.execute("SELECT count(*) FROM aggregate_revisions").fetchone()[0])
            self.assertEqual(0, connection.execute("SELECT count(*) FROM provenance_events").fetchone()[0])
            self.assertEqual(0, connection.execute("SELECT count(*) FROM outbox_events").fetchone()[0])
        finally:
            connection.close()

    def test_all_aggregate_kinds_return_detached_frozen_projections(self) -> None:
        kinds: tuple[AggregateKind, ...] = (
            "record",
            "document",
            "workflow",
            "evidence",
            "ontology",
            "decision",
        )
        written = []
        with self.factory() as unit:
            for index, kind in enumerate(kinds, start=10):
                aggregate_id = f"01890f6e-6a40-7cc5-98b7-{index + 500:012x}"
                candidate = replace(
                    draft(index, aggregate_id=aggregate_id),
                    aggregate_kind=kind,
                )
                written.append(unit.aggregates.append(candidate, event(index), expected_revision=None))
            unit.commit()

        with self.factory() as unit:
            for expected in written:
                actual = unit.aggregates.get(expected.aggregate_id)
                self.assertEqual(expected, actual)
                with self.assertRaises((AttributeError, TypeError)):
                    actual.revision = 99  # type: ignore[misc]
            unit.rollback()

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            for aggregate_kind, table in {
                "record": "scholarly_records",
                "document": "documents",
                "workflow": "workflows",
                "evidence": "evidence",
                "ontology": "ontologies",
                "decision": "decisions",
            }.items():
                with self.subTest(kind=aggregate_kind):
                    self.assertEqual(1, connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        finally:
            connection.close()

    def test_business_ports_retain_no_database_path_or_connection(self) -> None:
        unit = self.factory()
        for port in (self.factory, unit):
            slots = cast(tuple[str, ...], vars(type(port))["__slots__"])
            for slot in slots:
                value = getattr(port, f"_{type(port).__name__.lstrip('_')}{slot}")
                self.assertIsInstance(value, (str, type(None)))
                if isinstance(value, str):
                    self.assertRegex(value, r"^[0-9a-f]{64}$")
                self.assertNotIsInstance(value, Path)
        with unit as entered:
            repository = entered.aggregates
            slots = cast(tuple[str, ...], vars(type(repository))["__slots__"])
            for slot in slots:
                value = getattr(repository, f"_{type(repository).__name__.lstrip('_')}{slot}")
                self.assertIsInstance(value, str)
                self.assertRegex(value, r"^[0-9a-f]{64}$")
            entered.rollback()

    def test_business_modules_have_no_sql_or_database_dependency(self) -> None:
        source_root = REPO / "services" / "core-api" / "src" / "research_observatory_core"
        self.assertEqual([], core_data_boundary_errors(source_root))

        hostile_root = self.root / "hostile-core"
        hostile_root.mkdir()
        (hostile_root / "business.py").write_text(
            "from research_observatory_core.storage import open_canonical_database\n"
            "QUERY = 'SELECT project_id FROM projects'\n"
            "def attack(connection):\n"
            "    return connection.execute(QUERY)\n",
            encoding="utf-8",
        )
        errors = core_data_boundary_errors(hostile_root)
        self.assertTrue(any("open_canonical_database" in error for error in errors), errors)
        self.assertTrue(any("database call execute" in error for error in errors), errors)

    def test_dependency_neutral_ports_do_not_load_sqlite_or_sqlalchemy(self) -> None:
        command = (
            "import json,sys; "
            "import research_observatory_core.ports.repositories as ports; "
            "print(json.dumps({'sqlite3': 'sqlite3' in sys.modules, "
            "'sqlalchemy': any(name == 'sqlalchemy' or name.startswith('sqlalchemy.') for name in sys.modules), "
            "'module': ports.UnitOfWorkFactory.__module__}, sort_keys=True))"
        )
        result = subprocess.run(
            [str(REPO / ".venv" / "Scripts" / "python.exe"), "-c", command],
            cwd=REPO,
            env={**os.environ, "PYTHONPATH": str(SERVICE_SRC)},
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            {"module": "research_observatory_core.ports.repositories", "sqlalchemy": False, "sqlite3": False},
            json.loads(result.stdout),
        )


if __name__ == "__main__":
    unittest.main()
