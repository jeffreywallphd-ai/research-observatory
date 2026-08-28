from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.models import IntentDraftRequest  # noqa: E402
from research_observatory_core.ports.repositories import RepositoryIdempotencyConflict  # noqa: E402
from research_observatory_core.projects import ProjectLifecycleService  # noqa: E402
from research_observatory_core.repositories import sqlite_intent_revision_repository  # noqa: E402
from research_observatory_core.research_intents import IntentProblem, ResearchIntentService  # noqa: E402
from research_observatory_core.storage import development_plaintext_database_fixture  # noqa: E402

TOKEN = "0123456789abcdef" * 4
AUTHORITY = "127.0.0.1:49152"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
TRACE = "a" * 32
ACTOR_ID = "018f0000-0000-7000-8000-000000000001"
OTHER_ACTOR_ID = "018f0000-0000-7000-8000-000000000002"
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
            local_actor_id=ACTOR_ID,
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
        saved = self.service.save_draft(command, trace_id=TRACE, idempotency_key="1" * 32)

        self.assertEqual(saved.revision, 1)
        self.assertEqual(saved.status, "draft")
        self.assertFalse(saved.decision_complete)
        self.assertFalse(saved.launch_ready)
        self.assertIn("research-question", saved.unresolved_decisions)
        self.assertIn("source-scope", saved.unresolved_decisions)

        restarted = ResearchIntentService(
            self.projects,
            repository_factory=sqlite_intent_revision_repository,
            local_actor_id=ACTOR_ID,
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
                "SELECT event_type, actor_type, actor_id FROM provenance_events WHERE event_type='intent.draft.saved'"
            ).fetchall()
            outbox = connection.execute(
                "SELECT event_type, state FROM outbox_events WHERE event_type='intent.draft.saved'"
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual([row[0] for row in settings], [1])
        stored_revision = json.loads(settings[0][1])
        self.assertEqual(stored_revision["status"], "draft")
        self.assertEqual(stored_revision["createdBy"], {"actorType": "human", "actorId": ACTOR_ID})
        self.assertEqual(provenance, [("intent.draft.saved", "human", ACTOR_ID)])
        self.assertEqual(outbox, [("intent.draft.saved", "pending")])

    def test_scope_change_requires_bound_preview_and_preserves_prior_revision(self) -> None:
        first = self.service.save_draft(draft_request(self.root), trace_id=TRACE, idempotency_key="2" * 32)
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
            self.service.save_draft(changed, trace_id=TRACE, idempotency_key="3" * 32)
        self.assertEqual(denied.exception.code, "RO-CORE-INTENT-IMPACT-ACK-REQUIRED")
        self.assertEqual(self.service.workspace(self.root).current, first)

        saved = self.service.save_draft(
            changed.model_copy(update={"impact_acknowledgement": preview.acknowledgement_token}),
            trace_id=TRACE,
            idempotency_key="4" * 32,
        )
        self.assertEqual(saved.revision, 2)
        workspace = self.service.workspace(self.root)
        self.assertEqual([item.revision for item in workspace.history], [2, 1])
        self.assertIsNotNone(workspace.current)
        assert workspace.current is not None
        self.assertEqual(workspace.current.primary_use_case, "systematic-review")
        database = Path(self.root) / "state" / "project.sqlite3"
        connection = sqlite3.connect(database)
        try:
            revision_actors = tuple(
                json.loads(row[0])["createdBy"]["actorId"]
                for row in connection.execute(
                    "SELECT text_value FROM settings WHERE setting_key='research-intent.revision' ORDER BY revision"
                )
            )
            audit_actors = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT actor_id FROM provenance_events WHERE event_type='intent.draft.saved' ORDER BY occurred_at"
                )
            )
        finally:
            connection.close()
        self.assertEqual((ACTOR_ID, ACTOR_ID), revision_actors)
        self.assertEqual((ACTOR_ID, ACTOR_ID), audit_actors)

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
            missing_key = client.post(
                "/projects/intent/drafts", json=draft_request(self.root).model_dump(by_alias=True)
            )
            spoofed_actor = client.post(
                "/projects/intent/drafts",
                json=draft_request(self.root).model_dump(by_alias=True),
                headers={"Idempotency-Key": "5" * 32, "X-Actor-Id": OTHER_ACTOR_ID},
            )
            saved = client.post(
                "/projects/intent/drafts",
                json=draft_request(self.root).model_dump(by_alias=True),
                headers={"Idempotency-Key": "5" * 32},
            )
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
        self.assertEqual(missing_key.status_code, 422)
        self.assertEqual(spoofed_actor.status_code, 403)
        self.assertEqual(spoofed_actor.json()["code"], "RO-CORE-ACTOR-SPOOF-DENIED")
        self.assertEqual(saved.status_code, 200)
        self.assertFalse(saved.json()["launchReady"])
        self.assertEqual(after.json()["current"]["revision"], 1)
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["acknowledgementRequired"])

    def test_idempotent_replay_survives_restart_and_rejects_changed_command_or_actor(self) -> None:
        command = draft_request(self.root)
        key = "6" * 32
        first = self.service.save_draft(command, trace_id=TRACE, idempotency_key=key)
        restarted = ResearchIntentService(
            self.projects,
            repository_factory=sqlite_intent_revision_repository,
            local_actor_id=ACTOR_ID,
        )

        self.assertEqual(first, restarted.save_draft(command, trace_id="b" * 32, idempotency_key=key))
        with self.assertRaises(IntentProblem) as changed:
            restarted.save_draft(
                command.model_copy(update={"revision_rationale": "A different command."}),
                trace_id=TRACE,
                idempotency_key=key,
            )
        self.assertEqual(changed.exception.code, "RO-CORE-INTENT-IDEMPOTENCY-CONFLICT")

        other_actor = ResearchIntentService(
            self.projects,
            repository_factory=sqlite_intent_revision_repository,
            local_actor_id=OTHER_ACTOR_ID,
        )
        with self.assertRaises(IntentProblem) as substituted:
            other_actor.save_draft(command, trace_id=TRACE, idempotency_key=key)
        self.assertEqual(substituted.exception.code, "RO-CORE-INTENT-IDEMPOTENCY-CONFLICT")

        with self.assertRaises(IntentProblem) as stale:
            restarted.save_draft(command, trace_id=TRACE, idempotency_key="7" * 32)
        self.assertEqual(stale.exception.code, "RO-CORE-INTENT-REVISION-CONFLICT")

        database = Path(self.root) / "state" / "project.sqlite3"
        connection = sqlite3.connect(database)
        try:
            binding = json.loads(
                connection.execute(
                    "SELECT text_value FROM settings WHERE setting_key='research-intent.idempotency'"
                ).fetchone()[0]
            )
            counts = {
                "revision": connection.execute(
                    "SELECT COUNT(*) FROM settings WHERE setting_key='research-intent.revision'"
                ).fetchone()[0],
                "idempotency": connection.execute(
                    "SELECT COUNT(*) FROM settings WHERE setting_key='research-intent.idempotency'"
                ).fetchone()[0],
                "provenance": connection.execute(
                    "SELECT COUNT(*) FROM provenance_events WHERE event_type='intent.draft.saved'"
                ).fetchone()[0],
                "outbox": connection.execute(
                    "SELECT COUNT(*) FROM outbox_events WHERE event_type='intent.draft.saved'"
                ).fetchone()[0],
            }
            outbox_binding = connection.execute(
                "SELECT idempotency_key, record_sha256 FROM outbox_events WHERE event_type='intent.draft.saved'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(counts, {"revision": 1, "idempotency": 1, "provenance": 1, "outbox": 1})
        self.assertEqual((key, binding["commandSha256"]), outbox_binding)

        repository = sqlite_intent_revision_repository(Path(self.root), self.project.project_id)
        with self.assertRaises(RepositoryIdempotencyConflict):
            repository.replay(
                manifest_project_id="different-project",
                actor_id=ACTOR_ID,
                idempotency_key=key,
                command_sha256=binding["commandSha256"],
            )

    def test_competing_identical_writers_converge_on_one_committed_revision(self) -> None:
        command = draft_request(self.root)
        key = "a" * 32
        barrier = threading.Barrier(2)

        def save(trace_id: str):
            barrier.wait(timeout=5)
            return self.service.save_draft(command, trace_id=trace_id, idempotency_key=key)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(save, ("b" * 32, "c" * 32)))
        self.assertEqual(results[0], results[1])

        connection = sqlite3.connect(Path(self.root) / "state" / "project.sqlite3")
        try:
            self.assertEqual(
                (1, 1, 1, 1),
                (
                    connection.execute(
                        "SELECT COUNT(*) FROM settings WHERE setting_key='research-intent.revision'"
                    ).fetchone()[0],
                    connection.execute(
                        "SELECT COUNT(*) FROM settings WHERE setting_key='research-intent.idempotency'"
                    ).fetchone()[0],
                    connection.execute(
                        "SELECT COUNT(*) FROM provenance_events WHERE event_type='intent.draft.saved'"
                    ).fetchone()[0],
                    connection.execute(
                        "SELECT COUNT(*) FROM outbox_events WHERE event_type='intent.draft.saved'"
                    ).fetchone()[0],
                ),
            )
        finally:
            connection.close()

    def test_actor_unavailability_and_outbox_failure_roll_back_before_audit_authority(self) -> None:
        unavailable = ResearchIntentService(
            self.projects,
            repository_factory=sqlite_intent_revision_repository,
            local_actor_id=None,
        )
        with self.assertRaises(IntentProblem) as missing:
            unavailable.save_draft(draft_request(self.root), trace_id=TRACE, idempotency_key="8" * 32)
        self.assertEqual(missing.exception.code, "RO-CORE-INTENT-ACTOR-UNAVAILABLE")

        database = Path(self.root) / "state" / "project.sqlite3"
        with self.assertRaises(IntentProblem) as failed:
            self.service.save_draft(draft_request(self.root), trace_id="z" * 32, idempotency_key="9" * 32)
        self.assertEqual(failed.exception.code, "RO-CORE-INTENT-WRITE-FAILED")

        connection = sqlite3.connect(database)
        try:
            for table, predicate in (
                ("settings", "setting_key LIKE 'research-intent.%'"),
                ("provenance_events", "event_type='intent.draft.saved'"),
                ("outbox_events", "event_type='intent.draft.saved'"),
            ):
                with self.subTest(table=table):
                    self.assertEqual(
                        0,
                        connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {predicate}").fetchone()[0],
                    )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
