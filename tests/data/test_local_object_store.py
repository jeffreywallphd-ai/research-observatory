from __future__ import annotations

import hashlib
import io
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import BinaryIO, cast
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core import object_store as object_store_module  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.object_store import (  # noqa: E402
    ObjectAccessDecision,
    ObjectAccessDenied,
    ObjectAccessRequest,
    ObjectBusy,
    ObjectConflict,
    ObjectCorrupt,
    ObjectIntegrityMismatch,
    ObjectNotFound,
    ObjectPutCommand,
    ObjectReferenced,
    ObjectStoreProblem,
)
from research_observatory_core.ports.repositories import (  # noqa: E402
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    RepositoryConflict,
)
from research_observatory_core.repositories import create_sqlite_unit_of_work_factory  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    CanonicalConnection,
    initialize_database,
    open_canonical_database,
)

PROJECT_ID = "123e4567-e89b-42d3-a456-426614174000"
SECOND_PROJECT_ID = "123e4567-e89b-42d3-a456-426614174001"
CREATED_AT = "2026-08-18T12:00:00.000Z"


class FailingStream(io.RawIOBase):
    def __init__(self) -> None:
        self.calls = 0

    def read(self, _size: int = -1) -> bytes:
        self.calls += 1
        if self.calls == 1:
            return b"partial-research-content"
        raise OSError("injected source interruption")


class RecordingAccessPolicy:
    def __init__(self, outcome: str = "allow") -> None:
        self.outcome = outcome
        self.requests: list[ObjectAccessRequest] = []

    def authorize(self, request: ObjectAccessRequest) -> ObjectAccessDecision:
        self.requests.append(request)
        return ObjectAccessDecision(self.outcome, "test-policy")  # type: ignore[arg-type]


class FailingAccessPolicy:
    def authorize(self, request: ObjectAccessRequest) -> ObjectAccessDecision:
        raise RuntimeError(f"policy unavailable for {request.purpose}")


def put_command(**overrides: object) -> ObjectPutCommand:
    values: dict[str, object] = {
        "media_type": "application/pdf",
        "rights_status": "allowed",
        "protection_profile": "plaintext-fixture-v1",
        "retention_class": "project-lifetime",
        "creation_source": "test-fixture",
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return ObjectPutCommand(**values)  # type: ignore[arg-type]


def document_draft(index: int, object_sha256: str) -> AggregateRevisionDraft:
    return AggregateRevisionDraft(
        revision_id=f"01890f6e-6a40-7cc5-98b7-{index:012x}",
        aggregate_id="01890f6e-6a40-7cc5-98b7-000000000100",
        aggregate_kind="document",
        created_at=CREATED_AT,
        modified_at=f"2026-08-18T12:00:{index:02d}.000Z",
        display_label_observed=f"Document revision {index}",
        display_label_normalized=None,
        knowledge_status="observed",
        rights_status="allowed",
        object_sha256=object_sha256,
    )


def event(index: int) -> AtomicRepositoryEvent:
    return AtomicRepositoryEvent(
        event_id=f"01890f6e-6a40-7cc5-98b7-{index + 100:012x}",
        outbox_id=f"01890f6e-6a40-7cc5-98b7-{index + 200:012x}",
        event_type="document.revised" if index > 1 else "document.created",
        occurred_at=f"2026-08-18T12:01:{index:02d}.000Z",
        available_at=f"2026-08-18T12:01:{index:02d}.000Z",
        trace_id=f"{index:032x}",
        actor_type="human",
        actor_id="human.object-store-test",
        idempotency_key=f"object-document-{index}",
    )


class LocalObjectStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-object-store-")
        self.project = Path(self.temporary.name).resolve() / "project"
        for relative in ("state", "objects", ".tmp"):
            (self.project / relative).mkdir(parents=True, mode=0o700)
        self.database = self.project / "state" / "project.sqlite3"
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        self.store = create_local_object_store(self.project, PROJECT_ID, allow_plaintext_fixture=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def object_files(self) -> tuple[Path, ...]:
        return tuple(path for path in (self.project / "objects").rglob("*") if path.is_file())

    def test_streaming_put_deduplicates_with_opaque_path_and_survives_restart(self) -> None:
        content = (b"research-observatory-object\n" * 20_000) + b"end"
        expected = hashlib.sha256(content).hexdigest()

        first = self.store.put(io.BytesIO(content), put_command(expected_sha256=expected))
        second = self.store.put(io.BytesIO(content), put_command(expected_sha256=expected))

        self.assertEqual(first, second)
        self.assertEqual(expected, first.object_sha256)
        self.assertEqual(len(content), first.byte_length)
        self.assertEqual(0, first.reference_count)
        self.assertEqual("test-fixture", first.creation_source)
        files = self.object_files()
        self.assertEqual(1, len(files))
        relative = files[0].relative_to(self.project / "objects")
        self.assertEqual(3, len(relative.parts))
        self.assertNotIn(expected, relative.parts)
        self.assertEqual(64 + len(".blob"), len(relative.name))

        restarted = create_local_object_store(self.project, PROJECT_ID, allow_plaintext_fixture=True)
        with restarted.open(expected, purpose="document-analysis") as stream:
            self.assertFalse(hasattr(stream, "name"))
            self.assertFalse(hasattr(stream, "fileno"))
            if os.name == "nt":
                with self.assertRaises(PermissionError):
                    files[0].write_bytes(b"late mutation")
                with self.assertRaises(PermissionError):
                    files[0].unlink()
            self.assertEqual(content, stream.read())
        self.assertEqual(first, restarted.metadata(expected))
        self.assertFalse(hasattr(restarted, "root"))
        self.assertFalse(hasattr(restarted, "database"))

    def test_concurrent_duplicates_and_cross_project_content_are_project_scoped(self) -> None:
        content = b"same content, separate project authority" * 4096
        barrier = threading.Barrier(6)

        def publish() -> str:
            barrier.wait()
            return self.store.put(io.BytesIO(content), put_command()).object_sha256

        with ThreadPoolExecutor(max_workers=6) as executor:
            digests = tuple(executor.map(lambda _index: publish(), range(6)))
        self.assertEqual(1, len(set(digests)))
        self.assertEqual(1, len(self.object_files()))

        second = self.project.parent / "second-project"
        for relative in ("state", "objects", ".tmp"):
            (second / relative).mkdir(parents=True, mode=0o700)
        initialize_database(
            second / "state" / "project.sqlite3",
            project_id=SECOND_PROJECT_ID,
            project_created_at=CREATED_AT,
        )
        second_store = create_local_object_store(second, SECOND_PROJECT_ID, allow_plaintext_fixture=True)
        second_stored = second_store.put(io.BytesIO(content), put_command())
        self.assertEqual(digests[0], second_stored.object_sha256)
        first_name = self.object_files()[0].name
        second_name = next(path for path in (second / "objects").rglob("*") if path.is_file()).name
        self.assertNotEqual(first_name, second_name)

    def test_interrupted_and_hash_mismatched_puts_leave_no_visible_state(self) -> None:
        with self.assertRaises(ObjectStoreProblem) as interrupted:
            self.store.put(cast(BinaryIO, FailingStream()), put_command())
        self.assertIsNone(interrupted.exception.__cause__)
        self.assertIsNone(interrupted.exception.__context__)
        with self.assertRaises(ObjectIntegrityMismatch):
            self.store.put(io.BytesIO(b"wrong"), put_command(expected_sha256="a" * 64))
        with self.assertRaises(ObjectStoreProblem):
            self.store.put(
                io.BytesIO(b"metadata-rollback"),
                put_command(created_at="9999-99-99T99:99:99.999Z"),
            )

        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(0, connection.execute("SELECT count(*) FROM object_records").fetchone()[0])
        finally:
            connection.close()
        self.assertEqual((), self.object_files())
        self.assertEqual((), tuple((self.project / ".tmp").rglob("*.partial")))

    def test_hostile_non_string_command_fields_are_bounded(self) -> None:
        for field in ("media_type", "protection_profile", "creation_source"):
            with self.subTest(field=field), self.assertRaises(ObjectStoreProblem) as raised:
                self.store.put(io.BytesIO(b"hostile metadata"), put_command(**{field: 123}))
            self.assertIsNone(raised.exception.__cause__)
            self.assertIsNone(raised.exception.__context__)

        for creation_source in ("legacy-unreported", "not-a-source"):
            with self.subTest(creation_source=creation_source), self.assertRaises(ObjectStoreProblem):
                self.store.put(
                    io.BytesIO(f"invalid-{creation_source}".encode()),
                    put_command(creation_source=creation_source),
                )

    def test_duplicate_metadata_conflict_preserves_original_bytes_and_projection(self) -> None:
        content = b"stable identity and meaning"
        original = self.store.put(io.BytesIO(content), put_command())
        with self.assertRaises(ObjectConflict):
            self.store.put(
                io.BytesIO(content),
                put_command(media_type="text/plain"),
            )
        with self.assertRaises(ObjectConflict):
            self.store.put(
                io.BytesIO(content),
                put_command(creation_source="local-import"),
            )
        self.assertEqual(original, self.store.metadata(original.object_sha256))
        with self.store.open(original.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(content, stream.read())

    def test_corruption_is_denied_before_content_is_returned_and_quarantined(self) -> None:
        content = b"canonical source bytes"
        stored = self.store.put(io.BytesIO(content), put_command())
        only_file = self.object_files()[0]
        only_file.write_bytes(b"tampered source bytes")

        with self.assertRaises(ObjectCorrupt):
            self.store.open(stored.object_sha256, purpose="document-analysis")

        metadata = self.store.metadata(stored.object_sha256)
        self.assertEqual("quarantined", metadata.storage_state)
        self.assertIsNone(metadata.verified_at)

    def test_missing_object_bytes_are_quarantined_before_open(self) -> None:
        stored = self.store.put(io.BytesIO(b"must remain available"), put_command())
        self.object_files()[0].unlink()
        with self.assertRaises(ObjectCorrupt):
            self.store.open(stored.object_sha256, purpose="document-analysis")
        self.assertEqual("quarantined", self.store.metadata(stored.object_sha256).storage_state)

    def test_rights_and_reference_boundaries_deny_open_or_delete(self) -> None:
        denied = self.store.put(
            io.BytesIO(b"restricted"),
            put_command(rights_status="denied"),
        )
        with self.assertRaises(ObjectAccessDenied):
            self.store.open(denied.object_sha256, purpose="document-analysis")
        unknown = self.store.put(
            io.BytesIO(b"rights unknown"),
            put_command(rights_status="unknown"),
        )
        with self.assertRaises(ObjectAccessDenied):
            self.store.open(unknown.object_sha256, purpose="document-analysis")

        content = b"referenced document"
        referenced = self.store.put(io.BytesIO(content), put_command())
        factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)
        with factory() as unit:
            unit.aggregates.append(document_draft(1, referenced.object_sha256), event(1), expected_revision=None)
            unit.commit()
        with factory() as unit:
            unit.aggregates.append(document_draft(2, referenced.object_sha256), event(2), expected_revision=0)
            unit.commit()

        self.assertEqual(2, self.store.metadata(referenced.object_sha256).reference_count)
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            self.assertEqual(2, connection.execute("SELECT count(*) FROM documents").fetchone()[0])
            self.assertEqual(2, connection.execute("SELECT count(*) FROM provenance_events").fetchone()[0])
            self.assertEqual(2, connection.execute("SELECT count(*) FROM outbox_events").fetchone()[0])
        finally:
            connection.close()
        with self.assertRaises(ObjectReferenced):
            self.store.delete(referenced.object_sha256)
        with self.store.open(referenced.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(content, stream.read())

    def test_access_policy_denies_unknown_and_controlled_egress_before_exposing_a_reader(self) -> None:
        content = b"policy protected object"
        stored = self.store.put(io.BytesIO(content), put_command())
        original_object_path = object_store_module._object_path

        def forbidden_path(*args: object, **kwargs: object) -> object:
            raise AssertionError("denied access resolved the object path")

        with patch.object(object_store_module, "_object_path", forbidden_path):
            for call in (
                {"purpose": "remote-egress"},
                {"purpose": "project-export"},
                {"purpose": "project-export", "access_class": "controlled-egress"},
                {
                    "purpose": "project-export",
                    "access_class": "controlled-egress",
                    "destination_id": "export.local",
                },
            ):
                with self.subTest(call=call), self.assertRaises(ObjectAccessDenied):
                    self.store.open(stored.object_sha256, **call)  # type: ignore[arg-type]

        self.assertIs(object_store_module._object_path, original_object_path)
        with self.store.open(stored.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(content, stream.read())

    def test_injected_access_policy_allows_only_an_exact_bounded_decision(self) -> None:
        content = b"explicit controlled egress"
        stored = self.store.put(io.BytesIO(content), put_command())
        allowed = RecordingAccessPolicy()
        policy_store = create_local_object_store(
            self.project,
            PROJECT_ID,
            allow_plaintext_fixture=True,
            access_policy=allowed,
        )
        with policy_store.open(
            stored.object_sha256,
            purpose="provider-egress",
            access_class="controlled-egress",
            destination_id="provider.local-model",
        ) as stream:
            self.assertEqual(content, stream.read())
        self.assertEqual(1, len(allowed.requests))
        request = allowed.requests[0]
        self.assertEqual(PROJECT_ID, request.project_id)
        self.assertEqual(stored, request.object_metadata)
        self.assertEqual("provider.local-model", request.destination_id)

        for policy in (RecordingAccessPolicy("require-confirmation"), FailingAccessPolicy()):
            denied_store = create_local_object_store(
                self.project,
                PROJECT_ID,
                allow_plaintext_fixture=True,
                access_policy=policy,
            )
            with self.subTest(policy=type(policy).__name__), self.assertRaises(ObjectAccessDenied):
                denied_store.open(
                    stored.object_sha256,
                    purpose="provider-egress",
                    access_class="controlled-egress",
                    destination_id="provider.local-model",
                )

    def test_document_linkage_requires_currently_available_object_state(self) -> None:
        factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)
        for index, storage_state in enumerate(("deleted", "quarantined", "pending"), start=20):
            stored = self.store.put(io.BytesIO(f"state-{storage_state}".encode()), put_command())
            connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE object_records SET storage_state=?, verified_at=NULL WHERE object_sha256=?",
                    (storage_state, stored.object_sha256),
                )
                connection.execute("COMMIT")
            finally:
                connection.close()
            with (
                self.subTest(storage_state=storage_state),
                factory() as unit,
                self.assertRaises(RepositoryConflict),
            ):
                unit.aggregates.append(
                    document_draft(index, stored.object_sha256),
                    event(index),
                    expected_revision=None,
                )

        available = self.store.put(io.BytesIO(b"available-document"), put_command())
        with factory() as unit:
            unit.aggregates.append(document_draft(30, available.object_sha256), event(30), expected_revision=None)
            unit.commit()
        connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
        try:
            for table in ("aggregate_revisions", "documents", "provenance_events", "outbox_events"):
                self.assertEqual(1, connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        finally:
            connection.close()

    def test_unreferenced_delete_is_durable_and_restart_cleans_abandoned_staging(self) -> None:
        stored = self.store.put(io.BytesIO(b"disposable derivative"), put_command())
        self.store.delete(stored.object_sha256)
        self.store.delete(stored.object_sha256)
        with self.assertRaises(ObjectNotFound):
            self.store.open(stored.object_sha256, purpose="document-analysis")
        self.assertEqual("deleted", self.store.metadata(stored.object_sha256).storage_state)
        self.assertEqual((), self.object_files())

        abandoned = self.project / ".tmp" / "object-store" / "abandoned.partial"
        abandoned.parent.mkdir(parents=True, exist_ok=True)
        abandoned.write_bytes(b"not published")
        create_local_object_store(self.project, PROJECT_ID, allow_plaintext_fixture=True)
        self.assertFalse(abandoned.exists())

    def test_delete_crash_recovery_restores_before_commit_and_discards_after_commit(self) -> None:
        precommit = self.store.put(io.BytesIO(b"precommit-delete-recovery"), put_command())
        original_execute = CanonicalConnection.execute

        def crash_before_update(connection: CanonicalConnection, sql: str, parameters: object = ()):
            if "SET storage_state='deleted'" in sql:
                raise KeyboardInterrupt("injected precommit process death")
            return original_execute(connection, sql, parameters)

        with patch.object(CanonicalConnection, "execute", crash_before_update), self.assertRaises(KeyboardInterrupt):
            self.store.delete(precommit.object_sha256)
        staged = tuple((self.project / ".tmp" / "object-store").glob("delete-*.partial"))
        self.assertEqual(1, len(staged))
        self.assertEqual((), self.object_files())
        restarted = create_local_object_store(self.project, PROJECT_ID, allow_plaintext_fixture=True)
        self.assertFalse(staged[0].exists())
        with restarted.open(precommit.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(b"precommit-delete-recovery", stream.read())

        postcommit = restarted.put(io.BytesIO(b"postcommit-delete-recovery"), put_command())
        crashed = False

        def crash_after_commit(connection: CanonicalConnection, sql: str, parameters: object = ()):
            nonlocal crashed
            result = original_execute(connection, sql, parameters)
            if sql.strip() == "COMMIT" and not crashed:
                crashed = True
                raise KeyboardInterrupt("injected postcommit process death")
            return result

        with patch.object(CanonicalConnection, "execute", crash_after_commit), self.assertRaises(KeyboardInterrupt):
            restarted.delete(postcommit.object_sha256)
        staged_after = tuple((self.project / ".tmp" / "object-store").glob("delete-*.partial"))
        self.assertEqual(1, len(staged_after))
        recovered = create_local_object_store(self.project, PROJECT_ID, allow_plaintext_fixture=True)
        self.assertFalse(staged_after[0].exists())
        self.assertEqual("deleted", recovered.metadata(postcommit.object_sha256).storage_state)
        with self.assertRaises(ObjectNotFound):
            recovered.open(postcommit.object_sha256, purpose="document-analysis")

    def test_failed_delete_restore_retains_recovery_bytes_for_retry(self) -> None:
        stored = self.store.put(io.BytesIO(b"restore-must-be-retryable"), put_command())
        original_execute = CanonicalConnection.execute

        def crash_before_update(connection: CanonicalConnection, sql: str, parameters: object = ()):
            if "SET storage_state='deleted'" in sql:
                raise KeyboardInterrupt("injected precommit process death")
            return original_execute(connection, sql, parameters)

        with patch.object(CanonicalConnection, "execute", crash_before_update), self.assertRaises(KeyboardInterrupt):
            self.store.delete(stored.object_sha256)
        staged = next((self.project / ".tmp" / "object-store").glob("delete-*.partial"))
        with (
            patch.object(object_store_module, "_move_no_replace", side_effect=OSError("injected restore failure")),
            self.assertRaises(ObjectStoreProblem),
        ):
            create_local_object_store(self.project, PROJECT_ID, allow_plaintext_fixture=True)
        self.assertTrue(staged.exists())
        restarted = create_local_object_store(self.project, PROJECT_ID, allow_plaintext_fixture=True)
        with restarted.open(stored.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(b"restore-must-be-retryable", stream.read())

    def test_delete_database_failure_rolls_file_and_metadata_back(self) -> None:
        content = b"transactionally preserved"
        stored = self.store.put(io.BytesIO(content), put_command())
        original_execute = CanonicalConnection.execute

        def fail_delete_update(
            connection: CanonicalConnection,
            sql: str,
            parameters: object = (),
        ):
            if "SET storage_state='deleted'" in sql:
                raise sqlite3.OperationalError("injected delete metadata failure")
            return original_execute(connection, sql, parameters)

        with (
            patch.object(CanonicalConnection, "execute", fail_delete_update),
            self.assertRaises(ObjectStoreProblem) as raised,
        ):
            self.store.delete(stored.object_sha256)
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)
        self.assertEqual("available", self.store.metadata(stored.object_sha256).storage_state)
        with self.store.open(stored.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(content, stream.read())

    def test_put_holds_verified_bytes_through_commit_and_reconciles_commit_ack_failure(self) -> None:
        content = b"held-through-object-publication"
        original_execute = CanonicalConnection.execute
        mutation_attempted = False
        mutation_denied = False
        replacement_denied = False

        def mutate_before_begin(connection: CanonicalConnection, sql: str, parameters: object = ()):
            nonlocal mutation_attempted, mutation_denied, replacement_denied
            if sql.strip() == "BEGIN IMMEDIATE" and not mutation_attempted and self.object_files():
                mutation_attempted = True
                try:
                    self.object_files()[0].write_bytes(b"late substitution")
                except PermissionError:
                    mutation_denied = True
                replacement = self.project.parent / "late-replacement.bin"
                replacement.write_bytes(b"late replacement")
                try:
                    os.replace(replacement, self.object_files()[0])
                except PermissionError:
                    replacement_denied = True
            return original_execute(connection, sql, parameters)

        with patch.object(CanonicalConnection, "execute", mutate_before_begin):
            held = self.store.put(io.BytesIO(content), put_command())
        self.assertTrue(mutation_attempted)
        self.assertTrue(mutation_denied)
        if os.name == "nt":
            self.assertTrue(replacement_denied)
        with self.store.open(held.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(content, stream.read())

        acknowledged = False

        def fail_after_real_commit(connection: CanonicalConnection, sql: str, parameters: object = ()):
            nonlocal acknowledged
            result = original_execute(connection, sql, parameters)
            if sql.strip() == "COMMIT" and not acknowledged:
                acknowledged = True
                raise sqlite3.OperationalError("injected lost commit acknowledgement")
            return result

        committed_content = b"committed-before-acknowledgement-failure"
        with patch.object(CanonicalConnection, "execute", fail_after_real_commit):
            committed = self.store.put(io.BytesIO(committed_content), put_command())
        self.assertEqual("available", committed.storage_state)
        with self.store.open(committed.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(committed_content, stream.read())

        if hasattr(os, "link"):
            alias = self.project.parent / "late-publication-link.bin"
            linked = False

            def link_during_commit(connection: CanonicalConnection, sql: str, parameters: object = ()):
                nonlocal linked
                if sql.strip() == "COMMIT" and not linked:
                    linked = True
                    target = next(
                        path for path in self.object_files() if path.read_bytes() == b"late-hardlink-publication"
                    )
                    os.link(target, alias)
                return original_execute(connection, sql, parameters)

            with (
                patch.object(CanonicalConnection, "execute", link_during_commit),
                self.assertRaises(ObjectCorrupt),
            ):
                self.store.put(io.BytesIO(b"late-hardlink-publication"), put_command())
            self.assertTrue(alias.exists())
            hardlinked_digest = hashlib.sha256(b"late-hardlink-publication").hexdigest()
            self.assertEqual("quarantined", self.store.metadata(hardlinked_digest).storage_state)

            combined_alias = self.project.parent / "late-acknowledgement-link.bin"
            combined_content = b"late-hardlink-with-lost-commit-ack"
            combined = False

            def link_then_lose_commit_ack(connection: CanonicalConnection, sql: str, parameters: object = ()):
                nonlocal combined
                result = original_execute(connection, sql, parameters)
                if sql.strip() == "COMMIT" and not combined:
                    combined = True
                    target = next(path for path in self.object_files() if path.read_bytes() == combined_content)
                    os.link(target, combined_alias)
                    raise sqlite3.OperationalError("injected lost acknowledgement after late hardlink")
                return result

            with (
                patch.object(CanonicalConnection, "execute", link_then_lose_commit_ack),
                self.assertRaises(ObjectCorrupt),
            ):
                self.store.put(io.BytesIO(combined_content), put_command())
            combined_digest = hashlib.sha256(combined_content).hexdigest()
            self.assertEqual("quarantined", self.store.metadata(combined_digest).storage_state)
            self.assertEqual(2, combined_alias.stat().st_nlink)

    def test_open_serializes_rights_transition_and_delete_is_retryable_while_stream_active(self) -> None:
        content = b"rights-and-reader-serialization"
        stored = self.store.put(io.BytesIO(content), put_command())
        with self.store.open(stored.object_sha256, purpose="document-analysis") as stream:
            with self.assertRaises(ObjectBusy):
                self.store.delete(stored.object_sha256)
            self.assertEqual("available", self.store.metadata(stored.object_sha256).storage_state)
            self.assertEqual(content, stream.read())
        self.store.delete(stored.object_sha256)
        self.assertEqual("deleted", self.store.metadata(stored.object_sha256).storage_state)

        rights_content = b"rights-transition-private-content"
        rights_object = self.store.put(io.BytesIO(rights_content), put_command())
        verified = threading.Event()
        continue_open = threading.Event()
        writer_started = threading.Event()
        writer_done = threading.Event()
        original_verified_reader = object_store_module._verified_reader

        def delayed_reader(path: Path, digest: str, length: int):
            reader = original_verified_reader(path, digest, length)
            if digest == rights_object.object_sha256:
                verified.set()
                self.assertTrue(continue_open.wait(5))
            return reader

        def deny_rights() -> None:
            connection = open_canonical_database(self.database, expected_project_id=PROJECT_ID)
            try:
                writer_started.set()
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE object_records SET rights_status='denied' WHERE object_sha256=?",
                    (rights_object.object_sha256,),
                )
                connection.execute("COMMIT")
            finally:
                connection.close()
                writer_done.set()

        with (
            patch.object(object_store_module, "_verified_reader", delayed_reader),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            opened = executor.submit(self.store.open, rights_object.object_sha256, purpose="document-analysis")
            self.assertTrue(verified.wait(5))
            changed = executor.submit(deny_rights)
            self.assertTrue(writer_started.wait(5))
            self.assertFalse(writer_done.wait(0.1))
            continue_open.set()
            stream = opened.result(timeout=5)
            self.assertFalse(writer_done.wait(0.1))
            self.assertEqual(rights_content, stream.read())
            stream.close()
            changed.result(timeout=5)
        with self.assertRaises(ObjectAccessDenied):
            self.store.open(rights_object.object_sha256, purpose="document-analysis")

    @unittest.skipUnless(hasattr(os, "link"), "hardlink support is unavailable")
    def test_hardlink_alias_is_treated_as_corruption_without_outside_mutation(self) -> None:
        stored = self.store.put(io.BytesIO(b"link-sensitive"), put_command())
        object_file = self.object_files()[0]
        outside = self.project.parent / "outside-object.bin"
        os.link(object_file, outside)
        before = outside.read_bytes()

        with self.assertRaises(ObjectCorrupt):
            self.store.open(stored.object_sha256, purpose="document-analysis")

        self.assertEqual(before, outside.read_bytes())
        self.assertEqual("quarantined", self.store.metadata(stored.object_sha256).storage_state)

    @unittest.skipUnless(hasattr(os, "link"), "hardlink support is unavailable")
    def test_hardlinked_abandoned_staging_fails_closed_without_outside_mutation(self) -> None:
        staging = self.project / ".tmp" / "object-store"
        hostile = staging / "hostile.partial"
        outside = self.project.parent / "outside-staging.bin"
        outside.write_bytes(b"outside staging authority")
        os.link(outside, hostile)
        before = outside.read_bytes()

        with self.assertRaises(ObjectStoreProblem):
            create_local_object_store(self.project, PROJECT_ID, allow_plaintext_fixture=True)

        self.assertEqual(before, outside.read_bytes())
        self.assertTrue(hostile.exists())


if __name__ == "__main__":
    unittest.main()
