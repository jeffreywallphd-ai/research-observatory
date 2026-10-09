"""Fresh native/Core inspection authority around each bounded original request."""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field

from .document_revisions import DocumentRevisionProblem
from .document_viewer_ranges import DocumentViewerRangePool, ViewerRangeKey, ViewerRangeProblem
from .ports.object_store import ObjectReadCancelled


def _principal(actor):
    return (actor.actor_id, actor.actor_type, actor.intent_revision_id, actor.intent_sha256, actor.policy_sha256)


def _sha(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


@dataclass(slots=True)
class _Request:
    root: str
    stop: threading.Event = field(default_factory=threading.Event)
    session_stop: Callable[[], bool] = lambda: False
    transport_stop: Callable[[], bool] = lambda: False

    def stopped(self) -> bool:
        try:
            return self.stop.is_set() or self.session_stop() is not False or self.transport_stop() is not False
        except Exception:
            return True


class DocumentViewerService:
    def __init__(self, attachments, imports, *, repository_factory) -> None:
        self.attachments, self.imports = attachments, imports
        self.repository_factory = repository_factory
        self.ranges = DocumentViewerRangePool()
        self._mutex = threading.Condition(threading.Lock())
        self._requests: dict[tuple[str, str, str], _Request] = {}
        self._terminal: OrderedDict[tuple[str, str, str], str] = OrderedDict()
        self._early_cancellations: dict[tuple[str, str, str], str] = {}
        self._cancel_overflow = False
        self._stopped = threading.Event()

    def _scoped(self, command, trace, action, *, request: _Request | None = None):
        session_stop: list[Callable[[], bool]] = [lambda: True]

        def scoped(selected, actor):
            active = [True]
            stop = session_stop[0]
            if request is not None:
                request.session_stop = stop

            def stopped():
                return self._stopped.is_set() or stop() or (request is not None and request.stopped())

            def guard(read):
                if not active[0] or stopped():
                    raise ObjectReadCancelled()
                return read()

            repository = self.repository_factory(
                selected._database,
                command.project_id,
                selected._objects,
                actor=lambda: guard(lambda: actor),
                guard=guard,
                now=lambda: actor.occurred_at,
            )
            try:
                result = guard(lambda: action(repository, actor, stopped))
                if stopped():
                    raise ObjectReadCancelled()
                return result
            finally:
                active[0] = False

        return self.attachments._action(
            command.root,
            command.project_id,
            command.session_id,
            trace,
            scoped,
            session_stop=lambda stop: session_stop.__setitem__(0, stop),
            reuse_native_store=True,
        )

    def describe(self, command, *, trace_id):
        return self._scoped(
            command,
            trace_id,
            lambda repository, _actor, stopped: repository.describe(command.selector, cancellation_requested=stopped),
        )

    def text_chunk(self, command, *, trace_id):
        return self._scoped(
            command,
            trace_id,
            lambda repository, _actor, _stopped: repository.text_chunk(
                command.selector, node_id=command.node_id, offset=command.offset
            ),
        )

    def outline(self, command, *, trace_id):
        return self._scoped(
            command,
            trace_id,
            lambda repository, _actor, _stopped: repository.outline(
                command.selector, after_node_id=command.after_node_id
            ),
        )

    def read_range(self, command, *, trace_id, cancellation_requested: Callable[[], bool] = lambda: False):
        identity = (command.project_id, command.session_id, command.request_id)
        request = _Request(command.root, transport_stop=cancellation_requested)
        # Register before waiting for project authority. A concurrent native
        # cancellation cannot be lost while the initial metadata guard waits.
        with self._mutex:
            if self._stopped.is_set() or self._cancel_overflow:
                raise ObjectReadCancelled()
            if identity in self._requests or identity in self._terminal:
                raise ViewerRangeProblem("viewer-request-conflict")
            if len(self._requests) >= 64:
                raise ViewerRangeProblem("viewer-queue-full")
            self._requests[identity] = request
            if self._early_cancellations.get(identity) == command.root:
                request.stop.set()
                self._early_cancellations.pop(identity)
            self._mutex.notify_all()
        try:
            metadata, principal = self._scoped(
                command,
                trace_id,
                lambda repository, actor, stopped: (
                    repository.describe(command.selector, cancellation_requested=stopped),
                    _principal(actor),
                ),
                request=request,
            )
            key = ViewerRangeKey(
                command.project_id,
                command.session_id,
                _sha(principal),
                _sha(metadata.model_dump(mode="json", by_alias=True)),
                metadata.source.attachment_id,
                metadata.source.document_revision_id,
                command.start,
                command.end,
            )

            def owned_read(cancelled):
                def current(repository, actor, stopped):
                    def stop():
                        return stopped() or cancelled()

                    if _principal(actor) != principal:
                        raise DocumentRevisionProblem("viewer-authority-changed")
                    # Do not replay identical metadata descriptions around the
                    # physical read. This fresh scope and the encrypted writer
                    # establish current authority; each waiter still performs
                    # complete fresh validation below after actual closure.
                    return repository._read_owned_range(
                        command.selector, metadata, start=command.start, end=command.end, cancellation_requested=stop
                    )

                # Coalesced readers own cancellation collectively. A member's
                # cancellation cannot invalidate a still-authorized follower.
                return self._scoped(command, trace_id, current)

            value = self.ranges.read(key, command.request_id, owned_read, cancellation_requested=request.stopped)

            def delivery(repository, actor, stopped):
                if (
                    _principal(actor) != principal
                    or repository.describe(command.selector, cancellation_requested=stopped) != metadata
                ):
                    raise DocumentRevisionProblem("viewer-authority-changed")
                return metadata, value

            # Fresh per-waiter authority after the owned stream/transaction has
            # closed. Successful coalescing is not an authorization cache.
            return self._scoped(command, trace_id, delivery, request=request)
        finally:
            request.stop.set()
            with self._mutex:
                self._requests.pop(identity, None)
                # read_range only reaches this after its own participation is
                # terminal, including last-member physical callback closure.
                self._terminal[identity] = request.root
                while len(self._terminal) > 256:
                    self._terminal.popitem(last=False)
                self._mutex.notify_all()

    def cancel(self, command) -> bool:
        """Acknowledge exact terminal ownership, never mere stop/absence."""
        identity = (command.project_id, command.session_id, command.request_id)
        deadline = time.monotonic() + 1.0
        with self._mutex:
            request = self._requests.get(identity)
            if request is not None and request.root != command.root:
                return False
            if identity in self._terminal:
                return self._terminal[identity] == command.root
            if request is None:
                early_root = self._early_cancellations.get(identity)
                if early_root is not None and early_root != command.root:
                    return False
                if early_root is None:
                    if len(self._early_cancellations) >= 256:
                        self._cancel_overflow = True
                        return False
                    # No expiry can turn a delayed issued operation into live
                    # work. Unconsumed bounded markers exhaust closed.
                    self._early_cancellations[identity] = command.root
            while True:
                request = self._requests.get(identity)
                if request is not None:
                    if request.root != command.root:
                        return False
                    request.stop.set()
                if identity in self._terminal:
                    return self._terminal[identity] == command.root
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._mutex.wait(remaining)

    def signal_stop(self, root: str | None = None) -> None:
        if root is None:
            self._stopped.set()
        with self._mutex:
            for request in self._requests.values():
                if root is None or request.root == root:
                    request.stop.set()

    def shutdown(self) -> None:
        self.signal_stop()
        if not self.ranges.close(timeout=1.0):
            raise DocumentRevisionProblem("viewer-owned-read-drain-pending")
