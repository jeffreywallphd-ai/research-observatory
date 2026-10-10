"""Encrypted, current-authority table/figure observations and human exclusions.

Reuse the existing canonical writer, v28 index, material manifests and source
fence. Excluding an unreliable object appends a revision; it never edits the
accepted parse, original copy or earlier observations.
"""

from collections.abc import Callable

from .document_reference_repository import REFERENCE_EVENT, LocalDocumentReferenceRepository, _Receipt
from .document_revisions import DocumentRevisionProblem, protected_json
from .document_table_figures import (
    MAX_TABLE_FIGURE_BYTES,
    TABLE_FIGURE_EXTRACTION_VERSION,
    TABLE_FIGURE_MEDIA,
    TableFigureCollection,
    TableFigureCommand,
    TableFigureExcludeCommand,
    TableFigureExclusion,
    TableFigureProblem,
    extract_table_figures,
)
from .domain_contracts import new_uuid_v7
from .parsing.docling import DOCLING_MEDIA_TYPE
from .ports.reconciliation import ReconciliationActor
from .reconciliation_repository import _digest

EXTRA_PARAMETER = ("table-figure-extraction", "1.0.0", _digest(TABLE_FIGURE_EXTRACTION_VERSION))


def _publication_step(_step: str) -> None:
    """Deterministic interruption seam; no I/O."""


class LocalDocumentTableFigureRepository(LocalDocumentReferenceRepository):
    def _bounded(self, action):
        try:
            self.anchors._current_actor()
            return self.revisions._bounded(action)
        except DocumentRevisionProblem as problem:
            if problem.code == "viewer-resource-limit":
                raise
            raise DocumentRevisionProblem("document-table-figures-denied") from None
        except Exception:
            raise DocumentRevisionProblem("document-table-figures-denied") from None

    @staticmethod
    def _check(cancelled):
        if cancelled():
            raise TableFigureProblem("structure-operation-cancelled")

    def _head(self, connection, document_revision_id):
        rows = connection.execute(
            "SELECT e.revision_id,e.collection_id FROM document_enrichments e "
            "JOIN aggregate_revisions r ON r.revision_id=e.revision_id AND r.project_id=e.project_id "
            "WHERE e.project_id=? AND e.document_revision_id=? AND e.enrichment_kind='table-figures' "
            "AND NOT EXISTS (SELECT 1 FROM aggregate_revisions n WHERE n.project_id=r.project_id "
            "AND n.aggregate_id=r.aggregate_id AND n.revision>r.revision) LIMIT 2",
            (self.revisions.project, document_revision_id),
        ).fetchall()
        if len(rows) > 1:
            raise TableFigureProblem("structure-collection-head-invalid")
        return tuple(rows[0]) if rows else None

    @staticmethod
    def _index_rows(collection):
        return [
            (
                collection.project_id,
                collection.collection_revision_id,
                collection.document_revision_id,
                entry.node_id,
                entry.node_id,
                entry.source_order,
            )
            for entry in collection.entries
        ]

    def _record(self, connection, revision_id, *, check_previous=True):
        row = connection.execute(
            "SELECT collection_id,document_revision_id,previous_revision_id,command_id,"
            "command_sha256,actor_id,payload_sha256 FROM document_enrichments "
            "WHERE project_id=? AND revision_id=? AND enrichment_kind='table-figures'",
            (self.revisions.project, revision_id),
        ).fetchone()
        if row is None:
            raise TableFigureProblem("structure-collection-unavailable")
        metadata = connection.execute(
            "SELECT byte_length FROM object_records WHERE project_id=? AND object_sha256=?",
            (self.revisions.project, row[6]),
        ).fetchone()
        if metadata is None or not 0 < metadata[0] <= MAX_TABLE_FIGURE_BYTES:
            raise TableFigureProblem("structure-collection-invalid")
        collection = TableFigureCollection.model_validate_json(
            self.revisions.objects._read_protected_document_artifact(
                connection, _Receipt(row[6], metadata[0]), TABLE_FIGURE_MEDIA
            )
        )
        if (
            collection.project_id != self.revisions.project
            or collection.collection_revision_id != revision_id
            or tuple(row[:6])
            != (
                collection.collection_id,
                collection.document_revision_id,
                collection.previous_collection_revision_id,
                collection.command_id,
                collection.command_sha256,
                collection.actor_id,
            )
        ):
            raise TableFigureProblem("structure-collection-binding-invalid")
        with self.revisions._aggregates(connection) as aggregates:
            revision = aggregates.get_revision(revision_id)
            if (revision.aggregate_kind, revision.aggregate_id, revision.object_sha256, revision.knowledge_status) != (
                "document",
                collection.collection_id,
                row[6],
                "inferred",
            ):
                raise TableFigureProblem("structure-collection-binding-invalid")
            if collection.previous_collection_revision_id is None:
                if revision.revision != 0 or collection.change_kind != "extraction" or collection.exclusions:
                    raise TableFigureProblem("structure-collection-predecessor-invalid")
            else:
                previous = aggregates.get_revision(collection.previous_collection_revision_id)
                if previous.aggregate_id != collection.collection_id or previous.revision + 1 != revision.revision:
                    raise TableFigureProblem("structure-collection-predecessor-invalid")
            events = connection.execute(
                "SELECT event_type,actor_type,actor_id,occurred_at FROM provenance_events "
                "WHERE project_id=? AND revision_id=?",
                (self.revisions.project, revision_id),
            ).fetchall()
            if [tuple(e) for e in events] != [
                (REFERENCE_EVENT, "human", collection.actor_id, collection.extracted_at)
            ] or revision.modified_at != collection.extracted_at:
                raise TableFigureProblem("structure-collection-provenance-invalid")
        rows = connection.execute(
            "SELECT project_id,collection_revision_id,document_revision_id,element_id,node_id,element_order "
            "FROM document_enrichment_elements WHERE project_id=? AND collection_revision_id=?",
            (self.revisions.project, revision_id),
        ).fetchall()
        if sorted(tuple(r) for r in rows) != sorted(self._index_rows(collection)):
            raise TableFigureProblem("structure-collection-index-invalid")
        for table in ("document_enrichment_identifiers", "document_enrichment_targets"):
            if connection.execute(
                f"SELECT 1 FROM {table} WHERE project_id=? AND collection_revision_id=? LIMIT 1",
                (self.revisions.project, revision_id),
            ).fetchone():
                raise TableFigureProblem("structure-collection-index-invalid")
        if check_previous and collection.previous_collection_revision_id is not None:
            previous = self._record(connection, collection.previous_collection_revision_id, check_previous=False)
            # Authenticate just the immutable predecessor, not an unbounded
            # history walk. Canonical commit/index already pins every revision.
            if (collection.document_revision_id, collection.source, collection.entries) != (
                previous.document_revision_id,
                previous.source,
                previous.entries,
            ):
                raise TableFigureProblem("structure-collection-history-invalid")
            if collection.change_kind == "extraction":
                if collection.exclusions != previous.exclusions:
                    raise TableFigureProblem("structure-exclusion-history-invalid")
            elif (
                len(collection.exclusions) != len(previous.exclusions) + 1
                or collection.exclusions[:-1] != previous.exclusions
            ):
                raise TableFigureProblem("structure-exclusion-history-invalid")
        return collection

    def _prepare(self, connection, actor, document_revision_id, cancelled):
        self._check(cancelled)
        accepted = self.revisions._accepted(connection, document_revision_id)
        receipts = [r for r in accepted.structure.raw_artifacts if r.media_type == DOCLING_MEDIA_TYPE]
        if len(receipts) > 1 or (receipts and receipts[0].byte_length > MAX_TABLE_FIGURE_BYTES):
            raise TableFigureProblem("structure-parser-binding-invalid")
        docling = (
            self.revisions.objects._read_protected_document_artifact(connection, receipts[0], DOCLING_MEDIA_TYPE)
            if receipts
            else None
        )
        entries = extract_table_figures(
            accepted, native_artifact=self._native(connection, accepted), docling_artifact=docling, cancelled=cancelled
        )
        with self.revisions._aggregates(connection) as aggregates:
            inputs = self._inputs(connection, aggregates, accepted)
            self.matching.reconciliation._require_fresh_inputs(aggregates, tuple(i.revision_id for i in inputs))
        return accepted, entries, inputs

    def _validate(self, connection, aggregates, collection, expected):
        self._validate_inputs(
            connection,
            aggregates,
            collection,
            expected,
            payload_configuration="table-figure-collection",
            extra_parameter=EXTRA_PARAMETER,
        )

    @staticmethod
    def _require_same(collection, accepted, entries, actor):
        if (
            collection.document_revision_id,
            collection.source,
            collection.content_sha256,
            collection.structure_sha256,
            collection.entries,
            collection.intent_sha256,
            collection.policy_sha256,
        ) != (
            accepted.revision_id,
            accepted.structure.binding.source,
            accepted.content_sha256,
            accepted.structure_sha256,
            entries,
            actor.intent_sha256,
            actor.policy_sha256,
        ):
            raise TableFigureProblem("structure-collection-requires-review")

    def read(self, document_revision_id, *, cancelled: Callable[[], bool] = lambda: False):
        def read():
            source = self._source(document_revision_id)

            def current(connection, actor):
                accepted, entries, inputs = self._prepare(connection, actor, document_revision_id, cancelled)
                head = self._head(connection, document_revision_id)
                if head is None:
                    return None
                collection = self._record(connection, head[0])
                self._require_same(collection, accepted, entries, actor)
                with self.revisions._aggregates(connection) as aggregates:
                    self._validate(connection, aggregates, collection, {i.revision_id for i in inputs})
                self._check(cancelled)
                return collection

            return self.anchors._fenced(source, current)

        return self._bounded(read)

    def enrich(self, command, *, cancelled: Callable[[], bool] = lambda: False):
        return self._change(command, exclusion=False, cancelled=cancelled)

    def exclude(self, command, *, cancelled: Callable[[], bool] = lambda: False):
        return self._change(command, exclusion=True, cancelled=cancelled)

    def _change(self, command, *, exclusion, cancelled):
        def change():
            selected = (TableFigureExcludeCommand if exclusion else TableFigureCommand).model_validate(command)
            source = self._source(selected.revision_id)
            actor = self.anchors._current_actor()
            accepted, entries, inputs = self.anchors._fenced(
                source, lambda c, a: self._prepare(c, a, selected.revision_id, cancelled)
            )
            digest = _digest(
                [
                    self.revisions.project,
                    selected.model_dump(mode="json", by_alias=True),
                    actor.actor_id,
                    actor.intent_revision_id,
                    actor.intent_sha256,
                    actor.policy_sha256,
                    TABLE_FIGURE_EXTRACTION_VERSION,
                    "exclusion" if exclusion else "extraction",
                ]
            )

            def build(connection, current_actor):
                self._check(cancelled)
                if current_actor != actor:
                    raise TableFigureProblem("structure-authority-changed")
                existing = connection.execute(
                    "SELECT revision_id,command_sha256 FROM document_enrichments WHERE project_id=? AND command_id=?",
                    (self.revisions.project, selected.command_id),
                ).fetchone()
                if existing:
                    if existing[1] != digest:
                        raise TableFigureProblem("structure-command-reuse-conflict")
                    return self._record(connection, existing[0])
                head = self._head(connection, selected.revision_id)
                if (head[0] if head else None) != selected.expected_collection_revision_id:
                    raise TableFigureProblem("structure-collection-predecessor-changed")
                previous = self._record(connection, head[0]) if head else None
                exclusions: tuple[TableFigureExclusion, ...] = previous.exclusions if previous else ()
                if exclusion:
                    if not isinstance(selected, TableFigureExcludeCommand):
                        raise TableFigureProblem("structure-exclusion-command-invalid")
                    if (
                        previous is None
                        or selected.node_id not in {e.node_id for e in entries}
                        or selected.node_id in {e.node_id for e in exclusions}
                    ):
                        raise TableFigureProblem("structure-exclusion-unavailable")
                    self._require_same(previous, accepted, entries, actor)
                    exclusions += (
                        TableFigureExclusion(
                            node_id=selected.node_id,
                            actor_id=actor.actor_id,
                            command_id=selected.command_id,
                            rationale=selected.rationale,
                            occurred_at=actor.occurred_at,
                        ),
                    )
                return TableFigureCollection(
                    project_id=self.revisions.project,
                    collection_id=head[1] if head else new_uuid_v7(),
                    collection_revision_id=new_uuid_v7(),
                    previous_collection_revision_id=selected.expected_collection_revision_id,
                    document_revision_id=accepted.revision_id,
                    source=accepted.structure.binding.source,
                    content_sha256=accepted.content_sha256,
                    structure_sha256=accepted.structure_sha256,
                    command_id=selected.command_id,
                    command_sha256=digest,
                    actor_id=actor.actor_id,
                    intent_sha256=actor.intent_sha256,
                    policy_sha256=actor.policy_sha256,
                    extracted_at=actor.occurred_at,
                    change_kind="exclusion" if exclusion else "extraction",
                    entries=entries,
                    exclusions=exclusions,
                )

            collection = self.anchors._fenced(source, build)
            self._require_same(collection, accepted, entries, actor)
            _publication_step("table-figures-prepared")
            raw = protected_json(collection)
            self.admit(len(raw))

            def publish(connection, stored):
                self._check(cancelled)
                current_actor = self.anchors._current_actor()
                self.revisions._authority(connection, current_actor)
                if current_actor != actor or self.revisions._accepted(connection, selected.revision_id) != accepted:
                    raise TableFigureProblem("structure-document-authority-changed")
                with self.revisions._aggregates(connection) as aggregates:
                    material = {i.revision_id: i for i in self._inputs(connection, aggregates, accepted)}
                    if tuple(material.values()) != inputs:
                        raise TableFigureProblem("structure-document-inputs-changed")
                    self.matching.reconciliation._require_fresh_inputs(aggregates, tuple(material))
                    existing = connection.execute(
                        "SELECT revision_id,command_sha256 FROM document_enrichments "
                        "WHERE project_id=? AND command_id=?",
                        (self.revisions.project, selected.command_id),
                    ).fetchone()
                    if existing:
                        if (
                            tuple(existing) != (collection.collection_revision_id, digest)
                            or self._record(connection, existing[0]) != collection
                        ):
                            raise TableFigureProblem("structure-command-reuse-conflict")
                        self._validate(connection, aggregates, collection, set(material))
                        return collection
                    head = self._head(connection, selected.revision_id)
                    if (head[0] if head else None) != selected.expected_collection_revision_id:
                        raise TableFigureProblem("structure-collection-predecessor-changed")
                    reconciler = self.matching.reconciliation
                    human = ReconciliationActor(
                        actor.actor_id, actor.trace_id, actor.occurred_at, actor.intent_sha256, actor.policy_sha256
                    )
                    revision = reconciler._append(
                        aggregates,
                        sources=tuple(material[k] for k in sorted(material)),
                        actor=human,
                        digest=stored.object_sha256,
                        label="Document tables and figures",
                        kind="document",
                        current=aggregates.get_revision(head[0]) if head else None,
                        revision_id=collection.collection_revision_id,
                        aggregate_id=collection.collection_id,
                        object_sha256=stored.object_sha256,
                        event_type=REFERENCE_EVENT,
                        idempotency_key="document.table-figures." + selected.command_id,
                        payload_configuration="table-figure-collection",
                        extra_parameter=EXTRA_PARAMETER,
                        checkpoint=lambda: self._check(cancelled),
                        sort_manifest_inputs=True,
                    )
                    connection.execute(
                        "INSERT INTO document_enrichments VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            revision.revision_id,
                            self.revisions.project,
                            revision.aggregate_id,
                            accepted.revision_id,
                            "table-figures",
                            collection.previous_collection_revision_id,
                            selected.command_id,
                            digest,
                            actor.actor_id,
                            stored.object_sha256,
                        ),
                    )
                    for row in self._index_rows(collection):
                        connection.execute("INSERT INTO document_enrichment_elements VALUES (?,?,?,?,?,?)", row)
                    if head:
                        reconciler._publish_impacts(
                            connection,
                            (reconciler._change(aggregates.get_revision(head[0]), revision, human, human=False),),
                        )
                    _publication_step("table-figures-before-commit")
                    self._check(cancelled)
                    return collection

            result = self.revisions._put(raw, TABLE_FIGURE_MEDIA, source, publish, cancelled)
            self._check(cancelled)
            return result

        return self._bounded(change)
