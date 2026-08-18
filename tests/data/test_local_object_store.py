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

from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.object_store import (  # noqa: E402
    ObjectAccessDenied,
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


def put_command(**overrides: object) -> ObjectPutCommand:
    values: dict[str, object] = {
        "media_type": "application/pdf",
        "rights_status": "allowed",
        "protection_profile": "plaintext-fixture-v1",
        "retention_class": "project-lifetime",
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
        self.store = create_local_object_store(self.project, PROJECT_ID)

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
        files = self.object_files()
        self.assertEqual(1, len(files))
        relative = files[0].relative_to(self.project / "objects")
        self.assertEqual(3, len(relative.parts))
        self.assertNotIn(expected, relative.parts)
        self.assertEqual(64 + len(".blob"), len(relative.name))

        restarted = create_local_object_store(self.project, PROJECT_ID)
        with restarted.open(expected, purpose="document-analysis") as stream:
            self.assertFalse(hasattr(stream, "name"))
            self.assertFalse(hasattr(stream, "fileno"))
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
        second_store = create_local_object_store(second, SECOND_PROJECT_ID)
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

    def test_duplicate_metadata_conflict_preserves_original_bytes_and_projection(self) -> None:
        content = b"stable identity and meaning"
        original = self.store.put(io.BytesIO(content), put_command())
        with self.assertRaises(ObjectConflict):
            self.store.put(
                io.BytesIO(content),
                put_command(media_type="text/plain"),
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
        with self.assertRaises(ObjectReferenced):
            self.store.delete(referenced.object_sha256)
        with self.store.open(referenced.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(content, stream.read())

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
        create_local_object_store(self.project, PROJECT_ID)
        self.assertFalse(abandoned.exists())

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
            create_local_object_store(self.project, PROJECT_ID)

        self.assertEqual(before, outside.read_bytes())
        self.assertTrue(hostile.exists())


if __name__ == "__main__":
    unittest.main()
