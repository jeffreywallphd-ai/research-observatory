from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from research_observatory_core.ports.repositories import (
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    DependencyChange,
    MaterialDependency,
    RepositoryConflict,
)
from research_observatory_core.ports.workflow_executor import WorkflowActor
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_dependency_impact_repository,
    sqlite_material_dependency_repository,
    sqlite_workflow_queue_repository,
)
from research_observatory_core.selective_recalculation import (
    RecalculationWorkflowIdentity,
    RecalculationWorkflowRequest,
    RestoreRevisionCommand,
    SelectiveRecalculationService,
)
from research_observatory_core.storage import development_plaintext_database_fixture, initialize_database
from research_observatory_core.workflow_contracts import workflow_snapshot_errors

PROJECT_ID = "01890f6e-6a40-7cc5-98b7-123456789abc"
SYSTEM_ID = "01890f6e-6a40-7cc5-98b7-000000000301"
RESEARCHER_ID = "01890f6e-6a40-7cc5-98b7-000000000302"
OCCURRED_AT = "2026-09-01T22:00:00.000Z"


def uid(index: int) -> str:
    return f"01890f6e-6a40-7cc5-98b7-{index:012x}"


def fingerprint(character: str) -> str:
    return "sha256:" + character * 64


def event(
    index: int,
    *,
    actor_type: str = "worker",
    event_type: str = "evidence.created",
    occurred_at: str | None = None,
) -> AtomicRepositoryEvent:
    timestamp = occurred_at or f"2026-09-01T22:00:{index:02d}.000Z"
    return AtomicRepositoryEvent(
        event_id=uid(10_000 + index),
        outbox_id=uid(20_000 + index),
        event_type=event_type,
        occurred_at=timestamp,
        available_at=timestamp,
        trace_id=f"{index + 1:032x}",
        actor_type=actor_type,  # type: ignore[arg-type]
        actor_id=RESEARCHER_ID if actor_type == "human" else SYSTEM_ID,
        idempotency_key=f"selective-recalculation-{index}",
    )


def dependency(index: int, revision: AggregateRevision, character: str) -> MaterialDependency:
    return MaterialDependency(
        dependency_id=uid(30_000 + index),
        dependency_kind="source-revision",
        relation_type="direct",
        revision_id=revision.revision_id,
        configuration_id=None,
        configuration_version=None,
        fingerprint=fingerprint(character),
        governing_policy_id="dependency.material.v1",
        governing_policy_version="1.0.0",
    )


class SelectiveRecalculationE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve() / "project"
        (self.root / "state").mkdir(parents=True)
        self.database = self.root / "state" / "project.sqlite3"
        self.protection = development_plaintext_database_fixture()
        self.protection.__enter__()
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=OCCURRED_AT)
        self.factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)
        self._build_fixture()
        self.impacts = sqlite_dependency_impact_repository(self.root, PROJECT_ID)
        preview = self.impacts.preview(self.change)
        run = self.impacts.begin(
            self.change,
            preview_sha256=preview.preview_sha256,
            run_id=uid(80_002),
            batch_size=8,
        )
        self.impacts.advance(run.run_id, expected_checkpoint_sha256=run.checkpoint_sha256)
        self.service = SelectiveRecalculationService(
            unit_of_work=self.factory,
            dependencies=sqlite_material_dependency_repository(self.root, PROJECT_ID),
            impacts=self.impacts,
            workflows=sqlite_workflow_queue_repository(self.root, PROJECT_ID),
        )

    def tearDown(self) -> None:
        self.protection.__exit__(None, None, None)
        self.temporary.cleanup()

    def _append(self, draft: AggregateRevisionDraft, index: int, expected: int | None = None) -> AggregateRevision:
        with self.factory() as unit:
            revision = unit.aggregates.append(draft, event(index), expected_revision=expected)
            unit.commit()
            return revision

    def _build_fixture(self) -> None:
        self.source_v1 = self._append(
            AggregateRevisionDraft(
                revision_id=uid(1),
                aggregate_id=uid(101),
                aggregate_kind="evidence",
                created_at=OCCURRED_AT,
                modified_at=OCCURRED_AT,
                display_label_observed="source v1",
                display_label_normalized=None,
                knowledge_status="observed",
                rights_status="allowed",
                dependency_coverage="not-applicable",
            ),
            1,
        )
        self.source_v2 = self._append(
            replace(
                AggregateRevisionDraft(
                    revision_id=uid(2),
                    aggregate_id=self.source_v1.aggregate_id,
                    aggregate_kind="evidence",
                    created_at=OCCURRED_AT,
                    modified_at="2026-09-01T22:00:02.000Z",
                    display_label_observed="source v2",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="allowed",
                    dependency_coverage="not-applicable",
                ),
                provenance_inputs=(self.source_v1,),
            ),
            2,
            0,
        )
        self.verified = self._append(
            AggregateRevisionDraft(
                revision_id=uid(3),
                aggregate_id=uid(103),
                aggregate_kind="evidence",
                created_at=OCCURRED_AT,
                modified_at="2026-09-01T22:00:03.000Z",
                display_label_observed="verified unchanged input",
                display_label_normalized=None,
                knowledge_status="verified",
                rights_status="allowed",
                dependency_coverage="not-applicable",
            ),
            3,
        )
        self.adjudicated = self._append(
            AggregateRevisionDraft(
                revision_id=uid(4),
                aggregate_id=uid(104),
                aggregate_kind="evidence",
                created_at=OCCURRED_AT,
                modified_at="2026-09-01T22:00:04.000Z",
                display_label_observed="adjudicated synthesis",
                display_label_normalized="adjudicated synthesis",
                knowledge_status="adjudicated",
                rights_status="allowed",
                dependency_coverage="complete",
                provenance_inputs=(self.source_v1, self.verified),
                material_dependencies=(
                    dependency(4, self.source_v1, "a"),
                    dependency(5, self.verified, "c"),
                ),
            ),
            4,
        )
        self.change = DependencyChange(
            change_id=uid(80_001),
            idempotency_key="source-v1-superseded",
            reason="SOURCE_VERSION",
            dependency_kind="source-revision",
            previous_revision_id=self.source_v1.revision_id,
            replacement_revision_id=self.source_v2.revision_id,
            configuration_id=None,
            previous_configuration_version=None,
            replacement_configuration_version=None,
            previous_fingerprint=fingerprint("a"),
            replacement_fingerprint=fingerprint("b"),
            propagation_policy_id="dependency.propagation.v1",
            propagation_policy_version="1.0.0",
            actor_id=SYSTEM_ID,
            trace_id="9" * 32,
            occurred_at=OCCURRED_AT,
        )

    def request(self, *, target_revision_id: str | None = None) -> RecalculationWorkflowRequest:
        return RecalculationWorkflowRequest(
            target_revision_id=target_revision_id or self.adjudicated.revision_id,
            change=self.change,
            identity=RecalculationWorkflowIdentity(
                workflow_definition_id=uid(90_001),
                definition_revision_id=uid(90_002),
                workflow_run_id=uid(90_003),
                snapshot_id=uid(90_004),
                step_run_id=uid(90_005),
                job_id=uid(90_006),
                history_event_ids=tuple(uid(91_000 + index) for index in range(5)),
            ),
            actor=WorkflowActor(SYSTEM_ID, "system", "workflow-coordinator"),
            created_at="2026-09-01T22:01:00.000Z",
            available_at="2026-09-01T22:01:00.000Z",
            intent_id=uid(90_007),
            intent_revision_id=uid(90_008),
            intent_sha256=fingerprint("d"),
            policy_id="private-local-research",
            policy_version="1.0.0",
            policy_sha256=fingerprint("e"),
            configuration_id="selective-recalculation-default",
            configuration_version="1.0.0",
            priority=10,
        )

    def test_selective_job_reuses_only_unchanged_verified_inputs_and_survives_restart(self) -> None:
        scheduled = self.service.schedule(self.request())
        replay = self.service.schedule(self.request())

        self.assertEqual(self.adjudicated.revision_id, scheduled.workflow.target_revision_id)
        self.assertEqual((self.source_v2.revision_id,), scheduled.workflow.replacement_revision_ids)
        self.assertEqual((self.verified.revision_id,), scheduled.workflow.reused_revision_ids)
        self.assertEqual(scheduled.workflow.plan_sha256, scheduled.workflow.submission.command_fingerprint)
        definition = json.loads(scheduled.workflow.submission.definition_json)
        snapshot = json.loads(scheduled.workflow.submission.snapshot_json)
        self.assertEqual((), workflow_snapshot_errors(definition, snapshot))
        media_by_revision = {item["revisionId"]: item["mediaType"] for item in snapshot["artifacts"]}
        self.assertEqual(
            "application/vnd.research-observatory.replacement-revision+json",
            media_by_revision[self.source_v2.revision_id],
        )
        self.assertNotIn(self.source_v1.revision_id, media_by_revision)
        self.assertEqual(1, len(scheduled.workflow.stale_cause_ids))
        self.assertEqual("runnable", scheduled.job.state)
        self.assertEqual(scheduled.job, replay.job)
        self.assertEqual(scheduled.workflow.submission, replay.workflow.submission)

        reopened = sqlite_workflow_queue_repository(self.root, PROJECT_ID)
        authority = reopened.authority(scheduled.job.job_id)
        self.assertEqual(scheduled.workflow.submission.definition_json, authority.definition_json)
        self.assertEqual(scheduled.workflow.submission.snapshot_json, authority.snapshot_json)
        projection = reopened.task_center(limit=10)[0]
        self.assertEqual("selective-recalculation", projection.workflow_key)
        self.assertEqual("queued", projection.state)

    def test_candidate_comparison_and_adjudicated_restore_append_history_without_overwrite(self) -> None:
        candidate_draft = AggregateRevisionDraft(
            revision_id=uid(5),
            aggregate_id=self.adjudicated.aggregate_id,
            aggregate_kind="evidence",
            created_at=self.adjudicated.created_at,
            modified_at="2026-09-01T22:02:00.000Z",
            display_label_observed="recomputed synthesis candidate",
            display_label_normalized="recomputed synthesis candidate",
            knowledge_status="verified",
            rights_status="allowed",
            dependency_coverage="complete",
            provenance_inputs=(self.adjudicated, self.source_v2, self.verified),
            material_dependencies=(
                dependency(6, self.source_v2, "b"),
                dependency(7, self.verified, "c"),
            ),
        )
        candidate = self.service.append_candidate(
            candidate_draft,
            event(5, event_type="evidence.recalculated"),
            expected_current_revision_id=self.adjudicated.revision_id,
        )
        self.assertEqual(
            candidate,
            self.service.append_candidate(
                candidate_draft,
                event(5, event_type="evidence.recalculated"),
                expected_current_revision_id=self.adjudicated.revision_id,
            ),
        )
        comparison = self.service.compare(self.adjudicated.revision_id, candidate.revision_id)
        self.assertEqual(
            ("display-label-normalized", "display-label-observed", "knowledge-status"),
            comparison.changed_fields,
        )
        self.assertEqual(1, candidate.revision)

        restored = self.service.restore(
            RestoreRevisionCommand(
                prior_adjudicated_revision_id=self.adjudicated.revision_id,
                expected_current_revision_id=candidate.revision_id,
                new_revision_id=uid(6),
                dependency_ids=(uid(30_008), uid(30_009)),
                modified_at="2026-09-01T22:03:00.000Z",
                event=event(
                    6,
                    actor_type="human",
                    event_type="aggregate.revision-restored",
                    occurred_at="2026-09-01T22:03:00.000Z",
                ),
            )
        )
        self.assertEqual(2, restored.revision)
        self.assertEqual(
            restored,
            self.service.restore(
                RestoreRevisionCommand(
                    prior_adjudicated_revision_id=self.adjudicated.revision_id,
                    expected_current_revision_id=candidate.revision_id,
                    new_revision_id=uid(6),
                    dependency_ids=(uid(30_008), uid(30_009)),
                    modified_at="2026-09-01T22:03:00.000Z",
                    event=event(
                        6,
                        actor_type="human",
                        event_type="aggregate.revision-restored",
                        occurred_at="2026-09-01T22:03:00.000Z",
                    ),
                )
            ),
        )
        self.assertEqual("adjudicated", restored.knowledge_status)
        self.assertEqual((), self.service.compare(self.adjudicated.revision_id, restored.revision_id).changed_fields)

        reopened_factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)
        with reopened_factory() as unit:
            self.assertEqual(
                (self.adjudicated.revision_id, candidate.revision_id, restored.revision_id),
                tuple(item.revision_id for item in unit.aggregates.history(self.adjudicated.aggregate_id)),
            )
            self.assertEqual(self.adjudicated, unit.aggregates.get_revision(self.adjudicated.revision_id))
        restored_dependencies = sqlite_material_dependency_repository(self.root, PROJECT_ID).registration(
            restored.revision_id
        )
        original_dependencies = sqlite_material_dependency_repository(self.root, PROJECT_ID).registration(
            self.adjudicated.revision_id
        )
        self.assertEqual(
            tuple(item.revision_id for item in original_dependencies.dependencies),
            tuple(item.revision_id for item in restored_dependencies.dependencies),
        )

    def test_substitution_and_non_adjudicated_restore_fail_without_canonical_change(self) -> None:
        with self.assertRaises(RepositoryConflict):
            self.service.schedule(self.request(target_revision_id=self.source_v1.revision_id))
        with self.assertRaises(RepositoryConflict):
            self.service.compare(self.source_v1.revision_id, self.adjudicated.revision_id)
        with self.assertRaises(RepositoryConflict):
            self.service.restore(
                RestoreRevisionCommand(
                    prior_adjudicated_revision_id=self.verified.revision_id,
                    expected_current_revision_id=self.verified.revision_id,
                    new_revision_id=uid(7),
                    dependency_ids=(),
                    modified_at="2026-09-01T22:04:00.000Z",
                    event=event(
                        7,
                        actor_type="human",
                        event_type="aggregate.revision-restored",
                        occurred_at="2026-09-01T22:04:00.000Z",
                    ),
                )
            )
        with self.factory() as unit:
            self.assertEqual((self.adjudicated,), unit.aggregates.history(self.adjudicated.aggregate_id))


if __name__ == "__main__":
    unittest.main()
