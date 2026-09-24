"""Authenticated exact-preview/confirmation endpoints; no caller egress stamp or keys."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute
from pydantic import ConfigDict, Field

from .connector_service import ConnectorPreview, ConnectorRetention
from .connector_worker import ConnectorWorkerService
from .connectors.contracts import (
    ConnectorCapabilities,
    ConnectorModel,
    ConnectorRequest,
    InvocationId,
    ProjectId,
    ProviderId,
)
from .connectors.inspection import ConnectorInspection, ConnectorRecentRuns
from .connectors.providers import HOSTS, ProviderProblem
from .connectors.settings import ConnectorConnectionStatus
from .models import ProblemDetail
from .ports.credential_store import CredentialStoreProblem, SecretAccessContext, SecretConflict, SecretPurpose
from .ports.workflow_executor import WorkflowJobRecord, WorkflowJobState, WorkflowQueueProblem
from .projects import ProjectLifecycleProblem
from .transport import CoreProblem, problem_detail


class ConnectorProjectRequest(ConnectorModel):
    root: Annotated[str, Field(strict=True, min_length=1, max_length=4096)] = Field(repr=False)


class ConnectorPreviewRequest(ConnectorProjectRequest):
    request: ConnectorRequest = Field(repr=False)
    retention: ConnectorRetention


class ConnectorConfirmationRequest(ConnectorProjectRequest):
    preview_id: InvocationId
    confirmation: Annotated[str, Field(strict=True, min_length=1, max_length=128)] = Field(repr=False)


class ConnectorJobRequest(ConnectorProjectRequest):
    job_id: InvocationId


class ConnectorInspectionRequest(ConnectorProjectRequest):
    preview_id: InvocationId
    record_offset: Annotated[int, Field(strict=True, ge=0, le=999)]


class ConnectorJobStatus(ConnectorModel):
    job_id: InvocationId
    workflow_run_id: InvocationId
    state: WorkflowJobState
    diagnostic_code: str | None


class ConnectorCapabilitiesPage(ConnectorModel):
    items: tuple[ConnectorCapabilities, ...]


class _ConfigurationAddress(ConnectorProjectRequest):
    project_id: ProjectId
    provider_id: ProviderId


class _ConfigurationWrite(_ConfigurationAddress):
    model_config = ConfigDict(frozen=False)
    key: Annotated[str, Field(strict=True, min_length=3, max_length=1024)] | None = Field(repr=False)
    contact: Annotated[str, Field(strict=True, min_length=3, max_length=1024)] | None = Field(repr=False)
    expected_version: Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$")] | None
    preserve_key: Annotated[bool, Field(strict=True)] = False
    preserve_contact: Annotated[bool, Field(strict=True)] = False


def _status(job: WorkflowJobRecord) -> ConnectorJobStatus:
    return ConnectorJobStatus(
        job_id=job.job_id, workflow_run_id=job.workflow_run_id, state=job.state, diagnostic_code=job.diagnostic_code
    )


def connector_problem(request: Request, code: str, *, status: int = 409) -> CoreProblem:
    return CoreProblem(
        problem_detail(
            status=status,
            code="RO-CORE-CONNECTOR-" + code.upper(),
            title="Scholarly source action is unavailable",
            detail="No successful source coverage is implied. Accepted observations remain in the project.",
            trace_id=request.state.trace_id,
            retryable=False,
            remediation=(
                "Check the durable task status, current Intent, privacy and rights. "
                "Preview and confirm the exact request before trying again."
            ),
        )
    )


class _BoundedConnectorRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            body = bytearray()
            private = request.url.path.startswith("/native/connectors/")
            maximum = 8192 if private else 256 * 1024
            async for chunk in request.stream():
                if len(body) + len(chunk) > maximum:
                    raise connector_problem(request, "request-limit", status=413)
                body.extend(chunk)
            request._body = bytes(body)
            try:
                response = await handler(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            finally:
                if private:
                    body[:] = b"\0" * len(body)
                    request._body = b""

        return bounded


def register_connector_routes(
    app: FastAPI,
    service: Callable[[Request], ConnectorWorkerService | None],
    project_problem: Callable[[Request, ProjectLifecycleProblem], CoreProblem],
) -> None:
    router = APIRouter(
        prefix="/projects/connectors",
        route_class=_BoundedConnectorRoute,
        tags=["connectors"],
        responses={403: {"model": ProblemDetail}, 409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
    )

    def run[Result](request: Request, action: Callable[[ConnectorWorkerService], Result]) -> Result:
        runtime = service(request)
        if runtime is None:
            raise connector_problem(request, "unavailable", status=503)
        try:
            return action(runtime)
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from None
        except ProviderProblem as error:
            status = 403 if error.code in {"policy-denied", "permission-denied"} else 409
            raise connector_problem(request, error.code, status=status) from None
        except WorkflowQueueProblem:
            raise connector_problem(request, "job-unavailable") from None
        except SecretConflict:
            raise connector_problem(request, "configuration-conflict") from None
        except CredentialStoreProblem:
            raise connector_problem(request, "configuration-unavailable", status=503) from None
        except ValueError:
            raise connector_problem(request, "invalid-request", status=422) from None

    @router.get("/capabilities", response_model=ConnectorCapabilitiesPage)
    def available(request: Request) -> ConnectorCapabilitiesPage:
        return run(
            request,
            lambda runtime: ConnectorCapabilitiesPage(items=tuple(runtime.settings.describe(name) for name in HOSTS)),
        )

    @router.post("/previews", response_model=ConnectorPreview)
    def preview(request: Request, command: ConnectorPreviewRequest) -> ConnectorPreview:
        return run(request, lambda runtime: runtime.consent.preview(command.root, command.request, command.retention))

    @router.post("/confirmations", response_model=ConnectorJobStatus)
    def confirm(request: Request, command: ConnectorConfirmationRequest) -> ConnectorJobStatus:
        return run(
            request,
            lambda runtime: _status(
                runtime.confirm_and_schedule(command.root, command.preview_id, confirmation=command.confirmation)
            ),
        )

    @router.post("/jobs/status", response_model=ConnectorJobStatus)
    def status(request: Request, command: ConnectorJobRequest) -> ConnectorJobStatus:
        return run(request, lambda runtime: _status(runtime.status(command.root, command.job_id)))

    @router.post("/recent", response_model=ConnectorRecentRuns)
    def recent(request: Request, command: ConnectorProjectRequest) -> ConnectorRecentRuns:
        return run(request, lambda runtime: runtime.recent(command.root))

    @router.post("/inspect", response_model=ConnectorInspection | None)
    def inspect(request: Request, command: ConnectorInspectionRequest) -> ConnectorInspection | None:
        return run(request, lambda runtime: runtime.inspect(command.root, command.preview_id, command.record_offset))

    @router.post("/jobs/cancel", response_model=ConnectorJobStatus)
    def cancel(request: Request, command: ConnectorJobRequest) -> ConnectorJobStatus:
        def cancel(runtime: ConnectorWorkerService) -> ConnectorJobStatus:
            runtime.cancel(command.root, command.job_id)
            return _status(runtime.status(command.root, command.job_id))

        return run(request, cancel)

    app.include_router(router)
    # These fixed native-only routes are not in the renderer bridge allowlist or
    # generated public API. Configuration itself grants no scientific egress.
    private = APIRouter(prefix="/native/connectors", route_class=_BoundedConnectorRoute, include_in_schema=False)

    @private.post("/configuration/status", response_model=ConnectorConnectionStatus)
    def configuration_status(request: Request, command: _ConfigurationAddress) -> ConnectorConnectionStatus:
        return run(
            request, lambda runtime: runtime.connection_status(command.root, command.project_id, command.provider_id)
        )

    @private.post("/configuration/replace", response_model=ConnectorConnectionStatus)
    def configure(request: Request, command: _ConfigurationWrite) -> ConnectorConnectionStatus:
        try:
            return run(
                request,
                lambda runtime: runtime.configure_connection(
                    command.root,
                    command.project_id,
                    command.provider_id,
                    key=command.key,
                    contact=command.contact,
                    expected_version=command.expected_version,
                    preserve_key=command.preserve_key,
                    preserve_contact=command.preserve_contact,
                    context=SecretAccessContext(
                        "CAP-04.S02", SecretPurpose.CONNECTOR_AUTHENTICATION, request.state.trace_id
                    ),
                ),
            )
        finally:
            # Best-effort reference release, not a Python heap-erasure claim.
            command.key = command.contact = None

    app.include_router(private)
