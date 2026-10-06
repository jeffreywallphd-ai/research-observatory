"""Synthetic source locations are observations, never permission or arbitrary URLs."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.contracts import ConnectorRecord, SourceField  # noqa: E402
from research_observatory_core.connectors.providers import map_response  # noqa: E402

from tests.connectors.test_scholarly_mapping import fixture, request  # noqa: E402


class LocationSelectionTests(unittest.TestCase):
    def record(self) -> ConnectorRecord:
        document = fixture("openalex")
        document["results"][0]["primary_location"] = {
            "is_oa": True,
            "pdf_url": "https://papers.example/synthetic.pdf",
            "landing_page_url": "https://papers.example/synthetic",
            "license": "cc-by-4.0",
            "version": "publishedVersion",
        }
        return map_response(request("openalex"), document, retrieved_at="2026-10-06T00:00:00.000Z").records[0]

    def test_selected_location_retains_its_own_license_and_version(self):
        from research_observatory_core.acquisition.locations import retained_locations

        locations = retained_locations(self.record())
        self.assertEqual("https://papers.example/synthetic.pdf", locations[0].url)
        self.assertEqual("cc-by-4.0", locations[0].license)
        self.assertEqual("publishedVersion", locations[0].version)
        self.assertNotEqual(locations[0].key, locations[1].key)

    def test_duplicate_field_cannot_substitute_a_location(self):
        from research_observatory_core.acquisition.locations import retained_locations
        from research_observatory_core.ports.acquisition import AcquisitionProblem

        record = self.record()
        field = next(x for x in record.fields if x.name == "primary_location")
        changed = ConnectorRecord.model_validate(record.model_dump() | {"fields": (*record.fields, field)})
        with self.assertRaisesRegex(AcquisitionProblem, "source-invalid"):
            retained_locations(changed)

    def test_closed_source_does_not_become_open_from_an_untrusted_url(self):
        from research_observatory_core.acquisition.locations import retained_locations

        record = self.record()
        fields = tuple(
            SourceField(
                namespace=x.namespace,
                name=x.name,
                encoding="json",
                value=json.dumps({"is_oa": False, "pdf_url": "https://papers.example/closed.pdf"}),
            )
            if x.name == "primary_location"
            else x
            for x in record.fields
        )
        self.assertEqual(
            (), retained_locations(ConnectorRecord.model_validate(record.model_dump() | {"fields": fields}))
        )

    def test_alternative_copies_and_provider_locations_keep_distinct_observations(self):
        from research_observatory_core.acquisition.locations import retained_locations

        record = self.record()
        alternatives = SourceField(
            namespace="openalex",
            name="locations",
            encoding="json",
            value=json.dumps(
                [
                    {
                        "is_oa": True,
                        "pdf_url": "https://copies.example/a.pdf",
                        "license": "cc-by",
                        "version": "publishedVersion",
                    },
                    {
                        "is_oa": True,
                        "pdf_url": "https://copies.example/b.pdf",
                        "license": None,
                        "version": "submittedVersion",
                    },
                ]
            ),
        )
        fields = (*(item for item in record.fields if item.name != "locations"), alternatives)
        locations = retained_locations(ConnectorRecord.model_validate(record.model_dump() | {"fields": fields}))
        self.assertEqual(("cc-by", "publishedVersion"), (locations[-2].license, locations[-2].version))
        self.assertEqual((None, "submittedVersion"), (locations[-1].license, locations[-1].version))
        self.assertNotEqual(locations[-2].key, locations[-1].key)
        for provider, name, value in (
            (
                "unpaywall",
                "oa_locations",
                [{"url_for_pdf": "https://copies.example/c.pdf", "license": None, "version": "acceptedVersion"}],
            ),
            ("semantic-scholar", "openAccessPdf", {"url": "https://copies.example/d.pdf", "license": "cc-by-4.0"}),
        ):
            replacements = (SourceField(namespace=provider, name=name, encoding="json", value=json.dumps(value)),)
            if provider == "semantic-scholar":
                replacements += (SourceField(namespace=provider, name="isOpenAccess", encoding="json", value="true"),)
            # Synthetic retained fields exercise optional provider observations;
            # this does not claim their live API adapter or availability.
            source = ConnectorRecord.model_validate(
                record.model_dump() | {"provider_id": provider, "fields": replacements}
            )
            locations = retained_locations(source)
            self.assertEqual(1, len(locations))
            self.assertIsNone(locations[0].license if provider == "unpaywall" else locations[0].version)


class AcquisitionDestinationTests(unittest.TestCase):
    def test_only_https_443_without_credentials_fragments_or_ip_literals(self):
        from research_observatory_core.acquisition.transport import validated_url
        from research_observatory_core.ports.acquisition import AcquisitionProblem

        self.assertEqual("papers.example", validated_url("https://papers.example/paper?opaque=synthetic").host)
        for url in (
            "http://papers.example/paper",
            "https://user:secret@papers.example.invalid/paper",
            "https://papers.example:444/paper",
            "https://127.0.0.1/paper",
            "https://[::1]/paper",
            "https://papers.example/paper#fragment",
            "file:///paper",
            "https://papers.example/\nsecret",
        ):
            with self.subTest(url=url), self.assertRaises(AcquisitionProblem):
                validated_url(url)

    def test_socket_uses_checked_numeric_ip_and_rejects_any_private_answer(self):
        from research_observatory_core.acquisition.transport import AcquisitionNetworkBackend
        from research_observatory_core.ports.acquisition import AcquisitionProblem

        calls = []

        class SocketBackend:
            def connect_tcp(self, host, port, timeout=None, socket_options=None):
                calls.append((host, port))
                return object()

        backend = AcquisitionNetworkBackend("papers.example", backend=SocketBackend())
        public = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        with patch("socket.getaddrinfo", return_value=[public]):
            backend.connect_tcp("papers.example", 443, 2)
        self.assertEqual([("8.8.8.8", 443)], calls)
        for address in ("127.0.0.1", "10.1.2.3", "169.254.169.254", "::ffff:8.8.8.8", "2002:0808:0808::1"):
            private = (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
            with (
                self.subTest(address=address),
                patch("socket.getaddrinfo", return_value=[public, private]),
                self.assertRaises(AcquisitionProblem),
            ):
                backend.connect_tcp("papers.example", 443, 2)
        self.assertEqual(1, len(calls))

    def test_deadline_caps_each_socket_phase(self):
        from research_observatory_core.acquisition.transport import _CheckedStream
        from research_observatory_core.ports.acquisition import AcquisitionProblem

        stream = unittest.mock.Mock()
        checked = _CheckedStream(stream, lambda: None, 120.0)
        with patch("research_observatory_core.acquisition.transport.time.monotonic", return_value=119.5):
            checked.read(65536, timeout=1.0)
            checked.write(b"synthetic", timeout=1.0)
            checked.start_tls(object(), server_hostname="papers.example", timeout=10.0)
        self.assertEqual(0.5, stream.read.call_args.kwargs["timeout"])
        self.assertEqual(0.5, stream.write.call_args.kwargs["timeout"])
        self.assertEqual(0.5, stream.start_tls.call_args.kwargs["timeout"])
        with (
            patch("research_observatory_core.acquisition.transport.time.monotonic", return_value=120.0),
            self.assertRaisesRegex(AcquisitionProblem, "timeout"),
        ):
            checked.read(65536, timeout=1.0)


class AcquisitionStreamTests(unittest.TestCase):
    def test_stream_without_length_rejects_actual_wire_cap_and_counts_retries(self):
        from research_observatory_core.acquisition.service import _Source
        from research_observatory_core.ports.acquisition import AcquisitionProblem
        from research_observatory_core.ports.document_attachments import MAX_DOCUMENT_BYTES

        total = [0]
        source = _Source(
            iter([b"x" * 1048576] * 129),
            lambda: None,
            total=total,
            expected_length=None,
            maximum=MAX_DOCUMENT_BYTES,
            clock=lambda: 1.0,
        )
        for _ in range(128):
            self.assertEqual(1048576, len(source.read(1048576)))
        with self.assertRaisesRegex(AcquisitionProblem, "too-large"):
            source.read(1048576)
        self.assertIsNone(source.finished_at)
        # A retry inherits consumed wire bytes; its new representation is fresh.
        total = [MAX_DOCUMENT_BYTES]
        source = _Source(
            iter([b"new"]),
            lambda: None,
            total=total,
            expected_length=None,
            maximum=MAX_DOCUMENT_BYTES,
            clock=lambda: 1.0,
        )
        with self.assertRaisesRegex(AcquisitionProblem, "too-large"):
            source.read(65536)


class AcquisitionMigrationTests(unittest.TestCase):
    def setUp(self):
        from research_observatory_core.storage import development_plaintext_database_fixture

        self.manifest = json.loads((REPO / "tests/fixtures/documents/v23-predecessor.json").read_text())
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-acquisition-v23-")
        self.addCleanup(self.cleanup)
        self.project = Path(self.temporary.name) / "project"
        with ZipFile(REPO / "tests/fixtures/documents/v23-predecessor.zip") as z:
            for name in ("state/project.sqlite3", *(x["relativePath"] for x in self.manifest["ciphertext"])):
                path = self.project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(z.read(name))
        self.database = self.project / "state/project.sqlite3"
        self.fixture = development_plaintext_database_fixture()
        self.fixture.__enter__()
        self.addCleanup(self.fixture.__exit__, None, None, None)

    def cleanup(self):
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

    def rows(self):
        with closing(sqlite3.connect(self.database)) as db:
            return {
                table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in self.manifest["counts"]
            }

    def test_literal_v23_preserves_rows_ciphertext_and_verified_backup(self):
        import hashlib

        from research_observatory_core.migrations import runner
        from research_observatory_core.storage import _schema_fingerprint

        self.assertEqual(self.manifest["databaseSha256"], hashlib.sha256(self.database.read_bytes()).hexdigest())
        before = self.rows()
        self.assertEqual({table: len(rows) for table, rows in before.items()}, self.manifest["counts"])
        plan = runner.plan_database_migration(self.database, expected_project_id=self.manifest["projectId"])
        self.assertEqual(("0024_open_access_acquisition",), plan.migration_ids)
        result = runner.migrate_database(self.database, expected_project_id=self.manifest["projectId"])
        self.assertEqual(before, self.rows())
        with closing(sqlite3.connect(self.project / result.backup_relative_path)) as db:
            self.assertEqual(23, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(self.manifest["schemaSha256"], _schema_fingerprint(db))
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(24, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
            self.assertEqual(0, db.execute("SELECT count(*) FROM acquisition_locations").fetchone()[0])
        for item in self.manifest["ciphertext"]:
            self.assertEqual(
                item["sha256"], hashlib.sha256((self.project / item["relativePath"]).read_bytes()).hexdigest()
            )
        self.assertFalse(
            runner.plan_database_migration(
                self.database, expected_project_id=self.manifest["projectId"]
            ).migration_required
        )

    def test_each_material_v24_interruption_retains_exact_v23(self):
        from research_observatory_core.migrations import runner
        from research_observatory_core.migrations.versions import v0024_open_access_acquisition as migration

        before = self.rows()
        for target_step in migration.MATERIAL_MIGRATION_STEPS:

            def interrupt(step, target_step=target_step):
                if step == target_step:
                    raise RuntimeError("synthetic v24 interruption")

            with (
                self.subTest(step=target_step),
                patch.object(migration, "_migration_step_completed", side_effect=interrupt),
                self.assertRaises(RuntimeError),
            ):
                runner.migrate_database(self.database, expected_project_id=self.manifest["projectId"])
            self.assertEqual(before, self.rows())
            with closing(sqlite3.connect(self.database)) as db:
                self.assertEqual(23, db.execute("PRAGMA user_version").fetchone()[0])
        self.assertEqual(
            "migrated", runner.migrate_database(self.database, expected_project_id=self.manifest["projectId"]).status
        )


class AcquisitionIntegrationTests(unittest.TestCase):
    """Actual canonical source/rights and encrypted objects; unit transport/inspector."""

    def setUp(self):
        from research_observatory_core.acquisition.service import OpenAccessAcquisitionService
        from research_observatory_core.document_attachment_repository import (
            AcquisitionRepository,
            LocalDocumentAttachmentService,
        )
        from research_observatory_core.domain_contracts import new_uuid_v7
        from research_observatory_core.ingestion.preview_workflow import fingerprint
        from research_observatory_core.object_store import create_local_object_store
        from research_observatory_core.ports.corpus import CorpusActor
        from research_observatory_core.ports.document_attachments import DocumentInspectionProblem
        from research_observatory_core.ports.reconciliation import ReconciliationActor
        from research_observatory_core.reconciliation.versions import (
            VersionCommand,
            VersionDate,
            VersionDefinition,
            VersionPlan,
        )
        from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository
        from research_observatory_core.repositories import sqlite_intent_revision_repository
        from research_observatory_core.research_intents import validated_workflow_authority
        from research_observatory_core.storage import open_canonical_database

        from tests.connectors import test_connector_workflow as workflow_fixtures
        from tests.corpus import test_repository as corpus_fixtures
        from workers.document.inspection import DocumentInspectionError, classify_document

        self.fixture = corpus_fixtures.CorpusConnectorWriterTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        f = self.fixture
        document = fixture("openalex")
        document["results"][0]["primary_location"] = {
            "is_oa": True,
            "pdf_url": "https://papers.example/synthetic.txt",
            "license": "cc-by-4.0",
            "version": "acceptedVersion",
        }
        _, job = f.schedule()
        with patch.object(workflow_fixtures, "fixture", return_value=document):
            f.worker.run_pending()
        page = f.worker.reconciliation_sources(f.root, job.job_id, after=0, limit=1)
        self.address = page.addresses[0]
        self.source = f.worker.reconciliation_source(f.root, self.address)
        self.database, self.project = f.repository._database, f.project.project_id
        repo = SqliteReconciliationRepository(self.database, self.project)
        reconcile_actor = ReconciliationActor(new_uuid_v7(), "a" * 32, f.clock.now(), "b" * 64, "c" * 64)
        result = repo.reconcile(
            self.address, command_id=new_uuid_v7(), actor=reconcile_actor, resolve=lambda _address: self.source
        )
        self.work_id = result.work_id
        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
            self.assertion_id = db.execute(
                "SELECT revision_id FROM reconciliation_assertions WHERE project_id=?", (self.project,)
            ).fetchone()[0]
        context = repo.version_context((self.work_id,), resolve=lambda _address: self.source)
        plan = VersionPlan(
            action="register",
            work_ids=(self.work_id,),
            context_sha256=context.fingerprint,
            rationale="Synthetic selected full-text Version",
            definition=VersionDefinition(
                kind="accepted-manuscript",
                assertion_revision_ids=(self.assertion_id,),
                date=VersionDate(precision="not-reported", value=None),
            ),
        )
        preview = repo.preview_versions(plan, actor=reconcile_actor, resolve=lambda _address: self.source)
        version = repo.decide_versions(
            VersionCommand(command_id=new_uuid_v7(), plan=plan, expected_preview_sha256=preview.preview_sha256),
            actor=reconcile_actor,
            resolve=lambda _address: self.source,
        ).version_revisions[0]
        self.version = version
        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
            self.work_revision_id = db.execute(
                "SELECT revision_id FROM aggregate_revisions WHERE project_id=? AND aggregate_id=? "
                "ORDER BY revision DESC LIMIT 1",
                (self.project, self.work_id),
            ).fetchone()[0]
        intents = sqlite_intent_revision_repository(Path(f.root), self.project)
        bridge = intents.project_identity()
        _, revisions, _, _ = validated_workflow_authority(intents, expected_project_id=bridge.domain_project_id)
        intent = revisions[0]
        self.actor = CorpusActor(
            actor_id=new_uuid_v7(),
            trace_id="d" * 32,
            occurred_at=f.clock.now(),
            intent_revision_id=intent["revisionId"],
            intent_sha256=intent["revisionContentHash"].removeprefix("sha256:"),
            policy_sha256=fingerprint(f.privacy.get(f.root).model_dump(mode="json", by_alias=True)).removeprefix(
                "sha256:"
            ),
        )
        self.objects = create_local_object_store(Path(f.root), self.project, key_provider=f.keys)

        def inspect(stream, *, filename, declared_media_type, cancel):
            try:
                return classify_document(
                    stream.read(), extension=Path(filename).suffix, declared_media_type=declared_media_type
                )
            except DocumentInspectionError as error:
                raise DocumentInspectionProblem(error.code) from None

        self.attachments = LocalDocumentAttachmentService(self.database, self.project, self.objects, inspector=inspect)
        self.repository = AcquisitionRepository(
            self.database, self.project, f.repository.source_record, self.attachments
        )
        self.location = self.repository.locations(self.assertion_id, actor=self.actor)[0]
        self.calls = []
        self.responses = [(200, [(b"content-type", b"text/plain")], [b"Synthetic acquired full text.\n"])]
        self.before_network = lambda: None
        self.during_stream = lambda: None
        owner = self

        class Transport:
            @contextmanager
            def open(self, url, *, timeout, checkpoint):
                checkpoint()
                owner.before_network()
                owner.calls.append(url)
                status, headers, chunks = owner.responses.pop(0)

                class Response:
                    def iter_stream(self):
                        for chunk in chunks:
                            owner.during_stream()
                            if isinstance(chunk, Exception):
                                raise chunk
                            yield chunk

                response = Response()
                response.status, response.headers = status, headers
                yield response

        self.transport = Transport()
        self.session = "a" * 32
        self.authority_current = True

        def guard(_actor, action):
            from research_observatory_core.ports.acquisition import AcquisitionProblem

            if not self.authority_current:
                raise AcquisitionProblem("acquisition-authority-changed")
            return action()

        self.service = OpenAccessAcquisitionService(
            self.repository,
            self.attachments,
            session_id=self.session,
            authority_guard=guard,
            transport=self.transport,
            clock=f.clock.monotonic,
            sleep=lambda delay: setattr(f.clock, "seconds", f.clock.seconds + delay),
        )

    def selection(self, **updates):
        from research_observatory_core.ports.acquisition import AcquisitionSelection

        return AcquisitionSelection(
            location_id=self.location.location_id,
            location_sha256=self.location.location_sha256,
            source_assertion_revision_id=self.assertion_id,
            work_id=self.work_id,
            work_revision_id=self.work_revision_id,
            version_id=self.version.version_id,
            version_revision_id=self.version.revision_id,
            **updates,
        )

    def permission(self, value="permitted"):
        from research_observatory_core.domain_contracts import new_uuid_v7
        from research_observatory_core.ports.rights import RightsPermissionDraft
        from research_observatory_core.rights_policy import RightsUse

        subject = self.location.rights_subject
        prior = self.repository.rights.current(subject, actor=self.actor)
        permissions = tuple(
            RightsPermissionDraft(
                use=RightsUse(action=action, purpose=purpose, destination_kind="local-project"),
                value=value,
                basis="researcher-confirmed",
                confidence="confirmed",
                grantee_actor_id=self.actor.actor_id,
                evidence_revision_ids=(self.assertion_id,),
                license_observation_revision_id=None,
                entitlement_revision_id=None,
            )
            for action, purpose in (("store", "document-acquisition"), ("inspect", "document-analysis"))
        )
        return self.repository.rights.publish_draft(
            subject,
            permissions,
            prior.revision_id if prior else None,
            command_id=new_uuid_v7(),
            command_sha256="f" * 64,
            actor=self.actor,
        )

    def acquire(self, **selection_updates):
        from research_observatory_core.domain_contracts import new_uuid_v7

        self.preview = self.service.preview(self.selection(**selection_updates), actor=self.actor)
        self.operation_id = new_uuid_v7()
        return self.service.acquire(
            self.preview.preview_id,
            confirmation=self.preview.confirmation,
            operation_id=self.operation_id,
            cancellation_requested=lambda: False,
        )

    def commit(self, candidate):
        from research_observatory_core.domain_contracts import new_uuid_v7

        return self.attachments.commit(
            candidate.candidate_id,
            confirmation_sha256=candidate.candidate_sha256,
            command_id=new_uuid_v7(),
            actor=self.actor,
            operation_id=self.operation_id,
            session_id=self.session,
            match_confirmed=True,
            permitted_use="project-only",
            exact_selection=self.selection().association,
        )

    def count(self, table):
        from research_observatory_core.storage import open_canonical_database

        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
            return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def test_attempt_record_precedes_any_network_request(self):
        self.permission()
        self.before_network = lambda: self.assertEqual(1, self.count("acquisition_attempts"))
        self.acquire()

    def test_conflicting_retry_does_not_terminate_prior_unresolved_attempt(self):
        from research_observatory_core.domain_contracts import new_uuid_v7
        from research_observatory_core.ports.acquisition import AcquisitionProblem
        from research_observatory_core.storage import open_canonical_database

        self.permission()
        original = self.service.preview(self.selection(), actor=self.actor)
        operation = new_uuid_v7()
        self.repository.begin_attempt(
            original.selection,
            operation_id=operation,
            session_id=self.session,
            confirmation_sha256=original.confirmation_sha256,
            expected_policy_revision_id=original.provider_policy_revision_id,
            actor=self.actor,
        )
        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
            before = db.execute(
                "SELECT * FROM aggregate_revisions WHERE aggregate_id=? ORDER BY revision", (operation,)
            ).fetchall()
            original_attempt = db.execute(
                "SELECT * FROM acquisition_attempts WHERE operation_id=?", (operation,)
            ).fetchall()
        renewed = self.service.preview(self.selection(), actor=self.actor)
        with self.assertRaisesRegex(AcquisitionProblem, "operation-conflict"):
            self.service.acquire(
                renewed.preview_id,
                confirmation=renewed.confirmation,
                operation_id=operation,
                cancellation_requested=lambda: False,
            )
        self.assertEqual([], self.calls)
        self.assertEqual(0, self.count("acquisition_attempt_results"))
        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
            self.assertEqual(
                before,
                db.execute(
                    "SELECT * FROM aggregate_revisions WHERE aggregate_id=? ORDER BY revision", (operation,)
                ).fetchall(),
            )
            self.assertEqual(
                original_attempt,
                db.execute("SELECT * FROM acquisition_attempts WHERE operation_id=?", (operation,)).fetchall(),
            )

    def test_typed_inspector_cancellation_records_cancelled_and_discards_owned_stage(self):
        from research_observatory_core.document_attachment_repository import _inspect_signed_worker
        from research_observatory_core.domain_contracts import new_uuid_v7
        from research_observatory_core.ports.document_attachments import DocumentInspectionProblem
        from research_observatory_core.storage import open_canonical_database

        from workers.document.inspection import DocumentInspectionError

        self.permission()
        preview = self.service.preview(self.selection(), actor=self.actor)
        operation = new_uuid_v7()
        before_objects = self.count("object_records")
        cancel_requested = [False]

        def worker_cancel(stream, *, filename, declared_media_type, cancel):
            cancel_requested[0] = True
            self.assertTrue(cancel())
            raise DocumentInspectionError("cancelled")

        with (
            patch.object(self.attachments, "_inspector", side_effect=_inspect_signed_worker),
            patch("workers.windows.document_launcher.inspect_document", side_effect=worker_cancel),
            self.assertRaisesRegex(DocumentInspectionProblem, "cancelled"),
        ):
            self.service.acquire(
                preview.preview_id,
                confirmation=preview.confirmation,
                operation_id=operation,
                cancellation_requested=lambda: cancel_requested[0],
            )
        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
            self.assertEqual(
                [("cancelled", "acquisition-cancelled")],
                [
                    tuple(row)
                    for row in db.execute(
                        "SELECT outcome,code FROM acquisition_attempt_results WHERE operation_id=?", (operation,)
                    ).fetchall()
                ],
            )
            self.assertEqual(
                "acquisition-cancelled",
                db.execute(
                    "SELECT display_label_observed FROM aggregate_revisions WHERE aggregate_id=? "
                    "ORDER BY revision DESC LIMIT 1",
                    (operation,),
                ).fetchone()[0],
            )
        self.assertEqual(before_objects, self.count("object_records"))
        self.assertEqual(0, self.count("document_attachment_candidates"))
        self.assertEqual(0, self.count("document_acquisition_sources"))

    def test_runtime_session_loss_cancels_owned_post_transfer_inspection(self):
        from types import SimpleNamespace

        from research_observatory_core.domain_contracts import new_uuid_v7
        from research_observatory_core.main import DocumentAttachmentRuntime
        from research_observatory_core.ports.object_store import ObjectStagingCancelled

        self.permission()
        preview = self.service.preview(self.selection(), actor=self.actor)
        current_session = [self.session]
        runtime = DocumentAttachmentRuntime(
            SimpleNamespace(native_context=lambda *_args: current_session[0]),
            None,
            lambda *_args: self.objects,
        )
        original_inspect = self.attachments._inspector
        inspected = []
        before_objects = self.count("object_records")

        def inspect(stream, *, filename, declared_media_type, cancel):
            # Called only after transfer into authenticated encrypted staging.
            inspected.append(True)
            current_session[0] = None
            if cancel():
                raise ObjectStagingCancelled()
            return original_inspect(stream, filename=filename, declared_media_type=declared_media_type, cancel=cancel)

        with (
            patch.object(runtime, "_acquisition", return_value=(self.service, self.actor)),
            patch.object(self.attachments, "_inspector", side_effect=inspect),
            self.assertRaises(ObjectStagingCancelled),
        ):
            runtime.acquisition_download(
                self.fixture.root,
                self.project,
                self.session,
                preview.preview_id,
                confirmation=preview.confirmation,
                operation_id=new_uuid_v7(),
                trace_id="d" * 32,
                cancellation_requested=lambda: False,
            )
        self.assertEqual([True], inspected)
        self.assertEqual(0, self.count("document_attachment_candidates"))
        self.assertEqual(0, self.count("document_acquisition_sources"))
        self.assertEqual(before_objects, self.count("object_records"))

    def test_oa_observation_is_not_permission_and_sibling_substitution_denies(self):
        from research_observatory_core.ports.acquisition import AcquisitionProblem

        with self.assertRaisesRegex(AcquisitionProblem, "rights-denied"):
            self.service.preview(self.selection(), actor=self.actor)
        self.assertEqual([], self.calls)
        self.permission()
        changed = self.selection().model_copy(update={"location_sha256": "a" * 64})
        with self.assertRaisesRegex(AcquisitionProblem, "selection-invalid"):
            self.service.preview(changed, actor=self.actor)
        self.assertEqual([], self.calls)

    def test_selected_source_license_checksum_survive_commit_and_restart(self):
        from research_observatory_core.document_attachment_repository import AcquisitionRepository
        from research_observatory_core.domain_contracts import new_uuid_v7
        from research_observatory_core.storage import open_canonical_database

        self.permission()
        data = self.responses[0][2][0]
        candidate = self.acquire(expected_sha256=hashlib.sha256(data).hexdigest())
        attachment = self.attachments.commit(
            candidate.candidate_id,
            confirmation_sha256=candidate.candidate_sha256,
            command_id=new_uuid_v7(),
            actor=self.actor,
            operation_id=self.operation_id,
            session_id=self.session,
            match_confirmed=True,
            permitted_use="project-only",
            exact_selection=self.selection().association,
        )
        restarted = AcquisitionRepository(
            self.database, self.project, self.fixture.repository.source_record, self.attachments
        )
        location, receipt = restarted.source_for_revision(attachment.document_revision_id, actor=self.actor)
        self.assertEqual(self.location, location)
        self.assertEqual("cc-by-4.0", location.license)
        self.assertEqual("acceptedVersion", location.version)
        self.assertEqual(candidate.object_sha256, receipt.actual_sha256)
        self.assertEqual(receipt.expected_sha256, receipt.actual_sha256)
        self.assertEqual(self.preview.confirmation_sha256, receipt.confirmation_sha256)
        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
            self.assertEqual(
                "connector-acquisition",
                db.execute(
                    "SELECT creation_source FROM object_records WHERE object_sha256=?", (candidate.object_sha256,)
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                db.execute(
                    "SELECT count(*) FROM provenance_events WHERE revision_id=?", (attachment.document_revision_id,)
                ).fetchone()[0],
            )
        for blob in Path(self.fixture.root).glob("objects/*/*/*.blob"):
            self.assertNotIn(data, blob.read_bytes())

    def test_spoofed_content_and_oversized_length_publish_no_candidate(self):
        from research_observatory_core.ports.document_attachments import DocumentInspectionProblem

        self.permission()
        self.responses = [(200, [(b"content-type", b"application/pdf")], [b"Synthetic text is not a PDF."])]
        with self.assertRaisesRegex(DocumentInspectionProblem, "mismatch|unsupported"):
            self.acquire()
        self.assertEqual(0, self.count("document_attachment_candidates"))
        from research_observatory_core.ports.acquisition import AcquisitionProblem

        self.responses = [(200, [(b"content-type", b"text/plain"), (b"content-length", b"134217729")], [b"unused"])]
        with self.assertRaisesRegex(AcquisitionProblem, "too-large"):
            self.acquire()
        self.assertEqual(0, self.count("document_acquisition_sources"))
        self.assertEqual(1, self.count("reconciliation_assertions"))

    def test_stream_revocation_and_publication_failure_leave_no_association(self):
        from research_observatory_core.ports.acquisition import AcquisitionProblem

        self.permission()
        self.during_stream = lambda: setattr(self, "authority_current", False)
        with self.assertRaisesRegex(AcquisitionProblem, "authority-changed"):
            self.acquire()
        self.assertEqual(0, self.count("document_attachment_candidates"))
        self.authority_current = True
        self.during_stream = lambda: None
        self.responses = [(200, [(b"content-type", b"text/plain")], [b"Synthetic new complete copy\n"])]
        with (
            patch(
                "research_observatory_core.document_attachment_repository.publish_acquisition_source",
                side_effect=RuntimeError("synthetic publication interruption"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.acquire()
        self.assertEqual(0, self.count("document_attachment_candidates"))
        self.assertEqual(0, self.count("document_attachment_operations"))

    def test_retry_discards_owned_partial_and_does_not_concatenate_changed_bytes(self):
        import httpcore2

        self.permission()
        self.responses = [
            (
                200,
                [(b"content-type", b"text/plain")],
                [b"Synthetic old partial", httpcore2.ReadError("synthetic interrupted socket")],
            ),
            (200, [(b"content-type", b"text/plain")], [b"Synthetic new full copy\n"]),
        ]
        candidate = self.acquire()
        self.assertEqual(hashlib.sha256(b"Synthetic new full copy\n").hexdigest(), candidate.object_sha256)
        self.assertEqual(2, len(self.calls))
        self.assertEqual(1, self.count("document_attachment_candidates"))

    def test_redirect_requires_explicit_host_and_never_exceeds_five(self):
        from research_observatory_core.ports.acquisition import AcquisitionProblem

        self.permission()
        self.responses = [(302, [(b"location", b"https://cdn.example/new.txt")], [])]
        with self.assertRaisesRegex(AcquisitionProblem, "redirect-denied"):
            self.acquire()
        self.responses = [(302, [(b"location", b"/again")], [])] * 6
        with self.assertRaisesRegex(AcquisitionProblem, "redirect-limit"):
            self.acquire()
        self.assertEqual(0, self.count("document_attachment_candidates"))

    def test_current_provider_rights_fence_preview_stream_and_final_commit(self):
        from research_observatory_core.domain_contracts import new_uuid_v7
        from research_observatory_core.ports.acquisition import AcquisitionProblem
        from research_observatory_core.ports.document_attachments import AttachmentProblem

        self.permission()
        preview = self.service.preview(self.selection(), actor=self.actor)
        self.permission("denied")
        with self.assertRaisesRegex(AcquisitionProblem, "rights-denied"):
            self.service.acquire(
                preview.preview_id,
                confirmation=preview.confirmation,
                operation_id=new_uuid_v7(),
                cancellation_requested=lambda: False,
            )
        self.assertEqual([], self.calls)
        self.permission()
        self.during_stream = lambda: self.permission("denied")
        with self.assertRaisesRegex(AcquisitionProblem, "rights-denied"):
            self.acquire()
        self.assertEqual(0, self.count("document_acquisition_sources"))
        self.permission()
        self.during_stream = lambda: None
        self.responses = [(200, [(b"content-type", b"text/plain")], [b"Synthetic complete permitted copy\n"])]
        candidate = self.acquire()
        self.permission("denied")
        with self.assertRaisesRegex(AttachmentProblem, "rights-denied"):
            self.commit(candidate)
        self.assertEqual(0, self.count("document_attachment_assertions"))
        self.assertEqual(1, self.count("reconciliation_assertions"))

    def test_expected_checksum_encoding_and_truncation_never_publish(self):
        from research_observatory_core.ports.acquisition import AcquisitionProblem
        from research_observatory_core.ports.object_store import ObjectStoreProblem

        self.permission()
        with self.assertRaises(ObjectStoreProblem):
            self.acquire(expected_sha256="0" * 64)
        for headers, chunks, code in (
            (
                [(b"content-type", b"text/plain"), (b"content-encoding", b"gzip")],
                [b"untrusted compressed"],
                "content-type-denied",
            ),
            ([(b"content-type", b"text/plain"), (b"content-length", b"40")], [b"too short"], "truncated"),
            (
                [(b"content-type", b"text/plain"), (b"content-type", b"application/pdf")],
                [b"ambiguous"],
                "response-invalid",
            ),
        ):
            self.responses = [(200, headers, chunks)]
            with self.subTest(code=code), self.assertRaisesRegex(AcquisitionProblem, code):
                self.acquire()
        self.assertEqual(0, self.count("document_attachment_candidates"))
        self.assertEqual(0, self.count("document_acquisition_sources"))
        self.assertEqual(4, self.count("acquisition_attempt_results"))

    def test_cancellation_deadline_and_bounded_retry_keep_durable_requests(self):
        from research_observatory_core.domain_contracts import new_uuid_v7
        from research_observatory_core.ports.acquisition import AcquisitionProblem
        from research_observatory_core.ports.object_store import ObjectStagingCancelled

        self.permission()
        preview = self.service.preview(self.selection(), actor=self.actor)
        with self.assertRaises(ObjectStagingCancelled):
            self.service.acquire(
                preview.preview_id,
                confirmation=preview.confirmation,
                operation_id=new_uuid_v7(),
                cancellation_requested=lambda: True,
            )
        self.assertEqual([], self.calls)
        self.responses = [(503, [(b"retry-after", b"120")], [])]
        with self.assertRaisesRegex(AcquisitionProblem, "network-unavailable"):
            self.acquire()
        self.responses = [(503, [], [])] * 3
        with self.assertRaisesRegex(AcquisitionProblem, "network-unavailable"):
            self.acquire()
        self.assertEqual(4, len(self.calls))
        self.responses = [(200, [(b"content-type", b"text/plain")], [b"Synthetic late content\n"])]
        self.during_stream = lambda: setattr(self.fixture.clock, "seconds", self.fixture.clock.seconds + 120)
        with self.assertRaisesRegex(AcquisitionProblem, "network-timeout"):
            self.acquire()
        self.assertEqual(0, self.count("document_attachment_candidates"))
        self.assertEqual(4, self.count("acquisition_attempt_results"))

    def test_confirmation_restart_and_duplicate_operation_dispatch_no_extra_copy(self):
        from research_observatory_core.acquisition.service import OpenAccessAcquisitionService
        from research_observatory_core.domain_contracts import new_uuid_v7
        from research_observatory_core.ports.acquisition import AcquisitionProblem

        self.permission()
        preview = self.service.preview(self.selection(), actor=self.actor)
        operation = new_uuid_v7()
        with self.assertRaisesRegex(AcquisitionProblem, "confirmation-required"):
            self.service.acquire(
                preview.preview_id, confirmation="wrong", operation_id=operation, cancellation_requested=lambda: False
            )
        restarted = OpenAccessAcquisitionService(
            self.repository,
            self.attachments,
            session_id=self.session,
            authority_guard=self.service.guard,
            transport=self.transport,
        )
        with self.assertRaisesRegex(AcquisitionProblem, "confirmation-required"):
            restarted.acquire(
                preview.preview_id,
                confirmation=preview.confirmation,
                operation_id=operation,
                cancellation_requested=lambda: False,
            )
        self.service.acquire(
            preview.preview_id,
            confirmation=preview.confirmation,
            operation_id=operation,
            cancellation_requested=lambda: False,
        )
        preview = self.service.preview(self.selection(), actor=self.actor)
        with self.assertRaisesRegex(AcquisitionProblem, "operation-conflict"):
            self.service.acquire(
                preview.preview_id,
                confirmation=preview.confirmation,
                operation_id=operation,
                cancellation_requested=lambda: False,
            )
        self.assertEqual(1, len(self.calls))
        self.assertEqual(1, self.count("document_attachment_candidates"))
        self.assertEqual(1, self.count("acquisition_attempt_results"))

    def test_current_privacy_denies_previously_confirmed_egress(self):
        from research_observatory_core.corpus.membership import CorpusProblem
        from research_observatory_core.domain_contracts import new_uuid_v7

        self.permission()
        preview = self.service.preview(self.selection(), actor=self.actor)
        self.fixture.policy(False)
        with self.assertRaises(CorpusProblem):
            self.service.acquire(
                preview.preview_id,
                confirmation=preview.confirmation,
                operation_id=new_uuid_v7(),
                cancellation_requested=lambda: False,
            )
        self.assertEqual([], self.calls)
        self.assertEqual(0, self.count("acquisition_attempts"))

    def test_missing_expected_checksum_stays_missing_and_immutable_facts_are_atomic(self):
        from research_observatory_core.storage import open_canonical_database

        self.permission()
        candidate = self.acquire()
        attachment = self.commit(candidate)
        _, receipt = self.repository.source_for_revision(attachment.document_revision_id, actor=self.actor)
        self.assertIsNone(receipt.expected_sha256)
        with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
            for table in (
                "acquisition_locations",
                "acquisition_attempts",
                "acquisition_attempt_results",
                "document_acquisition_sources",
            ):
                with self.subTest(table=table), self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                    db.execute(f"DELETE FROM {table}")
            for row in db.execute(
                "SELECT revision_id FROM acquisition_attempts UNION ALL "
                "SELECT revision_id FROM acquisition_attempt_results"
            ):
                self.assertEqual(
                    1, db.execute("SELECT count(*) FROM provenance_events WHERE revision_id=?", (row[0],)).fetchone()[0]
                )
                self.assertEqual(
                    1, db.execute("SELECT count(*) FROM outbox_events WHERE revision_id=?", (row[0],)).fetchone()[0]
                )


if __name__ == "__main__":
    unittest.main()
