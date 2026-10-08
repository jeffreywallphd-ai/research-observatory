"""Core API process entry point."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import BinaryIO

import uvicorn
from fastapi import FastAPI
from pydantic import ValidationError

from . import CORE_API_SCHEMA_VERSION, CORE_API_VERSION, CORE_SERVICE_ID
from .acquisition.service import AcquisitionPreview, OpenAccessAcquisitionService
from .app import create_app
from .authentication import WORKFLOW_STARTUP_RECORD_BYTES, NativeWorkflowContext, parse_startup_record
from .config import CoreSettings
from .connector_repository import ConnectorRepository
from .connector_service import ConnectorConsentService, ConnectorProjectAdapters
from .connector_worker import ConnectorWorkerAdapters, ConnectorWorkerService
from .connectors.plugin_credentials import PluginCredentialSettings
from .connectors.plugin_package_store import PluginPackageStore
from .connectors.plugin_trust import PluginPublisherTrustStore
from .connectors.settings import ConnectorSettings
from .corpus_query import ConnectorWorkerQueryResolver
from .corpus_report_repository import SqliteCorpusReportRepository
from .corpus_repository import SqliteCorpusRepository
from .corpus_service import CorpusService
from .document_attachment_api import (
    DocumentAccessNeedCommand,
    DocumentCandidateRecovery,
    DocumentCommit,
    DocumentRecoveryQuery,
    DocumentStageCommand,
    DocumentStatusQuery,
)
from .document_attachment_repository import AcquisitionRepository, LocalDocumentAttachmentService
from .document_parse_worker import document_worker_policy
from .document_revision_repository import LocalDocumentRevisionRepository
from .document_revision_service import DocumentRevisionService
from .document_viewer_service import DocumentViewerService
from .import_preview_repository import sqlite_import_preview_repository
from .import_preview_service import ImportPreviewService, ImportProjectAdapters
from .logging import emit_log_record
from .migrations.runner import migration_framework_projection
from .model_catalog import ModelCatalogService
from .model_gateway_service import ProjectModelGatewayService
from .model_registry_repository import SqliteModelRoutingRepository, sqlite_model_catalog_repository
from .modules import default_module_registry
from .object_store import create_local_object_store, upgrade_local_object_envelopes
from .plugin_admin_service import PluginAdminService
from .plugin_consent import PluginConsentService
from .plugin_grant_repository import SqlitePluginGrantRepository
from .plugin_job_repository import PluginJobRepository
from .plugin_package_repository import SqlitePluginPackageRepository
from .plugin_runtime import InstalledPluginRuntime
from .plugin_worker import PluginWorkerAdapters, PluginWorkerService
from .ports.acquisition import AcquisitionLocation, AcquisitionProblem, AcquisitionSelection
from .ports.corpus import CorpusActor
from .ports.credential_store import CredentialStoreProblem
from .ports.database_keys import DatabaseKeyProvider
from .ports.document_attachments import (
    AttachmentCandidate,
    AttachmentProblem,
    DocumentAttachment,
    DocumentAttachmentStatus,
)
from .ports.import_previews import PreviewProblem
from .ports.object_store import ObjectStore
from .ports.object_store_keys import ObjectMasterKeyProvider
from .privacy import ProjectPrivacyService
from .projects import ProjectLifecycleProblem, ProjectLifecycleService, _ProjectActionScope
from .provenance import ProvenanceService
from .repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_dependency_impact_repository,
    sqlite_intent_authority_snapshot,
    sqlite_intent_revision_repository,
    sqlite_material_dependency_repository,
    sqlite_privacy_policy_repository,
    sqlite_provenance_ledger_repository,
    sqlite_selective_recalculation_repository,
    sqlite_workflow_admission_binding,
    sqlite_workflow_progress_repository,
    sqlite_workflow_queue_repository,
)
from .research_intents import ResearchIntentService
from .rights_repository import SqliteRightsRepository
from .selective_recalculation import RecalculationControlService
from .storage import (
    DEVELOPMENT_PLAINTEXT_PROFILE,
    configure_protected_database_provider,
    database_protection_profile,
)
from .task_center import TaskCenterService
from .windows_credentials import (
    WindowsCredentialStore,
    create_windows_database_key_provider,
    create_windows_local_actor_identity,
    create_windows_object_key_provider,
    default_windows_profile_vault_path,
)
from .workflow_executor import LocalAdmissionController, LocalWorkerAdmission, WorkerResources
from .workflow_progress import WorkflowProgressService

EXIT_CONFIGURATION_ERROR = 2
SUPERVISION_PROTOCOL_VERSION = "1.0"
STARTING_DIAGNOSTIC_CODE = "RO-CORE-STARTING"
_DEFAULT_OBJECT_KEY_PROVIDER = object()
_DEFAULT_DATABASE_KEY_PROVIDER = object()
_DEFAULT_LOCAL_ACTOR_ID = object()
_DEFAULT_CONNECTOR_SETTINGS = object()


class DocumentAttachmentRuntime:
    """Compose a current Core actor/session with the encrypted attachment port."""

    def __init__(
        self,
        imports: ImportPreviewService,
        corpus: CorpusService,
        object_store_factory: Callable[[Path, str], ObjectStore],
        *,
        admission_factory: Callable[[Path, str], LocalWorkerAdmission] | None = None,
    ) -> None:
        self._imports = imports
        self._corpus = corpus
        self._object_store_factory = object_store_factory
        self._admission_factory = admission_factory
        self._acquisitions: dict[tuple[str, str, str], OpenAccessAcquisitionService] = {}
        self._acquisition_slots: dict[str, threading.BoundedSemaphore] = {}

    @contextmanager
    def _document_reservation(self, root: str, project_id: str) -> Iterator[None]:
        if self._admission_factory is None:
            # Direct development fixtures may omit local OS composition.
            # Production composition always supplies the shared controller.
            yield
            return
        binding = self._admission_factory(Path(root).resolve(strict=True), project_id)
        binding.validate(binding.repository)
        token = binding.controller.reserve(binding, "document", local_limit=1)
        if token is None:
            raise AttachmentProblem("attachment-resource-unavailable")
        try:
            yield
        finally:
            binding.controller.release(token)

    def _acquisition(
        self, root: str, project_id: str, session_id: str, trace_id: str
    ) -> tuple[OpenAccessAcquisitionService, CorpusActor]:
        def selected(attachments: LocalDocumentAttachmentService, actor: CorpusActor):
            key = (root, project_id, session_id)
            service = self._acquisitions.get(key)
            if service is None:

                def guard(expected_actor: CorpusActor, action):
                    def current(_attachments, actual_actor):
                        if (
                            actual_actor.actor_id,
                            actual_actor.intent_revision_id,
                            actual_actor.intent_sha256,
                            actual_actor.policy_sha256,
                        ) != (
                            expected_actor.actor_id,
                            expected_actor.intent_revision_id,
                            expected_actor.intent_sha256,
                            expected_actor.policy_sha256,
                        ):
                            raise AcquisitionProblem("acquisition-authority-changed")
                        return action()

                    return self._action(root, project_id, session_id, trace_id, current)

                pages = ConnectorRepository(attachments._database, project_id, attachments._objects)
                service = OpenAccessAcquisitionService(
                    AcquisitionRepository(attachments._database, project_id, pages.source_record, attachments),
                    attachments,
                    session_id=session_id,
                    authority_guard=guard,
                    slot=self._acquisition_slots.setdefault(project_id, threading.BoundedSemaphore(1)),
                )
                # A close/reopen gets new, empty consent state. An old running
                # object still fences every socket/stage through native session.
                self._acquisitions = {other: value for other, value in self._acquisitions.items() if other[0] != root}
                self._acquisitions[key] = service
            return service, actor

        return self._action(root, project_id, session_id, trace_id, selected)

    def acquisition_locations(
        self, root: str, project_id: str, session_id: str, source_assertion_revision_id: str, *, trace_id: str
    ) -> tuple[AcquisitionLocation, ...]:
        service, actor = self._acquisition(root, project_id, session_id, trace_id)
        return service.guard(actor, lambda: service.repository.locations(source_assertion_revision_id, actor=actor))

    def acquisition_preview(
        self, root: str, project_id: str, session_id: str, selection: AcquisitionSelection, *, trace_id: str
    ) -> AcquisitionPreview:
        service, actor = self._acquisition(root, project_id, session_id, trace_id)
        return service.preview(selection, actor=actor)

    def acquisition_download(
        self,
        root: str,
        project_id: str,
        session_id: str,
        preview_id: str,
        *,
        confirmation: str,
        operation_id: str,
        trace_id: str,
        cancellation_requested: Callable[[], bool],
    ) -> AttachmentCandidate:
        service, _actor = self._acquisition(root, project_id, session_id, trace_id)

        def cancelled() -> bool:
            if cancellation_requested():
                return True
            try:
                return self._imports.native_context(root, project_id) != session_id
            except PreviewProblem, ProjectLifecycleProblem:
                return True

        # Remote waits and LPAC inspection run outside the lifecycle writer.
        with self._document_reservation(root, project_id):
            return service.acquire(
                preview_id,
                confirmation=confirmation,
                operation_id=operation_id,
                cancellation_requested=cancelled,
            )

    def context(self, root: str, project_id: str) -> str:
        return self._imports.native_context(root, project_id)

    def recover_candidate(self, command: DocumentCandidateRecovery, *, trace_id: str) -> AttachmentCandidate:
        # A caller-provided session is meaningful only inside this native/Core
        # lifecycle fence and current Corpus authority, as with explicit Attach.
        return self._action(
            command.root,
            command.project_id,
            command.session_id,
            trace_id,
            lambda selected, actor: selected.recover_candidate(
                command.candidate_id,
                original_operation_id=command.original_operation_id,
                recovery_operation_id=command.recovery_operation_id,
                session_id=command.session_id,
                confirmation_sha256=command.confirmation_sha256,
                exact_selection=command.selection.association,
                actor=actor,
            ),
        )

    def record_access_need(self, command: DocumentAccessNeedCommand, *, trace_id: str):
        def record(selected, actor):
            pages = ConnectorRepository(selected._database, command.project_id, selected._objects)
            repository = AcquisitionRepository(selected._database, command.project_id, pages.source_record, selected)
            return repository.record_access_need(
                command.selection,
                command_id=command.command_id,
                kind=command.kind,
                channel=command.channel,
                actor=actor,
            )

        return self._action(command.root, command.project_id, command.session_id, trace_id, record)

    def retained_candidates(self, command: DocumentRecoveryQuery, *, trace_id: str):
        return self._action(
            command.root,
            command.project_id,
            command.session_id,
            trace_id,
            lambda selected, actor: selected.retained_candidates(command.selection, actor=actor),
        )

    def _action[Result](
        self,
        root: str,
        project_id: str,
        session_id: str,
        trace_id: str,
        action: Callable[[LocalDocumentAttachmentService, CorpusActor], Result],
        *,
        session_stop: Callable[[Callable[[], bool]], None] | None = None,
    ) -> Result:
        native_stores: list[ObjectStore] = []

        def current(project_scope: _ProjectActionScope | None = None) -> Result:
            def authorized(_repository, actor, _intent, path: Path, actual_id: str) -> Result:
                if actual_id != project_id:
                    raise AttachmentProblem("attachment-authority-changed")
                if project_scope is None:
                    objects = self._object_store_factory(path, actual_id)
                else:
                    if len(native_stores) != 1:
                        raise AttachmentProblem("attachment-authority-changed")
                    # The exact current native binding prepared this adapter
                    # at open. Each operation still checks current authority,
                    # keys and policy; no selected binding escapes this action.
                    objects = native_stores[0]
                service = LocalDocumentAttachmentService(
                    path / "state/project.sqlite3", actual_id, objects
                )
                return action(service, actor)

            # Corpus owns current researcher, accepted Intent, privacy and
            # write authority. The native session fences close/reopen and
            # project switches throughout this one bounded action.
            if project_scope is None:
                return self._corpus._with_authority(root, trace_id, authorized)
            return self._corpus._with_authority(root, trace_id, authorized, project_scope=project_scope)

        if session_stop is None:
            return self._imports.in_native_session(root, project_id, session_id, current)
        return self._imports.in_native_scoped_session(
            root,
            project_id,
            session_id,
            current,
            session_stop=session_stop,
            store_consumer=native_stores.append,
        )

    def stage(
        self,
        command: DocumentStageCommand,
        source: BinaryIO,
        *,
        trace_id: str,
        cancellation_requested: Callable[[], bool],
    ) -> AttachmentCandidate:
        service, actor = self._action(
            command.root,
            command.project_id,
            command.session_id,
            trace_id,
            lambda selected, current_actor: (selected, current_actor),
        )

        def cancelled() -> bool:
            if cancellation_requested():
                return True
            try:
                return self._imports.native_context(command.root, command.project_id) != command.session_id
            except PreviewProblem, ProjectLifecycleProblem:
                return True

        def publication_guard[Result](action: Callable[[], Result]) -> Result:
            def current(_service: LocalDocumentAttachmentService, current_actor: CorpusActor) -> Result:
                if (
                    current_actor.actor_id,
                    current_actor.intent_revision_id,
                    current_actor.intent_sha256,
                    current_actor.policy_sha256,
                ) != (actor.actor_id, actor.intent_revision_id, actor.intent_sha256, actor.policy_sha256):
                    raise AttachmentProblem("attachment-authority-changed")
                return action()

            return self._action(command.root, command.project_id, command.session_id, trace_id, current)

        # The lifecycle mutex is released throughout encrypted upload and LPAC
        # inspection. Only the final candidate transaction is fenced by the
        # current project session again.
        with self._document_reservation(command.root, command.project_id):
            return service.stage(
                source,
                source_name=command.source_name,
                declared_media_type=command.declared_media_type,
                source_assertion_revision_id=command.source_assertion_revision_id,
                work_id=command.work_id,
                work_revision_id=command.work_revision_id,
                version_id=command.version_id,
                version_revision_id=command.version_revision_id,
                actor=actor,
                operation_id=command.operation_id,
                session_id=command.session_id,
                cancellation_requested=cancelled,
                publication_guard=publication_guard,
            )

    def load_candidate(
        self, root: str, project_id: str, session_id: str, candidate_id: str, *, trace_id: str
    ) -> AttachmentCandidate:
        return self._action(
            root,
            project_id,
            session_id,
            trace_id,
            lambda service, actor: service.load_candidate(candidate_id, actor=actor),
        )

    def cancel(
        self,
        root: str,
        project_id: str,
        session_id: str,
        candidate_id: str,
        *,
        operation_id: str,
        trace_id: str,
    ) -> None:
        self._action(
            root,
            project_id,
            session_id,
            trace_id,
            lambda service, actor: service.cancel(
                candidate_id, actor=actor, operation_id=operation_id, session_id=session_id
            ),
        )

    def status(self, command: DocumentStatusQuery, *, trace_id: str) -> DocumentAttachmentStatus:
        return self._action(
            command.root,
            command.project_id,
            command.session_id,
            trace_id,
            lambda service, actor: service.status(
                source_assertion_revision_id=command.source_assertion_revision_id,
                work_id=command.work_id,
                work_revision_id=command.work_revision_id,
                version_id=command.version_id,
                version_revision_id=command.version_revision_id,
                operation_id=command.operation_id,
                command_id=command.command_id,
                session_id=command.session_id,
                actor=actor,
            ),
        )

    def commit(self, command: DocumentCommit, *, trace_id: str) -> DocumentAttachment:
        return self._action(
            command.root,
            command.project_id,
            command.session_id,
            trace_id,
            lambda service, actor: service.commit(
                command.candidate_id,
                confirmation_sha256=command.confirmation_sha256,
                command_id=command.command_id,
                actor=actor,
                operation_id=command.operation_id,
                session_id=command.session_id,
                match_confirmed=command.match_confirmed,
                permitted_use=command.permitted_use,
                exact_selection=(
                    command.source_assertion_revision_id,
                    command.work_id,
                    command.work_revision_id,
                    command.version_id,
                    command.version_revision_id,
                ),
            ),
        )


def create_runtime_app(
    *,
    settings: CoreSettings,
    capability_digest: bytes | None = None,
    expected_authority: str | None = None,
    object_key_provider: ObjectMasterKeyProvider | None | object = _DEFAULT_OBJECT_KEY_PROVIDER,
    database_key_provider: DatabaseKeyProvider | None | object = _DEFAULT_DATABASE_KEY_PROVIDER,
    local_actor_id: str | None | object = _DEFAULT_LOCAL_ACTOR_ID,
    profile_vault_root: Path | None = None,
    workflow_context: NativeWorkflowContext | None = None,
    connector_settings: ConnectorSettings | None | object = _DEFAULT_CONNECTOR_SETTINGS,
) -> FastAPI:
    """Compose Core with the Windows profile vault and mandatory pre-open upgrades."""

    if object_key_provider is _DEFAULT_OBJECT_KEY_PROVIDER:
        resolved_provider = create_windows_object_key_provider(profile_vault_root) if os.name == "nt" else None
    else:
        if profile_vault_root is not None:
            raise ValueError("an injected object-key provider cannot also select a profile vault root")
        if object_key_provider is not None and not isinstance(object_key_provider, ObjectMasterKeyProvider):
            raise ValueError("object-key provider is invalid")
        resolved_provider = object_key_provider

    if database_key_provider is _DEFAULT_DATABASE_KEY_PROVIDER:
        if os.name != "nt":
            if database_protection_profile() != DEVELOPMENT_PLAINTEXT_PROFILE:
                raise RuntimeError("the W1 protected database profile requires Windows")
        else:
            configure_protected_database_provider(create_windows_database_key_provider(profile_vault_root))
    elif database_key_provider is None:
        if database_protection_profile() != DEVELOPMENT_PLAINTEXT_PROFILE:
            raise ValueError("plaintext database operation is allowed only in the explicit development fixture profile")
    else:
        if profile_vault_root is not None:
            raise ValueError("an injected database-key provider cannot also select a profile vault root")
        if not isinstance(database_key_provider, DatabaseKeyProvider):
            raise ValueError("database-key provider is invalid")
        configure_protected_database_provider(database_key_provider)

    if local_actor_id is _DEFAULT_LOCAL_ACTOR_ID:
        if os.name == "nt":
            try:
                resolved_actor_id: str | None = create_windows_local_actor_identity(profile_vault_root)
            except CredentialStoreProblem:
                resolved_actor_id = None
                emit_log_record(
                    "security.local-actor-unavailable",
                    level="ERROR",
                    fields={"reasonCode": "local-actor-profile-authority-unavailable"},
                )
        else:
            resolved_actor_id = None
    elif local_actor_id is None or isinstance(local_actor_id, str):
        resolved_actor_id = local_actor_id
    else:
        raise ValueError("local actor identity is invalid")

    projects = ProjectLifecycleService(
        object_upgrade=partial(upgrade_local_object_envelopes, key_provider=resolved_provider)
    )
    privacy = ProjectPrivacyService(projects, sqlite_privacy_policy_repository)
    # One process-wide resource ledger, with explicit interactive headroom.
    # These are conservative admission reservations, not OS-enforced quotas.
    controller = LocalAdmissionController(interactive_reserve=WorkerResources(1, 256 * 1024**2, 0, 256 * 1024**2))
    # Every adapter shares this policy. Actual parser activity eligibility
    # reserves the four-CPU/four-GiB bounds before claim; metadata stays lighter.

    def import_adapters(path: Path, identity: str) -> ImportProjectAdapters:
        queue = sqlite_workflow_queue_repository(path, identity)
        return ImportProjectAdapters(
            previews=sqlite_import_preview_repository(path / "state/project.sqlite3", identity),
            intents=sqlite_intent_revision_repository(path, identity),
            queue=queue,
            store=create_local_object_store(
                path,
                identity,
                key_provider=resolved_provider,
                access_policy=privacy.object_access_policy(str(path)),
                reconcile_abandoned=False,
            ),
            units=create_sqlite_unit_of_work_factory(path / "state/project.sqlite3", identity),
            admission=sqlite_workflow_admission_binding(
                queue,
                controller=controller,
                policy=document_worker_policy(identity),
            ),
        )

    from .reconciliation_repository import SqliteReconciliationRepository
    from .reconciliation_service import ReconciliationService
    from .reconciliation_worker import ReconciliationBatchAdapters

    imports = None
    reconciliation = None
    connectors = None
    plugin_admin = None
    plugin_consent = None
    plugin_worker = None
    corpus = None
    attachments = None
    document_revisions = None
    if workflow_context is not None and resolved_actor_id is not None and resolved_provider is not None:
        imports = ImportPreviewService(
            projects,
            privacy,
            import_adapters,
            local_actor_id=resolved_actor_id,
            resume_epoch=workflow_context.resume_epoch,
        )

        def connector_pages(path: Path, identity: str) -> ConnectorRepository:
            return ConnectorRepository(
                path / "state/project.sqlite3",
                identity,
                create_local_object_store(
                    path,
                    identity,
                    key_provider=resolved_provider,
                    access_policy=privacy.object_access_policy(str(path)),
                    reconcile_abandoned=False,
                ),
            )

        def connector_adapters(path: Path, identity: str) -> ConnectorWorkerAdapters:
            queue = sqlite_workflow_queue_repository(path, identity)
            return ConnectorWorkerAdapters(
                connector_pages(path, identity),
                queue,
                sqlite_workflow_admission_binding(
                    queue,
                    controller=controller,
                    policy=document_worker_policy(identity),
                ),
            )

        consent = ConnectorConsentService(
            projects,
            privacy,
            lambda path, identity: ConnectorProjectAdapters(
                sqlite_intent_revision_repository(path, identity), connector_pages(path, identity)
            ),
            local_actor_id=resolved_actor_id,
        )
        resolved_connector_settings: ConnectorSettings | None
        if connector_settings is _DEFAULT_CONNECTOR_SETTINGS:
            resolved_connector_settings = ConnectorSettings(
                WindowsCredentialStore(profile_vault_root or default_windows_profile_vault_path())
                if os.name == "nt"
                else None
            )
        elif connector_settings is None or isinstance(connector_settings, ConnectorSettings):
            resolved_connector_settings = connector_settings
        else:
            raise ValueError("connector settings authority is invalid")
        connectors = ConnectorWorkerService(
            projects,
            consent,
            connector_adapters,
            local_actor_id=resolved_actor_id,
            settings=resolved_connector_settings,
        )

        if os.name == "nt":
            installed_plugin_runtime = InstalledPluginRuntime()
            plugin_admin = PluginAdminService(
                projects,
                PluginPublisherTrustStore(
                    WindowsCredentialStore(profile_vault_root or default_windows_profile_vault_path()),
                    "local-default",
                ),
                actor_id=resolved_actor_id,
                grant_repository_factory=lambda path, identity: SqlitePluginGrantRepository(
                    path / "state/project.sqlite3", identity
                ),
                package_repository_factory=lambda path, identity: SqlitePluginPackageRepository(
                    path / "state/project.sqlite3", identity
                ),
                runtime_available=installed_plugin_runtime.available,
                package_store_factory=lambda path, identity: PluginPackageStore(
                    create_local_object_store(
                        path,
                        identity,
                        key_provider=resolved_provider,
                        access_policy=privacy.object_access_policy(str(path)),
                        reconcile_abandoned=False,
                    )
                ),
            )
            plugin_consent = PluginConsentService(projects, privacy, plugin_admin, sqlite_intent_revision_repository)

            def plugin_adapters(path: Path, identity: str) -> PluginWorkerAdapters:
                queue = sqlite_workflow_queue_repository(path, identity)
                objects = create_local_object_store(
                    path,
                    identity,
                    key_provider=resolved_provider,
                    access_policy=privacy.object_access_policy(str(path)),
                    reconcile_abandoned=False,
                )
                return PluginWorkerAdapters(
                    PluginJobRepository(path / "state/project.sqlite3", identity, objects),
                    queue,
                    sqlite_workflow_admission_binding(
                        queue,
                        controller=controller,
                        policy=document_worker_policy(identity),
                    ),
                    objects,
                )

            plugin_worker = PluginWorkerService(
                projects,
                plugin_admin,
                plugin_consent,
                plugin_adapters,
                local_actor_id=resolved_actor_id,
                runtime=installed_plugin_runtime,
                credentials=PluginCredentialSettings(
                    WindowsCredentialStore(profile_vault_root or default_windows_profile_vault_path())
                ),
            )

        def reconciliation_adapters(path: Path, identity: str) -> ReconciliationBatchAdapters:
            queue = sqlite_workflow_queue_repository(path, identity)
            return ReconciliationBatchAdapters(
                SqliteReconciliationRepository(path / "state/project.sqlite3", identity),
                queue,
                sqlite_workflow_admission_binding(
                    queue,
                    controller=controller,
                    policy=document_worker_policy(identity),
                ),
            )

        reconciliation = ReconciliationService(
            projects,
            privacy,
            imports=imports,
            connectors=connectors,
            repository_factory=lambda path, identity: SqliteReconciliationRepository(
                path / "state/project.sqlite3", identity
            ),
            intent_factory=sqlite_intent_revision_repository,
            actor_id=resolved_actor_id,
            batch_adapter_factory=reconciliation_adapters,
            resume_epoch=workflow_context.resume_epoch,
        )
        corpus = CorpusService(
            projects,
            privacy,
            imports=imports,
            connectors=connectors,
            repository_factory=lambda path, identity: SqliteCorpusRepository(path / "state/project.sqlite3", identity),
            report_repository_factory=lambda path, identity: SqliteCorpusReportRepository(
                path / "state/project.sqlite3", identity
            ),
            intent_factory=sqlite_intent_authority_snapshot,
            actor_id=resolved_actor_id,
            connector_query=ConnectorWorkerQueryResolver(connectors),
            rights_repository_factory=lambda path, identity: SqliteRightsRepository(
                path / "state/project.sqlite3",
                identity,
                connector_record_resolver=lambda revision, ordinal: connector_pages(path, identity).source_record(
                    revision, ordinal
                ),
            ),
        )
        attachments = DocumentAttachmentRuntime(
            imports,
            corpus,
            lambda path, identity: create_local_object_store(
                path,
                identity,
                key_provider=resolved_provider,
                access_policy=privacy.object_access_policy(str(path)),
                reconcile_abandoned=False,
            ),
            admission_factory=lambda path, identity: sqlite_workflow_admission_binding(
                sqlite_workflow_queue_repository(path, identity),
                controller=controller,
                policy=document_worker_policy(identity),
            ),
        )
        document_revisions = DocumentRevisionService(
            attachments,
            imports,
            lambda path, identity: sqlite_workflow_admission_binding(
                sqlite_workflow_queue_repository(path, identity),
                controller=controller,
                policy=document_worker_policy(identity),
            ),
            repository_factory=LocalDocumentRevisionRepository,
        )
    return create_app(
        settings=settings,
        capability_digest=capability_digest,
        expected_authority=expected_authority,
        projects=projects,
        privacy=privacy,
        imports=imports,
        attachments=attachments,
        document_revisions=document_revisions,
        document_viewer=DocumentViewerService(attachments, imports) if attachments is not None else None,
        connectors=connectors,
        plugin_admin=plugin_admin,
        plugin_consent=plugin_consent,
        plugin_worker=plugin_worker,
        reconciliation=reconciliation,
        corpus=corpus,
        model_gateway=ProjectModelGatewayService(
            projects,
            privacy,
            local_actor_id=resolved_actor_id,
            routing_repository_factory=lambda path, identity, actor: SqliteModelRoutingRepository(
                path / "state/project.sqlite3", identity, actor
            ),
            catalog_repository_factory=sqlite_model_catalog_repository,
            unit_of_work_factory=lambda path, identity: create_sqlite_unit_of_work_factory(
                path / "state/project.sqlite3", identity
            ),
        ),
        model_catalog=ModelCatalogService(
            projects,
            repository_factory=sqlite_model_catalog_repository,
            local_actor_id=resolved_actor_id,
        ),
        intents=ResearchIntentService(
            projects,
            repository_factory=sqlite_intent_revision_repository,
            stale_state_repository_factory=sqlite_dependency_impact_repository,
            local_actor_id=resolved_actor_id,
        ),
        workflow_progress=WorkflowProgressService(
            projects,
            repository_factory=sqlite_workflow_progress_repository,
            intent_repository_factory=sqlite_intent_revision_repository,
            stale_state_repository_factory=sqlite_dependency_impact_repository,
            local_actor_id=resolved_actor_id,
        ),
        provenance=ProvenanceService(projects, sqlite_provenance_ledger_repository),
        task_center=TaskCenterService(projects, sqlite_workflow_queue_repository, resolved_actor_id),
        recalculation=RecalculationControlService(
            projects,
            recalculation_factory=sqlite_selective_recalculation_repository,
            dependency_factory=sqlite_material_dependency_repository,
            workflow_factory=sqlite_workflow_queue_repository,
            unit_of_work_factory=lambda path, project_id: create_sqlite_unit_of_work_factory(
                path / "state" / "project.sqlite3",
                project_id,
            ),
            local_actor_id=resolved_actor_id,
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research Observatory local Core API")
    parser.add_argument("--check", action="store_true", help="validate configuration without opening a socket")
    parser.add_argument("--version", action="store_true", help="print the component version and exit")
    parser.add_argument(
        "--supervised",
        action="store_true",
        help="emit the bounded desktop-supervision handshake and accept shutdown on stdin",
    )
    return parser


def supervision_handshake(*, host: str, port: int) -> dict[str, object]:
    """Return the portable, secret-safe startup handoff consumed by Tauri."""

    return {
        "protocolVersion": SUPERVISION_PROTOCOL_VERSION,
        "buildId": CORE_API_VERSION,
        "pid": os.getpid(),
        "host": host,
        "port": port,
        "nonce": secrets.token_hex(16),
        "capabilities": list(default_module_registry().capabilities),
        "databaseCompatibility": {
            "minimum": "0.1.0",
            "maximumExclusive": "0.2.0",
        },
        "diagnosticCode": STARTING_DIAGNOSTIC_CODE,
    }


def _watch_supervisor(server: uvicorn.Server) -> None:
    """Stop cleanly when the supervisor requests shutdown or closes its pipe."""

    try:
        command = sys.stdin.readline()
    except OSError, UnicodeError:
        command = ""
    if command == "shutdown\n" or command == "":
        server.should_exit = True


def run_supervised(settings: CoreSettings, *, profile_vault_root: Path | None = None) -> int:
    """Bind an OS-assigned loopback socket and serve under desktop ownership."""

    record = bytearray(sys.stdin.buffer.readline(WORKFLOW_STARTUP_RECORD_BYTES + 1))
    try:
        capability_digest, workflow_context = parse_startup_record(record)
    except ValueError:
        print(
            json.dumps(
                {
                    "schemaVersion": CORE_API_SCHEMA_VERSION,
                    "service": CORE_SERVICE_ID,
                    "status": "startup-authentication-error",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_CONFIGURATION_ERROR
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((settings.bind_host, settings.bind_port))
        assigned_host, assigned_port = listener.getsockname()
        authority = f"{assigned_host}:{assigned_port}"
        configuration = uvicorn.Config(
            create_runtime_app(
                settings=settings,
                capability_digest=capability_digest,
                expected_authority=authority,
                profile_vault_root=profile_vault_root,
                workflow_context=workflow_context,
            ),
            host=assigned_host,
            port=assigned_port,
            log_level=settings.log_level.casefold(),
            access_log=False,
            server_header=False,
            log_config=None,
            proxy_headers=False,
        )
        del capability_digest
        server = uvicorn.Server(configuration)
        print(json.dumps(supervision_handshake(host=assigned_host, port=assigned_port), sort_keys=True), flush=True)
        watcher = threading.Thread(target=_watch_supervisor, args=(server,), name="supervisor-control", daemon=True)
        watcher.start()
        server.run(sockets=[listener])
    finally:
        listener.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.version:
        print(CORE_API_VERSION)
        return 0
    try:
        settings = CoreSettings()
    except ValidationError:
        print(
            json.dumps(
                {
                    "schemaVersion": CORE_API_SCHEMA_VERSION,
                    "service": CORE_SERVICE_ID,
                    "status": "configuration-error",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_CONFIGURATION_ERROR
    if arguments.check:
        # Construct the migration projection so frozen-package qualification
        # proves the governed migration runtime is loadable without expanding
        # the stable public configuration-check envelope.
        migration_framework_projection()
        print(
            json.dumps(
                {
                    "schemaVersion": CORE_API_SCHEMA_VERSION,
                    "service": CORE_SERVICE_ID,
                    "status": "configuration-valid",
                    "configuration": settings.public_projection(),
                },
                sort_keys=True,
            )
        )
        return 0
    if arguments.supervised:
        return run_supervised(settings)
    uvicorn.run(
        create_runtime_app(settings=settings),
        host=settings.bind_host,
        port=settings.bind_port,
        log_level=settings.log_level.casefold(),
        access_log=False,
        server_header=False,
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
