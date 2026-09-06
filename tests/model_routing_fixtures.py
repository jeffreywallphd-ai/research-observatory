"""Synthetic in-memory persistence for deterministic router tests only."""

from contextlib import nullcontext
from threading import RLock

from research_observatory_core.model_routing_contracts import CircuitState, RoutingEvent, RoutingRun
from research_observatory_core.ports.repositories import RepositoryConflict


class MemoryRoutingRepository:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.runs: dict[str, RoutingRun] = {}
        self.circuits: dict[str, CircuitState] = {}
        self.lock = RLock()

    def read(self, task_id: str) -> RoutingRun | None:
        with self.lock:
            return self.runs.get(task_id)

    def session(self):
        return nullcontext()

    def atomic(self):
        return self.lock

    def admit(self, run: RoutingRun) -> tuple[RoutingRun, bool]:
        with self.lock:
            run = RoutingRun.model_validate(run)
            if run.project_id != self.project_id:
                raise ValueError("project mismatch")
            prior = self.runs.get(run.task_id)
            if prior is not None:
                if prior.task_hash != run.task_hash or prior.policy != run.policy:
                    raise RepositoryConflict("request identity conflict")
                return prior, False
            self.runs[run.task_id] = run
            return run, True

    def append(self, task_id: str, *, expected_revision: int, event: RoutingEvent) -> RoutingRun:
        with self.lock:
            prior = self.runs[task_id]
            if prior.revision != expected_revision or prior.terminal:
                raise ValueError("routing revision conflict")
            result = RoutingRun.model_validate(prior.model_dump() | {"events": (*prior.events, event)})
            self.runs[task_id] = result
            return result

    def circuit(self, manifest_hash: str) -> CircuitState:
        with self.lock:
            return self.circuits.get(manifest_hash, CircuitState(manifest_hash=manifest_hash))

    def change_circuit(
        self, state: CircuitState, *, expected_revision: int, expected_attempt_id: str | None = None
    ) -> CircuitState:
        with self.lock:
            state = CircuitState.model_validate(state)
            if (
                self.circuit(state.manifest_hash).revision != expected_revision
                or state.revision != expected_revision + 1
                or self.circuit(state.manifest_hash).active_attempt_id != expected_attempt_id
            ):
                raise RepositoryConflict("circuit revision conflict")
            self.circuits[state.manifest_hash] = state
            return state
