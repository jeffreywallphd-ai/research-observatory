from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.repositories import (  # noqa: E402
    AggregateKind,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    RepositoryConflict,
    RepositoryNotFound,
    RepositoryProblem,
    RepositoryTransactionFailed,
    SqliteAggregateRepository,
    SqliteUnitOfWork,
    SqliteUnitOfWorkFactory,
)
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
        self.factory = SqliteUnitOfWorkFactory(self.database, PROJECT_ID)

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
        with self.factory() as unit:
            first = unit.aggregates.append(draft(1), event(0, key="duplicate-key"), expected_revision=None)
            unit.commit()

        second_id = "01890f6e-6a40-7cc5-98b7-000000000202"
        with self.factory() as unit:
            with self.assertRaises(RepositoryProblem):
                unit.aggregates.append(
                    draft(2, aggregate_id=second_id),
                    event(2, key="duplicate-key"),
                    expected_revision=None,
                )
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
        unit = cast(SqliteUnitOfWork, self.factory())
        for port in (self.factory, unit):
            for slot in type(port).__slots__:
                value = getattr(port, f"_{type(port).__name__}{slot}")
                self.assertIsInstance(value, (str, type(None)))
                if isinstance(value, str):
                    self.assertRegex(value, r"^[0-9a-f]{64}$")
                self.assertNotIsInstance(value, Path)
        with unit as entered:
            repository = cast(SqliteAggregateRepository, entered.aggregates)
            for slot in type(repository).__slots__:
                value = getattr(repository, f"_{type(repository).__name__}{slot}")
                self.assertIsInstance(value, str)
                self.assertRegex(value, r"^[0-9a-f]{64}$")
            entered.rollback()

    def test_business_modules_have_no_sql_or_database_dependency(self) -> None:
        source_root = Path("services/core-api/src/research_observatory_core")
        permitted = {
            Path("services/core-api/src/research_observatory_core/repositories.py"),
            Path("services/core-api/src/research_observatory_core/storage.py"),
        }
        failures: list[str] = []
        sql_prefixes = (
            "alter ",
            "attach ",
            "begin",
            "commit",
            "create ",
            "delete ",
            "drop ",
            "insert ",
            "pragma ",
            "rollback",
            "select ",
            "update ",
            "vacuum",
        )
        for path in sorted(source_root.rglob("*.py")):
            repository_path = Path(path.as_posix())
            if repository_path in permitted or "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    modules = [alias.name for alias in node.names]
                    if isinstance(node, ast.ImportFrom) and node.module:
                        modules.append(node.module)
                    if any(module == "sqlite3" or module.startswith("sqlalchemy") for module in modules):
                        failures.append(f"{path.as_posix()}:{node.lineno}: database dependency")
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in {"execute", "executemany"} or not node.args:
                    continue
                argument = node.args[0]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    normalized = " ".join(argument.value.split()).casefold()
                    if normalized.startswith(sql_prefixes):
                        failures.append(f"{path.as_posix()}:{node.lineno}: ad hoc SQL")
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
