"""Bounded native-only consent and durable plugin invocation commands."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute
from pydantic import Field

from .connector_service import ConnectorRetention
from .connectors.plugin_credentials import PluginCredentialProblem, PluginCredentialStatus
from .connectors.plugin_grants import PluginGrantProblem
from .connectors.plugin_manifest import PluginInvocationRequest
from .models import ContractModel, ProblemDetail
from .plugin_admin_service import PluginAdminService
from .plugin_api import _problem
from .plugin_consent import PluginConsentPreview, PluginConsentProblem, PluginConsentService
from .plugin_job_repository import PluginJobRepositoryProblem
from .plugin_worker import PluginWorkerProblem, PluginWorkerService
from .ports.object_store import ObjectStoreProblem
from .ports.workflow_executor import WorkflowJobRecord, WorkflowQueueProblem
from .projects import ProjectLifecycleProblem
from .transport import CoreProblem

_MAX_SUBMISSION = 128 * 1024


class _BoundedInvocationRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            maximum = 180_000 if request.url.path.endswith("/submit") else 8192
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > maximum:
                    raise _problem(request, "request-limit", status=413)
                body.extend(chunk)
            request._body = bytes(body)
            try:
                result = await handler(request)
                result.headers["Cache-Control"] = "no-store"
                return result
            finally:
                body[:] = b"\0" * len(body)
                request._body = b""

        return bounded


class PluginJobAddress(ContractModel):
    root: Annotated[str, Field(strict=True, min_length=1, max_length=4096)] = Field(repr=False)
    project_id: str


class PluginPreviewCommand(PluginJobAddress):
    package_sha256: Annotated[str, Field(strict=True, pattern=r"^sha256:[0-9a-f]{64}$")]
    manifest_sha256: Annotated[str, Field(strict=True, pattern=r"^sha256:[0-9a-f]{64}$")]
    request: PluginInvocationRequest = Field(repr=False)
    retention: ConnectorRetention


class PluginConfirmCommand(PluginJobAddress):
    preview_id: str
    confirmation: str = Field(repr=False, strict=True, min_length=1, max_length=256)


class PluginSubmitCommand(PluginJobAddress):
    preview_id: str
    request: PluginInvocationRequest = Field(repr=False)
    input_data: Annotated[str, Field(strict=True, max_length=174_764)] = Field(repr=False)

    def decoded(self) -> bytes:
        try:
            raw = base64.b64decode(self.input_data, validate=True)
        except binascii.Error, ValueError:
            raise PluginWorkerProblem("plugin-worker-input-invalid") from None
        if len(raw) > _MAX_SUBMISSION or base64.b64encode(raw).decode("ascii") != self.input_data:
            raise PluginWorkerProblem("plugin-worker-input-invalid")
        return raw


class PluginJobCommand(PluginJobAddress):
    job_id: str


class PluginCredentialCommand(PluginJobAddress):
    preview_id: str
    request: PluginInvocationRequest = Field(repr=False)
    scope: Annotated[str, Field(strict=True, min_length=1, max_length=128)]


class PluginCredentialConfigure(PluginCredentialCommand):
    secret: Annotated[str, Field(strict=True, min_length=3, max_length=1024)] = Field(repr=False)
    expected_version: Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$")] | None


class PluginCredentialProjection(ContractModel):
    configured: bool
    version: str | None
    origin: tuple[str, str, int] | None

    @classmethod
    def from_status(cls, status: PluginCredentialStatus) -> PluginCredentialProjection:
        return cls(configured=status.configured, version=status.version, origin=status.origin)


class PluginAccepted(ContractModel):
    accepted: bool


class PluginJobStatus(ContractModel):
    job_id: str
    state: str
    attempt_count: int
    diagnostic_code: str | None
    output_sha256: str | None

    @classmethod
    def from_record(cls, record: WorkflowJobRecord) -> PluginJobStatus:
        return cls(
            job_id=record.job_id,
            state=record.state,
            attempt_count=record.attempt_count,
            diagnostic_code=record.diagnostic_code,
            output_sha256=record.committed_output_sha256,
        )


def register_plugin_invocation_routes(
    app: FastAPI,
    admin: Callable[[Request], PluginAdminService | None],
    consent: Callable[[Request], PluginConsentService | None],
    worker: Callable[[Request], PluginWorkerService | None],
    project_problem: Callable[[Request, ProjectLifecycleProblem], CoreProblem],
) -> None:
    router = APIRouter(
        prefix="/native/connectors/plugins/invocations",
        route_class=_BoundedInvocationRoute,
        include_in_schema=False,
        responses={403: {"model": ProblemDetail}, 409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
    )

    def run[Result](request: Request, action: Callable[[], Result]) -> Result:
        try:
            return action()
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from None
        except (PluginConsentProblem, PluginWorkerProblem, PluginCredentialProblem, PluginGrantProblem) as error:
            code = str(error)
            status = 403 if "denied" in code or "stale" in code else 409
            raise _problem(request, code, status=status) from None
        except PluginJobRepositoryProblem, ObjectStoreProblem, WorkflowQueueProblem:
            raise _problem(request, "unavailable", status=503) from None
        except ValueError:
            raise _problem(request, "invalid-request", status=422) from None

    @router.post("/preview", response_model=PluginConsentPreview)
    def preview(request: Request, command: PluginPreviewCommand) -> PluginConsentPreview:
        runtime, administration = consent(request), admin(request)
        if runtime is None or administration is None:
            raise _problem(request, "unavailable", status=503)
        return run(
            request,
            lambda: runtime.preview(
                command.root,
                command.project_id,
                command.package_sha256,
                command.manifest_sha256,
                command.request,
                command.retention,
                actor=administration.actor(request.state.trace_id),
            ),
        )

    @router.post("/confirm", response_model=PluginAccepted)
    def confirm(request: Request, command: PluginConfirmCommand) -> PluginAccepted:
        runtime = consent(request)
        if runtime is None:
            raise _problem(request, "unavailable", status=503)
        run(
            request,
            lambda: runtime.confirm(
                command.root,
                command.project_id,
                command.preview_id,
                confirmation=command.confirmation,
            ),
        )
        return PluginAccepted(accepted=True)

    @router.post("/submit", response_model=PluginJobStatus)
    def submit(request: Request, command: PluginSubmitCommand) -> PluginJobStatus:
        runtime = worker(request)
        if runtime is None:
            raise _problem(request, "unavailable", status=503)
        if command.request.project_id != command.project_id:
            raise _problem(request, "project-denied", status=403)
        return run(
            request,
            lambda: PluginJobStatus.from_record(
                runtime.submit(command.root, command.preview_id, command.request, command.decoded())
            ),
        )

    @router.post("/credentials/status", response_model=PluginCredentialProjection)
    def credential_status(request: Request, command: PluginCredentialCommand) -> PluginCredentialProjection:
        runtime = worker(request)
        if runtime is None:
            raise _problem(request, "unavailable", status=503)
        if command.request.project_id != command.project_id:
            raise _problem(request, "project-denied", status=403)
        return run(
            request,
            lambda: PluginCredentialProjection.from_status(
                runtime.credential_status(
                    command.root,
                    command.project_id,
                    command.preview_id,
                    command.request,
                    command.scope,
                    trace_id=request.state.trace_id,
                )
            ),
        )

    @router.post("/credentials/configure", response_model=PluginCredentialProjection)
    def credential_configure(request: Request, command: PluginCredentialConfigure) -> PluginCredentialProjection:
        runtime = worker(request)
        if runtime is None:
            raise _problem(request, "unavailable", status=503)
        if command.request.project_id != command.project_id:
            raise _problem(request, "project-denied", status=403)
        return run(
            request,
            lambda: PluginCredentialProjection.from_status(
                runtime.configure_credential(
                    command.root,
                    command.project_id,
                    command.preview_id,
                    command.request,
                    command.scope,
                    command.secret,
                    expected_version=command.expected_version,
                    trace_id=request.state.trace_id,
                )
            ),
        )

    @router.post("/status", response_model=PluginJobStatus)
    def status(request: Request, command: PluginJobCommand) -> PluginJobStatus:
        runtime = worker(request)
        if runtime is None:
            raise _problem(request, "unavailable", status=503)
        return run(
            request,
            lambda: PluginJobStatus.from_record(runtime.status(command.root, command.project_id, command.job_id)),
        )

    @router.post("/cancel", response_model=PluginAccepted)
    def cancel(request: Request, command: PluginJobCommand) -> PluginAccepted:
        runtime = worker(request)
        if runtime is None:
            raise _problem(request, "unavailable", status=503)
        run(request, lambda: runtime.cancel(command.root, command.project_id, command.job_id))
        return PluginAccepted(accepted=True)

    app.include_router(router)
