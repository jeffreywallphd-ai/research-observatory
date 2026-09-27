"""Current-authority callback and canonical exact-reconciliation persistence port."""

from dataclasses import dataclass
from typing import Protocol

from ..reconciliation.contracts import ReconciliationInspection, ReconciliationResult, SourceAddress, SourceAssertion


@dataclass(frozen=True, slots=True)
class ReconciliationActor:
    actor_id: str
    trace_id: str
    occurred_at: str
    intent_sha256: str
    policy_sha256: str


class ReconciliationSourceResolver(Protocol):
    def __call__(self, address: SourceAddress) -> SourceAssertion:
        """Resolve trusted data and CURRENT action rights under the project fence."""
        ...


class ReconciliationRepository(Protocol):
    def reconcile(
        self,
        source: SourceAddress,
        *,
        command_id: str,
        actor: ReconciliationActor,
        resolve: ReconciliationSourceResolver,
    ) -> ReconciliationResult: ...

    def inspect(
        self,
        revision_id: str,
        *,
        resolve: ReconciliationSourceResolver,
    ) -> ReconciliationInspection: ...


class ReconciliationSourceService(Protocol):
    def reconciliation_source(self, root: str, address: SourceAddress) -> SourceAssertion: ...


class ReconciliationConnectorSourceService(ReconciliationSourceService, Protocol):
    def reconciliation_address(self, root: str, preview_id: str, ordinal: int) -> SourceAddress: ...
