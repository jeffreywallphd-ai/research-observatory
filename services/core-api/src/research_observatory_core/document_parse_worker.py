"""One admitted parser activity with a live lease and lock-free stop latch."""

from __future__ import annotations

import threading
from collections.abc import Callable

from .ports.document_revisions import DocumentRevisionWorkerRepository
from .workflow_executor import (
    ActivityWorkerDemand,
    ProjectWorkerPolicy,
    WorkerResources,
    WorkflowActivityError,
    WorkflowAtomicCompletion,
    WorkflowCancellationRequested,
)


def document_worker_policy(project_id: str) -> ProjectWorkerPolicy:
    """All Core document-lane adapters share one immutable project policy."""
    metadata = WorkerResources(1, 256 * 1024**2, 0, 1024**3)
    parser = WorkerResources(4, 4 * 1024**3, 0, 1024**3)
    return ProjectWorkerPolicy(
        project_id,
        parser,
        {"document": metadata},
        {"document": 1},
        activity_demands={"document-parse": ActivityWorkerDemand("document", parser, exclusive=True)},
    )


class DocumentParseActivity:
    def __init__(
        self,
        repository: DocumentRevisionWorkerRepository,
        *,
        session_stopped: Callable[[], bool],
        runtime=None,
        heartbeat_seconds: float = 2.0,
    ) -> None:
        if not callable(session_stopped) or not 0.25 <= heartbeat_seconds <= 5.0:
            raise ValueError("document parser heartbeat configuration invalid")
        self.repository, self.session_stopped = repository, session_stopped
        self.runtime, self.heartbeat_seconds = runtime, heartbeat_seconds

    def __call__(self, context, claim) -> WorkflowAtomicCompletion:
        stopped, finished = threading.Event(), threading.Event()
        lease_failures = []
        inputs = self.repository.claim_input(claim)
        request = inputs.request(claim)

        def pulse():
            # Never passed into a canonical writer or a worker callback.
            if self.session_stopped():
                stopped.set()
                return
            context.cancellation_safe_point()
            context.heartbeat({"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None})

        def monitor():
            while not finished.wait(self.heartbeat_seconds):
                try:
                    pulse()
                except Exception as error:
                    lease_failures.append(error)
                    stopped.set()
                    return

        pulse()
        pipeline = self.repository.parser_pipeline(context, request, self.runtime)
        heartbeat = threading.Thread(target=monitor, name="ro-document-lease", daemon=True)
        heartbeat.start()
        try:
            result = pipeline.stage(request, actor=self.repository.actor(), cancelled=stopped.is_set)
        finally:
            finished.set()
            heartbeat.join(timeout=6)
        if heartbeat.is_alive() or lease_failures or stopped.is_set() or self.session_stopped():
            stopped.set()
            context.cancellation_safe_point()
            raise WorkflowActivityError("stale-authority")
        if result.kind == "cancelled":
            raise WorkflowCancellationRequested("document parse cancelled")
        if result.kind != "success":
            raise WorkflowActivityError(result.code)
        # Refresh once after inference and stop the monitor before the sole
        # normalized-result writer. In-writer predicates only read this latch.
        pulse()
        if stopped.is_set():
            raise WorkflowActivityError("stale-authority")
        _, completion = self.repository.retain(context.claim, request, result, stopped=stopped.is_set)
        return completion
