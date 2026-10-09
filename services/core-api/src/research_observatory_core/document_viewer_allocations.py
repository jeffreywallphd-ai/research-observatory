"""Trusted Viewer-only admission; other revision readers retain their contracts."""

from copy import copy

from .document_revisions import DocumentRevisionProblem
from .source_anchor_repository import LocalSourceAnchorRepository

_MIB = 1024 * 1024
_SOURCE_LIMIT = 128 * _MIB
_FRAME_AND_CONTEXT_ALLOWANCE = 24 * _MIB


def viewer_core_allowance(source_bytes: int) -> int:
    if type(source_bytes) is not int or not 0 < source_bytes <= _SOURCE_LIMIT:
        raise DocumentRevisionProblem("viewer-resource-limit")
    # Match the trusted decoder allowance (source +16MiB), main/surfaces64MiB,
    # assets8MiB, and8MiB reserved for the bounded serialized range/handoff.
    return 256 * _MIB - (source_bytes + 16 * _MIB) - 64 * _MIB - 8 * _MIB - 8 * _MIB


class ViewerArtifactReads:
    """One cumulative ledger through accepted/result/raw/manifest validation.

    The fixed frame allowance covers4MiB ciphertext/plaintext frames, the
    previous frame, read_exact copies and the retained crypto output buffer.
    Artifact charges include reader/serialization copies, decoded text and
    canonical normalization backing arrays. Nothing is refunded during a call:
    prior models/raw data can remain live during nested validation. Admission
    precedes the actual adapter, which still validates metadata and authenticates
    the complete encrypted artifact. This wrapper grants no read authority.
    """

    cost_multiplier = 128

    def __init__(self, objects, source_bytes):
        self._objects = objects
        self.remaining = viewer_core_allowance(source_bytes) - _FRAME_AND_CONTEXT_ALLOWANCE

    def __getattr__(self, name):
        return getattr(self._objects, name)

    def _read_protected_document_artifact(self, connection, receipt, media_type):
        size = receipt.byte_length
        if type(size) is not int or size <= 0:
            raise DocumentRevisionProblem("viewer-resource-limit")
        charge = size * self.cost_multiplier + 4096
        if charge > self.remaining:
            raise DocumentRevisionProblem("viewer-resource-limit")
        self.remaining -= charge
        return self._objects._read_protected_document_artifact(connection, receipt, media_type)

    def _read_parser_manifest(self, connection, receipt):
        # Delegating this helper would let its internal adapter call bypass the
        # request ledger. Repeated manifest reads must retain their own charges.
        return self._read_protected_document_artifact(
            connection, receipt, "application/vnd.research-observatory.parser-attempt+json"
        )


def viewer_revision_reads(revisions, source_bytes):
    bounded = copy(revisions)
    bounded.objects = ViewerArtifactReads(revisions.objects, source_bytes)
    return bounded


class ViewerOutlineReads(LocalSourceAnchorRepository):
    """Preserve the fixed viewer denial without changing ordinary anchor errors."""

    def _bounded(self, action):
        try:
            self._current_actor()
            return self.revisions._bounded(action)
        except DocumentRevisionProblem as problem:
            if problem.code == "viewer-resource-limit":
                raise
            raise DocumentRevisionProblem("source-anchor-denied") from None
        except Exception:
            raise DocumentRevisionProblem("source-anchor-denied") from None
