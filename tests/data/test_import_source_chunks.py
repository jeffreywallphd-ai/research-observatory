"""Actual encrypted-object boundary for bounded, write-friendly source replay."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights  # noqa: E402
from research_observatory_core.ingestion.reference_imports import ImportSession, ImportSource  # noqa: E402
from research_observatory_core.ingestion.source_chunks import (  # noqa: E402
    CHUNK_BYTES,
    ChunkedImportSource,
    SourceChunk,
    put_source_chunk,
)
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.data import test_encrypted_object_store as encrypted_fixture  # noqa: E402
from tests.data.test_encrypted_object_store import (  # noqa: E402
    CREATED_AT,
    PROJECT_ID,
    MemoryKeyProvider,
)

PERMITTED = ImportPermission(value="permitted", basis="researcher-confirmed")
RIGHTS = ImportRights(store=PERMITTED, inspect=PERMITTED)


class ImportSourceChunkTests(unittest.TestCase):
    # Reuse only isolated storage setup, not inherited historical test methods.
    setUp = encrypted_fixture.EncryptedObjectStoreTests.setUp
    tearDown = encrypted_fixture.EncryptedObjectStoreTests.tearDown
    project: Path
    v1: bytes

    def store(self):
        return create_local_object_store(
            self.project, PROJECT_ID, key_provider=MemoryKeyProvider({"object-key-v1": self.v1}, "object-key-v1")
        )

    def retain(self, raw: bytes):
        store = self.store()
        return tuple(
            put_source_chunk(store, raw[index : index + CHUNK_BYTES], rights=RIGHTS, created_at=CREATED_AT)
            for index in range(0, len(raw), CHUNK_BYTES)
        )

    def test_restarted_encrypted_source_preserves_bytes_and_releases_writer_before_yield(self):
        raw = b"title\n" + (b"Synthetic private title\n" * 12000)
        chunks = self.retain(raw)
        self.assertGreater(len(chunks), 1)
        observed = bytearray()
        source = ChunkedImportSource(self.store(), chunks, authorize=lambda: RIGHTS)
        while block := source.read(8192):
            observed.extend(block)
            connection = open_canonical_database(self.project / "state/project.sqlite3", expected_project_id=PROJECT_ID)
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.rollback()
            finally:
                connection.close()
        self.assertEqual(raw, observed)
        for path in (self.project / "objects").rglob("*"):
            if path.is_file():
                self.assertNotIn(b"Synthetic private title", path.read_bytes())
        parser = ImportSession(
            ChunkedImportSource(self.store(), chunks, authorize=lambda: RIGHTS),
            ImportSource("fixture.csv", hashlib.sha256(raw).hexdigest()),
            "csv",
        )
        self.assertEqual(12001, sum(1 for _ in parser.records()))
        self.assertTrue(parser.complete)

    def test_unknown_revoked_rights_and_cancelled_authority_deny_buffered_reads(self):
        raw = b"title\nSynthetic\n"
        chunks = self.retain(raw)
        current = RIGHTS
        source = ChunkedImportSource(self.store(), chunks, authorize=lambda: current)
        self.assertEqual(b"t", source.read(1))
        current = ImportRights()
        with self.assertRaisesRegex(ValueError, "import-inspect-denied"):
            source.read(1)
        current = RIGHTS
        with self.assertRaisesRegex(ValueError, "source-closed"):
            source.read(1)
        with self.assertRaisesRegex(ValueError, "import-store-denied"):
            put_source_chunk(self.store(), raw, rights=ImportRights(), created_at=CREATED_AT)

    def test_chunk_length_substitution_and_unbounded_reads_fail_closed(self):
        chunks = self.retain(b"title\nSynthetic\n")
        substituted = (SourceChunk(chunks[0].object_sha256, chunks[0].byte_length + 1),)
        source = ChunkedImportSource(self.store(), substituted, authorize=lambda: RIGHTS)
        with self.assertRaisesRegex(ValueError, "source-chunk-length"):
            source.read(8192)
        source = ChunkedImportSource(self.store(), chunks, authorize=lambda: RIGHTS)
        for size in (-1, CHUNK_BYTES + 1, True):
            with self.assertRaises(ValueError):
                source.read(size)
        with self.assertRaisesRegex(ValueError, "source-chunk-limit"):
            put_source_chunk(self.store(), b"x" * (CHUNK_BYTES + 1), rights=RIGHTS, created_at=CREATED_AT)


if __name__ == "__main__":
    unittest.main()
