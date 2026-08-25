#!/usr/bin/env python3
"""Exact, one-time GCR-0003 controller-generation bootstrap.

This controller recognizes only GCR-0003.B00. It cannot create or approve a
recovery supplement, append an amendment, release a hold, resume a Wave, claim
a task, or approve a release gate.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import subprocess
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

GCR_ID = "GCR-0003"
BOOTSTRAP_ID = "GCR-0003.B00"
BRANCH = "codex/w1-windows-local-runtime"
ACTOR = "codex"
PACKET_COMMIT = "f062cff48036bce9f094b86370a9499837f4b358"
PACKET_SHA256 = "dc6055395a409fe4a9753657522cf54181bf881c15c72ba65aa3cccd32d2a666"
AUTHORITY_BASE_COMMIT = "72e2989440292ca30f8b5d4717aa61c56c5b9f48"
PACKET_PATH = "planning/governance-control-recovery/GCR-0003.packet.json"
APPROVAL_PATH = "planning/governance-control-recovery/GCR-0003.approval.json"
APPROVAL_COMMIT = "d6ec319a6d9d3ccbc5fc195e91d8ee6be594ef3c"
REQUEST_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-request.v3.schema.json"
RUNTIME_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-runtime.v3.schema.json"
SUCCESSOR_RUNTIME_SCHEMA_PATH = "planning/governance-control-recovery/GCR-0004.B00.gcr3-runtime.schema.json"
TRANSACTION_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-transaction.v3.schema.json"
STATE_PATH = "planning/governance-control-recovery/GCR-0003.B00.state.json"
TRANSACTION_PATH = "planning/governance-control-recovery/GCR-0003.B00.adoption-transaction.json"
LOCK_PATH = "planning/governance-control-recovery/GCR-0003.B00.adoption.lock"
BACKLOG_NEXT_PATH = "planning/governance-control-recovery/GCR-0003.B00.adoption-backlog.next"
STATE_NEXT_PATH = "planning/governance-control-recovery/GCR-0003.B00.adoption-state.next"
BACKLOG_PATH = "planning/backlog.yaml"
TRIGGER_PATH = "artifacts/evidence/W1.A04.B00.json"
TRIGGER_SHA256 = "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c"
BACKLOG_SHA256 = "c7347d103cc1fc6cf54be319f96a8ca5dcf74eddbedd70a3d77a097d335b978d"
ADOPTION_EVIDENCE_PATH = "artifacts/evidence/governance-control-recovery/GCR-0003.B00.adoption.json"
PREDECESSOR_REVISION = 9
SUCCESSOR_REVISION = 10
SUPPORTED_CONTROL_CEILING = 11
RESULT_STATUS = {"approved": "APPROVED", "changes-requested": "CHANGES_REQUESTED", "blocked": "BLOCKED"}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
GCR4_ID = "GCR-0004"
GCR4_BOOTSTRAP_ID = "GCR-0004.B00"
GCR4_PACKET_PATH = "planning/governance-control-recovery/GCR-0004.packet.json"
GCR4_PACKET_COMMIT = "55cfb8ed74166398e387228a90b30365e78bf3cd"
GCR4_PACKET_SHA256 = "274b0fc717691e909c7d05d1bf6411beca69749ed6d45ff30039ce6d33c57591"
GCR4_PACKET_REVIEW_PATH = "planning/governance-control-recovery/GCR-0004.review-R01.json"
GCR4_PACKET_REVIEW_COMMIT = "edac7c8bf30c9b29dfde3cf351894a9de3c3fa73"
GCR4_PACKET_REVIEW_SHA256 = "12fcc12914d4e30d038fc8c3d4d8822247e2481e6b19877ac9bd21bc70af9e4e"
GCR4_APPROVAL_PATH = "planning/governance-control-recovery/GCR-0004.approval.json"
GCR4_APPROVAL_COMMIT = "e56218e5c0cc2823d78cfb855e66eb82d39c4cda"
GCR4_APPROVAL_SHA256 = "a3d310939084de2b03f5f2980ace59a9680394f3d611f05d63fe9c9b4976ff5b"
GCR4_STATE_PATH = "planning/governance-control-recovery/GCR-0004.B00.state.json"
GCR4_APPLICATION_EVIDENCE_PATH = "artifacts/evidence/governance-control-recovery/GCR-0004.B00.application.json"
GCR3_R01_CANDIDATE_COMMIT = "a0988d8d9cfde8cde5cc9cf148f9b37ae8e13873"
GCR3_R01_REVIEWED_STATE_COMMIT = "702ffbc587cca2ec05567d86dc9fd0fa0a25b4a5"
GCR3_R01_REVIEWED_STATE_SHA256 = "0828cb7a52ff5f739dcfbc49832e7b2437f997fced38bac917098081368328e4"
GCR3_R01_LEDGER_PATH = "planning/governance-control-recovery/GCR-0003.B00.review-R01.json"
GCR3_R01_LEDGER_SHA256 = "cdfdb2f9fc122cb1a3be3d4546542dfc108a35c96995a340d32b5ae3510ba93b"


def trigger_witness() -> dict[str, Any]:
    return {
        "path": TRIGGER_PATH,
        "sha256": TRIGGER_SHA256,
        "role": "atomic-failure-trigger-only",
        "untracked": True,
        "unstaged": True,
        "executionAuthority": False,
    }


def load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object")
    return value, payload


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
    schema = (
        SUCCESSOR_RUNTIME_SCHEMA_PATH
        if document.get("schemaVersion") == "3.1-control-recovery-state"
        else RUNTIME_SCHEMA_PATH
    )
    validate_schema(repo, document, schema, label)


def validate_transaction(repo: Path, document: dict[str, Any]) -> None:
    validate_schema(repo, document, TRANSACTION_SCHEMA_PATH, "GCR-0003 adoption transaction")


def validate_trigger(repo: Path) -> None:
    path = safe_path(repo, TRIGGER_PATH, label="GCR-0003 trigger witness", prefix="artifacts/evidence")
    if path.is_symlink() or getattr(os.path, "isjunction", lambda _value: False)(path):
        raise SystemExit("GCR-0003 trigger witness must not be redirected")
    if sha256(path.read_bytes()) != TRIGGER_SHA256:
        raise SystemExit("GCR-0003 trigger witness is missing or has changed")
    if TRIGGER_PATH in set(git(repo, "ls-files", "--", TRIGGER_PATH).splitlines()):
        raise SystemExit("GCR-0003 trigger witness must remain untracked")
    if TRIGGER_PATH in set(git(repo, "diff", "--cached", "--name-only", "--").splitlines()):
        raise SystemExit("GCR-0003 trigger witness must remain unstaged")


def require_workspace(repo: Path, *, extra_untracked: set[str] | None = None) -> None:
    if git(repo, "branch", "--show-current") != BRANCH:
        raise SystemExit(f"GCR-0003 transitions require exact branch {BRANCH}")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=repo, check=False).returncode != 0:
        raise SystemExit("Tracked worktree changes exist; GCR-0003 transitions require an exact commit")
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise SystemExit("Staged changes exist; GCR-0003 transitions require an exact commit")
    validate_trigger(repo)
    allowed = {TRIGGER_PATH, *(extra_untracked or set())}
    untracked = set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    if untracked != allowed:
        difference = sorted(untracked ^ allowed)
        raise SystemExit(f"GCR-0003 untracked-path boundary differs: {difference[0] if difference else '<unknown>'}")


def require_recovery_workspace(repo: Path) -> None:
    if git(repo, "branch", "--show-current") != BRANCH:
        raise SystemExit(f"GCR-0003 recovery requires exact branch {BRANCH}")
    validate_trigger(repo)
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise SystemExit("GCR-0003 recovery refuses staged changes")
    tracked = set(git(repo, "diff", "--name-only", "HEAD", "--").splitlines())
    if not tracked.issubset({BACKLOG_PATH, STATE_PATH}):
        raise SystemExit(f"GCR-0003 recovery tracked-path boundary differs: {sorted(tracked)[0]}")
    allowed = {TRIGGER_PATH, *transaction_artifacts(repo)}
    untracked = set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    if not untracked.issubset(allowed) or TRIGGER_PATH not in untracked:
        difference = sorted(untracked ^ (untracked & allowed))
        raise SystemExit(
            f"GCR-0003 recovery untracked-path boundary differs: {difference[0] if difference else '<unknown>'}"
        )


def load_authority(repo: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    packet, packet_payload = load_json(safe_path(repo, PACKET_PATH, label="GCR-0003 packet"), "GCR-0003 packet")
    approval, approval_payload = load_json(
        safe_path(repo, APPROVAL_PATH, label="GCR-0003 approval"), "GCR-0003 approval"
    )
    if sha256(packet_payload) != PACKET_SHA256 or taskctl.git_blob(repo, PACKET_COMMIT, PACKET_PATH) != packet_payload:
        raise SystemExit("GCR-0003 packet differs from its approved immutable Git blob")
    validate_schema(repo, packet, REQUEST_SCHEMA_PATH, "GCR-0003 packet")
    validate_runtime(repo, approval, "GCR-0003 approval")
    introduction = taskctl.approval_introduction_commit(repo, APPROVAL_PATH)
    if introduction != APPROVAL_COMMIT or taskctl.git_blob(repo, introduction, APPROVAL_PATH) != approval_payload:
        raise SystemExit("GCR-0003 approval is absent, replaced, or edited after introduction")
    packet_reference = approval.get("packet") or {}
    review_reference = (approval.get("independentPacketReview") or {}).get("ledger") or {}
    if (
        packet_reference != {"path": PACKET_PATH, "sha256": PACKET_SHA256, "commit": PACKET_COMMIT}
        or approval.get("status") != "APPROVED"
        or approval.get("controlRecoveryId") != GCR_ID
        or approval.get("triggerWitness") != trigger_witness()
        or (approval.get("executionAuthority") or {}).get("bootstrapUnit") != BOOTSTRAP_ID
        or not taskctl.git_is_ancestor(repo, PACKET_COMMIT, introduction)
    ):
        raise SystemExit("GCR-0003 approval identity, packet, witness, or scope is invalid")
    review_relative = str(review_reference.get("path") or "")
    review_path = safe_path(
        repo, review_relative, label="GCR-0003 packet review", prefix="planning/governance-control-recovery"
    )
    review_payload = review_path.read_bytes()
    review_commit = str(review_reference.get("commit") or "")
    if (
        sha256(review_payload) != review_reference.get("sha256")
        or not taskctl.git_commit_exists(repo, review_commit)
        or not taskctl.git_is_ancestor(repo, review_commit)
        or taskctl.git_blob(repo, review_commit, review_relative) != review_payload
    ):
        raise SystemExit("GCR-0003 packet review binding is invalid")
    review = json.loads(review_payload)
    validate_runtime(repo, review, "GCR-0003 packet review")
    if (
        review.get("documentType") != "governance-control-recovery-packet-review"
        or review.get("candidateCommit") != PACKET_COMMIT
        or review.get("packetSha256") != PACKET_SHA256
        or review.get("result") != "approved"
        or review.get("findings") != []
        or review.get("approvalAvailable") is not True
    ):
        raise SystemExit("GCR-0003 packet review is adverse, stale, or not approval-eligible")
    for reference in packet.get("files", []):
        relative = str(reference.get("path") or "")
        payload = safe_path(repo, relative, label="GCR-0003 packet file").read_bytes()
        if sha256(payload) != reference.get("sha256") or taskctl.git_blob(repo, PACKET_COMMIT, relative) != payload:
            raise SystemExit(f"GCR-0003 packet file binding is invalid: {relative}")
    for pattern in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", []):
        validate_scope_pattern(str(pattern))
    validate_trigger(repo)
    return approval, packet, str(introduction)


def current_boundary(repo: Path, packet: dict[str, Any], *, revision: int) -> tuple[bytes, dict[str, Any]]:
    path = repo / BACKLOG_PATH
    payload = path.read_bytes()
    data, _capabilities, _slices, tasks, gates = taskctl.load(str(path))
    control = data.get("control_plane") or {}
    active = taskctl.active_recovery_holds(data)
    hold = active[0] if len(active) == 1 else {}
    wave = taskctl.wave_map(data).get("W1") or {}
    task = tasks.get("CAP-02.S04.T03") or {}
    gate = gates.get("G1") or {}
    supplements = hold.get("supplements") or []
    if (
        control.get("revision") != revision
        or control.get("minimum_tool_revision") != revision
        or hold.get("id") != "HOLD-W1-GRR-0002"
        or hold.get("status") != "ACTIVE"
        or (hold.get("bootstrap") or {}).get("status") != "APPROVED"
        or not supplements
        or supplements[0].get("id") != "GRR-0002.S01"
        or (supplements[0].get("bootstrap") or {}).get("status") != "APPROVED"
        or (wave.get("campaign") or {}).get("status") != "PAUSED"
        or (wave.get("campaign") or {}).get("scope") != "wave"
        or task.get("status") != "BLOCKED"
        or task.get("recovery_control") is not None
        or "W1.A04" in taskctl.wave_amendment_map(data)
        or gate.get("status") != "PENDING"
    ):
        raise SystemExit("GCR-0003 stopped boundary differs from the exact approved packet")
    if revision == PREDECESSOR_REVISION:
        if (
            sha256(payload) != BACKLOG_SHA256
            or (packet.get("activationBoundary") or {}).get("controlRevision") != PREDECESSOR_REVISION
        ):
            raise SystemExit("GCR-0003 revision-9 boundary differs from its approved trigger")
        generations = control.get("control_generations") or []
        if [item.get("id") for item in generations] != ["GCR-0001", "GCR-0002"]:
            raise SystemExit("GCR-0003 predecessor generation ledger is invalid")
        if [item.get("id") for item in supplements] != ["GRR-0002.S01"]:
            raise SystemExit("GCR-0003 predecessor supplement ledger is invalid")
    elif revision in {SUCCESSOR_REVISION, SUPPORTED_CONTROL_CEILING}:
        generations = control.get("control_generations") or []
        if [item.get("id") for item in generations] != ["GCR-0001", "GCR-0002", "GCR-0003"]:
            raise SystemExit("GCR-0003 successor generation ledger is invalid")
        expected_supplements = ["GRR-0002.S01"] if revision == SUCCESSOR_REVISION else ["GRR-0002.S01", "GRR-0002.S02"]
        if [item.get("id") for item in supplements] != expected_supplements:
            raise SystemExit("GCR-0003 successor supplement ledger is invalid")
        if revision == SUPPORTED_CONTROL_CEILING:
            latest = supplements[-1]
            if (
                latest.get("predecessor_control_revision") != SUCCESSOR_REVISION
                or latest.get("successor_control_revision") != SUPPORTED_CONTROL_CEILING
            ):
                raise SystemExit("GCR-0003 successor supplement transition is invalid")
    else:
        raise SystemExit("GCR-0003 recognizes only control revisions 9 through 11")
    return payload, data


def load_state(repo: Path, *, required: bool) -> tuple[dict[str, Any] | None, bytes | None]:
    path = repo / STATE_PATH
    if not path.is_file():
        if required:
            raise SystemExit("Canonical GCR-0003 state does not exist")
        return None, None
    state, payload = load_json(path, "GCR-0003 state")
    validate_runtime(repo, state, "GCR-0003 state")
    if (
        state.get("controlRecoveryId") != GCR_ID
        or state.get("bootstrapUnit") != BOOTSTRAP_ID
        or state.get("triggerWitness") != trigger_witness()
    ):
        raise SystemExit("GCR-0003 state identity or trigger witness is invalid")
    return state, payload


def evidence_path(attempt_id: str) -> str:
    return f"artifacts/evidence/governance-control-recovery/{BOOTSTRAP_ID}.{attempt_id}.json"


def review_path(attempt_id: str) -> str:
    return f"planning/governance-control-recovery/{BOOTSTRAP_ID}.review-{attempt_id}.json"


def changed_paths(repo: Path, base: str, candidate: str) -> list[str]:
    if not taskctl.git_commit_exists(repo, base) or not taskctl.git_commit_exists(repo, candidate):
        raise SystemExit("GCR-0003 base or candidate commit is absent")
    if base == candidate or not taskctl.git_is_ancestor(repo, base, candidate):
        raise SystemExit("GCR-0003 candidate must strictly descend from its required base")
    return sorted(filter(None, git(repo, "diff", "--name-only", f"{base}..{candidate}", "--").splitlines()))


def open_findings(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    opened: dict[str, dict[str, Any]] = {}
    for attempt in state.get("attempts", []):
        for closure in attempt.get("closures", []):
            opened.pop(str(closure.get("findingId") or ""), None)
        for finding in attempt.get("findings", []):
            opened[str(finding.get("id") or "")] = finding
    return opened


def required_root_cause(attempt_index: int, supplied: object = None) -> str | None:
    if attempt_index < 2:
        if supplied is not None:
            raise SystemExit("GCR-0003 root-cause analysis is not allowed before the third submission")
        return None
    if not isinstance(supplied, str) or not supplied.strip() or supplied != supplied.strip():
        raise SystemExit("GCR-0003 third and later submissions require a normalized root-cause analysis")
    return supplied


def _immutable_json(
    repo: Path, *, path: str, commit: str, expected_sha256: str, label: str
) -> tuple[dict[str, Any], bytes]:
    document, payload = load_json(safe_path(repo, path, label=label), label)
    if (
        sha256(payload) != expected_sha256
        or not taskctl.git_commit_exists(repo, commit)
        or not taskctl.git_is_ancestor(repo, commit)
        or taskctl.git_blob(repo, commit, path) != payload
    ):
        raise SystemExit(f"{label} differs from its exact immutable Git authority")
    return document, payload


def validate_gcr4_bridge(repo: Path, state: dict[str, Any]) -> str:
    """Authenticate the sole GCR-0004 bridge and return its finalization commit."""
    if state.get("schemaVersion") != "3.1-control-recovery-state":
        raise SystemExit("GCR-0003 successor state does not select the GCR-0004 runtime envelope")
    recovery = state.get("reviewTransitionRecovery") or {}
    if (
        recovery.get("controlRecoveryId") != GCR4_ID
        or recovery.get("bootstrapUnit") != GCR4_BOOTSTRAP_ID
        or recovery.get("reviewedStateCommit") != GCR3_R01_REVIEWED_STATE_COMMIT
        or recovery.get("adverseLedger") != {"path": GCR3_R01_LEDGER_PATH, "sha256": GCR3_R01_LEDGER_SHA256}
        or recovery.get("result") != "changes-requested"
        or recovery.get("controlRevision") != PREDECESSOR_REVISION
        or recovery.get("ordinaryExecutionAuthority") is not False
    ):
        raise SystemExit("GCR-0003 successor state lacks the exact GCR-0004 bridge record")

    # Import lazily so the frozen v3 reader remains usable for its historical
    # documents without implicitly selecting a newer controller generation.
    import gcr4ctl

    packet, packet_payload = _immutable_json(
        repo,
        path=GCR4_PACKET_PATH,
        commit=GCR4_PACKET_COMMIT,
        expected_sha256=GCR4_PACKET_SHA256,
        label="GCR-0004 packet",
    )
    packet_review, packet_review_payload = _immutable_json(
        repo,
        path=GCR4_PACKET_REVIEW_PATH,
        commit=GCR4_PACKET_REVIEW_COMMIT,
        expected_sha256=GCR4_PACKET_REVIEW_SHA256,
        label="GCR-0004 packet review",
    )
    approval, approval_payload = _immutable_json(
        repo,
        path=GCR4_APPROVAL_PATH,
        commit=GCR4_APPROVAL_COMMIT,
        expected_sha256=GCR4_APPROVAL_SHA256,
        label="GCR-0004 approval",
    )
    gcr4ctl.validate_schema(repo, packet, gcr4ctl.REQUEST_SCHEMA_PATH, "GCR-0004 packet")
    gcr4ctl.validate_runtime(repo, packet_review, "GCR-0004 packet review")
    gcr4ctl.validate_runtime(repo, approval, "GCR-0004 approval")
    if (
        taskctl.approval_introduction_commit(repo, GCR4_APPROVAL_PATH) != GCR4_APPROVAL_COMMIT
        or approval.get("status") != "APPROVED"
        or approval.get("controlRecoveryId") != GCR4_ID
        or approval.get("packet")
        != {"path": GCR4_PACKET_PATH, "sha256": GCR4_PACKET_SHA256, "commit": GCR4_PACKET_COMMIT}
        or ((approval.get("independentPacketReview") or {}).get("ledger") or {})
        != {
            "path": GCR4_PACKET_REVIEW_PATH,
            "sha256": GCR4_PACKET_REVIEW_SHA256,
            "commit": GCR4_PACKET_REVIEW_COMMIT,
        }
        or (approval.get("executionAuthority") or {}).get("bootstrapUnit") != GCR4_BOOTSTRAP_ID
        or (approval.get("executionAuthority") or {}).get("ordinaryExecution") is not False
        or approval.get("triggerWitness") != trigger_witness()
        or packet_review.get("candidateCommit") != GCR4_PACKET_COMMIT
        or packet_review.get("packetSha256") != GCR4_PACKET_SHA256
        or packet_review.get("result") != "approved"
        or packet_review.get("findings") != []
        or packet_review.get("approvalAvailable") is not True
        or not taskctl.git_is_ancestor(repo, GCR4_PACKET_COMMIT, GCR4_APPROVAL_COMMIT)
        or not taskctl.git_is_ancestor(repo, GCR4_PACKET_REVIEW_COMMIT, GCR4_APPROVAL_COMMIT)
        or taskctl.git_blob(repo, GCR4_APPROVAL_COMMIT, GCR4_APPROVAL_PATH) != approval_payload
        or taskctl.git_blob(repo, GCR4_PACKET_COMMIT, GCR4_PACKET_PATH) != packet_payload
        or taskctl.git_blob(repo, GCR4_PACKET_REVIEW_COMMIT, GCR4_PACKET_REVIEW_PATH) != packet_review_payload
    ):
        raise SystemExit("GCR-0004 packet review or approval authority is not exact")
    for reference in packet.get("files", []):
        relative = str(reference.get("path") or "")
        payload = safe_path(repo, relative, label="GCR-0004 packet file", prefix="planning").read_bytes()
        if (
            sha256(payload) != reference.get("sha256")
            or taskctl.git_blob(repo, GCR4_PACKET_COMMIT, relative) != payload
        ):
            raise SystemExit(f"GCR-0004 packet file binding differs: {relative}")

    approved_state = str(recovery.get("approvedGcr4StateCommit") or "")
    approved_payload = taskctl.git_blob(repo, approved_state, GCR4_STATE_PATH)
    if approved_payload is None:
        raise SystemExit("GCR-0004 approved B00 state is absent")
    try:
        approved_document = json.loads(approved_payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("GCR-0004 approved B00 state is malformed") from exc
    if not isinstance(approved_document, dict):
        raise SystemExit("GCR-0004 approved B00 state must be an object")
    gcr4ctl.validate_runtime(repo, approved_document, "GCR-0004 approved B00 state")
    gcr4ctl.validate_history(repo, approved_document, packet)
    latest = (approved_document.get("attempts") or [{}])[-1]
    gcr4_review = latest.get("review") or {}
    gcr4_ledger = latest.get("ledger") or {}
    gcr4_reviewed_state = str(gcr4_review.get("reviewedStateCommit") or "")
    gcr4_ledger_path = str(gcr4_ledger.get("path") or "")
    if (
        approved_document.get("status") != "APPROVED"
        or gcr4_review.get("result") != "approved"
        or gcr4ctl.open_findings(approved_document)
        or taskctl.approval_introduction_commit(repo, gcr4_ledger_path) != approved_state
        or taskctl.git_blob(repo, approved_state, GCR4_STATE_PATH) != approved_payload
    ):
        raise SystemExit("GCR-0004 B00 lacks an exact independently approved state")
    require_exact_commit_delta(
        repo,
        parent=gcr4_reviewed_state,
        commit=approved_state,
        expected={gcr4_ledger_path: "A", GCR4_STATE_PATH: "M"},
        label="GCR-0004 approved-state commit",
    )

    evidence = recovery.get("applicationEvidence") or {}
    evidence_commit = str(evidence.get("commit") or "")
    evidence_path = str(evidence.get("path") or "")
    evidence_payload = taskctl.git_blob(repo, evidence_commit, evidence_path)
    if evidence_path != GCR4_APPLICATION_EVIDENCE_PATH or evidence_payload is None:
        raise SystemExit("GCR-0004 application evidence reference is not canonical")
    try:
        evidence_document = json.loads(evidence_payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("GCR-0004 application evidence is malformed") from exc
    if not isinstance(evidence_document, dict):
        raise SystemExit("GCR-0004 application evidence must be an object")
    gcr4ctl.validate_runtime(repo, evidence_document, "GCR-0004 application evidence")
    require_exact_commit_delta(
        repo,
        parent=approved_state,
        commit=evidence_commit,
        expected={GCR4_APPLICATION_EVIDENCE_PATH: "A"},
        label="GCR-0004 application-evidence commit",
    )
    if (
        sha256(evidence_payload) != evidence.get("sha256")
        or evidence_document.get("controlRecoveryId") != GCR4_ID
        or evidence_document.get("bootstrapUnit") != GCR4_BOOTSTRAP_ID
        or evidence_document.get("approvedStateCommit") != approved_state
        or evidence_document.get("reviewedStateCommit") != GCR3_R01_REVIEWED_STATE_COMMIT
        or evidence_document.get("triggerWitness") != trigger_witness()
        or evidence_document.get("adverseLedger")
        != {"path": GCR3_R01_LEDGER_PATH, "sha256": GCR3_R01_LEDGER_SHA256, "bytePreserved": True}
        or evidence_document.get("predecessorStateSha256") != GCR3_R01_REVIEWED_STATE_SHA256
        or evidence_document.get("successorStatus") != "CHANGES_REQUESTED"
        or evidence_document.get("controlRevision") != PREDECESSOR_REVISION
        or evidence_document.get("expectedChangedFiles") != [GCR3_R01_LEDGER_PATH, STATE_PATH]
        or evidence_document.get("unverifiedItems") != []
        or not evidence_document.get("checks")
        or any(
            check.get("exitCode") != 0 or check.get("result") != "passed"
            for check in evidence_document.get("checks", [])
        )
    ):
        raise SystemExit("GCR-0004 application evidence boundary is invalid")

    finalization = taskctl.approval_introduction_commit(repo, GCR3_R01_LEDGER_PATH)
    if not finalization or not taskctl.git_is_ancestor(repo, finalization):
        raise SystemExit("GCR-0004 bridge finalization commit is absent or forked")
    require_exact_commit_delta(
        repo,
        parent=evidence_commit,
        commit=finalization,
        expected={GCR3_R01_LEDGER_PATH: "A", STATE_PATH: "M"},
        label="GCR-0004 bridge finalization commit",
    )
    ledger_payload = taskctl.git_blob(repo, finalization, GCR3_R01_LEDGER_PATH)
    bridge_state_payload = taskctl.git_blob(repo, finalization, STATE_PATH)
    frozen_payload = taskctl.git_blob(repo, GCR3_R01_REVIEWED_STATE_COMMIT, STATE_PATH)
    current_ledger_payload = safe_path(
        repo,
        GCR3_R01_LEDGER_PATH,
        label="current GCR-0003 R01 adverse ledger",
        prefix="planning/governance-control-recovery",
    ).read_bytes()
    if (
        ledger_payload is None
        or sha256(ledger_payload) != GCR3_R01_LEDGER_SHA256
        or current_ledger_payload != ledger_payload
        or taskctl.git_blob(repo, "HEAD", GCR3_R01_LEDGER_PATH) != ledger_payload
        or bridge_state_payload is None
        or frozen_payload is None
        or sha256(frozen_payload) != GCR3_R01_REVIEWED_STATE_SHA256
    ):
        raise SystemExit("GCR-0004 bridge ledger or predecessor state binding is invalid")
    try:
        ledger_document = json.loads(ledger_payload)
        bridge_state = json.loads(bridge_state_payload)
        frozen_state = json.loads(frozen_payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("GCR-0004 bridge history is malformed") from exc
    if not all(isinstance(item, dict) for item in (ledger_document, bridge_state, frozen_state)):
        raise SystemExit("GCR-0004 bridge history documents must be objects")
    validate_schema(repo, frozen_state, RUNTIME_SCHEMA_PATH, "GCR-0003 frozen R01 state")
    validate_schema(repo, ledger_document, RUNTIME_SCHEMA_PATH, "GCR-0003 R01 adverse ledger")
    validate_schema(repo, bridge_state, SUCCESSOR_RUNTIME_SCHEMA_PATH, "GCR-0003 bridged R01 state")
    submission = frozen_state.get("currentSubmission") or {}
    bridge_attempts = bridge_state.get("attempts") or []
    bridge_attempt = bridge_attempts[0] if len(bridge_attempts) == 1 else {}
    bridge_review = bridge_attempt.get("review") or {}
    expected_ledger = {
        "path": GCR3_R01_LEDGER_PATH,
        "sha256": GCR3_R01_LEDGER_SHA256,
        "commit": GCR3_R01_REVIEWED_STATE_COMMIT,
    }
    if (
        frozen_state.get("status") != "REVIEW"
        or frozen_state.get("attempts") != []
        or submission.get("attemptId") != "R01"
        or submission.get("candidateCommit") != GCR3_R01_CANDIDATE_COMMIT
        or ledger_document.get("reviewedStateCommit") != GCR3_R01_REVIEWED_STATE_COMMIT
        or ledger_document.get("candidateCommit") != GCR3_R01_CANDIDATE_COMMIT
        or ledger_document.get("result") != "changes-requested"
        or bridge_state.get("status") != "CHANGES_REQUESTED"
        or bridge_state.get("currentSubmission") is not None
        or bridge_state.get("adoption") is not None
        or bridge_state.get("reviewTransitionRecovery") != recovery
        or bridge_attempt.get("submission") != submission
        or bridge_attempt.get("ledger") != expected_ledger
        or bridge_attempt.get("findings") != (ledger_document.get("findings") or [])
        or bridge_attempt.get("closures") != (ledger_document.get("closures") or [])
        or bridge_review.get("reviewer") != ledger_document.get("reviewer")
        or bridge_review.get("result") != ledger_document.get("result")
        or bridge_review.get("reviewedStateCommit") != GCR3_R01_REVIEWED_STATE_COMMIT
        or bridge_review.get("notes") != ledger_document.get("notes")
        or not any(item.get("blocking") is True for item in bridge_attempt.get("findings") or [])
        or state.get("reviewTransitionRecovery") != recovery
        or (state.get("attempts") or [{}])[0] != bridge_attempt
    ):
        raise SystemExit("GCR-0004 bridge is not the exact ledger-derived one-time R01 projection")
    return finalization


def exact_gcr4_lineage_paths(
    repo: Path, state: dict[str, Any], *, candidate: str, original_patterns: list[str]
) -> set[str]:
    finalization = validate_gcr4_bridge(repo, state)
    if candidate == finalization or not taskctl.git_is_ancestor(repo, finalization, candidate):
        raise SystemExit("GCR-0003 remediation candidate does not descend from the exact GCR-0004 bridge")
    bridge_paths = set(changed_paths(repo, APPROVAL_COMMIT, finalization))
    for relative in bridge_paths:
        if not path_authorized(relative, original_patterns) and taskctl.git_blob(
            repo, candidate, relative
        ) != taskctl.git_blob(repo, finalization, relative):
            raise SystemExit(f"GCR-0004 bridge-only path changed after finalization: {relative}")
    return bridge_paths


def validate_evidence_document(
    repo: Path,
    packet: dict[str, Any],
    relative: str,
    document: dict[str, Any],
    candidate: str,
    base: str,
    attempt_id: str,
    prior_open: dict[str, dict[str, Any]],
    *,
    bridge_state: dict[str, Any] | None = None,
) -> None:
    if relative != evidence_path(attempt_id):
        raise SystemExit(f"GCR-0003 evidence path must be {evidence_path(attempt_id)}")
    validate_runtime(repo, document, "GCR-0003 evidence")
    actual = changed_paths(repo, base, candidate)
    patterns = [str(item) for item in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", [])]
    outside = [item for item in actual if not path_authorized(item, patterns)]
    bridge_only: set[str] = set()
    if outside:
        if bridge_state is None:
            bridge_state, _state_payload = load_state(repo, required=True)
        assert bridge_state is not None
        bridge_paths = exact_gcr4_lineage_paths(repo, bridge_state, candidate=candidate, original_patterns=patterns)
        outside = [item for item in outside if item not in bridge_paths]
        bridge_only = {item for item in bridge_paths if not path_authorized(item, patterns)}
    effective_actual = [item for item in actual if item not in bridge_only]
    criteria = document.get("acceptanceCriteria") or []
    expected_criteria = packet.get("acceptanceCriteria") or []
    closures = document.get("findingClosures") or []
    closure_ids = [str(item.get("findingId") or "") for item in closures]
    if (
        document.get("controlRecoveryId") != GCR_ID
        or document.get("bootstrapUnit") != BOOTSTRAP_ID
        or document.get("attemptId") != attempt_id
        or document.get("commit") != candidate
        or document.get("baseCommit") != base
        or document.get("branch") != BRANCH
        or document.get("triggerWitness") != trigger_witness()
        or sorted(document.get("changedFiles") or []) != effective_actual
        or outside
        or [item.get("index") for item in criteria] != list(range(1, len(expected_criteria) + 1))
        or [item.get("statement") for item in criteria] != expected_criteria
        or document.get("unverifiedItems") != []
        or len(closure_ids) != len(set(closure_ids))
        or set(closure_ids) != set(prior_open)
    ):
        raise SystemExit("GCR-0003 evidence identity, scope, criteria, closures, or verification is invalid")
    checks = document.get("checks") or []
    if (
        not checks
        or len({item.get("id") for item in checks}) != len(checks)
        or any(item.get("exitCode") != 0 or item.get("result") != "passed" for item in checks)
    ):
        raise SystemExit("GCR-0003 evidence checks must be unique and passing")
    selection = document.get("verificationSelection") or {}
    if set(selection.get("selectedChecks") or []) != {item.get("id") for item in checks}:
        raise SystemExit("GCR-0003 verification selection differs from the passing checks")
    for closure in closures:
        if (
            str(closure.get("findingId") or "") not in prior_open
            or closure.get("disposition") not in {"fixed", "not-reproduced", "superseded", "accepted-risk"}
            or not str(closure.get("evidence") or "").strip()
        ):
            raise SystemExit("GCR-0003 finding closure is stale or incomplete")


def validate_evidence(
    repo: Path,
    packet: dict[str, Any],
    relative: str,
    candidate: str,
    base: str,
    attempt_id: str,
    prior_open: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], bytes]:
    document, payload = load_json(
        safe_path(repo, relative, label="GCR-0003 evidence", prefix="artifacts/evidence/governance-control-recovery"),
        "GCR-0003 evidence",
    )
    validate_evidence_document(
        repo,
        packet,
        relative,
        document,
        candidate,
        base,
        attempt_id,
        prior_open,
    )
    return document, payload


def freeze_submission(args: argparse.Namespace, *, remediation: bool) -> None:
    authority = load_authority(args.repo)
    _approval, packet, approval_base = authority
    if present_transaction_artifacts(args.repo):
        recover_transaction(args.repo, authority)
    state, _payload = load_state(args.repo, required=False)
    if remediation:
        if state is None or state.get("status") not in {"CHANGES_REQUESTED", "BLOCKED"}:
            raise SystemExit("GCR-0003 resubmission requires an adverse prior review")
    elif state is not None:
        raise SystemExit("GCR-0003 initial submission already exists")
    attempts = (state or {}).get("attempts", [])
    attempt_id = f"R{len(attempts) + 1:02d}"
    relative = str(args.evidence)
    require_workspace(args.repo, extra_untracked={relative})
    candidate = str(args.implementation_commit)
    if candidate != git(args.repo, "rev-parse", "HEAD"):
        raise SystemExit("GCR-0003 candidate must equal current HEAD")
    if str(args.agent).strip() != ACTOR or args.agent != ACTOR:
        raise SystemExit(f"GCR-0003 implementer must be exact actor {ACTOR}")
    if not remediation and str(args.approval_commit) != approval_base:
        raise SystemExit("GCR-0003 approval commit differs from the immutable approval introduction")
    prior_candidate = str(
        (((state or {}).get("attempts") or [{}])[-1].get("submission") or {}).get("candidateCommit") or ""
    )
    if remediation and (
        not prior_candidate
        or not taskctl.git_is_ancestor(args.repo, prior_candidate, candidate)
        or prior_candidate == candidate
    ):
        raise SystemExit("GCR-0003 remediation candidate must strictly descend from the prior candidate")
    prior_open = open_findings(state or {})
    _document, evidence_payload = validate_evidence(
        args.repo, packet, relative, candidate, approval_base, attempt_id, prior_open
    )
    submission = {
        "attemptId": attempt_id,
        "submittedBy": ACTOR,
        "candidateCommit": candidate,
        "baseCommit": approval_base,
        "branch": BRANCH,
        "evidence": {"path": relative, "sha256": sha256(evidence_payload), "commit": candidate},
        "submittedAt": taskctl.utc_now(),
        "priorAttemptId": (attempts[-1].get("submission") or {}).get("attemptId") if attempts else None,
        "openFindingIds": sorted(prior_open),
        "rootCauseAnalysis": required_root_cause(len(attempts), getattr(args, "root_cause_analysis", None)),
    }
    if state is None:
        state = {
            "schemaVersion": "3.0-control-recovery-state",
            "documentType": "governance-control-recovery-bootstrap-state",
            "controlRecoveryId": GCR_ID,
            "bootstrapUnit": BOOTSTRAP_ID,
            "status": "REVIEW",
            "approval": {
                "path": APPROVAL_PATH,
                "sha256": sha256((args.repo / APPROVAL_PATH).read_bytes()),
                "commit": approval_base,
            },
            "triggerWitness": trigger_witness(),
            "attempts": [],
            "currentSubmission": submission,
            "adoption": None,
        }
    else:
        state["status"] = "REVIEW"
        state["currentSubmission"] = submission
    validate_runtime(args.repo, state, "GCR-0003 submission state")
    write_json_atomic(args.repo / STATE_PATH, state)
    print(f"Submitted {BOOTSTRAP_ID}/{attempt_id} for independent review at {candidate}")


def validate_review(
    repo: Path,
    ledger: dict[str, Any],
    state: dict[str, Any],
    relative: str,
    reviewer: str,
    reviewed_state: str,
) -> None:
    validate_runtime(repo, ledger, "GCR-0003 review ledger")
    submission = state.get("currentSubmission") or {}
    findings = ledger.get("findings") or []
    closures = ledger.get("closures") or []
    ordering = [SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings]
    finding_ids = [str(item.get("id") or "") for item in findings]
    prior_open = open_findings(state)
    prior_finding_ids = {
        str(finding.get("id") or "") for attempt in state.get("attempts", []) for finding in attempt.get("findings", [])
    }
    closure_ids = [str(item.get("findingId") or "") for item in closures]
    if (
        relative != review_path(str(submission.get("attemptId") or ""))
        or ledger.get("controlRecoveryId") != GCR_ID
        or ledger.get("bootstrapUnit") != BOOTSTRAP_ID
        or ledger.get("attemptId") != submission.get("attemptId")
        or ledger.get("candidateCommit") != submission.get("candidateCommit")
        or ledger.get("reviewedStateCommit") != reviewed_state
        or ledger.get("reviewer") != reviewer
        or ledger.get("evidence") != submission.get("evidence")
        or ordering != sorted(ordering)
        or any(value == 99 for value in ordering)
        or len(finding_ids) != len(set(finding_ids))
        or bool(set(finding_ids) & prior_finding_ids)
        or len(closure_ids) != len(set(closure_ids))
        or set(closure_ids) - set(prior_open)
    ):
        raise SystemExit("GCR-0003 review ledger differs from the frozen submission or review controls")
    result = str(ledger.get("result") or "")
    if result not in RESULT_STATUS:
        raise SystemExit("GCR-0003 review result is invalid")
    if result == "approved" and (
        findings or any(item.get("blocking") for item in prior_open.values() if str(item.get("id")) not in closure_ids)
    ):
        raise SystemExit("GCR-0003 approval cannot introduce findings or retain an open blocker")


def command_review(args: argparse.Namespace) -> None:
    authority = load_authority(args.repo)
    if present_transaction_artifacts(args.repo):
        recover_transaction(args.repo, authority)
    state, _payload = load_state(args.repo, required=True)
    assert state is not None
    if state.get("status") != "REVIEW" or not state.get("currentSubmission"):
        raise SystemExit("GCR-0003 has no frozen submission eligible for review")
    relative = str(args.ledger)
    require_workspace(args.repo, extra_untracked={relative})
    reviewer = str(args.reviewer).strip()
    if not reviewer or reviewer != args.reviewer or reviewer == ACTOR:
        raise SystemExit("GCR-0003 reviewer must be normalized and independent")
    reviewed_state = git(args.repo, "rev-parse", "HEAD")
    ledger, ledger_payload = load_json(
        safe_path(
            repo=args.repo, relative=relative, label="GCR-0003 review", prefix="planning/governance-control-recovery"
        ),
        "GCR-0003 review",
    )
    validate_review(args.repo, ledger, state, relative, reviewer, reviewed_state)
    submission = copy.deepcopy(state["currentSubmission"])
    attempt = {
        "submission": submission,
        "review": {
            "reviewer": reviewer,
            "result": ledger["result"],
            "reviewedAt": taskctl.utc_now(),
            "reviewedStateCommit": reviewed_state,
            "notes": ledger.get("notes"),
        },
        "ledger": {"path": relative, "sha256": sha256(ledger_payload), "commit": reviewed_state},
        "findings": ledger.get("findings") or [],
        "closures": ledger.get("closures") or [],
    }
    state["attempts"].append(attempt)
    state["status"] = RESULT_STATUS[str(ledger["result"])]
    state["currentSubmission"] = None
    validate_runtime(args.repo, state, "GCR-0003 reviewed state")
    write_json_atomic(args.repo / STATE_PATH, state)
    print(f"Recorded {BOOTSTRAP_ID}/{submission['attemptId']} as {state['status']}")


def validate_history(repo: Path, state: dict[str, Any], packet: dict[str, Any]) -> None:
    attempts = state.get("attempts") or []
    if [((item.get("submission") or {}).get("attemptId")) for item in attempts] != [
        f"R{index:02d}" for index in range(1, len(attempts) + 1)
    ]:
        raise SystemExit("GCR-0003 attempt history is not append-only and sequential")
    bridge_finalization = (
        validate_gcr4_bridge(repo, state) if state.get("schemaVersion") == "3.1-control-recovery-state" else None
    )
    if bridge_finalization is not None:
        original_patterns = [str(item) for item in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", [])]
        for relative in changed_paths(repo, APPROVAL_COMMIT, bridge_finalization):
            if not path_authorized(relative, original_patterns) and taskctl.git_blob(
                repo, "HEAD", relative
            ) != taskctl.git_blob(repo, bridge_finalization, relative):
                raise SystemExit(f"GCR-0004 bridge-only history changed after finalization: {relative}")
    prior_candidate: str | None = None
    for index, attempt in enumerate(attempts):
        submission = attempt.get("submission") or {}
        attempt_id = str(submission.get("attemptId") or "")
        candidate = str(submission.get("candidateCommit") or "")
        evidence = submission.get("evidence") or {}
        ledger = attempt.get("ledger") or {}
        review = attempt.get("review") or {}
        reviewed_state = str(review.get("reviewedStateCommit") or "")
        prior_open = open_findings({"attempts": attempts[:index]})
        if (
            submission.get("baseCommit") != (state.get("approval") or {}).get("commit")
            or submission.get("branch") != BRANCH
            or submission.get("submittedBy") != ACTOR
            or evidence.get("commit") != candidate
            or submission.get("priorAttemptId")
            != (((attempts[index - 1].get("submission") or {}).get("attemptId")) if index else None)
            or set(submission.get("openFindingIds") or []) != set(prior_open)
            or (index < 2 and submission.get("rootCauseAnalysis") is not None)
            or (
                index >= 2
                and (
                    not isinstance(submission.get("rootCauseAnalysis"), str)
                    or not str(submission.get("rootCauseAnalysis")).strip()
                    or submission.get("rootCauseAnalysis") != str(submission.get("rootCauseAnalysis")).strip()
                )
            )
        ):
            raise SystemExit(f"GCR-0003 {attempt_id} submission base or branch is invalid")
        if prior_candidate and (
            prior_candidate == candidate or not taskctl.git_is_ancestor(repo, prior_candidate, candidate)
        ):
            raise SystemExit(f"GCR-0003 {attempt_id} candidate is not a strict remediation descendant")
        prior_candidate = candidate
        expected_delta = {str(evidence.get("path")): "A", STATE_PATH: "A" if index == 0 else "M"}
        require_exact_commit_delta(
            repo,
            parent=candidate,
            commit=reviewed_state,
            expected=expected_delta,
            label=f"GCR-0003 {attempt_id} reviewed-state commit",
        )
        evidence_payload = taskctl.git_blob(repo, reviewed_state, str(evidence.get("path") or ""))
        if evidence_payload is None or sha256(evidence_payload) != evidence.get("sha256"):
            raise SystemExit(f"GCR-0003 {attempt_id} evidence Git binding is invalid")
        try:
            evidence_document = json.loads(evidence_payload)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"GCR-0003 {attempt_id} evidence Git blob is malformed") from exc
        if not isinstance(evidence_document, dict):
            raise SystemExit(f"GCR-0003 {attempt_id} evidence Git blob must be an object")
        validate_evidence_document(
            repo,
            packet,
            str(evidence.get("path") or ""),
            evidence_document,
            candidate,
            str(submission.get("baseCommit") or ""),
            attempt_id,
            prior_open,
            bridge_state=state,
        )
        reviewed_state_payload = taskctl.git_blob(repo, reviewed_state, STATE_PATH)
        if reviewed_state_payload is None:
            raise SystemExit(f"GCR-0003 {attempt_id} reviewed state Git blob is absent")
        try:
            reviewed_state_document = json.loads(reviewed_state_payload)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"GCR-0003 {attempt_id} reviewed state Git blob is malformed") from exc
        validate_runtime(repo, reviewed_state_document, f"GCR-0003 {attempt_id} reviewed state")
        if (
            reviewed_state_document.get("status") != "REVIEW"
            or reviewed_state_document.get("currentSubmission") != submission
            or reviewed_state_document.get("attempts") != attempts[:index]
            or reviewed_state_document.get("approval") != state.get("approval")
            or reviewed_state_document.get("triggerWitness") != state.get("triggerWitness")
            or reviewed_state_document.get("adoption") is not None
        ):
            raise SystemExit(f"GCR-0003 {attempt_id} reviewed-state projection is not exact")
        ledger_relative = str(ledger.get("path") or "")
        if index == 0 and bridge_finalization is not None:
            if ledger_relative != GCR3_R01_LEDGER_PATH or reviewed_state != GCR3_R01_REVIEWED_STATE_COMMIT:
                raise SystemExit("GCR-0003 R01 does not identify the exact GCR-0004 bridge boundary")
            ledger_payload = taskctl.git_blob(repo, bridge_finalization, ledger_relative)
            if ledger_payload is None or sha256(ledger_payload) != GCR3_R01_LEDGER_SHA256:
                raise SystemExit("GCR-0003 R01 exceptional review ledger Git binding is invalid")
            try:
                ledger_document = json.loads(ledger_payload)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise SystemExit("GCR-0003 R01 exceptional review ledger is malformed") from exc
            reviewer = str(ledger_document.get("reviewer") or "") if isinstance(ledger_document, dict) else ""
            if not reviewer or reviewer != ledger_document.get("reviewer") or reviewer == ACTOR:
                raise SystemExit("GCR-0003 R01 exceptional reviewer is not independent and normalized")
            validate_review(
                repo,
                ledger_document,
                reviewed_state_document,
                ledger_relative,
                reviewer,
                reviewed_state,
            )
            expected_review = {
                "reviewer": reviewer,
                "result": ledger_document["result"],
                "reviewedAt": review.get("reviewedAt"),
                "reviewedStateCommit": reviewed_state,
                "notes": ledger_document.get("notes"),
            }
            if (
                review != expected_review
                or ledger != {"path": ledger_relative, "sha256": GCR3_R01_LEDGER_SHA256, "commit": reviewed_state}
                or attempt.get("findings") != (ledger_document.get("findings") or [])
                or attempt.get("closures") != (ledger_document.get("closures") or [])
            ):
                raise SystemExit("GCR-0003 R01 exceptional ledger and state record disagree")
            continue
        approval_projection = taskctl.approval_introduction_commit(repo, ledger_relative)
        if not approval_projection:
            raise SystemExit(f"GCR-0003 {attempt_id} review projection commit is absent")
        require_exact_commit_delta(
            repo,
            parent=reviewed_state,
            commit=approval_projection,
            expected={ledger_relative: "A", STATE_PATH: "M"},
            label=f"GCR-0003 {attempt_id} review projection",
        )
        ledger_payload = taskctl.git_blob(repo, approval_projection, ledger_relative)
        if ledger_payload is None or sha256(ledger_payload) != ledger.get("sha256"):
            raise SystemExit(f"GCR-0003 {attempt_id} review ledger Git binding is invalid")
        try:
            ledger_document = json.loads(ledger_payload)
            approval_state_document = json.loads(taskctl.git_blob(repo, approval_projection, STATE_PATH) or b"")
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"GCR-0003 {attempt_id} review projection is malformed") from exc
        reviewer = str(ledger_document.get("reviewer") or "") if isinstance(ledger_document, dict) else ""
        if not reviewer or reviewer != ledger_document.get("reviewer") or reviewer == ACTOR:
            raise SystemExit(f"GCR-0003 {attempt_id} historical reviewer is not independent and normalized")
        validate_review(
            repo,
            ledger_document,
            reviewed_state_document,
            ledger_relative,
            reviewer,
            reviewed_state,
        )
        expected_review = {
            "reviewer": reviewer,
            "result": ledger_document["result"],
            "reviewedAt": review.get("reviewedAt"),
            "reviewedStateCommit": reviewed_state,
            "notes": ledger_document.get("notes"),
        }
        expected_ledger = {
            "path": ledger_relative,
            "sha256": sha256(ledger_payload),
            "commit": reviewed_state,
        }
        if (
            not isinstance(approval_state_document, dict)
            or review != expected_review
            or ledger != expected_ledger
            or attempt.get("findings") != (ledger_document.get("findings") or [])
            or attempt.get("closures") != (ledger_document.get("closures") or [])
        ):
            raise SystemExit(f"GCR-0003 {attempt_id} review ledger and state record disagree")
        expected_approval_state = copy.deepcopy(reviewed_state_document)
        expected_approval_state["attempts"].append(attempt)
        expected_approval_state["status"] = RESULT_STATUS[str(ledger_document["result"])]
        expected_approval_state["currentSubmission"] = None
        if approval_state_document != expected_approval_state:
            raise SystemExit(f"GCR-0003 {attempt_id} approval-state projection is not ledger-derived")
    current = state.get("currentSubmission")
    expected_status = RESULT_STATUS[str((attempts[-1].get("review") or {}).get("result"))] if attempts else "REVIEW"
    if current is not None:
        current_candidate = str(current.get("candidateCommit") or "")
        latest_candidate = str((attempts[-1].get("submission") or {}).get("candidateCommit") or "") if attempts else ""
        if (
            state.get("status") != "REVIEW"
            or current.get("attemptId") != f"R{len(attempts) + 1:02d}"
            or current.get("baseCommit") != (state.get("approval") or {}).get("commit")
            or current.get("branch") != BRANCH
            or current.get("priorAttemptId")
            != (((attempts[-1].get("submission") or {}).get("attemptId")) if attempts else None)
            or set(current.get("openFindingIds") or []) != set(open_findings(state))
            or (
                bool(attempts)
                and (
                    current_candidate == latest_candidate
                    or not taskctl.git_is_ancestor(repo, latest_candidate, current_candidate)
                )
            )
            or (len(attempts) < 2 and current.get("rootCauseAnalysis") is not None)
            or (
                len(attempts) >= 2
                and (
                    not isinstance(current.get("rootCauseAnalysis"), str)
                    or not str(current.get("rootCauseAnalysis")).strip()
                    or current.get("rootCauseAnalysis") != str(current.get("rootCauseAnalysis")).strip()
                )
            )
        ):
            raise SystemExit("GCR-0003 current remediation submission is not the exact next REVIEW projection")
    elif attempts and state.get("status") not in {expected_status, "ADOPTION_FINALIZATION"}:
        raise SystemExit("GCR-0003 state status differs from the latest immutable review")
    elif not attempts and state.get("status") == "REVIEW":
        raise SystemExit("GCR-0003 REVIEW state lacks its frozen submission")


def transaction_artifacts(repo: Path) -> dict[str, Path]:
    return {
        relative: _artifact_path(repo, relative)
        for relative in (LOCK_PATH, TRANSACTION_PATH, BACKLOG_NEXT_PATH, STATE_NEXT_PATH)
    }


def present_transaction_artifacts(repo: Path) -> list[str]:
    return [relative for relative, path in transaction_artifacts(repo).items() if os.path.lexists(path)]


@contextmanager
def transaction_lock(
    repo: Path,
    *,
    anchor: dict[str, Any] | None = None,
    authority: tuple[dict[str, Any], dict[str, Any], str] | None = None,
    recover: bool = False,
) -> Iterator[None]:
    path = transaction_artifacts(repo)[LOCK_PATH]
    if os.path.lexists(path):
        if not recover or not path.is_file() or path.is_symlink():
            raise SystemExit("GCR-0003 adoption lock already exists or is redirected")
        yield
        return
    if recover or anchor is None or authority is None:
        raise SystemExit("GCR-0003 adoption requires an exact recovery anchor")
    validate_recovery_anchor(repo, anchor, authority)
    payload = (json.dumps(anchor, indent=2, ensure_ascii=False) + "\n").encode()
    write_new_durable(path, payload)
    adoption_fault_boundary("lock-durable")
    try:
        yield
    except BaseException:
        raise


def canonical_sha(document: dict[str, Any]) -> str:
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())


def binding(path: str, payload: bytes, document: dict[str, Any]) -> dict[str, str]:
    return {"path": path, "rawSha256": sha256(payload), "canonicalSha256": canonical_sha(document)}


def recovery_anchor_document(
    *, transaction: dict[str, Any], predecessor_backlog: bytes, predecessor_state: bytes
) -> dict[str, Any]:
    """Build the durable pre-publication authority and raw-byte recovery anchor."""
    return {
        "schemaVersion": "3.0-control-recovery-adoption-anchor",
        "documentType": "governance-control-recovery-adoption-anchor",
        "transactionId": f"{BOOTSTRAP_ID}.ADOPT",
        "controlRecoveryId": GCR_ID,
        "bootstrapUnit": BOOTSTRAP_ID,
        "actor": ACTOR,
        "branch": BRANCH,
        "adoptionEvidenceCommit": transaction["adoptionEvidenceCommit"],
        "approvedStateCommit": transaction["reviewedStateCommit"],
        "predecessor": copy.deepcopy(transaction["predecessor"]),
        "predecessorPayloads": {
            "backlogBase64": base64.b64encode(predecessor_backlog).decode("ascii"),
            "stateBase64": base64.b64encode(predecessor_state).decode("ascii"),
        },
    }


def _decode_anchor_payload(value: object, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise SystemExit(f"GCR-0003 recovery anchor {label} payload is absent")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeError, ValueError) as exc:
        raise SystemExit(f"GCR-0003 recovery anchor {label} payload is invalid") from exc


def validate_recovery_anchor(
    repo: Path,
    anchor: dict[str, Any],
    authority: tuple[dict[str, Any], dict[str, Any], str],
) -> tuple[bytes, bytes]:
    """Authenticate the exact committed recovery base and its raw worktree preimages."""
    expected_keys = {
        "schemaVersion",
        "documentType",
        "transactionId",
        "controlRecoveryId",
        "bootstrapUnit",
        "actor",
        "branch",
        "adoptionEvidenceCommit",
        "approvedStateCommit",
        "predecessor",
        "predecessorPayloads",
    }
    evidence_commit = str(anchor.get("adoptionEvidenceCommit") or "")
    approved_state = str(anchor.get("approvedStateCommit") or "")
    if (
        set(anchor) != expected_keys
        or anchor.get("schemaVersion") != "3.0-control-recovery-adoption-anchor"
        or anchor.get("documentType") != "governance-control-recovery-adoption-anchor"
        or anchor.get("transactionId") != f"{BOOTSTRAP_ID}.ADOPT"
        or anchor.get("controlRecoveryId") != GCR_ID
        or anchor.get("bootstrapUnit") != BOOTSTRAP_ID
        or anchor.get("actor") != ACTOR
        or anchor.get("branch") != BRANCH
        or git(repo, "rev-parse", "HEAD") != evidence_commit
    ):
        raise SystemExit("GCR-0003 recovery anchor identity or HEAD binding is invalid")
    parents = git(repo, "rev-list", "--parents", "-n", "1", evidence_commit).split()
    if parents != [evidence_commit, approved_state]:
        raise SystemExit("GCR-0003 recovery anchor is not based on the exact approved-state parent")
    require_exact_commit_delta(
        repo,
        parent=approved_state,
        commit=evidence_commit,
        expected={ADOPTION_EVIDENCE_PATH: "A"},
        label="GCR-0003 recovery-anchor adoption-evidence commit",
    )
    evidence_payload = taskctl.git_blob(repo, evidence_commit, ADOPTION_EVIDENCE_PATH)
    if evidence_payload is None:
        raise SystemExit("GCR-0003 recovery anchor adoption evidence is unavailable")
    try:
        evidence = json.loads(evidence_payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("GCR-0003 recovery anchor adoption evidence is malformed") from exc
    validate_runtime(repo, evidence, "GCR-0003 recovery anchor adoption evidence")
    if (
        evidence.get("controlRecoveryId") != GCR_ID
        or evidence.get("bootstrapUnit") != BOOTSTRAP_ID
        or evidence.get("reviewedStateCommit") != approved_state
        or evidence.get("triggerWitness") != trigger_witness()
        or evidence.get("predecessorRevision") != PREDECESSOR_REVISION
        or evidence.get("successorRevision") != SUCCESSOR_REVISION
        or evidence.get("supportedControlCeiling") != SUPPORTED_CONTROL_CEILING
        or evidence.get("expectedChangedFiles") != [BACKLOG_PATH, STATE_PATH]
        or evidence.get("unverifiedItems") != []
    ):
        raise SystemExit("GCR-0003 recovery anchor adoption evidence binding is invalid")
    payloads = anchor.get("predecessorPayloads")
    predecessor = anchor.get("predecessor")
    if not isinstance(payloads, dict) or set(payloads) != {"backlogBase64", "stateBase64"}:
        raise SystemExit("GCR-0003 recovery anchor payload map is invalid")
    if not isinstance(predecessor, dict) or set(predecessor) != {
        "controlRevision",
        "minimumToolRevision",
        "supportedControlCeiling",
        "backlog",
        "state",
    }:
        raise SystemExit("GCR-0003 recovery anchor predecessor map is invalid")
    backlog_payload = _decode_anchor_payload(payloads.get("backlogBase64"), "backlog")
    state_payload = _decode_anchor_payload(payloads.get("stateBase64"), "state")
    try:
        backlog = yaml.safe_load(backlog_payload)
        state = json.loads(state_payload)
        committed_backlog = yaml.safe_load(taskctl.git_blob(repo, approved_state, BACKLOG_PATH) or b"")
    except (UnicodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise SystemExit("GCR-0003 recovery anchor predecessor payload is malformed") from exc
    committed_state = taskctl.git_blob(repo, approved_state, STATE_PATH)
    if (
        not isinstance(backlog, dict)
        or not isinstance(state, dict)
        or not isinstance(committed_backlog, dict)
        or sha256(backlog_payload) != BACKLOG_SHA256
        or predecessor.get("controlRevision") != PREDECESSOR_REVISION
        or predecessor.get("minimumToolRevision") != PREDECESSOR_REVISION
        or predecessor.get("supportedControlCeiling") != PREDECESSOR_REVISION
        or predecessor.get("backlog") != binding(BACKLOG_PATH, backlog_payload, backlog)
        or predecessor.get("state") != binding(STATE_PATH, state_payload, state)
        or canonical_sha(backlog) != canonical_sha(committed_backlog)
        or committed_state != state_payload
        or (backlog.get("control_plane") or {}).get("revision") != PREDECESSOR_REVISION
        or (backlog.get("control_plane") or {}).get("minimum_tool_revision") != PREDECESSOR_REVISION
        or state.get("status") != "APPROVED"
    ):
        raise SystemExit("GCR-0003 recovery anchor predecessor authority or raw bytes are invalid")
    validate_runtime(repo, state, "GCR-0003 recovery anchor predecessor state")
    _approval, packet, approval_base = authority
    expected_approval = {
        "path": APPROVAL_PATH,
        "sha256": sha256((repo / APPROVAL_PATH).read_bytes()),
        "commit": approval_base,
    }
    if state.get("approval") != expected_approval:
        raise SystemExit("GCR-0003 recovery anchor approval reference is not canonical")
    validate_history(repo, state, packet)
    _reviewed_state, canonical_approved_state_commit, _ledger, _ledger_payload = canonical_approved_state(
        repo, state, state_payload
    )
    if canonical_approved_state_commit != approved_state:
        raise SystemExit("GCR-0003 recovery anchor approved-state projection is not canonical")
    return backlog_payload, state_payload


def load_recovery_anchor(
    repo: Path, authority: tuple[dict[str, Any], dict[str, Any], str]
) -> tuple[dict[str, Any], bytes, bytes]:
    path = transaction_artifacts(repo)[LOCK_PATH]
    if not path.is_file() or path.is_symlink():
        raise SystemExit("GCR-0003 recovery anchor is absent or redirected")
    anchor, _payload = load_json(path, "GCR-0003 recovery anchor")
    backlog, state = validate_recovery_anchor(repo, anchor, authority)
    return anchor, backlog, state


def transaction_document(
    *,
    predecessor_backlog: bytes,
    predecessor_state: bytes,
    successor_backlog: bytes,
    successor_state: bytes,
    reviewed_state: str,
    evidence_commit: str,
) -> dict[str, Any]:
    predecessor_backlog_doc = yaml.safe_load(predecessor_backlog)
    predecessor_state_doc = json.loads(predecessor_state)
    successor_backlog_doc = yaml.safe_load(successor_backlog)
    successor_state_doc = json.loads(successor_state)
    return {
        "schemaVersion": "3.0-control-recovery-adoption-transaction",
        "documentType": "governance-control-recovery-adoption-transaction",
        "transactionId": f"{BOOTSTRAP_ID}.ADOPT",
        "controlRecoveryId": GCR_ID,
        "bootstrapUnit": BOOTSTRAP_ID,
        "status": "PREPARED",
        "createdBy": ACTOR,
        "createdAt": taskctl.utc_now(),
        "branch": BRANCH,
        "authorityBaseCommit": AUTHORITY_BASE_COMMIT,
        "adoptionEvidenceCommit": evidence_commit,
        "reviewedStateCommit": reviewed_state,
        "activeHold": {
            "id": "HOLD-W1-GRR-0002",
            "status": "ACTIVE",
            "recoveryRequestId": "GRR-0002",
            "latestApprovedSupplement": "GRR-0002.S01",
            "installedControlGeneration": "GCR-0002",
        },
        "triggerWitness": {
            "path": TRIGGER_PATH,
            "sha256": TRIGGER_SHA256,
            "untracked": True,
            "unstaged": True,
            "executionAuthority": False,
        },
        "predecessor": {
            "controlRevision": PREDECESSOR_REVISION,
            "minimumToolRevision": PREDECESSOR_REVISION,
            "supportedControlCeiling": PREDECESSOR_REVISION,
            "backlog": binding(BACKLOG_PATH, predecessor_backlog, predecessor_backlog_doc),
            "state": binding(STATE_PATH, predecessor_state, predecessor_state_doc),
        },
        "successor": {
            "controlRevision": SUCCESSOR_REVISION,
            "minimumToolRevision": SUCCESSOR_REVISION,
            "supportedControlCeiling": SUPPORTED_CONTROL_CEILING,
            "backlog": binding(BACKLOG_PATH, successor_backlog, successor_backlog_doc),
            "state": binding(STATE_PATH, successor_state, successor_state_doc),
        },
        "paths": {
            "manifest": TRANSACTION_PATH,
            "lock": LOCK_PATH,
            "backlogNext": BACKLOG_NEXT_PATH,
            "stateNext": STATE_NEXT_PATH,
            "backlog": BACKLOG_PATH,
            "state": STATE_PATH,
        },
        "durability": {
            "sameFilesystem": True,
            "exclusiveCreateLock": True,
            "replaceExistingWriteThrough": True,
            "flushSuccessorFilesBeforeManifest": True,
            "flushManifestBeforePublication": True,
            "flushPublishedFiles": True,
            "flushParentDirectories": True,
            "cleanupAfterValidatedPairOnly": True,
        },
        "publicationOrder": [
            "acquire-exclusive-lock",
            "authenticate-authority-cas-workspace-and-witness",
            "write-and-flush-successor-files",
            "exclusive-create-and-flush-prepared-manifest",
            "replace-backlog-write-through-and-flush",
            "replace-state-write-through-and-flush",
            "validate-exact-successor-pair",
            "flush-parent-directories",
            "remove-and-flush-transaction-artifacts",
        ],
        "recovery": {
            "command": "python tools/gcr3ctl.py --repo . recover GCR-0003 --agent codex",
            "idempotent": True,
            "automaticPreflight": True,
            "validTerminalPairs": ["exact-predecessor-pair", "exact-successor-pair"],
            "failClosedStates": [
                "prepared",
                "partial-publication",
                "marker-missing",
                "substituted",
                "stale",
                "dirty-workspace",
                "split-backlog-state",
            ],
            "decisionRule": (
                "complete-successor-only-when-manifest-authority-and-both-durable-successors-validate-"
                "otherwise-restore-exact-predecessor-pair"
            ),
        },
        "finalization": {
            "directChildOfAdoptionEvidenceCommit": True,
            "exactChangedFiles": [BACKLOG_PATH, STATE_PATH],
            "transactionArtifactsAbsent": True,
            "predecessorOrSuccessorPairOnly": True,
        },
    }


def pair_matches(repo: Path, transaction: dict[str, Any], generation: str) -> bool:
    return bindings_match(repo, transaction[generation])


def bindings_match(repo: Path, bindings: dict[str, Any]) -> bool:
    for label, path in (("backlog", repo / BACKLOG_PATH), ("state", repo / STATE_PATH)):
        if not path.is_file() or path.is_symlink():
            return False
        payload = path.read_bytes()
        try:
            document = yaml.safe_load(payload) if label == "backlog" else json.loads(payload)
        except UnicodeError, yaml.YAMLError, json.JSONDecodeError:
            return False
        expected = bindings[label]
        if (
            expected.get("path") != (BACKLOG_PATH if label == "backlog" else STATE_PATH)
            or sha256(payload) != expected.get("rawSha256")
            or canonical_sha(document) != expected.get("canonicalSha256")
        ):
            return False
    return True


def validate_successor_pair(repo: Path, backlog_payload: bytes, state_payload: bytes) -> None:
    try:
        backlog = yaml.safe_load(backlog_payload)
        state = json.loads(state_payload)
    except (UnicodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise SystemExit(f"GCR-0003 successor pair is malformed: {exc}") from exc
    schema_errors = taskctl.backlog_schema_errors(backlog)
    semantic_errors = taskctl.validate(*taskctl.index_backlog(backlog), repo=None)
    validate_runtime(repo, state, "GCR-0003 successor state")
    if (
        schema_errors
        or semantic_errors
        or backlog.get("control_plane", {}).get("revision") != SUCCESSOR_REVISION
        or backlog.get("control_plane", {}).get("minimum_tool_revision") != SUCCESSOR_REVISION
        or state.get("status") != "ADOPTION_FINALIZATION"
    ):
        raise SystemExit("GCR-0003 successor pair is not an exact valid revision-10 adoption")


def restore_predecessor(repo: Path, anchor: dict[str, Any], backlog: bytes, state: bytes) -> None:
    # The raw snapshots are authenticated before any write. In particular, do
    # not reconstruct the Windows worktree bytes from normalized Git blobs.
    artifacts = transaction_artifacts(repo)
    for relative, payload, live in (
        (BACKLOG_NEXT_PATH, backlog, repo / BACKLOG_PATH),
        (STATE_NEXT_PATH, state, repo / STATE_PATH),
    ):
        staged = artifacts[relative]
        if os.path.lexists(staged):
            if not staged.is_file() or staged.is_symlink():
                raise SystemExit(f"GCR-0003 restore artifact is redirected: {relative}")
            unlink_durable(staged)
        write_new_durable(staged, payload)
        move_write_through(staged, live)
    if not bindings_match(repo, anchor["predecessor"]):
        raise SystemExit("GCR-0003 predecessor restoration did not produce the exact pair")
    fsync_directory((repo / BACKLOG_PATH).parent)
    fsync_directory((repo / STATE_PATH).parent)


def cleanup_transaction(repo: Path) -> None:
    artifacts = transaction_artifacts(repo)
    for relative in (TRANSACTION_PATH, BACKLOG_NEXT_PATH, STATE_NEXT_PATH, LOCK_PATH):
        path = artifacts[relative]
        if os.path.lexists(path):
            if not path.is_file() or path.is_symlink():
                raise SystemExit(f"GCR-0003 transaction artifact is redirected: {relative}")
            unlink_durable(path)
            adoption_fault_boundary(f"cleanup-{PurePosixPath(relative).name}")


def complete_transaction(repo: Path, transaction: dict[str, Any]) -> None:
    validate_transaction(repo, transaction)
    artifacts = transaction_artifacts(repo)
    successor_payloads: dict[str, bytes] = {}
    for label, next_relative, live_relative in (
        ("backlog", BACKLOG_NEXT_PATH, BACKLOG_PATH),
        ("state", STATE_NEXT_PATH, STATE_PATH),
    ):
        expected = transaction["successor"][label]
        live = repo / live_relative
        if live.is_file() and sha256(live.read_bytes()) == expected["rawSha256"]:
            successor_payloads[label] = live.read_bytes()
            continue
        next_path = artifacts[next_relative]
        if not next_path.is_file() or next_path.is_symlink() or sha256(next_path.read_bytes()) != expected["rawSha256"]:
            raise SystemExit(f"GCR-0003 durable successor is unavailable or substituted: {label}")
        successor_payloads[label] = next_path.read_bytes()
    validate_successor_pair(repo, successor_payloads["backlog"], successor_payloads["state"])
    for label, next_relative, live_relative in (
        ("backlog", BACKLOG_NEXT_PATH, BACKLOG_PATH),
        ("state", STATE_NEXT_PATH, STATE_PATH),
    ):
        live = repo / live_relative
        expected = transaction["successor"][label]["rawSha256"]
        if not live.is_file() or sha256(live.read_bytes()) != expected:
            move_write_through(artifacts[next_relative], live)
        adoption_fault_boundary(f"{label}-published")
    if not pair_matches(repo, transaction, "successor"):
        raise SystemExit("GCR-0003 publication did not produce the exact successor pair")
    fsync_directory((repo / BACKLOG_PATH).parent)
    fsync_directory((repo / STATE_PATH).parent)
    adoption_fault_boundary("successor-directories-durable")
    cleanup_transaction(repo)


def recover_transaction(repo: Path, authority: tuple[dict[str, Any], dict[str, Any], str]) -> str:
    present = present_transaction_artifacts(repo)
    if not present:
        return "ABSENT"
    require_recovery_workspace(repo)
    with taskctl.exclusive_backlog_lock(repo / BACKLOG_PATH):
        if not present_transaction_artifacts(repo):
            return "ABSENT"
        anchor, predecessor_backlog, predecessor_state = load_recovery_anchor(repo, authority)
        with transaction_lock(repo, recover=True):
            manifest = transaction_artifacts(repo)[TRANSACTION_PATH]
            if not manifest.is_file() or manifest.is_symlink():
                restore_predecessor(repo, anchor, predecessor_backlog, predecessor_state)
                cleanup_transaction(repo)
                return "RESTORED_PREDECESSOR"
            try:
                transaction, _payload = load_json(manifest, "GCR-0003 transaction")
                validate_transaction(repo, transaction)
                if (
                    transaction.get("adoptionEvidenceCommit") != anchor.get("adoptionEvidenceCommit")
                    or transaction.get("reviewedStateCommit") != anchor.get("approvedStateCommit")
                    or transaction.get("predecessor") != anchor.get("predecessor")
                ):
                    raise SystemExit("GCR-0003 transaction differs from the durable recovery anchor")
                complete_transaction(repo, transaction)
            except SystemExit:
                restore_predecessor(repo, anchor, predecessor_backlog, predecessor_state)
                cleanup_transaction(repo)
                return "RESTORED_PREDECESSOR"
    return "COMPLETED_SUCCESSOR"


def canonical_approved_state(
    repo: Path, state: dict[str, Any], state_payload: bytes
) -> tuple[str, str, dict[str, Any], bytes]:
    if state.get("status") != "APPROVED" or not state.get("attempts") or open_findings(state):
        raise SystemExit("GCR-0003 adoption requires an independently APPROVED latest review")
    latest = state["attempts"][-1]
    review = latest.get("review") or {}
    ledger = latest.get("ledger") or {}
    reviewed_state = str(review.get("reviewedStateCommit") or "")
    ledger_relative = str(ledger.get("path") or "")
    approved_state = taskctl.approval_introduction_commit(repo, ledger_relative)
    if (
        review.get("result") != "approved"
        or not approved_state
        or taskctl.git_blob(repo, approved_state, STATE_PATH) != state_payload
    ):
        raise SystemExit("GCR-0003 canonical approved-state commit cannot be derived")
    ledger_payload = (repo / ledger_relative).read_bytes()
    if taskctl.git_blob(repo, approved_state, ledger_relative) != ledger_payload:
        raise SystemExit("GCR-0003 approved-state commit lacks the exact ledger")
    require_exact_commit_delta(
        repo,
        parent=reviewed_state,
        commit=approved_state,
        expected={ledger_relative: "A", STATE_PATH: "M"},
        label="GCR-0003 approved-state commit",
    )
    return reviewed_state, approved_state, ledger, ledger_payload


def command_adopt(args: argparse.Namespace) -> None:
    authority = load_authority(args.repo)
    _approval, packet, approval_base = authority
    if present_transaction_artifacts(args.repo):
        recover_transaction(args.repo, authority)
    state, state_payload = load_state(args.repo, required=True)
    assert state is not None and state_payload is not None
    validate_history(args.repo, state, packet)
    reviewed_state, approved_state, ledger, ledger_payload = canonical_approved_state(args.repo, state, state_payload)
    if str(args.approved_state_commit) != approved_state:
        raise SystemExit("GCR-0003 approved-state argument differs from the canonical review projection")
    evidence_relative = str(args.evidence)
    canonical_evidence = ADOPTION_EVIDENCE_PATH
    if evidence_relative != canonical_evidence:
        raise SystemExit(f"GCR-0003 adoption evidence path must be {canonical_evidence}")
    evidence_commit = git(args.repo, "rev-parse", "HEAD")
    require_exact_commit_delta(
        args.repo,
        parent=approved_state,
        commit=evidence_commit,
        expected={evidence_relative: "A"},
        label="GCR-0003 adoption-evidence commit",
    )
    require_workspace(args.repo)
    evidence, evidence_payload = load_json(args.repo / evidence_relative, "GCR-0003 adoption evidence")
    validate_runtime(args.repo, evidence, "GCR-0003 adoption evidence")
    if (
        taskctl.git_blob(args.repo, evidence_commit, evidence_relative) != evidence_payload
        or evidence.get("controlRecoveryId") != GCR_ID
        or evidence.get("bootstrapUnit") != BOOTSTRAP_ID
        or evidence.get("reviewedStateCommit") != approved_state
        or evidence.get("triggerWitness") != trigger_witness()
        or sorted(evidence.get("expectedChangedFiles") or []) != sorted([BACKLOG_PATH, STATE_PATH])
        or evidence.get("unverifiedItems") != []
        or any(item.get("exitCode") != 0 or item.get("result") != "passed" for item in evidence.get("checks", []))
    ):
        raise SystemExit("GCR-0003 adoption evidence identity, paths, checks, or binding is invalid")
    backlog_payload, data = current_boundary(args.repo, packet, revision=PREDECESSOR_REVISION)
    now = taskctl.utc_now()
    generation = {
        "id": GCR_ID,
        "bootstrap_id": BOOTSTRAP_ID,
        "hold_id": "HOLD-W1-GRR-0002",
        "predecessor_revision": PREDECESSOR_REVISION,
        "successor_revision": SUCCESSOR_REVISION,
        "supported_control_ceiling": SUPPORTED_CONTROL_CEILING,
        "approval_reference": {
            "path": APPROVAL_PATH,
            "sha256": sha256((args.repo / APPROVAL_PATH).read_bytes()),
            "introduction_commit": approval_base,
        },
        "review_reference": {
            "path": ledger.get("path"),
            "sha256": sha256(ledger_payload),
            "reviewed_state_commit": reviewed_state,
            "approved_state_commit": approved_state,
        },
        "adopted_by": ACTOR,
        "adopted_at": now,
    }
    if str(args.agent).strip() != ACTOR or args.agent != ACTOR:
        raise SystemExit(f"GCR-0003 adopter must be exact actor {ACTOR}")
    candidate = copy.deepcopy(taskctl.serializable_backlog(data))
    control = candidate["control_plane"]
    if [item.get("id") for item in control.get("control_generations", [])] != ["GCR-0001", "GCR-0002"]:
        raise SystemExit("GCR-0003 predecessor generation ledger is not exact")
    control["revision"] = SUCCESSOR_REVISION
    control["minimum_tool_revision"] = SUCCESSOR_REVISION
    control["control_generations"].append(generation)
    schema_errors = taskctl.backlog_schema_errors(candidate)
    semantic_errors = taskctl.validate(*taskctl.index_backlog(candidate), repo=None)
    if schema_errors or semantic_errors:
        raise SystemExit(
            "GCR-0003 adoption candidate is invalid:\n- " + "\n- ".join([*schema_errors, *semantic_errors])
        )
    state["status"] = "ADOPTION_FINALIZATION"
    state["adoption"] = {
        "adoptedBy": ACTOR,
        "adoptedAt": now,
        "predecessorRevision": PREDECESSOR_REVISION,
        "successorRevision": SUCCESSOR_REVISION,
        "supportedControlCeiling": SUPPORTED_CONTROL_CEILING,
        "reviewedStateCommit": approved_state,
        "evidence": {"path": evidence_relative, "sha256": sha256(evidence_payload), "commit": evidence_commit},
    }
    validate_runtime(args.repo, state, "GCR-0003 adopted state")
    successor_backlog = yaml.safe_dump(
        taskctl.serializable_backlog(candidate), sort_keys=False, allow_unicode=True, width=120
    ).encode()
    successor_state = (json.dumps(state, indent=2, ensure_ascii=False) + "\n").encode()
    transaction = transaction_document(
        predecessor_backlog=backlog_payload,
        predecessor_state=state_payload,
        successor_backlog=successor_backlog,
        successor_state=successor_state,
        reviewed_state=approved_state,
        evidence_commit=evidence_commit,
    )
    validate_transaction(args.repo, transaction)
    validate_successor_pair(args.repo, successor_backlog, successor_state)
    anchor = recovery_anchor_document(
        transaction=transaction,
        predecessor_backlog=backlog_payload,
        predecessor_state=state_payload,
    )
    validate_recovery_anchor(args.repo, anchor, authority)
    artifacts = transaction_artifacts(args.repo)
    with (
        taskctl.exclusive_backlog_lock(args.repo / BACKLOG_PATH),
        transaction_lock(args.repo, anchor=anchor, authority=authority),
    ):
        if (args.repo / BACKLOG_PATH).read_bytes() != backlog_payload or (
            args.repo / STATE_PATH
        ).read_bytes() != state_payload:
            raise SystemExit("GCR-0003 adoption state changed before transaction preparation")
        write_new_durable(artifacts[BACKLOG_NEXT_PATH], successor_backlog)
        adoption_fault_boundary("backlog-next-durable")
        write_new_durable(artifacts[STATE_NEXT_PATH], successor_state)
        adoption_fault_boundary("state-next-durable")
        write_new_durable(artifacts[TRANSACTION_PATH], (json.dumps(transaction, indent=2) + "\n").encode())
        adoption_fault_boundary("transaction-published")
        complete_transaction(args.repo, transaction)
    print(
        "Prepared GCR-0003 revision 9-to-10 successor; exact two-path finalization commit is required "
        "before GRR-0002.S02"
    )


def command_recover(args: argparse.Namespace) -> None:
    authority = load_authority(args.repo)
    if str(args.agent).strip() != ACTOR or args.agent != ACTOR:
        raise SystemExit(f"GCR-0003 recovery actor must be {ACTOR}")
    print(
        f"GCR-0003 adoption recovery: {recover_transaction(args.repo, authority)}; "
        "ordinary execution remains unauthorized"
    )


def command_validate(args: argparse.Namespace) -> None:
    _approval, packet, _base = load_authority(args.repo)
    present = present_transaction_artifacts(args.repo)
    if present:
        raise SystemExit(f"GCR-0003 adoption transaction requires explicit recovery: {present}")
    backlog = yaml.safe_load((args.repo / BACKLOG_PATH).read_bytes())
    revision = int((backlog.get("control_plane") or {}).get("revision") or 0)
    _payload, data = current_boundary(args.repo, packet, revision=revision)
    errors = taskctl.validate(*taskctl.index_backlog(data), repo=args.repo)
    if errors:
        raise SystemExit("GCR-0003 control semantics are invalid:\n- " + "\n- ".join(errors))
    state, _state_payload = load_state(args.repo, required=False)
    status = "AUTHORIZED"
    if state is not None:
        validate_history(args.repo, state, packet)
        status = "ADOPTED" if state.get("status") == "ADOPTION_FINALIZATION" else str(state.get("status"))
    if args.require_approved and status not in {"APPROVED", "ADOPTED"}:
        raise SystemExit(f"{BOOTSTRAP_ID} is not independently approved")
    print(f"Valid {GCR_ID}: bootstrap={status}; control={revision}")


def command_status(args: argparse.Namespace) -> None:
    _approval, _packet, base = load_authority(args.repo)
    state, _payload = load_state(args.repo, required=False)
    backlog = yaml.safe_load((args.repo / BACKLOG_PATH).read_bytes())
    print(
        yaml.safe_dump(
            {
                "controlRecovery": GCR_ID,
                "bootstrap": {"id": BOOTSTRAP_ID, "status": (state or {}).get("status", "AUTHORIZED")},
                "approvalBase": base,
                "controlRevision": backlog["control_plane"]["revision"],
                "adoptionTransaction": {
                    "status": "RECOVERY_REQUIRED" if present_transaction_artifacts(args.repo) else "ABSENT",
                    "artifacts": present_transaction_artifacts(args.repo),
                },
                "ordinaryExecutionAuthority": False,
            },
            sort_keys=False,
        ).rstrip()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("request")
    submit.add_argument("--agent", required=True)
    submit.add_argument("--approval-commit", required=True)
    submit.add_argument("--implementation-commit", required=True)
    submit.add_argument("--evidence", required=True)
    resubmit = commands.add_parser("resubmit")
    resubmit.add_argument("request")
    resubmit.add_argument("--agent", required=True)
    resubmit.add_argument("--implementation-commit", required=True)
    resubmit.add_argument("--evidence", required=True)
    resubmit.add_argument("--root-cause-analysis")
    review = commands.add_parser("review")
    review.add_argument("request")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--from", dest="ledger", required=True)
    adopt = commands.add_parser("adopt")
    adopt.add_argument("request")
    adopt.add_argument("--agent", required=True)
    adopt.add_argument("--approved-state-commit", required=True)
    adopt.add_argument("--evidence", required=True)
    recover = commands.add_parser("recover")
    recover.add_argument("request")
    recover.add_argument("--agent", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("request")
    validate.add_argument("--require-approved", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("request")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.repo = args.repo.resolve()
    if args.request != GCR_ID:
        raise SystemExit(f"gcr3ctl recognizes only {GCR_ID}")
    if args.command == "submit":
        freeze_submission(args, remediation=False)
    elif args.command == "resubmit":
        freeze_submission(args, remediation=True)
    elif args.command == "review":
        command_review(args)
    elif args.command == "adopt":
        command_adopt(args)
    elif args.command == "recover":
        command_recover(args)
    elif args.command == "validate":
        command_validate(args)
    elif args.command == "status":
        command_status(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
