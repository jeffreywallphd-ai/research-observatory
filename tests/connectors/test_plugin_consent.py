"""Plugin egress needs its own exact, current human research consent."""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_grants import PluginGrantActor  # noqa: E402
from research_observatory_core.connectors.plugin_manifest import (  # noqa: E402
    PluginInvocationPlan,
    PluginInvocationRequest,
    verify_plugin_package,
)
from research_observatory_core.connectors.plugin_package_intake import inspect_plugin_archive  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.plugin_admin_service import PluginAuthorizedDispatch  # noqa: E402
from research_observatory_core.plugin_consent import (  # noqa: E402
    PluginConsentProblem,
    PluginConsentService,
    intent_destination_id,
)
from research_observatory_core.repositories import sqlite_intent_revision_repository  # noqa: E402

from tests.connectors.test_connector_authority import ConnectorAuthorityFixture  # noqa: E402
from tests.connectors.test_plugin_package_intake import archive  # noqa: E402
from tests.service import test_research_intents as fixtures  # noqa: E402


class FakeCurrentPluginAdmin:
    def __init__(self, plan: PluginInvocationPlan, package) -> None:
        self.plan, self.package = plan, package
        self.active = True

    def prepare_persisted_invocation(self, _root, _project, package, manifest, signature, request, *, actor):
        if (
            not self.active
            or package != self.plan.package_sha256
            or manifest != self.plan.manifest_sha256
            or signature != self.plan.signature_sha256
            or request.invocation_id != self.plan.invocation_id
        ):
            raise ValueError("inactive")
        return PluginAuthorizedDispatch(self.package, self.plan, {})

    def recheck_admitted_invocation(self, _root, _project, admitted, request, *, actor):
        if not self.active or admitted.plan != self.plan or request.invocation_id != self.plan.invocation_id:
            raise ValueError("inactive")
        return self.plan


class PluginConsentTests(ConnectorAuthorityFixture):
    def setUp(self) -> None:
        super().setUp()
        raw, key = archive()
        inspected = inspect_plugin_archive(raw)
        manifest = inspected.manifest
        package = verify_plugin_package(
            inspected.manifest_bytes, inspected.signature, inspected.files, {manifest.publisher_key_id: key}
        )
        self.plugin_request = PluginInvocationRequest(
            project_id=self.project.project_id,
            invocation_id=new_uuid_v7(),
            scientific_request_sha256="sha256:" + "1" * 64,
            operation=manifest.operations[0],
            destination=manifest.destinations[0],
        )
        self.plan = PluginInvocationPlan(
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.plugin_version,
            sdk_version=manifest.sdk_version,
            required_features=manifest.required_features,
            source_id=manifest.source_identity.source_id,
            package_sha256=inspected.package_sha256,
            manifest_sha256=inspected.manifest_sha256,
            publisher_key_id=manifest.publisher_key_id,
            signature_sha256=inspected.signature_sha256,
            project_id=self.project.project_id,
            grant_revision=1,
            permissions=manifest.permissions,
            invocation_id=self.plugin_request.invocation_id,
            scientific_request_sha256=self.plugin_request.scientific_request_sha256,
            request_sha256="sha256:" + "2" * 64,
            operation=self.plugin_request.operation,
            destination=self.plugin_request.destination,
        )
        self.admin = FakeCurrentPluginAdmin(self.plan, package)
        self.actor = PluginGrantActor(fixtures.ACTOR_ID, fixtures.TRACE, self.clock.now())
        self.plugin_consent = self._service()

    def tearDown(self) -> None:
        self.plugin_consent.shutdown()
        super().tearDown()

    def _service(self) -> PluginConsentService:
        return PluginConsentService(
            self.projects,
            self.privacy,
            self.admin,  # type: ignore[arg-type]
            sqlite_intent_revision_repository,
            clock=self.clock.monotonic,
            now=lambda: datetime(2026, 10, 1, tzinfo=UTC),
        )

    def _preview(self):
        return self.plugin_consent.preview(
            self.root,
            self.project.project_id,
            self.plan.package_sha256,
            self.plan.manifest_sha256,
            self.plan.signature_sha256,
            self.plugin_request,
            self.rights,
            actor=self.actor,
        )

    def _confirmed(self):
        preview = self._preview()
        with self.assertRaises(PluginConsentProblem):
            self.plugin_consent.confirm(self.root, self.project.project_id, preview.preview_id, confirmation="yes")
        with self.assertRaises(PluginConsentProblem):
            self.plugin_consent.authority(self.root, preview.preview_id)
        with self.assertRaises(PluginConsentProblem):
            self.plugin_consent.confirm(self.root, new_uuid_v7(), preview.preview_id, confirmation=preview.confirmation)
        self.plugin_consent.confirm(
            self.root, self.project.project_id, preview.preview_id, confirmation=preview.confirmation
        )
        return preview, self.plugin_consent.authority(self.root, preview.preview_id)

    def test_accepted_plugin_destination_privacy_rights_and_confirmation_are_independent(self) -> None:
        with self.assertRaises(PluginConsentProblem):
            self._preview()
        self.intent(providers=(self.plan.source_id,))
        with self.assertRaises(PluginConsentProblem):
            self._preview()
        self.policy()
        from research_observatory_core.connector_service import ConnectorRetention

        with self.assertRaises(PluginConsentProblem):
            self.plugin_consent.preview(
                self.root,
                self.project.project_id,
                self.plan.package_sha256,
                self.plan.manifest_sha256,
                self.plan.signature_sha256,
                self.plugin_request,
                ConnectorRetention(),
                actor=self.actor,
            )
        preview, authority = self._confirmed()
        stamp = authority.guard(self.plugin_request, self.plan, "admission", lambda value: value)
        self.assertEqual(preview.preview_id, stamp.preview_id)
        self.assertEqual(preview.request_sha256, stamp.request_sha256)
        self.assertEqual(preview.policy_sha256, stamp.policy_sha256)
        self.assertEqual(preview.intent_revision_id, stamp.intent.revision_id)
        self.assertEqual(preview.destination, self.plan.destination)
        self.assertEqual(preview.signature_sha256, self.plan.signature_sha256)
        self.assertEqual(preview.permissions, self.plan.permissions)
        self.assertEqual(preview.data_classes, self.admin.package.manifest.data_classes)
        self.assertEqual(preview.declared_terms, self.admin.package.manifest.terms)
        self.assertEqual(preview.retention, self.rights)
        self.assertTrue(stamp.confirmation_sha256.startswith("sha256:"))

    def test_exact_plan_current_policy_grant_and_restart_fence(self) -> None:
        self.intent(providers=(self.plan.source_id,))
        self.policy()
        preview, authority = self._confirmed()
        changed = self.plan.model_copy(update={"request_sha256": "sha256:" + "3" * 64})
        with self.assertRaises(PluginConsentProblem):
            authority.guard(self.plugin_request, changed, "dispatch", lambda _: self.fail("must deny"))
        restarted = self._service()
        with self.assertRaises(PluginConsentProblem):
            restarted.authority(self.root, preview.preview_id)
        self.admin.active = False
        with self.assertRaises(PluginConsentProblem):
            authority.guard(self.plugin_request, self.plan, "broker", lambda _: self.fail("must deny"))
        self.admin.active = True
        self.policy(False)
        with self.assertRaises(PluginConsentProblem):
            authority.guard(self.plugin_request, self.plan, "publication", lambda _: self.fail("must deny"))
        restarted.shutdown()

    def test_expiry_revoke_and_changed_accepted_intent_fail_closed(self) -> None:
        self.intent(providers=(self.plan.source_id,))
        self.policy()
        preview, authority = self._confirmed()
        self.intent("local-only")
        with self.assertRaises(PluginConsentProblem):
            authority.guard(self.plugin_request, self.plan, "dispatch", lambda _: self.fail("must deny"))
        self.intent(providers=(self.plan.source_id,))
        preview, authority = self._confirmed()
        self.plugin_consent.revoke(self.root, preview.preview_id)
        with self.assertRaises(PluginConsentProblem):
            authority.guard(self.plugin_request, self.plan, "publication", lambda _: self.fail("must deny"))
        _, authority = self._confirmed()
        self.clock.seconds += 601
        with self.assertRaises(PluginConsentProblem):
            authority.guard(self.plugin_request, self.plan, "broker", lambda _: self.fail("must deny"))

    def test_long_plugin_source_has_stable_bounded_intent_destination_id(self) -> None:
        long_plan = self.plan.model_copy(update={"source_id": "plugin." + "a" * 121})
        alias = intent_destination_id(long_plan)
        self.assertTrue(alias.startswith("plugin.sha256."))
        self.assertLessEqual(len(alias), 100)
        self.assertEqual(alias, intent_destination_id(long_plan))
        self.assertNotEqual(
            alias, intent_destination_id(long_plan.model_copy(update={"source_id": "plugin." + "b" * 121}))
        )


if __name__ == "__main__":
    unittest.main()
