"""Local project package lifecycle authority.

The project package is authoritative.  This module deliberately avoids the
SQLite repository owned by CAP-02.S02 and operates only on the versioned
manifest, classified directories, profile document, lock, and audit seam.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import threading
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import ProjectLifecycleState, ProjectProjection

_DIRECTORY_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_TEMPLATE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
_PROJECT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$")
_RELEASE_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_MANIFEST_KEYS = {
    "schemaVersion",
    "documentType",
    "projectId",
    "projectRevision",
    "packageFormatVersion",
    "layoutVersion",
    "lifecycleState",
    "applicationCompatibility",
    "databaseProfile",
    "objectFormat",
    "createdAt",
    "modifiedAt",
}
_PROFILE_KEYS = {"schemaVersion", "documentType", "displayName", "templateId"}
_PROJECT_DIRECTORIES = ("state", "objects", "indexes", "cache", "models", "config", "exports", "logs", ".locks", ".tmp")
_IMPLEMENTED_TEMPLATES = {"theory-synthesis"}
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _redirect(path: Path) -> bool:
    try:
        return path.is_symlink() or path.is_junction()
    except OSError as error:
        raise ProjectLifecycleProblem(
            status=422,
            code="RO-CORE-PROJECT-PATH-INVALID",
            title="Project path cannot be inspected",
            detail="The selected local path could not be verified without following a redirect.",
            remediation="Choose a present local directory that is not a symbolic link or junction.",
        ) from error


def _canonical_directory(value: str) -> Path:
    if not value or len(value) > 4096 or "\x00" in value:
        raise ProjectLifecycleProblem.invalid_path()
    path = Path(value)
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise ProjectLifecycleProblem.invalid_path()
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if _redirect(current):
            raise ProjectLifecycleProblem.invalid_path()
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ProjectLifecycleProblem(
            status=404,
            code="RO-CORE-PROJECT-NOT-FOUND",
            title="Project location was not found",
            detail="The selected local project directory is unavailable.",
            remediation="Locate the project directory or choose another local location.",
        ) from error
    if resolved != path or not path.is_dir() or _redirect(path):
        raise ProjectLifecycleProblem.invalid_path()
    return path


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise ProjectLifecycleProblem(
            status=500,
            code="RO-CORE-PROJECT-WRITE-FAILED",
            title="Project update could not be published",
            detail="The local project remained unchanged or recoverable after a filesystem write failed.",
            remediation="Check local storage availability and retry once.",
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def _release_version(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, str) or not (match := _RELEASE_VERSION.fullmatch(value)):
        return None
    version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return version if all(part <= _MAX_SAFE_INTEGER for part in version) else None


def _utc_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not _UTC_TIMESTAMP.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(slots=True)
class ProjectLifecycleProblem(Exception):
    status: int
    code: str
    title: str
    detail: str
    remediation: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.code

    @classmethod
    def invalid_path(cls) -> ProjectLifecycleProblem:
        return cls(
            status=422,
            code="RO-CORE-PROJECT-PATH-INVALID",
            title="Project path is not allowed",
            detail="Project locations must be absolute, canonical local directories without redirects or traversal.",
            remediation="Choose a direct local directory outside symbolic links and junctions.",
        )


class ProjectLifecycleService:
    """Serialize package lifecycle operations for one supervised Core process."""

    def __init__(self) -> None:
        self._instance_id = str(uuid.uuid4())
        self._opened: set[Path] = set()
        self._mutex = threading.RLock()

    def create(
        self,
        *,
        parent_directory: str,
        directory_name: str,
        display_name: str,
        template_id: str,
        trace_id: str,
    ) -> ProjectProjection:
        parent = _canonical_directory(parent_directory)
        if not _DIRECTORY_NAME.fullmatch(directory_name):
            raise ProjectLifecycleProblem.invalid_path()
        clean_name = display_name.strip()
        if not 1 <= len(clean_name) <= 120 or any(ord(character) < 32 for character in clean_name):
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-NAME-INVALID",
                title="Project name is invalid",
                detail="The project name must contain 1 to 120 visible characters.",
                remediation="Enter a concise project name without control characters.",
            )
        if not _TEMPLATE_ID.fullmatch(template_id) or template_id not in _IMPLEMENTED_TEMPLATES:
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-TEMPLATE-INVALID",
                title="Project template is invalid",
                detail="The selected project template is not a canonical local template identifier.",
                remediation="Choose an implemented project template.",
            )
        target = parent / directory_name
        if target.exists() or _redirect(target):
            raise ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-ALREADY-EXISTS",
                title="Project location already exists",
                detail="Creation will not replace an existing filesystem entry.",
                remediation="Choose another directory name or open the existing project.",
            )
        project_id = str(uuid.uuid4())
        now = _timestamp()
        staging = parent / f".{directory_name}.ro-staging-{secrets.token_hex(8)}"
        try:
            staging.mkdir(mode=0o700)
            for relative in _PROJECT_DIRECTORIES:
                (staging / relative).mkdir(mode=0o700)
            manifest = {
                "schemaVersion": "1.0",
                "documentType": "research-observatory-project-manifest",
                "projectId": project_id,
                "projectRevision": 0,
                "packageFormatVersion": "1.0.0",
                "layoutVersion": "1.0",
                "lifecycleState": "active",
                "applicationCompatibility": {"minimum": "0.1.0", "maximumExclusive": "1.0.0"},
                "databaseProfile": "sqlite-wal-v1",
                "objectFormat": "encrypted-content-addressed-v1",
                "createdAt": now,
                "modifiedAt": now,
            }
            profile = {
                "schemaVersion": "1.0",
                "documentType": "research-observatory-project-profile",
                "displayName": clean_name,
                "templateId": template_id,
            }
            _atomic_json(staging / "project.ro.json", manifest)
            _atomic_json(staging / "config" / "project-profile.json", profile)
            self._audit(staging, "project.created", "active", trace_id)
            os.rename(staging, target)
        except ProjectLifecycleProblem:
            self._remove_staging(staging)
            raise
        except OSError as error:
            self._remove_staging(staging)
            raise ProjectLifecycleProblem(
                status=500,
                code="RO-CORE-PROJECT-CREATE-FAILED",
                title="Project creation did not complete",
                detail="Creation stopped before the staged project was published.",
                remediation="Remove any named staging directory after inspection, then retry.",
                retryable=True,
            ) from error
        return self._projection(target, manifest=manifest, profile=profile)

    def shutdown(self) -> None:
        """Release only locks owned by this supervised Core instance."""

        with self._mutex:
            for path in tuple(self._opened):
                lock = path / ".locks" / "session.lock"
                try:
                    record = json.loads(lock.read_text(encoding="utf-8"))
                    if isinstance(record, dict) and record.get("instanceId") == self._instance_id:
                        lock.unlink()
                except OSError, UnicodeError, json.JSONDecodeError:
                    continue
                finally:
                    self._opened.discard(path)

    def open(self, *, root: str, trace_id: str) -> ProjectProjection:
        with self._mutex:
            path = _canonical_directory(root)
            self._validate_layout(path)
            manifest, profile = self._documents(path)
            if manifest["lifecycleState"] != "active":
                raise ProjectLifecycleProblem(
                    status=409,
                    code="RO-CORE-PROJECT-NOT-ACTIVE",
                    title="Project is not active",
                    detail="Archived or trashed projects cannot open for mutation.",
                    remediation="Restore an archived project before opening it.",
                )
            lock = path / ".locks" / "session.lock"
            if path in self._opened or lock.exists() or _redirect(lock):
                raise ProjectLifecycleProblem(
                    status=409,
                    code="RO-CORE-PROJECT-ALREADY-OPEN",
                    title="Project is already open",
                    detail="A concurrent local open was detected and no project bytes were changed.",
                    remediation="Return to the existing project window or close its verified session first.",
                )
            record = {
                "schemaVersion": "1.0",
                "documentType": "research-observatory-project-lock",
                "projectId": manifest["projectId"],
                "instanceId": self._instance_id,
                "processId": os.getpid(),
                "heartbeatAt": _timestamp(),
                "recoveryToken": secrets.token_hex(32),
            }
            try:
                descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                    json.dump(record, stream, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError as error:
                raise ProjectLifecycleProblem(
                    status=409,
                    code="RO-CORE-PROJECT-ALREADY-OPEN",
                    title="Project is already open",
                    detail="A concurrent local open acquired the project lock first.",
                    remediation="Return to the existing project window or close its verified session first.",
                ) from error
            except OSError as error:
                raise ProjectLifecycleProblem(
                    status=500,
                    code="RO-CORE-PROJECT-LOCK-FAILED",
                    title="Project lock could not be acquired",
                    detail="The project was not opened because exclusive access could not be established.",
                    remediation="Check local filesystem permissions and retry.",
                    retryable=True,
                ) from error
            self._opened.add(path)
            self._audit(path, "project.opened", "active", trace_id)
            return self._projection(path, manifest=manifest, profile=profile)

    def close(self, *, root: str, trace_id: str) -> ProjectProjection:
        with self._mutex:
            path = _canonical_directory(root)
            self._validate_layout(path)
            manifest, profile = self._documents(path)
            lock = path / ".locks" / "session.lock"
            if path in self._opened:
                try:
                    record = json.loads(lock.read_text(encoding="utf-8"))
                    if record.get("instanceId") != self._instance_id:
                        raise ProjectLifecycleProblem(
                            status=409,
                            code="RO-CORE-PROJECT-LOCK-CHANGED",
                            title="Project lock identity changed",
                            detail="The lock no longer belongs to this supervised Core instance.",
                            remediation="Do not break the lock; use the safe-open recovery workflow.",
                        )
                    lock.unlink()
                except ProjectLifecycleProblem:
                    raise
                except (OSError, UnicodeError, json.JSONDecodeError) as error:
                    raise ProjectLifecycleProblem(
                        status=500,
                        code="RO-CORE-PROJECT-CLOSE-FAILED",
                        title="Project close did not complete",
                        detail="The verified project lock could not be removed.",
                        remediation="Keep the application open and retry close before using recovery.",
                        retryable=True,
                    ) from error
                self._opened.remove(path)
                self._audit(path, "project.closed", str(manifest["lifecycleState"]), trace_id)
            elif lock.exists() or _redirect(lock):
                raise ProjectLifecycleProblem(
                    status=409,
                    code="RO-CORE-PROJECT-OPEN-ELSEWHERE",
                    title="Project is owned by another session",
                    detail="This Core instance will not remove an unverified project lock.",
                    remediation="Return to the owning session or use the reviewed stale-lock recovery workflow.",
                )
            return self._projection(path, manifest=manifest, profile=profile)

    def archive(self, *, root: str, trace_id: str) -> ProjectProjection:
        return self._transition(
            root=root, expected="active", target="archived", event="project.archived", trace_id=trace_id
        )

    def restore(self, *, root: str, trace_id: str) -> ProjectProjection:
        return self._transition(
            root=root, expected="archived", target="active", event="project.restored", trace_id=trace_id
        )

    def delete(self, *, root: str, confirmation: str, trace_id: str) -> ProjectProjection:
        with self._mutex:
            path = _canonical_directory(root)
            self._validate_layout(path)
            manifest, profile = self._documents(path)
            self._require_closed(path)
            expected = f"delete:{manifest['projectId']}"
            if not secrets.compare_digest(confirmation, expected):
                raise ProjectLifecycleProblem(
                    status=422,
                    code="RO-CORE-PROJECT-DELETE-CONFIRMATION-INVALID",
                    title="Project deletion was not confirmed",
                    detail="Deletion requires the exact project-specific confirmation shown by the application.",
                    remediation="Review the consequences and enter the exact confirmation phrase.",
                )
            trash = path.parent / ".research-observatory-trash"
            if trash.exists():
                if not trash.is_dir() or _redirect(trash):
                    raise ProjectLifecycleProblem.invalid_path()
            else:
                trash.mkdir(mode=0o700)
            trash = _canonical_directory(str(trash))
            original_manifest = manifest
            manifest = self._updated_manifest(manifest, "trash")
            _atomic_json(path / "project.ro.json", manifest)
            self._audit(path, "project.trashed", "trash", trace_id)
            destination = trash / f"{manifest['projectId']}-{secrets.token_hex(6)}"
            try:
                os.rename(path, destination)
            except OSError as error:
                _atomic_json(path / "project.ro.json", original_manifest)
                self._audit(path, "project.trash-rollback", str(original_manifest["lifecycleState"]), trace_id)
                raise ProjectLifecycleProblem(
                    status=500,
                    code="RO-CORE-PROJECT-DELETE-FAILED",
                    title="Project was not moved to recoverable trash",
                    detail="The lifecycle state was rolled back because the recoverable move failed.",
                    remediation="Check local storage permissions and retry.",
                    retryable=True,
                ) from error
            return self._projection(destination, manifest=manifest, profile=profile)

    def _transition(self, *, root: str, expected: str, target: str, event: str, trace_id: str) -> ProjectProjection:
        with self._mutex:
            path = _canonical_directory(root)
            self._validate_layout(path)
            manifest, profile = self._documents(path)
            self._require_closed(path)
            if manifest["lifecycleState"] != expected:
                raise ProjectLifecycleProblem(
                    status=409,
                    code="RO-CORE-PROJECT-STATE-CONFLICT",
                    title="Project lifecycle state changed",
                    detail=f"This action requires a project in the {expected} state.",
                    remediation="Refresh project state before choosing another lifecycle action.",
                    retryable=True,
                )
            original_manifest = manifest
            manifest = self._updated_manifest(original_manifest, target)
            _atomic_json(path / "project.ro.json", manifest)
            try:
                self._audit(path, event, target, trace_id)
            except ProjectLifecycleProblem:
                _atomic_json(path / "project.ro.json", original_manifest)
                raise
            return self._projection(path, manifest=manifest, profile=profile)

    def _require_closed(self, path: Path) -> None:
        lock = path / ".locks" / "session.lock"
        if path in self._opened or lock.exists() or _redirect(lock):
            raise ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-MUST-CLOSE",
                title="Project must be closed first",
                detail="Lifecycle changes are denied while any project lock is present.",
                remediation="Close the verified project session, then retry the lifecycle action.",
            )

    def _documents(self, path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            manifest = json.loads((path / "project.ro.json").read_text(encoding="utf-8"))
            profile = json.loads((path / "config" / "project-profile.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-MANIFEST-INVALID",
                title="Project metadata is invalid",
                detail="The project manifest or profile is unavailable or malformed.",
                remediation="Do not modify the project; use the safe-open repair workflow.",
            ) from error
        compatibility = manifest.get("applicationCompatibility") if isinstance(manifest, dict) else None
        minimum = _release_version(compatibility.get("minimum")) if isinstance(compatibility, dict) else None
        maximum = _release_version(compatibility.get("maximumExclusive")) if isinstance(compatibility, dict) else None
        created = _utc_datetime(manifest.get("createdAt")) if isinstance(manifest, dict) else None
        modified = _utc_datetime(manifest.get("modifiedAt")) if isinstance(manifest, dict) else None
        if (
            not isinstance(manifest, dict)
            or set(manifest) != _MANIFEST_KEYS
            or manifest.get("schemaVersion") != "1.0"
            or manifest.get("documentType") != "research-observatory-project-manifest"
            or not isinstance(manifest.get("projectId"), str)
            or not _PROJECT_ID.fullmatch(str(manifest["projectId"]))
            or manifest.get("lifecycleState") not in {"active", "archived", "trash"}
            or not isinstance(manifest.get("projectRevision"), int)
            or isinstance(manifest.get("projectRevision"), bool)
            or not 0 <= manifest.get("projectRevision", -1) <= _MAX_SAFE_INTEGER
            or manifest.get("packageFormatVersion") != "1.0.0"
            or manifest.get("layoutVersion") != "1.0"
            or manifest.get("databaseProfile") != "sqlite-wal-v1"
            or manifest.get("objectFormat") != "encrypted-content-addressed-v1"
            or not isinstance(compatibility, dict)
            or set(compatibility) != {"minimum", "maximumExclusive"}
            or minimum is None
            or maximum is None
            or minimum >= maximum
            or created is None
            or modified is None
            or created > modified
        ):
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-MANIFEST-INVALID",
                title="Project manifest is invalid",
                detail="The project root does not match the implemented versioned manifest contract.",
                remediation="Do not modify the project; use the safe-open repair workflow.",
            )
        if (
            not isinstance(profile, dict)
            or set(profile) != _PROFILE_KEYS
            or profile.get("schemaVersion") != "1.0"
            or profile.get("documentType") != "research-observatory-project-profile"
            or not isinstance(profile.get("displayName"), str)
            or not 1 <= len(profile["displayName"]) <= 120
            or any(ord(character) < 32 or ord(character) == 127 for character in profile["displayName"])
            or not isinstance(profile.get("templateId"), str)
            or not _TEMPLATE_ID.fullmatch(profile["templateId"])
            or profile["templateId"] not in _IMPLEMENTED_TEMPLATES
        ):
            raise ProjectLifecycleProblem(
                status=422,
                code="RO-CORE-PROJECT-PROFILE-INVALID",
                title="Project profile is invalid",
                detail="The local project profile does not match its exact versioned contract.",
                remediation="Do not modify the project; use the safe-open repair workflow.",
            )
        return manifest, profile

    @staticmethod
    def _validate_layout(path: Path) -> None:
        expected = {*_PROJECT_DIRECTORIES, "project.ro.json"}
        try:
            if {entry.name for entry in path.iterdir()} != expected:
                raise ProjectLifecycleProblem.invalid_path()
            for relative in _PROJECT_DIRECTORIES:
                directory = path / relative
                if _redirect(directory) or not directory.is_dir():
                    raise ProjectLifecycleProblem.invalid_path()
            for document in (path / "project.ro.json", path / "config" / "project-profile.json"):
                if _redirect(document) or not document.is_file():
                    raise ProjectLifecycleProblem.invalid_path()
        except ProjectLifecycleProblem:
            raise
        except OSError as error:
            raise ProjectLifecycleProblem.invalid_path() from error

    def _projection(
        self,
        path: Path,
        *,
        manifest: dict[str, Any] | None = None,
        profile: dict[str, Any] | None = None,
    ) -> ProjectProjection:
        if manifest is None or profile is None:
            manifest, profile = self._documents(path)
        return ProjectProjection(
            project_id=str(manifest["projectId"]),
            display_name=str(profile["displayName"]),
            template_id=str(profile["templateId"]),
            lifecycle_state=ProjectLifecycleState(str(manifest["lifecycleState"])),
            root=str(path),
            open=path in self._opened,
            revision=int(manifest["projectRevision"]),
            delete_confirmation=f"delete:{manifest['projectId']}",
        )

    def _updated_manifest(self, manifest: dict[str, Any], state: str) -> dict[str, Any]:
        if int(manifest["projectRevision"]) >= _MAX_SAFE_INTEGER:
            raise ProjectLifecycleProblem(
                status=409,
                code="RO-CORE-PROJECT-REVISION-EXHAUSTED",
                title="Project revision cannot advance",
                detail="The project reached the maximum supported manifest revision.",
                remediation="Keep the project closed and request a reviewed format migration.",
            )
        return {
            **manifest,
            "projectRevision": int(manifest["projectRevision"]) + 1,
            "lifecycleState": state,
            "modifiedAt": _timestamp(),
        }

    def _audit(self, root: Path, event: str, state: str, trace_id: str) -> None:
        if not _TRACE_ID.fullmatch(trace_id):
            raise ProjectLifecycleProblem(
                status=500,
                code="RO-CORE-PROJECT-AUDIT-FAILED",
                title="Project audit identity is invalid",
                detail="The lifecycle action was denied because its correlation identity was invalid.",
                remediation="Retry through the generated desktop client.",
            )
        record = {
            "schemaVersion": "1.0",
            "event": event,
            "state": state,
            "recordedAt": _timestamp(),
            "traceId": trace_id,
        }
        path = root / "logs" / "project-lifecycle.jsonl"
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise ProjectLifecycleProblem(
                status=500,
                code="RO-CORE-PROJECT-AUDIT-FAILED",
                title="Project audit record could not be written",
                detail="The lifecycle action did not complete without its required local audit record.",
                remediation="Check local storage availability and retry.",
            ) from error

    @staticmethod
    def _remove_staging(staging: Path) -> None:
        if staging.exists() and not _redirect(staging):
            with suppress(OSError):
                shutil.rmtree(staging)
