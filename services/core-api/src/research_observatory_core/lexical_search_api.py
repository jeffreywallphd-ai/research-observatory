"""Fixed bounded search commands; Core owns execution and current authority."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request
from pydantic import Field

from .document_attachment_api import BoundedDocumentJsonRoute, DocumentProject
from .ingestion.import_drafts import DraftValue, Identity
from .parsing.contracts import Count
from .ports.lexical_search import LexicalSearchPort
from .search import parse_query
from .search.contracts import MAX_QUERY_LENGTH, QueryError
from .search.delivery_values import CursorText, SearchExplanation, SearchJob, SearchPage
from .search.errors import IndexServiceProblem
from .search.run_values import QueryWire, SearchFilters, SearchValue
from .transport import CoreProblem, problem_detail

type SearchQueryInput = Annotated[str, Field(strict=True, min_length=1, max_length=MAX_QUERY_LENGTH)]


class SearchValidationCommand(DraftValue):
    query: SearchQueryInput = Field(repr=False)


class SearchQueryDiagnostic(SearchValue):
    code: Annotated[str, Field(strict=True, min_length=1, max_length=120)]
    start: Count
    end: Count
    line: Annotated[int, Field(strict=True, ge=1)]
    column: Annotated[int, Field(strict=True, ge=1)]


class SearchQueryValidation(SearchValue):
    valid: bool
    original_query: Annotated[str, Field(strict=True, min_length=1, max_length=MAX_QUERY_LENGTH)] | None = Field(
        repr=False
    )
    normalized_query: Annotated[str, Field(strict=True, max_length=MAX_QUERY_LENGTH * 4)] | None = Field(repr=False)
    query_document: QueryWire | None = Field(repr=False)
    diagnostic: SearchQueryDiagnostic | None


class SearchRunCommand(DocumentProject):
    command_id: Identity
    query: SearchQueryInput = Field(repr=False)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SearchAddress(DocumentProject):
    job_id: Identity


class SearchPageCommand(SearchAddress):
    after: CursorText | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=50)] = 50


class SearchExplanationCommand(SearchAddress):
    item_id: Identity


class BoundedSearchRoute(BoundedDocumentJsonRoute):
    command_bytes = 256 * 1024


def register_search_routes(app: FastAPI, runtime: Callable[[Request], LexicalSearchPort | None]):
    router = APIRouter(prefix="/projects/search", route_class=BoundedSearchRoute, tags=["search"])

    def run(request, action):
        try:
            service = runtime(request)
            if service is None:
                raise IndexServiceProblem("search is unavailable")
            # Keep the strict typed value through FastAPI response validation.
            # JSON-mode dumping here turns tuples into lists before validation.
            return action(service)
        except Exception:
            raise CoreProblem(
                problem_detail(
                    status=409,
                    code="RO-CORE-SEARCH-DENIED",
                    title="Search needs attention",
                    detail="The current search inputs, result or project authority could not be confirmed.",
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Review the current project, rights and search status, then execute the query again.",
                )
            ) from None

    @router.post("/validate", operation_id="validateLexicalQuery", response_model=SearchQueryValidation)
    def validate(_request: Request, command: SearchValidationCommand):
        try:
            query = parse_query(command.query)
            return SearchQueryValidation(
                valid=True,
                original_query=query.original_query,
                normalized_query=query.normalized_query,
                query_document=query.to_json(),
                diagnostic=None,
            )
        except QueryError as error:
            return SearchQueryValidation(
                valid=False,
                original_query=None,
                normalized_query=None,
                query_document=None,
                diagnostic=SearchQueryDiagnostic.model_validate(error.diagnostic.to_dict()),
            )

    @router.post("/run", operation_id="executeLexicalSearch", response_model=SearchJob)
    def submit(request: Request, command: SearchRunCommand):
        return run(request, lambda service: service.submit(command, trace_id=request.state.trace_id))

    @router.post("/status", operation_id="inspectLexicalSearch", response_model=SearchJob)
    def status(request: Request, command: SearchAddress):
        return run(request, lambda service: service.status(command, trace_id=request.state.trace_id))

    @router.post("/page", operation_id="pageLexicalSearch", response_model=SearchPage)
    def page(request: Request, command: SearchPageCommand):
        return run(request, lambda service: service.page(command, trace_id=request.state.trace_id))

    @router.post("/explain", operation_id="explainLexicalSearch", response_model=SearchExplanation)
    def explain(request: Request, command: SearchExplanationCommand):
        return run(request, lambda service: service.explain(command, trace_id=request.state.trace_id))

    @router.post("/cancel", operation_id="cancelLexicalSearch", response_model=SearchJob)
    def cancel(request: Request, command: SearchAddress):
        return run(request, lambda service: service.cancel(command, trace_id=request.state.trace_id))

    app.include_router(router)
