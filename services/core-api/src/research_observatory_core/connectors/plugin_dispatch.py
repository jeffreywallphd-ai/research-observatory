"""Core-only dispatch of an authorized connector into an injected signed LPAC runtime.

The production composition must supply an application-pinned runtime and the
packaged Windows launcher. There is deliberately no fallback runner. A returned
object is an encrypted, uncommitted stage; the workflow queue owns publication.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from pydantic import Field

from ..plugin_admin_service import PluginAdminService
from ..ports.object_store import ObjectPutCommand, ObjectStore, StoredObject
from .broker import utc_now
from .contracts import ConnectorModel, ObjectDigest
from .plugin_broker import PluginBrokerCall, PluginBrokerRates, PluginNetworkBroker
from .plugin_grants import PluginGrantActor
from .plugin_manifest import PluginInvocationPlan, PluginInvocationRequest
from .plugin_result import PluginResultProblem, PluginValidatedPage, validate_plugin_output
from .plugin_scientific_request import PluginScientificRequestProblem, parse_plugin_scientific_request
from .transport import bounded_json

_MAX_BINARY = 10 * 1_048_576
_MAX_BROKER_CALLS = 64


class PluginDispatchProblem(ValueError):
    """A content-free failure category for the owning workflow attempt."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ConnectorRunner(Protocol):
    def __call__(
        self,
        runtime: object,
        package: object,
        package_files: dict[str, bytes],
        *,
        job_nonce: str,
        invocation_id: str,
        operation: str,
        input_data: bytes,
        broker_callback: Callable[[dict[str, Any]], bytes],
        cancelled: Callable[[], bool],
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class PluginStagedOutput:
    """Encrypted worker output and sanitized broker bodies, still uncommitted."""

    object_sha256: str
    byte_length: int
    broker_calls: int
    retrieved_at: str
    validated_page: PluginValidatedPage
    broker_responses: tuple[PluginBrokerResponseRef, ...]


class PluginBrokerResponseRef(ConnectorModel):
    """A Core-staged sanitized broker body, never worker-selected authority."""

    object_sha256: ObjectDigest
    byte_length: Annotated[int, Field(strict=True, ge=1, le=_MAX_BINARY)]


class PluginDispatchController:
    def __init__(
        self,
        admin: PluginAdminService,
        *,
        runtime_provider: Callable[[], object],
        runner: ConnectorRunner,
        object_store: Callable[[str], ObjectStore | None],
        current_request: Callable[[str, str], PluginInvocationRequest | None],
        policy_recheck: Callable[[PluginInvocationPlan, PluginBrokerCall | None], None],
        current_credential_origin: Callable[[str, PluginInvocationPlan], tuple[str, str, int] | None],
        cancelled: Callable[[str], bool],
        lease_secret: Callable[[str, PluginInvocationPlan], AbstractContextManager[str]] | None = None,
        rates: PluginBrokerRates | None = None,
    ) -> None:
        if not all(
            callable(value)
            for value in (
                runtime_provider,
                runner,
                object_store,
                current_request,
                policy_recheck,
                current_credential_origin,
                cancelled,
            )
        ):
            raise ValueError("plugin-dispatch-authority-required")
        self._admin, self._runtime_provider, self._runner = admin, runtime_provider, runner
        self._object_store, self._current_request = object_store, current_request
        self._policy_recheck, self._credential_origin = policy_recheck, current_credential_origin
        self._cancelled, self._lease_secret = cancelled, lease_secret
        self._rates = rates or PluginBrokerRates()
        self._active_mutex = threading.Lock()
        self._active_projects: set[str] = set()

    async def dispatch(
        self,
        *,
        root: str,
        project_id: str,
        session_id: str,
        package_token: str,
        request: PluginInvocationRequest,
        input_data: bytes,
        actor: PluginGrantActor,
    ) -> PluginStagedOutput:
        """Admit at most one connector job for each project in this Core instance."""

        with self._active_mutex:
            if project_id in self._active_projects:
                raise PluginDispatchProblem("plugin-project-busy")
            self._active_projects.add(project_id)
        try:
            return await self._dispatch(
                root=root,
                project_id=project_id,
                session_id=session_id,
                package_token=package_token,
                package_sha256=None,
                manifest_sha256=None,
                signature_sha256=None,
                request=request,
                input_data=input_data,
                actor=actor,
            )
        finally:
            with self._active_mutex:
                self._active_projects.discard(project_id)

    async def dispatch_persisted(
        self,
        *,
        root: str,
        project_id: str,
        package_sha256: str,
        manifest_sha256: str,
        signature_sha256: str,
        request: PluginInvocationRequest,
        input_data: bytes,
        actor: PluginGrantActor,
    ) -> PluginStagedOutput:
        """Run an already queued job from its exact signed package, not a token."""

        with self._active_mutex:
            if project_id in self._active_projects:
                raise PluginDispatchProblem("plugin-project-busy")
            self._active_projects.add(project_id)
        try:
            return await self._dispatch(
                root=root,
                project_id=project_id,
                session_id=None,
                package_token=None,
                package_sha256=package_sha256,
                manifest_sha256=manifest_sha256,
                signature_sha256=signature_sha256,
                request=request,
                input_data=input_data,
                actor=actor,
            )
        finally:
            with self._active_mutex:
                self._active_projects.discard(project_id)

    async def _dispatch(
        self,
        *,
        root: str,
        project_id: str,
        session_id: str | None,
        package_token: str | None,
        package_sha256: str | None,
        manifest_sha256: str | None,
        signature_sha256: str | None,
        request: PluginInvocationRequest,
        input_data: bytes,
        actor: PluginGrantActor,
    ) -> PluginStagedOutput:
        """Recheck every boundary and stage only after a witnessed LPAC result.

        The caller must hold a durable ADR-0025 attempt/lease and publish the
        returned object under its own transaction and fencing checks.
        """

        if (
            not isinstance(request, PluginInvocationRequest)
            or request.project_id != project_id
            or not isinstance(input_data, bytes)
            or len(input_data) > _MAX_BINARY
            or "sha256:" + hashlib.sha256(input_data).hexdigest() != request.scientific_request_sha256
        ):
            raise PluginDispatchProblem("plugin-input-invalid")
        try:
            scientific = parse_plugin_scientific_request(input_data, request.operation)
        except PluginScientificRequestProblem:
            raise PluginDispatchProblem("plugin-input-invalid") from None
        persisted = package_sha256 is not None and manifest_sha256 is not None and signature_sha256 is not None
        if persisted and session_id is None and package_token is None:
            assert package_sha256 is not None and manifest_sha256 is not None and signature_sha256 is not None
            admitted = self._admin.prepare_persisted_invocation(
                root, project_id, package_sha256, manifest_sha256, signature_sha256, request, actor=actor
            )
        elif (
            package_sha256 is None
            and manifest_sha256 is None
            and signature_sha256 is None
            and session_id is not None
            and package_token is not None
        ):
            admitted = self._admin.prepare_invocation(root, project_id, session_id, package_token, request, actor=actor)
        else:
            raise PluginDispatchProblem("plugin-authority-invalid")
        plan = admitted.plan

        def audit(code: str) -> None:
            try:
                if persisted:
                    self._admin.record_denial_persisted(
                        root,
                        project_id,
                        plugin_id=plan.plugin_id,
                        invocation_id=plan.invocation_id,
                        reason_code=code,
                        actor=actor,
                    )
                else:
                    assert session_id is not None
                    self._admin.record_denial(
                        root,
                        project_id,
                        session_id,
                        plugin_id=plan.plugin_id,
                        invocation_id=plan.invocation_id,
                        reason_code=code,
                        actor=actor,
                    )
            except Exception:
                raise PluginDispatchProblem("plugin-audit-unavailable") from None

        def check_current(call: PluginBrokerCall | None = None) -> None:
            try:
                if self._cancelled(plan.invocation_id):
                    raise ValueError
                owned = self._current_request(plan.project_id, plan.invocation_id)
                if owned is None or PluginInvocationRequest.model_validate(owned) != request:
                    raise ValueError
                current_plan = self._admin.recheck_admitted_invocation(
                    root,
                    project_id,
                    admitted,
                    request,
                    actor=actor,
                    session_id=None if persisted else session_id,
                    package_token=None if persisted else package_token,
                )
                if current_plan != plan:
                    raise ValueError
                if self._policy_recheck(plan, call) is not None:
                    raise ValueError
            except Exception:
                raise PluginDispatchProblem("plugin-policy-denied") from None

        try:
            check_current()
        except PluginDispatchProblem as error:
            audit(error.code)
            raise
        try:
            runtime = self._runtime_provider()
            if runtime is None:
                raise ValueError
        except Exception:
            audit("plugin-runtime-unavailable")
            raise PluginDispatchProblem("plugin-runtime-unavailable") from None

        def current_grant(owned_project: str, plugin_id: str):
            if owned_project != project_id:
                return None
            if persisted:
                return self._admin.current_grant_persisted(root, project_id, plugin_id)
            assert session_id is not None
            return self._admin.current_grant(root, project_id, session_id, plugin_id)

        broker = PluginNetworkBroker(
            package=admitted.package,
            current_grant=current_grant,
            current_request=self._current_request,
            recheck=lambda current_plan, call: check_current(call) if current_plan == plan else check_current_denied(),
            audit_denial=audit,
            current_credential_origin=self._credential_origin,
            rates=self._rates,
            lease_secret=self._lease_secret,
        )
        loop = asyncio.get_running_loop()
        broker_failed = threading.Event()
        broker_attempt_lock = threading.Lock()
        broker_attempts = 0
        observed_search_cursors: list[str | None] = []
        broker_responses: list[tuple[int, PluginBrokerResponseRef]] = []

        def stage_object(body: bytes) -> StoredObject:
            if not isinstance(body, bytes) or not 0 < len(body) <= _MAX_BINARY:
                raise ValueError("plugin-stage-body-invalid")
            store = self._object_store(plan.project_id)
            if store is None:
                raise ValueError("plugin-stage-store-unavailable")
            digest = hashlib.sha256(body).hexdigest()
            stored = store.put(
                io.BytesIO(body),
                ObjectPutCommand(
                    media_type="application/json",
                    # This records only the currently authorized local stage
                    # and inspection. It grants no export, model or sharing use.
                    rights_status="allowed",
                    protection_profile="project-encrypted-v1",
                    retention_class="project-lifetime",
                    creation_source="connector-acquisition",
                    created_at=actor.occurred_at,
                    expected_sha256=digest,
                ),
            )
            if (
                not isinstance(stored, StoredObject)
                or stored.protection_profile != "project-encrypted-v1"
                or stored.rights_status != "allowed"
                or stored.retention_class != "project-lifetime"
                or stored.byte_length != len(body)
                or stored.object_sha256 != digest
            ):
                raise ValueError("plugin-stage-result-invalid")
            return stored

        def broker_callback(frame: dict[str, Any]) -> bytes:
            nonlocal broker_attempts
            try:
                with broker_attempt_lock:
                    permitted = broker_attempts < (1 if plan.operation == "search" else _MAX_BROKER_CALLS)
                    broker_attempts += 1
                    attempt_index = broker_attempts
                if not permitted:
                    audit("plugin-broker-call-invalid")
                    raise PluginDispatchProblem("plugin-broker-call-invalid")
                try:
                    call = PluginBrokerCall.model_validate(frame)
                except Exception:
                    audit("plugin-broker-call-invalid")
                    raise PluginDispatchProblem("plugin-broker-call-invalid") from None
                if call.model_copy(update={"credential_scope": None}) != scientific.call:
                    audit("policy-denied")
                    raise PluginDispatchProblem("plugin-policy-denied")
                future = asyncio.run_coroutine_threadsafe(broker.fetch(plan, call), loop)
                deadline = time.monotonic() + 35
                while True:
                    try:
                        response = future.result(timeout=max(0.01, min(0.1, deadline - time.monotonic())))
                        break
                    except FutureTimeout:
                        if self._cancelled(plan.invocation_id):
                            future.cancel()
                            audit("plugin-worker-cancelled")
                            raise PluginDispatchProblem("plugin-worker-cancelled") from None
                        if time.monotonic() >= deadline:
                            future.cancel()
                            audit("plugin-broker-timeout")
                            raise PluginDispatchProblem("plugin-broker-timeout") from None
                try:
                    check_current(call)
                except PluginDispatchProblem as error:
                    audit(error.code)
                    raise
                # The broker supplies sanitized JSON; retain exactly those
                # validated bytes, never an unsanitized wire response.
                body = bounded_json(response.body)
                if plan.operation == "search":
                    if not isinstance(body, dict):
                        raise PluginDispatchProblem("plugin-worker-output-invalid")
                    cursor = body.get("nextCursor")
                    if cursor is not None:
                        try:
                            PluginBrokerCall.model_validate(
                                {
                                    **scientific.call.model_dump(mode="json", by_alias=True, exclude_none=True),
                                    "cursor": cursor,
                                }
                            )
                        except Exception:
                            raise PluginDispatchProblem("plugin-worker-output-invalid") from None
                stored_response = stage_object(response.body)
                try:
                    check_current(call)
                except PluginDispatchProblem as error:
                    audit(error.code)
                    raise
                broker_responses.append(
                    (
                        attempt_index,
                        PluginBrokerResponseRef(
                            object_sha256=stored_response.object_sha256,
                            byte_length=stored_response.byte_length,
                        ),
                    )
                )
                if plan.operation == "search":
                    observed_search_cursors.append(cursor)
                return response.body
            except Exception:
                # A worker may catch a broker exception and still return a
                # syntactically valid page. The Core stage must remain poisoned.
                broker_failed.set()
                raise

        def check_current_denied() -> None:
            raise PluginDispatchProblem("plugin-policy-denied")

        try:
            result = await asyncio.to_thread(
                self._runner,
                runtime,
                admitted.package,
                admitted.files,
                job_nonce=secrets.token_hex(16),
                invocation_id=plan.invocation_id,
                operation=plan.operation,
                input_data=input_data,
                broker_callback=broker_callback,
                cancelled=lambda: self._cancelled(plan.invocation_id),
            )
        except Exception:
            audit("plugin-worker-failed")
            raise PluginDispatchProblem("plugin-worker-failed") from None
        if broker_failed.is_set():
            audit("plugin-worker-failed")
            raise PluginDispatchProblem("plugin-worker-failed")
        output = getattr(result, "output", None)
        token = getattr(result, "token", None)
        calls = getattr(result, "broker_calls", None)
        if (
            not isinstance(output, bytes)
            or len(output) > _MAX_BINARY
            or not isinstance(token, dict)
            or token.get("appContainer") is not True
            or token.get("lessPrivileged") is not True
            or token.get("allApplicationPackagesDenied") is not True
            or type(token.get("capabilityCount")) is not int
            or token["capabilityCount"] != 0
            or type(calls) is not int
            or not 1 <= calls <= _MAX_BROKER_CALLS
        ):
            audit("plugin-worker-result-invalid")
            raise PluginDispatchProblem("plugin-worker-result-invalid")
        if calls != len(broker_responses):
            audit("plugin-worker-result-invalid")
            raise PluginDispatchProblem("plugin-worker-result-invalid")
        retrieved_at = utc_now()
        try:
            validated_page = validate_plugin_output(plan, output, retrieved_at=retrieved_at)
        except PluginResultProblem:
            audit("plugin-worker-output-invalid")
            raise PluginDispatchProblem("plugin-worker-output-invalid") from None
        if plan.operation == "search" and (
            len(observed_search_cursors) != 1
            or calls != 1
            or validated_page.next_cursor != observed_search_cursors[0]
            or (validated_page.next_cursor is not None and validated_page.next_cursor == scientific.call.cursor)
        ):
            audit("plugin-worker-output-invalid")
            raise PluginDispatchProblem("plugin-worker-output-invalid")
        try:
            check_current()
        except PluginDispatchProblem as error:
            audit(error.code)
            raise
        try:
            stored = await asyncio.to_thread(stage_object, output)
        except Exception:
            audit("plugin-stage-failed")
            raise PluginDispatchProblem("plugin-stage-failed") from None
        try:
            check_current()
        except PluginDispatchProblem as error:
            # A content-addressed orphan is reconciled by the existing project
            # storage cleanup; this method never reports it as a committed page.
            audit(error.code)
            raise
        ordered_responses = tuple(ref for _, ref in sorted(broker_responses, key=lambda entry: entry[0]))
        return PluginStagedOutput(
            stored.object_sha256, stored.byte_length, calls, retrieved_at, validated_page, ordered_responses
        )
