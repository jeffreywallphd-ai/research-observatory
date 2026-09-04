from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
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
from research_observatory_core.research_intents import IntentProblem, ResearchIntentService  # noqa: E402
from research_observatory_core.storage import development_plaintext_database_fixture  # noqa: E402
from research_observatory_core.workflow_progress import (  # noqa: E402
    WorkflowProgressProblem,
    WorkflowProgressService,
)

TRACE = "a" * 32
ACTOR_ID = "018f0000-0000-7000-8000-000000000001"
TOKEN = "0123456789abcdef" * 4
AUTHORITY = "127.0.0.1:49152"
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
        self._save_intent("hermeneutic-inquiry")
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
        if profile_id == "systematic-review":
            payload.update(
                {
                    "noveltyStandard": "bounded-comparative",
                    "noveltyRationale": "Bound comparative claims to the recorded protocol and corpus.",
                    "stoppingConditions": ["coverage-threshold"],
                }
            )
        from research_observatory_core.models import IntentDraftRequest

        command = IntentDraftRequest.model_validate(payload)
        if expected_revision > 0:
            preview = self.intents.preview(command.to_impact_request())
            command = command.model_copy(update={"impact_acknowledgement": preview.acknowledgement_token})
        return self.intents.save_draft(
            command,
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
                    dependency_coverage="not-applicable",
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

    def test_authenticated_api_exposes_read_and_explicit_command_without_actor_injection(self) -> None:
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(TOKEN),
            expected_authority=AUTHORITY,
            projects=self.projects,
            intents=self.intents,
            workflow_progress=self.service,
        )
        with TestClient(
            app,
            base_url=f"http://{AUTHORITY}",
            headers={"Authorization": f"Bearer {TOKEN}"},
            client=("127.0.0.1", 50000),
        ) as client:
            workspace = client.post("/projects/workflow-progress", json={"root": self.root})
            self.assertEqual(200, workspace.status_code)
            payload = workspace.json()
            self.assertTrue(payload["bootstrapRequired"])
            command = {
                "root": self.root,
                "action": "start",
                "stageKey": payload["recommendedStageKey"],
                "expectedSelectionRevisionId": payload["selectionRevisionId"],
                "expectedSelectionRevisionContentHash": payload["selectionRevisionContentHash"],
                "expectedStageStateRevisionId": None,
                "expectedStageStateRevisionContentHash": None,
                "completionEvidenceRevisionIds": [],
                "supportingPageContractId": None,
                "rationale": None,
            }
            started = client.post(
                "/projects/workflow-progress/commands",
                json=command,
                headers={"Idempotency-Key": "e" * 32},
            )
            self.assertEqual(200, started.status_code)
            self.assertEqual("current", started.json()["current"]["status"])
            self.assertNotIn("actor", json.dumps(command))

    def test_replay_is_exact_and_conflicting_reuse_leaves_authority_unchanged(self) -> None:
        workspace = self.service.workspace(self.root)
        command = self._command(workspace, "start")
        started = self.service.command(command, trace_id=TRACE, idempotency_key="2" * 32)
        replayed = self._service().command(command, trace_id=TRACE, idempotency_key="2" * 32)
        self.assertEqual(started, replayed)

        substituted = command.model_copy(update={"stage_key": "substituted-stage"})
        with self.assertRaisesRegex(
            WorkflowProgressProblem,
            "RO-CORE-WORKFLOW-PROGRESS-IDEMPOTENCY-CONFLICT",
        ):
            self.service.command(substituted, trace_id=TRACE, idempotency_key="2" * 32)
        self.assertEqual(started, self._service().workspace(self.root))

    def test_completion_rejects_noncanonical_evidence_and_selection_substitution(self) -> None:
        started = self.service.command(
            self._command(self.service.workspace(self.root), "start"),
            trace_id=TRACE,
            idempotency_key="3" * 32,
        )
        with self.assertRaisesRegex(
            WorkflowProgressProblem,
            "RO-CORE-WORKFLOW-PROGRESS-EVIDENCE-NOT-FOUND",
        ):
            self.service.command(
                self._command(
                    started,
                    "complete",
                    stageKey=started.current.stage_key,
                    completionEvidenceRevisionIds=["018f47a2-4d6b-7f78-9f2e-7fb76c86d099"],
                ),
                trace_id=TRACE,
                idempotency_key="4" * 32,
            )
        with self.assertRaisesRegex(WorkflowProgressProblem, "RO-CORE-WORKFLOW-PROGRESS-CONFLICT"):
            self.service.command(
                self._command(
                    started,
                    "revisit",
                    expectedSelectionRevisionContentHash="sha256:" + "f" * 64,
                ),
                trace_id=TRACE,
                idempotency_key="5" * 32,
            )
        self.assertEqual(started, self._service().workspace(self.root))

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

    def test_completed_revisitable_workflow_can_begin_an_explicit_new_pass(self) -> None:
        progress = self.service.command(
            self._command(self.service.workspace(self.root), "start"),
            trace_id=TRACE,
            idempotency_key="f" * 32,
        )
        evidence = self._append_evidence()
        sequence = 16
        while progress.current is not None:
            progress = self.service.command(
                self._command(
                    progress,
                    "complete",
                    stageKey=progress.current.stage_key,
                    completionEvidenceRevisionIds=[evidence.revision_id],
                ),
                trace_id=TRACE,
                idempotency_key=f"{sequence:032x}",
            )
            sequence += 1
        completed_head = next(item for item in progress.history if item.stage_key == progress.recommended_stage_key)

        revisited = self.service.command(
            self._command(
                progress,
                "revisit",
                expectedStageStateRevisionId=completed_head.stage_state_revision_id,
                expectedStageStateRevisionContentHash=completed_head.revision_content_hash,
            ),
            trace_id=TRACE,
            idempotency_key=f"{sequence:032x}",
        )

        self.assertEqual("current", revisited.current.status)
        self.assertEqual(2, revisited.current.pass_number)
        self.assertEqual(completed_head.stage_state_id, revisited.current.stage_state_id)

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

    def test_profile_change_atomically_binds_exact_prior_stage_head(self) -> None:
        started = self.service.command(
            self._command(self.service.workspace(self.root), "start"),
            trace_id=TRACE,
            idempotency_key="c" * 32,
        )
        current_intent = self.intents.workspace(self.root).current

        self._save_intent("systematic-review", expected_revision=current_intent.revision, key="d" * 32)

        authority = sqlite_intent_revision_repository(
            Path(self.root), self.project.project_id
        ).read_workflow_authority()
        changed = json.loads(authority.selections[-1].content_json)
        impacts = changed["impactPreview"]["priorStageStates"]
        self.assertEqual(1, len(impacts))
        self.assertEqual(started.current.stage_state_id, impacts[0]["stageStateId"])
        self.assertEqual(started.current.stage_state_revision_id, impacts[0]["stageStateRevisionId"])
        self.assertEqual(started.current.revision_content_hash, impacts[0]["stageStateRevisionContentHash"])

        restarted = self._service().workspace(self.root)
        self.assertTrue(restarted.bootstrap_required)
        self.assertIsNone(restarted.current)
        self.assertEqual("systematic-review", restarted.profile_id)

    def test_profile_change_cas_rejects_a_concurrent_stage_write(self) -> None:
        started = self.service.command(
            self._command(self.service.workspace(self.root), "start"),
            trace_id=TRACE,
            idempotency_key="6" * 32,
        )
        prior_intent = self.intents.workspace(self.root).current
        raced = False

        class RacingRepository:
            def __init__(inner_self, delegate):
                inner_self.delegate = delegate

            def __getattr__(inner_self, name):
                return getattr(inner_self.delegate, name)

            def append(inner_self, **kwargs):
                nonlocal raced
                if not raced:
                    raced = True
                    self.service.command(
                        self._command(
                            started,
                            "open-supporting",
                            stageKey=started.current.stage_key,
                            supportingPageContractId="project-settings.html",
                        ),
                        trace_id=TRACE,
                        idempotency_key="7" * 32,
                    )
                return inner_self.delegate.append(**kwargs)

        racing_intents = ResearchIntentService(
            self.projects,
            repository_factory=lambda path, project_id: RacingRepository(
                sqlite_intent_revision_repository(path, project_id)
            ),
            stale_state_repository_factory=sqlite_dependency_impact_repository,
            local_actor_id=ACTOR_ID,
        )
        payload = json.loads(INTENT_FIXTURE.read_text(encoding="utf-8"))
        payload.update(
            {
                "root": self.root,
                "expectedRevision": prior_intent.revision,
                "primaryUseCase": "systematic-review",
                "noveltyStandard": "bounded-comparative",
                "noveltyRationale": "Bound comparative claims to the recorded protocol and corpus.",
                "stoppingConditions": ["coverage-threshold"],
            }
        )
        from research_observatory_core.models import IntentDraftRequest

        draft = IntentDraftRequest.model_validate(payload)
        preview = racing_intents.preview(draft.to_impact_request())
        draft = draft.model_copy(update={"impact_acknowledgement": preview.acknowledgement_token})
        with self.assertRaisesRegex(IntentProblem, "RO-CORE-INTENT-REVISION-CONFLICT"):
            racing_intents.save_draft(draft, trace_id=TRACE, idempotency_key="8" * 32)

        self.assertEqual(prior_intent.revision, self.intents.workspace(self.root).current.revision)
        self.assertIsNotNone(self._service().workspace(self.root).supporting_handoff)

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
