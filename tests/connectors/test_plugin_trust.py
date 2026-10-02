"""Windows local publisher trust and cross-project plugin grant authority."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from nacl.signing import SigningKey

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_grants import (  # noqa: E402
    PluginEnableConfirmation,
    PluginGrantActor,
    PluginGrantProblem,
)
from research_observatory_core.connectors.plugin_manifest import PluginInvocationRequest  # noqa: E402
from research_observatory_core.connectors.plugin_trust import (  # noqa: E402
    PluginGrantService,
    PluginPublisherTrustStore,
    PluginTrustDecision,
)
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.plugin_grant_repository import SqlitePluginGrantRepository  # noqa: E402
from research_observatory_core.ports.credential_store import SecretUnavailable  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    configure_protected_database_provider,
    initialize_database,
)
from research_observatory_core.windows_credentials import WindowsCredentialStore  # noqa: E402

from tests.connectors.test_plugin_manifest_contract import (  # noqa: E402
    DESTINATION,
    OTHER_PROJECT_ID,
    PACKAGE_FILE,
    PATH,
    PROJECT_ID,
    PUBLISHER_ID,
    SCIENTIFIC_DIGEST,
    _manifest_bytes,
    _manifest_document,
)
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402

NOW = "2026-10-01T12:00:00.000Z"
PROFILE_ID = "local-plugin-test"


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@unittest.skipUnless(os.name == "nt", "profile-local DPAPI publisher trust authority")
class PluginTrustTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-plugin-trust-")
        self.addCleanup(self._cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.credentials = WindowsCredentialStore(self.root / "profile-vault", audit_sink=lambda _event: None)
        self.trust = PluginPublisherTrustStore(self.credentials, PROFILE_ID)
        self.key = SigningKey(b"\x15" * 32)
        self.public_key = bytes(self.key.verify_key)
        self.raw = _manifest_bytes(_manifest_document())
        self.signature = self.key.sign(self.raw).signature
        self.files = {PATH: PACKAGE_FILE}
        self.actor = PluginGrantActor(new_uuid_v7(), "a" * 32, NOW)
        self.system = PluginGrantActor(new_uuid_v7(), "b" * 32, NOW, "system")
        configure_protected_database_provider(InMemoryDatabaseKeyProvider())
        self.repos = {}
        for project_id in (PROJECT_ID, OTHER_PROJECT_ID):
            state = self.root / project_id / "state"
            state.mkdir(parents=True)
            database = state / "project.sqlite3"
            result = initialize_database(database, project_id=project_id, project_created_at=NOW)
            self.assertTrue(result.ok, result.errors)
            self.repos[project_id] = SqlitePluginGrantRepository(database, project_id)

    def _cleanup(self) -> None:
        if os.name == "nt":
            subprocess.run(
                [
                    str(Path(os.environ["SYSTEMROOT"]) / "System32/icacls.exe"),
                    self.temporary.name,
                    "/reset",
                    "/t",
                    "/c",
                    "/q",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
        self.temporary.cleanup()

    def _decision(
        self,
        operation: str,
        key: bytes | None = None,
        *,
        expected_revision: int | None = None,
        previous_key_sha256: str | None = None,
        action_id: str | None = None,
    ) -> PluginTrustDecision:
        return PluginTrustDecision(
            action_id=action_id or new_uuid_v7(),
            publisher_key_id=PUBLISHER_ID,
            public_key_sha256=_sha(self.public_key if key is None else key),
            expected_revision=expected_revision,
            operation=operation,
            previous_key_sha256=previous_key_sha256,
        )

    def _trust(self) -> PluginTrustDecision:
        decision = self._decision("trust")
        state = self.trust.decide(self.public_key, decision, actor=self.actor)
        self.assertEqual((1, "active", _sha(self.public_key)), (state.revision, state.status, state.public_key_sha256))
        return decision

    def _confirmation(self, project_id: str, package) -> PluginEnableConfirmation:
        trust = self.trust.state(PUBLISHER_ID, audit_context=self.actor.trace_id)
        assert trust is not None
        return PluginEnableConfirmation(
            action_id=new_uuid_v7(),
            project_id=project_id,
            plugin_id=package.manifest.plugin_id,
            plugin_version=package.manifest.plugin_version,
            publisher_key_id=package.manifest.publisher_key_id,
            trusted_key_sha256=trust.public_key_sha256,
            trusted_key_revision=trust.revision,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            permissions=package.manifest.permissions,
            destinations=package.manifest.destinations,
            operations=package.manifest.operations,
            data_classes=package.manifest.data_classes,
            credential_scopes=package.manifest.credential_scopes,
            expected_revision=None,
        )

    def _request(self, project_id: str) -> PluginInvocationRequest:
        return PluginInvocationRequest.model_validate(
            {
                "projectId": project_id,
                "invocationId": new_uuid_v7(),
                "scientificRequestSha256": SCIENTIFIC_DIGEST,
                "operation": "lookup",
                "destination": DESTINATION,
            }
        )

    def test_package_cannot_self_trust_and_local_revoke_denies_both_projects(self) -> None:
        first_service = PluginGrantService(self.trust, self.repos[PROJECT_ID])
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-publisher-untrusted"):
            self.trust.verify_package(self.raw, self.signature, self.files, audit_context=self.actor.trace_id)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-publisher-untrusted"):
            first_service.enable(
                self.raw,
                self.signature,
                self.files,
                PluginEnableConfirmation(
                    action_id=new_uuid_v7(),
                    project_id=PROJECT_ID,
                    plugin_id="fixture.repository",
                    plugin_version="1.0.0",
                    publisher_key_id=PUBLISHER_ID,
                    trusted_key_sha256=_sha(self.public_key),
                    trusted_key_revision=1,
                    package_sha256=_sha(b"absent"),
                    manifest_sha256=_sha(self.raw),
                    permissions=(),
                    destinations=(),
                    operations=(),
                    data_classes=(),
                    credential_scopes=(),
                    expected_revision=None,
                ),
                actor=self.actor,
            )
        self.assertIsNone(self.repos[PROJECT_ID].current_grant("fixture.repository"))
        self._trust()
        restarted = PluginPublisherTrustStore(
            WindowsCredentialStore(self.root / "profile-vault", audit_sink=lambda _event: None), PROFILE_ID
        )
        package = restarted.verify_package(self.raw, self.signature, self.files, audit_context=self.actor.trace_id)
        self.assertEqual(self.public_key, restarted.active_key(PUBLISHER_ID, audit_context=self.actor.trace_id))
        services = {
            project_id: PluginGrantService(restarted, repository) for project_id, repository in self.repos.items()
        }
        requests = {}
        for project_id, service in services.items():
            service.enable(
                self.raw, self.signature, self.files, self._confirmation(project_id, package), actor=self.actor
            )
            request = self._request(project_id)
            requests[project_id] = request
            plan = service.current_authorization(
                self.raw,
                self.signature,
                self.files,
                request,
                expected_plugin_id="fixture.repository",
                actor=self.system,
            )
            self.assertEqual(project_id, plan.project_id)
        revoke = self._decision("revoke", expected_revision=1)
        self.assertEqual("revoked", restarted.decide(None, revoke, actor=self.actor).status)
        for project_id, service in services.items():
            with self.assertRaisesRegex(PluginGrantProblem, "plugin-publisher-revoked"):
                service.current_authorization(
                    self.raw,
                    self.signature,
                    self.files,
                    requests[project_id],
                    expected_plugin_id="fixture.repository",
                    actor=self.system,
                )
            self.assertIsNotNone(self.repos[project_id].current_grant("fixture.repository"))
            expected_events = ["denied", "enabled", "denied"] if project_id == PROJECT_ID else ["enabled", "denied"]
            self.assertEqual(
                expected_events,
                [event.event_kind for event in self.repos[project_id].audit_history("fixture.repository")],
            )
        self.assertEqual(
            ["trust", "revoke"],
            [event.operation for event in restarted.history(PUBLISHER_ID, audit_context=self.actor.trace_id)],
        )

    def test_collision_requires_revoke_and_explicit_key_rotation(self) -> None:
        first = self._trust()
        self.assertEqual(1, self.trust.decide(self.public_key, first, actor=self.actor).revision)
        second_key = bytes(SigningKey(b"\x16" * 32).verify_key)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-publisher-collision"):
            self.trust.decide(second_key, self._decision("trust", second_key, expected_revision=1), actor=self.actor)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-publisher-rotation-denied"):
            self.trust.decide(
                second_key,
                self._decision("rotate", second_key, expected_revision=1, previous_key_sha256=_sha(self.public_key)),
                actor=self.actor,
            )
        self.trust.decide(None, self._decision("revoke", expected_revision=1), actor=self.actor)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-publisher-rotation-required"):
            self.trust.decide(second_key, self._decision("trust", second_key, expected_revision=2), actor=self.actor)
        rotated = self.trust.decide(
            second_key,
            self._decision("rotate", second_key, expected_revision=2, previous_key_sha256=_sha(self.public_key)),
            actor=self.actor,
        )
        self.assertEqual((3, "active", _sha(second_key)), (rotated.revision, rotated.status, rotated.public_key_sha256))
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-package-invalid"):
            self.trust.verify_package(self.raw, self.signature, self.files, audit_context=self.actor.trace_id)
        self.assertEqual(
            ["trust", "revoke", "rotate"],
            [event.operation for event in self.trust.history(PUBLISHER_ID, audit_context=self.actor.trace_id)],
        )

    def test_dispatch_rechecks_exact_package_and_project_grant(self) -> None:
        self._trust()
        service = PluginGrantService(self.trust, self.repos[PROJECT_ID])
        package = self.trust.verify_package(self.raw, self.signature, self.files, audit_context=self.actor.trace_id)
        grant = service.enable(
            self.raw, self.signature, self.files, self._confirmation(PROJECT_ID, package), actor=self.actor
        )
        changed_file = b"# changed signed package\n"
        changed_raw = _manifest_bytes(_manifest_document(package_file=changed_file))
        request = self._request(PROJECT_ID)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-invocation-denied"):
            service.current_authorization(
                changed_raw,
                self.key.sign(changed_raw).signature,
                {PATH: changed_file},
                request,
                expected_plugin_id=grant.plugin_id,
                actor=self.system,
            )
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-invocation-denied"):
            service.current_authorization(
                self.raw,
                self.signature,
                self.files,
                self._request(OTHER_PROJECT_ID),
                expected_plugin_id=grant.plugin_id,
                actor=self.system,
            )
        self.assertEqual(grant, self.repos[PROJECT_ID].current_grant(grant.plugin_id))
        self.assertEqual(
            ["enabled", "denied", "denied"],
            [event.event_kind for event in self.repos[PROJECT_ID].audit_history(grant.plugin_id)],
        )

    def test_rotation_resigning_identical_package_needs_new_project_consent_after_restart(self) -> None:
        self._trust()
        service = PluginGrantService(self.trust, self.repos[PROJECT_ID])
        package = self.trust.verify_package(self.raw, self.signature, self.files, audit_context=self.actor.trace_id)
        original = service.enable(
            self.raw, self.signature, self.files, self._confirmation(PROJECT_ID, package), actor=self.actor
        )
        self.trust.decide(None, self._decision("revoke", expected_revision=1), actor=self.actor)
        new_key = SigningKey(b"\x17" * 32)
        new_public = bytes(new_key.verify_key)
        self.trust.decide(
            new_public,
            self._decision("rotate", new_public, expected_revision=2, previous_key_sha256=_sha(self.public_key)),
            actor=self.actor,
        )
        restarted = PluginPublisherTrustStore(
            WindowsCredentialStore(self.root / "profile-vault", audit_sink=lambda _event: None), PROFILE_ID
        )
        restarted_service = PluginGrantService(restarted, self.repos[PROJECT_ID])
        resigned = new_key.sign(self.raw).signature
        self.assertNotEqual(self.signature, resigned)
        request = self._request(PROJECT_ID)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-trust-changed"):
            restarted_service.current_authorization(
                self.raw,
                resigned,
                self.files,
                request,
                expected_plugin_id=original.plugin_id,
                actor=self.system,
            )
        authority = self.repos[PROJECT_ID].current_grant_authority(original.plugin_id)
        assert authority is not None
        self.assertEqual((1, _sha(self.public_key)), (authority.trusted_key_revision, authority.trusted_key_sha256))
        renewed = replace(
            self._confirmation(PROJECT_ID, package),
            action_id=new_uuid_v7(),
            expected_revision=1,
        )
        self.assertEqual(
            2, restarted_service.enable(self.raw, resigned, self.files, renewed, actor=self.actor).revision
        )
        plan = restarted_service.current_authorization(
            self.raw,
            resigned,
            self.files,
            request,
            expected_plugin_id=original.plugin_id,
            actor=self.system,
        )
        self.assertEqual(2, plan.grant_revision)

    def test_retrusting_same_key_does_not_revive_prior_project_permission(self) -> None:
        self._trust()
        service = PluginGrantService(self.trust, self.repos[PROJECT_ID])
        package = self.trust.verify_package(self.raw, self.signature, self.files, audit_context=self.actor.trace_id)
        service.enable(self.raw, self.signature, self.files, self._confirmation(PROJECT_ID, package), actor=self.actor)
        self.trust.decide(None, self._decision("revoke", expected_revision=1), actor=self.actor)
        self.trust.decide(self.public_key, self._decision("trust", expected_revision=2), actor=self.actor)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-trust-changed"):
            service.current_authorization(
                self.raw,
                self.signature,
                self.files,
                self._request(PROJECT_ID),
                expected_plugin_id="fixture.repository",
                actor=self.system,
            )

    def test_corrupt_unavailable_and_partial_trust_fail_closed_then_exact_retry_recovers(self) -> None:
        decision = self._decision("trust")
        original_put = self.credentials.put

        def interrupt_head(reference, material, context, *, expected_version=None):
            if reference.name == "head":
                raise SecretUnavailable("synthetic interruption")
            return original_put(reference, material, context, expected_version=expected_version)

        with (
            patch.object(self.credentials, "put", side_effect=interrupt_head),
            self.assertRaisesRegex(PluginGrantProblem, "plugin-publisher-unavailable"),
        ):
            self.trust.decide(self.public_key, decision, actor=self.actor)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-publisher-incomplete"):
            self.trust.active_key(PUBLISHER_ID, audit_context=self.actor.trace_id)
        self.assertEqual(1, self.trust.decide(self.public_key, decision, actor=self.actor).revision)
        with (
            patch.object(self.credentials, "lease_record", side_effect=SecretUnavailable("synthetic unavailable")),
            self.assertRaisesRegex(PluginGrantProblem, "plugin-publisher-unavailable"),
        ):
            self.trust.active_key(PUBLISHER_ID, audit_context=self.actor.trace_id)
        sealed = next((self.root / "profile-vault").rglob("*.sealed"))
        original = sealed.read_bytes()
        sealed.write_bytes(original[:-1] + bytes((original[-1] ^ 0x40,)))
        try:
            with self.assertRaisesRegex(PluginGrantProblem, "plugin-publisher-corrupt"):
                self.trust.active_key(PUBLISHER_ID, audit_context=self.actor.trace_id)
        finally:
            sealed.write_bytes(original)
        self.assertEqual(self.public_key, self.trust.active_key(PUBLISHER_ID, audit_context=self.actor.trace_id))

    def test_system_actor_cannot_create_local_trust_or_revoke(self) -> None:
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-actor-invalid"):
            self.trust.decide(self.public_key, self._decision("trust"), actor=self.system)
        self._trust()
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-actor-invalid"):
            self.trust.decide(None, self._decision("revoke", expected_revision=1), actor=self.system)
        state = self.trust.state(PUBLISHER_ID, audit_context=self.actor.trace_id)
        assert state is not None
        self.assertEqual("active", state.status)
