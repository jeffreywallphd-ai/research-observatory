"""Authenticated, bounded Core entry and inspection for corpus membership."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute
from pydantic import Field

from .corpus.membership import CorpusItemRevision, CorpusProblem
from .corpus_service import CorpusService
from .ingestion.import_drafts import DraftValue, Identity
from .models import ProblemDetail
from .reconciliation.contracts import SourceAddress
from .transport import CoreProblem, problem_detail


class CorpusCreateRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    command_id: Identity
    work_id: Identity
    work_revision_id: Identity
    source: SourceAddress


class CorpusReadRequest(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    item_id: Identity


def _problem(request: Request, error: CorpusProblem | None) -> CoreProblem:
    code = error.code if error is not None else "corpus-runtime-unavailable"
    invalid = code in {
        "corpus-command-invalid",
        "corpus-trace-invalid",
        "corpus-evidence-invalid",
        "corpus-reason-invalid",
    }
    unavailable = error is None or code == "corpus-actor-unavailable"
    integrity = "integrity" in code or code == "corpus-storage-invalid"
    not_found = code == "corpus-item-not-found"
    denied = any(part in code for part in ("authority", "source", "rights", "query")) or code in {
        "corpus-intent-unavailable",
        "corpus-policy-unavailable",
        "corpus-protocol-unavailable",
    }
    status = (
        503 if unavailable else 500 if integrity else 404 if not_found else 422 if invalid else 403 if denied else 409
    )
    public_code = {
        503: "RO-CORE-CORPUS-UNAVAILABLE",
        500: "RO-CORE-CORPUS-INTEGRITY-FAILED",
        404: "RO-CORE-CORPUS-NOT-FOUND",
        422: "RO-CORE-CORPUS-INVALID",
        403: "RO-CORE-CORPUS-DENIED",
        409: "RO-CORE-CORPUS-CONFLICT",
    }[status]
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
            async for chunk in request.stream():
                if len(body) + len(chunk) > 32768:
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
        except CorpusProblem as error:
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

    app.include_router(router)
