"""Project-scoped privacy policy and bounded cache-clearing authority."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .domain_contracts import new_uuid_v7
from .logging import emit_log_record
from .models import (
    CacheClearPreview,
    CacheClearRequest,
    CacheClearResult,
    CacheClearState,
    DeletionDisclosure,
    DocumentRetentionPolicy,
    EgressEnforcement,
    PrivacyNetworkPolicy,
    PrivacyPolicyProjection,
    PrivacyPolicyUpdateRequest,
    RemoteModelApproval,
    TelemetryMode,
)
from .ports.object_store import ObjectAccessDecision, ObjectAccessPolicy, ObjectAccessRequest
from .ports.repositories import (
    PrivacyAuditEvent,
    PrivacyPolicyRepository,
    PrivacySetting,
    RepositoryConflict,
    RepositoryProblem,
)
from .projects import ProjectLifecycleService, _held_directory_renamer, _stable_directories

_SETTING_KEYS = (
    "privacy.cache-retention-days",
    "privacy.document-retention",
    "privacy.egress-consent-version",
    "privacy.log-retention-days",
    "privacy.network-policy",
    "privacy.remote-model-approval",
    "privacy.telemetry-mode",
)
_DEFAULTS: dict[str, str | int] = {
    "privacy.cache-retention-days": 30,
    "privacy.document-retention": "project-lifetime",
    "privacy.egress-consent-version": "none",
    "privacy.log-retention-days": 14,
    "privacy.network-policy": "offline",
    "privacy.remote-model-approval": "preview-every-task",
    "privacy.telemetry-mode": "off",
}
_CONSENT_TOKEN = "acknowledge-egress-preview-v1"
_CONSENT_VERSION = "egress-preview-v1"
_PREVIEW_LIFETIME_SECONDS = 300.0
_MAX_CACHE_ITEMS = 100_000
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_CACHE_TOMBSTONE_PREFIX = "cache-clear-"
_DELETION_LIMITATIONS = (
    "Filesystem unlink does not prove physical media erasure.",
    "SSD wear levelling and device remapping can retain prior blocks.",
    "Filesystem journals, snapshots, backups, and hard links can retain copies.",
    "Only the rebuildable project cache is cleared; canonical project data is excluded.",
)
_PrivacyRepositoryFactory = Callable[[Path, str], PrivacyPolicyRepository]


@dataclass(slots=True)
class PrivacyPolicyProblem(Exception):
    status: int
    code: str
    title: str
    detail: str
    remediation: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class _CacheInventory:
    root_identity: tuple[int, int]
    fingerprint: str
    item_count: int
    byte_count: int
    directories: tuple[tuple[str, tuple[int, int]], ...]


@dataclass(slots=True)
class _CacheTreeProtection:
    _preserve_callbacks: list[Callable[[], None]] = field(default_factory=list)

    def preserve_for_cleanup(self) -> None:
        """Retain deny-add ACLs while a staged tree is physically removed."""

        for preserve in self._preserve_callbacks:
            preserve()


@dataclass(frozen=True, slots=True)
class _PendingCachePreview:
    project_id: str
    root: Path
    policy_revision: int
    inventory: _CacheInventory
    expires_monotonic: float
    expires_at: datetime


def _problem(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    remediation: str,
    retryable: bool = False,
) -> PrivacyPolicyProblem:
    return PrivacyPolicyProblem(status, code, title, detail, remediation, retryable)


def _unavailable_repository(_path: Path, _project_id: str) -> PrivacyPolicyRepository:
    raise _problem(
        status=500,
        code="RO-CORE-PRIVACY-POLICY-UNAVAILABLE",
        title="Privacy policy is unavailable",
        detail="The project privacy persistence adapter is not composed in this runtime.",
        remediation="Keep the project local-only and use the packaged Core runtime.",
    )


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _disclosure() -> DeletionDisclosure:
    return DeletionDisclosure(
        disclosure_version="secure-deletion-disclosure-v1",
        scope="project-cache-only",
        logical_removal=True,
        physical_erasure_guaranteed=False,
        canonical_project_data_excluded=True,
        limitations=_DELETION_LIMITATIONS,
    )


def _projection(project_id: str, revision: int, values: dict[str, str | int]) -> PrivacyPolicyProjection:
    network = PrivacyNetworkPolicy(str(values["privacy.network-policy"]))
    consent_recorded = values["privacy.egress-consent-version"] == _CONSENT_VERSION
    enforcement = (
        EgressEnforcement.REQUIRE_TASK_PREVIEW
        if network is PrivacyNetworkPolicy.APPROVED_PROVIDERS and consent_recorded
        else EgressEnforcement.DENY
    )
    return PrivacyPolicyProjection(
        project_id=project_id,
        revision=revision,
        defaults_applied=revision == 0,
        network_policy=network,
        remote_model_approval=RemoteModelApproval(str(values["privacy.remote-model-approval"])),
        telemetry_mode=TelemetryMode(str(values["privacy.telemetry-mode"])),
        log_retention_days=int(values["privacy.log-retention-days"]),
        document_retention=DocumentRetentionPolicy(str(values["privacy.document-retention"])),
        cache_retention_days=int(values["privacy.cache-retention-days"]),
        egress_consent_recorded=consent_recorded,
        egress_enforcement=enforcement,
        deletion_disclosure=_disclosure(),
    )


def _read_policy(repository: PrivacyPolicyRepository, project_id: str) -> PrivacyPolicyProjection:
    try:
        record = repository.read()
    except RepositoryProblem as error:
        raise _problem(
            status=500,
            code="RO-CORE-PRIVACY-POLICY-UNAVAILABLE",
            title="Privacy policy is unavailable",
            detail="The project privacy policy could not be read from canonical local state.",
            remediation="Keep the project local-only and run project health checks before retrying.",
            retryable=True,
        ) from error
    if record is None:
        return _projection(project_id, 0, dict(_DEFAULTS))
    if len(record.settings) != len(_SETTING_KEYS) or tuple(setting.key for setting in record.settings) != _SETTING_KEYS:
        raise _problem(
            status=500,
            code="RO-CORE-PRIVACY-POLICY-INCOMPLETE",
            title="Privacy policy is incomplete",
            detail="The latest project privacy revision does not contain every governed setting.",
            remediation="Keep the project local-only and restore or repair a verified working copy.",
        )
    values = {setting.key: setting.value for setting in record.settings}
    try:
        return _projection(project_id, record.revision, values)
    except (TypeError, ValueError) as error:
        raise _problem(
            status=500,
            code="RO-CORE-PRIVACY-POLICY-INCOMPLETE",
            title="Privacy policy is incomplete",
            detail="The latest project privacy revision contains an unsupported value.",
            remediation="Keep the project local-only and restore or repair a verified working copy.",
        ) from error


def _policy_values(command: PrivacyPolicyUpdateRequest) -> dict[str, str | int]:
    return {
        "privacy.cache-retention-days": command.cache_retention_days,
        "privacy.document-retention": command.document_retention.value,
        "privacy.egress-consent-version": (
            "none" if command.network_policy is PrivacyNetworkPolicy.OFFLINE else _CONSENT_VERSION
        ),
        "privacy.log-retention-days": command.log_retention_days,
        "privacy.network-policy": command.network_policy.value,
        "privacy.remote-model-approval": command.remote_model_approval.value,
        "privacy.telemetry-mode": command.telemetry_mode.value,
    }


def _policy_record_sha256(project_id: str, revision: int, values: dict[str, str | int]) -> str:
    payload = json.dumps(
        {"projectId": project_id, "revision": revision, "settings": values},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_policy(
    repository: PrivacyPolicyRepository,
    project_id: str,
    command: PrivacyPolicyUpdateRequest,
    trace_id: str,
) -> PrivacyPolicyProjection:
    current = _read_policy(repository, project_id)
    if command.expected_revision != current.revision:
        raise _problem(
            status=409,
            code="RO-CORE-PRIVACY-REVISION-CONFLICT",
            title="Privacy settings changed",
            detail="The submitted settings were based on an older project privacy revision.",
            remediation="Reload the current privacy settings, review every disclosure, and submit again.",
        )
    if command.network_policy is not PrivacyNetworkPolicy.OFFLINE and command.egress_consent_token != _CONSENT_TOKEN:
        raise _problem(
            status=422,
            code="RO-CORE-PRIVACY-CONSENT-REQUIRED",
            title="Informed egress consent is required",
            detail="A non-offline network policy requires the exact current egress disclosure acknowledgement.",
            remediation="Review the will-send/will-not-send boundary and explicitly acknowledge it.",
        )
    values = _policy_values(command)
    next_revision = current.revision + 1
    if next_revision > _MAX_SAFE_INTEGER:
        raise _problem(
            status=409,
            code="RO-CORE-PRIVACY-REVISION-EXHAUSTED",
            title="Privacy settings cannot advance",
            detail="The project privacy revision range is exhausted.",
            remediation="Preserve the project and use the reviewed recovery workflow.",
        )
    now = _timestamp()
    record_sha256 = _policy_record_sha256(project_id, next_revision, values)
    try:
        repository.append(
            expected_revision=current.revision,
            revision=next_revision,
            settings=tuple(PrivacySetting(key=key, value=values[key]) for key in _SETTING_KEYS),
            event=PrivacyAuditEvent(
                event_id=new_uuid_v7(),
                event_type="privacy.policy.changed",
                occurred_at=now,
                trace_id=trace_id,
                record_sha256=record_sha256,
            ),
        )
    except RepositoryConflict as error:
        raise _problem(
            status=409,
            code="RO-CORE-PRIVACY-REVISION-CONFLICT",
            title="Privacy settings changed",
            detail="Another local request committed a newer privacy revision first.",
            remediation="Reload the current privacy settings and submit again.",
        ) from error
    except RepositoryProblem as error:
        raise _problem(
            status=500,
            code="RO-CORE-PRIVACY-WRITE-FAILED",
            title="Privacy settings were not saved",
            detail="The append-only privacy revision did not commit to canonical local state.",
            remediation="Existing privacy restrictions remain authoritative. Retry after project health checks.",
            retryable=True,
        ) from error
    emit_log_record(
        "privacy.policy.updated",
        level="INFO",
        fields={"reasonCode": "privacy-policy-updated", "traceId": trace_id},
    )
    return _projection(project_id, next_revision, values)


def _reparse(status: os.stat_result) -> bool:
    return bool(getattr(status, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _directory_identity(path: Path) -> tuple[int, int] | None:
    try:
        status = path.stat(follow_symlinks=False)
    except OSError:
        return None
    if not stat.S_ISDIR(status.st_mode) or _reparse(status):
        return None
    return (status.st_dev, status.st_ino)


def _cache_clear_boundary(_name: str) -> None:
    """Deterministic adversarial-test seam at destructive cache boundaries."""


@contextmanager
def _deny_directory_additions(
    path: Path,
    expected_identity: tuple[int, int],
) -> Iterator[Callable[[], None]]:
    """Temporarily deny same-user child insertion while retaining exact ACL restoration."""

    if os.name != "nt":
        yield lambda: None
        return

    import ctypes
    from ctypes import wintypes

    class SidAndAttributes(ctypes.Structure):
        _fields_ = (("sid", ctypes.c_void_p), ("attributes", wintypes.DWORD))

    class TokenUser(ctypes.Structure):
        _fields_ = (("user", SidAndAttributes),)

    class Trustee(ctypes.Structure):
        _fields_ = (
            ("multiple_trustee", ctypes.c_void_p),
            ("multiple_trustee_operation", wintypes.DWORD),
            ("trustee_form", wintypes.DWORD),
            ("trustee_type", wintypes.DWORD),
            ("name", wintypes.LPWSTR),
        )

    class ExplicitAccess(ctypes.Structure):
        _fields_ = (
            ("permissions", wintypes.DWORD),
            ("access_mode", wintypes.DWORD),
            ("inheritance", wintypes.DWORD),
            ("trustee", Trustee),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    open_process_token = advapi32.OpenProcessToken
    open_process_token.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    open_process_token.restype = wintypes.BOOL
    get_token_information = advapi32.GetTokenInformation
    get_token_information.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    get_token_information.restype = wintypes.BOOL
    get_security_info = advapi32.GetSecurityInfo
    get_security_info.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    )
    get_security_info.restype = wintypes.DWORD
    set_entries_in_acl = advapi32.SetEntriesInAclW
    set_entries_in_acl.argtypes = (
        wintypes.ULONG,
        ctypes.POINTER(ExplicitAccess),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    )
    set_entries_in_acl.restype = wintypes.DWORD
    set_security_info = advapi32.SetSecurityInfo
    set_security_info.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )
    set_security_info.restype = wintypes.DWORD
    local_free = kernel32.LocalFree
    local_free.argtypes = (ctypes.c_void_p,)
    local_free.restype = ctypes.c_void_p

    file_read_attributes = 0x00000080
    read_control = 0x00020000
    write_dac = 0x00040000
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    open_existing = 3
    file_flag_open_reparse_point = 0x00200000
    file_flag_backup_semantics = 0x02000000
    invalid_handle = wintypes.HANDLE(-1).value
    dacl_security_information = 0x00000004
    file_add_file = 0x0002
    file_add_subdirectory = 0x0004

    handle = create_file(
        str(path),
        file_read_attributes | read_control | write_dac,
        file_share_read | file_share_write,
        None,
        open_existing,
        file_flag_open_reparse_point | file_flag_backup_semantics,
        None,
    )
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    token = wintypes.HANDLE()
    security_descriptor = ctypes.c_void_p()
    original_acl = ctypes.c_void_p()
    updated_acl = ctypes.c_void_p()
    updated = False
    restore = True
    try:
        if _directory_identity(path) != expected_identity:
            raise OSError("cache directory identity changed before namespace protection")
        if not open_process_token(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        required = wintypes.DWORD()
        get_token_information(token, 1, None, 0, ctypes.byref(required))
        if not required.value:
            raise ctypes.WinError(ctypes.get_last_error())
        token_buffer = ctypes.create_string_buffer(required.value)
        if not get_token_information(token, 1, token_buffer, required, ctypes.byref(required)):
            raise ctypes.WinError(ctypes.get_last_error())
        current_sid = ctypes.cast(token_buffer, ctypes.POINTER(TokenUser)).contents.user.sid
        status = get_security_info(
            handle,
            1,
            dacl_security_information,
            None,
            None,
            ctypes.byref(original_acl),
            None,
            ctypes.byref(security_descriptor),
        )
        if status:
            raise OSError(status, "GetSecurityInfo failed")
        entry = ExplicitAccess(
            file_add_file | file_add_subdirectory,
            3,
            0,
            Trustee(None, 0, 0, 1, ctypes.cast(current_sid, wintypes.LPWSTR)),
        )
        status = set_entries_in_acl(1, ctypes.byref(entry), original_acl, ctypes.byref(updated_acl))
        if status:
            raise OSError(status, "SetEntriesInAclW failed")
        status = set_security_info(handle, 1, dacl_security_information, None, None, updated_acl, None)
        if status:
            raise OSError(status, "SetSecurityInfo failed")
        updated = True
        if _directory_identity(path) != expected_identity:
            raise OSError("cache directory identity changed while namespace protection was installed")

        def preserve() -> None:
            nonlocal restore
            restore = False

        yield preserve
    finally:
        active_error = sys.exc_info()[1]
        restore_error: OSError | None = None
        if updated and restore:
            status = set_security_info(handle, 1, dacl_security_information, None, None, original_acl, None)
            if status:
                restore_error = OSError(status, "cache directory ACL restoration failed")
        if updated_acl.value:
            local_free(updated_acl)
        if security_descriptor.value:
            local_free(security_descriptor)
        if token.value:
            close_handle(token)
        close_handle(handle)
        if restore_error is not None:
            if active_error is not None:
                raise restore_error from active_error
            raise restore_error


@contextmanager
def _protect_cache_tree(cache: Path, inventory: _CacheInventory) -> Iterator[_CacheTreeProtection]:
    with ExitStack() as stack:
        preserve_callbacks: list[Callable[[], None]] = []
        for relative, identity in sorted(
            inventory.directories,
            key=lambda item: (len(Path(item[0]).parts), item[0]),
        ):
            preserve_callbacks.append(stack.enter_context(_deny_directory_additions(cache / relative, identity)))
        if _inventory(cache) != inventory:
            raise OSError("cache tree changed while namespace protection was installed")
        yield _CacheTreeProtection(preserve_callbacks)


def _inventory(cache: Path) -> _CacheInventory:
    try:
        root_status = cache.stat(follow_symlinks=False)
        if not stat.S_ISDIR(root_status.st_mode) or _reparse(root_status):
            raise OSError("cache root is redirected")
        root_identity = (root_status.st_dev, root_status.st_ino)
        digest = hashlib.sha256()
        items = 0
        byte_count = 0
        directories = [("", root_identity)]
        stack = [cache]
        while stack:
            directory = stack.pop()
            with os.scandir(directory) as entries:
                ordered = sorted(entries, key=lambda entry: entry.name)
            for entry in ordered:
                status = entry.stat(follow_symlinks=False)
                relative = Path(entry.path).relative_to(cache).as_posix()
                kind = (
                    "redirect"
                    if _reparse(status) or stat.S_ISLNK(status.st_mode)
                    else ("directory" if stat.S_ISDIR(status.st_mode) else "file")
                )
                if kind == "directory":
                    directories.append((relative, (status.st_dev, status.st_ino)))
                    stack.append(Path(entry.path))
                else:
                    items += 1
                    if items > _MAX_CACHE_ITEMS:
                        raise OSError("cache inventory exceeds bound")
                    if kind == "file":
                        byte_count += int(status.st_size)
                        if byte_count > _MAX_SAFE_INTEGER:
                            raise OSError("cache byte count exceeds bound")
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                digest.update(kind.encode("ascii"))
                digest.update(b"\0")
                digest.update(str(status.st_size).encode("ascii"))
                digest.update(b"\0")
                digest.update(str(status.st_mtime_ns).encode("ascii"))
                digest.update(b"\n")
        ordered_directories = tuple(sorted(directories, key=lambda item: item[0]))
        if any(_directory_identity(cache / relative) != identity for relative, identity in ordered_directories):
            raise OSError("cache directory identity changed during inventory")
        return _CacheInventory(root_identity, digest.hexdigest(), items, byte_count, ordered_directories)
    except (OSError, UnicodeError, ValueError) as error:
        raise _problem(
            status=409,
            code="RO-CORE-CACHE-INVENTORY-FAILED",
            title="Cache cleanup cannot be previewed",
            detail="The project cache could not be inventoried without following an unsafe or changing path.",
            remediation="Close other local tools, repair cache path redirects, and preview again.",
        ) from error


def _remove_tree_no_follow(
    path: Path,
    *,
    expected_root_identity: tuple[int, int] | None = None,
    remove_root: bool = True,
) -> None:
    status = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(status.st_mode) or _reparse(status):
        raise OSError("cleanup root is redirected")
    if expected_root_identity is not None and (status.st_dev, status.st_ino) != expected_root_identity:
        raise OSError("cleanup root identity changed")
    with os.scandir(path) as entries:
        ordered = list(entries)
    for entry in ordered:
        candidate = Path(entry.path)
        child = entry.stat(follow_symlinks=False)
        if stat.S_ISDIR(child.st_mode) and not _reparse(child):
            _remove_tree_no_follow(candidate)
        elif stat.S_ISDIR(child.st_mode):
            candidate.rmdir()
        else:
            candidate.unlink()
    if remove_root:
        path.rmdir()


class ProjectPrivacyObjectAccessPolicy(ObjectAccessPolicy):
    """Translate one project policy into the object-store tri-state handoff."""

    def __init__(self, service: ProjectPrivacyService, root: str) -> None:
        self._service = service
        self._root = root

    def authorize(self, request: ObjectAccessRequest) -> ObjectAccessDecision:
        try:
            policy = self._service.get(self._root)
        except Exception:
            return ObjectAccessDecision("deny", "privacy-policy-unavailable")
        if request.project_id != policy.project_id:
            return ObjectAccessDecision("deny", "privacy-project-mismatch")
        if request.access_class == "local-read":
            return ObjectAccessDecision("allow", "privacy-local-read")
        if policy.network_policy is PrivacyNetworkPolicy.APPROVED_PROVIDERS:
            return ObjectAccessDecision("require-confirmation", "privacy-egress-preview-required")
        if policy.network_policy is PrivacyNetworkPolicy.METADATA_ONLY:
            return ObjectAccessDecision("deny", "privacy-metadata-only")
        return ObjectAccessDecision("deny", "privacy-offline")


class ProjectPrivacyService:
    """Own append-only project policy and cache-clearing preview/commit state."""

    def __init__(self, projects: ProjectLifecycleService, repository_factory: _PrivacyRepositoryFactory) -> None:
        if not isinstance(projects, ProjectLifecycleService):
            raise TypeError("project lifecycle authority is required")
        if not callable(repository_factory):
            raise TypeError("privacy repository factory is required")
        self._projects = projects
        self._repository_factory = repository_factory
        self._previews: dict[str, _PendingCachePreview] = {}
        self._mutex = threading.RLock()

    @classmethod
    def unavailable(cls, projects: ProjectLifecycleService) -> ProjectPrivacyService:
        """Build the fail-closed test/composition fallback without a data adapter."""

        return cls(projects, _unavailable_repository)

    def _repository(self, path: Path, project_id: str) -> PrivacyPolicyRepository:
        repository = self._repository_factory(path, project_id)
        if not isinstance(repository, PrivacyPolicyRepository):
            raise _problem(
                status=500,
                code="RO-CORE-PRIVACY-POLICY-UNAVAILABLE",
                title="Privacy policy is unavailable",
                detail="The project privacy persistence adapter is invalid.",
                remediation="Keep the project local-only and repair the packaged Core runtime.",
            )
        return repository

    def get(self, root: str) -> PrivacyPolicyProjection:
        return self._projects.perform_open_project_action(
            root=root,
            require_write=False,
            action=lambda path, project_id: _read_policy(self._repository(path, project_id), project_id),
        )

    def update(self, command: PrivacyPolicyUpdateRequest, *, trace_id: str) -> PrivacyPolicyProjection:
        return self._projects.perform_open_project_action(
            root=command.root,
            require_write=True,
            action=lambda path, project_id: _write_policy(
                self._repository(path, project_id), project_id, command, trace_id
            ),
        )

    def object_access_policy(self, root: str) -> ProjectPrivacyObjectAccessPolicy:
        return ProjectPrivacyObjectAccessPolicy(self, root)

    def preview_cache(self, root: str) -> CacheClearPreview:
        return self._projects.perform_open_project_action(
            root=root,
            require_write=False,
            action=self._preview_cache,
        )

    def _preview_cache(self, path: Path, project_id: str) -> CacheClearPreview:
        policy = _read_policy(self._repository(path, project_id), project_id)
        inventory = _inventory(path / "cache")
        token = secrets.token_hex(16)
        expires_at = datetime.now(UTC) + timedelta(seconds=_PREVIEW_LIFETIME_SECONDS)
        with self._mutex:
            self._previews = {
                key: preview for key, preview in self._previews.items() if preview.expires_monotonic > time.monotonic()
            }
            self._previews[token] = _PendingCachePreview(
                project_id=project_id,
                root=path,
                policy_revision=policy.revision,
                inventory=inventory,
                expires_monotonic=time.monotonic() + _PREVIEW_LIFETIME_SECONDS,
                expires_at=expires_at,
            )
        return CacheClearPreview(
            project_id=project_id,
            policy_revision=policy.revision,
            preview_token=token,
            confirmation=f"clear-cache:{token}",
            expires_at=expires_at,
            item_count=inventory.item_count,
            byte_count=inventory.byte_count,
            deletion_disclosure=_disclosure(),
        )

    def clear_cache(self, command: CacheClearRequest, *, trace_id: str) -> CacheClearResult:
        return self._projects.perform_open_project_action(
            root=command.root,
            require_write=True,
            action=lambda path, project_id: self._clear_cache(path, project_id, command, trace_id),
        )

    def _clear_cache(
        self,
        path: Path,
        project_id: str,
        command: CacheClearRequest,
        trace_id: str,
    ) -> CacheClearResult:
        with self._mutex:
            preview = self._previews.get(command.preview_token)
        if (
            preview is None
            or preview.expires_monotonic <= time.monotonic()
            or preview.project_id != project_id
            or preview.root != path
            or command.confirmation != f"clear-cache:{command.preview_token}"
        ):
            raise _problem(
                status=409,
                code="RO-CORE-CACHE-PREVIEW-STALE",
                title="Cache cleanup preview is stale",
                detail="Cache clearing requires the exact current project-specific preview and confirmation.",
                remediation="Preview the cache again, review the deletion limitations, and reconfirm.",
            )
        cache = path / "cache"
        temporary = path / ".tmp"
        tombstone = temporary / f"{_CACHE_TOMBSTONE_PREFIX}{command.preview_token}"
        if tombstone.exists() or tombstone.is_symlink():
            raise _problem(
                status=409,
                code="RO-CORE-CACHE-CLEANUP-CONFLICT",
                title="Cache cleanup cannot start",
                detail="A cache cleanup staging identity already exists.",
                remediation="Run project health recovery before retrying cache cleanup.",
            )
        repository = self._repository(path, project_id)
        policy = _read_policy(repository, project_id)
        cleanup_pending = False
        try:
            with _stable_directories([path, temporary]):
                with _held_directory_renamer(cache) as rename_cache:
                    inventory = _inventory(cache)
                    if policy.revision != preview.policy_revision or inventory != preview.inventory:
                        with self._mutex:
                            self._previews.pop(command.preview_token, None)
                        raise _problem(
                            status=409,
                            code="RO-CORE-CACHE-PREVIEW-STALE",
                            title="Cache cleanup preview is stale",
                            detail="The project policy or cache inventory changed after the preview.",
                            remediation="Preview the cache again and review the updated scope before clearing.",
                        )
                    with _protect_cache_tree(cache, inventory) as tree_protection:
                        _cache_clear_boundary("before-held-cache-rename")
                        rename_cache(tombstone)
                        replacement_identity: tuple[int, int] | None = None
                        try:
                            _cache_clear_boundary("after-held-cache-rename")
                            if _directory_identity(tombstone) != inventory.root_identity:
                                raise OSError("staged cache identity does not match the confirmed inventory")
                            if _inventory(tombstone) != inventory:
                                raise OSError("staged cache contents changed before deletion")
                            cache.mkdir(mode=0o700)
                            replacement_identity = _directory_identity(cache)
                            if replacement_identity is None:
                                raise OSError("replacement cache identity is invalid")
                            _cache_clear_boundary("after-staged-cache-validation")
                            now = _timestamp()
                            record_sha256 = hashlib.sha256(
                                json.dumps(
                                    {
                                        "byteCount": inventory.byte_count,
                                        "fingerprint": inventory.fingerprint,
                                        "itemCount": inventory.item_count,
                                        "projectId": project_id,
                                        "scope": "project-cache-only",
                                    },
                                    sort_keys=True,
                                    separators=(",", ":"),
                                ).encode("utf-8")
                            ).hexdigest()
                            repository.append_event(
                                PrivacyAuditEvent(
                                    event_id=new_uuid_v7(),
                                    event_type="privacy.cache.cleared",
                                    occurred_at=now,
                                    trace_id=trace_id,
                                    record_sha256=record_sha256,
                                )
                            )
                        except BaseException as error:
                            if replacement_identity is not None:
                                if _directory_identity(cache) != replacement_identity:
                                    raise OSError("replacement cache changed before rollback") from error
                                cache.rmdir()
                            if _directory_identity(tombstone) != inventory.root_identity:
                                raise OSError("staged cache changed before rollback") from error
                            rename_cache(cache)
                            raise
                        try:
                            _cache_clear_boundary("after-cache-audit-before-cleanup")
                        except OSError:
                            cleanup_pending = True
                        tree_protection.preserve_for_cleanup()
                    if not cleanup_pending:
                        try:
                            _remove_tree_no_follow(
                                tombstone,
                                expected_root_identity=inventory.root_identity,
                                remove_root=False,
                            )
                        except OSError:
                            cleanup_pending = True
                if not cleanup_pending:
                    try:
                        if _directory_identity(tombstone) != inventory.root_identity:
                            raise OSError("empty cleanup root identity changed")
                        tombstone.rmdir()
                    except OSError:
                        cleanup_pending = True
        except PrivacyPolicyProblem:
            raise
        except (OSError, RepositoryProblem, TypeError, ValueError) as error:
            raise _problem(
                status=500,
                code="RO-CORE-CACHE-CLEAR-FAILED",
                title="Cache was not cleared",
                detail="The cache cleanup commit failed and the prior cache was retained when rollback was possible.",
                remediation="Run project health checks and preview the cache again.",
                retryable=True,
            ) from error
        with self._mutex:
            self._previews.pop(command.preview_token, None)
        state = CacheClearState.CLEARED_CLEANUP_PENDING if cleanup_pending else CacheClearState.CLEARED
        emit_log_record(
            "privacy.cache.cleared",
            level="INFO",
            fields={"reasonCode": state.value, "traceId": trace_id},
        )
        return CacheClearResult(
            project_id=project_id,
            state=state,
            item_count=inventory.item_count,
            byte_count=inventory.byte_count,
            cleanup_pending=cleanup_pending,
            deletion_disclosure=_disclosure(),
        )


__all__ = ["PrivacyPolicyProblem", "ProjectPrivacyObjectAccessPolicy", "ProjectPrivacyService"]
