"""Resolve corpus query lineage through protected, accepted connector history.

The preview ID is the persisted revision of the confirmed ConnectorJobInput.
It is a query revision only after the worker has re-established the exact
accepted page and its source assertion from retained local authority.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from .connectors.providers import ProviderProblem
from .corpus.membership import CorpusProblem
from .ports.repositories import RepositoryProblem
from .projects import ProjectLifecycleProblem
from .reconciliation.contracts import ReconciliationProblem, SourceAddress, SourceAssertion

if TYPE_CHECKING:
    from .connector_worker import ConnectorWorkerService


class ConnectorWorkerQueryResolver:
    """Adapt the worker's protected owner inventory to corpus discovery."""

    def __init__(self, worker: ConnectorWorkerService) -> None:
        self._worker = worker

    def __call__(self, root: str, address: SourceAddress, source: SourceAssertion) -> str:
        try:
            address = SourceAddress.model_validate(address)
            source = SourceAssertion.model_validate(source)
            if address.kind != "connector-record" or source.address != address:
                raise CorpusProblem("corpus-connector-query-unavailable")
            retained_address = SourceAddress.model_validate(
                self._worker.reconciliation_address(root, address.context_id, address.ordinal)
            )
            if retained_address != address:
                raise CorpusProblem("corpus-connector-query-unavailable")
            retained_source = SourceAssertion.model_validate(self._worker.reconciliation_source(root, retained_address))
            if retained_source != source:
                raise CorpusProblem("corpus-connector-query-unavailable")
        except (
            ReconciliationProblem,
            ProviderProblem,
            ProjectLifecycleProblem,
            RepositoryProblem,
            ValidationError,
            ValueError,
            TypeError,
        ):
            raise CorpusProblem("corpus-connector-query-unavailable") from None
        return address.context_id
