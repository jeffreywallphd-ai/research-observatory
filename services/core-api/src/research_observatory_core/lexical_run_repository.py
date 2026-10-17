"""Protected immutable SearchRun subtype and atomic existing-queue publication."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import replace

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .lexical_catalog_repository import IndexValidation
from .lexical_index_repository import CoreLexicalIndexService, IndexServiceProblem
from .lexical_input_repository import rights_time_partition, source_authority_epoch
from .lexical_query_repository import CoreLexicalQueryService, LexicalReadSnapshot
from .lexical_run_lineage import validate_run_lineage
from .ports.repositories import AggregateRevisionDraft, AtomicRepositoryEvent, MaterialDependency
from .ports.workflow_executor import WorkflowActor, WorkflowJobClaim, WorkflowOutputReference
from .repositories import _projection_content_sha256
from .search.contracts import load_query_document
from .search.run_schema import REVISION_EVENT
from .search.run_values import (
    SearchInputIdentity,
    SearchInputManifest,
    SearchRequestInput,
    SearchRunContent,
    SearchRunRecord,
    content_sha256,
)
from .search.workflow import ACTIVITY, RUN_MEDIA_TYPE, bind_claim, submission
from .workflow_executor import WorkflowAtomicCompletion


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def result_sha256(snapshot: LexicalReadSnapshot) -> str:
    return _sha(tuple((hit.item_id, hit.score.hex()) for hit in snapshot.ranked))


class SqliteLexicalRunRepository:
    def __init__(self, index: CoreLexicalIndexService, *, session_id: str, intent: Callable, now: Callable[[], str]):
        self.index, self.session_id, self.intent, self.now = index, session_id, intent, now
        self.documents = index.sources.documents
        self.queue = self.documents.queue
        self.project = index.project

    def prepare(self, *, cancelled: Callable[[], bool]) -> None:
        self.index.synchronize(cancelled=cancelled)

    def run_query(
        self,
        claim: WorkflowJobClaim,
        inputs: SearchRequestInput,
        *,
        before_publish: Callable[[], None],
        cancelled: Callable[[], bool],
    ):
        def publish(snapshot, _store):
            before_publish()
            return self.complete(claim, snapshot, cancelled=cancelled)[1]

        return CoreLexicalQueryService(self.index).read(
            load_query_document(inputs.query_document),
            filters=inputs.filters.kernel(),
            consume=publish,
            cancelled=cancelled,
        )

    def _authority(self, db, inputs: SearchRequestInput) -> None:
        actor = self.documents.actor()
        self.documents._authority(db, actor)
        if (inputs.project_id, inputs.actor_id, inputs.session_id, inputs.intent, inputs.policy_sha256) != (
            self.project,
            actor.actor_id,
            self.session_id,
            self.intent(),
            actor.policy_sha256,
        ) or (inputs.intent.revision_id, inputs.intent.content_hash) != (
            actor.intent_revision_id,
            "sha256:" + actor.intent_sha256,
        ):
            raise IndexServiceProblem("search current authority changed")

    def _input(self, db, job_id: str) -> SearchRequestInput:
        if not is_uuid_v7(job_id):
            raise IndexServiceProblem("search job address is invalid")
        row = db.execute(
            "SELECT input_json,input_sha256,command_id,actor_id,session_id FROM search_lexical_jobs "
            "WHERE project_id=? AND job_id=?",
            (self.project, job_id),
        ).fetchone()
        if row is None:
            raise IndexServiceProblem("search job is unavailable")
        inputs = SearchRequestInput.model_validate_json(row[0])
        if (inputs.configuration_hash[7:], inputs.command_id, inputs.actor_id, inputs.session_id) != tuple(row[1:]):
            raise IndexServiceProblem("search job binding is invalid")
        self._authority(db, inputs)
        return inputs

    def submit(self, inputs: SearchRequestInput):
        inputs = SearchRequestInput.model_validate(inputs)

        def submit():
            with self.index.sources.corpus._transaction(write=True) as (db, _aggregates):
                self._authority(db, inputs)
                prior = db.execute(
                    "SELECT job_id FROM search_lexical_jobs WHERE project_id=? AND command_id=?",
                    (self.project, inputs.command_id),
                ).fetchone()
                if prior is not None:
                    if self._input(db, prior[0]) != inputs:
                        raise IndexServiceProblem("search command conflicts")
                    return self.queue._row(self.queue._select_job(db, self.project, prior[0]))
                job = self.queue._enqueue_with_connection(
                    db, submission(inputs, now=self.now()), actor=WorkflowActor(inputs.actor_id, "human", "researcher")
                )
                db.execute(
                    "INSERT INTO search_lexical_jobs VALUES(?,?,?,?,?,?,?,?)",
                    (
                        job.job_id,
                        self.project,
                        inputs.command_id,
                        inputs.model_dump_json(by_alias=True),
                        inputs.configuration_hash[7:],
                        inputs.actor_id,
                        inputs.session_id,
                        self.now(),
                    ),
                )
                return job

        return self.index._bounded(submit)

    def claim_input(self, claim: WorkflowJobClaim) -> SearchRequestInput:
        def read():
            with self.index.sources.corpus._transaction(write=False) as (db, _aggregates):
                inputs = self._input(db, claim.job_id)
            return bind_claim(self.queue.authority(claim.job_id), claim, inputs)

        return self.index._bounded(read)

    def _classify(self, db, event, payload_sha256, *, completion=False):
        row = db.execute(
            "SELECT outbox_id,revision_id,record_sha256 FROM outbox_events WHERE project_id=? AND outbox_id=?",
            (self.project, event),
        ).fetchone()
        if row is None:
            raise IndexServiceProblem("search observation outbox is unavailable")
        db.execute(
            "INSERT INTO search_observation_events VALUES(?,?,?,?,?,?)",
            (row[0], self.project, row[1], row[2], payload_sha256, "job-completed" if completion else "node-created"),
        )

    def _append(self, db, aggregates, payload, sources, *, worker_id, run_id=None, check):
        check()
        actor, now = self.documents.actor(), self.now()
        digest = content_sha256(payload)
        revisions = tuple(aggregates.get_revision(identity) for identity in sources)
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
            for source in revisions
        )
        for name, value in (
            ("lexical-node-payload", digest),
            (
                "lexical-input-snapshot",
                payload.inputs.input_sha256 if isinstance(payload, SearchRunContent) else payload.input_sha256,
            ),
            ("current-intent", actor.intent_sha256),
            ("current-privacy", actor.policy_sha256),
        ):
            dependencies += (
                MaterialDependency(
                    new_uuid_v7(),
                    "parameter-set",
                    "direct",
                    None,
                    "search." + name,
                    "1.0.0",
                    "sha256:" + value,
                    "dependency.material.v1",
                    "1.0.0",
                ),
            )
        outbox_id = new_uuid_v7()
        revision = aggregates.append(
            AggregateRevisionDraft(
                revision_id=new_uuid_v7(),
                aggregate_id=run_id or new_uuid_v7(),
                aggregate_kind="workflow",
                created_at=now,
                modified_at=now,
                display_label_observed="Executed lexical search" if run_id else "Lexical search input manifest",
                display_label_normalized=None,
                knowledge_status="observed",
                rights_status="unknown",
                dependency_coverage="complete",
                provenance_inputs=revisions,
                material_dependencies=dependencies,
            ),
            AtomicRepositoryEvent(
                event_id=new_uuid_v7(),
                outbox_id=outbox_id,
                event_type=REVISION_EVENT,
                occurred_at=now,
                available_at=now,
                trace_id=actor.trace_id,
                actor_type="worker",
                actor_id=worker_id,
                idempotency_key="search-node-" + outbox_id,
            ),
            expected_revision=None,
        )
        if isinstance(payload, SearchRunContent):
            db.execute(
                "INSERT INTO search_lexical_runs(revision_id,project_id,job_id,search_run_id,"
                "payload_sha256,run_json) "
                "VALUES(?,?,?,?,?,?)",
                (
                    revision.revision_id,
                    self.project,
                    payload.job_id,
                    payload.search_run_id,
                    digest,
                    payload.model_dump_json(by_alias=True),
                ),
            )
        else:
            db.execute(
                "INSERT INTO search_input_manifests(revision_id,project_id,job_id,payload_sha256,manifest_json) "
                "VALUES(?,?,?,?,?)",
                (revision.revision_id, self.project, payload.job_id, digest, payload.model_dump_json(by_alias=True)),
            )
        self._classify(db, outbox_id, digest)
        check()
        return revision

    def _load_result(self, db, aggregates, job_id: str) -> SearchRunRecord | None:
        inputs = self._input(db, job_id)
        _job, accepted = self.queue._accepted_status_with_connection(db, job_id)
        if accepted is None:
            return None
        if accepted.activity_type != ACTIVITY or len(accepted.outputs) != 1:
            raise IndexServiceProblem("search accepted output is invalid")
        row = db.execute(
            "SELECT revision_id,payload_sha256,run_json FROM search_lexical_runs WHERE project_id=? AND job_id=?",
            (self.project, job_id),
        ).fetchone()
        if row is None:
            raise IndexServiceProblem("search accepted run is unavailable")
        content = SearchRunContent.model_validate_json(row[2])
        revision = aggregates.get_revision(row[0])
        output = accepted.outputs[0]
        if content.request != inputs or (
            output.artifact_id,
            output.revision_id,
            output.content_hash,
            output.media_type,
            output.provenance_entity_id,
        ) != (
            content.search_run_id,
            revision.revision_id,
            _projection_content_sha256(revision),
            RUN_MEDIA_TYPE,
            content.search_run_id,
        ):
            raise IndexServiceProblem("search accepted run binding is invalid")
        binding = db.execute(
            "SELECT 1 FROM material_dependencies WHERE project_id=? AND output_revision_id=? "
            "AND configuration_id='search.lexical-node-payload' AND fingerprint=?",
            (self.project, revision.revision_id, "sha256:" + row[1]),
        ).fetchone()
        if binding is None:
            raise IndexServiceProblem("search payload provenance is invalid")
        record = SearchRunRecord(revision_id=row[0], payload_sha256=row[1], content=content)
        self._current_record(db, record)
        validate_run_lineage(db, aggregates, revision.revision_id, content)
        self._current_record(db, record)
        return record

    def _current_record(self, db, record: SearchRunRecord) -> None:
        identity = record.content.inputs
        now = self.index.catalog.now()
        if (
            now < identity.validated_at
            or source_authority_epoch(db, self.project) != identity.source_authority_epoch
            or rights_time_partition(db, self.project, now) != identity.rights_time_partition
        ):
            raise IndexServiceProblem("search run source authority changed")
        self.index._fence(
            db,
            IndexValidation(
                identity.source_watermark,
                identity.authority_sha256,
                identity.actor_sha256,
                identity.earliest_rights_expiry,
            ),
        )
        selection = self.index.catalog._selection(db)
        generation = self.index.catalog._load(db, identity.generation_id)
        if (
            selection is None
            or selection["event_id"] != identity.selection_id
            or generation.stage != "Ready"
            or generation.event_id != identity.generation_event_id
            or generation.projection_sha256 != identity.projection_sha256
            or generation.authority_sha256 != identity.authority_sha256
            or generation.checkpoint != identity.source_watermark
            or generation.configuration_sha256 != identity.generation_configuration_sha256
            or generation.derivative_key_version != identity.derivative_key_version
            or generation.scope.canonical_key_version != identity.canonical_key_version
            or generation.scope.lifecycle_sha256 != identity.lifecycle_sha256
        ):
            raise IndexServiceProblem("search run inputs changed")
        self.index._current(generation)
        if identity.earliest_rights_expiry is not None and self.index.catalog.now() >= identity.earliest_rights_expiry:
            raise IndexServiceProblem("search run permission expired")

    def result(self, job_id: str) -> SearchRunRecord | None:
        def read():
            with self.index.sources.corpus._transaction(write=False) as (db, aggregates):
                record = self._load_result(db, aggregates, job_id)
            # A new current transaction closes changes during lineage decoding;
            # the prior read snapshot cannot attest its own delivery freshness.
            if record is not None:
                with self.index.sources.corpus._transaction(write=True) as (db, _aggregates):
                    self._authority(db, record.content.request)
                    self._current_record(db, record)
            return record

        return self.index._bounded(read)

    def complete(self, claim: WorkflowJobClaim, snapshot: LexicalReadSnapshot, *, cancelled: Callable[[], bool]):
        def publish():
            with self.index.sources.corpus._transaction(write=True) as (db, aggregates):
                inputs = self._input(db, claim.job_id)
                bind_claim(self.queue.authority(claim.job_id), claim, inputs)
                replay = self._load_result(db, aggregates, claim.job_id)
                if replay is not None:
                    if (
                        replay.content.attempt_id,
                        replay.content.inputs.input_sha256,
                        replay.content.result_sha256,
                    ) != (claim.attempt_id, snapshot.input_sha256, result_sha256(snapshot)):
                        raise IndexServiceProblem("search completion replay conflicts")
                    accepted = self.queue._accepted_status_with_connection(db, claim.job_id)[1]
                    if accepted is None:
                        raise IndexServiceProblem("search completion replay is unavailable")
                    return replay, WorkflowAtomicCompletion(accepted.outputs)
                renewed = [0.0]

                def check_current():
                    self.index._check_cancel(cancelled)
                    self._authority(db, inputs)
                    self.index._fence(db, snapshot.validation)
                    selection = self.index.catalog._selection(db)
                    if (
                        selection is None
                        or selection["event_id"] != snapshot.generation.selection_id
                        or self.index.catalog._load(db, snapshot.generation.generation_id)
                        != replace(snapshot.generation, selection_id=None)
                    ):
                        raise IndexServiceProblem("search selection changed before commit")
                    self.index._current(snapshot.generation)
                    now = self.index.catalog.now()
                    if (
                        now < snapshot.validated_at
                        or source_authority_epoch(db, self.project) != snapshot.source_authority_epoch
                        or rights_time_partition(db, self.project, now) != snapshot.rights_time_partition
                    ):
                        raise IndexServiceProblem("search source authority changed before commit")
                    if snapshot.validation.expires_at is not None and now >= snapshot.validation.expires_at:
                        raise IndexServiceProblem("search permission expired before commit")
                    self.index._check_cancel(cancelled)

                def check():
                    check_current()
                    lease = self.queue._lease_row(db, claim, self.now(), states=("running",))
                    self.queue._verify_attempt_capability(db, claim)
                    if lease[3] is not None:
                        raise IndexServiceProblem("search cancelled before commit")
                    if time.monotonic() - renewed[0] >= 2:
                        self.queue._heartbeat_with_connection(
                            db,
                            claim,
                            now=self.now(),
                            lease_duration_ms=30000,
                            progress={"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None},
                        )
                        renewed[0] = time.monotonic()

                check()
                roots = snapshot.source_revisions
                source_set = _sha(roots)
                level = 0
                while len(roots) > 60:
                    next_roots = []
                    for ordinal, offset in enumerate(range(0, len(roots), 60)):
                        manifest = SearchInputManifest(
                            project_id=self.project,
                            job_id=claim.job_id,
                            input_sha256=snapshot.input_sha256,
                            level=level,
                            ordinal=ordinal,
                            source_revision_ids=roots[offset : offset + 60],
                        )
                        node = self._append(
                            db,
                            aggregates,
                            manifest,
                            manifest.source_revision_ids,
                            worker_id=claim.worker_id,
                            check=check,
                        )
                        next_roots.append(node.revision_id)
                    roots = tuple(sorted(next_roots))
                    level += 1
                generation, validation = snapshot.generation, snapshot.validation
                if generation.selection_id is None or generation.projection_sha256 is None:
                    raise IndexServiceProblem("search selected generation is incomplete")
                identity = SearchInputIdentity(
                    project_id=self.project,
                    generation_id=generation.generation_id,
                    selection_id=generation.selection_id,
                    generation_event_id=generation.event_id,
                    generation_configuration_sha256=generation.configuration_sha256,
                    projection_sha256=generation.projection_sha256,
                    source_watermark=validation.watermark,
                    source_authority_epoch=snapshot.source_authority_epoch,
                    rights_time_partition=snapshot.rights_time_partition,
                    validated_at=snapshot.validated_at,
                    authority_sha256=validation.authority_sha256,
                    actor_sha256=validation.actor_sha256,
                    lifecycle_sha256=generation.scope.lifecycle_sha256,
                    canonical_key_version=generation.scope.canonical_key_version,
                    derivative_key_version=generation.derivative_key_version,
                    earliest_rights_expiry=validation.expires_at,
                    input_sha256=snapshot.input_sha256,
                    source_set_sha256=source_set,
                )
                content = SearchRunContent(
                    search_run_id=new_uuid_v7(),
                    project_id=self.project,
                    job_id=claim.job_id,
                    attempt_id=claim.attempt_id,
                    request_sha256=inputs.configuration_hash[7:],
                    request=inputs,
                    inputs=identity,
                    source_roots=roots,
                    result_count=len(snapshot.ranked),
                    result_sha256=result_sha256(snapshot),
                    executed_at=self.now(),
                )
                revision = self._append(
                    db,
                    aggregates,
                    content,
                    roots,
                    worker_id=claim.worker_id,
                    run_id=content.search_run_id,
                    check=check,
                )
                output = WorkflowOutputReference(
                    content.search_run_id,
                    revision.revision_id,
                    _projection_content_sha256(revision),
                    RUN_MEDIA_TYPE,
                    content.search_run_id,
                )
                self.queue._stage_artifact_with_connection(db, claim, artifact=output, role="output", now=self.now())
                check()
                self.queue._complete_with_connection(db, claim, now=self.now(), outputs=(output,))
                completion_outbox = db.execute(
                    "SELECT outbox_id FROM workflow_committed_outputs WHERE project_id=? AND job_id=?",
                    (self.project, claim.job_id),
                ).fetchone()[0]
                self._classify(db, completion_outbox, content_sha256(content), completion=True)
                # The transaction contains the entire accepted node, immutable
                # subtype, source edges, provenance/outbox, staged output and
                # fenced terminal winner. No derivative transaction participates.
                result = (
                    SearchRunRecord(
                        revision_id=revision.revision_id, payload_sha256=content_sha256(content), content=content
                    ),
                    WorkflowAtomicCompletion((output,)),
                )
                # The queue is now terminal, so renewing a running lease would
                # reject a legitimate winner. Current source/time/authority must
                # still hold after that write or the entire acceptance rolls back.
                check_current()
                return result

        return self.index._bounded(publish)
