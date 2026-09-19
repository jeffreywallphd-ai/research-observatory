"""Bounded fixed-draft worker; no canonical records, network or model calls."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import partial

from ..domain_contracts import new_uuid_v7
from ..ports.import_previews import ImportPreviewRepository, PreviewActor, PreviewProblem
from ..ports.repositories import AggregateRevisionDraft, AtomicRepositoryEvent, MaterialDependency, UnitOfWorkFactory
from ..ports.workflow_executor import WorkflowJobClaim, WorkflowOutputReference
from ..workflow_executor import WorkflowActivityContext, WorkflowActivityError
from .import_summaries import SummaryResult, summary_receipt_fingerprint
from .preview_activity import ImportActionGuard
from .summary_workflow import SummaryJobInput


class ImportSummaryActivity:
    def __init__(
        self,
        *,
        inputs: SummaryJobInput,
        repository: ImportPreviewRepository,
        unit_of_work: UnitOfWorkFactory,
        guard: ImportActionGuard,
        trace_id: str,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._inputs, self._repository = SummaryJobInput.model_validate(inputs), repository
        self._units, self._guard, self._trace, self._clock = unit_of_work, guard, trace_id, clock

    def _receipt(self, result: SummaryResult, claim: WorkflowJobClaim, actor: PreviewActor) -> str:
        inputs = self._inputs
        binding = summary_receipt_fingerprint(
            project_id=inputs.project_id,
            preview_id=inputs.preview.preview_id,
            job_id=claim.job_id,
            summary_attempt_id=claim.attempt_id,
            parse_attempt_id=inputs.parse_attempt_id,
            draft_revision=inputs.draft_revision,
            source_sha256=inputs.preview.source_sha256,
            manifest_sha256=inputs.preview.manifest_sha256,
            result=result,
        )
        with self._units() as unit:
            receipt = unit.aggregates.append(
                AggregateRevisionDraft(
                    revision_id=new_uuid_v7(),
                    aggregate_id=new_uuid_v7(),
                    aggregate_kind="workflow",
                    created_at=actor.occurred_at,
                    modified_at=actor.occurred_at,
                    display_label_observed="Local import draft summary",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                    dependency_coverage="complete",
                    material_dependencies=(
                        MaterialDependency(
                            dependency_id=new_uuid_v7(),
                            dependency_kind="parameter-set",
                            relation_type="direct",
                            revision_id=None,
                            configuration_id="import.draft-summary",
                            configuration_version="1.0.0",
                            fingerprint=binding,
                            governing_policy_id="dependency.material.v1",
                            governing_policy_version="1.0.0",
                        ),
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
                    idempotency_key="import-summary-receipt-" + claim.attempt_id,
                ),
                expected_revision=None,
            )
            unit.commit()
        return receipt.revision_id

    def __call__(
        self, context: WorkflowActivityContext, claim: WorkflowJobClaim
    ) -> tuple[WorkflowOutputReference, ...]:
        def actor() -> PreviewActor:
            return PreviewActor(actor_id=context.claim.worker_id, trace_id=self._trace, occurred_at=context.now())

        last_heartbeat = self._clock()

        def poll() -> None:
            nonlocal last_heartbeat
            self._guard(context.cancellation_safe_point)
            now = self._clock()
            if now - last_heartbeat >= min(5.0, context.lease_duration_ms / 3000):
                self._guard(
                    lambda: context.heartbeat(
                        {"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None}
                    )
                )
                last_heartbeat = now

        inputs, preview = self._inputs, self._inputs.preview.preview_id
        try:
            poll()
            self._guard(
                lambda: self._repository.begin_summary(
                    preview, revision=inputs.draft_revision, claim=context.claim, actor=actor()
                )
            )
            after = 0
            while after < inputs.record_count:
                poll()
                rows = self._guard(
                    partial(
                        self._repository.append_summary_page,
                        preview,
                        revision=inputs.draft_revision,
                        after=after,
                        claim=context.claim,
                        actor=actor(),
                    )
                )
                if not rows or rows[0].ordinal != after + 1 or rows[-1].ordinal > inputs.record_count:
                    raise PreviewProblem("preview-summary-incomplete")
                after = rows[-1].ordinal
            poll()
            result = self._guard(lambda: self._repository.summary_result(preview, claim=context.claim, actor=actor()))
            poll()
            receipt = self._guard(lambda: self._receipt(result, context.claim, actor()))
            poll()
            output = self._guard(
                lambda: self._repository.finish_summary(
                    preview, claim=context.claim, result=result, receipt_revision_id=receipt, actor=actor()
                )
            )
            return (output,)
        except PreviewProblem as error:
            code = str(error)
            if "rights" in code or "record-denied" in code:
                raise WorkflowActivityError("rights-denied") from None
            if any(reason in code for reason in ("revision", "authority", "mismatch", "resume", "closed")):
                raise WorkflowActivityError("stale-authority") from None
            raise WorkflowActivityError("import-summary-failed") from None
