"""Import intake authority over actual project storage and encrypted objects."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import cast
from unittest.mock import patch

from research_observatory_core import storage
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.import_preview_repository import sqlite_import_preview_repository
from research_observatory_core.ingestion.preview_workflow import fingerprint
from research_observatory_core.ingestion.protected_import_profiles import profile_limits
from research_observatory_core.ingestion.reference_imports import PARSER_VERSION, ImportSession, ImportSource
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

    def test_parser_settings_are_atomic_immutable_and_identity_bound(self):
        command = PreviewCreate(
            preview_id=new_uuid_v7(),
            source_name="synthetic.csv",
            format_name="csv",
            delimiter=";",
            rights=fixture.RIGHTS,
            actor=self.actor(),
        )
        repository = self.repository()
        with (
            patch.object(repository, "_event", side_effect=PreviewProblem("synthetic-create-fault")),
            self.assertRaises(PreviewProblem),
        ):
            repository.create(command)
        connection = storage.open_canonical_database(
            self.project / "state/project.sqlite3", expected_project_id=fixture.PROJECT_ID
        )
        try:
            key = "imports.preview." + command.preview_id
            self.assertEqual(
                0, connection.execute("SELECT count(*) FROM settings WHERE setting_key=?", (key,)).fetchone()[0]
            )
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT count(*) FROM import_previews WHERE preview_id=?", (command.preview_id,)
                ).fetchone()[0],
            )
            self.assertEqual(";", repository.create(command).delimiter)
            self.assertEqual(";", self.repository().read(command.preview_id).delimiter)
            row = connection.execute(
                "SELECT setting_id, text_value FROM settings WHERE setting_key=?", (key,)
            ).fetchone()
            for sql in (
                "UPDATE settings SET text_value='{}' WHERE setting_key=?",
                "DELETE FROM settings WHERE setting_key=?",
            ):
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(sql, (key,))
            # Even a later adapter-inserted revision cannot become replacement authority.
            connection.execute(
                "INSERT INTO settings SELECT ?, project_id, setting_key, 1, value_type, text_value, "
                "integer_value, real_value, boolean_value, created_at, modified_at FROM settings WHERE setting_id=?",
                (new_uuid_v7(), row[0]),
            )
            with self.assertRaises(PreviewProblem):
                repository.read(command.preview_id)
        finally:
            connection.close()

    def test_legacy_preview_has_comma_default_without_backfill(self):
        preview, actor = new_uuid_v7(), self.actor()
        connection = storage.open_canonical_database(
            self.project / "state/project.sqlite3", expected_project_id=fixture.PROJECT_ID
        )
        try:
            connection.execute(
                "INSERT INTO import_previews VALUES (?, ?, 'legacy.csv', 'csv', 'utf-8', ?, ?, ?, ?)",
                (
                    preview,
                    fixture.PROJECT_ID,
                    fixture.RIGHTS.model_dump_json(by_alias=True),
                    actor.actor_id,
                    actor.trace_id,
                    actor.occurred_at,
                ),
            )
            connection.execute(
                "INSERT INTO import_preview_events VALUES (?, ?, 1, 'created', ?, ?, ?)",
                (preview, fixture.PROJECT_ID, actor.actor_id, actor.trace_id, actor.occurred_at),
            )
            self.assertEqual(",", self.repository().read(preview).delimiter)
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT count(*) FROM settings WHERE setting_key=?", ("imports.preview." + preview,)
                ).fetchone()[0],
            )
        finally:
            connection.close()

    def test_completed_parser_cannot_substitute_a_different_delimiter(self):
        raw = b"title,doi\nSynthetic,10.99999/EXAMPLE\n"
        preview, sealed, session, claim, _, actor = self.parse_attempt(raw)
        self.repository().append_records(preview, claim=claim, records=tuple(session.records()), actor=actor)
        wrong = ImportSession(io.BytesIO(raw), session.source, "csv", delimiter=";")
        tuple(wrong.records())
        receipt = self.receipt_revision(preview, sealed.manifest_sha256, actor)
        with self.assertRaisesRegex(PreviewProblem, "preview-parse-source-mismatch"):
            self.repository().finish_parse(
                preview, claim=claim, session=wrong, receipt_revision_id=receipt, actor=actor
            )
        self.assertEqual("parse-started", self.repository().read(preview).state)

    def test_malformed_or_substituted_parser_settings_fail_without_publishing_preview(self):
        from research_observatory_core.import_preview_repository import _ProtectedParserSettings

        for mutation in (
            {"projectId": new_uuid_v7()},
            {"previewId": new_uuid_v7()},
            {"formatName": "ris"},
            {"encoding": "cp1252"},
            {"delimiter": "|"},
            {"schemaVersion": "2.0"},
            {"parserProfile": "legacy-preview-120s-v1"},
            {"parserProfile": "unknown"},
            {"parserLimitsHash": "sha256:" + "0" * 64},
            {"unexpected": True},
            None,
        ):
            command = PreviewCreate(
                preview_id=new_uuid_v7(),
                source_name="synthetic.csv",
                format_name="csv",
                delimiter=";",
                rights=fixture.RIGHTS,
                actor=self.actor(),
            )
            value = {
                "schemaVersion": "1.1",
                "parserProfile": "protected-preview-900s-v1",
                "parserLimitsHash": "sha256:eee2a0c5d0b4c8a2ea8b13d393819f4807aa51f2b4ad95cc78168654dd122495",
                "projectId": fixture.PROJECT_ID,
                "previewId": command.preview_id,
                "formatName": "csv",
                "encoding": "utf-8",
                "delimiter": ";",
            }
            payload = "invalid-json" if mutation is None else json.dumps({**value, **mutation})
            with (
                patch.object(_ProtectedParserSettings, "model_dump_json", return_value=payload),
                self.assertRaises(PreviewProblem),
            ):
                self.repository().create(command)
            with self.assertRaisesRegex(PreviewProblem, "preview-not-found"):
                self.repository().read(command.preview_id)

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

    def parse_attempt(self, raw: bytes, *, legacy_variant=None):
        preview = self.create_legacy(legacy_variant) if legacy_variant is not None else self.create()
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
        cast(list[dict[str, object]], snapshot["jobs"])[0]["idempotencyKey"] = fingerprint({"previewId": preview})
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
        session = ImportSession(
            io.BytesIO(raw),
            ImportSource(sealed.source_name, sealed.source_sha256),
            "csv",
            delimiter=sealed.delimiter,
            limits=profile_limits(sealed.parser_profile),
        )
        self.repository().begin_parse(preview, claim=claim, actor=actor)
        return preview, sealed, session, claim, queue, actor

    def receipt_revision(
        self,
        preview: str,
        manifest: str,
        actor: PreviewActor,
        *,
        parser_configuration_hash=None,
        include_parser_configuration=True,
    ):
        state = self.repository().read(preview)
        configured = parser_configuration_hash or fingerprint(
            {
                "parserVersion": PARSER_VERSION,
                "format": state.format_name,
                "encoding": state.encoding,
                "delimiter": state.delimiter,
                "limits": asdict(profile_limits(state.parser_profile)),
            }
        )
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
                        *(
                            ()
                            if not include_parser_configuration
                            else (
                                MaterialDependency(
                                    dependency_id=new_uuid_v7(),
                                    dependency_kind="parameter-set",
                                    relation_type="direct",
                                    revision_id=None,
                                    configuration_id="import.parser-configuration",
                                    configuration_version="1.0.0",
                                    fingerprint=configured,
                                    governing_policy_id="dependency.material.v1",
                                    governing_policy_version="1.0.0",
                                ),
                            )
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

    def test_new_settings_select900_and_legacy_missing_or_v1_is_never_upgraded(self):
        from research_observatory_core.ingestion.protected_import_profiles import LEGACY_PROFILE, PROTECTED_PROFILE

        current = self.create()
        self.assertEqual(PROTECTED_PROFILE, self.repository().read(current).parser_profile)
        frozen = json.loads(
            (Path(__file__).parents[1] / "fixtures/imports/protected-preview-legacy120-authority-v1.json").read_text()
        )
        for case in frozen["cases"]:
            state = case["unscheduled"]["state"]
            actor = self.actor()
            connection = storage.open_canonical_database(
                self.project / "state/project.sqlite3", expected_project_id=fixture.PROJECT_ID
            )
            try:
                connection.execute(
                    "INSERT INTO import_previews VALUES (?, ?, ?, 'csv', 'utf-8', ?, ?, ?, ?)",
                    (
                        state["previewId"],
                        fixture.PROJECT_ID,
                        state["sourceName"],
                        json.dumps(state["rights"]),
                        actor.actor_id,
                        actor.trace_id,
                        actor.occurred_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO import_preview_events VALUES (?, ?, 1, 'created', ?, ?, ?)",
                    (state["previewId"], fixture.PROJECT_ID, actor.actor_id, actor.trace_id, actor.occurred_at),
                )
                for row in case["unscheduled"]["settingsRows"]:
                    columns = tuple(row)
                    connection.execute(
                        "INSERT INTO settings ("
                        + ",".join(columns)
                        + ") VALUES ("
                        + ",".join("?" for _ in columns)
                        + ")",
                        tuple(row.values()),
                    )
                before = connection.execute(
                    "SELECT * FROM settings WHERE setting_key=?", ("imports.preview." + state["previewId"],)
                ).fetchall()
                for _ in range(2):
                    actual = self.repository().read(state["previewId"])
                    self.assertEqual(LEGACY_PROFILE, actual.parser_profile)
                    self.assertEqual(state["delimiter"], actual.delimiter)
                self.assertEqual(
                    before,
                    connection.execute(
                        "SELECT * FROM settings WHERE setting_key=?", ("imports.preview." + state["previewId"],)
                    ).fetchall(),
                )
            finally:
                connection.close()

    def test_new_profile_rejects_actual_legacy_session_even_with_valid_new_receipt(self):
        raw = b"title\nSynthetic\n"
        preview, sealed, session, claim, _, actor = self.parse_attempt(raw)
        self.repository().append_records(preview, claim=claim, records=tuple(session.records()), actor=actor)
        old = ImportSession(io.BytesIO(raw), session.source, "csv")
        tuple(old.records())
        receipt = self.receipt_revision(preview, sealed.manifest_sha256, actor)
        with self.assertRaisesRegex(PreviewProblem, "preview-parser-session-profile-mismatch"):
            self.repository().finish_parse(preview, claim=claim, session=old, receipt_revision_id=receipt, actor=actor)
        self.assertEqual("parse-started", self.repository().read(preview).state)

    def test_new_settings_require_explicit_profile_hash_and_object_shape(self):
        from research_observatory_core.import_preview_repository import _ProtectedParserSettings

        for missing in ("parserProfile", "parserLimitsHash", "non-object"):
            command = PreviewCreate(
                preview_id=new_uuid_v7(),
                source_name="synthetic.csv",
                format_name="csv",
                rights=fixture.RIGHTS,
                actor=self.actor(),
            )
            value = {
                "schemaVersion": "1.1",
                "projectId": fixture.PROJECT_ID,
                "previewId": command.preview_id,
                "formatName": "csv",
                "encoding": "utf-8",
                "delimiter": ",",
                "parserProfile": "protected-preview-900s-v1",
                "parserLimitsHash": "sha256:eee2a0c5d0b4c8a2ea8b13d393819f4807aa51f2b4ad95cc78168654dd122495",
            }
            if missing == "non-object":
                payload = "[]"
            else:
                del value[missing]
                payload = json.dumps(value)
            with (
                self.subTest(missing=missing),
                patch.object(_ProtectedParserSettings, "model_dump_json", return_value=payload),
                self.assertRaises(PreviewProblem),
            ):
                self.repository().create(command)
            with self.assertRaisesRegex(PreviewProblem, "preview-not-found"):
                self.repository().read(command.preview_id)

    def test_new_profile_rejects_wrong_actual_parser_receipt(self):
        preview, sealed, session, claim, _, actor = self.parse_attempt(b"title\nSynthetic\n")
        self.repository().append_records(preview, claim=claim, records=tuple(session.records()), actor=actor)
        receipt = self.receipt_revision(
            preview, sealed.manifest_sha256, actor, parser_configuration_hash="sha256:" + "0" * 64
        )
        with self.assertRaisesRegex(PreviewProblem, "preview-parser-receipt-profile-mismatch"):
            self.repository().finish_parse(
                preview, claim=claim, session=session, receipt_revision_id=receipt, actor=actor
            )
        with self.assertRaises(PreviewProblem):
            self.repository().records_page(preview, after=0, limit=10)

    def create_legacy(self, variant="v1-comma", *, version_mode="captured"):
        document = json.loads(
            (Path(__file__).parents[1] / "fixtures/imports/protected-preview-legacy120-authority-v1.json").read_text()
        )
        case = next(case for case in document["cases"] if case["variant"] == variant)
        state = case["unscheduled"]["state"]
        actor = self.actor()
        connection = storage.open_canonical_database(
            self.project / "state/project.sqlite3", expected_project_id=fixture.PROJECT_ID
        )
        try:
            connection.execute(
                "INSERT INTO import_previews VALUES (?, ?, ?, 'csv', 'utf-8', ?, ?, ?, ?)",
                (
                    state["previewId"],
                    fixture.PROJECT_ID,
                    state["sourceName"],
                    json.dumps(state["rights"]),
                    actor.actor_id,
                    actor.trace_id,
                    actor.occurred_at,
                ),
            )
            connection.execute(
                "INSERT INTO import_preview_events VALUES (?, ?, 1, 'created', ?, ?, ?)",
                (state["previewId"], fixture.PROJECT_ID, actor.actor_id, actor.trace_id, actor.occurred_at),
            )
            for row in case["unscheduled"]["settingsRows"]:
                row = dict(row)
                value = json.loads(row["text_value"])
                if version_mode == "omitted":
                    del value["schemaVersion"]
                elif version_mode == "python-name":
                    value["schema_version"] = value.pop("schemaVersion")
                elif version_mode == "unknown":
                    value["schemaVersion"] = "2.0"
                else:
                    self.assertEqual("captured", version_mode)
                if version_mode != "captured":
                    row["text_value"] = json.dumps(value)
                connection.execute(
                    "INSERT INTO settings (" + ",".join(row) + ") VALUES (" + ",".join("?" for _ in row) + ")",
                    tuple(row.values()),
                )
        finally:
            connection.close()
        return state["previewId"]

    def test_legacy_source_only_receipt_still_accepts_without_profile_backfill(self):
        for variant in ("missing-comma", "v1-comma"):
            with self.subTest(variant=variant):
                preview, sealed, session, claim, queue, actor = self.parse_attempt(
                    b"title\nSynthetic\n", legacy_variant=variant
                )
                self.assertEqual(120.0, session.limits.max_seconds)
                self.repository().append_records(preview, claim=claim, records=tuple(session.records()), actor=actor)
                receipt = self.receipt_revision(
                    preview, sealed.manifest_sha256, actor, include_parser_configuration=False
                )
                output = self.repository().finish_parse(
                    preview, claim=claim, session=session, receipt_revision_id=receipt, actor=actor
                )
                queue.stage_artifact(claim, artifact=output, role="output", now=actor.occurred_at)
                queue.complete(claim, outputs=(output,), now=actor.occurred_at)
                restored = self.repository()
                self.assertEqual(2, len(restored.records_page(preview, after=0, limit=10)))
                self.assertEqual("legacy-preview-120s-v1", restored.read(preview).parser_profile)

    def test_legacy_settings_default_and_python_version_name_keep_exact120_authority(self):
        from contextlib import closing

        from research_observatory_core.import_preview_repository import _ParserSettings
        from research_observatory_core.ingestion.preview_workflow import PreviewIntentContext, preview_job_input

        document = json.loads(
            (Path(__file__).parents[1] / "fixtures/imports/protected-preview-legacy120-authority-v1.json").read_text()
        )
        frozen = next(case for case in document["cases"] if case["variant"] == "v1-comma")
        context = document["syntheticContext"]
        for mode in ("omitted", "python-name"):
            with self.subTest(mode=mode):
                data = ImportPreviewRepositoryTests(methodName="runTest")
                lifecycle: unittest.TestCase = data
                lifecycle.setUp()
                self.addCleanup(lifecycle.tearDown)
                preview = data.create_legacy("v1-comma", version_mode=mode)
                state = data.repository().read(preview)
                self.assertEqual("legacy-preview-120s-v1", state.parser_profile)
                with closing(
                    storage.open_canonical_database(
                        data.project / "state/project.sqlite3", expected_project_id=fixture.PROJECT_ID
                    )
                ) as connection:
                    raw_settings = connection.execute(
                        "SELECT text_value FROM settings WHERE setting_key=?", ("imports.preview." + preview,)
                    ).fetchone()[0]
                self.assertEqual("1.0", _ParserSettings.model_validate_json(raw_settings).schema_version)
                raw = frozen["syntheticSourceUtf8"].encode("utf-8")
                for ordinal, chunk in enumerate(data.retain(raw), 1):
                    data.repository().append_chunk(preview, ordinal=ordinal, chunk=chunk)
                sealed = data.repository().seal(
                    preview,
                    source_sha256=hashlib.sha256(raw).hexdigest(),
                    byte_length=len(raw),
                    chunk_count=1,
                    actor=data.actor(),
                )
                inputs = preview_job_input(
                    sealed,
                    PreviewIntentContext.model_validate_json(json.dumps(context["intent"])),
                    context["policyHash"],
                    context["resumeEpoch"],
                )
                self.assertEqual(frozen["unscheduled"]["inputs"], inputs.model_dump(mode="json", by_alias=True))
                self.assertEqual(frozen["unscheduled"]["configurationHash"], inputs.configuration_hash)
                with closing(
                    storage.open_canonical_database(
                        data.project / "state/project.sqlite3", expected_project_id=fixture.PROJECT_ID
                    )
                ) as connection:
                    self.assertEqual(
                        raw_settings,
                        connection.execute(
                            "SELECT text_value FROM settings WHERE setting_key=?", ("imports.preview." + preview,)
                        ).fetchone()[0],
                    )
        invalid = self.create_legacy("v1-comma", version_mode="unknown")
        with self.assertRaises(PreviewProblem):
            self.repository().read(invalid)
