#!/usr/bin/env python3
"""Small, pure governance event verification and projection kernel.

This module performs no filesystem, Git, clock, or process operations.  It is
the shadow protocol core for typed event envelopes, capability negotiation,
hash-chain verification, checkpoint validation, and deterministic projection.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any, TypedDict

SCHEMA_VERSION = "1.0"
GENESIS_HASH = "0" * 64
EVENT_TYPE = "governance-event"
CHECKPOINT_TYPE = "governance-checkpoint"
PROJECTION_TYPE = "governance-next-action-projection"
EVENT_KIND = "next-action-observed"
SUPPORTED_CAPABILITIES = frozenset(
    {
        "event.next-action-observed.v1",
        "invariant.advisory-only.v1",
        "projection.next-action.v1",
        "source.sha256.v1",
    }
)
REQUIRED_EVENT_CAPABILITIES = SUPPORTED_CAPABILITIES
DECISION_FIELDS = {
    "action",
    "approvalRequired",
    "category",
    "command",
    "effect",
    "executableNow",
    "riskTier",
    "summary",
    "target",
}
DECISION_ACTIONS = {
    "amendment": {"inspect-amendment"},
    "complete": {"none"},
    "recovery-hold": {"inspect-recovery"},
    "release-gate": {"review-gate"},
    "task": {"claim-amendment-task", "claim-wave-task"},
    "wave": {"inspect-active-wave", "qualify-wave", "resume-wave", "start-wave"},
    "wave-approval": {"review-wave"},
}
PROGRAM_FIELDS = {"blockedWave", "currentWave", "nextGate", "state"}
PROGRAM_STATES = {
    "ACTIVE_WAVE",
    "AMENDMENT_INTERRUPTED",
    "COMPLETE",
    "GATE_PENDING",
    "RECOVERY_INTERRUPTED",
}
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SourceBinding(TypedDict):
    path: str
    sha256: str


class GovernanceEvent(TypedDict):
    schemaVersion: str
    documentType: str
    eventId: str
    sequence: int
    kind: str
    subject: str
    capabilities: list[str]
    authority: str
    mutationPerformed: bool
    previousEventHash: str
    source: SourceBinding
    payload: dict[str, Any]
    eventHash: str


class GovernanceCheckpoint(TypedDict):
    schemaVersion: str
    documentType: str
    throughSequence: int
    throughEventHash: str
    capabilities: list[str]
    projection: dict[str, Any]
    projectionSha256: str
    checkpointHash: str


class KernelValidationError(ValueError):
    """Raised when an event, checkpoint, or tail fails closed."""


class PausedCorrectionProjection(TypedDict):
    """Validation-only roles; never an approval or permission to mutate."""

    parentId: str
    correctionId: str
    phase: str
    holdOwner: str | None
    parentFrozen: bool


def paused_predecessor_record_hash(record: Mapping[str, Any]) -> str:
    """Match the compatibility adapter's complete serialized-record binding."""
    _validate_json_domain(record)
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate_correction_identity(record: Mapping[str, Any], binding: Mapping[str, Any], correction_id: str) -> None:
    """Validate immutable relation fields even after the live parent advances."""
    expected_fields = {
        "id",
        "changeRequestId",
        "status",
        "packetCommit",
        "approvalReference",
        "effectiveStateCommit",
        "recordSha256",
        "returnPolicy",
    }
    if set(binding) != expected_fields or binding.get("returnPolicy") != "paused-predecessor":
        raise KernelValidationError("Paused correction binding or return policy is unsupported")
    parent_id = str(binding.get("id") or "")
    match = re.fullmatch(r"(W(?:[0-9]|1[01]))\.A([0-9]{2})", parent_id)
    if (
        match is None
        or correction_id != f"{match[1]}.A{int(match[2]) + 1:02d}"
        or record.get("id") != parent_id
        or record.get("target_wave") != match[1]
        or record.get("change_request_id") != binding.get("changeRequestId")
        or "correction" in record
    ):
        raise KernelValidationError("Paused correction must name its immediate non-correction predecessor")
    approval = record.get("approval_reference") or {}
    if binding.get("approvalReference") != {
        "path": approval.get("path"),
        "sha256": approval.get("sha256"),
        "introductionCommit": approval.get("introduction_commit"),
    }:
        raise KernelValidationError("Paused correction predecessor approval differs from its binding")
    for field in ("packetCommit", "effectiveStateCommit"):
        if not isinstance(binding.get(field), str) or re.fullmatch(r"[0-9a-f]{40}", binding[field]) is None:
            raise KernelValidationError("Paused correction commit binding is invalid")
    if binding.get("status") != "PAUSED" or re.fullmatch(r"[0-9a-f]{64}", str(binding.get("recordSha256"))) is None:
        raise KernelValidationError("Paused correction snapshot status/hash is invalid")


def validate_paused_predecessor_record(
    record: Mapping[str, Any], binding: Mapping[str, Any], correction_id: str
) -> None:
    """Validate exact paused bytes; the adapter must also authenticate Git and approval."""
    _validate_correction_identity(record, binding, correction_id)
    if binding.get("status") != "PAUSED" or (record.get("lifecycle") or {}).get("status") != "PAUSED":
        raise KernelValidationError("Correction predecessor must be PAUSED, never assumed adopted")
    campaign = record.get("campaign") or {}
    tasks = record.get("tasks") or []
    if (
        campaign.get("status") != "PAUSED"
        or campaign.get("lease") is not None
        or not tasks
        or any(task.get("status") in {"IN_PROGRESS", "REVIEW"} or task.get("lease") is not None for task in tasks)
    ):
        raise KernelValidationError("Paused correction predecessor is not quiescent and lease-free")
    if binding.get("recordSha256") != paused_predecessor_record_hash(record):
        raise KernelValidationError("Paused correction predecessor record changed")


def validate_returned_predecessor_history(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    """Return permits new work, never removal of the authenticated prior history."""

    def prefix(prior: Any, current: Any) -> bool:
        return isinstance(prior, list) and isinstance(current, list) and current[: len(prior)] == prior

    if before.get("bootstrap") != after.get("bootstrap") or not prefix(
        (before.get("lifecycle") or {}).get("history", []), (after.get("lifecycle") or {}).get("history", [])
    ):
        raise KernelValidationError("Returned predecessor bootstrap/lifecycle history changed")
    prior_exit = ((before.get("completion") or {}).get("exit_review_control") or {}).get("attempts", [])
    current_exit = ((after.get("completion") or {}).get("exit_review_control") or {}).get("attempts", [])
    if not prefix(prior_exit, current_exit):
        raise KernelValidationError("Returned predecessor exit review history changed")
    prior_tasks, current_tasks = before.get("tasks") or [], after.get("tasks") or []
    if [item.get("id") for item in prior_tasks] != [item.get("id") for item in current_tasks]:
        raise KernelValidationError("Returned predecessor task inventory changed")
    for prior, current in zip(prior_tasks, current_tasks, strict=True):
        if prior.get("status") == "DONE" and prior != current:
            raise KernelValidationError("Returned predecessor completed task record changed")
        if not prefix(
            (prior.get("review_control") or {}).get("attempts", []),
            (current.get("review_control") or {}).get("attempts", []),
        ):
            raise KernelValidationError("Returned predecessor task review history changed")


def project_paused_corrections(amendments: Iterable[Mapping[str, Any]]) -> list[PausedCorrectionProjection]:
    """Derive single-owner correction roles without performing any mutation.

    Normal legacy records require no new metadata. A pending bootstrap freezes
    its parent but has not acquired the hold. Materialization owns the hold;
    qualified adoption returns it to the parent. Existing taskctl still checks
    every bootstrap/task/exit review, authenticated Git source and atomic write.
    """
    records = list(amendments)
    by_id = {str(item.get("id")): item for item in records}
    if len(by_id) != len(records):
        raise KernelValidationError("Duplicate amendment identity in correction projection")
    projections: list[PausedCorrectionProjection] = []
    seen_parents: set[str] = set()
    for child in records:
        if "correction" not in child:
            continue
        binding = child["correction"]
        if not isinstance(binding, dict):
            raise KernelValidationError("Paused correction binding must be an object")
        parent_id = str(binding.get("id") or "")
        parent = by_id.get(parent_id)
        child_id = str(child.get("id") or "")
        wave_records = [item for item in records if item.get("target_wave") == child.get("target_wave")]
        if (
            parent is None
            or parent_id in seen_parents
            or parent not in wave_records
            or wave_records.index(child) != wave_records.index(parent) + 1
            or "correction" in parent
        ):
            raise KernelValidationError("Missing, competing, nested or reordered paused correction predecessor")
        seen_parents.add(parent_id)
        _validate_correction_identity(parent, binding, child_id)
        state = (child.get("lifecycle") or {}).get("status")
        if state not in {"APPROVED", "MATERIALIZED", "ACTIVE", "PAUSED", "REVIEW", "BLOCKED", "ADOPTED"}:
            raise KernelValidationError("Correction disposal requires separately reviewed recovery; it is unsupported")
        frozen = state != "ADOPTED"
        if frozen:
            validate_paused_predecessor_record(parent, binding, child_id)
        else:
            # The immutable historical parent and binding are authenticated by
            # the adapter. Only after adoption may the live parent advance.
            if binding.get("returnPolicy") != "paused-predecessor":
                raise KernelValidationError("Returned correction has an unsupported return policy")
            if (parent.get("lifecycle") or {}).get("status") not in {
                "PAUSED",
                "ACTIVE",
                "REVIEW",
                "BLOCKED",
                "ADOPTED",
            }:
                raise KernelValidationError("Returned correction predecessor has regressed or been disposed")
        owner: str | None = parent_id if state in {"APPROVED", "ADOPTED"} else child_id
        if state == "ADOPTED" and (parent.get("lifecycle") or {}).get("status") == "ADOPTED":
            owner = None
        projections.append(
            {
                "parentId": parent_id,
                "correctionId": child_id,
                "phase": "returned" if state == "ADOPTED" else "pending-entry" if state == "APPROVED" else "executing",
                "holdOwner": owner,
                "parentFrozen": frozen,
            }
        )
    return projections


def _validate_json_domain(value: Any, path: str = "$") -> None:
    if value is None or type(value) in {bool, int, str}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise KernelValidationError(f"Governance document contains a non-finite number at {path}")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_domain(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise KernelValidationError(f"Governance document contains a non-string key at {path}")
            _validate_json_domain(item, f"{path}.{key}")
        return
    raise KernelValidationError(f"Governance document contains a non-JSON value at {path}: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    _validate_json_domain(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise KernelValidationError(f"Governance document is not canonical JSON: {exc}") from exc


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def document_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return sha256(canonical_bytes({key: value for key, value in document.items() if key != hash_field}))


def _require_exact_fields(document: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(document)
    if actual != expected:
        difference = sorted(actual ^ expected)
        raise KernelValidationError(f"{label} fields differ: {difference[0] if difference else '<unknown>'}")


def _validate_capabilities(values: Any, supported: frozenset[str], label: str) -> list[str]:
    if not isinstance(values, list) or not values or any(not isinstance(value, str) for value in values):
        raise KernelValidationError(f"{label} capabilities must be a non-empty string list")
    if values != sorted(set(values)):
        raise KernelValidationError(f"{label} capabilities must be sorted and unique")
    unknown = sorted(set(values) - supported)
    if unknown:
        raise KernelValidationError(f"Unsupported governance capability: {unknown[0]}")
    missing = sorted(REQUIRED_EVENT_CAPABILITIES - set(values))
    if missing:
        raise KernelValidationError(f"{label} is missing required governance capability: {missing[0]}")
    return values


def _validate_decision(decision: Any) -> None:
    if not isinstance(decision, dict):
        raise KernelValidationError("Governance next-action decision is invalid")
    _require_exact_fields(decision, DECISION_FIELDS, "Governance next-action decision")
    category = decision.get("category")
    action = decision.get("action")
    risk_tier = decision.get("riskTier")
    if (
        type(category) is not str
        or category not in DECISION_ACTIONS
        or type(action) is not str
        or action not in DECISION_ACTIONS[category]
        or type(decision.get("summary")) is not str
        or not decision.get("summary")
        or not (
            decision.get("target") is None or (type(decision.get("target")) is str and bool(decision.get("target")))
        )
        or not (
            decision.get("command") is None or (type(decision.get("command")) is str and bool(decision.get("command")))
        )
        or type(risk_tier) is not int
        or risk_tier not in range(4)
        or type(decision.get("executableNow")) is not bool
        or type(decision.get("approvalRequired")) is not bool
        or decision.get("effect") not in {"read-only", "mutation-template"}
        or (risk_tier == 0) != (decision.get("effect") == "read-only")
    ):
        raise KernelValidationError("Governance next-action decision is invalid")


def _validate_program(program: Any) -> None:
    if not isinstance(program, dict):
        raise KernelValidationError("Governance program position is invalid")
    _require_exact_fields(program, PROGRAM_FIELDS, "Governance program position")
    if type(program.get("state")) is not str or program.get("state") not in PROGRAM_STATES:
        raise KernelValidationError("Governance program position is invalid")
    for field in ("blockedWave", "currentWave", "nextGate"):
        value = program.get(field)
        if value is not None and (type(value) is not str or not value):
            raise KernelValidationError("Governance program position is invalid")


def validate_event(
    event: Mapping[str, Any],
    *,
    supported_capabilities: frozenset[str] = SUPPORTED_CAPABILITIES,
) -> None:
    _require_exact_fields(
        event,
        {
            "schemaVersion",
            "documentType",
            "eventId",
            "sequence",
            "kind",
            "subject",
            "capabilities",
            "authority",
            "mutationPerformed",
            "previousEventHash",
            "source",
            "payload",
            "eventHash",
        },
        "Governance event",
    )
    sequence = event.get("sequence")
    source = event.get("source")
    payload = event.get("payload")
    if (
        event.get("schemaVersion") != SCHEMA_VERSION
        or event.get("documentType") != EVENT_TYPE
        or not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence < 1
        or event.get("eventId") != f"GE-{sequence:08d}"
        or event.get("kind") != EVENT_KIND
        or not isinstance(event.get("subject"), str)
        or not event.get("subject")
        or event.get("authority") != "advisory-only"
        or event.get("mutationPerformed") is not False
        or not isinstance(event.get("previousEventHash"), str)
        or not HEX_SHA256.fullmatch(str(event.get("previousEventHash")))
        or not isinstance(source, dict)
        or set(source) != {"path", "sha256"}
        or source.get("path") != "planning/backlog.yaml"
        or not isinstance(source.get("sha256"), str)
        or not HEX_SHA256.fullmatch(str(source.get("sha256")))
        or not isinstance(payload, dict)
        or set(payload) != {"decision", "legacyCategory", "program", "shadowAgreement"}
        or not isinstance(payload.get("decision"), dict)
        or not isinstance(payload.get("program"), dict)
        or not isinstance(payload.get("legacyCategory"), str)
        or not isinstance(payload.get("shadowAgreement"), bool)
    ):
        raise KernelValidationError("Governance event identity, authority, source, or payload is invalid")
    _validate_capabilities(event.get("capabilities"), supported_capabilities, "Event")
    _validate_decision(payload["decision"])
    _validate_program(payload["program"])
    if event.get("eventHash") != document_hash(event, "eventHash"):
        raise KernelValidationError("Governance event hash differs")


def build_next_action_event(
    *,
    sequence: int,
    previous_event_hash: str,
    subject: str,
    source: SourceBinding,
    program: dict[str, Any],
    decision: dict[str, Any],
    legacy_category: str,
    shadow_agreement: bool,
) -> GovernanceEvent:
    event: GovernanceEvent = {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": EVENT_TYPE,
        "eventId": f"GE-{sequence:08d}",
        "sequence": sequence,
        "kind": EVENT_KIND,
        "subject": subject,
        "capabilities": sorted(SUPPORTED_CAPABILITIES),
        "authority": "advisory-only",
        "mutationPerformed": False,
        "previousEventHash": previous_event_hash,
        "source": copy.deepcopy(source),
        "payload": {
            "decision": copy.deepcopy(decision),
            "legacyCategory": legacy_category,
            "program": copy.deepcopy(program),
            "shadowAgreement": shadow_agreement,
        },
        "eventHash": "",
    }
    event["eventHash"] = document_hash(event, "eventHash")
    validate_event(event)
    return event


def initial_projection() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": PROJECTION_TYPE,
        "throughSequence": 0,
        "throughEventHash": GENESIS_HASH,
        "observationCount": 0,
        "source": None,
        "program": None,
        "decision": None,
        "legacyCategory": None,
        "shadowAgreement": None,
    }


def apply_event(projection: dict[str, Any], event: GovernanceEvent) -> dict[str, Any]:
    payload = event["payload"]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": PROJECTION_TYPE,
        "throughSequence": event["sequence"],
        "throughEventHash": event["eventHash"],
        "observationCount": int(projection.get("observationCount", 0)) + 1,
        "source": copy.deepcopy(event["source"]),
        "program": copy.deepcopy(payload["program"]),
        "decision": copy.deepcopy(payload["decision"]),
        "legacyCategory": payload["legacyCategory"],
        "shadowAgreement": payload["shadowAgreement"],
    }


def validate_projection(projection: Mapping[str, Any]) -> None:
    _require_exact_fields(
        projection,
        {
            "schemaVersion",
            "documentType",
            "throughSequence",
            "throughEventHash",
            "observationCount",
            "source",
            "program",
            "decision",
            "legacyCategory",
            "shadowAgreement",
        },
        "Governance projection",
    )
    through_sequence = projection.get("throughSequence")
    observation_count = projection.get("observationCount")
    if (
        projection.get("schemaVersion") != SCHEMA_VERSION
        or projection.get("documentType") != PROJECTION_TYPE
        or not isinstance(through_sequence, int)
        or isinstance(through_sequence, bool)
        or through_sequence < 0
        or not isinstance(observation_count, int)
        or isinstance(observation_count, bool)
        or observation_count != through_sequence
        or not isinstance(projection.get("throughEventHash"), str)
        or not HEX_SHA256.fullmatch(str(projection.get("throughEventHash")))
    ):
        raise KernelValidationError("Governance projection identity or sequence is invalid")
    if through_sequence == 0:
        if projection.get("throughEventHash") != GENESIS_HASH or any(
            projection.get(key) is not None
            for key in ("source", "program", "decision", "legacyCategory", "shadowAgreement")
        ):
            raise KernelValidationError("Governance genesis projection is invalid")
        return
    source = projection.get("source")
    if (
        projection.get("throughEventHash") == GENESIS_HASH
        or not isinstance(source, dict)
        or set(source) != {"path", "sha256"}
        or source.get("path") != "planning/backlog.yaml"
        or not isinstance(source.get("sha256"), str)
        or not HEX_SHA256.fullmatch(str(source.get("sha256")))
        or not isinstance(projection.get("program"), dict)
        or not isinstance(projection.get("legacyCategory"), str)
        or not isinstance(projection.get("shadowAgreement"), bool)
    ):
        raise KernelValidationError("Governance projection source or payload is invalid")
    _validate_decision(projection.get("decision"))
    _validate_program(projection.get("program"))


def validate_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    supported_capabilities: frozenset[str] = SUPPORTED_CAPABILITIES,
) -> None:
    _require_exact_fields(
        checkpoint,
        {
            "schemaVersion",
            "documentType",
            "throughSequence",
            "throughEventHash",
            "capabilities",
            "projection",
            "projectionSha256",
            "checkpointHash",
        },
        "Governance checkpoint",
    )
    projection = checkpoint.get("projection")
    through_sequence = checkpoint.get("throughSequence")
    if (
        checkpoint.get("schemaVersion") != SCHEMA_VERSION
        or checkpoint.get("documentType") != CHECKPOINT_TYPE
        or not isinstance(through_sequence, int)
        or isinstance(through_sequence, bool)
        or through_sequence < 0
        or not isinstance(checkpoint.get("throughEventHash"), str)
        or not HEX_SHA256.fullmatch(str(checkpoint.get("throughEventHash")))
        or not isinstance(projection, dict)
        or projection.get("throughSequence") != through_sequence
        or projection.get("throughEventHash") != checkpoint.get("throughEventHash")
        or checkpoint.get("projectionSha256") != sha256(canonical_bytes(projection))
        or checkpoint.get("checkpointHash") != document_hash(checkpoint, "checkpointHash")
    ):
        raise KernelValidationError("Governance checkpoint binding is invalid")
    _validate_capabilities(checkpoint.get("capabilities"), supported_capabilities, "Checkpoint")
    validate_projection(projection)


def build_checkpoint(projection: dict[str, Any]) -> GovernanceCheckpoint:
    checkpoint: GovernanceCheckpoint = {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": CHECKPOINT_TYPE,
        "throughSequence": int(projection["throughSequence"]),
        "throughEventHash": str(projection["throughEventHash"]),
        "capabilities": sorted(SUPPORTED_CAPABILITIES),
        "projection": copy.deepcopy(projection),
        "projectionSha256": sha256(canonical_bytes(projection)),
        "checkpointHash": "",
    }
    checkpoint["checkpointHash"] = document_hash(checkpoint, "checkpointHash")
    validate_checkpoint(checkpoint)
    return checkpoint


def verify_and_project(
    events: Iterable[GovernanceEvent],
    *,
    checkpoint: GovernanceCheckpoint | None = None,
    trusted_checkpoint_hash: str | None = None,
    supported_capabilities: frozenset[str] = SUPPORTED_CAPABILITIES,
) -> dict[str, Any]:
    if checkpoint is None:
        if trusted_checkpoint_hash is not None:
            raise KernelValidationError("Trusted checkpoint hash was supplied without a checkpoint")
        projection = initial_projection()
    else:
        if trusted_checkpoint_hash is None:
            raise KernelValidationError("Checkpoint replay requires an external trusted checkpoint hash")
        validate_checkpoint(checkpoint, supported_capabilities=supported_capabilities)
        if checkpoint["checkpointHash"] != trusted_checkpoint_hash:
            raise KernelValidationError("Governance checkpoint differs from the trusted checkpoint hash")
        projection = copy.deepcopy(checkpoint["projection"])
    expected_sequence = int(projection["throughSequence"]) + 1
    previous_hash = str(projection["throughEventHash"])
    for event in events:
        validate_event(event, supported_capabilities=supported_capabilities)
        if event["sequence"] != expected_sequence:
            raise KernelValidationError(f"Governance event sequence gap at {event['eventId']}")
        if event["previousEventHash"] != previous_hash:
            raise KernelValidationError(f"Governance event ancestry differs at {event['eventId']}")
        projection = apply_event(projection, event)
        expected_sequence += 1
        previous_hash = event["eventHash"]
    return projection
