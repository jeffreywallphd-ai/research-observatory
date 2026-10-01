"""Versioned corpus conditions; authority to apply them remains in Core.

Membership follows the frozen v1 corpus-item lifecycle. Pending review,
duplicate relationships, and copy availability are independent facts, so an
included Work can still have an unavailable copy or an open review. These
values are data contracts only: callers must resolve actor, source, Work,
protocol, and evidence authority inside the protected Core transaction.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..ingestion.import_drafts import Digest, DraftValue, Identity, ProjectIdentity

type Membership = Literal["candidate", "included", "excluded", "withdrawn"]
type Review = Literal["none", "pending"]
type Availability = Literal["unknown", "not-applicable", "available", "unavailable"]
type Dimension = Literal["membership", "review", "duplicate", "availability", "discovery", "work-reference"]
type DiscoveryKind = Literal["import-member", "connector-record", "citation", "recommendation", "manual"]

_MEMBERSHIP_TRANSITIONS = frozenset(
    {
        ("candidate", "included"),
        ("candidate", "excluded"),
        ("candidate", "withdrawn"),
        ("included", "candidate"),
        ("included", "withdrawn"),
        ("excluded", "candidate"),
        ("excluded", "withdrawn"),
    }
)
_MEMBERSHIP_COMMANDS = {
    ("candidate", "included"): "include",
    ("candidate", "excluded"): "exclude",
    ("candidate", "withdrawn"): "withdraw",
    ("included", "candidate"): "reconsider",
    ("included", "withdrawn"): "withdraw",
    ("excluded", "candidate"): "reconsider",
    ("excluded", "withdrawn"): "withdraw",
}


class CorpusProblem(RuntimeError):
    """Content-free corpus contract failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _canonical_utc_milliseconds(value: str, code: str) -> None:
    try:
        instant = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(code) from error
    if instant.isoformat(timespec="milliseconds").replace("+00:00", "Z") != value:
        raise ValueError(code)


class DiscoveryPath(DraftValue):
    """Immutable source edge; the repository must re-resolve its protected source."""

    schema_version: Literal["1.0"] = "1.0"
    path_id: Identity
    project_id: ProjectIdentity
    item_id: Identity
    kind: DiscoveryKind
    source_revision_id: Identity
    direction: Literal["source-to-corpus-item"]
    occurred_at: Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")]
    predecessor_item_revision_id: Identity | None
    context_id: Identity
    context_revision_id: Identity
    ordinal: Annotated[int, Field(strict=True, ge=0, le=200000)] | None = None
    record_key_sha256: Digest | None = None
    query_revision_id: Identity | None = None
    citing_work_revision_id: Identity | None = None
    recommendation_revision_id: Identity | None = None
    manual_decision_revision_id: Identity | None = None

    @model_validator(mode="after")
    def exact_source_shape(self) -> Self:
        if (
            self.path_id == self.item_id
            or self.source_revision_id == self.path_id
            or self.predecessor_item_revision_id in {self.item_id, self.path_id}
        ):
            raise ValueError("corpus-discovery-identity-invalid")
        _canonical_utc_milliseconds(self.occurred_at, "corpus-discovery-time-invalid")
        typed = (
            self.query_revision_id,
            self.citing_work_revision_id,
            self.recommendation_revision_id,
            self.manual_decision_revision_id,
        )
        if self.kind == "import-member":
            if self.ordinal is None or self.ordinal < 1 or self.record_key_sha256 is None or any(typed):
                raise ValueError("corpus-import-path-invalid")
        elif self.kind == "connector-record":
            if (
                self.ordinal is None
                or self.ordinal > 999
                or self.record_key_sha256 is not None
                or self.query_revision_id is None
                or any(typed[1:])
            ):
                raise ValueError("corpus-connector-path-invalid")
        else:
            expected = {
                "citation": self.citing_work_revision_id,
                "recommendation": self.recommendation_revision_id,
                "manual": self.manual_decision_revision_id,
            }[self.kind]
            if (
                self.ordinal is not None
                or self.record_key_sha256 is not None
                or expected is None
                or sum(bool(x) for x in typed) != 1
            ):
                raise ValueError("corpus-discovery-path-invalid")
        return self


class CorpusItemRevision(DraftValue):
    """One immutable CorpusItem projection with orthogonal named conditions."""

    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    item_id: Identity
    revision_id: Identity
    previous_revision_id: Identity | None
    work_id: Identity
    work_revision_id: Identity
    membership: Membership
    review: Review
    duplicate_of_item_id: Identity | None
    availability: Availability
    discovery_path_ids: Annotated[tuple[Identity, ...], Field(min_length=1, max_length=1000)]
    decision_revision_id: Identity | None

    @model_validator(mode="after")
    def coherent_revision(self) -> Self:
        if self.item_id in {self.revision_id, self.work_id} or self.previous_revision_id == self.revision_id:
            raise ValueError("corpus-item-identity-invalid")
        if self.duplicate_of_item_id == self.item_id:
            raise ValueError("corpus-duplicate-self-invalid")
        if self.discovery_path_ids != tuple(sorted(set(self.discovery_path_ids))):
            raise ValueError("corpus-discovery-paths-invalid")
        if self.previous_revision_id is None and (
            self.membership != "candidate"
            or self.review != "pending"
            or self.duplicate_of_item_id is not None
            or self.availability != "unknown"
            or self.decision_revision_id is not None
        ):
            raise ValueError("corpus-initial-state-invalid")
        if self.previous_revision_id is not None and self.decision_revision_id is None:
            raise ValueError("corpus-decision-required")
        return self

    @property
    def conditions(self) -> tuple[str, ...]:
        """All named backlog conditions without a lossy exclusive status."""

        conditions: list[str] = [self.membership]
        if self.review == "pending":
            conditions.append("pending")
        if self.duplicate_of_item_id is not None:
            conditions.append("duplicate")
        if self.availability == "unavailable":
            conditions.append("unavailable")
        return tuple(conditions)

    @property
    def discovery_fingerprint(self) -> str:
        """Exact predecessor for a later append-only discovery edge."""

        payload = json.dumps(self.discovery_path_ids, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class CorpusDecision(DraftValue):
    """Exact prior/new fact and authority for one consequential state change."""

    schema_version: Literal["1.0"] = "1.0"
    decision_id: Identity
    project_id: ProjectIdentity
    item_id: Identity
    previous_revision_id: Identity
    next_revision_id: Identity
    dimension: Dimension
    command: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
    previous_value: Annotated[str, Field(min_length=1, max_length=64)]
    next_value: Annotated[str, Field(min_length=1, max_length=64)]
    previous_decision_revision_id: Identity | None
    supersedes_decision_revision_id: Identity | None = None
    next_work_id: Identity | None = None
    actor_id: Identity
    reason_code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
    protocol_revision_id: Identity
    evidence_revision_ids: Annotated[tuple[Identity, ...], Field(min_length=1, max_length=64)]
    occurred_at: Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")]

    @model_validator(mode="after")
    def coherent_decision(self) -> Self:
        if self.previous_revision_id == self.next_revision_id or self.decision_id in {
            self.item_id,
            self.previous_revision_id,
            self.next_revision_id,
        }:
            raise ValueError("corpus-decision-identity-invalid")
        if self.evidence_revision_ids != tuple(sorted(set(self.evidence_revision_ids))):
            raise ValueError("corpus-decision-evidence-invalid")
        if self.previous_value == self.next_value:
            raise ValueError("corpus-decision-no-change")
        if (
            self.previous_decision_revision_id == self.decision_id
            or self.supersedes_decision_revision_id == self.decision_id
        ):
            raise ValueError("corpus-decision-self-supersession")
        if (self.next_work_id is not None) != (self.dimension == "work-reference"):
            raise ValueError("corpus-decision-work-target-invalid")
        _canonical_utc_milliseconds(self.occurred_at, "corpus-decision-time-invalid")
        return self


def apply_decision(current: CorpusItemRevision, decision: CorpusDecision) -> CorpusItemRevision:
    """Validate one transition against a caller-supplied exact current snapshot.

    This pure reducer does not attest actor or evidence authority. The Core
    repository must re-read those facts and commit the decision, revision,
    provenance, outbox, and dependency impacts in one transaction.
    """

    current = CorpusItemRevision.model_validate(current)
    decision = CorpusDecision.model_validate(decision)
    if (current.project_id, current.item_id) != (decision.project_id, decision.item_id):
        raise CorpusProblem("corpus-decision-scope-mismatch")
    if decision.previous_revision_id != current.revision_id:
        raise CorpusProblem("corpus-predecessor-stale")
    if decision.previous_decision_revision_id != current.decision_revision_id:
        raise CorpusProblem("corpus-decision-chain-mismatch")
    if current.membership == "withdrawn":
        raise CorpusProblem("corpus-withdrawn-terminal")
    if decision.dimension in {"discovery", "work-reference"}:
        raise CorpusProblem("corpus-dimension-requires-specific-command")
    field = {
        "membership": "membership",
        "review": "review",
        "duplicate": "duplicate_of_item_id",
        "availability": "availability",
    }[decision.dimension]
    observed = getattr(current, field)
    previous = "none" if observed is None else observed
    if previous != decision.previous_value:
        raise CorpusProblem("corpus-prior-value-mismatch")
    if decision.dimension == "membership":
        if (previous, decision.next_value) not in _MEMBERSHIP_TRANSITIONS:
            raise CorpusProblem("corpus-transition-invalid")
        if decision.command != _MEMBERSHIP_COMMANDS[(previous, decision.next_value)]:
            raise CorpusProblem("corpus-command-invalid")
        next_value: str | None = decision.next_value
    elif decision.dimension == "review":
        if decision.next_value not in {"none", "pending"} or decision.command != (
            "queue-review" if decision.next_value == "pending" else "resolve-review"
        ):
            raise CorpusProblem("corpus-review-invalid")
        next_value = decision.next_value
    elif decision.dimension == "availability":
        if decision.next_value not in {"unknown", "not-applicable", "available", "unavailable"} or decision.command != (
            "mark-" + decision.next_value
        ):
            raise CorpusProblem("corpus-availability-invalid")
        next_value = decision.next_value
    elif decision.dimension == "duplicate":
        if decision.next_value != "none" and not _is_identity(decision.next_value):
            raise CorpusProblem("corpus-duplicate-target-invalid")
        if decision.next_value == current.item_id:
            raise CorpusProblem("corpus-duplicate-self-invalid")
        if decision.command != ("clear-duplicate" if decision.next_value == "none" else "mark-duplicate"):
            raise CorpusProblem("corpus-duplicate-command-invalid")
        next_value = None if decision.next_value == "none" else decision.next_value
    else:
        raise CorpusProblem("corpus-dimension-invalid")
    values = current.model_dump()
    values.update(
        {
            "revision_id": decision.next_revision_id,
            "previous_revision_id": current.revision_id,
            "decision_revision_id": decision.decision_id,
            field: next_value,
        }
    )
    return CorpusItemRevision.model_validate(values)


def append_discovery_path(
    current: CorpusItemRevision, path: DiscoveryPath, decision: CorpusDecision
) -> CorpusItemRevision:
    """Append one immutable edge under a decision bound to the exact prior edge set."""

    current = CorpusItemRevision.model_validate(current)
    path = DiscoveryPath.model_validate(path)
    decision = CorpusDecision.model_validate(decision)
    _require_decision_scope(current, decision)
    if current.membership == "withdrawn":
        raise CorpusProblem("corpus-withdrawn-terminal")
    if (path.project_id, path.item_id) != (current.project_id, current.item_id):
        raise CorpusProblem("corpus-discovery-scope-mismatch")
    if path.predecessor_item_revision_id != current.revision_id:
        raise CorpusProblem("corpus-discovery-item-predecessor-stale")
    if path.occurred_at != decision.occurred_at:
        raise CorpusProblem("corpus-discovery-time-mismatch")
    if decision.dimension != "discovery" or decision.command != "add-discovery":
        raise CorpusProblem("corpus-discovery-command-invalid")
    if decision.previous_value != current.discovery_fingerprint or decision.next_value != path.path_id:
        raise CorpusProblem("corpus-discovery-predecessor-stale")
    if (
        path.path_id in current.discovery_path_ids
        or path.path_id == decision.decision_id
        or path.source_revision_id not in decision.evidence_revision_ids
    ):
        raise CorpusProblem("corpus-discovery-source-invalid")
    return CorpusItemRevision.model_validate(
        current.model_dump()
        | {
            "revision_id": decision.next_revision_id,
            "previous_revision_id": current.revision_id,
            "decision_revision_id": decision.decision_id,
            "discovery_path_ids": tuple(sorted((*current.discovery_path_ids, path.path_id))),
        }
    )


def rebind_work(current: CorpusItemRevision, decision: CorpusDecision) -> CorpusItemRevision:
    """Retarget after a Core-verified Work merge/split without erasing prior identity."""

    current = CorpusItemRevision.model_validate(current)
    decision = CorpusDecision.model_validate(decision)
    _require_decision_scope(current, decision)
    if current.membership == "withdrawn":
        raise CorpusProblem("corpus-withdrawn-terminal")
    if decision.dimension != "work-reference" or decision.command != "rebind-work":
        raise CorpusProblem("corpus-work-command-invalid")
    if decision.previous_value != current.work_revision_id or not _is_identity(decision.next_value):
        raise CorpusProblem("corpus-work-predecessor-stale")
    if decision.next_value not in decision.evidence_revision_ids:
        raise CorpusProblem("corpus-work-evidence-invalid")
    if decision.next_work_id is None or decision.next_work_id == current.item_id:
        raise CorpusProblem("corpus-work-target-invalid")
    return CorpusItemRevision.model_validate(
        current.model_dump()
        | {
            "revision_id": decision.next_revision_id,
            "previous_revision_id": current.revision_id,
            "decision_revision_id": decision.decision_id,
            "work_id": decision.next_work_id,
            "work_revision_id": decision.next_value,
        }
    )


def _require_decision_scope(current: CorpusItemRevision, decision: CorpusDecision) -> None:
    if (current.project_id, current.item_id) != (decision.project_id, decision.item_id):
        raise CorpusProblem("corpus-decision-scope-mismatch")
    if decision.previous_revision_id != current.revision_id:
        raise CorpusProblem("corpus-predecessor-stale")
    if decision.previous_decision_revision_id != current.decision_revision_id:
        raise CorpusProblem("corpus-decision-chain-mismatch")


def _is_identity(value: str) -> bool:
    from ..domain_contracts import is_uuid_v7

    return is_uuid_v7(value)
