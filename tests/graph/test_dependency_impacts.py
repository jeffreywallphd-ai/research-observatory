from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.dependency_impacts import (
    DependencyGraphEdge,
    plan_dependency_impact,
)
from research_observatory_core.ports.repositories import (
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    ConditionalDependencyDecision,
    DependencyChange,
    DependencyImpactLimitExceeded,
    DependencyImpactLimits,
    MaterialDependency,
    RepositoryConflict,
    RepositoryProblem,
)
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_dependency_impact_repository,
)
from research_observatory_core.storage import (
    development_plaintext_database_fixture,
    initialize_database,
    open_canonical_database,
)

PROJECT_ID = "01890f6e-6a40-4cc5-98b7-123456789abc"
OTHER_PROJECT_ID = "01890f6e-6a40-4cc5-98b7-123456789abd"
ACTOR_ID = "01890f6e-6a40-7cc5-98b7-000000000301"
OCCURRED_AT = "2026-09-01T22:00:00.000Z"


def uid(index: int) -> str:
    return f"01890f6e-6a40-7cc5-98b7-{index:012x}"


def fingerprint(character: str) -> str:
    return "sha256:" + character * 64


def event(index: int) -> AtomicRepositoryEvent:
    return AtomicRepositoryEvent(
        event_id=uid(10_000 + index),
        outbox_id=uid(20_000 + index),
        event_type="evidence.created",
        occurred_at=f"2026-09-01T22:00:{index:02d}.000Z",
        available_at=f"2026-09-01T22:00:{index:02d}.000Z",
        trace_id=f"{index + 1:032x}",
        actor_type="worker",
        actor_id=ACTOR_ID,
        idempotency_key=f"dependency-impact-fixture-{index}",
    )


def dependency(
    index: int,
    source_revision_id: str,
    *,
    relation_type: str = "direct",
    source_fingerprint: str | None = None,
) -> MaterialDependency:
    return MaterialDependency(
        dependency_id=uid(30_000 + index),
        dependency_kind="source-revision",
        relation_type=relation_type,  # type: ignore[arg-type]
        revision_id=source_revision_id,
        configuration_id=None,
        configuration_version=None,
        fingerprint=source_fingerprint or fingerprint("a"),
        governing_policy_id="dependency.material.v1",
        governing_policy_version="1.0.0",
    )


def draft(
    index: int,
    label: str,
    *,
    aggregate_id: str | None = None,
    dependencies: tuple[MaterialDependency, ...] = (),
) -> AggregateRevisionDraft:
    return AggregateRevisionDraft(
        revision_id=uid(index),
        aggregate_id=aggregate_id or uid(1_000 + index),
        aggregate_kind="evidence",
        created_at=OCCURRED_AT,
        modified_at=f"2026-09-01T22:00:{index:02d}.000Z",
        display_label_observed=label,
        display_label_normalized=None,
        knowledge_status="observed",
        rights_status="unknown",
        dependency_coverage="complete" if dependencies else "not-applicable",
        material_dependencies=dependencies,
    )


def revision_change(previous: AggregateRevision, replacement: AggregateRevision) -> DependencyChange:
    return DependencyChange(
        change_id=uid(80_001),
        idempotency_key="fixture-extraction-superseded",
        reason="SOURCE_VERSION",
        dependency_kind="source-revision",
        previous_revision_id=previous.revision_id,
        replacement_revision_id=replacement.revision_id,
        configuration_id=None,
        previous_configuration_version=None,
        replacement_configuration_version=None,
        previous_fingerprint=fingerprint("a"),
        replacement_fingerprint=fingerprint("b"),
        propagation_policy_id="dependency.propagation.v1",
        propagation_policy_version="1.0.0",
        actor_id=ACTOR_ID,
        trace_id="9" * 32,
        occurred_at=OCCURRED_AT,
    )


class DependencyImpactPlannerTests(unittest.TestCase):
    def test_relation_policy_duplicate_paths_and_cycles_are_deterministic_and_bounded(self) -> None:
        change = replace(
            revision_change(
                AggregateRevision(
                    revision_id=uid(1),
                    aggregate_id=uid(101),
                    aggregate_kind="evidence",
                    project_id=PROJECT_ID,
                    revision=1,
                    contract_version="1.0",
                    created_at=OCCURRED_AT,
                    modified_at=OCCURRED_AT,
                    display_label_observed="source",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                ),
                AggregateRevision(
                    revision_id=uid(2),
                    aggregate_id=uid(101),
                    aggregate_kind="evidence",
                    project_id=PROJECT_ID,
                    revision=2,
                    contract_version="1.0",
                    created_at=OCCURRED_AT,
                    modified_at=OCCURRED_AT,
                    display_label_observed="source",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                ),
            ),
            change_id=uid(80_002),
        )
        edges = (
            DependencyGraphEdge(uid(301), uid(1), uid(11), "evidence", "direct", fingerprint("a"), "p", "1.0.0"),
            DependencyGraphEdge(uid(302), uid(11), uid(12), "evidence", "direct", fingerprint("c"), "p", "1.0.0"),
            DependencyGraphEdge(uid(303), uid(11), uid(13), "evidence", "direct", fingerprint("d"), "p", "1.0.0"),
            DependencyGraphEdge(uid(304), uid(12), uid(14), "evidence", "direct", fingerprint("e"), "p", "1.0.0"),
            DependencyGraphEdge(uid(305), uid(13), uid(14), "evidence", "direct", fingerprint("f"), "p", "1.0.0"),
            DependencyGraphEdge(uid(306), uid(14), uid(12), "evidence", "direct", fingerprint("1"), "p", "1.0.0"),
            DependencyGraphEdge(uid(307), uid(1), uid(15), "evidence", "non-material", fingerprint("a"), "p", "1.0.0"),
            DependencyGraphEdge(uid(308), uid(1), uid(16), "evidence", "conditional", fingerprint("a"), "p", "1.0.0"),
        )
        decision = ConditionalDependencyDecision(
            dependency_id=uid(308),
            decision_id=uid(81_001),
            disposition="propagate",
            governing_policy_id="p",
            governing_policy_version="1.0.0",
            actor_id=ACTOR_ID,
            decided_at=OCCURRED_AT,
        )

        first = plan_dependency_impact(PROJECT_ID, change, edges, decisions=(decision,))
        second = plan_dependency_impact(PROJECT_ID, change, tuple(reversed(edges)), decisions=(decision,))
        self.assertEqual(first, second)
        self.assertEqual((uid(11), uid(16), uid(12), uid(13), uid(14)), first.affected_output_revision_ids)
        self.assertEqual((uid(15),), first.informational_output_revision_ids)
        self.assertEqual(1, len(first.cycle_groups))
        self.assertEqual((uid(12), uid(14)), first.cycle_groups[0].member_revision_ids)
        self.assertEqual(6, len({item.output_revision_id for item in first.impacts}))

        undecided = plan_dependency_impact(PROJECT_ID, change, edges)
        conditional = next(item for item in undecided.impacts if item.output_revision_id == uid(16))
        self.assertEqual("unknown-impact", conditional.disposition)
        self.assertEqual("unknown", conditional.confidence)
        self.assertTrue(conditional.review_required)

        ignored = plan_dependency_impact(
            PROJECT_ID, change, edges, decisions=(replace(decision, disposition="ignore"),)
        )
        self.assertIn(uid(16), ignored.informational_output_revision_ids)

        fingerprint_unavailable = plan_dependency_impact(
            PROJECT_ID,
            replace(change, replacement_fingerprint=None),
            edges,
            decisions=(decision,),
            legacy_unreported_output_ids=(uid(91), uid(90)),
            limits=DependencyImpactLimits(max_legacy_samples=1),
        )
        self.assertTrue(
            all(
                item.disposition != "stale"
                for item in fingerprint_unavailable.impacts
                if item.disposition != "informational"
            )
        )
        self.assertEqual(2, fingerprint_unavailable.legacy_unreported_count)
        self.assertEqual((uid(90),), fingerprint_unavailable.legacy_unreported_samples)

        with self.assertRaises(DependencyImpactLimitExceeded):
            plan_dependency_impact(
                PROJECT_ID,
                change,
                edges,
                decisions=(decision,),
                limits=DependencyImpactLimits(max_nodes=2),
            )
        with self.assertRaises(DependencyImpactLimitExceeded):
            plan_dependency_impact(
                PROJECT_ID,
                change,
                (),
                legacy_unreported_output_ids=(uid(90), uid(91)),
                limits=DependencyImpactLimits(max_nodes=1),
            )


class SqliteDependencyImpactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.protection = development_plaintext_database_fixture()
        self.protection.__enter__()
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-dependency-impact-")
        self.root = Path(self.temporary.name).resolve() / "project"
        (self.root / "state").mkdir(parents=True)
        self.database = self.root / "state" / "project.sqlite3"
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=OCCURRED_AT)
        self.factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)
        self.revisions: dict[str, AggregateRevision] = {}
        self._build_fixture()

    def tearDown(self) -> None:
        try:
            self.temporary.cleanup()
        finally:
            self.protection.__exit__(None, None, None)

    def _append(self, name: str, source: str | None = None, *, relation_type: str = "direct") -> None:
        index = len(self.revisions) + 1
        dependencies: tuple[MaterialDependency, ...] = ()
        if source is not None:
            dependencies = (dependency(index, self.revisions[source].revision_id, relation_type=relation_type),)
        with self.factory() as unit:
            self.revisions[name] = unit.aggregates.append(
                draft(index, name, dependencies=dependencies),
                event(index),
                expected_revision=None,
            )
            unit.commit()

    def _build_fixture(self) -> None:
        self._append("extraction-v1")
        source = self.revisions["extraction-v1"]
        with self.factory() as unit:
            self.revisions["extraction-v2"] = unit.aggregates.append(
                draft(20, "extraction-v2", aggregate_id=source.aggregate_id),
                event(20),
                expected_revision=0,
            )
            unit.commit()
        self._append("matrix", "extraction-v1")
        self._append("graph", "matrix")
        self._append("synthesis", "graph")
        self._append("dossier", "synthesis")
        self._append("other-source")
        self._append("unrelated", "other-source")
        self._append("non-material", "extraction-v1", relation_type="non-material")

    def change(self) -> DependencyChange:
        return revision_change(self.revisions["extraction-v1"], self.revisions["extraction-v2"])

    def test_preview_propagate_checkpoint_restart_and_replay_touch_only_expected_outputs(self) -> None:
        repository = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        before = self._authority_counts()
        preview = repository.preview(self.change())
        self.assertEqual(before, self._authority_counts())
        self.assertEqual(preview, repository.preview(self.change()))
        expected = tuple(self.revisions[name].revision_id for name in ("matrix", "graph", "synthesis", "dossier"))
        self.assertEqual(expected, preview.affected_output_revision_ids)
        self.assertEqual((self.revisions["non-material"].revision_id,), preview.informational_output_revision_ids)

        run = repository.begin(
            self.change(),
            preview_sha256=preview.preview_sha256,
            run_id=uid(90_001),
            batch_size=2,
        )
        self.assertEqual("running", run.state)
        first = repository.advance(run.run_id, expected_checkpoint_sha256=run.checkpoint_sha256)
        self.assertEqual(2, first.processed_items)
        self.assertEqual("running", first.state)

        reopened = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        completed = reopened.advance(first.run_id, expected_checkpoint_sha256=first.checkpoint_sha256)
        self.assertEqual("completed", completed.state)
        self.assertEqual(4, completed.stale_count)
        self.assertEqual(expected, tuple(item.output_revision_id for item in reopened.stale_states()))
        replay = reopened.begin(
            self.change(),
            preview_sha256=preview.preview_sha256,
            run_id=uid(90_001),
            batch_size=2,
        )
        self.assertEqual(completed, replay)
        self.assertEqual(before, self._authority_counts())
        self.assertEqual(3, len(reopened.audit(run_id=run.run_id)))

    def test_stale_preview_and_failed_batch_are_fail_closed_and_recoverable(self) -> None:
        repository = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        preview = repository.preview(self.change())
        self._append("later-dependent", "dossier")
        with self.assertRaises(RepositoryConflict):
            repository.begin(
                self.change(),
                preview_sha256=preview.preview_sha256,
                run_id=uid(90_002),
                batch_size=8,
            )

        current = repository.preview(self.change())
        run = repository.begin(
            self.change(),
            preview_sha256=current.preview_sha256,
            run_id=uid(90_003),
            batch_size=8,
        )
        with (
            patch(
                "research_observatory_core.repositories._record_dependency_stale_batch",
                side_effect=RuntimeError("fail"),
            ),
            self.assertRaises(RepositoryProblem),
        ):
            repository.advance(run.run_id, expected_checkpoint_sha256=run.checkpoint_sha256)
        reopened = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        unchanged = reopened.run(run.run_id)
        self.assertEqual(0, unchanged.processed_items)
        self.assertEqual((), reopened.stale_states())
        self.assertEqual("failed-attempt", reopened.audit(run_id=run.run_id)[-1].event_type)
        recovered = reopened.advance(run.run_id, expected_checkpoint_sha256=unchanged.checkpoint_sha256)
        self.assertEqual("completed", recovered.state)
        with self.assertRaises(RepositoryConflict):
            reopened.advance(run.run_id, expected_checkpoint_sha256=unchanged.checkpoint_sha256)

    def test_cancellation_is_checkpoint_bound_and_preserves_only_completed_batches(self) -> None:
        repository = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        preview = repository.preview(self.change())
        started = repository.begin(
            self.change(),
            preview_sha256=preview.preview_sha256,
            run_id=uid(90_004),
            batch_size=2,
        )
        checkpointed = repository.advance(
            started.run_id,
            expected_checkpoint_sha256=started.checkpoint_sha256,
        )
        cancelled = repository.cancel(
            started.run_id,
            expected_checkpoint_sha256=checkpointed.checkpoint_sha256,
            occurred_at="2026-09-01T22:01:00.000Z",
        )

        self.assertEqual("cancelled", cancelled.state)
        self.assertEqual(2, cancelled.processed_items)
        self.assertEqual(2, len(repository.stale_states()))
        with self.assertRaises(RepositoryConflict):
            repository.advance(started.run_id, expected_checkpoint_sha256=cancelled.checkpoint_sha256)
        with self.assertRaises(RepositoryConflict):
            repository.cancel(
                started.run_id,
                expected_checkpoint_sha256=checkpointed.checkpoint_sha256,
                occurred_at="2026-09-01T22:02:00.000Z",
            )

    def _authority_counts(self) -> tuple[int, int, tuple[tuple[str, str], ...]]:
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            return (
                int(connection.execute("SELECT count(*) FROM aggregate_revisions").fetchone()[0]),
                int(connection.execute("SELECT count(*) FROM material_dependencies").fetchone()[0]),
                tuple(
                    (str(row[0]), str(row[1]))
                    for row in connection.execute(
                        "SELECT revision_id, knowledge_status FROM aggregate_revisions ORDER BY revision_id"
                    )
                ),
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
