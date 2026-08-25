#!/usr/bin/env python3
"""Exact GCR-0004 controller for the GCR-0003 R01 review-transition bridge.

The controller recognizes only GCR-0004.B00. It cannot change the backlog,
close a GCR-0003 finding, adopt a control generation, release a hold, resume a
Wave, claim a task, approve a gate, merge a branch, or perform remote work.
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

GCR_ID = "GCR-0004"
BOOTSTRAP_ID = "GCR-0004.B00"
BRANCH = "codex/w1-windows-local-runtime"
ACTOR = "codex"
PACKET_COMMIT = "55cfb8ed74166398e387228a90b30365e78bf3cd"
PACKET_SHA256 = "274b0fc717691e909c7d05d1bf6411beca69749ed6d45ff30039ce6d33c57591"
APPROVAL_COMMIT = "e56218e5c0cc2823d78cfb855e66eb82d39c4cda"
PACKET_PATH = "planning/governance-control-recovery/GCR-0004.packet.json"
APPROVAL_PATH = "planning/governance-control-recovery/GCR-0004.approval.json"
REQUEST_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-request.v4.schema.json"
RUNTIME_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-runtime.v4.schema.json"
TRANSACTION_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-transaction.v4.schema.json"
STATE_PATH = "planning/governance-control-recovery/GCR-0004.B00.state.json"
TRANSACTION_PATH = "planning/governance-control-recovery/GCR-0004.B00.application-transaction.json"
LOCK_PATH = "planning/governance-control-recovery/GCR-0004.B00.application.lock"
STATE_NEXT_PATH = "planning/governance-control-recovery/GCR-0004.B00.gcr3-state.next"
APPLICATION_EVIDENCE_PATH = "artifacts/evidence/governance-control-recovery/GCR-0004.B00.application.json"
GCR3_STATE_PATH = "planning/governance-control-recovery/GCR-0003.B00.state.json"
GCR3_LEDGER_PATH = "planning/governance-control-recovery/GCR-0003.B00.review-R01.json"
GCR3_RUNTIME_V3_PATH = "planning/governance-control-recovery/governance-control-recovery-runtime.v3.schema.json"
GCR3_SUCCESSOR_SCHEMA_PATH = "planning/governance-control-recovery/GCR-0004.B00.gcr3-runtime.schema.json"
GCR3_REVIEWED_STATE_COMMIT = "702ffbc587cca2ec05567d86dc9fd0fa0a25b4a5"
GCR3_CANDIDATE_COMMIT = "a0988d8d9cfde8cde5cc9cf148f9b37ae8e13873"
GCR3_STATE_SHA256 = "0828cb7a52ff5f739dcfbc49832e7b2437f997fced38bac917098081368328e4"
GCR3_LEDGER_SHA256 = "cdfdb2f9fc122cb1a3be3d4546542dfc108a35c96995a340d32b5ae3510ba93b"
GCR3_RUNTIME_V3_SHA256 = "7918c0d255074fdbfd1c400aa9e4008ad6d8efa91584a3010d59612f4cc57124"
BACKLOG_PATH = "planning/backlog.yaml"
BACKLOG_SHA256 = "c7347d103cc1fc6cf54be319f96a8ca5dcf74eddbedd70a3d77a097d335b978d"
TRIGGER_PATH = "artifacts/evidence/W1.A04.B00.json"
TRIGGER_SHA256 = "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c"
RESULT_STATUS = {"approved": "APPROVED", "changes-requested": "CHANGES_REQUESTED", "blocked": "BLOCKED"}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def trigger_witness() -> dict[str, Any]:
    return {
        "path": TRIGGER_PATH,
        "sha256": TRIGGER_SHA256,
        "role": "atomic-failure-trigger-only",
        "untracked": True,
        "unstaged": True,
        "executionAuthority": False,
    }


def adverse_ledger_reference(*, untracked: bool = True) -> dict[str, Any]:
    return {
        "path": GCR3_LEDGER_PATH,
        "sha256": GCR3_LEDGER_SHA256,
        "untracked": untracked,
        "unstaged": untracked,
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
    validate_schema(repo, document, RUNTIME_SCHEMA_PATH, label)


def validate_transaction(repo: Path, document: dict[str, Any]) -> None:
    validate_schema(repo, document, TRANSACTION_SCHEMA_PATH, "GCR-0004 application transaction")


def validate_trigger(repo: Path) -> None:
    path = safe_path(repo, TRIGGER_PATH, label="GCR-0004 trigger witness", prefix="artifacts/evidence")
    if path.is_symlink() or getattr(os.path, "isjunction", lambda _value: False)(path):
        raise SystemExit("GCR-0004 trigger witness must not be redirected")
    if sha256(path.read_bytes()) != TRIGGER_SHA256:
        raise SystemExit("GCR-0004 trigger witness is missing or has changed")
    if TRIGGER_PATH in set(git(repo, "ls-files", "--", TRIGGER_PATH).splitlines()):
        raise SystemExit("GCR-0004 trigger witness must remain untracked")
    if TRIGGER_PATH in set(git(repo, "diff", "--cached", "--name-only", "--").splitlines()):
        raise SystemExit("GCR-0004 trigger witness must remain unstaged")


def validate_adverse_ledger(repo: Path, *, require_untracked: bool) -> tuple[dict[str, Any], bytes]:
    path = safe_path(repo, GCR3_LEDGER_PATH, label="GCR-0003 adverse ledger", prefix="planning")
    if path.is_symlink() or getattr(os.path, "isjunction", lambda _value: False)(path):
        raise SystemExit("GCR-0003 adverse ledger must not be redirected")
    ledger, payload = load_json(path, "GCR-0003 adverse ledger")
    if sha256(payload) != GCR3_LEDGER_SHA256:
        raise SystemExit("GCR-0003 adverse ledger differs from the independently reviewed bytes")
    tracked = GCR3_LEDGER_PATH in set(git(repo, "ls-files", "--", GCR3_LEDGER_PATH).splitlines())
    staged = GCR3_LEDGER_PATH in set(git(repo, "diff", "--cached", "--name-only", "--").splitlines())
    if require_untracked and (tracked or staged):
        raise SystemExit("GCR-0003 adverse ledger must remain untracked and unstaged before bridge finalization")
    if not require_untracked and not tracked:
        raise SystemExit("Applied GCR-0003 adverse ledger must be tracked")
    validate_schema(repo, ledger, GCR3_RUNTIME_V3_PATH, "GCR-0003 adverse ledger")
    if (
        ledger.get("controlRecoveryId") != "GCR-0003"
        or ledger.get("bootstrapUnit") != "GCR-0003.B00"
        or ledger.get("attemptId") != "R01"
        or ledger.get("candidateCommit") != GCR3_CANDIDATE_COMMIT
        or ledger.get("reviewedStateCommit") != GCR3_REVIEWED_STATE_COMMIT
        or ledger.get("result") != "changes-requested"
        or not any(item.get("blocking") is True for item in ledger.get("findings", []))
        or ledger.get("closures") != []
    ):
        raise SystemExit("GCR-0003 adverse ledger identity, result, findings, or closures are invalid")
    return ledger, payload


def require_workspace(repo: Path, *, extra_untracked: set[str] | None = None) -> None:
    if git(repo, "branch", "--show-current") != BRANCH:
        raise SystemExit(f"GCR-0004 transitions require exact branch {BRANCH}")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=repo, check=False).returncode != 0:
        raise SystemExit("Tracked worktree changes exist; GCR-0004 transitions require an exact commit")
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise SystemExit("Staged changes exist; GCR-0004 transitions require an exact commit")
    validate_trigger(repo)
    validate_adverse_ledger(repo, require_untracked=True)
    allowed = {TRIGGER_PATH, GCR3_LEDGER_PATH, *(extra_untracked or set())}
    untracked = set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    if untracked != allowed:
        difference = sorted(untracked ^ allowed)
        raise SystemExit(f"GCR-0004 untracked-path boundary differs: {difference[0] if difference else '<unknown>'}")


def load_authority(repo: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    packet, packet_payload = load_json(safe_path(repo, PACKET_PATH, label="GCR-0004 packet"), "GCR-0004 packet")
    approval, approval_payload = load_json(
        safe_path(repo, APPROVAL_PATH, label="GCR-0004 approval"), "GCR-0004 approval"
    )
    if sha256(packet_payload) != PACKET_SHA256 or taskctl.git_blob(repo, PACKET_COMMIT, PACKET_PATH) != packet_payload:
        raise SystemExit("GCR-0004 packet differs from its independently reviewed Git blob")
    validate_schema(repo, packet, REQUEST_SCHEMA_PATH, "GCR-0004 packet")
    validate_runtime(repo, approval, "GCR-0004 approval")
    introduction = taskctl.approval_introduction_commit(repo, APPROVAL_PATH)
    if introduction != APPROVAL_COMMIT or taskctl.git_blob(repo, introduction, APPROVAL_PATH) != approval_payload:
        raise SystemExit("GCR-0004 approval is absent, replaced, or edited after introduction")
    packet_ref = approval.get("packet") or {}
    review_ref = (approval.get("independentPacketReview") or {}).get("ledger") or {}
    review_path = safe_path(repo, str(review_ref.get("path") or ""), label="GCR-0004 packet review")
    review, review_payload = load_json(review_path, "GCR-0004 packet review")
    validate_runtime(repo, review, "GCR-0004 packet review")
    if (
        packet_ref != {"path": PACKET_PATH, "sha256": PACKET_SHA256, "commit": PACKET_COMMIT}
        or approval.get("status") != "APPROVED"
        or approval.get("controlRecoveryId") != GCR_ID
        or approval.get("triggerWitness") != trigger_witness()
        or (approval.get("executionAuthority") or {}).get("bootstrapUnit") != BOOTSTRAP_ID
        or (approval.get("executionAuthority") or {}).get("ordinaryExecution") is not False
        or sha256(review_payload) != review_ref.get("sha256")
        or taskctl.git_blob(repo, str(review_ref.get("commit") or ""), str(review_ref.get("path") or ""))
        != review_payload
        or review.get("result") != "approved"
        or review.get("approvalAvailable") is not True
        or review.get("candidateCommit") != PACKET_COMMIT
        or review.get("packetSha256") != PACKET_SHA256
        or review.get("findings") != []
        or not taskctl.git_is_ancestor(repo, PACKET_COMMIT, introduction)
        or not taskctl.git_is_ancestor(repo, str(review_ref.get("commit") or ""), introduction)
    ):
        raise SystemExit("GCR-0004 approval or independent packet review authority is invalid")
    for reference in packet.get("files", []):
        relative = str(reference.get("path") or "")
        path = safe_path(repo, relative, label="GCR-0004 packet file", prefix="planning")
        payload = path.read_bytes()
        if sha256(payload) != reference.get("sha256") or taskctl.git_blob(repo, PACKET_COMMIT, relative) != payload:
            raise SystemExit(f"GCR-0004 packet file binding differs: {relative}")
    for pattern in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", []):
        validate_scope_pattern(str(pattern))
    predecessor = packet.get("predecessorAuthority") or {}
    for key in ("gcr3Packet", "gcr3PacketReview", "gcr3Approval", "gcr3Evidence"):
        reference = predecessor.get(key) or {}
        authority_payload = taskctl.git_blob(
            repo,
            str(reference.get("commit") or ""),
            str(reference.get("path") or ""),
        )
        if authority_payload is None or sha256(authority_payload) != reference.get("sha256"):
            raise SystemExit(f"GCR-0004 predecessor authority differs: {key}")
    frozen = predecessor.get("frozenReviewedState") or {}
    frozen_payload = taskctl.git_blob(repo, GCR3_REVIEWED_STATE_COMMIT, GCR3_STATE_PATH)
    if (
        frozen.get("commit") != GCR3_REVIEWED_STATE_COMMIT
        or frozen.get("sha256") != GCR3_STATE_SHA256
        or frozen_payload is None
        or sha256(frozen_payload) != GCR3_STATE_SHA256
        or sha256((repo / GCR3_RUNTIME_V3_PATH).read_bytes()) != GCR3_RUNTIME_V3_SHA256
    ):
        raise SystemExit("GCR-0004 frozen GCR-0003 authority differs")
    backlog_payload = (repo / BACKLOG_PATH).read_bytes()
    backlog = yaml.safe_load(backlog_payload)
    task_map = taskctl.index_backlog(backlog)[3]
    if (
        sha256(backlog_payload) != BACKLOG_SHA256
        or (backlog.get("control_plane") or {}).get("revision") != 9
        or (backlog.get("control_plane") or {}).get("minimum_tool_revision") != 9
        or taskctl.wave_map(backlog)["W1"]["campaign"]["status"] != "PAUSED"
        or task_map["CAP-02.S04.T03"]["status"] != "BLOCKED"
        or "W1.A04" in taskctl.wave_amendment_map(backlog)
        or taskctl.index_backlog(backlog)[4]["G1"]["status"] != "PENDING"
    ):
        raise SystemExit("GCR-0004 stopped W1 boundary differs")
    return approval, packet, introduction


def state_path(repo: Path) -> Path:
    return safe_path(
        repo,
        STATE_PATH,
        label="GCR-0004 state",
        prefix="planning/governance-control-recovery",
        require_exists=False,
    )


def load_state(repo: Path, *, required: bool) -> tuple[dict[str, Any] | None, bytes | None]:
    path = state_path(repo)
    if not path.exists():
        if required:
            raise SystemExit("GCR-0004 B00 state is absent")
        return None, None
    state, payload = load_json(path, "GCR-0004 state")
    validate_runtime(repo, state, "GCR-0004 state")
    return state, payload


def evidence_path(attempt_id: str) -> str:
    return f"artifacts/evidence/governance-control-recovery/GCR-0004.B00.{attempt_id}.json"


def review_path(attempt_id: str) -> str:
    return f"planning/governance-control-recovery/GCR-0004.B00.review-{attempt_id}.json"


def open_findings(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    opened: dict[str, dict[str, Any]] = {}
    for attempt in state.get("attempts", []):
        for closure in attempt.get("closures", []):
            opened.pop(str(closure.get("findingId") or ""), None)
        for finding in attempt.get("findings", []):
            opened[str(finding.get("id") or "")] = finding
    return opened


def changed_paths(repo: Path, base: str, candidate: str) -> list[str]:
    if base == candidate or not taskctl.git_is_ancestor(repo, base, candidate):
        raise SystemExit("GCR-0004 implementation candidate must strictly descend from its approval base")
    return sorted(line for line in git(repo, "diff", "--name-only", f"{base}..{candidate}", "--").splitlines() if line)


def validate_evidence(
    repo: Path,
    packet: dict[str, Any],
    relative: str,
    candidate: str,
    base: str,
    attempt_id: str,
    prior_open: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], bytes]:
    expected = evidence_path(attempt_id)
    if relative != expected:
        raise SystemExit(f"GCR-0004 evidence path must be {expected}")
    document, payload = load_json(
        safe_path(repo, relative, label="GCR-0004 evidence", prefix="artifacts/evidence/governance-control-recovery"),
        "GCR-0004 evidence",
    )
    validate_runtime(repo, document, "GCR-0004 evidence")
    actual = changed_paths(repo, base, candidate)
    patterns = [str(item) for item in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", [])]
    outside = [path for path in actual if not path_authorized(path, patterns)]
    premature = sorted(set(actual) & {GCR3_STATE_PATH, GCR3_LEDGER_PATH})
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
        or document.get("adverseLedger") != adverse_ledger_reference()
        or document.get("changedFiles") != actual
        or outside
        or premature
        or [item.get("index") for item in criteria] != list(range(1, len(expected_criteria) + 1))
        or [item.get("statement") for item in criteria] != expected_criteria
        or document.get("unverifiedItems") != []
        or len(closure_ids) != len(set(closure_ids))
        or set(closure_ids) != set(prior_open)
    ):
        raise SystemExit("GCR-0004 evidence identity, scope, criteria, closures, or verification is invalid")
    checks = document.get("checks") or []
    if (
        not checks
        or len({item.get("id") for item in checks}) != len(checks)
        or any(item.get("exitCode") != 0 or item.get("result") != "passed" for item in checks)
        or set((document.get("verificationSelection") or {}).get("selectedChecks") or [])
        != {item.get("id") for item in checks}
    ):
        raise SystemExit("GCR-0004 evidence checks must be unique, selected, and passing")
    for closure in closures:
        if (
            str(closure.get("findingId") or "") not in prior_open
            or closure.get("disposition") not in {"fixed", "not-reproduced", "superseded", "accepted-risk"}
            or not str(closure.get("evidence") or "").strip()
        ):
            raise SystemExit("GCR-0004 finding closure is stale or incomplete")
    return document, payload


def freeze_submission(args: argparse.Namespace, *, remediation: bool) -> None:
    _approval, packet, base = load_authority(args.repo)
    if present_transaction_artifacts(args.repo):
        recover_transaction(args.repo)
    state, _payload = load_state(args.repo, required=False)
    if remediation:
        if state is None or state.get("status") not in {"CHANGES_REQUESTED", "BLOCKED"}:
            raise SystemExit("GCR-0004 resubmission requires an adverse prior review")
    elif state is not None:
        raise SystemExit("GCR-0004 initial submission already exists")
    if not remediation and str(args.approval_commit) != base:
        raise SystemExit("GCR-0004 approval-commit argument differs from the immutable approval introduction")
    attempts = (state or {}).get("attempts", [])
    attempt_id = f"R{len(attempts) + 1:02d}"
    relative = str(args.evidence)
    require_workspace(args.repo, extra_untracked={relative})
    candidate = str(args.implementation_commit)
    if candidate != git(args.repo, "rev-parse", "HEAD"):
        raise SystemExit("GCR-0004 candidate must equal current HEAD")
    if args.agent != ACTOR:
        raise SystemExit(f"GCR-0004 implementer must be exact actor {ACTOR}")
    prior_open = open_findings(state or {})
    document, payload = validate_evidence(
        args.repo,
        packet,
        relative,
        candidate,
        base,
        attempt_id,
        prior_open,
    )
    if len(attempts) >= 2:
        rca = document.get("rootCauseAnalysis")
        if not isinstance(rca, str) or not rca.strip() or rca != rca.strip():
            raise SystemExit("GCR-0004 third and later submissions require a normalized root-cause analysis")
    elif document.get("rootCauseAnalysis") is not None:
        raise SystemExit("GCR-0004 R01/R02 evidence must not invent a root-cause analysis")
    if attempts:
        prior_candidate = str((attempts[-1].get("submission") or {}).get("candidateCommit") or "")
        if prior_candidate == candidate or not taskctl.git_is_ancestor(args.repo, prior_candidate, candidate):
            raise SystemExit("GCR-0004 remediation candidate is not a strict descendant")
    submission = {
        "attemptId": attempt_id,
        "submittedBy": ACTOR,
        "submittedAt": taskctl.utc_now(),
        "candidateCommit": candidate,
        "baseCommit": base,
        "branch": BRANCH,
        "evidence": {"path": relative, "sha256": sha256(payload), "commit": candidate},
        "priorAttemptId": ((attempts[-1].get("submission") or {}).get("attemptId") if attempts else None),
        "openFindingIds": sorted(prior_open),
        "rootCauseAnalysis": document.get("rootCauseAnalysis"),
    }
    if state is None:
        state = {
            "schemaVersion": "4.0-control-recovery-state",
            "documentType": "governance-control-recovery-bootstrap-state",
            "controlRecoveryId": GCR_ID,
            "bootstrapUnit": BOOTSTRAP_ID,
            "status": "REVIEW",
            "approval": {
                "path": APPROVAL_PATH,
                "sha256": sha256((args.repo / APPROVAL_PATH).read_bytes()),
                "commit": base,
            },
            "triggerWitness": trigger_witness(),
            "adverseLedger": adverse_ledger_reference(),
            "attempts": [],
            "currentSubmission": submission,
            "application": None,
        }
    else:
        state["status"] = "REVIEW"
        state["currentSubmission"] = submission
    validate_runtime(args.repo, state, "GCR-0004 submission state")
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
    validate_runtime(repo, ledger, "GCR-0004 review ledger")
    submission = state.get("currentSubmission") or {}
    findings = ledger.get("findings") or []
    closures = ledger.get("closures") or []
    ordering = [SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings]
    finding_ids = [str(item.get("id") or "") for item in findings]
    prior_open = open_findings(state)
    prior_ids = {
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
        or len(finding_ids) != len(set(finding_ids))
        or set(finding_ids) & prior_ids
        or len(closure_ids) != len(set(closure_ids))
        or set(closure_ids) - set(prior_open)
    ):
        raise SystemExit("GCR-0004 review ledger differs from the frozen submission or review controls")
    result = str(ledger.get("result") or "")
    if result not in RESULT_STATUS:
        raise SystemExit("GCR-0004 review result is invalid")
    remaining = [item for key, item in prior_open.items() if key not in closure_ids]
    if result == "approved" and (findings or any(item.get("blocking") for item in remaining)):
        raise SystemExit("GCR-0004 approval cannot introduce findings or retain an open blocker")


def command_review(args: argparse.Namespace) -> None:
    load_authority(args.repo)
    state, _payload = load_state(args.repo, required=True)
    assert state is not None
    if state.get("status") != "REVIEW" or not state.get("currentSubmission"):
        raise SystemExit("GCR-0004 has no frozen submission eligible for review")
    relative = str(args.ledger)
    require_workspace(args.repo, extra_untracked={relative})
    reviewer = str(args.reviewer).strip()
    if not reviewer or reviewer != args.reviewer or reviewer == ACTOR:
        raise SystemExit("GCR-0004 reviewer must be normalized and independent")
    reviewed_state = git(args.repo, "rev-parse", "HEAD")
    ledger, payload = load_json(
        safe_path(
            repo=args.repo, relative=relative, label="GCR-0004 review", prefix="planning/governance-control-recovery"
        ),
        "GCR-0004 review",
    )
    validate_review(args.repo, ledger, state, relative, reviewer, reviewed_state)
    submission = copy.deepcopy(state["currentSubmission"])
    state["attempts"].append(
        {
            "submission": submission,
            "review": {
                "reviewer": reviewer,
                "result": ledger["result"],
                "reviewedAt": taskctl.utc_now(),
                "reviewedStateCommit": reviewed_state,
                "notes": ledger.get("notes"),
            },
            "ledger": {"path": relative, "sha256": sha256(payload), "commit": reviewed_state},
            "findings": ledger.get("findings") or [],
            "closures": ledger.get("closures") or [],
        }
    )
    state["status"] = RESULT_STATUS[str(ledger["result"])]
    state["currentSubmission"] = None
    validate_runtime(args.repo, state, "GCR-0004 reviewed state")
    write_json_atomic(args.repo / STATE_PATH, state)
    print(f"Recorded {BOOTSTRAP_ID}/{submission['attemptId']} as {state['status']}")


def validate_history(repo: Path, state: dict[str, Any], packet: dict[str, Any]) -> None:
    attempts = state.get("attempts") or []
    if [((item.get("submission") or {}).get("attemptId")) for item in attempts] != [
        f"R{index:02d}" for index in range(1, len(attempts) + 1)
    ]:
        raise SystemExit("GCR-0004 attempt history is not append-only and sequential")
    prior_candidate: str | None = None
    for index, attempt in enumerate(attempts):
        submission = attempt.get("submission") or {}
        review = attempt.get("review") or {}
        ledger_ref = attempt.get("ledger") or {}
        attempt_id = str(submission.get("attemptId") or "")
        candidate = str(submission.get("candidateCommit") or "")
        reviewed_state = str(review.get("reviewedStateCommit") or "")
        evidence = submission.get("evidence") or {}
        if (
            submission.get("baseCommit") != APPROVAL_COMMIT
            or submission.get("branch") != BRANCH
            or submission.get("submittedBy") != ACTOR
            or evidence.get("commit") != candidate
            or submission.get("priorAttemptId")
            != ((attempts[index - 1].get("submission") or {}).get("attemptId") if index else None)
        ):
            raise SystemExit(f"GCR-0004 {attempt_id} submission authority is invalid")
        if prior_candidate and (
            prior_candidate == candidate or not taskctl.git_is_ancestor(repo, prior_candidate, candidate)
        ):
            raise SystemExit(f"GCR-0004 {attempt_id} candidate is not a strict remediation descendant")
        prior_candidate = candidate
        require_exact_commit_delta(
            repo,
            parent=candidate,
            commit=reviewed_state,
            expected={str(evidence.get("path")): "A", STATE_PATH: "A" if index == 0 else "M"},
            label=f"GCR-0004 {attempt_id} reviewed-state commit",
        )
        evidence_payload = taskctl.git_blob(repo, reviewed_state, str(evidence.get("path") or ""))
        reviewed_payload = taskctl.git_blob(repo, reviewed_state, STATE_PATH)
        if evidence_payload is None or sha256(evidence_payload) != evidence.get("sha256") or reviewed_payload is None:
            raise SystemExit(f"GCR-0004 {attempt_id} reviewed-state evidence binding is invalid")
        prior_open = open_findings({"attempts": attempts[:index]})
        _evidence_document, worktree_evidence_payload = validate_evidence(
            repo,
            packet,
            str(evidence.get("path") or ""),
            candidate,
            APPROVAL_COMMIT,
            attempt_id,
            prior_open,
        )
        if worktree_evidence_payload != evidence_payload:
            raise SystemExit(f"GCR-0004 {attempt_id} evidence changed after its reviewed-state commit")
        reviewed_document = json.loads(reviewed_payload)
        validate_runtime(repo, reviewed_document, f"GCR-0004 {attempt_id} reviewed state")
        if (
            reviewed_document.get("status") != "REVIEW"
            or reviewed_document.get("currentSubmission") != submission
            or reviewed_document.get("attempts") != attempts[:index]
        ):
            raise SystemExit(f"GCR-0004 {attempt_id} reviewed-state projection is invalid")
        ledger_relative = str(ledger_ref.get("path") or "")
        projection_commit = taskctl.approval_introduction_commit(repo, ledger_relative)
        if not projection_commit:
            raise SystemExit(f"GCR-0004 {attempt_id} review projection is absent")
        require_exact_commit_delta(
            repo,
            parent=reviewed_state,
            commit=projection_commit,
            expected={ledger_relative: "A", STATE_PATH: "M"},
            label=f"GCR-0004 {attempt_id} review projection",
        )
        ledger_payload = taskctl.git_blob(repo, projection_commit, ledger_relative)
        state_payload = taskctl.git_blob(repo, projection_commit, STATE_PATH)
        if ledger_payload is None or sha256(ledger_payload) != ledger_ref.get("sha256") or state_payload is None:
            raise SystemExit(f"GCR-0004 {attempt_id} review projection binding is invalid")
        ledger = json.loads(ledger_payload)
        projected = json.loads(state_payload)
        reviewer = str(ledger.get("reviewer") or "")
        validate_review(repo, ledger, reviewed_document, ledger_relative, reviewer, reviewed_state)
        expected_attempt = copy.deepcopy(attempt)
        expected_state = copy.deepcopy(reviewed_document)
        expected_state["attempts"].append(expected_attempt)
        expected_state["status"] = RESULT_STATUS[str(ledger["result"])]
        expected_state["currentSubmission"] = None
        if (
            ledger_ref != {"path": ledger_relative, "sha256": sha256(ledger_payload), "commit": reviewed_state}
            or projected != expected_state
        ):
            raise SystemExit(f"GCR-0004 {attempt_id} review ledger and state projection disagree")
    current = state.get("currentSubmission")
    if current is not None:
        if state.get("status") != "REVIEW" or current.get("attemptId") != f"R{len(attempts) + 1:02d}":
            raise SystemExit("GCR-0004 current submission is not the exact next REVIEW projection")
    elif attempts:
        expected = RESULT_STATUS[str((attempts[-1].get("review") or {}).get("result"))]
        if state.get("status") not in {expected, "APPLICATION_FINALIZATION"}:
            raise SystemExit("GCR-0004 state status differs from the latest immutable review")
    elif state.get("status") == "REVIEW":
        raise SystemExit("GCR-0004 REVIEW state lacks a frozen submission")
    if (
        state.get("approval")
        != {
            "path": APPROVAL_PATH,
            "sha256": sha256((repo / APPROVAL_PATH).read_bytes()),
            "commit": APPROVAL_COMMIT,
        }
        or state.get("triggerWitness") != trigger_witness()
    ):
        raise SystemExit("GCR-0004 state authority differs from approval or witness")
    if state.get("adverseLedger") != adverse_ledger_reference():
        raise SystemExit("GCR-0004 state adverse-ledger boundary differs")
    for pattern in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", []):
        validate_scope_pattern(str(pattern))


def canonical_approved_state(
    repo: Path, state: dict[str, Any], state_payload: bytes
) -> tuple[str, str, dict[str, Any], bytes]:
    if state.get("status") != "APPROVED" or not state.get("attempts") or open_findings(state):
        raise SystemExit("GCR-0004 application requires an independently APPROVED latest review")
    latest = state["attempts"][-1]
    review = latest.get("review") or {}
    ledger_ref = latest.get("ledger") or {}
    reviewed_state = str(review.get("reviewedStateCommit") or "")
    ledger_relative = str(ledger_ref.get("path") or "")
    approved_state = taskctl.approval_introduction_commit(repo, ledger_relative)
    if (
        review.get("result") != "approved"
        or not approved_state
        or taskctl.git_blob(repo, approved_state, STATE_PATH) != state_payload
    ):
        raise SystemExit("GCR-0004 canonical approved-state commit cannot be derived")
    ledger_payload = (repo / ledger_relative).read_bytes()
    if taskctl.git_blob(repo, approved_state, ledger_relative) != ledger_payload:
        raise SystemExit("GCR-0004 approved-state commit lacks the exact ledger")
    require_exact_commit_delta(
        repo,
        parent=reviewed_state,
        commit=approved_state,
        expected={ledger_relative: "A", STATE_PATH: "M"},
        label="GCR-0004 approved-state commit",
    )
    return reviewed_state, approved_state, ledger_ref, ledger_payload


def canonical_sha(document: dict[str, Any]) -> str:
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())


def state_binding(payload: bytes, document: dict[str, Any]) -> dict[str, str]:
    return {"path": GCR3_STATE_PATH, "rawSha256": sha256(payload), "canonicalSha256": canonical_sha(document)}


def transaction_artifacts(repo: Path) -> dict[str, Path]:
    return {relative: _artifact_path(repo, relative) for relative in (LOCK_PATH, TRANSACTION_PATH, STATE_NEXT_PATH)}


def present_transaction_artifacts(repo: Path) -> list[str]:
    return [relative for relative, path in transaction_artifacts(repo).items() if os.path.lexists(path)]


def application_anchor(
    *, approved_state: str, evidence_commit: str, predecessor_payload: bytes, successor_payload: bytes
) -> dict[str, Any]:
    return {
        "schemaVersion": "4.0-control-recovery-review-transition-anchor",
        "documentType": "governance-control-recovery-review-transition-anchor",
        "transactionId": "GCR-0004.B00.APPLY",
        "controlRecoveryId": GCR_ID,
        "bootstrapUnit": BOOTSTRAP_ID,
        "actor": ACTOR,
        "branch": BRANCH,
        "approvedStateCommit": approved_state,
        "applicationEvidenceCommit": evidence_commit,
        "reviewedStateCommit": GCR3_REVIEWED_STATE_COMMIT,
        "adverseLedgerSha256": GCR3_LEDGER_SHA256,
        "predecessorStateBase64": base64.b64encode(predecessor_payload).decode("ascii"),
        "successorStateSha256": sha256(successor_payload),
    }


def validate_anchor(repo: Path, anchor: dict[str, Any]) -> tuple[bytes, str, str]:
    expected_keys = {
        "schemaVersion",
        "documentType",
        "transactionId",
        "controlRecoveryId",
        "bootstrapUnit",
        "actor",
        "branch",
        "approvedStateCommit",
        "applicationEvidenceCommit",
        "reviewedStateCommit",
        "adverseLedgerSha256",
        "predecessorStateBase64",
        "successorStateSha256",
    }
    evidence_commit = str(anchor.get("applicationEvidenceCommit") or "")
    approved_state = str(anchor.get("approvedStateCommit") or "")
    if (
        set(anchor) != expected_keys
        or anchor.get("schemaVersion") != "4.0-control-recovery-review-transition-anchor"
        or anchor.get("documentType") != "governance-control-recovery-review-transition-anchor"
        or anchor.get("transactionId") != "GCR-0004.B00.APPLY"
        or anchor.get("controlRecoveryId") != GCR_ID
        or anchor.get("bootstrapUnit") != BOOTSTRAP_ID
        or anchor.get("actor") != ACTOR
        or anchor.get("branch") != BRANCH
        or anchor.get("reviewedStateCommit") != GCR3_REVIEWED_STATE_COMMIT
        or anchor.get("adverseLedgerSha256") != GCR3_LEDGER_SHA256
        or git(repo, "rev-parse", "HEAD") != evidence_commit
    ):
        raise SystemExit("GCR-0004 recovery anchor identity or HEAD binding is invalid")
    parents = git(repo, "rev-list", "--parents", "-n", "1", evidence_commit).split()
    if parents != [evidence_commit, approved_state]:
        raise SystemExit("GCR-0004 application evidence is not based on the approved-state parent")
    require_exact_commit_delta(
        repo,
        parent=approved_state,
        commit=evidence_commit,
        expected={APPLICATION_EVIDENCE_PATH: "A"},
        label="GCR-0004 application-evidence commit",
    )
    try:
        predecessor = base64.b64decode(str(anchor.get("predecessorStateBase64") or "").encode("ascii"), validate=True)
    except (UnicodeError, ValueError) as exc:
        raise SystemExit("GCR-0004 predecessor state snapshot is invalid") from exc
    if sha256(predecessor) != GCR3_STATE_SHA256:
        raise SystemExit("GCR-0004 predecessor state snapshot differs")
    return predecessor, approved_state, evidence_commit


@contextmanager
def transaction_lock(repo: Path, *, anchor: dict[str, Any] | None = None, recover: bool = False) -> Iterator[None]:
    path = transaction_artifacts(repo)[LOCK_PATH]
    if os.path.lexists(path):
        if not recover or not path.is_file() or path.is_symlink():
            raise SystemExit("GCR-0004 application lock already exists or is redirected")
        yield
        return
    if recover or anchor is None:
        raise SystemExit("GCR-0004 application requires an exact recovery anchor")
    write_new_durable(path, (json.dumps(anchor, indent=2, ensure_ascii=False) + "\n").encode())
    adoption_fault_boundary("gcr4-lock-durable")
    yield


def load_anchor(repo: Path) -> tuple[dict[str, Any], bytes, str, str]:
    path = transaction_artifacts(repo)[LOCK_PATH]
    if not path.is_file() or path.is_symlink():
        raise SystemExit("GCR-0004 recovery anchor is absent or redirected")
    anchor, _payload = load_json(path, "GCR-0004 recovery anchor")
    predecessor, approved_state, evidence_commit = validate_anchor(repo, anchor)
    return anchor, predecessor, approved_state, evidence_commit


def recovered_gcr3_state(
    repo: Path,
    *,
    approved_state: str,
    evidence_commit: str,
    evidence_payload: bytes,
) -> dict[str, Any]:
    predecessor_payload = (repo / GCR3_STATE_PATH).read_bytes()
    if sha256(predecessor_payload) != GCR3_STATE_SHA256:
        raise SystemExit("GCR-0003 frozen state differs before bridge derivation")
    predecessor = json.loads(predecessor_payload)
    validate_schema(repo, predecessor, GCR3_RUNTIME_V3_PATH, "GCR-0003 frozen reviewed state")
    ledger, ledger_payload = validate_adverse_ledger(repo, require_untracked=True)
    submission = copy.deepcopy(predecessor.get("currentSubmission") or {})
    if (
        predecessor.get("status") != "REVIEW"
        or predecessor.get("attempts") != []
        or submission.get("attemptId") != "R01"
        or submission.get("candidateCommit") != GCR3_CANDIDATE_COMMIT
        or ledger.get("evidence") != submission.get("evidence")
    ):
        raise SystemExit("GCR-0003 frozen submission and adverse ledger disagree")
    result_state = {
        "schemaVersion": "3.1-control-recovery-state",
        "documentType": predecessor["documentType"],
        "controlRecoveryId": predecessor["controlRecoveryId"],
        "bootstrapUnit": predecessor["bootstrapUnit"],
        "status": "CHANGES_REQUESTED",
        "approval": copy.deepcopy(predecessor["approval"]),
        "triggerWitness": copy.deepcopy(predecessor["triggerWitness"]),
        "attempts": [
            {
                "submission": submission,
                "review": {
                    "reviewer": ledger["reviewer"],
                    "result": ledger["result"],
                    "reviewedAt": taskctl.utc_now(),
                    "reviewedStateCommit": GCR3_REVIEWED_STATE_COMMIT,
                    "notes": ledger.get("notes"),
                },
                "ledger": {
                    "path": GCR3_LEDGER_PATH,
                    "sha256": sha256(ledger_payload),
                    "commit": GCR3_REVIEWED_STATE_COMMIT,
                },
                "findings": copy.deepcopy(ledger.get("findings") or []),
                "closures": copy.deepcopy(ledger.get("closures") or []),
            }
        ],
        "currentSubmission": None,
        "adoption": None,
        "reviewTransitionRecovery": {
            "controlRecoveryId": GCR_ID,
            "bootstrapUnit": BOOTSTRAP_ID,
            "reviewedStateCommit": GCR3_REVIEWED_STATE_COMMIT,
            "adverseLedger": {"path": GCR3_LEDGER_PATH, "sha256": GCR3_LEDGER_SHA256},
            "approvedGcr4StateCommit": approved_state,
            "applicationEvidence": {
                "path": APPLICATION_EVIDENCE_PATH,
                "sha256": sha256(evidence_payload),
                "commit": evidence_commit,
            },
            "result": "changes-requested",
            "controlRevision": 9,
            "ordinaryExecutionAuthority": False,
        },
    }
    validate_schema(
        repo,
        result_state,
        GCR3_SUCCESSOR_SCHEMA_PATH,
        "GCR-0003 recovered adverse state",
    )
    return result_state


def transaction_document(
    *, predecessor: bytes, successor: bytes, approved_state: str, evidence_commit: str
) -> dict[str, Any]:
    predecessor_document = json.loads(predecessor)
    successor_document = json.loads(successor)
    return {
        "schemaVersion": "4.0-control-recovery-review-transition",
        "documentType": "governance-control-recovery-review-transition-transaction",
        "transactionId": "GCR-0004.B00.APPLY",
        "controlRecoveryId": GCR_ID,
        "bootstrapUnit": BOOTSTRAP_ID,
        "status": "PREPARED",
        "createdBy": ACTOR,
        "createdAt": taskctl.utc_now(),
        "branch": BRANCH,
        "reviewedStateCommit": GCR3_REVIEWED_STATE_COMMIT,
        "approvedGcr4StateCommit": approved_state,
        "applicationEvidenceCommit": evidence_commit,
        "activeHold": {
            "id": "HOLD-W1-GRR-0002",
            "status": "ACTIVE",
            "recoveryRequestId": "GRR-0002",
            "installedControlGeneration": "GCR-0002",
        },
        "triggerWitness": {
            "path": TRIGGER_PATH,
            "sha256": TRIGGER_SHA256,
            "untracked": True,
            "unstaged": True,
            "executionAuthority": False,
        },
        "adverseLedger": {
            "path": GCR3_LEDGER_PATH,
            "sha256": GCR3_LEDGER_SHA256,
            "reviewedStateCommit": GCR3_REVIEWED_STATE_COMMIT,
            "result": "changes-requested",
            "bytePreserved": True,
        },
        "predecessorState": state_binding(predecessor, predecessor_document),
        "successorState": state_binding(successor, successor_document),
        "paths": {
            "manifest": TRANSACTION_PATH,
            "lock": LOCK_PATH,
            "stateNext": STATE_NEXT_PATH,
            "state": GCR3_STATE_PATH,
            "ledger": GCR3_LEDGER_PATH,
        },
        "durability": {
            "sameFilesystem": True,
            "exclusiveCreateLock": True,
            "replaceExistingWriteThrough": True,
            "flushSuccessorBeforeManifest": True,
            "flushManifestBeforePublication": True,
            "flushPublishedState": True,
            "flushParentDirectories": True,
            "cleanupAfterValidatedPairOnly": True,
        },
        "publicationOrder": [
            "authenticate-authority-workspace-ledger-and-cas",
            "acquire-exclusive-lock",
            "write-and-flush-successor-state",
            "exclusive-create-and-flush-prepared-manifest",
            "replace-state-write-through-and-flush",
            "validate-exact-ledger-state-pair",
            "flush-parent-directories",
            "remove-and-flush-transaction-artifacts",
        ],
        "recovery": {
            "command": "python tools/gcr4ctl.py --repo . recover GCR-0004 --agent codex",
            "idempotent": True,
            "automaticPreflight": True,
            "validTerminalPairs": [
                "exact-frozen-state-plus-untracked-ledger",
                "exact-derived-state-plus-byte-identical-ledger",
            ],
            "failClosedStates": [
                "prepared",
                "partial-publication",
                "marker-missing",
                "substituted",
                "stale",
                "dirty-workspace",
                "split-ledger-state",
            ],
            "decisionRule": (
                "complete-successor-only-when-manifest-authority-ledger-and-durable-successor-validate-"
                "otherwise-restore-exact-frozen-state"
            ),
        },
        "finalization": {
            "directChildOfApplicationEvidenceCommit": True,
            "exactChangedFiles": [GCR3_LEDGER_PATH, GCR3_STATE_PATH],
            "transactionArtifactsAbsent": True,
            "controlRevisionUnchanged": 9,
            "ordinaryExecutionDenied": True,
        },
    }


def binding_matches(path: Path, expected: dict[str, Any]) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    payload = path.read_bytes()
    try:
        document = json.loads(payload)
    except UnicodeError, json.JSONDecodeError:
        return False
    return (
        expected.get("path") == GCR3_STATE_PATH
        and sha256(payload) == expected.get("rawSha256")
        and canonical_sha(document) == expected.get("canonicalSha256")
    )


def validate_successor(repo: Path, payload: bytes) -> None:
    document = json.loads(payload)
    validate_schema(
        repo,
        document,
        GCR3_SUCCESSOR_SCHEMA_PATH,
        "GCR-0003 recovered successor state",
    )
    if (
        document.get("schemaVersion") != "3.1-control-recovery-state"
        or document.get("status") != "CHANGES_REQUESTED"
        or (document.get("reviewTransitionRecovery") or {}).get("ordinaryExecutionAuthority") is not False
    ):
        raise SystemExit("GCR-0004 successor state is not the exact adverse projection")


def cleanup_transaction(repo: Path) -> None:
    for relative in (TRANSACTION_PATH, STATE_NEXT_PATH, LOCK_PATH):
        path = transaction_artifacts(repo)[relative]
        if os.path.lexists(path):
            if not path.is_file() or path.is_symlink():
                raise SystemExit(f"GCR-0004 transaction artifact is redirected: {relative}")
            unlink_durable(path)
            adoption_fault_boundary(f"gcr4-cleanup-{PurePosixPath(relative).name}")


def restore_predecessor(repo: Path, predecessor: bytes) -> None:
    next_path = transaction_artifacts(repo)[STATE_NEXT_PATH]
    if os.path.lexists(next_path):
        if not next_path.is_file() or next_path.is_symlink():
            raise SystemExit("GCR-0004 state-next artifact is redirected")
        unlink_durable(next_path)
    write_new_durable(next_path, predecessor)
    move_write_through(next_path, repo / GCR3_STATE_PATH)
    if sha256((repo / GCR3_STATE_PATH).read_bytes()) != GCR3_STATE_SHA256:
        raise SystemExit("GCR-0004 predecessor restoration failed")
    fsync_directory((repo / GCR3_STATE_PATH).parent)


def complete_transaction(repo: Path, transaction: dict[str, Any]) -> None:
    validate_transaction(repo, transaction)
    expected = transaction["successorState"]
    live = repo / GCR3_STATE_PATH
    next_path = transaction_artifacts(repo)[STATE_NEXT_PATH]
    if binding_matches(live, expected):
        payload = live.read_bytes()
    elif next_path.is_file() and not next_path.is_symlink() and sha256(next_path.read_bytes()) == expected["rawSha256"]:
        payload = next_path.read_bytes()
    else:
        raise SystemExit("GCR-0004 durable successor state is unavailable or substituted")
    validate_successor(repo, payload)
    if not binding_matches(live, expected):
        move_write_through(next_path, live)
    adoption_fault_boundary("gcr4-state-published")
    if not binding_matches(live, expected):
        raise SystemExit("GCR-0004 publication did not produce the exact successor state")
    validate_adverse_ledger(repo, require_untracked=True)
    fsync_directory(live.parent)
    adoption_fault_boundary("gcr4-state-directory-durable")
    cleanup_transaction(repo)


def recover_transaction(repo: Path) -> str:
    present = present_transaction_artifacts(repo)
    if not present:
        return "ABSENT"
    if git(repo, "branch", "--show-current") != BRANCH or git(repo, "diff", "--cached", "--name-only", "--"):
        raise SystemExit("GCR-0004 recovery requires the exact branch and an unstaged index")
    validate_trigger(repo)
    validate_adverse_ledger(repo, require_untracked=True)
    anchor, predecessor, _approved_state, _evidence_commit = load_anchor(repo)
    with transaction_lock(repo, recover=True):
        manifest = transaction_artifacts(repo)[TRANSACTION_PATH]
        if not manifest.is_file() or manifest.is_symlink():
            restore_predecessor(repo, predecessor)
            cleanup_transaction(repo)
            return "RESTORED_PREDECESSOR"
        try:
            transaction, _payload = load_json(manifest, "GCR-0004 transaction")
            validate_transaction(repo, transaction)
            if (
                transaction.get("applicationEvidenceCommit") != anchor.get("applicationEvidenceCommit")
                or transaction.get("approvedGcr4StateCommit") != anchor.get("approvedStateCommit")
                or transaction.get("predecessorState", {}).get("rawSha256") != GCR3_STATE_SHA256
                or transaction.get("successorState", {}).get("rawSha256") != anchor.get("successorStateSha256")
            ):
                raise SystemExit("GCR-0004 transaction differs from the durable recovery anchor")
            complete_transaction(repo, transaction)
        except SystemExit:
            restore_predecessor(repo, predecessor)
            cleanup_transaction(repo)
            return "RESTORED_PREDECESSOR"
    return "COMPLETED_SUCCESSOR"


def command_apply(args: argparse.Namespace) -> None:
    _approval, packet, _base = load_authority(args.repo)
    if present_transaction_artifacts(args.repo):
        recover_transaction(args.repo)
    state, state_payload = load_state(args.repo, required=True)
    assert state is not None and state_payload is not None
    validate_history(args.repo, state, packet)
    _reviewed_state, approved_state, _ledger_ref, _ledger_payload = canonical_approved_state(
        args.repo, state, state_payload
    )
    if str(args.approved_state_commit) != approved_state:
        raise SystemExit("GCR-0004 approved-state argument differs from the canonical review projection")
    if args.agent != ACTOR:
        raise SystemExit(f"GCR-0004 application actor must be {ACTOR}")
    relative = str(args.evidence)
    if relative != APPLICATION_EVIDENCE_PATH:
        raise SystemExit(f"GCR-0004 application evidence path must be {APPLICATION_EVIDENCE_PATH}")
    evidence_commit = git(args.repo, "rev-parse", "HEAD")
    require_exact_commit_delta(
        args.repo,
        parent=approved_state,
        commit=evidence_commit,
        expected={relative: "A"},
        label="GCR-0004 application-evidence commit",
    )
    require_workspace(args.repo)
    evidence, evidence_payload = load_json(args.repo / relative, "GCR-0004 application evidence")
    validate_runtime(args.repo, evidence, "GCR-0004 application evidence")
    if (
        taskctl.git_blob(args.repo, evidence_commit, relative) != evidence_payload
        or evidence.get("controlRecoveryId") != GCR_ID
        or evidence.get("bootstrapUnit") != BOOTSTRAP_ID
        or evidence.get("approvedStateCommit") != approved_state
        or evidence.get("reviewedStateCommit") != GCR3_REVIEWED_STATE_COMMIT
        or evidence.get("triggerWitness") != trigger_witness()
        or evidence.get("adverseLedger")
        != {"path": GCR3_LEDGER_PATH, "sha256": GCR3_LEDGER_SHA256, "bytePreserved": True}
        or evidence.get("predecessorStateSha256") != GCR3_STATE_SHA256
        or evidence.get("successorStatus") != "CHANGES_REQUESTED"
        or evidence.get("controlRevision") != 9
        or evidence.get("expectedChangedFiles") != [GCR3_LEDGER_PATH, GCR3_STATE_PATH]
        or evidence.get("unverifiedItems") != []
        or any(item.get("exitCode") != 0 or item.get("result") != "passed" for item in evidence.get("checks", []))
    ):
        raise SystemExit("GCR-0004 application evidence identity, paths, checks, or boundary is invalid")
    predecessor = (args.repo / GCR3_STATE_PATH).read_bytes()
    successor_document = recovered_gcr3_state(
        args.repo,
        approved_state=approved_state,
        evidence_commit=evidence_commit,
        evidence_payload=evidence_payload,
    )
    successor = (json.dumps(successor_document, indent=2, ensure_ascii=False) + "\n").encode()
    transaction = transaction_document(
        predecessor=predecessor,
        successor=successor,
        approved_state=approved_state,
        evidence_commit=evidence_commit,
    )
    validate_transaction(args.repo, transaction)
    validate_successor(args.repo, successor)
    anchor = application_anchor(
        approved_state=approved_state,
        evidence_commit=evidence_commit,
        predecessor_payload=predecessor,
        successor_payload=successor,
    )
    artifacts = transaction_artifacts(args.repo)
    with transaction_lock(args.repo, anchor=anchor):
        if (args.repo / GCR3_STATE_PATH).read_bytes() != predecessor:
            raise SystemExit("GCR-0003 frozen state changed before bridge transaction preparation")
        write_new_durable(artifacts[STATE_NEXT_PATH], successor)
        adoption_fault_boundary("gcr4-state-next-durable")
        write_new_durable(artifacts[TRANSACTION_PATH], (json.dumps(transaction, indent=2) + "\n").encode())
        adoption_fault_boundary("gcr4-transaction-published")
        complete_transaction(args.repo, transaction)
    print(
        "Prepared exact GCR-0003 R01 CHANGES_REQUESTED projection; finalization commit must add only the "
        "unchanged ledger and recovered GCR-0003 state"
    )


def validate_applied_bridge(repo: Path) -> None:
    ledger, ledger_payload = validate_adverse_ledger(repo, require_untracked=False)
    state, _state_payload = load_json(repo / GCR3_STATE_PATH, "current GCR-0003 state")
    validate_schema(repo, state, GCR3_SUCCESSOR_SCHEMA_PATH, "current GCR-0003 state")
    recovery = state.get("reviewTransitionRecovery") or {}
    evidence = recovery.get("applicationEvidence") or {}
    finalization_commit = taskctl.approval_introduction_commit(repo, GCR3_LEDGER_PATH)
    evidence_commit = str(evidence.get("commit") or "")
    if not finalization_commit:
        raise SystemExit("GCR-0004 finalization commit is absent")
    require_exact_commit_delta(
        repo,
        parent=evidence_commit,
        commit=finalization_commit,
        expected={GCR3_LEDGER_PATH: "A", GCR3_STATE_PATH: "M"},
        label="GCR-0004 bridge finalization commit",
    )
    final_state_payload = taskctl.git_blob(repo, finalization_commit, GCR3_STATE_PATH)
    if final_state_payload is None:
        raise SystemExit("GCR-0004 finalization state Git blob is absent")
    final_state = json.loads(final_state_payload)
    validate_schema(repo, final_state, GCR3_SUCCESSOR_SCHEMA_PATH, "finalized GCR-0003 bridge state")
    final_recovery = final_state.get("reviewTransitionRecovery") or {}
    if (
        final_state.get("status") != "CHANGES_REQUESTED"
        or final_state.get("currentSubmission") is not None
        or final_state.get("adoption") is not None
        or len(final_state.get("attempts") or []) != 1
        or (final_state["attempts"][0].get("findings") or []) != (ledger.get("findings") or [])
        or final_state["attempts"][0].get("closures") != []
        or final_recovery.get("controlRecoveryId") != GCR_ID
        or final_recovery.get("bootstrapUnit") != BOOTSTRAP_ID
        or final_recovery.get("reviewedStateCommit") != GCR3_REVIEWED_STATE_COMMIT
        or final_recovery.get("ordinaryExecutionAuthority") is not False
        or evidence.get("path") != APPLICATION_EVIDENCE_PATH
        or recovery != final_recovery
        or not (state.get("attempts") or [])
        or state["attempts"][0] != final_state["attempts"][0]
        or taskctl.git_blob(repo, finalization_commit, GCR3_LEDGER_PATH) != ledger_payload
    ):
        raise SystemExit("GCR-0004 applied bridge state, ledger, or authority is invalid")


def command_recover(args: argparse.Namespace) -> None:
    load_authority(args.repo)
    if args.agent != ACTOR:
        raise SystemExit(f"GCR-0004 recovery actor must be {ACTOR}")
    print(f"GCR-0004 application recovery: {recover_transaction(args.repo)}; ordinary execution remains denied")


def command_validate(args: argparse.Namespace) -> None:
    _approval, packet, _base = load_authority(args.repo)
    present = present_transaction_artifacts(args.repo)
    if present:
        raise SystemExit(f"GCR-0004 application transaction requires explicit recovery: {present}")
    state, state_payload = load_state(args.repo, required=False)
    status = "AUTHORIZED"
    if state is not None:
        assert state_payload is not None
        validate_history(args.repo, state, packet)
        status = str(state.get("status"))
    ledger_tracked = GCR3_LEDGER_PATH in set(git(args.repo, "ls-files", "--", GCR3_LEDGER_PATH).splitlines())
    if ledger_tracked:
        validate_applied_bridge(args.repo)
        status = "APPLIED"
    else:
        validate_adverse_ledger(args.repo, require_untracked=True)
        if sha256((args.repo / GCR3_STATE_PATH).read_bytes()) != GCR3_STATE_SHA256:
            raise SystemExit("GCR-0003 frozen state changed before bridge application")
    backlog = yaml.safe_load((args.repo / BACKLOG_PATH).read_bytes())
    if (backlog.get("control_plane") or {}).get("revision") != 9:
        raise SystemExit("GCR-0004 bridge must not change the control revision")
    if args.require_approved and status not in {"APPROVED", "APPLIED"}:
        raise SystemExit(f"{BOOTSTRAP_ID} is not independently approved")
    print(f"Valid {GCR_ID}: bootstrap={status}; control=9")


def command_status(args: argparse.Namespace) -> None:
    _approval, _packet, base = load_authority(args.repo)
    state, _payload = load_state(args.repo, required=False)
    ledger_tracked = GCR3_LEDGER_PATH in set(git(args.repo, "ls-files", "--", GCR3_LEDGER_PATH).splitlines())
    print(
        yaml.safe_dump(
            {
                "controlRecovery": GCR_ID,
                "bootstrap": BOOTSTRAP_ID,
                "approvalBase": base,
                "status": "APPLIED" if ledger_tracked else ((state or {}).get("status") or "AUTHORIZED"),
                "gcr3ReviewedState": GCR3_REVIEWED_STATE_COMMIT,
                "gcr3AdverseLedger": GCR3_LEDGER_PATH,
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
        raise SystemExit("GCR-0004 submit requires the exact approval-introduction commit")
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
