#!/usr/bin/env python3
"""Exact GCR-0005 controller for the GRR-0002.B02 R01 review bridge.

The controller recognizes only GCR-0005.B00.  It cannot remediate B02, create
or execute W1.A04, release the recovery hold, resume W1, approve G1, or perform
Git integration or remote work.
"""

from __future__ import annotations

import argparse
import base64
import copy
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

import taskctl
import yaml
from gcrctl import (
    _artifact_path,
    adoption_fault_boundary,
    fsync_directory,
    git,
    move_write_through,
    path_authorized,
    require_exact_commit_delta,
    safe_path,
    sha256,
    unlink_durable,
    validate_scope_pattern,
    write_json_atomic,
    write_new_durable,
)
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

GCR_ID = "GCR-0005"
BOOTSTRAP_ID = "GCR-0005.B00"
BRANCH = "codex/w1-windows-local-runtime"
ACTOR = "codex"
PACKET_COMMIT = "86e0393595809ccff589e1793970e38536ec4116"
PACKET_SHA256 = "41a6f4778d23c510b2353d80756a463ee6ebc53a83b281d709b7840257e28a05"
APPROVAL_COMMIT = "c23a823aadc915400884c3827f7f6feef879cf8b"
PACKET_PATH = "planning/governance-control-recovery/GCR-0005.packet.json"
APPROVAL_PATH = "planning/governance-control-recovery/GCR-0005.approval.json"
AUTHORITY_PATH = "planning/governance-control-recovery/GCR-0005.authority.json"
REQUEST_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-request.v5.schema.json"
RUNTIME_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-runtime.v5.schema.json"
TRANSACTION_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-transaction.v5.schema.json"
STATE_PATH = "planning/governance-control-recovery/GCR-0005.B00.state.json"
TRANSACTION_PATH = "planning/governance-control-recovery/GCR-0005.B00.application-transaction.json"
LOCK_PATH = "planning/governance-control-recovery/GCR-0005.B00.application.lock"
BACKLOG_NEXT_PATH = "planning/governance-control-recovery/GCR-0005.B00.backlog.next"
APPLICATION_EVIDENCE_PATH = "artifacts/evidence/governance-control-recovery/GCR-0005.B00.application.json"
BACKLOG_PATH = "planning/backlog.yaml"
LEDGER_PATH = "planning/governance-recovery-approvals/GRR-0002.B02.review-R01.json"
LEDGER_SHA256 = "4b92f7b3a6a621e25c919f8571d7a87617966ae76a7dcbc4f3dcdd05af563e09"
LEDGER_COMMIT = "8b784cabc5d5d996c00fd2fbcc8f22a1ad05b5bb"
REVIEWED_STATE_COMMIT = "962f92ff831c9a3d87a7d6ba796c8194e70b6c2c"
B02_CANDIDATE_COMMIT = "d363c04c385251a5d789a0313e173342e7e0ae3e"
B02_EVIDENCE_PATH = "planning/governance-recovery-approvals/GRR-0002.B02.evidence.json"
B02_EVIDENCE_SHA256 = "77cdc545de58ef9d7237a8ba1c32969a449a87216479fd104e5649e6b5958595"
BACKLOG_BEFORE_RAW = "431ac0390c7aa1b1be229f741cea0b00fb73cfd24713fdcb0e8cc6a13595c7a1"
BACKLOG_BEFORE_CANONICAL = "3ffa93f894b5b63cbefd11d8b058eddf4deda96069aa03c9bb15bc116bc691cb"
BACKLOG_AFTER = "86c40fde359bd64f0979e0a5e982fdfa13de3823b5b77afd1e5341abcc726798"
PROJECTION_TIMESTAMP = "2026-08-26T02:15:00+00:00"
TRIGGER_PATH = "artifacts/evidence/W1.A04.B00.json"
TRIGGER_SHA256 = "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c"
HOLD_ID = "HOLD-W1-GRR-0002"
RESULT_STATUS = {"approved": "APPROVED", "changes-requested": "CHANGES_REQUESTED", "blocked": "BLOCKED"}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
GENERATED_PATHS = [
    "docs/planning-implementation-plan.md",
    "planning/status-summary.md",
    "planning/review-site/manifest.json",
    "planning/review-site/recoveries/GRR-0002.html",
    "planning/review-site/recoveries/index.html",
    "planning/review-site/waves/W1.html",
]
FINAL_PATHS = [GENERATED_PATHS[0], BACKLOG_PATH, *GENERATED_PATHS[1:]]
PREDECESSOR_RAW_SHA256 = {
    "docs/planning-implementation-plan.md": "3d9b16df31a4ca068e4b1f1675bac02ac6870a3604f02d335cd64f87037a9b2c",
    BACKLOG_PATH: BACKLOG_BEFORE_RAW,
    "planning/status-summary.md": "c45a5fda92119fb1d0bae4dfa3d7655fec77db79f5bcf1fc27b5ff210a693623",
    "planning/review-site/manifest.json": "36f0f5603d272d37accdab63e7ce05cba72614256a210bb049f29ac719152704",
    "planning/review-site/recoveries/GRR-0002.html": "cc897bd20403fa87138622d9aeae474c47c9d2e18e0aa0b40716be2696c91cd8",
    "planning/review-site/recoveries/index.html": "24fa4dc0d7990d49b8e2e38f359add4d79a871574d2b6c08cc01113fa25ada6c",
    "planning/review-site/waves/W1.html": "722ed0192ff6d6b38916d67225fa593d15cd46e6dac0d658615edcd3bc817d9b",
}


def strict_json(payload: bytes, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate object key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(payload, object_pairs_hook=reject_duplicates)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Cannot parse {label}: {exc}") from exc


def load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"Cannot load {label}: {path}: {exc}") from exc
    value = strict_json(payload, label)
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object")
    return value, payload


def canonical_sha(document: Any) -> str:
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())


def git_worktree_equivalent(payload: bytes, blob: bytes | None) -> bool:
    return blob is not None and blob in {payload, payload.replace(b"\r\n", b"\n")}


def schema_document(repo: Path, relative: str, label: str) -> dict[str, Any]:
    schema, _payload = load_json(safe_path(repo, relative, label=label), label)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SystemExit(f"{label} is invalid: {exc}") from exc
    return schema


def validate_schema(repo: Path, document: dict[str, Any], relative: str, label: str) -> None:
    errors = sorted(
        Draft202012Validator(
            schema_document(repo, relative, f"{label} schema"),
            format_checker=FormatChecker(),
        ).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        rendered = [
            "$"
            + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
            + f": {error.message}"
            for error in errors
        ]
        raise SystemExit(f"{label} schema validation failed:\n- " + "\n- ".join(rendered))


def validate_runtime(repo: Path, document: dict[str, Any], label: str) -> None:
    validate_schema(repo, document, RUNTIME_SCHEMA_PATH, label)


def validate_transaction(repo: Path, document: dict[str, Any]) -> None:
    validate_schema(repo, document, TRANSACTION_SCHEMA_PATH, "GCR-0005 application transaction")


def trigger_reference() -> dict[str, Any]:
    return {
        "path": TRIGGER_PATH,
        "sha256": TRIGGER_SHA256,
        "untracked": True,
        "unstaged": True,
        "executionAuthority": False,
    }


def validate_witness(repo: Path) -> None:
    path = safe_path(repo, TRIGGER_PATH, label="GCR-0005 witness", prefix="artifacts/evidence")
    if path.is_symlink() or getattr(os.path, "isjunction", lambda _path: False)(path):
        raise SystemExit("GCR-0005 witness must not be redirected")
    if sha256(path.read_bytes()) != TRIGGER_SHA256:
        raise SystemExit("GCR-0005 witness is missing or changed")
    if TRIGGER_PATH in set(git(repo, "ls-files", "--", TRIGGER_PATH).splitlines()):
        raise SystemExit("GCR-0005 witness must remain untracked")
    if TRIGGER_PATH in set(git(repo, "diff", "--cached", "--name-only", "--").splitlines()):
        raise SystemExit("GCR-0005 witness must remain unstaged")


def validate_adverse_ledger(repo: Path) -> tuple[dict[str, Any], bytes]:
    path = safe_path(repo, LEDGER_PATH, label="GRR-0002.B02 adverse ledger", prefix="planning")
    if path.is_symlink() or getattr(os.path, "isjunction", lambda _path: False)(path):
        raise SystemExit("GRR-0002.B02 adverse ledger must not be redirected")
    ledger, payload = load_json(path, "GRR-0002.B02 adverse ledger")
    if sha256(payload) != LEDGER_SHA256 or taskctl.git_blob(repo, LEDGER_COMMIT, LEDGER_PATH) != payload:
        raise SystemExit("GRR-0002.B02 adverse ledger differs from the immutable reviewed bytes")
    if (
        ledger.get("recoveryRequestId") != "GRR-0002"
        or ledger.get("supplementId") != "GRR-0002.S02"
        or ledger.get("bootstrapUnit") != "GRR-0002.B02"
        or ledger.get("attemptId") != "R01"
        or ledger.get("candidateCommit") != B02_CANDIDATE_COMMIT
        or ledger.get("reviewedStateCommit") != REVIEWED_STATE_COMMIT
        or ledger.get("result") != "changes-requested"
        or ledger.get("evidence") != {"path": B02_EVIDENCE_PATH, "sha256": B02_EVIDENCE_SHA256}
        or ledger.get("closures") != []
        or [item.get("id") for item in ledger.get("findings", [])] != ["GRR-0002.B02-R01-F01"]
        or not all(item.get("blocking") is True for item in ledger.get("findings", []))
    ):
        raise SystemExit("GRR-0002.B02 adverse ledger identity or finding is invalid")
    return ledger, payload


def _hold(data: dict[str, Any]) -> dict[str, Any]:
    holds = [item for item in (data.get("control_plane") or {}).get("recovery_holds", []) if item.get("id") == HOLD_ID]
    if len(holds) != 1:
        raise SystemExit("GCR-0005 requires the sole named active recovery hold")
    return holds[0]


def _b02(data: dict[str, Any]) -> dict[str, Any]:
    hold = _hold(data)
    supplements = [item for item in hold.get("supplements", []) if item.get("id") == "GRR-0002.S02"]
    if len(supplements) != 1:
        raise SystemExit("GCR-0005 requires the exact S02 supplement")
    return supplements[0]["bootstrap"]


def validate_boundary(data: dict[str, Any], *, expected_status: str) -> None:
    control = data.get("control_plane") or {}
    hold = _hold(data)
    bootstrap = _b02(data)
    task = taskctl.index_backlog(data)[3]["CAP-02.S04.T03"]
    gate = taskctl.index_backlog(data)[4]["G1"]
    campaign = taskctl.wave_map(data)["W1"]["campaign"]
    if (
        control.get("revision") != 11
        or control.get("minimum_tool_revision") != 11
        or hold.get("status") != "ACTIVE"
        or campaign.get("status") != "PAUSED"
        or campaign.get("scope") != "wave"
        or task.get("status") != "BLOCKED"
        or "W1.A04" in taskctl.wave_amendment_map(data)
        or gate.get("status") != "PENDING"
        or bootstrap.get("status") != expected_status
        or bootstrap.get("implementation_commit") != B02_CANDIDATE_COMMIT
        or (bootstrap.get("evidence") or {}).get("sha256") != B02_EVIDENCE_SHA256
    ):
        raise SystemExit("GCR-0005 stopped W1/B02 boundary differs")


def load_authority(repo: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    packet, packet_payload = load_json(safe_path(repo, PACKET_PATH, label="GCR-0005 packet"), "GCR-0005 packet")
    approval, approval_payload = load_json(
        safe_path(repo, APPROVAL_PATH, label="GCR-0005 approval"), "GCR-0005 approval"
    )
    if sha256(packet_payload) != PACKET_SHA256 or taskctl.git_blob(repo, PACKET_COMMIT, PACKET_PATH) != packet_payload:
        raise SystemExit("GCR-0005 packet differs from its independently reviewed Git blob")
    validate_schema(repo, packet, REQUEST_SCHEMA_PATH, "GCR-0005 packet")
    validate_runtime(repo, approval, "GCR-0005 approval")
    introduction = taskctl.approval_introduction_commit(repo, APPROVAL_PATH)
    if introduction != APPROVAL_COMMIT or taskctl.git_blob(repo, introduction, APPROVAL_PATH) != approval_payload:
        raise SystemExit("GCR-0005 approval is absent, replaced, or edited after introduction")
    review_ref = (approval.get("independentReview") or {}).get("ledger") or {}
    review, review_payload = load_json(repo / str(review_ref.get("path") or ""), "GCR-0005 packet review")
    validate_runtime(repo, review, "GCR-0005 packet review")
    if (
        approval.get("packet") != {"path": PACKET_PATH, "sha256": PACKET_SHA256, "commit": PACKET_COMMIT}
        or approval.get("status") != "APPROVED"
        or approval.get("controlRecoveryId") != GCR_ID
        or review.get("candidateCommit") != PACKET_COMMIT
        or review.get("result") != "approved"
        or review.get("findings") != []
        or review.get("approvalAvailable") is not True
        or sha256(review_payload) != review_ref.get("sha256")
        or taskctl.git_blob(repo, str(review_ref.get("commit") or ""), str(review_ref.get("path") or ""))
        != review_payload
        or any(
            (approval.get("executionAuthority") or {}).get(key) is not False
            for key in (
                "reviewProjection",
                "b02Remediation",
                "amendment",
                "task",
                "waveResume",
                "holdRelease",
                "gateApproval",
            )
        )
        or (approval.get("executionAuthority") or {}).get("bootstrapOnly") is not True
        or not taskctl.git_is_ancestor(repo, PACKET_COMMIT, introduction)
        or not taskctl.git_is_ancestor(repo, str(review_ref.get("commit") or ""), introduction)
    ):
        raise SystemExit("GCR-0005 approval or packet-review authority is invalid")
    for reference in packet.get("files", []):
        relative = str(reference.get("path") or "")
        payload = safe_path(repo, relative, label="GCR-0005 packet file").read_bytes()
        if sha256(payload) != reference.get("sha256") or taskctl.git_blob(repo, PACKET_COMMIT, relative) != payload:
            raise SystemExit(f"GCR-0005 packet file binding differs: {relative}")
    for pattern in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", []):
        validate_scope_pattern(str(pattern))
    authority, authority_payload = load_json(repo / AUTHORITY_PATH, "GCR-0005 authority manifest")
    if sha256(authority_payload) != (packet.get("rootAuthority") or {}).get("authorityManifest", {}).get("sha256"):
        raise SystemExit("GCR-0005 authority manifest differs")
    frozen = authority.get("frozenSupplementReviewBoundary") or {}
    if (
        frozen.get("reviewedStateCommit") != REVIEWED_STATE_COMMIT
        or frozen.get("candidateCommit") != B02_CANDIDATE_COMMIT
        or (frozen.get("evidence") or {}).get("sha256") != B02_EVIDENCE_SHA256
        or (frozen.get("adverseLedger") or {}).get("sha256") != LEDGER_SHA256
    ):
        raise SystemExit("GCR-0005 frozen B02 authority differs")
    frozen_backlog = taskctl.git_blob(repo, REVIEWED_STATE_COMMIT, BACKLOG_PATH)
    if frozen_backlog is None or sha256(frozen_backlog) != BACKLOG_BEFORE_CANONICAL:
        raise SystemExit("GCR-0005 frozen reviewed backlog differs")
    supplement_authority = authority.get("supplementAuthority") or {}
    for key in (
        "packet",
        "approval",
        "scopeAddendumPacket",
        "scopeAddendumReview",
        "scopeAddendumApproval",
        "defectiveController",
    ):
        reference = supplement_authority.get(key) or {}
        relative = str(reference.get("path") or "")
        commit = str(reference.get("commit") or "")
        expected_hash = str(reference.get("sha256") or "")
        authority_blob = taskctl.git_blob(repo, commit, relative)
        if authority_blob is None or sha256(authority_blob) != expected_hash:
            raise SystemExit(f"GCR-0005 predecessor authority differs: {key}")
        live = safe_path(repo, relative, label=f"GCR-0005 {key} authority").read_bytes()
        if not git_worktree_equivalent(live, authority_blob) or sha256(live.replace(b"\r\n", b"\n")) != expected_hash:
            raise SystemExit(f"GCR-0005 live predecessor authority differs: {key}")
    evidence_payload = taskctl.git_blob(repo, REVIEWED_STATE_COMMIT, B02_EVIDENCE_PATH)
    if (
        evidence_payload is None
        or sha256(evidence_payload) != B02_EVIDENCE_SHA256
        or not git_worktree_equivalent((repo / B02_EVIDENCE_PATH).read_bytes(), evidence_payload)
    ):
        raise SystemExit("GCR-0005 frozen B02 evidence differs")
    live_backlog = (repo / BACKLOG_PATH).read_bytes()
    live_backlog_sha = sha256(live_backlog)
    expected_bootstrap_status = {
        BACKLOG_BEFORE_RAW: "REVIEW",
        BACKLOG_AFTER: "CHANGES_REQUESTED",
    }.get(live_backlog_sha)
    if expected_bootstrap_status is None:
        raise SystemExit("GCR-0005 live backlog is neither the exact predecessor nor exact successor")
    live_data = yaml.safe_load(live_backlog)
    validate_boundary(live_data, expected_status=expected_bootstrap_status)
    control = live_data.get("control_plane") or {}
    hold = _hold(live_data)
    bootstrap = _b02(live_data)
    supplement = next(item for item in hold.get("supplements", []) if item.get("id") == "GRR-0002.S02")
    if (
        control.get("revision") != 11
        or control.get("minimum_tool_revision") != 11
        or hold.get("status") != "ACTIVE"
        or supplement.get("packet_reference")
        != {
            "path": supplement_authority["packet"]["path"],
            "sha256": supplement_authority["packet"]["sha256"],
            "commit": supplement_authority["packet"]["commit"],
        }
        or supplement.get("approval_reference", {}).get("path") != supplement_authority["approval"]["path"]
        or supplement.get("approval_reference", {}).get("sha256") != supplement_authority["approval"]["sha256"]
        or bootstrap.get("id") != "GRR-0002.B02"
        or bootstrap.get("implementation_commit") != B02_CANDIDATE_COMMIT
        or (bootstrap.get("evidence") or {}).get("sha256") != B02_EVIDENCE_SHA256
    ):
        raise SystemExit("GCR-0005 live S02/addendum/recovery authority differs")
    validate_witness(repo)
    validate_adverse_ledger(repo)
    return approval, packet, introduction


def state_path(repo: Path) -> Path:
    return safe_path(
        repo,
        STATE_PATH,
        label="GCR-0005 state",
        prefix="planning/governance-control-recovery",
        require_exists=False,
    )


def evidence_path(attempt_id: str) -> str:
    return f"artifacts/evidence/governance-control-recovery/GCR-0005.B00.{attempt_id}.json"


def review_path(attempt_id: str) -> str:
    return f"planning/governance-control-recovery/GCR-0005.B00.review-{attempt_id}.json"


def _attempt_keys(state: dict[str, Any]) -> list[str]:
    attempts = state.get("attempts") or {}
    if not isinstance(attempts, dict):
        raise SystemExit("GCR-0005 completed attempts must be a map")
    keys = sorted(attempts, key=lambda key: int(key[1:]) if key.startswith("R") and key[1:].isdigit() else 10000)
    expected = [f"R{index:02d}" for index in range(1, len(keys) + 1)]
    if keys != expected or list(attempts) != keys:
        raise SystemExit("GCR-0005 completed attempts are duplicated, reordered, skipped, or malformed")
    return keys


def fold_findings(state: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    opened: dict[str, dict[str, Any]] = {}
    blocking: set[str] = set()
    seen: set[str] = set()
    for key in _attempt_keys(state):
        attempt = state["attempts"][key]
        for closure in attempt.get("closures", []):
            target = str(closure.get("findingId") or "")
            if target not in opened:
                raise SystemExit(f"GCR-0005 {key} closure targets no open prior finding")
            opened.pop(target)
        for finding in attempt.get("findings", []):
            finding_id = str(finding.get("id") or "")
            if not finding_id or finding_id in seen:
                raise SystemExit(f"GCR-0005 {key} finding identity is empty or duplicated")
            seen.add(finding_id)
            opened[finding_id] = finding
            if finding.get("blocking") is True:
                blocking.add(finding_id)
    return opened, blocking


def _git_document(repo: Path, commit: str, relative: str, label: str) -> tuple[dict[str, Any], bytes]:
    payload = taskctl.git_blob(repo, commit, relative)
    if payload is None:
        raise SystemExit(f"{label} Git blob is absent")
    document = strict_json(payload, label)
    if not isinstance(document, dict):
        raise SystemExit(f"{label} must be a JSON object")
    return document, payload


def _exact_parent(repo: Path, parent: str, commit: str, expected: dict[str, str], label: str) -> None:
    parents = git(repo, "rev-list", "--parents", "-n", "1", commit).split()
    if parents != [commit, parent]:
        raise SystemExit(f"{label} is not the exact direct child of {parent}")
    require_exact_commit_delta(repo, parent=parent, commit=commit, expected=expected, label=label)


def _first_descendant(repo: Path, commit: str) -> str | None:
    head = git(repo, "rev-parse", "HEAD")
    if commit == head:
        return None
    descendants = git(repo, "rev-list", "--ancestry-path", "--reverse", f"{commit}..{head}").splitlines()
    return descendants[0] if descendants else None


def changed_paths(repo: Path, base: str, candidate: str) -> list[str]:
    if base == candidate or not taskctl.git_is_ancestor(repo, base, candidate):
        raise SystemExit("GCR-0005 implementation candidate must strictly descend from its approval base")
    return sorted(line for line in git(repo, "diff", "--name-only", f"{base}..{candidate}", "--").splitlines() if line)


def validate_evidence_document(
    repo: Path,
    packet: dict[str, Any],
    document: dict[str, Any],
    *,
    candidate: str,
    attempt_id: str,
    prior_open: dict[str, dict[str, Any]],
) -> None:
    validate_runtime(repo, document, f"GCR-0005 {attempt_id} evidence")
    actual = changed_paths(repo, APPROVAL_COMMIT, candidate)
    patterns = [str(item) for item in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", [])]
    outside = [path for path in actual if not path_authorized(path, patterns)]
    protected = {
        BACKLOG_PATH,
        LEDGER_PATH,
        TRIGGER_PATH,
        B02_EVIDENCE_PATH,
        "planning/governance-recovery-requests/GRR-0002.S02.packet.json",
        "planning/governance-recovery-approvals/GRR-0002.S02.json",
        "planning/governance-recovery-approvals/GRR-0002.B02.scope-addendum.approval.json",
    }
    criteria = document.get("acceptanceCriteria") or []
    outcomes = document.get("requiredOutcomes") or []
    closures = document.get("closures") or []
    closure_ids = [str(item.get("findingId") or "") for item in closures]
    checks = document.get("checks") or []
    if (
        document.get("controlRecoveryId") != GCR_ID
        or document.get("bootstrapUnit") != BOOTSTRAP_ID
        or document.get("attemptId") != attempt_id
        or document.get("agent") != ACTOR
        or document.get("approvalCommit") != APPROVAL_COMMIT
        or document.get("baseCommit") != APPROVAL_COMMIT
        or document.get("candidateCommit") != candidate
        or document.get("branch") != BRANCH
        or document.get("changedPaths") != actual
        or outside
        or set(actual) & protected
        or [item.get("criterion") for item in criteria] != (packet.get("acceptanceCriteria") or [])
        or [item.get("criterion") for item in outcomes]
        != (packet.get("bootstrapUnit") or {}).get("requiredOutcomes", [])
        or document.get("unverifiedItems") != []
        or len(closure_ids) != len(set(closure_ids))
        or set(closure_ids) != set(prior_open)
        or not checks
        or len({item.get("command") for item in checks}) != len(checks)
        or any(item.get("result") != "passed" for item in checks)
    ):
        raise SystemExit("GCR-0005 evidence identity, scope, criteria, findings, or checks is invalid")


def validate_review_ledger(
    repo: Path,
    ledger: dict[str, Any],
    submission: dict[str, Any],
    *,
    reviewer: str,
    reviewed_state: str,
    prior_open: dict[str, dict[str, Any]],
    prior_ids: set[str],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    validate_runtime(repo, ledger, f"GCR-0005 {submission.get('attemptId')} review ledger")
    attempt_id = str(submission.get("attemptId") or "")
    findings = ledger.get("findings") or []
    closures = ledger.get("closures") or []
    ordering = [SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings]
    finding_ids = [str(item.get("id") or "") for item in findings]
    closure_ids = [str(item.get("findingId") or "") for item in closures]
    if (
        ledger.get("controlRecoveryId") != GCR_ID
        or ledger.get("bootstrapUnit") != BOOTSTRAP_ID
        or ledger.get("attemptId") != attempt_id
        or ledger.get("candidateCommit") != submission.get("candidateCommit")
        or ledger.get("reviewedStateCommit") != reviewed_state
        or ledger.get("reviewer") != reviewer
        or ledger.get("evidence")
        != {
            "path": (submission.get("evidence") or {}).get("path"),
            "sha256": (submission.get("evidence") or {}).get("sha256"),
            "commit": (submission.get("evidence") or {}).get("commit"),
        }
        or ordering != sorted(ordering)
        or len(finding_ids) != len(set(finding_ids))
        or set(finding_ids) & prior_ids
        or len(closure_ids) != len(set(closure_ids))
        or set(closure_ids) - set(prior_open)
    ):
        raise SystemExit("GCR-0005 review ledger differs from its frozen submission or append-only controls")
    result = str(ledger.get("result") or "")
    if result not in RESULT_STATUS:
        raise SystemExit("GCR-0005 review result is invalid")
    opened = {key: copy.deepcopy(value) for key, value in prior_open.items() if key not in closure_ids}
    blocking = {key for key, value in prior_open.items() if value.get("blocking") is True}
    for finding in findings:
        opened[str(finding["id"])] = copy.deepcopy(finding)
        if finding.get("blocking") is True:
            blocking.add(str(finding["id"]))
    if result == "approved" and (findings or set(opened) & blocking):
        raise SystemExit("GCR-0005 approval cannot introduce findings or retain an open blocker")
    return opened, blocking


def _projection_state(
    reviewed: dict[str, Any],
    *,
    attempt_id: str,
    attempt: dict[str, Any],
    opened: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    projected = copy.deepcopy(reviewed)
    projected["attempts"][attempt_id] = copy.deepcopy(attempt)
    result = str((attempt.get("review") or {}).get("result") or "")
    projected["status"] = RESULT_STATUS[result]
    projected["currentSubmission"] = None
    projected["latestReviewResult"] = result
    projected["openFindingIds"] = sorted(opened)
    return projected


def validate_history(
    repo: Path,
    state: dict[str, Any],
    packet: dict[str, Any],
    *,
    allow_uncommitted_projection: bool = False,
) -> None:
    validate_runtime(repo, state, "GCR-0005 state")
    expected_approval = {
        "path": APPROVAL_PATH,
        "sha256": sha256((repo / APPROVAL_PATH).read_bytes()),
        "commit": APPROVAL_COMMIT,
    }
    if state.get("approval") != expected_approval:
        raise SystemExit("GCR-0005 state approval authority differs")
    keys = _attempt_keys(state)
    opened: dict[str, dict[str, Any]] = {}
    blocking: set[str] = set()
    seen_ids: set[str] = set()
    prior_candidate: str | None = None
    expected_previous: dict[str, Any] = {}
    for index, key in enumerate(keys):
        attempt = state["attempts"][key]
        submission = attempt.get("submission") or {}
        review = attempt.get("review") or {}
        ledger_ref = attempt.get("ledger") or {}
        evidence = submission.get("evidence") or {}
        candidate = str(submission.get("candidateCommit") or "")
        evidence_commit = str(evidence.get("commit") or "")
        reviewed_state = str(review.get("reviewedStateCommit") or "")
        ledger_commit = str(ledger_ref.get("commit") or "")
        if (
            submission.get("attemptId") != key
            or submission.get("submittedBy") != ACTOR
            or submission.get("baseCommit") != APPROVAL_COMMIT
            or submission.get("branch") != BRANCH
            or submission.get("priorAttemptId") != (keys[index - 1] if index else None)
            or submission.get("openFindingIds") != sorted(opened)
            or evidence.get("path") != evidence_path(key)
        ):
            raise SystemExit(f"GCR-0005 {key} submission binding is invalid")
        if index >= 2:
            rca = submission.get("rootCauseAnalysis")
            if not isinstance(rca, dict) or not rca:
                raise SystemExit(f"GCR-0005 {key} requires a root-cause analysis")
        elif submission.get("rootCauseAnalysis") is not None:
            raise SystemExit(f"GCR-0005 {key} must not invent a root-cause analysis")
        if prior_candidate and (
            prior_candidate == candidate or not taskctl.git_is_ancestor(repo, prior_candidate, candidate)
        ):
            raise SystemExit(f"GCR-0005 {key} candidate is not a strict remediation descendant")
        prior_candidate = candidate
        _exact_parent(repo, candidate, evidence_commit, {evidence_path(key): "A"}, f"GCR-0005 {key} evidence commit")
        evidence_document, evidence_payload = _git_document(
            repo,
            evidence_commit,
            evidence_path(key),
            f"GCR-0005 {key} evidence",
        )
        if sha256(evidence_payload) != evidence.get("sha256"):
            raise SystemExit(f"GCR-0005 {key} evidence hash differs")
        validate_evidence_document(
            repo, packet, evidence_document, candidate=candidate, attempt_id=key, prior_open=opened
        )
        if submission.get("rootCauseAnalysis") != evidence_document.get("rootCauseAnalysis"):
            raise SystemExit(f"GCR-0005 {key} root-cause analysis differs from its evidence")
        _exact_parent(
            repo,
            evidence_commit,
            reviewed_state,
            {STATE_PATH: "A" if index == 0 else "M"},
            f"GCR-0005 {key} reviewed-state commit",
        )
        reviewed, _reviewed_payload = _git_document(repo, reviewed_state, STATE_PATH, f"GCR-0005 {key} reviewed state")
        validate_runtime(repo, reviewed, f"GCR-0005 {key} reviewed state")
        if (
            reviewed.get("status") != "REVIEW"
            or reviewed.get("attempts") != expected_previous
            or reviewed.get("currentSubmission") != submission
            or reviewed.get("latestReviewResult") is not None
            or reviewed.get("openFindingIds") != sorted(opened)
            or reviewed.get("application") is not None
        ):
            raise SystemExit(f"GCR-0005 {key} reviewed-state projection is invalid")
        ledger_relative = str(ledger_ref.get("path") or "")
        if ledger_relative != review_path(key):
            raise SystemExit(f"GCR-0005 {key} review ledger path is not canonical")
        _exact_parent(repo, reviewed_state, ledger_commit, {ledger_relative: "A"}, f"GCR-0005 {key} ledger commit")
        ledger, ledger_payload = _git_document(repo, ledger_commit, ledger_relative, f"GCR-0005 {key} review ledger")
        if sha256(ledger_payload) != ledger_ref.get("sha256"):
            raise SystemExit(f"GCR-0005 {key} review ledger hash differs")
        reviewer = str(review.get("reviewer") or "")
        opened_after, blocking_after = validate_review_ledger(
            repo,
            ledger,
            submission,
            reviewer=reviewer,
            reviewed_state=reviewed_state,
            prior_open=opened,
            prior_ids=seen_ids,
        )
        if (
            reviewer == ACTOR
            or review.get("result") != ledger.get("result")
            or review.get("notes") != ledger.get("notes", "")
            or attempt.get("findings") != (ledger.get("findings") or [])
            or attempt.get("closures") != (ledger.get("closures") or [])
        ):
            raise SystemExit(f"GCR-0005 {key} review/ledger projection differs")
        expected_projected = _projection_state(reviewed, attempt_id=key, attempt=attempt, opened=opened_after)
        projection_commit = _first_descendant(repo, ledger_commit)
        if projection_commit is None:
            if not allow_uncommitted_projection or index != len(keys) - 1 or state != expected_projected:
                raise SystemExit(f"GCR-0005 {key} state-only review projection commit is absent")
        else:
            _exact_parent(
                repo,
                ledger_commit,
                projection_commit,
                {STATE_PATH: "M"},
                f"GCR-0005 {key} state projection commit",
            )
            projected, _payload = _git_document(repo, projection_commit, STATE_PATH, f"GCR-0005 {key} projected state")
            if projected != expected_projected:
                raise SystemExit(f"GCR-0005 {key} projected state disagrees with the ledger")
        opened = opened_after
        blocking = blocking_after
        seen_ids.update(str(item.get("id")) for item in attempt.get("findings", []))
        expected_previous[key] = copy.deepcopy(attempt)
    current = state.get("currentSubmission")
    if current is not None:
        next_id = f"R{len(keys) + 1:02d}"
        if (
            state.get("status") != "REVIEW"
            or current.get("attemptId") != next_id
            or current.get("priorAttemptId") != (keys[-1] if keys else None)
            or current.get("openFindingIds") != sorted(opened)
            or state.get("latestReviewResult") is not None
            or state.get("openFindingIds") != sorted(opened)
            or state.get("application") is not None
        ):
            raise SystemExit("GCR-0005 pending submission is not the exact next RNN")
        evidence = current.get("evidence") or {}
        candidate = str(current.get("candidateCommit") or "")
        evidence_commit = str(evidence.get("commit") or "")
        _exact_parent(
            repo,
            candidate,
            evidence_commit,
            {evidence_path(next_id): "A"},
            f"GCR-0005 {next_id} evidence commit",
        )
        evidence_document, evidence_payload = _git_document(
            repo,
            evidence_commit,
            evidence_path(next_id),
            f"GCR-0005 {next_id} evidence",
        )
        if sha256(evidence_payload) != evidence.get("sha256"):
            raise SystemExit(f"GCR-0005 {next_id} evidence hash differs")
        validate_evidence_document(
            repo, packet, evidence_document, candidate=candidate, attempt_id=next_id, prior_open=opened
        )
        if current.get("rootCauseAnalysis") != evidence_document.get("rootCauseAnalysis"):
            raise SystemExit(f"GCR-0005 {next_id} root-cause analysis differs from its evidence")
        reviewed_state = git(repo, "log", "-1", "--format=%H", "--", STATE_PATH)
        _exact_parent(
            repo,
            evidence_commit,
            reviewed_state,
            {STATE_PATH: "A" if not keys else "M"},
            f"GCR-0005 {next_id} pending reviewed state",
        )
        reviewed, _payload = _git_document(repo, reviewed_state, STATE_PATH, f"GCR-0005 {next_id} pending state")
        if reviewed != state:
            raise SystemExit("GCR-0005 pending state differs from its state-only commit")
    elif keys:
        latest = str((state["attempts"][keys[-1]].get("review") or {}).get("result") or "")
        if (
            state.get("latestReviewResult") != latest
            or state.get("openFindingIds") != sorted(opened)
            or state.get("status") not in {RESULT_STATUS[latest], "APPLICATION_FINALIZATION", "APPLIED"}
        ):
            raise SystemExit("GCR-0005 latest result or open-finding projection is stale")
        if state.get("status") in {"APPROVED", "APPLICATION_FINALIZATION", "APPLIED"} and set(opened) & blocking:
            raise SystemExit("GCR-0005 approval retains an open blocking finding")
    elif state.get("status") != "READY":
        raise SystemExit("GCR-0005 state has neither completed attempts nor a pending submission")


def load_state(
    repo: Path,
    packet: dict[str, Any],
    *,
    required: bool,
    validate: bool = True,
) -> tuple[dict[str, Any] | None, bytes | None]:
    path = state_path(repo)
    if not path.exists():
        if required:
            raise SystemExit("GCR-0005 B00 state is absent")
        return None, None
    state, payload = load_json(path, "GCR-0005 state")
    validate_runtime(repo, state, "GCR-0005 state")
    if validate:
        validate_history(repo, state, packet)
    return state, payload


def require_workspace(repo: Path, *, transaction: bool = False) -> None:
    if git(repo, "branch", "--show-current") != BRANCH:
        raise SystemExit(f"GCR-0005 transitions require exact branch {BRANCH}")
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise SystemExit("GCR-0005 transitions refuse staged changes")
    validate_witness(repo)
    validate_adverse_ledger(repo)
    untracked = set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    allowed = {TRIGGER_PATH}
    if transaction:
        allowed.update(present_transaction_artifacts(repo))
    if untracked != allowed:
        difference = sorted(untracked ^ allowed)
        raise SystemExit(f"GCR-0005 untracked-path boundary differs: {difference[0] if difference else '<unknown>'}")
    dirty = set(git(repo, "diff", "--name-only", "HEAD", "--").splitlines())
    allowed_dirty = set(FINAL_PATHS) if transaction else set()
    if dirty - allowed_dirty:
        raise SystemExit(f"GCR-0005 refuses unrelated tracked dirt: {sorted(dirty - allowed_dirty)[0]}")
    if not transaction and dirty:
        raise SystemExit("GCR-0005 transitions require an exact tracked commit")


def freeze_submission(args: argparse.Namespace, *, remediation: bool) -> None:
    _approval, packet, base = load_authority(args.repo)
    if present_transaction_artifacts(args.repo):
        recover_transaction(args.repo)
    state, _payload = load_state(args.repo, packet, required=False)
    if remediation:
        if state is None or state.get("status") not in {"CHANGES_REQUESTED", "BLOCKED"}:
            raise SystemExit("GCR-0005 resubmission requires an adverse completed review")
    elif state is not None:
        raise SystemExit("GCR-0005 initial submission already exists")
    if not remediation and str(args.approval_commit) != base:
        raise SystemExit("GCR-0005 approval-commit argument differs from the immutable introduction")
    if args.agent != ACTOR:
        raise SystemExit(f"GCR-0005 implementer must be exact actor {ACTOR}")
    require_workspace(args.repo)
    attempts = (state or {}).get("attempts") or {}
    attempt_id = f"R{len(attempts) + 1:02d}"
    candidate = str(args.implementation_commit)
    head = git(args.repo, "rev-parse", "HEAD")
    relative = str(args.evidence)
    if relative != evidence_path(attempt_id):
        raise SystemExit(f"GCR-0005 evidence path must be {evidence_path(attempt_id)}")
    _exact_parent(
        repo=args.repo,
        parent=candidate,
        commit=head,
        expected={relative: "A"},
        label=f"GCR-0005 {attempt_id} evidence-only commit",
    )
    document, payload = _git_document(args.repo, head, relative, f"GCR-0005 {attempt_id} evidence")
    opened, _blocking = fold_findings(state or {"attempts": {}})
    validate_evidence_document(
        args.repo,
        packet,
        document,
        candidate=candidate,
        attempt_id=attempt_id,
        prior_open=opened,
    )
    if remediation:
        prior_candidate = str((attempts[f"R{len(attempts):02d}"]["submission"]).get("candidateCommit") or "")
        if prior_candidate == candidate or not taskctl.git_is_ancestor(args.repo, prior_candidate, candidate):
            raise SystemExit("GCR-0005 remediation candidate must be a strict descendant")
    if len(attempts) >= 2:
        rca = document.get("rootCauseAnalysis")
        if not isinstance(rca, dict) or not rca:
            raise SystemExit("GCR-0005 third and later submissions require root-cause analysis")
    elif document.get("rootCauseAnalysis") is not None:
        raise SystemExit("GCR-0005 R01/R02 evidence must not invent root-cause analysis")
    submission = {
        "attemptId": attempt_id,
        "submittedBy": ACTOR,
        "submittedAt": taskctl.utc_now(),
        "candidateCommit": candidate,
        "baseCommit": APPROVAL_COMMIT,
        "branch": BRANCH,
        "evidence": {"path": relative, "sha256": sha256(payload), "commit": head},
        "priorAttemptId": f"R{len(attempts):02d}" if attempts else None,
        "openFindingIds": sorted(opened),
        "rootCauseAnalysis": document.get("rootCauseAnalysis"),
    }
    if state is None:
        state = {
            "schemaVersion": "5.0-control-recovery-state",
            "documentType": "governance-control-recovery-bootstrap-state",
            "controlRecoveryId": GCR_ID,
            "bootstrapUnit": BOOTSTRAP_ID,
            "status": "REVIEW",
            "approval": {
                "path": APPROVAL_PATH,
                "sha256": sha256((args.repo / APPROVAL_PATH).read_bytes()),
                "commit": APPROVAL_COMMIT,
            },
            "attempts": {},
            "currentSubmission": submission,
            "latestReviewResult": None,
            "openFindingIds": [],
            "application": None,
        }
    else:
        state["status"] = "REVIEW"
        state["currentSubmission"] = submission
        state["latestReviewResult"] = None
    validate_runtime(args.repo, state, "GCR-0005 submission state")
    write_json_atomic(args.repo / STATE_PATH, state)
    print(f"Submitted {BOOTSTRAP_ID}/{attempt_id}; commit the state alone before independent review")


def command_review(args: argparse.Namespace) -> None:
    _approval, packet, _base = load_authority(args.repo)
    state, _payload = load_state(args.repo, packet, required=True)
    assert state is not None
    if state.get("status") != "REVIEW" or not state.get("currentSubmission"):
        raise SystemExit("GCR-0005 has no pending frozen submission")
    require_workspace(args.repo)
    reviewer = str(args.reviewer).strip()
    if not reviewer or reviewer != args.reviewer or reviewer == ACTOR:
        raise SystemExit("GCR-0005 reviewer must be normalized and independent")
    submission = copy.deepcopy(state["currentSubmission"])
    attempt_id = str(submission["attemptId"])
    relative = str(args.ledger)
    if relative != review_path(attempt_id):
        raise SystemExit(f"GCR-0005 review ledger path must be {review_path(attempt_id)}")
    ledger_commit = git(args.repo, "rev-parse", "HEAD")
    ledger, payload = _git_document(args.repo, ledger_commit, relative, f"GCR-0005 {attempt_id} review ledger")
    reviewed_state = str(ledger.get("reviewedStateCommit") or "")
    _exact_parent(
        args.repo,
        reviewed_state,
        ledger_commit,
        {relative: "A"},
        f"GCR-0005 {attempt_id} ledger-only commit",
    )
    reviewed, _reviewed_payload = _git_document(
        args.repo,
        reviewed_state,
        STATE_PATH,
        f"GCR-0005 {attempt_id} reviewed state",
    )
    if reviewed != state:
        raise SystemExit("GCR-0005 review ledger does not bind the live frozen state")
    opened, _blocking = fold_findings(state)
    prior_ids = {
        str(finding.get("id")) for attempt in state["attempts"].values() for finding in attempt.get("findings", [])
    }
    opened_after, _blocking_after = validate_review_ledger(
        args.repo,
        ledger,
        submission,
        reviewer=reviewer,
        reviewed_state=reviewed_state,
        prior_open=opened,
        prior_ids=prior_ids,
    )
    attempt = {
        "submission": submission,
        "review": {
            "reviewer": reviewer,
            "result": ledger["result"],
            "reviewedAt": taskctl.utc_now(),
            "reviewedStateCommit": reviewed_state,
            "notes": ledger.get("notes", ""),
        },
        "ledger": {"path": relative, "sha256": sha256(payload), "commit": ledger_commit},
        "findings": copy.deepcopy(ledger.get("findings") or []),
        "closures": copy.deepcopy(ledger.get("closures") or []),
    }
    state = _projection_state(
        state,
        attempt_id=attempt_id,
        attempt=attempt,
        opened=opened_after,
    )
    validate_history(args.repo, state, packet, allow_uncommitted_projection=True)
    write_json_atomic(args.repo / STATE_PATH, state)
    print(f"Recorded {BOOTSTRAP_ID}/{attempt_id} as {state['status']}; commit only the state projection")


def frozen_predecessor_backlog(repo: Path) -> bytes:
    canonical = taskctl.git_blob(repo, REVIEWED_STATE_COMMIT, BACKLOG_PATH)
    if canonical is None or sha256(canonical) != BACKLOG_BEFORE_CANONICAL:
        raise SystemExit("GCR-0005 frozen predecessor backlog Git blob differs")
    raw = canonical.replace(b"\n", b"\r\n")
    if sha256(raw) != BACKLOG_BEFORE_RAW:
        raise SystemExit("GCR-0005 frozen predecessor raw backlog cannot be reproduced")
    return raw


def derive_successor_backlog(repo: Path) -> bytes:
    predecessor = frozen_predecessor_backlog(repo)
    data = yaml.safe_load(predecessor)
    validate_boundary(data, expected_status="REVIEW")
    ledger, _ledger_payload = validate_adverse_ledger(repo)
    bootstrap = _b02(data)
    current = copy.deepcopy(bootstrap.get("current_submission") or {})
    if (
        current.get("attempt_id") != "R01"
        or current.get("candidate_commit") != B02_CANDIDATE_COMMIT
        or current.get("evidence_sha256") != B02_EVIDENCE_SHA256
        or bootstrap.get("attempts") != []
    ):
        raise SystemExit("GCR-0005 frozen B02 submission differs")
    review = {
        "reviewer": ledger["reviewer"],
        "result": ledger["result"],
        "reviewed_at": PROJECTION_TIMESTAMP,
        "notes": ledger["notes"],
    }
    bootstrap["attempts"].append(
        {
            "id": current["attempt_id"],
            "implementer": bootstrap["implementer"],
            "implementation_commit": bootstrap["implementation_commit"],
            "submission_branch": bootstrap["submission_branch"],
            "evidence": copy.deepcopy(bootstrap["evidence"]),
            "review": review,
            "ledger": {"path": LEDGER_PATH, "sha256": LEDGER_SHA256},
        }
    )
    bootstrap["status"] = "CHANGES_REQUESTED"
    bootstrap["review"] = review
    bootstrap["current_submission"] = None
    successor = yaml.safe_dump(
        taskctl.serializable_backlog(data),
        sort_keys=False,
        allow_unicode=True,
        width=120,
    ).encode()
    if sha256(successor) != BACKLOG_AFTER or sha256(successor.replace(b"\r\n", b"\n")) != BACKLOG_AFTER:
        raise SystemExit("GCR-0005 ledger-derived successor hash differs")
    validate_boundary(yaml.safe_load(successor), expected_status="CHANGES_REQUESTED")
    return successor


def bridge_recovery_index(payload: bytes) -> bytes:
    before = b"Bootstrap GRR-0002.B00: APPROVED; supplements: 2</p>"
    after = b"Bootstrap GRR-0002.B00: APPROVED; supplements: 2; latest GRR-0002.B02: CHANGES_REQUESTED</p>"
    if after in payload:
        if before in payload:
            raise SystemExit("GCR-0005 recovery-index bridge is duplicated")
        return payload
    if before not in payload:
        raise SystemExit("GCR-0005 recovery-index projection marker cannot be placed")
    return payload.replace(before, after, 1)


def canonical_approved_state(
    repo: Path,
    state: dict[str, Any],
    state_payload: bytes,
) -> str:
    if (
        state.get("status") != "APPROVED"
        or state.get("currentSubmission") is not None
        or state.get("latestReviewResult") != "approved"
        or state.get("openFindingIds") != []
        or not state.get("attempts")
    ):
        raise SystemExit("GCR-0005 application requires an independently APPROVED B00")
    approved = git(repo, "log", "-1", "--format=%H", "--", STATE_PATH)
    if taskctl.git_blob(repo, approved, STATE_PATH) != state_payload:
        raise SystemExit("GCR-0005 approved state differs from its canonical state-only projection commit")
    latest_key = _attempt_keys(state)[-1]
    ledger_commit = str((state["attempts"][latest_key].get("ledger") or {}).get("commit") or "")
    _exact_parent(repo, ledger_commit, approved, {STATE_PATH: "M"}, "GCR-0005 approved state projection")
    return approved


def application_ledger_reference() -> dict[str, Any]:
    return {
        "path": LEDGER_PATH,
        "sha256": LEDGER_SHA256,
        "commit": LEDGER_COMMIT,
        "reviewedStateCommit": REVIEWED_STATE_COMMIT,
        "candidateCommit": B02_CANDIDATE_COMMIT,
        "evidenceSha256": B02_EVIDENCE_SHA256,
        "result": "changes-requested",
    }


def validate_application_evidence(
    repo: Path,
    document: dict[str, Any],
    *,
    approved_state: str,
    application_commit: str,
) -> None:
    validate_runtime(repo, document, "GCR-0005 application evidence")
    if (
        document.get("approvedStateCommit") != approved_state
        or document.get("applicationBaseCommit") != approved_state
        or document.get("ledger") != application_ledger_reference()
        or document.get("ledgerBytePreserved") is not True
        or document.get("openFindingIds") != ["GRR-0002.B02-R01-F01"]
        or document.get("changedPaths") != FINAL_PATHS
        or document.get("unverifiedItems") != []
        or document.get("ordinaryExecutionAuthority") is not False
        or any(item.get("result") != "passed" for item in document.get("checks", []))
    ):
        raise SystemExit("GCR-0005 application evidence authority, checks, or scope differs")
    _exact_parent(
        repo,
        approved_state,
        application_commit,
        {APPLICATION_EVIDENCE_PATH: "A"},
        "GCR-0005 application-evidence commit",
    )


def authenticate_application_authority(
    repo: Path,
    *,
    expected_application: str,
) -> tuple[dict[str, Any], bytes, str, dict[str, Any], bytes]:
    _approval, packet, _base = load_authority(repo)
    state, state_payload = load_state(repo, packet, required=True)
    assert state is not None and state_payload is not None
    approved = canonical_approved_state(repo, state, state_payload)
    evidence, evidence_payload = _git_document(
        repo,
        expected_application,
        APPLICATION_EVIDENCE_PATH,
        "GCR-0005 application evidence",
    )
    validate_application_evidence(
        repo,
        evidence,
        approved_state=approved,
        application_commit=expected_application,
    )
    if taskctl.git_blob(repo, expected_application, STATE_PATH) != state_payload:
        raise SystemExit("GCR-0005 application commit does not inherit the canonical approved state")
    return state, state_payload, approved, evidence, evidence_payload


def _safe_extract_archive(payload: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit("GCR-0005 Git archive contains an unsafe path")
        archive.extractall(destination, filter="data")


def stage_successor_files(repo: Path, application_commit: str, backlog: bytes) -> dict[str, bytes]:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", application_commit],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise SystemExit("GCR-0005 could not materialize the application-evidence tree")
    with tempfile.TemporaryDirectory(prefix="gcr5-stage-") as temporary:
        stage = Path(temporary)
        _safe_extract_archive(archive.stdout, stage)
        (stage / BACKLOG_PATH).write_bytes(backlog)
        commands = (
            [sys.executable, str(repo / "tools/backlog_views.py"), "--repo", str(stage)],
            [sys.executable, str(repo / "tools/plan_review_site.py"), "--repo", str(stage)],
        )
        for command in commands:
            result = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise SystemExit(f"GCR-0005 deterministic view staging failed: {result.stdout}{result.stderr}")

        def staged_payload(relative: str) -> bytes:
            payload = (stage / relative).read_bytes()
            replacements = (
                (stage.resolve().as_uri().encode(), repo.resolve().as_uri().encode()),
                (stage.resolve().as_posix().encode(), repo.resolve().as_posix().encode()),
                (str(stage.resolve()).encode(), str(repo.resolve()).encode()),
            )
            for source, destination in replacements:
                payload = payload.replace(source, destination)
            if relative == "planning/review-site/recoveries/index.html":
                payload = bridge_recovery_index(payload)
            return payload

        changed = sorted(
            relative
            for relative in GENERATED_PATHS
            if (stage / relative).is_file()
            and not git_worktree_equivalent(
                staged_payload(relative),
                taskctl.git_blob(repo, application_commit, relative),
            )
        )
        if changed != sorted(GENERATED_PATHS):
            raise SystemExit(f"GCR-0005 deterministic view delta differs: {changed}")
        return {BACKLOG_PATH: backlog, **{relative: staged_payload(relative) for relative in GENERATED_PATHS}}


def transaction_document(
    repo: Path,
    *,
    approved_state: str,
    state_payload: bytes,
    application_commit: str,
    evidence_payload: bytes,
) -> dict[str, Any]:
    return {
        "schemaVersion": "5.0-control-recovery-transaction",
        "documentType": "governance-control-recovery-review-transition-transaction",
        "controlRecoveryId": GCR_ID,
        "bootstrapUnit": BOOTSTRAP_ID,
        "status": "PREPARED",
        "actor": ACTOR,
        "branch": BRANCH,
        "packetAuthority": {"path": PACKET_PATH, "sha256": PACKET_SHA256, "commit": PACKET_COMMIT},
        "approvalAuthority": {
            "path": APPROVAL_PATH,
            "sha256": sha256((repo / APPROVAL_PATH).read_bytes()),
            "commit": APPROVAL_COMMIT,
        },
        "approvedStateAuthority": {
            "path": STATE_PATH,
            "sha256": sha256(state_payload),
            "commit": approved_state,
            "status": "APPROVED",
        },
        "applicationEvidenceAuthority": {
            "path": APPLICATION_EVIDENCE_PATH,
            "sha256": sha256(evidence_payload),
            "commit": application_commit,
        },
        "hold": {"id": HOLD_ID, "status": "ACTIVE", "controlRevision": 11, "minimumToolRevision": 11},
        "witness": trigger_reference(),
        "reviewedSubmission": {
            "reviewedStateCommit": REVIEWED_STATE_COMMIT,
            "candidateCommit": B02_CANDIDATE_COMMIT,
            "evidenceSha256": B02_EVIDENCE_SHA256,
            "attemptId": "R01",
            "status": "REVIEW",
        },
        "lockPath": LOCK_PATH,
        "transactionPath": TRANSACTION_PATH,
        "backlogPath": BACKLOG_PATH,
        "backlogNextPath": BACKLOG_NEXT_PATH,
        "backlogBeforeRawSha256": BACKLOG_BEFORE_RAW,
        "backlogBeforeCanonicalSha256": BACKLOG_BEFORE_CANONICAL,
        "backlogAfterRawSha256": BACKLOG_AFTER,
        "backlogAfterCanonicalSha256": BACKLOG_AFTER,
        "ledger": {
            "path": LEDGER_PATH,
            "sha256": LEDGER_SHA256,
            "commit": LEDGER_COMMIT,
            "reviewedStateCommit": REVIEWED_STATE_COMMIT,
            "result": "changes-requested",
            "openFindingIds": ["GRR-0002.B02-R01-F01"],
            "bytePreserved": True,
        },
        "projectionTimestamp": PROJECTION_TIMESTAMP,
        "generatedPaths": GENERATED_PATHS,
        "cas": {"rawBytes": True, "canonicalContent": True, "staleWriterDenied": True, "exactSuccessorOnly": True},
        "durability": {
            "exclusiveLock": True,
            "flushSuccessor": True,
            "flushManifest": True,
            "replaceExistingWriteThrough": True,
            "flushBacklog": True,
            "flushGeneratedFiles": True,
            "flushDirectories": True,
        },
        "recovery": {
            "allowedTerminalStates": ["EXACT_PREDECESSOR", "EXACT_SUCCESSOR"],
            "dirtyWorkspaceDenied": True,
            "staleOrSubstitutedDenied": True,
            "idempotent": True,
            "cleanupAfterValidationOnly": True,
        },
        "finalization": {
            "directChildOfApplicationEvidence": True,
            "exactChangedPaths": FINAL_PATHS,
            "ledgerUnchanged": True,
            "ordinaryExecutionStillDenied": True,
        },
        "publicationOrder": [
            "exclusive-lock",
            "durable-successor",
            "durable-manifest",
            "replace-backlog",
            "generate-views",
            "validate-exact-state",
            "flush",
            "commit-direct-child",
            "cleanup",
        ],
        "ordinaryExecutionAuthority": False,
    }


def transaction_artifacts(repo: Path) -> dict[str, Path]:
    return {relative: _artifact_path(repo, relative) for relative in (LOCK_PATH, TRANSACTION_PATH, BACKLOG_NEXT_PATH)}


def present_transaction_artifacts(repo: Path) -> list[str]:
    return [relative for relative, path in transaction_artifacts(repo).items() if os.path.lexists(path)]


def application_anchor(
    *,
    approved_state: str,
    application_commit: str,
    predecessor: dict[str, bytes],
    successor: dict[str, bytes],
) -> dict[str, Any]:
    return {
        "schemaVersion": "5.0-control-recovery-snapshot-anchor",
        "documentType": "governance-control-recovery-seven-path-anchor",
        "controlRecoveryId": GCR_ID,
        "bootstrapUnit": BOOTSTRAP_ID,
        "actor": ACTOR,
        "branch": BRANCH,
        "approvedStateCommit": approved_state,
        "applicationEvidenceCommit": application_commit,
        "paths": FINAL_PATHS,
        "snapshots": {
            relative: {
                "predecessorSha256": sha256(predecessor[relative]),
                "predecessorBase64": base64.b64encode(predecessor[relative]).decode("ascii"),
                "successorSha256": sha256(successor[relative]),
                "successorBase64": base64.b64encode(successor[relative]).decode("ascii"),
            }
            for relative in FINAL_PATHS
        },
    }


def _decode_snapshot(value: Any, *, label: str) -> bytes:
    try:
        return base64.b64decode(str(value).encode("ascii"), validate=True)
    except (UnicodeError, ValueError) as exc:
        raise SystemExit(f"GCR-0005 {label} snapshot is invalid") from exc


def validate_anchor(repo: Path, anchor: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, bytes], str, str]:
    expected_keys = {
        "schemaVersion",
        "documentType",
        "controlRecoveryId",
        "bootstrapUnit",
        "actor",
        "branch",
        "approvedStateCommit",
        "applicationEvidenceCommit",
        "paths",
        "snapshots",
    }
    approved = str(anchor.get("approvedStateCommit") or "")
    application = str(anchor.get("applicationEvidenceCommit") or "")
    if (
        set(anchor) != expected_keys
        or anchor.get("schemaVersion") != "5.0-control-recovery-snapshot-anchor"
        or anchor.get("documentType") != "governance-control-recovery-seven-path-anchor"
        or anchor.get("controlRecoveryId") != GCR_ID
        or anchor.get("bootstrapUnit") != BOOTSTRAP_ID
        or anchor.get("actor") != ACTOR
        or anchor.get("branch") != BRANCH
        or anchor.get("paths") != FINAL_PATHS
        or set(anchor.get("snapshots") or {}) != set(FINAL_PATHS)
        or git(repo, "rev-parse", "HEAD") != application
    ):
        raise SystemExit("GCR-0005 recovery anchor identity or HEAD binding is invalid")
    _state, _state_payload, canonical_approved, _evidence, _evidence_payload = authenticate_application_authority(
        repo,
        expected_application=application,
    )
    if approved != canonical_approved:
        raise SystemExit("GCR-0005 recovery anchor substitutes the canonical approved state")
    expected_successor = stage_successor_files(repo, application, derive_successor_backlog(repo))
    predecessor: dict[str, bytes] = {}
    successor: dict[str, bytes] = {}
    for relative in FINAL_PATHS:
        record = anchor["snapshots"][relative]
        if set(record) != {
            "predecessorSha256",
            "predecessorBase64",
            "successorSha256",
            "successorBase64",
        }:
            raise SystemExit(f"GCR-0005 anchor has unexpected snapshot fields: {relative}")
        predecessor[relative] = _decode_snapshot(record["predecessorBase64"], label=f"{relative} predecessor")
        successor[relative] = _decode_snapshot(record["successorBase64"], label=f"{relative} successor")
        if (
            sha256(predecessor[relative]) != record["predecessorSha256"]
            or sha256(successor[relative]) != record["successorSha256"]
            or sha256(predecessor[relative]) != PREDECESSOR_RAW_SHA256[relative]
            or not git_worktree_equivalent(
                predecessor[relative],
                taskctl.git_blob(repo, application, relative),
            )
            or successor[relative] != expected_successor[relative]
        ):
            raise SystemExit(f"GCR-0005 anchor snapshot or application tree differs: {relative}")
    if sha256(predecessor[BACKLOG_PATH]) != BACKLOG_BEFORE_RAW or sha256(successor[BACKLOG_PATH]) != BACKLOG_AFTER:
        raise SystemExit("GCR-0005 anchor backlog boundaries differ")
    return predecessor, successor, approved, application


@contextmanager
def transaction_lock(repo: Path, *, anchor: dict[str, Any] | None = None, recover: bool = False) -> Iterator[None]:
    path = transaction_artifacts(repo)[LOCK_PATH]
    if os.path.lexists(path):
        if not recover or not path.is_file() or path.is_symlink():
            raise SystemExit("GCR-0005 application lock already exists or is redirected")
        yield
        return
    if recover or anchor is None:
        raise SystemExit("GCR-0005 application requires an authenticated snapshot anchor")
    write_new_durable(path, (json.dumps(anchor, indent=2, ensure_ascii=False) + "\n").encode())
    adoption_fault_boundary("gcr5-lock-durable")
    yield


def load_anchor(repo: Path) -> tuple[dict[str, bytes], dict[str, bytes], str, str]:
    path = transaction_artifacts(repo)[LOCK_PATH]
    if not path.is_file() or path.is_symlink():
        raise SystemExit("GCR-0005 recovery anchor is absent or redirected")
    anchor, _payload = load_json(path, "GCR-0005 recovery anchor")
    return validate_anchor(repo, anchor)


def _validate_live_pair(repo: Path, predecessor: dict[str, bytes], successor: dict[str, bytes]) -> None:
    for relative in FINAL_PATHS:
        path = repo / relative
        if not path.is_file() or path.is_symlink() or getattr(os.path, "isjunction", lambda _path: False)(path):
            raise SystemExit(f"GCR-0005 protected path is absent or redirected: {relative}")
        if path.read_bytes() not in {predecessor[relative], successor[relative]}:
            raise SystemExit(f"GCR-0005 protected path is stale or substituted: {relative}")


def _publish_snapshot(repo: Path, target: dict[str, bytes], *, label: str, lock_held: bool = False) -> None:
    scratch = transaction_artifacts(repo)[BACKLOG_NEXT_PATH]
    scratch.parent.mkdir(parents=True, exist_ok=True)

    def publish() -> None:
        for relative in FINAL_PATHS:
            destination = repo / relative
            if destination.read_bytes() == target[relative]:
                continue
            if os.path.lexists(scratch):
                if not scratch.is_file() or scratch.is_symlink():
                    raise SystemExit("GCR-0005 scratch path is redirected")
                unlink_durable(scratch)
            write_new_durable(scratch, target[relative])
            move_write_through(scratch, destination)
            fsync_directory(destination.parent)
            adoption_fault_boundary(f"gcr5-{label}-{PurePosixPath(relative).name}")
        for relative in FINAL_PATHS:
            if (repo / relative).read_bytes() != target[relative]:
                raise SystemExit(f"GCR-0005 {label} publication differs: {relative}")

    if lock_held:
        publish()
    else:
        with taskctl.exclusive_backlog_lock(repo / BACKLOG_PATH):
            publish()


def cleanup_transaction(repo: Path) -> None:
    for relative in (TRANSACTION_PATH, BACKLOG_NEXT_PATH, LOCK_PATH):
        path = transaction_artifacts(repo)[relative]
        if os.path.lexists(path):
            if not path.is_file() or path.is_symlink():
                raise SystemExit(f"GCR-0005 transaction artifact is redirected: {relative}")
            unlink_durable(path)
            adoption_fault_boundary(f"gcr5-cleanup-{PurePosixPath(relative).name}")


def validate_transaction_authority(
    repo: Path,
    transaction: dict[str, Any],
    *,
    approved: str,
    application: str,
) -> None:
    validate_transaction(repo, transaction)
    _state, state_payload, canonical_approved, _evidence, evidence_payload = authenticate_application_authority(
        repo,
        expected_application=application,
    )
    if approved != canonical_approved:
        raise SystemExit("GCR-0005 transaction substitutes the canonical approved state")
    expected = transaction_document(
        repo,
        approved_state=approved,
        state_payload=state_payload,
        application_commit=application,
        evidence_payload=evidence_payload,
    )
    if transaction != expected:
        raise SystemExit("GCR-0005 application transaction differs from exact authority")


def complete_transaction(
    repo: Path,
    transaction: dict[str, Any],
    *,
    validated_anchor: tuple[dict[str, bytes], dict[str, bytes], str, str] | None = None,
) -> None:
    predecessor, successor, approved, application = validated_anchor or load_anchor(repo)
    validate_transaction_authority(repo, transaction, approved=approved, application=application)
    _validate_live_pair(repo, predecessor, successor)
    _publish_snapshot(repo, successor, label="successor", lock_held=True)
    adoption_fault_boundary("gcr5-seven-path-successor-durable")
    validate_boundary(yaml.safe_load((repo / BACKLOG_PATH).read_bytes()), expected_status="CHANGES_REQUESTED")
    if sha256((repo / BACKLOG_PATH).read_bytes()) != BACKLOG_AFTER:
        raise SystemExit("GCR-0005 published backlog does not equal the exact successor")
    fsync_directory(repo / "planning")
    fsync_directory(repo / "docs")
    cleanup_transaction(repo)


def restore_predecessor(repo: Path, predecessor: dict[str, bytes], successor: dict[str, bytes]) -> None:
    _validate_live_pair(repo, predecessor, successor)
    _publish_snapshot(repo, predecessor, label="predecessor", lock_held=True)
    cleanup_transaction(repo)


def recover_transaction(repo: Path) -> str:
    present = present_transaction_artifacts(repo)
    if not present:
        return "ABSENT"
    with taskctl.exclusive_backlog_lock(repo / BACKLOG_PATH):
        require_workspace(repo, transaction=True)
        with transaction_lock(repo, recover=True):
            predecessor, successor, approved, application = load_anchor(repo)
            _validate_live_pair(repo, predecessor, successor)
            manifest = transaction_artifacts(repo)[TRANSACTION_PATH]
            if not manifest.exists():
                restore_predecessor(repo, predecessor, successor)
                return "RESTORED_PREDECESSOR"
            if not manifest.is_file() or manifest.is_symlink():
                raise SystemExit("GCR-0005 transaction manifest is redirected")
            transaction, _payload = load_json(manifest, "GCR-0005 application transaction")
            validate_transaction_authority(repo, transaction, approved=approved, application=application)
            complete_transaction(
                repo,
                transaction,
                validated_anchor=(predecessor, successor, approved, application),
            )
    return "COMPLETED_SUCCESSOR"


def command_apply(args: argparse.Namespace) -> None:
    _approval, _packet, _base = load_authority(args.repo)
    if present_transaction_artifacts(args.repo):
        recover_transaction(args.repo)
    if args.agent != ACTOR:
        raise SystemExit(f"GCR-0005 application actor must be {ACTOR}")
    if str(args.evidence) != APPLICATION_EVIDENCE_PATH:
        raise SystemExit(f"GCR-0005 application evidence path must be {APPLICATION_EVIDENCE_PATH}")
    application = git(args.repo, "rev-parse", "HEAD")
    with taskctl.exclusive_backlog_lock(args.repo / BACKLOG_PATH):
        require_workspace(args.repo)
        _state, state_payload, approved, _evidence, evidence_payload = authenticate_application_authority(
            args.repo,
            expected_application=application,
        )
        if str(args.approved_state_commit) != approved:
            raise SystemExit("GCR-0005 approved-state argument differs from the canonical projection commit")
        successor_backlog = derive_successor_backlog(args.repo)
        successor = stage_successor_files(args.repo, application, successor_backlog)
        predecessor = {relative: (args.repo / relative).read_bytes() for relative in FINAL_PATHS}
        if any(
            sha256(payload) != PREDECESSOR_RAW_SHA256[relative]
            or not git_worktree_equivalent(payload, taskctl.git_blob(args.repo, application, relative))
            for relative, payload in predecessor.items()
        ):
            raise SystemExit("GCR-0005 seven-path predecessor differs from the exact application-evidence tree")
        transaction = transaction_document(
            args.repo,
            approved_state=approved,
            state_payload=state_payload,
            application_commit=application,
            evidence_payload=evidence_payload,
        )
        validate_transaction(args.repo, transaction)
        anchor = application_anchor(
            approved_state=approved,
            application_commit=application,
            predecessor=predecessor,
            successor=successor,
        )
        artifacts = transaction_artifacts(args.repo)
        with transaction_lock(args.repo, anchor=anchor):
            write_new_durable(artifacts[BACKLOG_NEXT_PATH], successor[BACKLOG_PATH])
            adoption_fault_boundary("gcr5-successor-durable")
            write_new_durable(
                artifacts[TRANSACTION_PATH],
                (json.dumps(transaction, indent=2, ensure_ascii=False) + "\n").encode(),
            )
            adoption_fault_boundary("gcr5-transaction-durable")
            complete_transaction(args.repo, transaction)
    print("Applied exact seven-path B02 R01 CHANGES_REQUESTED projection; commit only those seven paths")


def validate_finalization(repo: Path) -> str:
    final = git(repo, "rev-parse", "HEAD")
    parents = git(repo, "rev-list", "--parents", "-n", "1", final).split()
    if len(parents) != 2:
        raise SystemExit("GCR-0005 finalization must have exactly one parent")
    application = parents[1]
    _exact_parent(
        repo,
        application,
        final,
        {relative: "M" for relative in FINAL_PATHS},
        "GCR-0005 exact seven-path finalization",
    )
    authenticate_application_authority(repo, expected_application=application)
    expected = stage_successor_files(repo, application, derive_successor_backlog(repo))
    for relative in FINAL_PATHS:
        worktree = safe_path(repo, relative, label="GCR-0005 finalized path").read_bytes()
        blob = taskctl.git_blob(repo, final, relative)
        if worktree != expected[relative] or blob != expected[relative].replace(b"\r\n", b"\n"):
            raise SystemExit(f"GCR-0005 finalized Git/worktree bytes differ: {relative}")
    validate_boundary(yaml.safe_load((repo / BACKLOG_PATH).read_bytes()), expected_status="CHANGES_REQUESTED")
    validate_adverse_ledger(repo)
    if present_transaction_artifacts(repo):
        raise SystemExit("GCR-0005 finalized tree retains transaction artifacts")
    require_workspace(repo)
    for command in (
        [sys.executable, str(repo / "tools/backlog_views.py"), "--repo", str(repo), "--check"],
        [sys.executable, str(repo / "tools/plan_review_check.py"), "--repo", str(repo)],
    ):
        result = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise SystemExit(f"GCR-0005 finalized generated views are invalid: {result.stdout}{result.stderr}")
    return final


def validate_exact_predecessor(repo: Path) -> None:
    head = git(repo, "rev-parse", "HEAD")
    for relative in FINAL_PATHS:
        path = safe_path(repo, relative, label="GCR-0005 predecessor path")
        if path.is_symlink() or getattr(os.path, "isjunction", lambda _path: False)(path):
            raise SystemExit(f"GCR-0005 predecessor path is redirected: {relative}")
        payload = path.read_bytes()
        if sha256(payload) != PREDECESSOR_RAW_SHA256[relative] or not git_worktree_equivalent(
            payload, taskctl.git_blob(repo, head, relative)
        ):
            raise SystemExit(f"GCR-0005 exact predecessor Git/worktree bytes differ: {relative}")


def validate_current_boundary(repo: Path) -> tuple[str, str]:
    present = present_transaction_artifacts(repo)
    if present:
        raise SystemExit(f"GCR-0005 application transaction requires explicit recovery: {present}")
    _approval, packet, base = load_authority(repo)
    state, _payload = load_state(repo, packet, required=False)
    backlog_sha = sha256((repo / BACKLOG_PATH).read_bytes())
    if backlog_sha == BACKLOG_BEFORE_RAW:
        validate_exact_predecessor(repo)
        require_workspace(repo)
        validate_boundary(yaml.safe_load((repo / BACKLOG_PATH).read_bytes()), expected_status="REVIEW")
        return str((state or {}).get("status") or "AUTHORIZED"), base
    if backlog_sha == BACKLOG_AFTER:
        validate_finalization(repo)
        return "APPLIED", base
    raise SystemExit("GCR-0005 backlog is neither the exact predecessor nor finalized successor")


def command_recover(args: argparse.Namespace) -> None:
    load_authority(args.repo)
    if args.agent != ACTOR:
        raise SystemExit(f"GCR-0005 recovery actor must be {ACTOR}")
    print(f"GCR-0005 application recovery: {recover_transaction(args.repo)}; ordinary execution remains denied")


def command_validate(args: argparse.Namespace) -> None:
    status, _base = validate_current_boundary(args.repo)
    if args.require_approved and status not in {"APPROVED", "APPLIED"}:
        raise SystemExit(f"{BOOTSTRAP_ID} is not independently approved")
    print(f"Valid {GCR_ID}: bootstrap={status}; control=11; ordinary execution denied")


def command_status(args: argparse.Namespace) -> None:
    status, base = validate_current_boundary(args.repo)
    print(
        yaml.safe_dump(
            {
                "controlRecovery": GCR_ID,
                "bootstrap": BOOTSTRAP_ID,
                "approvalBase": base,
                "status": status,
                "hold": HOLD_ID,
                "ordinaryExecutionAuthority": False,
            },
            sort_keys=False,
        ).rstrip()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("request")
    submit.add_argument("--agent", required=True)
    submit.add_argument("--approval-commit", required=True)
    submit.add_argument("--implementation-commit", required=True)
    submit.add_argument("--evidence", required=True)
    submit.set_defaults(handler=lambda args: freeze_submission(args, remediation=False))
    resubmit = sub.add_parser("resubmit")
    resubmit.add_argument("request")
    resubmit.add_argument("--agent", required=True)
    resubmit.add_argument("--implementation-commit", required=True)
    resubmit.add_argument("--evidence", required=True)
    resubmit.set_defaults(handler=lambda args: freeze_submission(args, remediation=True))
    review = sub.add_parser("review")
    review.add_argument("request")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--from", dest="ledger", required=True)
    review.set_defaults(handler=command_review)
    apply = sub.add_parser("apply")
    apply.add_argument("request")
    apply.add_argument("--agent", required=True)
    apply.add_argument("--approved-state-commit", required=True)
    apply.add_argument("--evidence", required=True)
    apply.set_defaults(handler=command_apply)
    recover = sub.add_parser("recover")
    recover.add_argument("request")
    recover.add_argument("--agent", required=True)
    recover.set_defaults(handler=command_recover)
    validate = sub.add_parser("validate")
    validate.add_argument("request")
    validate.add_argument("--require-approved", action="store_true")
    validate.set_defaults(handler=command_validate)
    status = sub.add_parser("status")
    status.add_argument("request")
    status.set_defaults(handler=command_status)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.repo = args.repo.resolve()
    if getattr(args, "request", GCR_ID) != GCR_ID:
        raise SystemExit(f"This controller recognizes only {GCR_ID}")
    if getattr(args, "command", "") == "submit" and str(args.approval_commit) != APPROVAL_COMMIT:
        raise SystemExit("GCR-0005 submit requires the exact approval-introduction commit")
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
