"""Native-only, bounded document parse/revision commands; Core owns all content."""

from collections.abc import Callable
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request
from pydantic import Field

from .anchors.contracts import AnchorSelection
from .document_attachment_api import BoundedDocumentJsonRoute, DocumentSession
from .document_revisions import DocumentRevisionAcceptance, DocumentRevisionProblem
from .ingestion.import_drafts import Identity
from .transport import CoreProblem, problem_detail


class DocumentParseCommand(DocumentSession):
    command_id: Identity
    attachment_id: Identity


class DocumentParseStatusCommand(DocumentSession):
    job_id: Identity


class DocumentParseResultCommand(DocumentSession):
    result_id: Identity


class DocumentAcceptCommand(DocumentSession):
    acceptance: DocumentRevisionAcceptance


class DocumentRevisionReadCommand(DocumentSession):
    revision_id: Identity


class DocumentRevisionHistoryCommand(DocumentSession):
    document_id: Identity


class SourceAnchorCreateCommand(DocumentSession):
    command_id: Identity
    selection: AnchorSelection


class SourceAnchorReadCommand(DocumentSession):
    anchor_id: Identity
    expected_revision_id: Identity


class DocumentReaderRevisionsCommand(DocumentSession):
    attachment_id: Identity


class SourceAnchorListCommand(DocumentSession):
    revision_id: Identity
    after_id: Identity | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 100


class DocumentReaderOutlineCommand(DocumentSession):
    revision_id: Identity
    after_node_id: Identity | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=50)] = 50


def register_document_revision_routes(app: FastAPI, runtime: Callable):
    router = APIRouter(
        prefix="/native/document-revisions", route_class=BoundedDocumentJsonRoute, include_in_schema=False
    )

    def run(request, action):
        service = runtime(request)
        try:
            if service is None:
                raise DocumentRevisionProblem("document-revision-unavailable")
            return action(service)
        except Exception:
            raise CoreProblem(
                problem_detail(
                    status=409,
                    code="RO-CORE-DOCUMENT-REVISION-DENIED",
                    title="Document revision needs attention",
                    detail="The current document, result or project authority could not be confirmed.",
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Review the current source and parse status before confirming another action.",
                )
            ) from None

    @router.post("/parse")
    def parse(request: Request, command: DocumentParseCommand):
        return run(request, lambda service: asdict(service.parse(command, trace_id=request.state.trace_id)))

    @router.post("/parse-status")
    def status(request: Request, command: DocumentParseStatusCommand):
        def current(service):
            job, receipt = service.status(command, trace_id=request.state.trace_id)
            return {
                "job": asdict(job),
                "receipt": None if receipt is None else receipt.model_dump(mode="json", by_alias=True),
            }

        return run(request, current)

    @router.post("/parse-result")
    def result(request: Request, command: DocumentParseResultCommand):
        def current(service):
            receipt, parsed = service.result(command, trace_id=request.state.trace_id)
            return {
                "receipt": receipt.model_dump(mode="json", by_alias=True),
                "result": parsed.model_dump(mode="json", by_alias=True),
            }

        return run(request, current)

    @router.post("/accept")
    def accept(request: Request, command: DocumentAcceptCommand):
        return run(
            request,
            lambda service: service.accept(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/read")
    def read(request: Request, command: DocumentRevisionReadCommand):
        return run(
            request,
            lambda service: service.read(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/history")
    def history(request: Request, command: DocumentRevisionHistoryCommand):
        return run(request, lambda service: {"revisionIds": service.history(command, trace_id=request.state.trace_id)})

    @router.post("/anchor-create")
    def anchor_create(request: Request, command: SourceAnchorCreateCommand):
        return run(
            request,
            lambda service: service.anchor_create(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/anchor-read")
    def anchor_read(request: Request, command: SourceAnchorReadCommand):
        return run(
            request,
            lambda service: service.anchor_read(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/anchor-list")
    def anchor_list(request: Request, command: SourceAnchorListCommand):
        return run(
            request, lambda service: {"anchorIds": service.anchor_list(command, trace_id=request.state.trace_id)}
        )

    @router.post("/reader-outline")
    def reader_outline(request: Request, command: DocumentReaderOutlineCommand):
        return run(
            request,
            lambda service: service.reader_outline(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/reader-revisions")
    def reader_revisions(request: Request, command: DocumentReaderRevisionsCommand):
        return run(
            request,
            lambda service: service.reader_revisions(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    app.include_router(router)
