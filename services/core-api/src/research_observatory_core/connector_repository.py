"""Protected connector observations on the existing canonical repository.

Small append-only settings entries are validated indexes, never research-state
authority. Document revisions own protected page/raw objects and provenance.
An interrupted object put can leave an encrypted orphan; only the one canonical
transaction publishes observations, references, cache and cursor advancement.
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from .connectors.contracts import (
    ConnectorModel,
    ConnectorRecord,
    ConnectorRequest,
    ConnectorResultPage,
    InvocationId,
    ObjectDigest,
    ProjectId,
    RequestDigest,
)
from .connectors.providers import ProviderProblem
from .connectors.workflow import ConnectorJobInput
from .domain_contracts import new_uuid_v7
from .ports.connector_runtime import ConnectorAuthorityStamp, ConnectorCacheEntry
from .ports.object_store import ObjectPutCommand, ObjectStore, ObjectStoreProblem
from .ports.repositories import (
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    MaterialDependency,
    RepositoryProblem,
)
from .ports.workflow_executor import WorkflowOutputReference
from .repositories import _UNIT_OF_WORKS, _projection_content_sha256, _SqliteAggregateRepository
from .storage import CanonicalConnection, StorageProblem, open_canonical_database

_MAX_DOCUMENT = 16 * 1024 * 1024


class _ReplayPublication(Exception):
    """A concurrent identical invocation won; read it after releasing the writer."""


def _bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _request_hash(value: ConnectorRequest) -> str:
    return "sha256:" + hashlib.sha256(_bytes(value.model_dump(mode="json", by_alias=True))).hexdigest()


class _Pointer(ConnectorModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectId
    revision_id: InvocationId
    object_sha256: ObjectDigest
    invocation_id: InvocationId
    request_sha256: RequestDigest
    scientific_sha256: RequestDigest
    page_sha256: RequestDigest


class _StoredPage(ConnectorModel):
    schema_version: Literal["1.0"] = "1.0"
    page: ConnectorResultPage = Field(repr=False)
    raw_revision_id: InvocationId | None
    etag: Annotated[str, Field(strict=True, max_length=1024)] | None = Field(repr=False)
    last_modified: Annotated[str, Field(strict=True, max_length=1024)] | None = Field(repr=False)
    intent_revision_id: InvocationId
    intent_sha256: RequestDigest
    policy_sha256: RequestDigest
    confirmation_sha256: RequestDigest
    rights_sha256: RequestDigest


class ConnectorRepository:
    """Trusted Core adapter: callers must hold current project/action authority."""

    def __init__(self, database: Path, project_id: str, objects: ObjectStore):
        if not database.is_absolute():
            raise ValueError("connector-repository-path-invalid")
        self._database, self._project, self._objects = database, project_id, objects

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[tuple[CanonicalConnection, _SqliteAggregateRepository]]:
        connection, token = None, None
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project)
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            token = _UNIT_OF_WORKS.register(connection, self._project)
            yield connection, _SqliteAggregateRepository(token)
            connection.execute("COMMIT")
        except _ReplayPublication:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error, StorageProblem, RepositoryProblem, ObjectStoreProblem, ValueError, OSError, TypeError:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise ProviderProblem("incompatible-response") from None
        finally:
            if token is not None:
                _UNIT_OF_WORKS.unregister(token)
            if connection is not None:
                connection.close()

    def _request(self, request: ConnectorRequest) -> ConnectorRequest:
        request = ConnectorRequest.model_validate(request)
        if request.project_id != self._project:
            raise ProviderProblem("policy-denied")
        return request

    @staticmethod
    def _key(kind: str, identity: str) -> str:
        return "connector." + kind + "." + identity.removeprefix("sha256:")

    def _pointer(self, connection: CanonicalConnection, key: str) -> _Pointer | None:
        row = connection.execute(
            "SELECT value_type, text_value FROM settings WHERE project_id=? AND setting_key=? "
            "ORDER BY revision DESC LIMIT 1",
            (self._project, key),
        ).fetchone()
        if row is None:
            return None
        if row[0] != "text":
            raise ValueError("connector-pointer-invalid")
        pointer = _Pointer.model_validate_json(row[1])
        if pointer.project_id != self._project:
            raise ValueError("connector-pointer-project-invalid")
        return pointer

    def _read_object(self, digest: str) -> bytes:
        with self._objects.open(digest, purpose="document-analysis") as stream:
            raw = stream.read(_MAX_DOCUMENT + 1)
        if len(raw) > _MAX_DOCUMENT or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("connector-object-invalid")
        return raw

    def _stored(self, aggregates: _SqliteAggregateRepository, pointer: _Pointer) -> _StoredPage:
        revision = aggregates.get_revision(pointer.revision_id)
        if (revision.project_id, revision.aggregate_kind, revision.object_sha256) != (
            self._project,
            "document",
            pointer.object_sha256,
        ):
            raise ValueError("connector-revision-invalid")
        stored = _StoredPage.model_validate_json(self._read_object(pointer.object_sha256))
        request = self._request(stored.page.request)
        if (pointer.invocation_id, pointer.request_sha256, pointer.scientific_sha256, pointer.page_sha256) != (
            request.invocation_id,
            _request_hash(request),
            request.scientific_sha256(),
            request.page_sha256(),
        ):
            raise ValueError("connector-pointer-binding-invalid")
        if stored.page.response.body_state == "retained":
            if stored.raw_revision_id is None:
                raise ValueError("connector-body-reference-missing")
            raw = aggregates.get_revision(stored.raw_revision_id)
            if (raw.project_id, raw.aggregate_kind, raw.object_sha256) != (
                self._project,
                "document",
                stored.page.response.object_sha256,
            ):
                raise ValueError("connector-body-reference-invalid")
        elif stored.raw_revision_id is not None:
            raise ValueError("connector-unavailable-body-reference")
        return stored

    def replay(self, request: ConnectorRequest) -> ConnectorResultPage | None:
        request = self._request(request)
        with self._transaction() as (connection, aggregates):
            pointer = self._pointer(connection, self._key("invocation", request.invocation_id))
            if pointer is None:
                return None
            if pointer.request_sha256 != _request_hash(request):
                raise ValueError("connector-invocation-conflict")
            return self._stored(aggregates, pointer).page

    def checkpoint(self, request: ConnectorRequest) -> tuple[str, ConnectorResultPage] | None:
        request = self._request(request)
        with self._transaction() as (connection, aggregates):
            pointer = self._pointer(connection, self._key("checkpoint", request.scientific_sha256()))
            if pointer is None:
                return None
            stored = self._stored(aggregates, pointer)
            if pointer.scientific_sha256 != request.scientific_sha256() or stored.page.outcome != "complete":
                raise ValueError("connector-checkpoint-invalid")
            return pointer.revision_id, stored.page

    def cached(self, request: ConnectorRequest) -> ConnectorCacheEntry | None:
        request = self._request(request)
        with self._transaction() as (connection, aggregates):
            pointer = self._pointer(connection, self._key("cache", request.page_sha256()))
            if pointer is None:
                return None
            stored = self._stored(aggregates, pointer)
            page = stored.page
            if pointer.page_sha256 != request.page_sha256() or page.outcome != "complete":
                raise ValueError("connector-cache-invalid")
            if page.response.object_sha256 is None or page.retrieved_at is None:
                raise ValueError("connector-cache-body-unavailable")
            body = self._read_object(page.response.object_sha256)
            if len(body) != page.response.byte_length:
                raise ValueError("connector-cache-body-invalid")
            return ConnectorCacheEntry(
                self._project,
                request.page_sha256(),
                body,
                page.retrieved_at,
                page.observed_at,
                stored.etag,
                stored.last_modified,
            )

    def source_record(self, revision_id: str, ordinal: int) -> ConnectorRecord:
        """Stable source assertion address for reconciliation, not a canonical Work."""
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or not 0 <= ordinal < 1000:
            raise ProviderProblem("invalid-query")
        with self._transaction() as (_, aggregates):
            revision = aggregates.get_revision(revision_id)
            if revision.aggregate_kind != "document" or revision.object_sha256 is None:
                raise ValueError("connector-source-invalid")
            stored = _StoredPage.model_validate_json(self._read_object(revision.object_sha256))
            self._request(stored.page.request)
            if ordinal >= len(stored.page.records):
                raise ValueError("connector-source-ordinal-invalid")
            return stored.page.records[ordinal]

    def save_operation(self, inputs: ConnectorJobInput, *, actor_id: str, now: str) -> None:
        inputs = ConnectorJobInput.model_validate(inputs)
        self._request(inputs.preview.request)
        digest = self._put(inputs.model_dump_json(by_alias=True).encode(), now)
        with self._transaction(write=True) as (connection, aggregates):
            identity = inputs.preview.preview_id
            existing = connection.execute(
                "SELECT revision_id FROM aggregate_revisions WHERE revision_id=?", (identity,)
            ).fetchone()
            if existing is not None:
                revision = aggregates.get_revision(identity)
                if revision.aggregate_kind != "document" or revision.object_sha256 != digest:
                    raise ValueError("connector-operation-conflict")
                return
            aggregates.append(
                AggregateRevisionDraft(
                    revision_id=identity,
                    aggregate_id=new_uuid_v7(),
                    aggregate_kind="document",
                    created_at=now,
                    modified_at=now,
                    display_label_observed="Confirmed scholarly metadata request",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                    dependency_coverage="complete",
                    object_sha256=digest,
                    material_dependencies=(
                        MaterialDependency(
                            new_uuid_v7(),
                            "parameter-set",
                            "direct",
                            None,
                            "connector.confirmed-input",
                            "1.0.0",
                            inputs.configuration_hash,
                            "dependency.material.v1",
                            "1.0.0",
                        ),
                    ),
                ),
                AtomicRepositoryEvent(
                    event_id=new_uuid_v7(),
                    outbox_id=new_uuid_v7(),
                    event_type="document.created",
                    occurred_at=now,
                    available_at=now,
                    trace_id=identity.replace("-", ""),
                    actor_type="human",
                    actor_id=actor_id,
                    idempotency_key="connector-confirmation-" + identity,
                ),
                expected_revision=None,
            )

    def operation(self, revision_id: str) -> ConnectorJobInput:
        with self._transaction() as (_, aggregates):
            revision = aggregates.get_revision(revision_id)
            if revision.aggregate_kind != "document" or revision.object_sha256 is None:
                raise ValueError("connector-operation-invalid")
            inputs = ConnectorJobInput.model_validate_json(self._read_object(revision.object_sha256))
            self._request(inputs.preview.request)
            if inputs.preview.preview_id != revision_id:
                raise ValueError("connector-operation-identity-invalid")
            return inputs

    def output_reference(self, request: ConnectorRequest) -> WorkflowOutputReference:
        request = self._request(request)
        with self._transaction() as (connection, aggregates):
            pointer = self._pointer(connection, self._key("invocation", request.invocation_id))
            if pointer is None or pointer.request_sha256 != _request_hash(request):
                raise ValueError("connector-result-unavailable")
            stored = self._stored(aggregates, pointer)
            if stored.page.outcome != "complete":
                raise ValueError("connector-result-incomplete")
            revision = aggregates.get_revision(pointer.revision_id)
            return WorkflowOutputReference(
                revision.aggregate_id,
                revision.revision_id,
                _projection_content_sha256(revision),
                "application/json",
                revision.aggregate_id,
            )

    def _put(self, body: bytes, now: str) -> str:
        if len(body) > _MAX_DOCUMENT:
            raise ProviderProblem("response-too-large")
        # This describes only the already-authorized local store/inspect action.
        # Export/model/share rights remain unknown and need their own checks.
        stored = self._objects.put(
            io.BytesIO(body),
            ObjectPutCommand(
                media_type="application/json",
                rights_status="allowed",
                protection_profile="project-encrypted-v1",
                retention_class="project-lifetime",
                creation_source="connector-acquisition",
                created_at=now,
                expected_sha256=hashlib.sha256(body).hexdigest(),
            ),
        )
        return stored.object_sha256

    @staticmethod
    def _append(
        aggregates: _SqliteAggregateRepository,
        page: ConnectorResultPage,
        digest: str,
        authority: ConnectorAuthorityStamp,
        sources: tuple[AggregateRevision, ...],
        label: str,
        revision_id: str | None = None,
    ) -> AggregateRevision:
        dependencies = tuple(
            MaterialDependency(
                new_uuid_v7(),
                "source-revision",
                "direct",
                source.revision_id,
                None,
                None,
                _projection_content_sha256(source),
                "dependency.material.v1",
                "1.0.0",
            )
            for source in sources
        )
        for name, fingerprint in (
            ("request", _request_hash(page.request)),
            ("intent", authority.intent_sha256),
            ("privacy", authority.policy_sha256),
            ("confirmation", authority.confirmation_sha256),
            ("rights", authority.rights_sha256),
        ):
            dependencies += (
                MaterialDependency(
                    new_uuid_v7(),
                    "parameter-set",
                    "direct",
                    None,
                    "connector." + name,
                    "1.0.0",
                    fingerprint,
                    "dependency.material.v1",
                    "1.0.0",
                ),
            )
        return aggregates.append(
            AggregateRevisionDraft(
                revision_id=revision_id or new_uuid_v7(),
                aggregate_id=new_uuid_v7(),
                aggregate_kind="document",
                created_at=page.observed_at,
                modified_at=page.observed_at,
                display_label_observed=label,
                display_label_normalized=None,
                knowledge_status="observed",
                rights_status="unknown",
                dependency_coverage="complete",
                object_sha256=digest,
                provenance_inputs=sources,
                material_dependencies=dependencies,
            ),
            AtomicRepositoryEvent(
                event_id=new_uuid_v7(),
                outbox_id=new_uuid_v7(),
                event_type="document.created",
                occurred_at=page.observed_at,
                available_at=page.observed_at,
                trace_id=page.request.invocation_id.replace("-", ""),
                actor_type="worker",
                actor_id=authority.actor_id,
                idempotency_key=new_uuid_v7(),
            ),
            expected_revision=None,
        )

    def _write_pointer(self, connection: CanonicalConnection, key: str, pointer: _Pointer, now: str) -> None:
        row = connection.execute(
            "SELECT COALESCE(MAX(revision), -1) FROM settings WHERE project_id=? AND setting_key=?",
            (self._project, key),
        ).fetchone()
        connection.execute(
            "INSERT INTO settings (setting_id,project_id,setting_key,revision,value_type,"
            "text_value,created_at,modified_at) "
            "VALUES (?,?,?,?,'text',?,?,?)",
            (new_uuid_v7(), self._project, key, row[0] + 1, pointer.model_dump_json(by_alias=True), now, now),
        )

    def publish(
        self,
        page: ConnectorResultPage,
        *,
        body: bytes | None,
        etag: str | None,
        last_modified: str | None,
        authority: ConnectorAuthorityStamp,
    ) -> ConnectorResultPage:
        page = ConnectorResultPage.model_validate(page)
        request = self._request(page.request)
        if authority.project_id != self._project:
            raise ProviderProblem("policy-denied")
        prior = self.replay(request)
        if prior is not None:
            return prior
        predecessor_state = self.checkpoint(request)
        if (predecessor_state[0] if predecessor_state else None) != authority.expected_checkpoint_revision_id:
            raise ProviderProblem("invalid-cursor")
        if request.cursor is not None and (
            predecessor_state is None or predecessor_state[1].next_cursor != request.cursor
        ):
            raise ProviderProblem("invalid-cursor")
        retained = page.response.body_state == "retained"
        if retained != (body is not None) or (retained and not authority.retain_body):
            raise ProviderProblem("policy-denied")
        if body is not None and (hashlib.sha256(body).hexdigest(), len(body)) != (
            page.response.object_sha256,
            page.response.byte_length,
        ):
            raise ProviderProblem("incompatible-response")
        try:
            raw_digest = self._put(body, page.observed_at) if body is not None else None
            # Raw/page objects are put before BEGIN IMMEDIATE: the object store owns
            # its own transaction. Their canonical references are committed together.
            raw_id = new_uuid_v7() if raw_digest else None
            stored = _StoredPage(
                page=page,
                raw_revision_id=raw_id,
                etag=etag if retained else None,
                last_modified=last_modified if retained else None,
                intent_revision_id=authority.intent_revision_id,
                intent_sha256=authority.intent_sha256,
                policy_sha256=authority.policy_sha256,
                confirmation_sha256=authority.confirmation_sha256,
                rights_sha256=authority.rights_sha256,
            )
            # The raw document revision gets its preselected ID inside the same transaction.
            page_digest = self._put(_bytes(stored.model_dump(mode="json", by_alias=True)), page.observed_at)
            with self._transaction(write=True) as (connection, aggregates):
                previous = self._pointer(connection, self._key("invocation", request.invocation_id))
                if previous is not None:
                    if previous.request_sha256 != _request_hash(request):
                        raise ValueError("connector-invocation-conflict")
                    raise _ReplayPublication
                checkpoint_key = self._key("checkpoint", request.scientific_sha256())
                checkpoint = self._pointer(connection, checkpoint_key)
                if (checkpoint.revision_id if checkpoint else None) != authority.expected_checkpoint_revision_id:
                    raise ValueError("connector-checkpoint-conflict")
                predecessor: tuple[AggregateRevision, ...] = ()
                if checkpoint:
                    # The immutable predecessor was verified before BEGIN IMMEDIATE.
                    # Exact CAS above fences intervening publication; object reads
                    # must not contend with this writer through their audit connection.
                    if checkpoint.scientific_sha256 != request.scientific_sha256():
                        raise ValueError("connector-checkpoint-binding-invalid")
                    predecessor = (aggregates.get_revision(checkpoint.revision_id),)
                elif request.cursor is not None:
                    raise ValueError("connector-cursor-predecessor-missing")
                if raw_digest:
                    raw_revision = self._append(
                        aggregates, page, raw_digest, authority, (), "Connector response snapshot", raw_id
                    )
                    predecessor += (raw_revision,)
                revision = self._append(aggregates, page, page_digest, authority, predecessor, "Connector observation")
                pointer = _Pointer(
                    project_id=self._project,
                    revision_id=revision.revision_id,
                    object_sha256=page_digest,
                    invocation_id=request.invocation_id,
                    request_sha256=_request_hash(request),
                    scientific_sha256=request.scientific_sha256(),
                    page_sha256=request.page_sha256(),
                )
                self._write_pointer(
                    connection, self._key("invocation", request.invocation_id), pointer, page.observed_at
                )
                if page.outcome == "complete":
                    self._write_pointer(connection, checkpoint_key, pointer, page.observed_at)
                    if retained:
                        self._write_pointer(
                            connection, self._key("cache", request.page_sha256()), pointer, page.observed_at
                        )
            return page
        except _ReplayPublication:
            replayed = self.replay(request)
            if replayed is None:
                raise ProviderProblem("incompatible-response") from None
            return replayed
        except ObjectStoreProblem, ValueError, OSError:
            raise ProviderProblem("incompatible-response") from None
