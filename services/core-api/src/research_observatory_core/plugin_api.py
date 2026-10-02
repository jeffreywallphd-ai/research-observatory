"""Native-only authenticated connector package, trust, and grant commands."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute
from pydantic import Field

from .connectors.plugin_grants import PluginEnableConfirmation, PluginGrantProblem
from .connectors.plugin_manifest import PluginDestination
from .connectors.plugin_package_intake import PluginPackageIntakeProblem
from .connectors.plugin_trust import PluginTrustDecision
from .models import ContractModel, ProblemDetail
from .plugin_admin_service import (
    PluginAdminService,
    PluginCandidateReview,
    PluginGrantStatus,
    PluginTransferStatus,
    PluginTrustStatus,
)
from .projects import ProjectLifecycleProblem
from .transport import CoreProblem, problem_detail


class _BoundedPluginRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            maximum = 180_000 if request.url.path.endswith("/packages/chunk") else 8192
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


class PluginContextRequest(ContractModel):
    root: Annotated[str, Field(strict=True, min_length=1, max_length=4096)] = Field(repr=False)
    project_id: str


class PluginContext(ContractModel):
    project_id: str
    session_id: str


class PluginSessionRequest(PluginContextRequest):
    session_id: Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$")]


class PluginIntakeRequest(PluginSessionRequest):
    intake_id: str


class PluginChunkRequest(PluginIntakeRequest):
    ordinal: Annotated[int, Field(strict=True, ge=1, le=512)]
    data: Annotated[str, Field(strict=True, min_length=4, max_length=174_764)] = Field(repr=False)

    def decoded(self) -> bytes:
        try:
            value = base64.b64decode(self.data, validate=True)
        except binascii.Error, ValueError:
            raise PluginGrantProblem("plugin-chunk-invalid") from None
        if not 1 <= len(value) <= 128 * 1024 or base64.b64encode(value).decode("ascii") != self.data:
            raise PluginGrantProblem("plugin-chunk-invalid")
        return value


class PluginSealRequest(PluginIntakeRequest):
    archive_sha256: Annotated[str, Field(strict=True, pattern=r"^sha256:[0-9a-f]{64}$")]
    byte_length: Annotated[int, Field(strict=True, ge=1, le=64 * 1024 * 1024)]
    chunk_count: Annotated[int, Field(strict=True, ge=1, le=512)]


class PluginReviewRequest(PluginSessionRequest):
    package_token: Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]


class PluginTrustAddress(PluginSessionRequest):
    publisher_key_id: Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]


class PluginTrustDecisionRequest(PluginTrustAddress):
    action_id: str
    public_key_hex: Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")] | None
    public_key_sha256: Annotated[str, Field(strict=True, pattern=r"^sha256:[0-9a-f]{64}$")]
    expected_revision: Annotated[int, Field(strict=True, ge=1)] | None
    operation: Literal["trust", "revoke", "rotate"]
    previous_key_sha256: Annotated[str, Field(strict=True, pattern=r"^sha256:[0-9a-f]{64}$")] | None


class PluginGrantAddress(PluginSessionRequest):
    plugin_id: Annotated[str, Field(strict=True, pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$", max_length=121)]


class PluginEnableReview(ContractModel):
    action_id: str
    project_id: str
    plugin_id: str
    plugin_version: str
    publisher_key_id: str
    trusted_key_sha256: str
    trusted_key_revision: int
    package_sha256: str
    manifest_sha256: str
    permissions: tuple[str, ...]
    destinations: tuple[PluginDestination, ...]
    operations: tuple[str, ...]
    data_classes: tuple[str, ...]
    credential_scopes: tuple[str, ...]
    expected_revision: int | None

    def confirmation(self) -> PluginEnableConfirmation:
        return PluginEnableConfirmation(**self.model_dump())


class PluginEnableRequest(PluginReviewRequest):
    confirmation: PluginEnableReview


class PluginRevokeRequest(PluginGrantAddress):
    expected_revision: Annotated[int, Field(strict=True, ge=1)]
    action_id: str


def _problem(request: Request, code: str, *, status: int = 409) -> CoreProblem:
    return CoreProblem(
        problem_detail(
            status=status,
            code="RO-CORE-PLUGIN-" + code.upper(),
            title="Connector plugin action is unavailable",
            detail="No package or project permission was accepted by this response.",
            trace_id=request.state.trace_id,
            retryable=False,
            remediation="Review the selected package, current publisher trust and project permission before retrying.",
        )
    )


def register_plugin_routes(
    app: FastAPI,
    service: Callable[[Request], PluginAdminService | None],
    project_problem: Callable[[Request, ProjectLifecycleProblem], CoreProblem],
) -> None:
    router = APIRouter(
        prefix="/native/connectors/plugins",
        route_class=_BoundedPluginRoute,
        include_in_schema=False,
        responses={403: {"model": ProblemDetail}, 409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
    )

    def run[Result](request: Request, action: Callable[[PluginAdminService], Result]) -> Result:
        runtime = service(request)
        if runtime is None:
            raise _problem(request, "unavailable", status=503)
        try:
            return action(runtime)
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from None
        except (PluginGrantProblem, PluginPackageIntakeProblem) as error:
            code = error.code
            status = 403 if any(part in code for part in ("denied", "untrusted", "revoked", "stale")) else 409
            raise _problem(request, code, status=status) from None
        except ValueError:
            raise _problem(request, "invalid-request", status=422) from None

    @router.post("/packages/context", response_model=PluginContext)
    def context(request: Request, command: PluginContextRequest) -> PluginContext:
        return run(
            request,
            lambda runtime: PluginContext(
                project_id=command.project_id, session_id=runtime.context(command.root, command.project_id)
            ),
        )

    @router.post("/packages/create", response_model=PluginTransferStatus)
    def create(request: Request, command: PluginSessionRequest) -> PluginTransferStatus:
        return run(request, lambda runtime: runtime.create(command.root, command.project_id, command.session_id))

    @router.post("/packages/chunk", response_model=PluginTransferStatus)
    def chunk(request: Request, command: PluginChunkRequest) -> PluginTransferStatus:
        return run(
            request,
            lambda runtime: runtime.chunk(
                command.root,
                command.project_id,
                command.session_id,
                command.intake_id,
                command.ordinal,
                command.decoded(),
            ),
        )

    @router.post("/packages/seal", response_model=PluginTransferStatus)
    def seal(request: Request, command: PluginSealRequest) -> PluginTransferStatus:
        return run(
            request,
            lambda runtime: runtime.seal(
                command.root,
                command.project_id,
                command.session_id,
                command.intake_id,
                archive_sha256=command.archive_sha256,
                byte_length=command.byte_length,
                chunk_count=command.chunk_count,
                trace_id=request.state.trace_id,
            ),
        )

    @router.post("/packages/status", response_model=PluginTransferStatus)
    def status(request: Request, command: PluginIntakeRequest) -> PluginTransferStatus:
        return run(
            request,
            lambda runtime: runtime.status(command.root, command.project_id, command.session_id, command.intake_id),
        )

    @router.post("/packages/cancel", response_model=PluginTransferStatus)
    def cancel(request: Request, command: PluginIntakeRequest) -> PluginTransferStatus:
        return run(
            request,
            lambda runtime: runtime.cancel(command.root, command.project_id, command.session_id, command.intake_id),
        )

    @router.post("/packages/review", response_model=PluginCandidateReview)
    def review(request: Request, command: PluginReviewRequest) -> PluginCandidateReview:
        return run(
            request,
            lambda runtime: runtime.review(
                command.root,
                command.project_id,
                command.session_id,
                command.package_token,
                trace_id=request.state.trace_id,
            ),
        )

    @router.post("/packages/discard", response_model=PluginTransferStatus)
    def discard(request: Request, command: PluginReviewRequest) -> PluginTransferStatus:
        return run(
            request,
            lambda runtime: runtime.discard(
                command.root, command.project_id, command.session_id, command.package_token
            ),
        )

    @router.post("/trust/status", response_model=PluginTrustStatus)
    def trust_status(request: Request, command: PluginTrustAddress) -> PluginTrustStatus:
        return run(
            request,
            lambda runtime: runtime.trust_status(
                command.root,
                command.project_id,
                command.session_id,
                command.publisher_key_id,
                trace_id=request.state.trace_id,
            ),
        )

    @router.post("/trust/decide", response_model=PluginTrustStatus)
    def trust_decide(request: Request, command: PluginTrustDecisionRequest) -> PluginTrustStatus:
        decision = PluginTrustDecision(
            command.action_id,
            command.publisher_key_id,
            command.public_key_sha256,
            command.expected_revision,
            command.operation,
            command.previous_key_sha256,
        )
        public_key = bytes.fromhex(command.public_key_hex) if command.public_key_hex is not None else None
        return run(
            request,
            lambda runtime: runtime.trust_decide(
                command.root,
                command.project_id,
                command.session_id,
                decision,
                public_key,
                actor=runtime.actor(request.state.trace_id),
            ),
        )

    @router.post("/grants/status", response_model=PluginGrantStatus)
    def grant_status(request: Request, command: PluginGrantAddress) -> PluginGrantStatus:
        return run(
            request,
            lambda runtime: runtime.grant_status(
                command.root, command.project_id, command.session_id, command.plugin_id
            ),
        )

    @router.post("/grants/enable", response_model=PluginGrantStatus)
    def grant_enable(request: Request, command: PluginEnableRequest) -> PluginGrantStatus:
        return run(
            request,
            lambda runtime: runtime.enable(
                command.root,
                command.project_id,
                command.session_id,
                command.package_token,
                command.confirmation.confirmation(),
                actor=runtime.actor(request.state.trace_id),
            ),
        )

    @router.post("/grants/revoke", response_model=PluginGrantStatus)
    def grant_revoke(request: Request, command: PluginRevokeRequest) -> PluginGrantStatus:
        return run(
            request,
            lambda runtime: runtime.revoke(
                command.root,
                command.project_id,
                command.session_id,
                command.plugin_id,
                command.expected_revision,
                command.action_id,
                actor=runtime.actor(request.state.trace_id),
            ),
        )

    app.include_router(router)
