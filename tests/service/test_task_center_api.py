from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.models import WorkflowTaskCenterPage, WorkflowTaskCenterRun  # noqa: E402
from research_observatory_core.projects import ProjectLifecycleService  # noqa: E402
from research_observatory_core.repositories import sqlite_workflow_queue_repository  # noqa: E402
from research_observatory_core.storage import development_plaintext_database_fixture  # noqa: E402
from research_observatory_core.task_center import TaskCenterService  # noqa: E402
from research_observatory_core.workflow_contracts import canonical_workflow_json  # noqa: E402
from research_observatory_core.workflow_executor import prepare_workflow_job  # noqa: E402

from tests.workflows.test_local_workflow_executor import SYSTEM, WORKER_A, runnable_contracts  # noqa: E402
from tests.workflows.test_task_center import RESEARCHER, waiting_human_authority  # noqa: E402

TOKEN = "0123456789abcdef" * 4
AUTHORITY = "127.0.0.1:49152"
RUN_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d005"
TASK_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d030"


def workflow_etag(
    run: dict[str, Any],
    *,
    revision_delta: int = 0,
    snapshot_revision_delta: int = 0,
) -> str:
    return (
        f'"workflow-{run["workflowRunId"]}-{run["revision"] + revision_delta}'
        f'-{run["snapshotRevision"] + snapshot_revision_delta}"'
    )


def waiting_run() -> WorkflowTaskCenterRun:
    return WorkflowTaskCenterRun.model_validate(
        {
            "workflowRunId": RUN_ID,
            "workflowKey": "source-review",
            "definitionRevisionId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d002",
            "definitionVersion": "1.0.0",
            "snapshotId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d004",
            "snapshotRevision": 1,
            "continuationFromWorkflowRunId": None,
            "continuationFromJobId": None,
            "state": "waiting-human",
            "activeCompute": False,
            "progress": {"kind": "quantified", "unit": "steps", "completedUnits": 1, "totalUnits": 2},
            "revision": 28,
            "interruptionKind": None,
            "updatedAt": "2026-08-30T12:01:28.000Z",
            "steps": [],
            "jobs": [],
            "humanTasks": [
                {
                    "humanTaskId": TASK_ID,
                    "stepRunId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d011",
                    "state": "claimed",
                    "requiredRole": "researcher",
                    "assignedActorId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d041",
                    "requestedAt": "2026-08-30T12:01:25.000Z",
                    "evidenceArtifactIds": [],
                    "allowedDispositions": ["approved", "rejected"],
                    "consequencesByDisposition": {
                        "approved": "resume-workflow",
                        "rejected": "end-workflow",
                    },
                    "decisionId": None,
                    "disposition": None,
                    "decidedAt": None,
                }
            ],
            "retainedArtifacts": [],
            "events": [],
        }
    )


class FakeTaskCenter:
    def __init__(self) -> None:
        self.run = waiting_run()
        self.decisions: list[dict[str, object]] = []

    def list(self, *, root: str, limit: int) -> WorkflowTaskCenterPage:
        self.last_list = (root, limit)
        return WorkflowTaskCenterPage(items=(self.run,))

    def decide(self, **values: object) -> WorkflowTaskCenterRun:
        self.decisions.append(values)
        return self.run


class TaskCenterApiTests(unittest.TestCase):
    def test_projection_and_decision_use_exact_precondition_without_client_consequence(self) -> None:
        service = FakeTaskCenter()
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(TOKEN),
            expected_authority=AUTHORITY,
            task_center=service,  # type: ignore[arg-type]
        )
        headers = {"Authorization": f"Bearer {TOKEN}"}
        with TestClient(
            app,
            base_url=f"http://{AUTHORITY}",
            headers=headers,
            client=("127.0.0.1", 50000),
        ) as client:
            page = client.get("/projects/workflows/task-center", params={"root": "C:/Research/study-one", "limit": 20})
            self.assertEqual(200, page.status_code)
            self.assertEqual("waiting-human", page.json()["items"][0]["state"])
            self.assertEqual(("C:/Research/study-one", 20), service.last_list)

            missing = client.post(
                f"/projects/workflows/human-tasks/{TASK_ID}/decide",
                json={"root": "C:/Research/study-one", "disposition": "approved"},
                headers={"Idempotency-Key": "a" * 32},
            )
            self.assertEqual(428, missing.status_code)

            injected = client.post(
                f"/projects/workflows/human-tasks/{TASK_ID}/decide",
                json={
                    "root": "C:/Research/study-one",
                    "disposition": "approved",
                    "consequenceCode": "end-workflow",
                },
                headers={
                    "If-Match": f'"workflow-{RUN_ID}-28-1"',
                    "Idempotency-Key": "a" * 32,
                },
            )
            self.assertEqual(422, injected.status_code)

            accepted = client.post(
                f"/projects/workflows/human-tasks/{TASK_ID}/decide",
                json={"root": "C:/Research/study-one", "disposition": "approved"},
                headers={
                    "If-Match": f'"workflow-{RUN_ID}-28-1"',
                    "Idempotency-Key": "a" * 32,
                },
            )
            self.assertEqual(200, accepted.status_code)
            self.assertEqual(f'"workflow-{RUN_ID}-28-1"', accepted.headers["etag"])
            self.assertEqual(
                {
                    "root": "C:/Research/study-one",
                    "human_task_id": TASK_ID,
                    "expected_run_id": RUN_ID,
                    "expected_snapshot_revision": 1,
                    "expected_history_sequence": 28,
                    "disposition": "approved",
                    "idempotency_key": "a" * 32,
                },
                service.decisions[0],
            )

    def test_real_project_api_persists_exact_human_decision_across_core_restart(self) -> None:
        with (
            development_plaintext_database_fixture(),
            tempfile.TemporaryDirectory(prefix="ro-task-center-api-") as temporary,
        ):
            projects = ProjectLifecycleService()
            created = projects.create(
                parent_directory=temporary,
                directory_name="study-one",
                display_name="Study One",
                template_id="theory-synthesis",
                trace_id="b" * 32,
            )
            opened = projects.open(root=created.root, trace_id="b" * 32)
            definition, snapshot, human_task_id = waiting_human_authority()
            snapshot["projectId"] = opened.project_id
            repository = sqlite_workflow_queue_repository(Path(opened.root), opened.project_id)
            repository.register_authority(
                definition_json=canonical_workflow_json(definition),
                snapshot_json=canonical_workflow_json(snapshot),
                actor=RESEARCHER,
            )
            task_center = TaskCenterService(projects, sqlite_workflow_queue_repository, RESEARCHER.actor_id)
            app = create_app(
                settings=CoreSettings(),
                capability_digest=capability_token_digest(TOKEN),
                expected_authority=AUTHORITY,
                projects=projects,
                task_center=task_center,
            )
            headers = {"Authorization": f"Bearer {TOKEN}"}
            with TestClient(
                app,
                base_url=f"http://{AUTHORITY}",
                headers=headers,
                client=("127.0.0.1", 50000),
            ) as client:
                page = client.get("/projects/workflows/task-center", params={"root": opened.root, "limit": 20})
                self.assertEqual(200, page.status_code, page.text)
                waiting = page.json()["items"][0]
                decision = client.post(
                    f"/projects/workflows/human-tasks/{human_task_id}/decide",
                    json={"root": opened.root, "disposition": "approved"},
                    headers={
                        "If-Match": (
                            f'"workflow-{waiting["workflowRunId"]}-{waiting["revision"]}-{waiting["snapshotRevision"]}"'
                        ),
                        "Idempotency-Key": "c" * 32,
                    },
                )
                self.assertEqual(200, decision.status_code, decision.text)
                self.assertEqual("succeeded", decision.json()["state"])
                self.assertEqual(2, decision.json()["snapshotRevision"])

            restarted_projects = ProjectLifecycleService()
            restarted = restarted_projects.open(root=opened.root, trace_id="d" * 32)
            restarted_app = create_app(
                settings=CoreSettings(),
                capability_digest=capability_token_digest(TOKEN),
                expected_authority=AUTHORITY,
                projects=restarted_projects,
                task_center=TaskCenterService(
                    restarted_projects,
                    sqlite_workflow_queue_repository,
                    RESEARCHER.actor_id,
                ),
            )
            with TestClient(
                restarted_app,
                base_url=f"http://{AUTHORITY}",
                headers=headers,
                client=("127.0.0.1", 50000),
            ) as client:
                restored = client.get(
                    "/projects/workflows/task-center",
                    params={"root": restarted.root, "limit": 20},
                )
                self.assertEqual(200, restored.status_code, restored.text)
                persisted = restored.json()["items"][0]
                self.assertEqual("succeeded", persisted["state"])
                self.assertEqual(2, persisted["snapshotRevision"])
                definition_reference = cast(dict[str, object], snapshot["definition"])
                self.assertEqual(definition_reference["definitionRevisionId"], persisted["definitionRevisionId"])

    def test_real_api_cancel_and_retry_require_the_exact_snapshot_and_history_pair(self) -> None:
        with (
            development_plaintext_database_fixture(),
            tempfile.TemporaryDirectory(prefix="ro-task-center-api-preconditions-") as temporary,
        ):
            projects = ProjectLifecycleService()
            created = projects.create(
                parent_directory=temporary,
                directory_name="study-one",
                display_name="Study One",
                template_id="theory-synthesis",
                trace_id="e" * 32,
            )
            opened = projects.open(root=created.root, trace_id="e" * 32)
            repository = sqlite_workflow_queue_repository(Path(opened.root), opened.project_id)

            definition, snapshot, job_id = runnable_contracts()
            snapshot["projectId"] = opened.project_id
            running_submission = prepare_workflow_job(
                definition,
                snapshot,
                job_id=job_id,
                concurrency_class="document",
                priority=4,
                available_at="2026-08-30T12:02:00.000Z",
            )
            repository.enqueue(running_submission, actor=SYSTEM)
            running_claim = repository.claim_next(
                worker_id=WORKER_A,
                concurrency_classes=("document",),
                now="2026-08-30T12:02:00.000Z",
                lease_duration_ms=30_000,
            )
            assert running_claim is not None
            repository.start(running_claim, now="2026-08-30T12:02:00.100Z")

            task_center = TaskCenterService(projects, sqlite_workflow_queue_repository, RESEARCHER.actor_id)
            app = create_app(
                settings=CoreSettings(),
                capability_digest=capability_token_digest(TOKEN),
                expected_authority=AUTHORITY,
                projects=projects,
                task_center=task_center,
            )
            headers = {"Authorization": f"Bearer {TOKEN}"}
            with TestClient(
                app,
                base_url=f"http://{AUTHORITY}",
                headers=headers,
                client=("127.0.0.1", 50000),
            ) as client:
                page = client.get("/projects/workflows/task-center", params={"root": opened.root, "limit": 20})
                self.assertEqual(200, page.status_code, page.text)
                running = next(
                    item for item in page.json()["items"] if item["workflowRunId"] == running_claim.workflow_run_id
                )
                cancel_url = f"/projects/workflows/jobs/{job_id}/cancel"
                cancel_body = {"root": opened.root, "reasonCode": "user-requested"}
                substituted = client.post(
                    cancel_url,
                    json=cancel_body,
                    headers={"If-Match": workflow_etag(running, snapshot_revision_delta=1)},
                )
                self.assertEqual(412, substituted.status_code, substituted.text)
                stale = client.post(
                    cancel_url,
                    json=cancel_body,
                    headers={"If-Match": workflow_etag(running, revision_delta=-1)},
                )
                self.assertEqual(412, stale.status_code, stale.text)
                cancelled = client.post(
                    cancel_url,
                    json=cancel_body,
                    headers={"If-Match": workflow_etag(running)},
                )
                self.assertEqual(200, cancelled.status_code, cancelled.text)
                self.assertEqual("cancelling", cancelled.json()["state"])

                repository.cancel(
                    running_claim,
                    now="2026-08-30T12:02:00.400Z",
                    reason_code="user-requested",
                )
                retry_definition, retry_snapshot, retry_job_id = runnable_contracts(identity_variant=True)
                retry_snapshot["projectId"] = opened.project_id
                retry_submission = prepare_workflow_job(
                    retry_definition,
                    retry_snapshot,
                    job_id=retry_job_id,
                    concurrency_class="document",
                    priority=4,
                    available_at="2026-08-30T12:03:00.000Z",
                )
                repository.enqueue(retry_submission, actor=SYSTEM)
                retry_claim = repository.claim_next(
                    worker_id=WORKER_A,
                    concurrency_classes=("document",),
                    now="2026-08-30T12:03:00.000Z",
                    lease_duration_ms=30_000,
                )
                assert retry_claim is not None
                repository.start(retry_claim, now="2026-08-30T12:03:00.100Z")
                repository.fail(retry_claim, now="2026-08-30T12:03:00.200Z", error_code="invalid-input")
                page = client.get("/projects/workflows/task-center", params={"root": opened.root, "limit": 20})
                failed = next(
                    item for item in page.json()["items"] if item["workflowRunId"] == retry_claim.workflow_run_id
                )
                retry_url = f"/projects/workflows/jobs/{retry_job_id}/retry"
                retry_headers = {"Idempotency-Key": "f" * 32}
                substituted = client.post(
                    retry_url,
                    json={"root": opened.root},
                    headers={
                        **retry_headers,
                        "If-Match": workflow_etag(failed, snapshot_revision_delta=1),
                    },
                )
                self.assertEqual(412, substituted.status_code, substituted.text)
                stale = client.post(
                    retry_url,
                    json={"root": opened.root},
                    headers={
                        **retry_headers,
                        "If-Match": workflow_etag(failed, revision_delta=-1),
                    },
                )
                self.assertEqual(412, stale.status_code, stale.text)
                continued = client.post(
                    retry_url,
                    json={"root": opened.root},
                    headers={
                        **retry_headers,
                        "If-Match": workflow_etag(failed),
                    },
                )
                self.assertEqual(200, continued.status_code, continued.text)
                self.assertEqual(failed["workflowRunId"], continued.json()["continuationFromWorkflowRunId"])
                self.assertEqual(retry_job_id, continued.json()["continuationFromJobId"])


if __name__ == "__main__":
    unittest.main()
