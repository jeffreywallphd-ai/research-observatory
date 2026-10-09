"""Fixed native-only viewer commands; no URLs, paths or caller-owned authority."""

import asyncio
import base64
import threading
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request
from pydantic import Field, model_validator

from .document_attachment_api import BoundedDocumentJsonRoute, DocumentSession
from .document_revisions import DocumentRevisionProblem
from .parsing.contracts import Identity
from .ports.document_viewer import ViewerSourceSelector
from .ports.object_store import MAX_VIEWER_RANGE_BYTES, MAX_VIEWER_SOURCE_BYTES, ObjectReadCancelled
from .transport import CoreProblem, problem_detail


class ViewerSourceCommand(DocumentSession):
    selector: ViewerSourceSelector


class ViewerRangeCommand(ViewerSourceCommand):
    request_id: Identity
    start: Annotated[int, Field(strict=True, ge=0, lt=MAX_VIEWER_SOURCE_BYTES)]
    end: Annotated[int, Field(strict=True, gt=0, le=MAX_VIEWER_SOURCE_BYTES)]

    @model_validator(mode="after")
    def range_limits(self):
        if not 0 < self.end - self.start <= MAX_VIEWER_RANGE_BYTES:
            raise ValueError("viewer-range-invalid")
        return self


class ViewerCancelCommand(DocumentSession):
    request_id: Identity


class ViewerTextCommand(ViewerSourceCommand):
    node_id: Identity
    offset: Annotated[int, Field(strict=True, ge=0, le=64 * 1024 * 1024)]


class ViewerOutlineCommand(ViewerSourceCommand):
    after_node_id: Identity | None = None


def register_document_viewer_routes(app: FastAPI, runtime: Callable):
    router = APIRouter(prefix="/native/document-viewer", route_class=BoundedDocumentJsonRoute, include_in_schema=False)

    def run(request, action):
        try:
            service = runtime(request)
            if service is None:
                raise RuntimeError("viewer-unavailable")
            return action(service)
        except Exception as failure:
            if isinstance(failure, DocumentRevisionProblem) and failure.code == "viewer-resource-limit":
                raise CoreProblem(
                    problem_detail(
                        status=413,
                        code="RO-CORE-DOCUMENT-VIEWER-RESOURCE-LIMIT",
                        title="Structured view exceeds the local limit",
                        detail="This structured view would exceed the bounded local viewer allocation.",
                        trace_id=request.state.trace_id,
                        retryable=False,
                        remediation="Continue inspecting the retained original or return to source review.",
                    )
                ) from None
            raise CoreProblem(
                problem_detail(
                    status=409,
                    code="RO-CORE-DOCUMENT-VIEWER-DENIED",
                    title="Source view is unavailable",
                    detail="The current source, project session or inspection authority could not be confirmed.",
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Return to the source and review its current availability and permissions.",
                )
            ) from None

    @router.post("/source")
    def source(request: Request, command: ViewerSourceCommand):
        return run(
            request,
            lambda service: service.describe(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/range")
    async def read_range(request: Request, command: ViewerRangeCommand):
        disconnected = threading.Event()

        # Waiting range requests use the separate async executor, preserving
        # synchronous metadata/rights and cancel-route capacity during scrolling.
        def read(service):
            metadata, value = service.read_range(
                command, trace_id=request.state.trace_id, cancellation_requested=disconnected.is_set
            )
            if disconnected.is_set():
                raise ObjectReadCancelled()
            return {
                "schemaVersion": "1.0",
                "requestId": command.request_id,
                "metadata": metadata.model_dump(mode="json", by_alias=True),
                "start": command.start,
                "end": command.end,
                "bytesBase64": base64.b64encode(value).decode("ascii"),
            }

        task = asyncio.create_task(asyncio.to_thread(run, request, read))
        # Observe eventual thread completion after ASGI cancellation without
        # killing an owned reader or claiming that its lease released early.
        task.add_done_callback(lambda completed: None if completed.cancelled() else completed.exception())
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=0.02)
                if await request.is_disconnected():
                    disconnected.set()
            return await task
        finally:
            disconnected.set()

    @router.post("/text")
    def text_chunk(request: Request, command: ViewerTextCommand):
        return run(
            request,
            lambda service: service.text_chunk(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/outline")
    def outline(request: Request, command: ViewerOutlineCommand):
        return run(
            request,
            lambda service: service.outline(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/cancel")
    def cancel(request: Request, command: ViewerCancelCommand):
        # No lifecycle/DB lock: the bounded wait observes actual owner closure.
        # Unknown registration or deadline expiry is explicitly not drained.
        return run(
            request,
            lambda service: {
                "schemaVersion": "1.0",
                "projectId": command.project_id,
                "sessionId": command.session_id,
                "requestId": command.request_id,
                "drained": service.cancel(command),
            },
        )

    app.include_router(router)
