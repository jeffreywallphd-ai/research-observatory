"""FastAPI composition root for the local Core process."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request, Response, status

from . import CORE_API_VERSION
from .authentication import LocalAuthenticationMiddleware
from .config import CoreSettings
from .logging import emit_log_record
from .models import (
    CapabilitiesResponse,
    ConfigurationResponse,
    HealthResponse,
    ModuleResponse,
    ModulesResponse,
    ReadinessResponse,
    RuntimeState,
    VersionResponse,
)
from .modules import ModuleRegistry, default_module_registry


@dataclass(slots=True)
class RuntimeContext:
    settings: CoreSettings
    modules: ModuleRegistry
    state: RuntimeState = RuntimeState.STARTING


def create_app(
    *,
    settings: CoreSettings | None = None,
    modules: ModuleRegistry | None = None,
    capability_token: str | None = None,
    expected_authority: str | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings = settings if settings is not None else CoreSettings()
        resolved_modules = modules if modules is not None else default_module_registry()
        context = RuntimeContext(settings=resolved_settings, modules=resolved_modules)
        app.state.runtime = context
        context.state = RuntimeState.READY
        emit_log_record("runtime.started", level=resolved_settings.log_level, fields={"state": context.state.value})
        try:
            yield
        finally:
            context.state = RuntimeState.STOPPING
            emit_log_record(
                "runtime.stopping", level=resolved_settings.log_level, fields={"state": context.state.value}
            )

    app = FastAPI(
        title="Research Observatory Core API",
        summary="Local-first application Core API",
        description="Typed local process boundary. No university or cloud service is activated by this API.",
        version=CORE_API_VERSION,
        openapi_version="3.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.add_middleware(
        LocalAuthenticationMiddleware,
        token=capability_token,
        authority=expected_authority,
    )

    def runtime(request: Request) -> RuntimeContext:
        return request.app.state.runtime

    @app.get("/healthz", response_model=HealthResponse, tags=["runtime"])
    def health(request: Request) -> HealthResponse:
        context = runtime(request)
        return HealthResponse(state=context.state, capabilities=context.modules.capabilities)

    @app.get("/readyz", response_model=ReadinessResponse, tags=["runtime"])
    def readiness(request: Request, response: Response) -> ReadinessResponse:
        context = runtime(request)
        ready = context.state is RuntimeState.READY
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(state=context.state, capabilities=context.modules.capabilities, ready=ready)

    @app.get("/runtime/version", response_model=VersionResponse, tags=["runtime"])
    def version() -> VersionResponse:
        return VersionResponse()

    @app.get("/runtime/configuration", response_model=ConfigurationResponse, tags=["runtime"])
    def configuration(request: Request) -> ConfigurationResponse:
        return ConfigurationResponse.model_validate(runtime(request).settings.public_projection())

    @app.get("/runtime/modules", response_model=ModulesResponse, tags=["runtime"])
    def registered_modules(request: Request) -> ModulesResponse:
        definitions = runtime(request).modules.definitions
        return ModulesResponse(
            modules=tuple(
                ModuleResponse(module_id=definition.module_id, capabilities=definition.capabilities)
                for definition in definitions
            )
        )

    @app.get("/runtime/capabilities", response_model=CapabilitiesResponse, tags=["runtime"])
    def capabilities(request: Request) -> CapabilitiesResponse:
        return CapabilitiesResponse(capabilities=runtime(request).modules.capabilities)

    return app


app = create_app()
