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


def canonical_bytes(value: Any) -> bytes:
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
    risk_tier = decision.get("riskTier")
    if (
        not isinstance(decision.get("category"), str)
        or not isinstance(decision.get("action"), str)
        or not isinstance(decision.get("summary"), str)
        or not isinstance(risk_tier, int)
        or isinstance(risk_tier, bool)
        or risk_tier not in range(4)
        or not isinstance(decision.get("approvalRequired"), bool)
    ):
        raise KernelValidationError("Governance next-action decision is invalid")


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
        or not isinstance(source.get("path"), str)
        or not source.get("path")
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
        or not isinstance(source.get("path"), str)
        or not source.get("path")
        or not isinstance(source.get("sha256"), str)
        or not HEX_SHA256.fullmatch(str(source.get("sha256")))
        or not isinstance(projection.get("program"), dict)
        or not isinstance(projection.get("legacyCategory"), str)
        or not isinstance(projection.get("shadowAgreement"), bool)
    ):
        raise KernelValidationError("Governance projection source or payload is invalid")
    _validate_decision(projection.get("decision"))


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
