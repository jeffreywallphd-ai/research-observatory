"""Canonical project pointer from an exact signed package pair to encrypted bytes.

The object is written first. This immutable-by-policy pointer is committed
before the project grant; an interrupted write may leave only an encrypted
orphan, never an enabled grant referencing missing package bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .domain_contracts import new_uuid_v7
from .storage import StorageProblem, open_canonical_database

_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OBJECT = re.compile(r"[0-9a-f]{64}\Z")


class PluginPackagePointerProblem(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PluginPackagePointer:
    project_id: str
    package_sha256: str
    manifest_sha256: str
    signature_sha256: str
    archive_object_sha256: str


def _validated(pointer: PluginPackagePointer) -> PluginPackagePointer:
    if (
        not isinstance(pointer, PluginPackagePointer)
        or not isinstance(pointer.project_id, str)
        or not isinstance(pointer.package_sha256, str)
        or not isinstance(pointer.manifest_sha256, str)
        or not isinstance(pointer.signature_sha256, str)
        or not isinstance(pointer.archive_object_sha256, str)
        or _SHA.fullmatch(pointer.package_sha256) is None
        or _SHA.fullmatch(pointer.manifest_sha256) is None
        or _SHA.fullmatch(pointer.signature_sha256) is None
        or _OBJECT.fullmatch(pointer.archive_object_sha256) is None
    ):
        raise PluginPackagePointerProblem("plugin-package-pointer-invalid")
    return pointer


def _key(package_sha256: str, manifest_sha256: str) -> str:
    if (
        not isinstance(package_sha256, str)
        or not isinstance(manifest_sha256, str)
        or _SHA.fullmatch(package_sha256) is None
        or _SHA.fullmatch(manifest_sha256) is None
    ):
        raise PluginPackagePointerProblem("plugin-package-digest-invalid")
    digest = hashlib.sha256(
        b"research-observatory-plugin-package-pointer-v1\0"
        + package_sha256.encode("ascii")
        + b"\0"
        + manifest_sha256.encode("ascii")
    ).hexdigest()
    return "plugin.package." + digest


def _encoded(pointer: PluginPackagePointer) -> str:
    value = {
        "schemaVersion": "1.0",
        "projectId": pointer.project_id,
        "packageSha256": pointer.package_sha256,
        "manifestSha256": pointer.manifest_sha256,
        "signatureSha256": pointer.signature_sha256,
        "archiveObjectSha256": pointer.archive_object_sha256,
    }
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _decoded(raw: str, project_id: str) -> PluginPackagePointer:
    try:
        value = json.loads(raw)
        if (
            not isinstance(value, dict)
            or set(value)
            != {
                "schemaVersion",
                "projectId",
                "packageSha256",
                "manifestSha256",
                "signatureSha256",
                "archiveObjectSha256",
            }
            or value["schemaVersion"] != "1.0"
        ):
            raise ValueError
        pointer = _validated(
            PluginPackagePointer(
                value["projectId"],
                value["packageSha256"],
                value["manifestSha256"],
                value["signatureSha256"],
                value["archiveObjectSha256"],
            )
        )
        if pointer.project_id != project_id or _encoded(pointer) != raw:
            raise ValueError
        return pointer
    except ValueError, TypeError, KeyError:
        raise PluginPackagePointerProblem("plugin-package-pointer-corrupt") from None


class SqlitePluginPackageRepository:
    def __init__(self, database: Path, project_id: str) -> None:
        if not isinstance(database, Path) or not database.is_absolute() or not isinstance(project_id, str):
            raise PluginPackagePointerProblem("plugin-package-repository-invalid")
        self._database, self._project_id = database, project_id

    def _read(self, connection, package_sha256: str, manifest_sha256: str) -> PluginPackagePointer | None:
        rows = connection.execute(
            "SELECT revision,value_type,text_value FROM settings WHERE project_id=? AND setting_key=? "
            "ORDER BY revision",
            (self._project_id, _key(package_sha256, manifest_sha256)),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1 or rows[0][0] != 1 or rows[0][1] != "text" or not isinstance(rows[0][2], str):
            raise PluginPackagePointerProblem("plugin-package-pointer-corrupt")
        pointer = _decoded(rows[0][2], self._project_id)
        if (pointer.package_sha256, pointer.manifest_sha256) != (package_sha256, manifest_sha256):
            raise PluginPackagePointerProblem("plugin-package-pointer-corrupt")
        return pointer

    def read(self, package_sha256: str, manifest_sha256: str) -> PluginPackagePointer | None:
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project_id)
            try:
                return self._read(connection, package_sha256, manifest_sha256)
            finally:
                connection.close()
        except PluginPackagePointerProblem:
            raise
        except sqlite3.Error, StorageProblem, OSError:
            raise PluginPackagePointerProblem("plugin-package-pointer-unavailable") from None

    def record(self, pointer: PluginPackagePointer, *, now: str) -> PluginPackagePointer:
        pointer = _validated(pointer)
        if pointer.project_id != self._project_id:
            raise PluginPackagePointerProblem("plugin-package-project-mismatch")
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project_id)
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._read(connection, pointer.package_sha256, pointer.manifest_sha256)
                if current is not None:
                    if current != pointer:
                        raise PluginPackagePointerProblem("plugin-package-identity-conflict")
                    connection.commit()
                    return current
                connection.execute(
                    "INSERT INTO settings (setting_id,project_id,setting_key,revision,value_type,text_value,"
                    "integer_value,real_value,boolean_value,created_at,modified_at) "
                    "VALUES (?, ?, ?, 1, 'text', ?, NULL, NULL, NULL, ?, ?)",
                    (
                        new_uuid_v7(),
                        self._project_id,
                        _key(pointer.package_sha256, pointer.manifest_sha256),
                        _encoded(pointer),
                        now,
                        now,
                    ),
                )
                connection.commit()
                return pointer
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()
        except PluginPackagePointerProblem:
            raise
        except sqlite3.Error, StorageProblem, OSError:
            raise PluginPackagePointerProblem("plugin-package-pointer-unavailable") from None
