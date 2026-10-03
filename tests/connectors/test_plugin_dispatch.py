"""Core dispatch refuses stale authority and stages only verified bounded output."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import tempfile
import threading
import unittest
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_broker import PluginBrokerProblem  # noqa: E402
from research_observatory_core.connectors.plugin_dispatch import (  # noqa: E402
    PluginDispatchController,
    PluginDispatchProblem,
)
from research_observatory_core.connectors.plugin_grants import PluginGrantActor  # noqa: E402
from research_observatory_core.connectors.plugin_manifest import (  # noqa: E402
    PluginInvocationRequest,
    PluginProjectGrant,
    authorize_plugin_invocation,
    verify_plugin_package,
)
from research_observatory_core.connectors.plugin_package_intake import inspect_plugin_archive  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.plugin_admin_service import PluginAdminService, PluginAuthorizedDispatch  # noqa: E402
from research_observatory_core.plugin_grant_repository import SqlitePluginGrantRepository  # noqa: E402
from research_observatory_core.ports.object_store import ObjectStore, StoredObject  # noqa: E402
from research_observatory_core.storage import configure_protected_database_provider, initialize_database  # noqa: E402

from tests.connectors.test_plugin_manifest_contract import _manifest_bytes, _manifest_document  # noqa: E402
from tests.connectors.test_plugin_package_intake import archive  # noqa: E402
from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402

PROJECT = "0190a000-0000-7000-8000-000000000040"


class _Admin:
    def __init__(self, package, files, plan, grant):
        self.dispatch = PluginAuthorizedDispatch(package, plan, files)
        self.grant = grant
        self.denials: list[str] = []
        self.current = True

    def prepare_invocation(self, *_args, **_kwargs):
        return self.dispatch

    def prepare_persisted_invocation(self, *_args, **_kwargs):
        return self.dispatch

    def recheck_invocation(self, *_args, **_kwargs):
        if not self.current:
            raise ValueError("stale")
        return self.dispatch.plan

    def recheck_persisted_invocation(self, *_args, **_kwargs):
        return self.recheck_invocation()

    def recheck_admitted_invocation(self, *_args, **_kwargs):
        return self.recheck_invocation()

    def current_grant(self, *_args):
        return self.grant if self.current else None

    def current_grant_persisted(self, *_args):
        return self.current_grant()

    def record_denial(self, *_args, reason_code, **_kwargs):
        self.denials.append(reason_code)

    def record_denial_persisted(self, *_args, reason_code, **_kwargs):
        self.denials.append(reason_code)


class _Store:
    def __init__(self):
        self.puts = 0
        self.bodies: dict[str, bytes] = {}

    def put(self, source, command):
        self.puts += 1
        body = source.read()
        self.bodies[hashlib.sha256(body).hexdigest()] = body
        assert command.protection_profile == "project-encrypted-v1"
        assert command.rights_status == "allowed"
        assert command.retention_class == "project-lifetime"
        return StoredObject(
            object_sha256=hashlib.sha256(body).hexdigest(),
            byte_length=len(body),
            media_type=command.media_type,
            rights_status=command.rights_status,
            protection_profile=command.protection_profile,
            retention_class=command.retention_class,
            creation_source=command.creation_source,
            storage_state="available",
            created_at=command.created_at,
            verified_at=command.created_at,
            reference_count=0,
            envelope_version="1.0",
            key_version="test",
            ciphertext_byte_length=len(body) + 32,
        )


class PluginDispatchTests(unittest.TestCase):
    def setUp(self):
        raw, key = archive()
        inspected = inspect_plugin_archive(raw)
        package = verify_plugin_package(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            {inspected.manifest.publisher_key_id: key},
        )
        manifest = package.manifest
        self.input_data = b'{"identifier":"synthetic-1"}'
        self.request = PluginInvocationRequest(
            project_id=PROJECT,
            invocation_id=new_uuid_v7(),
            scientific_request_sha256="sha256:" + hashlib.sha256(self.input_data).hexdigest(),
            operation=manifest.operations[0],
            destination=manifest.destinations[0],
        )
        grant = PluginProjectGrant(
            project_id=PROJECT,
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.plugin_version,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            publisher_key_id=manifest.publisher_key_id,
            permissions=manifest.permissions,
            destinations=manifest.destinations,
            revision=1,
        )
        plan = authorize_plugin_invocation(package, grant, self.request)
        self.admin = _Admin(package, dict(inspected.files), plan, grant)
        self.store = _Store()
        self.actor = PluginGrantActor(new_uuid_v7(), "a" * 32, "2026-10-01T12:00:00.000Z")
        self.cancelled = False

    def _controller(self, runner):
        return PluginDispatchController(
            cast(PluginAdminService, self.admin),
            runtime_provider=lambda: object(),
            runner=runner,
            object_store=lambda _project: cast(ObjectStore, self.store),
            current_request=lambda _project, _invocation: self.request,
            policy_recheck=lambda _plan, _call: None,
            current_credential_origin=lambda _scope, _plan: None,
            cancelled=lambda _invocation: self.cancelled,
        )

    def _run(self, runner):
        return asyncio.run(
            self._controller(runner).dispatch(
                root="C:/synthetic",
                project_id=PROJECT,
                session_id="a" * 32,
                package_token="b" * 64,
                request=self.request,
                input_data=self.input_data,
                actor=self.actor,
            )
        )

    def _valid_output(self):
        return json.dumps(
            {
                "schemaVersion": "1.0",
                "invocationId": self.request.invocation_id,
                "operation": self.request.operation,
                "records": [],
                "continuation": "exhausted",
            },
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    async def _lookup_response(_broker, _plan, _call):
        return SimpleNamespace(body=b'{"id":"synthetic-1"}', redacted=False)

    def _search(self):
        manifest_document = _manifest_document()
        manifest_document["operations"].append("search")
        raw, key = archive(manifest=_manifest_bytes(manifest_document))
        inspected = inspect_plugin_archive(raw)
        package = verify_plugin_package(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            {inspected.manifest.publisher_key_id: key},
        )
        self.input_data = b'{"query":"approved","pageSize":2}'
        self.request = PluginInvocationRequest(
            project_id=PROJECT,
            invocation_id=new_uuid_v7(),
            scientific_request_sha256="sha256:" + hashlib.sha256(self.input_data).hexdigest(),
            operation="search",
            destination=package.manifest.destinations[0],
        )
        grant = PluginProjectGrant(
            project_id=PROJECT,
            plugin_id=package.manifest.plugin_id,
            plugin_version=package.manifest.plugin_version,
            package_sha256=package.package_sha256,
            manifest_sha256=package.manifest_sha256,
            publisher_key_id=package.manifest.publisher_key_id,
            permissions=package.manifest.permissions,
            destinations=package.manifest.destinations,
            revision=1,
        )
        self.admin = _Admin(
            package, dict(inspected.files), authorize_plugin_invocation(package, grant, self.request), grant
        )

    def _search_output(self, next_cursor):
        page = {
            "schemaVersion": "1.0",
            "invocationId": self.request.invocation_id,
            "operation": "search",
            "records": [],
            "continuation": "next-page" if next_cursor is not None else "exhausted",
        }
        if next_cursor is not None:
            page["nextCursor"] = next_cursor
        return json.dumps(page, separators=(",", ":")).encode()

    def test_broker_observation_has_separate_encrypted_stage_reference(self):
        response = b'{"id":"synthetic-1"}'

        async def fetch(_broker, _plan, _call):
            return SimpleNamespace(body=response, redacted=False)

        def runner(_runtime, _package, _files, **kwargs):
            self.assertEqual(response, kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"}))
            return SimpleNamespace(
                output=self._valid_output(),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        with patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", fetch):
            staged = self._run(runner)
        self.assertEqual(2, self.store.puts)
        self.assertEqual(1, len(staged.broker_responses))
        reference = staged.broker_responses[0]
        self.assertEqual(
            (hashlib.sha256(response).hexdigest(), len(response)), (reference.object_sha256, reference.byte_length)
        )
        self.assertIs(reference.redacted, False)
        self.assertEqual(response, self.store.bodies[reference.object_sha256])
        self.assertNotEqual(staged.object_sha256, reference.object_sha256)

    def test_broker_redaction_flag_stays_with_core_staged_response(self):
        private_value = b"private-contact-sentinel"
        response = b'{"contact":"[REDACTED]"}'

        async def fetch(_broker, _plan, _call):
            return SimpleNamespace(body=response, redacted=True)

        def runner(_runtime, _package, _files, **kwargs):
            self.assertEqual(response, kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"}))
            return SimpleNamespace(
                output=self._valid_output(),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        with patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", fetch):
            staged = self._run(runner)
        reference = staged.broker_responses[0]
        self.assertIs(reference.redacted, True)
        self.assertEqual(response, self.store.bodies[reference.object_sha256])
        self.assertFalse(any(private_value in body for body in self.store.bodies.values()))

    def test_non_search_changed_identifier_denied_before_broker_fetch(self):
        fetches: list[str] = []

        async def fetch(_broker, _plan, _call):
            fetches.append("egress")
            return SimpleNamespace(body=b'{"id":"different"}', redacted=False)

        def runner(_runtime, _package, _files, **kwargs):
            with suppress(PluginDispatchProblem):
                kwargs["broker_callback"]({"operation": "lookup", "identifier": "different"})
            return SimpleNamespace(
                output=self._valid_output(),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        with (
            patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", fetch),
            self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-failed"),
        ):
            self._run(runner)
        self.assertEqual([], fetches)
        self.assertEqual(0, self.store.puts)

    def test_non_search_multiple_exact_calls_retain_ordered_sanitized_responses(self):
        responses = [b'{"sequence":1}', b'{"sequence":2}']

        async def fetch(_broker, _plan, _call):
            return SimpleNamespace(body=responses.pop(0), redacted=False)

        def runner(_runtime, _package, _files, **kwargs):
            call = {"operation": "lookup", "identifier": "synthetic-1"}
            first = kwargs["broker_callback"](call)
            second = kwargs["broker_callback"](call)
            self.assertEqual((b'{"sequence":1}', b'{"sequence":2}'), (first, second))
            return SimpleNamespace(
                output=self._valid_output(),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=2,
            )

        with patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", fetch):
            staged = self._run(runner)
        self.assertEqual(2, staged.broker_calls)
        self.assertEqual(3, self.store.puts)
        self.assertEqual(
            (b'{"sequence":1}', b'{"sequence":2}'),
            tuple(self.store.bodies[ref.object_sha256] for ref in staged.broker_responses),
        )

    def test_zero_broker_call_result_cannot_stage_source_assertion(self):
        def runner(_runtime, _package, _files, **_kwargs):
            return SimpleNamespace(
                output=self._valid_output(),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=0,
            )

        with self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-result-invalid"):
            self._run(runner)
        self.assertEqual(0, self.store.puts)

    def test_search_next_cursor_must_equal_sanitized_broker_observation(self):
        self._search()

        async def fetch(_broker, _plan, _call):
            return SimpleNamespace(body=b'{"items":[],"nextCursor":"page-2"}', redacted=False)

        def runner(_runtime, _package, _files, **kwargs):
            kwargs["broker_callback"]({"operation": "search", "query": "approved", "pageSize": 2})
            return SimpleNamespace(
                output=self._search_output("forged-page"),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        with (
            patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", fetch),
            self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-output-invalid"),
        ):
            self._run(runner)
        self.assertEqual(1, self.store.puts)

        def omitted_runner(_runtime, _package, _files, **kwargs):
            kwargs["broker_callback"]({"operation": "search", "query": "approved", "pageSize": 2})
            return SimpleNamespace(
                output=self._search_output(None),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        with (
            patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", fetch),
            self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-output-invalid"),
        ):
            self._run(omitted_runner)
        self.assertEqual(2, self.store.puts)

        with patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", fetch):

            def valid_runner(_runtime, _package, _files, **kwargs):
                kwargs["broker_callback"]({"operation": "search", "query": "approved", "pageSize": 2})
                return SimpleNamespace(
                    output=self._search_output("page-2"),
                    token={
                        "appContainer": True,
                        "lessPrivileged": True,
                        "capabilityCount": 0,
                        "allApplicationPackagesDenied": True,
                    },
                    broker_calls=1,
                )

            staged = self._run(valid_runner)
        self.assertEqual("page-2", staged.validated_page.next_cursor)
        self.assertEqual(4, self.store.puts)

    def test_swallowed_broker_failure_cannot_stage_search_page(self):
        self._search()

        async def failed_fetch(_broker, _plan, _call):
            raise PluginBrokerProblem("provider-unavailable")

        def runner(_runtime, _package, _files, **kwargs):
            with suppress(PluginBrokerProblem):
                kwargs["broker_callback"]({"operation": "search", "query": "approved", "pageSize": 2})
            return SimpleNamespace(
                output=self._search_output(None),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        with (
            patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", failed_fetch),
            self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-failed"),
        ):
            self._run(runner)
        self.assertEqual(0, self.store.puts)

    def test_search_second_broker_attempt_is_denied_before_egress(self):
        self._search()
        fetches: list[str] = []

        async def fetch(_broker, _plan, _call):
            fetches.append("egress")
            return SimpleNamespace(body=b'{"records":[],"nextCursor":"page-2"}', redacted=False)

        def runner(_runtime, _package, _files, **kwargs):
            call = {"operation": "search", "query": "approved", "pageSize": 2}
            kwargs["broker_callback"](call)
            with suppress(PluginDispatchProblem):
                kwargs["broker_callback"](call)
            return SimpleNamespace(
                output=self._search_output("page-2"),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        with (
            patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", fetch),
            self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-failed"),
        ):
            self._run(runner)
        self.assertEqual(["egress"], fetches)
        self.assertEqual(1, self.store.puts)

    def test_search_failed_first_broker_attempt_cannot_retry_egress(self):
        self._search()
        fetches: list[str] = []

        async def fetch(_broker, _plan, _call):
            fetches.append("egress")
            raise PluginBrokerProblem("provider-unavailable")

        def runner(_runtime, _package, _files, **kwargs):
            call = {"operation": "search", "query": "approved", "pageSize": 2}
            with suppress(PluginBrokerProblem):
                kwargs["broker_callback"](call)
            with suppress(PluginDispatchProblem):
                kwargs["broker_callback"](call)
            return SimpleNamespace(
                output=self._search_output(None),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        with (
            patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", fetch),
            self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-failed"),
        ):
            self._run(runner)
        self.assertEqual(["egress"], fetches)
        self.assertEqual(0, self.store.puts)

    def test_verified_worker_result_is_encrypted_stage_without_publication(self):
        output = self._valid_output()

        def runner(_runtime, _package, _files, **kwargs):
            self.assertEqual(self.request.invocation_id, kwargs["invocation_id"])
            self.assertEqual(self.input_data, kwargs["input_data"])
            kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"})
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

        with patch(
            "research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", self._lookup_response
        ):
            staged = self._run(runner)
        self.assertEqual(
            (hashlib.sha256(output).hexdigest(), len(output), 1),
            (staged.object_sha256, staged.byte_length, staged.broker_calls),
        )
        self.assertEqual(2, self.store.puts)
        self.assertEqual("exhausted", staged.validated_page.continuation)
        self.assertEqual((), staged.validated_page.records)
        self.assertRegex(staged.retrieved_at, r"^20[0-9]{2}-")

    def test_durable_claim_dispatch_uses_package_pair_without_candidate_token(self):
        def runner(_runtime, _package, _files, **kwargs):
            kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"})
            return SimpleNamespace(
                output=self._valid_output(),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        plan = self.admin.dispatch.plan
        with patch(
            "research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", self._lookup_response
        ):
            staged = asyncio.run(
                self._controller(runner).dispatch_persisted(
                    root="C:/synthetic",
                    project_id=PROJECT,
                    package_sha256=plan.package_sha256,
                    manifest_sha256=plan.manifest_sha256,
                    signature_sha256=plan.signature_sha256,
                    request=self.request,
                    input_data=self.input_data,
                    actor=self.actor,
                )
            )
        self.assertEqual(hashlib.sha256(self._valid_output()).hexdigest(), staged.object_sha256)

    def test_bad_broker_frame_and_revocation_never_stage(self):
        def raw_url(_runtime, _package, _files, **kwargs):
            kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1", "url": "https://evil.test"})

        with self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-failed"):
            self._run(raw_url)
        self.assertIn("plugin-broker-call-invalid", self.admin.denials)
        self.assertEqual(0, self.store.puts)

        def revoked(_runtime, _package, _files, **kwargs):
            kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"})
            self.admin.current = False
            return SimpleNamespace(
                output=self._valid_output(),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        with (
            patch(
                "research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", self._lookup_response
            ),
            self.assertRaisesRegex(PluginDispatchProblem, "plugin-policy-denied"),
        ):
            self._run(revoked)
        self.assertEqual(1, self.store.puts)

    def test_failed_persisted_worker_records_content_free_durable_denial_without_staging(self):
        with tempfile.TemporaryDirectory(prefix="ro-plugin-worker-denial-", dir=REPO / "artifacts/tmp") as temporary:
            state = Path(temporary) / "state"
            state.mkdir()
            database = state / "project.sqlite3"
            configure_protected_database_provider(InMemoryDatabaseKeyProvider())
            initialized = initialize_database(
                database, project_id=PROJECT, project_created_at="2026-10-01T12:00:00.000Z"
            )
            self.assertTrue(initialized.ok, initialized.errors)
            repository = SqlitePluginGrantRepository(database, PROJECT)
            plan = self.admin.dispatch.plan

            def persist_denial(_root, _project, *, plugin_id, invocation_id, reason_code, actor):
                repository.record_denial(
                    plugin_id=plugin_id,
                    invocation_id=invocation_id,
                    package_sha256=plan.package_sha256,
                    reason_code=reason_code,
                    actor=actor,
                )

            def failed_worker(_runtime, _package, _files, **_kwargs):
                raise RuntimeError("synthetic worker did not return an output")

            with (
                patch.object(self.admin, "record_denial_persisted", side_effect=persist_denial),
                self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-failed"),
            ):
                asyncio.run(
                    self._controller(failed_worker).dispatch_persisted(
                        root="C:/synthetic",
                        project_id=PROJECT,
                        package_sha256=plan.package_sha256,
                        manifest_sha256=plan.manifest_sha256,
                        signature_sha256=plan.signature_sha256,
                        request=self.request,
                        input_data=self.input_data,
                        actor=self.actor,
                    )
                )
            self.assertEqual(0, self.store.puts)
            events = SqlitePluginGrantRepository(database, PROJECT).audit_history(plan.plugin_id)
            self.assertEqual(1, len(events))
            self.assertEqual("denied", events[0].event_kind)
            self.assertEqual("plugin-worker-failed", events[0].reason_code)
            self.assertEqual(self.request.invocation_id, events[0].invocation_id)
            self.assertEqual(plan.package_sha256, events[0].package_sha256)
            self.assertNotIn("synthetic worker did not return an output", repr(events))

    def test_same_project_second_job_denied_while_first_worker_runs(self):
        entered, release = threading.Event(), threading.Event()

        def runner(_runtime, _package, _files, **kwargs):
            entered.set()
            release.wait(5)
            kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"})
            return SimpleNamespace(
                output=self._valid_output(),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        controller = self._controller(runner)

        async def concurrent():
            args = dict(
                root="C:/synthetic",
                project_id=PROJECT,
                session_id="a" * 32,
                package_token="b" * 64,
                request=self.request,
                input_data=self.input_data,
                actor=self.actor,
            )
            first = asyncio.create_task(controller.dispatch(**args))
            await asyncio.to_thread(entered.wait, 5)
            try:
                with self.assertRaisesRegex(PluginDispatchProblem, "plugin-project-busy"):
                    await controller.dispatch(**args)
            finally:
                release.set()
            await first

        with patch(
            "research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", self._lookup_response
        ):
            asyncio.run(concurrent())
        self.assertEqual(2, self.store.puts)

    def test_cancel_during_broker_wait_cannot_stage_a_late_response(self):
        entered = threading.Event()

        async def slow_fetch(_broker, _plan, _call):
            entered.set()
            await asyncio.sleep(5)
            return SimpleNamespace(body=b"{}")

        def runner(_runtime, _package, _files, **kwargs):
            kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"})

        async def cancelled_run():
            active = asyncio.create_task(
                self._controller(runner).dispatch(
                    root="C:/synthetic",
                    project_id=PROJECT,
                    session_id="a" * 32,
                    package_token="b" * 64,
                    request=self.request,
                    input_data=self.input_data,
                    actor=self.actor,
                )
            )
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            self.cancelled = True
            with self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-failed"):
                await active

        with patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", slow_fetch):
            asyncio.run(cancelled_run())
        self.assertEqual(0, self.store.puts)
        self.assertIn("plugin-worker-cancelled", self.admin.denials)

    def test_missing_lpac_deny_all_packages_witness_never_stages(self):
        def weak_token(_runtime, _package, _files, **_kwargs):
            return SimpleNamespace(
                output=self._valid_output(),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": False,
                },
                broker_calls=0,
            )

        with self.assertRaisesRegex(PluginDispatchProblem, "plugin-worker-result-invalid"):
            self._run(weak_token)
        self.assertEqual(0, self.store.puts)

    def test_post_stage_fence_does_not_return_cancelled_result(self):
        original_put = self.store.put

        def stage_then_revoke(source, command):
            stored = original_put(source, command)
            if self.store.puts == 2:
                self.admin.current = False
            return stored

        setattr(self.store, "put", stage_then_revoke)  # noqa: B010 - deliberate fault injection

        def runner(_runtime, _package, _files, **kwargs):
            kwargs["broker_callback"]({"operation": "lookup", "identifier": "synthetic-1"})
            return SimpleNamespace(
                output=self._valid_output(),
                token={
                    "appContainer": True,
                    "lessPrivileged": True,
                    "capabilityCount": 0,
                    "allApplicationPackagesDenied": True,
                },
                broker_calls=1,
            )

        with (
            patch(
                "research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker.fetch", self._lookup_response
            ),
            self.assertRaisesRegex(PluginDispatchProblem, "plugin-policy-denied"),
        ):
            self._run(runner)
        self.assertEqual(2, self.store.puts)


if __name__ == "__main__":
    unittest.main()
