"""Real owned HTTPS and signed LPAC acquisition; no public internet or research data.

The lower TCP seam maps an already validated public address to a local listener.
TLS verification, HTTP framing, protected repositories and worker isolation are
real. The fixture CA and synthetic signing inventory are test-owned authority.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import httpcore2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.acquisition.transport import AcquisitionHTTPTransport  # noqa: E402


class OwnedHttpsFixture:
    def __init__(self, testcase: unittest.TestCase):
        self.requests: list[bytes] = []
        self.targets: list[tuple[str, int]] = []
        self.body = b"Synthetic verified acquired full text.\n"
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-acquisition-tls-synthetic-")
        testcase.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        openssl = shutil.which("openssl")
        if openssl is None and os.name == "nt":
            bundled = Path(os.environ["PROGRAMFILES"]) / "Git/usr/bin/openssl.exe"
            openssl = str(bundled) if bundled.is_file() else None
        if openssl is None:
            testcase.fail("The owned TLS fixture requires OpenSSL.")
        cert, key = root / "fixture.pem", root / "fixture.key"
        subprocess.run(
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=papers.example",
                "-addext",
                "subjectAltName=DNS:papers.example",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        self.pem = cert.read_bytes()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append(self.raw_requestline + self.headers.as_bytes())
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(owner.body)))
                self.send_header("Content-Disposition", 'attachment; filename="../../untrusted.exe"')
                self.send_header("Set-Cookie", "synthetic=must-not-forward")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(owner.body)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        testcase.addCleanup(self.close)
        self.original_backend = httpcore2.SyncBackend()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    @contextmanager
    def network(self, *, trusted=True):
        context = ssl.create_default_context()
        if trusted:
            context.load_verify_locations(cadata=self.pem.decode("ascii"))
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        original_resolver = socket.getaddrinfo
        owner = self

        class FixtureSocket:
            def connect_tcp(self, host, port, timeout=None, socket_options=None):
                if (host, port) != ("93.184.216.34", 443):
                    raise AssertionError("The acquisition socket was not pinned to the validated address.")
                owner.targets.append((host, port))
                return owner.original_backend.connect_tcp(
                    "127.0.0.1", owner.server.server_port, timeout, socket_options=socket_options
                )

        def resolve(host, port, *args, **kwargs):
            if host in {"papers.example", "wrong.example"}:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
            return original_resolver(host, port, *args, **kwargs)

        with (
            patch("socket.getaddrinfo", side_effect=resolve),
            patch("httpcore2.SyncBackend", return_value=FixtureSocket()),
            patch("httpx2.create_ssl_context", return_value=context) as factory,
        ):
            yield
        factory.assert_called_with(verify=True, trust_env=False)


class AcquisitionTlsTests(unittest.TestCase):
    def test_verified_hostname_tls_and_no_credentials_cookies_referrer_or_proxy(self):
        fixture = OwnedHttpsFixture(self)
        with (
            fixture.network(),
            patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1"}),
        ):
            for _ in range(2):
                with AcquisitionHTTPTransport().open(
                    "https://papers.example/paper", timeout=3, checkpoint=lambda: None
                ) as response:
                    self.assertEqual(fixture.body, b"".join(response.iter_stream()))
        self.assertEqual([("93.184.216.34", 443)] * 2, fixture.targets)
        for request in fixture.requests:
            self.assertIn(b"Host: papers.example", request)
            self.assertIn(b"Accept-Encoding: identity", request)
            for forbidden in (b"authorization:", b"cookie:", b"referer:", b"proxy-authorization:"):
                self.assertNotIn(forbidden, request.lower())

    def test_untrusted_and_wrong_hostname_tls_never_send_http(self):
        fixture = OwnedHttpsFixture(self)
        for trusted, host in ((False, "papers.example"), (True, "wrong.example")):
            with (
                self.subTest(trusted=trusted),
                fixture.network(trusted=trusted),
                self.assertRaises(httpcore2.ConnectError),
                AcquisitionHTTPTransport().open("https://" + host + "/paper", timeout=3, checkpoint=lambda: None),
            ):
                self.fail("A certificate denial cannot send a request.")
        self.assertEqual([], fixture.requests)


class AcquisitionPrincipalTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows signed LPAC acquisition")
    def test_current_core_session_through_verified_tls_encrypted_stage_and_signed_lpac(self):
        import sqlcipher3.dbapi2 as sqlcipher
        from fastapi.testclient import TestClient
        from research_observatory_core import storage
        from research_observatory_core.app import create_app
        from research_observatory_core.authentication import capability_token_digest
        from research_observatory_core.corpus_repository import SqliteCorpusRepository
        from research_observatory_core.corpus_service import CorpusService
        from research_observatory_core.domain_contracts import new_uuid_v7
        from research_observatory_core.import_preview_repository import sqlite_import_preview_repository
        from research_observatory_core.import_preview_service import ImportPreviewService, ImportProjectAdapters
        from research_observatory_core.main import DocumentAttachmentRuntime
        from research_observatory_core.ports.import_previews import PreviewProblem
        from research_observatory_core.repositories import (
            create_sqlite_unit_of_work_factory,
            sqlite_intent_revision_repository,
            sqlite_workflow_admission_binding,
            sqlite_workflow_queue_repository,
        )
        from research_observatory_core.workflow_executor import (
            LocalAdmissionController,
            ProjectWorkerPolicy,
            WorkerResources,
        )

        from tests.database_key_fixtures import InMemoryDatabaseKeyProvider
        from tests.documents.test_oa_acquisition import AcquisitionIntegrationTests
        from workers.windows import document_launcher, recovery_guardian
        from workers.windows.runtime_inventory import APPLICATION_INVENTORY_PUBLIC_KEY, SignedWorkerRuntime

        build_value, guardian_value = (
            os.environ.get("RO_W2_SIGNED_WORKER_BUILD"),
            os.environ.get("RO_W2_CORE_SIDECAR_GUARDIAN"),
        )
        if not build_value or not guardian_value:
            self.fail("Signed worker and native Core guardian are required for acquisition principal proof.")
        build, guardian = Path(build_value).resolve(strict=True), Path(guardian_value).resolve(strict=True)
        signed = SignedWorkerRuntime(
            build / "package",
            (build / "inventory.json").read_bytes(),
            (build / "inventory.sig").read_bytes(),
            APPLICATION_INVENTORY_PUBLIC_KEY,
        )
        selected = AcquisitionIntegrationTests(methodName="runTest")
        selected.setUp()
        self.addCleanup(selected.doCleanups)
        f = selected.fixture
        selected.permission()
        # Convert this owned synthetic fixture before exercising the runtime;
        # production database reads/writes use SQLCipher and the real key port.
        keys = InMemoryDatabaseKeyProvider()
        with keys.active_key(selected.project, create=True) as lease:
            material = lease.use(bytes)
        protected = selected.database.with_name("protected-fixture.sqlite3")
        source = sqlcipher.connect(selected.database.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(protected), "x'" + material.hex() + "'"))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.user_version={storage.DATABASE_SCHEMA_VERSION}")
            source.execute(f"PRAGMA protected.application_id={storage.APPLICATION_ID}")
            self.assertEqual("wal", source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0])
            source.execute("DETACH DATABASE protected")
        finally:
            source.close()
        selected.database.unlink()
        for suffix in ("-wal", "-shm"):
            selected.database.with_name(selected.database.name + suffix).unlink(missing_ok=True)
        protected.replace(selected.database)
        with storage._DATABASE_PROTECTION_LOCK:
            prior_protection = storage._DATABASE_PROTECTION
        storage.configure_protected_database_provider(keys)

        def restore_protection():
            with storage._DATABASE_PROTECTION_LOCK:
                storage._DATABASE_PROTECTION = prior_protection

        self.addCleanup(restore_protection)
        self.assertFalse(selected.database.read_bytes().startswith(b"SQLite format 3"))

        def adapters(path, project):
            return ImportProjectAdapters(
                sqlite_import_preview_repository(path / "state/project.sqlite3", project),
                sqlite_intent_revision_repository(path, project),
                f.queue,
                selected.objects,
                create_sqlite_unit_of_work_factory(path / "state/project.sqlite3", project),
                f.admission,
            )

        imports = ImportPreviewService(
            f.projects,
            f.privacy,
            adapters,
            local_actor_id=selected.actor.actor_id,
            resume_epoch="8" * 32,
            now=f.clock.now,
        )
        self.addCleanup(imports.shutdown)
        corpus = CorpusService(
            f.projects,
            f.privacy,
            imports=imports,
            connectors=f.worker,
            repository_factory=lambda path, project: SqliteCorpusRepository(path / "state/project.sqlite3", project),
            intent_factory=sqlite_intent_revision_repository,
            actor_id=selected.actor.actor_id,
            now=f.clock.now,
        )
        controller = LocalAdmissionController(interactive_reserve=WorkerResources(1, 256 * 1024**2, 0, 256 * 1024**2))
        demand = WorkerResources(1, 256 * 1024**2, 0, 1024**3)
        runtime = DocumentAttachmentRuntime(
            imports,
            corpus,
            lambda _path, _project: selected.objects,
            admission_factory=lambda path, project: sqlite_workflow_admission_binding(
                sqlite_workflow_queue_repository(path, project),
                controller=controller,
                policy=ProjectWorkerPolicy(project, demand, {"document": demand}, {"document": 1}),
            ),
        )
        session = runtime.context(f.root, selected.project)
        preview = runtime.acquisition_preview(
            f.root, selected.project, session, selected.selection(), trace_id="d" * 32
        )
        fixture = OwnedHttpsFixture(self)
        with (
            fixture.network(),
            patch.object(document_launcher, "load_installed_worker_runtime", return_value=signed),
            patch.object(recovery_guardian, "_guardian_command", return_value=[str(guardian), "--plugin-acl-guardian"]),
        ):
            operation = new_uuid_v7()
            candidate = runtime.acquisition_download(
                f.root,
                selected.project,
                session,
                preview.preview_id,
                confirmation=preview.confirmation,
                operation_id=operation,
                trace_id="d" * 32,
                cancellation_requested=lambda: False,
            )
        self.assertEqual(hashlib.sha256(fixture.body).hexdigest(), candidate.object_sha256)
        self.assertEqual("plain-text", candidate.format)
        self.assertEqual(1, len(fixture.requests))
        queue = sqlite_workflow_queue_repository(Path(f.root), selected.project)
        with storage.open_canonical_database(selected.database, expected_project_id=selected.project) as database:
            job_id = database.execute(
                "SELECT job_id FROM document_intake_jobs WHERE operation_id=?", (operation,)
            ).fetchone()[0]
        self.assertEqual("succeeded", queue.get(job_id).state)
        self.assertEqual(0, selected.count("document_attachment_assertions"))
        self.assertEqual(1, selected.count("document_acquisition_sources"))
        self.assertEqual(1, selected.count("acquisition_attempt_results"))
        imports.detach(f.root)
        with self.assertRaises(PreviewProblem):
            runtime.acquisition_download(
                f.root,
                selected.project,
                session,
                preview.preview_id,
                confirmation=preview.confirmation,
                operation_id=new_uuid_v7(),
                trace_id="d" * 32,
                cancellation_requested=lambda: False,
            )
        self.assertEqual(1, len(fixture.requests))
        new_session = runtime.context(f.root, selected.project)
        self.assertNotEqual(session, new_session)
        app = create_app(
            attachments=runtime,
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        association = {
            key: value
            for key, value in selected.selection().model_dump(mode="json", by_alias=True).items()
            if key in {"sourceAssertionRevisionId", "workId", "workRevisionId", "versionId", "versionRevisionId"}
        }
        with TestClient(
            app,
            base_url="http://127.0.0.1:49152",
            headers={"Authorization": "Bearer " + "a" * 64},
            client=("127.0.0.1", 50000),
        ) as client:
            base = {"root": f.root, "projectId": selected.project, "sessionId": new_session}
            retained = client.post(
                "/native/document-attachments/retained-candidates", json={**base, "selection": association}
            )
            self.assertEqual(200, retained.status_code, retained.text)
            self.assertEqual(candidate.candidate_id, retained.json()["retained"][0]["candidateId"])
            recovery = new_uuid_v7()
            command = {
                **base,
                "selection": association,
                "candidateId": candidate.candidate_id,
                "originalOperationId": operation,
                "recoveryOperationId": recovery,
                "confirmationSha256": candidate.candidate_sha256,
            }
            denied = client.post(
                "/native/document-attachments/candidate-recovery", json={**command, "sessionId": session}
            )
            self.assertEqual(403, denied.status_code, denied.text)
            recovered = client.post("/native/document-attachments/candidate-recovery", json=command)
            self.assertEqual(200, recovered.status_code, recovered.text)
            self.assertEqual(candidate.candidate_id, recovered.json()["candidateId"])
            self.assertEqual(0, selected.count("document_attachment_assertions"))
            committed = client.post(
                "/native/document-attachments/commit",
                json={
                    **base,
                    **association,
                    "candidateId": candidate.candidate_id,
                    "confirmationSha256": candidate.candidate_sha256,
                    "operationId": recovery,
                    "commandId": new_uuid_v7(),
                    "matchConfirmed": True,
                    "permittedUse": "project-only",
                },
            )
            self.assertEqual(200, committed.status_code, committed.text)
        self.assertEqual(1, len(fixture.requests), "fresh recovery and explicit Attach repeat no HTTP")
        self.assertEqual(1, selected.count("document_attachment_recoveries"))
        self.assertEqual(1, selected.count("document_attachment_assertions"))
        self.assertFalse(selected.database.read_bytes().startswith(b"SQLite format 3"))

        # A downstream consumer receives only portable immutable identities and
        # metadata. Exact protected reads still recheck the current local copy.
        from research_observatory_core.document_attachment_api import DocumentAttachmentView
        from research_observatory_core.document_attachment_repository import AcquisitionRepository
        from research_observatory_core.ports.acquisition import AcquisitionRepositoryPort
        from research_observatory_core.ports.document_attachments import DocumentAttachment
        from research_observatory_core.ports.object_store import ObjectAccessDenied
        from research_observatory_core.ports.rights import RightsPermissionDraft
        from research_observatory_core.rights_policy import RightsUse

        from tests.documents.acquisition_handoff_consumer import consume_attached_source

        view = DocumentAttachmentView.model_validate(committed.json())
        attachment = DocumentAttachment(**view.model_dump())
        restarted: AcquisitionRepositoryPort = AcquisitionRepository(
            selected.database, selected.project, f.repository.source_record, selected.attachments
        )
        retained_source = restarted.source_for_revision(attachment.document_revision_id, actor=selected.actor)
        self.assertIsNotNone(retained_source)
        location, receipt = retained_source
        self.assertEqual(selected.location, location)
        self.assertEqual("cc-by-4.0", location.license)
        self.assertEqual("acceptedVersion", location.version)
        self.assertEqual(candidate.object_sha256, receipt.actual_sha256)
        self.assertEqual(selected.location.location_sha256, receipt.location_sha256)
        self.assertEqual(fixture.body, consume_attached_source(restarted, selected.objects, attachment, selected.actor))
        with self.assertRaises(ObjectAccessDenied):
            selected.objects.open(attachment.object_sha256, purpose="document-analysis")
        with self.assertRaises(ObjectAccessDenied):
            selected.objects.open_document_attachment(attachment.attachment_id, new_uuid_v7(), actor=selected.actor)
        prior_policy = selected.repository.rights.current(candidate.rights_subject, actor=selected.actor)
        self.assertIsNotNone(prior_policy)
        selected.repository.rights.publish_draft(
            candidate.rights_subject,
            (
                RightsPermissionDraft(
                    use=RightsUse(action="inspect", purpose="document-analysis", destination_kind="local-project"),
                    value="denied",
                    basis="researcher-confirmed",
                    confidence="confirmed",
                    evidence_revision_ids=(candidate.source_assertion_revision_id,),
                    license_observation_revision_id=None,
                    entitlement_revision_id=None,
                ),
            ),
            prior_policy.revision_id,
            command_id=new_uuid_v7(),
            command_sha256="6" * 64,
            actor=selected.actor,
        )
        with self.assertRaises(ObjectAccessDenied):
            consume_attached_source(restarted, selected.objects, attachment, selected.actor)
        self.assertEqual(
            retained_source, restarted.source_for_revision(attachment.document_revision_id, actor=selected.actor)
        )
        self.assertEqual(1, len(fixture.requests), "portable handoff and denied reads send no further HTTP")
        self.assertEqual(1, selected.count("document_attachment_recoveries"))
        self.assertEqual(1, selected.count("document_attachment_assertions"))


if __name__ == "__main__":
    unittest.main()
