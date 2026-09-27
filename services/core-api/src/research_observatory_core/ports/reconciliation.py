"""Current-authority callback and canonical exact-reconciliation persistence port."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Literal, Protocol

from ..reconciliation.batch import BatchInput
from ..reconciliation.candidate_sets import CandidateExplanation, CandidateSetContent
from ..reconciliation.candidate_views import CandidatePage
from ..reconciliation.candidates import PreparedRecord
from ..reconciliation.contracts import ReconciliationInspection, ReconciliationResult, SourceAddress, SourceAssertion
from ..reconciliation.decisions import ReviewCommand, ReviewContext, ReviewOutcome, ReviewPlan, ReviewPreview
from ..reconciliation.inventory import SourcePage
from .workflow_executor import WorkflowJobClaim, WorkflowOutputReference


@dataclass(frozen=True, slots=True)
class ReconciliationActor:
    actor_id: str
    trace_id: str
    occurred_at: str
    intent_sha256: str
    policy_sha256: str
    actor_type: Literal["human", "worker"] = "human"


class ReconciliationSourceResolver(Protocol):
    def __call__(self, address: SourceAddress) -> SourceAssertion:
        """Resolve trusted data and CURRENT action rights under the project fence."""
        ...


class ReconciliationRepository(Protocol):
    def advance_review_impacts(self) -> bool:
        """Advance one persisted review-impact checkpoint under the project fence."""
        ...

    def batch_request(self, request_id: str) -> BatchInput | None: ...

    def save_batch_request(self, inputs: BatchInput, *, actor: ReconciliationActor) -> BatchInput: ...

    def publish_batch(
        self,
        inputs: BatchInput,
        addresses: tuple[SourceAddress, ...],
        *,
        claim: WorkflowJobClaim,
        actor: ReconciliationActor,
        resolve: ReconciliationSourceResolver,
        now: Callable[[], str],
        interrupted: Callable[[], bool] | None = None,
        lease_duration_ms: int = 30000,
    ) -> WorkflowOutputReference: ...

    def candidate_set(self, revision_id: str, *, resolve: ReconciliationSourceResolver) -> CandidateSetContent: ...

    def inspect_candidates(
        self, revision_id: str, *, after: int, limit: int, resolve: ReconciliationSourceResolver
    ) -> CandidatePage: ...

    def candidate_pairs(
        self,
        revision_id: str,
        *,
        after: int,
        limit: int,
        resolve: ReconciliationSourceResolver,
    ) -> tuple[CandidateExplanation, ...]: ...

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
