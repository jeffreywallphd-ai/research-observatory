"""Reentrant FIFO admission for bounded project actions.

A viewer releases its source transaction between ranges. The next range must
also yield the project action guard to metadata writers already waiting for it.
"""

import threading
from collections import deque


class FairProjectActionMutex:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._waiting: deque[object] = deque()
        self._owner: int | None = None
        self._depth = 0

    def waiting_count(self) -> int:
        with self._condition:
            return len(self._waiting)

    def __enter__(self):
        identity = threading.get_ident()
        with self._condition:
            if self._owner == identity:
                self._depth += 1
                return self
            ticket = object()
            self._waiting.append(ticket)
            try:
                while self._owner is not None or self._waiting[0] is not ticket:
                    self._condition.wait()
                self._waiting.popleft()
                self._owner, self._depth = identity, 1
                return self
            except BaseException:
                self._waiting.remove(ticket)
                self._condition.notify_all()
                raise

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        with self._condition:
            if self._owner != threading.get_ident() or self._depth < 1:
                raise RuntimeError("project action mutex cannot be released by another owner")
            self._depth -= 1
            if self._depth == 0:
                self._owner = None
                self._condition.notify_all()
