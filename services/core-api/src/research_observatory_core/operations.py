"""Bounded in-memory operation contract used by the local runtime seam."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock

from .models import OperationProgressEvent, OperationState, OperationStatus

MAX_RETAINED_EVENTS = 256
MAX_IDEMPOTENCY_RECORDS = 512


class OperationPreconditionFailed(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


class OperationReplayGap(ValueError):
    pass


@dataclass(slots=True)
class OperationRecord:
    operation_id: str
    kind: str
    trace_id: str
    state: OperationState = OperationState.QUEUED
    sequence: int = 0
    progress_percent: int = 0
    cancellation_requested: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events: list[OperationProgressEvent] = field(default_factory=list)

    def projection(self) -> OperationStatus:
        return OperationStatus(
            operation_id=self.operation_id,
            kind=self.kind,
            state=self.state,
            sequence=self.sequence,
            progress_percent=self.progress_percent,
            cancellation_requested=self.cancellation_requested,
            created_at=self.created_at,
            updated_at=self.updated_at,
            trace_id=self.trace_id,
        )

    @property
    def etag(self) -> str:
        return f'"{self.operation_id}-{self.sequence}"'

    def transition(self, state: OperationState, progress_percent: int) -> None:
        self.state = state
        self.progress_percent = progress_percent
        self.sequence += 1
        self.updated_at = datetime.now(UTC)
        self.events.append(
            OperationProgressEvent(
                operation_id=self.operation_id,
                sequence=self.sequence,
                state=state,
                progress_percent=progress_percent,
                terminal=state in {OperationState.SUCCEEDED, OperationState.FAILED, OperationState.CANCELLED},
                trace_id=self.trace_id,
            )
        )
        if len(self.events) > MAX_RETAINED_EVENTS:
            del self.events[: len(self.events) - MAX_RETAINED_EVENTS]


class OperationRegistry:
    """Thread-safe operation projections; durable workflow ownership arrives in CAP-03."""

    def __init__(self) -> None:
        self._records: dict[str, OperationRecord] = {}
        self._idempotency: dict[str, tuple[str, OperationStatus]] = {}
        self._lock = RLock()

    def add_fixture(self, record: OperationRecord) -> None:
        """Install a deterministic integration fixture without exposing a production create route."""

        with self._lock:
            if record.operation_id in self._records:
                raise ValueError("operation identity already exists")
            self._records[record.operation_id] = record

    def get(self, operation_id: str) -> OperationStatus | None:
        with self._lock:
            record = self._records.get(operation_id)
            return record.projection() if record is not None else None

    def etag(self, operation_id: str) -> str | None:
        with self._lock:
            record = self._records.get(operation_id)
            return record.etag if record is not None else None

    def page(self, *, after: str | None, limit: int) -> tuple[tuple[OperationStatus, ...], str | None]:
        with self._lock:
            identities = sorted(self._records)
            if after is not None:
                if after not in self._records:
                    raise ValueError("cursor is not an existing operation identity")
                identities = [identity for identity in identities if identity > after]
            selected = identities[:limit]
            next_cursor = selected[-1] if len(identities) > limit and selected else None
            return tuple(self._records[identity].projection() for identity in selected), next_cursor

    def cancel(self, operation_id: str, *, if_match: str, idempotency_key: str) -> OperationStatus | None:
        with self._lock:
            prior = self._idempotency.get(idempotency_key)
            if prior is not None:
                prior_operation_id, projection = prior
                if prior_operation_id != operation_id:
                    raise IdempotencyConflict("idempotency identity was already used for another operation")
                return projection
            record = self._records.get(operation_id)
            if record is None:
                return None
            if if_match != record.etag:
                raise OperationPreconditionFailed("operation revision does not match")
            if record.state in {OperationState.SUCCEEDED, OperationState.FAILED}:
                raise RuntimeError("terminal operation cannot be cancelled")
            if record.state is not OperationState.CANCELLED:
                record.cancellation_requested = True
                record.transition(OperationState.CANCELLED, record.progress_percent)
            projection = record.projection()
            self._idempotency[idempotency_key] = (operation_id, projection)
            if len(self._idempotency) > MAX_IDEMPOTENCY_RECORDS:
                del self._idempotency[next(iter(self._idempotency))]
            return projection

    def events(self, operation_id: str, *, after_sequence: int) -> tuple[OperationProgressEvent, ...] | None:
        with self._lock:
            record = self._records.get(operation_id)
            if record is None:
                return None
            if record.events and after_sequence < record.events[0].sequence - 1:
                raise OperationReplayGap("requested event position is outside retained history")
            return tuple(event for event in record.events if event.sequence > after_sequence)
