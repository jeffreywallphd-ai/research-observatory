"""Atomic persistence boundary for selective recalculation workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Protocol, runtime_checkable

from .ports.repositories import (
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    DependencyChange,
    DependencyStaleState,
    MaterialDependency,
)
from .ports.workflow_executor import (
    WorkflowActor,
    WorkflowJobClaim,
    WorkflowJobRecord,
    WorkflowJobSubmission,
)


@dataclass(frozen=True, slots=True)
class RecalculationAuthority:
    """One transactionally coherent view of all inputs to a recalculation plan."""

    target: AggregateRevision
    dependencies: tuple[MaterialDependency, ...]
    causes: tuple[DependencyStaleState, ...]
    changes: tuple[DependencyChange, ...]
    replacements: tuple[AggregateRevision, ...]
    reusable: tuple[AggregateRevision, ...]
    policy_id: str
    policy_version: str
    privacy_policy_revision: int
    policy_sha256: str
    authority_sha256: str


@dataclass(frozen=True, slots=True)
class RecalculationCandidateCommit:
    """Worker authority for atomically committing one workflow output revision."""

    claim: WorkflowJobClaim
    draft: AggregateRevisionDraft
    event: AtomicRepositoryEvent
    expected_current_revision_id: str
    plan_sha256: str
    completed_at: str


@dataclass(frozen=True, slots=True)
class RestoreRevisionCommit:
    """Exact completed human-decision authority for one immutable restoration."""

    prior_adjudicated_revision_id: str
    expected_current_revision_id: str
    new_revision_id: str
    dependency_ids: tuple[str, ...]
    workflow_run_id: str
    human_task_id: str
    decision_id: str
    modified_at: str
    event: AtomicRepositoryEvent


def recalculation_authority_document(authority: RecalculationAuthority) -> dict[str, object]:
    """Return the canonical authority document shared by planning and persistence."""

    return {
        "changes": [asdict(item) for item in authority.changes],
        "causes": [asdict(item) for item in authority.causes],
        "dependencies": [asdict(item) for item in authority.dependencies],
        "replacementRevisions": [asdict(item) for item in authority.replacements],
        "reusedRevisions": [asdict(item) for item in authority.reusable],
        "policy": {
            "policyId": authority.policy_id,
            "policyVersion": authority.policy_version,
            "privacyPolicyRevision": authority.privacy_policy_revision,
            "policySha256": authority.policy_sha256,
        },
        "target": asdict(authority.target),
    }


def recalculation_authority_sha256(authority: RecalculationAuthority) -> str:
    """Hash a coherent authority view without trusting its supplied digest."""

    payload = json.dumps(
        recalculation_authority_document(authority),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@runtime_checkable
class SelectiveRecalculationRepository(Protocol):
    """Atomic adapter used where workflow and canonical revision state must agree."""

    def plan_authority(self, target_revision_id: str) -> RecalculationAuthority: ...

    def enqueue_if_current(
        self,
        authority: RecalculationAuthority,
        submission: WorkflowJobSubmission,
        *,
        actor: WorkflowActor,
    ) -> WorkflowJobRecord: ...

    def commit_candidate(self, command: RecalculationCandidateCommit) -> AggregateRevision: ...

    def restore_revision(self, command: RestoreRevisionCommit) -> AggregateRevision: ...


__all__ = [
    "RecalculationAuthority",
    "RecalculationCandidateCommit",
    "RestoreRevisionCommit",
    "SelectiveRecalculationRepository",
    "recalculation_authority_document",
    "recalculation_authority_sha256",
]
