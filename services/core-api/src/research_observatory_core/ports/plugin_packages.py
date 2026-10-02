"""Exact signed-package pointer independent of its encrypted storage adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PluginPackagePointerProblem(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PluginPackagePointer:
    project_id: str
    package_sha256: str
    manifest_sha256: str
    signature_sha256: str
    archive_object_sha256: str


class PluginPackageRepository(Protocol):
    def read(self, package_sha256: str, manifest_sha256: str, signature_sha256: str) -> PluginPackagePointer | None: ...

    def record(self, pointer: PluginPackagePointer, *, now: str) -> PluginPackagePointer: ...
