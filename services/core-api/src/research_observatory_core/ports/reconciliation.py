"""Current-authority callback and canonical exact-reconciliation persistence port."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Protocol

from ..reconciliation.candidates import PreparedRecord
from ..reconciliation.contracts import ReconciliationInspection, ReconciliationResult, SourceAddress, SourceAssertion
from ..reconciliation.decisions import ReviewCommand, ReviewContext, ReviewOutcome, ReviewPlan, ReviewPreview
from ..reconciliation.inventory import SourcePage


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
    def prepared_record(self, revision_id: str, *, resolve: ReconciliationSourceResolver) -> PreparedRecord: ...

    def review_context(
        self, work_ids: tuple[str, ...], *, unassigned: tuple[str, ...] = (), resolve: ReconciliationSourceResolver
    ) -> ReviewContext: ...

    def preview_review(
        self, plan: ReviewPlan, *, actor: ReconciliationActor, resolve: ReconciliationSourceResolver
    ) -> ReviewPreview: ...

    def review(
        self, command: ReviewCommand, *, actor: ReconciliationActor, resolve: ReconciliationSourceResolver
    ) -> ReviewOutcome: ...

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
    def reconciliation_pages(
        self, root: str, job_id: str, *, limit: int = 100, checkpoint: Callable[[], None] | None = None
    ) -> Iterator[SourcePage]: ...

    def reconciliation_sources(self, root: str, job_id: str, *, after: int, limit: int = 100) -> SourcePage: ...

    def reconciliation_source(self, root: str, address: SourceAddress) -> SourceAssertion: ...


class ReconciliationConnectorSourceService(ReconciliationSourceService, Protocol):
    def reconciliation_address(self, root: str, preview_id: str, ordinal: int) -> SourceAddress: ...
