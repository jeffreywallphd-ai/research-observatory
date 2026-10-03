"""Encrypted plugin job inputs and fenced, atomic source-result publication.

The signed package and grant authorize code. A queued invocation separately
binds accepted research Intent, current privacy policy, and explicit consent.
Only a live workflow attempt can publish a validated page. An interrupted
object put leaves ciphertext, never a canonical source assertion.
"""

from __future__ import annotations

import hashlib
import io
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .connectors.contracts import ConnectorModel, ConnectorRecord, InvocationId, ObjectDigest, UtcInstant
from .connectors.plugin_dispatch import PluginBrokerResponseRef, PluginStagedOutput
from .connectors.plugin_manifest import PluginInvocationPlan
from .connectors.plugin_result import validate_plugin_output
from .connectors.plugin_scientific_request import (
    PluginScientificRequest,
    PluginScientificRequestProblem,
    parse_plugin_scientific_request,
)
from .connectors.plugin_workflow import PluginJobInput, bind_plugin_claim
from .connectors.transport import bounded_json
from .domain_contracts import new_uuid_v7
from .ports.object_store import ObjectPutCommand, ObjectStore, ObjectStoreProblem
from .ports.plugin_jobs import PluginJobRepositoryProblem
from .ports.repositories import (
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    MaterialDependency,
    RepositoryProblem,
)
from .ports.workflow_executor import WorkflowJobClaim, WorkflowOutputReference, WorkflowQueueConflict
from .repositories import (
    _UNIT_OF_WORKS,
    _projection_content_sha256,
    _SqliteAggregateRepository,
    _SqliteWorkflowQueueRepository,
)
from .storage import CanonicalConnection, StorageProblem, open_canonical_database

_MAX_DOCUMENT = 16 * 1024 * 1024


class PluginPublishedPage(ConnectorModel):
    """A source-reported page with Core identity and sanitized broker-body references."""

    schema_version: Literal["1.0"] = "1.0"
    revision_id: InvocationId
    job_id: InvocationId
    plan: PluginInvocationPlan = Field(repr=False)
    retrieved_at: UtcInstant
    observed_at: UtcInstant
    raw_object_sha256: ObjectDigest
    raw_byte_length: Annotated[int, Field(strict=True, ge=0, le=10 * 1_048_576)]
    broker_calls: Annotated[int, Field(strict=True, ge=0, le=64)]
    broker_responses: Annotated[tuple[PluginBrokerResponseRef, ...], Field(max_length=64)] = Field(
        default=(), repr=False
    )
    records: Annotated[tuple[ConnectorRecord, ...], Field(max_length=1000)] = Field(repr=False)
    continuation: Literal["exhausted", "next-page"]
    next_cursor: Annotated[str, Field(strict=True, min_length=1, max_length=4096)] | None = Field(
        default=None, repr=False
    )

    @model_validator(mode="after")
    def source_binding(self) -> PluginPublishedPage:
        if (
            self.observed_at < self.retrieved_at
            or (self.continuation == "next-page") != (self.next_cursor is not None)
            or (self.broker_responses and len(self.broker_responses) != self.broker_calls)
            or any(
                record.provider_id != self.plan.source_id or record.retrieved_at != self.retrieved_at
                for record in self.records
            )
        ):
            raise ValueError("plugin-published-source-invalid")
        return self


class PluginJobRepository:
    def __init__(self, database: Path, project_id: str, objects: ObjectStore) -> None:
        if not isinstance(database, Path) or not database.is_absolute() or not isinstance(project_id, str):
            raise PluginJobRepositoryProblem("plugin-job-repository-invalid")
        self._database, self._project, self._objects = database, project_id, objects
        self._queue = _SqliteWorkflowQueueRepository(database, project_id)

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[tuple[CanonicalConnection, _SqliteAggregateRepository]]:
        connection, token = None, None
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project)
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            token = _UNIT_OF_WORKS.register(connection, self._project)
            yield connection, _SqliteAggregateRepository(token)
            connection.execute("COMMIT")
        except BaseException:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise
        finally:
            if token is not None:
                _UNIT_OF_WORKS.unregister(token)
            if connection is not None:
                connection.close()

    def _put(
        self, body: bytes, *, now: str, creation_source: Literal["local-derivation", "connector-acquisition"]
    ) -> str:
        if not isinstance(body, bytes) or len(body) > _MAX_DOCUMENT:
            raise PluginJobRepositoryProblem("plugin-job-document-invalid")
        digest = hashlib.sha256(body).hexdigest()
        try:
            stored = self._objects.put(
                io.BytesIO(body),
                ObjectPutCommand(
                    media_type="application/json",
                    rights_status="allowed",  # This grants only local store/inspect.
                    protection_profile="project-encrypted-v1",
                    retention_class="project-lifetime",
                    creation_source=creation_source,
                    created_at=now,
                    expected_sha256=digest,
                ),
            )
            if (stored.object_sha256, stored.byte_length, stored.protection_profile) != (
                digest,
                len(body),
                "project-encrypted-v1",
            ):
                raise ValueError
            return digest
        except ObjectStoreProblem, ValueError:
            raise PluginJobRepositoryProblem("plugin-job-object-unavailable") from None

    def _read(self, digest: str) -> bytes:
        try:
            with self._objects.open(digest, purpose="document-analysis") as source:
                body = source.read(_MAX_DOCUMENT + 1)
            if len(body) > _MAX_DOCUMENT or hashlib.sha256(body).hexdigest() != digest:
                raise ValueError
            return body
        except ObjectStoreProblem, ValueError:
            raise PluginJobRepositoryProblem("plugin-job-object-unavailable") from None

    def save_input(self, inputs: PluginJobInput, *, actor_id: str, now: str) -> None:
        inputs = PluginJobInput.model_validate(inputs)
        if inputs.project_id != self._project:
            raise PluginJobRepositoryProblem("plugin-job-project-invalid")
        digest = self._put(inputs.model_dump_json(by_alias=True).encode(), now=now, creation_source="local-derivation")
        try:
            with self._transaction(write=True) as (connection, aggregates):
                identity = inputs.invocation_id
                row = connection.execute(
                    "SELECT revision_id FROM aggregate_revisions WHERE project_id=? AND revision_id=?",
                    (self._project, identity),
                ).fetchone()
                if row is not None:
                    prior = aggregates.get_revision(identity)
                    if prior.aggregate_kind != "document" or prior.object_sha256 != digest:
                        raise PluginJobRepositoryProblem("plugin-job-input-conflict")
                    return
                aggregates.append(
                    AggregateRevisionDraft(
                        revision_id=identity,
                        aggregate_id=new_uuid_v7(),
                        aggregate_kind="document",
                        created_at=now,
                        modified_at=now,
                        display_label_observed="Confirmed connector plugin request",
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
                                "plugin.confirmed-input",
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
                        idempotency_key="plugin-input-" + identity,
                    ),
                    expected_revision=None,
                )
        except sqlite3.Error, StorageProblem, RepositoryProblem, ObjectStoreProblem:
            raise PluginJobRepositoryProblem("plugin-job-input-unavailable") from None

    def input(self, invocation_id: str) -> PluginJobInput:
        try:
            with self._transaction() as (_, aggregates):
                revision = aggregates.get_revision(invocation_id)
                if revision.aggregate_kind != "document" or revision.object_sha256 is None:
                    raise ValueError
                inputs = PluginJobInput.model_validate_json(self._read(revision.object_sha256))
                if inputs.project_id != self._project or inputs.invocation_id != invocation_id:
                    raise ValueError
                return inputs
        except sqlite3.Error, StorageProblem, RepositoryProblem, ValueError:
            raise PluginJobRepositoryProblem("plugin-job-input-unavailable") from None

    @staticmethod
    def _key(invocation_id: str) -> str:
        return "plugin.result." + invocation_id

    def _pointer(self, connection: CanonicalConnection, invocation_id: str) -> str | None:
        rows = connection.execute(
            "SELECT revision,value_type,text_value FROM settings WHERE project_id=? AND setting_key=? "
            "ORDER BY revision",
            (self._project, self._key(invocation_id)),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1 or rows[0][0] != 1 or rows[0][1] != "text":
            raise PluginJobRepositoryProblem("plugin-job-result-corrupt")
        return rows[0][2]

    def _published(
        self, aggregates: _SqliteAggregateRepository, revision_id: str, inputs: PluginJobInput
    ) -> PluginPublishedPage:
        revision = aggregates.get_revision(revision_id)
        if revision.aggregate_kind != "document" or revision.object_sha256 is None:
            raise PluginJobRepositoryProblem("plugin-job-result-corrupt")
        page = PluginPublishedPage.model_validate_json(self._read(revision.object_sha256))
        if (
            page.revision_id != revision_id
            or page.plan.project_id != self._project
            or page.plan.invocation_id != inputs.invocation_id
            or page.plan.package_sha256 != inputs.package_sha256
            or page.plan.manifest_sha256 != inputs.manifest_sha256
            or page.plan.signature_sha256 != inputs.signature_sha256
            or page.plan.request_sha256 != inputs.authorization_request_sha256
            or page.plan.scientific_request_sha256 != inputs.request.scientific_request_sha256
        ):
            raise PluginJobRepositoryProblem("plugin-job-result-corrupt")
        return page

    def _scientific(self, inputs: PluginJobInput) -> PluginScientificRequest:
        data = self._read(inputs.input_object_sha256)
        if (
            len(data) != inputs.input_byte_length
            or "sha256:" + hashlib.sha256(data).hexdigest() != inputs.request.scientific_request_sha256
        ):
            raise PluginJobRepositoryProblem("plugin-job-input-unavailable")
        try:
            return parse_plugin_scientific_request(data, inputs.request.operation)
        except PluginScientificRequestProblem:
            raise PluginJobRepositoryProblem("plugin-job-input-unavailable") from None

    @staticmethod
    def _continuation_plan(plan: PluginInvocationPlan) -> dict:
        identity = plan.model_dump(mode="json", by_alias=True)
        for field in ("invocationId", "scientificRequestSha256", "requestSha256"):
            identity.pop(field)
        return identity

    def _predecessor_candidate(
        self, inputs: PluginJobInput, plan: PluginInvocationPlan
    ) -> tuple[str, PluginPublishedPage] | None:
        if plan.operation != "search":
            return None
        scientific = self._scientific(inputs)
        previous_id = scientific.previous_invocation_id
        if previous_id is None:
            return None
        if previous_id == inputs.invocation_id:
            raise PluginJobRepositoryProblem("plugin-job-predecessor-invalid")
        try:
            previous_inputs = self.input(previous_id)
            previous_page = self.result(previous_inputs)
        except PluginJobRepositoryProblem:
            raise PluginJobRepositoryProblem("plugin-job-predecessor-invalid") from None
        if previous_page is None:
            raise PluginJobRepositoryProblem("plugin-job-predecessor-invalid")
        previous_scientific = self._scientific(previous_inputs)
        if (
            previous_page.continuation != "next-page"
            or not previous_page.broker_responses
            or previous_page.next_cursor != scientific.call.cursor
            or previous_scientific.call.cursor == scientific.call.cursor
            or previous_scientific.call.query != scientific.call.query
            or previous_scientific.call.page_size != scientific.call.page_size
            or self._continuation_plan(previous_page.plan) != self._continuation_plan(plan)
        ):
            raise PluginJobRepositoryProblem("plugin-job-predecessor-invalid")
        return previous_id, previous_page

    def _predecessor(
        self,
        connection: CanonicalConnection,
        aggregates: _SqliteAggregateRepository,
        candidate: tuple[str, PluginPublishedPage] | None,
    ) -> AggregateRevision | None:
        if candidate is None:
            return None
        previous_id, page = candidate
        if self._pointer(connection, previous_id) != page.revision_id:
            raise PluginJobRepositoryProblem("plugin-job-predecessor-invalid")
        return aggregates.get_revision(page.revision_id)

    def result(self, inputs: PluginJobInput) -> PluginPublishedPage | None:
        inputs = PluginJobInput.model_validate(inputs)
        if inputs.project_id != self._project:
            raise PluginJobRepositoryProblem("plugin-job-project-invalid")
        try:
            with self._transaction() as (connection, aggregates):
                revision_id = self._pointer(connection, inputs.invocation_id)
                return self._published(aggregates, revision_id, inputs) if revision_id is not None else None
        except sqlite3.Error, StorageProblem, RepositoryProblem, ObjectStoreProblem, ValueError:
            raise PluginJobRepositoryProblem("plugin-job-result-unavailable") from None

    @staticmethod
    def _output(revision: AggregateRevision) -> WorkflowOutputReference:
        return WorkflowOutputReference(
            revision.aggregate_id,
            revision.revision_id,
            _projection_content_sha256(revision),
            "application/json",
            revision.aggregate_id,
        )

    def publish(
        self,
        inputs: PluginJobInput,
        plan: PluginInvocationPlan,
        staged: PluginStagedOutput,
        claim: WorkflowJobClaim,
        *,
        actor_id: str,
        now: Callable[[], str],
        recheck_current: Callable[[], None],
        interrupted: Callable[[], bool],
    ) -> WorkflowOutputReference:
        """Validate staged ciphertext, then atomically publish under claim fence."""

        inputs = PluginJobInput.model_validate(inputs)
        plan = PluginInvocationPlan.model_validate(plan)
        if (
            inputs.project_id != self._project
            or plan.project_id != self._project
            or plan.invocation_id != inputs.invocation_id
            or plan.package_sha256 != inputs.package_sha256
            or plan.manifest_sha256 != inputs.manifest_sha256
            or plan.signature_sha256 != inputs.signature_sha256
            or plan.request_sha256 != inputs.authorization_request_sha256
            or plan.scientific_request_sha256 != inputs.request.scientific_request_sha256
            or plan.operation != inputs.request.operation
            or plan.destination != inputs.request.destination
            or not isinstance(staged, PluginStagedOutput)
        ):
            raise PluginJobRepositoryProblem("plugin-job-publication-invalid")
        recheck_current()
        if interrupted():
            raise PluginJobRepositoryProblem("plugin-job-interrupted")
        raw = self._read(staged.object_sha256)
        if (
            len(raw) != staged.byte_length
            or validate_plugin_output(plan, raw, retrieved_at=staged.retrieved_at) != staged.validated_page
        ):
            raise PluginJobRepositoryProblem("plugin-job-stage-invalid")
        try:
            broker_responses = tuple(PluginBrokerResponseRef.model_validate(ref) for ref in staged.broker_responses)
            if not 1 <= len(broker_responses) == staged.broker_calls <= 64 or (
                plan.operation == "search" and len(broker_responses) != 1
            ):
                raise ValueError
            observed_search_cursor = None
            for ref in broker_responses:
                if ref.redacted is None:
                    raise ValueError
                body = self._read(ref.object_sha256)
                if len(body) != ref.byte_length:
                    raise ValueError
                response = bounded_json(body)
                if plan.operation == "search":
                    if not isinstance(response, dict):
                        raise ValueError
                    observed_search_cursor = response.get("nextCursor")
            if plan.operation == "search" and (
                observed_search_cursor != staged.validated_page.next_cursor
                or (
                    observed_search_cursor is not None
                    and observed_search_cursor == self._scientific(inputs).call.cursor
                )
            ):
                raise ValueError
        except Exception:
            raise PluginJobRepositoryProblem("plugin-job-broker-response-invalid") from None
        predecessor_candidate = self._predecessor_candidate(inputs, plan)
        revision_id = new_uuid_v7()
        observed_at = now()
        page = PluginPublishedPage(
            revision_id=revision_id,
            job_id=claim.job_id,
            plan=plan,
            retrieved_at=staged.retrieved_at,
            observed_at=observed_at,
            raw_object_sha256=staged.object_sha256,
            raw_byte_length=staged.byte_length,
            broker_calls=staged.broker_calls,
            broker_responses=broker_responses,
            records=staged.validated_page.records,
            continuation=staged.validated_page.continuation,
            next_cursor=staged.validated_page.next_cursor,
        )
        digest = self._put(
            page.model_dump_json(by_alias=True).encode(), now=observed_at, creation_source="connector-acquisition"
        )
        try:
            with self._transaction(write=True) as (connection, aggregates):
                bind_plugin_claim(self._queue.authority(claim.job_id), claim, inputs)
                recheck_current()
                if interrupted():
                    raise PluginJobRepositoryProblem("plugin-job-interrupted")
                self._queue._verify_attempt_capability(connection, claim)
                lease = self._queue._lease_row(connection, claim, now(), states=("running",))
                if lease[3] is not None:
                    raise PluginJobRepositoryProblem("plugin-job-interrupted")
                prior_id = self._pointer(connection, inputs.invocation_id)
                if prior_id is not None:
                    prior = self._published(aggregates, prior_id, inputs)
                    if (
                        prior.raw_object_sha256 != staged.object_sha256
                        or prior.broker_responses != broker_responses
                        or prior.job_id != claim.job_id
                    ):
                        raise PluginJobRepositoryProblem("plugin-job-result-conflict")
                    output = self._output(aggregates.get_revision(prior_id))
                    self._queue._complete_with_connection(connection, claim, now=now(), outputs=(output,))
                    return output
                source = aggregates.get_revision(inputs.invocation_id)
                expected_input_digest = hashlib.sha256(inputs.model_dump_json(by_alias=True).encode()).hexdigest()
                if source.aggregate_kind != "document" or source.object_sha256 != expected_input_digest:
                    raise PluginJobRepositoryProblem("plugin-job-input-unavailable")
                predecessor = self._predecessor(connection, aggregates, predecessor_candidate)
                dependencies = tuple(
                    MaterialDependency(
                        new_uuid_v7(),
                        "parameter-set",
                        "direct",
                        None,
                        "plugin." + label,
                        "1.0.0",
                        value,
                        "dependency.material.v1",
                        "1.0.0",
                    )
                    for label, value in (
                        ("package", inputs.package_sha256),
                        ("manifest", inputs.manifest_sha256),
                        ("signature", inputs.signature_sha256),
                        ("intent", inputs.intent.content_hash),
                        ("privacy", inputs.policy_hash),
                        ("input", inputs.configuration_hash),
                        ("raw-output", "sha256:" + staged.object_sha256),
                    )
                ) + tuple(
                    MaterialDependency(
                        new_uuid_v7(),
                        "parameter-set",
                        "direct",
                        None,
                        f"plugin.broker-response.{index}",
                        "1.0.0",
                        "sha256:" + ref.object_sha256,
                        "dependency.material.v1",
                        "1.0.0",
                    )
                    for index, ref in enumerate(broker_responses, 1)
                )
                dependencies += tuple(
                    MaterialDependency(
                        new_uuid_v7(),
                        "parameter-set",
                        "direct",
                        None,
                        f"plugin.broker-response-redacted.{index}",
                        "1.0.0",
                        "sha256:"
                        + hashlib.sha256(
                            ("plugin.broker-response-redacted.v1:" + str(ref.redacted).lower()).encode()
                        ).hexdigest(),
                        "dependency.material.v1",
                        "1.0.0",
                    )
                    for index, ref in enumerate(broker_responses, 1)
                )
                revision = aggregates.append(
                    AggregateRevisionDraft(
                        revision_id=revision_id,
                        aggregate_id=new_uuid_v7(),
                        aggregate_kind="document",
                        created_at=observed_at,
                        modified_at=observed_at,
                        display_label_observed="Connector plugin source observations",
                        display_label_normalized=None,
                        knowledge_status="observed",
                        rights_status="unknown",
                        dependency_coverage="complete",
                        object_sha256=digest,
                        provenance_inputs=(source,) if predecessor is None else (source, predecessor),
                        material_dependencies=dependencies,
                    ),
                    AtomicRepositoryEvent(
                        event_id=new_uuid_v7(),
                        outbox_id=new_uuid_v7(),
                        event_type="document.created",
                        occurred_at=observed_at,
                        available_at=observed_at,
                        trace_id=inputs.invocation_id.replace("-", ""),
                        actor_type="worker",
                        actor_id=actor_id,
                        idempotency_key="plugin-result-" + inputs.invocation_id,
                    ),
                    expected_revision=None,
                )
                output = self._output(revision)
                connection.execute(
                    "INSERT INTO settings (setting_id,project_id,setting_key,revision,value_type,text_value,"
                    "created_at,modified_at) "
                    "VALUES (?,?,?,1,'text',?,?,?)",
                    (
                        new_uuid_v7(),
                        self._project,
                        self._key(inputs.invocation_id),
                        revision_id,
                        observed_at,
                        observed_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO workflow_attempt_artifacts VALUES "
                    "(?, ?, ?, ?, ?, 'output', 'retained-incomplete', ?, ?, ?, ?, ?)",
                    (
                        claim.attempt_id,
                        self._project,
                        claim.job_id,
                        output.artifact_id,
                        output.revision_id,
                        output.content_hash,
                        output.media_type,
                        output.provenance_entity_id,
                        observed_at,
                        observed_at,
                    ),
                )
                self._queue._complete_with_connection(connection, claim, now=now(), outputs=(output,))
                return output
        except sqlite3.Error, StorageProblem, RepositoryProblem, ObjectStoreProblem, WorkflowQueueConflict:
            raise PluginJobRepositoryProblem("plugin-job-publication-unavailable") from None
