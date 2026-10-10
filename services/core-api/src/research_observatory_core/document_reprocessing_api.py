"""Bounded Native reprocessing commands; no renderer principal or parser choice."""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import Field

from .document_attachment_api import BoundedDocumentJsonRoute, DocumentSession
from .document_reprocessing import (
    ReprocessingAcceptance,
    ReprocessingCancel,
    ReprocessingContinue,
    ReprocessingCreate,
    ReprocessingReconcile,
)
from .parsing.contracts import Digest, Identity
from .transport import CoreProblem, problem_detail


class _ReprocessingRoute(BoundedDocumentJsonRoute):
    command_bytes = 65_536


class ReprocessingQueueCommand(DocumentSession):
    after_batch_id: Identity | None = None


class ReprocessingCreateCommand(DocumentSession):
    batch: ReprocessingCreate


class ReprocessingReadCommand(DocumentSession):
    batch_revision_id: Identity


class ReprocessingCompareCommand(ReprocessingReadCommand):
    item_id: Identity
    offset: Annotated[int, Field(strict=True, ge=0, le=100_000)] = 0


class ReprocessingReconcileCommand(DocumentSession):
    reconciliation: ReprocessingReconcile


class ReprocessingAcceptCommand(DocumentSession):
    acceptance: ReprocessingAcceptance


class ReprocessingContinueCommand(DocumentSession):
    continuation: ReprocessingContinue


class ReprocessingCancelCommand(DocumentSession):
    cancellation: ReprocessingCancel


class ReprocessingImpactCommand(ReprocessingReadCommand):
    item_id: Identity


class ReprocessingResumeCommand(ReprocessingImpactCommand):
    expected_checkpoint_sha256: Digest


def register_document_reprocessing_routes(app, runtime):
    router = APIRouter(prefix="/native/document-reprocessing", route_class=_ReprocessingRoute, include_in_schema=False)

    def run(request, action):
        try:
            service = runtime(request)
            if service is None:
                raise ValueError("document-reprocessing-unavailable")
            return action(service)
        except Exception:
            raise CoreProblem(
                problem_detail(
                    status=409,
                    code="RO-CORE-DOCUMENT-REPROCESSING-ATTENTION",
                    title="Document reprocessing needs attention",
                    detail="Current source, job, comparison, accepted revision or authority could not be confirmed.",
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Reload the current comparison and reconcile before confirming another action.",
                )
            ) from None

    @router.post("/queue")
    def queue(request: Request, command: ReprocessingQueueCommand):
        return run(request, lambda s: s.reprocessing_queue(command, trace_id=request.state.trace_id))

    @router.post("/create")
    def create(request: Request, command: ReprocessingCreateCommand):
        return run(request, lambda s: s.reprocessing_create(command, trace_id=request.state.trace_id))

    @router.post("/read")
    def read(request: Request, command: ReprocessingReadCommand):
        return run(request, lambda s: s.reprocessing_read(command, trace_id=request.state.trace_id))

    @router.post("/compare")
    def compare(request: Request, command: ReprocessingCompareCommand):
        return run(request, lambda s: s.reprocessing_compare(command, trace_id=request.state.trace_id))

    @router.post("/reconcile")
    def reconcile(request: Request, command: ReprocessingReconcileCommand):
        return run(request, lambda s: s.reprocessing_reconcile(command, trace_id=request.state.trace_id))

    @router.post("/accept")
    def accept(request: Request, command: ReprocessingAcceptCommand):
        return run(request, lambda s: s.reprocessing_accept(command, trace_id=request.state.trace_id))

    @router.post("/continue")
    def continue_item(request: Request, command: ReprocessingContinueCommand):
        return run(request, lambda s: s.reprocessing_continue(command, trace_id=request.state.trace_id))

    @router.post("/cancel")
    def cancel(request: Request, command: ReprocessingCancelCommand):
        return run(request, lambda s: s.reprocessing_cancel(command, trace_id=request.state.trace_id))

    @router.post("/read-impact")
    def read_impact(request: Request, command: ReprocessingImpactCommand):
        return run(request, lambda s: s.reprocessing_read_impact(command, trace_id=request.state.trace_id))

    @router.post("/resume-impact")
    def resume(request: Request, command: ReprocessingResumeCommand):
        return run(request, lambda s: s.reprocessing_resume_impact(command, trace_id=request.state.trace_id))

    app.include_router(router)
