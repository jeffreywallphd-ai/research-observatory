"""Authenticated bounded reconciliation commands; callers provide addresses only."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute
from pydantic import Field

from .connectors.providers import ProviderProblem
from .ingestion.import_drafts import DraftValue, Identity
from .models import ProblemDetail
from .ports.import_previews import PreviewProblem
from .ports.workflow_executor import WorkflowQueueProblem
from .projects import ProjectLifecycleProblem
from .reconciliation.contracts import (
    ReconciliationInspection,
    ReconciliationProblem,
    ReconciliationResult,
    SourceAddress,
)
from .reconciliation_service import ReconciliationService
from .transport import CoreProblem, problem_detail


class ReconciliationRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    command_id: Identity
    source: SourceAddress


class ReconciliationReadRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    assertion_revision_id: Identity


class ReconciliationConnectorAddressRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    preview_id: Identity
    ordinal: Annotated[int, Field(strict=True, ge=0, le=999)]


def _problem(request: Request, status: int, code: str) -> CoreProblem:
    return CoreProblem(
        problem_detail(
            status=status,
            code=code,
            title="Scholarly reconciliation is unavailable",
            detail="The requested local action could not be completed under current project and source authority.",
            trace_id=request.state.trace_id,
            retryable=False,
            remediation="Inspect current project, Intent and source rights before retrying the same command.",
        )
    )


class BoundedReconciliationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 32768:
                    raise _problem(request, 413, "RO-CORE-RECONCILIATION-REQUEST-LIMIT")
                body.extend(chunk)
            request._body = bytes(body)
            response = await handler(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        return bounded


def register_reconciliation_routes(
    app: FastAPI,
    service: Callable[[Request], ReconciliationService | None],
    project_problem: Callable[[Request, ProjectLifecycleProblem], CoreProblem],
) -> None:
    router = APIRouter(
        prefix="/projects/reconciliation",
        tags=["reconciliation"],
        route_class=BoundedReconciliationRoute,
        responses={code: {"model": ProblemDetail} for code in (403, 409, 413, 422, 503)},
    )

    def run(request, action):
        runtime = service(request)
        if runtime is None:
            raise _problem(request, 503, "RO-CORE-RECONCILIATION-UNAVAILABLE")
        try:
            return action(runtime)
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from error
        except ReconciliationProblem as error:
            denied = any(item in error.code for item in ("rights", "authority", "intent", "policy"))
            raise _problem(
                request,
                403 if denied else 409,
                "RO-CORE-RECONCILIATION-DENIED" if denied else "RO-CORE-RECONCILIATION-CONFLICT",
            ) from None
        except PreviewProblem, ProviderProblem, WorkflowQueueProblem:
            raise _problem(request, 403, "RO-CORE-RECONCILIATION-SOURCE-DENIED") from None
        except ValueError, TypeError:
            raise _problem(request, 422, "RO-CORE-RECONCILIATION-INVALID") from None

    @router.post("/exact", operation_id="reconcileScholarlySource", response_model=ReconciliationResult)
    def exact(request: Request, command: ReconciliationRequest) -> ReconciliationResult:
        return run(
            request,
            lambda runtime: runtime.reconcile(
                command.root, command.source, command_id=command.command_id, trace_id=request.state.trace_id
            ),
        )

    @router.post("/inspect", operation_id="inspectScholarlyReconciliation", response_model=ReconciliationInspection)
    def inspect(request: Request, command: ReconciliationReadRequest) -> ReconciliationInspection:
        return run(
            request,
            lambda runtime: runtime.inspect(
                command.root, command.assertion_revision_id, trace_id=request.state.trace_id
            ),
        )

    @router.post("/connector-address", operation_id="resolveScholarlyConnectorAddress", response_model=SourceAddress)
    def connector_address(request: Request, command: ReconciliationConnectorAddressRequest) -> SourceAddress:
        return run(
            request,
            lambda runtime: runtime.connector_address(
                command.root, command.preview_id, command.ordinal, trace_id=request.state.trace_id
            ),
        )

    app.include_router(router)
