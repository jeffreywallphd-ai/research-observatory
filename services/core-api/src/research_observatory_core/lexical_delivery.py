"""UI-independent current search pages over an immutable executed observation."""

import base64
import hashlib
import json
from dataclasses import asdict

from .anchors.contracts import AnchorSelection
from .domain_contracts import is_uuid_v7
from .lexical_index_repository import IndexServiceProblem
from .lexical_query_repository import CoreLexicalQueryService
from .lexical_run_repository import SqliteLexicalRunRepository, result_sha256
from .parsing.contracts import CodepointRange
from .search.contracts import TEXT_FIELDS, load_query_document
from .search.delivery_values import (
    SearchContribution,
    SearchCursor,
    SearchDocumentTarget,
    SearchExecution,
    SearchExplanation,
    SearchHit,
    SearchPage,
    SearchSnippet,
)
from .search.ranking import positive_leaves

PAGE_BYTES = 512 * 1024


def display_metadata(rows):
    """Compose only the already-lawful selected fields, distributed by source."""
    if not rows or len({(row.item_id, row.work_id, row.work_revision_id) for row in rows}) != 1:
        raise IndexServiceProblem("search displayed field binding is invalid")
    metadata = tuple(row for row in rows if row.document_revision_id is None)
    titles = {row.title for row in metadata if row.title}
    years = {row.year for row in metadata if row.year is not None}
    if len(titles) > 1 or len(years) > 1:
        raise IndexServiceProblem("search selected fields are inconsistent")
    return next(iter(titles), "Untitled record"), next(iter(years), None)


def _binding(record):
    return hashlib.sha256(
        json.dumps(
            (
                record.revision_id,
                record.payload_sha256,
                record.content.request_sha256,
                record.content.inputs.input_sha256,
                record.content.result_sha256,
            ),
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _encode(cursor):
    return base64.urlsafe_b64encode(cursor.model_dump_json(by_alias=True).encode()).decode().rstrip("=")


def _decode(raw):
    if not isinstance(raw, str) or not 1 <= len(raw) <= 4096:
        raise IndexServiceProblem("search cursor is invalid")
    try:
        cursor = SearchCursor.model_validate_json(
            base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
        )
        if _encode(cursor) != raw:
            raise ValueError("noncanonical cursor")
        return cursor
    except Exception:
        raise IndexServiceProblem("search cursor is invalid") from None


def _execution(record, query):
    run = record.content
    return SearchExecution(
        project_id=run.project_id,
        search_run_id=run.search_run_id,
        revision_id=record.revision_id,
        job_id=run.job_id,
        generation_id=run.inputs.generation_id,
        source_watermark=run.inputs.source_watermark,
        input_sha256=run.inputs.input_sha256,
        result_sha256=run.result_sha256,
        result_count=run.result_count,
        validated_at=run.inputs.validated_at,
        expires_at=run.inputs.earliest_rights_expiry,
        original_query=query.original_query,
        normalized_query=query.normalized_query,
        filters=run.request.filters,
        field_weights=run.request.field_weights,
    )


class CoreLexicalResultService:
    def __init__(self, repository: SqliteLexicalRunRepository):
        self.repository, self.index = repository, repository.index
        self.reader = CoreLexicalQueryService(self.index)

    def _read(self, job_id, consume, *, cancelled):
        record = self.repository.result(job_id)
        if record is None:
            raise IndexServiceProblem("search result is not ready")
        query = load_query_document(record.content.request.query_document)

        def current(snapshot, store):
            if (
                snapshot.input_sha256 != record.content.inputs.input_sha256
                or result_sha256(snapshot) != record.content.result_sha256
                or len(snapshot.ranked) != record.content.result_count
            ):
                raise IndexServiceProblem("search result inputs changed")
            return consume(record, query, snapshot, store)

        return self.reader.read(
            query, filters=record.content.request.filters.kernel(), consume=current, cancelled=cancelled
        )

    def _item(self, query, snapshot, store, item_id, *, cancelled):
        captured = self.index.sources.capture(item_id, cancelled=cancelled)
        if captured.watermark != snapshot.validation.watermark or not store.item_matches(item_id, captured.rows):
            raise IndexServiceProblem("search hit source changed")
        ranked = store.rank(query, tuple(row.entry_id for row in captured.rows), (item_id,))
        if len(ranked) != 1:
            raise IndexServiceProblem("search hit changed")
        return captured, ranked[0]

    def _preview(self, query, store, captured, ranked, *, cancelled):
        rows = {row.entry_id: row for row in captured.rows}
        leaves = dict(positive_leaves(query))
        for component in sorted(ranked.components, key=lambda value: (-value.score, value.leaf_sha256)):
            row = rows[component.entry_id]
            leaf = leaves[component.leaf_sha256]
            fields = (leaf.field,) if leaf.field is not None else TEXT_FIELDS
            for name in fields:
                if not getattr(row, name.replace("-", "_")):
                    continue
                snippet = store.snippet(query, component, field=name)
                if not snippet.highlights:
                    continue
                source = None
                if name == "full-text":
                    accepted = self.index.sources.documents.read_for_index(
                        row.document_revision_id, cancelled=cancelled
                    )
                    original = next(
                        value
                        for value in accepted.structure.text_projections
                        if value.projection_id == row.projection_id
                    )
                    start, end = snippet.highlights[0]
                    start += snippet.start + row.normalized_start
                    end += snippet.start + row.normalized_start
                    if (
                        original.normalized_text[start:end]
                        != snippet.text[snippet.highlights[0][0] : snippet.highlights[0][1]]
                    ):
                        raise IndexServiceProblem("search snippet source range changed")
                    nodes = sorted(
                        (
                            node
                            for node in accepted.structure.nodes
                            if node.text is not None
                            and node.text.projection_id == row.projection_id
                            and node.text.normalized_range.start <= start < end <= node.text.normalized_range.end
                        ),
                        key=lambda node: (
                            node.text.normalized_range.end - node.text.normalized_range.start,
                            node.order,
                            node.node_id,
                        ),
                    )
                    selection = (
                        AnchorSelection(
                            revision_id=accepted.revision_id,
                            node_id=nodes[0].node_id,
                            normalized_range=CodepointRange(start=start, end=end),
                        )
                        if nodes
                        else None
                    )
                    source = SearchDocumentTarget(
                        revision_id=accepted.revision_id,
                        source=accepted.result.binding.source,
                        selection=selection,
                        location_state="contained-text-selection" if selection else "unanchored-preview",
                    )
                value = asdict(snippet)
                value["highlights"] = tuple(CodepointRange(start=start, end=end) for start, end in snippet.highlights)
                return SearchSnippet(**value), source
        return None, None

    def page(self, job_id, *, after=None, limit=50, cancelled=lambda: False):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise IndexServiceProblem("search page limit is invalid")

        def page(record, query, snapshot, store):
            offset = 0
            if after is not None:
                cursor = _decode(after)
                offset = cursor.next_position
                if (
                    cursor.revision_id != record.revision_id
                    or cursor.binding_sha256 != _binding(record)
                    or offset > len(snapshot.ranked)
                ):
                    raise IndexServiceProblem("search cursor belongs to different inputs")
                previous = snapshot.ranked[offset - 1]
                if (previous.item_id, previous.score.hex()) != (cursor.last_item_id, cursor.last_score):
                    raise IndexServiceProblem("search cursor position is invalid")
            execution = _execution(record, query)
            hits = []
            result = None
            for position, hit in enumerate(snapshot.ranked[offset : offset + limit], start=offset + 1):
                self.index._check_cancel(cancelled)
                captured, ranked = self._item(query, snapshot, store, hit.item_id, cancelled=cancelled)
                if ranked.score != hit.score:
                    raise IndexServiceProblem("search hit score changed")
                metadata = next((row for row in captured.rows if row.document_revision_id is None), captured.rows[0])
                snippet, source = self._preview(query, store, captured, ranked, cancelled=cancelled)
                title, year = display_metadata(captured.rows)
                hits.append(
                    SearchHit(
                        item_id=hit.item_id,
                        work_id=metadata.work_id,
                        work_revision_id=metadata.work_revision_id,
                        position=position,
                        score=hit.score,
                        title=title[:512],
                        title_truncated=len(title) > 512,
                        year=year,
                        snippet=snippet,
                        source=source,
                    )
                )
                cursor = (
                    None
                    if position == len(snapshot.ranked)
                    else _encode(
                        SearchCursor(
                            revision_id=record.revision_id,
                            binding_sha256=_binding(record),
                            next_position=position,
                            last_item_id=hit.item_id,
                            last_score=hit.score.hex(),
                        )
                    )
                )
                candidate = SearchPage(
                    execution=execution, after_cursor=after, start_position=offset, hits=tuple(hits), next_cursor=cursor
                )
                if len(candidate.model_dump_json(by_alias=True).encode()) > PAGE_BYTES:
                    if len(hits) == 1:
                        raise IndexServiceProblem("search page byte budget exceeded")
                    break
                result = candidate
            return (
                result
                if result is not None
                else SearchPage(
                    execution=execution, after_cursor=after, start_position=offset, hits=(), next_cursor=None
                )
            )

        return self._read(job_id, page, cancelled=cancelled)

    def explain(self, job_id, item_id, *, cancelled=lambda: False):
        if not is_uuid_v7(item_id):
            raise IndexServiceProblem("search explanation address is invalid")

        def explain(record, query, snapshot, store):
            expected = next((value for value in snapshot.ranked if value.item_id == item_id), None)
            if expected is None:
                raise IndexServiceProblem("search explanation is unavailable")
            _captured, ranked = self._item(query, snapshot, store, item_id, cancelled=cancelled)
            if ranked.score != expected.score:
                raise IndexServiceProblem("search explanation score changed")
            leaves = dict(positive_leaves(query))
            return SearchExplanation(
                execution=_execution(record, query),
                item_id=item_id,
                score=ranked.score,
                components=tuple(
                    SearchContribution.model_validate(
                        {
                            "leafSha256": value.leaf_sha256,
                            "entryId": value.entry_id,
                            "field": leaves[value.leaf_sha256].field,
                            "matchKind": leaves[value.leaf_sha256].kind,
                            "score": value.score,
                        }
                    )
                    for value in ranked.components
                ),
            )

        return self._read(job_id, explain, cancelled=cancelled)
