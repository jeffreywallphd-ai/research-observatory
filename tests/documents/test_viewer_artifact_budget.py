"""Admission must precede protected allocation and include nested manifests."""

import unittest
from types import SimpleNamespace

from research_observatory_core.document_revisions import DocumentRevisionProblem
from research_observatory_core.document_viewer_allocations import ViewerArtifactReads, viewer_core_allowance


class ProtectedReads:
    def __init__(self):
        self.calls = []

    def _read_protected_document_artifact(self, connection, receipt, media_type):
        self.calls.append((receipt.byte_length, media_type))
        return b"synthetic"


class ViewerArtifactBudgetTests(unittest.TestCase):
    def test_first_oversized_artifact_is_denied_before_decrypting(self):
        underlying = ProtectedReads()
        reader = ViewerArtifactReads(underlying, 128 * 1024 * 1024)
        with self.assertRaisesRegex(DocumentRevisionProblem, "viewer-resource-limit"):
            reader._read_protected_document_artifact(None, SimpleNamespace(byte_length=64 * 1024 * 1024), "synthetic")
        self.assertEqual([], underlying.calls)

    def test_individually_small_nested_reads_share_a_cumulative_limit(self):
        underlying = ProtectedReads()
        reader = ViewerArtifactReads(underlying, 128 * 1024 * 1024)
        size = reader.remaining // reader.cost_multiplier // 2 + 1
        receipt = SimpleNamespace(byte_length=size)
        self.assertEqual(b"synthetic", reader._read_protected_document_artifact(None, receipt, "accepted"))
        with self.assertRaisesRegex(DocumentRevisionProblem, "viewer-resource-limit"):
            reader._read_protected_document_artifact(None, receipt, "normalized")
        self.assertEqual([(size, "accepted")], underlying.calls)

    def test_raw_and_repeated_manifest_reads_cannot_bypass_admission(self):
        underlying = ProtectedReads()
        reader = ViewerArtifactReads(underlying, 128 * 1024 * 1024)
        receipt = SimpleNamespace(byte_length=1)
        reader._read_protected_document_artifact(None, receipt, "raw")
        before = reader.remaining
        reader._read_parser_manifest(None, receipt)
        self.assertLess(reader.remaining, before)
        before = reader.remaining
        reader._read_parser_manifest(None, receipt)
        self.assertLess(reader.remaining, before)
        with self.assertRaisesRegex(DocumentRevisionProblem, "viewer-resource-limit"):
            reader._read_parser_manifest(None, SimpleNamespace(byte_length=64 * 1024 * 1024))
        self.assertEqual(3, len(underlying.calls))

    def test_authoritative_source_length_determines_allowance_without_changing_parser_limits(self):
        self.assertEqual(32 * 1024 * 1024, viewer_core_allowance(128 * 1024 * 1024))
        self.assertEqual(150 * 1024 * 1024, viewer_core_allowance(10 * 1024 * 1024))
        for invalid in (True, -1, 0, 128 * 1024 * 1024 + 1, 1.5):
            with self.assertRaisesRegex(DocumentRevisionProblem, "viewer-resource-limit"):
                viewer_core_allowance(invalid)
