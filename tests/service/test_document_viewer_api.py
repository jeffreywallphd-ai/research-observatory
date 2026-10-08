"""Actual authenticated Core/native-session/SQLCipher/original read composition."""

import asyncio
import base64
import json
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from research_observatory_core import object_store
from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.document_viewer_service import DocumentViewerService
from research_observatory_core.domain_contracts import new_uuid_v7

from tests.documents import test_document_revision_workflow as workflows


class DocumentViewerApiTests(unittest.TestCase):
    def setUp(self):
        self.f = workflows.DocumentRevisionWorkflowTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.viewer = DocumentViewerService(self.f.service.attachments, self.f.service.imports)
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
            "sessionId": self.f.command.session_id,
            "selector": {
                "attachmentId": self.f.f.source.attachment_id,
                "documentRevisionId": self.f.f.source.document_revision_id,
            },
        }
        self.range = dict(self.command, requestId=new_uuid_v7(), start=0, end=9)
        self.path = "/native/document-viewer"

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
                cancelled = self.client.post(
                    self.path + "/cancel", json=dict(cancel_command, requestId=self.range["requestId"])
                )
                self.assertEqual(200, cancelled.status_code, cancelled.text)
                self.assertTrue(cancelled.json()["cancelled"])
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
