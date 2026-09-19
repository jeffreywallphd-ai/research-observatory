"""Authenticated, body-bounded import review routes; no filesystem or actor input."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute
from pydantic import Field

from .import_preview_service import ImportPreviewService
from .import_review import (
    RESPONSE_BYTES,
    DiagnosticPage,
    GroupEdit,
    ImportPreviewItem,
    ImportPreviewPage,
    ImportReview,
    MappingEdit,
    MutationRevision,
    PageLimit,
    RecordSelection,
    ReviewDetail,
    ReviewPage,
    ReviewPageRequest,
    ReviewSummary,
    Section,
    preview_item,
)
from .ingestion.import_drafts import DraftValue, Identity, Revision
from .models import ProblemDetail
from .ports.import_previews import PreviewProblem
from .projects import ProjectLifecycleProblem
from .transport import CoreProblem, problem_detail


class ImportProjectRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]


class ImportListRequest(ImportProjectRequest):
    after: Identity | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=25)] = 25


class ImportAddress(ImportProjectRequest):
    preview_id: Identity


class ImportPageRequest(ImportAddress, ReviewPageRequest):
    pass


class ImportDetailRequest(ImportAddress, RecordSelection):
    revision: Revision
    section: Section
    start: Annotated[int, Field(strict=True, ge=0, le=4096)] = 0
    limit: PageLimit = 25


class ImportMappingRequest(ImportAddress, MappingEdit):
    pass


class ImportGroupRequest(ImportAddress, GroupEdit):
    pass


class ImportUndoRequest(ImportAddress):
    expected_revision: MutationRevision


def _problem(request: Request, status: int, code: str, title: str) -> CoreProblem:
    return CoreProblem(
        problem_detail(
            status=status,
            code=code,
            title=title,
            detail="No canonical import was published. Draft state must be read again after an uncertain response.",
            trace_id=request.state.trace_id,
            retryable=False,
            remediation=(
                "Reload the preview in its open project. Review its current revision before submitting another edit."
            ),
        )
    )


class BoundedImportRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            # Inspect actual bytes, not a caller's Content-Length, before JSON decoding.
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > RESPONSE_BYTES:
                    raise _problem(request, 413, "RO-CORE-IMPORT-REQUEST-LIMIT", "Import request is too large")
                body.extend(chunk)
            request._body = bytes(body)
            response = await handler(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        return bounded


def register_import_routes(
    app: FastAPI,
    service: Callable[[Request], ImportPreviewService | None],
    project_problem: Callable[[Request, ProjectLifecycleProblem], CoreProblem],
) -> None:
    router = APIRouter(
        prefix="/projects/imports",
        tags=["imports"],
        route_class=BoundedImportRoute,
        responses={
            403: {"model": ProblemDetail},
            409: {"model": ProblemDetail},
            413: {"model": ProblemDetail},
            422: {"model": ProblemDetail},
            503: {"model": ProblemDetail},
        },
    )

    def run[Result](
        request: Request, command: ImportProjectRequest, action: Callable[[ImportReview, ImportPreviewService], Result]
    ) -> Result:
        runtime = service(request)
        if runtime is None:
            raise _problem(request, 503, "RO-CORE-IMPORT-UNAVAILABLE", "Import review is unavailable in this session")
        try:
            return runtime.review_action(command.root, lambda review: action(review, runtime))
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from error
        except PreviewProblem as error:
            reason = str(error)
            if reason in {"preview-rights-denied", "preview-record-rights-denied", "preview-rights-restore-denied"}:
                raise _problem(
                    request, 403, "RO-CORE-IMPORT-RIGHTS-DENIED", "Current rights do not permit this review"
                ) from None
            if reason in {"preview-draft-revision-conflict", "preview-mapping-revision-conflict"}:
                raise _problem(
                    request, 409, "RO-CORE-IMPORT-REVISION-CONFLICT", "The import draft has changed"
                ) from None
            raise _problem(
                request, 409, "RO-CORE-IMPORT-REVIEW-UNAVAILABLE", "This import review action is unavailable"
            ) from None
        except ValueError:
            # Domain errors never echo researcher corrections or source values.
            raise _problem(
                request, 422, "RO-CORE-IMPORT-DECISION-INVALID", "The import decision is not valid"
            ) from None

    @router.post("/list", response_model=ImportPreviewPage)
    def previews(request: Request, command: ImportListRequest) -> ImportPreviewPage:
        return run(
            request,
            command,
            lambda _review, runtime: runtime.previews_page(command.root, after=command.after, limit=command.limit),
        )

    @router.post("/status", response_model=ImportPreviewItem)
    def preview_status(request: Request, command: ImportAddress) -> ImportPreviewItem:
        return run(
            request,
            command,
            lambda _review, runtime: preview_item(*runtime.intake_status(command.root, command.preview_id)),
        )

    @router.post("/cancel", response_model=ImportPreviewItem)
    def cancel_preview(request: Request, command: ImportAddress) -> ImportPreviewItem:
        def action(_review: ImportReview, runtime: ImportPreviewService):
            # Inspect before mutating; no filename or state for a denied source.
            runtime.intake_status(command.root, command.preview_id)
            runtime.cancel(command.root, command.preview_id, trace_id=request.state.trace_id)
            return preview_item(*runtime.intake_status(command.root, command.preview_id))

        return run(request, command, action)

    @router.post("/begin-review", response_model=ReviewSummary)
    def begin_review(request: Request, command: ImportAddress) -> ReviewSummary:
        return run(
            request,
            command,
            lambda review, runtime: review.begin(command.preview_id, actor=runtime.actor(request.state.trace_id)),
        )

    @router.post("/review", response_model=ReviewSummary)
    def review_summary(request: Request, command: ImportAddress) -> ReviewSummary:
        return run(request, command, lambda review, _runtime: review.summary(command.preview_id))

    @router.post("/records", response_model=ReviewPage)
    def review_page(request: Request, command: ImportPageRequest) -> ReviewPage:
        page = ReviewPageRequest(revision=command.revision, after=command.after, limit=command.limit)
        return run(request, command, lambda review, _runtime: review.page(command.preview_id, page))

    @router.post("/detail", response_model=ReviewDetail)
    def review_detail(request: Request, command: ImportDetailRequest) -> ReviewDetail:
        return run(
            request,
            command,
            lambda review, _runtime: review.detail(
                command.preview_id,
                revision=command.revision,
                ordinal=command.ordinal,
                record_key=command.record_key,
                section=command.section,
                start=command.start,
                limit=command.limit,
            ),
        )

    @router.post("/mapping", response_model=ReviewSummary)
    def review_mapping(request: Request, command: ImportMappingRequest) -> ReviewSummary:
        edit = MappingEdit(expected_revision=command.expected_revision, mode=command.mode, columns=command.columns)
        return run(
            request,
            command,
            lambda review, runtime: review.map(command.preview_id, edit, actor=runtime.actor(request.state.trace_id)),
        )

    @router.post("/edit", response_model=ReviewSummary)
    def review_edit(request: Request, command: ImportGroupRequest) -> ReviewSummary:
        edit = GroupEdit(
            expected_revision=command.expected_revision,
            records=command.records,
            included=command.included,
            corrections=command.corrections,
        )
        return run(
            request,
            command,
            lambda review, runtime: review.edit(command.preview_id, edit, actor=runtime.actor(request.state.trace_id)),
        )

    @router.post("/undo", response_model=ReviewSummary)
    def review_undo(request: Request, command: ImportUndoRequest) -> ReviewSummary:
        return run(
            request,
            command,
            lambda review, runtime: review.undo(
                command.preview_id,
                expected_revision=command.expected_revision,
                actor=runtime.actor(request.state.trace_id),
            ),
        )

    @router.post("/report", response_model=DiagnosticPage)
    def review_report(request: Request, command: ImportPageRequest) -> DiagnosticPage:
        page = ReviewPageRequest(revision=command.revision, after=command.after, limit=command.limit)
        return run(request, command, lambda review, _runtime: review.report(command.preview_id, page))

    app.include_router(router)
