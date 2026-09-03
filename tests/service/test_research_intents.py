from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.models import (  # noqa: E402
    IntentAcceptRequest,
    IntentDraftRequest,
    IntentPolicyRequest,
)
from research_observatory_core.ports.repositories import RepositoryIdempotencyConflict  # noqa: E402
from research_observatory_core.projects import ProjectLifecycleService  # noqa: E402
from research_observatory_core.repositories import sqlite_intent_revision_repository  # noqa: E402
from research_observatory_core.research_intents import IntentProblem, ResearchIntentService  # noqa: E402
from research_observatory_core.storage import development_plaintext_database_fixture  # noqa: E402
from research_observatory_core.workflow_profile_contracts import (  # noqa: E402
    approved_workflow_profile_catalog,
    decode_project_workflow_selection,
    decode_workflow_profile_migration,
)

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


def accept_request(revision, *, confirmed: bool = True) -> IntentAcceptRequest:
    return IntentAcceptRequest(
        root=revision.root if hasattr(revision, "root") else "unused",
        expected_revision=revision.revision,
        expected_revision_content_hash=revision.revision_content_hash,
        confirmed=confirmed,
        decision_rationale="I reviewed this exact decision-complete revision and accept it as governing.",
    )


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
            legacy_bridges = connection.execute(
                """
                SELECT event_type, bridge_state
                  FROM provenance_legacy_bridges
                 WHERE event_type='intent.draft.saved'
                """
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual([row[0] for row in settings], [1])
        stored_revision = json.loads(settings[0][1])
        self.assertEqual(stored_revision["status"], "draft")
        self.assertEqual(stored_revision["createdBy"], {"actorType": "human", "actorId": ACTOR_ID})
        self.assertEqual(provenance, [("intent.draft.saved", "human", ACTOR_ID)])
        self.assertEqual(outbox, [("intent.draft.saved", "pending")])
        self.assertEqual(legacy_bridges, [("intent.draft.saved", "legacy-narrow")])

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
        self.assertIn("Protocol, corpus, evidence table, cited synthesis, and audit bundle", preview.affected_outputs)
        self.assertIn("Theory Map", preview.affected_workflows)
        self.assertIn("research-intent-revision", preview.affected_schemas)
        self.assertTrue(preview.affected_checkpoints)
        self.assertEqual(preview.autonomy_default_effects, ("researcher-selected-autonomy-remains",))
        self.assertEqual(preview.stopping_logic_effects, ("researcher-selected-stopping-remains",))
        self.assertEqual(preview.stale_artifact_ids, ())
        self.assertTrue(preview.all_tools_accessible)
        self.assertTrue(preview.evidence_requirements_unchanged)
        self.assertTrue(preview.provenance_requirements_unchanged)

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
            selections = tuple(
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT text_value FROM settings WHERE setting_key='workflow-profile.selection' ORDER BY revision"
                )
            )
            migrations = tuple(
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT text_value FROM settings WHERE setting_key='workflow-profile.migration' ORDER BY revision"
                )
            )
        finally:
            connection.close()
        self.assertEqual((ACTOR_ID, ACTOR_ID), revision_actors)
        self.assertEqual((ACTOR_ID, ACTOR_ID), audit_actors)
        catalog = approved_workflow_profile_catalog()
        self.assertEqual([1, 2], [selection["revision"] for selection in selections])
        self.assertTrue(all(decode_project_workflow_selection(catalog, selection) for selection in selections))
        self.assertEqual(1, len(migrations))
        self.assertIsNotNone(decode_workflow_profile_migration(catalog, migrations[0]))
        self.assertEqual(selections[1]["acceptedMigration"]["migrationId"], migrations[0]["migrationId"])
        self.assertEqual(
            selections[1]["acceptedMigration"]["migrationContentHash"],
            migrations[0]["migrationContentHash"],
        )

    def test_catalog_projection_exposes_all_governed_profiles_without_restricting_tools(self) -> None:
        projection = self.service.workflow_profile_catalog()

        self.assertEqual("RO-UI-ACADEMIC-MINIMAL-1.5", projection.reference_id)
        self.assertEqual(14, len(projection.profiles))
        systematic = next(profile for profile in projection.profiles if profile.profile_id == "systematic-review")
        self.assertTrue(systematic.purpose)
        self.assertTrue(systematic.expected_outputs)
        self.assertEqual("linear", systematic.process_form)
        self.assertEqual(list(range(1, len(systematic.stages) + 1)), [stage.order for stage in systematic.stages])
        self.assertTrue(projection.all_tools_accessible)
        self.assertTrue(projection.evidence_requirements_unchanged)
        self.assertTrue(projection.provenance_requirements_unchanged)

    def test_profile_change_after_same_profile_intent_revision_binds_the_immediate_intent_predecessor(self) -> None:
        first = self.service.save_draft(draft_request(self.root), trace_id=TRACE, idempotency_key="a" * 32)
        second_command = draft_request(
            self.root,
            expected_revision=first.revision,
            revisionRationale="Clarify the same-profile intent without changing workflow authority.",
        )
        second = self.service.save_draft(second_command, trace_id=TRACE, idempotency_key="b" * 32)
        change = draft_request(
            self.root,
            expected_revision=second.revision,
            primaryUseCase="living-review",
            noveltyStandard="incremental",
            stoppingConditions=["coverage-threshold"],
            revisionRationale="Adopt the living-review workflow after impact review.",
        )
        preview = self.service.preview(change.to_impact_request())
        third = self.service.save_draft(
            change.model_copy(update={"impact_acknowledgement": preview.acknowledgement_token}),
            trace_id=TRACE,
            idempotency_key="c" * 32,
        )

        self.assertEqual(3, third.revision)
        database = Path(self.root) / "state" / "project.sqlite3"
        connection = sqlite3.connect(database)
        try:
            selections = [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT text_value FROM settings WHERE setting_key='workflow-profile.selection' ORDER BY revision"
                )
            ]
            migration = json.loads(
                connection.execute(
                    "SELECT text_value FROM settings WHERE setting_key='workflow-profile.migration' AND revision=2"
                ).fetchone()[0]
            )
        finally:
            connection.close()
        self.assertEqual([1, 2], [selection["revision"] for selection in selections])
        self.assertEqual(1, selections[1]["parentSelection"]["researchIntent"]["revision"])
        self.assertEqual(2, migration["priorResearchIntent"]["revision"])
        self.assertEqual(3, migration["targetResearchIntent"]["revision"])
        self.assertEqual(migration["targetResearchIntent"], selections[1]["researchIntent"])
        restarted = ResearchIntentService(
            self.projects,
            repository_factory=sqlite_intent_revision_repository,
            local_actor_id=ACTOR_ID,
        )
        restarted_workspace = restarted.workspace(self.root)
        self.assertIsNotNone(restarted_workspace.current)
        assert restarted_workspace.current is not None
        self.assertEqual("living-review", restarted_workspace.current.primary_use_case)

    def test_restart_denies_tampered_workflow_acceptance_lookup(self) -> None:
        first = self.service.save_draft(draft_request(self.root), trace_id=TRACE, idempotency_key="d" * 32)
        change = draft_request(
            self.root,
            expected_revision=first.revision,
            primaryUseCase="systematic-review",
            noveltyStandard="bounded-comparative",
            stoppingConditions=["coverage-threshold"],
        )
        preview = self.service.preview(change.to_impact_request())
        changed = self.service.save_draft(
            change.model_copy(update={"impact_acknowledgement": preview.acknowledgement_token}),
            trace_id=TRACE,
            idempotency_key="e" * 32,
        )
        database = Path(self.root) / "state" / "project.sqlite3"
        connection = sqlite3.connect(database)
        try:
            decision = json.loads(
                connection.execute(
                    "SELECT text_value FROM settings WHERE setting_key='workflow-profile.acceptance' AND revision=2"
                ).fetchone()[0]
            )
            decision["decisionContentHash"] = "sha256:" + "f" * 64
            trigger_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='settings_no_update'"
            ).fetchone()[0]
            connection.execute("DROP TRIGGER settings_no_update")
            connection.execute(
                "UPDATE settings SET text_value=? WHERE setting_key='workflow-profile.acceptance' AND revision=2",
                (json.dumps(decision, sort_keys=True, separators=(",", ":")),),
            )
            connection.execute(trigger_sql)
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(IntentProblem) as acceptance_denied:
            self.service.accept(
                accept_request(changed).model_copy(update={"root": self.root}),
                trace_id=TRACE,
                idempotency_key="f" * 32,
            )
        self.assertEqual("RO-CORE-WORKFLOW-PROFILE-READ-FAILED", acceptance_denied.exception.code)
        with self.assertRaises(IntentProblem) as denied:
            self.service.workspace(self.root)
        self.assertEqual("RO-CORE-WORKFLOW-PROFILE-READ-FAILED", denied.exception.code)

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
            catalog = client.get("/workflow-profiles/catalog")
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
            accepted = client.post(
                "/projects/intent/acceptances",
                json={
                    "root": self.root,
                    "expectedRevision": saved.json()["revision"],
                    "expectedRevisionContentHash": saved.json()["revisionContentHash"],
                    "confirmed": True,
                    "decisionRationale": "I reviewed and accept this exact revision.",
                },
                headers={"Idempotency-Key": "6" * 32},
            )
            policy = client.post(
                "/projects/intent/policy/evaluations",
                json={
                    "root": self.root,
                    "action": "approve-claim",
                    "subjectType": "model",
                    "stoppingCondition": None,
                },
            )

        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(14, len(catalog.json()["profiles"]))
        self.assertTrue(catalog.json()["allToolsAccessible"])
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
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["status"], "accepted")
        self.assertTrue(accepted.json()["launchReady"])
        self.assertEqual(policy.status_code, 200)
        self.assertEqual(policy.json()["outcome"], "require-confirmation")
        self.assertEqual(policy.json()["requiredGates"], ["claim-approval"])

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

    def test_human_acceptance_creates_restart_safe_governing_revision(self) -> None:
        draft = self.service.save_draft(draft_request(self.root), trace_id=TRACE, idempotency_key="b" * 32)
        command = IntentAcceptRequest(
            root=self.root,
            expected_revision=draft.revision,
            expected_revision_content_hash=draft.revision_content_hash,
            confirmed=True,
            decision_rationale="I reviewed and accept this exact research intent.",
        )
        accepted = self.service.accept(command, trace_id=TRACE, idempotency_key="c" * 32)

        self.assertEqual(accepted.status, "accepted")
        self.assertEqual(accepted.revision, 2)
        self.assertTrue(accepted.launch_ready)
        self.assertFalse(accepted.can_request_acceptance)
        restarted = ResearchIntentService(
            self.projects,
            repository_factory=sqlite_intent_revision_repository,
            local_actor_id=ACTOR_ID,
        )
        self.assertEqual(accepted, restarted.accept(command, trace_id="d" * 32, idempotency_key="c" * 32))
        workspace = restarted.workspace(self.root)
        self.assertEqual(workspace.current, accepted)
        policy = restarted.evaluate_policy(
            IntentPolicyRequest(root=self.root, action="propose-query", subject_type="human"),
            trace_id=TRACE,
        )
        self.assertIsNotNone(policy.governing_intent)
        assert policy.governing_intent is not None
        self.assertEqual(policy.governing_intent.revision, accepted.revision)
        self.assertEqual(policy.governing_intent.revision_content_hash, accepted.revision_content_hash)

        connection = sqlite3.connect(Path(self.root) / "state" / "project.sqlite3")
        try:
            stored = json.loads(
                connection.execute(
                    "SELECT text_value FROM settings WHERE setting_key='research-intent.revision' AND revision=2"
                ).fetchone()[0]
            )
            events = connection.execute(
                "SELECT event_type, actor_type, actor_id FROM provenance_events WHERE event_type='intent.accepted'"
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(stored["decision"]["disposition"], "accepted")
        self.assertEqual(stored["decision"]["actorId"], ACTOR_ID)
        self.assertEqual(events, [("intent.accepted", "human", ACTOR_ID)])

    def test_policy_projection_cache_tracks_the_exact_accepted_revision(self) -> None:
        first_draft = self.service.save_draft(
            draft_request(self.root),
            trace_id=TRACE,
            idempotency_key="ca" * 16,
        )
        first_acceptance = IntentAcceptRequest(
            root=self.root,
            expected_revision=first_draft.revision,
            expected_revision_content_hash=first_draft.revision_content_hash,
            confirmed=True,
            decision_rationale="Accept the first exact governing revision.",
        )
        first_accepted = self.service.accept(
            first_acceptance,
            trace_id=TRACE,
            idempotency_key="cb" * 16,
        )

        with patch.object(self.service, "_read", wraps=self.service._read) as read_history:
            for suffix in ("1", "2"):
                decision = self.service.evaluate_policy(
                    IntentPolicyRequest(root=self.root, action="propose-query", subject_type="model"),
                    trace_id=suffix * 32,
                )
                assert decision.governing_intent is not None
                self.assertEqual(decision.governing_intent.revision, first_accepted.revision)
            self.assertEqual(read_history.call_count, 0)

            second_draft = self.service.save_draft(
                draft_request(
                    self.root,
                    expected_revision=first_accepted.revision,
                    contributionIntent="A revised contribution governed by a new accepted revision.",
                ),
                trace_id=TRACE,
                idempotency_key="cc" * 16,
            )
            second_accepted = self.service.accept(
                IntentAcceptRequest(
                    root=self.root,
                    expected_revision=second_draft.revision,
                    expected_revision_content_hash=second_draft.revision_content_hash,
                    confirmed=True,
                    decision_rationale="Replace the governing projection with this reviewed revision.",
                ),
                trace_id=TRACE,
                idempotency_key="cd" * 16,
            )
            replayed_first = self.service.accept(
                first_acceptance,
                trace_id="4" * 32,
                idempotency_key="cb" * 16,
            )
            self.assertEqual(replayed_first, first_accepted)
            read_history.reset_mock()
            updated = self.service.evaluate_policy(
                IntentPolicyRequest(root=self.root, action="propose-query", subject_type="model"),
                trace_id="3" * 32,
            )

        self.assertEqual(read_history.call_count, 0)
        assert updated.governing_intent is not None
        self.assertEqual(updated.governing_intent.revision, second_accepted.revision)
        self.assertEqual(
            updated.governing_intent.revision_content_hash,
            second_accepted.revision_content_hash,
        )

    def test_acceptance_gate_rejects_missing_confirmation_and_stale_revision(self) -> None:
        draft = self.service.save_draft(draft_request(self.root), trace_id=TRACE, idempotency_key="d" * 32)
        unconfirmed = IntentAcceptRequest(
            root=self.root,
            expected_revision=draft.revision,
            expected_revision_content_hash=draft.revision_content_hash,
            confirmed=False,
            decision_rationale="This request deliberately lacks confirmation.",
        )
        with self.assertRaises(IntentProblem) as denied:
            self.service.accept(unconfirmed, trace_id=TRACE, idempotency_key="e" * 32)
        self.assertEqual(denied.exception.code, "RO-CORE-INTENT-ACCEPTANCE-CONFIRMATION-REQUIRED")
        self.assertIn("cannot be bypassed", denied.exception.detail)
        self.assertEqual(self.service.workspace(self.root).current, draft)

        stale = unconfirmed.model_copy(
            update={"confirmed": True, "expected_revision_content_hash": "sha256:" + "0" * 64}
        )
        with self.assertRaises(IntentProblem) as conflict:
            self.service.accept(stale, trace_id=TRACE, idempotency_key="f" * 32)
        self.assertEqual(conflict.exception.code, "RO-CORE-INTENT-ACCEPTANCE-REVISION-CONFLICT")
        self.assertEqual(self.service.workspace(self.root).current, draft)

    def test_mode_policy_matrix_is_governing_reference_bound_and_labeled(self) -> None:
        modes = (
            ("systematic-review", "coverage-threshold", "systematic-working-output"),
            ("theory-synthesis", "interpretive-saturation", "theory-working-output"),
            ("technical-landscape", "benchmark-complete", "technical-working-output"),
            ("hermeneutic-inquiry", "interpretive-saturation", "hermeneutic-working-output"),
            ("critical-problematization", "interpretive-saturation", "critical-working-output"),
            ("novelty-audit", "nearest-prior-work-challenged", "novelty-working-output"),
        )
        revision = 0
        for index, (use_case, stopping, label) in enumerate(modes):
            command = draft_request(
                self.root,
                expected_revision=revision,
                primaryUseCase=use_case,
                autonomyLevel="execute-reversible",
                stoppingConditions=[stopping],
            )
            preview = self.service.preview(command.to_impact_request())
            if preview.acknowledgement_required:
                command = command.model_copy(update={"impact_acknowledgement": preview.acknowledgement_token})
            draft = self.service.save_draft(
                command,
                trace_id=TRACE,
                idempotency_key=f"{index + 1:032x}",
            )
            accepted = self.service.accept(
                IntentAcceptRequest(
                    root=self.root,
                    expected_revision=draft.revision,
                    expected_revision_content_hash=draft.revision_content_hash,
                    confirmed=True,
                    decision_rationale=f"Accept the reviewed {use_case} intent.",
                ),
                trace_id=TRACE,
                idempotency_key=f"{index + 101:032x}",
            )
            revision = accepted.revision
            decision = self.service.evaluate_policy(
                IntentPolicyRequest(
                    root=self.root,
                    action="prepare-draft-output",
                    subject_type="model",
                ),
                trace_id=TRACE,
            )
            with self.subTest(mode=use_case):
                self.assertEqual(decision.outcome, "allow")
                self.assertEqual(decision.output_label, label)
                self.assertEqual(decision.required_gates, ("claim-approval", "publication"))
                self.assertIsNotNone(decision.governing_intent)
                assert decision.governing_intent is not None
                self.assertEqual(decision.governing_intent.revision, accepted.revision)

    def test_policy_denies_gate_bypass_and_unauthorized_autonomy_with_durable_audit(self) -> None:
        draft = self.service.save_draft(
            draft_request(self.root, autonomyLevel="suggest"),
            trace_id=TRACE,
            idempotency_key="1a" * 16,
        )
        self.service.accept(
            IntentAcceptRequest(
                root=self.root,
                expected_revision=draft.revision,
                expected_revision_content_hash=draft.revision_content_hash,
                confirmed=True,
                decision_rationale="Accept the exact reviewed intent.",
            ),
            trace_id=TRACE,
            idempotency_key="1b" * 16,
        )
        claim = self.service.evaluate_policy(
            IntentPolicyRequest(root=self.root, action="approve-claim", subject_type="model"),
            trace_id=TRACE,
        )
        execute = self.service.evaluate_policy(
            IntentPolicyRequest(root=self.root, action="execute-approved-query", subject_type="model"),
            trace_id=TRACE,
        )
        egress = self.service.evaluate_policy(
            IntentPolicyRequest(root=self.root, action="external-egress", subject_type="system"),
            trace_id=TRACE,
        )
        stopping = self.service.evaluate_policy(
            IntentPolicyRequest(
                root=self.root,
                action="recommend-stopping",
                subject_type="model",
                stopping_condition="interpretive-saturation",
            ),
            trace_id=TRACE,
        )

        self.assertEqual(claim.outcome, "require-confirmation")
        self.assertEqual(claim.required_gates, ("claim-approval",))
        self.assertIn("cannot be satisfied by policy evaluation", claim.explanation)
        self.assertEqual(execute.outcome, "deny")
        self.assertEqual(execute.reason_code, "autonomy-level-prohibits-action")
        self.assertEqual(egress.outcome, "deny")
        self.assertEqual(egress.required_gates, ("external-egress",))
        self.assertEqual(stopping.outcome, "recommend-human")
        self.assertTrue(stopping.stopping_requires_human_confirmation)

        connection = sqlite3.connect(Path(self.root) / "state" / "project.sqlite3")
        try:
            decisions = connection.execute(
                "SELECT text_value FROM settings WHERE setting_key='research-intent.policy-decision' ORDER BY revision"
            ).fetchall()
            events = connection.execute(
                "SELECT event_type, actor_id FROM provenance_events WHERE event_type='intent.policy.evaluated'"
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(len(decisions), 4)
        self.assertEqual(len(events), 4)
        self.assertTrue(all(event == ("intent.policy.evaluated", ACTOR_ID) for event in events))
        audited = [json.loads(row[0])["decision"] for row in decisions]
        self.assertEqual(
            [item["reasonCode"] for item in audited],
            [
                "claim-approval-requires-human-confirmation",
                "autonomy-level-prohibits-action",
                "active-intent-prohibits-external-egress",
                "stopping-requires-human-confirmation",
            ],
        )

    def test_policy_fails_closed_without_accepted_intent_and_on_audit_failure(self) -> None:
        no_intent = self.service.evaluate_policy(
            IntentPolicyRequest(root=self.root, action="propose-query", subject_type="model"),
            trace_id=TRACE,
        )
        self.assertEqual(no_intent.outcome, "deny")
        self.assertEqual(no_intent.reason_code, "no-active-accepted-intent")
        self.assertIsNone(no_intent.governing_intent)

        draft = self.service.save_draft(draft_request(self.root), trace_id=TRACE, idempotency_key="2a" * 16)
        self.service.accept(
            IntentAcceptRequest(
                root=self.root,
                expected_revision=draft.revision,
                expected_revision_content_hash=draft.revision_content_hash,
                confirmed=True,
                decision_rationale="Accept this exact reviewed intent.",
            ),
            trace_id=TRACE,
            idempotency_key="2b" * 16,
        )
        with self.assertRaises(IntentProblem) as failed:
            self.service.evaluate_policy(
                IntentPolicyRequest(root=self.root, action="propose-query", subject_type="model"),
                trace_id="z" * 32,
            )
        self.assertEqual(failed.exception.code, "RO-CORE-INTENT-POLICY-AUDIT-FAILED")

        connection = sqlite3.connect(Path(self.root) / "state" / "project.sqlite3")
        try:
            decision_count = connection.execute(
                "SELECT COUNT(*) FROM settings WHERE setting_key='research-intent.policy-decision'"
            ).fetchone()[0]
            event_count = connection.execute(
                "SELECT COUNT(*) FROM provenance_events WHERE event_type='intent.policy.evaluated'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual((decision_count, event_count), (1, 1))


if __name__ == "__main__":
    unittest.main()
