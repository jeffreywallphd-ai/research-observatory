"""Current canonical metadata and accepted-IR projection for local search only."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field

from .document_revision_repository import LocalDocumentRevisionRepository
from .domain_contracts import is_uuid_v7
from .lexical_catalog_repository import actor_context_sha256
from .lexical_index_store import IndexRow
from .lexical_input_repository import lexical_watermark
from .parsing.normalization import MAX_IR_BYTES
from .parsing.source import source_identity
from .ports.reconciliation import ReconciliationSourceResolver
from .reconciliation.contracts import SourceAssertion
from .reconciliation.exact import SourceOrigin, select_field
from .reconciliation_repository import SqliteReconciliationRepository
from .rights_policy import RightsRequest, RightsSubject, RightsUse
from .rights_repository import SqliteRightsRepository
from .storage import CanonicalConnection, open_canonical_database

_FIELDS = {"title", "abstract", "authors", "venue", "tags", "year"}
_MAX_ITEM_TEXT_BYTES = 128 * 1024 * 1024


class IndexSourceProblem(RuntimeError):
    """Current source authority cannot be established; no cached grant fallback."""


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _text_ranges(text: str, start: int, end: int, *, cancelled: Callable[[], bool] = lambda: False):
    """One accepted projection preserves the actual FTS analyzer's adjacency.

    Source-codepoint overlap cannot bound analyzed-token distance: punctuation
    or discarded marks may separate two adjacent tokens by arbitrary source
    distance. The accepted IR's existing byte bound caps this atomic FTS unit.
    """
    if cancelled() is not False or start != 0 or end != len(text):
        raise IndexSourceProblem("index projection range is invalid or stopped")
    if len(text.encode("utf-8")) > MAX_IR_BYTES:
        raise IndexSourceProblem("index projection byte budget exceeded")
    if text:
        yield start, end


@dataclass(frozen=True, slots=True)
class ItemIndexProjection:
    item_id: str
    item_revision_id: str
    watermark: int
    authority_sha256: str
    expires_at: str | None
    rows: tuple[IndexRow, ...] = field(repr=False)
    _sources: tuple[SourceAssertion, ...] = field(repr=False)
    _metadata_sha256: str = field(repr=False)
    _document_revisions: tuple[str, ...] = field(repr=False)


class CanonicalIndexSources:
    def __init__(self, documents: LocalDocumentRevisionRepository, *, resolve: ReconciliationSourceResolver) -> None:
        self.documents = documents
        self.database, self.project = documents.database, documents.project
        self.corpus = documents.corpus
        self.reconciliation = SqliteReconciliationRepository(self.database, self.project)
        self.rights = SqliteRightsRepository(self.database, self.project)
        self.resolve = resolve

    def _bounded(self, action):
        try:
            return self.documents.guard(action)
        except IndexSourceProblem:
            raise
        except Exception:
            raise IndexSourceProblem("index sources are unavailable") from None

    def item_ids(self, *, after: str | None = None, limit: int = 256) -> tuple[str, ...]:
        def read():
            if (after is not None and not is_uuid_v7(after)) or type(limit) is not int or not 1 <= limit <= 256:
                raise IndexSourceProblem("index cursor is invalid")
            with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
                self.documents._authority(db, self.documents.actor())
                return tuple(
                    row[0]
                    for row in db.execute(
                        "SELECT DISTINCT item_id FROM corpus_item_states WHERE project_id=? AND (? IS NULL OR "
                        "item_id>?) ORDER BY item_id LIMIT ?",
                        (self.project, after, after, limit),
                    )
                )

        return self._bounded(read)

    def metadata_subject(self, source: SourceAssertion) -> RightsSubject:
        def read():
            with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
                db.execute("BEGIN")
                try:
                    self.documents._authority(db, self.documents.actor())
                    return self.rights.source_metadata_subject_with_connection(db, source)
                finally:
                    db.rollback()

        return self._bounded(read)

    def _permission(self, db, subject, actor):
        witnesses = []
        allowed = True
        expiry = None
        for action in ("inspect", "index"):
            decision = self.rights.evaluate_with_connection(
                db,
                RightsRequest(
                    actor_id=actor.actor_id,
                    subject=subject,
                    use=RightsUse(action=action, purpose="local-search", destination_kind="local-project"),
                ),
                actor=actor,
            )
            allowed = allowed and decision.code == "allow"
            witnesses.append(
                (
                    action,
                    decision.code,
                    decision.authority_kind,
                    decision.policy_revision_id,
                    decision.governing_assertion_ids,
                    decision.source_assertion_sha256,
                    decision.expires_at,
                )
            )
            if decision.expires_at is not None:
                expiry = decision.expires_at if expiry is None else min(expiry, decision.expires_at)
        return allowed, _sha((subject.model_dump(mode="json", by_alias=True), witnesses)), expiry

    def _metadata(self, db, item_id, sources):
        actor = self.documents.actor()
        self.documents._authority(db, actor)
        with self.documents._aggregates(db) as aggregates:
            item, _ = self.corpus._current(db, aggregates, item_id)
            state = self.reconciliation._state(db, item.work_id)
            base = (
                item.model_dump(mode="json", by_alias=True),
                state.fingerprint,
                actor_context_sha256(self.project, actor),
            )
            if (
                item.membership == "withdrawn"
                or state.disposition != "active"
                or state.revision_id != item.work_revision_id
            ):
                return item, (), (), _sha(base), None
            self.corpus._work(db, aggregates, item.work_id, item.work_revision_id)
        by_address = {value.address.model_dump_json(): value for value in sources}
        retained = tuple(
            self.reconciliation._authorized_load(
                db, revision, lambda address: by_address[address.model_dump_json()]
            ).assertion
            for revision in state.assertion_revision_ids
        )
        observations: dict[str, list[tuple[str, str, SourceOrigin]]] = {}
        for source in retained:
            for value in source.fields:
                name = {"author": "authors", "container": "venue"}.get(value.name, value.name)
                if name in _FIELDS:
                    observations.setdefault(name, []).append((source.source_revision_id, value.observed, value.origin))
        selected = {name: select_field(tuple(values)).selected for name, values in observations.items()}
        rows = []
        bindings: list[object] = [base]
        expiry = None
        for source in retained:
            subject = self.rights.source_metadata_subject_with_connection(db, source)
            allowed, authority, expires = self._permission(db, subject, actor)
            bindings.append(
                (subject.source_assertion_revision_id, _sha(source.model_dump(mode="json", by_alias=True)), authority)
            )
            if not allowed:
                continue
            if expires is not None:
                expiry = expires if expiry is None else min(expiry, expires)
            fields = {}
            for value in source.fields:
                name = {"author": "authors", "container": "venue"}.get(value.name, value.name)
                if name in _FIELDS and selected.get(name) == value.observed:
                    fields[name] = value.observed
            year_text = fields.pop("year", None)
            year = (
                int(year_text)
                if isinstance(year_text, str)
                and year_text.isascii()
                and year_text.isdigit()
                and 1 <= int(year_text) <= 9999
                else None
            )
            identifiers = " ".join(sorted({value.observed for value in source.identifiers if value.role == "subject"}))
            rows.append(
                IndexRow(
                    entry_id=_sha(
                        (
                            item.item_id,
                            item.revision_id,
                            item.work_revision_id,
                            subject.source_assertion_revision_id,
                            authority,
                            "metadata",
                        )
                    ),
                    item_id=item.item_id,
                    work_id=item.work_id,
                    work_revision_id=item.work_revision_id,
                    source_revision_id=subject.source_assertion_revision_id,
                    authority_sha256=authority,
                    year=year,
                    identifiers=identifiers,
                    decisions=item.membership + " " + item.review,
                    title=fields.get("title", ""),
                    abstract=fields.get("abstract", ""),
                    authors=fields.get("authors", ""),
                    venue=fields.get("venue", ""),
                    tags=fields.get("tags", ""),
                )
            )
        documents = tuple(
            str(row[0])
            for row in db.execute(
                "SELECT n.revision_id FROM document_normalized_revisions n JOIN aggregate_revisions r ON "
                "r.project_id=n.project_id AND r.revision_id=n.revision_id JOIN document_attachment_assertions a "
                "ON a.project_id=n.project_id AND a.document_id=n.document_id WHERE n.project_id=? AND "
                "a.work_id=? AND a.work_revision_id=? AND NOT EXISTS(SELECT 1 FROM aggregate_revisions newer "
                "WHERE newer.project_id=r.project_id AND newer.aggregate_id=r.aggregate_id AND "
                "newer.revision>r.revision) ORDER BY n.revision_id LIMIT 1001",
                (self.project, item.work_id, item.work_revision_id),
            )
        )
        if len(documents) > 1000:
            raise IndexSourceProblem("index document budget exceeded")
        bindings.append(documents)
        return item, tuple(rows), documents, _sha(bindings), expiry

    def capture(self, item_id: str, *, cancelled: Callable[[], bool] = lambda: False) -> ItemIndexProjection:
        def read():
            if not is_uuid_v7(item_id) or cancelled() is not False:
                raise IndexSourceProblem("index source request stopped")
            with closing(open_canonical_database(self.database, expected_project_id=self.project)) as db:
                self.documents._authority(db, self.documents.actor())
                item = self.corpus._load(db, item_id)
                state = self.reconciliation._state(db, item.work_id)
                addresses = tuple(
                    self.reconciliation._load(db, revision).assertion.address
                    for revision in state.assertion_revision_ids
                )
            resolved = tuple(self.resolve(address) for address in addresses)
            with self.corpus._transaction(write=True) as (db, _aggregates):
                item, rows, revisions, metadata_hash, expiry = self._metadata(db, item_id, resolved)
                watermark = lexical_watermark(db, self.project)
            all_rows = list(rows)
            text_bytes = sum(
                sum(
                    len(value.encode("utf-8"))
                    for value in (
                        row.title,
                        row.abstract,
                        row.authors,
                        row.venue,
                        row.identifiers,
                        row.tags,
                        row.decisions,
                    )
                )
                for row in rows
            )
            doc_bindings: list[tuple[object, ...]] = []
            for revision in revisions:
                if cancelled() is not False:
                    raise IndexSourceProblem("index source request stopped")
                with self.corpus._transaction(write=True) as (db, _aggregates):
                    _source, permitted, _authority, _expires = self._document_context(db, revision)
                if not permitted:
                    doc_bindings.append((revision, "unavailable"))
                    continue
                accepted = self.documents.read_for_index(revision, cancelled=cancelled)
                source = accepted.result.binding.source
                if source.work_id != item.work_id or source.work_revision_id != item.work_revision_id:
                    raise IndexSourceProblem("index document association changed")
                with self.corpus._transaction(write=True) as (db, _aggregates):
                    current, permitted, authority, expires = self._document_context(db, revision)
                    if current != source:
                        raise IndexSourceProblem("index document copy changed")
                if not permitted:
                    doc_bindings.append((revision, "unavailable"))
                    continue
                if expires is not None:
                    expiry = expires if expiry is None else min(expiry, expires)
                doc_bindings.append((revision, accepted.content_sha256, accepted.structure_sha256, authority))
                for row in self._text_rows(item, accepted, authority, cancelled=cancelled):
                    text_bytes += len(row.full_text.encode("utf-8"))
                    if len(all_rows) >= 100_000 or text_bytes > _MAX_ITEM_TEXT_BYTES:
                        raise IndexSourceProblem("index item row or byte budget exceeded")
                    all_rows.append(row)
            if len(all_rows) > 100_000:
                raise IndexSourceProblem("index item row budget exceeded")
            snapshot = ItemIndexProjection(
                item.item_id,
                item.revision_id,
                watermark,
                _sha((metadata_hash, doc_bindings)),
                expiry,
                tuple(all_rows),
                resolved,
                metadata_hash,
                revisions,
            )
            with self.corpus._transaction(write=True) as (db, _aggregates):
                self.revalidate(db, snapshot, cancelled=cancelled)
            return snapshot

        return self._bounded(read)

    def _document_context(self, db, revision):
        from .document_attachment_repository import LocalDocumentAttachmentService

        receipt_row = db.execute(
            "SELECT result_id FROM document_normalized_revisions WHERE project_id=? AND revision_id=?",
            (self.project, revision),
        ).fetchone()
        if receipt_row is None:
            raise IndexSourceProblem("index document changed")
        source = self.documents._receipt(db, receipt_row[0]).binding.source
        attachments = LocalDocumentAttachmentService(self.database, self.project, self.documents.objects)
        attachment = attachments._attachment(db, source.attachment_id)
        candidate = attachments._candidate(db, attachment.candidate_id)
        if source_identity(attachment, candidate, source.provenance) != source:
            raise IndexSourceProblem("index document copy changed")
        attachments._current_binding(
            db,
            source_assertion_revision_id=source.source_assertion_revision_id,
            work_id=source.work_id,
            work_revision_id=source.work_revision_id,
            version_id=source.version_id,
            version_revision_id=source.version_revision_id,
        )
        permitted, authority, expiry = self._permission(db, candidate.rights_subject, self.documents.actor())
        return source, permitted, authority, expiry

    @staticmethod
    def _text_rows(item, accepted, authority, *, cancelled=lambda: False):
        source = accepted.result.binding.source
        for projection in accepted.structure.text_projections:
            for start, end in _text_ranges(
                projection.normalized_text, 0, len(projection.normalized_text), cancelled=cancelled
            ):
                yield IndexRow(
                    entry_id=_sha(
                        (
                            item.item_id,
                            item.revision_id,
                            item.work_revision_id,
                            accepted.revision_id,
                            projection.projection_id,
                            start,
                            end,
                            authority,
                        )
                    ),
                    item_id=item.item_id,
                    work_id=item.work_id,
                    work_revision_id=item.work_revision_id,
                    source_revision_id=source.source_assertion_revision_id,
                    authority_sha256=authority,
                    document_revision_id=accepted.revision_id,
                    element_id=projection.projection_id,
                    projection_id=projection.projection_id,
                    normalized_start=start,
                    normalized_end=end,
                    full_text=projection.normalized_text,
                )

    def revalidate(
        self,
        db: CanonicalConnection,
        snapshot: ItemIndexProjection,
        *,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> None:
        if cancelled() is not False:
            raise IndexSourceProblem("index source validation cancelled")
        item, rows, revisions, metadata_hash, expiry = self._metadata(db, snapshot.item_id, snapshot._sources)
        watermark = lexical_watermark(db, self.project)
        if (
            watermark != snapshot.watermark
            or item.revision_id != snapshot.item_revision_id
            or metadata_hash != snapshot._metadata_sha256
            or revisions != snapshot._document_revisions
        ):
            raise IndexSourceProblem("index source changed")
        expected = list(rows)
        bindings: list[tuple[object, ...]] = []
        text_bytes = 0
        for revision in revisions:
            if cancelled() is not False:
                raise IndexSourceProblem("index source validation cancelled")
            source, permitted, authority, expires = self._document_context(db, revision)
            if not permitted:
                bindings.append((revision, "unavailable"))
                continue
            accepted = self.documents._accepted(db, revision)
            if (
                accepted.result.binding.source != source
                or source.work_id != item.work_id
                or source.work_revision_id != item.work_revision_id
            ):
                raise IndexSourceProblem("index document source changed")
            bindings.append((revision, accepted.content_sha256, accepted.structure_sha256, authority))
            if expires is not None:
                expiry = expires if expiry is None else min(expiry, expires)
            for row in self._text_rows(item, accepted, authority, cancelled=cancelled):
                text_bytes += len(row.full_text.encode("utf-8"))
                if len(expected) >= 100_000 or text_bytes > _MAX_ITEM_TEXT_BYTES:
                    raise IndexSourceProblem("index item row or byte budget exceeded")
                expected.append(row)
        if cancelled() is not False:
            raise IndexSourceProblem("index source validation cancelled")
        if (
            tuple(expected) != snapshot.rows
            or _sha((metadata_hash, bindings)) != snapshot.authority_sha256
            or expiry != snapshot.expires_at
        ):
            raise IndexSourceProblem("index projection differs from current source")
