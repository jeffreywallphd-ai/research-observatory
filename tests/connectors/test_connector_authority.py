"""Actual local lifecycle/Intent/privacy authority; no external requests or secrets."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

# ruff: noqa: E402

from research_observatory_core.connector_service import (
    ConnectorConsentService,
    ConnectorProjectAdapters,
    ConnectorRetention,
)
from research_observatory_core.connectors.providers import ProviderProblem
from research_observatory_core.models import PrivacyPolicyUpdateRequest
from research_observatory_core.ports.connector_runtime import ConnectorPageRepository
from research_observatory_core.privacy import ProjectPrivacyService
from research_observatory_core.repositories import sqlite_intent_revision_repository, sqlite_privacy_policy_repository

from tests.connectors import test_connector_intent as intent_fixtures
from tests.connectors.test_connector_broker import Clock, Repository
from tests.connectors.test_scholarly_mapping import request
from tests.service import test_research_intents as fixtures


class ConnectorAuthorityFixture(intent_fixtures.ConnectorIntentFixture):
    repository: ConnectorPageRepository

    def setUp(self):
        super().setUp()
        self.clock = Clock()
        self.repository = Repository()
        self.privacy = ProjectPrivacyService(self.projects, sqlite_privacy_policy_repository)
        self.connectors = self.consent_service()
        self.request = request("openalex", projectId=self.project.project_id)
        self.rights = ConnectorRetention.model_validate(
            {
                "rights": {
                    name: {"value": "permitted", "basis": "researcher-confirmed"} for name in ("store", "inspect")
                },
                "retainBody": True,
            }
        )

    def tearDown(self):
        self.connectors.detach(self.root)
        super().tearDown()

    def consent_service(self):
        return ConnectorConsentService(
            self.projects,
            self.privacy,
            lambda path, project: ConnectorProjectAdapters(
                sqlite_intent_revision_repository(path, project), self.repository
            ),
            local_actor_id=fixtures.ACTOR_ID,
            now=self.clock.now,
            clock=self.clock.monotonic,
        )

    def policy(self, enabled=True):
        current = self.privacy.get(self.root)
        values = current.model_dump(mode="json", by_alias=True)
        command = {
            key: values[key]
            for key in (
                "remoteModelApproval",
                "telemetryMode",
                "logRetentionDays",
                "documentRetention",
                "cacheRetentionDays",
            )
        }
        return self.privacy.update(
            PrivacyPolicyUpdateRequest.model_validate(
                command
                | {
                    "root": self.root,
                    "expectedRevision": current.revision,
                    "networkPolicy": "approved-providers" if enabled else "offline",
                    "egressConsentToken": "acknowledge-egress-preview-v1" if enabled else None,
                }
            ),
            trace_id=fixtures.TRACE,
        )

    def intent(self, mode="approved-content", providers=("openalex",)):
        current = self.service.workspace(self.root).current
        command = fixtures.draft_request(
            self.root,
            expected_revision=current.revision if current else 0,
            egressPolicy={"mode": mode, "approvedDestinationIds": [] if mode == "local-only" else list(providers)},
        )
        impact = self.service.preview(command.to_impact_request())
        command = command.model_copy(update={"impact_acknowledgement": impact.acknowledgement_token})
        draft = self.service.save_draft(
            command, trace_id=fixtures.TRACE, idempotency_key=str(command.expected_revision + 1) * 32
        )
        return self.accept(draft)

    def preview(self):
        return self.connectors.preview(self.root, self.request, self.rights)


class ConnectorAuthorityTests(ConnectorAuthorityFixture):
    def test_local_default_and_accepted_intent_are_independent_denial_gates(self):
        with self.assertRaises(ProviderProblem):
            self.preview()
        self.intent()
        with self.assertRaises(ProviderProblem):
            self.preview()
        self.policy()
        preview = self.preview()
        with self.assertRaises(ProviderProblem):
            self.connectors.authority(self.root, preview.preview_id)
        with self.assertRaises(ProviderProblem):
            self.connectors.confirm(self.root, preview.preview_id, confirmation="yes")
        self.connectors.confirm(self.root, preview.preview_id, confirmation=preview.confirmation)
        authority = self.connectors.authority(self.root, preview.preview_id)
        stamp = authority.guard(self.request, "admission", lambda value: value)
        self.assertEqual(fixtures.ACTOR_ID, stamp.actor_id)
        self.assertEqual(self.project.project_id, stamp.project_id)
        self.assertEqual(self.request, preview.request)

    def confirmed(self):
        self.intent()
        self.policy()
        preview = self.preview()
        self.connectors.confirm(self.root, preview.preview_id, confirmation=preview.confirmation)
        return preview, self.connectors.authority(self.root, preview.preview_id)

    def test_exact_payload_current_policy_and_rights_revocation(self):
        preview, authority = self.confirmed()
        changed = type(self.request).model_validate(self.request.model_dump() | {"page_size": 2})
        with self.assertRaises(ProviderProblem):
            authority.guard(changed, "dispatch", lambda _: self.fail("must not dispatch"))
        self.connectors.revoke(self.root, preview.preview_id)
        with self.assertRaises(ProviderProblem):
            authority.guard(self.request, "publication", lambda _: self.fail("must not publish"))
        preview = self.preview()
        self.connectors.confirm(self.root, preview.preview_id, confirmation=preview.confirmation)
        authority = self.connectors.authority(self.root, preview.preview_id)
        self.policy(False)
        with self.assertRaises(ProviderProblem):
            authority.guard(self.request, "cache", lambda _: self.fail("must not expose cache"))

    def test_new_accepted_intent_fences_prior_confirmation(self):
        _, authority = self.confirmed()
        self.intent("local-only")
        with self.assertRaises(ProviderProblem):
            authority.guard(self.request, "dispatch", lambda _: self.fail("stale intent"))

    def test_restart_close_and_expiry_do_not_restore_confirmation(self):
        preview, authority = self.confirmed()
        restarted = self.consent_service()
        with self.assertRaises(ProviderProblem):
            restarted.authority(self.root, preview.preview_id)
        self.clock.seconds += 601
        with self.assertRaises(ProviderProblem):
            authority.guard(self.request, "dispatch", lambda _: self.fail("expired consent"))
        fresh = self.preview()
        self.connectors.confirm(self.root, fresh.preview_id, confirmation=fresh.confirmation)
        authority = self.connectors.authority(self.root, fresh.preview_id)
        self.connectors.detach(self.root)
        self.projects.close(root=self.root, trace_id=fixtures.TRACE)
        self.projects.open(root=self.root, trace_id=fixtures.TRACE)
        with self.assertRaises(ProviderProblem):
            authority.guard(self.request, "publication", lambda _: self.fail("old session"))

    def test_unknown_rights_and_unimplemented_redaction_are_not_grants(self):
        self.intent()
        self.policy()
        with self.assertRaises(ProviderProblem):
            self.connectors.preview(self.root, self.request, ConnectorRetention())
        self.intent("approved-redacted")
        with self.assertRaises(ProviderProblem):
            self.preview()


if __name__ == "__main__":
    unittest.main()
