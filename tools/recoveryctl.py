#!/usr/bin/env python3
"""Fail-closed governance recovery controller.

This controller is intentionally smaller than taskctl.  It can validate an
immutable Governance Recovery Request (GRR), freeze/review the one authorized
bootstrap, and release its hold only after the separately approved amendment
has been adopted with a security checkpoint.  It cannot execute product work.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

import taskctl
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
REVIEW_RESULTS = {"approved": "APPROVED", "changes-requested": "CHANGES_REQUESTED", "blocked": "BLOCKED"}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_sha256(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object: {path}")
    return value, payload


def schema_errors(value: Any, schema_path: Path) -> list[str]:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError) as exc:
        return [f"Cannot load schema {schema_path}: {exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return sorted(
        "$"
        + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
        + f": {error.message}"
        for error in validator.iter_errors(value)
    )


def is_junction(path: Path) -> bool:
    predicate = getattr(os.path, "isjunction", None)
    return bool(predicate and predicate(path))


def safe_repo_path(
    repo: Path,
    relative: str,
    *,
    label: str,
    require_exists: bool = True,
    designated_prefix: str | None = None,
) -> Path:
    """Reject lexical and resolved escapes, including redirected parents."""
    if not relative or "\\" in relative or ":" in relative or re.search(r"(?:^|/)\.{1,2}(?:/|$)", relative):
        raise SystemExit(f"{label} is not a canonical repository-relative POSIX path: {relative!r}")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise SystemExit(f"{label} contains an absolute or dot-segment path: {relative!r}")
    if (
        designated_prefix
        and relative != designated_prefix
        and not relative.startswith(designated_prefix.rstrip("/") + "/")
    ):
        raise SystemExit(f"{label} is outside {designated_prefix}: {relative!r}")
    candidate = repo.joinpath(*pure.parts)
    current = repo
    for part in pure.parts:
        current = current / part
        if (current.exists() or current.is_symlink()) and (current.is_symlink() or is_junction(current)):
            raise SystemExit(f"{label} traverses a symlink or junction: {relative!r}")
    try:
        candidate.resolve(strict=False).relative_to(repo.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"{label} resolves outside the repository: {relative!r}") from exc
    if require_exists and not candidate.is_file():
        raise SystemExit(f"{label} does not name an existing regular file: {relative!r}")
    return candidate


def validate_scope_pattern(repo: Path, pattern: str) -> None:
    if "**" in pattern and not pattern.endswith("/**"):
        raise SystemExit(f"Authorized scope wildcard must be a terminal /**: {pattern}")
    lexical = pattern[:-3].rstrip("/") if pattern.endswith("/**") else pattern
    if "*" in lexical:
        raise SystemExit(f"Authorized scope contains an unsupported wildcard: {pattern}")
    safe_repo_path(repo, lexical, label="Authorized scope", require_exists=False)


def path_authorized(relative: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if relative == prefix or relative.startswith(prefix + "/"):
                return True
        elif relative == pattern:
            return True
    return False


def git_output(repo: Path, *arguments: str) -> str:
    result = subprocess.run(["git", *arguments], cwd=repo, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Git command failed: git {' '.join(arguments)}\n{result.stderr.strip()}")
    return result.stdout.strip()


def require_commit(repo: Path, commit: str, *, ancestor_of: str = "HEAD", label: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None or not taskctl.git_commit_exists(repo, commit):
        raise SystemExit(f"{label} is not an existing full Git commit: {commit}")
    if not taskctl.git_is_ancestor(repo, commit, ancestor_of):
        raise SystemExit(f"{label} is outside the required Git ancestry: {commit}")


def require_clean(repo: Path, *, allowed_untracked: set[str] | None = None) -> None:
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=repo, check=False).returncode != 0:
        raise SystemExit("Tracked worktree changes exist; recovery transitions require an exact clean commit")
    untracked = set(git_output(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    unexpected = sorted(untracked - (allowed_untracked or set()))
    if unexpected:
        raise SystemExit(f"Untracked source exists outside the authorized recovery transition: {unexpected[0]}")


def recovery_paths(repo: Path, request_id: str) -> tuple[Path, Path]:
    if re.fullmatch(r"GRR-[0-9]{4}", request_id) is None:
        raise SystemExit(f"Invalid recovery request identity: {request_id}")
    packet = safe_repo_path(
        repo,
        f"planning/governance-recovery-requests/{request_id}.packet.json",
        label="Recovery packet",
        designated_prefix="planning/governance-recovery-requests",
    )
    approval = safe_repo_path(
        repo,
        f"planning/governance-recovery-approvals/{request_id}.json",
        label="Recovery approval",
        designated_prefix="planning/governance-recovery-approvals",
    )
    return packet, approval


def recovery_identity_errors(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    request_id = str(packet.get("recoveryRequestId") or "")
    wave_id = str(packet.get("targetWave") or "")
    chain = packet.get("authorityChain") or {}
    wave_base = chain.get("waveBase") or {}
    amendments = chain.get("orderedAmendments") or []
    hold_id = str((packet.get("controlHold") or {}).get("id") or "")
    bootstrap_id = str((packet.get("bootstrapUnit") or {}).get("id") or "")
    post = packet.get("postBootstrap") or {}
    amendment_id = str(post.get("requiredAmendmentId") or "")
    task_ids = [str(item) for item in post.get("requiredProposedTaskIds", [])]
    if wave_base.get("waveId") != wave_id:
        errors.append("recovery target Wave differs from the authority-chain base Wave")
    if hold_id != f"HOLD-{wave_id}-{request_id}":
        errors.append("recovery hold identity is not bound to the target Wave and request")
    if bootstrap_id != f"{request_id}.B00":
        errors.append("recovery bootstrap identity is outside the request namespace")
    expected_predecessors = [f"{wave_id}.A{index:02d}" for index in range(1, len(amendments) + 1)]
    actual_predecessors = [str((item or {}).get("id")) for item in amendments]
    if actual_predecessors != expected_predecessors or len(actual_predecessors) != len(set(actual_predecessors)):
        errors.append("recovery predecessor amendment identities are gapped, reordered, duplicated, or cross-Wave")
    if amendment_id != f"{wave_id}.A{len(amendments) + 1:02d}":
        errors.append("recovery post-bootstrap amendment is not the next consecutive identity")
    prior_ecr_numbers = [
        int(str((item or {}).get("changeRequestId")).removeprefix("ECR-"))
        for item in amendments
        if re.fullmatch(r"ECR-[0-9]{4}", str((item or {}).get("changeRequestId") or ""))
    ]
    if post.get("requiredChangeRequestId") != f"ECR-{max(prior_ecr_numbers, default=0) + 1:04d}":
        errors.append("recovery post-bootstrap ECR is not the next consecutive identity")
    expected_tasks = [f"{amendment_id}.T{index:02d}" for index in range(1, len(task_ids) + 1)]
    if not task_ids or task_ids != expected_tasks:
        errors.append("recovery proposed task identities are not exact, ordered, and amendment-bound")
    if (
        post.get("postBootstrapExecutionAuthority") is not False
        or post.get("ordinaryWaveResumeAuthorized") is not False
    ):
        errors.append("recovery packet grants unauthorized post-bootstrap execution or Wave resume authority")
    return errors


def load_recovery_authority(repo: Path, request_id: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    packet_path, approval_path = recovery_paths(repo, request_id)
    packet, packet_payload = load_json(packet_path, "recovery packet")
    approval, approval_payload = load_json(approval_path, "recovery approval")
    schema_relative = str(packet.get("$schema") or "")
    if schema_relative == "./governance-recovery-request.schema.json":
        schema_name = "governance-recovery-request.schema.json"
    elif schema_relative == "./governance-recovery-request.v2.schema.json":
        schema_name = "governance-recovery-request.v2.schema.json"
    else:
        raise SystemExit(f"Unsupported recovery packet schema: {schema_relative}")
    schema_path = safe_repo_path(
        repo,
        f"planning/governance-recovery-requests/{schema_name}",
        label="Recovery packet schema",
        designated_prefix="planning/governance-recovery-requests",
    )
    errors = schema_errors(packet, schema_path)
    approval_schema = safe_repo_path(
        repo,
        "planning/governance-recovery-requests/governance-recovery-approval.schema.json",
        label="Recovery approval schema",
    )
    errors.extend(schema_errors(approval, approval_schema))
    if errors:
        raise SystemExit("Governance recovery schema validation failed:\n- " + "\n- ".join(errors))
    if packet.get("recoveryRequestId") != request_id or approval.get("recoveryRequestId") != request_id:
        raise SystemExit("Recovery packet/approval identity mismatch")
    if approval.get("status") != "APPROVED":
        raise SystemExit(f"{request_id} is not explicitly APPROVED")
    packet_reference = approval.get("packet") or {}
    packet_relative = f"planning/governance-recovery-requests/{request_id}.packet.json"
    if packet_reference.get("path") != packet_relative or packet_reference.get("sha256") != sha256(packet_payload):
        raise SystemExit("Recovery approval does not bind the exact packet path/hash")
    packet_commit = str(packet_reference.get("commit") or "")
    require_commit(repo, packet_commit, label="Recovery packet commit")
    if taskctl.git_blob(repo, packet_commit, packet_relative) != packet_payload:
        raise SystemExit("Recovery packet differs from the immutable approved Git blob")
    approval_relative = f"planning/governance-recovery-approvals/{request_id}.json"
    introduction = taskctl.approval_introduction_commit(repo, approval_relative)
    if not introduction:
        raise SystemExit("Recovery approval has no immutable introduction commit")
    require_commit(repo, introduction, label="Recovery approval introduction")
    if not taskctl.git_is_ancestor(repo, packet_commit, introduction):
        raise SystemExit("Recovery approval does not descend from its reviewed packet")
    if taskctl.git_blob(repo, introduction, approval_relative) != approval_payload:
        raise SystemExit("Recovery approval differs from its immutable introduction Git blob")
    if approval.get("targetWave") != packet.get("targetWave"):
        raise SystemExit("Recovery approval target Wave differs from the packet")
    identity_errors = recovery_identity_errors(packet)
    if identity_errors:
        raise SystemExit("Recovery identity validation failed:\n- " + "\n- ".join(identity_errors))
    execution = approval.get("executionAuthority") or {}
    if execution.get("bootstrapOnly") is not True or any(
        execution.get(field) is not False
        for field in ("postBootstrapExecution", "ordinaryWaveResume", "taskExecution", "releaseGateApproval")
    ):
        raise SystemExit("Recovery approval is not constrained to the bootstrap")
    review = approval.get("independentPacketReview") or {}
    if review.get("result") != "APPROVED" or review.get("candidateCommit") != packet_commit:
        raise SystemExit("Recovery approval lacks an exact-commit independent packet approval")
    if review.get("reviewer") == approval.get("approvedBy"):
        raise SystemExit("Recovery packet reviewer is not independent from the human approver")
    for pattern in (packet.get("bootstrapUnit") or {}).get("authorizedPaths", []):
        validate_scope_pattern(repo, str(pattern))
    for reference in packet.get("files", []):
        relative = str(reference.get("path") or "")
        path = safe_repo_path(repo, relative, label="Recovery packet file")
        payload = path.read_bytes()
        if sha256(payload) != reference.get("sha256"):
            raise SystemExit(f"Recovery packet file hash mismatch: {relative}")
        if taskctl.git_blob(repo, packet_commit, relative) != payload:
            raise SystemExit(f"Recovery packet file differs from approved Git blob: {relative}")
    return approval, packet, approval_payload, packet_payload


def backlog_state(
    repo: Path,
) -> tuple[bytes, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    path = repo / "planning" / "backlog.yaml"
    payload = path.read_bytes()
    data, capabilities, slices, tasks, gates = taskctl.load(str(path))
    return payload, data, capabilities, slices, tasks, gates


def recovery_hold(data: dict[str, Any], request_id: str) -> dict[str, Any]:
    matches = [
        hold
        for hold in (data.get("control_plane") or {}).get("recovery_holds", [])
        if hold.get("recovery_request_id") == request_id
    ]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one backlog recovery hold for {request_id}, found {len(matches)}")
    return matches[0]


def validate_authority_chain(repo: Path, packet: dict[str, Any], data: dict[str, Any]) -> None:
    chain = packet.get("authorityChain") or {}
    wave_id = str(packet.get("targetWave"))
    base = taskctl.wave_approval_base_map(data).get(wave_id) or {}
    packet_base = chain.get("waveBase") or {}
    if (
        packet_base.get("waveId") != wave_id
        or packet_base.get("packetCommit") != base.get("packet_commit")
        or packet_base.get("approvalRecordCommit") != base.get("record_commit")
    ):
        raise SystemExit("Recovery packet base-Wave authority differs from the backlog")
    actual = [item for item in data.get("wave_amendments", []) if item.get("target_wave") == wave_id]
    frozen = chain.get("orderedAmendments", [])
    if len(actual) < len(frozen):
        raise SystemExit("Recovery authority chain lost a frozen predecessor amendment")
    expected_ids = [f"{wave_id}.A{index:02d}" for index in range(1, len(frozen) + 1)]
    if [item.get("id") for item in frozen] != expected_ids:
        raise SystemExit("Recovery packet predecessor amendments are gapped, reordered, duplicated, or forked")
    for packet_item, backlog_item in zip(frozen, actual, strict=False):
        reference = backlog_item.get("approval_reference") or {}
        if (
            packet_item.get("id") != backlog_item.get("id")
            or packet_item.get("status") != "ADOPTED"
            or packet_item.get("approvalRecord", {}).get("path") != reference.get("path")
            or packet_item.get("approvalRecord", {}).get("sha256") != reference.get("sha256")
            or packet_item.get("approvalRecord", {}).get("introductionCommit") != reference.get("introduction_commit")
            or (backlog_item.get("lifecycle") or {}).get("status") != "ADOPTED"
        ):
            raise SystemExit(f"Frozen predecessor authority mismatch: {packet_item.get('id')}")
        for commit in (
            str(packet_item.get("packetCommit") or ""),
            str(packet_item.get("effectiveStateCommit") or ""),
            str((packet_item.get("approvalRecord") or {}).get("introductionCommit") or ""),
        ):
            require_commit(repo, commit, label=f"{packet_item.get('id')} authority commit")
    next_amendment = f"{wave_id}.A{len(frozen) + 1:02d}"
    if (packet.get("postBootstrap") or {}).get("requiredAmendmentId") != next_amendment:
        raise SystemExit("Recovery post-bootstrap amendment is not consecutive with the frozen predecessor chain")


def validate_request(
    repo: Path, request_id: str, *, require_approved: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    approval, packet, _approval_payload, _packet_payload = load_recovery_authority(repo, request_id)
    _payload, data, _capabilities, _slices, _tasks, _gates = backlog_state(repo)
    validate_authority_chain(repo, packet, data)
    hold = recovery_hold(data, request_id)
    errors = taskctl.recovery_hold_errors(data, repo)
    if errors:
        raise SystemExit("Invalid governance recovery hold:\n- " + "\n- ".join(errors))
    validate_bootstrap_history(repo, packet, approval, hold)
    if require_approved and approval.get("status") != "APPROVED":
        raise SystemExit(f"{request_id} is not approved")
    return approval, packet, hold


def save_backlog(repo: Path, payload: bytes, data: dict[str, Any]) -> None:
    path = repo / "planning" / "backlog.yaml"
    prior_data = yaml.safe_load(payload)
    taskctl.save_validated(
        str(path),
        data,
        expected_sha256=sha256(payload),
        expected_identity=taskctl.identity_snapshot(data),
        expected_amendment_identity=taskctl.amendment_identity_snapshot(data),
        expected_approved_waves=taskctl.approved_wave_snapshot(data),
        expected_amendment_history=taskctl.amendment_history_snapshot(data),
        expected_task_review_history=taskctl.task_review_history_snapshot(data),
        expected_wave_checkpoint_history=taskctl.wave_checkpoint_history_snapshot(data),
        expected_recovery_history=taskctl.recovery_history_snapshot(prior_data),
        repo=repo,
    )


def evidence_relative(repo: Path, value: str, request_id: str, bootstrap_id: str) -> tuple[str, Path]:
    raw = Path(value)
    path = raw if raw.is_absolute() else repo / raw
    try:
        relative = path.resolve(strict=False).relative_to(repo.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as exc:
        raise SystemExit("Recovery evidence must be inside the repository") from exc
    pattern = (
        rf"planning/governance-recovery-approvals/{re.escape(bootstrap_id)}"
        rf"(?:\.remediation-[0-9]{{2}})?\.evidence\.json"
    )
    if re.fullmatch(pattern, relative) is None:
        raise SystemExit(
            f"Recovery evidence must use the approved control-artifact path for {request_id}/{bootstrap_id}"
        )
    return relative, safe_repo_path(
        repo, relative, label="Recovery evidence", designated_prefix="planning/governance-recovery-approvals"
    )


def evidence_document(
    repo: Path,
    request_id: str,
    packet: dict[str, Any],
    approval: dict[str, Any],
    evidence_value: str,
    candidate: str,
    *,
    lineage_base: str | None = None,
    expected_branch: str | None = None,
    require_current_branch: bool = True,
) -> tuple[dict[str, Any], bytes, str]:
    bootstrap = packet.get("bootstrapUnit") or {}
    bootstrap_id = str(bootstrap.get("id"))
    relative, path = evidence_relative(repo, evidence_value, request_id, bootstrap_id)
    document, payload = load_json(path, "recovery bootstrap evidence")
    schema_path = repo / "planning" / "governance-recovery-requests" / "governance-recovery-evidence.schema.json"
    errors = schema_errors(document, schema_path)
    if errors:
        raise SystemExit("Recovery evidence schema validation failed:\n- " + "\n- ".join(errors))
    base = lineage_base or str((approval.get("packet") or {}).get("commit") or "")
    approval_intro = taskctl.approval_introduction_commit(
        repo, f"planning/governance-recovery-approvals/{request_id}.json"
    )
    first_submission = lineage_base is None
    expected_base = str(approval_intro) if first_submission else base
    if document.get("recoveryRequestId") != request_id or document.get("bootstrapUnit") != bootstrap_id:
        raise SystemExit("Recovery evidence request/bootstrap identity mismatch")
    if document.get("baseCommit") != expected_base or document.get("candidateCommit") != candidate:
        raise SystemExit("Recovery evidence base/candidate commit binding mismatch")
    declared_branch = str(document.get("branch") or "")
    if not declared_branch.startswith("codex/"):
        raise SystemExit("Recovery evidence must name a codex branch")
    if expected_branch is not None and declared_branch != expected_branch:
        raise SystemExit("Recovery evidence branch differs from the frozen submission branch")
    if require_current_branch and declared_branch != git_output(repo, "branch", "--show-current"):
        raise SystemExit("Recovery evidence must name the current codex branch")
    require_commit(repo, expected_base, ancestor_of=candidate, label="Recovery evidence base")
    require_commit(repo, candidate, label="Recovery evidence candidate")
    actual_paths = sorted(
        line
        for line in git_output(repo, "diff", "--name-only", f"{expected_base}..{candidate}", "--").splitlines()
        if line
    )
    declared_paths = sorted(str(item) for item in document.get("changedPaths", []))
    if declared_paths != actual_paths:
        raise SystemExit("Recovery evidence changedPaths differs from the exact Git diff")
    patterns = [str(item) for item in bootstrap.get("authorizedPaths", [])]
    for changed in actual_paths:
        safe_repo_path(repo, changed, label="Changed recovery path", require_exists=False)
        if not path_authorized(changed, patterns):
            raise SystemExit(f"Recovery candidate changed a path outside the approved bootstrap scope: {changed}")
    required_outcomes = [item.get("criterion") for item in document.get("requiredOutcomes", [])]
    if required_outcomes != bootstrap.get("requiredOutcomes"):
        raise SystemExit("Recovery evidence does not map every required outcome exactly and in order")
    criteria = [item.get("criterion") for item in document.get("acceptanceCriteria", [])]
    if criteria != packet.get("acceptanceCriteria"):
        raise SystemExit("Recovery evidence does not map every acceptance criterion exactly and in order")
    if document.get("unverifiedItems") != []:
        raise SystemExit("Recovery bootstrap evidence may not retain unverified items")
    commands = [str(item.get("command")) for item in document.get("checks", [])]
    if len(commands) != len(set(commands)) or any(
        item.get("result") != "passed" for item in document.get("checks", [])
    ):
        raise SystemExit("Recovery evidence checks must be unique and passing")
    return document, payload, relative


def validate_bootstrap_history(
    repo: Path,
    packet: dict[str, Any],
    approval: dict[str, Any],
    hold: dict[str, Any],
) -> None:
    """Revalidate every frozen evidence/ledger pair and its live projection."""
    bootstrap = hold.get("bootstrap") or {}
    bootstrap_id = str(bootstrap.get("id") or "")
    attempts = bootstrap.get("attempts") or []
    prior_candidate: str | None = None
    prior_open: set[str] = set()
    blocking_ids: set[str] = set()
    for attempt in attempts:
        attempt_id = str(attempt.get("id") or "")
        candidate = str(attempt.get("implementation_commit") or "")
        branch = str(attempt.get("submission_branch") or "")
        evidence = attempt.get("evidence") or {}
        if evidence.get("commit") != candidate:
            raise SystemExit(f"{bootstrap_id}/{attempt_id} evidence commit differs from its frozen candidate")
        _document, evidence_payload, evidence_path = evidence_document(
            repo,
            str(packet.get("recoveryRequestId")),
            packet,
            approval,
            str(evidence.get("path") or ""),
            candidate,
            lineage_base=prior_candidate,
            expected_branch=branch,
            require_current_branch=False,
        )
        if evidence.get("path") != evidence_path or evidence.get("sha256") != sha256(evidence_payload):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} frozen evidence reference does not match its file")
        expected_ledger = f"planning/governance-recovery-approvals/{bootstrap_id}.review-{attempt_id}.json"
        ledger_reference = attempt.get("ledger") or {}
        if ledger_reference.get("path") != expected_ledger:
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review ledger path is not canonical")
        ledger_path = safe_repo_path(
            repo,
            expected_ledger,
            label=f"{bootstrap_id}/{attempt_id} review ledger",
            designated_prefix="planning/governance-recovery-approvals",
        )
        ledger, ledger_payload = load_json(ledger_path, "recovery review ledger")
        if ledger_reference.get("sha256") != sha256(ledger_payload):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review ledger hash mismatch")
        review = attempt.get("review") or {}
        reviewer = taskctl.normalized_identity(str(ledger.get("reviewer") or ""), "Recovery bootstrap reviewer")
        result = str(ledger.get("result") or "")
        expected_fields = {
            "schemaVersion": "1.0",
            "documentType": "governance-recovery-bootstrap-review",
            "recoveryRequestId": packet.get("recoveryRequestId"),
            "bootstrapUnit": bootstrap_id,
            "attemptId": attempt_id,
            "candidateCommit": candidate,
            "reviewer": reviewer,
            "result": result,
            "evidence": {"path": evidence_path, "sha256": sha256(evidence_payload)},
        }
        if any(ledger.get(field) != expected for field, expected in expected_fields.items()):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review ledger differs from the frozen attempt")
        reviewed_state = str(ledger.get("reviewedStateCommit") or "")
        require_commit(repo, reviewed_state, label=f"{bootstrap_id}/{attempt_id} reviewed state")
        if reviewer == attempt.get("implementer") or reviewer != review.get("reviewer"):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review independence or reviewer projection is invalid")
        if result not in REVIEW_RESULTS or result != review.get("result"):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review result projection is invalid")
        findings = ledger.get("findings")
        closures = ledger.get("closures")
        if not isinstance(findings, list) or not isinstance(closures, list):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review findings/closures are invalid")
        closure_ids = {str(item.get("findingId") or "") for item in closures if isinstance(item, dict)}
        if len(closure_ids) != len(closures) or not closure_ids.issubset(prior_open):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review closures are not append-only and valid")
        finding_ids = {str(item.get("id") or "") for item in findings if isinstance(item, dict)}
        if len(finding_ids) != len(findings) or "" in finding_ids:
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review findings are invalid or duplicated")
        prior_open = (prior_open - closure_ids) | finding_ids
        blocking_ids.update(
            str(item.get("id")) for item in findings if isinstance(item, dict) and item.get("blocking") is True
        )
        if result == "approved" and prior_open & blocking_ids:
            raise SystemExit(f"{bootstrap_id}/{attempt_id} approval retains open blocking findings")
        prior_candidate = candidate
    status = str(bootstrap.get("status") or "")
    if attempts and status != "REVIEW":
        last = attempts[-1]
        last_review = last.get("review") or {}
        if status != REVIEW_RESULTS.get(str(last_review.get("result") or "")):
            raise SystemExit(f"{bootstrap_id} status is not the last immutable review disposition")
        for field in ("implementation_commit", "submission_branch", "evidence", "review"):
            if bootstrap.get(field) != last.get(field):
                raise SystemExit(f"{bootstrap_id} {field} projection differs from its last immutable attempt")
    current = bootstrap.get("current_submission")
    if status == "REVIEW" and current:
        candidate = str(current.get("candidate_commit") or "")
        evidence = bootstrap.get("evidence") or {}
        lineage_base = str(attempts[-1].get("implementation_commit")) if attempts else None
        _document, evidence_payload, evidence_path = evidence_document(
            repo,
            str(packet.get("recoveryRequestId")),
            packet,
            approval,
            str(evidence.get("path") or ""),
            candidate,
            lineage_base=lineage_base,
            expected_branch=str(bootstrap.get("submission_branch") or ""),
            require_current_branch=True,
        )
        if (
            evidence.get("path") != evidence_path
            or evidence.get("sha256") != sha256(evidence_payload)
            or evidence.get("commit") != candidate
            or current.get("evidence_sha256") != sha256(evidence_payload)
            or current.get("acceptance_criteria_sha256") != canonical_json_sha256(packet.get("acceptanceCriteria", []))
        ):
            raise SystemExit(f"{bootstrap_id} current submission differs from its frozen evidence")


def command_validate(args: argparse.Namespace) -> None:
    approval, packet, hold = validate_request(args.repo, args.request, require_approved=args.require_approved)
    print(
        f"Valid {args.request}: packet={(approval.get('packet') or {}).get('commit')}; "
        f"bootstrap={(hold.get('bootstrap') or {}).get('status')}; hold={hold.get('status')}; "
        f"next={(packet.get('postBootstrap') or {}).get('requiredAmendmentId')}"
    )


def command_status(args: argparse.Namespace) -> None:
    _approval, packet, hold = validate_request(args.repo, args.request)
    bootstrap = hold.get("bootstrap") or {}
    post = packet.get("postBootstrap") or {}
    print(
        yaml.safe_dump(
            {
                "recoveryRequest": args.request,
                "hold": hold.get("id"),
                "holdStatus": hold.get("status"),
                "bootstrap": {"id": bootstrap.get("id"), "status": bootstrap.get("status")},
                "postBootstrap": post,
                "executionAuthority": "bootstrap-only; separate ECR approval required",
            },
            sort_keys=False,
        ).rstrip()
    )


def freeze_submission(args: argparse.Namespace, *, remediation: bool) -> None:
    approval, packet, hold = validate_request(args.repo, args.request)
    bootstrap = hold.get("bootstrap") or {}
    expected_status = {"CHANGES_REQUESTED", "BLOCKED"} if remediation else {"IN_PROGRESS"}
    if bootstrap.get("status") not in expected_status:
        raise SystemExit(f"Bootstrap {bootstrap.get('id')} is not eligible for this submission transition")
    candidate = str(args.implementation_commit)
    head = git_output(args.repo, "rev-parse", "HEAD")
    if candidate != head:
        raise SystemExit("Recovery implementation commit must equal current HEAD")
    agent = taskctl.normalized_identity(args.agent, "Recovery bootstrap implementer")
    if agent != bootstrap.get("implementer"):
        raise SystemExit("Recovery bootstrap implementer must retain the approved hold identity")
    prior_candidate: str | None = str(bootstrap.get("implementation_commit") or "") if remediation else None
    if remediation:
        assert prior_candidate is not None
        require_commit(args.repo, prior_candidate, ancestor_of=candidate, label="Prior recovery candidate")
        if prior_candidate == candidate:
            raise SystemExit("Recovery remediation must be a strict descendant of the prior candidate")
    bootstrap_id = str(bootstrap.get("id"))
    expected_name = (
        f"planning/governance-recovery-approvals/{bootstrap_id}.remediation-"
        f"{len(bootstrap.get('attempts') or []):02d}.evidence.json"
        if remediation
        else f"planning/governance-recovery-approvals/{bootstrap_id}.evidence.json"
    )
    provided = Path(args.evidence)
    provided_relative = (
        provided.resolve(strict=False).relative_to(args.repo.resolve(strict=True)).as_posix()
        if provided.is_absolute()
        else provided.as_posix()
    )
    if provided_relative != expected_name:
        raise SystemExit(f"Recovery evidence path must be {expected_name}")
    require_clean(args.repo, allowed_untracked={expected_name})
    document, evidence_payload, relative = evidence_document(
        args.repo,
        args.request,
        packet,
        approval,
        args.evidence,
        candidate,
        lineage_base=prior_candidate,
    )
    backlog_payload, data, _capabilities, _slices, _tasks, _gates = backlog_state(args.repo)
    mutable_hold = recovery_hold(data, args.request)
    mutable_bootstrap = mutable_hold["bootstrap"]
    attempt_id = f"R{len(mutable_bootstrap.get('attempts') or []) + 1:02d}"
    evidence_reference = {
        "type": "governance-recovery-evidence",
        "path": relative,
        "sha256": sha256(evidence_payload),
        "commit": candidate,
        "recorded_at": taskctl.utc_now(),
    }
    mutable_bootstrap.update(
        status="REVIEW",
        implementation_commit=candidate,
        submission_branch=document.get("branch"),
        evidence=evidence_reference,
        review={"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
        current_submission={
            "attempt_id": attempt_id,
            "candidate_commit": candidate,
            "evidence_sha256": sha256(evidence_payload),
            "acceptance_criteria_sha256": canonical_json_sha256(packet.get("acceptanceCriteria", [])),
        },
    )
    save_backlog(args.repo, backlog_payload, data)
    print(f"Submitted {bootstrap_id} {attempt_id} for independent control/security review")


def review_ledger(
    args: argparse.Namespace,
    packet: dict[str, Any],
    bootstrap: dict[str, Any],
) -> tuple[dict[str, Any], bytes, str]:
    current = bootstrap.get("current_submission") or {}
    attempt_id = str(current.get("attempt_id") or "")
    expected_relative = f"planning/governance-recovery-approvals/{bootstrap.get('id')}.review-{attempt_id}.json"
    value = Path(args.from_path)
    relative = (
        value.resolve(strict=False).relative_to(args.repo.resolve(strict=True)).as_posix()
        if value.is_absolute()
        else value.as_posix()
    )
    if relative != expected_relative:
        raise SystemExit(f"Recovery review ledger path must be {expected_relative}")
    path = safe_repo_path(
        args.repo, relative, label="Recovery review ledger", designated_prefix="planning/governance-recovery-approvals"
    )
    ledger, payload = load_json(path, "recovery review ledger")
    required = {
        "schemaVersion": "1.0",
        "documentType": "governance-recovery-bootstrap-review",
        "recoveryRequestId": args.request,
        "bootstrapUnit": bootstrap.get("id"),
        "attemptId": attempt_id,
        "candidateCommit": current.get("candidate_commit"),
        "reviewedStateCommit": git_output(args.repo, "rev-parse", "HEAD"),
    }
    for field, expected in required.items():
        if ledger.get(field) != expected:
            raise SystemExit(f"Recovery review ledger {field} differs from the frozen submission")
    reviewer = taskctl.normalized_identity(str(ledger.get("reviewer") or ""), "Recovery bootstrap reviewer")
    cli_reviewer = taskctl.normalized_identity(args.reviewer, "Recovery bootstrap reviewer")
    if reviewer != cli_reviewer:
        raise SystemExit("Recovery review ledger reviewer must equal the CLI review actor")
    if reviewer == bootstrap.get("implementer"):
        raise SystemExit("Recovery bootstrap reviewer must be independent from the implementer")
    result = str(ledger.get("result") or "")
    if result not in REVIEW_RESULTS:
        raise SystemExit("Recovery review result must be approved, changes-requested, or blocked")
    evidence = ledger.get("evidence") or {}
    reference = bootstrap.get("evidence") or {}
    if evidence != {"path": reference.get("path"), "sha256": reference.get("sha256")}:
        raise SystemExit("Recovery review ledger evidence binding differs from the frozen evidence")
    findings = ledger.get("findings")
    closures = ledger.get("closures")
    if not isinstance(findings, list) or not isinstance(closures, list):
        raise SystemExit("Recovery review ledger requires findings and closures arrays")
    ordering = [SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings if isinstance(item, dict)]
    if len(ordering) != len(findings) or ordering != sorted(ordering):
        raise SystemExit("Recovery findings must be valid and severity-ranked")
    finding_ids: set[str] = set()
    for finding in findings:
        finding_id = str(finding.get("id") or "")
        criterion_index = finding.get("criterionIndex")
        if (
            not finding_id
            or finding_id in finding_ids
            or type(finding.get("blocking")) is not bool
            or type(criterion_index) is not int
            or not 1 <= criterion_index <= len(packet.get("acceptanceCriteria", []))
            or not str(finding.get("title") or "").strip()
            or not str(finding.get("reproduction") or "").strip()
            or not str(finding.get("requiredRemediation") or "").strip()
        ):
            raise SystemExit("Recovery review ledger contains an invalid or duplicate finding")
        finding_ids.add(finding_id)
    prior_open: set[str] = set()
    for attempt in bootstrap.get("attempts", []):
        prior_ledger, _ = load_json(args.repo / (attempt.get("ledger") or {}).get("path", ""), "prior recovery review")
        for closure in prior_ledger.get("closures", []):
            prior_open.discard(str(closure.get("findingId")))
        prior_open.update(str(item.get("id")) for item in prior_ledger.get("findings", []))
    closure_ids = [str(item.get("findingId") or "") for item in closures if isinstance(item, dict)]
    if (
        len(closure_ids) != len(closures)
        or len(closure_ids) != len(set(closure_ids))
        or not set(closure_ids).issubset(prior_open)
    ):
        raise SystemExit("Recovery review closures must target unique prior open findings")
    open_after = (prior_open - set(closure_ids)) | finding_ids
    blocking_ids = {str(item.get("id")) for item in findings if item.get("blocking") is True}
    for attempt in bootstrap.get("attempts", []):
        prior_ledger, _ = load_json(args.repo / (attempt.get("ledger") or {}).get("path", ""), "prior recovery review")
        blocking_ids.update(str(item.get("id")) for item in prior_ledger.get("findings", []) if item.get("blocking"))
    if result == "approved" and open_after & blocking_ids:
        raise SystemExit("Recovery bootstrap cannot be approved with open blocking findings")
    if result == "approved" and findings:
        raise SystemExit("An approved recovery disposition must not introduce new findings")
    return ledger, payload, relative


def command_bootstrap_review(args: argparse.Namespace) -> None:
    _approval, packet, hold = validate_request(args.repo, args.request)
    bootstrap = hold.get("bootstrap") or {}
    if bootstrap.get("status") != "REVIEW" or not bootstrap.get("current_submission"):
        raise SystemExit("Recovery bootstrap is not awaiting independent review")
    expected_relative = (
        f"planning/governance-recovery-approvals/{bootstrap.get('id')}.review-"
        f"{bootstrap['current_submission']['attempt_id']}.json"
    )
    require_clean(args.repo, allowed_untracked={expected_relative})
    ledger, ledger_payload, relative = review_ledger(args, packet, bootstrap)
    backlog_payload, data, _capabilities, _slices, _tasks, _gates = backlog_state(args.repo)
    mutable = recovery_hold(data, args.request)["bootstrap"]
    result = str(ledger["result"])
    review = {
        "reviewer": str(ledger["reviewer"]),
        "result": result,
        "reviewed_at": taskctl.utc_now(),
        "notes": str(ledger.get("notes") or ""),
    }
    mutable.setdefault("attempts", []).append(
        {
            "id": mutable["current_submission"]["attempt_id"],
            "implementer": mutable["implementer"],
            "implementation_commit": mutable["implementation_commit"],
            "submission_branch": mutable["submission_branch"],
            "evidence": copy.deepcopy(mutable["evidence"]),
            "review": review,
            "ledger": {"path": relative, "sha256": sha256(ledger_payload)},
        }
    )
    mutable["status"] = REVIEW_RESULTS[result]
    mutable["review"] = review
    mutable["current_submission"] = None
    save_backlog(args.repo, backlog_payload, data)
    print(f"Recovery bootstrap review {mutable['attempts'][-1]['id']}: {mutable['status']}")


def command_release(args: argparse.Namespace) -> None:
    _approval, packet, hold = validate_request(args.repo, args.request)
    if (hold.get("bootstrap") or {}).get("status") != "APPROVED":
        raise SystemExit("Recovery hold release requires independent bootstrap approval")
    amendment_id = str((packet.get("postBootstrap") or {}).get("requiredAmendmentId"))
    backlog_payload, data, _capabilities, _slices, _tasks, _gates = backlog_state(args.repo)
    amendment = taskctl.wave_amendment_map(data).get(amendment_id)
    if not amendment or (amendment.get("lifecycle") or {}).get("status") != "ADOPTED":
        raise SystemExit(f"Recovery hold release requires adopted {amendment_id}")
    if (amendment.get("completion") or {}).get("status") != "APPROVED":
        raise SystemExit(f"Recovery hold release requires independently approved {amendment_id} completion")
    wave = taskctl.wave_map(data).get(str(hold.get("target_wave"))) or {}
    actor = taskctl.normalized_identity(args.agent, "Recovery release actor")
    if actor != (wave.get("campaign") or {}).get("owner"):
        raise SystemExit("Recovery hold release actor must own the paused target Wave campaign")
    checkpoints = [
        checkpoint
        for checkpoint in wave.get("checkpoints", [])
        if checkpoint.get("kind") == "security"
        and any(
            isinstance(reference, dict) and reference.get("amendment_id") == amendment_id
            for reference in checkpoint.get("evidence", [])
        )
    ]
    if not checkpoints:
        raise SystemExit(f"Recovery hold release requires a bound {amendment_id} control/security checkpoint")
    require_clean(args.repo)
    mutable = recovery_hold(data, args.request)
    mutable["status"] = "RELEASED"
    mutable["released_at"] = taskctl.utc_now()
    save_backlog(args.repo, backlog_payload, data)
    print(f"Released {mutable['id']}; {hold.get('target_wave')} remains PAUSED pending explicit ordinary resume")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("request")
    validate.add_argument("--require-approved", action="store_true")
    status = sub.add_parser("status")
    status.add_argument("request")
    submit = sub.add_parser("bootstrap-submit")
    submit.add_argument("request")
    submit.add_argument("--agent", required=True)
    submit.add_argument("--implementation-commit", required=True)
    submit.add_argument("--evidence", required=True)
    resubmit = sub.add_parser("bootstrap-resubmit")
    resubmit.add_argument("request")
    resubmit.add_argument("--agent", required=True)
    resubmit.add_argument("--implementation-commit", required=True)
    resubmit.add_argument("--evidence", required=True)
    review = sub.add_parser("bootstrap-review")
    review.add_argument("request")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--from", dest="from_path", required=True)
    release = sub.add_parser("release")
    release.add_argument("request")
    release.add_argument("--agent", required=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.repo = args.repo.resolve(strict=True)
    if not (args.repo / ".git").exists():
        parser.error(f"Not a Git repository: {args.repo}")
    if args.command == "validate":
        command_validate(args)
    elif args.command == "status":
        command_status(args)
    elif args.command == "bootstrap-submit":
        freeze_submission(args, remediation=False)
    elif args.command == "bootstrap-resubmit":
        freeze_submission(args, remediation=True)
    elif args.command == "bootstrap-review":
        if taskctl.normalized_identity(args.reviewer, "Recovery bootstrap reviewer") == "":
            raise SystemExit("Recovery bootstrap reviewer is required")
        command_bootstrap_review(args)
    elif args.command == "release":
        taskctl.normalized_identity(args.agent, "Recovery release actor")
        command_release(args)
    else:
        parser.error("Unsupported recovery command")


if __name__ == "__main__":
    main()
