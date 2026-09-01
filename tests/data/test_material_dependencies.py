from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from research_observatory_core.ports.repositories import (
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    DependencyCoverage,
    DependencyRegistrationRequired,
    MaterialDependency,
    RepositoryConflict,
    RepositoryProblem,
)
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_material_dependency_repository,
)
from research_observatory_core.storage import (
    development_plaintext_database_fixture,
    initialize_database,
    open_canonical_database,
)

PROJECT_ID = "01890f6e-6a40-4cc5-98b7-123456789abc"
CREATED_AT = "2026-09-01T21:00:00.000Z"
ACTOR_ID = "01890f6e-6a40-7cc5-98b7-000000000301"


def event(index: int, *, key: str | None = None) -> AtomicRepositoryEvent:
    return AtomicRepositoryEvent(
        event_id=f"01890f6e-6a40-7cc5-98b7-{index + 100:012x}",
        outbox_id=f"01890f6e-6a40-7cc5-98b7-{index + 200:012x}",
        event_type="evidence.created",
        occurred_at=f"2026-09-01T21:00:{index:02d}.000Z",
        available_at=f"2026-09-01T21:00:{index:02d}.000Z",
        trace_id=f"{index + 1:032x}",
        actor_type="worker",
        actor_id=ACTOR_ID,
        idempotency_key=key or f"dependency-registration-{index}",
    )


def draft(
    index: int,
    *,
    coverage: str,
    dependencies: tuple[MaterialDependency, ...] = (),
) -> AggregateRevisionDraft:
    return AggregateRevisionDraft(
        revision_id=f"01890f6e-6a40-7cc5-98b7-{index:012x}",
        aggregate_id=f"01890f6e-6a40-7cc5-98b7-{index + 1_000:012x}",
        aggregate_kind="evidence",
        created_at=CREATED_AT,
        modified_at=f"2026-09-01T21:00:{index:02d}.000Z",
        display_label_observed=f"Dependency fixture {index}",
        display_label_normalized=None,
        knowledge_status="observed",
        rights_status="unknown",
        dependency_coverage=coverage,  # type: ignore[arg-type]
        material_dependencies=dependencies,
    )


class MaterialDependencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.protection = development_plaintext_database_fixture()
        self.protection.__enter__()
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-material-dependencies-")
        self.root = Path(self.temporary.name).resolve() / "project"
        (self.root / "state").mkdir(parents=True)
        self.database = self.root / "state" / "project.sqlite3"
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        self.factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)

    def tearDown(self) -> None:
        try:
            self.temporary.cleanup()
        finally:
            self.protection.__exit__(None, None, None)

    def create_source(self):
        with self.factory() as unit:
            source = unit.aggregates.append(
                draft(1, coverage="not-applicable"),
                event(1),
                expected_revision=None,
            )
            unit.commit()
        return source

    @staticmethod
    def revision_dependency(source_revision_id: str) -> MaterialDependency:
        return MaterialDependency(
            dependency_id="01890f6e-6a40-7cc5-98b7-000000001101",
            dependency_kind="source-revision",
            relation_type="direct",
            revision_id=source_revision_id,
            configuration_id=None,
            configuration_version=None,
            fingerprint="sha256:" + "a" * 64,
            governing_policy_id="dependency.material.v1",
            governing_policy_version="1.0.0",
        )

    @staticmethod
    def configuration_dependency() -> MaterialDependency:
        return MaterialDependency(
            dependency_id="01890f6e-6a40-7cc5-98b7-000000001102",
            dependency_kind="model-version",
            relation_type="conditional",
            revision_id=None,
            configuration_id="model.local.fixture",
            configuration_version="1.0.0",
            fingerprint="sha256:" + "b" * 64,
            governing_policy_id="dependency.material.v1",
            governing_policy_version="1.0.0",
        )

    def test_typed_registration_is_atomic_reopenable_and_idempotent(self) -> None:
        source = self.create_source()
        dependencies = (self.revision_dependency(source.revision_id), self.configuration_dependency())
        output_draft = draft(2, coverage="complete", dependencies=dependencies)
        output_event = event(2)
        with self.factory() as unit:
            output = unit.aggregates.append(output_draft, output_event, expected_revision=None)
            unit.commit()

        reopened = sqlite_material_dependency_repository(self.root, PROJECT_ID)
        registration = reopened.registration(output.revision_id)
        self.assertEqual("complete", registration.coverage)
        self.assertEqual(output.aggregate_id, registration.output_aggregate_id)
        self.assertEqual(output_event.event_id, registration.registration_event_id)
        self.assertEqual(dependencies, registration.dependencies)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(
                (output_event.event_id, ACTOR_ID, output_event.occurred_at, 2),
                tuple(
                    connection.execute(
                        """
                        SELECT coverage.registration_event_id, event.actor_id,
                               coverage.registered_at, count(dependency.dependency_id)
                          FROM material_dependency_outputs AS coverage
                          JOIN provenance_events AS event
                            ON event.event_id=coverage.registration_event_id
                          JOIN material_dependencies AS dependency
                            ON dependency.output_revision_id=coverage.output_revision_id
                         WHERE coverage.output_revision_id=?
                         GROUP BY coverage.registration_event_id, event.actor_id,
                                  coverage.registered_at
                        """,
                        (output.revision_id,),
                    ).fetchone()
                ),
            )
        finally:
            connection.close()

        with self.factory() as unit:
            replay = unit.aggregates.append(output_draft, output_event, expected_revision=None)
            unit.commit()
        self.assertEqual(output, replay)
        self.assertEqual(2, len(reopened.registration(output.revision_id).dependencies))

        changed = replace(
            dependencies[1],
            fingerprint="sha256:" + "c" * 64,
        )
        with self.factory() as unit, self.assertRaises(RepositoryConflict):
            unit.aggregates.append(
                replace(output_draft, material_dependencies=(dependencies[0], changed)),
                output_event,
                expected_revision=None,
            )

    def test_missing_substituted_and_late_failure_leave_no_partial_authority(self) -> None:
        source = self.create_source()
        with self.factory() as unit, self.assertRaises(DependencyRegistrationRequired) as missing:
            unit.aggregates.append(draft(2, coverage="complete"), event(2), expected_revision=None)
        self.assertEqual("RO-CORE-DEPENDENCY-REGISTRATION-REQUIRED", missing.exception.code)

        dependency = self.revision_dependency(source.revision_id)
        with self.factory() as unit, self.assertRaises(RepositoryProblem):
            unit.aggregates.append(
                draft(3, coverage="not-applicable", dependencies=(dependency,)),
                event(3),
                expected_revision=None,
            )
        with self.factory() as unit, self.assertRaises(RepositoryConflict):
            unit.aggregates.append(
                draft(
                    4,
                    coverage="complete",
                    dependencies=(replace(dependency, revision_id=draft(4, coverage="complete").revision_id),),
                ),
                event(4),
                expected_revision=None,
            )
        with self.factory() as unit, self.assertRaises(RepositoryConflict):
            unit.aggregates.append(
                draft(
                    5,
                    coverage="complete",
                    dependencies=(replace(dependency, revision_id="01890f6e-6a40-7cc5-98b7-000000009999"),),
                ),
                event(5),
                expected_revision=None,
            )
        with self.factory() as unit, self.assertRaises(RepositoryConflict):
            unit.aggregates.append(
                draft(5, coverage="complete", dependencies=(replace(dependency, dependency_kind="ontology-version"),)),
                event(5),
                expected_revision=None,
            )
        duplicate_semantic_edge = replace(
            dependency,
            dependency_id="01890f6e-6a40-7cc5-98b7-000000001103",
        )
        with self.factory() as unit, self.assertRaises(RepositoryProblem):
            unit.aggregates.append(
                draft(6, coverage="complete", dependencies=(dependency, duplicate_semantic_edge)),
                event(6),
                expected_revision=None,
            )

        output_draft = draft(7, coverage="complete", dependencies=(dependency,))
        output_event = event(7)
        from research_observatory_core import repositories

        original = repositories._record_material_dependencies

        def fail_after_insert(
            connection: Any,
            *,
            project_id: str,
            revision: AggregateRevision,
            coverage: DependencyCoverage,
            dependencies: tuple[MaterialDependency, ...],
            event: AtomicRepositoryEvent,
        ) -> None:
            original(
                connection,
                project_id=project_id,
                revision=revision,
                coverage=coverage,
                dependencies=dependencies,
                event=event,
            )
            raise sqlite3.OperationalError("injected dependency registration failure")

        with (
            patch(
                "research_observatory_core.repositories._record_material_dependencies", side_effect=fail_after_insert
            ),
            self.factory() as unit,
            self.assertRaises(RepositoryProblem),
        ):
            unit.aggregates.append(output_draft, output_event, expected_revision=None)

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            for table in (
                "aggregate_revisions",
                "material_dependency_outputs",
                "material_dependencies",
                "provenance_events",
                "outbox_events",
            ):
                self.assertEqual(
                    0,
                    connection.execute(
                        f"SELECT count(*) FROM {table} WHERE project_id=? AND "
                        + (
                            "revision_id=?"
                            if table == "aggregate_revisions"
                            else "output_revision_id=?"
                            if table in {"material_dependency_outputs", "material_dependencies"}
                            else "event_id=?"
                            if table == "provenance_events"
                            else "outbox_id=?"
                        ),
                        (
                            PROJECT_ID,
                            output_draft.revision_id
                            if table in {"aggregate_revisions", "material_dependency_outputs", "material_dependencies"}
                            else output_event.event_id
                            if table == "provenance_events"
                            else output_event.outbox_id,
                        ),
                    ).fetchone()[0],
                    table,
                )
        finally:
            connection.close()

        with self.factory() as unit:
            recovered = unit.aggregates.append(output_draft, output_event, expected_revision=None)
            unit.commit()
        self.assertEqual(
            "complete",
            sqlite_material_dependency_repository(self.root, PROJECT_ID).registration(recovered.revision_id).coverage,
        )


if __name__ == "__main__":
    unittest.main()
