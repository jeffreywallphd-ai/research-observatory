"""Encrypted, immutable selected connector archives for durable local jobs.

The archive is data, not execution authority. Reopening it re-inspects exact
bytes; callers must separately recheck publisher trust, project grant, job
fence, and policy before dispatch. Candidate tokens are never persisted.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import UTC, datetime

from ..ports.object_store import ObjectPutCommand, ObjectStore, ObjectStoreProblem
from .plugin_package_intake import (
    MAX_ARCHIVE_BYTES,
    InspectedPluginArchive,
    PluginPackageIntakeProblem,
    inspect_plugin_archive,
)

_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OBJECT_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MEDIA_TYPE = "application/vnd.research-observatory.connector-package+zip"


class PluginPackageStoreProblem(ValueError):
    """Content-free failure to persist or reopen an exact selected package."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _expected(value: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise PluginPackageStoreProblem("plugin-package-digest-invalid")
    return value[7:]


def _inspect(raw: bytes, package_sha256: str, manifest_sha256: str) -> InspectedPluginArchive:
    try:
        inspected = inspect_plugin_archive(raw)
    except PluginPackageIntakeProblem:
        raise PluginPackageStoreProblem("plugin-package-content-invalid") from None
    if inspected.package_sha256 != package_sha256 or inspected.manifest_sha256 != manifest_sha256:
        raise PluginPackageStoreProblem("plugin-package-digest-mismatch")
    return inspected


class PluginPackageStore:
    """Store exact selected ZIP bytes only in the project's encrypted ObjectStore."""

    def __init__(self, objects: ObjectStore) -> None:
        self._objects = objects

    def save(self, archive_bytes: bytes, expected_package_sha256: str, expected_manifest_sha256: str) -> str:
        _expected(expected_package_sha256)
        _expected(expected_manifest_sha256)
        if not isinstance(archive_bytes, bytes) or not 0 < len(archive_bytes) <= MAX_ARCHIVE_BYTES:
            raise PluginPackageStoreProblem("plugin-package-size-invalid")
        _inspect(archive_bytes, expected_package_sha256, expected_manifest_sha256)
        digest = hashlib.sha256(archive_bytes).hexdigest()
        try:
            stored = self._objects.put(
                io.BytesIO(archive_bytes),
                ObjectPutCommand(
                    media_type=_MEDIA_TYPE,
                    rights_status="not-applicable",
                    protection_profile="project-encrypted-v1",
                    retention_class="project-lifetime",
                    creation_source="local-import",
                    created_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    expected_sha256=digest,
                ),
            )
        except ObjectStoreProblem:
            raise PluginPackageStoreProblem("plugin-package-store-unavailable") from None
        if (
            stored.object_sha256 != digest
            or stored.byte_length != len(archive_bytes)
            or stored.protection_profile != "project-encrypted-v1"
            or stored.retention_class != "project-lifetime"
            or stored.media_type != _MEDIA_TYPE
            or stored.rights_status != "not-applicable"
        ):
            raise PluginPackageStoreProblem("plugin-package-store-mismatch")
        return digest

    def load(self, archive_object_sha256: str, package_sha256: str, manifest_sha256: str) -> InspectedPluginArchive:
        if not isinstance(archive_object_sha256, str) or _OBJECT_SHA.fullmatch(archive_object_sha256) is None:
            raise PluginPackageStoreProblem("plugin-package-digest-invalid")
        _expected(package_sha256)
        _expected(manifest_sha256)
        try:
            metadata = self._objects.metadata(archive_object_sha256)
            if (
                metadata.object_sha256 != archive_object_sha256
                or metadata.protection_profile != "project-encrypted-v1"
                or metadata.retention_class != "project-lifetime"
                or metadata.media_type != _MEDIA_TYPE
                or metadata.rights_status != "not-applicable"
                or metadata.storage_state != "available"
            ):
                raise PluginPackageStoreProblem("plugin-package-store-mismatch")
            with self._objects.open(archive_object_sha256, purpose="connector-plugin-execution") as source:
                raw = source.read(MAX_ARCHIVE_BYTES + 1)
        except ObjectStoreProblem:
            raise PluginPackageStoreProblem("plugin-package-store-unavailable") from None
        if not 0 < len(raw) <= MAX_ARCHIVE_BYTES or hashlib.sha256(raw).hexdigest() != archive_object_sha256:
            raise PluginPackageStoreProblem("plugin-package-store-mismatch")
        return _inspect(raw, package_sha256, manifest_sha256)
