"""One Core GET stream, pinned public peer and ordinary hostname TLS identity."""

from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import httpcore2
import httpx2

from ..connectors.transport import private_wire
from ..ports.acquisition import AcquisitionProblem


def validated_url(value: str) -> httpx2.URL:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 8192
        or any(ord(x) <= 32 or ord(x) == 127 for x in value)
        or "\\" in value
    ):
        raise AcquisitionProblem("acquisition-destination-denied")
    try:
        url = httpx2.URL(value)
        if (
            url.scheme != "https"
            or url.port not in (None, 443)
            or url.userinfo
            or url.fragment
            or not url.host
            or url.host.endswith(".")
        ):
            raise ValueError
        # Canonical DNS names only. Numeric/literal destinations and ambiguous
        # host encodings are not a selectable scholarly source location.
        if (
            not re.fullmatch(r"(?=.{1,253}\Z)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", url.host)
            or "." not in url.host
            or ".." in url.host
        ):
            raise ValueError
        try:
            ipaddress.ip_address(url.host)
        except ValueError:
            pass
        else:
            raise ValueError
        return url
    except ValueError, httpx2.InvalidURL:
        raise AcquisitionProblem("acquisition-destination-denied") from None


class AcquisitionNetworkBackend(httpcore2.NetworkBackend):
    def __init__(
        self,
        host: str,
        *,
        backend: Any = None,
        checkpoint: Callable[[], None] = lambda: None,
        deadline: float | None = None,
    ):
        self._host = host
        self._backend = backend or httpcore2.SyncBackend()
        self._checkpoint = checkpoint
        self._deadline = deadline

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host != self._host or port != 443 or local_address is not None:
            raise AcquisitionProblem("acquisition-destination-denied")
        ready = threading.Event()
        started = time.monotonic()
        answers: list[Any] = []

        def resolve():
            try:
                answers.append(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
            except OSError:
                answers.append(None)
            finally:
                ready.set()

        # An expired DNS result can never dispatch a socket. The owned daemon
        # only completes name resolution; it has no project or egress grant.
        threading.Thread(target=resolve, daemon=True).start()
        if not ready.wait(min(10.0, timeout if timeout is not None else 10.0)):
            raise AcquisitionProblem("acquisition-network-timeout")
        if not answers[0]:
            raise AcquisitionProblem("acquisition-network-unavailable")
        targets = []
        for entry in answers[0]:
            try:
                address = ipaddress.ip_address(entry[4][0])
            except ValueError:
                raise AcquisitionProblem("acquisition-destination-denied") from None
            if (
                not address.is_global
                or address.is_multicast
                or address.is_reserved
                or (
                    isinstance(address, ipaddress.IPv6Address)
                    and (address.ipv4_mapped is not None or address.sixtofour is not None or address.teredo is not None)
                )
            ):
                raise AcquisitionProblem("acquisition-destination-denied")
            targets.append(str(address))
        self._checkpoint()
        remaining = None if timeout is None else timeout - (time.monotonic() - started)
        remaining = _remaining_timeout(remaining, self._deadline)
        if remaining is not None and remaining <= 0:
            raise AcquisitionProblem("acquisition-network-timeout")
        stream = self._backend.connect_tcp(targets[0], port, remaining, socket_options=socket_options)
        return _CheckedStream(stream, self._checkpoint, self._deadline)

    def connect_unix_socket(self, *args, **kwargs):
        raise AcquisitionProblem("acquisition-destination-denied")


class AcquisitionHTTPTransport:
    @contextmanager
    def open(self, url: str, *, timeout: float, checkpoint: Callable[[], None]) -> Iterator[Any]:
        address = validated_url(url)
        with (
            private_wire(),
            httpcore2.ConnectionPool(
                ssl_context=httpx2.create_ssl_context(verify=True, trust_env=False),
                network_backend=AcquisitionNetworkBackend(
                    address.host, checkpoint=checkpoint, deadline=time.monotonic() + timeout
                ),
                max_connections=1,
                max_keepalive_connections=0,
                retries=0,
                http1=True,
                http2=False,
            ) as pool,
            pool.stream(
                "GET",
                str(address),
                headers={
                    "User-Agent": "ResearchObservatory/1.0",
                    "Accept-Encoding": "identity",
                    "Accept": "application/pdf,application/xml,text/xml,text/html,text/plain,"
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                },
                extensions={
                    "timeout": {
                        "connect": min(10.0, timeout),
                        "read": min(1.0, timeout),
                        "write": min(1.0, timeout),
                        "pool": min(1.0, timeout),
                    }
                },
            ) as response,
        ):
            yield response


def _remaining_timeout(timeout: float | None, deadline: float | None) -> float | None:
    if deadline is None:
        return timeout
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AcquisitionProblem("acquisition-network-timeout")
    return remaining if timeout is None else min(timeout, remaining)


class _CheckedStream(httpcore2.NetworkStream):
    def __init__(self, stream: Any, checkpoint: Callable[[], None], deadline: float | None):
        self._stream, self._checkpoint = stream, checkpoint
        self._deadline = deadline

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        self._checkpoint()
        return self._stream.read(max_bytes, timeout=_remaining_timeout(timeout, self._deadline))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._checkpoint()
        self._stream.write(buffer, timeout=_remaining_timeout(timeout, self._deadline))

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self._checkpoint()
        return _CheckedStream(
            self._stream.start_tls(
                ssl_context, server_hostname=server_hostname, timeout=_remaining_timeout(timeout, self._deadline)
            ),
            self._checkpoint,
            self._deadline,
        )

    def get_extra_info(self, info: str):
        return self._stream.get_extra_info(info)

    def close(self) -> None:
        self._stream.close()
