"""One existing-queue activity owns lawful index preparation and search execution."""

import threading

from .ports.lexical_search import SearchActivityRepository
from .workflow_executor import WorkflowActivityError


class LexicalSearchActivity:
    def __init__(self, repository: SearchActivityRepository, *, session_stopped, heartbeat_seconds=2.0):
        if not callable(session_stopped) or not 0.25 <= heartbeat_seconds <= 5.0:
            raise ValueError("search heartbeat configuration is invalid")
        self.repository, self.session_stopped = repository, session_stopped
        self.heartbeat_seconds = heartbeat_seconds

    def __call__(self, context, claim):
        stopped, finished = threading.Event(), threading.Event()
        failures = []
        inputs = self.repository.claim_input(claim)

        def pulse():
            if self.session_stopped():
                stopped.set()
                raise WorkflowActivityError("stale-authority")
            context.cancellation_safe_point()
            context.heartbeat({"kind": "unknown", "unit": "records", "completedUnits": None, "totalUnits": None})

        def monitor():
            while not finished.wait(self.heartbeat_seconds):
                try:
                    pulse()
                except Exception as error:
                    failures.append(error)
                    stopped.set()
                    return

        def cancelled():
            return stopped.is_set() or self.session_stopped()

        pulse()
        heartbeat = threading.Thread(target=monitor, name="ro-search-lease", daemon=True)
        heartbeat.start()
        try:
            self.repository.prepare(cancelled=cancelled)

            def before_publish():
                # The monitor ends before the sole canonical output writer.
                # That writer renews/checks its own fenced attempt capability.
                finished.set()
                heartbeat.join(timeout=6)
                if heartbeat.is_alive() or failures or cancelled():
                    context.cancellation_safe_point()
                    raise WorkflowActivityError("stale-authority")
                pulse()

            return self.repository.run_query(
                context.claim,
                inputs,
                before_publish=before_publish,
                cancelled=cancelled,
            )
        finally:
            finished.set()
            heartbeat.join(timeout=6)
            if heartbeat.is_alive():
                raise WorkflowActivityError("worker-drain-pending")
