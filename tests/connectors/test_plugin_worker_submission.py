"""A changed consent cannot replay a prior plugin invocation by idempotency key."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
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
from research_observatory_core.connectors.plugin_broker import (  # noqa: E402
    PluginBrokerCall,
    PluginBrokerResponse,
    PluginNetworkBroker,
)
from research_observatory_core.connectors.plugin_credentials import PluginCredentialSettings  # noqa: E402
from research_observatory_core.connectors.plugin_grants import (  # noqa: E402
    PluginEnableConfirmation,
    PluginGrantActor,
    PluginGrantProblem,
)
from research_observatory_core.connectors.plugin_manifest import PluginProjectGrant, verify_plugin_package  # noqa: E402
from research_observatory_core.connectors.plugin_package_intake import inspect_plugin_archive  # noqa: E402
from research_observatory_core.connectors.plugin_package_store import PluginPackageStore  # noqa: E402
from research_observatory_core.connectors.plugin_scientific_request import (  # noqa: E402
    parse_plugin_scientific_request,
)
from research_observatory_core.connectors.plugin_trust import (  # noqa: E402
    PluginPublisherTrustStore,
    PluginTrustDecision,
)
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.plugin_admin_service import PluginAdminService, PluginAuthorizedDispatch  # noqa: E402
from research_observatory_core.plugin_consent import (  # noqa: E402
    PluginConsentProblem,
    PluginConsentService,
    PluginConsentStamp,
)
from research_observatory_core.plugin_grant_repository import SqlitePluginGrantRepository  # noqa: E402
from research_observatory_core.plugin_invocation_api import register_plugin_invocation_routes  # noqa: E402
from research_observatory_core.plugin_job_repository import PluginJobRepository  # noqa: E402
from research_observatory_core.plugin_package_repository import SqlitePluginPackageRepository  # noqa: E402
from research_observatory_core.plugin_runtime import InstalledPluginRuntime  # noqa: E402
from research_observatory_core.plugin_worker import (  # noqa: E402
    PluginWorkerAdapters,
    PluginWorkerProblem,
    PluginWorkerService,
    _assert_scientific_broker_call,
    _Binding,
)
from research_observatory_core.projects import ProjectLifecycleService  # noqa: E402
from research_observatory_core.repositories import (  # noqa: E402
    _SqliteWorkflowQueueRepository,
    sqlite_workflow_admission_binding,
)
from research_observatory_core.storage import (  # noqa: E402
    configure_protected_database_provider,
    initialize_database,
)
from research_observatory_core.transport import CoreProblem, TraceCorrelationMiddleware  # noqa: E402
from research_observatory_core.windows_credentials import WindowsCredentialStore  # noqa: E402
from research_observatory_core.workflow_executor import (  # noqa: E402
    LocalAdmissionController,
    ProjectWorkerPolicy,
    WorkerResources,
)

from tests.connectors.test_plugin_admin_service import FakeProjects, _project_error  # noqa: E402
from tests.connectors.test_plugin_broker import streamed  # noqa: E402
from tests.connectors.test_plugin_dispatch import _Admin  # noqa: E402
from tests.connectors.test_plugin_job_repository import NOW as JOB_NOW  # noqa: E402
from tests.connectors.test_plugin_job_repository import PluginJobFixture  # noqa: E402
from tests.connectors.test_plugin_package_intake import archive  # noqa: E402
from tests.connectors.test_plugin_package_store import MemoryKeyProvider  # noqa: E402
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402
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

    @unittest.skipUnless(os.name == "nt", "Windows publisher trust authority")
    def test_persisted_dispatch_uses_real_core_grant_without_system_trust_or_enable(self):
        """Use real package/grant authority with fixture consent, runtime, and broker I/O."""
        # Keep the inherited plaintext fixture outside this protected Core root.
        protected = tempfile.TemporaryDirectory(prefix="ro-plugin-worker-protected-")
        self.addCleanup(protected.cleanup)
        self.root = Path(protected.name).resolve()
        for directory in ("state", "objects", ".tmp"):
            (self.root / directory).mkdir()
        self.database = self.root / "state/project.sqlite3"
        configure_protected_database_provider(InMemoryDatabaseKeyProvider())
        self.assertTrue(
            initialize_database(self.database, project_id=self.inputs.project_id, project_created_at=JOB_NOW).ok
        )
        self.keys = MemoryKeyProvider()
        self.objects = create_local_object_store(self.root, self.inputs.project_id, key_provider=self.keys)
        self.repository = PluginJobRepository(self.database, self.inputs.project_id, self.objects)
        self.queue = _SqliteWorkflowQueueRepository(self.database, self.inputs.project_id)
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
        self.addCleanup(
            lambda: subprocess.run(
                [
                    str(Path(os.environ["SYSTEMROOT"]) / "System32/icacls.exe"),
                    str(self.root),
                    "/reset",
                    "/t",
                    "/c",
                    "/q",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
        )
        admin = PluginAdminService(
            cast(ProjectLifecycleService, FakeProjects(self.root)),
            PluginPublisherTrustStore(
                WindowsCredentialStore(self.root / "profile-vault", audit_sink=lambda _event: None),
                "worker-grant-test",
            ),
            actor_id=self.actor.actor_id,
            grant_repository_factory=lambda path, identity: SqlitePluginGrantRepository(
                path / "state/project.sqlite3", identity
            ),
            package_repository_factory=lambda path, identity: SqlitePluginPackageRepository(
                path / "state/project.sqlite3", identity
            ),
            package_store_factory=lambda _path, _identity: PluginPackageStore(self.objects),
            runtime_available=lambda: True,
        )
        root, project_id = str(self.root), self.inputs.project_id
        session = admin.context(root, project_id)
        human = admin.actor("a" * 32)
        system = PluginGrantActor(human.actor_id, human.trace_id, human.occurred_at, actor_type="system")
        raw, public_key = archive()
        intake = admin.create(root, project_id, session)
        admin.chunk(root, project_id, session, intake.intake_id, 1, raw)
        sealed = admin.seal(
            root,
            project_id,
            session,
            intake.intake_id,
            archive_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            trace_id=human.trace_id,
        )
        assert sealed.review is not None and sealed.package_token is not None
        key_sha256 = "sha256:" + hashlib.sha256(public_key).hexdigest()
        trust = PluginTrustDecision(new_uuid_v7(), sealed.review.publisher_key_id, key_sha256, None, "trust")
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-actor-invalid"):
            admin.trust_decide(root, project_id, session, trust, public_key, actor=system)
        self.assertEqual(
            "untrusted",
            admin.review(root, project_id, session, sealed.package_token, trace_id=human.trace_id).review.trust_status,
        )
        trusted = admin.trust_decide(root, project_id, session, trust, public_key, actor=human)
        self.assertEqual("active", trusted.status)
        assert trusted.public_key_sha256 is not None and trusted.revision is not None
        reviewed = admin.review(root, project_id, session, sealed.package_token, trace_id=human.trace_id).review
        assert reviewed is not None
        confirmation = PluginEnableConfirmation(
            action_id=new_uuid_v7(),
            project_id=project_id,
            plugin_id=reviewed.plugin_id,
            plugin_version=reviewed.plugin_version,
            publisher_key_id=reviewed.publisher_key_id,
            trusted_key_sha256=trusted.public_key_sha256,
            trusted_key_revision=trusted.revision,
            package_sha256=reviewed.package_sha256,
            manifest_sha256=reviewed.manifest_sha256,
            permissions=reviewed.permissions,
            destinations=reviewed.destinations,
            operations=reviewed.operations,
            data_classes=reviewed.data_classes,
            credential_scopes=reviewed.credential_scopes,
            expected_revision=None,
        )
        with self.assertRaisesRegex(PluginGrantProblem, "plugin-grant-actor-invalid"):
            admin.enable(root, project_id, session, sealed.package_token, confirmation, actor=system)
        self.assertIsNone(admin.current_grant_persisted(root, project_id, reviewed.plugin_id))
        enabled = admin.enable(root, project_id, session, sealed.package_token, confirmation, actor=human)
        self.assertEqual(("enabled", 1), (enabled.status, enabled.revision))
        grants = SqlitePluginGrantRepository(self.database, project_id)
        self.assertEqual(["enabled"], [event.event_kind for event in grants.audit_history(reviewed.plugin_id)])

        self.worker._admin = admin
        requests: list[str] = []

        async def synthetic_fetch(_broker, _plan, _call):
            requests.append("lookup")
            return PluginBrokerResponse(body=b'{"id":"synthetic-1"}', redacted=False)

        def run(_runtime, _package, _files, **kwargs):
            kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"})
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
        with (
            patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", synthetic_fetch),
            patch.object(admin, "prepare_persisted_invocation", wraps=admin.prepare_persisted_invocation) as prepare,
        ):
            queued = self.worker.submit(root, self.preview_id, self.inputs.request, self.input_data)
            self.worker.run_pending()
        result = self.queue.get(queued.job_id)
        self.assertGreaterEqual(prepare.call_count, 1)
        self.assertEqual(
            "succeeded",
            result.state,
            f"persisted Core actor type={prepare.call_args.kwargs['actor'].actor_type}",
        )
        self.assertEqual("system", prepare.call_args.kwargs["actor"].actor_type)
        self.assertEqual(self.actor.actor_id, prepare.call_args.kwargs["actor"].actor_id)
        self.assertEqual(queued.job_id.replace("-", ""), prepare.call_args.kwargs["actor"].trace_id)
        self.assertEqual(["lookup"], requests)
        page = self.repository.result(self.repository.input(self.inputs.invocation_id))
        self.assertIsNotNone(page)
        self.assertNotEqual(b"SQLite format 3\0", self.database.read_bytes()[:16])
        self.assertEqual(["enabled"], [event.event_kind for event in grants.audit_history(reviewed.plugin_id)])

    def _run_confirmed_job(self):
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
            kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"})
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

        async def synthetic_fetch(_broker, _plan, _call):
            return PluginBrokerResponse(body=b'{"id":"synthetic-1"}', redacted=False)

        with patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", synthetic_fetch):
            queued = self.worker.submit(str(self.root), self.preview_id, self.inputs.request, self.input_data)
            self.worker.run_pending()
        return queued, calls

    def test_confirmed_job_runs_through_claim_and_fenced_encrypted_publication(self):
        queued, calls = self._run_confirmed_job()
        result = self.queue.get(queued.job_id)
        self.assertEqual("succeeded", result.state)
        self.assertEqual([self.input_data], calls)
        page = self.repository.result(self.repository.input(self.inputs.invocation_id))
        assert page is not None
        self.assertEqual(queued.job_id, page.job_id)
        self.assertEqual(self.plan.source_id, page.plan.source_id)
        self.assertEqual(1, len(page.broker_responses))
        with self.objects.open(page.broker_responses[0].object_sha256, purpose="document-analysis") as source:
            self.assertEqual(b'{"id":"synthetic-1"}', source.read())
        physical = tuple(path for path in (self.root / "objects").rglob("*") if path.is_file())
        self.assertTrue(physical)
        self.assertFalse(any(self.input_data in path.read_bytes() for path in physical))

    def test_due_heartbeat_does_not_interrupt_fenced_publication(self):
        polls = []

        def advancing_clock():
            instant = float(len(polls) * 3)
            polls.append(instant)
            return instant

        with patch("research_observatory_core.plugin_worker.time", SimpleNamespace(monotonic=advancing_clock)):
            self.test_confirmed_job_runs_through_claim_and_fenced_encrypted_publication()
        self.assertGreater(len(polls), 1)

    def test_stop_after_last_poll_cannot_publish(self):
        publish = self.repository.publish

        def stop_before_writer(*args, **kwargs):
            self.worker._stopped.set()
            return publish(*args, **kwargs)

        with patch.object(self.repository, "publish", stop_before_writer):
            queued, _calls = self._run_confirmed_job()
        self.assertEqual("failed", self.queue.get(queued.job_id).state)
        self.assertIsNone(self.repository.result(self.repository.input(self.inputs.invocation_id)))

    def test_durable_cancel_after_last_poll_cannot_publish(self):
        publish = self.repository.publish

        def cancel_before_writer(*args, **kwargs):
            self.queue.request_cancellation(
                args[3].job_id,
                actor=self.actor,
                now=self.worker._now(),
                reason_code="plugin-user-cancelled",
                interruption_kind="user-cancel",
            )
            return publish(*args, **kwargs)

        with patch.object(self.repository, "publish", cancel_before_writer):
            queued, _calls = self._run_confirmed_job()
        self.assertEqual("cancelled", self.queue.get(queued.job_id).state)
        self.assertIsNone(self.repository.result(self.repository.input(self.inputs.invocation_id)))

    def test_expired_lease_cannot_publish(self):
        publish = self.repository.publish

        def expire_at_writer(*args, **kwargs):
            kwargs["now"] = lambda: "2099-10-01T12:00:00.000Z"
            return publish(*args, **kwargs)

        with patch.object(self.repository, "publish", expire_at_writer):
            queued, _calls = self._run_confirmed_job()
        self.assertEqual("failed", self.queue.get(queued.job_id).state)
        self.assertIsNone(self.repository.result(self.repository.input(self.inputs.invocation_id)))

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

    def test_search_continuation_requires_exact_consented_broker_cursor(self):
        previous_id = new_uuid_v7()
        raw = json.dumps(
            {"query": "public records", "pageSize": 2, "cursor": "page-b", "previousInvocationId": previous_id},
            separators=(",", ":"),
        ).encode()
        _assert_scientific_broker_call(
            raw,
            "search",
            PluginBrokerCall(operation="search", query="public records", page_size=2, cursor="page-b"),
        )
        with self.assertRaisesRegex(PluginWorkerProblem, "broker-parameters-denied"):
            _assert_scientific_broker_call(
                raw,
                "search",
                PluginBrokerCall(operation="search", query="public records", page_size=2, cursor="page-c"),
            )

    def test_predecessor_must_be_published_same_package_and_exact_next_cursor(self):
        previous_id = new_uuid_v7()
        current_id = new_uuid_v7()
        prior_plan = self.plan.model_copy(update={"operation": "search", "invocation_id": previous_id})
        current_plan = self.plan.model_copy(update={"operation": "search", "invocation_id": current_id})
        prior_request = self.inputs.request.model_copy(update={"operation": "search", "invocation_id": previous_id})
        prior_input = self.inputs.model_copy(update={"request": prior_request})
        current = parse_plugin_scientific_request(
            json.dumps(
                {"query": "public records", "pageSize": 2, "cursor": "page-b", "previousInvocationId": previous_id},
                separators=(",", ":"),
            ).encode(),
            "search",
        )
        page = SimpleNamespace(plan=prior_plan, continuation="next-page", next_cursor="page-b")
        jobs = SimpleNamespace(input=lambda _id: prior_input, result=lambda _input: page)
        binding = SimpleNamespace(project_id=self.inputs.project_id, adapters=SimpleNamespace(jobs=jobs))
        with patch.object(self.worker, "_input_bytes", return_value=b'{"query":"public records","pageSize":2}'):
            self.worker._predecessor(cast(_Binding, binding), current_plan, current)
            for changed in (
                SimpleNamespace(plan=prior_plan, continuation="next-page", next_cursor="page-c"),
                SimpleNamespace(plan=prior_plan, continuation="exhausted", next_cursor=None),
                SimpleNamespace(
                    plan=prior_plan.model_copy(update={"package_sha256": "sha256:" + "a" * 64}),
                    continuation="next-page",
                    next_cursor="page-b",
                ),
                SimpleNamespace(
                    plan=prior_plan.model_copy(update={"grant_revision": prior_plan.grant_revision + 1}),
                    continuation="next-page",
                    next_cursor="page-b",
                ),
            ):
                with (
                    self.subTest(changed=changed),
                    self.assertRaisesRegex(PluginWorkerProblem, "page-predecessor-denied"),
                ):
                    self.worker._predecessor(
                        cast(
                            _Binding,
                            SimpleNamespace(
                                project_id=self.inputs.project_id,
                                adapters=SimpleNamespace(
                                    jobs=SimpleNamespace(
                                        input=lambda _id: prior_input,
                                        result=lambda _input, page=changed: page,
                                    )
                                ),
                            ),
                        ),
                        current_plan,
                        current,
                    )
            with self.assertRaisesRegex(PluginWorkerProblem, "page-predecessor-denied"):
                self.worker._predecessor(
                    cast(
                        _Binding,
                        SimpleNamespace(
                            project_id=self.inputs.project_id,
                            adapters=SimpleNamespace(
                                jobs=SimpleNamespace(input=lambda _id: prior_input, result=lambda _input: None)
                            ),
                        ),
                    ),
                    current_plan,
                    current,
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
