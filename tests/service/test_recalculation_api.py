from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.models import (  # noqa: E402
    RecalculationComparisonProjection,
    RecalculationPreview,
    RecalculationRestoredRevision,
    RecalculationRestoreReviewProjection,
    RecalculationScheduleProjection,
)

TOKEN = "0123456789abcdef" * 4
AUTHORITY = "127.0.0.1:49152"
ROOT = "C:/Research/study-one"
TARGET_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d101"
PRIOR_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d102"
CHANGE_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d103"
INTENT_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d104"
INTENT_REVISION_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d105"
RUN_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d106"
TASK_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d107"
DECISION_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d108"
SHA = "sha256:" + "a" * 64


class FakeRecalculationControl:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def preview(self, command: object) -> RecalculationPreview:
        self.calls.append(("preview", command))
        return RecalculationPreview(
            project_id="01890f6e-6a40-4cc5-98b7-123456789abc",
            target_revision_id=TARGET_ID,
            plan_sha256=SHA,
            policy_sha256=SHA,
            change_ids=(CHANGE_ID,),
            replacement_revision_ids=(),
            reusable_revision_ids=(),
            causes=(),
        )

    def schedule(self, command: object, *, idempotency_key: str) -> RecalculationScheduleProjection:
        self.calls.append(("schedule", (command, idempotency_key)))
        return RecalculationScheduleProjection(
            project_id="01890f6e-6a40-4cc5-98b7-123456789abc",
            target_revision_id=TARGET_ID,
            plan_sha256=SHA,
            workflow_run_id=RUN_ID,
            job_id=TASK_ID,
            state="runnable",
        )

    def compare(self, command: object) -> RecalculationComparisonProjection:
        self.calls.append(("compare", command))
        return RecalculationComparisonProjection(
            aggregate_id="018f47a2-4d6b-7f78-9f2e-7fb76c86d109",
            before_revision_id=PRIOR_ID,
            after_revision_id=TARGET_ID,
            before_revision=1,
            after_revision=2,
            changed_fields=("display-label-observed",),
        )

    def request_restore_review(
        self, command: object, *, idempotency_key: str
    ) -> RecalculationRestoreReviewProjection:
        self.calls.append(("restore-review", (command, idempotency_key)))
        return RecalculationRestoreReviewProjection(
            workflow_run_id=RUN_ID,
            human_task_id=TASK_ID,
            snapshot_revision=1,
            history_sequence=7,
            policy_sha256=SHA,
        )

    def restore(self, command: object, *, trace_id: str) -> RecalculationRestoredRevision:
        self.calls.append(("restore", (command, trace_id)))
        return RecalculationRestoredRevision(
            project_id="01890f6e-6a40-4cc5-98b7-123456789abc",
            aggregate_id="018f47a2-4d6b-7f78-9f2e-7fb76c86d109",
            revision_id="018f47a2-4d6b-7f78-9f2e-7fb76c86d110",
            revision=3,
            knowledge_status="adjudicated",
            rights_status="allowed",
        )


class RecalculationApiTests(unittest.TestCase):
    def test_routes_expose_complete_flow_without_accepting_actor_or_policy_authority(self) -> None:
        service = FakeRecalculationControl()
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(TOKEN),
            expected_authority=AUTHORITY,
            recalculation=service,  # type: ignore[arg-type]
        )
        headers = {"Authorization": f"Bearer {TOKEN}"}
        with TestClient(
            app,
            base_url=f"http://{AUTHORITY}",
            headers=headers,
            client=("127.0.0.1", 50000),
        ) as client:
            preview = client.post(
                "/projects/recalculation/preview",
                json={"root": ROOT, "targetRevisionId": TARGET_ID},
            )
            self.assertEqual(200, preview.status_code, preview.text)
            self.assertTrue(preview.json()["deferPreservesStaleVisibility"])

            schedule_body = {
                "root": ROOT,
                "targetRevisionId": TARGET_ID,
                "changeId": CHANGE_ID,
                "expectedPlanSha256": SHA,
                "intentId": INTENT_ID,
                "intentRevisionId": INTENT_REVISION_ID,
                "intentSha256": SHA,
                "requestedAt": "2026-09-02T18:30:00.000Z",
            }
            rejected = client.post(
                "/projects/recalculation/schedules",
                json={**schedule_body, "actorId": DECISION_ID, "policySha256": SHA},
                headers={"Idempotency-Key": "b" * 32},
            )
            self.assertEqual(422, rejected.status_code)
            scheduled = client.post(
                "/projects/recalculation/schedules",
                json=schedule_body,
                headers={"Idempotency-Key": "b" * 32},
            )
            self.assertEqual(200, scheduled.status_code, scheduled.text)

            comparison = client.post(
                "/projects/recalculation/comparisons",
                json={"root": ROOT, "beforeRevisionId": PRIOR_ID, "afterRevisionId": TARGET_ID},
            )
            self.assertEqual(200, comparison.status_code, comparison.text)

            review = client.post(
                "/projects/recalculation/restore-reviews",
                json={
                    "root": ROOT,
                    "beforeRevisionId": PRIOR_ID,
                    "afterRevisionId": TARGET_ID,
                    "intentId": INTENT_ID,
                    "intentRevisionId": INTENT_REVISION_ID,
                    "intentSha256": SHA,
                    "requestedAt": "2026-09-02T18:31:00.000Z",
                },
                headers={"Idempotency-Key": "c" * 32},
            )
            self.assertEqual(200, review.status_code, review.text)

            restored = client.post(
                "/projects/recalculation/restorations",
                json={
                    "root": ROOT,
                    "priorAdjudicatedRevisionId": PRIOR_ID,
                    "expectedCurrentRevisionId": TARGET_ID,
                    "workflowRunId": RUN_ID,
                    "humanTaskId": TASK_ID,
                    "decisionId": DECISION_ID,
                    "modifiedAt": "2026-09-02T18:32:00.000Z",
                },
            )
            self.assertEqual(200, restored.status_code, restored.text)

        self.assertEqual(
            ("preview", "schedule", "compare", "restore-review", "restore"),
            tuple(name for name, _ in service.calls),
        )


if __name__ == "__main__":
    unittest.main()
