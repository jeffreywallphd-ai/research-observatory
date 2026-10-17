"""UI independent Core commands for protected lexical index lifecycle.

Native authority, current canonical sources and exact-purpose keys are injected
by Core. No command relies on renderer state, executable query SQL or AI state.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import asdict
from typing import Protocol

from .domain_contracts import new_uuid_v7
from .lexical_catalog_repository import (
    IndexCatalogProblem,
    IndexGeneration,
    IndexGenerationLease,
    IndexValidation,
    SqliteIndexCatalog,
    actor_context_sha256,
)
from .lexical_index_io import IndexFileGuard, _identity, _present, assert_retired_absent, purge_bootstrap
from .lexical_index_store import IndexRow, ProtectedLexicalStore, recover_retired_generation
from .lexical_input_repository import is_lexical_observation, lexical_watermark
from .lexical_source_repository import CanonicalIndexSources, ItemIndexProjection
from .ports.database_keys import DatabaseKeyProvider
from .ports.derivative_keys import DerivativeKeyProvider, DerivativeKeyScope, DerivativePurpose
from .search.contracts import QueryDocument
from .search.errors import IndexServiceProblem as IndexServiceProblem
from .storage import CanonicalConnection

_MAX_QUERY_BATCH_ITEMS = 256
_MAX_QUERY_BATCH_ENTRIES = 100_000


class IndexOrchestration(Protocol):
    def __call__[T](self, action: Callable[[], T]) -> T: ...


class IndexProjectionStale(IndexServiceProblem):
    """Current lawful rows require replacement, without weakening authority."""


class IndexCleanupPending(IndexServiceProblem):
    """The new selection is valid; a retired generation still needs cleanup."""

    def __init__(self, selected_generation_id: str) -> None:
        super().__init__("index selected; obsolete generation cleanup pending")
        self.selected_generation_id = selected_generation_id


def _index_step(_name: str) -> None:
    """Deterministic crash/failure seam; never mutates authority."""


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class CoreLexicalIndexService:
    def __init__(
        self,
        sources: CanonicalIndexSources,
        keys: DerivativeKeyProvider,
        canonical_keys: DatabaseKeyProvider,
        *,
        orchestration: IndexOrchestration | None = None,
    ) -> None:
        self.sources, self.keys, self.canonical_keys = sources, keys, canonical_keys
        self.database, self.project = sources.database, sources.project
        self.root = self.database.parent.parent
        self.catalog = SqliteIndexCatalog(
            self.database, self.project, keys, actor=sources.documents.actor, guard=sources.documents.guard
        )
        self._leases: dict[str, IndexGenerationLease] = {}
        self._orchestration = orchestration

    def _bounded(self, action):
        try:
            return self.sources.documents.guard(action)
        except IndexServiceProblem:
            raise
        except Exception:
            raise IndexServiceProblem("protected search index needs attention") from None

    def _orchestrate[T](self, action: Callable[[], T]) -> T:
        # Direct callers retain the original whole-command guard. An admitted
        # worker can orchestrate bounded guarded phases without holding the
        # project mutex over index construction, ranking or heartbeat joins.
        # Catalog/source operations and canonical publication keep _bounded.
        if self._orchestration is None:
            return self._bounded(action)
        try:
            return self._orchestration(action)
        except IndexServiceProblem:
            raise
        except Exception:
            raise IndexServiceProblem("protected search orchestration needs attention") from None

    def _scope(self, generation_id: str) -> DerivativeKeyScope:
        with self.canonical_keys.active_key(self.project, create=False) as key:
            version = key.version
        lifecycle = _sha(
            (
                str(self.root).casefold(),
                _identity(self.root, directory=True),
                _identity(self.database.parent, directory=True),
                _identity(self.database),
                version,
            )
        )
        return DerivativeKeyScope(self.project, generation_id, DerivativePurpose.LEXICAL, version, lifecycle)

    def _current(self, generation: IndexGeneration) -> None:
        if generation.scope != self._scope(generation.generation_id):
            raise IndexServiceProblem("index lifecycle changed; rebuild required")

    def begin_rebuild(self) -> IndexGenerationLease:
        def begin():
            lease = self.catalog.create(self._scope(new_uuid_v7()))
            self._leases[lease.generation_id] = lease
            return lease

        return self._bounded(begin)

    def _items(self) -> Iterator[str]:
        cursor = None
        while batch := self.sources.item_ids(after=cursor):
            yield from batch
            cursor = batch[-1]

    @staticmethod
    def _chunks(rows: tuple[IndexRow, ...]) -> Iterator[tuple[IndexRow, ...]]:
        batch: list[IndexRow] = []
        size = 0
        for row in rows:
            row_size = sum(len(value.encode("utf-8")) for value in asdict(row).values() if isinstance(value, str))
            if batch and (len(batch) == 256 or size + row_size > 4 * 1024 * 1024):
                yield tuple(batch)
                batch, size = [], 0
            batch.append(row)
            size += row_size
        if batch:
            yield tuple(batch)

    def _stage_item(
        self,
        store: ProtectedLexicalStore,
        captured: ItemIndexProjection,
        lease: IndexGenerationLease,
        *,
        cancelled: Callable[[], bool],
    ) -> None:
        if not self.catalog.initialized(lease.generation_id):
            raise IndexServiceProblem("index source admission requires initialized storage")
        self.catalog.renew(lease)
        while old := store.entry_ids(captured.item_id, limit=256):
            self.catalog.assert_owner(lease)
            store.stage((), old)
        for chunk in self._chunks(captured.rows):
            self.catalog.renew(lease)
            store.stage(chunk, ())

        def revalidate():
            with self.sources.corpus._transaction(write=True) as (db, _aggregates):
                self.sources.revalidate(db, captured, cancelled=cancelled)

        self._bounded(revalidate)
        self.catalog.assert_owner(lease)

    @staticmethod
    def _check_cancel(cancelled: Callable[[], bool]) -> None:
        if cancelled() is not False:
            raise IndexServiceProblem("index operation cancelled")

    def _fence(self, db, validation: IndexValidation) -> None:
        self.sources.documents._authority(db, self.sources.documents.actor())
        watermark = lexical_watermark(db, self.project)
        if (
            watermark != validation.watermark
            or actor_context_sha256(self.project, self.sources.documents.actor()) != validation.actor_sha256
        ):
            raise IndexServiceProblem("index source watermark changed")

    def _revalidator(
        self, validation: IndexValidation, *, cancelled: Callable[[], bool] = lambda: False
    ) -> Callable[[CanonicalConnection], None]:
        def current(db: CanonicalConnection) -> None:
            self._check_cancel(cancelled)
            self._fence(db, validation)
            self._check_cancel(cancelled)

        return current

    def _validate(
        self,
        store: ProtectedLexicalStore,
        lease: IndexGenerationLease | None,
        *,
        repair_shadow: bool,
        cancelled: Callable[[], bool],
    ) -> IndexValidation:
        watermark = self.catalog.watermark()
        authority = hashlib.sha256()
        expiry = None
        count = 0
        for item_id in self._items():
            self._check_cancel(cancelled)
            if lease is not None:
                self.catalog.renew(lease)
            captured = self.sources.capture(item_id, cancelled=cancelled)
            if captured.watermark != watermark:
                raise IndexServiceProblem("index source changed during validation")
            if not store.item_matches(item_id, captured.rows):
                if not repair_shadow or lease is None or store.sealed:
                    raise IndexProjectionStale("index projection requires rebuild")
                self._stage_item(store, captured, lease, cancelled=cancelled)
            count += len(captured.rows)
            authority.update(bytes.fromhex(captured.authority_sha256))
            if captured.expires_at is not None:
                expiry = captured.expires_at if expiry is None else min(expiry, captured.expires_at)
        if count != store.projection().entry_count:
            raise IndexServiceProblem("index projection contains unbound rows")
        validation = IndexValidation(
            watermark, authority.hexdigest(), actor_context_sha256(self.project, self.sources.documents.actor()), expiry
        )

        def validate_current():
            with self.sources.corpus._transaction(write=True) as (db, _aggregates):
                self._fence(db, validation)

        self._bounded(validate_current)
        return validation

    def run_build(
        self, lease: IndexGenerationLease, *, cancelled: Callable[[], bool] = lambda: False
    ) -> IndexGeneration:
        def build():
            snapshot = self.catalog.get(lease.generation_id)
            self._current(snapshot)
            if snapshot.stage != "Building":
                raise IndexServiceProblem("index build is not active")
            self.catalog.assert_owner(lease)
            previous = self.catalog.selected()
            path = self.root / "indexes" / ("lexical-" + snapshot.generation_id + ".sqlite3")
            try:
                self._check_cancel(cancelled)
                create = not path.exists()
                if not create and not self.catalog.initialized(snapshot.generation_id):
                    raise IndexServiceProblem("interrupted bootstrap requires a fresh rebuild")
                with ProtectedLexicalStore(
                    self.root,
                    snapshot.scope,
                    self.keys,
                    create=create,
                    cancelled=cancelled,
                    _bootstrap=lambda identities: self.catalog.bind_bootstrap(lease, identities),
                ) as store:
                    if create:
                        _index_step("empty-schema-initialized")
                        if store.sealed or store.checkpoint != 0 or store.projection().entry_count != 0:
                            raise IndexServiceProblem("bootstrap is not an empty protected index")
                        self.catalog.acknowledge_initialization(lease, store.file_identities)
                        _index_step("initialization-acknowledged")
                    self.catalog.bind_file(lease, store.file_identity)
                    if not store.sealed:
                        cursor = snapshot.cursor_item_id
                        while batch := self.sources.item_ids(after=cursor):
                            for item_id in batch:
                                self._check_cancel(cancelled)
                                captured = self.sources.capture(item_id, cancelled=cancelled)
                                self._stage_item(store, captured, lease, cancelled=cancelled)
                                _index_step("shadow-item-committed")
                                self.catalog.record_progress(lease, cursor_item_id=item_id)
                                cursor = item_id
                    validation = self._validate(store, lease, repair_shadow=True, cancelled=cancelled)
                    if not store.sealed:
                        store.finish_build(validation.watermark)
                    if store.checkpoint != validation.watermark:
                        raise IndexServiceProblem("sealed shadow requires a new rebuild")
                    store.integrity_check()
                    projection = store.projection()
                    _index_step("shadow-sealed")
                    self._check_cancel(cancelled)
                    self._current(snapshot)
                    self.catalog.publish_ready(
                        lease,
                        projection,
                        validation,
                        expected_selection_id=None if previous is None else previous.selection_id,
                        revalidate=self._revalidator(validation, cancelled=cancelled),
                        cancelled=cancelled,
                    )
                    _index_step("shadow-selected")
                selected = self.catalog.selected()
                if selected is None:
                    raise IndexServiceProblem("index selection is unavailable")
                try:
                    self.collect_obsolete()
                except IndexServiceProblem:
                    raise IndexCleanupPending(selected.generation_id) from None
                return selected
            except BaseException:
                try:
                    if self.catalog.get(lease.generation_id).stage == "Building":
                        self.catalog.cancel(lease)
                except Exception:
                    # Expired/replaced owners cannot rewrite the successor's
                    # history. The committed Building head is never selected.
                    pass
                raise

        return self._orchestrate(build)

    def rebuild(self, *, cancelled: Callable[[], bool] = lambda: False) -> IndexGeneration:
        return self.run_build(self.begin_rebuild(), cancelled=cancelled)

    def resume(self, generation_id: str, *, cancelled: Callable[[], bool] = lambda: False) -> IndexGeneration:
        lease = self.catalog.acquire(generation_id)
        previous = self._leases.get(generation_id)
        if previous is not None:
            previous.close()
        self._leases[generation_id] = lease
        return self.run_build(lease, cancelled=cancelled)

    def retire(self, generation_id: str) -> None:
        def mark():
            snapshot = self.catalog.get(generation_id)
            selected = self.catalog.selected()
            if selected is not None and selected.generation_id == generation_id:
                raise IndexServiceProblem("selected index cannot be retired")
            if snapshot.stage != "Retired":
                lease = self._leases.get(generation_id)
                if lease is not None:
                    try:
                        self.catalog.retire(lease)
                    except IndexCatalogProblem:
                        lease = None
                if lease is None:
                    lease = self.catalog.acquire(generation_id)
                    self._leases[generation_id] = lease
                    self.catalog.retire(lease)
            return snapshot

        def remove():
            snapshot = self._bounded(mark)
            # Reacquire current project authority before the generation/file
            # guards. An admitted worker releases the mutex between phases.
            self._retire_cleanup(snapshot)

        self._orchestrate(remove)

    def _retire_cleanup(self, snapshot: IndexGeneration) -> None:
        def cleanup():
            generation_id = snapshot.generation_id
            path = self.root / "indexes" / ("lexical-" + generation_id + ".sqlite3")
            initialized = self.catalog.authorize_retirement(snapshot)
            if not initialized:
                held_identities: dict[str, tuple[int, int]] | None = None

                def authorize_bootstrap(identities):
                    nonlocal held_identities
                    if self.catalog.authorize_retirement(snapshot, bootstrap_identities=identities) is not False:
                        raise IndexServiceProblem("bootstrap recovery mode changed")
                    held_identities = dict(identities)

                def revoke_bootstrap():
                    # All present fixed roles are now exclusively held for
                    # DELETE, and no source admission was ever acknowledged.
                    if (
                        held_identities is None
                        or self.catalog.authorize_retirement(snapshot, bootstrap_identities=held_identities)
                        is not False
                    ):
                        raise IndexServiceProblem("bootstrap recovery authority changed")
                    self.keys.revoke(snapshot.scope, expected_version=snapshot.derivative_key_version)

                purge_bootstrap(self.root, generation_id, authorize=authorize_bootstrap, revoke=revoke_bootstrap)

            elif _present(path):

                def eligible(identity):
                    if self.catalog.authorize_retirement(snapshot, identity=identity) is not True:
                        raise IndexServiceProblem("retired recovery mode changed")

                if any(_present(path.with_name(path.name + suffix)) for suffix in ("-wal", "-shm", "-journal")):
                    recover_retired_generation(
                        self.root,
                        snapshot.scope,
                        self.keys,
                        expected_version=snapshot.derivative_key_version,
                        authorize=eligible,
                    )
                guard = IndexFileGuard(self.root, generation_id, create=False, retirement=True)
                try:
                    identity = guard.file_identity
                    eligible(identity)

                    def revoke():
                        eligible(identity)
                        self.keys.revoke(snapshot.scope, expected_version=snapshot.derivative_key_version)
                        _index_step("retirement-key-revoked")

                    guard.purge_retired(revoke)
                finally:
                    guard.close(clean_sidecars=False)
            else:
                assert_retired_absent(self.root, generation_id)
                if self.catalog.authorize_retirement(snapshot) is not True:
                    raise IndexServiceProblem("retired recovery mode changed")
                self.keys.revoke(snapshot.scope, expected_version=snapshot.derivative_key_version)
                assert_retired_absent(self.root, generation_id)
            lease = self._leases.pop(generation_id, None)
            if lease is not None:
                lease.close()

        self._bounded(cleanup)

    def collect_obsolete(self) -> None:
        def collect():
            selected = self.catalog.selected()
            if selected is None:
                raise IndexServiceProblem("index has no safe replacement")
            cursor = None
            while True:

                def page(after=cursor):
                    with self.sources.corpus._transaction(write=False) as (db, _aggregates):
                        return tuple(
                            row[0]
                            for row in db.execute(
                                "SELECT generation_id FROM search_generations WHERE project_id=? AND (? IS NULL OR "
                                "generation_id>?) ORDER BY generation_id LIMIT 256",
                                (self.project, after, after),
                            )
                        )

                identities = self._bounded(page)
                if not identities:
                    break
                for identity in identities:
                    if identity != selected.generation_id:
                        self.retire(identity)
                cursor = identities[-1]

        self._orchestrate(collect)

    def _changed_items(self, after: int, through: int) -> tuple[str, ...]:
        """Map source revisions, including rights, to current corpus identities."""
        if type(after) is not int or type(through) is not int or not 0 <= after <= through:
            raise IndexServiceProblem("index change cursor is invalid")
        result: set[str] = set()
        cursor = after
        while cursor < through:
            previous = cursor
            cursor, items, fallback = self._bounded(lambda cursor=cursor: self._changed_items_batch(cursor, through))
            if fallback:
                # No canonical read transaction or phase guard is held while
                # the existing ordered item port enumerates bounded pages.
                return tuple(self._items())
            result.update(items)
            if cursor == previous:
                raise IndexServiceProblem("index change sequence is incomplete")
        return tuple(sorted(result))

    def _changed_items_batch(self, after: int, through: int) -> tuple[int, tuple[str, ...], bool]:
        result: set[str] = set()
        with self.sources.corpus._transaction(write=False) as (db, _aggregates):
            cursor = after
            rows = db.execute(
                "SELECT c.sequence,c.revision_id,c.event_type,o.revision_id,o.event_type,c.record_sha256,o.re"
                "cord_sha256 FROM search_changes c JOIN outbox_events o ON o.outbox_id=c.outbox_id AND "
                "o.project_id=c.project_id WHERE c.project_id=? AND c.sequence>? AND c.sequence<=? ORDER BY "
                "c.sequence LIMIT 256",
                (self.project, cursor, through),
            ).fetchall()
            if not rows:
                return cursor, (), False
            for sequence, revision, kind, original_revision, original_kind, digest, original_digest in rows:
                if (
                    revision != original_revision
                    or kind != original_kind
                    or digest != original_digest
                    or sequence != cursor + 1
                ):
                    raise IndexServiceProblem("index change sequence is invalid")
                cursor = sequence
                if is_lexical_observation(db, self.project, sequence):
                    continue
                if revision is None:
                    return cursor, (), True
                aggregate = db.execute(
                    "SELECT aggregate_kind,aggregate_id FROM aggregate_revisions WHERE project_id=? AND revision_id=?",
                    (self.project, revision),
                ).fetchone()
                if aggregate is None:
                    return cursor, (), True
                if aggregate[0] == "corpus-item":
                    result.add(aggregate[1])
                    continue
                work_ids = set()
                if aggregate[0] == "record":
                    work_ids.add(aggregate[1])
                elif aggregate[0] == "document":
                    work_ids.update(
                        row[0]
                        for row in db.execute(
                            "SELECT work_id FROM document_attachment_assertions WHERE project_id=? AND document_id=?",
                            (self.project, aggregate[1]),
                        )
                    )
                else:
                    assertion = db.execute(
                        "SELECT s.source_assertion_revision_id FROM rights_policy_revisions r JOIN "
                        "rights_policy_subjects s ON s.project_id=r.project_id AND "
                        "s.subject_sha256=r.subject_sha256 WHERE r.project_id=? AND r.revision_id=?",
                        (self.project, revision),
                    ).fetchone()
                    if assertion is None:
                        return cursor, (), True
                    work_ids.update(
                        row[0]
                        for row in db.execute(
                            "SELECT s.work_id FROM reconciliation_work_members m JOIN "
                            "reconciliation_work_states s ON s.project_id=m.project_id AND "
                            "s.revision_id=m.work_revision_id WHERE m.project_id=? AND "
                            "m.assertion_revision_id=?",
                            (self.project, assertion[0]),
                        )
                    )
                for work in work_ids:
                    result.update(
                        row[0]
                        for row in db.execute(
                            "SELECT DISTINCT item_id FROM corpus_item_states WHERE project_id=? AND work_id=?",
                            (self.project, work),
                        )
                    )
        return cursor, tuple(sorted(result)), False

    def synchronize(self, *, cancelled: Callable[[], bool] = lambda: False) -> IndexGeneration:
        def update():
            selected = self.catalog.selected()
            if selected is None:
                return self.rebuild(cancelled=cancelled)
            self._current(selected)
            target = self.catalog.watermark()
            if target == selected.checkpoint:
                with ProtectedLexicalStore(self.root, selected.scope, self.keys, cancelled=cancelled) as store:
                    if not self.catalog.file_bound(selected.generation_id, store.file_identity):
                        raise IndexServiceProblem("selected index file changed")
                    try:
                        self._validate(store, None, repair_shadow=False, cancelled=cancelled)
                    except IndexProjectionStale:
                        pass
                    else:
                        return selected
                return self.rebuild(cancelled=cancelled)

            def changed_rights():
                with self.sources.corpus._transaction(write=False) as (db, _aggregates):
                    return (
                        db.execute(
                            "SELECT 1 FROM search_changes c JOIN rights_policy_revisions r ON "
                            "r.project_id=c.project_id AND r.revision_id=c.revision_id WHERE c.project_id=? AND "
                            "c.sequence>? AND c.sequence<=? LIMIT 1",
                            (self.project, selected.checkpoint, target),
                        ).fetchone()
                        is not None
                    )

            rights_changed = self._bounded(changed_rights)
            if rights_changed:
                return self.rebuild(cancelled=cancelled)
            lease = self._leases.get(selected.generation_id)
            if lease is not None:
                try:
                    self.catalog.renew(lease)
                except IndexCatalogProblem:
                    # acquire() still fences a live successor. An expired
                    # cached token is never renewed or treated as ownership.
                    replacement = self.catalog.acquire(selected.generation_id)
                    lease.close()
                    lease = replacement
                    self._leases[selected.generation_id] = lease
            if lease is None:
                lease = self.catalog.acquire(selected.generation_id)
                self._leases[selected.generation_id] = lease
            self.catalog.renew(lease)
            affected = self._changed_items(selected.checkpoint, target)
            rows: list[IndexRow] = []
            removed: list[str] = []
            with ProtectedLexicalStore(self.root, selected.scope, self.keys, cancelled=cancelled) as store:
                if not self.catalog.file_bound(selected.generation_id, store.file_identity):
                    raise IndexServiceProblem("selected index file changed")
                if (
                    store.checkpoint != selected.checkpoint
                    or store.projection().manifest_sha256 != selected.projection_sha256
                ):
                    # A private commit has no cross-store atomicity with its
                    # canonical acknowledgement. Never reconstruct/replay an
                    # old batch from its already-mutated mirror. A fresh
                    # shadow validates the latest complete lawful source head.
                    affected = ()
                    needs_rebuild = True
                else:
                    needs_rebuild = False
                for item_id in affected:
                    captured = self.sources.capture(item_id, cancelled=cancelled)
                    if captured.watermark != target:
                        raise IndexServiceProblem("index sources changed during update")
                    old = store.entry_ids(item_id)
                    new_ids = {row.entry_id for row in captured.rows}
                    removed.extend(entry for entry in old if entry not in new_ids)
                    rows.extend(captured.rows)
                    if (
                        len(rows) + len(removed) > 256
                        or len(tuple(self._chunks(tuple(rows)))) > 1
                        or sum(
                            len(value.encode("utf-8"))
                            for row in rows
                            for value in asdict(row).values()
                            if isinstance(value, str)
                        )
                        > 4 * 1024 * 1024
                    ):
                        break
                else:
                    if needs_rebuild:
                        # Close the old reader before replacement/retirement.
                        return None
                    self.catalog.renew(lease)
                    self._check_cancel(cancelled)
                    store.apply(tuple(rows), tuple(removed), expected_checkpoint=selected.checkpoint, checkpoint=target)
                    _index_step("incremental-derivative-committed")
                    validation = self._validate(store, lease, repair_shadow=False, cancelled=cancelled)
                    store.integrity_check()
                    self.catalog.publish_ready(
                        lease,
                        store.projection(),
                        validation,
                        expected_selection_id=selected.selection_id,
                        revalidate=self._revalidator(validation, cancelled=cancelled),
                        cancelled=cancelled,
                    )
                    updated = self.catalog.selected()
                    if updated is None:
                        raise IndexServiceProblem("index update selection is unavailable")
                    return updated
            # A large replacement uses a private shadow rather than exposing a
            # partly replaced item's text across multiple active transactions.
            return self.rebuild(cancelled=cancelled)

        updated = self._orchestrate(update)
        return self.rebuild(cancelled=cancelled) if updated is None else updated

    def match(self, query: QueryDocument, *, cancelled: Callable[[], bool] = lambda: False) -> tuple[str, ...]:
        """Internal authorized candidate IDs; ranking/paging belongs to S01.T03."""

        def read():
            query.validate()
            selected = self.catalog.selected()
            if selected is None:
                raise IndexServiceProblem("index has no selected generation")
            self._current(selected)
            watermark = self.catalog.watermark()
            entries: list[str] = []
            items: list[str] = []
            result: list[str] = []
            expiry = None
            with ProtectedLexicalStore(self.root, selected.scope, self.keys, cancelled=cancelled) as store:
                if not self.catalog.file_bound(selected.generation_id, store.file_identity):
                    raise IndexServiceProblem("selected index file changed")
                if (
                    store.checkpoint != selected.checkpoint
                    or store.projection().manifest_sha256 != selected.projection_sha256
                ):
                    raise IndexServiceProblem("index update requires acknowledgement")
                for item_id in self._items():
                    self._check_cancel(cancelled)
                    captured = self.sources.capture(item_id, cancelled=cancelled)
                    if captured.watermark != watermark:
                        raise IndexServiceProblem("search authority changed")
                    if captured.rows:
                        if selected.checkpoint != watermark:
                            raise IndexServiceProblem("index source changes require synchronization")
                        if len(captured.rows) > _MAX_QUERY_BATCH_ENTRIES:
                            raise IndexServiceProblem("index item authorization budget exceeded")
                        if items and (
                            len(items) == _MAX_QUERY_BATCH_ITEMS
                            or len(entries) + len(captured.rows) > _MAX_QUERY_BATCH_ENTRIES
                        ):
                            result.extend(store.match(query, tuple(entries), tuple(items)))
                            entries, items = [], []
                        # Every permitted row for an item stays together. Full
                        # Boolean evaluation over disjoint item universes can
                        # then be united without changing AND/OR/NOT meaning.
                        items.append(item_id)
                        entries.extend(row.entry_id for row in captured.rows)
                    if captured.expires_at is not None:
                        expiry = captured.expires_at if expiry is None else min(expiry, captured.expires_at)
                if items:
                    result.extend(store.match(query, tuple(entries), tuple(items)))
            validation = IndexValidation(
                watermark, "0" * 64, actor_context_sha256(self.project, self.sources.documents.actor()), expiry
            )
            with self.sources.corpus._transaction(write=True) as (db, _aggregates):
                self._fence(db, validation)
                if expiry is not None and self.catalog.now() >= expiry:
                    raise IndexServiceProblem("search permission expired")
            self._current(selected)
            self._check_cancel(cancelled)
            if expiry is not None and self.catalog.now() >= expiry:
                raise IndexServiceProblem("search permission expired")
            return tuple(result)

        return self._bounded(read)

    def close(self) -> None:
        for lease in self._leases.values():
            lease.close()
        self._leases.clear()
