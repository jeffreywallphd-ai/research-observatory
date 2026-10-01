"""The populated predecessor remains literal and usable by SQLite and SQLCipher."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]

from tests.reconciliation.v16_predecessor import (
    APPLICATION_ID,
    FIRST_VERSION_REVISION_ID,
    FIXTURE_HASHES,
    FIXTURES,
    ORIGINAL_BINARY_SHA256,
    POPULATED_COUNTS,
    PROJECT_ID,
    ROWS_SHA256,
    SCHEMA_SHA256,
    SECOND_VERSION_REVISION_ID,
    restore_v16,
    row_fingerprint,
    schema_fingerprint,
)


class V16PredecessorTests(unittest.TestCase):
    def test_committed_literal_documents_and_populated_history(self):
        for name, digest in FIXTURE_HASHES.items():
            self.assertEqual(digest, hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest())
        temporary_root = Path(__file__).resolve().parents[2] / "artifacts/tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as temporary:
            database = Path(temporary) / "state/project.sqlite3"
            witness = restore_v16(database)
            self.assertEqual(PROJECT_ID, witness["projectId"])
            self.assertEqual(POPULATED_COUNTS, witness["counts"])
            self.assertEqual((FIRST_VERSION_REVISION_ID, SECOND_VERSION_REVISION_ID), witness["versionRevisionIds"])
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
                self.assertEqual(SCHEMA_SHA256, schema_fingerprint(db))
                self.assertEqual(ROWS_SHA256, row_fingerprint(db))
                self.assertEqual(2, db.execute("SELECT COUNT(*) FROM import_source_records").fetchone()[0])
                self.assertEqual(2, db.execute("SELECT COUNT(*) FROM reconciliation_assertions").fetchone()[0])
                self.assertEqual(1, db.execute("SELECT COUNT(*) FROM reconciliation_version_relations").fetchone()[0])

    def test_reconstruction_matches_original_when_local_capture_is_available(self):
        original = Path(__file__).resolve().parents[2] / "artifacts/tmp/w2-v16-populated-original.sqlite3"
        if not original.exists():
            self.skipTest("ignored original binary is optional outside the capture workspace")
        self.assertEqual(ORIGINAL_BINARY_SHA256, hashlib.sha256(original.read_bytes()).hexdigest())
        temporary_root = Path(__file__).resolve().parents[2] / "artifacts/tmp"
        with tempfile.TemporaryDirectory(dir=temporary_root) as temporary:
            reconstructed = Path(temporary) / "state/project.sqlite3"
            restore_v16(reconstructed)
            with (
                closing(sqlite3.connect(original.as_uri() + "?mode=ro&immutable=1", uri=True)) as before,
                closing(sqlite3.connect(reconstructed.as_uri() + "?mode=ro&immutable=1", uri=True)) as after,
            ):
                self.assertEqual(schema_fingerprint(before), schema_fingerprint(after))
                self.assertEqual(row_fingerprint(before), row_fingerprint(after))

    def test_literal_restore_exports_to_real_sqlcipher_with_ephemeral_key(self):
        temporary_root = Path(__file__).resolve().parents[2] / "artifacts/tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as temporary:
            source = Path(temporary) / "state/project.sqlite3"
            encrypted = Path(temporary) / "protected.sqlite3"
            restore_v16(source)
            key = os.urandom(32)
            with closing(sqlcipher.connect(source.as_uri() + "?mode=ro", uri=True, isolation_level=None)) as db:
                db.execute("ATTACH DATABASE ? AS protected KEY ?", (str(encrypted), f"x'{key.hex()}'"))
                db.execute("SELECT sqlcipher_export('protected')").fetchone()
                db.execute(f"PRAGMA protected.application_id={APPLICATION_ID}")
                db.execute("PRAGMA protected.user_version=16")
                db.execute("DETACH DATABASE protected")
            self.assertNotEqual(b"SQLite format 3\x00", encrypted.read_bytes()[:16])
            with closing(sqlcipher.connect(encrypted, isolation_level=None)) as db:
                db.execute(f"PRAGMA key=\"x'{key.hex()}'\"")
                self.assertEqual(SCHEMA_SHA256, schema_fingerprint(db))
                self.assertEqual(ROWS_SHA256, row_fingerprint(db))
                self.assertEqual((16,), db.execute("PRAGMA user_version").fetchone())
                self.assertEqual(("ok",), db.execute("PRAGMA quick_check").fetchone())
                self.assertEqual([], db.execute("PRAGMA cipher_integrity_check").fetchall())
                for name, count in POPULATED_COUNTS.items():
                    self.assertEqual(count, db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0], name)
