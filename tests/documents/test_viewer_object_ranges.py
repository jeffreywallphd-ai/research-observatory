"""Bounded original ranges over the real encrypted object adapter."""

import threading
import unittest
from unittest.mock import patch

from research_observatory_core import object_store
from research_observatory_core.ports.object_store import ObjectAccessDenied, ObjectReadCancelled

from tests.documents import test_viewer_read_cancellation as cancellation


class ViewerObjectRangeTests(unittest.TestCase):
    def setUp(self):
        self.f = cancellation.ViewerReadCancellationTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def read(self, start, end, **options):
        return self.f.f.store.read_document_attachment_range(
            self.f.attachment.attachment_id,
            self.f.attachment.document_revision_id,
            start=start,
            end=end,
            actor=self.f.f.corpus.actor,
            **options,
        )

    def test_first_and_distant_ranges_are_exact_and_all_prefix_reads_are_bounded(self):
        sizes = []
        original = object_store._EncryptedReader.read

        def observed(reader, size=-1):
            sizes.append(size)
            return original(reader, size)

        with patch.object(object_store._EncryptedReader, "read", observed):
            self.assertEqual(self.f.content[:32], self.read(0, 32))
            self.assertEqual(self.f.content[-32:], self.read(len(self.f.content) - 32, len(self.f.content)))
        self.assertTrue(sizes)
        self.assertTrue(all(0 < size <= 1024 * 1024 for size in sizes))
        self.assertFalse(object_store._READERS.in_use(self.f.f.corpus.project, self.f.candidate.object_sha256))

    def test_invalid_noninteger_and_oversize_ranges_deny_without_an_owned_reader(self):
        for start, end in ((-1, 1), (0, 0), (1, 0), (True, 32), (0, 1.5), (0, 1024 * 1024 + 1)):
            with self.subTest(start=start, end=end), self.assertRaises(ObjectAccessDenied):
                self.read(start, end)
        with self.assertRaises(ObjectAccessDenied):
            self.read(len(self.f.content) - 1, len(self.f.content) + 1)
        self.f.assert_preserved_and_released()

    def test_cancel_during_prefix_discard_rolls_back_and_fresh_retry_returns_exact_range(self):
        stopped = threading.Event()
        original = object_store._EncryptedReader.read
        observed = []

        def cancel_after_prefix(reader, size=-1):
            value = original(reader, size)
            observed.append(size)
            stopped.set()
            return value

        with (
            patch.object(object_store._EncryptedReader, "read", cancel_after_prefix),
            self.assertRaises(ObjectReadCancelled),
        ):
            self.read(len(self.f.content) - 32, len(self.f.content), cancellation_requested=stopped.is_set)
        self.assertEqual([1024 * 1024], observed)
        self.f.assert_preserved_and_released()
        self.assertEqual(self.f.content[-32:], self.read(len(self.f.content) - 32, len(self.f.content)))

    def test_changed_inspect_rights_deny_every_range(self):
        current = self.f.f.rights.current(self.f.candidate.rights_subject, actor=self.f.f.corpus.actor)
        self.f.f.publish_right(
            self.f.candidate, value="denied", predecessor=current.revision_id, inspect=True
        )
        with self.assertRaises(ObjectAccessDenied):
            self.read(0, 32)
        self.assertFalse(object_store._READERS.in_use(self.f.f.corpus.project, self.f.candidate.object_sha256))


if __name__ == "__main__":
    unittest.main(verbosity=2)
