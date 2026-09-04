from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
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
from research_observatory_core.workflow_progress import WorkflowProgressService  # noqa: E402

TRACE = "a" * 32
ACTOR_ID = "018f0000-0000-7000-8000-000000000001"
TOKEN = "0123456789abcdef" * 4
AUTHORITY = "127.0.0.1:49152"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
REFERENCE_ID = "RO-UI-ACADEMIC-MINIMAL-1.5"
REFERENCE_VERSION = "1.5"
PROFILE_CATALOG_VERSION = "1.0.0"
PROFILE_CATALOG_HASH = "sha256:0a3887774b30bb2d2d7fced5c9e43452e7e34993407a6122155b740814350e49"
INTENT_GUIDANCE_HASH = "sha256:2feffbaf216da3adb4d8fe0b3ca6e2579cdc2dcedc2d57341086a14def5fe0d2"
CYCLICAL_PROFILES = {
    "hermeneutic-inquiry",
    "living-review",
    "manuscript-review-revision",
}


class WorkflowProfileMatrixEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_profile = development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.addCleanup(self.database_profile.__exit__, None, None, None)
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-workflow-matrix-")
        self.addCleanup(self.temporary.cleanup)

    def _stack(self) -> tuple[ProjectLifecycleService, ResearchIntentService, WorkflowProgressService]:
        projects = ProjectLifecycleService()
        intents = ResearchIntentService(
            projects,
            repository_factory=sqlite_intent_revision_repository,
            stale_state_repository_factory=sqlite_dependency_impact_repository,
            local_actor_id=ACTOR_ID,
        )
        progress = WorkflowProgressService(
            projects,
            repository_factory=sqlite_workflow_progress_repository,
            intent_repository_factory=sqlite_intent_revision_repository,
            stale_state_repository_factory=sqlite_dependency_impact_repository,
            local_actor_id=ACTOR_ID,
        )
        return projects, intents, progress

    @staticmethod
    def _app(
        projects: ProjectLifecycleService,
        intents: ResearchIntentService,
        progress: WorkflowProgressService,
    ):
        return create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(TOKEN),
            expected_authority=AUTHORITY,
            projects=projects,
            intents=intents,
            workflow_progress=progress,
        )

    @staticmethod
    def _command(root: str, workspace: dict[str, Any], action: str, **changes: object) -> dict[str, object]:
        current = workspace.get("current")
        payload: dict[str, object] = {
            "root": root,
            "action": action,
            "stageKey": workspace["recommendedStageKey"],
            "expectedSelectionRevisionId": workspace["selectionRevisionId"],
            "expectedSelectionRevisionContentHash": workspace["selectionRevisionContentHash"],
            "expectedStageStateRevisionId": current["stageStateRevisionId"] if current else None,
            "expectedStageStateRevisionContentHash": current["revisionContentHash"] if current else None,
            "revisitSourceStageStateRevisionId": None,
            "revisitSourceStageStateRevisionContentHash": None,
            "completionEvidenceRevisionIds": [],
            "supportingPageContractId": None,
            "rationale": None,
        }
        payload.update(changes)
        return payload

    @staticmethod
    def _append_evidence(root: str, project_id: str, sequence: int) -> str:
        database = Path(root) / "state" / "project.sqlite3"
        factory = create_sqlite_unit_of_work_factory(database, project_id)
        revision_id = new_uuid_v7()
        with factory() as unit:
            unit.aggregates.append(
                AggregateRevisionDraft(
                    revision_id=revision_id,
                    aggregate_id=new_uuid_v7(),
                    aggregate_kind="evidence",
                    created_at="2026-09-04T12:00:00.000Z",
                    modified_at="2026-09-04T12:00:00.000Z",
                    display_label_observed="Researcher-reviewed workflow evidence",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                    dependency_coverage="not-applicable",
                ),
                AtomicRepositoryEvent(
                    event_id=new_uuid_v7(),
                    outbox_id=new_uuid_v7(),
                    event_type="evidence.created",
                    occurred_at="2026-09-04T12:00:00.000Z",
                    available_at="2026-09-04T12:00:00.000Z",
                    trace_id=f"{sequence:032x}",
                    actor_type="human",
                    actor_id=ACTOR_ID,
                    idempotency_key=f"{sequence + 1:032x}",
                ),
                expected_revision=None,
            )
            unit.commit()
        return revision_id

    def _catalog(self, client: TestClient) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        response = client.get("/workflow-profiles/catalog")
        self.assertEqual(200, response.status_code)
        catalog = response.json()
        self.assertEqual(REFERENCE_ID, catalog["referenceId"])
        self.assertEqual(REFERENCE_VERSION, catalog["referenceVersion"])
        self.assertEqual(PROFILE_CATALOG_VERSION, catalog["profileCatalogVersion"])
        self.assertEqual(PROFILE_CATALOG_HASH, catalog["profileCatalogHash"])
        self.assertEqual(INTENT_GUIDANCE_HASH, catalog["intentGuidanceHash"])
        self.assertEqual(14, len(catalog["profiles"]))
        return catalog, {profile["profileId"]: profile for profile in catalog["profiles"]}

    def test_all_fourteen_profiles_start_at_creation_and_resume_exactly_after_restart(self) -> None:
        projects, intents, progress = self._stack()
        roots: dict[str, tuple[str, str, str]] = {}
        try:
            with TestClient(
                self._app(projects, intents, progress),
                base_url=f"http://{AUTHORITY}",
                headers=HEADERS,
                client=("127.0.0.1", 50000),
            ) as client:
                catalog, profiles = self._catalog(client)
                self.assertTrue(catalog["allToolsAccessible"])
                for index, (profile_id, profile) in enumerate(profiles.items(), start=1):
                    with self.subTest(profile=profile_id):
                        created = client.post(
                            "/projects",
                            json={
                                "parentDirectory": self.temporary.name,
                                "directoryName": profile_id,
                                "displayName": profile["title"],
                                "primaryUseCase": profile_id,
                                "researchObjective": f"Exercise the exact {profile_id} governed workflow.",
                            },
                        )
                        self.assertEqual(200, created.status_code, created.text)
                        root = created.json()["root"]
                        opened = client.post("/projects/open", json={"root": root})
                        self.assertEqual(200, opened.status_code, opened.text)

                        intent = client.post("/projects/intent", json={"root": root})
                        current_intent = intent.json()["current"]
                        self.assertEqual(profile_id, current_intent["primaryUseCase"])
                        self.assertEqual(profile["defaultEvidenceTypes"], current_intent["evidenceTypes"])
                        self.assertEqual(profile["defaultAutonomyLevel"], current_intent["autonomyLevel"])
                        self.assertEqual(profile["defaultStoppingConditions"], current_intent["stoppingConditions"])
                        self.assertIsNone(current_intent["noveltyStandard"])
                        workspace = client.post("/projects/workflow-progress", json={"root": root})
                        self.assertEqual(200, workspace.status_code, workspace.text)
                        before = workspace.json()
                        self.assertTrue(before["bootstrapRequired"])
                        self.assertEqual(profile_id, before["profileId"])
                        self.assertEqual(profile["stages"][0]["stageKey"], before["recommendedStageKey"])

                        started_response = client.post(
                            "/projects/workflow-progress/commands",
                            json=self._command(root, before, "start"),
                            headers={"Idempotency-Key": f"{index:032x}"},
                        )
                        self.assertEqual(200, started_response.status_code, started_response.text)
                        started = started_response.json()
                        self.assertEqual(profile["stages"][0]["stageKey"], started["current"]["stageKey"])
                        self.assertEqual("current", started["current"]["status"])

                        supporting_response = client.post(
                            "/projects/workflow-progress/commands",
                            json=self._command(
                                root,
                                started,
                                "open-supporting",
                                stageKey=started["current"]["stageKey"],
                                supportingPageContractId="application-settings.html",
                            ),
                            headers={"Idempotency-Key": f"{index + 100:032x}"},
                        )
                        self.assertEqual(200, supporting_response.status_code, supporting_response.text)
                        detached = supporting_response.json()
                        self.assertEqual(started["current"], detached["current"])
                        self.assertEqual("application-settings.html", detached["supportingHandoff"]["pageContractId"])
                        self.assertEqual(
                            started["current"]["stageStateRevisionId"],
                            detached["supportingHandoff"]["returnStageStateRevisionId"],
                        )
                        self.assertTrue(profile["expectedOutputs"])
                        self.assertEqual(
                            list(range(1, len(profile["stages"]) + 1)),
                            [stage["order"] for stage in profile["stages"]],
                        )
                        roots[profile_id] = (
                            root,
                            started["current"]["stageStateRevisionId"],
                            detached["supportingHandoff"]["stageStateRevisionId"],
                        )
                        closed = client.post("/projects/close", json={"root": root})
                        self.assertEqual(200, closed.status_code, closed.text)
        finally:
            projects.shutdown()

        restarted_projects, restarted_intents, restarted_progress = self._stack()
        try:
            with TestClient(
                self._app(restarted_projects, restarted_intents, restarted_progress),
                base_url=f"http://{AUTHORITY}",
                headers=HEADERS,
                client=("127.0.0.1", 50000),
            ) as restarted_client:
                _catalog, profiles = self._catalog(restarted_client)
                for profile_id, (root, stage_revision_id, supporting_revision_id) in roots.items():
                    with self.subTest(restarted_profile=profile_id):
                        opened = restarted_client.post("/projects/open", json={"root": root})
                        self.assertEqual(200, opened.status_code, opened.text)
                        resumed = restarted_client.post("/projects/workflow-progress", json={"root": root})
                        self.assertEqual(200, resumed.status_code, resumed.text)
                        projection = resumed.json()
                        self.assertEqual(profile_id, projection["profileId"])
                        self.assertEqual(
                            profiles[profile_id]["stages"][0]["stageKey"],
                            projection["current"]["stageKey"],
                        )
                        self.assertEqual(stage_revision_id, projection["current"]["stageStateRevisionId"])
                        self.assertEqual(
                            supporting_revision_id,
                            projection["supportingHandoff"]["stageStateRevisionId"],
                        )
                        restarted_client.post("/projects/close", json={"root": root})
        finally:
            restarted_projects.shutdown()

    def test_exact_cycle_policy_preserves_prior_passes_and_denies_systematic_revisit(self) -> None:
        projects, intents, progress = self._stack()
        try:
            with TestClient(
                self._app(projects, intents, progress),
                base_url=f"http://{AUTHORITY}",
                headers=HEADERS,
                client=("127.0.0.1", 50000),
            ) as client:
                catalog, profiles = self._catalog(client)
                actual_cycles = {
                    profile_id for profile_id, profile in profiles.items() if profile["processForm"] == "revisitable"
                }
                self.assertEqual(CYCLICAL_PROFILES, actual_cycles)
                self.assertEqual("audit-lineage.html", profiles["systematic-review"]["stages"][-1]["pageContractId"])
                for index, profile_id in enumerate(profiles, start=301):
                    with self.subTest(profile=profile_id):
                        created = client.post(
                            "/projects",
                            json={
                                "parentDirectory": self.temporary.name,
                                "directoryName": f"cycle-{profile_id}",
                                "displayName": f"Cycle {profile_id}",
                                "primaryUseCase": profile_id,
                                "researchObjective": f"Exercise {profile_id} cycle authority.",
                            },
                        )
                        self.assertEqual(200, created.status_code, created.text)
                        root = created.json()["root"]
                        project_id = created.json()["projectId"]
                        client.post("/projects/open", json={"root": root})
                        before = client.post("/projects/workflow-progress", json={"root": root}).json()
                        started = client.post(
                            "/projects/workflow-progress/commands",
                            json=self._command(root, before, "start"),
                            headers={"Idempotency-Key": f"{index:032x}"},
                        ).json()
                        evidence_id = self._append_evidence(root, project_id, index + 20)
                        completed_response = client.post(
                            "/projects/workflow-progress/commands",
                            json=self._command(
                                root,
                                started,
                                "complete",
                                stageKey=started["current"]["stageKey"],
                                completionEvidenceRevisionIds=[evidence_id],
                            ),
                            headers={"Idempotency-Key": f"{index + 1:032x}"},
                        )
                        self.assertEqual(200, completed_response.status_code, completed_response.text)
                        advanced = completed_response.json()
                        source = next(
                            item
                            for item in advanced["history"]
                            if item["stageKey"] == started["current"]["stageKey"] and item["status"] == "completed"
                        )
                        revisit_command = self._command(
                            root,
                            advanced,
                            "revisit",
                            stageKey=source["stageKey"],
                            revisitSourceStageStateRevisionId=source["stageStateRevisionId"],
                            revisitSourceStageStateRevisionContentHash=source["revisionContentHash"],
                        )
                        revisited = client.post(
                            "/projects/workflow-progress/commands",
                            json=revisit_command,
                            headers={"Idempotency-Key": f"{index + 2:032x}"},
                        )
                        if profile_id in CYCLICAL_PROFILES:
                            self.assertEqual(200, revisited.status_code, revisited.text)
                            result = revisited.json()
                            self.assertEqual(source["stageKey"], result["current"]["stageKey"])
                            self.assertEqual(2, result["current"]["passNumber"])
                            self.assertTrue(
                                any(
                                    item["stageStateRevisionId"] == source["stageStateRevisionId"]
                                    and item["status"] == "completed"
                                    and item["passNumber"] == 1
                                    for item in result["history"]
                                )
                            )
                        else:
                            self.assertEqual(409, revisited.status_code, revisited.text)
                            self.assertEqual("RO-CORE-WORKFLOW-PROGRESS-CYCLE-DENIED", revisited.json()["code"])
                            unchanged = client.post("/projects/workflow-progress", json={"root": root})
                            self.assertEqual(advanced, unchanged.json())
                        client.post("/projects/close", json={"root": root})

                self.assertEqual(REFERENCE_ID, catalog["referenceId"])
                self.assertEqual(REFERENCE_VERSION, catalog["referenceVersion"])
                self.assertEqual(PROFILE_CATALOG_VERSION, catalog["profileCatalogVersion"])
                self.assertEqual(PROFILE_CATALOG_HASH, catalog["profileCatalogHash"])
        finally:
            projects.shutdown()


if __name__ == "__main__":
    unittest.main()
