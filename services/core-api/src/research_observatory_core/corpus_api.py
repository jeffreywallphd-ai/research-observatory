"""Authenticated, bounded Core entry for corpus membership and source rights."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute
from pydantic import Field, field_validator

from .corpus.membership import CorpusItemRevision, CorpusProblem
from .corpus_report_model import CorpusReportDrillPage, CorpusReportFilter, CorpusReportSnapshot
from .corpus_service import CorpusService
from .ingestion.import_drafts import DraftValue, Identity
from .models import ProblemDetail
from .ports.rights import RightsOutputRecheckState, RightsPermissionDraft, RightsProblem, RightsRecheckScope
from .reconciliation.contracts import SourceAddress
from .rights_policy import RightsDecision, RightsPolicyRevision, RightsSubject, RightsUse
from .transport import CoreProblem, problem_detail

_CORPUS_REQUEST_BYTES = 32_768
# A policy may contain up to 256 bounded assertions. This ceiling applies only
# to publication; inspection and evaluation retain the smaller command limit.
_RIGHTS_PUBLICATION_REQUEST_BYTES = 262_144


class CorpusCreateRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    command_id: Identity
    work_id: Identity
    work_revision_id: Identity
    source: SourceAddress


class CorpusReadRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    item_id: Identity


class CorpusReportCreateRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    command_id: Identity


class CorpusReportReadRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    snapshot_id: Identity


class CorpusReportDrillRequest(CorpusReportReadRequest):
    filter: CorpusReportFilter = Field(default_factory=lambda: CorpusReportFilter(kind="all"))
    cursor: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 50


class RightsPublishRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    command_id: Identity
    subject: RightsSubject
    permissions: list[RightsPermissionDraft] = Field(max_length=256)
    expected_predecessor_revision_id: Identity | None
    confirmed: bool

    @field_validator("permissions", mode="before")
    @classmethod
    def decode_evidence_arrays(cls, value: object) -> object:
        # Strict domain values use tuples; JSON has only arrays. Decode that one
        # transport shape before the domain draft enforces its typed bounds.
        if not isinstance(value, list):
            return value
        decoded = []
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("evidenceRevisionIds"), list):
                decoded.append({**item, "evidenceRevisionIds": tuple(item["evidenceRevisionIds"])})
            else:
                decoded.append(item)
        return decoded


class RightsCurrentRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    subject: RightsSubject


class RightsEvaluateRequest(RightsCurrentRequest):
    use: RightsUse


class RightsAdvanceRequest(RightsCurrentRequest):
    batch_size: Annotated[int, Field(strict=True, ge=1, le=1_000)] = 1_000


class RightsOutputRechecksRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    output_revision_id: Identity


def _problem(request: Request, error: CorpusProblem | RightsProblem | None) -> CoreProblem:
    code = error.code if error is not None else "corpus-runtime-unavailable"
    invalid = code in {
        "corpus-command-invalid",
        "corpus-trace-invalid",
        "corpus-evidence-invalid",
        "corpus-reason-invalid",
        "rights-command-invalid",
        "rights-policy-invalid",
        "rights-request-invalid",
    }
    unavailable = error is None or code in {"corpus-actor-unavailable", "corpus-report-unavailable"}
    integrity = "integrity" in code or code in {"corpus-storage-invalid", "rights-storage-invalid"}
    not_found = code in {"corpus-item-not-found", "corpus-report-not-found"}
    conflict = code.endswith("-conflict") or code in {"rights-predecessor-stale", "rights-impact-limit"}
    denied = any(part in code for part in ("authority", "source", "rights", "query")) or code in {
        "corpus-intent-unavailable",
        "corpus-policy-unavailable",
        "corpus-protocol-unavailable",
    }
    status = (
        503
        if unavailable
        else 500
        if integrity
        else 404
        if not_found
        else 422
        if invalid
        else 409
        if conflict
        else 403
        if denied
        else 409
    )
    public_code = {
        503: "RO-CORE-CORPUS-UNAVAILABLE",
        500: "RO-CORE-CORPUS-INTEGRITY-FAILED",
        404: "RO-CORE-CORPUS-NOT-FOUND",
        422: "RO-CORE-CORPUS-INVALID",
        403: "RO-CORE-CORPUS-DENIED",
        409: "RO-CORE-CORPUS-CONFLICT",
    }[status]
    if code == "corpus-report-limit":
        public_code = "RO-CORE-CORPUS-REPORT-LIMIT"
    return CoreProblem(
        problem_detail(
            status=status,
            code=public_code,
            title="Corpus action is unavailable",
            detail="The requested corpus action could not be completed under current project and source authority.",
            trace_id=request.state.trace_id,
            retryable=False,
            remediation="Inspect current project, Intent, source rights and item revision before retrying.",
        )
    )


class BoundedCorpusRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            body = bytearray()
            limit = (
                _RIGHTS_PUBLICATION_REQUEST_BYTES
                if request.url.path == "/projects/corpus/rights/publish"
                else _CORPUS_REQUEST_BYTES
            )
            async for chunk in request.stream():
                if len(body) + len(chunk) > limit:
                    raise CoreProblem(
                        problem_detail(
                            status=413,
                            code="RO-CORE-CORPUS-REQUEST-LIMIT",
                            title="Corpus request is too large",
                            detail="The corpus request exceeds the local Core limit.",
                            trace_id=request.state.trace_id,
                            retryable=False,
                            remediation="Submit a bounded corpus command.",
                        )
                    )
                body.extend(chunk)
            request._body = bytes(body)
            response = await handler(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        return bounded


def register_corpus_routes(app: FastAPI, service: Callable[[Request], CorpusService | None]) -> None:
    router = APIRouter(
        prefix="/projects/corpus",
        tags=["corpus"],
        route_class=BoundedCorpusRoute,
        responses={code: {"model": ProblemDetail} for code in (403, 404, 409, 413, 422, 500, 503)},
    )

    def run(request: Request, action):
        runtime = service(request)
        if runtime is None:
            raise _problem(request, None)
        try:
            return action(runtime)
        except (CorpusProblem, RightsProblem) as error:
            raise _problem(request, error) from None

    @router.post("/create", operation_id="createCorpusItem", response_model=CorpusItemRevision)
    def create(request: Request, command: CorpusCreateRequest) -> CorpusItemRevision:
        return run(
            request,
            lambda runtime: runtime.create(
                command.root,
                command_id=command.command_id,
                work_id=command.work_id,
                work_revision_id=command.work_revision_id,
                source=command.source,
                trace_id=request.state.trace_id,
            ),
        )

    @router.post("/inspect", operation_id="inspectCorpusItem", response_model=CorpusItemRevision)
    def inspect(request: Request, command: CorpusReadRequest) -> CorpusItemRevision:
        return run(
            request, lambda runtime: runtime.inspect(command.root, command.item_id, trace_id=request.state.trace_id)
        )

    @router.post("/reports/create", operation_id="createCorpusReport", response_model=CorpusReportSnapshot)
    def create_report(request: Request, command: CorpusReportCreateRequest) -> CorpusReportSnapshot:
        return run(
            request,
            lambda runtime: runtime.create_report(
                command.root, command_id=command.command_id, trace_id=request.state.trace_id
            ),
        )

    @router.post("/reports/inspect", operation_id="inspectCorpusReport", response_model=CorpusReportSnapshot)
    def inspect_report(request: Request, command: CorpusReportReadRequest) -> CorpusReportSnapshot:
        return run(
            request,
            lambda runtime: runtime.inspect_report(command.root, command.snapshot_id, trace_id=request.state.trace_id),
        )

    @router.post("/reports/drill", operation_id="drillCorpusReport", response_model=CorpusReportDrillPage)
    def drill_report(request: Request, command: CorpusReportDrillRequest) -> CorpusReportDrillPage:
        return run(
            request,
            lambda runtime: runtime.drill_report(
                command.root,
                command.snapshot_id,
                filter=command.filter,
                cursor=command.cursor,
                limit=command.limit,
                trace_id=request.state.trace_id,
            ),
        )

    @router.post("/rights/publish", operation_id="publishCorpusRightsPolicy", response_model=RightsPolicyRevision)
    def publish_rights(request: Request, command: RightsPublishRequest) -> RightsPolicyRevision:
        return run(
            request,
            lambda runtime: runtime.publish_rights(
                command.root,
                command_id=command.command_id,
                subject=command.subject,
                permissions=tuple(command.permissions),
                expected_predecessor_revision_id=command.expected_predecessor_revision_id,
                confirmed=command.confirmed,
                trace_id=request.state.trace_id,
            ),
        )

    @router.post("/rights/current", operation_id="getCorpusRightsPolicy", response_model=RightsPolicyRevision | None)
    def current_rights(request: Request, command: RightsCurrentRequest) -> RightsPolicyRevision | None:
        return run(
            request,
            lambda runtime: runtime.current_rights(command.root, command.subject, trace_id=request.state.trace_id),
        )

    @router.post(
        "/rights/recheck-scope", operation_id="getCorpusRightsRecheckScope", response_model=RightsRecheckScope | None
    )
    def rights_recheck_scope(request: Request, command: RightsCurrentRequest) -> RightsRecheckScope | None:
        return run(
            request,
            lambda runtime: runtime.rights_recheck_scope(
                command.root, command.subject, trace_id=request.state.trace_id
            ),
        )

    @router.post(
        "/rights/output-rechecks",
        operation_id="getCorpusRightsOutputRechecks",
        response_model=RightsOutputRecheckState,
    )
    def output_rights_rechecks(request: Request, command: RightsOutputRechecksRequest) -> RightsOutputRecheckState:
        return run(
            request,
            lambda runtime: runtime.output_rights_rechecks(
                command.root, command.output_revision_id, trace_id=request.state.trace_id
            ),
        )

    @router.post(
        "/rights/advance-rechecks", operation_id="advanceCorpusRightsRechecks", response_model=RightsRecheckScope | None
    )
    def advance_rights_rechecks(request: Request, command: RightsAdvanceRequest) -> RightsRecheckScope | None:
        return run(
            request,
            lambda runtime: runtime.advance_rights_rechecks(
                command.root, command.subject, batch_size=command.batch_size, trace_id=request.state.trace_id
            ),
        )

    @router.post("/rights/evaluate", operation_id="evaluateCorpusRights", response_model=RightsDecision)
    def evaluate_rights(request: Request, command: RightsEvaluateRequest) -> RightsDecision:
        return run(
            request,
            lambda runtime: runtime.evaluate_rights(
                command.root, command.subject, command.use, trace_id=request.state.trace_id
            ),
        )

    app.include_router(router)
