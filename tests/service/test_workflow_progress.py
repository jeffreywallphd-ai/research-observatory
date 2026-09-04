from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.models import WorkflowProgressCommand  # noqa: E402
from research_observatory_core.ports.repositories import (  # noqa: E402
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
)
from research_observatory_core.projects import ProjectLifecycleService  # noqa: E402
from research_observatory_core.repositories import (  # noqa: E402
    create_sqlite_unit_of_work_factory,
    sqlite_dependency_impact_repository,
    sqlite_intent_revision_repository,
    sqlite_workflow_progress_repository,
)
from research_observatory_core.research_intents import ResearchIntentService  # noqa: E402
from research_observatory_core.storage import development_plaintext_database_fixture  # noqa: E402
from research_observatory_core.workflow_progress import (  # noqa: E402
    WorkflowProgressProblem,
    WorkflowProgressService,
)

TRACE = "a" * 32
ACTOR_ID = "018f0000-0000-7000-8000-000000000001"
INTENT_FIXTURE = REPO / "tests" / "service" / "fixtures" / "valid-intent-draft-request.json"


class WorkflowProgressServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_profile = development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-workflow-progress-")
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.database_profile.__exit__, None, None, None)
        self.projects = ProjectLifecycleService()
        created = self.projects.create(
            parent_directory=self.temporary.name,
            directory_name="guided-study",
            display_name="Guided study",
            template_id="theory-synthesis",
            trace_id=TRACE,
        )
        self.root = created.root
        self.project = self.projects.open(root=self.root, trace_id=TRACE)
        self.intents = ResearchIntentService(
            self.projects,
            repository_factory=sqlite_intent_revision_repository,
            stale_state_repository_factory=sqlite_dependency_impact_repository,
            local_actor_id=ACTOR_ID,
        )
        self._save_intent("theory-synthesis")
        self.service = self._service()

    def tearDown(self) -> None:
        self.projects.shutdown()

    def _save_intent(self, profile_id: str, *, expected_revision: int = 0, key: str = "1" * 32):
        payload = json.loads(INTENT_FIXTURE.read_text(encoding="utf-8"))
        payload.update(
            {
                "root": self.root,
                "expectedRevision": expected_revision,
                "primaryUseCase": profile_id,
            }
        )
        from research_observatory_core.models import IntentDraftRequest

        return self.intents.save_draft(
            IntentDraftRequest.model_validate(payload),
            trace_id=TRACE,
            idempotency_key=key,
        )

    def _service(self) -> WorkflowProgressService:
        return WorkflowProgressService(
            self.projects,
            repository_factory=sqlite_workflow_progress_repository,
            intent_repository_factory=sqlite_intent_revision_repository,
            stale_state_repository_factory=sqlite_dependency_impact_repository,
            local_actor_id=ACTOR_ID,
        )

    def _command(self, workspace, action: str, **changes: object) -> WorkflowProgressCommand:
        payload: dict[str, object] = {
            "root": self.root,
            "action": action,
            "stageKey": workspace.recommended_stage_key,
            "expectedSelectionRevisionId": workspace.selection_revision_id,
            "expectedSelectionRevisionContentHash": workspace.selection_revision_content_hash,
            "expectedStageStateRevisionId": (
                workspace.current.stage_state_revision_id if workspace.current is not None else None
            ),
            "expectedStageStateRevisionContentHash": (
                workspace.current.revision_content_hash if workspace.current is not None else None
            ),
            "completionEvidenceRevisionIds": [],
            "supportingPageContractId": None,
            "rationale": None,
        }
        payload.update(changes)
        return WorkflowProgressCommand.model_validate(payload)

    def _append_evidence(self):
        database = Path(self.root) / "state" / "project.sqlite3"
        factory = create_sqlite_unit_of_work_factory(database, self.project.project_id)
        revision_id = new_uuid_v7()
        with factory() as unit:
            revision = unit.aggregates.append(
                AggregateRevisionDraft(
                    revision_id=revision_id,
                    aggregate_id=new_uuid_v7(),
                    aggregate_kind="evidence",
                    created_at="2026-09-04T02:00:00.000Z",
                    modified_at="2026-09-04T02:00:00.000Z",
                    display_label_observed="Researcher-reviewed completion evidence",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                ),
                AtomicRepositoryEvent(
                    event_id=new_uuid_v7(),
                    outbox_id=new_uuid_v7(),
                    event_type="evidence.created",
                    occurred_at="2026-09-04T02:00:00.000Z",
                    available_at="2026-09-04T02:00:00.000Z",
                    trace_id="b" * 32,
                    actor_type="human",
                    actor_id=ACTOR_ID,
                    idempotency_key="workflow-progress-completion-evidence",
                ),
                expected_revision=None,
            )
            unit.commit()
        return revision

    def test_explicit_human_start_and_completion_survive_restart(self) -> None:
        unopened = self.service.workspace(self.root)
        self.assertTrue(unopened.bootstrap_required)
        self.assertIsNone(unopened.current)

        started = self.service.command(
            self._command(unopened, "start"),
            trace_id=TRACE,
            idempotency_key="2" * 32,
        )
        self.assertEqual("current", started.current.status)
        started_revision = started.current.stage_state_revision_id

        # Creating an analytical/evidence output does not confer scholarly-stage authority.
        evidence = self._append_evidence()
        unchanged = self._service().workspace(self.root)
        self.assertEqual(started_revision, unchanged.current.stage_state_revision_id)

        completed = self.service.command(
            self._command(
                unchanged,
                "complete",
                stageKey=unchanged.current.stage_key,
                completionEvidenceRevisionIds=[evidence.revision_id],
            ),
            trace_id=TRACE,
            idempotency_key="3" * 32,
        )
        self.assertEqual("completed", completed.history[0].status)
        self.assertEqual(1, len(completed.history[0].completion_evidence_ids))
        self.assertNotEqual(started_revision, completed.current.stage_state_revision_id)

        restarted = self._service().workspace(self.root)
        self.assertEqual(completed.current, restarted.current)
        self.assertEqual(completed.history, restarted.history)

    def test_revisitable_profile_appends_a_new_pass_without_erasing_prior_state(self) -> None:
        started = self.service.command(
            self._command(self.service.workspace(self.root), "start"),
            trace_id=TRACE,
            idempotency_key="4" * 32,
        )
        revisited = self.service.command(
            self._command(started, "revisit", stageKey=started.current.stage_key),
            trace_id=TRACE,
            idempotency_key="5" * 32,
        )

        self.assertEqual(2, revisited.current.pass_number)
        self.assertEqual(started.current.stage_state_id, revisited.current.stage_state_id)
        self.assertEqual(started.current.stage_state_revision_id, revisited.current.parent_state_revision_id)
        self.assertIn(started.current, revisited.history)

    def test_linear_profile_rejects_a_second_pass_without_mutation(self) -> None:
        current = self.intents.workspace(self.root).current
        self._save_intent("systematic-review", expected_revision=current.revision, key="6" * 32)
        before = self._service().workspace(self.root)
        started = self.service.command(
            self._command(before, "start"),
            trace_id=TRACE,
            idempotency_key="7" * 32,
        )

        with self.assertRaisesRegex(WorkflowProgressProblem, "RO-CORE-WORKFLOW-PROGRESS-CYCLE-DENIED"):
            self.service.command(
                self._command(started, "revisit", stageKey=started.current.stage_key),
                trace_id=TRACE,
                idempotency_key="8" * 32,
            )
        self.assertEqual(started, self._service().workspace(self.root))

    def test_supporting_handoff_survives_restart_and_expires_when_primary_changes(self) -> None:
        started = self.service.command(
            self._command(self.service.workspace(self.root), "start"),
            trace_id=TRACE,
            idempotency_key="9" * 32,
        )
        detached = self.service.command(
            self._command(
                started,
                "open-supporting",
                stageKey=started.current.stage_key,
                supportingPageContractId="project-settings.html",
            ),
            trace_id=TRACE,
            idempotency_key="a" * 32,
        )
        self.assertEqual(started.current, detached.current)
        self.assertEqual("supporting", detached.supporting_handoff.navigation_role)
        self.assertEqual(
            started.current.stage_state_revision_id,
            detached.supporting_handoff.return_stage_state_revision_id,
        )
        self.assertEqual(detached.supporting_handoff, self._service().workspace(self.root).supporting_handoff)

        revisited = self.service.command(
            self._command(started, "revisit", stageKey=started.current.stage_key),
            trace_id=TRACE,
            idempotency_key="b" * 32,
        )
        self.assertIsNone(revisited.supporting_handoff)


if __name__ == "__main__":
    unittest.main()
