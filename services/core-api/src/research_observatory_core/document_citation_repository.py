"""Immutable encrypted citation contexts bound to the current reference revision.

Reuse canonical publication, current source/matching authority and complete
material-input validation. Inferred markers never enter the v28 element index
as invented canonical identities; their address is collection revision/order.
"""

from collections.abc import Callable

from .document_citations import (
    CITATION_EXTRACTION_VERSION,
    CITATION_MEDIA_TYPE,
    MAX_CITATION_BYTES,
    CitationCollection,
    CitationEnrichmentCommand,
    CitationProblem,
    extract_citation_contexts,
)
from .document_reference_repository import REFERENCE_EVENT, LocalDocumentReferenceRepository, _Receipt
from .document_references import match_reference_entries
from .document_revisions import DocumentRevisionProblem, protected_json
from .domain_contracts import new_uuid_v7
from .ports.reconciliation import ReconciliationActor
from .reconciliation_repository import _digest

EXTRA_PARAMETER = ("citation-extraction", "1.0.0", _digest(CITATION_EXTRACTION_VERSION))


def _publication_step(_step: str) -> None:
    """Deterministic precommit interruption seam, no I/O."""


class LocalDocumentCitationRepository(LocalDocumentReferenceRepository):
    def __init__(self, revisions, *, resolve, admit=lambda _size: None):
        super().__init__(revisions, resolve=resolve, admit=admit)
        self.references = LocalDocumentReferenceRepository(revisions, resolve=resolve, admit=admit)

    def _bounded(self, action):
        try:
            self.anchors._current_actor()
            return self.revisions._bounded(action)
        except DocumentRevisionProblem as problem:
            if problem.code == "viewer-resource-limit":
                raise
            raise DocumentRevisionProblem("document-citations-denied") from None
        except Exception:
            raise DocumentRevisionProblem("document-citations-denied") from None

    def _head(self, connection, document_revision_id):
        rows = connection.execute(
            "SELECT e.revision_id,e.collection_id FROM document_enrichments e "
            "JOIN aggregate_revisions r ON r.revision_id=e.revision_id AND r.project_id=e.project_id "
            "WHERE e.project_id=? AND e.document_revision_id=? AND e.enrichment_kind='citation-contexts' "
            "AND NOT EXISTS (SELECT 1 FROM aggregate_revisions n WHERE n.project_id=r.project_id "
            "AND n.aggregate_id=r.aggregate_id AND n.revision>r.revision) LIMIT 2",
            (self.revisions.project, document_revision_id),
        ).fetchall()
        if len(rows) > 1:
            raise CitationProblem("citation-collection-head-invalid")
        return tuple(rows[0]) if rows else None

    @staticmethod
    def _check(cancelled):
        if cancelled():
            raise CitationProblem("citation-operation-cancelled")

    @staticmethod
    def _index_rows(collection):
        return [
            (
                collection.project_id,
                collection.collection_revision_id,
                collection.document_revision_id,
                e.canonical_citation_id,
                e.node_id,
                e.canonical_order,
            )
            for e in collection.entries
            if e.canonical_citation_id is not None
        ]

    def _record(self, connection, collection_revision_id):
        row = connection.execute(
            "SELECT collection_id,document_revision_id,previous_revision_id,command_id,"
            "command_sha256,actor_id,payload_sha256 "
            "FROM document_enrichments WHERE project_id=? AND revision_id=? AND enrichment_kind='citation-contexts'",
            (self.revisions.project, collection_revision_id),
        ).fetchone()
        if row is None:
            raise CitationProblem("citation-collection-unavailable")
        metadata = connection.execute(
            "SELECT byte_length FROM object_records WHERE project_id=? AND object_sha256=?",
            (self.revisions.project, row[6]),
        ).fetchone()
        if metadata is None or not 0 < metadata[0] <= MAX_CITATION_BYTES:
            raise CitationProblem("citation-collection-invalid")
        raw = self.revisions.objects._read_protected_document_artifact(
            connection, _Receipt(row[6], metadata[0]), CITATION_MEDIA_TYPE
        )
        collection = CitationCollection.model_validate_json(raw)
        if (
            collection.project_id != self.revisions.project
            or collection.collection_revision_id != collection_revision_id
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
            raise CitationProblem("citation-collection-binding-invalid")
        with self.revisions._aggregates(connection) as aggregates:
            revision = aggregates.get_revision(collection_revision_id)
            if (revision.aggregate_kind, revision.aggregate_id, revision.object_sha256, revision.knowledge_status) != (
                "document",
                collection.collection_id,
                row[6],
                "inferred",
            ):
                raise CitationProblem("citation-collection-binding-invalid")
            if collection.previous_collection_revision_id is None:
                if revision.revision != 0:
                    raise CitationProblem("citation-collection-predecessor-invalid")
            else:
                previous = aggregates.get_revision(collection.previous_collection_revision_id)
                if previous.aggregate_id != collection.collection_id or previous.revision + 1 != revision.revision:
                    raise CitationProblem("citation-collection-predecessor-invalid")
            events = connection.execute(
                "SELECT event_type,actor_type,actor_id,occurred_at FROM provenance_events "
                "WHERE project_id=? AND revision_id=?",
                (self.revisions.project, collection_revision_id),
            ).fetchall()
            if [tuple(e) for e in events] != [
                (REFERENCE_EVENT, "human", collection.actor_id, collection.extracted_at)
            ] or revision.modified_at != collection.extracted_at:
                raise CitationProblem("citation-collection-provenance-invalid")
        rows = connection.execute(
            "SELECT project_id,collection_revision_id,document_revision_id,element_id,node_id,element_order "
            "FROM document_enrichment_elements WHERE project_id=? AND collection_revision_id=?",
            (self.revisions.project, collection_revision_id),
        ).fetchall()
        if sorted(tuple(row) for row in rows) != sorted(self._index_rows(collection)):
            raise CitationProblem("citation-collection-index-invalid")
        for table in ("document_enrichment_identifiers", "document_enrichment_targets"):
            if connection.execute(
                f"SELECT 1 FROM {table} WHERE project_id=? AND collection_revision_id=? LIMIT 1",
                (self.revisions.project, collection_revision_id),
            ).fetchone():
                raise CitationProblem("citation-collection-index-invalid")
        return collection

    def _prepare(self, connection, actor, document_revision_id, cancelled):
        accepted, entries, inputs, snapshot, prepared = self.references._prepare(
            connection, actor, document_revision_id, cancelled
        )
        head = self.references._head(connection, document_revision_id)
        if head is None:
            raise CitationProblem("citation-references-unavailable")
        reference = self.references._record(connection, head[0])
        matched = match_reference_entries(entries, snapshot.works, snapshot.assessments, cancelled=cancelled)
        if (
            reference.document_revision_id,
            reference.content_sha256,
            reference.structure_sha256,
            reference.entries,
            reference.intent_sha256,
            reference.policy_sha256,
            reference.catalog_sha256,
        ) != (
            accepted.revision_id,
            accepted.content_sha256,
            accepted.structure_sha256,
            matched,
            actor.intent_sha256,
            actor.policy_sha256,
            snapshot.sha256,
        ):
            raise CitationProblem("citation-references-require-review")
        with self.revisions._aggregates(connection) as aggregates:
            self.references._validate_inputs(
                connection, aggregates, reference, set(snapshot.input_revision_ids) | {i.revision_id for i in inputs}
            )
            digest = aggregates.get_revision(reference.collection_revision_id).object_sha256
        contexts = extract_citation_contexts(
            accepted, reference.entries, native_artifact=self._native(connection, accepted), cancelled=cancelled
        )
        return accepted, contexts, inputs, reference, digest, snapshot, prepared

    @staticmethod
    def _binding(reference, digest):
        return reference.collection_id, reference.collection_revision_id, digest

    def _validate(self, connection, aggregates, collection, expected):
        self._validate_inputs(
            connection,
            aggregates,
            collection,
            expected,
            payload_configuration="citation-collection",
            extra_parameter=EXTRA_PARAMETER,
        )

    def read(self, document_revision_id, *, cancelled: Callable[[], bool] = lambda: False):
        def read():
            source = self._source(document_revision_id)

            def current(connection, actor):
                accepted, contexts, inputs, reference, digest, _, _ = self._prepare(
                    connection, actor, document_revision_id, cancelled
                )
                head = self._head(connection, document_revision_id)
                if head is None:
                    return None
                collection = self._record(connection, head[0])
                self._require_same(collection, accepted, contexts, reference, digest, actor)
                with self.revisions._aggregates(connection) as aggregates:
                    self._validate(
                        connection,
                        aggregates,
                        collection,
                        {i.revision_id for i in inputs} | {reference.collection_revision_id},
                    )
                self._check(cancelled)
                return collection

            return self.anchors._fenced(source, current)

        return self._bounded(read)

    def _require_same(self, collection, accepted, contexts, reference, digest, actor):
        if (
            collection.document_revision_id,
            collection.content_sha256,
            collection.structure_sha256,
            collection.entries,
            collection.intent_sha256,
            collection.policy_sha256,
            collection.reference_collection_id,
            collection.reference_collection_revision_id,
            collection.reference_payload_sha256,
        ) != (
            accepted.revision_id,
            accepted.content_sha256,
            accepted.structure_sha256,
            contexts,
            actor.intent_sha256,
            actor.policy_sha256,
            *self._binding(reference, digest),
        ):
            raise CitationProblem("citation-collection-requires-review")

    def enrich(self, command, *, cancelled: Callable[[], bool] = lambda: False):
        def enrich():
            selected = CitationEnrichmentCommand.model_validate(command)
            source = self._source(selected.revision_id)
            actor = self.anchors._current_actor()
            accepted, contexts, inputs, reference, ref_digest, snapshot, prepared = self.anchors._fenced(
                source, lambda c, a: self._prepare(c, a, selected.revision_id, cancelled)
            )
            if reference.collection_revision_id != selected.reference_collection_revision_id:
                raise CitationProblem("citation-reference-predecessor-changed")
            digest = _digest(
                [
                    self.revisions.project,
                    selected.model_dump(mode="json", by_alias=True),
                    actor.actor_id,
                    actor.intent_revision_id,
                    actor.intent_sha256,
                    actor.policy_sha256,
                    CITATION_EXTRACTION_VERSION,
                    self._binding(reference, ref_digest),
                ]
            )

            def build(connection, current_actor):
                self._check(cancelled)
                if current_actor != actor:
                    raise CitationProblem("citation-authority-changed")
                existing = connection.execute(
                    "SELECT revision_id,command_sha256 FROM document_enrichments WHERE project_id=? AND command_id=?",
                    (self.revisions.project, selected.command_id),
                ).fetchone()
                if existing:
                    if existing[1] != digest:
                        raise CitationProblem("citation-command-reuse-conflict")
                    return self._record(connection, existing[0])
                head = self._head(connection, selected.revision_id)
                if (head[0] if head else None) != selected.expected_collection_revision_id:
                    raise CitationProblem("citation-collection-predecessor-changed")
                return CitationCollection(
                    project_id=self.revisions.project,
                    collection_id=head[1] if head else new_uuid_v7(),
                    collection_revision_id=new_uuid_v7(),
                    previous_collection_revision_id=selected.expected_collection_revision_id,
                    document_revision_id=accepted.revision_id,
                    content_sha256=accepted.content_sha256,
                    structure_sha256=accepted.structure_sha256,
                    reference_collection_id=reference.collection_id,
                    reference_collection_revision_id=reference.collection_revision_id,
                    reference_payload_sha256=ref_digest,
                    command_id=selected.command_id,
                    command_sha256=digest,
                    actor_id=actor.actor_id,
                    intent_sha256=actor.intent_sha256,
                    policy_sha256=actor.policy_sha256,
                    extracted_at=actor.occurred_at,
                    entries=contexts,
                )

            collection = self.anchors._fenced(source, build)
            self._require_same(collection, accepted, contexts, reference, ref_digest, actor)
            _publication_step("citation-prepared")
            raw = protected_json(collection)
            self.admit(len(raw))

            def publish(connection, stored):
                self._check(cancelled)
                current_actor = self.anchors._current_actor()
                self.revisions._authority(connection, current_actor)
                if current_actor != actor or self.revisions._accepted(connection, selected.revision_id) != accepted:
                    raise CitationProblem("citation-document-authority-changed")
                if self.references._head(connection, selected.revision_id) != (
                    reference.collection_revision_id,
                    reference.collection_id,
                ):
                    raise CitationProblem("citation-reference-predecessor-changed")
                if self.references._record(connection, reference.collection_revision_id) != reference:
                    raise CitationProblem("citation-reference-binding-invalid")
                with self.revisions._aggregates(connection) as aggregates:
                    current_snapshot = self.matching.snapshot(
                        connection, aggregates, reference.entries, resolve=self._cached(prepared), cancelled=cancelled
                    )
                    if (
                        current_snapshot != snapshot
                        or aggregates.get_revision(reference.collection_revision_id).object_sha256 != ref_digest
                    ):
                        raise CitationProblem("citation-reference-authority-changed")
                    self.references._validate_inputs(
                        connection,
                        aggregates,
                        reference,
                        set(snapshot.input_revision_ids) | {i.revision_id for i in inputs},
                    )
                    existing = connection.execute(
                        "SELECT revision_id,command_sha256 FROM document_enrichments "
                        "WHERE project_id=? AND command_id=?",
                        (self.revisions.project, selected.command_id),
                    ).fetchone()
                    material = {i.revision_id: i for i in inputs}
                    material[reference.collection_revision_id] = aggregates.get_revision(
                        reference.collection_revision_id
                    )
                    if existing:
                        if (
                            tuple(existing) != (collection.collection_revision_id, digest)
                            or self._record(connection, existing[0]) != collection
                        ):
                            raise CitationProblem("citation-command-reuse-conflict")
                        self._validate(connection, aggregates, collection, set(material))
                        return collection
                    head = self._head(connection, selected.revision_id)
                    if (head[0] if head else None) != selected.expected_collection_revision_id:
                        raise CitationProblem("citation-collection-predecessor-changed")
                    reconciler = self.matching.reconciliation
                    human = ReconciliationActor(
                        actor.actor_id, actor.trace_id, actor.occurred_at, actor.intent_sha256, actor.policy_sha256
                    )
                    revision = reconciler._append(
                        aggregates,
                        sources=tuple(material[k] for k in sorted(material)),
                        actor=human,
                        digest=stored.object_sha256,
                        label="Document citation contexts",
                        kind="document",
                        current=aggregates.get_revision(head[0]) if head else None,
                        revision_id=collection.collection_revision_id,
                        aggregate_id=collection.collection_id,
                        object_sha256=stored.object_sha256,
                        event_type=REFERENCE_EVENT,
                        idempotency_key="document.citations." + selected.command_id,
                        payload_configuration="citation-collection",
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
                            "citation-contexts",
                            collection.previous_collection_revision_id,
                            collection.command_id,
                            digest,
                            actor.actor_id,
                            stored.object_sha256,
                        ),
                    )
                    for row in self._index_rows(collection):
                        connection.execute("INSERT INTO document_enrichment_elements VALUES (?,?,?,?,?,?)", row)
                    if head:
                        previous = aggregates.get_revision(head[0])
                        reconciler._publish_impacts(
                            connection, (reconciler._change(previous, revision, human, human=False),)
                        )
                    _publication_step("citation-before-commit")
                    self._check(cancelled)
                    return collection

            result = self.revisions._put(raw, CITATION_MEDIA_TYPE, source, publish, cancelled)
            self._check(cancelled)
            return result

        return self._bounded(enrich)
