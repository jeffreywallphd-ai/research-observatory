"""Provider-bound public adapters receive only the governed Core broker."""

from __future__ import annotations

from ..ports.connectors import ConnectorAdapter, ConnectorCancellation, ConnectorFailure
from .broker import ConnectorBroker
from .contracts import ConnectorCapabilities, ConnectorError, ConnectorRequest, ConnectorResultPage
from .providers import HOSTS, capabilities


class ScholarlyAdapter:
    def __init__(self, provider: str, broker: ConnectorBroker):
        self._capabilities = capabilities(provider)
        self._broker = broker

    def describe(self) -> ConnectorCapabilities:
        return self._broker.describe(self._capabilities.provider_id)

    async def fetch(self, request: ConnectorRequest, *, cancellation: ConnectorCancellation) -> ConnectorResultPage:
        request = ConnectorRequest.model_validate(request)
        if request.provider_id != self._capabilities.provider_id:
            raise ConnectorFailure(ConnectorError(code="invalid-query", retryable=False, retry_after_ms=None))
        return await self._broker.fetch(request, cancellation=cancellation)


def scholarly_adapters(broker: ConnectorBroker) -> tuple[ConnectorAdapter, ...]:
    return tuple(ScholarlyAdapter(provider, broker) for provider in HOSTS)
