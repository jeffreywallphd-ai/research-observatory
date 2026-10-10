"""Native-only correction commands; roots, sessions and principals stay Native-owned."""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import Field

from .document_attachment_api import BoundedDocumentJsonRoute, DocumentSession
from .document_corrections import CorrectionAcceptance, CorrectionDiscard, CorrectionSave
from .parsing.contracts import Identity
from .transport import CoreProblem, problem_detail


class _CorrectionRoute(BoundedDocumentJsonRoute):
    command_bytes = 65_536


class CorrectionQueueCommand(DocumentSession):
    after_job_id: Identity | None = None


class CorrectionPageCommand(DocumentSession):
    revision_id: Identity
    draft_revision_id: Identity | None = None
    offset: Annotated[int, Field(strict=True, ge=0, lt=10_000)] = 0


class CorrectionSaveCommand(DocumentSession):
    correction: CorrectionSave


class CorrectionAcceptCommand(DocumentSession):
    acceptance: CorrectionAcceptance


class CorrectionDiscardCommand(DocumentSession):
    discard: CorrectionDiscard


class CorrectionDraftCommand(DocumentSession):
    draft_revision_id: Identity


class CorrectionTargetsCommand(DocumentSession):
    after_work_id: Identity | None = None


def register_document_correction_routes(app, runtime):
    router = APIRouter(prefix="/native/document-corrections", route_class=_CorrectionRoute, include_in_schema=False)

    def run(request, action):
        try:
            service = runtime(request)
            if service is None:
                raise ValueError("document-corrections-unavailable")
            return action(service)
        except Exception:
            raise CoreProblem(
                problem_detail(
                    status=409,
                    code="RO-CORE-DOCUMENT-CORRECTION-ATTENTION",
                    title="Document correction needs attention",
                    detail="The current source, draft, accepted revision or authority could not be confirmed.",
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Reload the current revision and saved proposal before confirming another action.",
                )
            ) from None

    @router.post("/queue")
    def queue(request: Request, command: CorrectionQueueCommand):
        return run(request, lambda service: service.correction_queue(command, trace_id=request.state.trace_id))

    @router.post("/page")
    def page(request: Request, command: CorrectionPageCommand):
        return run(request, lambda service: service.correction_page(command, trace_id=request.state.trace_id))

    @router.post("/save")
    def save(request: Request, command: CorrectionSaveCommand):
        return run(request, lambda service: service.correction_save(command, trace_id=request.state.trace_id))

    @router.post("/accept")
    def accept(request: Request, command: CorrectionAcceptCommand):
        return run(request, lambda service: service.correction_accept(command, trace_id=request.state.trace_id))

    @router.post("/discard")
    def discard(request: Request, command: CorrectionDiscardCommand):
        return run(request, lambda service: service.correction_discard(command, trace_id=request.state.trace_id))

    @router.post("/draft")
    def draft(request: Request, command: CorrectionDraftCommand):
        return run(request, lambda service: service.correction_draft(command, trace_id=request.state.trace_id))

    @router.post("/impact")
    def impact(request: Request, command: CorrectionDraftCommand):
        return run(request, lambda service: service.correction_impact(command, trace_id=request.state.trace_id))

    @router.post("/targets")
    def targets(request: Request, command: CorrectionTargetsCommand):
        return run(request, lambda service: service.correction_targets(command, trace_id=request.state.trace_id))

    app.include_router(router)
