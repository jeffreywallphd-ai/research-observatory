"""Core-owned transfer/session and exact signed-package admission checks."""

from __future__ import annotations

import base64
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from nacl.signing import SigningKey

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.authentication import (  # noqa: E402
    LocalAuthenticationMiddleware,
    capability_token_digest,
)
from research_observatory_core.connectors.plugin_grants import (  # noqa: E402
    PluginEnableConfirmation,
    PluginGrantActor,
    PluginGrantProblem,
)
from research_observatory_core.connectors.plugin_manifest import Operation, PluginInvocationRequest  # noqa: E402
from research_observatory_core.connectors.plugin_package_store import PluginPackageStore  # noqa: E402
from research_observatory_core.connectors.plugin_trust import (  # noqa: E402
    PluginPublisherTrustStore,
    PluginTrustDecision,
)
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.plugin_admin_service import PluginAdminService  # noqa: E402
from research_observatory_core.plugin_api import register_plugin_routes  # noqa: E402
from research_observatory_core.plugin_grant_repository import SqlitePluginGrantRepository  # noqa: E402
from research_observatory_core.plugin_package_repository import SqlitePluginPackageRepository  # noqa: E402
from research_observatory_core.projects import ProjectLifecycleProblem, ProjectLifecycleService  # noqa: E402
from research_observatory_core.storage import configure_protected_database_provider, initialize_database  # noqa: E402
from research_observatory_core.transport import CoreProblem, TraceCorrelationMiddleware, problem_detail  # noqa: E402
from research_observatory_core.windows_credentials import WindowsCredentialStore  # noqa: E402

from tests.connectors.test_plugin_package_intake import archive  # noqa: E402
from tests.connectors.test_plugin_package_store import MemoryKeyProvider  # noqa: E402
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402
from tests.service import test_core_api as api  # noqa: E402

PROJECT = "0190a000-0000-7000-8000-000000000040"
ACTOR = "0190a000-0000-7000-8000-000000000043"


class FakeProjects:
    def __init__(self, root: Path):
        self.root = root
        self.open = True

    def perform_open_project_action(self, *, root, require_write, action):
        if not self.open or not require_write or Path(root) != self.root:
            raise PluginGrantProblem("plugin-project-unavailable")
        return action(self.root, PROJECT)

    def shutdown(self):
        self.open = False


class FakeTrust:
    def state(self, *_args, **_kwargs):
        return None


class FakeGrants:
    calls = 0

    def current_grant_authority(self, *_args, **_kwargs):
        return None

    def record_denial(self, **_kwargs):
        self.calls += 1


def _project_error(_request: Request, _error: ProjectLifecycleProblem) -> CoreProblem:
    return CoreProblem(
        problem_detail(
            status=403,
            code="RO-CORE-PLUGIN-PROJECT-DENIED",
            title="Project unavailable",
            detail="The project is unavailable for this action.",
            trace_id="0" * 32,
            retryable=False,
            remediation="Open the project and retry.",
        )
    )


class PluginAdminSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-plugin-admin-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.projects = FakeProjects(self.root)
        self.service = PluginAdminService(
            cast(ProjectLifecycleService, self.projects),
            cast(PluginPublisherTrustStore, FakeTrust()),
            actor_id=ACTOR,
            grant_repository_factory=lambda *_: cast(SqlitePluginGrantRepository, FakeGrants()),
            package_repository_factory=lambda path, identity: SqlitePluginPackageRepository(
                path / "state/project.sqlite3", identity
            ),
        )
        self.session = self.service.context(str(self.root), PROJECT)

    def test_chunked_seal_binds_exact_digest_and_current_session_then_cancel_erases_token(self):
        raw, _ = archive()
        intake = self.service.create(str(self.root), PROJECT, self.session)
        self.assertEqual("receiving", intake.state)
        for ordinal, start in enumerate(range(0, len(raw), 128 * 1024), 1):
            self.service.chunk(
                str(self.root), PROJECT, self.session, intake.intake_id, ordinal, raw[start : start + 128 * 1024]
            )
        self.assertEqual(
            "receiving", self.service.status(str(self.root), PROJECT, self.session, intake.intake_id).state
        )
        sealed = self.service.seal(
            str(self.root),
            PROJECT,
            self.session,
            intake.intake_id,
            archive_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=ordinal,
            trace_id="a" * 32,
        )
        self.assertEqual("sealed", sealed.state)
        assert sealed.review is not None and sealed.package_token is not None
        self.assertEqual("untrusted", sealed.review.trust_status)
        self.assertEqual(
            sealed.package_token,
            self.service.review(
                str(self.root), PROJECT, self.session, sealed.package_token, trace_id="a" * 32
            ).package_token,
        )
        cancelled = self.service.cancel(str(self.root), PROJECT, self.session, intake.intake_id)
        self.assertEqual("cancelled", cancelled.state)
        with self.assertRaises(PluginGrantProblem):
            self.service.review(str(self.root), PROJECT, self.session, sealed.package_token, trace_id="a" * 32)

    def test_wrong_session_chunk_order_and_digest_never_seal_package(self):
        intake = self.service.create(str(self.root), PROJECT, self.session)
        with self.assertRaises(PluginGrantProblem):
            self.service.chunk(str(self.root), PROJECT, "0" * 32, intake.intake_id, 1, b"data")
        with self.assertRaises(PluginGrantProblem):
            self.service.chunk(str(self.root), PROJECT, self.session, intake.intake_id, 2, b"data")
        self.service.chunk(str(self.root), PROJECT, self.session, intake.intake_id, 1, b"data")
        with self.assertRaises(PluginGrantProblem):
            self.service.seal(
                str(self.root),
                PROJECT,
                self.session,
                intake.intake_id,
                archive_sha256="sha256:" + "0" * 64,
                byte_length=4,
                chunk_count=1,
                trace_id="a" * 32,
            )
        self.assertEqual(
            "receiving", self.service.status(str(self.root), PROJECT, self.session, intake.intake_id).state
        )
        self.assertIsNone(self.service.status(str(self.root), PROJECT, self.session, intake.intake_id).package_token)

    def test_repeated_context_preserves_review_then_project_close_erases_transfer(self):
        raw, _ = archive()
        intake = self.service.create(str(self.root), PROJECT, self.session)
        self.service.chunk(str(self.root), PROJECT, self.session, intake.intake_id, 1, raw)
        sealed = self.service.seal(
            str(self.root),
            PROJECT,
            self.session,
            intake.intake_id,
            archive_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            trace_id="a" * 32,
        )
        assert sealed.package_token is not None
        next_session = self.service.context(str(self.root), PROJECT)
        self.assertEqual(self.session, next_session)
        self.assertEqual(
            sealed.package_token,
            self.service.review(
                str(self.root), PROJECT, next_session, sealed.package_token, trace_id="a" * 32
            ).package_token,
        )
        self.projects.open = False
        self.service.clear(str(self.root))
        self.projects.open = True
        with self.assertRaises(PluginGrantProblem):
            self.service.status(str(self.root), PROJECT, next_session, intake.intake_id)

    def test_closed_session_cannot_commit_late_trust_or_grant_action(self):
        self.service.clear(str(self.root))
        actor = PluginGrantActor(ACTOR, "a" * 32, "2026-10-01T12:00:00.000Z")
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-session-stale"):
            self.service.trust_decide(
                str(self.root),
                PROJECT,
                self.session,
                PluginTrustDecision(new_uuid_v7(), "publisher", "sha256:" + "1" * 64, None, "trust"),
                b"1" * 32,
                actor=actor,
            )
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-session-stale"):
            self.service.revoke(
                str(self.root),
                PROJECT,
                self.session,
                "sample",
                1,
                new_uuid_v7(),
                actor=actor,
            )

    def test_default_product_runtime_gate_denies_enable_before_grant_write(self):
        raw, _ = archive()
        intake = self.service.create(str(self.root), PROJECT, self.session)
        self.service.chunk(str(self.root), PROJECT, self.session, intake.intake_id, 1, raw)
        sealed = self.service.seal(
            str(self.root),
            PROJECT,
            self.session,
            intake.intake_id,
            archive_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            trace_id="a" * 32,
        )
        assert sealed.package_token is not None
        review = sealed.review
        assert review is not None
        confirmation = PluginEnableConfirmation(
            action_id=new_uuid_v7(),
            project_id=PROJECT,
            plugin_id=review.plugin_id,
            plugin_version=review.plugin_version,
            publisher_key_id=review.publisher_key_id,
            trusted_key_sha256="sha256:" + "1" * 64,
            trusted_key_revision=1,
            package_sha256=review.package_sha256,
            manifest_sha256=review.manifest_sha256,
            permissions=review.permissions,
            destinations=review.destinations,
            operations=review.operations,
            data_classes=review.data_classes,
            credential_scopes=review.credential_scopes,
            expected_revision=None,
        )
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-runtime-unavailable"):
            self.service.enable(
                str(self.root),
                PROJECT,
                self.session,
                sealed.package_token,
                confirmation,
                actor=PluginGrantActor(ACTOR, "a" * 32, "2026-10-01T12:00:00.000Z"),
            )

    def test_sealed_discard_is_idempotent_and_cannot_erase_a_new_selection(self):
        raw, _ = archive()
        intake = self.service.create(str(self.root), PROJECT, self.session)
        self.service.chunk(str(self.root), PROJECT, self.session, intake.intake_id, 1, raw)
        sealed = self.service.seal(
            str(self.root),
            PROJECT,
            self.session,
            intake.intake_id,
            archive_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            trace_id="a" * 32,
        )
        assert sealed.package_token is not None
        first = self.service.discard(str(self.root), PROJECT, self.session, sealed.package_token)
        again = self.service.discard(str(self.root), PROJECT, self.session, sealed.package_token)
        self.assertEqual(("cancelled", None), (first.state, first.package_token))
        self.assertEqual(first, again)
        replacement = self.service.create(str(self.root), PROJECT, self.session)
        self.assertNotEqual(intake.intake_id, replacement.intake_id)
        with self.assertRaises(PluginGrantProblem):
            self.service.discard(str(self.root), PROJECT, self.session, sealed.package_token)
        self.assertEqual(
            "receiving", self.service.status(str(self.root), PROJECT, self.session, replacement.intake_id).state
        )

    def test_native_api_is_authenticated_bounded_hidden_and_project_fenced(self):
        app = FastAPI()
        app.add_middleware(
            LocalAuthenticationMiddleware, digest=capability_token_digest(api.TOKEN), authority=api.AUTHORITY
        )
        app.add_middleware(TraceCorrelationMiddleware)

        @app.exception_handler(CoreProblem)
        async def failed(_request: Request, error: CoreProblem):
            return JSONResponse(
                status_code=error.problem.status, content=error.problem.model_dump(mode="json", by_alias=True)
            )

        @app.exception_handler(RequestValidationError)
        async def invalid(_request: Request, _error: RequestValidationError):
            return JSONResponse(status_code=422, content={"code": "invalid"})

        register_plugin_routes(app, lambda _request: self.service, _project_error)
        base = "/native/connectors/plugins/packages/"
        address = {"root": str(self.root), "projectId": PROJECT, "sessionId": self.session}
        with api.authenticated_client(app) as client:
            self.assertNotIn(base + "context", app.openapi()["paths"])
            self.assertEqual(401, client.post(base + "create", json=address, headers={"Authorization": ""}).status_code)
            self.assertEqual(422, client.post(base + "create", json=address | {"path": "C:/private"}).status_code)
            wrong = client.post(base + "create", json=address | {"projectId": new_uuid_v7()})
            self.assertIn(wrong.status_code, {403, 409})
            created = client.post(base + "create", json=address)
            self.assertEqual(200, created.status_code, created.text)
            intake_id = created.json()["intakeId"]
            raw, _ = archive()
            chunk = client.post(
                base + "chunk",
                json=address
                | {
                    "intakeId": intake_id,
                    "ordinal": 1,
                    "data": base64.b64encode(raw).decode("ascii"),
                },
            )
            self.assertEqual(200, chunk.status_code, chunk.text)
            sealed = client.post(
                base + "seal",
                json=address
                | {
                    "intakeId": intake_id,
                    "archiveSha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                    "byteLength": len(raw),
                    "chunkCount": 1,
                },
            )
            self.assertEqual(200, sealed.status_code, sealed.text)
            body = sealed.json()
            self.assertEqual("unavailable", body["review"]["runtimeStatus"])
            self.assertEqual(len(raw), body["byteLength"])
            self.assertEqual("no-store", sealed.headers["cache-control"])
            cancelled = client.post(base + "cancel", json=address | {"intakeId": intake_id})
            self.assertEqual(200, cancelled.status_code, cancelled.text)
            self.assertIsNone(cancelled.json()["packageToken"])


@unittest.skipUnless(os.name == "nt", "Windows profile trust and protected database")
class PluginAdminRealAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-plugin-real-admin-")
        self.addCleanup(self._cleanup)
        self.root = Path(self.temporary.name).resolve()
        database = self.root / "state/project.sqlite3"
        database.parent.mkdir()
        (self.root / "objects").mkdir()
        (self.root / ".tmp").mkdir()
        configure_protected_database_provider(InMemoryDatabaseKeyProvider())
        assert initialize_database(database, project_id=PROJECT, project_created_at="2026-10-01T12:00:00.000Z").ok
        self.key = SigningKey(b"\x15" * 32)
        trust = PluginPublisherTrustStore(
            WindowsCredentialStore(self.root / "profile-vault", audit_sink=lambda _event: None), "local-plugin-test"
        )
        self.keys = MemoryKeyProvider()
        self.package_store_factory = lambda path, identity: PluginPackageStore(
            create_local_object_store(path, identity, key_provider=self.keys)
        )
        self.service = PluginAdminService(
            cast(ProjectLifecycleService, FakeProjects(self.root)),
            trust,
            actor_id=ACTOR,
            grant_repository_factory=lambda path, identity: SqlitePluginGrantRepository(
                path / "state/project.sqlite3", identity
            ),
            package_repository_factory=lambda path, identity: SqlitePluginPackageRepository(
                path / "state/project.sqlite3", identity
            ),
            runtime_available=lambda: True,
            package_store_factory=self.package_store_factory,
        )
        self.session = self.service.context(str(self.root), PROJECT)
        self.actor = PluginGrantActor(ACTOR, "a" * 32, "2026-10-01T12:00:00.000Z")

    def _cleanup(self):
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

    def test_native_session_trust_exact_consent_enable_revoke(self):
        raw, _ = archive()
        intake = self.service.create(str(self.root), PROJECT, self.session)
        self.service.chunk(str(self.root), PROJECT, self.session, intake.intake_id, 1, raw)
        sealed = self.service.seal(
            str(self.root),
            PROJECT,
            self.session,
            intake.intake_id,
            archive_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            trace_id=self.actor.trace_id,
        )
        assert sealed.review is not None and sealed.package_token is not None
        self.assertEqual("untrusted", sealed.review.trust_status)
        key = bytes(self.key.verify_key)
        state = self.service.trust_decide(
            str(self.root),
            PROJECT,
            self.session,
            PluginTrustDecision(
                new_uuid_v7(),
                sealed.review.publisher_key_id,
                "sha256:" + hashlib.sha256(key).hexdigest(),
                None,
                "trust",
            ),
            key,
            actor=self.actor,
        )
        self.assertEqual("active", state.status)
        assert state.public_key_sha256 is not None and state.revision is not None
        self.assertEqual(self.session, self.service.context(str(self.root), PROJECT))
        review = self.service.review(
            str(self.root),
            PROJECT,
            self.session,
            sealed.package_token,
            trace_id=self.actor.trace_id,
        ).review
        assert review is not None
        self.assertEqual("active", review.trust_status)
        confirmation = PluginEnableConfirmation(
            action_id=new_uuid_v7(),
            project_id=PROJECT,
            plugin_id=review.plugin_id,
            plugin_version=review.plugin_version,
            publisher_key_id=review.publisher_key_id,
            trusted_key_sha256=state.public_key_sha256,
            trusted_key_revision=state.revision,
            package_sha256=review.package_sha256,
            manifest_sha256=review.manifest_sha256,
            permissions=review.permissions,
            destinations=review.destinations,
            operations=review.operations,
            data_classes=review.data_classes,
            credential_scopes=review.credential_scopes,
            expected_revision=None,
        )
        enabled = self.service.enable(
            str(self.root), PROJECT, self.session, sealed.package_token, confirmation, actor=self.actor
        )
        self.assertEqual("enabled", enabled.status)
        self.assertEqual(1, enabled.revision)
        encrypted = tuple(path for path in (self.root / "objects").rglob("*") if path.is_file())
        self.assertEqual(1, len(encrypted))
        self.assertNotEqual(raw, encrypted[0].read_bytes())
        request = PluginInvocationRequest(
            project_id=PROJECT,
            invocation_id=new_uuid_v7(),
            scientific_request_sha256="sha256:" + hashlib.sha256(b"synthetic scientific request").hexdigest(),
            operation=cast(Operation, review.operations[0]),
            destination=review.destinations[0],
        )
        dispatch = self.service.prepare_invocation(
            str(self.root), PROJECT, self.session, sealed.package_token, request, actor=self.actor
        )
        self.assertEqual(review.package_sha256, dispatch.plan.package_sha256)
        self.assertEqual(review.plugin_id, dispatch.package.manifest.plugin_id)
        self.assertEqual(
            dispatch.plan,
            self.service.recheck_admitted_invocation(
                str(self.root),
                PROJECT,
                dispatch,
                request,
                actor=self.actor,
                session_id=self.session,
                package_token=sealed.package_token,
            ),
        )
        restarted = PluginAdminService(
            cast(ProjectLifecycleService, FakeProjects(self.root)),
            self.service._trust,
            actor_id=ACTOR,
            grant_repository_factory=lambda path, identity: SqlitePluginGrantRepository(
                path / "state/project.sqlite3", identity
            ),
            package_repository_factory=lambda path, identity: SqlitePluginPackageRepository(
                path / "state/project.sqlite3", identity
            ),
            runtime_available=lambda: True,
            package_store_factory=self.package_store_factory,
        )
        persisted = restarted.prepare_persisted_invocation(
            str(self.root),
            PROJECT,
            review.package_sha256,
            review.manifest_sha256,
            dispatch.plan.signature_sha256,
            request,
            actor=self.actor,
        )
        self.assertEqual(dispatch.plan, persisted.plan)
        removed_trust = self.service.trust_decide(
            str(self.root),
            PROJECT,
            self.session,
            PluginTrustDecision(
                new_uuid_v7(), review.publisher_key_id, state.public_key_sha256, state.revision, "revoke"
            ),
            None,
            actor=self.actor,
        )
        self.assertEqual("revoked", removed_trust.status)
        restored_trust = self.service.trust_decide(
            str(self.root),
            PROJECT,
            self.session,
            PluginTrustDecision(
                new_uuid_v7(), review.publisher_key_id, state.public_key_sha256, removed_trust.revision, "trust"
            ),
            key,
            actor=self.actor,
        )
        self.assertEqual("active", restored_trust.status)
        stale_review = self.service.review(
            str(self.root),
            PROJECT,
            self.session,
            sealed.package_token,
            trace_id=self.actor.trace_id,
        ).review
        assert stale_review is not None
        self.assertEqual("renewal-required", stale_review.grant_status)
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-trust-changed"):
            self.service.prepare_invocation(
                str(self.root), PROJECT, self.session, sealed.package_token, request, actor=self.actor
            )
        assert restored_trust.revision is not None
        renewed = self.service.enable(
            str(self.root),
            PROJECT,
            self.session,
            sealed.package_token,
            replace(
                confirmation,
                action_id=new_uuid_v7(),
                trusted_key_revision=restored_trust.revision,
                expected_revision=enabled.revision,
            ),
            actor=self.actor,
        )
        self.assertEqual(("enabled", 2), (renewed.status, renewed.revision))
        current_review = self.service.review(
            str(self.root),
            PROJECT,
            self.session,
            sealed.package_token,
            trace_id=self.actor.trace_id,
        ).review
        assert current_review is not None
        self.assertEqual("enabled", current_review.grant_status)
        new_key = SigningKey(b"\x16" * 32)
        new_public_key = bytes(new_key.verify_key)
        new_key_sha256 = "sha256:" + hashlib.sha256(new_public_key).hexdigest()
        with zipfile.ZipFile(io.BytesIO(raw)) as original:
            members = {name: original.read(name) for name in original.namelist()}
        members["manifest.sig"] = new_key.sign(members["manifest.json"]).signature
        rotated_raw, _ = archive(files=members)
        removed_again = self.service.trust_decide(
            str(self.root),
            PROJECT,
            self.session,
            PluginTrustDecision(
                new_uuid_v7(),
                review.publisher_key_id,
                state.public_key_sha256,
                restored_trust.revision,
                "revoke",
            ),
            None,
            actor=self.actor,
        )
        rotated_trust = self.service.trust_decide(
            str(self.root),
            PROJECT,
            self.session,
            PluginTrustDecision(
                new_uuid_v7(),
                review.publisher_key_id,
                new_key_sha256,
                removed_again.revision,
                "rotate",
                previous_key_sha256=state.public_key_sha256,
            ),
            new_public_key,
            actor=self.actor,
        )
        rotated_intake = self.service.create(str(self.root), PROJECT, self.session)
        self.service.chunk(str(self.root), PROJECT, self.session, rotated_intake.intake_id, 1, rotated_raw)
        rotated_sealed = self.service.seal(
            str(self.root),
            PROJECT,
            self.session,
            rotated_intake.intake_id,
            archive_sha256="sha256:" + hashlib.sha256(rotated_raw).hexdigest(),
            byte_length=len(rotated_raw),
            chunk_count=1,
            trace_id=self.actor.trace_id,
        )
        assert rotated_sealed.review is not None and rotated_sealed.package_token is not None
        assert rotated_trust.revision is not None
        self.assertEqual(review.package_sha256, rotated_sealed.review.package_sha256)
        self.assertEqual(review.manifest_sha256, rotated_sealed.review.manifest_sha256)
        self.assertNotEqual(review.signature_sha256, rotated_sealed.review.signature_sha256)
        self.assertEqual("renewal-required", rotated_sealed.review.grant_status)
        rotated_grant = self.service.enable(
            str(self.root),
            PROJECT,
            self.session,
            rotated_sealed.package_token,
            replace(
                confirmation,
                action_id=new_uuid_v7(),
                trusted_key_sha256=new_key_sha256,
                trusted_key_revision=rotated_trust.revision,
                expected_revision=renewed.revision,
            ),
            actor=self.actor,
        )
        self.assertEqual(("enabled", 3), (rotated_grant.status, rotated_grant.revision))
        reopened_rotated = restarted.prepare_persisted_invocation(
            str(self.root),
            PROJECT,
            review.package_sha256,
            review.manifest_sha256,
            rotated_sealed.review.signature_sha256,
            request,
            actor=self.actor,
        )
        self.assertEqual(rotated_sealed.review.signature_sha256, reopened_rotated.plan.signature_sha256)
        pointers = SqlitePluginPackageRepository(self.root / "state/project.sqlite3", PROJECT)
        self.assertIsNotNone(pointers.read(review.package_sha256, review.manifest_sha256, review.signature_sha256))
        self.assertIsNotNone(
            pointers.read(review.package_sha256, review.manifest_sha256, rotated_sealed.review.signature_sha256)
        )
        revoked = self.service.revoke(
            str(self.root),
            PROJECT,
            self.session,
            rotated_grant.plugin_id,
            cast(int, rotated_grant.revision),
            new_uuid_v7(),
            actor=self.actor,
        )
        self.assertEqual(("disabled", 4), (revoked.status, revoked.revision))
        self.assertEqual(
            "disabled", self.service.grant_status(str(self.root), PROJECT, self.session, enabled.plugin_id).status
        )
        with self.assertRaises(PluginGrantProblem):
            self.service.prepare_invocation(
                str(self.root), PROJECT, self.session, sealed.package_token, request, actor=self.actor
            )
        with self.assertRaises(PluginGrantProblem):
            restarted.prepare_persisted_invocation(
                str(self.root),
                PROJECT,
                review.package_sha256,
                review.manifest_sha256,
                dispatch.plan.signature_sha256,
                request,
                actor=self.actor,
            )
        with self.assertRaises(PluginGrantProblem):
            restarted.recheck_admitted_invocation(str(self.root), PROJECT, persisted, request, actor=self.actor)


if __name__ == "__main__":
    unittest.main()
