"""Core API process entry point."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import threading
from functools import partial
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pydantic import ValidationError

from . import CORE_API_SCHEMA_VERSION, CORE_API_VERSION, CORE_SERVICE_ID
from .app import create_app
from .authentication import STARTUP_RECORD_BYTES, parse_startup_authentication
from .config import CoreSettings
from .logging import emit_log_record
from .migrations.runner import migration_framework_projection
from .modules import default_module_registry
from .object_store import upgrade_local_object_envelopes
from .ports.credential_store import CredentialStoreProblem
from .ports.database_keys import DatabaseKeyProvider
from .ports.object_store_keys import ObjectMasterKeyProvider
from .privacy import ProjectPrivacyService
from .projects import ProjectLifecycleService
from .provenance import ProvenanceService
from .repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_intent_revision_repository,
    sqlite_material_dependency_repository,
    sqlite_privacy_policy_repository,
    sqlite_provenance_ledger_repository,
    sqlite_selective_recalculation_repository,
    sqlite_workflow_queue_repository,
)
from .research_intents import ResearchIntentService
from .selective_recalculation import RecalculationControlService
from .storage import (
    DEVELOPMENT_PLAINTEXT_PROFILE,
    configure_protected_database_provider,
    database_protection_profile,
)
from .task_center import TaskCenterService
from .windows_credentials import (
    create_windows_database_key_provider,
    create_windows_local_actor_identity,
    create_windows_object_key_provider,
)

EXIT_CONFIGURATION_ERROR = 2
SUPERVISION_PROTOCOL_VERSION = "1.0"
STARTING_DIAGNOSTIC_CODE = "RO-CORE-STARTING"
_DEFAULT_OBJECT_KEY_PROVIDER = object()
_DEFAULT_DATABASE_KEY_PROVIDER = object()
_DEFAULT_LOCAL_ACTOR_ID = object()


def create_runtime_app(
    *,
    settings: CoreSettings,
    capability_digest: bytes | None = None,
    expected_authority: str | None = None,
    object_key_provider: ObjectMasterKeyProvider | None | object = _DEFAULT_OBJECT_KEY_PROVIDER,
    database_key_provider: DatabaseKeyProvider | None | object = _DEFAULT_DATABASE_KEY_PROVIDER,
    local_actor_id: str | None | object = _DEFAULT_LOCAL_ACTOR_ID,
    profile_vault_root: Path | None = None,
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
    return create_app(
        settings=settings,
        capability_digest=capability_digest,
        expected_authority=expected_authority,
        projects=projects,
        privacy=ProjectPrivacyService(projects, sqlite_privacy_policy_repository),
        intents=ResearchIntentService(
            projects,
            repository_factory=sqlite_intent_revision_repository,
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

    record = bytearray(sys.stdin.buffer.readline(STARTUP_RECORD_BYTES + 1))
    try:
        capability_digest = parse_startup_authentication(record)
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
