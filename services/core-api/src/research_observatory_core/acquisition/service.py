"""Session-confirmed, bounded Core downloads into encrypted inspected storage."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, BinaryIO, cast
from urllib.parse import urljoin

import httpcore2

from ..domain_contracts import is_uuid_v7, new_uuid_v7
from ..ports.acquisition import (
    AcquisitionAttachmentPort,
    AcquisitionLocation,
    AcquisitionProblem,
    AcquisitionReceipt,
    AcquisitionRepositoryPort,
    AcquisitionSelection,
    AcquisitionStage,
)
from ..ports.corpus import CorpusActor
from ..ports.document_attachments import MAX_DOCUMENT_BYTES, AttachmentCandidate, DocumentInspectionProblem
from ..ports.object_store import ObjectStagingCancelled, ObjectStagingCleanupRequired, ObjectStoreProblem
from .transport import AcquisitionHTTPTransport, validated_url

_MEDIA = {
    "application/pdf": ".pdf",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/jats+xml": ".xml",
    "application/tei+xml": ".xml",
    "text/html": ".html",
    "text/plain": ".txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
_NETWORK_ERRORS = (httpcore2.TimeoutException, httpcore2.NetworkError, httpcore2.RemoteProtocolError)


@dataclass(frozen=True, slots=True)
class AcquisitionPreview:
    preview_id: str
    location: AcquisitionLocation
    selection: AcquisitionSelection
    provider_policy_revision_id: str
    confirmation_sha256: str
    confirmation: str = field(repr=False)


@dataclass(slots=True)
class _Pending:
    preview: AcquisitionPreview
    actor: CorpusActor
    expires: float
    used: bool = False


class _Retry(Exception):
    def __init__(self, seconds: float):
        self.seconds = seconds


class _Source:
    """Fill a bounded read plus one chunk remainder; storage owns encryption."""

    def __init__(
        self,
        chunks: Iterator[bytes],
        checkpoint: Callable[[], None],
        *,
        total: list[int],
        expected_length: int | None,
        maximum: int,
        clock: Callable[[], float],
    ):
        self.chunks, self.checkpoint = iter(chunks), checkpoint
        self.total, self.length, self.maximum, self.clock = total, expected_length, maximum, clock
        self.buffer = b""
        self.byte_length = 0
        self.digest = hashlib.sha256()
        self.finished_at: float | None = None
        self.failure: Exception | None = None

    def read(self, size: int = -1) -> bytes:
        try:
            return self._read(size)
        except Exception as error:
            self.failure = error
            raise

    def _read(self, size: int) -> bytes:
        if size < 1 or size > 1024 * 1024:
            raise AcquisitionProblem("acquisition-stream-bound-invalid")
        self.checkpoint()
        result = bytearray()
        while len(result) < size:
            if not self.buffer:
                if self.finished_at is not None:
                    break
                try:
                    chunk = next(self.chunks)
                except StopIteration:
                    if self.length is not None and self.byte_length != self.length:
                        raise AcquisitionProblem("acquisition-response-truncated") from None
                    self.finished_at = self.clock()
                    break
                if not isinstance(chunk, bytes) or len(chunk) > 1024 * 1024:
                    raise AcquisitionProblem("acquisition-stream-bound-invalid")
                self.total[0] += len(chunk)
                self.byte_length += len(chunk)
                if (
                    self.total[0] > self.maximum
                    or self.byte_length > self.maximum
                    or (self.length is not None and self.byte_length > self.length)
                ):
                    raise AcquisitionProblem("acquisition-response-too-large")
                if not chunk:
                    # An empty HTTP chunk is not EOF. Even an injected iterator
                    # with no socket I/O cannot spin past deadline/cancellation.
                    self.checkpoint()
                    continue
                self.digest.update(chunk)
                self.buffer = chunk
            count = min(size - len(result), len(self.buffer))
            result.extend(self.buffer[:count])
            self.buffer = self.buffer[count:]
        return bytes(result)


class OpenAccessAcquisitionService:
    def __init__(
        self,
        repository: AcquisitionRepositoryPort,
        attachments: AcquisitionAttachmentPort,
        *,
        session_id: str,
        authority_guard: Callable[[CorpusActor, Callable[[], Any]], Any],
        transport: Any = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        slot: threading.BoundedSemaphore | None = None,
    ):
        self.repository, self.attachments = repository, attachments
        self.session = session_id
        self.guard = authority_guard
        self.transport = transport or AcquisitionHTTPTransport()
        self.clock, self.sleep = clock, sleep
        self._pending: dict[str, _Pending] = {}
        self._mutex = threading.RLock()
        self._slot = slot or threading.BoundedSemaphore(1)

    def preview(self, selection: AcquisitionSelection, *, actor: CorpusActor) -> AcquisitionPreview:
        selection = AcquisitionSelection.model_validate(selection)
        location, policy = self.guard(actor, lambda: self.repository.authorize(selection, actor=actor))
        host = validated_url(location.url).host
        if len(set(selection.redirect_hosts)) != len(selection.redirect_hosts) or any(
            validated_url("https://" + name + "/").host != name for name in selection.redirect_hosts
        ):
            raise AcquisitionProblem("acquisition-redirect-policy-invalid")
        identity = new_uuid_v7()
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "selection": selection.model_dump(mode="json", by_alias=True),
                    "location": location.location_sha256,
                    "policy": policy.revision_id,
                    "actor": actor.actor_id,
                    "intent": actor.intent_revision_id,
                    "intentSha256": actor.intent_sha256,
                    "privacy": actor.policy_sha256,
                    "session": self.session,
                    "initialHost": host,
                    "preview": identity,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
        ).hexdigest()
        preview = AcquisitionPreview(
            identity,
            location,
            selection,
            policy.revision_id,
            fingerprint,
            "acquire-copy:" + identity + ":" + secrets.token_hex(16),
        )
        with self._mutex:
            self._pending = {
                key: value for key, value in self._pending.items() if value.expires > self.clock() and not value.used
            }
            if len(self._pending) >= 32:
                raise AcquisitionProblem("acquisition-preview-limit")
            self._pending[identity] = _Pending(preview, actor, self.clock() + 600)
        return preview

    def acquire(
        self, preview_id: str, *, confirmation: str, operation_id: str, cancellation_requested: Callable[[], bool]
    ) -> AttachmentCandidate:
        if not is_uuid_v7(operation_id) or not isinstance(confirmation, str) or len(confirmation) > 256:
            raise AcquisitionProblem("acquisition-command-invalid")
        with self._mutex:
            pending = self._pending.get(preview_id)
            if (
                pending is None
                or pending.used
                or pending.expires <= self.clock()
                or not hmac.compare_digest(confirmation, pending.preview.confirmation)
            ):
                raise AcquisitionProblem("acquisition-confirmation-required")
            if not self._slot.acquire(blocking=False):
                raise AcquisitionProblem("acquisition-busy")
            pending.used = True
        admitted = False
        try:
            claim = self.guard(
                pending.actor,
                lambda: self.repository.begin_attempt(
                    pending.preview.selection,
                    operation_id=operation_id,
                    session_id=self.session,
                    confirmation_sha256=pending.preview.confirmation_sha256,
                    expected_policy_revision_id=pending.preview.provider_policy_revision_id,
                    actor=pending.actor,
                ),
            )
            admitted = True
            self.attachments.ensure_intake_ready()
            self.guard(pending.actor, lambda: self.repository.intake_downloading(claim, actor=pending.actor))
            return self._download(
                pending,
                operation_id,
                lambda: cancellation_requested() or self.repository.intake_cancelled(claim),
                claim,
            )
        except BaseException as error:
            # A rejected duplicate has no authority to terminate an earlier
            # admitted request, including one retained for restart recovery.
            if not admitted:
                raise
            was_cancelled = isinstance(error, ObjectStagingCancelled) or (
                isinstance(error, DocumentInspectionProblem) and error.code == "cancelled"
            )
            code = (
                "acquisition-cleanup-required"
                if isinstance(error, ObjectStagingCleanupRequired)
                else "acquisition-cancelled"
                if was_cancelled
                else getattr(error, "code", "acquisition-failed")
            )
            if not isinstance(code, str) or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", code) is None:
                code = "acquisition-failed"
            # Revoked/closed sessions retain the admitted request for recovery.
            with suppress(Exception):
                self.guard(
                    pending.actor,
                    lambda: self.repository.fail_attempt(
                        operation_id,
                        actor=pending.actor,
                        cancelled=was_cancelled,
                        code=code,
                    ),
                )
            raise
        finally:
            if admitted:
                self.repository.release_intake(operation_id)
            self._slot.release()

    def _download(
        self, pending: _Pending, operation_id: str, cancelled: Callable[[], bool], claim
    ) -> AttachmentCandidate:
        preview, actor = pending.preview, pending.actor
        selection = preview.selection
        started = self.clock()
        deadline = started + 120
        wire = [0]
        redirects: list[str] = []

        def checkpoint(*, transfer: bool = True) -> None:
            if cancelled():
                raise ObjectStagingCancelled()
            if (transfer and self.clock() >= deadline) or self.clock() >= pending.expires:
                raise AcquisitionProblem("acquisition-network-timeout")

            def current():
                location, policy = self.repository.authorize(selection, actor=actor)
                if location != preview.location or policy.revision_id != preview.provider_policy_revision_id:
                    raise AcquisitionProblem("acquisition-preview-stale")

            self.guard(actor, current)

        for attempt in range(1, 4):
            url = preview.location.url
            try:
                while True:
                    checkpoint()
                    address = validated_url(url)
                    if address.host not in {validated_url(preview.location.url).host, *selection.redirect_hosts}:
                        raise AcquisitionProblem("acquisition-redirect-denied")
                    with self.transport.open(
                        url, timeout=max(0.001, deadline - self.clock()), checkpoint=checkpoint
                    ) as response:
                        headers: dict[str, str] = {}
                        for name, value in response.headers:
                            try:
                                key = name.decode("ascii").lower() if isinstance(name, bytes) else name.lower()
                                text = value.decode("latin-1") if isinstance(value, bytes) else value
                            except UnicodeError, AttributeError:
                                raise AcquisitionProblem("acquisition-response-invalid") from None
                            if len(headers) >= 100 or not 1 <= len(key) <= 128 or len(text) > 8192:
                                raise AcquisitionProblem("acquisition-response-invalid")
                            if key in headers and key in {
                                "content-type",
                                "content-length",
                                "content-encoding",
                                "location",
                                "retry-after",
                            }:
                                raise AcquisitionProblem("acquisition-response-invalid")
                            headers[key] = text
                        checkpoint()
                        if response.status in {301, 302, 303, 307, 308}:
                            if len(redirects) >= 5 or "location" not in headers:
                                raise AcquisitionProblem("acquisition-redirect-limit")
                            target = urljoin(url, headers["location"])
                            target_host = validated_url(target).host
                            if target_host not in {validated_url(preview.location.url).host, *selection.redirect_hosts}:
                                raise AcquisitionProblem("acquisition-redirect-denied")
                            redirects.append(target_host)
                            url = target
                            continue
                        if response.status in {429, 502, 503, 504}:
                            raw = headers.get("retry-after")
                            delay = 0.25 * attempt
                            if raw is not None:
                                try:
                                    delay = (
                                        float(raw)
                                        if raw.isascii() and raw.isdecimal() and len(raw) <= 6
                                        else max(0.0, (parsedate_to_datetime(raw) - datetime.now(UTC)).total_seconds())
                                    )
                                except ValueError, TypeError, OverflowError:
                                    raise AcquisitionProblem("acquisition-response-invalid") from None
                            raise _Retry(delay)
                        if response.status != 200:
                            raise AcquisitionProblem(
                                "acquisition-unavailable"
                                if response.status in {404, 410}
                                else "acquisition-access-denied"
                            )
                        media = headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        if (
                            media not in _MEDIA
                            or headers.get("content-encoding", "identity").strip().lower() != "identity"
                        ):
                            raise AcquisitionProblem("acquisition-content-type-denied")
                        length = headers.get("content-length")
                        if length is not None and (
                            not length.isascii()
                            or not length.isdecimal()
                            or len(length) > 20
                            or int(length) > MAX_DOCUMENT_BYTES - wire[0]
                        ):
                            raise AcquisitionProblem("acquisition-response-too-large")
                        source = _Source(
                            response.iter_stream(),
                            checkpoint,
                            total=wire,
                            expected_length=int(length) if length is not None else None,
                            maximum=MAX_DOCUMENT_BYTES,
                            clock=self.clock,
                        )

                        def receipt(
                            source: _Source = source, media: str = media, attempt: int = attempt
                        ) -> AcquisitionReceipt:
                            if source.finished_at is None:
                                raise AcquisitionProblem("acquisition-response-incomplete")
                            return AcquisitionReceipt(
                                location_id=selection.location_id,
                                location_sha256=selection.location_sha256,
                                provider_policy_revision_id=preview.provider_policy_revision_id,
                                retrieved_at=datetime.now(UTC)
                                .isoformat(timespec="milliseconds")
                                .replace("+00:00", "Z"),
                                expected_sha256=selection.expected_sha256,
                                actual_sha256=source.digest.hexdigest(),
                                media_type=media,
                                wire_bytes=wire[0],
                                expanded_bytes=source.byte_length,
                                attempts=attempt,
                                redirect_hosts=tuple(redirects),
                                elapsed_ms=int((source.finished_at - started) * 1000),
                                confirmation_sha256=preview.confirmation_sha256,
                            )

                        def publish(action):
                            # The transfer deadline covers network bytes; bounded
                            # LPAC inspection has its separate qualified limits.
                            checkpoint(transfer=False)
                            return self.guard(actor, action)

                        try:
                            # The encrypted store consumes read(size), without seeking.
                            return self.attachments.stage(
                                cast(BinaryIO, source),
                                source_name="acquired" + _MEDIA[media],
                                declared_media_type=media,
                                source_assertion_revision_id=selection.source_assertion_revision_id,
                                work_id=selection.work_id,
                                work_revision_id=selection.work_revision_id,
                                version_id=selection.version_id,
                                version_revision_id=selection.version_revision_id,
                                actor=actor,
                                operation_id=operation_id,
                                session_id=self.session,
                                cancellation_requested=cancelled,
                                publication_guard=publish,
                                acquisition=AcquisitionStage(selection.expected_sha256, receipt, claim),
                            )
                        except ObjectStoreProblem as error:
                            # Storage intentionally redacts arbitrary reader
                            # exceptions. Recover only this owned reader's typed
                            # denial/network result after its encrypted cleanup.
                            if not isinstance(error, ObjectStagingCleanupRequired) and isinstance(
                                source.failure, (*_NETWORK_ERRORS, AcquisitionProblem, ObjectStagingCancelled)
                            ):
                                raise source.failure from None
                            raise
            except (*_NETWORK_ERRORS, _Retry) as error:
                delay = error.seconds if isinstance(error, _Retry) else 0.25 * attempt
                if attempt == 3 or self.clock() + delay >= deadline:
                    raise AcquisitionProblem("acquisition-network-unavailable") from None
                wait_until = self.clock() + delay
                while self.clock() < wait_until:
                    checkpoint()
                    self.sleep(min(0.1, wait_until - self.clock()))
        raise AcquisitionProblem("acquisition-network-unavailable")
