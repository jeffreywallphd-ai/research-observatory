from __future__ import annotations

import json
import sqlite3
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
from research_observatory_core.models import IntentDraftRequest  # noqa: E402
from research_observatory_core.projects import ProjectLifecycleService  # noqa: E402
from research_observatory_core.repositories import sqlite_intent_revision_repository  # noqa: E402
from research_observatory_core.research_intents import IntentProblem, ResearchIntentService  # noqa: E402
from research_observatory_core.storage import development_plaintext_database_fixture  # noqa: E402

TOKEN = "0123456789abcdef" * 4
AUTHORITY = "127.0.0.1:49152"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
TRACE = "a" * 32
INTENT_REQUEST_FIXTURE = REPO / "tests" / "service" / "fixtures" / "valid-intent-draft-request.json"


def draft_request(root: str, *, expected_revision: int = 0, **changes: object) -> IntentDraftRequest:
    payload: dict[str, object] = json.loads(INTENT_REQUEST_FIXTURE.read_text(encoding="utf-8"))
    payload.update({"root": root, "expectedRevision": expected_revision})
    payload.update(changes)
    return IntentDraftRequest.model_validate(payload)


class ResearchIntentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_profile = development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.temp = tempfile.TemporaryDirectory(prefix="ro-intent-")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.database_profile.__exit__, None, None, None)
        self.projects = ProjectLifecycleService()
        created = self.projects.create(
            parent_directory=self.temp.name,
            directory_name="intent-study",
            display_name="Intent Study",
            template_id="theory-synthesis",
            trace_id=TRACE,
        )
        self.root = created.root
        self.project = self.projects.open(root=self.root, trace_id=TRACE)
        self.service = ResearchIntentService(
            self.projects,
            repository_factory=sqlite_intent_revision_repository,
        )

    def tearDown(self) -> None:
        self.projects.shutdown()

    def test_incomplete_draft_is_durable_but_cannot_launch(self) -> None:
        command = draft_request(
            self.root,
            researchObjective="",
            phenomenon="",
            sourceKinds=[],
            languageCodes=[],
            startYear=None,
            endYear=None,
            evidenceTypes=[],
            noveltyStandard=None,
            noveltyRationale="",
        )
        saved = self.service.save_draft(command, trace_id=TRACE)

        self.assertEqual(saved.revision, 1)
        self.assertEqual(saved.status, "draft")
        self.assertFalse(saved.decision_complete)
        self.assertFalse(saved.launch_ready)
        self.assertIn("research-question", saved.unresolved_decisions)
        self.assertIn("source-scope", saved.unresolved_decisions)

        restarted = ResearchIntentService(
            self.projects,
            repository_factory=sqlite_intent_revision_repository,
        ).workspace(self.root)
        self.assertEqual(restarted.current, saved)
        self.assertEqual([item.revision for item in restarted.history], [1])

        database = Path(self.root) / "state" / "project.sqlite3"
        connection = sqlite3.connect(database)
        try:
            settings = connection.execute(
                "SELECT revision, text_value FROM settings WHERE setting_key='research-intent.revision'"
            ).fetchall()
            provenance = connection.execute(
                "SELECT event_type, actor_type FROM provenance_events WHERE event_type='intent.draft.saved'"
            ).fetchall()
            outbox = connection.execute(
                "SELECT event_type, state FROM outbox_events WHERE event_type='intent.draft.saved'"
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual([row[0] for row in settings], [1])
        self.assertEqual(json.loads(settings[0][1])["status"], "draft")
        self.assertEqual(provenance, [("intent.draft.saved", "human")])
        self.assertEqual(outbox, [("intent.draft.saved", "pending")])

    def test_scope_change_requires_bound_preview_and_preserves_prior_revision(self) -> None:
        first = self.service.save_draft(draft_request(self.root), trace_id=TRACE)
        changed = draft_request(
            self.root,
            expected_revision=1,
            primaryUseCase="systematic-review",
            sourceKinds=["peer-reviewed-article"],
            noveltyStandard="bounded-comparative",
            stoppingConditions=["coverage-threshold"],
        )
        preview = self.service.preview(changed.to_impact_request())
        self.assertTrue(preview.acknowledgement_required)
        self.assertEqual(
            set(preview.change_categories),
            {"primary-use-case", "corpus-scope", "novelty-scope"},
        )
        self.assertIn("Screening protocol", preview.affected_outputs)
        self.assertIn("Theory Map", preview.affected_workflows)

        with self.assertRaises(IntentProblem) as denied:
            self.service.save_draft(changed, trace_id=TRACE)
        self.assertEqual(denied.exception.code, "RO-CORE-INTENT-IMPACT-ACK-REQUIRED")
        self.assertEqual(self.service.workspace(self.root).current, first)

        saved = self.service.save_draft(
            changed.model_copy(update={"impact_acknowledgement": preview.acknowledgement_token}),
            trace_id=TRACE,
        )
        self.assertEqual(saved.revision, 2)
        workspace = self.service.workspace(self.root)
        self.assertEqual([item.revision for item in workspace.history], [2, 1])
        self.assertIsNotNone(workspace.current)
        assert workspace.current is not None
        self.assertEqual(workspace.current.primary_use_case, "systematic-review")

    def test_api_requires_preview_acknowledgement_and_never_marks_draft_launch_ready(self) -> None:
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(TOKEN),
            expected_authority=AUTHORITY,
            projects=self.projects,
            intents=self.service,
        )
        with TestClient(
            app,
            base_url=f"http://{AUTHORITY}",
            headers=HEADERS,
            client=("127.0.0.1", 50000),
        ) as client:
            initial = client.post("/projects/intent", json={"root": self.root})
            saved = client.post("/projects/intent/drafts", json=draft_request(self.root).model_dump(by_alias=True))
            after = client.post("/projects/intent", json={"root": self.root})
            preview = client.post(
                "/projects/intent/preview",
                json=draft_request(self.root, expected_revision=1)
                .to_impact_request()
                .model_copy(update={"source_kinds": ("book",)})
                .model_dump(by_alias=True),
            )

        self.assertEqual(initial.status_code, 200)
        self.assertIsNone(initial.json()["current"])
        self.assertEqual(saved.status_code, 200)
        self.assertFalse(saved.json()["launchReady"])
        self.assertEqual(after.json()["current"]["revision"], 1)
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["acknowledgementRequired"])


if __name__ == "__main__":
    unittest.main()
