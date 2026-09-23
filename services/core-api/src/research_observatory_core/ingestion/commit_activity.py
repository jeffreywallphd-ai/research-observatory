"""Guarded, paged preparation followed by atomic canonical import acceptance."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import partial

from ..ports.import_commits import ImportCommitRepository, ImportPublicationInterrupted
from ..ports.import_previews import ImportActionGuard, PreviewActor, PreviewProblem
from ..ports.workflow_executor import WorkflowJobClaim
from ..workflow_executor import WorkflowActivityContext, WorkflowActivityError, WorkflowAtomicCompletion
from .commit_workflow import CommitJobInput


class ImportCommitActivity:
    def __init__(
        self,
        *,
        inputs: CommitJobInput,
        repository: ImportCommitRepository,
        guard: ImportActionGuard,
        trace_id: str,
        clock: Callable[[], float] = time.monotonic,
        interrupted: Callable[[], bool] | None = None,
    ):
        self._inputs = CommitJobInput.model_validate(inputs)
        self._repository, self._guard = repository, guard
        self._trace, self._clock = trace_id, clock
        self._interrupted = interrupted

    def __call__(self, context: WorkflowActivityContext, claim: WorkflowJobClaim) -> WorkflowAtomicCompletion:
        def actor() -> PreviewActor:
            return PreviewActor(actor_id=context.claim.worker_id, trace_id=self._trace, occurred_at=context.now())

        last_heartbeat = self._clock()

        def poll(force_heartbeat: bool = False) -> None:
            nonlocal last_heartbeat
            if self._interrupted is not None and self._interrupted():
                raise ImportPublicationInterrupted()
            self._guard(context.cancellation_safe_point)
            current = self._clock()
            if force_heartbeat or current - last_heartbeat >= min(5.0, context.lease_duration_ms / 3000):
                self._guard(
                    lambda: context.heartbeat(
                        {"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None}
                    )
                )
                last_heartbeat = current

        inputs = self._inputs
        try:
            poll()
            self._guard(lambda: self._repository.begin_commit(inputs, claim=context.claim, actor=actor()))
            after = 0
            while after < inputs.record_count:
                poll()
                next_after = self._guard(
                    partial(
                        self._repository.append_commit_page, inputs, after=after, claim=context.claim, actor=actor()
                    )
                )
                if not after < next_after <= min(after + 100, inputs.record_count):
                    raise PreviewProblem("preview-commit-incomplete")
                after = next_after
            poll()
            output = self._repository.publish_commit(
                inputs,
                claim=context.claim,
                actor=actor(),
                now=context.now,
                poll=poll,
                guard=self._guard,
                lease_duration_ms=context.lease_duration_ms,
                interrupted=self._interrupted,
            )
            return WorkflowAtomicCompletion((output,))
        except PreviewProblem as error:
            code = str(error)
            if "rights" in code or "record-denied" in code:
                raise WorkflowActivityError("rights-denied") from None
            if any(reason in code for reason in ("revision", "authority", "mismatch", "resume", "closed")):
                raise WorkflowActivityError("stale-authority") from None
            raise WorkflowActivityError("import-commit-failed") from None
