"""Supervised Core entrypoint for the native intent vertical integration check."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

from research_observatory_core import main as core_main
from research_observatory_core.config import CoreSettings
from research_observatory_core.main import run_supervised
from research_observatory_core.storage import configure_protected_database_provider, open_canonical_database
from research_observatory_core.windows_credentials import create_windows_database_key_provider


def _canonical_probe_path(value: str, scratch: Path, *, directory: bool) -> Path:
    """Accept only a canonical, nonredirected ignored local fixture artifact."""

    candidate = Path(value)
    if not candidate.is_absolute() or candidate != candidate.resolve(strict=True):
        raise ValueError("signed-probe-path-invalid")
    if (
        scratch not in candidate.parents
        or (directory and not candidate.is_dir())
        or (not directory and not candidate.is_file())
    ):
        raise ValueError("signed-probe-path-invalid")
    for part in (candidate, *candidate.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("signed-probe-path-redirected")
        if part == scratch:
            break
    return candidate


def _signed_document_probe():
    """Bind only a verified local test bundle to the source-Core fixture."""

    names = (
        "RO_W2_SIGNED_WORKER_BUILD",
        "RO_W2_CORE_SIDECAR_GUARDIAN",
        "RO_W2_CORE_SIDECAR_GUARDIAN_SHA256",
    )
    values = tuple(os.environ.get(name) for name in names)
    if not any(values):
        return None
    if not all(values):
        raise ValueError("signed-probe-input-incomplete")

    from workers.windows.runtime_inventory import (
        APPLICATION_INVENTORY_PUBLIC_KEY,
        SignedWorkerRuntime,
        verify_worker_runtime,
    )

    scratch = Path(__file__).resolve().parents[3] / "artifacts" / "tmp"
    if scratch != scratch.resolve(strict=True) or scratch.is_symlink() or scratch.is_junction():
        raise ValueError("signed-probe-scratch-invalid")
    worker_build = _canonical_probe_path(values[0], scratch, directory=True)
    if worker_build.parent != scratch:
        raise ValueError("signed-probe-worker-location-invalid")
    guardian = _canonical_probe_path(values[1], scratch, directory=False)
    if guardian.name != "research-observatory-core-x86_64-pc-windows-msvc.exe":
        raise ValueError("signed-probe-guardian-identity-invalid")
    guardian_digest = values[2]
    if re.fullmatch(r"[0-9a-fA-F]{64}", guardian_digest) is None:
        raise ValueError("signed-probe-guardian-hash-invalid")
    digest = hashlib.sha256()
    with guardian.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if not hmac.compare_digest(digest.hexdigest(), guardian_digest.lower()):
        raise ValueError("signed-probe-guardian-hash-mismatch")
    runtime = SignedWorkerRuntime(
        worker_build / "package",
        (worker_build / "inventory.json").read_bytes(),
        (worker_build / "inventory.sig").read_bytes(),
        APPLICATION_INVENTORY_PUBLIC_KEY,
    )
    verify_worker_runtime(runtime)
    return runtime, str(guardian)


_STAGE_EXCEPTION_CLASSES = {
    ("builtins", "AssertionError"): "builtins-assertion-error",
    ("builtins", "AttributeError"): "builtins-attribute-error",
    ("builtins", "FileNotFoundError"): "builtins-file-not-found",
    ("builtins", "ImportError"): "builtins-import-error",
    ("builtins", "KeyError"): "builtins-key-error",
    ("builtins", "MemoryError"): "builtins-memory-error",
    ("builtins", "ModuleNotFoundError"): "builtins-module-not-found",
    ("builtins", "OSError"): "builtins-os-error",
    ("builtins", "PermissionError"): "builtins-permission-error",
    ("builtins", "RuntimeError"): "builtins-runtime-error",
    ("builtins", "TimeoutError"): "builtins-timeout-error",
    ("builtins", "TypeError"): "builtins-type-error",
    ("builtins", "ValueError"): "builtins-value-error",
    ("workers.windows.lpac_launcher", "LPACError"): "worker-lpac-error",
    ("workers.windows.recovery_guardian", "GuardianError"): "worker-guardian-error",
    ("workers.windows.runtime_inventory", "RuntimeInventoryError"): "worker-inventory-error",
    ("workers.document.inspection", "DocumentInspectionError"): "worker-inspection-error",
}


def _record_stage_exception(error: Exception, temporary: Path) -> None:
    """Persist one fixed class code for a synthetic stage; never exception text."""
    identity = (type(error).__module__, type(error).__name__)
    record = {"kind": "document-stage-exception", "classCode": _STAGE_EXCEPTION_CLASSES.get(identity, "other")}
    try:
        if not temporary.is_dir() or temporary.is_symlink() or temporary.is_junction():
            return
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii")
        with (temporary / "document-stage-exception.json").open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        # The diagnostic cannot alter Core's original failure or response.
        pass


class _StageExceptionProbe:
    """Test-only outer ASGI observer; does not change the original response."""

    def __init__(self, app, temporary: Path) -> None:
        self._app = app
        self._temporary = temporary

    async def __call__(self, scope, receive, send) -> None:
        try:
            await self._app(scope, receive, send)
        except Exception as error:
            if scope.get("type") == "http" and scope.get("path") == "/native/document-attachments/stage":
                _record_stage_exception(error, self._temporary)
            raise


def inspect_project(profile_vault_root: Path, project_root: Path, project_id: str) -> int:
    """Report bounded persistence facts without exposing project or actor content."""

    configure_protected_database_provider(create_windows_database_key_provider(profile_vault_root))
    with open_canonical_database(
        project_root / "state" / "project.sqlite3",
        expected_project_id=project_id,
    ) as connection:
        revision_records = connection.execute(
            "SELECT COUNT(*) FROM settings WHERE setting_key='research-intent.revision'"
        ).fetchone()[0]
        event_rows = connection.execute(
            "SELECT event_type, COUNT(*), "
            "SUM(CASE WHEN actor_id IS NOT NULL AND actor_id <> '' THEN 1 ELSE 0 END) "
            "FROM provenance_events "
            "WHERE event_type IN ("
            "'intent.draft.saved','intent.accepted','intent.policy.evaluated','workflow.profile.activated'"
            ") "
            "GROUP BY event_type ORDER BY event_type"
        ).fetchall()
    events = {
        event_type: {"count": count, "actorBound": actor_bound == count}
        for event_type, count, actor_bound in event_rows
    }
    print(json.dumps({"revisionRecords": revision_records, "provenanceEvents": events}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-vault-root", type=Path, required=True)
    parser.add_argument("--supervised", action="store_true")
    parser.add_argument("--inspect-project-root", type=Path)
    parser.add_argument("--project-id")
    arguments = parser.parse_args()
    profile_vault_root = arguments.profile_vault_root.resolve(strict=True)
    if arguments.inspect_project_root is not None or arguments.project_id is not None:
        if arguments.supervised or arguments.inspect_project_root is None or arguments.project_id is None:
            parser.error("inspection requires project root and project ID without supervised mode")
        return inspect_project(
            profile_vault_root,
            arguments.inspect_project_root.resolve(strict=True),
            arguments.project_id,
        )
    if not arguments.supervised:
        parser.error("the integration sidecar requires supervised or inspection mode")
    try:
        signed_probe = _signed_document_probe()
    except OSError, ValueError:
        # The child never prints a local path, token, or exception body.
        print("RO-W2-SIGNED-DOCUMENT-PROBE-INVALID", file=sys.stderr, flush=True)
        return 2
    if signed_probe is None:
        return run_supervised(CoreSettings(), profile_vault_root=profile_vault_root)
    from workers.windows import document_launcher, recovery_guardian

    runtime, guardian = signed_probe
    temporary = _canonical_probe_path(
        str(profile_vault_root.parent / "temporary"),
        Path(__file__).resolve().parents[3] / "artifacts" / "tmp",
        directory=True,
    )
    original_app_factory = core_main.create_runtime_app

    def diagnostic_app_factory(**kwargs):
        return _StageExceptionProbe(original_app_factory(**kwargs), temporary)

    with (
        patch.object(document_launcher, "load_installed_worker_runtime", return_value=runtime),
        patch.object(recovery_guardian, "_guardian_command", return_value=[guardian, "--plugin-acl-guardian"]),
        patch.object(core_main, "create_runtime_app", side_effect=diagnostic_app_factory),
    ):
        return run_supervised(CoreSettings(), profile_vault_root=profile_vault_root)


if __name__ == "__main__":
    raise SystemExit(main())
