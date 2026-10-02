"""Core-held exact-request consent for one signed plugin invocation.

Package trust and a project grant never imply network consent. This ephemeral
authority binds an accepted Intent, current privacy policy, exact request,
retention decision and researcher confirmation; restart always revokes it.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field

from .connector_service import ConnectorRetention, _fingerprint
from .connectors.plugin_grants import PluginGrantActor
from .connectors.plugin_manifest import (
    DataClass,
    Permission,
    PluginDestination,
    PluginInvocationPlan,
    PluginInvocationRequest,
    PluginTerms,
)
from .domain_contracts import new_uuid_v7
from .ingestion.preview_workflow import PreviewIntentContext
from .models import ContractModel
from .plugin_admin_service import PluginAdminService, PluginAuthorizedDispatch
from .ports.repositories import IntentRevisionRepository
from .privacy import ProjectPrivacyService
from .projects import ProjectLifecycleService
from .research_intents import validated_workflow_authority

_TTL_SECONDS = 600.0
_MAX_PENDING = 4
type PluginConsentStage = Literal["admission", "dispatch", "broker", "publication"]


class PluginConsentProblem(ValueError):
    def __init__(self) -> None:
        super().__init__("plugin-consent-denied")


def intent_destination_id(plan: PluginInvocationPlan) -> str:
    """Give every valid plugin source a stable ID within Intent's 100-char bound."""

    if not isinstance(plan, PluginInvocationPlan):
        raise PluginConsentProblem()
    if len(plan.source_id) <= 100:
        return plan.source_id
    return "plugin.sha256." + hashlib.sha256(plan.source_id.encode("ascii")).hexdigest()


class PluginConsentPreview(ContractModel):
    preview_id: str
    project_id: str
    invocation_id: str
    source_id: str
    intent_destination_id: str
    operation: str
    destination: PluginDestination
    permissions: tuple[Permission, ...]
    data_classes: tuple[DataClass, ...]
    declared_terms: PluginTerms
    retention: ConnectorRetention
    package_sha256: str
    manifest_sha256: str
    request_sha256: str
    intent_revision_id: str
    policy_sha256: str
    expires_at: str
    confirmation: str = Field(repr=False)


@dataclass(frozen=True, slots=True)
class PluginConsentStamp:
    preview_id: str
    session_id: str
    request_sha256: str
    confirmation_sha256: str
    policy_sha256: str
    retention_sha256: str
    intent: PreviewIntentContext


@dataclass(slots=True)
class _Binding:
    path: Path
    project_id: str
    session_id: str = field(default_factory=lambda: secrets.token_hex(16))


@dataclass(slots=True)
class _Pending:
    binding: _Binding
    admitted: PluginAuthorizedDispatch
    request: PluginInvocationRequest
    actor: PluginGrantActor
    retention: ConnectorRetention
    preview: PluginConsentPreview
    intent: PreviewIntentContext
    policy_sha256: str
    expires: float
    confirmed: bool = False


class PluginConsentAuthority:
    def __init__(self, service: PluginConsentService, pending: _Pending) -> None:
        self._service, self._pending = service, pending

    @property
    def plan(self) -> PluginInvocationPlan:
        """Frozen preview identity; guard rechecks before each consequential use."""

        return self._pending.admitted.plan

    def guard[Result](
        self,
        request: PluginInvocationRequest,
        plan: PluginInvocationPlan,
        stage: PluginConsentStage,
        action: Callable[[PluginConsentStamp], Result],
    ) -> Result:
        return self._service._guard(self._pending, request, plan, stage, action)


class PluginConsentService:
    def __init__(
        self,
        projects: ProjectLifecycleService,
        privacy: ProjectPrivacyService,
        admin: PluginAdminService,
        intents: Callable[[Path, str], IntentRevisionRepository],
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._projects, self._privacy, self._admin, self._intents = projects, privacy, admin, intents
        self._clock, self._now = clock, now
        self._mutex = threading.RLock()
        self._bindings: dict[Path, _Binding] = {}
        self._pending: dict[str, _Pending] = {}
        self._stopped = False

    def _action[Result](self, root: str, action: Callable[[_Binding], Result]) -> Result:
        def bound(path: Path, identity: str) -> Result:
            with self._mutex:
                if self._stopped:
                    raise PluginConsentProblem()
                binding = self._bindings.get(path)
                if binding is None:
                    binding = _Binding(path, identity)
                    self._bindings[path] = binding
                if binding.project_id != identity:
                    raise PluginConsentProblem()
                return action(binding)

        try:
            return self._projects.perform_open_project_action(root=root, require_write=True, action=bound)
        except PluginConsentProblem:
            raise
        except Exception:
            raise PluginConsentProblem() from None

    def _current(
        self, binding: _Binding, plan: PluginInvocationPlan, request: PluginInvocationRequest
    ) -> tuple[PreviewIntentContext, str]:
        if (
            request.project_id != binding.project_id
            or plan.project_id != binding.project_id
            or plan.invocation_id != request.invocation_id
            or plan.scientific_request_sha256 != request.scientific_request_sha256
            or plan.operation != request.operation
            or plan.destination != request.destination
        ):
            raise PluginConsentProblem()
        policy = self._privacy.get(str(binding.path))
        if (
            policy.project_id != binding.project_id
            or policy.network_policy.value != "approved-providers"
            or not policy.egress_consent_recorded
            or policy.egress_enforcement.value != "require-task-preview"
        ):
            raise PluginConsentProblem()
        repository = self._intents(binding.path, binding.project_id)
        bridge = repository.project_identity()
        if bridge is None or bridge.manifest_project_id != binding.project_id:
            raise PluginConsentProblem()
        _, revisions, _, _ = validated_workflow_authority(repository, expected_project_id=bridge.domain_project_id)
        accepted = next((item for item in revisions if item.get("status") == "accepted"), None)
        if accepted is None or accepted.get("projectId") != bridge.domain_project_id:
            raise PluginConsentProblem()
        declaration = accepted.get("egressPolicy")
        if (
            not isinstance(declaration, Mapping)
            or declaration.get("mode") != "approved-content"
            or intent_destination_id(plan) not in declaration.get("approvedDestinationIds", ())
        ):
            raise PluginConsentProblem()
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

    def preview(
        self,
        root: str,
        project_id: str,
        package_sha256: str,
        manifest_sha256: str,
        request: PluginInvocationRequest,
        retention: ConnectorRetention,
        *,
        actor: PluginGrantActor,
    ) -> PluginConsentPreview:
        request = PluginInvocationRequest.model_validate(request)
        retention = ConnectorRetention.model_validate(retention)

        def create(binding: _Binding) -> PluginConsentPreview:
            if (
                binding.project_id != project_id
                or not retention.retain_body
                or not all(retention.rights.permits(purpose) for purpose in ("store", "inspect"))
            ):
                raise PluginConsentProblem()
            admitted = self._admin.prepare_persisted_invocation(
                root, project_id, package_sha256, manifest_sha256, request, actor=actor
            )
            intent, policy_sha256 = self._current(binding, admitted.plan, request)
            now = self._clock()
            self._pending = {
                key: value
                for key, value in self._pending.items()
                if value.expires > now and value.binding is not binding
            }
            if len(self._pending) >= _MAX_PENDING:
                raise PluginConsentProblem()
            identity = new_uuid_v7()
            confirmation = f"send-plugin-metadata:{identity}:{secrets.token_hex(16)}"
            preview = PluginConsentPreview(
                preview_id=identity,
                project_id=project_id,
                invocation_id=request.invocation_id,
                source_id=admitted.plan.source_id,
                intent_destination_id=intent_destination_id(admitted.plan),
                operation=request.operation,
                destination=admitted.plan.destination,
                permissions=admitted.plan.permissions,
                data_classes=admitted.package.manifest.data_classes,
                declared_terms=admitted.package.manifest.terms,
                retention=retention,
                package_sha256=package_sha256,
                manifest_sha256=manifest_sha256,
                request_sha256=admitted.plan.request_sha256,
                intent_revision_id=intent.revision_id,
                policy_sha256=policy_sha256,
                expires_at=(self._now() + timedelta(seconds=_TTL_SECONDS))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                confirmation=confirmation,
            )
            self._pending[identity] = _Pending(
                binding,
                admitted,
                request,
                actor,
                retention,
                preview,
                intent,
                policy_sha256,
                now + _TTL_SECONDS,
            )
            return preview

        return self._action(root, create)

    def _selected(self, binding: _Binding, preview_id: str, *, confirmed: bool) -> _Pending:
        pending = self._pending.get(preview_id)
        if (
            pending is None
            or pending.binding is not binding
            or pending.expires <= self._clock()
            or (confirmed and not pending.confirmed)
        ):
            raise PluginConsentProblem()
        return pending

    def confirm(self, root: str, project_id: str, preview_id: str, *, confirmation: str) -> None:
        def decide(binding: _Binding) -> None:
            if binding.project_id != project_id:
                raise PluginConsentProblem()
            pending = self._selected(binding, preview_id, confirmed=False)
            if not isinstance(confirmation, str) or not secrets.compare_digest(
                confirmation, pending.preview.confirmation
            ):
                raise PluginConsentProblem()
            pending.confirmed = True

        self._action(root, decide)

    def authority(self, root: str, preview_id: str) -> PluginConsentAuthority:
        return self._action(
            root, lambda binding: PluginConsentAuthority(self, self._selected(binding, preview_id, confirmed=True))
        )

    def _guard[Result](
        self,
        pending: _Pending,
        request: PluginInvocationRequest,
        plan: PluginInvocationPlan,
        stage: PluginConsentStage,
        action: Callable[[PluginConsentStamp], Result],
    ) -> Result:
        def guarded(binding: _Binding) -> Result:
            current = self._selected(binding, pending.preview.preview_id, confirmed=True)
            if (
                current is not pending
                or request != pending.request
                or plan != pending.admitted.plan
                or stage not in {"admission", "dispatch", "broker", "publication"}
            ):
                raise PluginConsentProblem()
            checked = self._admin.recheck_admitted_invocation(
                str(binding.path), binding.project_id, pending.admitted, request, actor=pending.actor
            )
            intent, policy_sha256 = self._current(binding, checked, request)
            if checked != plan or intent != pending.intent or policy_sha256 != pending.policy_sha256:
                raise PluginConsentProblem()
            stamp = PluginConsentStamp(
                preview_id=pending.preview.preview_id,
                session_id=binding.session_id,
                request_sha256=plan.request_sha256,
                confirmation_sha256="sha256:"
                + hashlib.sha256(pending.preview.confirmation.encode("ascii")).hexdigest(),
                policy_sha256=policy_sha256,
                retention_sha256=_fingerprint(pending.retention.model_dump(mode="json", by_alias=True)),
                intent=intent,
            )
            return action(stamp)

        return self._action(str(pending.binding.path), guarded)

    def revoke(self, root: str, preview_id: str) -> None:
        def drop(binding: _Binding) -> None:
            pending = self._pending.get(preview_id)
            if pending is not None and pending.binding is binding:
                self._pending.pop(preview_id)

        self._action(root, drop)

    def detach(self, root: str) -> None:
        with self._mutex:
            binding = self._bindings.pop(Path(root), None)
            if binding is not None:
                self._pending = {key: value for key, value in self._pending.items() if value.binding is not binding}

    def shutdown(self) -> None:
        with self._mutex:
            self._stopped = True
            self._pending.clear()
            self._bindings.clear()
