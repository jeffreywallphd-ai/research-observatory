#!/usr/bin/env python3
"""Exact, one-time GCR-0002 controller-generation bootstrap.

This controller recognizes only GCR-0002.B00. It cannot create or approve a
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

GCR_ID = "GCR-0002"
BOOTSTRAP_ID = "GCR-0002.B00"
BRANCH = "codex/w1-windows-local-runtime"
ACTOR = "codex"
PACKET_COMMIT = "26003f7671e164327e8b1b6066bc82fbe8afed67"
PACKET_SHA256 = "590f5c3888cb9b65b8a7c2ac3f856f7d7a63e6804daf24b59ebc8a8d78155e5c"
PACKET_PATH = "planning/governance-control-recovery/GCR-0002.packet.json"
APPROVAL_PATH = "planning/governance-control-recovery/GCR-0002.approval.json"
RUNTIME_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-runtime.v2.schema.json"
TRANSACTION_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-transaction.v2.schema.json"
STATE_PATH = "planning/governance-control-recovery/GCR-0002.B00.state.json"
TRANSACTION_PATH = "planning/governance-control-recovery/GCR-0002.B00.adoption-transaction.json"
LOCK_PATH = "planning/governance-control-recovery/GCR-0002.B00.adoption.lock"
BACKLOG_NEXT_PATH = "planning/governance-control-recovery/GCR-0002.B00.adoption-backlog.next"
STATE_NEXT_PATH = "planning/governance-control-recovery/GCR-0002.B00.adoption-state.next"
BACKLOG_PATH = "planning/backlog.yaml"
TRIGGER_PATH = "artifacts/evidence/W1.A04.B00.json"
TRIGGER_SHA256 = "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c"
BACKLOG_SHA256 = "0b3d22f30d3a024e37b6c7b9b07d48f3a0b96dd2fc6c1968809a21d35a2977e7"
ADOPTION_EVIDENCE_PATH = "artifacts/evidence/governance-control-recovery/GCR-0002.B00.adoption.json"
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
    validate_schema(repo, document, TRANSACTION_SCHEMA_PATH, "GCR-0002 adoption transaction")


def validate_trigger(repo: Path) -> None:
    path = safe_path(repo, TRIGGER_PATH, label="GCR-0002 trigger witness", prefix="artifacts/evidence")
    if path.is_symlink() or getattr(os.path, "isjunction", lambda _value: False)(path):
        raise SystemExit("GCR-0002 trigger witness must not be redirected")
    if sha256(path.read_bytes()) != TRIGGER_SHA256:
        raise SystemExit("GCR-0002 trigger witness is missing or has changed")
    if TRIGGER_PATH in set(git(repo, "ls-files", "--", TRIGGER_PATH).splitlines()):
        raise SystemExit("GCR-0002 trigger witness must remain untracked")
    if TRIGGER_PATH in set(git(repo, "diff", "--cached", "--name-only", "--").splitlines()):
        raise SystemExit("GCR-0002 trigger witness must remain unstaged")


def require_workspace(repo: Path, *, extra_untracked: set[str] | None = None) -> None:
    if git(repo, "branch", "--show-current") != BRANCH:
        raise SystemExit(f"GCR-0002 transitions require exact branch {BRANCH}")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=repo, check=False).returncode != 0:
        raise SystemExit("Tracked worktree changes exist; GCR-0002 transitions require an exact commit")
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise SystemExit("Staged changes exist; GCR-0002 transitions require an exact commit")
    validate_trigger(repo)
    allowed = {TRIGGER_PATH, *(extra_untracked or set())}
    untracked = set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    if untracked != allowed:
        difference = sorted(untracked ^ allowed)
        raise SystemExit(f"GCR-0002 untracked-path boundary differs: {difference[0] if difference else '<unknown>'}")


def require_recovery_workspace(repo: Path) -> None:
    if git(repo, "branch", "--show-current") != BRANCH:
        raise SystemExit(f"GCR-0002 recovery requires exact branch {BRANCH}")
    validate_trigger(repo)
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise SystemExit("GCR-0002 recovery refuses staged changes")
    tracked = set(git(repo, "diff", "--name-only", "HEAD", "--").splitlines())
    if not tracked.issubset({BACKLOG_PATH, STATE_PATH}):
        raise SystemExit(f"GCR-0002 recovery tracked-path boundary differs: {sorted(tracked)[0]}")
    allowed = {TRIGGER_PATH, *transaction_artifacts(repo)}
    untracked = set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    if not untracked.issubset(allowed) or TRIGGER_PATH not in untracked:
        difference = sorted(untracked ^ (untracked & allowed))
        raise SystemExit(
            f"GCR-0002 recovery untracked-path boundary differs: {difference[0] if difference else '<unknown>'}"
        )


def load_authority(repo: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    packet, packet_payload = load_json(safe_path(repo, PACKET_PATH, label="GCR-0002 packet"), "GCR-0002 packet")
    approval, approval_payload = load_json(
        safe_path(repo, APPROVAL_PATH, label="GCR-0002 approval"), "GCR-0002 approval"
    )
    if sha256(packet_payload) != PACKET_SHA256 or taskctl.git_blob(repo, PACKET_COMMIT, PACKET_PATH) != packet_payload:
        raise SystemExit("GCR-0002 packet differs from its approved immutable Git blob")
    validate_runtime(repo, approval, "GCR-0002 approval")
    introduction = taskctl.approval_introduction_commit(repo, APPROVAL_PATH)
    if not introduction or taskctl.git_blob(repo, introduction, APPROVAL_PATH) != approval_payload:
        raise SystemExit("GCR-0002 approval is absent, replaced, or edited after introduction")
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
        raise SystemExit("GCR-0002 approval identity, packet, witness, or scope is invalid")
    review_relative = str(review_reference.get("path") or "")
    review_path = safe_path(
        repo, review_relative, label="GCR-0002 packet review", prefix="planning/governance-control-recovery"
    )
    review_payload = review_path.read_bytes()
    review_commit = str(review_reference.get("commit") or "")
    if (
        sha256(review_payload) != review_reference.get("sha256")
        or not taskctl.git_commit_exists(repo, review_commit)
        or not taskctl.git_is_ancestor(repo, review_commit)
        or taskctl.git_blob(repo, review_commit, review_relative) != review_payload
    ):
        raise SystemExit("GCR-0002 packet review binding is invalid")
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
        or [item.get("id") for item in supplements] != ["GRR-0002.S01"]
        or ((supplements[-1].get("bootstrap") or {}).get("status") if supplements else None) != "APPROVED"
        or (wave.get("campaign") or {}).get("status") != "PAUSED"
        or (wave.get("campaign") or {}).get("scope") != "wave"
        or task.get("status") != "BLOCKED"
        or task.get("recovery_control") is not None
        or "W1.A04" in taskctl.wave_amendment_map(data)
        or gate.get("status") != "PENDING"
    ):
        raise SystemExit("GCR-0002 stopped boundary differs from the exact approved packet")
    if revision == 8:
        if sha256(payload) != BACKLOG_SHA256 or (packet.get("activationBoundary") or {}).get("controlRevision") != 8:
            raise SystemExit("GCR-0002 revision-8 boundary differs from its approved trigger")
    elif revision == 9:
        generations = control.get("control_generations") or []
        if [item.get("id") for item in generations] != ["GCR-0001", "GCR-0002"]:
            raise SystemExit("GCR-0002 successor generation ledger is invalid")
    else:
        raise SystemExit("GCR-0002 recognizes only control revisions 8 and 9")
    return payload, data


def load_state(repo: Path, *, required: bool) -> tuple[dict[str, Any] | None, bytes | None]:
    path = repo / STATE_PATH
    if not path.is_file():
        if required:
            raise SystemExit("Canonical GCR-0002 state does not exist")
        return None, None
    state, payload = load_json(path, "GCR-0002 state")
    validate_runtime(repo, state, "GCR-0002 state")
    if (
        state.get("controlRecoveryId") != GCR_ID
        or state.get("bootstrapUnit") != BOOTSTRAP_ID
        or state.get("triggerWitness") != trigger_witness()
    ):
        raise SystemExit("GCR-0002 state identity or trigger witness is invalid")
    return state, payload


def evidence_path(attempt_id: str) -> str:
    return f"artifacts/evidence/governance-control-recovery/{BOOTSTRAP_ID}.{attempt_id}.json"


def review_path(attempt_id: str) -> str:
    return f"planning/governance-control-recovery/{BOOTSTRAP_ID}.review-{attempt_id}.json"


def changed_paths(repo: Path, base: str, candidate: str) -> list[str]:
    if not taskctl.git_commit_exists(repo, base) or not taskctl.git_commit_exists(repo, candidate):
        raise SystemExit("GCR-0002 base or candidate commit is absent")
    if base == candidate or not taskctl.git_is_ancestor(repo, base, candidate):
        raise SystemExit("GCR-0002 candidate must strictly descend from its required base")
    return sorted(filter(None, git(repo, "diff", "--name-only", f"{base}..{candidate}", "--").splitlines()))


def open_findings(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    opened: dict[str, dict[str, Any]] = {}
    for attempt in state.get("attempts", []):
        for closure in attempt.get("closures", []):
            opened.pop(str(closure.get("findingId") or ""), None)
        for finding in attempt.get("findings", []):
            opened[str(finding.get("id") or "")] = finding
    return opened


def validate_evidence(
    repo: Path,
    packet: dict[str, Any],
    relative: str,
    candidate: str,
    base: str,
    attempt_id: str,
    prior_open: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], bytes]:
    if relative != evidence_path(attempt_id):
        raise SystemExit(f"GCR-0002 evidence path must be {evidence_path(attempt_id)}")
    document, payload = load_json(
        safe_path(repo, relative, label="GCR-0002 evidence", prefix="artifacts/evidence/governance-control-recovery"),
        "GCR-0002 evidence",
    )
    validate_runtime(repo, document, "GCR-0002 evidence")
    actual = changed_paths(repo, base, candidate)
    patterns = [str(item) for item in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", [])]
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
        or sorted(document.get("changedFiles") or []) != actual
        or any(not path_authorized(item, patterns) for item in actual)
        or [item.get("index") for item in criteria] != list(range(1, len(expected_criteria) + 1))
        or [item.get("statement") for item in criteria] != expected_criteria
        or document.get("unverifiedItems") != []
        or len(closure_ids) != len(set(closure_ids))
        or set(closure_ids) != set(prior_open)
    ):
        raise SystemExit("GCR-0002 evidence identity, scope, criteria, closures, or verification is invalid")
    checks = document.get("checks") or []
    if (
        not checks
        or len({item.get("id") for item in checks}) != len(checks)
        or any(item.get("exitCode") != 0 or item.get("result") != "passed" for item in checks)
    ):
        raise SystemExit("GCR-0002 evidence checks must be unique and passing")
    selection = document.get("verificationSelection") or {}
    if set(selection.get("selectedChecks") or []) != {item.get("id") for item in checks}:
        raise SystemExit("GCR-0002 verification selection differs from the passing checks")
    for closure in closures:
        if (
            str(closure.get("findingId") or "") not in prior_open
            or closure.get("disposition") not in {"fixed", "not-reproduced", "superseded", "accepted-risk"}
            or not str(closure.get("evidence") or "").strip()
        ):
            raise SystemExit("GCR-0002 finding closure is stale or incomplete")
    return document, payload


def freeze_submission(args: argparse.Namespace, *, remediation: bool) -> None:
    _approval, packet, approval_base = load_authority(args.repo)
    if present_transaction_artifacts(args.repo):
        recover_transaction(args.repo)
    state, _payload = load_state(args.repo, required=False)
    if remediation:
        if state is None or state.get("status") not in {"CHANGES_REQUESTED", "BLOCKED"}:
            raise SystemExit("GCR-0002 resubmission requires an adverse prior review")
    elif state is not None:
        raise SystemExit("GCR-0002 initial submission already exists")
    attempts = (state or {}).get("attempts", [])
    attempt_id = f"R{len(attempts) + 1:02d}"
    relative = str(args.evidence)
    require_workspace(args.repo, extra_untracked={relative})
    candidate = str(args.implementation_commit)
    if candidate != git(args.repo, "rev-parse", "HEAD"):
        raise SystemExit("GCR-0002 candidate must equal current HEAD")
    if str(args.agent).strip() != ACTOR or args.agent != ACTOR:
        raise SystemExit(f"GCR-0002 implementer must be exact actor {ACTOR}")
    if not remediation and str(args.approval_commit) != approval_base:
        raise SystemExit("GCR-0002 approval commit differs from the immutable approval introduction")
    prior_candidate = str(
        (((state or {}).get("attempts") or [{}])[-1].get("submission") or {}).get("candidateCommit") or ""
    )
    if remediation and (
        not prior_candidate
        or not taskctl.git_is_ancestor(args.repo, prior_candidate, candidate)
        or prior_candidate == candidate
    ):
        raise SystemExit("GCR-0002 remediation candidate must strictly descend from the prior candidate")
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
        "rootCauseAnalysis": None,
    }
    if state is None:
        state = {
            "schemaVersion": "2.0-control-recovery-state",
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
    validate_runtime(args.repo, state, "GCR-0002 submission state")
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
    validate_runtime(repo, ledger, "GCR-0002 review ledger")
    submission = state.get("currentSubmission") or {}
    findings = ledger.get("findings") or []
    closures = ledger.get("closures") or []
    ordering = [SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings]
    finding_ids = [str(item.get("id") or "") for item in findings]
    prior_open = open_findings(state)
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
        or set(closure_ids) - set(prior_open)
    ):
        raise SystemExit("GCR-0002 review ledger differs from the frozen submission or review controls")
    result = str(ledger.get("result") or "")
    if result not in RESULT_STATUS:
        raise SystemExit("GCR-0002 review result is invalid")
    if result == "approved" and (
        findings or any(item.get("blocking") for item in prior_open.values() if str(item.get("id")) not in closure_ids)
    ):
        raise SystemExit("GCR-0002 approval cannot introduce findings or retain an open blocker")


def command_review(args: argparse.Namespace) -> None:
    _approval, _packet, _base = load_authority(args.repo)
    if present_transaction_artifacts(args.repo):
        recover_transaction(args.repo)
    state, _payload = load_state(args.repo, required=True)
    assert state is not None
    if state.get("status") != "REVIEW" or not state.get("currentSubmission"):
        raise SystemExit("GCR-0002 has no frozen submission eligible for review")
    relative = str(args.ledger)
    require_workspace(args.repo, extra_untracked={relative})
    reviewer = str(args.reviewer).strip()
    if not reviewer or reviewer != args.reviewer or reviewer == ACTOR:
        raise SystemExit("GCR-0002 reviewer must be normalized and independent")
    reviewed_state = git(args.repo, "rev-parse", "HEAD")
    ledger, ledger_payload = load_json(
        safe_path(
            repo=args.repo, relative=relative, label="GCR-0002 review", prefix="planning/governance-control-recovery"
        ),
        "GCR-0002 review",
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
    validate_runtime(args.repo, state, "GCR-0002 reviewed state")
    write_json_atomic(args.repo / STATE_PATH, state)
    print(f"Recorded {BOOTSTRAP_ID}/{submission['attemptId']} as {state['status']}")


def validate_history(repo: Path, state: dict[str, Any], packet: dict[str, Any]) -> None:
    attempts = state.get("attempts") or []
    if [((item.get("submission") or {}).get("attemptId")) for item in attempts] != [
        f"R{index:02d}" for index in range(1, len(attempts) + 1)
    ]:
        raise SystemExit("GCR-0002 attempt history is not append-only and sequential")
    prior_candidate: str | None = None
    for index, attempt in enumerate(attempts):
        submission = attempt.get("submission") or {}
        attempt_id = str(submission.get("attemptId") or "")
        candidate = str(submission.get("candidateCommit") or "")
        evidence = submission.get("evidence") or {}
        ledger = attempt.get("ledger") or {}
        review = attempt.get("review") or {}
        reviewed_state = str(review.get("reviewedStateCommit") or "")
        if (
            submission.get("baseCommit") != (state.get("approval") or {}).get("commit")
            or submission.get("branch") != BRANCH
        ):
            raise SystemExit(f"GCR-0002 {attempt_id} submission base or branch is invalid")
        if prior_candidate and (
            prior_candidate == candidate or not taskctl.git_is_ancestor(repo, prior_candidate, candidate)
        ):
            raise SystemExit(f"GCR-0002 {attempt_id} candidate is not a strict remediation descendant")
        prior_candidate = candidate
        expected_delta = {str(evidence.get("path")): "A", STATE_PATH: "A" if index == 0 else "M"}
        require_exact_commit_delta(
            repo,
            parent=candidate,
            commit=reviewed_state,
            expected=expected_delta,
            label=f"GCR-0002 {attempt_id} reviewed-state commit",
        )
        evidence_payload = taskctl.git_blob(repo, reviewed_state, str(evidence.get("path") or ""))
        if evidence_payload is None or sha256(evidence_payload) != evidence.get("sha256"):
            raise SystemExit(f"GCR-0002 {attempt_id} evidence Git binding is invalid")
        ledger_relative = str(ledger.get("path") or "")
        approval_projection = taskctl.approval_introduction_commit(repo, ledger_relative)
        if not approval_projection:
            raise SystemExit(f"GCR-0002 {attempt_id} review projection commit is absent")
        require_exact_commit_delta(
            repo,
            parent=reviewed_state,
            commit=approval_projection,
            expected={ledger_relative: "A", STATE_PATH: "M"},
            label=f"GCR-0002 {attempt_id} review projection",
        )
        ledger_payload = taskctl.git_blob(repo, approval_projection, ledger_relative)
        if ledger_payload is None or sha256(ledger_payload) != ledger.get("sha256"):
            raise SystemExit(f"GCR-0002 {attempt_id} review ledger Git binding is invalid")
    expected_status = RESULT_STATUS[str((attempts[-1].get("review") or {}).get("result"))] if attempts else "REVIEW"
    if attempts and state.get("status") not in {expected_status, "ADOPTION_FINALIZATION"}:
        raise SystemExit("GCR-0002 state status differs from the latest immutable review")
    if state.get("status") == "REVIEW" and state.get("currentSubmission") is None:
        raise SystemExit("GCR-0002 REVIEW state lacks its frozen submission")


def transaction_artifacts(repo: Path) -> dict[str, Path]:
    return {
        relative: _artifact_path(repo, relative)
        for relative in (LOCK_PATH, TRANSACTION_PATH, BACKLOG_NEXT_PATH, STATE_NEXT_PATH)
    }


def present_transaction_artifacts(repo: Path) -> list[str]:
    return [relative for relative, path in transaction_artifacts(repo).items() if os.path.lexists(path)]


@contextmanager
def transaction_lock(repo: Path, *, anchor: dict[str, Any] | None = None, recover: bool = False) -> Iterator[None]:
    path = transaction_artifacts(repo)[LOCK_PATH]
    if os.path.lexists(path):
        if not recover or not path.is_file() or path.is_symlink():
            raise SystemExit("GCR-0002 adoption lock already exists or is redirected")
        yield
        return
    if recover or anchor is None:
        raise SystemExit("GCR-0002 adoption requires an exact recovery anchor")
    validate_recovery_anchor(repo, anchor)
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
        "schemaVersion": "2.0-control-recovery-adoption-anchor",
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
        raise SystemExit(f"GCR-0002 recovery anchor {label} payload is absent")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeError, ValueError) as exc:
        raise SystemExit(f"GCR-0002 recovery anchor {label} payload is invalid") from exc


def validate_recovery_anchor(repo: Path, anchor: dict[str, Any]) -> tuple[bytes, bytes]:
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
        or anchor.get("schemaVersion") != "2.0-control-recovery-adoption-anchor"
        or anchor.get("documentType") != "governance-control-recovery-adoption-anchor"
        or anchor.get("transactionId") != f"{BOOTSTRAP_ID}.ADOPT"
        or anchor.get("controlRecoveryId") != GCR_ID
        or anchor.get("bootstrapUnit") != BOOTSTRAP_ID
        or anchor.get("actor") != ACTOR
        or anchor.get("branch") != BRANCH
        or git(repo, "rev-parse", "HEAD") != evidence_commit
    ):
        raise SystemExit("GCR-0002 recovery anchor identity or HEAD binding is invalid")
    parents = git(repo, "rev-list", "--parents", "-n", "1", evidence_commit).split()
    if parents != [evidence_commit, approved_state]:
        raise SystemExit("GCR-0002 recovery anchor is not based on the exact approved-state parent")
    require_exact_commit_delta(
        repo,
        parent=approved_state,
        commit=evidence_commit,
        expected={ADOPTION_EVIDENCE_PATH: "A"},
        label="GCR-0002 recovery-anchor adoption-evidence commit",
    )
    evidence_payload = taskctl.git_blob(repo, evidence_commit, ADOPTION_EVIDENCE_PATH)
    if evidence_payload is None:
        raise SystemExit("GCR-0002 recovery anchor adoption evidence is unavailable")
    try:
        evidence = json.loads(evidence_payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("GCR-0002 recovery anchor adoption evidence is malformed") from exc
    validate_runtime(repo, evidence, "GCR-0002 recovery anchor adoption evidence")
    if (
        evidence.get("controlRecoveryId") != GCR_ID
        or evidence.get("bootstrapUnit") != BOOTSTRAP_ID
        or evidence.get("reviewedStateCommit") != approved_state
        or evidence.get("triggerWitness") != trigger_witness()
        or evidence.get("predecessorRevision") != 8
        or evidence.get("successorRevision") != 9
        or evidence.get("expectedChangedFiles") != [BACKLOG_PATH, STATE_PATH]
        or evidence.get("unverifiedItems") != []
    ):
        raise SystemExit("GCR-0002 recovery anchor adoption evidence binding is invalid")
    payloads = anchor.get("predecessorPayloads")
    predecessor = anchor.get("predecessor")
    if not isinstance(payloads, dict) or set(payloads) != {"backlogBase64", "stateBase64"}:
        raise SystemExit("GCR-0002 recovery anchor payload map is invalid")
    if not isinstance(predecessor, dict) or set(predecessor) != {
        "controlRevision",
        "minimumToolRevision",
        "backlog",
        "state",
    }:
        raise SystemExit("GCR-0002 recovery anchor predecessor map is invalid")
    backlog_payload = _decode_anchor_payload(payloads.get("backlogBase64"), "backlog")
    state_payload = _decode_anchor_payload(payloads.get("stateBase64"), "state")
    try:
        backlog = yaml.safe_load(backlog_payload)
        state = json.loads(state_payload)
        committed_backlog = yaml.safe_load(taskctl.git_blob(repo, approved_state, BACKLOG_PATH) or b"")
    except (UnicodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise SystemExit("GCR-0002 recovery anchor predecessor payload is malformed") from exc
    committed_state = taskctl.git_blob(repo, approved_state, STATE_PATH)
    if (
        not isinstance(backlog, dict)
        or not isinstance(state, dict)
        or not isinstance(committed_backlog, dict)
        or sha256(backlog_payload) != BACKLOG_SHA256
        or predecessor.get("controlRevision") != 8
        or predecessor.get("minimumToolRevision") != 8
        or predecessor.get("backlog") != binding(BACKLOG_PATH, backlog_payload, backlog)
        or predecessor.get("state") != binding(STATE_PATH, state_payload, state)
        or canonical_sha(backlog) != canonical_sha(committed_backlog)
        or committed_state != state_payload
        or (backlog.get("control_plane") or {}).get("revision") != 8
        or (backlog.get("control_plane") or {}).get("minimum_tool_revision") != 8
        or state.get("status") != "APPROVED"
    ):
        raise SystemExit("GCR-0002 recovery anchor predecessor authority or raw bytes are invalid")
    validate_runtime(repo, state, "GCR-0002 recovery anchor predecessor state")
    return backlog_payload, state_payload


def load_recovery_anchor(repo: Path) -> tuple[dict[str, Any], bytes, bytes]:
    path = transaction_artifacts(repo)[LOCK_PATH]
    if not path.is_file() or path.is_symlink():
        raise SystemExit("GCR-0002 recovery anchor is absent or redirected")
    anchor, _payload = load_json(path, "GCR-0002 recovery anchor")
    backlog, state = validate_recovery_anchor(repo, anchor)
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
        "schemaVersion": "2.0-control-recovery-adoption-transaction",
        "documentType": "governance-control-recovery-adoption-transaction",
        "transactionId": f"{BOOTSTRAP_ID}.ADOPT",
        "controlRecoveryId": GCR_ID,
        "bootstrapUnit": BOOTSTRAP_ID,
        "status": "PREPARED",
        "createdBy": ACTOR,
        "createdAt": taskctl.utc_now(),
        "branch": BRANCH,
        "adoptionEvidenceCommit": evidence_commit,
        "reviewedStateCommit": reviewed_state,
        "activeHold": {
            "id": "HOLD-W1-GRR-0002",
            "status": "ACTIVE",
            "recoveryRequestId": "GRR-0002",
            "latestApprovedSupplement": "GRR-0002.S01",
        },
        "triggerWitness": {
            "path": TRIGGER_PATH,
            "sha256": TRIGGER_SHA256,
            "untracked": True,
            "unstaged": True,
            "executionAuthority": False,
        },
        "predecessor": {
            "controlRevision": 8,
            "minimumToolRevision": 8,
            "backlog": binding(BACKLOG_PATH, predecessor_backlog, predecessor_backlog_doc),
            "state": binding(STATE_PATH, predecessor_state, predecessor_state_doc),
        },
        "successor": {
            "controlRevision": 9,
            "minimumToolRevision": 9,
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
            "command": "python tools/gcr2ctl.py --repo . recover GCR-0002 --agent codex",
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
        raise SystemExit(f"GCR-0002 successor pair is malformed: {exc}") from exc
    schema_errors = taskctl.backlog_schema_errors(backlog)
    semantic_errors = taskctl.validate(*taskctl.index_backlog(backlog), repo=None)
    validate_runtime(repo, state, "GCR-0002 successor state")
    if (
        schema_errors
        or semantic_errors
        or backlog.get("control_plane", {}).get("revision") != 9
        or state.get("status") != "ADOPTION_FINALIZATION"
    ):
        raise SystemExit("GCR-0002 successor pair is not an exact valid revision-9 adoption")


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
                raise SystemExit(f"GCR-0002 restore artifact is redirected: {relative}")
            unlink_durable(staged)
        write_new_durable(staged, payload)
        move_write_through(staged, live)
    if not bindings_match(repo, anchor["predecessor"]):
        raise SystemExit("GCR-0002 predecessor restoration did not produce the exact pair")
    fsync_directory((repo / BACKLOG_PATH).parent)
    fsync_directory((repo / STATE_PATH).parent)


def cleanup_transaction(repo: Path) -> None:
    artifacts = transaction_artifacts(repo)
    for relative in (TRANSACTION_PATH, BACKLOG_NEXT_PATH, STATE_NEXT_PATH, LOCK_PATH):
        path = artifacts[relative]
        if os.path.lexists(path):
            if not path.is_file() or path.is_symlink():
                raise SystemExit(f"GCR-0002 transaction artifact is redirected: {relative}")
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
            raise SystemExit(f"GCR-0002 durable successor is unavailable or substituted: {label}")
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
        raise SystemExit("GCR-0002 publication did not produce the exact successor pair")
    fsync_directory((repo / BACKLOG_PATH).parent)
    fsync_directory((repo / STATE_PATH).parent)
    adoption_fault_boundary("successor-directories-durable")
    cleanup_transaction(repo)


def recover_transaction(repo: Path) -> str:
    present = present_transaction_artifacts(repo)
    if not present:
        return "ABSENT"
    require_recovery_workspace(repo)
    with taskctl.exclusive_backlog_lock(repo / BACKLOG_PATH):
        if not present_transaction_artifacts(repo):
            return "ABSENT"
        anchor, predecessor_backlog, predecessor_state = load_recovery_anchor(repo)
        with transaction_lock(repo, recover=True):
            manifest = transaction_artifacts(repo)[TRANSACTION_PATH]
            if not manifest.is_file() or manifest.is_symlink():
                restore_predecessor(repo, anchor, predecessor_backlog, predecessor_state)
                cleanup_transaction(repo)
                return "RESTORED_PREDECESSOR"
            try:
                transaction, _payload = load_json(manifest, "GCR-0002 transaction")
                validate_transaction(repo, transaction)
                if (
                    transaction.get("adoptionEvidenceCommit") != anchor.get("adoptionEvidenceCommit")
                    or transaction.get("reviewedStateCommit") != anchor.get("approvedStateCommit")
                    or transaction.get("predecessor") != anchor.get("predecessor")
                ):
                    raise SystemExit("GCR-0002 transaction differs from the durable recovery anchor")
                complete_transaction(repo, transaction)
            except SystemExit:
                restore_predecessor(repo, anchor, predecessor_backlog, predecessor_state)
                cleanup_transaction(repo)
                return "RESTORED_PREDECESSOR"
    return "COMPLETED_SUCCESSOR"


def canonical_approved_state(
    repo: Path, state: dict[str, Any], state_payload: bytes
) -> tuple[str, str, dict[str, Any], bytes]:
    if state.get("status") != "APPROVED" or not state.get("attempts"):
        raise SystemExit("GCR-0002 adoption requires an independently APPROVED latest review")
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
        raise SystemExit("GCR-0002 canonical approved-state commit cannot be derived")
    ledger_payload = (repo / ledger_relative).read_bytes()
    if taskctl.git_blob(repo, approved_state, ledger_relative) != ledger_payload:
        raise SystemExit("GCR-0002 approved-state commit lacks the exact ledger")
    require_exact_commit_delta(
        repo,
        parent=reviewed_state,
        commit=approved_state,
        expected={ledger_relative: "A", STATE_PATH: "M"},
        label="GCR-0002 approved-state commit",
    )
    return reviewed_state, approved_state, ledger, ledger_payload


def command_adopt(args: argparse.Namespace) -> None:
    _approval, packet, approval_base = load_authority(args.repo)
    if present_transaction_artifacts(args.repo):
        recover_transaction(args.repo)
    state, state_payload = load_state(args.repo, required=True)
    assert state is not None and state_payload is not None
    validate_history(args.repo, state, packet)
    reviewed_state, approved_state, ledger, ledger_payload = canonical_approved_state(args.repo, state, state_payload)
    if str(args.approved_state_commit) != approved_state:
        raise SystemExit("GCR-0002 approved-state argument differs from the canonical review projection")
    evidence_relative = str(args.evidence)
    canonical_evidence = ADOPTION_EVIDENCE_PATH
    if evidence_relative != canonical_evidence:
        raise SystemExit(f"GCR-0002 adoption evidence path must be {canonical_evidence}")
    evidence_commit = git(args.repo, "rev-parse", "HEAD")
    require_exact_commit_delta(
        args.repo,
        parent=approved_state,
        commit=evidence_commit,
        expected={evidence_relative: "A"},
        label="GCR-0002 adoption-evidence commit",
    )
    require_workspace(args.repo)
    evidence, evidence_payload = load_json(args.repo / evidence_relative, "GCR-0002 adoption evidence")
    validate_runtime(args.repo, evidence, "GCR-0002 adoption evidence")
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
        raise SystemExit("GCR-0002 adoption evidence identity, paths, checks, or binding is invalid")
    backlog_payload, data = current_boundary(args.repo, packet, revision=8)
    now = taskctl.utc_now()
    generation = {
        "id": GCR_ID,
        "bootstrap_id": BOOTSTRAP_ID,
        "hold_id": "HOLD-W1-GRR-0002",
        "predecessor_revision": 8,
        "successor_revision": 9,
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
        raise SystemExit(f"GCR-0002 adopter must be exact actor {ACTOR}")
    candidate = copy.deepcopy(taskctl.serializable_backlog(data))
    control = candidate["control_plane"]
    if [item.get("id") for item in control.get("control_generations", [])] != ["GCR-0001"]:
        raise SystemExit("GCR-0002 predecessor generation ledger is not exact")
    control["revision"] = 9
    control["minimum_tool_revision"] = 9
    control["control_generations"].append(generation)
    schema_errors = taskctl.backlog_schema_errors(candidate)
    semantic_errors = taskctl.validate(*taskctl.index_backlog(candidate), repo=None)
    if schema_errors or semantic_errors:
        raise SystemExit(
            "GCR-0002 adoption candidate is invalid:\n- " + "\n- ".join([*schema_errors, *semantic_errors])
        )
    state["status"] = "ADOPTION_FINALIZATION"
    state["adoption"] = {
        "adoptedBy": ACTOR,
        "adoptedAt": now,
        "predecessorRevision": 8,
        "successorRevision": 9,
        "reviewedStateCommit": approved_state,
        "evidence": {"path": evidence_relative, "sha256": sha256(evidence_payload), "commit": evidence_commit},
    }
    validate_runtime(args.repo, state, "GCR-0002 adopted state")
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
    validate_recovery_anchor(args.repo, anchor)
    artifacts = transaction_artifacts(args.repo)
    with taskctl.exclusive_backlog_lock(args.repo / BACKLOG_PATH), transaction_lock(args.repo, anchor=anchor):
        if (args.repo / BACKLOG_PATH).read_bytes() != backlog_payload or (
            args.repo / STATE_PATH
        ).read_bytes() != state_payload:
            raise SystemExit("GCR-0002 adoption state changed before transaction preparation")
        write_new_durable(artifacts[BACKLOG_NEXT_PATH], successor_backlog)
        adoption_fault_boundary("backlog-next-durable")
        write_new_durable(artifacts[STATE_NEXT_PATH], successor_state)
        adoption_fault_boundary("state-next-durable")
        write_new_durable(artifacts[TRANSACTION_PATH], (json.dumps(transaction, indent=2) + "\n").encode())
        adoption_fault_boundary("transaction-published")
        complete_transaction(args.repo, transaction)
    print(
        "Prepared GCR-0002 revision 8-to-9 successor; exact two-path finalization commit is required "
        "before GRR-0002.S02"
    )


def command_recover(args: argparse.Namespace) -> None:
    load_authority(args.repo)
    if str(args.agent).strip() != ACTOR or args.agent != ACTOR:
        raise SystemExit(f"GCR-0002 recovery actor must be {ACTOR}")
    print(f"GCR-0002 adoption recovery: {recover_transaction(args.repo)}; ordinary execution remains unauthorized")


def command_validate(args: argparse.Namespace) -> None:
    _approval, packet, _base = load_authority(args.repo)
    present = present_transaction_artifacts(args.repo)
    if present:
        raise SystemExit(f"GCR-0002 adoption transaction requires explicit recovery: {present}")
    backlog = yaml.safe_load((args.repo / BACKLOG_PATH).read_bytes())
    revision = int((backlog.get("control_plane") or {}).get("revision") or 0)
    _payload, data = current_boundary(args.repo, packet, revision=revision)
    errors = taskctl.validate(*taskctl.index_backlog(data), repo=args.repo)
    if errors:
        raise SystemExit("GCR-0002 control semantics are invalid:\n- " + "\n- ".join(errors))
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
        raise SystemExit(f"gcr2ctl recognizes only {GCR_ID}")
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
