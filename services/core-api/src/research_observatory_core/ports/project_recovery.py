"""Dependency-neutral, private authority for explicit project recovery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from .object_store_keys import ObjectMasterKeyProvider


class RecoveryVerificationProblem(RuntimeError):
    """Content-free failure; a working copy must not be published."""

    def __init__(self, reason_code: str) -> None:
        super().__init__("recovery-copy verification failed")
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class RecoveryLocalReadAuthority:
    """Internal handoff from the existing validated staging privacy parser.

    No caller-supplied HTTP field or default policy creates this authority.
    Network modes all permit local read; object rights are checked separately.
    """

    project_id: str
    policy_revision: int
    network_policy: Literal["offline", "metadata-only", "approved-providers"]


@dataclass(frozen=True, slots=True)
class RecoveryCopyVerificationRequest:
    """Only a private owned staging copy may be supplied by the coordinator."""

    root: Path
    project_id: str
    local_read: RecoveryLocalReadAuthority
    key_provider: ObjectMasterKeyProvider | None
    cancellation_requested: Callable[[], bool]


@dataclass(frozen=True, slots=True)
class RecoveryCopyVerifiedFacts:
    """Private verification result; hashes are not renderer projections."""

    canonical_fact_sha256: str
    canonical_row_count: int
    available_object_count: int
    deleted_object_count: int
    authenticated_plaintext_byte_count: int


@dataclass(frozen=True, slots=True)
class RecoveryProcessIdentity:
    process_id: int
    creation_filetime: str
    executable_identity: str


@dataclass(frozen=True, slots=True)
class RecoveryNativeSession:
    principal_reference: str
    launch_session: str
    native: RecoveryProcessIdentity
    core: RecoveryProcessIdentity


@dataclass(frozen=True, slots=True)
class RecoveryOwnershipWitness:
    schema_version: Literal["1.0"]
    purpose: Literal["project-session-recovery"]
    witness_id: str
    project_id: str
    canonical_root: str
    root_file_identity: str
    core_instance_id: str
    recovery_token_sha256: str
    initial_heartbeat: str
    manifest_sha256: str
    native_session: RecoveryNativeSession
    disposition: Literal["created", "opened", "closed"]
    audit_byte_count: int
    audit_sha256: str


@runtime_checkable
class RecoveryExclusion(Protocol):
    """Owned cross-process handle; availability is not permission to recover."""

    def validate(self) -> None: ...
    def close(self) -> None: ...


@runtime_checkable
class RecoveryWitnessStore(Protocol):
    def acquire_project(self, project_id: str) -> RecoveryExclusion: ...
    def issue(self, witness: RecoveryOwnershipWitness) -> None: ...
    def read(
        self,
        project_id: str,
        core_instance_id: str,
        disposition: str,
        *,
        token_sha256: str,
    ) -> RecoveryOwnershipWitness: ...
    def check_nonterminal(self, project_id: str, core_instance_id: str, *, token_sha256: str) -> None: ...


@dataclass(frozen=True, slots=True)
class RecoveryNativeInspection:
    launch_session: str
    principal_reference: str
    native_owner_state: Literal["dead", "live", "pid-reused", "unknown"]
    core_owner_state: Literal["dead", "live", "pid-reused", "unknown"]
    source_file_identity: str
    destination_parent_identity: str


@runtime_checkable
class RecoveryNativeAuthority(Protocol):
    """Only the owned inherited Native control channel implements this port."""

    def current_session(self) -> RecoveryNativeSession: ...
    def inspect(
        self, witness: RecoveryOwnershipWitness, source: Path, destination: Path
    ) -> RecoveryNativeInspection: ...
