"""Trusted Core composition seams; none of these values is a caller egress grant."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from ..connectors.contracts import ConnectorRequest, ConnectorResultPage

if TYPE_CHECKING:
    from ..connectors.workflow import ConnectorJobInput
    from .workflow_executor import WorkflowOutputReference

type ConnectorStage = Literal["admission", "cache", "dispatch", "publication"]


@dataclass(frozen=True, slots=True)
class ConnectorAuthorityStamp:
    """Revalidated by Core under its project lock, never accepted from an API DTO."""

    project_id: str
    session_id: str = field(repr=False)
    intent_revision_id: str
    intent_sha256: str
    policy_sha256: str
    confirmation_sha256: str
    rights_sha256: str
    retain_body: bool
    actor_id: str
    expected_checkpoint_revision_id: str | None = None
    permitted_fields: tuple[str, ...] = ()


class ConnectorAuthority(Protocol):
    def guard[Result](
        self,
        request: ConnectorRequest,
        stage: ConnectorStage,
        action: Callable[[ConnectorAuthorityStamp], Result],
    ) -> Result:
        """Deny unless current project/session, Intent, policy, rights and exact
        confirmed payload permit this action. Hold the authority lock through
        bounded synchronous I/O. Never hold it across remote network waits.
        """
        ...


@dataclass(frozen=True, slots=True)
class ConnectorCacheEntry:
    project_id: str
    page_sha256: str
    body: bytes = field(repr=False)
    retrieved_at: str
    validated_at: str
    etag: str | None = field(repr=False)
    last_modified: str | None = field(repr=False)


class ConnectorPageRepository(Protocol):
    def replay(self, request: ConnectorRequest) -> ConnectorResultPage | None: ...

    def checkpoint(self, request: ConnectorRequest) -> tuple[str, ConnectorResultPage] | None: ...

    def cached(self, request: ConnectorRequest) -> ConnectorCacheEntry | None: ...

    def publish(
        self,
        page: ConnectorResultPage,
        *,
        body: bytes | None,
        etag: str | None,
        last_modified: str | None,
        authority: ConnectorAuthorityStamp,
    ) -> ConnectorResultPage:
        """Atomically accept immutable observations/response references and CAS
        the completed-page checkpoint; failed/partial pages cannot advance it.
        Identical invocation replay returns its prior observation; collisions deny.
        """
        ...


class ConnectorOperationRepository(ConnectorPageRepository, Protocol):
    def save_operation(self, inputs: ConnectorJobInput, *, actor_id: str, now: str) -> None: ...

    def operation(self, revision_id: str) -> ConnectorJobInput: ...

    def output_reference(self, request: ConnectorRequest) -> WorkflowOutputReference: ...
