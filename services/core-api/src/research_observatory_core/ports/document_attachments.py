"""Portable attachment candidate, result and denial contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..rights_policy import RightsSubject


class DocumentInspection(Protocol):
    @property
    def format(self) -> str: ...

    @property
    def media_type(self) -> str: ...

    @property
    def size_bytes(self) -> int: ...

    @property
    def sha256(self) -> str: ...


class AttachmentProblem(RuntimeError):
    """Bounded, content-free attachment failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class AttachmentCandidate:
    candidate_id: str
    project_id: str
    source_assertion_revision_id: str
    work_id: str
    work_revision_id: str
    version_id: str
    version_revision_id: str
    object_sha256: str
    byte_length: int
    format: str
    media_type: str
    source_name: str
    confirmation_required: bool
    candidate_sha256: str
    rights_subject: RightsSubject


@dataclass(frozen=True, slots=True)
class DocumentAttachment:
    attachment_id: str
    document_id: str
    document_revision_id: str
    candidate_id: str
    work_id: str
    work_revision_id: str
    version_id: str
    version_revision_id: str
    source_assertion_revision_id: str
    object_sha256: str
    rights_policy_revision_id: str
    provenance_event_id: str
    outbox_id: str
