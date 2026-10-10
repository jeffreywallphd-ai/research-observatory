"""Native-only, bounded document parse/revision commands; Core owns all content."""

from collections.abc import Callable
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request
from pydantic import Field, model_validator

from .anchors.contracts import AnchorSelection
from .document_attachment_api import BoundedDocumentJsonRoute, DocumentSession
from .document_citations import CitationEnrichmentCommand
from .document_references import ReferenceEnrichmentCommand
from .document_revisions import DocumentRevisionAcceptance, DocumentRevisionProblem
from .document_table_figures import TableFigureCommand, TableFigureExcludeCommand
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


class CitationLinksCommand(DocumentSession):
    revision_id: Identity
    citation_id: Identity
    after_reference_id: Identity | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=2)] = 2


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


class DocumentReferenceEnrichCommand(DocumentSession):
    enrichment: ReferenceEnrichmentCommand


class DocumentReferenceReadCommand(DocumentSession):
    revision_id: Identity
    expected_collection_revision_id: Identity | None = None
    after_order: Annotated[int, Field(strict=True, ge=0, le=999)] | None = None


class DocumentCitationEnrichCommand(DocumentSession):
    enrichment: CitationEnrichmentCommand


class DocumentCitationReadCommand(DocumentSession):
    revision_id: Identity
    expected_collection_revision_id: Identity | None = None
    after_order: Annotated[int, Field(strict=True, ge=0, le=999)] | None = None


class DocumentTableFigureEnrichCommand(DocumentSession):
    enrichment: TableFigureCommand


class DocumentTableFigureExcludeCommand(DocumentSession):
    enrichment: TableFigureExcludeCommand


class DocumentTableFigureReadCommand(DocumentSession):
    revision_id: Identity
    expected_collection_revision_id: Identity | None = None
    after_order: Annotated[int, Field(strict=True, ge=0, le=999)] | None = None
    after_cell: Annotated[int, Field(strict=True, ge=0, le=9999)] | None = None
    cell_object_id: Identity | None = None

    @model_validator(mode="after")
    def cursor_binding(self):
        if (self.after_cell is None) != (self.cell_object_id is None) or (
            (self.after_order is not None or self.after_cell is not None)
            and self.expected_collection_revision_id is None
        ):
            raise ValueError("structure-reader-cursor-invalid")
        return self


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

    @router.post("/citations-enrich")
    def citations_enrich(request: Request, command: DocumentCitationEnrichCommand):
        return run(
            request,
            lambda service: service.citation_enrich(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/citations-read")
    def citations_read(request: Request, command: DocumentCitationReadCommand):
        def current(service):
            result = service.citations_read(command, trace_id=request.state.trace_id)
            return None if result is None else result.model_dump(mode="json", by_alias=True)

        return run(request, current)

    @router.post("/table-figures-enrich")
    def table_figures_enrich(request: Request, command: DocumentTableFigureEnrichCommand):
        return run(
            request,
            lambda service: service.table_figures_enrich(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/table-figures-exclude")
    def table_figures_exclude(request: Request, command: DocumentTableFigureExcludeCommand):
        return run(
            request,
            lambda service: service.table_figures_exclude(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/table-figures-read")
    def table_figures_read(request: Request, command: DocumentTableFigureReadCommand):
        def current(service):
            result = service.table_figures_read(command, trace_id=request.state.trace_id)
            return None if result is None else result.model_dump(mode="json", by_alias=True)

        return run(request, current)

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

    @router.post("/anchor-resolve")
    def anchor_resolve(request: Request, command: SourceAnchorReadCommand):
        return run(
            request,
            lambda service: service.anchor_resolve(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/citation-links")
    def citation_links(request: Request, command: CitationLinksCommand):
        return run(
            request,
            lambda service: service.citation_links(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
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

    @router.post("/references-enrich")
    def references_enrich(request: Request, command: DocumentReferenceEnrichCommand):
        return run(
            request,
            lambda service: service.reference_enrich(command, trace_id=request.state.trace_id).model_dump(
                mode="json", by_alias=True
            ),
        )

    @router.post("/references-read")
    def references_read(request: Request, command: DocumentReferenceReadCommand):
        def current(service):
            result = service.references_read(command, trace_id=request.state.trace_id)
            return None if result is None else result.model_dump(mode="json", by_alias=True)

        return run(request, current)

    app.include_router(router)
