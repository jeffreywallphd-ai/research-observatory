"""Provider-neutral dispatch and durable routing ports; no SDK or connection types."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any, Protocol

from ..model_gateway_contracts import ModelTaskSnapshot
from ..model_registry_contracts import ModelManifest
from ..model_routing_contracts import CancellationToken, CircuitState, RoutingEvent, RoutingRun


class ModelAdapterFailure(RuntimeError):
    """Portable classified failure; never retain a provider message or payload."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        permitted = {
            "temporarily-unavailable",
            "rate-limited",
            "provider-timeout",
            "provider-denied",
            "input-rejected",
            "runtime-failed",
            "output-invalid",
        }
        if code not in permitted or type(retryable) is not bool:
            raise ValueError("model adapter error classification is invalid")
        super().__init__(code)
        self.code = code
        self.retryable = retryable and code in {"temporarily-unavailable", "rate-limited", "provider-timeout"}


class ModelAdapter(Protocol):
    """Trusted composition only; execution results remain untrusted data.

    Adapters must yield during execution, obey the cancellation signal and expose
    bounded cancel/health operations. Blocking runtimes belong in supervised
    processes, not the Core event loop. No live adapter is installed in W1.
    """

    def describe(self) -> ModelManifest: ...

    async def health(self) -> bool: ...

    async def execute(
        self,
        task_spec: ModelTaskSnapshot,
        input_refs: tuple[Mapping[str, Any], ...],
        *,
        attempt_id: str,
        cancel_token: CancellationToken,
    ) -> object: ...

    async def cancel(self, attempt_id: str) -> None: ...


class ModelRoutingRepository(Protocol):
    def session(self) -> AbstractContextManager[None]:
        """One invocation's guarded connection, never a cross-call cache or transaction."""
        ...

    def atomic(self) -> AbstractContextManager[None]:
        """Group synchronous journal/circuit facts; never span adapter execution."""
        ...

    def read(self, task_id: str) -> RoutingRun | None: ...

    def admit(self, run: RoutingRun) -> tuple[RoutingRun, bool]: ...

    def append(self, task_id: str, *, expected_revision: int, event: RoutingEvent) -> RoutingRun: ...

    def circuit(self, manifest_hash: str) -> CircuitState: ...

    def change_circuit(
        self, state: CircuitState, *, expected_revision: int, expected_attempt_id: str | None = None
    ) -> CircuitState: ...
