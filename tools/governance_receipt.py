#!/usr/bin/env python3
"""Pure, evidence-only transition receipts for the governance shadow kernel."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any, TypedDict, cast

import governance_kernel

SCHEMA_VERSION = "1.0"
DOCUMENT_TYPE = "governance-transition-receipt"
RECEIPT_CAPABILITY = "receipt.transition.v1"
SUPPORTED_CAPABILITIES = frozenset({RECEIPT_CAPABILITY})
CHECK_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
BRANCH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class GitBinding(TypedDict):
    commit: str
    branch: str
    trackedWorktreeClean: bool


class TransitionReceipt(TypedDict):
    schemaVersion: str
    documentType: str
    receiptId: str
    capabilities: list[str]
    mode: str
    authority: str
    mutationPerformed: bool
    eventBinding: dict[str, str]
    sourceBinding: dict[str, Any]
    projectionBinding: dict[str, Any]
    gitBinding: GitBinding
    verification: dict[str, Any]
    receiptHash: str


class ReceiptValidationError(governance_kernel.KernelValidationError):
    """Raised when a receipt does not exactly bind its transition evidence."""


def _require_exact_fields(document: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(document)
    if actual != expected:
        difference = sorted(actual ^ expected)
        raise ReceiptValidationError(f"{label} fields differ: {difference[0] if difference else '<unknown>'}")


def _value_hash(value: Any) -> str:
    return governance_kernel.sha256(governance_kernel.canonical_bytes(value))


def projection_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, str]]:
    governance_kernel.validate_projection(before)
    governance_kernel.validate_projection(after)
    delta: list[dict[str, str]] = []
    for field in sorted(before):
        if governance_kernel.canonical_bytes(before[field]) == governance_kernel.canonical_bytes(after[field]):
            continue
        delta.append(
            {
                "field": field,
                "beforeSha256": _value_hash(before[field]),
                "afterSha256": _value_hash(after[field]),
            }
        )
    return delta


def validate_git_binding(binding: Any) -> GitBinding:
    if not isinstance(binding, dict):
        raise ReceiptValidationError("Receipt Git binding is invalid")
    _require_exact_fields(binding, {"branch", "commit", "trackedWorktreeClean"}, "Receipt Git binding")
    commit = binding.get("commit")
    branch = binding.get("branch")
    if (
        type(commit) is not str
        or GIT_COMMIT.fullmatch(commit) is None
        or type(branch) is not str
        or BRANCH_NAME.fullmatch(branch) is None
        or branch.endswith(("/", "."))
        or ".." in branch.split("/")
        or type(binding.get("trackedWorktreeClean")) is not bool
    ):
        raise ReceiptValidationError("Receipt Git binding is invalid")
    return cast(GitBinding, binding)


def _validate_verification(
    verification: Any,
    *,
    event: governance_kernel.GovernanceEvent,
    source_changed: bool,
    tracked_worktree_clean: bool,
) -> None:
    if not isinstance(verification, dict):
        raise ReceiptValidationError("Receipt verification is invalid")
    _require_exact_fields(
        verification,
        {"overallStatus", "results", "selectedChecks", "trust"},
        "Receipt verification",
    )
    selected = verification.get("selectedChecks")
    results = verification.get("results")
    if (
        not isinstance(selected, list)
        or not selected
        or any(type(item) is not str or CHECK_ID.fullmatch(item) is None for item in selected)
        or selected != sorted(set(selected))
        or not isinstance(results, list)
    ):
        raise ReceiptValidationError("Receipt selected checks are invalid")
    normalized_results: list[dict[str, str]] = []
    for result in results:
        if not isinstance(result, dict):
            raise ReceiptValidationError("Receipt check result is invalid")
        _require_exact_fields(result, {"id", "status"}, "Receipt check result")
        if result.get("id") not in selected or result.get("status") not in {"failed", "passed"}:
            raise ReceiptValidationError("Receipt check result is invalid")
        normalized_results.append({"id": result["id"], "status": result["status"]})
    if normalized_results != sorted(normalized_results, key=lambda item: item["id"]):
        raise ReceiptValidationError("Receipt check results must be sorted")
    if [item["id"] for item in normalized_results] != selected:
        raise ReceiptValidationError("Receipt checks and results differ")
    statuses = {item["id"]: item["status"] for item in normalized_results}
    expected_results = {
        "event-envelope": "passed",
        "projection-transition": "passed",
        "source-byte-stability": "failed" if source_changed else "passed",
        "producer-git-binding": "passed" if tracked_worktree_clean else "failed",
    }
    if any(statuses[check_id] != expected for check_id, expected in expected_results.items() if check_id in statuses):
        raise ReceiptValidationError("Receipt check result contradicts its bound evidence")
    if "legacy-category-agreement" in statuses and statuses["legacy-category-agreement"] != (
        "passed" if event["payload"]["shadowAgreement"] else "failed"
    ):
        raise ReceiptValidationError("Receipt legacy agreement result contradicts its event")
    bound_facts_pass = not source_changed and tracked_worktree_clean and event["payload"]["shadowAgreement"]
    overall = "passed" if bound_facts_pass and all(status == "passed" for status in statuses.values()) else "failed"
    if verification.get("overallStatus") != overall or verification.get("trust") != "producer-asserted":
        raise ReceiptValidationError("Receipt verification status or trust is invalid")


def _validate_transition(
    event: governance_kernel.GovernanceEvent,
    before_projection: Mapping[str, Any],
    after_projection: Mapping[str, Any],
) -> None:
    governance_kernel.validate_event(event)
    governance_kernel.validate_projection(before_projection)
    governance_kernel.validate_projection(after_projection)
    if (
        event["sequence"] != before_projection["throughSequence"] + 1
        or event["previousEventHash"] != before_projection["throughEventHash"]
        or governance_kernel.apply_event(dict(before_projection), event) != after_projection
    ):
        raise ReceiptValidationError("Receipt transition differs from the event projection")


def validate_receipt(
    receipt: Mapping[str, Any],
    *,
    event: governance_kernel.GovernanceEvent,
    before_projection: Mapping[str, Any],
    after_projection: Mapping[str, Any],
    expected_git_binding: GitBinding,
    supported_capabilities: frozenset[str] = SUPPORTED_CAPABILITIES,
) -> None:
    _require_exact_fields(
        receipt,
        {
            "schemaVersion",
            "documentType",
            "receiptId",
            "capabilities",
            "mode",
            "authority",
            "mutationPerformed",
            "eventBinding",
            "sourceBinding",
            "projectionBinding",
            "gitBinding",
            "verification",
            "receiptHash",
        },
        "Governance receipt",
    )
    _validate_transition(event, before_projection, after_projection)
    capabilities = receipt.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or capabilities != sorted(set(capabilities))
        or set(capabilities) != {RECEIPT_CAPABILITY}
        or not set(capabilities).issubset(supported_capabilities)
    ):
        raise ReceiptValidationError("Receipt capabilities are invalid or unsupported")
    expected_id = f"GR-{event['eventId']}-{event['eventHash'][:12]}"
    if (
        receipt.get("schemaVersion") != SCHEMA_VERSION
        or receipt.get("documentType") != DOCUMENT_TYPE
        or receipt.get("receiptId") != expected_id
        or receipt.get("mode") != "shadow"
        or receipt.get("authority") != "evidence-only"
        or receipt.get("mutationPerformed") is not False
    ):
        raise ReceiptValidationError("Receipt identity or authority is invalid")
    event_binding = receipt.get("eventBinding")
    if not isinstance(event_binding, dict):
        raise ReceiptValidationError("Receipt event binding is invalid")
    _require_exact_fields(event_binding, {"eventHash", "eventId", "kind", "subject"}, "Receipt event binding")
    if event_binding != {
        "eventHash": event["eventHash"],
        "eventId": event["eventId"],
        "kind": event["kind"],
        "subject": event["subject"],
    }:
        raise ReceiptValidationError("Receipt event binding differs")
    source_binding = receipt.get("sourceBinding")
    if not isinstance(source_binding, dict):
        raise ReceiptValidationError("Receipt source binding is invalid")
    _require_exact_fields(source_binding, {"changed", "observed", "projected"}, "Receipt source binding")
    projected_source = after_projection["source"]
    source_changed = event["source"] != projected_source
    if source_binding != {
        "observed": event["source"],
        "projected": projected_source,
        "changed": source_changed,
    }:
        raise ReceiptValidationError("Receipt source binding differs")
    projection_binding = receipt.get("projectionBinding")
    if not isinstance(projection_binding, dict):
        raise ReceiptValidationError("Receipt projection binding is invalid")
    _require_exact_fields(
        projection_binding,
        {"afterSha256", "beforeSha256", "changedFields"},
        "Receipt projection binding",
    )
    if projection_binding != {
        "beforeSha256": _value_hash(before_projection),
        "afterSha256": _value_hash(after_projection),
        "changedFields": projection_delta(before_projection, after_projection),
    }:
        raise ReceiptValidationError("Receipt projection binding differs")
    binding = validate_git_binding(receipt.get("gitBinding"))
    trusted_binding = validate_git_binding(expected_git_binding)
    if binding != trusted_binding:
        raise ReceiptValidationError("Receipt Git binding differs from the expected producer state")
    _validate_verification(
        receipt.get("verification"),
        event=event,
        source_changed=source_changed,
        tracked_worktree_clean=binding["trackedWorktreeClean"],
    )
    if receipt.get("receiptHash") != governance_kernel.document_hash(receipt, "receiptHash"):
        raise ReceiptValidationError("Receipt hash differs")


def build_receipt(
    *,
    event: governance_kernel.GovernanceEvent,
    before_projection: Mapping[str, Any],
    after_projection: Mapping[str, Any],
    git_binding: GitBinding,
    check_results: Mapping[str, bool],
) -> TransitionReceipt:
    _validate_transition(event, before_projection, after_projection)
    binding = copy.deepcopy(validate_git_binding(git_binding))
    if (
        any(type(check_id) is not str or CHECK_ID.fullmatch(check_id) is None for check_id in check_results)
        or any(type(passed) is not bool for passed in check_results.values())
        or not check_results
    ):
        raise ReceiptValidationError("Receipt check selection is invalid")
    results = [
        {"id": check_id, "status": "passed" if check_results[check_id] else "failed"}
        for check_id in sorted(check_results)
    ]
    source_changed = event["source"] != after_projection["source"]
    receipt: TransitionReceipt = {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": DOCUMENT_TYPE,
        "receiptId": f"GR-{event['eventId']}-{event['eventHash'][:12]}",
        "capabilities": sorted(SUPPORTED_CAPABILITIES),
        "mode": "shadow",
        "authority": "evidence-only",
        "mutationPerformed": False,
        "eventBinding": {
            "eventId": event["eventId"],
            "eventHash": event["eventHash"],
            "kind": event["kind"],
            "subject": event["subject"],
        },
        "sourceBinding": {
            "observed": copy.deepcopy(event["source"]),
            "projected": copy.deepcopy(after_projection["source"]),
            "changed": source_changed,
        },
        "projectionBinding": {
            "beforeSha256": _value_hash(before_projection),
            "afterSha256": _value_hash(after_projection),
            "changedFields": projection_delta(before_projection, after_projection),
        },
        "gitBinding": binding,
        "verification": {
            "selectedChecks": sorted(check_results),
            "results": results,
            "overallStatus": (
                "passed"
                if (
                    not source_changed
                    and binding["trackedWorktreeClean"]
                    and event["payload"]["shadowAgreement"]
                    and all(check_results.values())
                )
                else "failed"
            ),
            "trust": "producer-asserted",
        },
        "receiptHash": "",
    }
    receipt["receiptHash"] = governance_kernel.document_hash(receipt, "receiptHash")
    validate_receipt(
        receipt,
        event=event,
        before_projection=before_projection,
        after_projection=after_projection,
        expected_git_binding=binding,
    )
    return receipt
