"""FastAPI composition root for the local Core process."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TypeVar

from fastapi import FastAPI, Header, Path, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException

from . import CORE_API_VERSION
from .authentication import LocalAuthenticationMiddleware
from .config import CoreSettings
from .logging import emit_log_record
from .models import (
    CacheClearPreview,
    CacheClearPreviewRequest,
    CacheClearRequest,
    CacheClearResult,
    CapabilitiesResponse,
    ConfigurationResponse,
    HealthResponse,
    IntentAcceptRequest,
    IntentDraftProjection,
    IntentDraftRequest,
    IntentImpactPreview,
    IntentImpactRequest,
    IntentPolicyDecision,
    IntentPolicyRequest,
    IntentWorkspaceProjection,
    ModuleResponse,
    ModulesResponse,
    OperationPage,
    OperationProgressEvent,
    OperationStatus,
    PrivacyPolicyProjection,
    PrivacyPolicyUpdateRequest,
    ProblemDetail,
    ProjectCreateRequest,
    ProjectDeleteRequest,
    ProjectPrivacyRequest,
    ProjectProjection,
    ProjectRootRequest,
    ProvenanceLineageNode,
    ProvenanceLineagePage,
    ProvenanceLineageRequest,
    ReadinessResponse,
    RecalculationComparisonProjection,
    RecalculationComparisonRequest,
    RecalculationPreview,
    RecalculationPreviewRequest,
    RecalculationRestoredRevision,
    RecalculationRestoreRequest,
    RecalculationRestoreReviewProjection,
    RecalculationRestoreReviewRequest,
    RecalculationScheduleProjection,
    RecalculationScheduleRequest,
    RuntimeState,
    VersionResponse,
    WorkflowCancelRequest,
    WorkflowHumanDecisionRequest,
    WorkflowProfileCatalogProjection,
    WorkflowProgressCommand,
    WorkflowProgressProjection,
    WorkflowRetryRequest,
    WorkflowTaskCenterPage,
    WorkflowTaskCenterRun,
)
from .modules import ModuleRegistry, default_module_registry
from .operations import (
    IdempotencyConflict,
    OperationPreconditionFailed,
    OperationRegistry,
    OperationReplayGap,
)
from .privacy import PrivacyPolicyProblem, ProjectPrivacyService
from .projects import ProjectLifecycleProblem, ProjectLifecycleService
from .provenance import ProvenanceProblem, ProvenanceService
from .research_intents import IntentProblem, ResearchIntentService
from .selective_recalculation import RecalculationControlProblem, RecalculationControlService
from .task_center import TaskCenterProblem, TaskCenterService
from .transport import CoreProblem, TraceCorrelationMiddleware, problem_detail
from .workflow_progress import WorkflowProgressProblem, WorkflowProgressService

_ACTION_RESULT = TypeVar("_ACTION_RESULT")


@dataclass(slots=True)
class RuntimeContext:
    settings: CoreSettings
    modules: ModuleRegistry
    operations: OperationRegistry
    projects: ProjectLifecycleService
    privacy: ProjectPrivacyService
    intents: ResearchIntentService
    workflow_progress: WorkflowProgressService
    provenance: ProvenanceService
    task_center: TaskCenterService
    recalculation: RecalculationControlService
    state: RuntimeState = RuntimeState.STARTING


def create_app(
    *,
    settings: CoreSettings | None = None,
    modules: ModuleRegistry | None = None,
    operations: OperationRegistry | None = None,
    projects: ProjectLifecycleService | None = None,
    privacy: ProjectPrivacyService | None = None,
    intents: ResearchIntentService | None = None,
    workflow_progress: WorkflowProgressService | None = None,
    provenance: ProvenanceService | None = None,
    task_center: TaskCenterService | None = None,
    recalculation: RecalculationControlService | None = None,
    capability_digest: bytes | None = None,
    expected_authority: str | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings = settings if settings is not None else CoreSettings()
        resolved_modules = modules if modules is not None else default_module_registry()
        resolved_operations = operations if operations is not None else OperationRegistry()
        resolved_projects = projects if projects is not None else ProjectLifecycleService()
        resolved_privacy = privacy if privacy is not None else ProjectPrivacyService.unavailable(resolved_projects)
        resolved_intents = intents if intents is not None else ResearchIntentService.unavailable(resolved_projects)
        resolved_workflow_progress = (
            workflow_progress
            if workflow_progress is not None
            else WorkflowProgressService.unavailable(resolved_projects)
        )
        resolved_provenance = provenance if provenance is not None else ProvenanceService.unavailable(resolved_projects)
        resolved_task_center = (
            task_center if task_center is not None else TaskCenterService.unavailable(resolved_projects)
        )
        resolved_recalculation = (
            recalculation if recalculation is not None else RecalculationControlService.unavailable(resolved_projects)
        )
        context = RuntimeContext(
            settings=resolved_settings,
            modules=resolved_modules,
            operations=resolved_operations,
            projects=resolved_projects,
            privacy=resolved_privacy,
            intents=resolved_intents,
            workflow_progress=resolved_workflow_progress,
            provenance=resolved_provenance,
            task_center=resolved_task_center,
            recalculation=resolved_recalculation,
        )
        app.state.runtime = context
        context.state = RuntimeState.READY
        emit_log_record("runtime.started", level=resolved_settings.log_level, fields={"state": context.state.value})
        try:
            yield
        finally:
            context.state = RuntimeState.STOPPING
            context.projects.shutdown()
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
        digest=capability_digest,
        authority=expected_authority,
    )
    app.add_middleware(TraceCorrelationMiddleware)

    @app.exception_handler(CoreProblem)
    async def core_problem(_request: Request, error: CoreProblem) -> JSONResponse:
        return JSONResponse(
            status_code=error.problem.status,
            content=error.problem.model_dump(mode="json", by_alias=True),
            media_type="application/problem+json",
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_problem(request: Request, _error: RequestValidationError) -> JSONResponse:
        problem = problem_detail(
            status=422,
            code="RO-CORE-VALIDATION-FAILED",
            title="Request validation failed",
            detail="The request did not match the versioned Core API contract.",
            trace_id=request.state.trace_id,
            retryable=False,
            remediation="Correct the request using the generated client and retry.",
        )
        return JSONResponse(
            status_code=problem.status,
            content=problem.model_dump(mode="json", by_alias=True),
            media_type="application/problem+json",
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(HTTPException)
    async def http_problem(request: Request, error: HTTPException) -> JSONResponse:
        known = error.status_code == 404
        problem = problem_detail(
            status=error.status_code,
            code="RO-CORE-ROUTE-NOT-FOUND" if known else "RO-CORE-METHOD-DENIED",
            title="API route was not found" if known else "API method is not allowed",
            detail=(
                "The requested route is not part of this Core API version."
                if known
                else "The request method is not supported for this Core API route."
            ),
            trace_id=request.state.trace_id,
            retryable=False,
            remediation="Use the generated client for the installed Core API version.",
        )
        return JSONResponse(
            status_code=problem.status,
            content=problem.model_dump(mode="json", by_alias=True),
            media_type="application/problem+json",
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(Exception)
    async def unexpected_problem(request: Request, _error: Exception) -> JSONResponse:
        problem = problem_detail(
            status=500,
            code="RO-CORE-INTERNAL-FAILED",
            title="Core request failed",
            detail="The local request failed without exposing private diagnostic content.",
            trace_id=request.state.trace_id,
            retryable=True,
            remediation="Retry once, then use the diagnostics workspace if the failure continues.",
        )
        return JSONResponse(
            status_code=problem.status,
            content=problem.model_dump(mode="json", by_alias=True),
            media_type="application/problem+json",
            headers={"Cache-Control": "no-store"},
        )

    def runtime(request: Request) -> RuntimeContext:
        return request.app.state.runtime

    def missing_operation(request: Request) -> CoreProblem:
        return CoreProblem(
            problem_detail(
                status=404,
                code="RO-CORE-OPERATION-NOT-FOUND",
                title="Operation was not found",
                detail="The requested operation is not available in this local runtime session.",
                trace_id=request.state.trace_id,
                retryable=False,
                remediation="Refresh operation status and select an available operation.",
            )
        )

    def project_problem(request: Request, error: ProjectLifecycleProblem) -> CoreProblem:
        return CoreProblem(
            problem_detail(
                status=error.status,
                code=error.code,
                title=error.title,
                detail=error.detail,
                trace_id=request.state.trace_id,
                retryable=error.retryable,
                remediation=error.remediation,
            )
        )

    def run_project_action(request: Request, action: Callable[[], ProjectProjection]) -> ProjectProjection:
        try:
            return action()
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from error

    def privacy_problem(request: Request, error: PrivacyPolicyProblem) -> CoreProblem:
        return CoreProblem(
            problem_detail(
                status=error.status,
                code=error.code,
                title=error.title,
                detail=error.detail,
                trace_id=request.state.trace_id,
                retryable=error.retryable,
                remediation=error.remediation,
            )
        )

    def run_privacy_action(request: Request, action: Callable[[], _ACTION_RESULT]) -> _ACTION_RESULT:
        try:
            return action()
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from error
        except PrivacyPolicyProblem as error:
            raise privacy_problem(request, error) from error

    def intent_problem(request: Request, error: IntentProblem) -> CoreProblem:
        return CoreProblem(
            problem_detail(
                status=error.status,
                code=error.code,
                title=error.title,
                detail=error.detail,
                trace_id=request.state.trace_id,
                retryable=error.retryable,
                remediation=error.remediation,
            )
        )

    def run_intent_action(request: Request, action: Callable[[], _ACTION_RESULT]) -> _ACTION_RESULT:
        try:
            return action()
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from error
        except IntentProblem as error:
            raise intent_problem(request, error) from error

    def run_workflow_progress_action(request: Request, action: Callable[[], _ACTION_RESULT]) -> _ACTION_RESULT:
        try:
            return action()
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from error
        except WorkflowProgressProblem as error:
            raise CoreProblem(
                problem_detail(
                    status=error.status,
                    code=error.code,
                    title=error.title,
                    detail=error.detail,
                    trace_id=request.state.trace_id,
                    retryable=error.retryable,
                    remediation=error.remediation,
                )
            ) from error

    def run_provenance_action(request: Request, action: Callable[[], _ACTION_RESULT]) -> _ACTION_RESULT:
        try:
            return action()
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from error
        except ProvenanceProblem as error:
            raise CoreProblem(
                problem_detail(
                    status=409,
                    code=error.code,
                    title="Provenance query is unavailable",
                    detail="The requested project lineage could not be inspected safely.",
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Open a compatible local project and retry with a bounded lineage request.",
                )
            ) from error

    def run_task_center_action(request: Request, action: Callable[[], _ACTION_RESULT]) -> _ACTION_RESULT:
        try:
            return action()
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from error
        except TaskCenterProblem as error:
            raise CoreProblem(
                problem_detail(
                    status=error.status,
                    code=error.code,
                    title=error.title,
                    detail=error.detail,
                    trace_id=request.state.trace_id,
                    retryable=error.retryable,
                    remediation=error.remediation,
                )
            ) from error

    def run_recalculation_action(request: Request, action: Callable[[], _ACTION_RESULT]) -> _ACTION_RESULT:
        try:
            return action()
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from error
        except RecalculationControlProblem as error:
            raise CoreProblem(
                problem_detail(
                    status=error.status,
                    code=error.code,
                    title=error.title,
                    detail=error.detail,
                    trace_id=request.state.trace_id,
                    retryable=error.retryable,
                    remediation=error.remediation,
                )
            ) from error

    def workflow_precondition(request: Request, if_match: str | None) -> tuple[str, int, int]:
        match = re.fullmatch(
            r'"workflow-([0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})-([1-9][0-9]*)-([1-9][0-9]*)"',
            if_match or "",
        )
        if match is None:
            raise CoreProblem(
                problem_detail(
                    status=428,
                    code="RO-CORE-WORKFLOW-PRECONDITION-REQUIRED",
                    title="Workflow precondition is required",
                    detail=(
                        "This action requires the exact workflow run, history revision "
                        "and snapshot revision last reviewed."
                    ),
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Refresh Task Center and retry the action from the current item.",
                )
            )
        return match.group(1), int(match.group(2)), int(match.group(3))

    def set_workflow_etag(response: Response, projection: WorkflowTaskCenterRun) -> None:
        response.headers["ETag"] = (
            f'"workflow-{projection.workflow_run_id}-{projection.revision}-{projection.snapshot_revision}"'
        )
        response.headers["Cache-Control"] = "no-store"

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

    @app.post(
        "/projects/provenance/lineage",
        response_model=ProvenanceLineagePage,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
        tags=["provenance"],
    )
    def provenance_lineage(request: Request, command: ProvenanceLineageRequest) -> ProvenanceLineagePage:
        page = run_provenance_action(
            request,
            lambda: runtime(request).provenance.lineage(
                root=command.root,
                revision_id=command.revision_id,
                direction=command.direction,
                cursor=command.cursor,
                page_size=command.page_size,
                max_depth=command.max_depth,
            ),
        )
        return ProvenanceLineagePage(
            revision_id=page.revision_id,
            direction=page.direction,
            items=tuple(
                ProvenanceLineageNode(
                    fact_id=item.fact_id,
                    relation_type=item.relation_type,
                    entity_direction=item.entity_direction,
                    revision_id=item.revision_id,
                    entity_id=item.entity_id,
                    entity_kind=item.entity_kind,
                    related_revision_id=item.related_revision_id,
                    knowledge_status=item.knowledge_status,
                    rights_status=item.rights_status,
                    depth=item.depth,
                    event_id=item.event_id,
                    event_type=item.event_type,
                    activity_id=item.activity_id,
                    activity_type=item.activity_type,
                    activity_status=item.activity_status,
                    configuration_id=item.configuration_id,
                    configuration_version=item.configuration_version,
                    configuration_hash=item.configuration_hash,
                    agent_id=item.agent_id,
                    agent_type=item.agent_type,
                    agent_role=item.agent_role,
                    occurred_at=item.occurred_at,
                )
                for item in page.items
            ),
            missing_revision_ids=page.missing_revision_ids,
            next_cursor=page.next_cursor,
            truncated=page.truncated,
            truncation_reason=page.truncation_reason,
            integrity_state=page.integrity_state,
            legacy_event_count=page.legacy_event_count,
            export_allowed=page.export_allowed,
            export_denial_reason=page.export_denial_reason,
        )

    @app.post(
        "/projects",
        response_model=ProjectProjection,
        responses={
            409: {"model": ProblemDetail},
            422: {"model": ProblemDetail},
            500: {"model": ProblemDetail},
            503: {"model": ProblemDetail},
        },
        tags=["projects"],
    )
    def create_project(request: Request, command: ProjectCreateRequest) -> ProjectProjection:
        return run_project_action(
            request,
            lambda: runtime(request).projects.create(
                parent_directory=command.parent_directory,
                directory_name=command.directory_name,
                display_name=command.display_name,
                template_id=command.primary_use_case,
                trace_id=request.state.trace_id,
                initialize_authority=lambda path, project_id: runtime(request).intents.initialize_created_project(
                    path,
                    project_id,
                    primary_use_case=command.primary_use_case,
                    research_objective=command.research_objective,
                    trace_id=request.state.trace_id,
                ),
            ),
        )

    @app.get(
        "/workflow-profiles/catalog",
        response_model=WorkflowProfileCatalogProjection,
        tags=["projects", "intent"],
    )
    def workflow_profile_catalog(request: Request) -> WorkflowProfileCatalogProjection:
        return runtime(request).intents.workflow_profile_catalog()

    @app.post(
        "/projects/open",
        response_model=ProjectProjection,
        responses={404: {"model": ProblemDetail}, 409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
        tags=["projects"],
    )
    def open_project(request: Request, command: ProjectRootRequest) -> ProjectProjection:
        return run_project_action(
            request,
            lambda: runtime(request).projects.open(root=command.root, trace_id=request.state.trace_id),
        )

    @app.post(
        "/projects/close",
        response_model=ProjectProjection,
        responses={404: {"model": ProblemDetail}, 409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
        tags=["projects"],
    )
    def close_project(request: Request, command: ProjectRootRequest) -> ProjectProjection:
        return run_project_action(
            request,
            lambda: runtime(request).projects.close(root=command.root, trace_id=request.state.trace_id),
        )

    @app.post(
        "/projects/archive",
        response_model=ProjectProjection,
        responses={404: {"model": ProblemDetail}, 409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
        tags=["projects"],
    )
    def archive_project(request: Request, command: ProjectRootRequest) -> ProjectProjection:
        return run_project_action(
            request,
            lambda: runtime(request).projects.archive(root=command.root, trace_id=request.state.trace_id),
        )

    @app.post(
        "/projects/restore",
        response_model=ProjectProjection,
        responses={404: {"model": ProblemDetail}, 409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
        tags=["projects"],
    )
    def restore_project(request: Request, command: ProjectRootRequest) -> ProjectProjection:
        return run_project_action(
            request,
            lambda: runtime(request).projects.restore(root=command.root, trace_id=request.state.trace_id),
        )

    @app.post(
        "/projects/delete",
        response_model=ProjectProjection,
        responses={404: {"model": ProblemDetail}, 409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
        tags=["projects"],
    )
    def delete_project(request: Request, command: ProjectDeleteRequest) -> ProjectProjection:
        return run_project_action(
            request,
            lambda: runtime(request).projects.delete(
                root=command.root,
                confirmation=command.confirmation,
                trace_id=request.state.trace_id,
            ),
        )

    @app.post(
        "/projects/privacy",
        response_model=PrivacyPolicyProjection,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["privacy"],
    )
    def project_privacy(request: Request, command: ProjectPrivacyRequest) -> PrivacyPolicyProjection:
        return run_privacy_action(request, lambda: runtime(request).privacy.get(command.root))

    @app.post(
        "/projects/privacy/update",
        response_model=PrivacyPolicyProjection,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["privacy"],
    )
    def update_project_privacy(request: Request, command: PrivacyPolicyUpdateRequest) -> PrivacyPolicyProjection:
        return run_privacy_action(
            request,
            lambda: runtime(request).privacy.update(command, trace_id=request.state.trace_id),
        )

    @app.post(
        "/projects/privacy/cache/preview",
        response_model=CacheClearPreview,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["privacy"],
    )
    def preview_project_cache(request: Request, command: CacheClearPreviewRequest) -> CacheClearPreview:
        return run_privacy_action(
            request,
            lambda: runtime(request).privacy.preview_cache(command.root),
        )

    @app.post(
        "/projects/privacy/cache/clear",
        response_model=CacheClearResult,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["privacy"],
    )
    def clear_project_cache(request: Request, command: CacheClearRequest) -> CacheClearResult:
        return run_privacy_action(
            request,
            lambda: runtime(request).privacy.clear_cache(command, trace_id=request.state.trace_id),
        )

    @app.post(
        "/projects/intent",
        response_model=IntentWorkspaceProjection,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["intent"],
    )
    def project_intent(request: Request, command: ProjectRootRequest) -> IntentWorkspaceProjection:
        return run_intent_action(request, lambda: runtime(request).intents.workspace(command.root))

    @app.post(
        "/projects/intent/preview",
        response_model=IntentImpactPreview,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["intent"],
    )
    def preview_intent(request: Request, command: IntentImpactRequest) -> IntentImpactPreview:
        return run_intent_action(request, lambda: runtime(request).intents.preview(command))

    @app.post(
        "/projects/intent/drafts",
        response_model=IntentDraftProjection,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["intent"],
    )
    def save_intent_draft(
        request: Request,
        command: IntentDraftRequest,
        idempotency_key: str = Header(
            alias="Idempotency-Key",
            pattern=r"^[0-9a-f]{32}$",
        ),
    ) -> IntentDraftProjection:
        return run_intent_action(
            request,
            lambda: runtime(request).intents.save_draft(
                command,
                trace_id=request.state.trace_id,
                idempotency_key=idempotency_key,
            ),
        )

    @app.post(
        "/projects/intent/acceptances",
        response_model=IntentDraftProjection,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["intent"],
    )
    def accept_intent(
        request: Request,
        command: IntentAcceptRequest,
        idempotency_key: str = Header(alias="Idempotency-Key", pattern=r"^[0-9a-f]{32}$"),
    ) -> IntentDraftProjection:
        return run_intent_action(
            request,
            lambda: runtime(request).intents.accept(
                command,
                trace_id=request.state.trace_id,
                idempotency_key=idempotency_key,
            ),
        )

    @app.post(
        "/projects/intent/policy/evaluations",
        response_model=IntentPolicyDecision,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["intent"],
    )
    def evaluate_intent_policy(request: Request, command: IntentPolicyRequest) -> IntentPolicyDecision:
        return run_intent_action(
            request,
            lambda: runtime(request).intents.evaluate_policy(command, trace_id=request.state.trace_id),
        )

    @app.post(
        "/projects/workflow-progress",
        response_model=WorkflowProgressProjection,
        responses={409: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["intent"],
    )
    def project_workflow_progress(request: Request, command: ProjectRootRequest) -> WorkflowProgressProjection:
        return run_workflow_progress_action(request, lambda: runtime(request).workflow_progress.workspace(command.root))

    @app.post(
        "/projects/workflow-progress/commands",
        response_model=WorkflowProgressProjection,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 500: {"model": ProblemDetail}},
        tags=["intent"],
    )
    def command_workflow_progress(
        request: Request,
        command: WorkflowProgressCommand,
        idempotency_key: str = Header(alias="Idempotency-Key", pattern=r"^[0-9a-f]{32}$"),
    ) -> WorkflowProgressProjection:
        return run_workflow_progress_action(
            request,
            lambda: runtime(request).workflow_progress.command(
                command,
                trace_id=request.state.trace_id,
                idempotency_key=idempotency_key,
            ),
        )

    @app.post(
        "/projects/recalculation/preview",
        response_model=RecalculationPreview,
        responses={409: {"model": ProblemDetail}, 412: {"model": ProblemDetail}, 503: {"model": ProblemDetail}},
        tags=["recalculation"],
    )
    def preview_recalculation(request: Request, command: RecalculationPreviewRequest) -> RecalculationPreview:
        return run_recalculation_action(request, lambda: runtime(request).recalculation.preview(command))

    @app.post(
        "/projects/recalculation/schedules",
        response_model=RecalculationScheduleProjection,
        responses={409: {"model": ProblemDetail}, 412: {"model": ProblemDetail}, 503: {"model": ProblemDetail}},
        tags=["recalculation"],
    )
    def schedule_recalculation(
        request: Request,
        command: RecalculationScheduleRequest,
        idempotency_key: str = Header(alias="Idempotency-Key", pattern=r"^[0-9a-f]{32}$"),
    ) -> RecalculationScheduleProjection:
        return run_recalculation_action(
            request,
            lambda: runtime(request).recalculation.schedule(command, idempotency_key=idempotency_key),
        )

    @app.post(
        "/projects/recalculation/comparisons",
        response_model=RecalculationComparisonProjection,
        responses={409: {"model": ProblemDetail}, 412: {"model": ProblemDetail}, 503: {"model": ProblemDetail}},
        tags=["recalculation"],
    )
    def compare_recalculation(
        request: Request,
        command: RecalculationComparisonRequest,
    ) -> RecalculationComparisonProjection:
        return run_recalculation_action(request, lambda: runtime(request).recalculation.compare(command))

    @app.post(
        "/projects/recalculation/restore-reviews",
        response_model=RecalculationRestoreReviewProjection,
        responses={409: {"model": ProblemDetail}, 412: {"model": ProblemDetail}, 503: {"model": ProblemDetail}},
        tags=["recalculation"],
    )
    def request_recalculation_restore_review(
        request: Request,
        command: RecalculationRestoreReviewRequest,
        idempotency_key: str = Header(alias="Idempotency-Key", pattern=r"^[0-9a-f]{32}$"),
    ) -> RecalculationRestoreReviewProjection:
        return run_recalculation_action(
            request,
            lambda: runtime(request).recalculation.request_restore_review(
                command,
                idempotency_key=idempotency_key,
            ),
        )

    @app.post(
        "/projects/recalculation/restorations",
        response_model=RecalculationRestoredRevision,
        responses={409: {"model": ProblemDetail}, 412: {"model": ProblemDetail}, 503: {"model": ProblemDetail}},
        tags=["recalculation"],
    )
    def restore_recalculation_revision(
        request: Request,
        command: RecalculationRestoreRequest,
    ) -> RecalculationRestoredRevision:
        return run_recalculation_action(
            request,
            lambda: runtime(request).recalculation.restore(command, trace_id=request.state.trace_id),
        )

    @app.get(
        "/projects/workflows/task-center",
        response_model=WorkflowTaskCenterPage,
        responses={409: {"model": ProblemDetail}, 422: {"model": ProblemDetail}, 503: {"model": ProblemDetail}},
        tags=["workflows"],
    )
    def workflow_task_center(
        request: Request,
        response: Response,
        root: str = Query(min_length=1, max_length=1024),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> WorkflowTaskCenterPage:
        response.headers["Cache-Control"] = "no-store"
        return run_task_center_action(request, lambda: runtime(request).task_center.list(root=root, limit=limit))

    @app.post(
        "/projects/workflows/jobs/{job_id}/cancel",
        response_model=WorkflowTaskCenterRun,
        responses={
            404: {"model": ProblemDetail},
            409: {"model": ProblemDetail},
            412: {"model": ProblemDetail},
            422: {"model": ProblemDetail},
            428: {"model": ProblemDetail},
            503: {"model": ProblemDetail},
        },
        tags=["workflows"],
    )
    def cancel_workflow_job(
        request: Request,
        response: Response,
        command: WorkflowCancelRequest,
        job_id: str = Path(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"),
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> WorkflowTaskCenterRun:
        run_id, revision, snapshot_revision = workflow_precondition(request, if_match)
        projection = run_task_center_action(
            request,
            lambda: runtime(request).task_center.cancel(
                root=command.root,
                job_id=job_id,
                expected_run_id=run_id,
                expected_snapshot_revision=snapshot_revision,
                expected_revision=revision,
                reason_code=command.reason_code,
            ),
        )
        set_workflow_etag(response, projection)
        return projection

    @app.post(
        "/projects/workflows/jobs/{job_id}/retry",
        response_model=WorkflowTaskCenterRun,
        responses={
            404: {"model": ProblemDetail},
            409: {"model": ProblemDetail},
            412: {"model": ProblemDetail},
            422: {"model": ProblemDetail},
            428: {"model": ProblemDetail},
            503: {"model": ProblemDetail},
        },
        tags=["workflows"],
    )
    def retry_workflow_job(
        request: Request,
        response: Response,
        command: WorkflowRetryRequest,
        job_id: str = Path(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"),
        if_match: str | None = Header(default=None, alias="If-Match"),
        idempotency_key: str = Header(alias="Idempotency-Key", pattern=r"^[0-9a-f]{32}$"),
    ) -> WorkflowTaskCenterRun:
        run_id, revision, snapshot_revision = workflow_precondition(request, if_match)
        projection = run_task_center_action(
            request,
            lambda: runtime(request).task_center.retry(
                root=command.root,
                job_id=job_id,
                expected_run_id=run_id,
                expected_snapshot_revision=snapshot_revision,
                expected_revision=revision,
                idempotency_key=idempotency_key,
            ),
        )
        set_workflow_etag(response, projection)
        return projection

    @app.post(
        "/projects/workflows/human-tasks/{human_task_id}/decide",
        response_model=WorkflowTaskCenterRun,
        responses={
            404: {"model": ProblemDetail},
            409: {"model": ProblemDetail},
            412: {"model": ProblemDetail},
            422: {"model": ProblemDetail},
            428: {"model": ProblemDetail},
            503: {"model": ProblemDetail},
        },
        tags=["workflows"],
    )
    def decide_workflow_human_task(
        request: Request,
        response: Response,
        command: WorkflowHumanDecisionRequest,
        human_task_id: str = Path(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"),
        if_match: str | None = Header(default=None, alias="If-Match"),
        idempotency_key: str = Header(alias="Idempotency-Key", pattern=r"^[0-9a-f]{32}$"),
    ) -> WorkflowTaskCenterRun:
        run_id, revision, snapshot_revision = workflow_precondition(request, if_match)
        projection = run_task_center_action(
            request,
            lambda: runtime(request).task_center.decide(
                root=command.root,
                human_task_id=human_task_id,
                expected_run_id=run_id,
                expected_snapshot_revision=snapshot_revision,
                expected_history_sequence=revision,
                disposition=command.disposition,
                idempotency_key=idempotency_key,
            ),
        )
        set_workflow_etag(response, projection)
        return projection

    @app.get(
        "/runtime/operations",
        response_model=OperationPage,
        responses={422: {"model": ProblemDetail}},
        tags=["operations"],
    )
    def list_operations(
        request: Request,
        after: str | None = Query(default=None, pattern=r"^op-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> OperationPage:
        try:
            items, next_cursor = runtime(request).operations.page(after=after, limit=limit)
        except ValueError as error:
            raise CoreProblem(
                problem_detail(
                    status=422,
                    code="RO-CORE-CURSOR-INVALID",
                    title="Operation cursor is invalid",
                    detail="The cursor does not identify an operation in the current local runtime session.",
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Restart pagination without a cursor.",
                )
            ) from error
        return OperationPage(items=items, next_cursor=next_cursor)

    @app.get(
        "/runtime/operations/{operation_id}",
        response_model=OperationStatus,
        responses={404: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
        tags=["operations"],
    )
    def operation_status(
        request: Request,
        response: Response,
        operation_id: str = Path(pattern=r"^op-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"),
    ) -> OperationStatus:
        projection = runtime(request).operations.get(operation_id)
        if projection is None:
            raise missing_operation(request)
        response.headers["ETag"] = runtime(request).operations.etag(operation_id) or ""
        response.headers["Cache-Control"] = "no-store"
        return projection

    @app.post(
        "/runtime/operations/{operation_id}/cancel",
        response_model=OperationStatus,
        responses={
            404: {"model": ProblemDetail},
            409: {"model": ProblemDetail},
            412: {"model": ProblemDetail},
            422: {"model": ProblemDetail},
            428: {"model": ProblemDetail},
        },
        tags=["operations"],
    )
    def cancel_operation(
        request: Request,
        response: Response,
        operation_id: str = Path(pattern=r"^op-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"),
        if_match: str | None = Header(default=None, alias="If-Match"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> OperationStatus:
        if (
            if_match is None
            or idempotency_key is None
            or len(idempotency_key) != 32
            or any(value not in "0123456789abcdef" for value in idempotency_key)
        ):
            raise CoreProblem(
                problem_detail(
                    status=428,
                    code="RO-CORE-PRECONDITION-REQUIRED",
                    title="Operation precondition is required",
                    detail="Cancellation requires the current ETag and one canonical idempotency key.",
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Refresh operation status, then retry cancellation through the generated client.",
                )
            )
        try:
            projection = runtime(request).operations.cancel(
                operation_id,
                if_match=if_match,
                idempotency_key=idempotency_key,
            )
        except OperationPreconditionFailed as error:
            raise CoreProblem(
                problem_detail(
                    status=412,
                    code="RO-CORE-REVISION-CONFLICT",
                    title="Operation revision changed",
                    detail="The operation changed after the desktop last read its status.",
                    trace_id=request.state.trace_id,
                    retryable=True,
                    remediation="Refresh operation status before retrying cancellation.",
                )
            ) from error
        except IdempotencyConflict as error:
            raise CoreProblem(
                problem_detail(
                    status=409,
                    code="RO-CORE-IDEMPOTENCY-CONFLICT",
                    title="Idempotency identity conflicts",
                    detail="The command identity was already used for a different operation.",
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Create a new command identity for the intended operation.",
                )
            ) from error
        except RuntimeError as error:
            raise CoreProblem(
                problem_detail(
                    status=409,
                    code="RO-CORE-OPERATION-TERMINAL",
                    title="Operation is already terminal",
                    detail="A completed or failed operation cannot be cancelled.",
                    trace_id=request.state.trace_id,
                    retryable=False,
                    remediation="Refresh operation status before choosing the next action.",
                )
            ) from error
        if projection is None:
            raise missing_operation(request)
        response.headers["ETag"] = runtime(request).operations.etag(operation_id) or ""
        response.headers["Cache-Control"] = "no-store"
        return projection

    @app.get(
        "/runtime/operations/{operation_id}/events",
        responses={
            200: {"model": OperationProgressEvent, "content": {"text/event-stream": {}}},
            404: {"model": ProblemDetail},
            409: {"model": ProblemDetail},
        },
        tags=["operations"],
    )
    def operation_events(
        request: Request,
        operation_id: str = Path(pattern=r"^op-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"),
        after_sequence: int = Query(default=0, alias="afterSequence", ge=0),
    ) -> StreamingResponse:
        try:
            events = runtime(request).operations.events(operation_id, after_sequence=after_sequence)
        except OperationReplayGap as error:
            raise CoreProblem(
                problem_detail(
                    status=409,
                    code="RO-CORE-EVENT-REPLAY-GAP",
                    title="Operation event replay gap",
                    detail="The requested event position is older than retained local progress history.",
                    trace_id=request.state.trace_id,
                    retryable=True,
                    remediation="Refresh authoritative operation status, then resume from its current sequence.",
                )
            ) from error
        if events is None:
            raise missing_operation(request)

        def stream() -> tuple[str, ...]:
            return tuple(
                f"id: {event.sequence}\nevent: operation-progress\ndata: {event.model_dump_json(by_alias=True)}\n\n"
                for event in events
            )

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
