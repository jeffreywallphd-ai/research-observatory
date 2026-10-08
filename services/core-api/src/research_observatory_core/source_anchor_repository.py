"""Existing canonical Document aggregates retain immutable protected anchors."""

from __future__ import annotations

import hashlib
from contextlib import closing
from dataclasses import asdict, dataclass

from pydantic import Field, ValidationError, model_validator

from .anchors.contracts import (
    ANCHOR_MEDIA_TYPE,
    MAX_ANCHOR_BYTES,
    MAX_QUOTE_CODEPOINTS,
    AnchorSelection,
    AnchorStalePropagation,
    CitationLinkResolution,
    CitationReferenceTarget,
    DocumentReaderOutline,
    DocumentReaderRevisions,
    ReaderOutlineNode,
    ReaderRevisionSummary,
    SourceAnchorReceipt,
    SourceAnchorResolution,
    SourceAnchorTarget,
    SourceDocumentMetadata,
    build_target,
)
from .document_revisions import DocumentRevisionProblem, protected_json
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .parsing.contracts import CodepointRange, IRValue
from .ports.object_store import ObjectCorrupt, ObjectNotFound
from .ports.repositories import (
    DEFAULT_DEPENDENCY_IMPACT_LIMITS,
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    DependencyChange,
    MaterialDependency,
)
from .repositories import (
    _command_fingerprint,
    _material_registration_with_connection,
    _projection_content_sha256,
    _SqliteDependencyImpactRepository,
)
from .storage import open_canonical_database


def _publication_step(_step: str) -> None:
    """Deterministic precommit interruption seam; no external I/O."""


class StoredSourceAnchor(IRValue):
    # Persistence envelope; native responses expose only the public target/IDs.
    anchor_id: str
    anchor_revision_id: str
    command_id: str
    command_sha256: str
    source_revision: AggregateRevision = Field(repr=False)
    event: AtomicRepositoryEvent
    dependency: MaterialDependency
    target: SourceAnchorTarget = Field(repr=False)

    @model_validator(mode="after")
    def identity_binding(self):
        if (
            not all(is_uuid_v7(value) for value in (self.anchor_id, self.anchor_revision_id, self.command_id))
            or self.anchor_id == self.anchor_revision_id
            or (self.source_revision.project_id, self.source_revision.aggregate_id, self.source_revision.revision_id)
            != (self.target.project_id, self.target.document_id, self.target.revision_id)
            or self.source_revision.aggregate_kind != "document"
            or self.event.event_type != "org.research-observatory.document.revision-recorded.v1"
            or self.event.actor_type != "human"
            or self.event.idempotency_key != "document.anchor." + self.command_id
            or self.dependency.revision_id != self.target.revision_id
            or self.dependency.dependency_kind != "source-revision"
            or self.dependency.relation_type != "direct"
        ):
            raise ValueError("anchor-persistence-binding-invalid")
        return self


@dataclass(frozen=True, slots=True)
class _Receipt:
    object_sha256: str
    byte_length: int


class LocalSourceAnchorRepository:
    def __init__(self, revisions):
        self.revisions = revisions
        self.principal = self._principal(revisions.actor())

    @staticmethod
    def _principal(actor):
        return (actor.actor_id, actor.actor_type, actor.intent_revision_id, actor.intent_sha256, actor.policy_sha256)

    def _current_actor(self):
        actor = self.revisions.actor()
        if actor.actor_type != "human" or self._principal(actor) != self.principal:
            raise DocumentRevisionProblem("source-anchor-authority-changed")
        return actor

    def _bounded(self, action):
        try:
            self._current_actor()
            return self.revisions._bounded(action)
        except Exception:
            raise DocumentRevisionProblem("source-anchor-denied") from None

    @staticmethod
    def receipt(record):
        return SourceAnchorReceipt(
            anchor_id=record.anchor_id,
            anchor_revision_id=record.anchor_revision_id,
            created_at=record.event.occurred_at,
            target=record.target,
        )

    def _source(self, connection, revision_id):
        row = connection.execute(
            "SELECT result_id FROM document_normalized_revisions WHERE project_id=? AND revision_id=?",
            (self.revisions.project, revision_id),
        ).fetchone()
        if row is None:
            raise DocumentRevisionProblem("source-anchor-revision-unavailable")
        return self.revisions._receipt(connection, row[0]).binding.source

    def _fenced(self, source, action):
        actor = self._current_actor()

        def current(connection):
            self.revisions._authority(connection, actor)
            result = action(connection, actor)
            # The enclosing native-session guard remains held through delivery.
            self.revisions._authority(connection, self._current_actor())
            return result

        return self.revisions.objects._read_authorized_document_context(source, actor=actor, action=current)

    def _fenced_resolved(self, anchor_id, revision_id, resolve_source, action):
        actor = self._current_actor()

        def current(connection, source):
            self.revisions._authority(connection, actor)
            result = action(connection, actor, source)
            self.revisions._authority(connection, self._current_actor())
            return result

        return self.revisions.objects._read_resolved_authorized_document_context(
            anchor_id, revision_id, actor=actor, resolve_source=resolve_source, action=current
        )

    def _target_revision(self, connection, anchor_revision_id):
        rows = connection.execute(
            "SELECT dependency_revision_id FROM material_dependencies WHERE project_id=? "
            "AND output_revision_id=? AND dependency_kind='source-revision' AND relation_type='direct'",
            (self.revisions.project, anchor_revision_id),
        ).fetchall()
        if len(rows) != 1:
            raise DocumentRevisionProblem("source-anchor-dependency-invalid")
        return str(rows[0][0])

    @staticmethod
    def _draft(record, digest):
        now = record.event.occurred_at
        return AggregateRevisionDraft(
            revision_id=record.anchor_revision_id,
            aggregate_id=record.anchor_id,
            aggregate_kind="document",
            created_at=now,
            modified_at=now,
            display_label_observed="Source passage anchor",
            display_label_normalized="source passage anchor",
            knowledge_status="extracted",
            rights_status="allowed",
            dependency_coverage="complete",
            object_sha256=digest,
            provenance_inputs=(record.source_revision,),
            material_dependencies=(record.dependency,),
        )

    def _record(self, connection, anchor_id):
        with self.revisions._aggregates(connection) as aggregates:
            revision = aggregates.get(anchor_id)
            metadata = connection.execute(
                "SELECT byte_length FROM object_records WHERE project_id=? AND object_sha256=?",
                (self.revisions.project, revision.object_sha256),
            ).fetchone()
            if revision.aggregate_kind != "document" or metadata is None or not 0 < metadata[0] <= MAX_ANCHOR_BYTES:
                raise DocumentRevisionProblem("source-anchor-unavailable")
            raw = self.revisions.objects._read_protected_document_artifact(
                connection,
                _Receipt(revision.object_sha256, metadata[0]),
                ANCHOR_MEDIA_TYPE,
            )
            record = StoredSourceAnchor.model_validate_json(raw)
            if (
                record.anchor_id != anchor_id
                or record.anchor_revision_id != revision.revision_id
                or revision.revision != 0
                or revision.aggregate_kind != "document"
                or (revision.created_at, revision.modified_at) != (record.event.occurred_at, record.event.occurred_at)
                or revision.knowledge_status != "extracted"
                or revision.rights_status != "allowed"
                or record.target.project_id != self.revisions.project
                or aggregates.get_revision(record.target.revision_id) != record.source_revision
                or self._source(connection, record.target.revision_id) != record.target.source
            ):
                raise DocumentRevisionProblem("source-anchor-binding-invalid")
            source = connection.execute(
                "SELECT content_sha256,structure_sha256 FROM document_normalized_revisions "
                "WHERE project_id=? AND revision_id=?",
                (self.revisions.project, record.target.revision_id),
            ).fetchone()
            identities = connection.execute(
                "SELECT element_id,role,node_kind FROM document_structure_elements "
                "WHERE project_id=? AND revision_id=? AND element_id IN (?,?)",
                (self.revisions.project, record.target.revision_id, record.target.node_id, record.target.projection_id),
            ).fetchall()
            expected: set[tuple[str, str, str | None]] = {(record.target.node_id, "node", record.target.node_kind)}
            if record.target.projection_id is not None:
                expected.add((record.target.projection_id, "projection", None))
            if (
                source is None
                or tuple(source) != (record.target.content_sha256, record.target.structure_sha256)
                or {tuple(row) for row in identities} != expected
            ):
                raise DocumentRevisionProblem("source-anchor-structure-invalid")
            draft = self._draft(record, revision.object_sha256)
            fingerprint = _command_fingerprint(
                self.revisions.project,
                revision,
                record.event,
                None,
                draft.provenance_inputs,
                draft.dependency_coverage,
                draft.material_dependencies,
            )
            if aggregates._replay(record.event, fingerprint) != revision:
                raise DocumentRevisionProblem("source-anchor-provenance-invalid")
            registration = _material_registration_with_connection(
                connection, self.revisions.project, revision.revision_id
            )
            if (
                registration.coverage != "complete"
                or registration.dependencies != (record.dependency,)
                or registration.registration_event_id != record.event.event_id
            ):
                raise DocumentRevisionProblem("source-anchor-dependency-invalid")
            return record

    def read(self, anchor_id):
        return self.receipt(self._read_record(anchor_id))

    def create(self, command_id, selection):
        return self.receipt(self._create_record(command_id, selection))

    @staticmethod
    def _metadata(revision):
        return SourceDocumentMetadata(
            project_id=revision.project_id,
            document_id=revision.aggregate_id,
            revision_id=revision.revision_id,
            accepted_at=revision.modified_at,
            display_label=revision.display_label_observed,
        )

    def _event_for_key(self, connection, key):
        rows = connection.execute(
            "SELECT p.event_id,o.outbox_id,p.event_type,p.occurred_at,o.available_at,"
            "p.trace_id,p.actor_type,p.actor_id,o.idempotency_key FROM outbox_events o "
            "JOIN provenance_events p ON p.project_id=o.project_id AND p.revision_id=o.revision_id "
            "AND p.record_sha256=o.record_sha256 WHERE o.project_id=? AND o.idempotency_key=?",
            (self.revisions.project, key),
        ).fetchall()
        if len(rows) != 1:
            raise DocumentRevisionProblem("source-anchor-provenance-invalid")
        return AtomicRepositoryEvent(*tuple(rows[0]))

    def _canonical_anchor(self, connection, anchor_id):
        """Authenticate identity/derivation independently of unreadable payload bytes."""
        with self.revisions._aggregates(connection) as aggregates:
            revision = aggregates.get(anchor_id)
            registration = _material_registration_with_connection(
                connection, self.revisions.project, revision.revision_id
            )
            if (
                revision.aggregate_kind != "document"
                or revision.revision != 0
                or revision.knowledge_status != "extracted"
                or revision.rights_status != "allowed"
                or registration.coverage != "complete"
                or len(registration.dependencies) != 1
            ):
                raise DocumentRevisionProblem("source-anchor-binding-invalid")
            dependency = registration.dependencies[0]
            if dependency.dependency_kind != "source-revision" or dependency.relation_type != "direct":
                raise DocumentRevisionProblem("source-anchor-dependency-invalid")
            source_revision = aggregates.get_revision(dependency.revision_id)
            source = self._source(connection, source_revision.revision_id)
            row = connection.execute(
                "SELECT idempotency_key FROM outbox_events WHERE project_id=? AND revision_id=? "
                "AND event_type='org.research-observatory.document.revision-recorded.v1'",
                (self.revisions.project, revision.revision_id),
            ).fetchall()
            if len(row) != 1 or not str(row[0][0]).startswith("document.anchor."):
                raise DocumentRevisionProblem("source-anchor-provenance-invalid")
            event = self._event_for_key(connection, str(row[0][0]))
            if (
                not is_uuid_v7(event.idempotency_key.removeprefix("document.anchor."))
                or event.actor_type != "human"
                or (revision.created_at, revision.modified_at) != (event.occurred_at, event.occurred_at)
                or source_revision.aggregate_kind != "document"
                or source_revision.aggregate_id != source.document_id
                or dependency.fingerprint != _projection_content_sha256(source_revision)
                or registration.registration_event_id != event.event_id
            ):
                raise DocumentRevisionProblem("source-anchor-provenance-invalid")
            fingerprint = _command_fingerprint(
                self.revisions.project,
                revision,
                event,
                None,
                (source_revision,),
                "complete",
                (dependency,),
            )
            if aggregates._replay(event, fingerprint) != revision:
                raise DocumentRevisionProblem("source-anchor-provenance-invalid")
            return revision, source_revision, source

    def _invalidate_broken(self, connection, revision):
        key = "document.anchor-broken." + revision.revision_id
        impacts = _SqliteDependencyImpactRepository(self.revisions.database, self.revisions.project)
        existing = connection.execute(
            "SELECT run_id,change_id FROM dependency_impact_runs WHERE project_id=? AND idempotency_key=?",
            (self.revisions.project, key),
        ).fetchone()
        if existing is None:
            actor = self._current_actor()
            event = self.revisions._event(
                actor, self.revisions.now(), "org.research-observatory.document.invalidated.v1", key
            )
            change = DependencyChange(
                change_id=event.event_id,
                idempotency_key=key,
                reason="SOURCE_VERSION",
                dependency_kind="source-revision",
                previous_revision_id=revision.revision_id,
                replacement_revision_id=None,
                configuration_id=None,
                previous_configuration_version=None,
                replacement_configuration_version=None,
                previous_fingerprint=_projection_content_sha256(revision),
                replacement_fingerprint=None,
                propagation_policy_id="dependency.material.v1",
                propagation_policy_version="1.0.0",
                actor_id=event.actor_id,
                trace_id=event.trace_id,
                occurred_at=event.occurred_at,
            )
            with self.revisions._aggregates(connection) as aggregates:
                aggregates.invalidate(revision.revision_id, event)
            preview = impacts._preview_with_connection(
                connection, change, decisions=(), limits=DEFAULT_DEPENDENCY_IMPACT_LIMITS
            )
            run = impacts._begin_with_connection(
                connection,
                change,
                preview_sha256=preview.preview_sha256,
                run_id=new_uuid_v7(),
                batch_size=1000,
            )
        else:
            event = self._event_for_key(connection, key)
            with self.revisions._aggregates(connection) as aggregates:
                aggregates.invalidate(revision.revision_id, event)
            change = impacts._change_with_connection(connection, str(existing[1]))
            if (change.change_id, change.previous_revision_id) != (event.event_id, revision.revision_id):
                raise DocumentRevisionProblem("source-anchor-invalidation-conflict")
            run = impacts._run_with_connection(connection, str(existing[0]))
        while run.state == "running":
            self.revisions._authority(connection, self._current_actor())
            run = impacts._advance_with_connection(
                connection, run.run_id, expected_checkpoint_sha256=run.checkpoint_sha256
            )
        if run.state != "completed":
            raise DocumentRevisionProblem("source-anchor-invalidation-incomplete")
        _publication_step("anchor-dependents-stale")
        return AnchorStalePropagation(
            run_id=run.run_id,
            state=run.state,
            total_items=run.total_items,
            processed_items=run.processed_items,
            stale_count=run.stale_count,
            unknown_count=run.unknown_count,
        )

    def resolve(self, anchor_id, *, expected_revision_id):
        if not is_uuid_v7(anchor_id) or not is_uuid_v7(expected_revision_id):
            raise DocumentRevisionProblem("source-anchor-resolution-invalid")

        def read():
            def resolve_source(db):
                with self.revisions._aggregates(db) as aggregates:
                    revision = aggregates.get(anchor_id)
                target_revision_id = self._target_revision(db, revision.revision_id)
                if target_revision_id != expected_revision_id:
                    raise DocumentRevisionProblem("source-anchor-revision-mismatch")
                return self._source(db, target_revision_id)

            def selected(connection, _actor, source):
                try:
                    record = self._record(connection, anchor_id)
                except ObjectCorrupt, ObjectNotFound, OSError, ValidationError:
                    record = None
                except DocumentRevisionProblem as error:
                    if error.code != "source-anchor-structure-invalid":
                        raise
                    record = None
                if record is None:
                    canonical, source_revision, confirmed_source = self._canonical_anchor(connection, anchor_id)
                    if confirmed_source != source or source_revision.revision_id != expected_revision_id:
                        raise DocumentRevisionProblem("source-anchor-revision-mismatch")
                    return SourceAnchorResolution(
                        anchor_id=anchor_id,
                        anchor_revision_id=canonical.revision_id,
                        source=source,
                        metadata=self._metadata(source_revision),
                        status="broken",
                        selector_used="not-resolved",
                        reason="protected-context-unavailable",
                        target=None,
                        propagation=self._invalidate_broken(connection, canonical),
                    )
                target = record.target
                missing = target.context is None
                return SourceAnchorResolution(
                    anchor_id=record.anchor_id,
                    anchor_revision_id=record.anchor_revision_id,
                    source=target.source,
                    metadata=self._metadata(record.source_revision),
                    status="missing" if missing else "exact" if target.page_region is not None else "fallback",
                    selector_used="not-resolved"
                    if missing
                    else "page-region"
                    if target.page_region is not None
                    else "structural-text",
                    reason="readable-text-not-reported" if missing else None,
                    target=None if missing else target,
                    propagation=None,
                )

            return self._fenced_resolved(anchor_id, expected_revision_id, resolve_source, selected)

        return self._bounded(read)

    def citation_links(self, revision_id, citation_id, *, after_reference_id=None, limit=2):
        if (
            not is_uuid_v7(revision_id)
            or not is_uuid_v7(citation_id)
            or type(limit) is not int
            or not 1 <= limit <= 2
            or (after_reference_id is not None and not is_uuid_v7(after_reference_id))
        ):
            raise DocumentRevisionProblem("citation-link-request-invalid")

        def read():
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as db:
                source = self._source(db, revision_id)

            def selected(connection, _actor):
                accepted = self.revisions._accepted(connection, revision_id)
                citation = next((row for row in accepted.structure.citations if row.citation_id == citation_id), None)
                if citation is None:
                    raise DocumentRevisionProblem("citation-link-unavailable")

                def target(node_id, span):
                    return build_target(
                        accepted,
                        AnchorSelection(
                            revision_id=revision_id,
                            node_id=node_id,
                            normalized_range=CodepointRange(
                                start=span.start, end=min(span.end, span.start + MAX_QUOTE_CODEPOINTS)
                            ),
                        ),
                    )

                candidates = citation.reference_candidates
                start = 0
                if after_reference_id is not None:
                    if after_reference_id not in candidates:
                        raise DocumentRevisionProblem("citation-link-cursor-invalid")
                    start = candidates.index(after_reference_id) + 1
                by_id = {row.reference_id: row for row in accepted.structure.references}
                targets = tuple(
                    CitationReferenceTarget(
                        reference_id=reference_id,
                        target=target(by_id[reference_id].node_id, by_id[reference_id].raw_text.normalized_range),
                        preview_truncated=by_id[reference_id].raw_text.normalized_range.end
                        - by_id[reference_id].raw_text.normalized_range.start
                        > MAX_QUOTE_CODEPOINTS,
                    )
                    for reference_id in candidates[start : start + limit]
                )
                with self.revisions._aggregates(connection) as aggregates:
                    source_revision = aggregates.get_revision(revision_id)
                result = CitationLinkResolution(
                    citation_id=citation_id,
                    source=source,
                    metadata=self._metadata(source_revision),
                    marker=target(citation.node_id, citation.marker.normalized_range),
                    marker_truncated=citation.marker.normalized_range.end - citation.marker.normalized_range.start
                    > MAX_QUOTE_CODEPOINTS,
                    resolution=citation.resolution,
                    total_candidates=len(candidates),
                    targets=targets,
                    next_reference_id=targets[-1].reference_id if targets and start + limit < len(candidates) else None,
                )
                if len(protected_json(result)) > 128 * 1024:
                    raise DocumentRevisionProblem("citation-link-response-limit")
                return result

            return self._fenced(source, selected)

        return self._bounded(read)

    def _read_record(self, anchor_id):
        if not is_uuid_v7(anchor_id):
            raise DocumentRevisionProblem("source-anchor-unavailable")

        def read():
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as db:
                with self.revisions._aggregates(db) as aggregates:
                    revision = aggregates.get(anchor_id)
                source = self._source(db, self._target_revision(db, revision.revision_id))
            return self._fenced(source, lambda connection, _actor: self._record(connection, anchor_id))

        return self._bounded(read)

    def _create_record(self, command_id, selection):
        if not is_uuid_v7(command_id):
            raise DocumentRevisionProblem("source-anchor-command-invalid")

        def create():
            command = AnchorSelection.model_validate(selection)
            semantic = hashlib.sha256(protected_json(command)).hexdigest()
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as db:
                previous = db.execute(
                    "SELECT r.aggregate_id FROM outbox_events e JOIN aggregate_revisions r "
                    "ON r.project_id=e.project_id AND r.revision_id=e.revision_id "
                    "WHERE e.project_id=? AND e.idempotency_key=?",
                    (self.revisions.project, "document.anchor." + command_id),
                ).fetchone()
            if previous is not None:
                record = self._read_record(str(previous[0]))
                if record.command_sha256 != semantic or record.event.actor_id != self._current_actor().actor_id:
                    raise DocumentRevisionProblem("source-anchor-command-conflict")
                return record
            accepted = self.revisions.read(command.revision_id)
            target = build_target(accepted, command)
            with (
                closing(
                    open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
                ) as db,
                self.revisions._aggregates(db) as aggregates,
            ):
                source_revision = aggregates.get_revision(command.revision_id)
            event = self.revisions._event(
                self._current_actor(),
                self.revisions.now(),
                "org.research-observatory.document.revision-recorded.v1",
                "document.anchor." + command_id,
            )
            record = StoredSourceAnchor.model_validate(
                {
                    "anchorId": new_uuid_v7(),
                    "anchorRevisionId": new_uuid_v7(),
                    "commandId": command_id,
                    "commandSha256": semantic,
                    "sourceRevision": asdict(source_revision),
                    "event": asdict(event),
                    "dependency": asdict(self.revisions._dependencies((source_revision,))[0]),
                    "target": target.model_dump(mode="json", by_alias=True),
                }
            )
            raw = protected_json(record)
            if len(raw) > MAX_ANCHOR_BYTES:
                raise DocumentRevisionProblem("source-anchor-oversize")

            def publish(connection, stored):
                actor = self._current_actor()
                self.revisions._authority(connection, actor)
                if (
                    actor.actor_id != record.event.actor_id
                    or self._source(connection, target.revision_id) != target.source
                ):
                    raise DocumentRevisionProblem("source-anchor-authority-changed")
                with self.revisions._aggregates(connection) as aggregates:
                    if aggregates.get_revision(target.revision_id) != record.source_revision:
                        raise DocumentRevisionProblem("source-anchor-revision-changed")
                    aggregates.append(self._draft(record, stored.object_sha256), record.event, expected_revision=None)
                    _publication_step("anchor-recorded")
                return record

            return self.revisions._put(raw, ANCHOR_MEDIA_TYPE, target.source, publish, lambda: False)

        return self._bounded(create)

    def list(self, revision_id, *, limit=100, after_id=None):
        if not is_uuid_v7(revision_id) or type(limit) is not int or not 1 <= limit <= 100:
            raise DocumentRevisionProblem("source-anchor-list-invalid")
        if after_id is not None and not is_uuid_v7(after_id):
            raise DocumentRevisionProblem("source-anchor-list-invalid")

        def read():
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as db:
                source = self._source(db, revision_id)

            def selected(connection, _actor):
                rows = connection.execute(
                    "SELECT r.aggregate_id FROM material_dependencies m JOIN aggregate_revisions r "
                    "ON r.project_id=m.project_id AND r.revision_id=m.output_revision_id "
                    "JOIN documents d ON d.project_id=r.project_id AND d.revision_id=r.revision_id "
                    "JOIN object_records o ON o.project_id=d.project_id AND o.object_sha256=d.object_sha256 "
                    "WHERE m.project_id=? AND m.dependency_revision_id=? AND m.dependency_kind='source-revision' "
                    "AND o.media_type=? AND r.aggregate_id>? ORDER BY r.aggregate_id LIMIT ?",
                    (self.revisions.project, revision_id, ANCHOR_MEDIA_TYPE, after_id or "", limit),
                ).fetchall()
                return tuple(self._record(connection, str(row[0])).anchor_id for row in rows)

            return self._fenced(source, selected)

        return self._bounded(read)

    def outline(self, revision_id, *, after_node_id=None, limit=50):
        if (
            not is_uuid_v7(revision_id)
            or type(limit) is not int
            or not 1 <= limit <= 50
            or (after_node_id is not None and not is_uuid_v7(after_node_id))
        ):
            raise DocumentRevisionProblem("source-anchor-outline-invalid")

        def read():
            with closing(
                open_canonical_database(self.revisions.database, expected_project_id=self.revisions.project)
            ) as db:
                source = self._source(db, revision_id)

            def selected(connection, _actor):
                accepted = self.revisions._accepted(connection, revision_id)
                nodes = accepted.structure.nodes
                start = 0
                if after_node_id is not None:
                    indices = [index for index, node in enumerate(nodes) if node.node_id == after_node_id]
                    if len(indices) != 1:
                        raise DocumentRevisionProblem("source-anchor-outline-cursor-invalid")
                    start = indices[0] + 1
                projections = {item.projection_id: item for item in accepted.structure.text_projections}
                items = []
                for node in nodes[start : start + limit]:
                    span = None
                    preview = ""
                    if node.text is not None and node.text.normalized_range.start < node.text.normalized_range.end:
                        span = CodepointRange(
                            start=node.text.normalized_range.start,
                            end=min(
                                node.text.normalized_range.end, node.text.normalized_range.start + MAX_QUOTE_CODEPOINTS
                            ),
                        )
                        preview = projections[node.text.projection_id].normalized_text[span.start : span.end][:160]
                    items.append(
                        ReaderOutlineNode(
                            node_id=node.node_id,
                            node_kind=node.kind,
                            preview=preview,
                            selection=AnchorSelection(
                                revision_id=revision_id, node_id=node.node_id, normalized_range=span
                            ),
                            page_number=node.locator.page_index + 1 if node.locator.kind == "page-region" else None,
                            has_text=span is not None,
                        )
                    )
                return DocumentReaderOutline(
                    project_id=self.revisions.project,
                    document_id=accepted.document_id,
                    revision_id=revision_id,
                    source=source,
                    nodes=tuple(items),
                    next_node_id=items[-1].node_id if items and start + limit < len(nodes) else None,
                )

            return self._fenced(source, selected)

        return self._bounded(read)

    def reader_revisions(self, attachment_id):
        if not is_uuid_v7(attachment_id):
            raise DocumentRevisionProblem("source-anchor-attachment-invalid")

        def read():
            source = self.revisions.source(attachment_id)

            def selected(connection, _actor):
                rows = connection.execute(
                    "SELECT r.revision_id,r.accepted_at FROM document_normalized_revisions r "
                    "JOIN document_parse_results p ON p.project_id=r.project_id AND p.result_id=r.result_id "
                    "JOIN document_parse_jobs j ON j.project_id=p.project_id AND j.job_id=p.job_id "
                    "WHERE r.project_id=? AND r.document_id=? AND j.source_revision_id=? "
                    "ORDER BY r.accepted_at DESC,r.revision_id DESC LIMIT 100",
                    (self.revisions.project, source.document_id, source.document_revision_id),
                ).fetchall()
                return DocumentReaderRevisions(
                    source=source,
                    revisions=tuple(ReaderRevisionSummary(revision_id=row[0], accepted_at=row[1]) for row in rows),
                )

            return self._fenced(source, selected)

        return self._bounded(read)
