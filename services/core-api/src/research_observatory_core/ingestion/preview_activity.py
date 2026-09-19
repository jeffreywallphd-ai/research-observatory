"""Bounded local parse activity; the trusted service supplies project/launch guards.

The constructor is a composition seam, not an untrusted job-payload decoder.
Runtime dispatch must bind the exact preview/source configuration to the real job.
No canonical scholarly import, filesystem path, network or credential access.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Protocol

from ..domain_contracts import new_uuid_v7
from ..ports.import_previews import ImportPreviewRepository, PreviewActor, PreviewProblem, PreviewState
from ..ports.object_store import ObjectStore
from ..ports.repositories import AggregateRevisionDraft, AtomicRepositoryEvent, MaterialDependency, UnitOfWorkFactory
from ..ports.workflow_executor import WorkflowJobClaim, WorkflowOutputReference
from ..workflow_executor import WorkflowActivityContext, WorkflowActivityError
from .import_drafts import ImportRights
from .preview_records import StoredImportRecord
from .preview_workflow import fingerprint
from .reference_imports import PARSER_VERSION, ImportProblem, ImportRecord, ImportSession, ImportSource
from .source_chunks import ChunkedImportSource


class ImportActionGuard(Protocol):
    """Retain current project and launch authority for one bounded operation."""

    def __call__[Result](self, action: Callable[[], Result]) -> Result: ...


class _GuardedSource:
    def __init__(self, source: ChunkedImportSource, guard: ImportActionGuard):
        self.source, self.guard = source, guard

    def read(self, size: int = -1) -> bytes:
        return self.guard(lambda: self.source.read(size))


class ImportPreviewActivity:
    def __init__(
        self,
        *,
        preview_id: str,
        repository: ImportPreviewRepository,
        store: ObjectStore,
        unit_of_work: UnitOfWorkFactory,
        guard: ImportActionGuard,
        trace_id: str,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._preview, self._repository, self._store = preview_id, repository, store
        self._units, self._guard, self._trace, self._clock = unit_of_work, guard, trace_id, clock

    def _rights(self) -> ImportRights:
        # Called only inside the guarded read, including for buffered bytes.
        state = self._repository.read(self._preview)
        if state.state in {"cancelled", "failed", "security-interrupted"}:
            raise PreviewProblem("preview-closed")
        return state.rights

    def _receipt(
        self,
        state: PreviewState,
        session: ImportSession,
        claim: WorkflowJobClaim,
        actor: PreviewActor,
        records_sha256: str,
    ) -> str:
        parameters = {
            "import.source-manifest": "sha256:" + str(state.manifest_sha256),
            "import.parser-configuration": fingerprint(
                {
                    "parserVersion": PARSER_VERSION,
                    "format": state.format_name,
                    "encoding": state.encoding,
                    "delimiter": session.delimiter,
                    "limits": asdict(session.limits),
                }
            ),
            "import.parse-result": fingerprint(
                {
                    "projectId": state.project_id,
                    "previewId": self._preview,
                    "jobId": claim.job_id,
                    "attemptId": claim.attempt_id,
                    "recordCount": session.record_count,
                    "recordsSha256": records_sha256,
                    "sourceSha256": state.source_sha256,
                    "complete": session.complete,
                }
            ),
        }
        with self._units() as unit:
            receipt = unit.aggregates.append(
                AggregateRevisionDraft(
                    revision_id=new_uuid_v7(),
                    aggregate_id=new_uuid_v7(),
                    aggregate_kind="workflow",
                    created_at=actor.occurred_at,
                    modified_at=actor.occurred_at,
                    display_label_observed="Local import preview parse",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                    dependency_coverage="complete",
                    material_dependencies=tuple(
                        MaterialDependency(
                            dependency_id=new_uuid_v7(),
                            dependency_kind="parameter-set",
                            relation_type="direct",
                            revision_id=None,
                            configuration_id=name,
                            configuration_version="1.0.0",
                            fingerprint=value,
                            governing_policy_id="dependency.material.v1",
                            governing_policy_version="1.0.0",
                        )
                        for name, value in parameters.items()
                    ),
                ),
                AtomicRepositoryEvent(
                    event_id=new_uuid_v7(),
                    outbox_id=new_uuid_v7(),
                    event_type="workflow.created",
                    occurred_at=actor.occurred_at,
                    available_at=actor.occurred_at,
                    trace_id=actor.trace_id,
                    actor_type="worker",
                    actor_id=actor.actor_id,
                    idempotency_key="import-preview-receipt-" + claim.attempt_id,
                ),
                expected_revision=None,
            )
            unit.commit()
        return receipt.revision_id

    def __call__(
        self,
        context: WorkflowActivityContext,
        claim: WorkflowJobClaim,
    ) -> tuple[WorkflowOutputReference, ...]:
        def actor() -> PreviewActor:
            return PreviewActor(actor_id=context.claim.worker_id, trace_id=self._trace, occurred_at=context.now())

        self._guard(context.cancellation_safe_point)
        state = self._guard(lambda: self._repository.read(self._preview))
        if state.project_id != claim.project_id or state.source_sha256 is None or state.manifest_sha256 is None:
            raise PreviewProblem("preview-activity-authority-mismatch")
        self._guard(lambda: self._repository.begin_parse(self._preview, claim=context.claim, actor=actor()))
        chunks = self._guard(lambda: self._repository.source_chunks(self._preview))
        source = ChunkedImportSource(self._store, chunks, authorize=self._rights)
        last_poll = last_heartbeat = self._clock()

        def poll(*, force: bool = False) -> bool:
            nonlocal last_poll, last_heartbeat
            now = self._clock()
            if force or now - last_poll >= 0.1:
                self._guard(context.cancellation_safe_point)
                last_poll = now
            if now - last_heartbeat >= min(5.0, context.lease_duration_ms / 3000):
                self._guard(
                    lambda: context.heartbeat(
                        {
                            "kind": "unknown",
                            "unit": "records",
                            "completedUnits": None,
                            "totalUnits": None,
                        }
                    )
                )
                last_heartbeat = now
            return False

        session = ImportSession(
            _GuardedSource(source, self._guard),
            ImportSource(state.source_name, state.source_sha256, state.encoding),
            state.format_name,
            delimiter=state.delimiter,
            cancelled=poll,
        )
        digest = hashlib.sha256(b'["import-preview-records/1",[')
        batch: list[ImportRecord] = []
        batch_bytes = 0
        count = 0

        def flush() -> None:
            nonlocal batch_bytes
            poll(force=True)
            self._guard(
                lambda: self._repository.append_records(
                    self._preview,
                    claim=context.claim,
                    records=tuple(batch),
                    actor=actor(),
                )
            )
            batch.clear()
            batch_bytes = 0

        try:
            for record in session.records():
                payload = StoredImportRecord.from_record(record).model_dump_json(by_alias=True).encode("utf-8")
                if len(payload) > 8 * 1024 * 1024:
                    raise WorkflowActivityError("import-record-limit")
                if batch and (len(batch) >= 100 or batch_bytes + len(payload) > 8 * 1024 * 1024):
                    flush()
                if count:
                    digest.update(b",")
                digest.update(payload)
                count += 1
                batch.append(record)
                batch_bytes += len(payload)
            if batch:
                flush()
            poll(force=True)
            if not session.complete or count != session.record_count:
                raise WorkflowActivityError("import-parse-incomplete")
            digest.update(b"]]")
            receipt = self._guard(lambda: self._receipt(state, session, context.claim, actor(), digest.hexdigest()))
            poll(force=True)
            output = self._guard(
                lambda: self._repository.finish_parse(
                    self._preview,
                    claim=context.claim,
                    session=session,
                    receipt_revision_id=receipt,
                    actor=actor(),
                )
            )
            return (output,)
        except ImportProblem as error:
            raise WorkflowActivityError("import-" + error.code) from None
        finally:
            source.close()
            batch.clear()
