"""A changed consent cannot replay a prior plugin invocation by idempotency key."""

from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import httpx2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.authentication import (  # noqa: E402
    LocalAuthenticationMiddleware,
    capability_token_digest,
)
from research_observatory_core.connectors.plugin_broker import PluginBrokerCall, PluginNetworkBroker  # noqa: E402
from research_observatory_core.connectors.plugin_credentials import PluginCredentialSettings  # noqa: E402
from research_observatory_core.connectors.plugin_grants import PluginGrantActor  # noqa: E402
from research_observatory_core.connectors.plugin_manifest import PluginProjectGrant, verify_plugin_package  # noqa: E402
from research_observatory_core.connectors.plugin_package_intake import inspect_plugin_archive  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.plugin_admin_service import PluginAdminService, PluginAuthorizedDispatch  # noqa: E402
from research_observatory_core.plugin_consent import (  # noqa: E402
    PluginConsentProblem,
    PluginConsentService,
    PluginConsentStamp,
)
from research_observatory_core.plugin_invocation_api import register_plugin_invocation_routes  # noqa: E402
from research_observatory_core.plugin_runtime import InstalledPluginRuntime  # noqa: E402
from research_observatory_core.plugin_worker import (  # noqa: E402
    PluginWorkerAdapters,
    PluginWorkerProblem,
    PluginWorkerService,
    _assert_scientific_broker_call,
)
from research_observatory_core.projects import ProjectLifecycleService  # noqa: E402
from research_observatory_core.repositories import sqlite_workflow_admission_binding  # noqa: E402
from research_observatory_core.transport import CoreProblem, TraceCorrelationMiddleware  # noqa: E402
from research_observatory_core.workflow_executor import (  # noqa: E402
    LocalAdmissionController,
    ProjectWorkerPolicy,
    WorkerResources,
)

from tests.connectors.test_plugin_admin_service import FakeProjects, _project_error  # noqa: E402
from tests.connectors.test_plugin_broker import streamed  # noqa: E402
from tests.connectors.test_plugin_dispatch import _Admin  # noqa: E402
from tests.connectors.test_plugin_job_repository import PluginJobFixture  # noqa: E402
from tests.connectors.test_plugin_package_intake import archive  # noqa: E402
from tests.service import test_core_api as api  # noqa: E402


class FakeAdmin:
    def __init__(self, plan):
        self.plan = plan
        self.inspected = inspect_plugin_archive(archive()[0])

    def actor(self, trace_id):
        return PluginGrantActor(new_uuid_v7(), trace_id, "2026-10-01T12:00:00.000Z")

    def prepare_persisted_invocation(self, _root, _project, _package, _manifest, _signature, _request, *, actor):
        return PluginAuthorizedDispatch(
            type("SignedPackage", (), {"manifest": self.inspected.manifest})(), self.plan, {}
        )


class FakeAuthority:
    def __init__(self, plan, stamp):
        self.plan = plan
        self.stamp = stamp

    def guard(self, request, plan, stage, action):
        assert request.invocation_id == self.plan.invocation_id
        assert plan == self.plan
        assert stage in {"admission", "dispatch", "broker", "publication"}
        return action(self.stamp)


class FakeConsent:
    def __init__(self, authority):
        self.current = authority

    def authority(self, _root, preview_id):
        assert preview_id == self.current.stamp.preview_id
        return self.current

    def revoke(self, _root, preview_id):
        assert preview_id == self.current.stamp.preview_id


class PluginWorkerSubmissionTests(PluginJobFixture):
    def setUp(self):
        super().setUp()
        self.preview_id = new_uuid_v7()
        self.stamp = PluginConsentStamp(
            preview_id=self.preview_id,
            session_id="3" * 32,
            request_sha256=self.plan.request_sha256,
            confirmation_sha256="sha256:" + "5" * 64,
            policy_sha256=self.inputs.policy_hash,
            retention_sha256="sha256:" + "6" * 64,
            intent=self.inputs.intent,
        )
        self.authority = FakeAuthority(self.plan, self.stamp)
        self.consent = FakeConsent(self.authority)
        demand = WorkerResources(1, 64 * 1024**2, 0, 64 * 1024**2)
        self.admission = sqlite_workflow_admission_binding(
            self.queue,
            controller=LocalAdmissionController(interactive_reserve=demand),
            policy=ProjectWorkerPolicy(self.inputs.project_id, demand, {"document": demand}, {"document": 1}),
        )
        self.worker = PluginWorkerService(
            cast(ProjectLifecycleService, FakeProjects(self.root)),
            cast(PluginAdminService, None),
            cast(PluginConsentService, self.consent),
            lambda _path, _identity: PluginWorkerAdapters(self.repository, self.queue, self.admission, self.objects),
            local_actor_id=self.actor.actor_id,
        )

    def test_confirmed_job_runs_through_claim_and_fenced_encrypted_publication(self):
        raw, key = archive()
        inspected = inspect_plugin_archive(raw)
        package = verify_plugin_package(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            {inspected.manifest.publisher_key_id: key},
        )
        manifest = package.manifest
        grant = PluginProjectGrant(
            project_id=self.inputs.project_id,
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.plugin_version,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            publisher_key_id=manifest.publisher_key_id,
            permissions=manifest.permissions,
            destinations=manifest.destinations,
            revision=1,
        )
        self.worker._admin = cast(PluginAdminService, _Admin(package, dict(inspected.files), self.plan, grant))
        calls = []

        def run(_runtime, _package, _files, **kwargs):
            calls.append(kwargs["input_data"])
            output = json.dumps(
                {
                    "schemaVersion": "1.0",
                    "invocationId": self.inputs.invocation_id,
                    "operation": self.inputs.request.operation,
                    "records": [],
                    "continuation": "exhausted",
                },
                separators=(",", ":"),
            ).encode()
            return SimpleNamespace(
                output=output,
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=0,
            )

        self.worker._runtime = cast(InstalledPluginRuntime, SimpleNamespace(load=lambda: object(), run=run))
        queued = self.worker.submit(str(self.root), self.preview_id, self.inputs.request, self.input_data)
        self.worker.run_pending()
        result = self.queue.get(queued.job_id)
        self.assertEqual("succeeded", result.state)
        self.assertEqual([self.input_data], calls)
        page = self.repository.result(self.repository.input(self.inputs.invocation_id))
        assert page is not None
        self.assertEqual(queued.job_id, page.job_id)
        self.assertEqual(self.plan.source_id, page.plan.source_id)
        physical = tuple(path for path in (self.root / "objects").rglob("*") if path.is_file())
        self.assertTrue(physical)
        self.assertFalse(any(self.input_data in path.read_bytes() for path in physical))

    def test_live_worker_broker_denies_changed_scientific_identifier_before_egress(self):
        raw, key = archive()
        inspected = inspect_plugin_archive(raw)
        package = verify_plugin_package(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            {inspected.manifest.publisher_key_id: key},
        )
        manifest = package.manifest
        grant = PluginProjectGrant(
            project_id=self.inputs.project_id,
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.plugin_version,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            publisher_key_id=manifest.publisher_key_id,
            permissions=manifest.permissions,
            destinations=manifest.destinations,
            revision=1,
        )
        admin = _Admin(package, dict(inspected.files), self.plan, grant)
        self.worker._admin = cast(PluginAdminService, admin)

        def run(_runtime, _package, _files, **kwargs):
            kwargs["broker_callback"]({"operation": "lookup", "identifier": "different"})
            self.fail("changed scientific identifier reached a successful worker result")

        self.worker._runtime = cast(InstalledPluginRuntime, SimpleNamespace(load=lambda: object(), run=run))
        queued = self.worker.submit(str(self.root), self.preview_id, self.inputs.request, self.input_data)
        self.worker.run_pending()
        self.assertNotEqual("succeeded", self.queue.get(queued.job_id).state)
        self.assertIn("policy-denied", admin.denials)
        self.assertIsNone(self.repository.result(self.repository.input(self.inputs.invocation_id)))

    def test_live_worker_broker_allows_exact_scientific_identifier_with_synthetic_transport(self):
        raw, key = archive()
        inspected = inspect_plugin_archive(raw)
        package = verify_plugin_package(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            {inspected.manifest.publisher_key_id: key},
        )
        manifest = package.manifest
        grant = PluginProjectGrant(
            project_id=self.inputs.project_id,
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.plugin_version,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            publisher_key_id=manifest.publisher_key_id,
            permissions=manifest.permissions,
            destinations=manifest.destinations,
            revision=1,
        )
        admin = _Admin(package, dict(inspected.files), self.plan, grant)
        self.worker._admin = cast(PluginAdminService, admin)
        requests: list[str] = []

        def respond(request: httpx2.Request) -> httpx2.Response:
            requests.append(str(request.url))
            return streamed(httpx2.Response(200, json={"id": "synthetic-1"}))

        def broker(**kwargs):
            return PluginNetworkBroker(**kwargs, transport_factory=lambda *_: httpx2.MockTransport(respond))

        def run(_runtime, _package, _files, **kwargs):
            body = kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"})
            self.assertEqual({"id": "synthetic-1"}, json.loads(body))
            output = json.dumps(
                {
                    "schemaVersion": "1.0",
                    "invocationId": self.inputs.invocation_id,
                    "operation": self.inputs.request.operation,
                    "records": [],
                    "continuation": "exhausted",
                },
                separators=(",", ":"),
            ).encode()
            return SimpleNamespace(
                output=output,
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        self.worker._runtime = cast(InstalledPluginRuntime, SimpleNamespace(load=lambda: object(), run=run))
        with patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker", side_effect=broker):
            queued = self.worker.submit(str(self.root), self.preview_id, self.inputs.request, self.input_data)
            self.worker.run_pending()
        self.assertEqual(("succeeded", []), (self.queue.get(queued.job_id).state, admin.denials))
        self.assertEqual(["https://repository.example.invalid/v1/records?identifier=synthetic-1"], requests)
        self.assertEqual([], admin.denials)

    def test_scientific_parameter_binding_rejects_cursor_and_ambiguous_input(self):
        approved = PluginBrokerCall(operation="lookup", identifier="synthetic-1")
        _assert_scientific_broker_call(self.input_data, self.plan.operation, approved)
        for input_data, call in (
            (self.input_data, PluginBrokerCall(operation="lookup", identifier="different")),
            (b'{"identifier":"one","identifier":"two"}', approved),
            (b'{"identifier":"synthetic-1","query":"extra"}', approved),
        ):
            with self.assertRaisesRegex(PluginWorkerProblem, "broker-parameters-denied"):
                _assert_scientific_broker_call(input_data, self.plan.operation, call)
        with self.assertRaisesRegex(PluginWorkerProblem, "broker-parameters-denied"):
            _assert_scientific_broker_call(
                b'{"query":"approved"}',
                "search",
                PluginBrokerCall(operation="search", query="approved", cursor="unapproved-page"),
            )

    def test_restart_without_ephemeral_consent_cancels_durable_runnable_job(self):
        queued = self.worker.submit(str(self.root), self.preview_id, self.inputs.request, self.input_data)

        class LostConsent:
            def authority(self, _root, _preview_id):
                raise PluginConsentProblem()

        reopened = PluginWorkerService(
            cast(ProjectLifecycleService, FakeProjects(self.root)),
            cast(PluginAdminService, None),
            cast(PluginConsentService, LostConsent()),
            lambda _path, _identity: PluginWorkerAdapters(self.repository, self.queue, self.admission, self.objects),
            local_actor_id=self.actor.actor_id,
        )
        reopened.attach(str(self.root))
        reopened.run_pending()
        self.assertEqual("cancelled", self.queue.get(queued.job_id).state)
        self.assertIsNone(self.repository.result(self.repository.input(self.inputs.invocation_id)))

    def test_exact_replay_succeeds_but_changed_consent_conflicts(self):
        first = self.worker.submit(str(self.root), self.preview_id, self.inputs.request, self.input_data)
        second = self.worker.submit(str(self.root), self.preview_id, self.inputs.request, self.input_data)
        self.assertEqual(first.job_id, second.job_id)
        self.authority.stamp = PluginConsentStamp(
            preview_id=self.preview_id,
            session_id=self.stamp.session_id,
            request_sha256=self.stamp.request_sha256,
            confirmation_sha256=self.stamp.confirmation_sha256,
            policy_sha256=self.stamp.policy_sha256,
            retention_sha256="sha256:" + "9" * 64,
            intent=self.stamp.intent,
        )
        with self.assertRaisesRegex(PluginWorkerProblem, "invocation-conflict"):
            self.worker.submit(str(self.root), self.preview_id, self.inputs.request, self.input_data)
        replay = self.queue.find_idempotency(self.inputs.idempotency_key)
        assert replay is not None
        self.assertEqual(first.job_id, replay.job_id)

    def test_credential_status_denies_scope_absent_from_signed_manifest(self):
        self.worker._admin = cast(PluginAdminService, FakeAdmin(self.plan))
        self.worker._credentials = PluginCredentialSettings(None)
        with self.assertRaisesRegex(PluginWorkerProblem, "scope-denied"):
            self.worker.credential_status(
                str(self.root),
                self.inputs.project_id,
                self.preview_id,
                self.inputs.request,
                "unlisted-token",
                trace_id="a" * 32,
            )

    def test_authenticated_native_submit_status_cancel_reaches_durable_job(self):
        app = FastAPI()
        app.add_middleware(
            LocalAuthenticationMiddleware, digest=capability_token_digest(api.TOKEN), authority=api.AUTHORITY
        )
        app.add_middleware(TraceCorrelationMiddleware)

        @app.exception_handler(CoreProblem)
        async def failed(_request: Request, error: CoreProblem):
            return JSONResponse(
                status_code=error.problem.status,
                content=error.problem.model_dump(mode="json", by_alias=True),
            )

        register_plugin_invocation_routes(
            app,
            lambda _request: cast(PluginAdminService, FakeAdmin(self.plan)),
            lambda _request: cast(PluginConsentService, self.consent),
            lambda _request: self.worker,
            _project_error,
        )
        route = "/native/connectors/plugins/invocations/"
        address = {"root": str(self.root), "projectId": self.inputs.project_id}
        payload = address | {
            "previewId": self.preview_id,
            "request": self.inputs.request.model_dump(mode="json", by_alias=True),
            "inputData": base64.b64encode(self.input_data).decode("ascii"),
        }
        with api.authenticated_client(app) as client:
            self.assertNotIn(route + "submit", app.openapi()["paths"])
            unauthenticated = client.post(route + "submit", json=payload, headers={"Authorization": ""})
            self.assertEqual(401, unauthenticated.status_code)
            submitted = client.post(route + "submit", json=payload)
            self.assertEqual(200, submitted.status_code, submitted.text)
            job_id = submitted.json()["jobId"]
            self.assertEqual("runnable", submitted.json()["state"])
            self.assertNotIn("inputData", submitted.text)
            status = client.post(route + "status", json=address | {"jobId": job_id})
            self.assertEqual(200, status.status_code, status.text)
            self.assertEqual(job_id, status.json()["jobId"])
            denied = client.post(route + "status", json=address | {"projectId": new_uuid_v7(), "jobId": job_id})
            self.assertEqual(403, denied.status_code, denied.text)
            cancelled = client.post(route + "cancel", json=address | {"jobId": job_id})
            self.assertEqual(200, cancelled.status_code, cancelled.text)


if __name__ == "__main__":
    unittest.main()
