"""Authenticated Core composition for local publisher trust and project grants.

The native selected-file bridge sends bounded archive chunks. Core retains one
short-lived candidate for the current writable project session. Candidate data
is never authority: signing trust and exact project consent are rechecked when
the researcher enables it and again before any later dispatch.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from .connectors.broker import utc_now
from .connectors.plugin_grants import PluginEnableConfirmation, PluginGrantActor, PluginGrantProblem
from .connectors.plugin_manifest import (
    PluginDestination,
    PluginInvocationPlan,
    PluginInvocationRequest,
    PluginProjectGrant,
    VerifiedPluginPackage,
    authorize_plugin_invocation,
)
from .connectors.plugin_package_intake import MAX_ARCHIVE_BYTES, InspectedPluginArchive, inspect_plugin_archive
from .connectors.plugin_package_store import PluginPackageStore
from .connectors.plugin_trust import PluginGrantService, PluginPublisherTrustStore, PluginTrustDecision
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .models import ContractModel
from .ports.plugin_grants import PluginGrantRepository
from .ports.plugin_packages import PluginPackagePointer, PluginPackageRepository
from .projects import ProjectLifecycleService

_SESSION = re.compile(r"[0-9a-f]{32}\Z")
_TOKEN = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TTL_SECONDS = 300.0
_CHUNK_BYTES = 128 * 1024
_MAX_CHUNKS = 512


class PluginPackageReview(ContractModel):
    plugin_id: str
    plugin_version: str
    publisher_key_id: str
    source_display_name: str
    manifest_sha256: str
    package_sha256: str
    signature_sha256: str
    permissions: tuple[str, ...]
    destinations: tuple[PluginDestination, ...]
    operations: tuple[str, ...]
    data_classes: tuple[str, ...]
    credential_scopes: tuple[str, ...]
    resource_profile: dict[str, int]
    trust_status: Literal["untrusted", "active", "revoked", "invalid"]
    grant_status: Literal["disabled", "enabled", "different-package", "renewal-required"]
    runtime_status: Literal["ready", "unavailable"]


class PluginTransferStatus(ContractModel):
    intake_id: str
    state: Literal["receiving", "sealed", "cancelled"]
    byte_length: int
    chunk_count: int
    package_token: str | None = None
    expires_at: str | None = None
    review: PluginPackageReview | None = None


class PluginCandidateReview(ContractModel):
    package_token: str
    expires_at: str
    review: PluginPackageReview


class PluginTrustStatus(ContractModel):
    publisher_key_id: str
    status: Literal["untrusted", "active", "revoked"]
    revision: int | None
    public_key_sha256: str | None


class PluginGrantStatus(ContractModel):
    plugin_id: str
    status: Literal["disabled", "enabled"]
    revision: int | None
    package_sha256: str | None
    manifest_sha256: str | None
    permissions: tuple[str, ...]
    destinations: tuple[PluginDestination, ...]


@dataclass(frozen=True, slots=True)
class PluginAuthorizedDispatch:
    """Core-only exact bytes and plan; never serialized into worker control frames."""

    package: VerifiedPluginPackage
    plan: PluginInvocationPlan
    files: dict[str, bytes] = field(repr=False)


@dataclass(slots=True)
class _Intake:
    intake_id: str
    data: bytearray = field(default_factory=bytearray, repr=False)
    chunk_count: int = 0
    sealed_byte_length: int = 0
    state: Literal["receiving", "sealed", "cancelled"] = "receiving"
    package_token: str | None = None

    def clear(self) -> None:
        self.data[:] = b"\0" * len(self.data)
        self.data.clear()


@dataclass(slots=True)
class _Candidate:
    token: str
    archive: InspectedPluginArchive = field(repr=False)
    expires_at: float
    raw_archive: bytearray | None = field(repr=False)

    def clear_raw(self) -> None:
        if self.raw_archive is not None:
            self.raw_archive[:] = b"\0" * len(self.raw_archive)
            self.raw_archive = None


@dataclass(slots=True)
class _ProjectSession:
    project_id: str
    session_id: str
    intake: _Intake | None = None
    candidate: _Candidate | None = None
    discarded_token: str | None = None

    def clear(self) -> None:
        if self.intake is not None:
            self.intake.clear()
        if self.candidate is not None:
            self.candidate.clear_raw()
        self.intake = None
        self.candidate = None
        self.discarded_token = None


class PluginAdminService:
    """One current native session per open project; no profile-wide package cache."""

    def __init__(
        self,
        projects: ProjectLifecycleService,
        trust: PluginPublisherTrustStore,
        *,
        actor_id: str,
        grant_repository_factory: Callable[[Path, str], PluginGrantRepository],
        package_store_factory: Callable[[Path, str], PluginPackageStore] | None = None,
        package_repository_factory: Callable[[Path, str], PluginPackageRepository],
        runtime_available: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], str] = utc_now,
    ) -> None:
        if not is_uuid_v7(actor_id):
            raise PluginGrantProblem("plugin-grant-actor-invalid")
        self._projects, self._trust = projects, trust
        self._actor_id, self._clock, self._now = actor_id, clock, now
        self._grant_repository_factory = grant_repository_factory
        self._package_store_factory = package_store_factory
        self._package_repository_factory = package_repository_factory
        self._runtime_available = runtime_available or (lambda: False)
        self._mutex = threading.RLock()
        self._sessions: dict[Path, _ProjectSession] = {}

    def _runtime_ready(self) -> bool:
        try:
            return self._runtime_available() is True
        except Exception:
            return False

    def actor(self, trace_id: str) -> PluginGrantActor:
        return PluginGrantActor(self._actor_id, trace_id, self._now())

    def clear(self, root: str | None = None) -> None:
        """Any project close/lock and Core shutdown erase all transfer authority."""

        with self._mutex:
            # A caller can name an alias of a project root at the native API.
            # Clearing every ephemeral transfer is safer than retaining one
            # under a differently spelled path after a lifecycle transition.
            sessions = tuple(self._sessions.values())
            self._sessions.clear()
            for session in sessions:
                session.clear()

    def _project[Result](self, root: str, project_id: str, action: Callable[[Path, str], Result]) -> Result:
        def apply(path: Path, identity: str) -> Result:
            if identity != project_id:
                raise PluginGrantProblem("plugin-project-mismatch")
            return action(path, identity)

        return self._projects.perform_open_project_action(root=root, require_write=True, action=apply)

    def _session[Result](
        self, root: str, project_id: str, session_id: str, action: Callable[[Path, _ProjectSession], Result]
    ) -> Result:
        if not isinstance(session_id, str) or _SESSION.fullmatch(session_id) is None:
            raise PluginGrantProblem("plugin-session-invalid")

        def apply(path: Path, identity: str) -> Result:
            with self._mutex:
                session = self._sessions.get(path)
                if session is None or session.project_id != identity or session.session_id != session_id:
                    raise PluginGrantProblem("plugin-session-stale")
                return action(path, session)

        return self._project(root, project_id, apply)

    def context(self, root: str, project_id: str) -> str:
        def create(path: Path, identity: str) -> str:
            with self._mutex:
                current = self._sessions.get(path)
                if current is not None and current.project_id == identity:
                    return current.session_id
                for previous in self._sessions.values():
                    previous.clear()
                self._sessions.clear()
                session_id = secrets.token_hex(16)
                self._sessions[path] = _ProjectSession(identity, session_id)
                return session_id

        return self._project(root, project_id, create)

    def create(self, root: str, project_id: str, session_id: str) -> PluginTransferStatus:
        def create(_path: Path, session: _ProjectSession) -> PluginTransferStatus:
            session.clear()
            session.intake = _Intake(new_uuid_v7())
            return self._status(session)

        return self._session(root, project_id, session_id, create)

    @staticmethod
    def _current_intake(session: _ProjectSession, intake_id: str) -> _Intake:
        intake = session.intake
        if not is_uuid_v7(intake_id) or intake is None or intake.intake_id != intake_id:
            raise PluginGrantProblem("plugin-intake-stale")
        return intake

    @staticmethod
    def _status(session: _ProjectSession) -> PluginTransferStatus:
        intake = session.intake
        if intake is None:
            raise PluginGrantProblem("plugin-intake-stale")
        return PluginTransferStatus(
            intake_id=intake.intake_id,
            state=intake.state,
            byte_length=len(intake.data) if intake.state == "receiving" else intake.sealed_byte_length,
            chunk_count=intake.chunk_count,
            package_token=intake.package_token,
        )

    def status(self, root: str, project_id: str, session_id: str, intake_id: str) -> PluginTransferStatus:
        def status(_path: Path, session: _ProjectSession) -> PluginTransferStatus:
            self._current_intake(session, intake_id)
            return self._status(session)

        return self._session(root, project_id, session_id, status)

    def chunk(
        self, root: str, project_id: str, session_id: str, intake_id: str, ordinal: int, data: bytes
    ) -> PluginTransferStatus:
        if (
            type(ordinal) is not int
            or not 1 <= ordinal <= _MAX_CHUNKS
            or not isinstance(data, bytes)
            or not 1 <= len(data) <= _CHUNK_BYTES
        ):
            raise PluginGrantProblem("plugin-chunk-invalid")

        def append(_path: Path, session: _ProjectSession) -> PluginTransferStatus:
            intake = self._current_intake(session, intake_id)
            if (
                intake.state != "receiving"
                or ordinal != intake.chunk_count + 1
                or len(intake.data) + len(data) > MAX_ARCHIVE_BYTES
            ):
                raise PluginGrantProblem("plugin-chunk-invalid")
            intake.data.extend(data)
            intake.chunk_count += 1
            return self._status(session)

        return self._session(root, project_id, session_id, append)

    def seal(
        self,
        root: str,
        project_id: str,
        session_id: str,
        intake_id: str,
        *,
        archive_sha256: str,
        byte_length: int,
        chunk_count: int,
        trace_id: str,
    ) -> PluginTransferStatus:
        if (
            not isinstance(archive_sha256, str)
            or _SHA.fullmatch(archive_sha256) is None
            or type(byte_length) is not int
            or not 1 <= byte_length <= MAX_ARCHIVE_BYTES
            or type(chunk_count) is not int
            or not 1 <= chunk_count <= _MAX_CHUNKS
        ):
            raise PluginGrantProblem("plugin-seal-invalid")

        def seal(_path: Path, session: _ProjectSession) -> PluginTransferStatus:
            intake = self._current_intake(session, intake_id)
            if (
                intake.state != "receiving"
                or len(intake.data) != byte_length
                or intake.chunk_count != chunk_count
                or "sha256:" + hashlib.sha256(intake.data).hexdigest() != archive_sha256
            ):
                raise PluginGrantProblem("plugin-seal-mismatch")
            inspected = inspect_plugin_archive(bytes(intake.data))
            selected = bytearray(intake.data)
            intake.clear()
            intake.sealed_byte_length = byte_length
            token = secrets.token_hex(32)
            intake.state = "sealed"
            intake.package_token = token
            session.candidate = _Candidate(token, inspected, self._clock() + _TTL_SECONDS, selected)
            reviewed = self._review(_path, session, trace_id)
            return self._status(session).model_copy(
                update={"expires_at": reviewed.expires_at, "review": reviewed.review}
            )

        return self._session(root, project_id, session_id, seal)

    def _review(self, path: Path, session: _ProjectSession, trace_id: str) -> PluginCandidateReview:
        candidate = session.candidate
        if candidate is None or self._clock() >= candidate.expires_at:
            session.clear()
            raise PluginGrantProblem("plugin-package-expired")
        inspected = candidate.archive
        manifest = inspected.manifest
        trust = self._trust.state(manifest.publisher_key_id, audit_context=trace_id)
        trust_status: Literal["untrusted", "active", "revoked", "invalid"] = (
            trust.status if trust is not None else "untrusted"
        )
        if trust_status == "active":
            try:
                self._trust.verify_package(
                    inspected.manifest_bytes, inspected.signature, inspected.files, audit_context=trace_id
                )
            except PluginGrantProblem:
                trust_status = "invalid"
        grants = self._grant_repository_factory(path, session.project_id)
        current = grants.current_grant_authority(manifest.plugin_id)
        grant_status: Literal["disabled", "enabled", "different-package", "renewal-required"] = "disabled"
        if current is not None:
            if (
                current.grant.package_sha256 != inspected.package_sha256
                or current.grant.manifest_sha256 != inspected.manifest_sha256
            ):
                grant_status = "different-package"
            elif (
                trust_status == "active"
                and trust is not None
                and current.trusted_key_sha256 == trust.public_key_sha256
                and current.trusted_key_revision == trust.revision
            ):
                grant_status = "enabled"
            else:
                grant_status = "renewal-required"
        remaining = max(0, int(candidate.expires_at - self._clock()))
        expires_at = (
            (datetime.now(UTC) + timedelta(seconds=remaining)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
        return PluginCandidateReview(
            package_token=candidate.token,
            expires_at=expires_at,
            review=PluginPackageReview(
                plugin_id=manifest.plugin_id,
                plugin_version=manifest.plugin_version,
                publisher_key_id=manifest.publisher_key_id,
                source_display_name=manifest.source_identity.display_name,
                manifest_sha256=inspected.manifest_sha256,
                package_sha256=inspected.package_sha256,
                signature_sha256=inspected.signature_sha256,
                permissions=manifest.permissions,
                destinations=manifest.destinations,
                operations=manifest.operations,
                data_classes=manifest.data_classes,
                credential_scopes=manifest.credential_scopes,
                resource_profile=manifest.resource_profile.model_dump(mode="json", by_alias=True),
                trust_status=trust_status,
                grant_status=grant_status,
                runtime_status="ready" if self._runtime_ready() else "unavailable",
            ),
        )

    def review(
        self, root: str, project_id: str, session_id: str, package_token: str, *, trace_id: str
    ) -> PluginCandidateReview:
        if not isinstance(package_token, str) or _TOKEN.fullmatch(package_token) is None:
            raise PluginGrantProblem("plugin-package-token-invalid")

        def review(path: Path, session: _ProjectSession) -> PluginCandidateReview:
            if session.candidate is None or session.candidate.token != package_token:
                raise PluginGrantProblem("plugin-package-token-stale")
            return self._review(path, session, trace_id)

        return self._session(root, project_id, session_id, review)

    def cancel(self, root: str, project_id: str, session_id: str, intake_id: str) -> PluginTransferStatus:
        def cancel(_path: Path, session: _ProjectSession) -> PluginTransferStatus:
            intake = self._current_intake(session, intake_id)
            discarded = session.candidate.token if session.candidate is not None else None
            session.clear()
            session.intake = _Intake(intake.intake_id, state="cancelled")
            session.discarded_token = discarded
            return self._status(session)

        return self._session(root, project_id, session_id, cancel)

    def discard(self, root: str, project_id: str, session_id: str, package_token: str) -> PluginTransferStatus:
        if not isinstance(package_token, str) or _TOKEN.fullmatch(package_token) is None:
            raise PluginGrantProblem("plugin-package-token-invalid")

        def discard(_path: Path, session: _ProjectSession) -> PluginTransferStatus:
            if session.discarded_token == package_token and session.intake is not None:
                return self._status(session)
            intake = session.intake
            if session.candidate is None or session.candidate.token != package_token or intake is None:
                raise PluginGrantProblem("plugin-package-token-stale")
            intake_id = intake.intake_id
            session.clear()
            session.intake = _Intake(intake_id, state="cancelled")
            session.discarded_token = package_token
            return self._status(session)

        return self._session(root, project_id, session_id, discard)

    def trust_status(
        self, root: str, project_id: str, session_id: str, publisher_key_id: str, *, trace_id: str
    ) -> PluginTrustStatus:
        def status(_path: Path, _session: _ProjectSession) -> PluginTrustStatus:
            state = self._trust.state(publisher_key_id, audit_context=trace_id)
            return PluginTrustStatus(
                publisher_key_id=publisher_key_id,
                status=state.status if state is not None else "untrusted",
                revision=state.revision if state is not None else None,
                public_key_sha256=state.public_key_sha256 if state is not None else None,
            )

        return self._session(root, project_id, session_id, status)

    def trust_decide(
        self,
        root: str,
        project_id: str,
        session_id: str,
        decision: PluginTrustDecision,
        public_key: bytes | None,
        *,
        actor: PluginGrantActor,
    ) -> PluginTrustStatus:
        def decide(_path: Path, _session: _ProjectSession) -> PluginTrustStatus:
            state = self._trust.decide(public_key, decision, actor=actor)
            return PluginTrustStatus(
                publisher_key_id=state.publisher_key_id,
                status=state.status,
                revision=state.revision,
                public_key_sha256=state.public_key_sha256,
            )

        return self._session(root, project_id, session_id, decide)

    def grant_status(self, root: str, project_id: str, session_id: str, plugin_id: str) -> PluginGrantStatus:
        def status(path: Path, identity: str) -> PluginGrantStatus:
            grants = self._grant_repository_factory(path, identity)
            current = grants.current_grant_authority(plugin_id)
            if current is not None:
                grant = current.grant
                return PluginGrantStatus(
                    plugin_id=plugin_id,
                    status="enabled",
                    revision=grant.revision,
                    package_sha256=grant.package_sha256,
                    manifest_sha256=grant.manifest_sha256,
                    permissions=grant.permissions,
                    destinations=grant.destinations,
                )
            history = grants.audit_history(plugin_id)
            previous = next((item for item in reversed(history) if item.event_kind in {"enabled", "revoked"}), None)
            return PluginGrantStatus(
                plugin_id=plugin_id,
                status="disabled",
                revision=previous.revision if previous else None,
                package_sha256=None,
                manifest_sha256=None,
                permissions=(),
                destinations=(),
            )

        return self._session(root, project_id, session_id, lambda path, session: status(path, session.project_id))

    def enable(
        self,
        root: str,
        project_id: str,
        session_id: str,
        package_token: str,
        confirmation: PluginEnableConfirmation,
        *,
        actor: PluginGrantActor,
    ) -> PluginGrantStatus:
        if not isinstance(confirmation, PluginEnableConfirmation):
            raise PluginGrantProblem("plugin-grant-confirmation-invalid")

        def enable(path: Path, session: _ProjectSession) -> PluginGrantStatus:
            if session.candidate is None or session.candidate.token != package_token:
                raise PluginGrantProblem("plugin-package-token-stale")
            self._review(path, session, actor.trace_id)  # Expiry and current authority are rechecked.
            if not self._runtime_ready():
                self._grant_repository_factory(path, session.project_id).record_denial(
                    plugin_id=session.candidate.archive.manifest.plugin_id,
                    reason_code="plugin-runtime-unavailable",
                    actor=actor,
                )
                raise PluginGrantProblem("plugin-runtime-unavailable")
            inspected = session.candidate.archive
            # Package persistence precedes the durable grant. A failed grant
            # may leave an encrypted orphan, but never an enabled grant whose
            # exact bytes cannot be reopened after Core restart.
            if self._package_store_factory is None:
                raise PluginGrantProblem("plugin-package-store-unavailable")
            self._trust.verify_package(
                inspected.manifest_bytes, inspected.signature, inspected.files, audit_context=actor.trace_id
            )
            store = self._package_store_factory(path, session.project_id)
            if session.candidate.raw_archive is not None:
                archive_object_sha256 = store.save(
                    bytes(session.candidate.raw_archive), inspected.package_sha256, inspected.manifest_sha256
                )
            else:
                current_pointer = self._package_repository_factory(path, session.project_id).read(
                    inspected.package_sha256, inspected.manifest_sha256, inspected.signature_sha256
                )
                if current_pointer is None:
                    raise PluginGrantProblem("plugin-package-store-unavailable")
                archive_object_sha256 = current_pointer.archive_object_sha256
            reopened = store.load(archive_object_sha256, inspected.package_sha256, inspected.manifest_sha256)
            if reopened.signature_sha256 != inspected.signature_sha256:
                raise PluginGrantProblem("plugin-package-identity-conflict")
            self._package_repository_factory(path, session.project_id).record(
                PluginPackagePointer(
                    session.project_id,
                    inspected.package_sha256,
                    inspected.manifest_sha256,
                    inspected.signature_sha256,
                    archive_object_sha256,
                ),
                now=actor.occurred_at,
            )
            grant = PluginGrantService(self._trust, self._grant_repository_factory(path, session.project_id)).enable(
                inspected.manifest_bytes,
                inspected.signature,
                inspected.files,
                confirmation,
                actor=actor,
            )
            session.candidate.clear_raw()
            return PluginGrantStatus(
                plugin_id=grant.plugin_id,
                status="enabled",
                revision=grant.revision,
                package_sha256=grant.package_sha256,
                manifest_sha256=grant.manifest_sha256,
                permissions=grant.permissions,
                destinations=grant.destinations,
            )

        return self._session(root, project_id, session_id, enable)

    def prepare_invocation(
        self,
        root: str,
        project_id: str,
        session_id: str,
        package_token: str,
        request: PluginInvocationRequest,
        *,
        actor: PluginGrantActor,
    ) -> PluginAuthorizedDispatch:
        """Reverify local trust, selected bytes and current grant at every launch."""

        if not isinstance(request, PluginInvocationRequest) or request.project_id != project_id:
            raise PluginGrantProblem("plugin-invocation-invalid")

        def prepare(path: Path, session: _ProjectSession) -> PluginAuthorizedDispatch:
            package, plan, inspected = self._current_authorization(path, session, package_token, request, actor)
            return PluginAuthorizedDispatch(package, plan, dict(inspected.files))

        return self._session(root, project_id, session_id, prepare)

    def _persisted_authorization(
        self,
        path: Path,
        project_id: str,
        package_sha256: str,
        manifest_sha256: str,
        signature_sha256: str,
        request: PluginInvocationRequest,
        actor: PluginGrantActor,
    ) -> PluginAuthorizedDispatch:
        if self._package_store_factory is None or not self._runtime_ready():
            raise PluginGrantProblem("plugin-runtime-unavailable")
        pointer = self._package_repository_factory(path, project_id).read(
            package_sha256, manifest_sha256, signature_sha256
        )
        if pointer is None:
            raise PluginGrantProblem("plugin-package-unavailable")
        inspected = self._package_store_factory(path, project_id).load(
            pointer.archive_object_sha256, package_sha256, manifest_sha256
        )
        if inspected.signature_sha256 != signature_sha256 or pointer.signature_sha256 != signature_sha256:
            raise PluginGrantProblem("plugin-package-identity-conflict")
        service = PluginGrantService(self._trust, self._grant_repository_factory(path, project_id))
        plan = service.current_authorization(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            request,
            expected_plugin_id=inspected.manifest.plugin_id,
            actor=actor,
        )
        package = self._trust.verify_package(
            inspected.manifest_bytes, inspected.signature, inspected.files, audit_context=actor.trace_id
        )
        return PluginAuthorizedDispatch(package, plan, dict(inspected.files))

    def prepare_persisted_invocation(
        self,
        root: str,
        project_id: str,
        package_sha256: str,
        manifest_sha256: str,
        signature_sha256: str,
        request: PluginInvocationRequest,
        *,
        actor: PluginGrantActor,
    ) -> PluginAuthorizedDispatch:
        """Restart-safe Core authority, without a persisted native candidate token."""

        if not isinstance(request, PluginInvocationRequest) or request.project_id != project_id:
            raise PluginGrantProblem("plugin-invocation-invalid")
        return self._project(
            root,
            project_id,
            lambda path, identity: self._persisted_authorization(
                path, identity, package_sha256, manifest_sha256, signature_sha256, request, actor
            ),
        )

    def recheck_persisted_invocation(
        self,
        root: str,
        project_id: str,
        package_sha256: str,
        manifest_sha256: str,
        signature_sha256: str,
        request: PluginInvocationRequest,
        *,
        actor: PluginGrantActor,
    ) -> PluginInvocationPlan:
        return self.prepare_persisted_invocation(
            root, project_id, package_sha256, manifest_sha256, signature_sha256, request, actor=actor
        ).plan

    def current_grant_persisted(self, root: str, project_id: str, plugin_id: str) -> PluginProjectGrant | None:
        return self._project(
            root,
            project_id,
            lambda path, identity: self._grant_repository_factory(path, identity).current_grant(plugin_id),
        )

    def record_denial_persisted(
        self,
        root: str,
        project_id: str,
        *,
        plugin_id: str,
        invocation_id: str,
        reason_code: str,
        actor: PluginGrantActor,
    ) -> None:
        self._project(
            root,
            project_id,
            lambda path, identity: self._grant_repository_factory(path, identity).record_denial(
                plugin_id=plugin_id, invocation_id=invocation_id, reason_code=reason_code, actor=actor
            ),
        )

    def recheck_admitted_invocation(
        self,
        root: str,
        project_id: str,
        admitted: PluginAuthorizedDispatch,
        request: PluginInvocationRequest,
        *,
        actor: PluginGrantActor,
        session_id: str | None = None,
        package_token: str | None = None,
    ) -> PluginInvocationPlan:
        """Recheck mutable authority without reloading immutable admitted bytes."""

        if not isinstance(admitted, PluginAuthorizedDispatch) or request.project_id != project_id:
            raise PluginGrantProblem("plugin-invocation-invalid")

        def check(path: Path, identity: str) -> PluginInvocationPlan:
            package = admitted.package
            authority = self._grant_repository_factory(path, identity).current_grant_authority(
                package.manifest.plugin_id
            )
            if authority is None:
                raise PluginGrantProblem("plugin-grant-not-active")
            _key, trust = self._trust.active_authority(package.manifest.publisher_key_id, audit_context=actor.trace_id)
            if (
                authority.trusted_key_sha256 != trust.public_key_sha256
                or authority.trusted_key_revision != trust.revision
            ):
                raise PluginGrantProblem("plugin-grant-trust-changed")
            try:
                return authorize_plugin_invocation(package, authority.grant, request)
            except ValueError:
                raise PluginGrantProblem("plugin-invocation-denied") from None

        if session_id is None and package_token is None:
            return self._project(root, project_id, check)
        if session_id is None or package_token is None:
            raise PluginGrantProblem("plugin-session-invalid")

        def selected(path: Path, session: _ProjectSession) -> PluginInvocationPlan:
            candidate = session.candidate
            if (
                candidate is None
                or candidate.token != package_token
                or self._clock() >= candidate.expires_at
                or candidate.archive.package_sha256 != admitted.package.package_sha256
                or candidate.archive.manifest_sha256 != admitted.package.manifest_sha256
                or candidate.archive.signature_sha256 != admitted.package.signature_sha256
            ):
                raise PluginGrantProblem("plugin-package-token-stale")
            return check(path, session.project_id)

        return self._session(root, project_id, session_id, selected)

    def _current_authorization(
        self,
        path: Path,
        session: _ProjectSession,
        package_token: str,
        request: PluginInvocationRequest,
        actor: PluginGrantActor,
    ) -> tuple[VerifiedPluginPackage, PluginInvocationPlan, InspectedPluginArchive]:
        candidate = session.candidate
        if candidate is None or candidate.token != package_token:
            raise PluginGrantProblem("plugin-package-token-stale")
        self._review(path, session, actor.trace_id)
        if not self._runtime_ready():
            raise PluginGrantProblem("plugin-runtime-unavailable")
        inspected = candidate.archive
        service = PluginGrantService(self._trust, self._grant_repository_factory(path, session.project_id))
        plan = service.current_authorization(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            request,
            expected_plugin_id=inspected.manifest.plugin_id,
            actor=actor,
        )
        package = self._trust.verify_package(
            inspected.manifest_bytes, inspected.signature, inspected.files, audit_context=actor.trace_id
        )
        return package, plan, inspected

    def recheck_invocation(
        self,
        root: str,
        project_id: str,
        session_id: str,
        package_token: str,
        request: PluginInvocationRequest,
        *,
        actor: PluginGrantActor,
    ) -> PluginInvocationPlan:
        """Return only the freshly authorized plan, without copying package bytes."""

        if not isinstance(request, PluginInvocationRequest) or request.project_id != project_id:
            raise PluginGrantProblem("plugin-invocation-invalid")
        return self._session(
            root,
            project_id,
            session_id,
            lambda path, session: self._current_authorization(path, session, package_token, request, actor)[1],
        )

    def current_grant(self, root: str, project_id: str, session_id: str, plugin_id: str) -> PluginProjectGrant | None:
        """Read current project authority under the same native session fence."""

        return self._session(
            root,
            project_id,
            session_id,
            lambda path, session: self._grant_repository_factory(path, session.project_id).current_grant(plugin_id),
        )

    def record_denial(
        self,
        root: str,
        project_id: str,
        session_id: str,
        *,
        plugin_id: str,
        invocation_id: str,
        reason_code: str,
        actor: PluginGrantActor,
    ) -> None:
        """Persist only stable denial codes; no worker text or scientific content."""

        self._session(
            root,
            project_id,
            session_id,
            lambda path, session: self._grant_repository_factory(path, session.project_id).record_denial(
                plugin_id=plugin_id, invocation_id=invocation_id, reason_code=reason_code, actor=actor
            ),
        )

    def revoke(
        self,
        root: str,
        project_id: str,
        session_id: str,
        plugin_id: str,
        expected_revision: int,
        action_id: str,
        *,
        actor: PluginGrantActor,
    ) -> PluginGrantStatus:
        def revoke(path: Path, session: _ProjectSession) -> PluginGrantStatus:
            grants = self._grant_repository_factory(path, session.project_id)
            grants.revoke(plugin_id, expected_revision=expected_revision, action_id=action_id, actor=actor)
            return PluginGrantStatus(
                plugin_id=plugin_id,
                status="disabled",
                revision=expected_revision + 1,
                package_sha256=None,
                manifest_sha256=None,
                permissions=(),
                destinations=(),
            )

        return self._session(root, project_id, session_id, revoke)
