"""Bounded public search values; canonical source inventories remain protected."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..anchors.contracts import AnchorSelection
from ..parsing.contracts import CodepointRange, Count, Digest, Identity, ProjectIdentity, SourceIdentity
from ..ports.workflow_executor import WorkflowJobState
from .contracts import MAX_QUERY_LENGTH
from .ranking import FIELD_WEIGHTS, RANKING_VERSION
from .run_values import Instant, SearchFilters, SearchValue

type LexicalScore = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
type PreviewText = Annotated[str, Field(strict=True, max_length=384)]
type QueryText = Annotated[str, Field(strict=True, max_length=MAX_QUERY_LENGTH * 4)]
type CursorText = Annotated[str, Field(strict=True, min_length=1, max_length=4096, pattern=r"^[A-Za-z0-9_-]+$")]
type SearchField = Literal["title", "abstract", "full-text", "authors", "venue", "identifiers", "tags", "decisions"]


class SearchSnippet(SearchValue):
    field: SearchField
    start: Count
    end: Count
    text: PreviewText = Field(repr=False)
    highlights: Annotated[tuple[CodepointRange, ...], Field(max_length=32)]
    truncated: bool

    @model_validator(mode="after")
    def exact_offsets(self):
        if (
            self.end - self.start != len(self.text)
            or any(not 0 <= span.start < span.end <= len(self.text) for span in self.highlights)
            or any(left.end > right.start for left, right in zip(self.highlights, self.highlights[1:], strict=False))
        ):
            raise ValueError("search-snippet-range-invalid")
        return self


class SearchDocumentTarget(SearchValue):
    revision_id: Identity
    source: SourceIdentity
    selection: AnchorSelection | None
    location_state: Literal["contained-text-selection", "unanchored-preview"]


class SearchHit(SearchValue):
    item_id: Identity
    work_id: Identity
    work_revision_id: Identity
    position: Annotated[int, Field(strict=True, ge=1)]
    score: LexicalScore
    title: Annotated[str, Field(strict=True, max_length=512)] = Field(repr=False)
    title_truncated: bool
    year: Annotated[int, Field(strict=True, ge=1, le=9999)] | None
    snippet: SearchSnippet | None
    source: SearchDocumentTarget | None


class SearchExecution(SearchValue):
    project_id: ProjectIdentity
    search_run_id: Identity
    revision_id: Identity
    job_id: Identity
    generation_id: Identity
    source_watermark: Count
    input_sha256: Digest
    result_sha256: Digest
    result_count: Count
    validated_at: Instant
    expires_at: Instant | None
    original_query: QueryText = Field(repr=False)
    normalized_query: QueryText = Field(repr=False)
    filters: SearchFilters
    ranking_version: Literal["ro-lexical-best-row-per-leaf-bm25-1"] = RANKING_VERSION
    field_weights: Annotated[tuple[float, ...], Field(min_length=8, max_length=8)]
    score_meaning: Literal["weighted-bm25-relevance"] = "weighted-bm25-relevance"
    semantic_state: Literal["unqualified"] = "unqualified"
    rerank_state: Literal["not-run"] = "not-run"

    @model_validator(mode="after")
    def fixed_method(self):
        if self.field_weights != FIELD_WEIGHTS:
            raise ValueError("search-rank-weights-invalid")
        return self


class SearchPage(SearchValue):
    execution: SearchExecution
    after_cursor: CursorText | None
    start_position: Count
    hits: Annotated[tuple[SearchHit, ...], Field(max_length=50)]
    next_cursor: CursorText | None

    @model_validator(mode="after")
    def complete_prefix(self):
        stop = self.start_position + len(self.hits)
        if (
            stop > self.execution.result_count
            or any(hit.position != self.start_position + index + 1 for index, hit in enumerate(self.hits))
            or (self.next_cursor is None) != (stop == self.execution.result_count)
            or (not self.hits and stop != self.execution.result_count)
            or (self.after_cursor is None and self.start_position != 0)
        ):
            raise ValueError("search-page-prefix-invalid")
        return self


class SearchJob(SearchValue):
    project_id: ProjectIdentity
    command_id: Identity
    job_id: Identity
    workflow_run_id: Identity
    state: WorkflowJobState
    attempt_count: Count
    cancellation_requested: bool
    diagnostic_code: Annotated[str, Field(strict=True, max_length=120)] | None


class SearchContribution(SearchValue):
    leaf_sha256: Digest
    entry_id: Digest
    field: SearchField | None
    match_kind: Literal["literal", "phrase"]
    score: LexicalScore


class SearchExplanation(SearchValue):
    execution: SearchExecution
    item_id: Identity
    score: LexicalScore
    components: Annotated[tuple[SearchContribution, ...], Field(max_length=256)]
    filter_effect: Literal["membership-only; statistical universe unchanged"] = (
        "membership-only; statistical universe unchanged"
    )


class SearchCursor(SearchValue):
    schema_version: Literal["1.0"] = "1.0"
    revision_id: Identity
    binding_sha256: Digest
    next_position: Annotated[int, Field(strict=True, ge=1)]
    last_item_id: Identity
    last_score: Annotated[str, Field(strict=True, min_length=1, max_length=32)]
