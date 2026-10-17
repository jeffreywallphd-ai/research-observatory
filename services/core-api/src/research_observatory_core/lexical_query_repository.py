"""UI-independent ranked reads after complete current canonical authorization.

No request implicitly rebuilds an index. Preparation/execution ownership belongs
to the admitted durable workflow; this adapter owns only a guarded read scope.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from .lexical_catalog_repository import IndexGeneration, IndexValidation
from .lexical_index_repository import CoreLexicalIndexService, IndexServiceProblem
from .lexical_index_store import ProtectedLexicalStore
from .lexical_input_repository import rights_time_partition, source_authority_epoch
from .search.contracts import QueryDocument
from .search.ranking import LexicalFilters, RankedItem

_NO_FILTERS = LexicalFilters()


@dataclass(frozen=True, slots=True)
class LexicalReadSnapshot:
    generation: IndexGeneration
    validation: IndexValidation
    ranked: tuple[RankedItem, ...]
    source_revisions: tuple[str, ...]
    source_authority_epoch: int
    rights_time_partition: int
    validated_at: str = field(compare=False)

    @property
    def input_sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "generation": asdict(self.generation),
                    "validation": asdict(self.validation),
                    "sourceRevisions": self.source_revisions,
                    "sourceAuthorityEpoch": self.source_authority_epoch,
                    "rightsTimePartition": self.rights_time_partition,
                },
                sort_keys=True,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()


class CoreLexicalQueryService:
    def __init__(self, index: CoreLexicalIndexService) -> None:
        self.index = index

    def _fence(
        self,
        selected: IndexGeneration,
        validation: IndexValidation,
        cancelled: Callable[[], bool],
        *,
        source_epoch: int,
        time_partition: int,
        validated_at: str,
    ) -> None:
        return self.index._bounded(
            lambda: self._guarded_fence(
                selected,
                validation,
                cancelled,
                source_epoch=source_epoch,
                time_partition=time_partition,
                validated_at=validated_at,
            )
        )

    def _guarded_fence(
        self,
        selected: IndexGeneration,
        validation: IndexValidation,
        cancelled: Callable[[], bool],
        *,
        source_epoch: int,
        time_partition: int,
        validated_at: str,
    ) -> None:
        index = self.index
        index._check_cancel(cancelled)
        with index.sources.corpus._transaction(write=True) as (db, _aggregates):
            index._fence(db, validation)
            now = index.catalog.now()
            if (
                now < validated_at
                or source_authority_epoch(db, index.project) != source_epoch
                or rights_time_partition(db, index.project, now) != time_partition
            ):
                raise IndexServiceProblem("search source authority changed")
        if validation.expires_at is not None and index.catalog.now() >= validation.expires_at:
            raise IndexServiceProblem("search permission expired")
        if index.catalog.selected() != selected:
            raise IndexServiceProblem("search selection changed")
        index._current(selected)
        index._check_cancel(cancelled)

    def read(
        self,
        query: QueryDocument,
        *,
        filters: LexicalFilters = _NO_FILTERS,
        consume=None,
        cancelled: Callable[[], bool] = lambda: False,
    ):
        """The consumer materializes bounded private values inside this scope.

        It cannot retain the protected store as a bearer capability. Final
        source/actor/selection/expiry/lifecycle fences precede return, including
        after consumer work. Detailed explanations are generated only for the
        requested page, not retained as a corpus-size by query-size matrix.
        """

        def read():
            query.validate()
            if type(filters) is not LexicalFilters:
                raise IndexServiceProblem("search filters are invalid")
            filters.__post_init__()
            index = self.index
            selected = index.catalog.selected()
            if selected is None:
                raise IndexServiceProblem("index preparation required")
            index._current(selected)
            if selected.checkpoint != index.catalog.watermark():
                raise IndexServiceProblem("index synchronization required")

            def capture_authority():
                with index.sources.corpus._transaction(write=True) as (db, _aggregates):
                    validated_at = index.catalog.now()
                    return (
                        validated_at,
                        source_authority_epoch(db, index.project),
                        rights_time_partition(db, index.project, validated_at),
                    )

            validated_at, source_epoch, time_partition = index._bounded(capture_authority)

            def fence(validation):
                self._fence(
                    selected,
                    validation,
                    cancelled,
                    source_epoch=source_epoch,
                    time_partition=time_partition,
                    validated_at=validated_at,
                )

            with ProtectedLexicalStore(index.root, selected.scope, index.keys, cancelled=cancelled) as store:
                if (
                    not index.catalog.file_bound(selected.generation_id, store.file_identity)
                    or store.checkpoint != selected.checkpoint
                    or store.projection().manifest_sha256 != selected.projection_sha256
                ):
                    raise IndexServiceProblem("selected index binding changed")
                # BM25 observes table-wide statistics. Prove the entire mirror
                # equals the current lawful projection BEFORE invoking it,
                # including denied/nonmatching rows and whole-corpus expiry.
                validation = index._validate(store, None, repair_shadow=False, cancelled=cancelled)
                if validation.authority_sha256 != selected.authority_sha256:
                    raise IndexServiceProblem("search authority changed")
                fence(validation)
                ranked: list[RankedItem] = []
                source_revisions: set[str] = set()
                entries: list[str] = []
                items: list[str] = []

                def batch():
                    fence(validation)
                    ranked.extend(store.rank(query, tuple(entries), tuple(items), explain_limit=0))
                    entries.clear()
                    items.clear()

                for item_id in index._items():
                    index._check_cancel(cancelled)
                    captured = index.sources.capture(item_id, cancelled=cancelled)
                    if captured.watermark != validation.watermark or not store.item_matches(item_id, captured.rows):
                        raise IndexServiceProblem("search input changed")
                    source_revisions.add(captured.item_revision_id)
                    for row in captured.rows:
                        source_revisions.update((row.work_revision_id, row.source_revision_id))
                        if row.document_revision_id is not None:
                            source_revisions.add(row.document_revision_id)
                    if not captured.rows or not any(filters.includes(row.year) for row in captured.rows):
                        continue
                    if items and (len(items) == 256 or len(entries) + len(captured.rows) > 100_000):
                        batch()
                    items.append(item_id)
                    entries.extend(row.entry_id for row in captured.rows)
                if items:
                    batch()
                snapshot = LexicalReadSnapshot(
                    selected,
                    validation,
                    tuple(sorted(ranked, key=lambda hit: (-hit.score, hit.item_id))),
                    tuple(sorted(source_revisions)),
                    source_epoch,
                    time_partition,
                    validated_at,
                )
                fence(validation)
                result = snapshot if consume is None else consume(snapshot, store)
                fence(validation)
            fence(validation)
            return result

        return self.index._orchestrate(read)
