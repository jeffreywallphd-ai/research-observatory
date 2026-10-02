"""Native-only bounded document intake and exact attachment commands.

Only the trusted desktop supervisor can call these fixed loopback routes. The
stage body has an 8192-byte JSON command prefix followed by raw selected bytes;
the prefix contains no source path or claimed actor. Plaintext is held only in
the bounded producer/consumer queue while the object store encrypts it.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict
from typing import Annotated, BinaryIO, Protocol, cast

from fastapi import APIRouter, FastAPI, Request, Response
from pydantic import Field, ValidationError, field_validator
from starlette.requests import ClientDisconnect

from workers.document.inspection import MAX_DOCUMENT_BYTES, DocumentInspectionError

from .corpus.membership import CorpusProblem
from .import_api import BoundedImportRoute
from .ingestion.import_drafts import DraftValue, Identity, ProjectIdentity
from .ports.document_attachments import AttachmentCandidate, AttachmentProblem, DocumentAttachment
from .ports.import_previews import PreviewProblem
from .ports.object_store import (
    ObjectSourceTooLarge,
    ObjectStagingCancelled,
    ObjectStoragePressure,
    ObjectStoreProblem,
)
from .projects import ProjectLifecycleProblem
from .rights_policy import RightsSubject
from .transport import CoreProblem, problem_detail

_HEADER_BYTES = 8192
_WIRE_CHUNK_BYTES = 128 * 1024
_QUEUE_CHUNKS = 2
_STAGE_DEADLINE_SECONDS = 180
_MAX_WIRE_BYTES = 4 + _HEADER_BYTES + MAX_DOCUMENT_BYTES
type SessionId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]


class DocumentProject(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    project_id: ProjectIdentity


class DocumentSession(DocumentProject):
    session_id: SessionId


class DocumentStageCommand(DocumentSession):
    source_name: Annotated[str, Field(min_length=1, max_length=255)]
    declared_media_type: Annotated[str, Field(min_length=1, max_length=200)] | None
    source_assertion_revision_id: Identity
    work_id: Identity
    work_revision_id: Identity
    version_id: Identity
    version_revision_id: Identity
    byte_length: Annotated[int, Field(strict=True, ge=1, le=MAX_DOCUMENT_BYTES)]

    @field_validator("source_name")
    @classmethod
    def selected_basename(cls, name: str) -> str:
        if name in {".", ".."} or "\x00" in name or "/" in name or "\\" in name:
            raise ValueError("document-source-name-invalid")
        return name


class DocumentAddress(DocumentSession):
    candidate_id: Identity


class DocumentCommit(DocumentAddress):
    confirmation_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    command_id: Identity


class DocumentContext(DraftValue):
    project_id: ProjectIdentity
    session_id: SessionId


class DocumentCandidateView(DraftValue):
    candidate_id: Identity
    project_id: ProjectIdentity
    source_assertion_revision_id: Identity
    work_id: Identity
    work_revision_id: Identity
    version_id: Identity
    version_revision_id: Identity
    object_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    byte_length: Annotated[int, Field(strict=True, ge=1, le=MAX_DOCUMENT_BYTES)]
    format: str
    media_type: str
    source_name: str
    confirmation_required: bool
    candidate_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    rights_subject: RightsSubject


class DocumentAttachmentView(DraftValue):
    attachment_id: Identity
    document_id: Identity
    document_revision_id: Identity
    candidate_id: Identity
    work_id: Identity
    work_revision_id: Identity
    version_id: Identity
    version_revision_id: Identity
    source_assertion_revision_id: Identity
    object_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    rights_policy_revision_id: Identity
    provenance_event_id: Identity
    outbox_id: Identity


class DocumentRuntimePort(Protocol):
    def context(self, root: str, project_id: str) -> str: ...

    def stage(
        self,
        command: DocumentStageCommand,
        source: BinaryIO,
        *,
        trace_id: str,
        cancellation_requested: Callable[[], bool],
    ) -> AttachmentCandidate: ...

    def load_candidate(
        self, root: str, project_id: str, session_id: str, candidate_id: str, *, trace_id: str
    ) -> AttachmentCandidate: ...

    def cancel(self, root: str, project_id: str, session_id: str, candidate_id: str, *, trace_id: str) -> None: ...

    def commit(self, command: DocumentCommit, *, trace_id: str) -> DocumentAttachment: ...


class _QueuedSource:
    """Sync BinaryIO reader over at most two 128 KiB in-memory IPC chunks."""

    def __init__(self, frames: queue.Queue[bytes | None], cancelled: threading.Event) -> None:
        self._frames = frames
        self._cancelled = cancelled
        self._pending = b""
        self._ended = False

    def read(self, size: int = -1) -> bytes:
        if not 0 < size <= 1_048_576:
            raise ValueError("document-stream-read-invalid")
        result = bytearray()
        while len(result) < size and not self._ended:
            if self._cancelled.is_set():
                raise ObjectStagingCancelled()
            if not self._pending:
                try:
                    frame = self._frames.get(timeout=0.1)
                except queue.Empty:
                    continue
                if frame is None:
                    self._ended = True
                    break
                self._pending = frame
            take = min(size - len(result), len(self._pending))
            result.extend(self._pending[:take])
            self._pending = self._pending[take:]
        return bytes(result)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("document-command-duplicate-key")
        value[key] = item
    return value


def _problem(request: Request, status: int, code: str, detail: str, remediation: str) -> CoreProblem:
    return CoreProblem(
        problem_detail(
            status=status,
            code=code,
            title="Document attachment unavailable" if status >= 500 else "Document attachment needs attention",
            detail=detail,
            trace_id=request.state.trace_id,
            retryable=status in {503, 507},
            remediation=remediation,
        )
    )


def _mapped_error(request: Request, error: BaseException) -> CoreProblem:
    if isinstance(error, DocumentInspectionError):
        code = error.code
        if code == "oversize":
            return _problem(
                request,
                413,
                "RO-CORE-DOCUMENT-OVERSIZE",
                "The selected file exceeds 128 MiB.",
                "Choose a smaller file.",
            )
        if code == "cancelled":
            return _problem(
                request,
                409,
                "RO-CORE-DOCUMENT-CANCELLED",
                "The attachment was cancelled.",
                "Select the file again to retry.",
            )
        if code == "worker-unavailable":
            return _problem(
                request,
                503,
                "RO-CORE-DOCUMENT-WORKER-UNAVAILABLE",
                "Document inspection is unavailable.",
                "Retry after the local worker is available.",
            )
        explanation = {
            "unsupported-format": "The selected document format is unsupported.",
            "password-protected": "The selected document is password protected.",
            "unsafe-content": "The selected document contains unsafe content.",
            "malformed-content": "The selected document is malformed.",
            "format-mismatch": "The selected filename or declared type does not match its content.",
        }.get(code, "The selected document failed inspection.")
        return _problem(
            request,
            422,
            "RO-CORE-DOCUMENT-" + code.upper(),
            explanation,
            "Choose a safe supported copy and retry.",
        )
    if isinstance(error, ObjectSourceTooLarge):
        return _problem(
            request, 413, "RO-CORE-DOCUMENT-OVERSIZE", "The selected file exceeds 128 MiB.", "Choose a smaller file."
        )
    if isinstance(error, ObjectStagingCancelled):
        return _problem(
            request,
            409,
            "RO-CORE-DOCUMENT-CANCELLED",
            "The attachment was cancelled.",
            "Select the file again to retry.",
        )
    if isinstance(error, ObjectStoragePressure):
        return _problem(
            request,
            507,
            "RO-CORE-DOCUMENT-STORAGE-PRESSURE",
            "Local storage cannot admit this file.",
            "Free space or select a smaller file, then retry.",
        )
    if isinstance(error, ObjectStoreProblem):
        return _problem(
            request,
            503,
            "RO-CORE-DOCUMENT-STORAGE-UNAVAILABLE",
            "Encrypted local storage is unavailable.",
            "Retry after checking the local project.",
        )
    if isinstance(error, AttachmentProblem):
        code = error.code
        if "rights" in code:
            status, public = 403, "RO-CORE-DOCUMENT-RIGHTS-DENIED"
        elif "authority" in code:
            status, public = 403, "RO-CORE-DOCUMENT-AUTHORITY-CHANGED"
        elif code == "attachment-confirmation-required":
            status, public = 409, "RO-CORE-DOCUMENT-CONFIRMATION-REQUIRED"
        elif code == "attachment-candidate-unavailable":
            status, public = 404, "RO-CORE-DOCUMENT-CANDIDATE-UNAVAILABLE"
        elif "cancelled" in code:
            status, public = 409, "RO-CORE-DOCUMENT-CANCELLED"
        elif "invalid" in code:
            status, public = 422, "RO-CORE-DOCUMENT-INTAKE-INVALID"
        else:
            status, public = 409, "RO-CORE-DOCUMENT-ASSOCIATION-STALE"
        return _problem(
            request,
            status,
            public,
            "Current attachment authority or selection is unavailable.",
            "Refresh the current project, Work/version, rights and candidate before retrying.",
        )
    if isinstance(error, (PreviewProblem, CorpusProblem, ProjectLifecycleProblem)):
        return _problem(
            request,
            403,
            "RO-CORE-DOCUMENT-AUTHORITY-CHANGED",
            "The local project session is no longer current.",
            "Reopen the project and select the file again.",
        )
    raise error


async def _stage_stream(request: Request, runtime: DocumentRuntimePort) -> AttachmentCandidate:
    lengths = request.headers.getlist("content-length")
    if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
        raise _problem(
            request,
            422,
            "RO-CORE-DOCUMENT-INTAKE-INVALID",
            "The selected stream length is invalid.",
            "Select the file again.",
        )
    wire_length = int(lengths[0])
    if wire_length > _MAX_WIRE_BYTES:
        raise _problem(
            request, 413, "RO-CORE-DOCUMENT-OVERSIZE", "The selected file exceeds 128 MiB.", "Choose a smaller file."
        )
    if request.headers.get("content-type") != "application/octet-stream":
        raise _problem(
            request,
            422,
            "RO-CORE-DOCUMENT-INTAKE-INVALID",
            "The selected stream type is invalid.",
            "Select the file again.",
        )
    incoming = request.stream().__aiter__()
    pending = memoryview(b"")

    async def take(count: int) -> bytes:
        nonlocal pending
        result = bytearray()
        while len(result) < count:
            if not pending:
                try:
                    pending = memoryview(await anext(incoming))
                except StopAsyncIteration, ClientDisconnect:
                    raise _problem(
                        request,
                        422,
                        "RO-CORE-DOCUMENT-INTAKE-INVALID",
                        "The selected stream ended early.",
                        "Select the file again.",
                    ) from None
                if not pending:
                    continue
            size = min(count - len(result), len(pending))
            result.extend(pending[:size])
            pending = pending[size:]
        return bytes(result)

    prefix = await take(4)
    header_length = int.from_bytes(prefix, "big")
    if not 0 < header_length <= _HEADER_BYTES:
        raise _problem(
            request,
            422,
            "RO-CORE-DOCUMENT-INTAKE-INVALID",
            "The selected stream header is invalid.",
            "Select the file again.",
        )
    encoded = await take(header_length)
    try:
        raw = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("invalid JSON constant")),
        )
    except UnicodeError, ValueError:
        raise _problem(
            request,
            422,
            "RO-CORE-DOCUMENT-INTAKE-INVALID",
            "The selected stream header is invalid.",
            "Select the file again.",
        ) from None
    if not isinstance(raw, dict):
        raise _problem(
            request,
            422,
            "RO-CORE-DOCUMENT-INTAKE-INVALID",
            "The selected stream header is invalid.",
            "Select the file again.",
        )
    claimed_length = raw.get("byteLength")
    if type(claimed_length) is int and claimed_length > MAX_DOCUMENT_BYTES:
        raise _problem(
            request, 413, "RO-CORE-DOCUMENT-OVERSIZE", "The selected file exceeds 128 MiB.", "Choose a smaller file."
        )
    try:
        command = DocumentStageCommand.model_validate(raw)
    except ValidationError:
        raise _problem(
            request,
            422,
            "RO-CORE-DOCUMENT-INTAKE-INVALID",
            "The selected stream header is invalid.",
            "Select the file again.",
        ) from None
    if wire_length != 4 + header_length + command.byte_length:
        raise _problem(
            request,
            422,
            "RO-CORE-DOCUMENT-INTAKE-INVALID",
            "The selected stream length changed.",
            "Select the file again.",
        )

    frames: queue.Queue[bytes | None] = queue.Queue(maxsize=_QUEUE_CHUNKS)
    cancelled = threading.Event()
    reader = _QueuedSource(frames, cancelled)
    work = asyncio.create_task(
        asyncio.to_thread(
            runtime.stage,
            command,
            cast(BinaryIO, reader),
            trace_id=request.state.trace_id,
            cancellation_requested=cancelled.is_set,
        )
    )

    async def push(frame: bytes | None) -> None:
        while True:
            if work.done():
                await work
                raise _problem(
                    request,
                    409,
                    "RO-CORE-DOCUMENT-CANCELLED",
                    "The attachment stopped during transfer.",
                    "Select the file again.",
                )
            try:
                frames.put_nowait(frame)
                return
            except queue.Full:
                await asyncio.sleep(0.005)

    async def chunks():
        if pending:
            yield pending
        async for part in incoming:
            if part:
                yield memoryview(part)

    received = 0
    try:
        async for part in chunks():
            if received + len(part) > command.byte_length:
                raise _problem(
                    request,
                    422,
                    "RO-CORE-DOCUMENT-INTAKE-INVALID",
                    "The selected stream has trailing bytes.",
                    "Select the file again.",
                )
            for offset in range(0, len(part), _WIRE_CHUNK_BYTES):
                await push(bytes(part[offset : offset + _WIRE_CHUNK_BYTES]))
            received += len(part)
        if received != command.byte_length:
            raise _problem(
                request,
                422,
                "RO-CORE-DOCUMENT-INTAKE-INVALID",
                "The selected stream ended early.",
                "Select the file again.",
            )
        await push(None)

        async def watch_disconnect() -> None:
            while not work.done():
                if await request.is_disconnected():
                    cancelled.set()
                    return
                await asyncio.sleep(0.05)

        watcher = asyncio.create_task(watch_disconnect())
        try:
            return await asyncio.wait_for(work, timeout=_STAGE_DEADLINE_SECONDS)
        finally:
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher
    except BaseException as error:
        cancelled.set()
        if not work.done():
            with suppress(queue.Full):
                frames.put_nowait(None)
        with suppress(TimeoutError, Exception):
            await asyncio.wait_for(asyncio.shield(work), timeout=10)
        if isinstance(error, ClientDisconnect):
            raise _problem(
                request,
                409,
                "RO-CORE-DOCUMENT-CANCELLED",
                "The selected stream disconnected.",
                "Select the file again.",
            ) from None
        if isinstance(error, TimeoutError):
            raise _problem(
                request,
                504,
                "RO-CORE-DOCUMENT-WORKER-UNAVAILABLE",
                "Document inspection timed out.",
                "Retry after checking the local worker.",
            ) from None
        raise


def register_document_attachment_routes(app: FastAPI, service: Callable[[Request], DocumentRuntimePort | None]) -> None:
    json_router = APIRouter(
        prefix="/native/document-attachments", route_class=BoundedImportRoute, include_in_schema=False
    )
    stream_router = APIRouter(prefix="/native/document-attachments", include_in_schema=False)

    def runtime(request: Request) -> DocumentRuntimePort:
        selected = service(request)
        if selected is None:
            raise _problem(
                request,
                503,
                "RO-CORE-DOCUMENT-UNAVAILABLE",
                "Local document attachment is unavailable.",
                "Open a writable project and retry.",
            )
        return selected

    def run[Result](request: Request, action: Callable[[DocumentRuntimePort], Result]) -> Result:
        try:
            return action(runtime(request))
        except (
            AttachmentProblem,
            DocumentInspectionError,
            ObjectStoreProblem,
            PreviewProblem,
            CorpusProblem,
            ProjectLifecycleProblem,
        ) as error:
            raise _mapped_error(request, error) from None

    @json_router.post("/context", response_model=DocumentContext)
    def context(request: Request, command: DocumentProject) -> DocumentContext:
        return run(
            request,
            lambda selected: DocumentContext(
                project_id=command.project_id, session_id=selected.context(command.root, command.project_id)
            ),
        )

    @stream_router.post("/stage", response_model=DocumentCandidateView)
    async def stage(request: Request, response: Response) -> DocumentCandidateView:
        try:
            candidate = await _stage_stream(request, runtime(request))
        except (
            AttachmentProblem,
            DocumentInspectionError,
            ObjectStoreProblem,
            PreviewProblem,
            CorpusProblem,
            ProjectLifecycleProblem,
        ) as error:
            raise _mapped_error(request, error) from None
        response.headers["Cache-Control"] = "no-store"
        return DocumentCandidateView.model_validate(asdict(candidate))

    @json_router.post("/candidate", response_model=DocumentCandidateView)
    def candidate(request: Request, command: DocumentAddress) -> DocumentCandidateView:
        result = run(
            request,
            lambda selected: selected.load_candidate(
                command.root,
                command.project_id,
                command.session_id,
                command.candidate_id,
                trace_id=request.state.trace_id,
            ),
        )
        return DocumentCandidateView.model_validate(asdict(result))

    @json_router.post("/cancel", status_code=204)
    def cancel(request: Request, command: DocumentAddress) -> Response:
        run(
            request,
            lambda selected: selected.cancel(
                command.root,
                command.project_id,
                command.session_id,
                command.candidate_id,
                trace_id=request.state.trace_id,
            ),
        )
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @json_router.post("/commit", response_model=DocumentAttachmentView)
    def commit(request: Request, command: DocumentCommit) -> DocumentAttachmentView:
        result = run(request, lambda selected: selected.commit(command, trace_id=request.state.trace_id))
        return DocumentAttachmentView.model_validate(asdict(result))

    app.include_router(json_router)
    app.include_router(stream_router)
