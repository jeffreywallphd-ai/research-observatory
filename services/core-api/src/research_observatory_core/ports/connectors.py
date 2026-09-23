"""Provider-neutral ports; implementations receive no reusable authentication.

Core composition must inject only a governed broker, not a raw HTTP client or
credential lease. Its policy/configuration checks, redaction, actual rate/cache
enforcement and accepted-page checkpoint publication are separate runtime duties.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..connectors.contracts import ConnectorCapabilities, ConnectorError, ConnectorRequest, ConnectorResultPage


@runtime_checkable
class ConnectorCancellation(Protocol):
    @property
    def cancelled(self) -> bool: ...


class ConnectorFailure(RuntimeError):
    """Only a validated classification; never accept a provider exception message."""

    def __init__(self, error: ConnectorError) -> None:
        self.error = ConnectorError.model_validate(error)
        super().__init__(self.error.code)


@runtime_checkable
class ConnectorAdapter(Protocol):
    def describe(self) -> ConnectorCapabilities: ...

    async def fetch(self, request: ConnectorRequest, *, cancellation: ConnectorCancellation) -> ConnectorResultPage:
        """One bounded page, never an automatically exhaustive search.

        A returned cursor is provisional until Core atomically accepts the page's
        observations and protected response references. Current project/intent/
        rights/egress authority is required again on retry, cache read and resume.
        A partial or failed page must never advance a completed-page checkpoint.
        """
        ...
