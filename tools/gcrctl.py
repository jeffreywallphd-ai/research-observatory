#!/usr/bin/env python3
"""One-time, exact-packet Governance Control Recovery controller.

GCR-0001 exists only because the active GRR hold and its supplement installer
could not represent their own next generation.  This controller deliberately
has no generic request creation path and recognizes only GCR-0001.B00.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import taskctl
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

GCR_ID = "GCR-0001"
BOOTSTRAP_ID = "GCR-0001.B00"
BRANCH = "codex/w1-windows-local-runtime"
ACTOR = "codex"
PACKET_COMMIT = "f4a88faac67e384514c486c161161e6fcc395fab"
PACKET_SHA256 = "43551219b638e1e3a740ee650a836bbb26d81c20fd06dee44828e6615fcf077c"
APPROVAL_PATH = "planning/governance-control-recovery/GCR-0001.approval.json"
PACKET_PATH = "planning/governance-control-recovery/GCR-0001.packet.json"
RUNTIME_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-runtime.schema.json"
STATE_PATH = "planning/governance-control-recovery/GCR-0001.B00.state.json"
TRANSACTION_PATH = "planning/governance-control-recovery/GCR-0001.B00.adoption-transaction.json"
TRANSACTION_SCHEMA_PATH = "planning/governance-control-recovery/governance-control-recovery-transaction.schema.json"
BACKLOG_PATH = "planning/backlog.yaml"
BACKLOG_NEXT_PATH = "planning/governance-control-recovery/GCR-0001.B00.adoption-backlog.next"
STATE_NEXT_PATH = "planning/governance-control-recovery/GCR-0001.B00.adoption-state.next"
TRIGGER_PATH = "artifacts/evidence/W1.A04.B00.json"
TRIGGER_SHA256 = "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c"
BACKLOG_SHA256 = "f3ebfba07cb6ccd779942ea8f988b0ceea6fe16cd18ca8f7a65775915da50139"
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
RESULT_STATUS = {
    "approved": "APPROVED",
    "changes-requested": "CHANGES_REQUESTED",
    "blocked": "BLOCKED",
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=repo, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Git command failed: git {' '.join(arguments)}\n{result.stderr.strip()}")
    return result.stdout.strip()


def git_parents(repo: Path, commit: str) -> list[str]:
    return git(repo, "show", "-s", "--format=%P", commit).split()


def git_delta(repo: Path, parent: str, commit: str) -> dict[str, str]:
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", "--no-renames", "-z", parent, commit],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Cannot reproduce Git delta {parent}..{commit}")
    fields = result.stdout.decode("utf-8", errors="strict").split("\0")
    fields = fields[:-1] if fields and fields[-1] == "" else fields
    if len(fields) % 2:
        raise SystemExit(f"Git delta {parent}..{commit} is malformed")
    delta: dict[str, str] = {}
    for offset in range(0, len(fields), 2):
        status, relative = fields[offset : offset + 2]
        if relative in delta:
            raise SystemExit(f"Git delta {parent}..{commit} repeats {relative}")
        delta[relative] = status
    return delta


def require_exact_commit_delta(
    repo: Path,
    *,
    parent: str,
    commit: str,
    expected: dict[str, str],
    label: str,
) -> None:
    if git_parents(repo, commit) != [parent] or git_delta(repo, parent, commit) != expected:
        raise SystemExit(f"{label} is not the exact single-parent path/status delta")


def safe_path(
    repo: Path,
    relative: str,
    *,
    label: str,
    prefix: str | None = None,
    require_exists: bool = True,
) -> Path:
    if not relative or "\\" in relative or ":" in relative or re.search(r"(?:^|/)\.{1,2}(?:/|$)", relative):
        raise SystemExit(f"{label} is not a canonical repository path: {relative!r}")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or pure.as_posix() != relative:
        raise SystemExit(f"{label} is not canonical: {relative!r}")
    if prefix and relative != prefix and not relative.startswith(prefix.rstrip("/") + "/"):
        raise SystemExit(f"{label} is outside {prefix}: {relative!r}")
    path = repo.joinpath(*pure.parts)
    try:
        path.resolve(strict=False).relative_to(repo.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"{label} resolves outside the repository: {relative!r}") from exc
    if require_exists and not path.is_file():
        raise SystemExit(f"{label} does not exist: {relative!r}")
    return path


def load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object: {path}")
    return value, payload


def runtime_schema(repo: Path) -> dict[str, Any]:
    schema, _payload = load_json(safe_path(repo, RUNTIME_SCHEMA_PATH, label="GCR runtime schema"), "schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SystemExit(f"GCR runtime schema is invalid: {exc}") from exc
    return schema


def validate_runtime(repo: Path, document: dict[str, Any], label: str) -> None:
    errors = sorted(
        Draft202012Validator(runtime_schema(repo), format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        rendered = [
            "$"
            + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
            + f": {error.message}"
            for error in errors
        ]
        raise SystemExit(f"{label} runtime-schema validation failed:\n- " + "\n- ".join(rendered))


def validate_transaction(repo: Path, document: dict[str, Any]) -> None:
    schema, _payload = load_json(
        safe_path(repo, TRANSACTION_SCHEMA_PATH, label="GCR adoption transaction schema"),
        "GCR adoption transaction schema",
    )
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SystemExit(f"GCR adoption transaction schema is invalid: {exc}") from exc
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        rendered = [
            "$"
            + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
            + f": {error.message}"
            for error in errors
        ]
        raise SystemExit("GCR adoption transaction validation failed:\n- " + "\n- ".join(rendered))


def trigger_witness() -> dict[str, Any]:
    return {
        "path": TRIGGER_PATH,
        "sha256": TRIGGER_SHA256,
        "role": "atomic-failure-trigger-only",
        "untracked": True,
        "unstaged": True,
        "executionAuthority": False,
    }


def validate_trigger(repo: Path) -> None:
    path = safe_path(repo, TRIGGER_PATH, label="GCR trigger witness", prefix="artifacts/evidence")
    if sha256(path.read_bytes()) != TRIGGER_SHA256:
        raise SystemExit("GCR trigger witness is missing or has changed")
    staged = set(git(repo, "diff", "--cached", "--name-only", "--").splitlines())
    if TRIGGER_PATH in staged:
        raise SystemExit("GCR trigger witness must remain unstaged")


def require_workspace(repo: Path, *, extra_untracked: set[str] | None = None) -> None:
    if git(repo, "branch", "--show-current") != BRANCH:
        raise SystemExit(f"GCR transitions require exact branch {BRANCH}")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=repo, check=False).returncode != 0:
        raise SystemExit("Tracked worktree changes exist; GCR transitions require an exact commit")
    validate_trigger(repo)
    allowed = {TRIGGER_PATH, *(extra_untracked or set())}
    untracked = set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    if untracked != allowed:
        unexpected = sorted(untracked ^ allowed)
        raise SystemExit(f"GCR untracked-path boundary differs: {unexpected[0] if unexpected else '<unknown>'}")


def require_recovery_workspace(
    repo: Path,
    *,
    present_artifacts: set[str],
    expected_tracked: set[str] | None = None,
) -> None:
    """Require the exact Git workspace permitted for transaction recovery."""
    if git(repo, "branch", "--show-current") != BRANCH:
        raise SystemExit(f"GCR recovery requires exact branch {BRANCH}")
    validate_trigger(repo)
    staged = set(git(repo, "diff", "--cached", "--name-only", "--").splitlines())
    if staged:
        raise SystemExit(f"GCR recovery staged-path boundary differs: {sorted(staged)[0]}")
    untracked = set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    allowed_untracked = {TRIGGER_PATH, *present_artifacts}
    if untracked != allowed_untracked:
        unexpected = sorted(untracked ^ allowed_untracked)
        raise SystemExit(
            f"GCR recovery untracked-path boundary differs: {unexpected[0] if unexpected else '<unknown>'}"
        )
    tracked = set(git(repo, "diff", "--name-only", "HEAD", "--").splitlines())
    canonical = {BACKLOG_PATH, STATE_PATH}
    if expected_tracked is None:
        unexpected_tracked = tracked - canonical
        if unexpected_tracked:
            raise SystemExit(f"GCR recovery tracked-path boundary differs: {sorted(unexpected_tracked)[0]}")
    elif tracked != expected_tracked:
        unexpected = sorted(tracked ^ expected_tracked)
        raise SystemExit(f"GCR recovery tracked-path boundary differs: {unexpected[0] if unexpected else '<unknown>'}")


def load_authority(repo: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    packet_path = safe_path(repo, PACKET_PATH, label="GCR packet")
    approval_path = safe_path(repo, APPROVAL_PATH, label="GCR approval")
    packet, packet_payload = load_json(packet_path, "GCR packet")
    approval, approval_payload = load_json(approval_path, "GCR approval")
    if sha256(packet_payload) != PACKET_SHA256:
        raise SystemExit("GCR packet hash differs from the approved packet")
    if taskctl.git_blob(repo, PACKET_COMMIT, PACKET_PATH) != packet_payload:
        raise SystemExit("GCR packet differs from its immutable approved Git blob")
    validate_runtime(repo, approval, "GCR approval")
    approval_intro = taskctl.approval_introduction_commit(repo, APPROVAL_PATH)
    if not approval_intro or taskctl.git_blob(repo, approval_intro, APPROVAL_PATH) != approval_payload:
        raise SystemExit("GCR approval is absent, replaced, or edited after introduction")
    if not taskctl.git_is_ancestor(repo, PACKET_COMMIT, approval_intro):
        raise SystemExit("GCR approval does not descend from its exact packet")
    packet_reference = approval.get("packet") or {}
    review_reference = (approval.get("independentPacketReview") or {}).get("ledger") or {}
    if (
        packet_reference != {"path": PACKET_PATH, "sha256": PACKET_SHA256, "commit": PACKET_COMMIT}
        or approval.get("status") != "APPROVED"
        or approval.get("controlRecoveryId") != GCR_ID
        or approval.get("triggerWitness") != trigger_witness()
        or (approval.get("executionAuthority") or {}).get("bootstrapUnit") != BOOTSTRAP_ID
    ):
        raise SystemExit("GCR approval identity, packet, witness, or execution scope is invalid")
    review_path = safe_path(
        repo,
        str(review_reference.get("path") or ""),
        label="GCR packet review",
        prefix="planning/governance-control-recovery",
    )
    review_payload = review_path.read_bytes()
    review_commit = str(review_reference.get("commit") or "")
    if (
        sha256(review_payload) != review_reference.get("sha256")
        or not taskctl.git_commit_exists(repo, review_commit)
        or not taskctl.git_is_ancestor(repo, review_commit)
        or taskctl.git_blob(repo, review_commit, str(review_reference.get("path"))) != review_payload
    ):
        raise SystemExit("GCR packet review binding is invalid")
    for pattern in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", []):
        validate_scope_pattern(str(pattern))
    validate_trigger(repo)
    return approval, packet, str(approval_intro)


def validate_scope_pattern(pattern: str) -> None:
    if "**" in pattern and not pattern.endswith("/**"):
        raise SystemExit(f"GCR authorized wildcard is unsafe: {pattern}")
    if pattern.count("*") > (2 if pattern.endswith("/**") else 1):
        raise SystemExit(f"GCR authorized wildcard is unsupported: {pattern}")
    lexical = pattern[:-3].rstrip("/") if pattern.endswith("/**") else pattern.replace("*", "scope")
    pure = PurePosixPath(lexical)
    if pure.is_absolute() or ".." in pure.parts or "\\" in pattern:
        raise SystemExit(f"GCR authorized path is unsafe: {pattern}")


def path_authorized(relative: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if relative == prefix or relative.startswith(prefix + "/"):
                return True
        elif "*" in PurePosixPath(pattern).name:
            expression = re.escape(pattern).replace(r"\*", "[^/]*")
            if re.fullmatch(expression, relative):
                return True
        elif relative == pattern:
            return True
    return False


def current_boundary(repo: Path, packet: dict[str, Any], *, revision: int = 6) -> tuple[bytes, dict[str, Any]]:
    backlog_path = repo / "planning/backlog.yaml"
    payload = backlog_path.read_bytes()
    data, _capabilities, _slices, tasks, gates = taskctl.load(str(backlog_path))
    control = data.get("control_plane") or {}
    active = taskctl.active_recovery_holds(data)
    wave = taskctl.wave_map(data).get("W1") or {}
    task = tasks.get("CAP-02.S04.T03") or {}
    gate = gates.get("G1") or {}
    if (
        control.get("revision") != revision
        or control.get("minimum_tool_revision") != revision
        or len(active) != 1
        or active[0].get("id") != "HOLD-W1-GRR-0002"
        or (active[0].get("bootstrap") or {}).get("status") != "APPROVED"
        or (wave.get("campaign") or {}).get("status") != "PAUSED"
        or (wave.get("campaign") or {}).get("scope") != "wave"
        or task.get("status") != "BLOCKED"
        or task.get("recovery_control") is not None
        or "W1.A04" in taskctl.wave_amendment_map(data)
        or gate.get("status") != "PENDING"
    ):
        raise SystemExit("GCR stopped boundary differs from the exact approved packet")
    if revision == 6 and sha256(payload) != BACKLOG_SHA256:
        raise SystemExit("GCR revision-6 backlog bytes differ from the approved trigger")
    if (packet.get("activationBoundary") or {}).get("controlRevision") != 6:
        raise SystemExit("GCR packet activation revision is invalid")
    return payload, data


def state_path(repo: Path, *, require_exists: bool = True) -> Path:
    return safe_path(repo, STATE_PATH, label="GCR state", require_exists=require_exists)


def load_state(repo: Path, *, required: bool) -> tuple[dict[str, Any] | None, bytes | None]:
    path = repo.joinpath(*PurePosixPath(STATE_PATH).parts)
    if not path.is_file():
        if required:
            raise SystemExit("Canonical GCR state does not exist")
        return None, None
    state, payload = load_json(path, "GCR state")
    validate_runtime(repo, state, "GCR state")
    if (
        state.get("controlRecoveryId") != GCR_ID
        or state.get("bootstrapUnit") != BOOTSTRAP_ID
        or state.get("triggerWitness") != trigger_witness()
    ):
        raise SystemExit("GCR state identity or trigger witness is invalid")
    return state, payload


def write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    payload = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def changed_paths(repo: Path, base: str, candidate: str) -> list[str]:
    if not taskctl.git_commit_exists(repo, base) or not taskctl.git_commit_exists(repo, candidate):
        raise SystemExit("GCR base or candidate commit is absent")
    if base == candidate or not taskctl.git_is_ancestor(repo, base, candidate):
        raise SystemExit("GCR implementation candidate must strictly descend from its required base")
    return sorted(line for line in git(repo, "diff", "--name-only", f"{base}..{candidate}", "--").splitlines() if line)


def evidence_path_for(attempt_id: str) -> str:
    return f"artifacts/evidence/governance-control-recovery/{BOOTSTRAP_ID}.{attempt_id}.json"


def review_path_for(attempt_id: str) -> str:
    return f"planning/governance-control-recovery/{BOOTSTRAP_ID}.review-{attempt_id}.json"


def open_findings(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    opened: dict[str, dict[str, Any]] = {}
    for attempt in state.get("attempts", []):
        for closure in attempt.get("closures", []):
            opened.pop(str(closure.get("findingId") or ""), None)
        for finding in attempt.get("findings", []):
            opened[str(finding.get("id") or "")] = finding
    return opened


def evidence_document(
    repo: Path,
    packet: dict[str, Any],
    relative: str,
    candidate: str,
    approval_base: str,
    attempt_id: str,
    prior_open: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], bytes]:
    expected = evidence_path_for(attempt_id)
    if relative != expected:
        raise SystemExit(f"GCR evidence path must be {expected}")
    path = safe_path(repo, relative, label="GCR evidence", prefix="artifacts/evidence/governance-control-recovery")
    document, payload = load_json(path, "GCR evidence")
    validate_runtime(repo, document, "GCR evidence")
    actual_paths = changed_paths(repo, approval_base, candidate)
    patterns = [str(item) for item in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", [])]
    outside = [path_value for path_value in actual_paths if not path_authorized(path_value, patterns)]
    criteria = document.get("acceptanceCriteria") or []
    expected_criteria = packet.get("acceptanceCriteria") or []
    closure_ids = [str(item.get("findingId") or "") for item in document.get("findingClosures", [])]
    if (
        document.get("controlRecoveryId") != GCR_ID
        or document.get("bootstrapUnit") != BOOTSTRAP_ID
        or document.get("attemptId") != attempt_id
        or document.get("commit") != candidate
        or document.get("baseCommit") != approval_base
        or document.get("branch") != BRANCH
        or document.get("triggerWitness") != trigger_witness()
        or sorted(document.get("changedFiles") or []) != actual_paths
        or outside
        or [item.get("index") for item in criteria] != list(range(1, len(expected_criteria) + 1))
        or [item.get("statement") for item in criteria] != expected_criteria
        or document.get("unverifiedItems") != []
        or len(closure_ids) != len(set(closure_ids))
        or set(closure_ids) != set(prior_open)
    ):
        raise SystemExit("GCR evidence identity, scope, criteria, closures, or verification boundary is invalid")
    checks = document.get("checks") or []
    if (
        not checks
        or len({str(item.get("id")) for item in checks}) != len(checks)
        or any(item.get("exitCode") != 0 or item.get("result") != "passed" for item in checks)
    ):
        raise SystemExit("GCR evidence checks must be unique and passing")
    for closure in document.get("findingClosures", []):
        finding = prior_open.get(str(closure.get("findingId"))) or {}
        if finding.get("blocking") is True and closure.get("disposition") == "accepted-risk":
            raise SystemExit("Blocking GCR findings cannot close as accepted risk")
    return document, payload


def freeze_submission(args: argparse.Namespace, *, remediation: bool) -> None:
    _approval, packet, approval_base = load_authority(args.repo)
    state, _state_payload = load_state(args.repo, required=remediation)
    if remediation:
        assert state is not None
        if state.get("status") not in {"CHANGES_REQUESTED", "BLOCKED"} or state.get("currentSubmission") is not None:
            raise SystemExit("GCR remediation requires an adverse immutable prior review")
    elif state is not None:
        raise SystemExit("Initial GCR submission refuses an existing canonical state")
    attempts = (state or {}).get("attempts", [])
    attempt_id = f"R{len(attempts) + 1:02d}"
    evidence_relative = str(args.evidence)
    require_workspace(args.repo, extra_untracked={evidence_relative})
    agent = str(args.agent).strip()
    if agent != ACTOR or args.agent != agent:
        raise SystemExit(f"GCR implementer must be exact actor {ACTOR}")
    candidate = str(args.implementation_commit)
    if candidate != git(args.repo, "rev-parse", "HEAD"):
        raise SystemExit("GCR implementation candidate must equal current HEAD")
    if not remediation and str(args.approval_commit) != approval_base:
        raise SystemExit("GCR approval commit must equal the immutable approval introduction")
    if remediation:
        prior_candidate = str((attempts[-1].get("submission") or {}).get("candidateCommit") or "")
        if prior_candidate == candidate or not taskctl.git_is_ancestor(args.repo, prior_candidate, candidate):
            raise SystemExit("GCR remediation candidate must strictly descend from the prior candidate")
    prior_open = open_findings(state or {"attempts": []})
    document, evidence_payload = evidence_document(
        args.repo,
        packet,
        evidence_relative,
        candidate,
        approval_base,
        attempt_id,
        prior_open,
    )
    current_boundary(args.repo, packet)
    submission = {
        "attemptId": attempt_id,
        "submittedBy": agent,
        "submittedAt": taskctl.utc_now(),
        "candidateCommit": candidate,
        "baseCommit": approval_base,
        "branch": BRANCH,
        "evidence": {"path": evidence_relative, "sha256": sha256(evidence_payload), "commit": candidate},
        "priorAttemptId": attempts[-1]["submission"]["attemptId"] if attempts else None,
        "openFindingIds": sorted(prior_open),
        "rootCauseAnalysis": (
            str(document.get("verificationSelection", {}).get("riskAnalysis")) if len(attempts) >= 2 else None
        ),
    }
    candidate_state = {
        "schemaVersion": "1.0-control-recovery-state",
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
        "attempts": attempts,
        "currentSubmission": submission,
        "adoption": None,
    }
    validate_runtime(args.repo, candidate_state, "GCR submission state")
    write_json_atomic(args.repo / STATE_PATH, candidate_state)
    print(f"Submitted {BOOTSTRAP_ID}/{attempt_id} for independent review; revision 6 remains active")


def validate_review_ledger(
    repo: Path,
    ledger: dict[str, Any],
    state: dict[str, Any],
    relative: str,
    reviewer: str,
    reviewed_state: str,
) -> None:
    validate_runtime(repo, ledger, "GCR review ledger")
    submission = state.get("currentSubmission") or {}
    attempt_id = str(submission.get("attemptId") or "")
    if relative != review_path_for(attempt_id):
        raise SystemExit(f"GCR review ledger path must be {review_path_for(attempt_id)}")
    findings = ledger.get("findings") or []
    severities = [SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings]
    prior_open = open_findings(state)
    closure_ids = [str(item.get("findingId") or "") for item in ledger.get("closures", [])]
    if (
        ledger.get("controlRecoveryId") != GCR_ID
        or ledger.get("bootstrapUnit") != BOOTSTRAP_ID
        or ledger.get("attemptId") != attempt_id
        or ledger.get("candidateCommit") != submission.get("candidateCommit")
        or ledger.get("reviewedStateCommit") != reviewed_state
        or ledger.get("reviewer") != reviewer
        or reviewer == submission.get("submittedBy")
        or ledger.get("evidence") != submission.get("evidence")
        or severities != sorted(severities)
        or len({str(item.get("id")) for item in findings}) != len(findings)
        or len(closure_ids) != len(set(closure_ids))
        or set(closure_ids) != set(prior_open)
    ):
        raise SystemExit("GCR review identity, independence, evidence, ordering, or closures are invalid")
    after_open = dict(prior_open)
    for closure_id in closure_ids:
        after_open.pop(closure_id, None)
    for finding in findings:
        after_open[str(finding.get("id"))] = finding
    if ledger.get("result") == "approved" and any(item.get("blocking") is True for item in after_open.values()):
        raise SystemExit("GCR approval retains an open blocking finding")


def command_review(args: argparse.Namespace) -> None:
    _approval, _packet, _approval_base = load_authority(args.repo)
    state, _payload = load_state(args.repo, required=True)
    assert state is not None
    if state.get("status") != "REVIEW" or state.get("currentSubmission") is None:
        raise SystemExit("GCR state has no frozen submission eligible for review")
    relative = str(args.ledger)
    require_workspace(args.repo, extra_untracked={relative})
    reviewer = str(args.reviewer).strip()
    if not reviewer or reviewer != args.reviewer or reviewer == ACTOR:
        raise SystemExit("GCR reviewer must be normalized and independent")
    reviewed_state = git(args.repo, "rev-parse", "HEAD")
    path = safe_path(
        args.repo,
        relative,
        label="GCR review ledger",
        prefix="planning/governance-control-recovery",
    )
    ledger, ledger_payload = load_json(path, "GCR review ledger")
    validate_review_ledger(args.repo, ledger, state, relative, reviewer, reviewed_state)
    submission = copy.deepcopy(state["currentSubmission"])
    projection = {
        "reviewer": reviewer,
        "result": ledger["result"],
        "reviewedAt": taskctl.utc_now(),
        "reviewedStateCommit": reviewed_state,
        "notes": ledger.get("notes"),
    }
    attempt = {
        "submission": submission,
        "review": projection,
        "ledger": {"path": relative, "sha256": sha256(ledger_payload), "commit": reviewed_state},
        "findings": ledger.get("findings") or [],
        "closures": ledger.get("closures") or [],
    }
    state["attempts"].append(attempt)
    state["status"] = RESULT_STATUS[str(ledger["result"])]
    state["currentSubmission"] = None
    validate_runtime(args.repo, state, "GCR reviewed state")
    write_json_atomic(args.repo / STATE_PATH, state)
    print(f"Recorded {BOOTSTRAP_ID}/{submission['attemptId']} as {state['status']}")


def validate_state_history(repo: Path, state: dict[str, Any], packet: dict[str, Any]) -> None:
    prior_candidate: str | None = None
    prior_open: dict[str, dict[str, Any]] = {}
    prior_attempts: list[dict[str, Any]] = []
    approval_base = str((state.get("approval") or {}).get("commit") or "")
    approval_path = safe_path(
        repo,
        str((state.get("approval") or {}).get("path") or ""),
        label="GCR historical approval",
        prefix="planning/governance-control-recovery",
    )
    approval_payload = approval_path.read_bytes()
    if (
        (state.get("approval") or {}).get("path") != APPROVAL_PATH
        or sha256(approval_payload) != (state.get("approval") or {}).get("sha256")
        or taskctl.git_blob(repo, approval_base, APPROVAL_PATH) != approval_payload
    ):
        raise SystemExit("GCR state approval binding is invalid")
    for index, attempt in enumerate(state.get("attempts", []), start=1):
        submission = attempt.get("submission") or {}
        attempt_id = f"R{index:02d}"
        candidate = str(submission.get("candidateCommit") or "")
        if (
            submission.get("attemptId") != attempt_id
            or submission.get("submittedBy") != ACTOR
            or submission.get("baseCommit") != approval_base
            or submission.get("branch") != BRANCH
            or submission.get("priorAttemptId") != (f"R{index - 1:02d}" if index > 1 else None)
            or submission.get("openFindingIds") != sorted(prior_open)
        ):
            raise SystemExit("GCR attempt history identity, base, branch, or prior-finding binding is invalid")
        if (
            not taskctl.git_commit_exists(repo, candidate)
            or not taskctl.git_is_ancestor(repo, approval_base, candidate)
            or not taskctl.git_is_ancestor(repo, candidate)
        ):
            raise SystemExit("GCR candidate is absent from the approved ancestry")
        if prior_candidate is not None and (
            prior_candidate == candidate or not taskctl.git_is_ancestor(repo, prior_candidate, candidate)
        ):
            raise SystemExit("GCR remediation candidate ancestry is invalid")
        evidence = submission.get("evidence") or {}
        _evidence_document, evidence_payload = evidence_document(
            repo,
            packet,
            str(evidence.get("path") or ""),
            candidate,
            approval_base,
            attempt_id,
            prior_open,
        )
        if sha256(evidence_payload) != evidence.get("sha256") or evidence.get("commit") != candidate:
            raise SystemExit("GCR historical evidence hash/candidate binding is invalid")
        review = attempt.get("review") or {}
        reviewed_state = str(review.get("reviewedStateCommit") or "")
        if (
            not taskctl.git_commit_exists(repo, reviewed_state)
            or reviewed_state == candidate
            or not taskctl.git_is_ancestor(repo, candidate, reviewed_state)
            or not taskctl.git_is_ancestor(repo, reviewed_state)
        ):
            raise SystemExit("GCR reviewed-state commit is absent or outside candidate ancestry")
        state_status = "A" if taskctl.git_blob(repo, candidate, STATE_PATH) is None else "M"
        require_exact_commit_delta(
            repo,
            parent=candidate,
            commit=reviewed_state,
            expected={str(evidence.get("path")): "A", STATE_PATH: state_status},
            label=f"{BOOTSTRAP_ID}/{attempt_id} reviewed-state commit",
        )
        if taskctl.git_blob(repo, reviewed_state, str(evidence.get("path"))) != evidence_payload:
            raise SystemExit("GCR reviewed-state evidence Git blob differs from the frozen evidence")
        historical_payload = taskctl.git_blob(repo, reviewed_state, STATE_PATH)
        try:
            historical_state = json.loads(historical_payload or b"")
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SystemExit("GCR reviewed-state Git blob is missing or malformed") from exc
        validate_runtime(repo, historical_state, "GCR reviewed-state Git blob")
        if (
            historical_state.get("status") != "REVIEW"
            or historical_state.get("attempts") != prior_attempts
            or historical_state.get("currentSubmission") != submission
            or historical_state.get("adoption") is not None
            or historical_state.get("approval") != state.get("approval")
            or historical_state.get("triggerWitness") != trigger_witness()
        ):
            raise SystemExit("GCR reviewed-state Git blob does not reproduce the frozen submission")
        ledger = attempt.get("ledger") or {}
        ledger_relative = str(ledger.get("path") or "")
        ledger_path = safe_path(
            repo,
            ledger_relative,
            label="GCR historical review",
            prefix="planning/governance-control-recovery",
        )
        ledger_document, ledger_payload = load_json(ledger_path, "GCR historical review")
        if (
            ledger_relative != review_path_for(attempt_id)
            or sha256(ledger_payload) != ledger.get("sha256")
            or ledger.get("commit") != reviewed_state
        ):
            raise SystemExit("GCR historical review path, hash, or reviewed-state binding is invalid")
        validate_review_ledger(
            repo,
            ledger_document,
            historical_state,
            ledger_relative,
            str(review.get("reviewer") or ""),
            reviewed_state,
        )
        ledger_introduction = taskctl.approval_introduction_commit(repo, ledger_relative)
        if (
            not ledger_introduction
            or ledger_introduction == reviewed_state
            or not taskctl.git_is_ancestor(repo, reviewed_state, ledger_introduction)
            or not taskctl.git_is_ancestor(repo, ledger_introduction)
            or taskctl.git_blob(repo, ledger_introduction, ledger_relative) != ledger_payload
        ):
            raise SystemExit("GCR historical review is absent, replaced, or outside reviewed-state ancestry")
        require_exact_commit_delta(
            repo,
            parent=reviewed_state,
            commit=ledger_introduction,
            expected={ledger_relative: "A", STATE_PATH: "M"},
            label=f"{BOOTSTRAP_ID}/{attempt_id} reviewed disposition commit",
        )
        if (
            review.get("result") != ledger_document.get("result")
            or review.get("reviewer") != ledger_document.get("reviewer")
            or review.get("reviewedStateCommit") != ledger_document.get("reviewedStateCommit")
            or review.get("notes") != ledger_document.get("notes")
            or attempt.get("findings") != ledger_document.get("findings")
            or attempt.get("closures") != ledger_document.get("closures")
        ):
            raise SystemExit("GCR review projection differs from its immutable ledger")
        closure_ids = {str(item.get("findingId")) for item in attempt.get("closures", [])}
        if closure_ids != set(prior_open):
            raise SystemExit("GCR historical closures do not exactly reconcile prior findings")
        for closure_id in closure_ids:
            prior_open.pop(closure_id, None)
        for finding in attempt.get("findings", []):
            prior_open[str(finding.get("id"))] = finding
        if (attempt.get("review") or {}).get("result") == "approved" and any(
            item.get("blocking") is True for item in prior_open.values()
        ):
            raise SystemExit("GCR historical approval retains a blocking finding")
        prior_candidate = candidate
        prior_attempts.append(attempt)
    current = state.get("currentSubmission")
    if current is not None:
        attempt_id = f"R{len(prior_attempts) + 1:02d}"
        candidate = str(current.get("candidateCommit") or "")
        evidence = current.get("evidence") or {}
        if (
            state.get("status") != "REVIEW"
            or current.get("attemptId") != attempt_id
            or current.get("submittedBy") != ACTOR
            or current.get("baseCommit") != approval_base
            or current.get("branch") != BRANCH
            or current.get("priorAttemptId") != (f"R{len(prior_attempts):02d}" if prior_attempts else None)
            or current.get("openFindingIds") != sorted(prior_open)
            or not taskctl.git_commit_exists(repo, candidate)
            or not taskctl.git_is_ancestor(repo, approval_base, candidate)
            or not taskctl.git_is_ancestor(repo, candidate)
            or (
                prior_candidate is not None
                and (prior_candidate == candidate or not taskctl.git_is_ancestor(repo, prior_candidate, candidate))
            )
        ):
            raise SystemExit("GCR current submission is not the next strict approved-ancestry candidate")
        _document, evidence_payload = evidence_document(
            repo,
            packet,
            str(evidence.get("path") or ""),
            candidate,
            approval_base,
            attempt_id,
            prior_open,
        )
        if sha256(evidence_payload) != evidence.get("sha256") or evidence.get("commit") != candidate:
            raise SystemExit("GCR current submission evidence binding is invalid")
    elif state.get("status") == "REVIEW":
        raise SystemExit("GCR REVIEW state lacks its frozen current submission")
    elif not prior_attempts:
        raise SystemExit("GCR reviewed state lacks immutable review history")
    elif (
        state.get("status") not in {"ADOPTED", "ADOPTION_FINALIZATION"}
        and state.get("status") != RESULT_STATUS[str((prior_attempts[-1].get("review") or {}).get("result"))]
    ):
        raise SystemExit("GCR live state differs from the latest immutable review result")
    if (state.get("status") == "ADOPTION_FINALIZATION") != (state.get("adoption") is not None):
        raise SystemExit("GCR adoption state and adoption record differ")
    if state.get("status") == "ADOPTED":
        raise SystemExit("GCR adopted state lacks the required predecessor-reader finalization marker")
    if state.get("status") == "ADOPTION_FINALIZATION":
        adoption = state.get("adoption") or {}
        backlog = yaml.safe_load((repo / BACKLOG_PATH).read_text(encoding="utf-8"))
        transition_errors = taskctl.governance_control_generation_errors(backlog, repo=None)
        if transition_errors:
            raise SystemExit("GCR control generation history is invalid:\n- " + "\n- ".join(transition_errors))
        generations = (backlog.get("control_plane") or {}).get("control_generations") or []
        if not generations:
            raise SystemExit("GCR adoption finalization lacks its immutable generation")
        finalization_errors = taskctl.governance_control_adoption_finalization_errors(
            repo,
            str((adoption.get("evidence") or {}).get("commit") or ""),
            (repo / STATE_PATH).read_bytes(),
            generations[0],
        )
        if finalization_errors:
            raise SystemExit("GCR adoption finalization failed:\n- " + "\n- ".join(finalization_errors))


def command_validate(args: argparse.Namespace) -> None:
    _approval, packet, _approval_base = load_authority(args.repo)
    present = transaction_artifacts_present(args.repo)
    if present:
        raise SystemExit(f"GCR adoption transaction requires explicit recovery: {present}")
    backlog = yaml.safe_load((args.repo / "planning/backlog.yaml").read_text(encoding="utf-8"))
    revision = int(backlog["control_plane"]["revision"])
    _backlog_payload, data = current_boundary(args.repo, packet, revision=revision)
    semantic_errors = taskctl.validate(*taskctl.index_backlog(data), repo=args.repo)
    if semantic_errors:
        raise SystemExit("GCR control semantics are invalid:\n- " + "\n- ".join(semantic_errors))
    state, _payload = load_state(args.repo, required=False)
    status = "AUTHORIZED"
    if state is not None:
        validate_state_history(args.repo, state, packet)
        status = "ADOPTED" if state.get("status") == "ADOPTION_FINALIZATION" else str(state.get("status"))
    if args.require_approved and status not in {"APPROVED", "ADOPTED"}:
        raise SystemExit(f"{BOOTSTRAP_ID} is not independently approved")
    print(f"Valid {GCR_ID}: bootstrap={status}; control={revision}")


def command_status(args: argparse.Namespace) -> None:
    _approval, _packet, approval_base = load_authority(args.repo)
    state, _payload = load_state(args.repo, required=False)
    backlog = yaml.safe_load((args.repo / "planning/backlog.yaml").read_text(encoding="utf-8"))
    semantic_errors = taskctl.validate(*taskctl.index_backlog(backlog), repo=args.repo)
    bootstrap_status = (state or {}).get("status", "AUTHORIZED")
    if semantic_errors:
        bootstrap_status = "CONTROL_HISTORY_INVALID"
    elif state is not None and bootstrap_status == "ADOPTION_FINALIZATION":
        adoption = state.get("adoption") or {}
        generations = (backlog.get("control_plane") or {}).get("control_generations") or []
        if not generations or taskctl.governance_control_adoption_finalization_errors(
            args.repo,
            str((adoption.get("evidence") or {}).get("commit") or ""),
            (args.repo / STATE_PATH).read_bytes(),
            generations[0] if generations else {},
        ):
            bootstrap_status = "ADOPTION_FINALIZATION_PENDING_OR_INVALID"
        else:
            bootstrap_status = "ADOPTED"
    elif bootstrap_status == "ADOPTED":
        bootstrap_status = "INVALID_LEGACY_ADOPTED_STATE"
    print(
        yaml.safe_dump(
            {
                "controlRecovery": GCR_ID,
                "bootstrap": {"id": BOOTSTRAP_ID, "status": bootstrap_status},
                "approvalBase": approval_base,
                "controlRevision": backlog["control_plane"]["revision"],
                "adoptionTransaction": (
                    {"status": "RECOVERY_REQUIRED", "artifacts": transaction_artifacts_present(args.repo)}
                    if transaction_artifacts_present(args.repo)
                    else {"status": "ABSENT", "artifacts": []}
                ),
                "controlValidation": {
                    "status": "INVALID" if semantic_errors else "VALID",
                    "firstError": semantic_errors[0] if semantic_errors else None,
                },
                "ordinaryExecutionAuthority": False,
            },
            sort_keys=False,
        ).rstrip()
    )


def command_recover(args: argparse.Namespace) -> None:
    _approval, packet, _approval_base = load_authority(args.repo)
    result = recover_adoption_transaction(args.repo, packet)
    print(f"GCR adoption recovery: {result}; ordinary execution remains unauthorized")


def canonical_approved_boundary(
    repo: Path,
    packet: dict[str, Any],
    state: dict[str, Any],
    state_payload: bytes,
) -> tuple[str, str, dict[str, Any], bytes]:
    validate_state_history(repo, state, packet)
    if state.get("status") != "APPROVED" or not state.get("attempts"):
        raise SystemExit("GCR adoption requires the latest immutable review to be APPROVED")
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
        raise SystemExit("GCR canonical approved-state commit cannot be derived from the latest ledger")
    ledger_payload = safe_path(
        repo,
        ledger_relative,
        label="GCR approved review",
        prefix="planning/governance-control-recovery",
    ).read_bytes()
    if taskctl.git_blob(repo, approved_state, ledger_relative) != ledger_payload:
        raise SystemExit("GCR approved-state commit does not contain the exact approved ledger")
    require_exact_commit_delta(
        repo,
        parent=reviewed_state,
        commit=approved_state,
        expected={ledger_relative: "A", STATE_PATH: "M"},
        label="GCR canonical approved-state commit",
    )
    return reviewed_state, approved_state, ledger, ledger_payload


def adoption_fault_boundary(_label: str) -> None:
    """Test seam for child-process termination; production behavior is deliberately inert."""


def _artifact_path(repo: Path, relative: str) -> Path:
    path = repo.joinpath(*PurePosixPath(relative).parts)
    try:
        path.resolve(strict=False).relative_to(repo.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"GCR transaction path escapes the repository: {relative}") from exc
    junction = getattr(os.path, "isjunction", lambda _path: False)
    if path.is_symlink() or junction(path):
        raise SystemExit(f"GCR transaction path is redirected: {relative}")
    return path


def transaction_artifacts(repo: Path) -> dict[str, Path]:
    return {
        TRANSACTION_PATH: _artifact_path(repo, TRANSACTION_PATH),
        BACKLOG_NEXT_PATH: _artifact_path(repo, BACKLOG_NEXT_PATH),
        STATE_NEXT_PATH: _artifact_path(repo, STATE_NEXT_PATH),
    }


def transaction_artifacts_present(repo: Path) -> list[str]:
    return [relative for relative, path in transaction_artifacts(repo).items() if os.path.lexists(path)]


def transaction_expected_tracked_paths(repo: Path, transaction: dict[str, Any]) -> set[str]:
    predecessor = transaction.get("predecessor") or {}
    successor = transaction.get("successor") or {}
    expected: set[str] = set()
    for relative, key in ((BACKLOG_PATH, "backlogSha256"), (STATE_PATH, "stateSha256")):
        current_hash = sha256((repo / relative).read_bytes())
        if current_hash == successor.get(key):
            expected.add(relative)
        elif current_hash != predecessor.get(key):
            raise SystemExit(f"GCR canonical {relative} bytes match neither transaction boundary")
    return expected


def fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        # MoveFileExW WRITE_THROUGH and destination-file fsync provide the available
        # Windows durability boundary; Python cannot portably fsync a directory handle.
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_new_durable(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        raise
    fsync_directory(path.parent)


def move_write_through(source: Path, destination: Path) -> None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        move_file = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move_file.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        move_file.restype = wintypes.BOOL
        replace_existing = 0x1
        write_through = 0x8
        if not move_file(str(source), str(destination), replace_existing | write_through):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(source, destination)
        fsync_directory(destination.parent)
    with destination.open("r+b") as handle:
        os.fsync(handle.fileno())


def unlink_durable(path: Path) -> None:
    path.unlink()
    fsync_directory(path.parent)


def hold_sha256(backlog: dict[str, Any]) -> str:
    hold = next(
        (
            item
            for item in (backlog.get("control_plane") or {}).get("recovery_holds", [])
            if item.get("id") == "HOLD-W1-GRR-0002"
        ),
        None,
    )
    if not isinstance(hold, dict):
        raise SystemExit("GCR transaction cannot reproduce HOLD-W1-GRR-0002")
    return taskctl.canonical_json_sha256(hold)


def transaction_document(
    *,
    reviewed_state: str,
    approved_state: str,
    evidence_commit: str,
    evidence_relative: str,
    evidence_payload: bytes,
    predecessor_backlog: bytes,
    predecessor_state: bytes,
    successor_backlog: bytes,
    successor_state: bytes,
    hold_sha: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0-control-recovery-adoption-transaction",
        "documentType": "governance-control-recovery-adoption-transaction",
        "transactionId": "GCR-0001.B00.ADOPT",
        "controlRecoveryId": GCR_ID,
        "bootstrapUnit": BOOTSTRAP_ID,
        "reviewedStateCommit": reviewed_state,
        "approvedStateCommit": approved_state,
        "evidenceCommit": evidence_commit,
        "evidence": {"path": evidence_relative, "sha256": sha256(evidence_payload)},
        "paths": {
            "backlog": BACKLOG_PATH,
            "state": STATE_PATH,
            "backlogNext": BACKLOG_NEXT_PATH,
            "stateNext": STATE_NEXT_PATH,
        },
        "predecessor": {
            "backlogSha256": sha256(predecessor_backlog),
            "stateSha256": sha256(predecessor_state),
            "holdSha256": hold_sha,
        },
        "successor": {
            "backlogSha256": sha256(successor_backlog),
            "stateSha256": sha256(successor_state),
            "holdSha256": hold_sha,
        },
        "createdAt": taskctl.utc_now(),
    }


def validate_successor_pair(
    repo: Path,
    transaction: dict[str, Any],
    backlog_payload: bytes,
    state_payload: bytes,
) -> None:
    try:
        backlog = yaml.safe_load(backlog_payload.decode("utf-8"))
        state = json.loads(state_payload)
    except (UnicodeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        raise SystemExit("GCR transaction successor payload is malformed") from exc
    validate_runtime(repo, state, "GCR transaction successor state")
    schema_errors = taskctl.backlog_schema_errors(backlog)
    semantic_errors = taskctl.validate(*taskctl.index_backlog(backlog), repo=None)
    generation = ((backlog.get("control_plane") or {}).get("control_generations") or [{}])[-1]
    adoption = state.get("adoption") or {}
    if (
        schema_errors
        or semantic_errors
        or hold_sha256(backlog) != (transaction.get("successor") or {}).get("holdSha256")
        or state.get("status") != "ADOPTION_FINALIZATION"
        or generation.get("id") != GCR_ID
        or (generation.get("review_reference") or {}).get("reviewed_state_commit")
        != transaction.get("reviewedStateCommit")
        or (generation.get("review_reference") or {}).get("approved_state_commit")
        != transaction.get("approvedStateCommit")
        or adoption.get("reviewedStateCommit") != transaction.get("approvedStateCommit")
        or (adoption.get("evidence") or {}).get("commit") != transaction.get("evidenceCommit")
        or (adoption.get("evidence") or {}).get("path") != (transaction.get("evidence") or {}).get("path")
        or (adoption.get("evidence") or {}).get("sha256") != (transaction.get("evidence") or {}).get("sha256")
    ):
        details = [*schema_errors, *semantic_errors]
        suffix = f": {'; '.join(details)}" if details else ""
        raise SystemExit(f"GCR transaction successor pair is invalid{suffix}")


def validate_transaction_authority(
    repo: Path,
    packet: dict[str, Any],
    transaction: dict[str, Any],
) -> tuple[bytes, bytes]:
    approved_state = str(transaction.get("approvedStateCommit") or "")
    reviewed_state = str(transaction.get("reviewedStateCommit") or "")
    evidence_commit = str(transaction.get("evidenceCommit") or "")
    predecessor_state = taskctl.git_blob(repo, approved_state, STATE_PATH)
    predecessor_backlog = taskctl.git_blob(repo, evidence_commit, BACKLOG_PATH)
    try:
        predecessor_state_document = json.loads(predecessor_state or b"")
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("GCR transaction approved-state Git blob is malformed") from exc
    _reviewed, derived_approved, _ledger, _ledger_payload = canonical_approved_boundary(
        repo,
        packet,
        predecessor_state_document,
        predecessor_state or b"",
    )
    evidence_relative = str((transaction.get("evidence") or {}).get("path") or "")
    evidence_payload = taskctl.git_blob(repo, evidence_commit, evidence_relative)
    if (
        reviewed_state != _reviewed
        or approved_state != derived_approved
        or git(repo, "rev-parse", "HEAD") != evidence_commit
        or not isinstance(predecessor_backlog, bytes)
        or evidence_payload is None
        or sha256(evidence_payload) != (transaction.get("evidence") or {}).get("sha256")
    ):
        raise SystemExit("GCR transaction Git authority is stale or substituted")
    require_exact_commit_delta(
        repo,
        parent=approved_state,
        commit=evidence_commit,
        expected={evidence_relative: "A"},
        label="GCR adoption-evidence commit",
    )
    predecessor = transaction.get("predecessor") or {}
    if (
        sha256(predecessor_backlog) != predecessor.get("backlogSha256")
        or sha256(predecessor_state or b"") != predecessor.get("stateSha256")
        or hold_sha256(yaml.safe_load(predecessor_backlog)) != predecessor.get("holdSha256")
    ):
        raise SystemExit("GCR transaction predecessor bytes or hold binding are stale")
    return predecessor_backlog, predecessor_state or b""


def complete_adoption_transaction_locked(repo: Path, packet: dict[str, Any]) -> None:
    artifacts = transaction_artifacts(repo)
    transaction_path = artifacts[TRANSACTION_PATH]
    if not transaction_path.is_file() or transaction_path.is_symlink():
        raise SystemExit("GCR adoption transaction manifest is missing or redirected")
    transaction, _payload = load_json(transaction_path, "GCR adoption transaction")
    validate_transaction(repo, transaction)
    require_recovery_workspace(
        repo,
        present_artifacts=set(transaction_artifacts_present(repo)),
        expected_tracked=transaction_expected_tracked_paths(repo, transaction),
    )
    _predecessor_backlog, _predecessor_state = validate_transaction_authority(repo, packet, transaction)
    backlog_path = repo / BACKLOG_PATH
    state_path_value = repo / STATE_PATH
    next_paths = {
        "backlog": artifacts[BACKLOG_NEXT_PATH],
        "state": artifacts[STATE_NEXT_PATH],
    }
    predecessor = transaction.get("predecessor") or {}
    successor = transaction.get("successor") or {}
    current = {"backlog": backlog_path.read_bytes(), "state": state_path_value.read_bytes()}
    old_hashes = {
        "backlog": predecessor.get("backlogSha256"),
        "state": predecessor.get("stateSha256"),
    }
    new_hashes = {"backlog": successor.get("backlogSha256"), "state": successor.get("stateSha256")}
    successor_payloads: dict[str, bytes] = {}
    for label in ("backlog", "state"):
        current_hash = sha256(current[label])
        next_path = next_paths[label]
        if current_hash == new_hashes[label]:
            if os.path.lexists(next_path):
                raise SystemExit(f"GCR transaction retains duplicate {label} successor payload")
            successor_payloads[label] = current[label]
        elif current_hash == old_hashes[label]:
            if not next_path.is_file() or next_path.is_symlink():
                raise SystemExit(f"GCR transaction lacks its durable {label} successor payload")
            payload = next_path.read_bytes()
            if sha256(payload) != new_hashes[label]:
                raise SystemExit(f"GCR transaction {label} successor payload hash is invalid")
            successor_payloads[label] = payload
        else:
            raise SystemExit(f"GCR canonical {label} bytes match neither transaction boundary")
    validate_successor_pair(repo, transaction, successor_payloads["backlog"], successor_payloads["state"])
    if sha256(current["backlog"]) == old_hashes["backlog"]:
        move_write_through(next_paths["backlog"], backlog_path)
        adoption_fault_boundary("backlog-replaced")
    if sha256(state_path_value.read_bytes()) == old_hashes["state"]:
        move_write_through(next_paths["state"], state_path_value)
        adoption_fault_boundary("state-replaced")
    if (
        sha256(backlog_path.read_bytes()) != new_hashes["backlog"]
        or sha256(state_path_value.read_bytes()) != new_hashes["state"]
    ):
        raise SystemExit("GCR adoption transaction did not reach its exact successor pair")
    validate_successor_pair(repo, transaction, backlog_path.read_bytes(), state_path_value.read_bytes())
    require_recovery_workspace(
        repo,
        present_artifacts=set(transaction_artifacts_present(repo)),
        expected_tracked={BACKLOG_PATH, STATE_PATH},
    )
    adoption_fault_boundary("successor-validated")
    unlink_durable(transaction_path)
    adoption_fault_boundary("transaction-removed")
    if transaction_artifacts_present(repo):
        raise SystemExit("GCR adoption transaction cleanup left an unexpected artifact")
    require_recovery_workspace(
        repo,
        present_artifacts=set(),
        expected_tracked={BACKLOG_PATH, STATE_PATH},
    )


def cleanup_unpublished_transaction_locked(
    repo: Path,
    packet: dict[str, Any],
    *,
    include_manifest: bool = False,
) -> None:
    artifacts = transaction_artifacts(repo)
    require_recovery_workspace(
        repo,
        present_artifacts=set(transaction_artifacts_present(repo)),
        expected_tracked=set(),
    )
    if os.path.lexists(artifacts[TRANSACTION_PATH]) and not include_manifest:
        raise SystemExit("Published GCR adoption transaction requires governed recovery")
    state, state_payload = load_state(repo, required=True)
    assert state is not None and state_payload is not None
    _reviewed, approved, _ledger, _ledger_payload = canonical_approved_boundary(repo, packet, state, state_payload)
    evidence_commit = git(repo, "rev-parse", "HEAD")
    evidence_relative = "artifacts/evidence/governance-control-recovery/GCR-0001.B00.adoption.json"
    require_exact_commit_delta(
        repo,
        parent=approved,
        commit=evidence_commit,
        expected={evidence_relative: "A"},
        label="GCR unpublished adoption-evidence commit",
    )
    historical_backlog = taskctl.git_blob(repo, evidence_commit, BACKLOG_PATH)
    if (
        historical_backlog is None
        or (repo / BACKLOG_PATH).read_bytes() != historical_backlog
        or taskctl.git_blob(repo, approved, STATE_PATH) != state_payload
    ):
        raise SystemExit("Unpublished GCR transaction artifacts coexist with a changed canonical record")
    cleanup_paths = [BACKLOG_NEXT_PATH, STATE_NEXT_PATH]
    if include_manifest:
        cleanup_paths.append(TRANSACTION_PATH)
    for relative in cleanup_paths:
        path = artifacts[relative]
        if os.path.lexists(path):
            if not path.is_file() or path.is_symlink():
                raise SystemExit(f"Unpublished GCR transaction artifact is redirected: {relative}")
            unlink_durable(path)


def recover_adoption_transaction(repo: Path, packet: dict[str, Any]) -> str:
    present = transaction_artifacts_present(repo)
    if not present:
        return "ABSENT"
    require_recovery_workspace(repo, present_artifacts=set(present))
    with taskctl.exclusive_backlog_lock(repo / BACKLOG_PATH):
        present = transaction_artifacts_present(repo)
        if not present:
            return "ABSENT"
        require_recovery_workspace(repo, present_artifacts=set(present))
        if TRANSACTION_PATH not in present:
            cleanup_unpublished_transaction_locked(repo, packet)
            return "RESTORED_PREDECESSOR"
        try:
            transaction, _payload = load_json(
                transaction_artifacts(repo)[TRANSACTION_PATH],
                "GCR adoption transaction",
            )
            validate_transaction(repo, transaction)
        except SystemExit:
            cleanup_unpublished_transaction_locked(repo, packet, include_manifest=True)
            return "RESTORED_PREDECESSOR"
        complete_adoption_transaction_locked(repo, packet)
        return "COMPLETED_SUCCESSOR"


def atomic_adoption_write(
    repo: Path,
    *,
    expected_backlog: bytes,
    expected_state: bytes,
    backlog_document: dict[str, Any],
    state_document: dict[str, Any],
    packet: dict[str, Any],
    reviewed_state: str,
    approved_state: str,
    evidence_commit: str,
    evidence_relative: str,
    evidence_payload: bytes,
) -> None:
    backlog_path = repo / BACKLOG_PATH
    state_path_value = repo / STATE_PATH
    backlog_bytes = yaml.safe_dump(
        taskctl.serializable_backlog(backlog_document),
        sort_keys=False,
        allow_unicode=True,
        width=120,
    ).encode("utf-8")
    state_bytes = (json.dumps(state_document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    hold_sha = hold_sha256(yaml.safe_load(expected_backlog))
    transaction = transaction_document(
        reviewed_state=reviewed_state,
        approved_state=approved_state,
        evidence_commit=evidence_commit,
        evidence_relative=evidence_relative,
        evidence_payload=evidence_payload,
        predecessor_backlog=expected_backlog,
        predecessor_state=expected_state,
        successor_backlog=backlog_bytes,
        successor_state=state_bytes,
        hold_sha=hold_sha,
    )
    validate_transaction(repo, transaction)
    validate_successor_pair(repo, transaction, backlog_bytes, state_bytes)
    artifacts = transaction_artifacts(repo)
    with taskctl.exclusive_backlog_lock(backlog_path):
        if transaction_artifacts_present(repo):
            raise SystemExit("A GCR adoption transaction already exists; run gcrctl recover")
        if backlog_path.read_bytes() != expected_backlog or state_path_value.read_bytes() != expected_state:
            raise SystemExit("GCR adoption state changed after validation; no transaction was prepared")
        write_new_durable(artifacts[BACKLOG_NEXT_PATH], backlog_bytes)
        adoption_fault_boundary("backlog-next-durable")
        write_new_durable(artifacts[STATE_NEXT_PATH], state_bytes)
        adoption_fault_boundary("state-next-durable")
        transaction_payload = (json.dumps(transaction, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        write_new_durable(artifacts[TRANSACTION_PATH], transaction_payload)
        adoption_fault_boundary("transaction-published")
        complete_adoption_transaction_locked(repo, packet)


def command_adopt(args: argparse.Namespace) -> None:
    _approval, packet, approval_base = load_authority(args.repo)
    if transaction_artifacts_present(args.repo):
        raise SystemExit("A GCR adoption transaction exists; use gcrctl recover before adoption")
    state, state_payload = load_state(args.repo, required=True)
    assert state is not None and state_payload is not None
    reviewed_state, approved_state, ledger, ledger_payload = canonical_approved_boundary(
        args.repo,
        packet,
        state,
        state_payload,
    )
    if str(args.approved_state_commit) != approved_state:
        raise SystemExit("GCR approved-state argument differs from the canonical latest ledger introduction")
    evidence_commit = git(args.repo, "rev-parse", "HEAD")
    evidence_relative = str(args.evidence)
    if evidence_relative != "artifacts/evidence/governance-control-recovery/GCR-0001.B00.adoption.json":
        raise SystemExit("GCR adoption evidence path is not canonical")
    require_exact_commit_delta(
        args.repo,
        parent=approved_state,
        commit=evidence_commit,
        expected={evidence_relative: "A"},
        label="GCR adoption-evidence commit",
    )
    require_workspace(args.repo)
    evidence_path = safe_path(args.repo, evidence_relative, label="GCR adoption evidence")
    evidence, evidence_payload = load_json(evidence_path, "GCR adoption evidence")
    if taskctl.git_blob(args.repo, evidence_commit, evidence_relative) != evidence_payload:
        raise SystemExit("GCR adoption evidence differs from its exact Git blob")
    validate_runtime(args.repo, evidence, "GCR adoption evidence")
    if (
        evidence.get("controlRecoveryId") != GCR_ID
        or evidence.get("bootstrapUnit") != BOOTSTRAP_ID
        or evidence.get("reviewedStateCommit") != approved_state
        or evidence.get("triggerWitness") != trigger_witness()
        or sorted(evidence.get("expectedChangedFiles") or []) != sorted(["planning/backlog.yaml", STATE_PATH])
        or evidence.get("unverifiedItems") != []
        or any(item.get("exitCode") != 0 or item.get("result") != "passed" for item in evidence.get("checks", []))
    ):
        raise SystemExit("GCR adoption evidence identity, paths, checks, or state binding is invalid")
    backlog_payload, data = current_boundary(args.repo, packet)
    latest = state["attempts"][-1]
    review = latest.get("review") or {}
    now = taskctl.utc_now()
    generation = {
        "id": GCR_ID,
        "bootstrap_id": BOOTSTRAP_ID,
        "hold_id": "HOLD-W1-GRR-0002",
        "predecessor_revision": 6,
        "successor_revision": 7,
        "approval_reference": {
            "path": APPROVAL_PATH,
            "sha256": sha256((args.repo / APPROVAL_PATH).read_bytes()),
            "introduction_commit": approval_base,
        },
        "review_reference": {
            "path": ledger.get("path"),
            "sha256": sha256(ledger_payload),
            "reviewed_state_commit": review.get("reviewedStateCommit"),
            "approved_state_commit": approved_state,
        },
        "adopted_by": str(args.agent).strip(),
        "adopted_at": now,
    }
    if generation["adopted_by"] != ACTOR or args.agent != generation["adopted_by"]:
        raise SystemExit(f"GCR adopter must be exact actor {ACTOR}")
    candidate = copy.deepcopy(taskctl.serializable_backlog(data))
    control = candidate["control_plane"]
    if control.get("control_generations"):
        raise SystemExit("GCR generation was already adopted")
    control["revision"] = 7
    control["minimum_tool_revision"] = 7
    control["control_generations"] = [generation]
    schema_errors = taskctl.backlog_schema_errors(candidate)
    semantic_errors = taskctl.validate(*taskctl.index_backlog(candidate), repo=None)
    if schema_errors or semantic_errors:
        raise SystemExit("GCR adoption candidate is invalid:\n- " + "\n- ".join([*schema_errors, *semantic_errors]))
    state["status"] = "ADOPTION_FINALIZATION"
    state["adoption"] = {
        "adoptedBy": ACTOR,
        "adoptedAt": now,
        "predecessorRevision": 6,
        "successorRevision": 7,
        "reviewedStateCommit": approved_state,
        "evidence": {"path": evidence_relative, "sha256": sha256(evidence_payload), "commit": evidence_commit},
    }
    validate_runtime(args.repo, state, "GCR adopted state")
    atomic_adoption_write(
        args.repo,
        expected_backlog=backlog_payload,
        expected_state=state_payload,
        backlog_document=candidate,
        state_document=state,
        packet=packet,
        reviewed_state=reviewed_state,
        approved_state=approved_state,
        evidence_commit=evidence_commit,
        evidence_relative=evidence_relative,
        evidence_payload=evidence_payload,
    )
    print(
        "Prepared GCR-0001 revision 6-to-7 successor; exact two-path finalization commit is required "
        "before GRR-0002.S01"
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
    validate = commands.add_parser("validate")
    validate.add_argument("request")
    validate.add_argument("--require-approved", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("request")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.repo = args.repo.resolve()
    if getattr(args, "request", GCR_ID) != GCR_ID:
        raise SystemExit(f"gcrctl recognizes only {GCR_ID}")
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
