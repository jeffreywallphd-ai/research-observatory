from __future__ import annotations

import hashlib
import json
import os
import sqlite3
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
from research_observatory_core.repositories import (  # noqa: E402
    create_sqlite_unit_of_work_factory,
    sqlite_provenance_ledger_repository,
)
from research_observatory_core.storage import (  # noqa: E402
    _immutable_triggers,
    development_plaintext_database_fixture,
    initialize_database,
    open_canonical_database,
)

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
        actor_id="01890f6e-6a40-7cc5-98b7-000000000301",
        idempotency_key=key or f"record-write-{index}",
    )


class SqliteRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_profile = development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.state = self.root / "state"
        self.state.mkdir()
        self.database = self.state / "project.sqlite3"
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        self.factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)

    def tearDown(self) -> None:
        try:
            self.temporary.cleanup()
        finally:
            self.database_profile.__exit__(None, None, None)

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
            self.assertEqual(2, connection.execute("SELECT count(*) FROM provenance_ledger_events").fetchone()[0])
            self.assertEqual(2, connection.execute("SELECT count(*) FROM provenance_ledger_checkpoints").fetchone()[0])
        finally:
            connection.close()

        lineage = sqlite_provenance_ledger_repository(self.root, PROJECT_ID)
        ancestors = lineage.lineage(
            revision_id=revised.revision_id,
            direction="ancestors",
            cursor=0,
            page_size=10,
            max_depth=4,
        )
        self.assertEqual("verified", ancestors.integrity_state)
        self.assertEqual(revised.revision_id, ancestors.items[0].revision_id)
        self.assertEqual(
            {revised.revision_id, created.revision_id},
            {item.revision_id for item in ancestors.items},
        )
        self.assertEqual(
            tuple(sorted(item.depth for item in ancestors.items)),
            tuple(item.depth for item in ancestors.items),
        )
        self.assertEqual(len(ancestors.items), len({item.fact_id for item in ancestors.items}))
        self.assertEqual(
            {"wasDerivedFrom", "wasGeneratedBy", "wasAttributedTo"},
            {item.relation_type for item in ancestors.items if item.revision_id == revised.revision_id},
        )
        self.assertTrue(all(item.agent_id == event(0).actor_id for item in ancestors.items))
        complete_descendants = lineage.lineage(
            revision_id=created.revision_id,
            direction="descendants",
            cursor=0,
            page_size=10,
            max_depth=4,
        )
        cursor = 0
        paged_fact_ids: list[str] = []
        while True:
            page = lineage.lineage(
                revision_id=created.revision_id,
                direction="descendants",
                cursor=cursor,
                page_size=1,
                max_depth=4,
            )
            paged_fact_ids.extend(item.fact_id for item in page.items)
            if page.next_cursor is None:
                break
            self.assertGreater(page.next_cursor, cursor)
            cursor = page.next_cursor
        self.assertEqual([item.fact_id for item in complete_descendants.items], paged_fact_ids)

    def test_missing_lineage_reference_and_checkpoint_mismatch_enter_integrity_review(self) -> None:
        with self.factory() as unit:
            first = unit.aggregates.append(draft(1), event(0), expected_revision=None)
            unit.commit()
        with self.factory() as unit:
            second = unit.aggregates.append(draft(2), event(1), expected_revision=0)
            unit.commit()

        raw = sqlite3.connect(self.database, autocommit=True)
        try:
            raw.execute("DROP TRIGGER provenance_ledger_relations_no_update")
            raw.execute("DROP TRIGGER provenance_ledger_relations_no_delete")
            raw.execute(
                """
                UPDATE provenance_ledger_relations
                   SET related_entity_id='01890f6e-6a40-7cc5-98b7-000000000991',
                       related_revision_id='01890f6e-6a40-7cc5-98b7-000000000992'
                 WHERE relation_type='wasDerivedFrom'
                """
            )
            for statement in _immutable_triggers(
                "provenance_ledger_relations", "provenance ledger relations are append-only"
            ):
                raw.execute(statement)
            raw.execute("DROP TRIGGER provenance_ledger_checkpoints_no_update")
            raw.execute("DROP TRIGGER provenance_ledger_checkpoints_no_delete")
            raw.execute(
                "UPDATE provenance_ledger_checkpoints SET chain_sha256=? WHERE sequence=2",
                ("sha256:" + "f" * 64,),
            )
            for statement in _immutable_triggers(
                "provenance_ledger_checkpoints", "provenance ledger checkpoints are append-only"
            ):
                raw.execute(statement)
        finally:
            raw.close()

        lineage = sqlite_provenance_ledger_repository(self.root, PROJECT_ID).lineage(
            revision_id=second.revision_id,
            direction="ancestors",
            cursor=0,
            page_size=10,
            max_depth=4,
        )
        self.assertEqual("integrity-review", lineage.integrity_state)
        self.assertTrue(lineage.items)
        self.assertEqual({second.revision_id}, {item.revision_id for item in lineage.items})
        self.assertEqual(
            {"wasDerivedFrom", "wasGeneratedBy", "wasAttributedTo"},
            {item.relation_type for item in lineage.items},
        )
        self.assertEqual(("01890f6e-6a40-7cc5-98b7-000000000992",), lineage.missing_revision_ids)
        self.assertNotIn(first.revision_id, tuple(item.revision_id for item in lineage.items))

    def test_authority_projection_corruption_enters_integrity_review(self) -> None:
        cases = (
            "event-identity",
            "project-authority",
            "narrow-audit",
            "actor-type",
            "trace-id",
            "idempotency",
        )
        for case in cases:
            with self.subTest(case=case):
                case_root = self.root / case
                case_database = case_root / "state" / "project.sqlite3"
                case_database.parent.mkdir(parents=True)
                initialize_database(case_database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
                case_factory = create_sqlite_unit_of_work_factory(case_database, PROJECT_ID)
                with case_factory() as unit:
                    revision = unit.aggregates.append(draft(1), event(0), expected_revision=None)
                    unit.commit()

                raw = sqlite3.connect(case_database, autocommit=True)
                try:
                    raw.execute("PRAGMA foreign_keys=OFF")
                    if case in {"event-identity", "project-authority"}:
                        for table in (
                            "provenance_ledger_events",
                            "provenance_ledger_entities",
                            "provenance_ledger_relations",
                            "provenance_ledger_checkpoints",
                        ):
                            raw.execute(f"DROP TRIGGER {table}_no_update")
                            raw.execute(f"DROP TRIGGER {table}_no_delete")
                        if case == "event-identity":
                            replacement = "01890f6e-6a40-7cc5-98b7-000000000999"
                            for table in (
                                "provenance_ledger_entities",
                                "provenance_ledger_relations",
                                "provenance_ledger_checkpoints",
                                "provenance_ledger_events",
                            ):
                                raw.execute(f"UPDATE {table} SET event_id=?", (replacement,))
                        else:
                            replacement = "123e4567-e89b-42d3-a456-426614174999"
                            for table in (
                                "provenance_ledger_entities",
                                "provenance_ledger_relations",
                                "provenance_ledger_checkpoints",
                                "provenance_ledger_events",
                            ):
                                raw.execute(f"UPDATE {table} SET project_id=?", (replacement,))
                        for table in (
                            "provenance_ledger_events",
                            "provenance_ledger_entities",
                            "provenance_ledger_relations",
                            "provenance_ledger_checkpoints",
                        ):
                            for statement in _immutable_triggers(table, table.replace("_", " ") + " are append-only"):
                                raw.execute(statement)
                    elif case in {"narrow-audit", "actor-type", "trace-id"}:
                        raw.execute("DROP TRIGGER provenance_events_no_update")
                        raw.execute("DROP TRIGGER provenance_events_no_delete")
                        if case == "narrow-audit":
                            raw.execute(
                                "UPDATE provenance_events SET record_sha256=? WHERE revision_id=?",
                                ("f" * 64, revision.revision_id),
                            )
                        elif case == "actor-type":
                            raw.execute(
                                "UPDATE provenance_events SET actor_type='model' WHERE revision_id=?",
                                (revision.revision_id,),
                            )
                        else:
                            raw.execute(
                                "UPDATE provenance_events SET trace_id=? WHERE revision_id=?",
                                ("f" * 32, revision.revision_id),
                            )
                        for statement in _immutable_triggers("provenance_events", "provenance events are append-only"):
                            raw.execute(statement)
                    else:
                        raw.execute("DROP TRIGGER provenance_ledger_events_no_update")
                        raw.execute("DROP TRIGGER provenance_ledger_events_no_delete")
                        raw.execute("UPDATE provenance_ledger_events SET idempotency_sha256=?", ("f" * 64,))
                        for statement in _immutable_triggers(
                            "provenance_ledger_events", "provenance ledger events are append-only"
                        ):
                            raw.execute(statement)
                finally:
                    raw.close()

                lineage = sqlite_provenance_ledger_repository(case_root, PROJECT_ID).lineage(
                    revision_id=revision.revision_id,
                    direction="ancestors",
                    cursor=0,
                    page_size=10,
                    max_depth=4,
                )
                self.assertEqual("integrity-review", lineage.integrity_state)
                self.assertIn(
                    revision.revision_id,
                    {
                        *(item.revision_id for item in lineage.items),
                        *lineage.missing_revision_ids,
                    },
                )

    def test_v1_chain_remains_verified_when_v2_segment_is_appended_after_restart(self) -> None:
        with self.factory() as unit:
            first = unit.aggregates.append(draft(1), event(0), expected_revision=None)
            unit.commit()

        raw = sqlite3.connect(self.database, autocommit=True)
        try:
            record_sha256, sequence = raw.execute(
                "SELECT record_sha256, sequence FROM provenance_ledger_events WHERE event_id=?",
                (event(0).event_id,),
            ).fetchone()
            v1_chain = "sha256:" + hashlib.sha256(f"genesis\n{record_sha256}\n{sequence}".encode("ascii")).hexdigest()
            for table in ("provenance_ledger_events", "provenance_ledger_checkpoints"):
                raw.execute(f"DROP TRIGGER {table}_no_update")
                raw.execute(f"DROP TRIGGER {table}_no_delete")
            raw.execute(
                """
                UPDATE provenance_ledger_events
                   SET segment_key='rfc8785.sha256.v1',
                       previous_chain_sha256=NULL,
                       chain_sha256=?
                 WHERE event_id=?
                """,
                (v1_chain, event(0).event_id),
            )
            raw.execute(
                """
                UPDATE provenance_ledger_checkpoints
                   SET segment_key='rfc8785.sha256.v1', chain_sha256=?
                 WHERE event_id=?
                """,
                (v1_chain, event(0).event_id),
            )
            for table in ("provenance_ledger_events", "provenance_ledger_checkpoints"):
                for statement in _immutable_triggers(table, table.replace("_", " ") + " are append-only"):
                    raw.execute(statement)
        finally:
            raw.close()

        restarted = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)
        with restarted() as unit:
            second = unit.aggregates.append(draft(2), event(1), expected_revision=0)
            unit.commit()

        lineage = sqlite_provenance_ledger_repository(self.root, PROJECT_ID).lineage(
            revision_id=second.revision_id,
            direction="ancestors",
            cursor=0,
            page_size=10,
            max_depth=4,
        )
        self.assertEqual("verified", lineage.integrity_state)
        self.assertEqual({second.revision_id, first.revision_id}, {item.revision_id for item in lineage.items})
        self.assertEqual(
            tuple(sorted(item.depth for item in lineage.items)),
            tuple(item.depth for item in lineage.items),
        )
        self.assertEqual(len(lineage.items), len({item.fact_id for item in lineage.items}))
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(
                [("rfc8785.sha256.v1", 1), ("rfc8785.sha256.v2", 1)],
                [
                    tuple(row)
                    for row in connection.execute(
                        "SELECT segment_key, sequence FROM provenance_ledger_events ORDER BY occurred_at"
                    ).fetchall()
                ],
            )
        finally:
            connection.close()

    def test_outbox_authority_corruption_cannot_replay_or_remain_verified(self) -> None:
        cases = {
            "outbox-id": ("outbox_id", "01890f6e-6a40-7cc5-98b7-000000000999"),
            "revision-id": ("revision_id", "second-revision"),
            "event-type": ("event_type", "org.research-observatory.record.corrupted.v1"),
            "occurred-at": ("occurred_at", "2026-08-18T01:00:59.000Z"),
            "available-at": ("available_at", "2026-08-18T01:02:00.000Z"),
            "idempotency-key": ("idempotency_key", "changed-command-key"),
            "record-sha256": ("record_sha256", "f" * 64),
        }
        for case, (column, replacement) in cases.items():
            with self.subTest(case=case):
                case_root = self.root / f"outbox-{case}"
                case_database = case_root / "state" / "project.sqlite3"
                case_database.parent.mkdir(parents=True)
                initialize_database(case_database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
                case_factory = create_sqlite_unit_of_work_factory(case_database, PROJECT_ID)
                first_event = event(0, key="first-command-key")
                with case_factory() as unit:
                    first = unit.aggregates.append(draft(1), first_event, expected_revision=None)
                    unit.commit()
                with case_factory() as unit:
                    second = unit.aggregates.append(
                        draft(2, aggregate_id="01890f6e-6a40-7cc5-98b7-000000000202"),
                        event(1, key="second-command-key"),
                        expected_revision=None,
                    )
                    unit.commit()

                raw = sqlite3.connect(case_database, autocommit=True)
                try:
                    value = second.revision_id if replacement == "second-revision" else replacement
                    raw.execute(
                        f"UPDATE outbox_events SET {column}=? WHERE idempotency_key='first-command-key'",
                        (value,),
                    )
                finally:
                    raw.close()

                with case_factory() as unit, self.assertRaises(RepositoryProblem):
                    unit.aggregates.append(draft(1), first_event, expected_revision=None)
                lineage = sqlite_provenance_ledger_repository(case_root, PROJECT_ID).lineage(
                    revision_id=first.revision_id,
                    direction="ancestors",
                    cursor=0,
                    page_size=10,
                    max_depth=4,
                )
                self.assertEqual("integrity-review", lineage.integrity_state)

    def test_invalid_actor_cannot_commit_canonical_output_without_provenance(self) -> None:
        invalid = replace(event(0), actor_id="legacy.actor")
        with self.factory() as unit, self.assertRaises(RepositoryProblem):
            unit.aggregates.append(draft(1), invalid, expected_revision=None)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            for table in (
                "aggregate_identities",
                "aggregate_revisions",
                "provenance_events",
                "provenance_ledger_events",
                "provenance_ledger_checkpoints",
                "outbox_events",
            ):
                self.assertEqual(0, connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0], table)
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
            replace(command_event, event_id="01890f6e-6a40-7cc5-98b7-000000000399"),
            replace(command_event, event_type="record.corrupted"),
            replace(command_event, occurred_at="2026-08-09T12:00:04.000Z"),
            replace(command_event, trace_id="f" * 32),
            replace(command_event, actor_type="model"),
            replace(command_event, actor_id="01890f6e-6a40-7cc5-98b7-000000000499"),
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
