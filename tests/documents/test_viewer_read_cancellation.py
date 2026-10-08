"""Cancellation over real encrypted attached originals; no renderer/tier claim."""

import io
import threading
import unittest
from contextlib import closing
from unittest.mock import patch

from research_observatory_core import object_store
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ports.object_store import ObjectCorrupt, ObjectReadCancelled
from research_observatory_core.storage import open_canonical_database

from tests.documents import test_local_attachment as attachments


class ViewerReadCancellationTests(unittest.TestCase):
    def setUp(self):
        self.f = attachments.LocalAttachmentServiceTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.content = b"Synthetic source for cancellation.\n" * 260_000
        self.candidate = self.f.service.stage(
            io.BytesIO(self.content),
            source_name="paper.txt",
            declared_media_type="text/plain",
            source_assertion_revision_id=self.f._assertion_id(),
            work_id=self.f.corpus.work_id,
            work_revision_id=self.f.work_revision_id,
            version_id=self.f.version.version_id,
            version_revision_id=self.f.version.revision_id,
            actor=self.f.corpus.actor,
        )
        self.f.publish_right(self.candidate, inspect=True)
        self.attachment = self.f.service.commit(
            self.candidate.candidate_id,
            confirmation_sha256=self.candidate.candidate_sha256,
            command_id=new_uuid_v7(),
            actor=self.f.corpus.actor,
        )
        self.before_metadata = self.f.store.metadata(self.candidate.object_sha256)

    def read(self, **options):
        return self.f.store.open_document_attachment(
            self.attachment.attachment_id,
            self.attachment.document_revision_id,
            actor=self.f.corpus.actor,
            **options,
        )

    def assert_preserved_and_released(self):
        current = self.f.store.metadata(self.candidate.object_sha256)
        self.assertEqual("available", current.storage_state)
        self.assertEqual(
            self.before_metadata.verified_at, current.verified_at, "cancelled read must roll back its writer"
        )
        self.assertFalse(object_store._READERS.in_use(self.f.corpus.project, self.candidate.object_sha256))
        with closing(open_canonical_database(self.f.corpus.database, expected_project_id=self.f.corpus.project)) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("ROLLBACK")
        with self.read() as source:
            self.assertEqual(self.content, source.read())

    def test_cancel_before_open_releases_writer_and_preserves_exact_source(self):
        with self.assertRaisesRegex(ObjectReadCancelled, "read cancel"):
            self.read(cancellation_requested=lambda: True)
        self.assert_preserved_and_released()

    def test_cancel_during_authentication_returns_no_stream_and_does_not_quarantine(self):
        stopped = threading.Event()
        original = object_store._pull_frame
        observed = []

        def signal_after_first_frame(*args, **kwargs):
            result = original(*args, **kwargs)
            observed.append(len(result[0]))
            stopped.set()
            return result

        with (
            patch.object(object_store, "_pull_frame", signal_after_first_frame),
            self.assertRaisesRegex(ObjectReadCancelled, "read cancel"),
        ):
            self.read(cancellation_requested=stopped.is_set)
        self.assertEqual(1, len(observed), "cancellation must stop at the next bounded frame checkpoint")
        self.assert_preserved_and_released()

    def test_cancel_after_verified_open_closes_live_read_and_does_not_return_buffered_bytes(self):
        stopped = threading.Event()
        source = self.read(cancellation_requested=stopped.is_set)
        self.addCleanup(source.close)
        self.assertEqual(self.content[:32], source.read(32))
        stopped.set()
        with self.assertRaisesRegex(ObjectReadCancelled, "read cancel"):
            source.read(32)
        self.assert_preserved_and_released()

    def test_failing_trusted_cancellation_probe_denies_without_corruption_classification(self):
        def unavailable():
            raise OSError("synthetic unavailable cancellation signal")

        with self.assertRaisesRegex(ObjectReadCancelled, "read cancel"):
            self.read(cancellation_requested=unavailable)
        self.assert_preserved_and_released()

    def test_cancel_during_plaintext_frame_read_denies_even_when_one_frame_satisfies_the_range(self):
        stopped = threading.Event()
        source = self.read(cancellation_requested=stopped.is_set)
        self.addCleanup(source.close)
        original = object_store._pull_frame

        def signal_after_frame(*args, **kwargs):
            result = original(*args, **kwargs)
            stopped.set()
            return result

        with (
            patch.object(object_store, "_pull_frame", signal_after_frame),
            self.assertRaises(ObjectReadCancelled),
        ):
            source.read(32)
        self.assert_preserved_and_released()

    def test_corrupt_final_frame_with_live_cancel_probe_still_denies_before_first_byte(self):
        ciphertext = self.f.project_root / "objects" / object_store._object_relative_path(
            self.f.corpus.project, self.candidate.object_sha256
        )
        payload = bytearray(ciphertext.read_bytes())
        payload[-1] ^= 1
        ciphertext.write_bytes(payload)
        with self.assertRaises(ObjectCorrupt):
            self.read(cancellation_requested=lambda: False)
        self.assertEqual("quarantined", self.f.store.metadata(self.candidate.object_sha256).storage_state)
        self.assertFalse(object_store._READERS.in_use(self.f.corpus.project, self.candidate.object_sha256))


if __name__ == "__main__":
    unittest.main(verbosity=2)
