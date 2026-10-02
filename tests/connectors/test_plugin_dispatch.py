"""Core dispatch refuses stale authority and stages only verified bounded output."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

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

    def put(self, source, command):
        self.puts += 1
        body = source.read()
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

    def test_verified_worker_result_is_encrypted_stage_without_publication(self):
        output = self._valid_output()

        def runner(_runtime, _package, _files, **kwargs):
            self.assertEqual(self.request.invocation_id, kwargs["invocation_id"])
            self.assertEqual(self.input_data, kwargs["input_data"])
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

        staged = self._run(runner)
        self.assertEqual(
            (hashlib.sha256(output).hexdigest(), len(output), 0),
            (staged.object_sha256, staged.byte_length, staged.broker_calls),
        )
        self.assertEqual(1, self.store.puts)
        self.assertEqual("exhausted", staged.validated_page.continuation)
        self.assertEqual((), staged.validated_page.records)
        self.assertRegex(staged.retrieved_at, r"^20[0-9]{2}-")

    def test_durable_claim_dispatch_uses_package_pair_without_candidate_token(self):
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

        plan = self.admin.dispatch.plan
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

        def revoked(_runtime, _package, _files, **_kwargs):
            self.admin.current = False
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

        with self.assertRaisesRegex(PluginDispatchProblem, "plugin-policy-denied"):
            self._run(revoked)
        self.assertEqual(0, self.store.puts)

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

        def runner(_runtime, _package, _files, **_kwargs):
            entered.set()
            release.wait(5)
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

        asyncio.run(concurrent())
        self.assertEqual(1, self.store.puts)

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
            self.admin.current = False
            return stored

        setattr(self.store, "put", stage_then_revoke)  # noqa: B010 - deliberate fault injection

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

        with self.assertRaisesRegex(PluginDispatchProblem, "plugin-policy-denied"):
            self._run(runner)
        self.assertEqual(1, self.store.puts)


if __name__ == "__main__":
    unittest.main()
