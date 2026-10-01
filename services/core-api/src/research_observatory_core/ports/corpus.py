"""Protected corpus command port; source and actor facts come from Core only.

The repository performs replay lookup and current-head validation inside one
writer transaction before invoking a pure builder. A replay returns its exact
prior result without minting any new durable IDs. It must validate prepared
source, Work, protocol, evidence, provenance and outbox facts atomically.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from ..corpus.membership import CorpusDecision, CorpusItemRevision, DiscoveryPath
from ..reconciliation.contracts import SourceAddress, SourceAssertion


@dataclass(frozen=True, slots=True)
class CorpusActor:
    actor_id: str
    trace_id: str
    occurred_at: str
    intent_revision_id: str
    intent_sha256: str
    policy_sha256: str
    actor_type: Literal["human"] = "human"


class CorpusConnectorQueryResolver(Protocol):
    def __call__(self, root: str, address: SourceAddress, source: SourceAssertion) -> str:
        """Return a trusted query revision from the retained connector run."""
        ...


class CorpusRepository(Protocol):
    def create(
        self,
        *,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        source: SourceAssertion,
        build: Callable[[], tuple[CorpusItemRevision, DiscoveryPath]],
    ) -> CorpusItemRevision: ...

    def create_citation(
        self,
        *,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        work_id: str,
        work_revision_id: str,
        citing_work_id: str,
        citing_work_revision_id: str,
        source_assertion_revision_id: str,
        build: Callable[[], tuple[CorpusItemRevision, DiscoveryPath]],
    ) -> CorpusItemRevision:
        """Create a candidate from a human-attested citation discovery edge."""
        ...

    def decide(
        self,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        build: Callable[[CorpusItemRevision], CorpusDecision],
    ) -> CorpusItemRevision: ...

    def add_path(
        self,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        source: SourceAssertion,
        build: Callable[[CorpusItemRevision], tuple[DiscoveryPath, CorpusDecision]],
    ) -> CorpusItemRevision: ...

    def add_citation_path(
        self,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        citing_work_id: str,
        citing_work_revision_id: str,
        source_assertion_revision_id: str,
        build: Callable[[CorpusItemRevision], tuple[DiscoveryPath, CorpusDecision]],
    ) -> CorpusItemRevision:
        """Validate retained citing Work/assertion before a human-attested path is published."""
        ...

    def rebind(
        self,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
        build: Callable[[CorpusItemRevision], CorpusDecision],
    ) -> CorpusItemRevision: ...

    def inspect(self, item_id: str, *, actor: CorpusActor) -> CorpusItemRevision:
        """Return content-free item state/IDs, not source text or copy access."""
        ...

    def history(
        self, item_id: str, *, actor: CorpusActor
    ) -> tuple[tuple[CorpusItemRevision, tuple[DiscoveryPath, ...], CorpusDecision | None], ...]:
        """Return validated revisions oldest first, with their paths and decision."""
        ...
