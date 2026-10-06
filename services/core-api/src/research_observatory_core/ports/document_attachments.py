"""Portable attachment candidate, result and denial contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from ..rights_policy import RightsSubject

MAX_DOCUMENT_BYTES = 128 * 1024 * 1024


class DocumentPublicationGuard(Protocol):
    def __call__[Result](self, action: Callable[[], Result]) -> Result: ...


class DocumentInspectionProblem(ValueError):
    """Content-free inspection denial crossing the portable attachment port."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


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


type AttachmentStatusState = Literal[
    "metadata-only",
    "candidate",
    "unresolved",
    "committed",
    "cancelled",
    "stale-session",
    "legacy",
    "unavailable",
    "intake-running",
    "intake-failed",
    "intake-cancelled",
]


@dataclass(frozen=True, slots=True)
class DocumentAttachmentStatus:
    """Exact durable database result; committed does not imply reader availability."""

    state: AttachmentStatusState
    project_id: str
    source_assertion_revision_id: str
    work_id: str
    work_revision_id: str
    version_id: str
    version_revision_id: str
    operation_id: str | None
    command_id: str | None
    candidate_id: str | None
    attachment_id: str | None
    document_revision_id: str | None
    intake_code: str | None = None
