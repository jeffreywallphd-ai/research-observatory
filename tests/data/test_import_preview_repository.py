"""Import intake authority over actual project storage and encrypted objects."""

from __future__ import annotations

import hashlib
import io
import sqlite3
import unittest
from pathlib import Path

from research_observatory_core import storage
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.import_preview_repository import sqlite_import_preview_repository
from research_observatory_core.ingestion.reference_imports import ImportSession, ImportSource
from research_observatory_core.ingestion.source_chunks import put_source_chunk
from research_observatory_core.object_store import create_local_object_store
from research_observatory_core.ports.import_previews import PreviewActor, PreviewCreate, PreviewProblem
from research_observatory_core.ports.object_store import ObjectReferenced
from research_observatory_core.ports.repositories import (
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    MaterialDependency,
)
from research_observatory_core.repositories import create_sqlite_unit_of_work_factory, sqlite_workflow_queue_repository
from research_observatory_core.workflow_executor import prepare_workflow_job

from tests.data import test_import_source_chunks as fixture
from tests.workflows import test_local_workflow_executor as worker_fixture


class ImportPreviewRepositoryTests(unittest.TestCase):
    setUp = fixture.ImportSourceChunkTests.setUp
    tearDown = fixture.ImportSourceChunkTests.tearDown
    project: Path
    v1: bytes

    def store(self):
        return create_local_object_store(
            self.project,
            fixture.PROJECT_ID,
            key_provider=fixture.MemoryKeyProvider({"object-key-v1": self.v1}, "object-key-v1"),
        )

    def retain(self, raw: bytes):
        return tuple(
            put_source_chunk(
                self.store(),
                raw[index : index + fixture.CHUNK_BYTES],
                rights=fixture.RIGHTS,
                created_at=fixture.CREATED_AT,
            )
            for index in range(0, len(raw), fixture.CHUNK_BYTES)
        )

    def repository(self, project_id: str = fixture.PROJECT_ID):
        return sqlite_import_preview_repository(self.project / "state/project.sqlite3", project_id)

    def actor(self):
        return PreviewActor(actor_id=new_uuid_v7(), trace_id="1" * 32, occurred_at=fixture.CREATED_AT)

    def create(self, preview_id: str | None = None):
        command = PreviewCreate(
            preview_id=preview_id or new_uuid_v7(),
            source_name="references.csv",
            format_name="csv",
            encoding="utf-8",
            rights=fixture.RIGHTS,
            actor=self.actor(),
        )
        self.repository().create(command)
        return command.preview_id

    def test_shared_references_survive_cancel_restart_and_block_deletion(self):
        raw = b"title\nSynthetic\n"
        chunk = self.retain(raw)[0]
        first, second = self.create(), self.create()
        for preview in (first, second):
            self.repository().append_chunk(preview, ordinal=1, chunk=chunk)
        self.assertEqual(2, self.store().metadata(chunk.object_sha256).reference_count)
        self.repository().cancel(first, actor=self.actor())
        self.assertEqual("cancelled", self.repository().read(first).state)
        self.assertEqual(2, self.store().metadata(chunk.object_sha256).reference_count)
        with self.assertRaises(ObjectReferenced):
            self.store().delete(chunk.object_sha256)
        sealed = self.repository().seal(
            second,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            actor=self.actor(),
        )
        self.assertEqual("source-sealed", sealed.state)
        self.assertEqual((chunk,), self.repository().source_chunks(second))
        self.assertEqual(sealed, self.repository().read(second))
        connection = storage.open_canonical_database(
            self.project / "state/project.sqlite3", expected_project_id=fixture.PROJECT_ID
        )
        try:
            self.assertEqual(0, connection.execute("SELECT count(*) FROM scholarly_records").fetchone()[0])
            self.assertEqual([], connection.execute("PRAGMA foreign_key_check").fetchall())
        finally:
            connection.close()

    def test_incomplete_substituted_or_closed_intake_is_not_published(self):
        chunk = self.retain(b"title\nSynthetic\n")[0]
        preview = self.create()
        with self.assertRaises(PreviewProblem):
            self.repository().append_chunk(preview, ordinal=2, chunk=chunk)
        self.repository().append_chunk(preview, ordinal=1, chunk=chunk)
        self.repository().append_chunk(preview, ordinal=1, chunk=chunk)  # exact retry
        with self.assertRaises(PreviewProblem):
            self.repository().seal(preview, source_sha256="f" * 64, byte_length=1, chunk_count=1, actor=self.actor())
        self.assertEqual("created", self.repository().read(preview).state)
        self.repository().cancel(preview, actor=self.actor())
        for action in (
            lambda: self.repository().source_chunks(preview),
            lambda: self.repository().append_chunk(preview, ordinal=1, chunk=chunk),
            lambda: self.repository().seal(
                preview, source_sha256="f" * 64, byte_length=chunk.byte_length, chunk_count=1, actor=self.actor()
            ),
            lambda: self.repository(new_uuid_v7()).read(preview),
        ):
            with self.assertRaises(PreviewProblem):
                action()

    def test_unknown_rights_and_path_sources_are_denied_without_state(self):
        from pydantic import ValidationError

        for value in ("folder/references.csv", "folder\\references.csv", "C:references.csv", ".."):
            with self.assertRaises(ValidationError):
                PreviewCreate(
                    preview_id=new_uuid_v7(),
                    source_name=value,
                    format_name="csv",
                    encoding="utf-8",
                    rights=fixture.RIGHTS,
                    actor=self.actor(),
                )
        command = PreviewCreate(
            preview_id=new_uuid_v7(),
            source_name="references.csv",
            format_name="csv",
            encoding="utf-8",
            rights=fixture.ImportRights(),
            actor=self.actor(),
        )
        with self.assertRaises(PreviewProblem):
            self.repository().create(command)
        with self.assertRaises(PreviewProblem):
            self.repository().read(command.preview_id)

    def test_sealed_chunk_membership_is_closed_even_to_adapter_sql(self):
        chunk = self.retain(b"x" * fixture.CHUNK_BYTES)[0]
        preview = self.create()
        self.repository().append_chunk(preview, ordinal=1, chunk=chunk)
        self.repository().seal(
            preview, source_sha256=chunk.object_sha256, byte_length=chunk.byte_length, chunk_count=1, actor=self.actor()
        )
        connection = storage.open_canonical_database(
            self.project / "state/project.sqlite3", expected_project_id=fixture.PROJECT_ID
        )
        try:
            for sql, args in (
                (
                    "INSERT INTO import_source_chunks VALUES (?, ?, 2, ?, ?)",
                    (preview, fixture.PROJECT_ID, chunk.object_sha256, chunk.byte_length),
                ),
                ("UPDATE import_source_seals SET source_sha256=?", ("a" * 64,)),
                ("DELETE FROM import_source_chunks WHERE preview_id=?", (preview,)),
            ):
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(sql, args)
        finally:
            connection.close()
        self.assertEqual((chunk,), self.repository().source_chunks(preview))

    def test_null_predecessor_cannot_bypass_draft_revision_check(self):
        # Isolate the CHECK, so an unrelated FK failure cannot conceal a NULL bypass.
        connection = sqlite3.connect(":memory:", autocommit=True)
        try:
            for statement in storage._DDL_STATEMENTS:
                connection.execute(statement)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK constraint failed"):
                connection.execute(
                    "INSERT INTO import_draft_revisions VALUES (?, ?, 2, NULL, ?, '{}', '{}', '{}', NULL, ?, ?, ?)",
                    (new_uuid_v7(), fixture.PROJECT_ID, new_uuid_v7(), new_uuid_v7(), "1" * 32, fixture.CREATED_AT),
                )
        finally:
            connection.close()

    def parse_attempt(self, raw: bytes):
        preview = self.create()
        for index, chunk in enumerate(self.retain(raw), 1):
            self.repository().append_chunk(preview, ordinal=index, chunk=chunk)
        sealed = self.repository().seal(
            preview,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=(len(raw) + fixture.CHUNK_BYTES - 1) // fixture.CHUNK_BYTES,
            actor=self.actor(),
        )
        definition, snapshot, job = worker_fixture.runnable_contracts(identity_variant=True)
        snapshot["projectId"] = fixture.PROJECT_ID
        queue = sqlite_workflow_queue_repository(self.project, fixture.PROJECT_ID)
        queue.enqueue(
            prepare_workflow_job(
                definition,
                snapshot,
                job_id=job,
                concurrency_class="document",
                priority=0,
                available_at="2026-08-30T12:02:00.000Z",
            ),
            actor=worker_fixture.SYSTEM,
        )
        claim = queue.claim_next(
            worker_id=worker_fixture.WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        queue.start(claim, now="2026-08-30T12:02:00.100Z")
        actor = PreviewActor(actor_id=claim.worker_id, trace_id="2" * 32, occurred_at="2026-08-30T12:02:00.200Z")
        session = ImportSession(io.BytesIO(raw), ImportSource("references.csv", sealed.source_sha256), "csv")
        self.repository().begin_parse(preview, claim=claim, actor=actor)
        return preview, sealed, session, claim, queue, actor

    def receipt_revision(self, preview: str, manifest: str, actor: PreviewActor):
        factory = create_sqlite_unit_of_work_factory(self.project / "state/project.sqlite3", fixture.PROJECT_ID)
        with factory() as unit:
            receipt = unit.aggregates.append(
                AggregateRevisionDraft(
                    revision_id=new_uuid_v7(),
                    aggregate_id=new_uuid_v7(),
                    aggregate_kind="workflow",
                    created_at=actor.occurred_at,
                    modified_at=actor.occurred_at,
                    display_label_observed="Import preview parse artifact",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                    dependency_coverage="complete",
                    material_dependencies=(
                        MaterialDependency(
                            dependency_id=new_uuid_v7(),
                            dependency_kind="parameter-set",
                            relation_type="direct",
                            revision_id=None,
                            configuration_id="import.source-manifest",
                            configuration_version="1.0.0",
                            fingerprint="sha256:" + manifest,
                            governing_policy_id="dependency.material.v1",
                            governing_policy_version="1.0.0",
                        ),
                    ),
                ),
                AtomicRepositoryEvent(
                    event_id=new_uuid_v7(),
                    outbox_id=new_uuid_v7(),
                    event_type="workflow.created",
                    occurred_at=actor.occurred_at,
                    available_at=actor.occurred_at,
                    trace_id=actor.trace_id,
                    actor_type="worker",
                    actor_id=actor.actor_id,
                    idempotency_key="preview-receipt-" + preview + "-" + new_uuid_v7(),
                ),
                expected_revision=None,
            )
            unit.commit()
        return receipt.revision_id

    def test_records_stay_provisional_until_exact_attempt_receipt_is_accepted(self):
        preview, sealed, session, claim, queue, actor = self.parse_attempt(b"title\nSynthetic\n")
        records = tuple(session.records())
        self.repository().append_records(preview, claim=claim, records=records, actor=actor)
        receipt = self.receipt_revision(preview, sealed.manifest_sha256, actor)
        output = self.repository().finish_parse(
            preview, claim=claim, session=session, receipt_revision_id=receipt, actor=actor
        )
        with self.assertRaises(PreviewProblem):
            self.repository().records_page(preview, after=0, limit=10)
        queue.stage_artifact(claim, artifact=output, role="output", now=actor.occurred_at)
        queue.complete(claim, now=actor.occurred_at, outputs=(output,))
        restored = self.repository().records_page(preview, after=0, limit=10)
        self.assertEqual([item.record_key for item in records], [item.record_key for item in restored])
        self.assertTrue(all(item.raw_bytes is None for item in restored))
        self.assertEqual((restored[1],), self.repository().records_page(preview, after=1, limit=1))
        connection = storage.open_canonical_database(
            self.project / "state/project.sqlite3", expected_project_id=fixture.PROJECT_ID
        )
        try:
            self.assertNotIn(
                "rawBase64", connection.execute("SELECT record_json FROM import_parse_records").fetchone()[0]
            )
            self.assertEqual(0, connection.execute("SELECT count(*) FROM scholarly_records").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT count(*) FROM workflows").fetchone()[0])
        finally:
            connection.close()

    def test_unfinished_parse_forged_lease_and_security_cancel_deny_publication(self):
        from dataclasses import replace

        preview, sealed, session, claim, queue, actor = self.parse_attempt(b"title\nSynthetic\n")
        receipt = self.receipt_revision(preview, sealed.manifest_sha256, actor)
        with self.assertRaises(PreviewProblem):
            self.repository().finish_parse(
                preview, claim=claim, session=session, receipt_revision_id=receipt, actor=actor
            )
        records = tuple(session.records())
        with self.assertRaises(PreviewProblem):
            self.repository().append_records(
                preview, claim=replace(claim, lease_token="forged"), records=records, actor=actor
            )
        self.repository().append_records(preview, claim=claim, records=records, actor=actor)
        output = self.repository().finish_parse(
            preview, claim=claim, session=session, receipt_revision_id=receipt, actor=actor
        )
        queue.stage_artifact(claim, artifact=output, role="output", now=actor.occurred_at)
        self.repository().cancel(preview, actor=actor, security_interruption=True)
        queue.request_cancellation(
            claim.job_id,
            actor=worker_fixture.SYSTEM,
            now=actor.occurred_at,
            reason_code="test-security-lock",
            interruption_kind="security-lock",
        )
        with self.assertRaises(PreviewProblem):
            self.repository().records_page(preview, after=0, limit=10)

    def test_restart_after_provisional_completion_uses_new_fenced_attempt(self):
        from dataclasses import replace

        raw = b"title\nSynthetic\n"
        preview, sealed, session, first, queue, actor = self.parse_attempt(raw)
        records = tuple(session.records())
        self.repository().append_records(preview, claim=first, records=records, actor=actor)
        receipt = self.receipt_revision(preview, sealed.manifest_sha256, actor)
        self.repository().finish_parse(preview, claim=first, session=session, receipt_revision_id=receipt, actor=actor)
        self.assertEqual(1, queue.recover_expired(now="2026-08-30T12:02:31.000Z", actor=worker_fixture.SYSTEM))
        second = queue.claim_next(
            worker_id=worker_fixture.WORKER_B,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:31.000Z",
            lease_duration_ms=30_000,
        )
        assert second is not None
        queue.start(second, now="2026-08-30T12:02:31.100Z")
        actor = PreviewActor(actor_id=second.worker_id, trace_id="3" * 32, occurred_at="2026-08-30T12:02:31.200Z")
        with self.assertRaises(PreviewProblem):
            self.repository().begin_parse(preview, claim=replace(second, job_id=new_uuid_v7()), actor=actor)
        self.repository().begin_parse(preview, claim=second, actor=actor)
        with self.assertRaises(PreviewProblem):
            self.repository().append_records(preview, claim=first, records=records, actor=actor)
        self.repository().append_records(preview, claim=second, records=records, actor=actor)
        receipt = self.receipt_revision(preview, sealed.manifest_sha256, actor)
        output = self.repository().finish_parse(
            preview, claim=second, session=session, receipt_revision_id=receipt, actor=actor
        )
        queue.stage_artifact(second, artifact=output, role="output", now=actor.occurred_at)
        queue.complete(second, now=actor.occurred_at, outputs=(output,))
        self.assertEqual(2, len(self.repository().records_page(preview, after=0, limit=10)))

    def test_record_source_substitution_rolls_back_the_whole_batch(self):
        from dataclasses import replace

        preview, _, session, claim, _, actor = self.parse_attempt(b"title\nSynthetic\n")
        records = tuple(session.records())
        substituted = replace(records[1], source=ImportSource("substituted.csv", session.source.sha256))
        with self.assertRaises(PreviewProblem):
            self.repository().append_records(preview, claim=claim, records=(records[0], substituted), actor=actor)
        self.repository().append_records(preview, claim=claim, records=records, actor=actor)
