"""Dependency-neutral master-key authority consumed by the object-store adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ObjectMasterKey:
    """One versioned 256-bit wrapping key supplied by the later profile vault."""

    key_version: str
    key_bytes: bytes


@runtime_checkable
class ObjectMasterKeyProvider(Protocol):
    """Lookup boundary; implementations must not expose persistence details."""

    def active_object_master_key(self) -> ObjectMasterKey: ...

    def object_master_key(self, key_version: str) -> ObjectMasterKey | None: ...


__all__ = ["ObjectMasterKey", "ObjectMasterKeyProvider"]
