"""Supervised Core entrypoint for the native intent vertical integration check."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import threading
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any
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
    worker_build_input, guardian_input, guardian_digest = values
    if not any(values):
        return None
    if not worker_build_input or not guardian_input or not guardian_digest:
        raise ValueError("signed-probe-input-incomplete")

    from workers.windows.runtime_inventory import (
        APPLICATION_INVENTORY_PUBLIC_KEY,
        SignedWorkerRuntime,
        verify_worker_runtime,
    )

    scratch = Path(__file__).resolve().parents[3] / "artifacts" / "tmp"
    if scratch != scratch.resolve(strict=True) or scratch.is_symlink() or scratch.is_junction():
        raise ValueError("signed-probe-scratch-invalid")
    worker_build = _canonical_probe_path(worker_build_input, scratch, directory=True)
    if worker_build.parent != scratch:
        raise ValueError("signed-probe-worker-location-invalid")
    guardian = _canonical_probe_path(guardian_input, scratch, directory=False)
    if guardian.name != "research-observatory-core-x86_64-pc-windows-msvc.exe":
        raise ValueError("signed-probe-guardian-identity-invalid")
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


@contextmanager
def _owned_roles_probe(profile_vault_root: Path) -> Iterator[None]:
    # Only the private Windows Native fixture supplies this enable switch.
    # No arbitrary filename, command, role or output directory is accepted.
    if os.environ.get("RO_W3_CORE_LIFETIME_PROBE") != "1":
        yield
        return

    from research_observatory_core import main as core_main
    from research_observatory_core import windows_credentials
    from research_observatory_core.windows_credentials import (
        WindowsRecoveryNativeAuthority,
        _recovery_current_process_identity,
    )

    from workers.windows import connector_launcher, lpac_launcher, no_write_acl, recovery_guardian

    repository = Path(__file__).resolve().parents[3]
    scratch = repository / "artifacts" / "tmp"
    fixture = profile_vault_root.parent
    if (
        fixture.parent != scratch
        or not fixture.name.startswith("search-populated-native-")
        or fixture != fixture.resolve(strict=True)
        or profile_vault_root != profile_vault_root.resolve(strict=True)
    ):
        raise ValueError("native-lifetime-fixture-invalid")
    proof_root = fixture / "core-owned-role-proof"
    if not proof_root.is_dir() or proof_root != proof_root.resolve(strict=True):
        raise ValueError("native-lifetime-proof-root-invalid")
    for path in (proof_root, profile_vault_root, fixture, scratch):
        if path.is_symlink() or path.is_junction():
            raise ValueError("native-lifetime-proof-redirected")

    # Import every alias-bearing module BEFORE capturing originals. Count entry,
    # not successful spawn; even failed launch attempts invalidate zero proof.
    originals = (
        (recovery_guardian, "start_guardian", "guardian"),
        (connector_launcher, "start_guardian", "guardian"),
        (connector_launcher, "_launch_signed_worker", "connector-worker"),
        (lpac_launcher, "_launch", "lpac-worker"),
        (lpac_launcher, "_run_icacls", "acl-utility"),
        (no_write_acl, "_run_icacls", "acl-utility"),
    )
    coverage = {
        "aliasesMatchedAtInstall": connector_launcher.start_guardian is recovery_guardian.start_guardian
        and no_write_acl._run_icacls is lpac_launcher._run_icacls,
        "observerError": False,
    }
    counters = {
        role: {"attempts": 0, "returns": 0, "errors": 0, "inflight": 0}
        for role in ("guardian", "connector-worker", "lpac-worker", "acl-utility")
    }
    guard = threading.Lock()
    identity = asdict(_recovery_current_process_identity())
    source_paths = [Path(__file__)]
    for module in (
        connector_launcher,
        lpac_launcher,
        no_write_acl,
        recovery_guardian,
        core_main,
        windows_credentials,
    ):
        source_file = module.__file__
        if not isinstance(source_file, str):
            raise ValueError("native-lifetime-source-unavailable")
        source_paths.append(Path(source_file))

    def source_pins() -> dict[str, str]:
        return {
            path.relative_to(repository).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_paths
        }

    initial_pins = source_pins()

    def note(role: str, event: str) -> None:
        try:
            with guard:
                counts = counters[role]
                if event == "entry":
                    counts["attempts"] += 1
                    counts["inflight"] += 1
                else:
                    counts[event] += 1
                    counts["inflight"] -= 1
        except BaseException:
            # An observer error never replaces an original launch result or
            # exception. Missing/uncertain proof is denied by the Native owner.
            coverage["observerError"] = True

    def wrap(original: Any, role: str) -> Any:
        def observed(*args: Any, **kwargs: Any) -> Any:
            note(role, "entry")
            try:
                result = original(*args, **kwargs)
            except BaseException:
                note(role, "errors")
                raise
            note(role, "returns")
            return result

        return observed

    installed = [(module, name, wrap(getattr(module, name), role)) for module, name, role in originals]
    runtime_returned = False
    with ExitStack() as stack:
        for module, name, wrapper in installed:
            stack.enter_context(patch.object(module, name, new=wrapper))
        try:
            yield
            runtime_returned = True
        finally:
            # No wait, poll, launch, kill, pipe read or worker cleanup is added.
            # A nonzero invocation cannot claim normal drain with this observer.
            try:
                aliases_retained = all(getattr(module, name) is wrapper for module, name, wrapper in installed)
                pins_equal = source_pins() == initial_pins
                # Runtime shutdown must already have stopped launch-capable
                # worker pumps. Query only; never join or extend their deadline.
                live = [thread for thread in threading.enumerate() if thread.is_alive()]

                def proven_nonlaunch(thread: threading.Thread) -> bool:
                    if thread is threading.main_thread():
                        return True
                    target = getattr(thread, "_target", None)
                    if target is core_main._watch_supervisor:
                        return True
                    owner = getattr(target, "__self__", None)
                    return (
                        getattr(target, "__func__", None) is WindowsRecoveryNativeAuthority._write_control
                        and type(owner) is WindowsRecoveryNativeAuthority
                        and getattr(owner, "_writer", None) is thread
                    )

                live_threads = sorted(thread.name for thread in live)
                unexpected_threads = sorted(thread.name for thread in live if not proven_nonlaunch(thread))
                # This is the FINAL registry snapshot, after every potentially
                # interleaving source/alias/thread check. Text names grant no
                # exemption. Remaining launch-capable/unknown threads deny zero.
                with guard:
                    observed = {role: dict(counts) for role, counts in counters.items()}
                    coverage_snapshot = dict(coverage)
                zero = (
                    runtime_returned
                    and coverage_snapshot["aliasesMatchedAtInstall"]
                    and not coverage_snapshot["observerError"]
                    and aliases_retained
                    and pins_equal
                    and not unexpected_threads
                    and all(all(value == 0 for value in counts.values()) for counts in observed.values())
                )
                record = {
                    "kind": "test-only-core-owned-role-zero-observation",
                    "coreIdentity": identity,
                    "installedBeforeRuntimeComposition": True,
                    "runtimeReturned": runtime_returned,
                    "finalizedBeforeCoreExit": True,
                    "coverage": coverage_snapshot,
                    "aliasesRetainedUntilFinalization": aliases_retained,
                    "sourcePins": initial_pins,
                    "sourcePinsEqualAfter": pins_equal,
                    "liveThreadsAtFinalization": live_threads,
                    "unexpectedLiveThreads": unexpected_threads,
                    "roles": observed,
                    "observedZeroRoleAttempts": zero,
                    "positiveWorkerGuardianDrain": "NOT_OBSERVED",
                    "limits": (
                        "Selected metadata-only journey. Any invocation or uncertainty invalidates observed zero. "
                        "Originals forward unchanged. Observer import/wrapper/hash/receipt overhead is part of the "
                        "instrumented run; no new waits or cleanup."
                    ),
                }
                filename = f"core-owned-roles-{identity['process_id']}-{identity['creation_filetime']}.json"
                with (proof_root / filename).open("x", encoding="utf-8", newline="\n") as output:
                    output.write(json.dumps(record, indent=2) + "\n")
                    output.flush()
                    os.fsync(output.fileno())
            except BaseException:
                # Retained Core exit alone cannot replace a missing receipt.
                # Original runtime return/exception and cleanup remain unchanged.
                pass


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
        exact_stage = scope.get("type") == "http" and scope.get("path") == "/native/document-attachments/stage"
        status = None
        body_seen = False

        async def observed_send(message) -> None:
            nonlocal status, body_seen
            await send(message)
            if not exact_stage:
                return
            if message.get("type") == "http.response.start":
                value = message.get("status")
                status = value if type(value) is int and 400 <= value <= 599 else None
            elif message.get("type") == "http.response.body" and not body_seen:
                body_seen = True
                body = message.get("body")
                if (
                    status is None
                    or message.get("more_body") is True
                    or not isinstance(body, bytes)
                    or len(body) > 2048
                ):
                    return
                try:
                    problem = json.loads(body)
                except ValueError, UnicodeError:
                    return
                if not isinstance(problem, dict):
                    return
                # Only fixed known classifications, never a supplied code,
                # exception message, source name, path or document content.
                supplied_code = problem.get("code")
                code = {
                    "RO-CORE-DOCUMENT-UNAVAILABLE": "document-unavailable",
                    "RO-CORE-DOCUMENT-INTAKE-INVALID": "intake-invalid",
                    "RO-CORE-DOCUMENT-WORKER-UNAVAILABLE": "worker-unavailable",
                    "RO-CORE-DOCUMENT-STORAGE-UNAVAILABLE": "storage-unavailable",
                    "RO-CORE-INTERNAL-FAILED": "internal-failed",
                }.get(supplied_code if isinstance(supplied_code, str) else "", "other")
                try:
                    if not self._temporary.is_dir() or self._temporary.is_symlink() or self._temporary.is_junction():
                        return
                    record = {"kind": "document-stage-rejection", "status": status, "code": code}
                    with (self._temporary / "document-stage-rejection.json").open("xb") as stream:
                        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii"))
                        stream.flush()
                        os.fsync(stream.fileno())
                except OSError:
                    pass

        try:
            await self._app(scope, receive, observed_send)
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
    with _owned_roles_probe(profile_vault_root):
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
