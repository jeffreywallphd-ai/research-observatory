#!/usr/bin/env python3
"""Exact, non-circular GCR-0007 reader-headroom controller.

This controller recognizes only GCR-0007.B00.  It cannot repair the historic
post-append defect, install GRR-0002.S03/B03, append W1.A04, release the hold,
resume W1, approve G1, or perform product or remote work.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

import taskctl
import yaml
from gcrctl import (
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

GCR_ID = "GCR-0007"
BOOTSTRAP_ID = "GCR-0007.B00"
BRANCH = "codex/w1-windows-local-runtime"
ACTOR = "codex"
PACKET_COMMIT = "b92f90d8139166aa690bfc2f924106f5e5ed37a8"
PACKET_SHA256 = "e17826eb1b8c4c1a05f0daefb0f4dc20bcd1d51669bda25b4785c85e9c69f163"
APPROVAL_COMMIT = "8babc35d0d82607a7301bc30189167dd4c0622c9"
AUTHORITY_BASE_COMMIT = "2eea1d0c67eb57d53e88f6717de3cfcd96fcf282"
PACKET_PATH = "planning/governance-control-recovery/GCR-0007.packet.json"
APPROVAL_PATH = "planning/governance-control-recovery/GCR-0007.approval.json"
AUTHORITY_PATH = "planning/governance-control-recovery/GCR-0007.authority.json"
TRIGGER_RECORD_PATH = "planning/governance-control-recovery/GCR-0007.trigger.json"
FEASIBILITY_PATH = "planning/governance-control-recovery/GCR-0006.feasibility-R01.json"
FEASIBILITY_SHA256 = "5986bd0371831f83ba7da0a01ead8bc50669e5e370c5294cb9e7101907085ca3"
FEASIBILITY_COMMIT = "2eea1d0c67eb57d53e88f6717de3cfcd96fcf282"
REQUEST_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-request.v7.schema.json"
RUNTIME_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-runtime.v7.schema.json"
TRANSACTION_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-transaction.v7.schema.json"
STATE_PATH = "planning/governance-control-recovery/GCR-0007.B00.state.json"
TRANSACTION_PATH = "planning/governance-control-recovery/GCR-0007.B00.adoption-transaction.json"
LOCK_PATH = "planning/governance-control-recovery/GCR-0007.B00.adoption.lock"
BACKLOG_NEXT_PATH = "planning/governance-control-recovery/GCR-0007.B00.adoption-backlog.next"
STATE_NEXT_PATH = "planning/governance-control-recovery/GCR-0007.B00.adoption-state.next"
BACKLOG_PATH = "planning/backlog.yaml"
TRIGGER_PATH = "artifacts/evidence/W1.A04.B00.json"
TRIGGER_SHA256 = "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c"
BACKLOG_PREDECESSOR_RAW_SHA256 = "aae3947377e06d9c752a7eae9b5d586c600b7e66016e41d95e753b100d9a93b7"
BACKLOG_PREDECESSOR_CANONICAL_SHA256 = "667225c669c393215b1b884e2cdc28fea6651bfd3b7d96b4bf93d161046487d4"
ADOPTION_EVIDENCE_PATH = "artifacts/evidence/governance-control-recovery/GCR-0007.B00.adoption.json"
PREDECESSOR_REVISION = 11
SUCCESSOR_REVISION = 11
SUPPORTED_CONTROL_CEILING = 12
HOLD_ID = "HOLD-W1-GRR-0002"
RESULT_STATUS = {"approved": "APPROVED", "changes-requested": "CHANGES_REQUESTED", "blocked": "BLOCKED"}
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
FINAL_PATHS = (BACKLOG_PATH, STATE_PATH)
TRANSACTION_PATHS = (LOCK_PATH, BACKLOG_NEXT_PATH, STATE_NEXT_PATH, TRANSACTION_PATH)


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


def json_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()


def schema_document(repo: Path, relative: str, label: str) -> dict[str, Any]:
    schema, _payload = load_json(safe_path(repo, relative, label=label), label)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SystemExit(f"{label} is invalid: {exc}") from exc
    return schema


def validate_schema(repo: Path, document: dict[str, Any], relative: str, label: str) -> None:
    schema = schema_document(repo, relative, f"{label} schema")
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"{'.'.join(str(item) for item in error.absolute_path) or '<root>'}: {error.message}" for error in errors
        )
        raise SystemExit(f"{label} schema validation failed: {detail}")


def validate_runtime(repo: Path, document: dict[str, Any], label: str) -> None:
    validate_schema(repo, document, RUNTIME_SCHEMA_PATH, label)


def validate_transaction(repo: Path, document: dict[str, Any]) -> None:
    validate_schema(repo, document, TRANSACTION_SCHEMA_PATH, "GCR-0007 adoption transaction")


def trigger_reference() -> dict[str, Any]:
    return {
        "path": TRIGGER_PATH,
        "sha256": TRIGGER_SHA256,
        "untracked": True,
        "unstaged": True,
        "executionAuthority": False,
    }


def guard_repo_path(repo: Path, relative: str, *, require_leaf: bool = True) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise SystemExit(f"GCR-0007 path is not repository-relative: {relative}")
    root = repo.resolve(strict=True)
    current = root
    for index, part in enumerate(pure.parts):
        current /= part
        leaf = index == len(pure.parts) - 1
        if not os.path.lexists(current):
            if leaf and not require_leaf:
                break
            raise SystemExit(f"GCR-0007 path component is absent: {relative}: {current}")
        metadata = current.lstat()
        attributes = int(getattr(metadata, "st_file_attributes", 0))
        reparse = bool(attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))
        junction = bool(getattr(os.path, "isjunction", lambda _path: False)(current))
        if current.is_symlink() or junction or reparse:
            raise SystemExit(f"GCR-0007 path component is redirected: {relative}: {current}")
        try:
            current.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"GCR-0007 path escapes the repository: {relative}") from exc
        if leaf and require_leaf and not stat.S_ISREG(metadata.st_mode):
            raise SystemExit(f"GCR-0007 path leaf is not a regular file: {relative}")
        if not leaf and not stat.S_ISDIR(metadata.st_mode):
            raise SystemExit(f"GCR-0007 path parent is not a directory: {relative}: {current}")
    return current


def validate_witness(repo: Path) -> None:
    path = guard_repo_path(repo, TRIGGER_PATH)
    if sha256(path.read_bytes()) != TRIGGER_SHA256:
        raise SystemExit("GCR-0007 witness is missing or changed")
    if git(repo, "ls-files", "--", TRIGGER_PATH):
        raise SystemExit("GCR-0007 witness must remain untracked")
    if TRIGGER_PATH in set(git(repo, "diff", "--cached", "--name-only", "--").splitlines()):
        raise SystemExit("GCR-0007 witness must remain unstaged")


def verify_reference(repo: Path, reference: dict[str, Any], label: str) -> tuple[dict[str, Any], bytes]:
    if set(reference) != {"path", "sha256", "commit"}:
        raise SystemExit(f"{label} reference shape is not exact")
    relative = str(reference.get("path") or "")
    commit = str(reference.get("commit") or "")
    document, payload = load_json(guard_repo_path(repo, relative), label)
    if (
        sha256(payload) != reference.get("sha256")
        or not taskctl.git_commit_exists(repo, commit)
        or not taskctl.git_is_ancestor(repo, commit)
        or taskctl.git_blob(repo, commit, relative) != payload
    ):
        raise SystemExit(f"{label} differs from its immutable Git authority")
    return document, payload


def _hold(data: dict[str, Any]) -> dict[str, Any]:
    matches = [
        item for item in (data.get("control_plane") or {}).get("recovery_holds", []) if item.get("id") == HOLD_ID
    ]
    if len(matches) != 1:
        raise SystemExit("GCR-0007 requires the sole exact active hold")
    return matches[0]


def validate_boundary(data: dict[str, Any], *, successor: bool = False) -> None:
    control = data.get("control_plane") or {}
    hold = _hold(data)
    wave = taskctl.wave_map(data).get("W1") or {}
    _capabilities, _slices, _slice_tasks, tasks, gates = taskctl.index_backlog(copy.deepcopy(data))
    task = tasks.get("CAP-02.S04.T03") or {}
    gate = gates.get("G1") or {}
    supplements = hold.get("supplements") or []
    b02 = (supplements[-1] if supplements else {}).get("bootstrap") or {}
    attempts = b02.get("attempts") or []
    latest = attempts[-1] if attempts else {}
    generations = control.get("control_generations") or []
    expected_ids = (
        ["GCR-0001", "GCR-0002", "GCR-0003", "GCR-0007"]
        if successor
        else [
            "GCR-0001",
            "GCR-0002",
            "GCR-0003",
        ]
    )
    if (
        control.get("revision") != 11
        or control.get("minimum_tool_revision") != 11
        or [item.get("id") for item in generations] != expected_ids
        or hold.get("status") != "ACTIVE"
        or [item.get("id") for item in supplements] != ["GRR-0002.S01", "GRR-0002.S02"]
        or b02.get("status") != "APPROVED"
        or (latest.get("review") or {}).get("result") != "approved"
        or (wave.get("campaign") or {}).get("status") != "PAUSED"
        or (wave.get("campaign") or {}).get("scope") != "wave"
        or task.get("status") != "BLOCKED"
        or "W1.A04" in taskctl.wave_amendment_map(data)
        or gate.get("status") != "PENDING"
    ):
        raise SystemExit("GCR-0007 stopped revision-11 boundary differs")
    if successor:
        generation = generations[-1]
        if any(
            (
                generation.get("id") != GCR_ID,
                generation.get("bootstrap_id") != BOOTSTRAP_ID,
                generation.get("hold_id") != HOLD_ID,
                generation.get("predecessor_revision") != 11,
                generation.get("successor_revision") != 11,
                generation.get("supported_control_ceiling") != 12,
                generation.get("generation_neutral") is not True,
            )
        ):
            raise SystemExit("GCR-0007 neutral generation is not exact")


def load_authority(
    repo: Path,
    *,
    allow_transaction_boundary: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    packet, packet_payload = load_json(guard_repo_path(repo, PACKET_PATH), "GCR-0007 packet")
    approval, approval_payload = load_json(guard_repo_path(repo, APPROVAL_PATH), "GCR-0007 approval")
    authority, authority_payload = load_json(guard_repo_path(repo, AUTHORITY_PATH), "GCR-0007 authority")
    trigger, trigger_payload = load_json(guard_repo_path(repo, TRIGGER_RECORD_PATH), "GCR-0007 trigger")
    if sha256(packet_payload) != PACKET_SHA256 or taskctl.git_blob(repo, PACKET_COMMIT, PACKET_PATH) != packet_payload:
        raise SystemExit("GCR-0007 packet differs from its reviewed Git blob")
    validate_schema(repo, packet, REQUEST_SCHEMA_PATH, "GCR-0007 packet")
    validate_runtime(repo, approval, "GCR-0007 approval")
    introduction = taskctl.approval_introduction_commit(repo, APPROVAL_PATH)
    review_ref = approval.get("packetReview") or {}
    review, review_payload = verify_reference(repo, review_ref, "GCR-0007 packet review")
    validate_runtime(repo, review, "GCR-0007 packet review")
    authority_ref = approval.get("authorityManifest") or {}
    feasibility_ref = approval.get("supersededGcr6Feasibility") or {}
    if (
        introduction != APPROVAL_COMMIT
        or taskctl.git_blob(repo, APPROVAL_COMMIT, APPROVAL_PATH) != approval_payload
        or approval.get("controlRecoveryId") != GCR_ID
        or approval.get("packetCommit") != PACKET_COMMIT
        or approval.get("packetSha256") != PACKET_SHA256
        or approval.get("witness") != trigger_reference()
        or approval.get("ordinaryExecutionAuthority") is not False
        or review.get("candidateCommit") != PACKET_COMMIT
        or review.get("packetSha256") != PACKET_SHA256
        or review.get("result") != "approved"
        or review.get("findings") != []
        or review.get("approvalAvailable") is not True
        or sha256(review_payload) != review_ref.get("sha256")
        or authority_ref != {"path": AUTHORITY_PATH, "sha256": sha256(authority_payload), "commit": PACKET_COMMIT}
        or feasibility_ref != {"path": FEASIBILITY_PATH, "sha256": FEASIBILITY_SHA256, "commit": FEASIBILITY_COMMIT}
        or not taskctl.git_is_ancestor(repo, PACKET_COMMIT, introduction)
        or not taskctl.git_is_ancestor(repo, str(review_ref.get("commit") or ""), introduction)
    ):
        raise SystemExit("GCR-0007 approval or independent packet review is invalid")
    root = packet.get("rootAuthority") or {}
    if (
        sha256(authority_payload) != (root.get("authorityManifest") or {}).get("sha256")
        or sha256(trigger_payload) != (root.get("triggerRecord") or {}).get("sha256")
        or trigger.get("baseCommit") != AUTHORITY_BASE_COMMIT
        or trigger.get("baseParentCommit") != "655e1a0e2451ced7fc26642f9fa16f775d5c0ddb"
    ):
        raise SystemExit("GCR-0007 authority or trigger record differs")
    for reference in packet.get("files") or []:
        relative = str(reference.get("path") or "")
        payload = guard_repo_path(repo, relative).read_bytes()
        if sha256(payload) != reference.get("sha256") or taskctl.git_blob(repo, PACKET_COMMIT, relative) != payload:
            raise SystemExit(f"GCR-0007 packet file differs: {relative}")
    for pattern in (packet.get("bootstrapUnit") or {}).get("authorizedPaths") or []:
        validate_scope_pattern(str(pattern))
    inert = authority.get("inertPredecessor") or {}
    for key in ("packet", "packetReview", "approval", "runtimeSchema", "transactionSchema", "feasibility"):
        verify_reference(repo, inert.get(key) or {}, f"GCR-0006 inert {key}")
    if (
        inert.get("id") != "GCR-0006"
        or inert.get("implementationStarted") is not False
        or inert.get("statePresent") is not False
        or inert.get("generationPresent") is not False
        or guard_repo_path(repo, "tools/gcr6ctl.py", require_leaf=False).exists()
        or guard_repo_path(
            repo,
            "planning/governance-control-recovery/GCR-0006.B00.state.json",
            require_leaf=False,
        ).exists()
    ):
        raise SystemExit("GCR-0006 is not the exact approved-but-inert predecessor")
    canonical = taskctl.git_blob(repo, AUTHORITY_BASE_COMMIT, BACKLOG_PATH)
    if canonical is None or sha256(canonical) != BACKLOG_PREDECESSOR_CANONICAL_SHA256:
        raise SystemExit("GCR-0007 predecessor backlog Git content differs")
    backlog = guard_repo_path(repo, BACKLOG_PATH).read_bytes()
    if sha256(backlog) == BACKLOG_PREDECESSOR_RAW_SHA256:
        data = yaml.safe_load(backlog)
        if not isinstance(data, dict):
            raise SystemExit("GCR-0007 predecessor backlog is malformed")
        validate_boundary(data)
    else:
        try:
            data = yaml.safe_load(backlog)
            if not isinstance(data, dict):
                raise ValueError("not an object")
            validate_boundary(data, successor=True)
        except SystemExit, ValueError, yaml.YAMLError:
            if not allow_transaction_boundary or not present_transaction_artifacts(repo):
                raise SystemExit("GCR-0007 live backlog is neither the exact predecessor nor successor") from None
    validate_witness(repo)
    return approval, packet, introduction


def state_path(repo: Path) -> Path:
    return guard_repo_path(repo, STATE_PATH, require_leaf=False)


def evidence_path(attempt_id: str) -> str:
    return f"artifacts/evidence/governance-control-recovery/{BOOTSTRAP_ID}.{attempt_id}.json"


def review_path(attempt_id: str) -> str:
    return f"planning/governance-control-recovery/{BOOTSTRAP_ID}.review-{attempt_id}.json"


def adoption_evidence_path(attempt_id: str) -> str:
    if not re.fullmatch(r"R[0-9]{2}", attempt_id):
        raise SystemExit("GCR-0007 adoption evidence attempt is invalid")
    if attempt_id == "R02":
        return ADOPTION_EVIDENCE_PATH
    return f"artifacts/evidence/governance-control-recovery/{BOOTSTRAP_ID}.adoption-{attempt_id}.json"


def _attempt_keys(state: dict[str, Any]) -> list[str]:
    attempts = state.get("attempts") or {}
    if not isinstance(attempts, dict):
        raise SystemExit("GCR-0007 attempts must be an ordered map")
    keys = list(attempts)
    if keys != [f"R{index:02d}" for index in range(1, len(keys) + 1)]:
        raise SystemExit("GCR-0007 attempts are duplicated, gapped, or reordered")
    return keys


def fold_findings(state: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    opened: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for key in _attempt_keys(state):
        review = state["attempts"][key].get("review") or {}
        for closure in review.get("closures") or []:
            finding_id = str(closure.get("findingId") or "")
            if finding_id not in opened:
                raise SystemExit(f"GCR-0007 {key} closes no open prior finding")
            opened.pop(finding_id)
        for finding in review.get("findings") or []:
            finding_id = str(finding.get("id") or "")
            if not finding_id or finding_id in seen:
                raise SystemExit(f"GCR-0007 {key} finding identity is empty or duplicated")
            seen.add(finding_id)
            opened[finding_id] = copy.deepcopy(finding)
    return opened, seen


def _git_document(repo: Path, commit: str, relative: str, label: str) -> tuple[dict[str, Any], bytes]:
    payload = taskctl.git_blob(repo, commit, relative)
    if payload is None:
        raise SystemExit(f"{label} Git blob is absent")
    value = strict_json(payload, label)
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object")
    return value, payload


def _exact_parent(repo: Path, parent: str, commit: str, expected: dict[str, str], label: str) -> None:
    parents = git(repo, "rev-list", "--parents", "-n", "1", commit).split()
    if parents != [commit, parent]:
        raise SystemExit(f"{label} is not the exact direct child of {parent}")
    require_exact_commit_delta(repo, parent=parent, commit=commit, expected=expected, label=label)


def _first_descendant(repo: Path, commit: str) -> str | None:
    head = git(repo, "rev-parse", "HEAD")
    if commit == head:
        return None
    values = git(repo, "rev-list", "--ancestry-path", "--reverse", f"{commit}..{head}").splitlines()
    return values[0] if values else None


def changed_paths(repo: Path, base: str, candidate: str) -> list[str]:
    if base == candidate or not taskctl.git_is_ancestor(repo, base, candidate):
        raise SystemExit("GCR-0007 candidate must strictly descend from the approval base")
    return sorted(git(repo, "diff", "--name-only", f"{base}..{candidate}", "--").splitlines())


def validate_evidence_document(
    repo: Path,
    packet: dict[str, Any],
    document: dict[str, Any],
    *,
    candidate: str,
    attempt_id: str,
    prior_open: dict[str, dict[str, Any]],
) -> list[str]:
    validate_runtime(repo, document, f"GCR-0007 {attempt_id} evidence")
    actual = changed_paths(repo, APPROVAL_COMMIT, candidate)
    patterns = [str(item) for item in (packet.get("bootstrapUnit") or {}).get("authorizedPaths") or []]
    outside = [relative for relative in actual if not path_authorized(relative, patterns)]
    protected_prefixes = (
        "planning/governance-control-recovery/GCR-0006",
        "planning/governance-control-recovery/governance-control-recovery-runtime.v6",
        "planning/governance-control-recovery/governance-control-recovery-transaction.v6",
    )
    criteria = document.get("acceptanceCriteria") or []
    outcomes = document.get("requiredOutcomes") or []
    checks = document.get("checks") or []
    closures = document.get("closures") or []
    closure_ids = [str(item.get("findingId") or "") for item in closures]
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
        or not actual
        or outside
        or any(relative.startswith(protected_prefixes) for relative in actual)
        or BACKLOG_PATH in actual
        or TRIGGER_PATH in actual
        or [item.get("criterion") for item in criteria] != (packet.get("acceptanceCriteria") or [])
        or [item.get("criterion") for item in outcomes]
        != ((packet.get("bootstrapUnit") or {}).get("requiredOutcomes") or [])
        or document.get("unverifiedItems") != []
        or set(closure_ids) != set(prior_open)
        or len(closure_ids) != len(set(closure_ids))
        or not checks
        or len({item.get("command") for item in checks}) != len(checks)
        or any(item.get("result") != "passed" for item in checks)
    ):
        raise SystemExit("GCR-0007 evidence identity, scope, criteria, closures, or checks is invalid")
    if int(attempt_id[1:]) >= 3:
        if not isinstance(document.get("rootCauseAnalysis"), dict) or not document.get("rootCauseAnalysis"):
            raise SystemExit("GCR-0007 third and later evidence requires root-cause analysis")
    elif document.get("rootCauseAnalysis") is not None:
        raise SystemExit("GCR-0007 R01/R02 evidence must not invent root-cause analysis")
    return actual


def validate_review_ledger(
    repo: Path,
    ledger: dict[str, Any],
    submission: dict[str, Any],
    *,
    reviewer: str,
    reviewed_state: str,
    prior_open: dict[str, dict[str, Any]],
    prior_ids: set[str],
) -> dict[str, dict[str, Any]]:
    validate_runtime(repo, ledger, f"GCR-0007 {submission.get('attemptId')} review")
    findings = ledger.get("findings") or []
    closures = ledger.get("closures") or []
    finding_ids = [str(item.get("id") or "") for item in findings]
    closure_ids = [str(item.get("findingId") or "") for item in closures]
    severities = [SEVERITY_ORDER.get(str(item.get("severity") or ""), 99) for item in findings]
    if (
        ledger.get("controlRecoveryId") != GCR_ID
        or ledger.get("bootstrapUnit") != BOOTSTRAP_ID
        or ledger.get("attemptId") != submission.get("attemptId")
        or ledger.get("candidateCommit") != submission.get("candidateCommit")
        or ledger.get("reviewedStateCommit") != reviewed_state
        or ledger.get("reviewer") != reviewer
        or ledger.get("evidence") != submission.get("evidence")
        or severities != sorted(severities)
        or len(finding_ids) != len(set(finding_ids))
        or set(finding_ids) & prior_ids
        or len(closure_ids) != len(set(closure_ids))
        or set(closure_ids) - set(prior_open)
    ):
        raise SystemExit("GCR-0007 review differs from its submission or append-only history")
    result = str(ledger.get("result") or "")
    if result not in RESULT_STATUS:
        raise SystemExit("GCR-0007 review result is invalid")
    opened = {key: copy.deepcopy(value) for key, value in prior_open.items() if key not in closure_ids}
    for finding in findings:
        opened[str(finding["id"])] = copy.deepcopy(finding)
    if result == "approved" and (findings or any(item.get("blocking") is True for item in opened.values())):
        raise SystemExit("GCR-0007 approval introduces findings or retains an open blocker")
    return opened


def _projection_state(
    reviewed: dict[str, Any], *, attempt_id: str, attempt: dict[str, Any], opened: dict[str, dict[str, Any]]
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
    validate_runtime(repo, state, "GCR-0007 state")
    if state.get("approval") != {
        "path": APPROVAL_PATH,
        "sha256": sha256(guard_repo_path(repo, APPROVAL_PATH).read_bytes()),
        "commit": APPROVAL_COMMIT,
    }:
        raise SystemExit("GCR-0007 state approval differs")
    keys = _attempt_keys(state)
    opened: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    prior_candidate: str | None = None
    previous_attempts: dict[str, Any] = {}
    for index, key in enumerate(keys):
        attempt = state["attempts"][key]
        submission = attempt.get("submission") or {}
        review = attempt.get("review") or {}
        ledger_ref = attempt.get("ledger") or {}
        evidence_ref = submission.get("evidence") or {}
        candidate = str(submission.get("candidateCommit") or "")
        evidence_commit = str(evidence_ref.get("commit") or "")
        reviewed_state = str(attempt.get("reviewedStateCommit") or "")
        ledger_commit = str(ledger_ref.get("commit") or "")
        if (
            submission.get("attemptId") != key
            or submission.get("agent") != ACTOR
            or submission.get("approvalCommit") != APPROVAL_COMMIT
            or submission.get("baseCommit") != APPROVAL_COMMIT
            or submission.get("branch") != BRANCH
            or evidence_ref.get("path") != evidence_path(key)
        ):
            raise SystemExit(f"GCR-0007 {key} submission binding is invalid")
        if prior_candidate and (
            prior_candidate == candidate or not taskctl.git_is_ancestor(repo, prior_candidate, candidate)
        ):
            raise SystemExit(f"GCR-0007 {key} candidate is not a strict remediation descendant")
        prior_candidate = candidate
        _exact_parent(repo, candidate, evidence_commit, {evidence_path(key): "A"}, f"GCR-0007 {key} evidence")
        evidence, evidence_payload = _git_document(
            repo,
            evidence_commit,
            evidence_path(key),
            f"GCR-0007 {key} evidence",
        )
        if sha256(evidence_payload) != evidence_ref.get("sha256"):
            raise SystemExit(f"GCR-0007 {key} evidence hash differs")
        actual = validate_evidence_document(
            repo, packet, evidence, candidate=candidate, attempt_id=key, prior_open=opened
        )
        if submission.get("changedPaths") != actual:
            raise SystemExit(f"GCR-0007 {key} changed-path freeze differs")
        _exact_parent(
            repo,
            evidence_commit,
            reviewed_state,
            {STATE_PATH: "A" if index == 0 else "M"},
            f"GCR-0007 {key} reviewed state",
        )
        reviewed, _payload = _git_document(repo, reviewed_state, STATE_PATH, f"GCR-0007 {key} reviewed state")
        if (
            reviewed.get("status") != "REVIEW"
            or reviewed.get("attempts") != previous_attempts
            or reviewed.get("currentSubmission") != submission
            or reviewed.get("latestReviewResult") is not None
            or reviewed.get("openFindingIds") != sorted(opened)
            or reviewed.get("activation") is not None
        ):
            raise SystemExit(f"GCR-0007 {key} reviewed-state projection is invalid")
        ledger_relative = str(ledger_ref.get("path") or "")
        if ledger_relative != review_path(key):
            raise SystemExit(f"GCR-0007 {key} ledger path is not canonical")
        _exact_parent(repo, reviewed_state, ledger_commit, {ledger_relative: "A"}, f"GCR-0007 {key} ledger")
        ledger, ledger_payload = _git_document(repo, ledger_commit, ledger_relative, f"GCR-0007 {key} ledger")
        if sha256(ledger_payload) != ledger_ref.get("sha256"):
            raise SystemExit(f"GCR-0007 {key} ledger hash differs")
        reviewer = str(review.get("reviewer") or "")
        opened_after = validate_review_ledger(
            repo,
            ledger,
            submission,
            reviewer=reviewer,
            reviewed_state=reviewed_state,
            prior_open=opened,
            prior_ids=seen_ids,
        )
        expected_review = {
            "reviewer": reviewer,
            "result": ledger.get("result"),
            "notes": ledger.get("notes", ""),
            "findings": ledger.get("findings") or [],
            "closures": ledger.get("closures") or [],
        }
        if reviewer == ACTOR or review != expected_review:
            raise SystemExit(f"GCR-0007 {key} review projection differs from its ledger")
        expected = _projection_state(reviewed, attempt_id=key, attempt=attempt, opened=opened_after)
        projection_commit = _first_descendant(repo, ledger_commit)
        if projection_commit is None:
            if not allow_uncommitted_projection or index != len(keys) - 1 or state != expected:
                raise SystemExit(f"GCR-0007 {key} state-only projection commit is absent")
        else:
            _exact_parent(repo, ledger_commit, projection_commit, {STATE_PATH: "M"}, f"GCR-0007 {key} projection")
            projected, _payload = _git_document(repo, projection_commit, STATE_PATH, f"GCR-0007 {key} projection")
            if projected != expected:
                raise SystemExit(f"GCR-0007 {key} projection disagrees with the ledger")
        opened = opened_after
        seen_ids.update(str(item.get("id")) for item in review.get("findings") or [])
        previous_attempts[key] = copy.deepcopy(attempt)
    current = state.get("currentSubmission")
    if current is not None:
        next_id = f"R{len(keys) + 1:02d}"
        if (
            state.get("status") != "REVIEW"
            or current.get("attemptId") != next_id
            or state.get("latestReviewResult") is not None
            or state.get("openFindingIds") != sorted(opened)
            or state.get("activation") is not None
        ):
            raise SystemExit("GCR-0007 pending submission is not the exact next RNN")
        evidence_ref = current.get("evidence") or {}
        candidate = str(current.get("candidateCommit") or "")
        evidence_commit = str(evidence_ref.get("commit") or "")
        _exact_parent(repo, candidate, evidence_commit, {evidence_path(next_id): "A"}, f"GCR-0007 {next_id} evidence")
        evidence, evidence_payload = _git_document(
            repo, evidence_commit, evidence_path(next_id), f"GCR-0007 {next_id} evidence"
        )
        if sha256(evidence_payload) != evidence_ref.get("sha256"):
            raise SystemExit(f"GCR-0007 {next_id} evidence hash differs")
        actual = validate_evidence_document(
            repo, packet, evidence, candidate=candidate, attempt_id=next_id, prior_open=opened
        )
        if current.get("changedPaths") != actual:
            raise SystemExit("GCR-0007 pending changed paths differ")
        reviewed_state = git(repo, "log", "-1", "--format=%H", "--", STATE_PATH)
        _exact_parent(
            repo,
            evidence_commit,
            reviewed_state,
            {STATE_PATH: "A" if not keys else "M"},
            f"GCR-0007 {next_id} pending state",
        )
        reviewed, _payload = _git_document(repo, reviewed_state, STATE_PATH, f"GCR-0007 {next_id} pending state")
        if reviewed != state:
            raise SystemExit("GCR-0007 pending state differs from its committed bytes")
    elif keys:
        latest = str((state["attempts"][keys[-1]].get("review") or {}).get("result") or "")
        allowed = {RESULT_STATUS[latest], "HEADROOM_ACTIVATION_FINALIZATION", "HEADROOM_ACTIVE"}
        if (
            state.get("latestReviewResult") != latest
            or state.get("openFindingIds") != sorted(opened)
            or state.get("status") not in allowed
        ):
            raise SystemExit("GCR-0007 latest review projection is stale")
        if state.get("status") in {"APPROVED", "HEADROOM_ACTIVATION_FINALIZATION", "HEADROOM_ACTIVE"} and any(
            item.get("blocking") is True for item in opened.values()
        ):
            raise SystemExit("GCR-0007 approval retains an open blocker")
    elif state.get("status") != "READY":
        raise SystemExit("GCR-0007 state lacks an attempt or pending submission")


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
            raise SystemExit("GCR-0007 B00 state is absent")
        return None, None
    state, payload = load_json(path, "GCR-0007 state")
    validate_runtime(repo, state, "GCR-0007 state")
    if validate:
        validate_history(repo, state, packet)
    return state, payload


def transaction_artifacts(repo: Path) -> dict[str, Path]:
    return {relative: guard_repo_path(repo, relative, require_leaf=False) for relative in TRANSACTION_PATHS}


def present_transaction_artifacts(repo: Path) -> list[str]:
    return [relative for relative, path in transaction_artifacts(repo).items() if os.path.lexists(path)]


def require_workspace(repo: Path, *, transaction: bool = False) -> None:
    if git(repo, "branch", "--show-current") != BRANCH:
        raise SystemExit(f"GCR-0007 transitions require exact branch {BRANCH}")
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise SystemExit("GCR-0007 transitions refuse staged changes")
    validate_witness(repo)
    untracked = set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    allowed = {TRIGGER_PATH}
    if transaction:
        allowed.update(present_transaction_artifacts(repo))
    if untracked != allowed:
        difference = sorted(untracked ^ allowed)
        raise SystemExit(f"GCR-0007 untracked boundary differs: {difference[0] if difference else '<unknown>'}")
    dirty = set(git(repo, "diff", "--name-only", "HEAD", "--").splitlines())
    allowed_dirty = set(FINAL_PATHS) if transaction else set()
    if dirty - allowed_dirty:
        raise SystemExit(f"GCR-0007 refuses unrelated tracked dirt: {sorted(dirty - allowed_dirty)[0]}")
    if not transaction and dirty:
        raise SystemExit("GCR-0007 transitions require an exact tracked commit")


def freeze_submission(args: argparse.Namespace, *, remediation: bool) -> None:
    _approval, packet, base = load_authority(args.repo)
    if present_transaction_artifacts(args.repo):
        raise SystemExit("GCR-0007 adoption transaction requires explicit recovery")
    state, state_payload = load_state(args.repo, packet, required=False)
    if remediation:
        adverse_review = state is not None and state.get("status") in {"CHANGES_REQUESTED", "BLOCKED"}
        failed_pre_activation_adoption = (
            state is not None
            and state_payload is not None
            and authenticated_failed_pre_activation_adoption(args.repo, state, state_payload)
        )
        if not adverse_review and not failed_pre_activation_adoption:
            raise SystemExit(
                "GCR-0007 resubmission requires an adverse review or a failed pre-activation adoption "
                "with immutable attempt-scoped evidence"
            )
    elif state is not None:
        raise SystemExit("GCR-0007 initial submission already exists")
    if not remediation and str(args.approval_commit) != base:
        raise SystemExit("GCR-0007 approval argument differs from its immutable introduction")
    if args.agent != ACTOR:
        raise SystemExit(f"GCR-0007 implementer must be exact actor {ACTOR}")
    require_workspace(args.repo)
    attempts = (state or {}).get("attempts") or {}
    attempt_id = f"R{len(attempts) + 1:02d}"
    candidate = str(args.implementation_commit)
    evidence_relative = str(args.evidence)
    head = git(args.repo, "rev-parse", "HEAD")
    if evidence_relative != evidence_path(attempt_id):
        raise SystemExit(f"GCR-0007 evidence path must be {evidence_path(attempt_id)}")
    _exact_parent(args.repo, candidate, head, {evidence_relative: "A"}, f"GCR-0007 {attempt_id} evidence")
    evidence, payload = _git_document(args.repo, head, evidence_relative, f"GCR-0007 {attempt_id} evidence")
    opened, _seen = fold_findings(state or {"attempts": {}})
    actual = validate_evidence_document(
        args.repo, packet, evidence, candidate=candidate, attempt_id=attempt_id, prior_open=opened
    )
    if remediation:
        prior = str(attempts[f"R{len(attempts):02d}"]["submission"].get("candidateCommit") or "")
        if candidate == prior or not taskctl.git_is_ancestor(args.repo, prior, candidate):
            raise SystemExit("GCR-0007 remediation candidate is not a strict descendant")
    submission = {
        "attemptId": attempt_id,
        "agent": ACTOR,
        "approvalCommit": APPROVAL_COMMIT,
        "baseCommit": APPROVAL_COMMIT,
        "candidateCommit": candidate,
        "branch": BRANCH,
        "evidence": {"path": evidence_relative, "sha256": sha256(payload), "commit": head},
        "changedPaths": actual,
    }
    if state is None:
        state = {
            "schemaVersion": "7.0-control-recovery-state",
            "documentType": "governance-control-recovery-successor-bootstrap-state",
            "controlRecoveryId": GCR_ID,
            "bootstrapUnit": BOOTSTRAP_ID,
            "status": "REVIEW",
            "approval": {
                "path": APPROVAL_PATH,
                "sha256": sha256(guard_repo_path(args.repo, APPROVAL_PATH).read_bytes()),
                "commit": APPROVAL_COMMIT,
            },
            "attempts": {},
            "currentSubmission": submission,
            "latestReviewResult": None,
            "openFindingIds": [],
            "activation": None,
        }
    else:
        state["status"] = "REVIEW"
        state["currentSubmission"] = submission
        state["latestReviewResult"] = None
    validate_runtime(args.repo, state, "GCR-0007 submission state")
    write_json_atomic(args.repo / STATE_PATH, state)
    print(f"Submitted {BOOTSTRAP_ID}/{attempt_id}; commit only the state before independent review")


def command_review(args: argparse.Namespace) -> None:
    _approval, packet, _base = load_authority(args.repo)
    state, _payload = load_state(args.repo, packet, required=True)
    assert state is not None
    if state.get("status") != "REVIEW" or not state.get("currentSubmission"):
        raise SystemExit("GCR-0007 has no pending frozen submission")
    require_workspace(args.repo)
    reviewer = str(args.reviewer).strip()
    if not reviewer or reviewer != args.reviewer or reviewer == ACTOR:
        raise SystemExit("GCR-0007 reviewer must be normalized and independent")
    submission = copy.deepcopy(state["currentSubmission"])
    attempt_id = str(submission["attemptId"])
    ledger_relative = str(args.ledger)
    if ledger_relative != review_path(attempt_id):
        raise SystemExit(f"GCR-0007 review path must be {review_path(attempt_id)}")
    ledger_commit = git(args.repo, "rev-parse", "HEAD")
    ledger, payload = _git_document(args.repo, ledger_commit, ledger_relative, f"GCR-0007 {attempt_id} review")
    reviewed_state = str(ledger.get("reviewedStateCommit") or "")
    _exact_parent(args.repo, reviewed_state, ledger_commit, {ledger_relative: "A"}, f"GCR-0007 {attempt_id} ledger")
    reviewed, _bytes = _git_document(args.repo, reviewed_state, STATE_PATH, f"GCR-0007 {attempt_id} reviewed state")
    if reviewed != state:
        raise SystemExit("GCR-0007 review does not bind the live frozen state")
    opened, seen = fold_findings(state)
    opened_after = validate_review_ledger(
        args.repo,
        ledger,
        submission,
        reviewer=reviewer,
        reviewed_state=reviewed_state,
        prior_open=opened,
        prior_ids=seen,
    )
    attempt = {
        "submission": submission,
        "reviewedStateCommit": reviewed_state,
        "review": {
            "reviewer": reviewer,
            "result": ledger["result"],
            "notes": ledger.get("notes", ""),
            "findings": copy.deepcopy(ledger.get("findings") or []),
            "closures": copy.deepcopy(ledger.get("closures") or []),
        },
        "ledger": {"path": ledger_relative, "sha256": sha256(payload), "commit": ledger_commit},
    }
    state = _projection_state(state, attempt_id=attempt_id, attempt=attempt, opened=opened_after)
    validate_history(args.repo, state, packet, allow_uncommitted_projection=True)
    write_json_atomic(args.repo / STATE_PATH, state)
    print(f"Recorded {BOOTSTRAP_ID}/{attempt_id} as {state['status']}; commit only the state projection")


def canonical_approved_state(
    repo: Path, state: dict[str, Any], state_payload: bytes
) -> tuple[str, str, dict[str, Any], bytes]:
    keys = _attempt_keys(state)
    opened, _seen = fold_findings(state)
    if state.get("status") != "APPROVED" or not keys or opened:
        raise SystemExit("GCR-0007 adoption requires an independently approved state without open findings")
    latest = state["attempts"][keys[-1]]
    ledger_ref = latest.get("ledger") or {}
    ledger_commit = str(ledger_ref.get("commit") or "")
    reviewed_state = str(latest.get("reviewedStateCommit") or "")
    approved_state = _first_descendant(repo, ledger_commit)
    if not approved_state:
        raise SystemExit("GCR-0007 approved state projection commit is absent")
    _exact_parent(repo, ledger_commit, approved_state, {STATE_PATH: "M"}, "GCR-0007 approved state P")
    if taskctl.git_blob(repo, approved_state, STATE_PATH) != state_payload:
        raise SystemExit("GCR-0007 approved state P differs from the live approved state")
    ledger, ledger_payload = _git_document(repo, ledger_commit, str(ledger_ref.get("path") or ""), "GCR-0007 ledger")
    if (
        (latest.get("review") or {}).get("result") != "approved"
        or ledger.get("result") != "approved"
        or sha256(ledger_payload) != ledger_ref.get("sha256")
    ):
        raise SystemExit("GCR-0007 latest immutable ledger is not approved")
    return reviewed_state, approved_state, ledger_ref, ledger_payload


def validate_adoption_evidence(
    repo: Path,
    document: dict[str, Any],
    payload: bytes,
    *,
    approved_state: str,
    evidence_commit: str,
    evidence_relative: str = ADOPTION_EVIDENCE_PATH,
) -> None:
    validate_runtime(repo, document, "GCR-0007 adoption evidence")
    if (
        document.get("controlRecoveryId") != GCR_ID
        or document.get("bootstrapUnit") != BOOTSTRAP_ID
        or document.get("approvedStateCommit") != approved_state
        or "adoptionEvidenceCommit" in document
        or "finalizationCommit" in document
        or document.get("predecessorRevision") != 11
        or document.get("successorRevision") != 11
        or document.get("supportedControlCeiling") != 12
        or document.get("generationNeutral") is not True
        or document.get("expectedFinalizationPaths") != list(FINAL_PATHS)
        or document.get("unverifiedItems") != []
        or document.get("ordinaryExecutionAuthority") is not False
        or not document.get("checks")
        or any(item.get("result") != "passed" for item in document.get("checks") or [])
        or taskctl.git_blob(repo, evidence_commit, evidence_relative) != payload
    ):
        raise SystemExit("GCR-0007 adoption evidence is circular, stale, adverse, or misbound")
    _exact_parent(
        repo,
        approved_state,
        evidence_commit,
        {evidence_relative: "A"},
        "GCR-0007 adoption evidence A",
    )


def authenticated_failed_pre_activation_adoption(
    repo: Path,
    state: dict[str, Any],
    state_payload: bytes,
) -> bool:
    if state.get("status") != "APPROVED" or state.get("activation") is not None:
        return False
    attempts = _attempt_keys(state)
    if not attempts:
        return False
    evidence_relative = adoption_evidence_path(attempts[-1])
    evidence_commit = taskctl.approval_introduction_commit(repo, evidence_relative)
    if not evidence_commit:
        return False
    _reviewed_state, approved_state, _ledger_ref, _ledger_payload = canonical_approved_state(repo, state, state_payload)
    evidence, evidence_payload = _git_document(
        repo,
        evidence_commit,
        evidence_relative,
        "GCR-0007 failed pre-activation adoption evidence",
    )
    validate_adoption_evidence(
        repo,
        evidence,
        evidence_payload,
        approved_state=approved_state,
        evidence_commit=evidence_commit,
        evidence_relative=evidence_relative,
    )
    return True


def generation_record(
    repo: Path,
    *,
    reviewed_state: str,
    approved_state: str,
    ledger_reference: dict[str, Any],
    adopted_at: str,
) -> dict[str, Any]:
    return {
        "id": GCR_ID,
        "bootstrap_id": BOOTSTRAP_ID,
        "hold_id": HOLD_ID,
        "predecessor_revision": 11,
        "successor_revision": 11,
        "supported_control_ceiling": 12,
        "generation_neutral": True,
        "approval_reference": {
            "path": APPROVAL_PATH,
            "sha256": sha256(guard_repo_path(repo, APPROVAL_PATH).read_bytes()),
            "introduction_commit": APPROVAL_COMMIT,
        },
        "review_reference": {
            "path": ledger_reference.get("path"),
            "sha256": ledger_reference.get("sha256"),
            "reviewed_state_commit": reviewed_state,
            "approved_state_commit": approved_state,
        },
        "adopted_by": ACTOR,
        "adopted_at": adopted_at,
    }


def binding(path: str, payload: bytes, document: Any) -> dict[str, str]:
    return {"path": path, "rawSha256": sha256(payload), "canonicalSha256": canonical_sha(document)}


def exact_generation(document: dict[str, Any]) -> dict[str, Any]:
    generations = (document.get("control_plane") or {}).get("control_generations") or []
    if len(generations) != 4:
        raise SystemExit("GCR-0007 successor does not contain exactly four generations")
    generation = generations[-1]
    if (
        generation.get("id") != GCR_ID
        or generation.get("bootstrap_id") != BOOTSTRAP_ID
        or generation.get("hold_id") != HOLD_ID
        or generation.get("predecessor_revision") != 11
        or generation.get("successor_revision") != 11
        or generation.get("supported_control_ceiling") != 12
        or generation.get("generation_neutral") is not True
    ):
        raise SystemExit("GCR-0007 successor generation is not the sole exact neutral exception")
    return generation


def validate_successor_documents(repo: Path, backlog_payload: bytes, state_payload: bytes) -> None:
    try:
        backlog = yaml.safe_load(backlog_payload)
        state = strict_json(state_payload, "GCR-0007 successor state")
    except yaml.YAMLError as exc:
        raise SystemExit(f"GCR-0007 successor backlog is malformed: {exc}") from exc
    if not isinstance(backlog, dict) or not isinstance(state, dict):
        raise SystemExit("GCR-0007 successor pair must contain objects")
    validate_runtime(repo, state, "GCR-0007 successor state")
    validate_boundary(backlog, successor=True)
    exact_generation(backlog)
    activation = state.get("activation") or {}
    if (
        state.get("status") != "HEADROOM_ACTIVATION_FINALIZATION"
        or activation.get("predecessorRevision") != 11
        or activation.get("successorRevision") != 11
        or activation.get("supportedControlCeiling") != 12
        or activation.get("generationNeutral") is not True
        or activation.get("changedPaths") != list(FINAL_PATHS)
        or activation.get("ordinaryExecutionAuthority") is not False
        or "finalizationCommit" in activation
    ):
        raise SystemExit("GCR-0007 successor state is not the exact non-circular finalization marker")
    if getattr(taskctl, "CONTROL_TOOL_REVISION", 0) >= 12:
        errors = taskctl.backlog_schema_errors(backlog)
        errors.extend(taskctl.validate(*taskctl.index_backlog(backlog), repo=None))
        if errors:
            raise SystemExit("GCR-0007 successor is rejected by the installed reader:\n- " + "\n- ".join(errors))


def prove_old_reader_fails_closed(repo: Path, successor: dict[str, Any]) -> None:
    payload = taskctl.git_blob(repo, APPROVAL_COMMIT, "planning/backlog.schema.json")
    if payload is None:
        raise SystemExit("GCR-0007 predecessor reader schema is unavailable")
    schema = strict_json(payload, "revision-11 backlog schema")
    if not isinstance(schema, dict):
        raise SystemExit("GCR-0007 predecessor reader schema is malformed")
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(successor))
    if not errors:
        raise SystemExit("GCR-0007 predecessor reader does not fail closed on the fourth generation")


def transaction_document(
    repo: Path,
    *,
    predecessor_backlog: bytes,
    predecessor_state: bytes,
    successor_backlog: bytes,
    successor_state: bytes,
    approved_state: str,
    evidence_reference: dict[str, Any],
) -> dict[str, Any]:
    predecessor_backlog_doc = yaml.safe_load(predecessor_backlog)
    predecessor_state_doc = strict_json(predecessor_state, "GCR-0007 predecessor state")
    successor_backlog_doc = yaml.safe_load(successor_backlog)
    successor_state_doc = strict_json(successor_state, "GCR-0007 successor state")
    return {
        "schemaVersion": "7.0-control-recovery-transaction",
        "documentType": "governance-control-recovery-noncircular-adoption-transaction",
        "controlRecoveryId": GCR_ID,
        "bootstrapUnit": BOOTSTRAP_ID,
        "status": "PREPARED",
        "actor": ACTOR,
        "branch": BRANCH,
        "packetAuthority": {"path": PACKET_PATH, "sha256": PACKET_SHA256, "commit": PACKET_COMMIT},
        "approvalAuthority": {
            "path": APPROVAL_PATH,
            "sha256": sha256(guard_repo_path(repo, APPROVAL_PATH).read_bytes()),
            "commit": APPROVAL_COMMIT,
        },
        "approvedStateAuthority": {
            "path": STATE_PATH,
            "sha256": sha256(predecessor_state),
            "commit": approved_state,
        },
        "adoptionEvidenceAuthority": copy.deepcopy(evidence_reference),
        "inertGcr6Feasibility": {
            "path": FEASIBILITY_PATH,
            "sha256": FEASIBILITY_SHA256,
            "commit": FEASIBILITY_COMMIT,
        },
        "hold": {"id": HOLD_ID, "status": "ACTIVE", "controlRevision": 11, "minimumToolRevision": 11},
        "witness": trigger_reference(),
        "lockPath": LOCK_PATH,
        "transactionPath": TRANSACTION_PATH,
        "backlogPath": BACKLOG_PATH,
        "statePath": STATE_PATH,
        "backlogNextPath": BACKLOG_NEXT_PATH,
        "stateNextPath": STATE_NEXT_PATH,
        "predecessor": {
            "controlRevision": 11,
            "minimumToolRevision": 11,
            "supportedControlCeiling": 11,
            "generationCount": 3,
            "backlog": binding(BACKLOG_PATH, predecessor_backlog, predecessor_backlog_doc),
            "state": binding(STATE_PATH, predecessor_state, predecessor_state_doc),
        },
        "successor": {
            "controlRevision": 11,
            "minimumToolRevision": 11,
            "supportedControlCeiling": 12,
            "generationCount": 4,
            "generationNeutral": True,
            "generationId": GCR_ID,
            "adoptionEvidence": copy.deepcopy(evidence_reference),
            "backlog": binding(BACKLOG_PATH, successor_backlog, successor_backlog_doc),
            "state": binding(STATE_PATH, successor_state, successor_state_doc),
        },
        "cas": {"rawBytes": True, "canonicalContent": True, "staleWriterDenied": True, "exactSuccessorOnly": True},
        "durability": {
            "exclusiveLock": True,
            "flushSuccessors": True,
            "flushManifest": True,
            "replaceExistingWriteThrough": True,
            "flushPublishedFiles": True,
            "flushDirectories": True,
        },
        "recovery": {
            "allowedTerminalStates": ["EXACT_PREDECESSOR_PAIR", "EXACT_SUCCESSOR_PAIR"],
            "dirtyWorkspaceDenied": True,
            "staleOrSubstitutedDenied": True,
            "idempotent": True,
            "cleanupAfterValidationOnly": True,
        },
        "finalization": {
            "topology": "approved-state-P to adoption-evidence-A to finalization-F",
            "deriveEvidenceCommit": "A-is-unique-direct-child-of-P-with-exact-evidence-only-delta",
            "deriveFinalizationCommit": "F-is-unique-direct-child-of-A-with-exact-backlog-and-state-delta",
            "exactChangedPaths": list(FINAL_PATHS),
            "canonicalContentContainsFinalizationCommit": False,
            "revisionUnchanged": True,
            "ordinaryExecutionStillDenied": True,
        },
        "publicationOrder": [
            "authenticate-P-and-A",
            "exclusive-lock",
            "durable-successors",
            "durable-manifest",
            "replace-backlog",
            "replace-state",
            "validate-exact-pair",
            "flush",
            "commit-F",
            "derive-and-validate-F",
            "cleanup",
        ],
        "ordinaryExecutionAuthority": False,
    }


def anchor_document(
    *,
    transaction: dict[str, Any],
    predecessor_backlog: bytes,
    predecessor_state: bytes,
    successor_backlog: bytes,
    successor_state: bytes,
) -> dict[str, Any]:
    return {
        "schemaVersion": "7.0-control-recovery-adoption-anchor",
        "controlRecoveryId": GCR_ID,
        "bootstrapUnit": BOOTSTRAP_ID,
        "approvedStateCommit": transaction["approvedStateAuthority"]["commit"],
        "adoptionEvidence": copy.deepcopy(transaction["adoptionEvidenceAuthority"]),
        "packetAuthority": copy.deepcopy(transaction["packetAuthority"]),
        "approvalAuthority": copy.deepcopy(transaction["approvalAuthority"]),
        "predecessor": copy.deepcopy(transaction["predecessor"]),
        "successor": copy.deepcopy(transaction["successor"]),
        "payloads": {
            "predecessorBacklog": base64.b64encode(predecessor_backlog).decode("ascii"),
            "predecessorState": base64.b64encode(predecessor_state).decode("ascii"),
            "successorBacklog": base64.b64encode(successor_backlog).decode("ascii"),
            "successorState": base64.b64encode(successor_state).decode("ascii"),
        },
    }


def _decode_payload(value: Any, label: str) -> bytes:
    if not isinstance(value, str):
        raise SystemExit(f"GCR-0007 anchor {label} snapshot is absent")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeError, ValueError) as exc:
        raise SystemExit(f"GCR-0007 anchor {label} snapshot is malformed") from exc


def validate_anchor(
    repo: Path,
    anchor: dict[str, Any],
    packet: dict[str, Any],
) -> tuple[dict[str, bytes], dict[str, bytes], str, str]:
    if (
        anchor.get("schemaVersion") != "7.0-control-recovery-adoption-anchor"
        or anchor.get("controlRecoveryId") != GCR_ID
        or anchor.get("bootstrapUnit") != BOOTSTRAP_ID
        or anchor.get("packetAuthority") != {"path": PACKET_PATH, "sha256": PACKET_SHA256, "commit": PACKET_COMMIT}
        or anchor.get("approvalAuthority", {}).get("commit") != APPROVAL_COMMIT
    ):
        raise SystemExit("GCR-0007 recovery anchor identity is invalid")
    approved_state = str(anchor.get("approvedStateCommit") or "")
    evidence_ref = anchor.get("adoptionEvidence") or {}
    evidence_commit = str(evidence_ref.get("commit") or "")
    evidence_relative = str(evidence_ref.get("path") or "")
    if (
        re.fullmatch(
            r"artifacts/evidence/governance-control-recovery/GCR-0007\.B00\.adoption(?:-R[0-9]{2})?\.json",
            evidence_relative,
        )
        is None
    ):
        raise SystemExit("GCR-0007 anchor adoption evidence path is invalid")
    _exact_parent(repo, approved_state, evidence_commit, {evidence_relative: "A"}, "GCR-0007 anchor A")
    evidence, evidence_payload = _git_document(
        repo, evidence_commit, evidence_relative, "GCR-0007 anchor adoption evidence"
    )
    if sha256(evidence_payload) != evidence_ref.get("sha256"):
        raise SystemExit("GCR-0007 anchor adoption evidence hash differs")
    validate_adoption_evidence(
        repo,
        evidence,
        evidence_payload,
        approved_state=approved_state,
        evidence_commit=evidence_commit,
        evidence_relative=evidence_relative,
    )
    payloads = anchor.get("payloads") or {}
    predecessor = {
        "backlog": _decode_payload(payloads.get("predecessorBacklog"), "predecessor backlog"),
        "state": _decode_payload(payloads.get("predecessorState"), "predecessor state"),
    }
    successor = {
        "backlog": _decode_payload(payloads.get("successorBacklog"), "successor backlog"),
        "state": _decode_payload(payloads.get("successorState"), "successor state"),
    }
    predecessor_backlog_doc = yaml.safe_load(predecessor["backlog"])
    predecessor_state_doc = strict_json(predecessor["state"], "GCR-0007 anchor predecessor state")
    successor_backlog_doc = yaml.safe_load(successor["backlog"])
    successor_state_doc = strict_json(successor["state"], "GCR-0007 anchor successor state")
    if (
        anchor.get("predecessor", {}).get("backlog")
        != binding(BACKLOG_PATH, predecessor["backlog"], predecessor_backlog_doc)
        or anchor.get("predecessor", {}).get("state")
        != binding(STATE_PATH, predecessor["state"], predecessor_state_doc)
        or anchor.get("successor", {}).get("backlog")
        != binding(BACKLOG_PATH, successor["backlog"], successor_backlog_doc)
        or anchor.get("successor", {}).get("state") != binding(STATE_PATH, successor["state"], successor_state_doc)
        or taskctl.git_blob(repo, approved_state, STATE_PATH) != predecessor["state"]
        or anchor.get("successor", {}).get("adoptionEvidence") != evidence_ref
    ):
        raise SystemExit("GCR-0007 recovery snapshots differ from their authenticated bindings")
    if not isinstance(predecessor_state_doc, dict):
        raise SystemExit("GCR-0007 predecessor state snapshot is malformed")
    validate_history(repo, predecessor_state_doc, packet)
    predecessor_attempts = _attempt_keys(predecessor_state_doc)
    if not predecessor_attempts or evidence_relative != adoption_evidence_path(predecessor_attempts[-1]):
        raise SystemExit("GCR-0007 anchor adoption evidence does not match the approved attempt")
    if predecessor_state_doc.get("status") != "APPROVED":
        raise SystemExit("GCR-0007 recovery predecessor is not independently approved")
    validate_successor_documents(repo, successor["backlog"], successor["state"])
    return predecessor, successor, approved_state, evidence_commit


@contextmanager
def adoption_lock(repo: Path, anchor: dict[str, Any]) -> Iterator[None]:
    path = transaction_artifacts(repo)[LOCK_PATH]
    if os.path.lexists(path):
        raise SystemExit("GCR-0007 adoption lock already exists or is redirected")
    write_new_durable(path, json_bytes(anchor))
    adoption_fault_boundary("gcr7-lock-durable")
    yield


def load_anchor(repo: Path, packet: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, bytes], str, str]:
    path = transaction_artifacts(repo)[LOCK_PATH]
    if not path.is_file() or path.is_symlink():
        raise SystemExit("GCR-0007 recovery anchor is absent or redirected")
    anchor, _payload = load_json(path, "GCR-0007 recovery anchor")
    return validate_anchor(repo, anchor, packet)


def _manifest_write(repo: Path, transaction: dict[str, Any], status: str) -> None:
    updated = copy.deepcopy(transaction)
    updated["status"] = status
    validate_transaction(repo, updated)
    write_json_atomic(repo / TRANSACTION_PATH, updated)
    fsync_directory((repo / TRANSACTION_PATH).parent)


def _pair_matches(repo: Path, snapshots: dict[str, bytes]) -> bool:
    for label, relative in (("backlog", BACKLOG_PATH), ("state", STATE_PATH)):
        path = guard_repo_path(repo, relative)
        if path.read_bytes() != snapshots[label]:
            return False
    return True


def _publish_payload(repo: Path, relative: str, next_relative: str, payload: bytes, label: str) -> None:
    artifacts = transaction_artifacts(repo)
    live = guard_repo_path(repo, relative)
    if live.read_bytes() == payload:
        return
    staged = artifacts[next_relative]
    if not staged.is_file() or staged.is_symlink() or staged.read_bytes() != payload:
        if os.path.lexists(staged):
            raise SystemExit(f"GCR-0007 {label} durable successor is substituted")
        write_new_durable(staged, payload)
    guard_repo_path(repo, relative)
    move_write_through(staged, live)
    if guard_repo_path(repo, relative).read_bytes() != payload:
        raise SystemExit(f"GCR-0007 {label} publication verification failed")


def complete_transaction(
    repo: Path,
    transaction: dict[str, Any],
    successor: dict[str, bytes],
) -> None:
    validate_transaction(repo, transaction)
    validate_successor_documents(repo, successor["backlog"], successor["state"])
    _publish_payload(repo, BACKLOG_PATH, BACKLOG_NEXT_PATH, successor["backlog"], "backlog")
    _manifest_write(repo, transaction, "BACKLOG_PUBLISHED")
    adoption_fault_boundary("gcr7-backlog-published")
    _publish_payload(repo, STATE_PATH, STATE_NEXT_PATH, successor["state"], "state")
    _manifest_write(repo, transaction, "STATE_PUBLISHED")
    adoption_fault_boundary("gcr7-state-published")
    if not _pair_matches(repo, successor):
        raise SystemExit("GCR-0007 publication produced a split successor pair")
    _manifest_write(repo, transaction, "VALIDATED")
    adoption_fault_boundary("gcr7-successor-validated")
    fsync_directory((repo / BACKLOG_PATH).parent)
    fsync_directory((repo / STATE_PATH).parent)
    adoption_fault_boundary("gcr7-successor-directories-durable")


def _restore_predecessor(repo: Path, predecessor: dict[str, bytes], evidence_commit: str) -> None:
    if git(repo, "rev-parse", "HEAD") != evidence_commit:
        raise SystemExit("GCR-0007 recovery refuses to restore predecessor after finalization history exists")
    for label, relative, next_relative in (
        ("backlog", BACKLOG_PATH, BACKLOG_NEXT_PATH),
        ("state", STATE_PATH, STATE_NEXT_PATH),
    ):
        staged = transaction_artifacts(repo)[next_relative]
        if os.path.lexists(staged):
            if not staged.is_file() or staged.is_symlink():
                raise SystemExit(f"GCR-0007 {label} recovery artifact is redirected")
            unlink_durable(staged)
        write_new_durable(staged, predecessor[label])
        guard_repo_path(repo, relative)
        move_write_through(staged, repo / relative)
        adoption_fault_boundary(f"gcr7-{label}-predecessor-restored")
    if not _pair_matches(repo, predecessor):
        raise SystemExit("GCR-0007 predecessor restoration did not produce an exact pair")


def cleanup_transaction(repo: Path) -> None:
    artifacts = transaction_artifacts(repo)
    for relative in (TRANSACTION_PATH, BACKLOG_NEXT_PATH, STATE_NEXT_PATH, LOCK_PATH):
        path = artifacts[relative]
        if os.path.lexists(path):
            if not path.is_file() or path.is_symlink():
                raise SystemExit(f"GCR-0007 transaction artifact is redirected: {relative}")
            unlink_durable(path)
            adoption_fault_boundary(f"gcr7-cleanup-{PurePosixPath(relative).name}")


def derive_finalization(
    repo: Path,
    *,
    evidence_commit: str,
    successor: dict[str, bytes] | None = None,
) -> str | None:
    head = git(repo, "rev-parse", "HEAD")
    if head == evidence_commit:
        return None
    candidates = taskctl.git_commits_changing_path_after(repo, evidence_commit, STATE_PATH)
    matches: list[str] = []
    for commit in candidates:
        try:
            parents = git(repo, "rev-list", "--parents", "-n", "1", commit).split()
        except SystemExit:
            continue
        if parents != [commit, evidence_commit]:
            continue
        if taskctl.git_name_status_delta(repo, evidence_commit, commit) != {BACKLOG_PATH: "M", STATE_PATH: "M"}:
            continue
        backlog_blob = taskctl.git_blob(repo, commit, BACKLOG_PATH)
        state_blob = taskctl.git_blob(repo, commit, STATE_PATH)
        if backlog_blob is None or state_blob is None:
            continue
        try:
            backlog = yaml.safe_load(backlog_blob)
            state = strict_json(state_blob, "GCR-0007 finalization state")
            if not isinstance(backlog, dict) or not isinstance(state, dict):
                continue
            exact_generation(backlog)
            validate_runtime(repo, state, "GCR-0007 finalization state")
        except SystemExit, yaml.YAMLError:
            continue
        activation = state.get("activation") or {}
        if (
            state.get("status") != "HEADROOM_ACTIVATION_FINALIZATION"
            or (activation.get("adoptionEvidence") or {}).get("commit") != evidence_commit
            or "finalizationCommit" in activation
        ):
            continue
        if successor is not None and (
            backlog_blob != successor["backlog"].replace(b"\r\n", b"\n") or state_blob != successor["state"]
        ):
            continue
        matches.append(commit)
    if not matches:
        return None
    if len(matches) != 1:
        raise SystemExit("GCR-0007 finalization F is forked or non-unique")
    finalization = matches[0]
    if not taskctl.git_is_ancestor(repo, finalization):
        raise SystemExit("GCR-0007 finalization F is not ancestral to HEAD")
    return finalization


def recover_transaction(
    repo: Path,
    packet: dict[str, Any],
) -> str:
    if not present_transaction_artifacts(repo):
        return "ABSENT"
    require_workspace(repo, transaction=True)
    with taskctl.exclusive_backlog_lock(repo / BACKLOG_PATH):
        predecessor, successor, _approved_state, evidence_commit = load_anchor(repo, packet)
        manifest = transaction_artifacts(repo)[TRANSACTION_PATH]
        if not manifest.exists():
            finalization = derive_finalization(repo, evidence_commit=evidence_commit, successor=successor)
            if finalization is not None:
                if not _pair_matches(repo, successor):
                    raise SystemExit("GCR-0007 committed finalization differs from its durable successor anchor")
                cleanup_transaction(repo)
                return f"COMPLETED_SUCCESSOR:{finalization}"
            _restore_predecessor(repo, predecessor, evidence_commit)
            cleanup_transaction(repo)
            return "RESTORED_PREDECESSOR"
        transaction, _payload = load_json(manifest, "GCR-0007 transaction")
        validate_transaction(repo, transaction)
        if (
            transaction.get("approvedStateAuthority", {}).get("commit") != _approved_state
            or transaction.get("adoptionEvidenceAuthority", {}).get("commit") != evidence_commit
            or transaction.get("predecessor") != anchor_from_snapshots(predecessor, transaction, "predecessor")
            or transaction.get("successor") != anchor_from_snapshots(successor, transaction, "successor")
        ):
            raise SystemExit("GCR-0007 transaction differs from its durable authenticated anchor")
        complete_transaction(repo, transaction, successor)
        finalization = derive_finalization(repo, evidence_commit=evidence_commit, successor=successor)
        if finalization is None:
            return "AWAITING_EXACT_FINALIZATION_F"
        cleanup_transaction(repo)
        return f"COMPLETED_SUCCESSOR:{finalization}"


def anchor_from_snapshots(snapshots: dict[str, bytes], transaction: dict[str, Any], generation: str) -> dict[str, Any]:
    backlog_doc = yaml.safe_load(snapshots["backlog"])
    state_doc = strict_json(snapshots["state"], f"GCR-0007 {generation} state")
    result = copy.deepcopy(transaction[generation])
    result["backlog"] = binding(BACKLOG_PATH, snapshots["backlog"], backlog_doc)
    result["state"] = binding(STATE_PATH, snapshots["state"], state_doc)
    return result


def prepare_transaction(
    repo: Path,
    *,
    anchor: dict[str, Any],
    transaction: dict[str, Any],
    predecessor: dict[str, bytes],
    successor: dict[str, bytes],
) -> None:
    artifacts = transaction_artifacts(repo)
    with taskctl.exclusive_backlog_lock(repo / BACKLOG_PATH), adoption_lock(repo, anchor):
        if (
            guard_repo_path(repo, BACKLOG_PATH).read_bytes() != predecessor["backlog"]
            or guard_repo_path(repo, STATE_PATH).read_bytes() != predecessor["state"]
        ):
            raise SystemExit("GCR-0007 predecessor changed before transaction preparation")
        write_new_durable(artifacts[BACKLOG_NEXT_PATH], successor["backlog"])
        adoption_fault_boundary("gcr7-backlog-next-durable")
        write_new_durable(artifacts[STATE_NEXT_PATH], successor["state"])
        adoption_fault_boundary("gcr7-state-next-durable")
        write_new_durable(artifacts[TRANSACTION_PATH], json_bytes(transaction))
        adoption_fault_boundary("gcr7-transaction-durable")
        complete_transaction(repo, transaction, successor)


def command_adopt(args: argparse.Namespace) -> None:
    _approval, packet, _base = load_authority(args.repo)
    if present_transaction_artifacts(args.repo):
        raise SystemExit("GCR-0007 adoption transaction already exists; run recover")
    state, state_payload = load_state(args.repo, packet, required=True)
    assert state is not None and state_payload is not None
    reviewed_state, approved_state, ledger_ref, _ledger_payload = canonical_approved_state(
        args.repo, state, state_payload
    )
    if str(args.approved_state_commit) != approved_state:
        raise SystemExit("GCR-0007 approved-state argument differs from canonical P")
    if args.agent != ACTOR:
        raise SystemExit(f"GCR-0007 adopter must be exact actor {ACTOR}")
    evidence_relative = str(args.evidence)
    attempts = _attempt_keys(state)
    expected_evidence_relative = adoption_evidence_path(attempts[-1])
    if evidence_relative != expected_evidence_relative:
        raise SystemExit(f"GCR-0007 adoption evidence path must be {expected_evidence_relative}")
    evidence_commit = git(args.repo, "rev-parse", "HEAD")
    evidence, evidence_payload = _git_document(
        args.repo, evidence_commit, evidence_relative, "GCR-0007 adoption evidence"
    )
    validate_adoption_evidence(
        args.repo,
        evidence,
        evidence_payload,
        approved_state=approved_state,
        evidence_commit=evidence_commit,
        evidence_relative=evidence_relative,
    )
    require_workspace(args.repo)
    predecessor_backlog = guard_repo_path(args.repo, BACKLOG_PATH).read_bytes()
    if sha256(predecessor_backlog) != BACKLOG_PREDECESSOR_RAW_SHA256:
        raise SystemExit("GCR-0007 adoption predecessor backlog bytes are stale")
    predecessor = yaml.safe_load(predecessor_backlog)
    if not isinstance(predecessor, dict):
        raise SystemExit("GCR-0007 predecessor backlog is malformed")
    validate_boundary(predecessor)
    now = taskctl.utc_now()
    successor = copy.deepcopy(taskctl.serializable_backlog(predecessor))
    control = successor["control_plane"]
    control["control_generations"].append(
        generation_record(
            args.repo,
            reviewed_state=reviewed_state,
            approved_state=approved_state,
            ledger_reference=ledger_ref,
            adopted_at=now,
        )
    )
    control["revision"] = 11
    control["minimum_tool_revision"] = 11
    prove_old_reader_fails_closed(args.repo, successor)
    evidence_reference = {"path": evidence_relative, "sha256": sha256(evidence_payload), "commit": evidence_commit}
    successor_state = copy.deepcopy(state)
    successor_state["status"] = "HEADROOM_ACTIVATION_FINALIZATION"
    successor_state["activation"] = {
        "approvedStateCommit": approved_state,
        "adoptionEvidence": evidence_reference,
        "predecessorRevision": 11,
        "successorRevision": 11,
        "supportedControlCeiling": 12,
        "generationNeutral": True,
        "changedPaths": list(FINAL_PATHS),
        "ordinaryExecutionAuthority": False,
    }
    successor_backlog = yaml.safe_dump(
        taskctl.serializable_backlog(successor), sort_keys=False, allow_unicode=True, width=120
    ).encode()
    successor_state_payload = json_bytes(successor_state)
    validate_successor_documents(args.repo, successor_backlog, successor_state_payload)
    transaction = transaction_document(
        args.repo,
        predecessor_backlog=predecessor_backlog,
        predecessor_state=state_payload,
        successor_backlog=successor_backlog,
        successor_state=successor_state_payload,
        approved_state=approved_state,
        evidence_reference=evidence_reference,
    )
    validate_transaction(args.repo, transaction)
    anchor = anchor_document(
        transaction=transaction,
        predecessor_backlog=predecessor_backlog,
        predecessor_state=state_payload,
        successor_backlog=successor_backlog,
        successor_state=successor_state_payload,
    )
    validate_anchor(args.repo, anchor, packet)
    prepare_transaction(
        args.repo,
        anchor=anchor,
        transaction=transaction,
        predecessor={"backlog": predecessor_backlog, "state": state_payload},
        successor={"backlog": successor_backlog, "state": successor_state_payload},
    )
    print(
        "Prepared exact GCR-0007 neutral successor. Commit only planning/backlog.yaml and the GCR-0007 state "
        "as F, then run recover to authenticate F and clean transaction artifacts."
    )


def command_recover(args: argparse.Namespace) -> None:
    if args.agent != ACTOR:
        raise SystemExit(f"GCR-0007 recovery actor must be exact {ACTOR}")
    _approval, packet, _base = load_authority(args.repo, allow_transaction_boundary=True)
    result = recover_transaction(args.repo, packet)
    print(f"GCR-0007 adoption recovery: {result}; ordinary execution remains unauthorized")


def validate_current_boundary(
    repo: Path,
    packet: dict[str, Any],
    *,
    state_required: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    present = present_transaction_artifacts(repo)
    if present:
        raise SystemExit("GCR-0007 transaction requires explicit recovery: " + ", ".join(present))
    require_workspace(repo)
    state, _payload = load_state(repo, packet, required=state_required)
    backlog_payload = guard_repo_path(repo, BACKLOG_PATH).read_bytes()
    head = git(repo, "rev-parse", "HEAD")
    head_backlog = taskctl.git_blob(repo, head, BACKLOG_PATH)
    if state is None or state.get("status") != "HEADROOM_ACTIVATION_FINALIZATION":
        canonical = taskctl.git_blob(repo, AUTHORITY_BASE_COMMIT, BACKLOG_PATH)
        if (
            sha256(backlog_payload) != BACKLOG_PREDECESSOR_RAW_SHA256
            or head_backlog != canonical
            or (state is None and taskctl.git_blob(repo, head, STATE_PATH) is not None)
        ):
            raise SystemExit("GCR-0007 live predecessor differs from its exact raw and Git boundary")
        return state, None
    state_payload = guard_repo_path(repo, STATE_PATH).read_bytes()
    validate_successor_documents(repo, backlog_payload, state_payload)
    evidence_commit = str(((state.get("activation") or {}).get("adoptionEvidence") or {}).get("commit") or "")
    finalization = derive_finalization(
        repo,
        evidence_commit=evidence_commit,
        successor={"backlog": backlog_payload, "state": state_payload},
    )
    if (
        finalization is None
        or head_backlog != backlog_payload.replace(b"\r\n", b"\n")
        or taskctl.git_blob(repo, head, STATE_PATH) != state_payload.replace(b"\r\n", b"\n")
    ):
        raise SystemExit("GCR-0007 live successor is not the exact committed P-to-A-to-F finalization")
    return state, finalization


def command_validate(args: argparse.Namespace) -> None:
    _approval, packet, _base = load_authority(args.repo)
    state, finalization = validate_current_boundary(args.repo, packet, state_required=True)
    assert state is not None
    if state.get("status") == "HEADROOM_ACTIVATION_FINALIZATION":
        assert finalization is not None
        print(f"Valid GCR-0007: derived HEADROOM_ACTIVE at exact finalization {finalization}")
        return
    if args.require_approved and state.get("status") != "APPROVED":
        raise SystemExit("GCR-0007 B00 is not independently approved")
    print(f"Valid GCR-0007: B00={state.get('status')}; live revision remains 11")


def command_status(args: argparse.Namespace) -> None:
    _approval, packet, _base = load_authority(args.repo)
    state, finalization = validate_current_boundary(args.repo, packet, state_required=False)
    if state is None:
        status = "READY"
        attempts: list[str] = []
    else:
        status = str(state.get("status"))
        attempts = _attempt_keys(state)
        if status == "HEADROOM_ACTIVATION_FINALIZATION" and finalization is not None:
            status = "HEADROOM_ACTIVE" if finalization else status
    print(
        yaml.safe_dump(
            {
                "controlRecovery": GCR_ID,
                "bootstrap": BOOTSTRAP_ID,
                "status": status,
                "attempts": attempts,
                "derivedFinalization": finalization,
                "liveControlRevision": 11,
                "supportedControlCeiling": 12 if finalization else 11,
                "ordinaryExecutionAuthority": False,
            },
            sort_keys=False,
        ).rstrip()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    subparsers = parser.add_subparsers(dest="command", required=True)
    submit = subparsers.add_parser("submit")
    submit.add_argument("request")
    submit.add_argument("--agent", required=True)
    submit.add_argument("--approval-commit", required=True)
    submit.add_argument("--implementation-commit", required=True)
    submit.add_argument("--evidence", required=True)
    submit.set_defaults(func=lambda args: freeze_submission(args, remediation=False))
    resubmit = subparsers.add_parser("resubmit")
    resubmit.add_argument("request")
    resubmit.add_argument("--agent", required=True)
    resubmit.add_argument("--implementation-commit", required=True)
    resubmit.add_argument("--evidence", required=True)
    resubmit.set_defaults(func=lambda args: freeze_submission(args, remediation=True))
    review = subparsers.add_parser("review")
    review.add_argument("request")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--from", dest="ledger", required=True)
    review.set_defaults(func=command_review)
    adopt = subparsers.add_parser("adopt")
    adopt.add_argument("request")
    adopt.add_argument("--agent", required=True)
    adopt.add_argument("--approved-state-commit", required=True)
    adopt.add_argument("--evidence", required=True)
    adopt.set_defaults(func=command_adopt)
    recover = subparsers.add_parser("recover")
    recover.add_argument("request")
    recover.add_argument("--agent", required=True)
    recover.set_defaults(func=command_recover)
    validate = subparsers.add_parser("validate")
    validate.add_argument("request")
    validate.add_argument("--require-approved", action="store_true")
    validate.set_defaults(func=command_validate)
    status = subparsers.add_parser("status")
    status.add_argument("request")
    status.set_defaults(func=command_status)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.repo = args.repo.resolve()
    if getattr(args, "request", GCR_ID) != GCR_ID:
        raise SystemExit(f"This controller recognizes only {GCR_ID}")
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
