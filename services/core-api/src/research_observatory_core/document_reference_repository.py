"""Current-authority encrypted reference collections, separate from accepted v1.

Protected source resolution happens before the object writer. The caller must
hold one Native/project/rights lifecycle fence through preparation, publication
and delivery. The writer recomputes the complete canonical matching snapshot
using only those already authorized sources; a new source is a conflict.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass

from .document_references import (
    MAX_REFERENCE_BYTES,
    NATIVE_MEDIA_TYPE,
    REFERENCE_EXTRACTION_VERSION,
    ReferenceCollection,
    ReferenceEnrichmentCommand,
    ReferenceProblem,
    extract_references,
    match_reference_entries,
)
from .document_revisions import DocumentRevisionProblem, protected_json
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .parsing.requests import ParseRequest
from .ports.reconciliation import ReconciliationActor, ReconciliationSourceResolver
from .reconciliation.candidates import DEFAULT_CONFIG
from .reconciliation.identifiers import NORMALIZER_VERSION
from .reconciliation_repository import _digest
from .reference_matching_repository import ReferenceMatchingRepository
from .repositories import _material_registration_with_connection, _projection_content_sha256
from .storage import open_canonical_database

REFERENCE_COLLECTION_MEDIA = "application/vnd.research-observatory.document-references+json"
REFERENCE_EVENT = "org.research-observatory.document.revision-recorded.v1"


def _publication_step(_step: str) -> None:
    """Deterministic precommit interruption seam; no external I/O."""


@dataclass(frozen=True, slots=True)
class _Receipt:
    object_sha256: str
    byte_length: int


class LocalDocumentReferenceRepository:
    def __init__(self, revisions, *, resolve: ReconciliationSourceResolver, admit=lambda _size: None):
        self.revisions = revisions
        self.anchors = revisions.source_anchors()
        self.matching = ReferenceMatchingRepository(revisions.database, revisions.project, admit=admit)
        self.resolve = resolve
        self.admit = admit

    def _bounded(self, action):
        try:
            self.anchors._current_actor()
            return self.revisions._bounded(action)
        except DocumentRevisionProblem as problem:
            if problem.code == "viewer-resource-limit":
                raise
            raise DocumentRevisionProblem("document-references-denied") from None
        except Exception:
            raise DocumentRevisionProblem("document-references-denied") from None

    def _source(self, document_revision_id):
        if not is_uuid_v7(document_revision_id):
            raise ReferenceProblem("reference-revision-unavailable")
        with closing(
            open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
        ) as db:
            return self.anchors._source(db, document_revision_id)

    def current_head(self, document_revision_id):
        """Opaque recovery selector only; a head grants no reference read authority."""
        return self._bounded(
            lambda: self.anchors._fenced(
                self._source(document_revision_id),
                lambda connection, _actor: self._head(connection, document_revision_id),
            )
        )

    @staticmethod
    def _check(cancelled):
        if cancelled():
            raise ReferenceProblem("reference-operation-cancelled")

    def _head(self, connection, document_revision_id):
        rows = connection.execute(
            "SELECT e.revision_id,e.collection_id FROM document_enrichments e "
            "JOIN aggregate_revisions r ON r.revision_id=e.revision_id AND r.project_id=e.project_id "
            "WHERE e.project_id=? AND e.document_revision_id=? AND e.enrichment_kind='references' "
            "AND NOT EXISTS (SELECT 1 FROM aggregate_revisions n WHERE n.project_id=r.project_id "
            "AND n.aggregate_id=r.aggregate_id AND n.revision>r.revision) LIMIT 2",
            (self.revisions.project, document_revision_id),
        ).fetchall()
        if len(rows) > 1:
            raise ReferenceProblem("reference-collection-head-invalid")
        return tuple(rows[0]) if rows else None

    def _inputs(self, connection, aggregates, accepted):
        result = self.revisions._result(connection, accepted.result)
        request = ParseRequest(
            schema_version="1.0",
            binding=result.binding,
            selection=self.revisions._input(connection, result.binding.attempt.job_id).selection,
        )
        raw = self.revisions._raw_inputs(connection, aggregates, request, result.ir)
        # The human-accepted revision is the current semantic input. Its own
        # immutable provenance retains the original copy. Do not reclassify that
        # pre-acceptance copy as a fresh output: an earlier rights recheck may
        # have invalidated it before the researcher accepted this structure.
        # Current exact-copy inspect/derive rights remain checked by _fenced.
        retained = tuple(item for item in raw if item.revision_id != result.binding.source.document_revision_id)
        values = retained + tuple(
            aggregates.get_revision(revision)
            for revision in (
                accepted.revision_id,
                accepted.decision_revision_id,
                accepted.result.revision_id,
            )
        )
        return tuple({item.revision_id: item for item in values}.values())

    def _native(self, connection, accepted):
        receipts = [item for item in accepted.structure.raw_artifacts if item.media_type == NATIVE_MEDIA_TYPE]
        if len(receipts) > 1:
            raise ReferenceProblem("reference-native-binding-invalid")
        if not receipts:
            return None
        if receipts[0].byte_length > MAX_REFERENCE_BYTES:
            raise ReferenceProblem("reference-operation-limit")
        return self.revisions.objects._read_protected_document_artifact(connection, receipts[0], NATIVE_MEDIA_TYPE)

    def _prepare(self, connection, actor, document_revision_id, cancelled):
        self._check(cancelled)
        accepted = self.revisions._accepted(connection, document_revision_id)
        entries = extract_references(accepted, native_artifact=self._native(connection, accepted), cancelled=cancelled)
        with self.revisions._aggregates(connection) as aggregates:
            inputs = self._inputs(connection, aggregates, accepted)
            prepared, collect = self.matching.reconciliation._source_snapshot(
                self.resolve, checkpoint=lambda: self._check(cancelled)
            )
            snapshot = self.matching.snapshot(connection, aggregates, entries, resolve=collect, cancelled=cancelled)
        return accepted, entries, inputs, snapshot, prepared

    @staticmethod
    def _cached(prepared):
        def resolve(address):
            key = _digest(address.model_dump(mode="json"))
            if key not in prepared:
                raise ReferenceProblem("reference-concurrent-source-change")
            return prepared[key]

        return resolve

    @staticmethod
    def _command_digest(command, actor, project):
        return _digest(
            [
                project,
                command.model_dump(mode="json", by_alias=True),
                actor.actor_id,
                actor.intent_revision_id,
                actor.intent_sha256,
                actor.policy_sha256,
                REFERENCE_EXTRACTION_VERSION,
                NORMALIZER_VERSION,
                DEFAULT_CONFIG.fingerprint,
            ]
        )

    def _record(self, connection, collection_revision_id):
        row = connection.execute(
            "SELECT collection_id,document_revision_id,previous_revision_id,command_id,"
            "command_sha256,actor_id,payload_sha256 "
            "FROM document_enrichments WHERE project_id=? AND revision_id=? AND enrichment_kind='references'",
            (self.revisions.project, collection_revision_id),
        ).fetchone()
        if row is None:
            raise ReferenceProblem("reference-collection-unavailable")
        metadata = connection.execute(
            "SELECT byte_length FROM object_records WHERE project_id=? AND object_sha256=?",
            (self.revisions.project, row[6]),
        ).fetchone()
        if metadata is None or not 0 < metadata[0] <= MAX_REFERENCE_BYTES:
            raise ReferenceProblem("reference-collection-invalid")
        raw = self.revisions.objects._read_protected_document_artifact(
            connection, _Receipt(row[6], metadata[0]), REFERENCE_COLLECTION_MEDIA
        )
        result = ReferenceCollection.model_validate_json(raw)
        if (
            result.project_id != self.revisions.project
            or result.collection_revision_id != collection_revision_id
            or tuple(row[:6])
            != (
                result.collection_id,
                result.document_revision_id,
                result.previous_collection_revision_id,
                result.command_id,
                result.command_sha256,
                result.actor_id,
            )
        ):
            raise ReferenceProblem("reference-collection-binding-invalid")
        with self.revisions._aggregates(connection) as aggregates:
            revision = aggregates.get_revision(collection_revision_id)
            if (
                revision.aggregate_kind != "document"
                or revision.aggregate_id != result.collection_id
                or revision.object_sha256 != row[6]
                or revision.knowledge_status != "inferred"
            ):
                raise ReferenceProblem("reference-collection-binding-invalid")
            if result.previous_collection_revision_id is None:
                if revision.revision != 0:
                    raise ReferenceProblem("reference-collection-predecessor-invalid")
            else:
                previous = aggregates.get_revision(result.previous_collection_revision_id)
                if previous.aggregate_id != result.collection_id or previous.revision + 1 != revision.revision:
                    raise ReferenceProblem("reference-collection-predecessor-invalid")
            events = connection.execute(
                (
                    "SELECT event_type,actor_type,actor_id,occurred_at FROM provenance_events "
                    "WHERE project_id=? AND revision_id=?"
                ),
                (self.revisions.project, collection_revision_id),
            ).fetchall()
            if [tuple(e) for e in events] != [
                (REFERENCE_EVENT, "human", result.actor_id, result.extracted_at)
            ] or revision.modified_at != result.extracted_at:
                raise ReferenceProblem("reference-collection-provenance-invalid")
        elements, identifiers, targets = self._index_rows(result)
        for table, columns, order, expected in (
            (
                "document_enrichment_elements",
                "project_id,collection_revision_id,document_revision_id,element_id,node_id,element_order",
                "element_order",
                elements,
            ),
            (
                "document_enrichment_identifiers",
                "project_id,collection_revision_id,element_id,ordinal,scheme,key_sha256",
                "element_id,ordinal",
                identifiers,
            ),
            (
                "document_enrichment_targets",
                "project_id,collection_revision_id,element_id,ordinal,work_id,work_revision_id,relation_type,score",
                "element_id,ordinal",
                targets,
            ),
        ):
            found = connection.execute(
                f"SELECT {columns} FROM {table} WHERE project_id=? AND collection_revision_id=? ORDER BY {order}",
                (self.revisions.project, collection_revision_id),
            ).fetchall()
            if sorted(tuple(item) for item in found) != sorted(expected):
                raise ReferenceProblem("reference-collection-index-invalid")
        return result

    @staticmethod
    def _index_rows(collection):
        elements, identifiers, targets = [], [], []
        for entry in collection.entries:
            prefix = (collection.project_id, collection.collection_revision_id, entry.reference_id)
            elements.append(
                (
                    collection.project_id,
                    collection.collection_revision_id,
                    collection.document_revision_id,
                    entry.reference_id,
                    entry.node_id,
                    entry.order,
                )
            )
            for ordinal, identifier in enumerate(entry.identifiers):
                value = identifier.assertion.normalized
                if value.status == "valid" and value.canonical is not None:
                    identifiers.append(
                        (*prefix, ordinal, value.scheme, _digest([NORMALIZER_VERSION, value.scheme, value.canonical]))
                    )
            proposed = (
                [(entry.target, "exact", 10000)]
                if entry.target
                else [(c.target, "candidate", c.score) for c in entry.candidates]
            )
            for ordinal, (work, relation, score) in enumerate(proposed):
                targets.append((*prefix, ordinal, work.work_id, work.revision_id, relation, score))
        return elements, identifiers, targets

    def _validate_inputs(self, connection, aggregates, collection, expected):
        # Canonical manifests preserve all material leaves beyond 64 inputs.
        leaves: set[str] = set()
        visited: set[str] = set()
        pending = [(collection.collection_revision_id, 0)]
        while pending:
            revision_id, depth = pending.pop()
            if revision_id in visited or depth > 16 or len(visited) >= 32768:
                raise ReferenceProblem("reference-collection-dependency-invalid")
            visited.add(revision_id)
            registration = _material_registration_with_connection(connection, self.revisions.project, revision_id)
            if registration.coverage != "complete":
                raise ReferenceProblem("reference-collection-dependency-invalid")
            params = {
                d.configuration_id: (d.configuration_version, d.fingerprint)
                for d in registration.dependencies
                if d.dependency_kind == "parameter-set"
            }
            expected_params = {
                "scholarly.current-intent": ("1.0.0", "sha256:" + collection.intent_sha256),
                "scholarly.current-privacy": ("1.0.0", "sha256:" + collection.policy_sha256),
                "scholarly.normalizer": ("1.0.0", "sha256:" + _digest(NORMALIZER_VERSION)),
            }
            if any(params.get(k) != v for k, v in expected_params.items()):
                raise ReferenceProblem("reference-collection-dependency-invalid")
            dependencies = [
                d for d in registration.dependencies if d.dependency_kind in ("source-revision", "human-decision")
            ]
            children = []
            for dependency in dependencies:
                child = aggregates.get_revision(dependency.revision_id)
                if dependency.relation_type != "direct" or dependency.fingerprint != _projection_content_sha256(child):
                    raise ReferenceProblem("reference-collection-dependency-invalid")
                children.append(child)
                if child.revision_id in expected:
                    leaves.add(child.revision_id)
                else:
                    if child.aggregate_kind != "workflow":
                        raise ReferenceProblem("reference-collection-dependency-invalid")
                    pending.append((child.revision_id, depth + 1))
            if revision_id != collection.collection_revision_id and params.get("scholarly.input-manifest") != (
                "1.0.0",
                "sha256:"
                + _digest(
                    [
                        (c.revision_id, _projection_content_sha256(c))
                        for c in sorted(children, key=lambda child: child.revision_id)
                    ]
                ),
            ):
                raise ReferenceProblem("reference-collection-dependency-invalid")
            if revision_id == collection.collection_revision_id:
                # _append's payload fingerprint uses the actual protected UTF-8
                # object bytes, whose digest is independently authenticated above.
                root = aggregates.get_revision(revision_id)
                if params.get("scholarly.reference-collection") != (
                    "1.0.0",
                    "sha256:" + root.object_sha256,
                ) or params.get("scholarly.reference-ranking") != ("1.0.0", "sha256:" + DEFAULT_CONFIG.fingerprint):
                    raise ReferenceProblem("reference-collection-dependency-invalid")
        if leaves != expected:
            raise ReferenceProblem("reference-collection-dependency-invalid")
        self.matching.reconciliation._require_fresh_inputs(aggregates, tuple(visited | leaves))

    def read(self, document_revision_id, *, cancelled: Callable[[], bool] = lambda: False):
        def read():
            source = self._source(document_revision_id)

            def current(connection, actor):
                accepted, entries, inputs, snapshot, _ = self._prepare(
                    connection, actor, document_revision_id, cancelled
                )
                head = self._head(connection, document_revision_id)
                if head is None:
                    return None
                collection = self._record(connection, head[0])
                matched = match_reference_entries(entries, snapshot.works, snapshot.assessments, cancelled=cancelled)
                if (
                    collection.document_revision_id,
                    collection.content_sha256,
                    collection.structure_sha256,
                    collection.intent_sha256,
                    collection.policy_sha256,
                    collection.catalog_sha256,
                    collection.entries,
                ) != (
                    accepted.revision_id,
                    accepted.content_sha256,
                    accepted.structure_sha256,
                    actor.intent_sha256,
                    actor.policy_sha256,
                    snapshot.sha256,
                    matched,
                ):
                    raise ReferenceProblem("reference-collection-requires-review")
                with self.revisions._aggregates(connection) as aggregates:
                    expected = set(snapshot.input_revision_ids) | {i.revision_id for i in inputs}
                    self._validate_inputs(connection, aggregates, collection, expected)
                self._check(cancelled)
                return collection

            return self.anchors._fenced(source, current)

        return self._bounded(read)

    def enrich(self, command, *, cancelled: Callable[[], bool] = lambda: False):
        def enrich():
            selected = ReferenceEnrichmentCommand.model_validate(command)
            source = self._source(selected.revision_id)
            actor = self.anchors._current_actor()
            digest = self._command_digest(selected, actor, self.revisions.project)
            accepted, entries, document_inputs, snapshot, prepared = self.anchors._fenced(
                source,
                lambda c, a: self._prepare(c, a, selected.revision_id, cancelled),
            )
            matched = match_reference_entries(entries, snapshot.works, snapshot.assessments, cancelled=cancelled)

            def build(connection, current_actor):
                self._check(cancelled)
                if current_actor != actor:
                    raise ReferenceProblem("reference-authority-changed")
                existing = connection.execute(
                    "SELECT revision_id,command_sha256 FROM document_enrichments WHERE project_id=? AND command_id=?",
                    (self.revisions.project, selected.command_id),
                ).fetchone()
                if existing:
                    if existing[1] != digest:
                        raise ReferenceProblem("reference-command-reuse-conflict")
                    return self._record(connection, existing[0])
                head = self._head(connection, selected.revision_id)
                if (head[0] if head else None) != selected.expected_collection_revision_id:
                    raise ReferenceProblem("reference-collection-predecessor-changed")
                return ReferenceCollection(
                    project_id=self.revisions.project,
                    collection_id=head[1] if head else new_uuid_v7(),
                    collection_revision_id=new_uuid_v7(),
                    previous_collection_revision_id=selected.expected_collection_revision_id,
                    document_revision_id=accepted.revision_id,
                    content_sha256=accepted.content_sha256,
                    structure_sha256=accepted.structure_sha256,
                    command_id=selected.command_id,
                    command_sha256=digest,
                    actor_id=actor.actor_id,
                    intent_sha256=actor.intent_sha256,
                    policy_sha256=actor.policy_sha256,
                    extracted_at=actor.occurred_at,
                    catalog_sha256=snapshot.sha256,
                    entries=matched,
                )

            collection = self.anchors._fenced(source, build)
            if (collection.catalog_sha256, collection.entries, collection.intent_sha256, collection.policy_sha256) != (
                snapshot.sha256,
                matched,
                actor.intent_sha256,
                actor.policy_sha256,
            ):
                raise ReferenceProblem("reference-collection-requires-review")
            _publication_step("reference-prepared")
            raw = protected_json(collection)
            self.admit(len(raw))

            def publish(connection, stored):
                self._check(cancelled)
                self.revisions._authority(connection, self.anchors._current_actor())
                if self.revisions._accepted(connection, selected.revision_id) != accepted:
                    raise ReferenceProblem("reference-document-changed")
                with self.revisions._aggregates(connection) as aggregates:
                    current_snapshot = self.matching.snapshot(
                        connection, aggregates, entries, resolve=self._cached(prepared), cancelled=cancelled
                    )
                    if current_snapshot != snapshot:
                        raise ReferenceProblem("reference-catalog-changed")
                    existing = connection.execute(
                        (
                            "SELECT revision_id,command_sha256 FROM document_enrichments WHERE "
                            "project_id=? AND command_id=?"
                        ),
                        (self.revisions.project, selected.command_id),
                    ).fetchone()
                    if existing:
                        if tuple(existing) != (collection.collection_revision_id, digest):
                            raise ReferenceProblem("reference-command-reuse-conflict")
                        recorded = self._record(connection, existing[0])
                        if recorded != collection:
                            raise ReferenceProblem("reference-collection-binding-invalid")
                        self._validate_inputs(
                            connection,
                            aggregates,
                            collection,
                            set(snapshot.input_revision_ids) | {i.revision_id for i in document_inputs},
                        )
                        return collection
                    head = self._head(connection, selected.revision_id)
                    if (head[0] if head else None) != selected.expected_collection_revision_id:
                        raise ReferenceProblem("reference-collection-predecessor-changed")
                    material = {i.revision_id: i for i in document_inputs}
                    material.update((r, aggregates.get_revision(r)) for r in snapshot.input_revision_ids)
                    reconciler = self.matching.reconciliation
                    revision = reconciler._append(
                        aggregates,
                        sources=tuple(material[k] for k in sorted(material)),
                        actor=ReconciliationActor(
                            actor.actor_id, actor.trace_id, actor.occurred_at, actor.intent_sha256, actor.policy_sha256
                        ),
                        digest=stored.object_sha256,
                        label="Document reference collection",
                        kind="document",
                        current=aggregates.get_revision(head[0]) if head else None,
                        revision_id=collection.collection_revision_id,
                        aggregate_id=collection.collection_id,
                        object_sha256=stored.object_sha256,
                        event_type=REFERENCE_EVENT,
                        idempotency_key="document.references." + selected.command_id,
                        payload_configuration="reference-collection",
                        extra_parameter=("reference-ranking", "1.0.0", DEFAULT_CONFIG.fingerprint),
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
                            "references",
                            collection.previous_collection_revision_id,
                            collection.command_id,
                            digest,
                            actor.actor_id,
                            stored.object_sha256,
                        ),
                    )
                    elements, identifiers, targets = self._index_rows(collection)
                    for table, rows, count in (
                        ("document_enrichment_elements", elements, 6),
                        ("document_enrichment_identifiers", identifiers, 6),
                        ("document_enrichment_targets", targets, 8),
                    ):
                        for row in rows:
                            connection.execute(
                                f"INSERT INTO {table} VALUES ({','.join('?' for _ in range(count))})", row
                            )
                    if head:
                        # Refresh preserves the old collection and atomically
                        # announces its replacement to existing dependants.
                        previous = aggregates.get_revision(head[0])
                        reconciler._publish_impacts(
                            connection,
                            (
                                reconciler._change(
                                    previous,
                                    revision,
                                    ReconciliationActor(
                                        actor.actor_id,
                                        actor.trace_id,
                                        actor.occurred_at,
                                        actor.intent_sha256,
                                        actor.policy_sha256,
                                    ),
                                    human=False,
                                ),
                            ),
                        )
                    _publication_step("reference-before-commit")
                    self._check(cancelled)
                    return collection

            result = self.revisions._put(raw, REFERENCE_COLLECTION_MEDIA, source, publish, cancelled)
            self._check(cancelled)
            return result

        return self._bounded(enrich)
