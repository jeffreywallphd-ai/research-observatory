"""Actual authenticated Core/native-session/SQLCipher/original read composition."""

import asyncio
import base64
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch

import sqlcipher3.dbapi2 as sqlcipher
from fastapi.testclient import TestClient
from research_observatory_core import object_store, storage
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.document_revision_repository import LocalDocumentRevisionRepository
from research_observatory_core.document_viewer_repository import LocalDocumentViewerRepository
from research_observatory_core.document_viewer_service import DocumentViewerService
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.import_preview_service import ImportPreviewService
from research_observatory_core.ingestion.import_drafts import ImportRights
from research_observatory_core.ingestion.preview_activity import _GuardedSource
from research_observatory_core.ingestion.source_chunks import ChunkedImportSource, put_source_chunk
from research_observatory_core.main import DocumentAttachmentRuntime

from tests.documents import test_document_revision_workflow as workflows


class DocumentViewerApiTests(unittest.TestCase):
    def assert_authentication_owns_writer(self):
        # The stream registry begins after full authentication. During the
        # held authentication frame, test the actual encrypted writer instead.
        # Test-owned key provider only; do not weaken the product connection's
        # PRAGMA authorizer to obtain a diagnostic connection with timeout=0.
        with storage._DATABASE_PROTECTION_LOCK:
            keys = storage._DATABASE_PROTECTION.provider
        material = keys.active_material_for_test(self.f.f.source.project_id)
        with closing(
            sqlcipher.connect(
                self.f.f.fixture.corpus.database.as_uri() + "?mode=rw",
                uri=True,
                timeout=0,
                isolation_level=None,
            )
        ) as database:
            database.execute("PRAGMA key = \"x'" + material.hex() + "'\"")
            self.assertTrue(database.execute("SELECT name FROM sqlite_schema LIMIT 1").fetchone())
            with self.assertRaisesRegex(sqlcipher.OperationalError, "locked"):
                database.execute("BEGIN IMMEDIATE")

    def setUp(self):
        self.f = workflows.DocumentRevisionWorkflowTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        # This fixture's protected source deliberately uses a different key
        # provider from the nested import fixture. Compose a native binding
        # with that exact source adapter, matching production's shared provider
        # rather than relying on an unrelated attachment factory override.
        original = self.f.service.imports
        adapters = original._action(self.f.command.root, lambda binding: binding.adapters)

        def native_adapters(path, project):
            self.assertEqual(self.f.command.root, str(path))
            self.assertEqual(self.f.command.project_id, project)
            return replace(adapters, store=self.f.f.fixture.store)

        self.imports = ImportPreviewService(
            original._projects,
            original._privacy,
            native_adapters,
            local_actor_id=original._actor_id,
            resume_epoch=original._epoch,
            now=original._now,
        )
        self.addCleanup(self.imports.shutdown)
        self.attachments = DocumentAttachmentRuntime(
            self.imports, self.f.service.attachments._corpus, self.f.service.attachments._object_store_factory
        )
        self.viewer = DocumentViewerService(
            self.attachments,
            self.imports,
            repository_factory=lambda *args, **kwargs: LocalDocumentViewerRepository(
                LocalDocumentRevisionRepository(*args, **kwargs)
            ),
        )
        self.addCleanup(self.viewer.shutdown)
        self.client = self.enterContext(
            TestClient(
                create_app(
                    projects=self.f.f.preview.service._projects,
                    document_viewer=self.viewer,
                    capability_digest=capability_token_digest("a" * 64),
                    expected_authority="127.0.0.1:49152",
                ),
                base_url="http://127.0.0.1:49152",
                headers={"Authorization": "Bearer " + "a" * 64},
                client=("127.0.0.1", 50000),
            )
        )
        self.command = {
            "root": self.f.command.root,
            "projectId": self.f.command.project_id,
            "sessionId": self.imports.native_context(self.f.command.root, self.f.command.project_id),
            "selector": {
                "attachmentId": self.f.f.source.attachment_id,
                "documentRevisionId": self.f.f.source.document_revision_id,
            },
        }
        self.range = dict(self.command, requestId=new_uuid_v7(), start=0, end=9)
        self.path = "/native/document-viewer"

    def test_current_native_adapter_reads_without_reinitializing_its_key_and_policy_ports(self):
        with patch.object(self.attachments, "_object_store_factory", side_effect=AssertionError("unexpected-reinit")):
            response = self.client.post(self.path + "/range", json=self.range)
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(b"Synthetic", base64.b64decode(response.json()["bytesBase64"], validate=True))

    def test_native_close_reopen_denies_the_old_session_before_any_source_authentication(self):
        self.assertEqual(200, self.client.post(self.path + "/range", json=self.range).status_code)
        self.imports.detach(self.command["root"])
        projects = self.imports._projects
        projects.close(root=self.command["root"], trace_id="1" * 32)
        projects.open(root=self.command["root"], trace_id="1" * 32)
        current_session = self.imports.native_context(self.command["root"], self.command["projectId"])
        self.assertNotEqual(self.command["sessionId"], current_session)
        with patch.object(object_store, "_pull_frame", wraps=object_store._pull_frame) as authentication:
            response = self.client.post(self.path + "/range", json=dict(self.range, requestId=new_uuid_v7()))
            self.assertEqual(409, response.status_code)
            authentication.assert_not_called()
        self.assertEqual(
            200,
            self.client.post(
                self.path + "/range", json=dict(self.range, sessionId=current_session, requestId=new_uuid_v7())
            ).status_code,
        )

    def test_reused_native_adapter_rechecks_missing_keys_without_quarantining_a_healthy_original(self):
        self.assertEqual(200, self.client.post(self.path + "/range", json=self.range).status_code)
        keys = self.f.f.fixture.keys
        saved = dict(keys.keys)
        try:
            keys.keys.clear()
            response = self.client.post(self.path + "/range", json=dict(self.range, requestId=new_uuid_v7()))
            self.assertEqual(409, response.status_code)
            self.assertNotIn("bytesBase64", response.text)
            self.assertEqual("available", self.f.f.fixture.store.metadata(self.f.f.source.object_sha256).storage_state)
        finally:
            keys.keys.update(saved)
        self.assertEqual(
            200, self.client.post(self.path + "/range", json=dict(self.range, requestId=new_uuid_v7())).status_code
        )

    def test_cancelled_viewer_allows_concurrent_guarded_import_read_and_metadata_writer_to_finish(self):
        rights = ImportRights.model_validate(
            {action: {"value": "permitted", "basis": "researcher-confirmed"} for action in ("store", "inspect")}
        )
        raw = b"Synthetic concurrent bibliography import\n"
        binding = self.imports._action(self.command["root"], lambda selected: selected)
        chunk = self.imports._guard(
            binding,
            lambda: put_source_chunk(binding.adapters.store, raw, rights=rights, created_at=self.f.f.actor.occurred_at),
        )
        source = ChunkedImportSource(binding.adapters.store, (chunk,), authorize=lambda: rights)
        self.addCleanup(source.close)
        imported = _GuardedSource(source, lambda action: self.imports._guard(binding, action))
        entered, release = threading.Event(), threading.Event()
        pull = object_store._pull_frame

        def held_frame(*args, **kwargs):
            value = pull(*args, **kwargs)
            entered.set()
            if not release.wait(3):
                raise RuntimeError("synthetic-concurrent-release-timeout")
            return value

        def metadata_writer():
            def write():
                with closing(
                    storage.open_canonical_database(
                        self.f.f.fixture.corpus.database, expected_project_id=self.command["projectId"]
                    )
                ) as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    cursor = connection.execute(
                        "UPDATE object_records SET verified_at=verified_at WHERE project_id=? AND object_sha256=?",
                        (self.command["projectId"], self.f.f.source.object_sha256),
                    )
                    self.assertEqual(1, cursor.rowcount)
                    connection.execute("COMMIT")
                    return True

            return self.imports._guard(binding, write)

        with patch.object(object_store, "_pull_frame", held_frame), ThreadPoolExecutor(max_workers=4) as executor:
            viewer = executor.submit(self.client.post, self.path + "/range", json=self.range)
            try:
                self.assertTrue(entered.wait(2))
                importing = executor.submit(imported.read, len(raw))
                writing = executor.submit(metadata_writer)
                deadline = time.monotonic() + 1
                while self.imports._projects._mutex.waiting_count() < 2:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.005)
                command = {key: self.command[key] for key in ("root", "projectId", "sessionId")}
                cancelling = executor.submit(
                    self.client.post, self.path + "/cancel", json=dict(command, requestId=self.range["requestId"])
                )
                time.sleep(0.1)
                self.assertFalse(cancelling.done())
                self.assert_authentication_owns_writer()
            finally:
                release.set()
            self.assertEqual(409, viewer.result(timeout=3).status_code)
            self.assertTrue(cancelling.result(timeout=3).json()["drained"])
            self.assertEqual(raw, importing.result(timeout=3))
            self.assertTrue(writing.result(timeout=3))
        self.assertFalse(object_store._READERS.in_use(self.command["projectId"], self.f.f.source.object_sha256))
        self.assertEqual(
            200, self.client.post(self.path + "/range", json=dict(self.range, requestId=new_uuid_v7())).status_code
        )

    def test_current_original_metadata_and_exact_range_cross_the_authenticated_boundary(self):
        self.f.f.permit(derive="denied")
        metadata = self.client.post(self.path + "/source", json=self.command)
        self.assertEqual(200, metadata.status_code, metadata.text)
        self.assertEqual(self.f.f.source.document_revision_id, metadata.json()["source"]["documentRevisionId"])
        response = self.client.post(self.path + "/range", json=self.range)
        self.assertEqual(200, response.status_code, response.text)
        value = response.json()
        self.assertEqual(self.range["requestId"], value["requestId"])
        self.assertEqual((0, 9), (value["start"], value["end"]))
        self.assertEqual(b"Synthetic", base64.b64decode(value["bytesBase64"], validate=True))
        self.assertNotIn(self.command["root"], response.text)
        self.assertFalse(any(path.startswith(self.path) for path in self.client.get("/openapi.json").json()["paths"]))

    def test_foreign_project_stale_session_and_source_substitution_deny(self):
        for command in (
            dict(self.range, projectId=new_uuid_v7()),
            dict(self.range, sessionId="c" * 32),
            dict(self.range, selector=dict(self.command["selector"], documentRevisionId=new_uuid_v7())),
        ):
            with self.subTest(command=command):
                response = self.client.post(self.path + "/range", json=command)
                self.assertEqual(409, response.status_code)
                self.assertNotIn("Synthetic", response.text)
                self.assertNotIn(self.command["root"], response.text)

    def test_exact_accepted_text_crosses_private_transport_without_anchor_creation(self):
        repository = self.f.fixture.repository
        result = self.f.fixture.parse(raw="Synthetic inert <script>text</script>")
        accepted = repository.accept(self.f.fixture.command(result))
        node = next(item for item in accepted.structure.nodes if item.text is not None)
        command = dict(
            self.command,
            selector=dict(self.command["selector"], normalizedRevisionId=accepted.revision_id),
            nodeId=node.node_id,
            offset=0,
        )
        response = self.client.post(self.path + "/text", json=command)
        self.assertEqual(200, response.status_code, response.text)
        self.assertIn("<script>", response.json()["text"])
        self.assertEqual(accepted.revision_id, response.json()["metadata"]["normalizedRevisionId"])
        self.assertLessEqual(len(response.json()["text"]), 4096)
        self.assertEqual((), repository.source_anchors().list(accepted.revision_id))
        self.f.f.permit(derive="denied")
        self.assertEqual(409, self.client.post(self.path + "/text", json=command).status_code)
        self.assertEqual(200, self.client.post(self.path + "/range", json=self.range).status_code)

    def test_viewer_outline_and_text_use_admission_while_normal_revision_read_is_unchanged(self):
        repository = self.f.fixture.repository
        accepted = repository.accept(self.f.fixture.command(self.f.fixture.parse()))
        selected = dict(
            self.command, selector=dict(self.command["selector"], normalizedRevisionId=accepted.revision_id)
        )
        outline = self.client.post(self.path + "/outline", json=dict(selected, afterNodeId=None))
        self.assertEqual(200, outline.status_code, outline.text)
        self.assertEqual(accepted.revision_id, outline.json()["revisionId"])
        node = next(item for item in accepted.structure.nodes if item.text is not None)
        text = dict(selected, nodeId=node.node_id, offset=0)
        from research_observatory_core.document_viewer_allocations import ViewerArtifactReads

        with patch.object(ViewerArtifactReads, "cost_multiplier", 2**40):
            for path, command in (("/outline", dict(selected, afterNodeId=None)), ("/text", text)):
                response = self.client.post(self.path + path, json=command)
                self.assertEqual(413, response.status_code, response.text)
                self.assertEqual("RO-CORE-DOCUMENT-VIEWER-RESOURCE-LIMIT", response.json()["code"])
            self.assertEqual(accepted.revision_id, repository.read(accepted.revision_id).revision_id)
            self.assertEqual(200, self.client.post(self.path + "/range", json=self.range).status_code)
        self.assertEqual(200, self.client.post(self.path + "/text", json=text).status_code)

    def test_viewer_outline_denies_substituted_original_or_derive_permission(self):
        repository = self.f.fixture.repository
        accepted = repository.accept(self.f.fixture.command(self.f.fixture.parse()))
        selected = dict(
            self.command, selector=dict(self.command["selector"], normalizedRevisionId=accepted.revision_id)
        )
        wrong = dict(selected, selector=dict(selected["selector"], documentRevisionId=new_uuid_v7()))
        self.assertEqual(409, self.client.post(self.path + "/outline", json=wrong).status_code)
        self.f.f.permit(derive="denied")
        self.assertEqual(409, self.client.post(self.path + "/outline", json=selected).status_code)
        self.assertEqual(200, self.client.post(self.path + "/range", json=self.range).status_code)

    def test_rights_revoked_between_selection_and_physical_admission_deny_without_reading(self):
        admitted_read = self.viewer.ranges.read

        def revoked(*args, **kwargs):
            self.f.f.fixture.publish_right(
                self.f.f.candidate, value="denied", predecessor=self.f.f.policy.revision_id, inspect=True
            )
            return admitted_read(*args, **kwargs)

        with (
            patch.object(self.viewer.ranges, "read", revoked),
            patch.object(object_store, "_pull_frame", wraps=object_store._pull_frame) as authentication,
        ):
            response = self.client.post(self.path + "/range", json=self.range)
            self.assertEqual(409, response.status_code)
            self.assertNotIn("bytesBase64", response.text)
            authentication.assert_not_called()

    def test_rights_revoked_after_owned_physical_close_deny_private_api_delivery(self):
        store_type = type(self.f.f.fixture.store)
        read = store_type._read_inspected_document_range

        def revoke_after_close(store, *args, **kwargs):
            result = read(store, *args, **kwargs)
            self.assertFalse(object_store._READERS.in_use(self.f.f.source.project_id, self.f.f.source.object_sha256))
            self.f.f.fixture.publish_right(
                self.f.f.candidate, value="denied", predecessor=self.f.f.policy.revision_id, inspect=True
            )
            return result

        with patch.object(store_type, "_read_inspected_document_range", revoke_after_close):
            response = self.client.post(self.path + "/range", json=self.range)
        self.assertEqual(409, response.status_code)
        self.assertNotIn("bytesBase64", response.text)

    def test_cancel_route_stops_the_owned_authentication_and_releases_its_actual_writer(self):
        entered, release = threading.Event(), threading.Event()
        pull = object_store._pull_frame
        replies, failures = [], []
        before = self.f.f.fixture.store.metadata(self.f.f.source.object_sha256)

        def held_frame(*args, **kwargs):
            result = pull(*args, **kwargs)
            entered.set()
            if not release.wait(2):
                raise RuntimeError("synthetic-release-timeout")
            return result

        def request():
            try:
                replies.append(self.client.post(self.path + "/range", json=self.range))
            except Exception as error:
                failures.append(error)

        with patch.object(object_store, "_pull_frame", held_frame):
            thread = threading.Thread(target=request)
            thread.start()
            try:
                self.assertTrue(entered.wait(2), "owned source authentication was not reached")
                cancel_command = {key: self.command[key] for key in ("root", "projectId", "sessionId")}
                with ThreadPoolExecutor(max_workers=1) as executor:
                    cancellation = executor.submit(
                        self.client.post,
                        self.path + "/cancel",
                        json=dict(cancel_command, requestId=self.range["requestId"]),
                    )
                    time.sleep(0.15)
                    self.assertFalse(cancellation.done(), "cancel ack must await the physical encrypted reader")
                    self.assert_authentication_owns_writer()
                    release.set()
                    cancelled = cancellation.result(timeout=2)
                self.assertEqual(200, cancelled.status_code, cancelled.text)
                self.assertTrue(cancelled.json()["drained"])
                self.assertEqual(self.range["requestId"], cancelled.json()["requestId"])
            finally:
                release.set()
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failures)
        self.assertEqual([409], [response.status_code for response in replies])
        self.assertFalse(object_store._READERS.in_use(self.f.f.source.project_id, self.f.f.source.object_sha256))
        current = self.f.f.fixture.store.metadata(self.f.f.source.object_sha256)
        self.assertEqual("available", current.storage_state)
        self.assertEqual(before.verified_at, current.verified_at)
        self.assertFalse(self.viewer._requests)
        self.assertEqual(
            200, self.client.post(self.path + "/range", json=dict(self.range, requestId=new_uuid_v7())).status_code
        )

    def test_cancel_ack_denies_at_deadline_while_real_authentication_is_still_held(self):
        entered, release = threading.Event(), threading.Event()
        pull = object_store._pull_frame
        replies = []

        def held_frame(*args, **kwargs):
            result = pull(*args, **kwargs)
            entered.set()
            if not release.wait(4):
                raise RuntimeError("synthetic-release-timeout")
            return result

        with patch.object(object_store, "_pull_frame", held_frame):
            thread = threading.Thread(
                target=lambda: replies.append(self.client.post(self.path + "/range", json=self.range))
            )
            thread.start()
            try:
                self.assertTrue(entered.wait(2))
                command = {key: self.command[key] for key in ("root", "projectId", "sessionId")}
                started = time.monotonic()
                cancelled = self.client.post(
                    self.path + "/cancel", json=dict(command, requestId=self.range["requestId"])
                )
                self.assertEqual(200, cancelled.status_code, cancelled.text)
                self.assertFalse(cancelled.json()["drained"])
                self.assertLess(time.monotonic() - started, 1.3)
                self.assertTrue(thread.is_alive())
                self.assert_authentication_owns_writer()
            finally:
                release.set()
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual([409], [response.status_code for response in replies])
        self.assertFalse(object_store._READERS.in_use(self.f.f.source.project_id, self.f.f.source.object_sha256))
        self.assertTrue(
            self.client.post(self.path + "/cancel", json=dict(command, requestId=self.range["requestId"])).json()[
                "drained"
            ]
        )

    def test_early_cancel_waits_for_late_registration_and_never_admits_a_source_read(self):
        command = {key: self.command[key] for key in ("root", "projectId", "sessionId")}
        with ThreadPoolExecutor(max_workers=1) as executor:
            cancelled = executor.submit(
                self.client.post, self.path + "/cancel", json=dict(command, requestId=self.range["requestId"])
            )
            time.sleep(0.1)
            self.assertFalse(cancelled.done(), "absent registration cannot acknowledge physical drain")
            response = self.client.post(self.path + "/range", json=self.range)
            self.assertEqual(409, response.status_code)
            ack = cancelled.result(timeout=2)
        self.assertTrue(ack.json()["drained"])
        self.assertFalse(object_store._READERS.in_use(self.f.f.source.project_id, self.f.f.source.object_sha256))

    def test_cancelled_exact_follower_hands_off_real_reader_without_stopping_live_member(self):
        entered, release = threading.Event(), threading.Event()
        barrier = threading.Barrier(2)
        pull, read_range = object_store._pull_frame, self.viewer.ranges.read
        second = dict(self.range, requestId=new_uuid_v7())

        def admitted_after_both_authorizations(*args, **kwargs):
            barrier.wait(timeout=2)
            return read_range(*args, **kwargs)

        def held_frame(*args, **kwargs):
            result = pull(*args, **kwargs)
            entered.set()
            if not release.wait(3):
                raise RuntimeError("synthetic-release-timeout")
            return result

        with (
            patch.object(self.viewer.ranges, "read", admitted_after_both_authorizations),
            patch.object(object_store, "_pull_frame", held_frame),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first_reply = executor.submit(self.client.post, self.path + "/range", json=self.range)
            second_reply = executor.submit(self.client.post, self.path + "/range", json=second)
            try:
                self.assertTrue(entered.wait(2))
                deadline = time.monotonic() + 1
                while self.viewer.ranges.pending_count(self.command["projectId"]) != 2:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.005)
                command = {key: self.command[key] for key in ("root", "projectId", "sessionId")}
                foreign = dict(command, root=command["root"] + "-foreign", requestId=self.range["requestId"])
                self.assertFalse(self.client.post(self.path + "/cancel", json=foreign).json()["drained"])
                ack = self.client.post(self.path + "/cancel", json=dict(command, requestId=self.range["requestId"]))
                self.assertTrue(ack.json()["drained"], ack.text)
                self.assertEqual(409, first_reply.result(timeout=1).status_code)
                self.assertFalse(second_reply.done())
                self.assert_authentication_owns_writer()
            finally:
                release.set()
            follower = second_reply.result(timeout=2)
        self.assertEqual(200, follower.status_code, follower.text)
        self.assertEqual(b"Synthetic", base64.b64decode(follower.json()["bytesBase64"], validate=True))
        self.assertFalse(object_store._READERS.in_use(self.f.f.source.project_id, self.f.f.source.object_sha256))

    def test_real_asgi_disconnect_reaches_cooperative_reader_and_denies_delivery(self):
        entered, observed_stop = threading.Event(), threading.Event()
        pull = object_store._pull_frame
        messages = []

        def wait_for_transport_stop(*args, **kwargs):
            value = pull(*args, **kwargs)
            entered.set()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with self.viewer._mutex:
                    stopped = any(request.transport_stop() for request in self.viewer._requests.values())
                if stopped:
                    observed_stop.set()
                    return value
                time.sleep(0.005)
            raise RuntimeError("synthetic-disconnect-timeout")

        async def disconnected_request():
            body = json.dumps(self.range).encode()
            initial = True

            async def receive():
                nonlocal initial
                if initial:
                    initial = False
                    return {"type": "http.request", "body": body, "more_body": False}
                if entered.is_set():
                    return {"type": "http.disconnect"}
                await asyncio.sleep(0.01)
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            path = self.path + "/range"
            await self.client.app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0", "spec_version": "2.4"},
                    "method": "POST",
                    "scheme": "http",
                    "path": path,
                    "raw_path": path.encode(),
                    "root_path": "",
                    "query_string": b"",
                    "http_version": "1.1",
                    "client": ("127.0.0.1", 50000),
                    "server": ("127.0.0.1", 49152),
                    "headers": [
                        (b"host", b"127.0.0.1:49152"),
                        (b"content-type", b"application/json"),
                        (b"authorization", b"Bearer " + b"a" * 64),
                    ],
                },
                receive,
                send,
            )

        with patch.object(object_store, "_pull_frame", wait_for_transport_stop):
            asyncio.run(disconnected_request())
        self.assertTrue(observed_stop.is_set())
        self.assertFalse(object_store._READERS.in_use(self.f.f.source.project_id, self.f.f.source.object_sha256))
        self.assertFalse(self.viewer._requests)
        self.assertFalse(any(b"bytesBase64" in message.get("body", b"") for message in messages))

    def test_renderer_origin_missing_native_auth_and_unbounded_commands_deny(self):
        self.assertEqual(
            401, self.client.post(self.path + "/range", json=self.range, headers={"Authorization": ""}).status_code
        )
        self.assertEqual(
            403,
            self.client.post(
                self.path + "/range", json=self.range, headers={"Origin": "tauri://localhost"}
            ).status_code,
        )
        for command in (
            dict(self.range, start=True),
            dict(self.range, end=1.5),
            dict(self.range, end=1024 * 1024 + 1),
            dict(self.range, end=0),
            dict(self.range, selector=dict(self.command["selector"], path="synthetic-untrusted-path")),
            dict(self.range, actorId=new_uuid_v7()),
        ):
            with self.subTest(command=command):
                self.assertEqual(422, self.client.post(self.path + "/range", json=command).status_code)
        self.assertEqual(
            413,
            self.client.post(
                self.path + "/range", content=b" " * 8193, headers={"Content-Type": "application/json"}
            ).status_code,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
