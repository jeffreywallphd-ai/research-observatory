"""Encrypted attachment staging cannot publish an uninspected source."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from unittest.mock import patch
from zipfile import ZipFile

from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.document_attachment_repository import (  # noqa: E402
    AttachmentProblem,
    LocalDocumentAttachmentService,
)
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.migrations import runner  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.object_store import (  # noqa: E402
    ObjectAccessDenied,
    ObjectConflict,
    ObjectCorrupt,
    ObjectPutCommand,
    ObjectStagingCancelled,
    ObjectStoragePressure,
    StoragePolicy,
)
from research_observatory_core.ports.reconciliation import ReconciliationActor  # noqa: E402
from research_observatory_core.ports.rights import RightsPermissionDraft  # noqa: E402
from research_observatory_core.reconciliation.contracts import SourceAddress  # noqa: E402
from research_observatory_core.reconciliation.exact import IdentifierAssertion  # noqa: E402
from research_observatory_core.reconciliation.versions import (  # noqa: E402
    VersionCommand,
    VersionDate,
    VersionDefinition,
    VersionPlan,
)
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository  # noqa: E402
from research_observatory_core.rights_policy import RightsUse  # noqa: E402
from research_observatory_core.rights_repository import SqliteRightsRepository  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    _schema_fingerprint,
    development_plaintext_database_fixture,
    open_canonical_database,
)

from tests.corpus import test_repository as corpus_fixtures  # noqa: E402
from tests.data import test_encrypted_object_store as object_fixtures  # noqa: E402

CREATED_AT = object_fixtures.CREATED_AT
PROJECT_ID = object_fixtures.PROJECT_ID
MemoryKeyProvider = object_fixtures.MemoryKeyProvider


class DocumentInspectionAdapterTests(unittest.TestCase):
    def test_worker_denial_crosses_port_as_content_free_problem(self) -> None:
        from research_observatory_core.document_attachment_repository import _inspect_signed_worker
        from research_observatory_core.ports.document_attachments import DocumentInspectionProblem

        from workers.document.inspection import DocumentInspectionError

        with (
            patch(
                "workers.windows.document_launcher.inspect_document",
                side_effect=DocumentInspectionError("password-protected"),
            ),
            self.assertRaises(DocumentInspectionProblem) as caught,
        ):
            _inspect_signed_worker(
                io.BytesIO(b"synthetic"), filename="synthetic.pdf", declared_media_type="application/pdf", cancel=None
            )
        self.assertEqual("password-protected", caught.exception.code)


class AttachmentStagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = object_fixtures.EncryptedObjectStoreTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.store = create_local_object_store(
            self.fixture.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v1": self.fixture.v1}, "object-key-v1"),
        )

    @staticmethod
    def command() -> ObjectPutCommand:
        return ObjectPutCommand(
            media_type="application/octet-stream",
            rights_status="allowed",
            protection_profile="project-encrypted-v1",
            retention_class="project-lifetime",
            creation_source="local-import",
            created_at=CREATED_AT,
        )

    def test_inspection_sees_exact_encrypted_staging_before_publication(self) -> None:
        content = b"%PDF-1.7\nSynthetic document bytes\n%%EOF\n"
        observed: list[bytes] = []

        def inspector(source, digest, length):
            with open_canonical_database(
                self.fixture.project / "state/project.sqlite3", expected_project_id=PROJECT_ID
            ) as db:
                self.assertEqual(0, db.execute("SELECT COUNT(*) FROM object_records").fetchone()[0])
            self.assertEqual([], [p for p in (self.fixture.project / "objects").rglob("*") if p.is_file()])
            staged = [p for p in (self.fixture.project / ".tmp/object-store").rglob("*") if p.is_file()]
            self.assertEqual(1, len(staged))
            self.assertNotIn(content, staged[0].read_bytes())
            value = source.read(1024)
            observed.append(value)
            self.assertEqual(hashlib.sha256(value).hexdigest(), digest)
            self.assertEqual(len(value), length)
            return "application/pdf"

        stored = self.store.put_inspected(
            io.BytesIO(content), self.command(), inspector, max_plaintext_bytes=128 * 1024 * 1024
        )
        self.assertEqual([content], observed)
        self.assertEqual("application/pdf", stored.media_type)
        self.assertEqual(hashlib.sha256(content).hexdigest(), stored.object_sha256)

    def test_new_adapter_preserves_another_adapters_active_encrypted_stage(self) -> None:
        content = b"synthetic active transfer"

        def inspector(source, digest, length):
            staged = tuple((self.fixture.project / ".tmp/object-store").glob("*.partial"))
            self.assertEqual(1, len(staged))
            identity = staged[0].stat().st_ino
            other = create_local_object_store(
                self.fixture.project,
                PROJECT_ID,
                key_provider=MemoryKeyProvider({"object-key-v1": self.fixture.v1}, "object-key-v1"),
            )
            self.assertEqual(identity, staged[0].stat().st_ino)
            self.assertEqual(content, source.read(1024))
            from research_observatory_core.ports.object_store import ObjectNotFound

            with self.assertRaises(ObjectNotFound):
                other.metadata(hashlib.sha256(content).hexdigest())
            return "text/plain"

        result = self.store.put_inspected(io.BytesIO(content), self.command(), inspector, max_plaintext_bytes=128)
        self.assertEqual(hashlib.sha256(content).hexdigest(), result.object_sha256)
        self.assertEqual((), tuple((self.fixture.project / ".tmp/object-store").glob("*.partial")))

    def test_project_open_upgrade_rejects_live_stage_without_deleting_it(self) -> None:
        from research_observatory_core.object_store import upgrade_local_object_envelopes
        from research_observatory_core.ports.object_store import ObjectBusy

        content = b"synthetic active encrypted stage"

        def inspector(source, digest, length):
            staged = tuple((self.fixture.project / ".tmp/object-store").glob("*.partial"))
            self.assertEqual(1, len(staged))
            before = staged[0].read_bytes()
            with self.assertRaises(ObjectBusy):
                upgrade_local_object_envelopes(
                    self.fixture.project,
                    PROJECT_ID,
                    key_provider=MemoryKeyProvider({"object-key-v1": self.fixture.v1}, "object-key-v1"),
                )
            self.assertEqual(before, staged[0].read_bytes())
            self.assertEqual(content, source.read())
            return "text/plain"

        stored = self.store.put_inspected(
            io.BytesIO(content), self.command(), inspector, max_plaintext_bytes=128 * 1024 * 1024
        )
        self.assertEqual(hashlib.sha256(content).hexdigest(), stored.object_sha256)

    def test_reconciliation_never_deletes_a_foreign_partial_name(self) -> None:
        from research_observatory_core.ports.object_store import ObjectStagingCleanupRequired

        foreign = self.fixture.project / ".tmp/object-store/unrelated.partial"
        foreign.parent.mkdir(exist_ok=True)
        foreign.write_bytes(b"Synthetic unrelated retained bytes")
        with self.assertRaises(ObjectStagingCleanupRequired):
            create_local_object_store(
                self.fixture.project,
                PROJECT_ID,
                key_provider=MemoryKeyProvider({"object-key-v1": self.fixture.v1}, "object-key-v1"),
            )
        self.assertEqual(b"Synthetic unrelated retained bytes", foreign.read_bytes())

    def test_rejected_inspection_leaves_no_canonical_object(self) -> None:
        content = b"synthetic unsupported content"

        def reject(source, digest, length):
            self.assertEqual(content, source.read(1024))
            raise ValueError("unsupported-format")

        with self.assertRaisesRegex(ValueError, "unsupported-format"):
            self.store.put_inspected(io.BytesIO(content), self.command(), reject, max_plaintext_bytes=128 * 1024 * 1024)
        with open_canonical_database(
            self.fixture.project / "state/project.sqlite3", expected_project_id=PROJECT_ID
        ) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM object_records").fetchone()[0])
        self.assertEqual([], [p for p in (self.fixture.project / "objects").rglob("*") if p.is_file()])
        self.assertEqual([], [p for p in (self.fixture.project / ".tmp/object-store").rglob("*") if p.is_file()])

    def test_slow_inspection_does_not_block_an_existing_verified_read(self) -> None:
        prior = self.store.put(io.BytesIO(b"previous object"), self.command())
        entered = threading.Event()
        release = threading.Event()
        errors: list[BaseException] = []

        def inspector(source, digest, length):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("inspection gate")
            self.assertEqual(b"new object", source.read())
            return "text/plain"

        def run_inspection():
            try:
                self.store.put_inspected(io.BytesIO(b"new object"), self.command(), inspector, max_plaintext_bytes=128)
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=run_inspection)
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            read_done = threading.Event()

            def read_prior():
                try:
                    with self.store.open(prior.object_sha256, purpose="test-verification") as reader:
                        self.assertEqual(b"previous object", reader.read())
                except BaseException as error:
                    errors.append(error)
                finally:
                    read_done.set()

            read_thread = threading.Thread(target=read_prior)
            read_thread.start()
            self.assertTrue(read_done.wait(2), "verified read waited behind document inspection")
            read_thread.join(2)
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], errors)

    def test_slow_selected_stream_does_not_block_an_existing_verified_read(self) -> None:
        prior = self.store.put(io.BytesIO(b"previous object"), self.command())
        entered = threading.Event()
        release = threading.Event()
        read_done = threading.Event()
        errors: list[BaseException] = []

        class SlowSource(io.BytesIO):
            def read(self, size=-1):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("selected source stalled")
                return super().read(size)

        def upload():
            try:
                self.store.put_inspected(
                    SlowSource(b"new object"),
                    self.command(),
                    lambda source, _digest, _length: (source.read(), "text/plain")[1],
                    max_plaintext_bytes=128,
                )
            except BaseException as error:
                errors.append(error)

        def read_prior():
            try:
                with self.store.open(prior.object_sha256, purpose="test-verification") as reader:
                    self.assertEqual(b"previous object", reader.read())
            except BaseException as error:
                errors.append(error)
            finally:
                read_done.set()

        uploader = threading.Thread(target=upload)
        uploader.start()
        try:
            self.assertTrue(entered.wait(2))
            reader = threading.Thread(target=read_prior)
            reader.start()
            self.assertTrue(read_done.wait(1), "verified read waited behind selected-source upload")
            reader.join(2)
        finally:
            release.set()
            uploader.join(5)
        self.assertFalse(uploader.is_alive())
        self.assertEqual([], errors)

    def test_inspected_upload_cancellation_callback_does_not_hold_store_lock(self) -> None:
        prior = self.store.put(io.BytesIO(b"previous object"), self.command())
        entered = threading.Event()
        project_lifecycle_lock = threading.Lock()
        read_done = threading.Event()
        errors: list[BaseException] = []

        def cancellation_requested() -> bool:
            entered.set()
            # The Core callback acquires this lock to recheck its native
            # session. Another Core operation may hold it while opening an
            # existing object, which would invert lifecycle -> store order.
            with project_lifecycle_lock:
                pass
            return False

        def upload() -> None:
            try:
                self.store.put_inspected(
                    io.BytesIO(b"new object"),
                    self.command(),
                    lambda source, _digest, _length: (source.read(), "text/plain")[1],
                    max_plaintext_bytes=128,
                    cancellation_requested=cancellation_requested,
                )
            except BaseException as error:
                errors.append(error)

        def read_prior() -> None:
            try:
                with self.store.open(prior.object_sha256, purpose="test-verification") as reader:
                    self.assertEqual(b"previous object", reader.read())
            except BaseException as error:
                errors.append(error)
            finally:
                read_done.set()

        project_lifecycle_lock.acquire()
        uploader = threading.Thread(target=upload)
        uploader.start()
        try:
            self.assertTrue(entered.wait(2))
            reader = threading.Thread(target=read_prior)
            reader.start()
            self.assertTrue(read_done.wait(1), "verified read waited behind upload cancellation callback")
            reader.join(2)
        finally:
            project_lifecycle_lock.release()
            uploader.join(5)
        self.assertFalse(uploader.is_alive())
        self.assertEqual([], errors)

    def test_cancellation_after_inspector_verdict_prevents_publication(self) -> None:
        cancelled = False

        def inspector(source, digest, length):
            nonlocal cancelled
            self.assertEqual(b"document", source.read())
            cancelled = True
            return "text/plain"

        with self.assertRaises(ObjectStagingCancelled):
            self.store.put_inspected(
                io.BytesIO(b"document"),
                self.command(),
                inspector,
                max_plaintext_bytes=128,
                cancellation_requested=lambda: cancelled,
            )
        with open_canonical_database(
            self.fixture.project / "state/project.sqlite3", expected_project_id=PROJECT_ID
        ) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM object_records").fetchone()[0])

    def test_staging_identity_change_after_verdict_is_rejected(self) -> None:
        with (
            patch("research_observatory_core.object_store._EncryptedReader.matches", return_value=False),
            self.assertRaises(ObjectCorrupt),
        ):
            self.store.put_inspected(
                io.BytesIO(b"document"),
                self.command(),
                lambda stream, _digest, _length: (stream.read(), "text/plain")[1],
                max_plaintext_bytes=128,
            )
        with open_canonical_database(
            self.fixture.project / "state/project.sqlite3", expected_project_id=PROJECT_ID
        ) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM object_records").fetchone()[0])

    def test_inspected_stage_substitution_before_verdict_is_rejected(self) -> None:
        from research_observatory_core import object_store as store_module

        original = store_module._stream_to_staging
        inspection_called = False

        def substituted(*args, **kwargs):
            staged, digest, length, envelope, identity = original(*args, **kwargs)
            ciphertext = staged.read_bytes()
            staged.rename(staged.with_suffix(".held"))
            staged.write_bytes(ciphertext)
            return staged, digest, length, envelope, identity

        def inspector(_source, _digest, _length):
            nonlocal inspection_called
            inspection_called = True
            return "text/plain"

        with (
            patch.object(store_module, "_stream_to_staging", side_effect=substituted),
            self.assertRaises(ObjectCorrupt),
        ):
            self.store.put_inspected(io.BytesIO(b"document"), self.command(), inspector, max_plaintext_bytes=128)
        self.assertFalse(inspection_called)
        with open_canonical_database(
            self.fixture.project / "state/project.sqlite3", expected_project_id=PROJECT_ID
        ) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM object_records").fetchone()[0])

    def test_disk_reserve_is_rechecked_after_slow_verdict(self) -> None:
        low = False

        def inspector(source, _digest, _length):
            nonlocal low
            self.assertEqual(b"document", source.read())
            low = True
            return "text/plain"

        with (
            patch(
                "research_observatory_core.object_store.shutil.disk_usage",
                side_effect=lambda _path: SimpleNamespace(free=0 if low else 10**12),
            ),
            self.assertRaises(ObjectStoragePressure),
        ):
            self.store.put_inspected(io.BytesIO(b"document"), self.command(), inspector, max_plaintext_bytes=128)
        with open_canonical_database(
            self.fixture.project / "state/project.sqlite3", expected_project_id=PROJECT_ID
        ) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM object_records").fetchone()[0])

    def test_concurrent_object_consumes_quota_during_inspected_upload(self) -> None:
        baseline = self.store.usage().project_byte_count
        capped = create_local_object_store(
            self.fixture.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v1": self.fixture.v1}, "object-key-v1"),
            storage_policy=StoragePolicy(project_hard_limit_bytes=baseline + 100, minimum_free_bytes=0),
        )
        entered = threading.Event()
        release = threading.Event()
        errors: list[BaseException] = []
        inspection_called = False

        class SlowSource(io.BytesIO):
            def read(self, size=-1):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("selected source stalled")
                return super().read(size)

        def inspect(source, _digest, _length):
            nonlocal inspection_called
            inspection_called = True
            return "text/plain"

        def upload() -> None:
            try:
                capped.put_inspected(SlowSource(b"document"), self.command(), inspect, max_plaintext_bytes=128)
            except BaseException as error:
                errors.append(error)

        uploader = threading.Thread(target=upload)
        uploader.start()
        try:
            self.assertTrue(entered.wait(2))
            other = capped.put(io.BytesIO(b"concurrent"), self.command())
            self.assertEqual(hashlib.sha256(b"concurrent").hexdigest(), other.object_sha256)
        finally:
            release.set()
            uploader.join(5)
        self.assertFalse(uploader.is_alive())
        self.assertFalse(inspection_called)
        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], ObjectStoragePressure)
        with open_canonical_database(
            self.fixture.project / "state/project.sqlite3", expected_project_id=PROJECT_ID
        ) as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM object_records").fetchone()[0])

    def test_final_quota_recheck_counts_inspected_staging_only_once(self) -> None:
        baseline = self.store.usage().project_byte_count
        # One encrypted secretstream frame for eight plaintext bytes occupies
        # 4 magic + 24 header + 4 frame length + 8 payload + 17 tag bytes.
        ciphertext_bytes = 57
        capped = create_local_object_store(
            self.fixture.project,
            PROJECT_ID,
            key_provider=MemoryKeyProvider({"object-key-v1": self.fixture.v1}, "object-key-v1"),
            storage_policy=StoragePolicy(
                project_hard_limit_bytes=baseline + ciphertext_bytes + 10,
                minimum_free_bytes=0,
            ),
        )
        stored = capped.put_inspected(
            io.BytesIO(b"document"),
            self.command(),
            lambda stream, _digest, _length: (stream.read(), "text/plain")[1],
            max_plaintext_bytes=128,
        )
        self.assertEqual(hashlib.sha256(b"document").hexdigest(), stored.object_sha256)

    def test_inspected_copy_deduplicates_prior_allowed_bytes_without_inheriting_copy_rights(self) -> None:
        content = b"same document bytes"
        prior = self.store.put(io.BytesIO(content), replace(self.command(), media_type="text/plain"))
        candidate_command = replace(self.command(), rights_status="unknown")
        repeated = self.store.put_inspected(
            io.BytesIO(content),
            candidate_command,
            lambda source, _digest, _length: (source.read(), "text/plain")[1],
            max_plaintext_bytes=128,
        )
        self.assertEqual(prior.object_sha256, repeated.object_sha256)
        self.assertEqual("allowed", repeated.rights_status)
        with open_canonical_database(
            self.fixture.project / "state/project.sqlite3", expected_project_id=PROJECT_ID
        ) as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM object_records").fetchone()[0])
        with self.assertRaises(ObjectConflict):
            self.store.put_inspected(
                io.BytesIO(content),
                candidate_command,
                lambda source, _digest, _length: (source.read(), "application/pdf")[1],
                max_plaintext_bytes=128,
            )


class LocalAttachmentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = corpus_fixtures.CorpusRepositoryTests(methodName="runTest")
        self.corpus.setUp()
        self.addCleanup(self.corpus.doCleanups)
        f = self.corpus
        self.project_root = f.database.parent.parent
        self.keys = MemoryKeyProvider({"object-key-v1": b"Z" * 32}, "object-key-v1")
        self.store = create_local_object_store(self.project_root, f.project, key_provider=self.keys)

        def inspector(stream, *, filename, declared_media_type, cancel):
            self.assertEqual("paper.txt", filename)
            content = stream.read()
            return SimpleNamespace(
                format="txt",
                media_type="text/plain",
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )

        self.service = LocalDocumentAttachmentService(f.database, f.project, self.store, inspector=inspector)
        self.rights = SqliteRightsRepository(f.database, f.project)
        self.version_repo = SqliteReconciliationRepository(f.database, f.project)
        self.reconcile_actor = ReconciliationActor(new_uuid_v7(), "b" * 32, f.actor.occurred_at, "c" * 64, "d" * 64)
        work_ids = (f.work_id,)

        def resolve(_address):
            return f.source

        context = self.version_repo.version_context(work_ids, resolve=resolve)
        plan = VersionPlan(
            action="register",
            work_ids=work_ids,
            context_sha256=context.fingerprint,
            rationale="Synthetic human Version selection",
            definition=VersionDefinition(
                kind="version-of-record",
                assertion_revision_ids=(self._assertion_id(),),
                date=VersionDate(precision="not-reported", value=None),
            ),
        )
        preview = self.version_repo.preview_versions(plan, actor=self.reconcile_actor, resolve=resolve)
        outcome = self.version_repo.decide_versions(
            VersionCommand(command_id=new_uuid_v7(), plan=plan, expected_preview_sha256=preview.preview_sha256),
            actor=self.reconcile_actor,
            resolve=resolve,
        )
        self.version = outcome.version_revisions[0]
        with open_canonical_database(f.database, expected_project_id=f.project) as db:
            self.work_revision_id = str(
                db.execute(
                    "SELECT revision_id FROM aggregate_revisions WHERE project_id=? AND aggregate_id=? "
                    "ORDER BY revision DESC LIMIT 1",
                    (f.project, f.work_id),
                ).fetchone()[0]
            )

    def _assertion_id(self) -> str:
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            return str(
                db.execute(
                    "SELECT assertion_revision_id FROM reconciliation_work_members "
                    "WHERE project_id=? AND work_revision_id=?",
                    (self.corpus.project, getattr(self, "work_revision_id", self.corpus.work_revision_id)),
                ).fetchone()[0]
            )

    def stage(self):
        f = self.corpus
        return self.service.stage(
            io.BytesIO(b"Synthetic plain text full text\n"),
            source_name="paper.txt",
            declared_media_type="text/plain",
            source_assertion_revision_id=self._assertion_id(),
            work_id=f.work_id,
            work_revision_id=self.work_revision_id,
            version_id=self.version.version_id,
            version_revision_id=self.version.revision_id,
            actor=f.actor,
        )

    def stage_operation(self, operation_id: str, session_id: str):
        f = self.corpus
        return self.service.stage(
            io.BytesIO(b"Synthetic plain text full text\n"),
            source_name="paper.txt",
            declared_media_type="text/plain",
            source_assertion_revision_id=self._assertion_id(),
            work_id=f.work_id,
            work_revision_id=self.work_revision_id,
            version_id=self.version.version_id,
            version_revision_id=self.version.revision_id,
            actor=f.actor,
            operation_id=operation_id,
            session_id=session_id,
        )

    def test_project_only_decision_binds_operation_and_publishes_exact_copy_rights_atomically(self) -> None:
        operation_id, session_id, command_id = new_uuid_v7(), "d" * 32, new_uuid_v7()
        candidate = self.stage_operation(operation_id, session_id)
        first = self.service.status(
            source_assertion_revision_id=candidate.source_assertion_revision_id,
            work_id=candidate.work_id,
            work_revision_id=candidate.work_revision_id,
            version_id=candidate.version_id,
            version_revision_id=candidate.version_revision_id,
            operation_id=operation_id,
            command_id=None,
            session_id=session_id,
            actor=self.corpus.actor,
        )
        self.assertEqual("candidate", first.state)
        self.assertEqual(candidate.candidate_id, first.candidate_id)
        attachment = self.service.commit(
            candidate.candidate_id,
            confirmation_sha256=candidate.candidate_sha256,
            command_id=command_id,
            actor=self.corpus.actor,
            operation_id=operation_id,
            session_id=session_id,
            match_confirmed=True,
            permitted_use="project-only",
            exact_selection=(
                candidate.source_assertion_revision_id,
                candidate.work_id,
                candidate.work_revision_id,
                candidate.version_id,
                candidate.version_revision_id,
            ),
        )
        self.assertEqual(candidate.version_revision_id, attachment.version_revision_id)
        restarted = LocalDocumentAttachmentService(self.corpus.database, self.corpus.project, self.store)
        status = restarted.status(
            source_assertion_revision_id=candidate.source_assertion_revision_id,
            work_id=candidate.work_id,
            work_revision_id=candidate.work_revision_id,
            version_id=candidate.version_id,
            version_revision_id=candidate.version_revision_id,
            operation_id=operation_id,
            command_id=command_id,
            session_id="e" * 32,
            actor=self.corpus.actor,
        )
        self.assertEqual("committed", status.state)
        self.assertEqual(attachment.attachment_id, status.attachment_id)
        self.assertEqual(attachment.document_revision_id, status.document_revision_id)
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM document_attachment_operations").fetchone()[0])
        policy = self.rights.current(candidate.rights_subject, actor=self.corpus.actor)
        self.assertIsNotNone(policy)
        assert policy is not None
        self.assertEqual(
            {("store", "document-attachment"), ("inspect", "document-analysis")},
            {(permission.use.action, permission.use.purpose) for permission in policy.permissions},
        )

    def test_operation_substitution_and_restart_unresolved_candidate_fail_closed(self) -> None:
        operation_id, session_id = new_uuid_v7(), "d" * 32
        candidate = self.stage_operation(operation_id, session_id)
        selected = dict(
            source_assertion_revision_id=candidate.source_assertion_revision_id,
            work_id=candidate.work_id,
            work_revision_id=candidate.work_revision_id,
            version_id=candidate.version_id,
            version_revision_id=candidate.version_revision_id,
        )
        self.assertEqual(
            "unresolved",
            self.service.status(
                **selected,
                operation_id=operation_id,
                command_id=new_uuid_v7(),
                session_id=session_id,
                actor=self.corpus.actor,
            ).state,
        )
        self.assertEqual(
            "stale-session",
            self.service.status(
                **selected,
                operation_id=operation_id,
                command_id=new_uuid_v7(),
                session_id="e" * 32,
                actor=self.corpus.actor,
            ).state,
        )
        self.assertEqual(
            "unavailable",
            self.service.status(
                **{**selected, "version_revision_id": new_uuid_v7()},
                operation_id=operation_id,
                command_id=None,
                session_id=session_id,
                actor=self.corpus.actor,
            ).state,
        )
        with self.assertRaisesRegex(AttachmentProblem, "operation|association"):
            self.service.commit(
                candidate.candidate_id,
                confirmation_sha256=candidate.candidate_sha256,
                command_id=new_uuid_v7(),
                actor=self.corpus.actor,
                operation_id=new_uuid_v7(),
                session_id=session_id,
                match_confirmed=True,
                permitted_use="project-only",
                exact_selection=tuple(selected.values()),
            )

    def test_explicit_project_only_does_not_override_existing_denial_and_audits_it(self) -> None:
        operation_id, session_id = new_uuid_v7(), "d" * 32
        candidate = self.stage_operation(operation_id, session_id)
        self.publish_right(candidate, value="denied")
        with self.assertRaisesRegex(AttachmentProblem, "attachment-rights-denied"):
            self.service.commit(
                candidate.candidate_id,
                confirmation_sha256=candidate.candidate_sha256,
                command_id=new_uuid_v7(),
                actor=self.corpus.actor,
                operation_id=operation_id,
                session_id=session_id,
                match_confirmed=True,
                permitted_use="project-only",
                exact_selection=(
                    candidate.source_assertion_revision_id,
                    candidate.work_id,
                    candidate.work_revision_id,
                    candidate.version_id,
                    candidate.version_revision_id,
                ),
            )
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_assertions").fetchone()[0])
            self.assertEqual(
                1,
                db.execute(
                    "SELECT COUNT(*) FROM rights_use_decisions WHERE event_kind='denied-attempt' AND use_action='store'"
                ).fetchone()[0],
            )

    def test_project_only_rights_publication_rolls_back_if_attachment_commit_interrupts(self) -> None:
        operation_id, session_id, command_id = new_uuid_v7(), "d" * 32, new_uuid_v7()
        candidate = self.stage_operation(operation_id, session_id)
        selection = (
            candidate.source_assertion_revision_id,
            candidate.work_id,
            candidate.work_revision_id,
            candidate.version_id,
            candidate.version_revision_id,
        )
        with (
            patch.object(self.service._rights, "evaluate_with_connection", side_effect=RuntimeError("synthetic stop")),
            self.assertRaisesRegex(RuntimeError, "synthetic stop"),
        ):
            self.service.commit(
                candidate.candidate_id,
                confirmation_sha256=candidate.candidate_sha256,
                command_id=command_id,
                actor=self.corpus.actor,
                operation_id=operation_id,
                session_id=session_id,
                match_confirmed=True,
                permitted_use="project-only",
                exact_selection=selection,
            )
        self.assertIsNone(self.rights.current(candidate.rights_subject, actor=self.corpus.actor))
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_assertions").fetchone()[0])
        attached = self.service.commit(
            candidate.candidate_id,
            confirmation_sha256=candidate.candidate_sha256,
            command_id=command_id,
            actor=self.corpus.actor,
            operation_id=operation_id,
            session_id=session_id,
            match_confirmed=True,
            permitted_use="project-only",
            exact_selection=selection,
        )
        self.assertEqual(candidate.version_revision_id, attached.version_revision_id)

    def publish_right(self, candidate, *, value="permitted", predecessor=None, inspect=False):
        actions: tuple[Literal["store", "inspect"], ...] = ("store", "inspect") if inspect else ("store",)
        return self.rights.publish_draft(
            candidate.rights_subject,
            tuple(
                RightsPermissionDraft(
                    use=RightsUse(
                        action=action,
                        purpose="document-attachment" if action == "store" else "document-analysis",
                        destination_kind="local-project",
                    ),
                    value=value,
                    basis="researcher-confirmed",
                    confidence="confirmed",
                    evidence_revision_ids=(candidate.source_assertion_revision_id,),
                    license_observation_revision_id=None,
                    entitlement_revision_id=None,
                    expires_at=None,
                )
                for action in actions
            ),
            predecessor,
            command_id=new_uuid_v7(),
            command_sha256="6" * 64,
            actor=self.corpus.actor,
        )

    def test_candidate_requires_exact_confirmation_and_current_copy_right_before_atomic_commit(self) -> None:
        candidate = self.stage()
        self.assertEqual("plain-text", candidate.format)
        self.assertTrue(candidate.confirmation_required)
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM documents WHERE object_sha256=?", (candidate.object_sha256,)
                ).fetchone()[0],
            )
            self.assertEqual(
                ("unknown", "available"),
                tuple(
                    db.execute(
                        "SELECT rights_status,storage_state FROM object_records WHERE project_id=? AND object_sha256=?",
                        (self.corpus.project, candidate.object_sha256),
                    ).fetchone()
                ),
            )
        with self.assertRaises(ObjectAccessDenied):
            self.store.open(candidate.object_sha256, purpose="document-analysis")
        command_id = new_uuid_v7()
        with self.assertRaisesRegex(AttachmentProblem, "attachment-confirmation-required"):
            self.service.commit(
                candidate.candidate_id, confirmation_sha256="0" * 64, command_id=command_id, actor=self.corpus.actor
            )
        with self.assertRaisesRegex(AttachmentProblem, "attachment-rights-denied"):
            self.service.commit(
                candidate.candidate_id,
                confirmation_sha256=candidate.candidate_sha256,
                command_id=command_id,
                actor=self.corpus.actor,
            )
        allowed = self.publish_right(candidate)
        attachment = self.service.commit(
            candidate.candidate_id,
            confirmation_sha256=candidate.candidate_sha256,
            command_id=command_id,
            actor=self.corpus.actor,
        )
        self.assertEqual(allowed.revision_id, attachment.rights_policy_revision_id)
        self.assertEqual(candidate.version_revision_id, attachment.version_revision_id)
        restarted = LocalDocumentAttachmentService(self.corpus.database, self.corpus.project, self.store)
        self.assertEqual(candidate, restarted.load_candidate(candidate.candidate_id, actor=self.corpus.actor))
        self.assertEqual(
            attachment,
            restarted.commit(
                candidate.candidate_id,
                confirmation_sha256=candidate.candidate_sha256,
                command_id=command_id,
                actor=self.corpus.actor,
            ),
        )
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM document_attachment_assertions").fetchone()[0])
            self.assertEqual(
                1,
                db.execute(
                    "SELECT COUNT(*) FROM documents WHERE revision_id=?", (attachment.document_revision_id,)
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                db.execute(
                    "SELECT COUNT(*) FROM provenance_events WHERE event_id=?", (attachment.provenance_event_id,)
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                db.execute("SELECT COUNT(*) FROM outbox_events WHERE outbox_id=?", (attachment.outbox_id,)).fetchone()[
                    0
                ],
            )

    def test_revoked_copy_right_denies_attachment_and_retains_denial_audit(self) -> None:
        candidate = self.stage()
        granted = self.publish_right(candidate)
        self.publish_right(candidate, value="denied", predecessor=granted.revision_id)
        with self.assertRaisesRegex(AttachmentProblem, "attachment-rights-denied"):
            self.service.commit(
                candidate.candidate_id,
                confirmation_sha256=candidate.candidate_sha256,
                command_id=new_uuid_v7(),
                actor=self.corpus.actor,
            )
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_assertions").fetchone()[0])
            self.assertEqual(
                1,
                db.execute(
                    "SELECT COUNT(*) FROM rights_use_decisions WHERE event_kind='denied-attempt' AND use_action='store'"
                ).fetchone()[0],
            )

    def test_exact_attached_read_uses_current_inspect_right_and_generic_hash_read_denies(self) -> None:
        candidate = self.stage()
        granted = self.publish_right(candidate, inspect=True)
        attachment = self.service.commit(
            candidate.candidate_id,
            confirmation_sha256=candidate.candidate_sha256,
            command_id=new_uuid_v7(),
            actor=self.corpus.actor,
        )
        with self.assertRaises(ObjectAccessDenied):
            self.store.open(candidate.object_sha256, purpose="document-analysis")
        with self.store.open_document_attachment(
            attachment.attachment_id, attachment.document_revision_id, actor=self.corpus.actor
        ) as reader:
            self.assertEqual(b"Synthetic plain text full text\n", reader.read())
        with self.assertRaises(ObjectAccessDenied):
            self.store.open_document_attachment(attachment.attachment_id, new_uuid_v7(), actor=self.corpus.actor)
        self.publish_right(candidate, value="denied", predecessor=granted.revision_id, inspect=True)
        with self.assertRaises(ObjectAccessDenied):
            self.store.open_document_attachment(
                attachment.attachment_id, attachment.document_revision_id, actor=self.corpus.actor
            )

    def test_interrupted_candidate_write_retries_same_encrypted_hash_after_restart(self) -> None:
        original = self.service._current_binding
        calls = 0

        def interrupt_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise AttachmentProblem("attachment-association-stale")
            return original(*args, **kwargs)

        with (
            patch.object(self.service, "_current_binding", side_effect=interrupt_second),
            self.assertRaisesRegex(AttachmentProblem, "attachment-association-stale"),
        ):
            self.stage()
        orphan = hashlib.sha256(b"Synthetic plain text full text\n").hexdigest()
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_candidates").fetchone()[0])
            self.assertEqual(
                0, db.execute("SELECT COUNT(*) FROM documents WHERE object_sha256=?", (orphan,)).fetchone()[0]
            )
            self.assertEqual(
                "available",
                db.execute("SELECT storage_state FROM object_records WHERE object_sha256=?", (orphan,)).fetchone()[0],
            )
        self.service = LocalDocumentAttachmentService(
            self.corpus.database, self.corpus.project, self.store, inspector=self.service._inspector
        )
        candidate = self.stage()
        self.assertEqual(orphan, candidate.object_sha256)
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            self.assertEqual(
                1, db.execute("SELECT COUNT(*) FROM object_records WHERE object_sha256=?", (orphan,)).fetchone()[0]
            )

    def test_version_from_another_work_cannot_be_substituted(self) -> None:
        imported = self.corpus._fixture
        imported.prepare_another(raw=b"title,doi\nOther synthetic paper,10.99999/synthetic-b\n")
        output = imported.publish()
        f = imported.fixture
        member = next(
            item
            for item in f.repository.manifest_members(output.revision_id, after=0, limit=100)
            if item.decision.included
        )
        address = SourceAddress(
            kind="import-member",
            context_id=f.inputs.preview.preview_id,
            revision_id=output.revision_id,
            ordinal=member.ordinal,
            record_key=member.record_key,
        )
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            raw_sha256 = str(
                db.execute(
                    "SELECT raw_sha256 FROM import_manifest_members "
                    "WHERE project_id=? AND manifest_revision_id=? AND ordinal=?",
                    (self.corpus.project, output.revision_id, member.ordinal),
                ).fetchone()[0]
            )
        second_source = self.corpus.source.model_copy(
            update={
                "address": address,
                "source_revision_id": member.source_record_revision_id,
                "identifiers": (IdentifierAssertion(scheme="doi", observed="10.99999/synthetic-b"),),
                "source_sha256": raw_sha256,
            }
        )
        second = self.version_repo.reconcile(
            address, command_id=new_uuid_v7(), actor=self.reconcile_actor, resolve=lambda _: second_source
        )
        assert second.work_id is not None
        self.assertNotEqual(self.corpus.work_id, second.work_id)
        context = self.version_repo.version_context((second.work_id,), resolve=lambda _: second_source)
        plan = VersionPlan(
            action="register",
            work_ids=(second.work_id,),
            context_sha256=context.fingerprint,
            rationale="Synthetic second WorkVersion",
            definition=VersionDefinition(
                kind="preprint",
                assertion_revision_ids=(second.assertion_revision_id,),
                date=VersionDate(precision="not-reported", value=None),
            ),
        )
        preview = self.version_repo.preview_versions(plan, actor=self.reconcile_actor, resolve=lambda _: second_source)
        other_version = self.version_repo.decide_versions(
            VersionCommand(command_id=new_uuid_v7(), plan=plan, expected_preview_sha256=preview.preview_sha256),
            actor=self.reconcile_actor,
            resolve=lambda _: second_source,
        ).version_revisions[0]
        with self.assertRaisesRegex(AttachmentProblem, "attachment-association-stale"):
            self.service.stage(
                io.BytesIO(b"Synthetic document"),
                source_name="paper.txt",
                declared_media_type="text/plain",
                source_assertion_revision_id=self._assertion_id(),
                work_id=self.corpus.work_id,
                work_revision_id=self.work_revision_id,
                version_id=other_version.version_id,
                version_revision_id=other_version.revision_id,
                actor=self.corpus.actor,
            )
        with open_canonical_database(self.corpus.database, expected_project_id=self.corpus.project) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_candidates").fetchone()[0])


class AttachmentMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((REPO / "tests/fixtures/documents/v21-predecessor.json").read_text(encoding="utf-8"))
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-document-v21-")
        self.addCleanup(self._cleanup)
        self.project = Path(self.temporary.name) / "project"
        with ZipFile(REPO / "tests/fixtures/documents/v21-predecessor.zip") as archive:
            for name in ("state/project.sqlite3", *(item["relativePath"] for item in self.manifest["ciphertext"])):
                target = self.project / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        self.database = self.project / "state/project.sqlite3"
        self.profile = development_plaintext_database_fixture()
        self.profile.__enter__()
        self.addCleanup(self.profile.__exit__, None, None, None)

    def _cleanup(self) -> None:
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
                check=False,
                timeout=30,
            )
        self.temporary.cleanup()

    def test_literal_populated_v21_migrates_without_changing_work_version_or_ciphertext(self) -> None:
        self.assertEqual(self.manifest["databaseSha256"], hashlib.sha256(self.database.read_bytes()).hexdigest())
        before = {
            item["relativePath"]: hashlib.sha256((self.project / item["relativePath"]).read_bytes()).hexdigest()
            for item in self.manifest["ciphertext"]
        }
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(21, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(
                self.manifest["schemaSha256"],
                __import__("research_observatory_core.storage", fromlist=["_schema_fingerprint"])._schema_fingerprint(
                    db
                ),
            )
            self.assertEqual(
                (self.manifest["versionId"], self.manifest["workId"]),
                (
                    db.execute(
                        "SELECT version_id FROM reconciliation_versions WHERE revision_id=?",
                        (self.manifest["versionRevisionId"],),
                    ).fetchone()[0],
                    db.execute(
                        "SELECT work_id FROM reconciliation_work_states WHERE revision_id=?",
                        (self.manifest["workRevisionId"],),
                    ).fetchone()[0],
                ),
            )
        plan = runner.plan_database_migration(self.database, expected_project_id=self.manifest["projectId"])
        self.assertEqual(
            (
                "0022_document_attachments",
                "0023_attachment_operations",
                "0024_open_access_acquisition",
                "0025_document_intake_recovery",
            ),
            plan.migration_ids,
        )
        result = runner.migrate_database(self.database, expected_project_id=self.manifest["projectId"])
        self.assertEqual("migrated", result.status)
        assert result.backup_relative_path is not None
        assert result.recovery_manifest_relative_path is not None
        recovery_schema = json.loads(
            (REPO / "packages/contracts/storage/sqlite-migration-recovery.schema.json").read_text(encoding="utf-8")
        )
        recovery_path = self.project / result.recovery_manifest_relative_path
        recovery_manifest = json.loads(recovery_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [],
            list(Draft202012Validator(recovery_schema, format_checker=FormatChecker()).iter_errors(recovery_manifest)),
        )
        with closing(sqlite3.connect(self.project / result.backup_relative_path)) as backup:
            self.assertEqual(
                self.manifest["schemaSha256"],
                __import__("research_observatory_core.storage", fromlist=["_schema_fingerprint"])._schema_fingerprint(
                    backup
                ),
            )
        with open_canonical_database(self.database, expected_project_id=self.manifest["projectId"]) as db:
            self.assertEqual(25, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(
                self.manifest["counts"]["reconciliation_versions"],
                db.execute("SELECT COUNT(*) FROM reconciliation_versions").fetchone()[0],
            )
            self.assertEqual(
                self.manifest["counts"]["object_records"],
                db.execute("SELECT COUNT(*) FROM object_records").fetchone()[0],
            )
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_assertions").fetchone()[0])
            self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
        self.assertEqual(before, {key: hashlib.sha256((self.project / key).read_bytes()).hexdigest() for key in before})

    def test_interrupted_v22_migration_leaves_exact_v21_predecessor_retryable(self) -> None:
        from research_observatory_core.migrations.versions import v0022_document_attachments

        original = v0022_document_attachments._migration_step_completed

        def interrupt(step):
            if step == "metadata-v22-copy":
                raise RuntimeError("synthetic migration interruption")
            return original(step)

        with (
            patch.object(v0022_document_attachments, "_migration_step_completed", side_effect=interrupt),
            self.assertRaises(RuntimeError),
        ):
            runner.migrate_database(self.database, expected_project_id=self.manifest["projectId"])
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(21, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(
                self.manifest["schemaSha256"],
                __import__("research_observatory_core.storage", fromlist=["_schema_fingerprint"])._schema_fingerprint(
                    db
                ),
            )
        result = runner.migrate_database(self.database, expected_project_id=self.manifest["projectId"])
        self.assertEqual("migrated", result.status)
        with open_canonical_database(self.database, expected_project_id=self.manifest["projectId"]) as canonical_db:
            self.assertEqual(25, canonical_db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(1, canonical_db.execute("SELECT COUNT(*) FROM reconciliation_versions").fetchone()[0])


class AttachmentOperationMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((REPO / "tests/fixtures/documents/v22-predecessor.json").read_text(encoding="utf-8"))
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-document-v22-")
        self.addCleanup(self._cleanup)
        self.project = Path(self.temporary.name) / "project"
        with ZipFile(REPO / "tests/fixtures/documents/v22-predecessor.zip") as archive:
            for name in ("state/project.sqlite3", *(item["relativePath"] for item in self.manifest["ciphertext"])):
                target = self.project / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        self.database = self.project / "state/project.sqlite3"
        self.profile = development_plaintext_database_fixture()
        self.profile.__enter__()
        self.addCleanup(self.profile.__exit__, None, None, None)

    def _cleanup(self) -> None:
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
                check=False,
                timeout=30,
            )
        self.temporary.cleanup()

    def _source_rows(self) -> dict[str, list[tuple[object, ...]]]:
        tables = (
            "document_attachment_candidates",
            "document_attachment_assertions",
            "rights_policy_revisions",
            "object_records",
        )
        with closing(sqlite3.connect(self.database)) as db:
            return {table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in tables}

    def _assert_literal_predecessor(self) -> None:
        self.assertEqual(self.manifest["databaseSha256"], hashlib.sha256(self.database.read_bytes()).hexdigest())
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(22, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(
                (22, self.manifest["profileSha256"], self.manifest["schemaSha256"]),
                db.execute("SELECT schema_version,profile_sha256,schema_sha256 FROM schema_metadata").fetchone(),
            )
            self.assertEqual(
                self.manifest["schemaSha256"],
                _schema_fingerprint(db),
            )
            self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
            for table, count in self.manifest["counts"].items():
                self.assertEqual(count, db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            self.assertEqual(
                (self.manifest["candidateId"], self.manifest["attachmentId"], self.manifest["documentRevisionId"]),
                db.execute(
                    "SELECT c.candidate_id,a.attachment_id,a.document_revision_id "
                    "FROM document_attachment_candidates c JOIN document_attachment_assertions a "
                    "ON a.project_id=c.project_id AND a.candidate_id=c.candidate_id"
                ).fetchone(),
            )

    def test_literal_populated_v22_migrates_without_changing_attachment_rights_or_ciphertext(self) -> None:
        self._assert_literal_predecessor()
        before_rows = self._source_rows()
        before_ciphertext = {
            item["relativePath"]: hashlib.sha256((self.project / item["relativePath"]).read_bytes()).hexdigest()
            for item in self.manifest["ciphertext"]
        }
        self.assertEqual(
            {item["relativePath"]: item["sha256"] for item in self.manifest["ciphertext"]},
            before_ciphertext,
        )
        plan = runner.plan_database_migration(self.database, expected_project_id=self.manifest["projectId"])
        self.assertEqual(
            ("0023_attachment_operations", "0024_open_access_acquisition", "0025_document_intake_recovery"),
            plan.migration_ids,
        )
        result = runner.migrate_database(self.database, expected_project_id=self.manifest["projectId"])
        self.assertEqual("migrated", result.status)
        assert result.backup_relative_path is not None
        assert result.recovery_manifest_relative_path is not None
        recovery_schema = json.loads(
            (REPO / "packages/contracts/storage/sqlite-migration-recovery.schema.json").read_text(encoding="utf-8")
        )
        recovery_path = self.project / result.recovery_manifest_relative_path
        recovery_manifest = json.loads(recovery_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [],
            list(Draft202012Validator(recovery_schema, format_checker=FormatChecker()).iter_errors(recovery_manifest)),
        )
        with closing(sqlite3.connect(self.project / result.backup_relative_path)) as backup:
            self.assertEqual(22, backup.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(
                self.manifest["schemaSha256"],
                _schema_fingerprint(backup),
            )
        with open_canonical_database(self.database, expected_project_id=self.manifest["projectId"]) as db:
            self.assertEqual(25, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_operations").fetchone()[0])
            self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
        self.assertEqual(before_rows, self._source_rows())
        self.assertEqual(
            before_ciphertext,
            {key: hashlib.sha256((self.project / key).read_bytes()).hexdigest() for key in before_ciphertext},
        )

    def test_interrupted_v23_migration_leaves_populated_v22_source_retryable(self) -> None:
        from research_observatory_core.migrations.versions import v0023_attachment_operations

        self._assert_literal_predecessor()
        before_rows = self._source_rows()
        original = v0023_attachment_operations._migration_step_completed

        def interrupt(step: str) -> None:
            if step == "metadata-v23-copy":
                raise RuntimeError("synthetic migration interruption")
            original(step)

        with (
            patch.object(v0023_attachment_operations, "_migration_step_completed", side_effect=interrupt),
            self.assertRaises(RuntimeError),
        ):
            runner.migrate_database(self.database, expected_project_id=self.manifest["projectId"])
        self._assert_literal_predecessor()
        self.assertEqual(before_rows, self._source_rows())
        result = runner.migrate_database(self.database, expected_project_id=self.manifest["projectId"])
        self.assertEqual("migrated", result.status)
        with open_canonical_database(self.database, expected_project_id=self.manifest["projectId"]) as db:
            self.assertEqual(25, db.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_operations").fetchone()[0])
        self.assertEqual(before_rows, self._source_rows())


if __name__ == "__main__":
    unittest.main()
