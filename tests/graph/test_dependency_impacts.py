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
    DEFAULT_DEPENDENCY_IMPACT_LIMITS,
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
    def test_preview_digest_binds_complete_change_and_conditional_decision_authority(self) -> None:
        previous = AggregateRevision(
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
        )
        replacement = replace(previous, revision_id=uid(2), revision=2)
        change = revision_change(previous, replacement)
        edge = DependencyGraphEdge(
            uid(301),
            previous.revision_id,
            uid(11),
            "evidence",
            "conditional",
            fingerprint("a"),
            "p",
            "1.0.0",
        )
        decision = ConditionalDependencyDecision(
            dependency_id=edge.dependency_id,
            decision_id=uid(81_001),
            disposition="propagate",
            governing_policy_id="p",
            governing_policy_version="1.0.0",
            actor_id=ACTOR_ID,
            decided_at=OCCURRED_AT,
        )
        canonical = plan_dependency_impact(PROJECT_ID, change, (edge,), decisions=(decision,))
        substitutions = (
            replace(change, idempotency_key="substituted-key"),
            replace(change, reason="RIGHTS_POLICY"),
            replace(change, replacement_revision_id=uid(3)),
            replace(change, replacement_fingerprint=fingerprint("c")),
            replace(change, propagation_policy_id="dependency.substituted.v1"),
            replace(change, propagation_policy_version="2.0.0"),
            replace(change, actor_id=uid(81_002)),
            replace(change, trace_id="8" * 32),
            replace(change, occurred_at="2026-09-01T22:00:01.000Z"),
        )
        for substituted in substitutions:
            with self.subTest(change=substituted):
                self.assertNotEqual(
                    canonical.preview_sha256,
                    plan_dependency_impact(PROJECT_ID, substituted, (edge,), decisions=(decision,)).preview_sha256,
                )
        for substituted_decision in (
            replace(decision, decision_id=uid(81_003)),
            replace(decision, actor_id=uid(81_004)),
            replace(decision, decided_at="2026-09-01T22:00:01.000Z"),
            replace(decision, disposition="ignore"),
        ):
            with self.subTest(decision=substituted_decision):
                self.assertNotEqual(
                    canonical.preview_sha256,
                    plan_dependency_impact(
                        PROJECT_ID,
                        change,
                        (edge,),
                        decisions=(substituted_decision,),
                    ).preview_sha256,
                )
        self.assertNotEqual(
            plan_dependency_impact(PROJECT_ID, change, (edge,)).preview_sha256,
            plan_dependency_impact(
                PROJECT_ID,
                replace(change, previous_revision_id=uid(4)),
                (edge,),
            ).preview_sha256,
        )
        with self.assertRaises(RepositoryConflict):
            plan_dependency_impact(PROJECT_ID, change, (), decisions=(decision,))

    def test_hard_limits_and_large_shallow_scc_are_deterministic(self) -> None:
        previous = AggregateRevision(
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
        )
        change = revision_change(previous, replace(previous, revision_id=uid(2), revision=2))
        hub = uid(10_000)
        members = tuple(uid(11_000 + index) for index in range(1_100))
        edges = [
            DependencyGraphEdge(
                uid(100_000), previous.revision_id, hub, "evidence", "direct", fingerprint("a"), "p", "1.0.0"
            )
        ]
        edges.extend(
            DependencyGraphEdge(
                uid(101_000 + index),
                hub,
                member,
                "evidence",
                "direct",
                fingerprint("c"),
                "p",
                "1.0.0",
            )
            for index, member in enumerate(members)
        )
        edges.extend(
            DependencyGraphEdge(
                uid(103_000 + index),
                member,
                members[(index + 1) % len(members)],
                "evidence",
                "direct",
                fingerprint("d"),
                "p",
                "1.0.0",
            )
            for index, member in enumerate(members)
        )

        preview = plan_dependency_impact(
            PROJECT_ID,
            change,
            tuple(edges),
            limits=replace(DEFAULT_DEPENDENCY_IMPACT_LIMITS, max_depth=128),
        )
        self.assertIn(members, tuple(group.member_revision_ids for group in preview.cycle_groups))
        for field, value in (
            ("max_nodes", 20_001),
            ("max_edges", 100_001),
            ("max_depth", 129),
            ("max_path_samples", 65),
            ("max_legacy_samples", 101),
        ):
            with self.subTest(limit=field), self.assertRaises(ValueError):
                plan_dependency_impact(
                    PROJECT_ID,
                    change,
                    tuple(edges),
                    limits=replace(DEFAULT_DEPENDENCY_IMPACT_LIMITS, **{field: value}),
                )
        with self.assertRaises(ValueError):
            plan_dependency_impact(
                PROJECT_ID,
                change,
                tuple(edges),
                limits=replace(DEFAULT_DEPENDENCY_IMPACT_LIMITS, max_path_samples=1),
            )

    def test_convergent_acyclic_graph_is_not_reported_as_a_cycle(self) -> None:
        previous = AggregateRevision(
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
        )
        change = revision_change(previous, replace(previous, revision_id=uid(2), revision=2))
        a, b, c = uid(11), uid(12), uid(13)
        edges = (
            DependencyGraphEdge(
                uid(301), previous.revision_id, a, "evidence", "direct", fingerprint("a"), "p", "1.0.0"
            ),
            DependencyGraphEdge(uid(302), a, b, "evidence", "direct", fingerprint("b"), "p", "1.0.0"),
            DependencyGraphEdge(uid(303), a, c, "evidence", "direct", fingerprint("c"), "p", "1.0.0"),
            DependencyGraphEdge(uid(304), b, c, "evidence", "direct", fingerprint("d"), "p", "1.0.0"),
        )

        preview = plan_dependency_impact(PROJECT_ID, change, edges)

        self.assertEqual((), preview.cycle_groups)
        self.assertTrue(all(item.cycle_group_id is None for item in preview.impacts))

    def test_self_loop_and_disjoint_cycles_are_exact_and_order_independent(self) -> None:
        previous = AggregateRevision(
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
        )
        change = revision_change(previous, replace(previous, revision_id=uid(2), revision=2))
        a, b, c, d, e = (uid(index) for index in range(11, 16))
        edges = (
            DependencyGraphEdge(
                uid(301), previous.revision_id, a, "evidence", "direct", fingerprint("a"), "p", "1.0.0"
            ),
            DependencyGraphEdge(uid(302), a, b, "evidence", "direct", fingerprint("b"), "p", "1.0.0"),
            DependencyGraphEdge(uid(303), b, a, "evidence", "direct", fingerprint("c"), "p", "1.0.0"),
            DependencyGraphEdge(
                uid(304), previous.revision_id, c, "evidence", "direct", fingerprint("a"), "p", "1.0.0"
            ),
            DependencyGraphEdge(uid(305), c, c, "evidence", "direct", fingerprint("d"), "p", "1.0.0"),
            DependencyGraphEdge(
                uid(306), previous.revision_id, d, "evidence", "direct", fingerprint("a"), "p", "1.0.0"
            ),
            DependencyGraphEdge(uid(307), d, e, "evidence", "direct", fingerprint("e"), "p", "1.0.0"),
            DependencyGraphEdge(uid(308), e, d, "evidence", "direct", fingerprint("f"), "p", "1.0.0"),
        )

        preview = plan_dependency_impact(PROJECT_ID, change, edges)
        reversed_preview = plan_dependency_impact(PROJECT_ID, change, tuple(reversed(edges)))

        self.assertEqual(preview, reversed_preview)
        self.assertEqual(
            ((a, b), (c,), (d, e)),
            tuple(group.member_revision_ids for group in preview.cycle_groups),
        )

    def test_long_path_sample_preserves_terminal_authority_and_reports_truncation(self) -> None:
        previous = AggregateRevision(
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
        )
        change = revision_change(previous, replace(previous, revision_id=uid(2), revision=2))
        outputs = tuple(uid(10_000 + index) for index in range(70))
        sources = (previous.revision_id, *outputs[:-1])
        edges = tuple(
            DependencyGraphEdge(
                uid(20_000 + index),
                source,
                output,
                "evidence",
                "direct",
                fingerprint("a" if index == 0 else "b"),
                "p",
                "1.0.0",
            )
            for index, (source, output) in enumerate(zip(sources, outputs, strict=True))
        )

        preview = plan_dependency_impact(PROJECT_ID, change, edges)
        reversed_preview = plan_dependency_impact(PROJECT_ID, change, tuple(reversed(edges)))
        exact_limit = next(item for item in preview.impacts if item.output_revision_id == outputs[62])
        terminal = next(item for item in preview.impacts if item.output_revision_id == outputs[-1])

        self.assertEqual(preview, reversed_preview)
        self.assertFalse(exact_limit.path_truncated)
        self.assertEqual(64, exact_limit.path_length)
        self.assertEqual(64, len(exact_limit.path_revision_ids))
        self.assertEqual(outputs[62], exact_limit.path_revision_ids[-1])
        self.assertTrue(terminal.path_truncated)
        self.assertEqual(71, terminal.path_length)
        self.assertEqual(64, len(terminal.path_revision_ids))
        self.assertEqual(previous.revision_id, terminal.path_revision_ids[0])
        self.assertEqual(outputs[-1], terminal.path_revision_ids[-1])
        narrower = plan_dependency_impact(
            PROJECT_ID,
            change,
            edges,
            limits=replace(DEFAULT_DEPENDENCY_IMPACT_LIMITS, max_path_samples=63),
        )
        self.assertNotEqual(preview.preview_sha256, narrower.preview_sha256)

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

    def test_truncated_path_authority_survives_propagation_and_restart(self) -> None:
        source_revision_id = self.revisions["dossier"].revision_id
        terminal_revision_id = source_revision_id
        exact_limit_revision_id: str | None = None
        with self.factory() as unit:
            for offset in range(66):
                index = 200 + offset
                terminal_revision_id = uid(index)
                revision = unit.aggregates.append(
                    AggregateRevisionDraft(
                        revision_id=terminal_revision_id,
                        aggregate_id=uid(1_000 + index),
                        aggregate_kind="evidence",
                        created_at=OCCURRED_AT,
                        modified_at=OCCURRED_AT,
                        display_label_observed=f"long-chain-{offset}",
                        display_label_normalized=None,
                        knowledge_status="observed",
                        rights_status="unknown",
                        dependency_coverage="complete",
                        material_dependencies=(dependency(index, source_revision_id),),
                    ),
                    AtomicRepositoryEvent(
                        event_id=uid(40_000 + index),
                        outbox_id=uid(50_000 + index),
                        event_type="evidence.created",
                        occurred_at=OCCURRED_AT,
                        available_at=OCCURRED_AT,
                        trace_id=f"{index + 1:032x}",
                        actor_type="worker",
                        actor_id=ACTOR_ID,
                        idempotency_key=f"dependency-impact-long-chain-{index}",
                    ),
                    expected_revision=None,
                )
                source_revision_id = revision.revision_id
                if offset == 58:
                    exact_limit_revision_id = revision.revision_id
            unit.commit()

        self.assertIsNotNone(exact_limit_revision_id)
        repository = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        preview = repository.preview(self.change())
        exact_limit_item = next(item for item in preview.impacts if item.output_revision_id == exact_limit_revision_id)
        preview_item = next(item for item in preview.impacts if item.output_revision_id == terminal_revision_id)
        self.assertFalse(exact_limit_item.path_truncated)
        self.assertEqual(64, exact_limit_item.path_length)
        self.assertEqual(64, len(exact_limit_item.path_revision_ids))
        self.assertEqual(exact_limit_revision_id, exact_limit_item.path_revision_ids[-1])
        self.assertTrue(preview_item.path_truncated)
        self.assertEqual(71, preview_item.path_length)
        self.assertEqual(terminal_revision_id, preview_item.path_revision_ids[-1])

        run = repository.begin(
            self.change(),
            preview_sha256=preview.preview_sha256,
            run_id=uid(90_060),
            batch_size=1_000,
        )
        completed = repository.advance(run.run_id, expected_checkpoint_sha256=run.checkpoint_sha256)
        self.assertEqual("completed", completed.state)
        reopened = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        exact_stale = next(
            item for item in reopened.stale_states() if item.output_revision_id == exact_limit_revision_id
        )
        stale = next(item for item in reopened.stale_states() if item.output_revision_id == terminal_revision_id)
        self.assertFalse(exact_stale.path_truncated)
        self.assertEqual(64, exact_stale.path_length)
        self.assertEqual(exact_limit_revision_id, exact_stale.path_revision_ids[-1])
        self.assertTrue(stale.path_truncated)
        self.assertEqual(71, stale.path_length)
        self.assertEqual(terminal_revision_id, stale.path_revision_ids[-1])

    def test_cycle_group_authority_survives_propagation_and_restart(self) -> None:
        matrix = self.revisions["matrix"].revision_id
        graph = self.revisions["graph"].revision_id
        synthesis = self.revisions["synthesis"].revision_id
        dossier = self.revisions["dossier"].revision_id
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            registration_event_id = str(
                connection.execute(
                    "SELECT event_id FROM provenance_events WHERE project_id=? ORDER BY occurred_at LIMIT 1",
                    (PROJECT_ID,),
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO material_dependencies (
                    dependency_id, project_id, output_revision_id,
                    dependency_kind, relation_type, dependency_revision_id,
                    configuration_id, configuration_version, fingerprint,
                    governing_policy_id, governing_policy_version,
                    semantic_sha256, registration_event_id, created_at
                ) VALUES (?, ?, ?, 'source-revision', 'direct', ?, NULL, NULL,
                          ?, 'dependency.material.v1', '1.0.0', ?, ?, ?)
                """,
                (
                    uid(39_999),
                    PROJECT_ID,
                    matrix,
                    dossier,
                    fingerprint("f"),
                    "e" * 64,
                    registration_event_id,
                    OCCURRED_AT,
                ),
            )
        finally:
            connection.close()

        repository = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        preview = repository.preview(self.change())
        expected_members = (matrix, graph, synthesis, dossier)
        cycle = next(group for group in preview.cycle_groups if group.member_revision_ids == expected_members)
        run = repository.begin(
            self.change(),
            preview_sha256=preview.preview_sha256,
            run_id=uid(90_061),
            batch_size=1_000,
        )
        completed = repository.advance(run.run_id, expected_checkpoint_sha256=run.checkpoint_sha256)
        self.assertEqual("completed", completed.state)

        reopened = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        durable = {
            item.output_revision_id: item.cycle_group_id
            for item in reopened.stale_states()
            if item.output_revision_id in expected_members
        }
        self.assertEqual(
            {member: cycle.cycle_group_id for member in expected_members},
            durable,
        )

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

    def test_graph_change_denies_advance_before_and_after_a_reopened_checkpoint(self) -> None:
        repository = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        preview = repository.preview(self.change())
        started = repository.begin(
            self.change(),
            preview_sha256=preview.preview_sha256,
            run_id=uid(90_010),
            batch_size=2,
        )
        self._append("post-begin-dependent", "dossier")
        with self.assertRaises(RepositoryConflict):
            repository.advance(started.run_id, expected_checkpoint_sha256=started.checkpoint_sha256)
        self.assertEqual((), repository.stale_states())

        fresh_change = replace(
            self.change(),
            change_id=uid(80_010),
            idempotency_key="fixture-extraction-superseded-checkpoint",
        )
        fresh_preview = repository.preview(fresh_change)
        checkpoint_run = repository.begin(
            fresh_change,
            preview_sha256=fresh_preview.preview_sha256,
            run_id=uid(90_011),
            batch_size=2,
        )
        checkpointed = repository.advance(
            checkpoint_run.run_id,
            expected_checkpoint_sha256=checkpoint_run.checkpoint_sha256,
        )
        self._append("post-checkpoint-dependent", "post-begin-dependent")
        reopened = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        with self.assertRaises(RepositoryConflict):
            reopened.advance(checkpointed.run_id, expected_checkpoint_sha256=checkpointed.checkpoint_sha256)
        self.assertEqual(2, len(reopened.stale_states()))

    def test_begin_denies_complete_change_authority_substitution_without_writes(self) -> None:
        repository = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        change = self.change()
        preview = repository.preview(change)
        substitutions = (
            replace(change, idempotency_key="substituted-key"),
            replace(change, reason="RIGHTS_POLICY"),
            replace(change, replacement_fingerprint=fingerprint("c")),
            replace(change, propagation_policy_id="dependency.substituted.v1"),
            replace(change, propagation_policy_version="2.0.0"),
            replace(change, actor_id=uid(81_020)),
            replace(change, trace_id="8" * 32),
            replace(change, occurred_at="2026-09-01T22:00:01.000Z"),
        )
        for index, substituted in enumerate(substitutions):
            with self.subTest(change=substituted), self.assertRaises(RepositoryConflict):
                repository.begin(
                    substituted,
                    preview_sha256=preview.preview_sha256,
                    run_id=uid(90_020 + index),
                    batch_size=2,
                )
        cross_aggregate = replace(
            change,
            replacement_revision_id=self.revisions["other-source"].revision_id,
        )
        with self.assertRaises(RepositoryConflict):
            repository.begin(
                cross_aggregate,
                preview_sha256=preview.preview_sha256,
                run_id=uid(90_040),
                batch_size=2,
            )
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(0, connection.execute("SELECT count(*) FROM dependency_impact_runs").fetchone()[0])
        finally:
            connection.close()

        with self.assertRaises(DependencyImpactLimitExceeded):
            repository.preview(
                change,
                limits=DependencyImpactLimits(max_nodes=1),
            )

    def test_conditional_decisions_are_immutable_and_reconstructable_after_restart(self) -> None:
        self._append("conditional-output", "extraction-v1", relation_type="conditional")
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            dependency_id = str(
                connection.execute(
                    "SELECT dependency_id FROM material_dependencies WHERE output_revision_id=?",
                    (self.revisions["conditional-output"].revision_id,),
                ).fetchone()[0]
            )
        finally:
            connection.close()
        repository = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        ignored = ConditionalDependencyDecision(
            dependency_id=dependency_id,
            decision_id=uid(81_030),
            disposition="ignore",
            governing_policy_id="dependency.material.v1",
            governing_policy_version="1.0.0",
            actor_id=ACTOR_ID,
            decided_at=OCCURRED_AT,
        )
        ignored_preview = repository.preview(self.change(), decisions=(ignored,))
        ignored_run = repository.begin(
            self.change(),
            preview_sha256=ignored_preview.preview_sha256,
            run_id=uid(90_050),
            batch_size=8,
            decisions=(ignored,),
        )
        ignored_run = repository.advance(
            ignored_run.run_id,
            expected_checkpoint_sha256=ignored_run.checkpoint_sha256,
        )
        self.assertEqual("completed", ignored_run.state)

        propagated = replace(ignored, decision_id=uid(81_031), disposition="propagate")
        propagated_change = replace(
            self.change(),
            change_id=uid(80_030),
            idempotency_key="fixture-extraction-superseded-propagated",
        )
        propagated_preview = repository.preview(propagated_change, decisions=(propagated,))
        propagated_run = repository.begin(
            propagated_change,
            preview_sha256=propagated_preview.preview_sha256,
            run_id=uid(90_051),
            batch_size=8,
            decisions=(propagated,),
        )
        propagated_run = repository.advance(
            propagated_run.run_id,
            expected_checkpoint_sha256=propagated_run.checkpoint_sha256,
        )
        self.assertEqual("completed", propagated_run.state)

        reopened = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        self.assertEqual((ignored,), reopened.decisions(ignored_run.run_id))
        self.assertEqual((propagated,), reopened.decisions(propagated_run.run_id))
        self.assertEqual("completed", reopened.audit(run_id=ignored_run.run_id)[-1].event_type)
        self.assertEqual("completed", reopened.audit(run_id=propagated_run.run_id)[-1].event_type)

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
