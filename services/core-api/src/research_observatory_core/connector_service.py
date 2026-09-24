"""Core-held exact-request consent, fenced by current canonical project authority.

A preview/confirmation is valid only in this open local service session. It is
not a portable egress grant. Durable pages carry its fingerprint and current
Intent/privacy/rights dependencies; restart requires a new explicit confirmation.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from pydantic import Field, model_validator

from .connectors.broker import utc_now
from .connectors.contracts import ConnectorModel, ConnectorRequest, InvocationId, RequestDigest, SourceTerms, UtcInstant
from .connectors.providers import HOSTS, ProviderProblem, compile_request, source_terms
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ingestion.import_drafts import ImportRights
from .ingestion.preview_workflow import PreviewIntentContext
from .ports.connector_runtime import (
    ConnectorAuthority,
    ConnectorAuthorityStamp,
    ConnectorPageRepository,
    ConnectorStage,
)
from .ports.repositories import IntentRevisionRepository, RepositoryProblem
from .privacy import PrivacyPolicyProblem, ProjectPrivacyService
from .projects import ProjectLifecycleProblem, ProjectLifecycleService
from .research_intents import validated_workflow_authority


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class ConnectorRetention(ConnectorModel):
    """Researcher's action-specific response rights, not inferred from public access.

    No full text, export, share or model-use permission is inferred. With the
    body disabled, only named fields plus identity/terms observations survive.
    """

    rights: ImportRights = Field(default_factory=ImportRights)
    retain_body: bool = Field(default=False, strict=True)
    permitted_fields: tuple[Annotated[str, Field(strict=True, min_length=1, max_length=128)], ...] = Field(
        default=(), max_length=64
    )

    @model_validator(mode="after")
    def exact_fields(self) -> ConnectorRetention:
        if len(set(self.permitted_fields)) != len(self.permitted_fields) or (
            self.retain_body and self.permitted_fields
        ):
            raise ValueError("connector-retention-fields-invalid")
        return self


class ConnectorPreview(ConnectorModel):
    preview_id: InvocationId
    request: ConnectorRequest = Field(repr=False)
    request_sha256: RequestDigest
    destination_host: str
    retention: ConnectorRetention
    terms: SourceTerms
    intent_revision_id: InvocationId
    intent_sha256: RequestDigest
    policy_sha256: RequestDigest
    expires_at: UtcInstant
    confirmation: str = Field(repr=False)


@dataclass(frozen=True, slots=True)
class ConnectorProjectAdapters:
    intents: IntentRevisionRepository
    pages: ConnectorPageRepository


@dataclass(slots=True)
class _Binding:
    path: Path
    project_id: str
    adapters: ConnectorProjectAdapters
    session_id: str = field(default_factory=lambda: secrets.token_hex(16), repr=False)
    stopped: threading.Event = field(default_factory=threading.Event)


@dataclass(slots=True)
class _Pending:
    binding: _Binding
    preview: ConnectorPreview
    stamp: ConnectorAuthorityStamp
    intent: PreviewIntentContext
    expires: float
    confirmed: bool = False


class _ConfirmedAuthority:
    def __init__(self, service: ConnectorConsentService, pending: _Pending):
        self._service, self._pending = service, pending

    def guard[Result](
        self, request: ConnectorRequest, stage: ConnectorStage, action: Callable[[ConnectorAuthorityStamp], Result]
    ) -> Result:
        return self._service._guard(self._pending, request, stage, action)


class ConnectorConsentService:
    def __init__(
        self,
        projects: ProjectLifecycleService,
        privacy: ProjectPrivacyService,
        adapters: Callable[[Path, str], ConnectorProjectAdapters],
        *,
        local_actor_id: str,
        now: Callable[[], str] = utc_now,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not is_uuid_v7(local_actor_id):
            raise ProviderProblem("policy-denied")
        self._projects, self._privacy, self._adapters = projects, privacy, adapters
        self._actor, self._now, self._clock = local_actor_id, now, clock
        self._bindings: dict[Path, _Binding] = {}
        self._pending: dict[str, _Pending] = {}
        self._mutex = threading.RLock()
        self._stopped = False

    def _action[Result](self, root: str, action: Callable[[_Binding], Result]) -> Result:
        def bound(path: Path, identity: str) -> Result:
            # Order is always lifecycle -> consent. Retain both for bounded I/O,
            # never while waiting on the network or a rate bucket.
            with self._mutex:
                if self._stopped:
                    raise ProviderProblem("policy-denied")
                binding = self._bindings.get(path)
                if binding is None:
                    binding = _Binding(path, identity, self._adapters(path, identity))
                    self._bindings[path] = binding
                if binding.project_id != identity or binding.stopped.is_set():
                    raise ProviderProblem("policy-denied")
                return action(binding)

        try:
            return self._projects.perform_open_project_action(root=root, require_write=True, action=bound)
        except ProjectLifecycleProblem, PrivacyPolicyProblem, RepositoryProblem:
            raise ProviderProblem("policy-denied") from None

    def _current(self, binding: _Binding, request: ConnectorRequest) -> tuple[PreviewIntentContext, str]:
        if request.project_id != binding.project_id:
            raise ProviderProblem("policy-denied")
        try:
            request.assert_resumable(self._now())
        except ValueError:
            raise ProviderProblem("invalid-cursor") from None
        compile_request(request)  # reject unsupported semantics before any grant
        policy = self._privacy.get(str(binding.path))
        if (
            policy.project_id != binding.project_id
            or policy.network_policy.value != "approved-providers"
            or not policy.egress_consent_recorded
            or policy.egress_enforcement.value != "require-task-preview"
        ):
            raise ProviderProblem("policy-denied")
        bridge = binding.adapters.intents.project_identity()
        if bridge is None or bridge.manifest_project_id != binding.project_id:
            raise ProviderProblem("policy-denied")
        _, revisions, _, _ = validated_workflow_authority(
            binding.adapters.intents, expected_project_id=bridge.domain_project_id
        )
        accepted = next((item for item in revisions if item.get("status") == "accepted"), None)
        if accepted is None or accepted.get("projectId") != bridge.domain_project_id:
            raise ProviderProblem("policy-denied")
        declaration = accepted.get("egressPolicy")
        # Redacted mode requires a verified redaction path, not a caller's claim
        # that arbitrary query text has been redacted. No such path is implied.
        if not isinstance(declaration, Mapping) or (
            declaration.get("mode") != "approved-content"
            or request.provider_id not in declaration.get("approvedDestinationIds", ())
        ):
            raise ProviderProblem("policy-denied")
        intent = PreviewIntentContext.model_validate(
            {
                "projectId": binding.project_id,
                "domainProjectId": bridge.domain_project_id,
                "intentId": accepted["intentId"],
                "revisionId": accepted["revisionId"],
                "contentHash": accepted["revisionContentHash"],
                "status": "accepted",
            }
        )
        return intent, _fingerprint(policy.model_dump(mode="json", by_alias=True))

    def preview(self, root: str, request: ConnectorRequest, retention: ConnectorRetention) -> ConnectorPreview:
        request, retention = ConnectorRequest.model_validate(request), ConnectorRetention.model_validate(retention)

        def preview(binding: _Binding) -> ConnectorPreview:
            intent, policy_hash = self._current(binding, request)
            if not retention.rights.permits("store") or not retention.rights.permits("inspect"):
                raise ProviderProblem("permission-denied")
            now = self._clock()
            self._pending = {
                key: value
                for key, value in self._pending.items()
                if value.expires > now and not value.binding.stopped.is_set()
            }
            if len(self._pending) >= 64:
                raise ProviderProblem("rate-limit")
            identity = new_uuid_v7()
            request_hash = _fingerprint(request.model_dump(mode="json", by_alias=True))
            expires = (datetime.fromisoformat(self._now().replace("Z", "+00:00")) + timedelta(minutes=10)).astimezone(
                UTC
            )
            result = ConnectorPreview(
                preview_id=identity,
                request=request,
                request_sha256=request_hash,
                destination_host=HOSTS[request.provider_id],
                retention=retention,
                terms=source_terms(request.provider_id),
                intent_revision_id=intent.revision_id,
                intent_sha256=intent.content_hash,
                policy_sha256=policy_hash,
                expires_at=expires.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                confirmation=f"send-metadata:{identity}:{secrets.token_hex(16)}",
            )
            checkpoint = binding.adapters.pages.checkpoint(request)
            stamp = ConnectorAuthorityStamp(
                binding.project_id,
                binding.session_id,
                intent.revision_id,
                intent.content_hash,
                policy_hash,
                _fingerprint(result.model_dump(mode="json", by_alias=True)),
                _fingerprint(retention.model_dump(mode="json", by_alias=True)),
                retention.retain_body,
                self._actor,
                expected_checkpoint_revision_id=checkpoint[0] if checkpoint else None,
                permitted_fields=retention.permitted_fields,
            )
            self._pending[identity] = _Pending(binding, result, stamp, intent, now + 600)
            return result

        return self._action(root, preview)

    def _selected(self, binding: _Binding, identity: str, *, confirmed: bool) -> _Pending:
        pending = self._pending.get(identity)
        if (
            pending is None
            or pending.binding is not binding
            or pending.expires <= self._clock()
            or (confirmed and not pending.confirmed)
        ):
            raise ProviderProblem("policy-denied")
        current = self._current(binding, pending.preview.request)
        if current != (pending.intent, pending.stamp.policy_sha256):
            raise ProviderProblem("policy-denied")
        return pending

    def confirm(self, root: str, preview_id: str, *, confirmation: str) -> None:
        def confirm(binding: _Binding) -> None:
            pending = self._selected(binding, preview_id, confirmed=False)
            if not secrets.compare_digest(confirmation, pending.preview.confirmation):
                raise ProviderProblem("policy-denied")
            pending.confirmed = True

        self._action(root, confirm)

    def authority(self, root: str, preview_id: str) -> ConnectorAuthority:
        """Internal worker composition only; an HTTP response never contains this object."""
        return self._action(
            root, lambda binding: _ConfirmedAuthority(self, self._selected(binding, preview_id, confirmed=True))
        )

    def confirmed_action[Result](self, root: str, preview_id: str, action: Callable[[_Pending], Result]) -> Result:
        """Trusted workflow composition under the same authority lock, never an API grant."""
        return self._action(root, lambda binding: action(self._selected(binding, preview_id, confirmed=True)))

    def _guard[Result](
        self,
        pending: _Pending,
        request: ConnectorRequest,
        stage: ConnectorStage,
        action: Callable[[ConnectorAuthorityStamp], Result],
    ) -> Result:
        def guarded(binding: _Binding) -> Result:
            selected = self._selected(binding, pending.preview.preview_id, confirmed=True)
            if (
                selected is not pending
                or request != pending.preview.request
                or stage not in {"admission", "cache", "dispatch", "publication"}
            ):
                raise ProviderProblem("policy-denied")
            return action(pending.stamp)

        return self._action(str(pending.binding.path), guarded)

    def revoke(self, root: str, preview_id: str) -> None:
        def revoke(binding: _Binding) -> None:
            pending = self._pending.get(preview_id)
            if pending is not None and pending.binding is binding:
                self._pending.pop(preview_id)

        self._action(root, revoke)

    def attach(self, root: str) -> None:
        self._action(root, lambda _: None)

    def detach(self, root: str) -> None:
        with self._mutex:
            binding = self._bindings.pop(Path(root), None)
            if binding is not None:
                binding.stopped.set()
                self._pending = {key: value for key, value in self._pending.items() if value.binding is not binding}

    def shutdown(self) -> None:
        with self._mutex:
            self._stopped = True
            for binding in self._bindings.values():
                binding.stopped.set()
            self._bindings.clear()
            self._pending.clear()
