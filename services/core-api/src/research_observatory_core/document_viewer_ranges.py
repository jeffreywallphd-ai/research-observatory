"""Owned, bounded original reads; authority and delivery belong to the service.

One worker owns all read callbacks, so a cancelled HTTP waiter cannot strand a
read needed by another identical request. No stream, transaction or plaintext
cache lives here. Only a completed, at-most-1-MiB result is shared briefly.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from .ports.object_store import (
    MAX_VIEWER_RANGE_BYTES,
    MAX_VIEWER_SOURCE_BYTES,
    ObjectReadCancelled,
    ObjectStoreProblem,
)

_MAX_WAITING_REQUESTS = 8
_MAX_TOTAL_REQUESTS = 64
_STOP_POLL_SECONDS = 0.01


class ViewerRangeProblem(RuntimeError):
    """Fixed, content-free viewer admission failure."""


@dataclass(frozen=True, slots=True)
class ViewerRangeKey:
    project_id: str
    session_id: str
    authority_sha256: str
    source_sha256: str
    attachment_id: str
    document_revision_id: str
    start: int
    end: int

    def validate(self) -> None:
        identities = (
            self.project_id,
            self.session_id,
            self.authority_sha256,
            self.source_sha256,
            self.attachment_id,
            self.document_revision_id,
        )
        if (
            any(type(value) is not str or not 1 <= len(value) <= 128 for value in identities)
            or type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end <= MAX_VIEWER_SOURCE_BYTES
            or self.end - self.start > MAX_VIEWER_RANGE_BYTES
        ):
            raise ViewerRangeProblem("viewer-range-invalid")


@dataclass(slots=True)
class _Member:
    signal: Callable[[], bool]
    cancelled: threading.Event = field(default_factory=threading.Event)

    def stopped(self) -> bool:
        if not self.cancelled.is_set():
            try:
                if self.signal() is not False:
                    self.cancelled.set()
            except Exception:
                self.cancelled.set()
        return self.cancelled.is_set()


@dataclass(slots=True)
class _Group:
    key: ViewerRangeKey
    read: Callable[[Callable[[], bool]], bytes]
    members: dict[tuple[str, str, str], _Member] = field(default_factory=dict)
    done: bool = False
    value: bytes | None = None
    error: type[ObjectStoreProblem] | None = None
    problem: str | None = None


class DocumentViewerRangePool:
    """At most one active read per project, eight waiters and exact coalescing.

    This implementation deliberately owns one worker across projects. Request
    signals must be trusted non-I/O latches, never nested authority/DB actions.
    The caller validates current authority before admission and after return.
    Cancellation denies a waiter's delivery immediately; ``drain`` separately
    establishes whether the actual owner has closed its live read.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition(threading.RLock())
        self._requests: dict[tuple[str, str, str], tuple[_Group, _Member]] = {}
        self._groups: dict[ViewerRangeKey, _Group] = {}
        self._queue: deque[_Group] = deque()
        self._active: _Group | None = None
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def pending_count(self, project_id: str) -> int:
        with self._condition:
            return sum(identity[0] == project_id for identity in self._requests)

    def _group_stopped(self, group: _Group) -> bool:
        with self._condition:
            return self._stopped.is_set() or not any(not member.stopped() for member in group.members.values())

    def read(
        self,
        key: ViewerRangeKey,
        request_id: str,
        read: Callable[[Callable[[], bool]], bytes],
        *,
        cancellation_requested: Callable[[], bool] = lambda: False,
    ) -> bytes:
        key.validate()
        if (
            type(request_id) is not str
            or not 1 <= len(request_id) <= 128
            or not callable(read)
            or not callable(cancellation_requested)
        ):
            raise ViewerRangeProblem("viewer-request-invalid")
        identity = (key.project_id, key.session_id, request_id)
        member = _Member(cancellation_requested)
        with self._condition:
            if self._stopped.is_set() or member.stopped():
                raise ObjectReadCancelled()
            if identity in self._requests:
                raise ViewerRangeProblem("viewer-request-conflict")
            active_for_project = self._active is not None and self._active.key.project_id == key.project_id
            if len(self._requests) >= _MAX_TOTAL_REQUESTS or self.pending_count(
                key.project_id
            ) >= _MAX_WAITING_REQUESTS + int(active_for_project):
                raise ViewerRangeProblem("viewer-queue-full")
            group = self._groups.get(key)
            if group is None:
                group = _Group(key, read)
                self._groups[key] = group
                self._queue.append(group)
            group.members[identity] = member
            self._requests[identity] = (group, member)
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="document-viewer-ranges", daemon=True)
                self._thread.start()
            self._condition.notify_all()
            try:
                while not group.done and not member.stopped() and not self._stopped.is_set():
                    self._condition.wait(_STOP_POLL_SECONDS)
                if member.stopped() or self._stopped.is_set():
                    raise ObjectReadCancelled()
                if group.error is not None:
                    raise group.error("viewer source read denied")
                if group.problem is not None:
                    raise ViewerRangeProblem(group.problem)
                if group.value is None:
                    raise ViewerRangeProblem("viewer-response-invalid")
                return group.value
            finally:
                # A cancelled participant may hand ownership to a live exact
                # follower. The last participant cannot settle while its actual
                # callback still owns the encrypted stream/transaction. Queued
                # groups have acquired neither and can be cancelled immediately.
                while (
                    not group.done
                    and self._active is group
                    and (
                        self._stopped.is_set()
                        or not any(other is not member and not other.stopped() for other in group.members.values())
                    )
                ):
                    self._condition.wait(_STOP_POLL_SECONDS)
                self._requests.pop(identity, None)
                group.members.pop(identity, None)
                if not group.members:
                    group.value = None
                self._condition.notify_all()

    def cancel(self, project_id: str, session_id: str, request_id: str) -> bool:
        """Cancel only an existing exact native-session/request registration."""
        with self._condition:
            request = self._requests.get((project_id, session_id, request_id))
            if request is None:
                return False
            request[1].cancelled.set()
            self._condition.notify_all()
            return True

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._queue and not self._stopped.is_set():
                    self._condition.wait()
                if not self._queue:
                    return
                group = self._queue.popleft()
                self._active = group
            value = None
            error = None
            problem = None
            try:
                if self._group_stopped(group):
                    raise ObjectReadCancelled()

                def group_cancelled(selected: _Group = group) -> bool:
                    return self._group_stopped(selected)

                value = group.read(group_cancelled)
                if self._group_stopped(group):
                    raise ObjectReadCancelled()
                if type(value) is not bytes or len(value) != group.key.end - group.key.start:
                    raise ViewerRangeProblem("viewer-response-invalid")
            except ObjectStoreProblem as failure:
                error = type(failure)
                value = None
            except ViewerRangeProblem as failure:
                problem = str(failure)
                value = None
            except Exception:
                problem = "viewer-source-read-failed"
                value = None
            finally:
                with self._condition:
                    group.value, group.error, group.problem = value, error, problem
                    group.done = True
                    self._groups.pop(group.key, None)
                    self._active = None
                    self._condition.notify_all()
                # The callback must already have closed its stream/transaction.
                # Yield scheduling between operations; the project lifecycle's
                # FIFO action mutex gives waiting metadata commands precedence.
                time.sleep(0)

    def drain(self, *, timeout: float = 1.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._active is not None or self._queue:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(min(remaining, _STOP_POLL_SECONDS))
            return True

    def close(self, *, timeout: float = 1.0) -> bool:
        """Deny every delivery, cooperatively cancel owners and report real drain."""
        self._stopped.set()
        with self._condition:
            self._condition.notify_all()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        return thread is None or not thread.is_alive()
