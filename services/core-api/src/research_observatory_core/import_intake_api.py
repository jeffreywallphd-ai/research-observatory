"""Native-only selected-stream intake. The renderer bridge does not allow these routes.

The existing loopback capability authenticates the native supervisor. An ephemeral
Core/project session additionally binds the whole multi-request transfer. No path
to a source file, actor, recovery epoch, or plaintext temporary file is accepted.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, Request
from pydantic import Field, model_validator

from .domain_contracts import new_uuid_v7
from .import_api import BoundedImportRoute, _problem
from .import_preview_service import ImportPreviewService
from .ingestion.import_drafts import Digest, DraftValue, Identity, ImportRights, ProjectIdentity
from .ingestion.reference_imports import ImportSource
from .ingestion.source_chunks import CHUNK_BYTES
from .ports.import_previews import PreviewCreate, PreviewProblem
from .ports.workflow_executor import WorkflowJobState
from .projects import ProjectLifecycleProblem
from .transport import CoreProblem

type SessionId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]


class IntakeProject(DraftValue):
    root: Annotated[str, Field(min_length=1, max_length=4096)]
    project_id: ProjectIdentity


class IntakeContext(DraftValue):
    project_id: ProjectIdentity
    session_id: SessionId


class IntakeSession(IntakeProject):
    session_id: SessionId


class IntakeCreate(IntakeSession):
    source_name: Annotated[str, Field(min_length=1, max_length=255)]
    format_name: Literal["ris", "bibtex", "csl-json", "doi-list", "csv"]
    encoding: Literal["utf-8", "cp1252"]
    rights: ImportRights

    @model_validator(mode="after")
    def basename_and_encoding(self):
        ImportSource(self.source_name, "0" * 64, self.encoding)
        if self.format_name == "csl-json" and self.encoding != "utf-8":
            raise ValueError("csl-requires-utf8")
        return self


class IntakeAddress(IntakeSession):
    preview_id: Identity


class IntakeChunk(IntakeAddress):
    ordinal: Annotated[int, Field(strict=True, ge=1, le=2048)]
    data: Annotated[str, Field(min_length=4, max_length=174764)]

    def decoded(self) -> bytes:
        try:
            value = base64.b64decode(self.data, validate=True)
        except binascii.Error, ValueError:
            raise ValueError("intake-chunk-invalid") from None
        if not 1 <= len(value) <= CHUNK_BYTES or base64.b64encode(value).decode("ascii") != self.data:
            raise ValueError("intake-chunk-invalid")
        return value


class IntakeSeal(IntakeAddress):
    source_sha256: Digest
    byte_length: Annotated[int, Field(strict=True, ge=0, le=268435456)]
    chunk_count: Annotated[int, Field(strict=True, ge=0, le=2048)]


class IntakeStatus(DraftValue):
    preview_id: Identity
    state: Literal[
        "created",
        "source-sealed",
        "parse-started",
        "parse-completed",
        "draft-revised",
        "cancelled",
        "failed",
        "security-interrupted",
    ]
    byte_length: Annotated[int, Field(strict=True, ge=0, le=268435456)]
    chunk_count: Annotated[int, Field(strict=True, ge=0, le=2048)]
    job_id: Identity | None
    job_state: WorkflowJobState | None


def register_intake_routes(
    app: FastAPI,
    service: Callable[[Request], ImportPreviewService | None],
    project_problem: Callable[[Request, ProjectLifecycleProblem], CoreProblem],
) -> None:
    router = APIRouter(prefix="/native/imports", route_class=BoundedImportRoute, include_in_schema=False)

    def run[Result](
        request: Request, command: IntakeProject, action: Callable[[ImportPreviewService], Result]
    ) -> Result:
        runtime = service(request)
        if runtime is None:
            raise _problem(request, 503, "RO-CORE-IMPORT-UNAVAILABLE", "Local imports are unavailable")
        try:
            if isinstance(command, IntakeSession):
                return runtime.in_native_session(
                    command.root, command.project_id, command.session_id, lambda: action(runtime)
                )
            return action(runtime)
        except ProjectLifecycleProblem as error:
            raise project_problem(request, error) from error
        except PreviewProblem as error:
            if str(error) == "preview-rights-denied":
                raise _problem(
                    request, 403, "RO-CORE-IMPORT-RIGHTS-DENIED", "Current rights do not permit this import"
                ) from None
            raise _problem(
                request, 409, "RO-CORE-IMPORT-INTAKE-UNAVAILABLE", "This import intake is no longer available"
            ) from None
        except ValueError:
            raise _problem(request, 422, "RO-CORE-IMPORT-INTAKE-INVALID", "The import input is not valid") from None

    def status(runtime: ImportPreviewService, root: str, preview: str) -> IntakeStatus:
        state, job = runtime.intake_status(root, preview)
        return IntakeStatus(
            preview_id=state.preview_id,
            state=state.state,
            byte_length=state.byte_length,
            chunk_count=state.chunk_count,
            job_id=job.job_id if job else None,
            job_state=job.state if job else None,
        )

    @router.post("/context", response_model=IntakeContext)
    def context(request: Request, command: IntakeProject) -> IntakeContext:
        return run(
            request,
            command,
            lambda runtime: IntakeContext(
                project_id=command.project_id, session_id=runtime.native_context(command.root, command.project_id)
            ),
        )

    @router.post("/create", response_model=IntakeStatus)
    def create(request: Request, command: IntakeCreate) -> IntakeStatus:
        def action(runtime):
            created = runtime.create(
                command.root,
                PreviewCreate(
                    preview_id=new_uuid_v7(),
                    source_name=command.source_name,
                    format_name=command.format_name,
                    encoding=command.encoding,
                    rights=command.rights,
                    actor=runtime.actor(request.state.trace_id),
                ),
            )
            return status(runtime, command.root, created.preview_id)

        return run(request, command, action)

    @router.post("/chunk", response_model=IntakeStatus)
    def chunk(request: Request, command: IntakeChunk) -> IntakeStatus:
        def action(runtime):
            runtime.append_chunk(command.root, command.preview_id, ordinal=command.ordinal, data=command.decoded())
            return status(runtime, command.root, command.preview_id)

        return run(request, command, action)

    @router.post("/seal", response_model=IntakeStatus)
    def seal(request: Request, command: IntakeSeal) -> IntakeStatus:
        def action(runtime):
            runtime.seal(
                command.root,
                command.preview_id,
                source_sha256=command.source_sha256,
                byte_length=command.byte_length,
                chunk_count=command.chunk_count,
                trace_id=request.state.trace_id,
            )
            return status(runtime, command.root, command.preview_id)

        return run(request, command, action)

    @router.post("/schedule", response_model=IntakeStatus)
    def schedule(request: Request, command: IntakeAddress) -> IntakeStatus:
        def action(runtime):
            runtime.schedule(command.root, command.preview_id)
            return status(runtime, command.root, command.preview_id)

        return run(request, command, action)

    @router.post("/status", response_model=IntakeStatus)
    def read_status(request: Request, command: IntakeAddress) -> IntakeStatus:
        return run(request, command, lambda runtime: status(runtime, command.root, command.preview_id))

    @router.post("/cancel", response_model=IntakeStatus)
    def cancel(request: Request, command: IntakeAddress) -> IntakeStatus:
        def action(runtime):
            runtime.cancel(command.root, command.preview_id, trace_id=request.state.trace_id)
            return status(runtime, command.root, command.preview_id)

        return run(request, command, action)

    app.include_router(router)
