"""Native-only attachment intake frames stream into Core without a plaintext file."""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import sys
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO
from unittest.mock import patch

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.document_attachment_api import DocumentStageCommand
from research_observatory_core.document_attachment_repository import (
    AttachmentCandidate,
    AttachmentProblem,
    LocalDocumentAttachmentService,
)
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.main import DocumentAttachmentRuntime
from research_observatory_core.ports.corpus import CorpusActor
from research_observatory_core.ports.import_previews import PreviewProblem
from research_observatory_core.ports.object_store import ObjectStagingCancelled
from research_observatory_core.reconciliation.contracts import SourceAddress
from research_observatory_core.rights_policy import RightsSubject
from research_observatory_core.storage import open_canonical_database

from tests.documents import test_local_attachment as attachment_fixtures


class _AttachmentRuntime:
    def __init__(self) -> None:
        self.project_id = new_uuid_v7()
        self.source_id = new_uuid_v7()
        self.work_id = new_uuid_v7()
        self.work_revision_id = new_uuid_v7()
        self.version_id = new_uuid_v7()
        self.version_revision_id = new_uuid_v7()
        self.candidate_id = new_uuid_v7()
        self.session_id = "b" * 32
        self.received: bytes | None = None
        self.stage_calls = 0
        self.wait_for_cancel = False
        self.upload_complete = threading.Event()
        self.cancel_observed = threading.Event()
        self.candidate = AttachmentCandidate(
            candidate_id=self.candidate_id,
            project_id=self.project_id,
            source_assertion_revision_id=self.source_id,
            work_id=self.work_id,
            work_revision_id=self.work_revision_id,
            version_id=self.version_id,
            version_revision_id=self.version_revision_id,
            object_sha256="0" * 64,
            byte_length=1,
            format="plain-text",
            media_type="text/plain",
            source_name="synthetic.txt",
            confirmation_required=True,
            candidate_sha256="c" * 64,
            rights_subject=RightsSubject(
                project_id=self.project_id,
                source_assertion_revision_id=self.source_id,
                address=SourceAddress(
                    kind="import-member",
                    context_id=new_uuid_v7(),
                    revision_id=new_uuid_v7(),
                    ordinal=1,
                    record_key="a" * 64,
                ),
                copy_id=self.candidate_id,
                copy_location="local-project-object",
                resource_class="full-text",
            ),
        )

    def context(self, root: str, project_id: str) -> str:
        if root != "C:/synthetic-project" or project_id != self.project_id:
            raise AttachmentProblem("attachment-authority-changed")
        return self.session_id

    def stage(self, command: DocumentStageCommand, source: BinaryIO, *, trace_id: str, cancellation_requested: object):
        self.stage_calls += 1
        assert command.session_id == self.session_id
        assert command.project_id == self.project_id
        assert len(trace_id) == 32
        chunks: list[bytes] = []
        while chunk := source.read(8192):
            assert len(chunk) <= 8192
            chunks.append(chunk)
        self.received = b"".join(chunks)
        self.upload_complete.set()
        if self.wait_for_cancel:
            for _ in range(200):
                if cancellation_requested():
                    self.cancel_observed.set()
                    raise ObjectStagingCancelled()
                time.sleep(0.01)
            raise AssertionError("disconnect was not delivered during inspection")
        return replace(
            self.candidate,
            object_sha256=hashlib.sha256(self.received).hexdigest(),
            byte_length=len(self.received),
        )

    def load_candidate(self, root: str, project_id: str, session_id: str, candidate_id: str, *, trace_id: str):
        if (root, project_id, session_id, candidate_id) != (
            "C:/synthetic-project",
            self.project_id,
            self.session_id,
            self.candidate_id,
        ):
            raise AttachmentProblem("attachment-candidate-unavailable")
        return self.candidate

    def cancel(self, root: str, project_id: str, session_id: str, candidate_id: str, *, trace_id: str) -> None:
        self.load_candidate(root, project_id, session_id, candidate_id, trace_id=trace_id)


class DocumentAttachmentApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = _AttachmentRuntime()
        app = create_app(
            attachments=self.runtime,
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        self.client = self.enterContext(
            TestClient(
                app,
                base_url="http://127.0.0.1:49152",
                headers={"Authorization": "Bearer " + "a" * 64},
                client=("127.0.0.1", 50000),
            )
        )

    def _header(self, length: int) -> dict[str, object]:
        return {
            "root": "C:/synthetic-project",
            "projectId": self.runtime.project_id,
            "sessionId": self.runtime.session_id,
            "sourceName": "synthetic.txt",
            "declaredMediaType": "text/plain",
            "sourceAssertionRevisionId": self.runtime.source_id,
            "workId": self.runtime.work_id,
            "workRevisionId": self.runtime.work_revision_id,
            "versionId": self.runtime.version_id,
            "versionRevisionId": self.runtime.version_revision_id,
            "byteLength": length,
        }

    @staticmethod
    def _frame(header: dict[str, object], body: bytes) -> bytes:
        encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
        return len(encoded).to_bytes(4, "big") + encoded + body

    def _stage(self, frame: bytes):
        return self.client.post(
            "/native/document-attachments/stage", content=frame, headers={"Content-Type": "application/octet-stream"}
        )

    def test_native_context_and_streamed_stage_return_exact_candidate_without_path(self) -> None:
        context = self.client.post(
            "/native/document-attachments/context",
            json={"root": "C:/synthetic-project", "projectId": self.runtime.project_id},
        )
        self.assertEqual(200, context.status_code)
        self.assertEqual(self.runtime.session_id, context.json()["sessionId"])
        data = b"Synthetic document line.\n" * 12_000
        result = self._stage(self._frame(self._header(len(data)), data))
        self.assertEqual(200, result.status_code, result.text)
        self.assertEqual(data, self.runtime.received)
        self.assertEqual(hashlib.sha256(data).hexdigest(), result.json()["objectSha256"])
        self.assertEqual(len(data), result.json()["byteLength"])
        self.assertEqual(self.runtime.candidate_id, result.json()["candidateId"])
        self.assertEqual("no-store", result.headers["cache-control"])
        self.assertNotIn("C:/synthetic-project", result.text)

    def test_stage_rejects_oversize_claim_short_body_extra_body_and_duplicate_header(self) -> None:
        data = b"synthetic"
        oversized = self._stage(self._frame(self._header(128 * 1024 * 1024 + 1), b""))
        self.assertEqual(413, oversized.status_code)
        self.assertEqual("RO-CORE-DOCUMENT-OVERSIZE", oversized.json()["code"])
        short = self._stage(self._frame(self._header(len(data) + 1), data))
        self.assertEqual(422, short.status_code)
        extra = self._stage(self._frame(self._header(len(data)), data + b"x"))
        self.assertEqual(422, extra.status_code)
        encoded = json.dumps(self._header(len(data)), separators=(",", ":"))
        duplicate = encoded[:-1] + ',"sourceName":"other.txt"}'
        repeated = self._stage(len(duplicate).to_bytes(4, "big") + duplicate.encode() + data)
        self.assertEqual(422, repeated.status_code)
        self.assertEqual(0, self.runtime.stage_calls)

    def test_private_stage_requires_core_capability_and_hides_invalid_input(self) -> None:
        data = b"Synthetic input"
        private_path = r"C:\private-research\secret.txt"
        frame = self._frame({**self._header(len(data)), "sourceName": private_path}, data)
        invalid = self._stage(frame)
        self.assertEqual(422, invalid.status_code)
        self.assertNotIn(private_path, invalid.text)
        self.assertNotIn(data.decode(), invalid.text)
        denied = self.client.post(
            "/native/document-attachments/stage",
            content=self._frame(self._header(len(data)), data),
            headers={"Authorization": "", "Content-Type": "application/octet-stream"},
        )
        self.assertEqual(401, denied.status_code)
        self.assertEqual(0, self.runtime.stage_calls)
        self.assertNotIn("/native/document-attachments/stage", self.client.get("/openapi.json").json()["paths"])

    def test_disconnect_after_upload_cancels_delayed_inspector(self) -> None:
        self.runtime.wait_for_cancel = True
        data = b"Synthetic delayed document\n" * 16
        body = self._frame(self._header(len(data)), data)
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "method": "POST",
            "path": "/native/document-attachments/stage",
            "raw_path": b"/native/document-attachments/stage",
            "query_string": b"",
            "scheme": "http",
            "server": ("127.0.0.1", 49152),
            "client": ("127.0.0.1", 50000),
            "headers": [
                (b"host", b"127.0.0.1:49152"),
                (b"authorization", b"Bearer " + b"a" * 64),
                (b"content-type", b"application/octet-stream"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
        sent: list[dict[str, object]] = []
        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.to_thread(self.runtime.upload_complete.wait, 2)
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        asyncio.run(self.client.app(scope, receive, send))
        self.assertTrue(self.runtime.upload_complete.is_set())
        self.assertTrue(self.runtime.cancel_observed.is_set())
        self.assertEqual(1, self.runtime.stage_calls)
        self.assertEqual(409, next(message["status"] for message in sent if message["type"] == "http.response.start"))

    def test_delayed_inspection_releases_project_lock_for_protected_read_and_close(self) -> None:
        lock = threading.RLock()
        selected_session = self.runtime.session_id
        entered = threading.Event()
        release = threading.Event()
        read_finished = threading.Event()
        errors: list[BaseException] = []
        actor = CorpusActor(
            actor_id=new_uuid_v7(),
            trace_id="a" * 32,
            occurred_at="2026-10-02T00:00:00.000Z",
            intent_revision_id=new_uuid_v7(),
            intent_sha256="c" * 64,
            policy_sha256="d" * 64,
        )

        class Imports:
            def native_context(self, root, project_id):
                with lock:
                    if root != "C:/synthetic-project" or project_id != self_project:
                        raise PreviewProblem("preview-project-session-changed")
                    return selected_session

            def in_native_session(self, root, project_id, session_id, action):
                with lock:
                    if self.native_context(root, project_id) != session_id:
                        raise PreviewProblem("preview-project-session-changed")
                    return action()

        class Corpus:
            def _with_authority(self, root, trace_id, action):
                with lock:
                    return action(None, actor, actor.intent_revision_id, Path(root), self_project)

            def protected_read(self):
                with lock:
                    read_finished.set()

        class SlowService:
            def stage(self, _source, *, cancellation_requested, publication_guard, **_kwargs):
                entered.set()
                if not release.wait(3):
                    raise AssertionError("inspection was not released")
                if cancellation_requested():
                    raise ObjectStagingCancelled()
                return publication_guard(lambda: self_candidate)

        self_project = self.runtime.project_id
        self_candidate = self.runtime.candidate
        imports, corpus = Imports(), Corpus()
        runtime = DocumentAttachmentRuntime(imports, corpus, lambda _path, _identity: object())
        command = DocumentStageCommand.model_validate(self._header(1))

        def inspect():
            try:
                runtime.stage(command, io.BytesIO(b"x"), trace_id="b" * 32, cancellation_requested=lambda: False)
            except BaseException as error:
                errors.append(error)

        with patch(
            "research_observatory_core.main.LocalDocumentAttachmentService",
            return_value=SlowService(),
        ):
            worker = threading.Thread(target=inspect)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                reader = threading.Thread(target=corpus.protected_read)
                reader.start()
                self.assertTrue(read_finished.wait(1), "LPAC inspection retained the project lifecycle lock")
                reader.join(2)
                with lock:
                    selected_session = "e" * 32
            finally:
                release.set()
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], ObjectStagingCancelled)

    def test_candidate_and_cancel_are_native_session_scoped(self) -> None:
        context = {
            "root": "C:/synthetic-project",
            "projectId": self.runtime.project_id,
            "sessionId": self.runtime.session_id,
            "candidateId": self.runtime.candidate_id,
        }
        candidate = self.client.post("/native/document-attachments/candidate", json=context)
        self.assertEqual(200, candidate.status_code, candidate.text)
        self.assertEqual(self.runtime.candidate_id, candidate.json()["candidateId"])
        self.assertEqual(204, self.client.post("/native/document-attachments/cancel", json=context).status_code)
        self.assertEqual(
            403,
            self.client.post(
                "/native/document-attachments/context",
                json={"root": context["root"], "projectId": new_uuid_v7()},
            ).status_code,
        )


class DocumentAttachmentRealPortTests(unittest.TestCase):
    def test_stream_to_encrypted_candidate_requires_current_version_confirmation_and_rights(self) -> None:
        fixture = attachment_fixtures.LocalAttachmentServiceTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        session = "d" * 32
        actor = fixture.corpus.actor

        class Imports:
            def native_context(self, root, project_id):
                if (root, project_id) != (str(fixture.project_root), fixture.corpus.project):
                    raise PreviewProblem("preview-project-session-changed")
                return session

            def in_native_session(self, root, project_id, session_id, action):
                if self.native_context(root, project_id) != session_id:
                    raise PreviewProblem("preview-project-session-changed")
                return action()

        class Corpus:
            def _with_authority(self, root, trace_id, action):
                if root != str(fixture.project_root):
                    raise AttachmentProblem("attachment-authority-changed")
                return action(None, actor, actor.intent_revision_id, fixture.project_root, fixture.corpus.project)

        runtime = DocumentAttachmentRuntime(Imports(), Corpus(), lambda _path, _identity: fixture.store)
        app = create_app(
            attachments=runtime,
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        client = self.enterContext(
            TestClient(
                app,
                base_url="http://127.0.0.1:49152",
                headers={"Authorization": "Bearer " + "a" * 64},
                client=("127.0.0.1", 50000),
            )
        )
        data = b"Synthetic plain text full text\n"
        header = {
            "root": str(fixture.project_root),
            "projectId": fixture.corpus.project,
            "sessionId": session,
            "sourceName": "paper.txt",
            "declaredMediaType": "text/plain",
            "sourceAssertionRevisionId": fixture._assertion_id(),
            "workId": fixture.corpus.work_id,
            "workRevisionId": fixture.work_revision_id,
            "versionId": fixture.version.version_id,
            "versionRevisionId": fixture.version.revision_id,
            "byteLength": len(data),
        }

        def stage(values):
            frame = DocumentAttachmentApiTests._frame(values, data)
            return client.post(
                "/native/document-attachments/stage",
                content=frame,
                headers={"Content-Type": "application/octet-stream"},
            )

        with patch(
            "research_observatory_core.main.LocalDocumentAttachmentService",
            side_effect=lambda database, project_id, store: LocalDocumentAttachmentService(
                database, project_id, store, inspector=fixture.service._inspector
            ),
        ):
            stale = stage({**header, "versionRevisionId": new_uuid_v7()})
            self.assertEqual(409, stale.status_code, stale.text)
            with open_canonical_database(fixture.corpus.database, expected_project_id=fixture.corpus.project) as db:
                self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_candidates").fetchone()[0])
            attached = stage(header)
            self.assertEqual(200, attached.status_code, attached.text)
            candidate = attached.json()
            self.assertEqual(hashlib.sha256(data).hexdigest(), candidate["objectSha256"])
            self.assertEqual(header["versionRevisionId"], candidate["versionRevisionId"])
            address = {
                "root": header["root"],
                "projectId": header["projectId"],
                "sessionId": session,
                "candidateId": candidate["candidateId"],
            }
            denied = client.post(
                "/native/document-attachments/commit",
                json={**address, "confirmationSha256": candidate["candidateSha256"], "commandId": new_uuid_v7()},
            )
            self.assertEqual(403, denied.status_code, denied.text)
            current = fixture.service.load_candidate(candidate["candidateId"], actor=actor)
            fixture.publish_right(current)
            wrong_confirmation = client.post(
                "/native/document-attachments/commit",
                json={**address, "confirmationSha256": "0" * 64, "commandId": new_uuid_v7()},
            )
            self.assertEqual(409, wrong_confirmation.status_code)
            committed = client.post(
                "/native/document-attachments/commit",
                json={**address, "confirmationSha256": candidate["candidateSha256"], "commandId": new_uuid_v7()},
            )
            self.assertEqual(200, committed.status_code, committed.text)
            self.assertEqual(header["versionRevisionId"], committed.json()["versionRevisionId"])
            self.assertEqual(
                200, client.post("/native/document-attachments/candidate", json=address).status_code
            )
            with open_canonical_database(fixture.corpus.database, expected_project_id=fixture.corpus.project) as db:
                self.assertEqual(1, db.execute("SELECT COUNT(*) FROM document_attachment_assertions").fetchone()[0])

    @unittest.skipUnless(os.name == "nt", "Windows signed LPAC integration")
    def test_native_route_to_encrypted_stage_and_signed_lpac_worker(self) -> None:
        build_value = os.environ.get("RO_W2_SIGNED_WORKER_BUILD")
        sidecar_value = os.environ.get("RO_W2_CORE_SIDECAR_GUARDIAN")
        if not build_value or not sidecar_value:
            self.skipTest("signed worker and Core guardian are required")
        from workers.windows import document_launcher, recovery_guardian
        from workers.windows.runtime_inventory import APPLICATION_INVENTORY_PUBLIC_KEY, SignedWorkerRuntime

        build = Path(build_value).resolve(strict=True)
        guardian = Path(sidecar_value).resolve(strict=True)
        signed = SignedWorkerRuntime(
            build / "package",
            (build / "inventory.json").read_bytes(),
            (build / "inventory.sig").read_bytes(),
            APPLICATION_INVENTORY_PUBLIC_KEY,
        )
        fixture = attachment_fixtures.LocalAttachmentServiceTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        session = "d" * 32
        actor = fixture.corpus.actor

        class Imports:
            def native_context(self, root, project_id):
                if (root, project_id) != (str(fixture.project_root), fixture.corpus.project):
                    raise PreviewProblem("preview-project-session-changed")
                return session

            def in_native_session(self, root, project_id, session_id, action):
                if self.native_context(root, project_id) != session_id:
                    raise PreviewProblem("preview-project-session-changed")
                return action()

        class Corpus:
            def _with_authority(self, root, trace_id, action):
                if root != str(fixture.project_root):
                    raise AttachmentProblem("attachment-authority-changed")
                return action(None, actor, actor.intent_revision_id, fixture.project_root, fixture.corpus.project)

        runtime = DocumentAttachmentRuntime(Imports(), Corpus(), lambda _path, _identity: fixture.store)
        app = create_app(
            attachments=runtime,
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        data = b"Synthetic plain text full text\n"
        header = {
            "root": str(fixture.project_root),
            "projectId": fixture.corpus.project,
            "sessionId": session,
            "sourceName": "paper.txt",
            "declaredMediaType": "text/plain",
            "sourceAssertionRevisionId": fixture._assertion_id(),
            "workId": fixture.corpus.work_id,
            "workRevisionId": fixture.work_revision_id,
            "versionId": fixture.version.version_id,
            "versionRevisionId": fixture.version.revision_id,
            "byteLength": len(data),
        }
        with (
            patch.object(document_launcher, "load_installed_worker_runtime", return_value=signed),
            patch.object(recovery_guardian, "_guardian_command", return_value=[str(guardian), "--plugin-acl-guardian"]),
            TestClient(
                app,
                base_url="http://127.0.0.1:49152",
                headers={"Authorization": "Bearer " + "a" * 64},
                client=("127.0.0.1", 50000),
            ) as client,
        ):
            result = client.post(
                "/native/document-attachments/stage",
                content=DocumentAttachmentApiTests._frame(header, data),
                headers={"Content-Type": "application/octet-stream"},
            )
            self.assertEqual(200, result.status_code, result.text)
            candidate = result.json()
            self.assertEqual(hashlib.sha256(data).hexdigest(), candidate["objectSha256"])
            self.assertEqual("plain-text", candidate["format"])
            self.assertEqual(header["versionRevisionId"], candidate["versionRevisionId"])
            denied = client.post(
                "/native/document-attachments/commit",
                json={
                    "root": header["root"],
                    "projectId": header["projectId"],
                    "sessionId": session,
                    "candidateId": candidate["candidateId"],
                    "confirmationSha256": candidate["candidateSha256"],
                    "commandId": new_uuid_v7(),
                },
            )
            self.assertEqual(403, denied.status_code, denied.text)
            with open_canonical_database(fixture.corpus.database, expected_project_id=fixture.corpus.project) as db:
                self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_assertions").fetchone()[0])

if __name__ == "__main__":
    unittest.main()
