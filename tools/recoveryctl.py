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
import fnmatch
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
CONTROL_RECOVERY_TRIGGER_PATH = "artifacts/evidence/W1.A04.B00.json"
CONTROL_RECOVERY_TRIGGER_SHA256 = "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c"
CONTROL_RECOVERY_STATE_PATH = "planning/governance-control-recovery/GCR-0001.B00.state.json"


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
    if pure.is_absolute() or relative != pure.as_posix() or any(part in {"", ".", ".."} for part in pure.parts):
        raise SystemExit(f"{label} contains an absolute or noncanonical path: {relative!r}")
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
    filename_glob = not pattern.endswith("/**") and pattern.count("*") == 1
    pure_pattern = PurePosixPath(pattern)
    if filename_glob and "*" not in pure_pattern.name:
        raise SystemExit(f"Authorized wildcard must remain within the final filename: {pattern}")
    lexical = (
        pattern[:-3].rstrip("/")
        if pattern.endswith("/**")
        else pattern.replace("*", "scope-marker")
        if filename_glob
        else pattern
    )
    if "*" in lexical or ("*" in pattern and not (pattern.endswith("/**") or filename_glob)):
        raise SystemExit(f"Authorized scope contains an unsupported wildcard: {pattern}")
    safe_repo_path(repo, lexical, label="Authorized scope", require_exists=False)


def path_authorized(relative: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if relative == prefix or relative.startswith(prefix + "/"):
                return True
        elif pattern.count("*") == 1 and "*" in PurePosixPath(pattern).name:
            pattern_path = PurePosixPath(pattern)
            relative_path = PurePosixPath(relative)
            if relative_path.parent == pattern_path.parent and fnmatch.fnmatchcase(
                relative_path.name, pattern_path.name
            ):
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


def require_supplement_workspace(
    repo: Path,
    packet: dict[str, Any],
    *,
    transition_untracked: set[str] | None = None,
) -> None:
    """Require the exact workspace authorized for one supplement transition.

    The v2 lane is created by GCR-0001 while its atomic W1.A04 failure witness
    deliberately remains untracked, unstaged, and non-authoritative. Every v2
    transition must authenticate that one witness and, when applicable,
    exactly one canonical evidence or review artifact. Legacy v1 supplement
    history retains its original clean-workspace contract.
    """

    allowed_transition = set(transition_untracked or set())
    if packet.get("schemaVersion") != "2.0-recovery-supplement-proposal":
        require_clean(repo, allowed_untracked=allowed_transition)
        return
    if CONTROL_RECOVERY_TRIGGER_PATH in allowed_transition:
        raise SystemExit("The GCR trigger witness cannot be used as a supplement transition artifact")

    staged = set(git_output(repo, "diff", "--cached", "--name-only", "--").splitlines())
    if staged:
        if CONTROL_RECOVERY_TRIGGER_PATH in staged:
            raise SystemExit("The GCR trigger witness must remain unstaged")
        raise SystemExit(f"Staged source exists outside the authorized recovery transition: {sorted(staged)[0]}")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=repo, check=False).returncode != 0:
        raise SystemExit("Tracked worktree changes exist; recovery transitions require an exact clean commit")

    witness_path = safe_repo_path(
        repo,
        CONTROL_RECOVERY_TRIGGER_PATH,
        label="GCR trigger witness",
        designated_prefix="artifacts/evidence",
    )
    if sha256(witness_path.read_bytes()) != CONTROL_RECOVERY_TRIGGER_SHA256:
        raise SystemExit("The GCR trigger witness hash differs from its approved atomic-failure boundary")
    state_path = safe_repo_path(
        repo,
        CONTROL_RECOVERY_STATE_PATH,
        label="GCR canonical state",
        designated_prefix="planning/governance-control-recovery",
    )
    state, _state_payload = load_json(state_path, "GCR canonical state")
    expected_witness = {
        "path": CONTROL_RECOVERY_TRIGGER_PATH,
        "sha256": CONTROL_RECOVERY_TRIGGER_SHA256,
        "role": "atomic-failure-trigger-only",
        "untracked": True,
        "unstaged": True,
        "executionAuthority": False,
    }
    if state.get("triggerWitness") != expected_witness:
        raise SystemExit("The GCR trigger witness is missing its exact non-authoritative state binding")

    expected_untracked = {CONTROL_RECOVERY_TRIGGER_PATH, *allowed_transition}
    untracked = set(git_output(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    if untracked != expected_untracked:
        difference = sorted(untracked ^ expected_untracked)
        raise SystemExit(
            "Supplement recovery untracked-path boundary differs: " + (difference[0] if difference else "<unknown>")
        )


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


def supplement_paths(repo: Path, supplement_id: str) -> tuple[Path, Path]:
    match = re.fullmatch(r"(GRR-[0-9]{4})\.S([0-9]{2})", supplement_id)
    if match is None:
        raise SystemExit(f"Invalid recovery supplement identity: {supplement_id}")
    packet = safe_repo_path(
        repo,
        f"planning/governance-recovery-requests/{supplement_id}.packet.json",
        label="Recovery supplement packet",
        designated_prefix="planning/governance-recovery-requests",
    )
    approval = safe_repo_path(
        repo,
        f"planning/governance-recovery-approvals/{supplement_id}.json",
        label="Recovery supplement approval",
        designated_prefix="planning/governance-recovery-approvals",
    )
    return packet, approval


def exact_file_reference(
    repo: Path,
    reference: dict[str, Any],
    *,
    commit: str,
    label: str,
) -> bytes:
    relative = str(reference.get("path") or "")
    path = safe_repo_path(repo, relative, label=label)
    payload = path.read_bytes()
    if reference.get("sha256") != sha256(payload):
        raise SystemExit(f"{label} hash mismatch: {relative}")
    if taskctl.git_blob(repo, commit, relative) != payload:
        raise SystemExit(f"{label} differs from its immutable Git blob: {relative}")
    return payload


def load_supplement_authority(repo: Path, supplement_id: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    packet_path, approval_path = supplement_paths(repo, supplement_id)
    packet, packet_payload = load_json(packet_path, "recovery supplement packet")
    approval, approval_payload = load_json(approval_path, "recovery supplement approval")
    packet_schema_name = {
        "./governance-recovery-supplement.schema.json": "governance-recovery-supplement.schema.json",
        "./governance-recovery-supplement.v2.schema.json": "governance-recovery-supplement.v2.schema.json",
    }.get(str(packet.get("$schema") or ""))
    approval_schema_reference = str(approval.get("$schema") or "")
    approval_schema_name = None
    if approval_schema_reference == (
        "../governance-recovery-requests/governance-recovery-supplement-approval.schema.json"
    ):
        approval_schema_name = "governance-recovery-supplement-approval.schema.json"
    elif approval_schema_reference == (
        "../governance-recovery-requests/governance-recovery-supplement-approval.v2.schema.json"
    ):
        approval_schema_name = "governance-recovery-supplement-approval.v2.schema.json"
    if packet_schema_name is None or approval_schema_name is None:
        raise SystemExit("Unsupported recovery supplement packet or approval schema")
    packet_schema = safe_repo_path(
        repo,
        f"planning/governance-recovery-requests/{packet_schema_name}",
        label="Recovery supplement packet schema",
    )
    approval_schema = safe_repo_path(
        repo,
        f"planning/governance-recovery-requests/{approval_schema_name}",
        label="Recovery supplement approval schema",
    )
    errors = schema_errors(packet, packet_schema)
    errors.extend(schema_errors(approval, approval_schema))
    if errors:
        raise SystemExit("Governance recovery supplement schema validation failed:\n- " + "\n- ".join(errors))
    request_id = supplement_id.split(".", 1)[0]
    bootstrap = packet.get("supplementalBootstrap") or {}
    if (
        packet.get("documentType") != "governance-recovery-supplement-packet"
        or packet.get("recoveryRequestId") != request_id
        or packet.get("supplementId") != supplement_id
        or approval.get("recoveryRequestId") != request_id
        or approval.get("supplementId") != supplement_id
        or approval.get("status") != "APPROVED"
        or approval.get("targetWave") != packet.get("targetWave")
        or approval.get("supplementalBootstrapUnit") != bootstrap.get("id")
    ):
        raise SystemExit("Recovery supplement packet/approval identity or status mismatch")
    packet_relative = f"planning/governance-recovery-requests/{supplement_id}.packet.json"
    packet_reference = approval.get("packet") or {}
    if packet_reference.get("path") != packet_relative or packet_reference.get("sha256") != sha256(packet_payload):
        raise SystemExit("Recovery supplement approval does not bind the exact packet path/hash")
    packet_commit = str(packet_reference.get("commit") or "")
    require_commit(repo, packet_commit, label="Recovery supplement packet commit")
    if taskctl.git_blob(repo, packet_commit, packet_relative) != packet_payload:
        raise SystemExit("Recovery supplement packet differs from the immutable approved Git blob")
    approval_relative = f"planning/governance-recovery-approvals/{supplement_id}.json"
    approval_introduction = taskctl.approval_introduction_commit(repo, approval_relative)
    if not approval_introduction:
        raise SystemExit("Recovery supplement approval has no immutable introduction commit")
    require_commit(repo, approval_introduction, label="Recovery supplement approval introduction")
    if not taskctl.git_is_ancestor(repo, packet_commit, approval_introduction):
        raise SystemExit("Recovery supplement approval does not descend from its reviewed packet")
    if taskctl.git_blob(repo, approval_introduction, approval_relative) != approval_payload:
        raise SystemExit("Recovery supplement approval differs from its immutable introduction Git blob")
    review = approval.get("independentPacketReview") or {}
    if (
        review.get("result") != "APPROVED"
        or review.get("candidateCommit") != packet_commit
        or review.get("packetSha256") != sha256(packet_payload)
        or review.get("reviewer") == approval.get("approvedBy")
        or review.get("openFindingIds") != []
    ):
        raise SystemExit("Recovery supplement lacks an exact independent packet approval")
    prior = review.get("priorAdverseLedger") or {}
    if prior:
        prior_payload = exact_file_reference(
            repo,
            prior,
            commit=packet_commit,
            label="Recovery supplement prior adverse review",
        )
        prior_ledger = json.loads(prior_payload)
        prior_attempt = str(prior_ledger.get("attemptId") or "")
        expected_review_attempt = (
            f"R{int(prior_attempt.removeprefix('R')) + 1:02d}" if re.fullmatch(r"R[0-9]{2,}", prior_attempt) else ""
        )
        if (
            prior_ledger.get("result") not in {"changes-requested", "blocked"}
            or review.get("attemptId") != expected_review_attempt
            or sorted(review.get("closedFindingIds") or [])
            != sorted(str(item.get("id")) for item in prior_ledger.get("findings", []))
        ):
            raise SystemExit("Recovery supplement approval does not exactly close the prior adverse packet review")
    elif review.get("attemptId") != "R01" or review.get("closedFindingIds") != []:
        raise SystemExit("First-round recovery supplement approval has invalid review history")
    execution = approval.get("executionAuthority") or {}
    if execution.get("supplementalBootstrapOnly") is not True or any(
        execution.get(field) is not False
        for field in (
            "postBootstrapExecution",
            "amendmentMaterialization",
            "ordinaryWaveResume",
            "taskExecution",
            "releaseGateApproval",
        )
    ):
        raise SystemExit("Recovery supplement approval is not constrained to its supplemental bootstrap")
    for pattern in bootstrap.get("authorizedPaths", []):
        validate_scope_pattern(repo, str(pattern))
    for reference in packet.get("files", []):
        exact_file_reference(repo, reference, commit=packet_commit, label="Recovery supplement packet file")
    named_packet_files = {
        "proposal": (packet_reference.get("proposalPath"), packet_reference.get("proposalSha256")),
        "schema": (packet_reference.get("schemaPath"), packet_reference.get("schemaSha256")),
        "review": (packet_reference.get("reviewPath"), packet_reference.get("reviewSha256")),
    }
    packet_files = {str(item.get("path")): str(item.get("sha256")) for item in packet.get("files", [])}
    for label, (relative, digest) in named_packet_files.items():
        if packet_files.get(str(relative)) != digest:
            raise SystemExit(f"Recovery supplement approval {label} binding differs from the packet file ledger")
    base_approval, base_packet, base_approval_payload, base_packet_payload = load_recovery_authority(repo, request_id)
    base = packet.get("baseRecoveryAuthority") or {}
    base_packet_reference = base.get("packet") or {}
    base_approval_reference = base.get("approval") or {}
    base_approval_relative = f"planning/governance-recovery-approvals/{request_id}.json"
    base_intro = taskctl.approval_introduction_commit(repo, base_approval_relative)
    if (
        base_packet_reference.get("path") != f"planning/governance-recovery-requests/{request_id}.packet.json"
        or base_packet_reference.get("sha256") != sha256(base_packet_payload)
        or base_packet_reference.get("commit") != (base_approval.get("packet") or {}).get("commit")
        or base_approval_reference.get("path") != base_approval_relative
        or base_approval_reference.get("sha256") != sha256(base_approval_payload)
        or base_approval_reference.get("introductionCommit") != base_intro
        or base.get("holdId") != (base_packet.get("controlHold") or {}).get("id")
        or base.get("bootstrapUnit") != (base_packet.get("bootstrapUnit") or {}).get("id")
    ):
        raise SystemExit("Recovery supplement base authority differs from the approved recovery request")
    latest = base.get("latestApprovedReview") or {}
    latest_payload = exact_file_reference(
        repo,
        {"path": latest.get("path"), "sha256": latest.get("sha256")},
        commit=packet_commit,
        label="Recovery supplement base latest review",
    )
    latest_ledger = json.loads(latest_payload)
    if (
        latest_ledger.get("attemptId") != latest.get("attemptId")
        or latest_ledger.get("candidateCommit") != latest.get("candidateCommit")
        or latest_ledger.get("reviewedStateCommit") != latest.get("reviewedStateCommit")
        or latest_ledger.get("result") != "approved"
    ):
        raise SystemExit("Recovery supplement base latest review binding is stale or adverse")
    require_commit(repo, str(latest.get("candidateCommit") or ""), label="Recovery base bootstrap candidate")
    require_commit(repo, str(latest.get("reviewedStateCommit") or ""), label="Recovery base reviewed state")
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


def recovery_supplement(hold: dict[str, Any], supplement_id: str) -> dict[str, Any]:
    matches = [item for item in hold.get("supplements", []) if item.get("id") == supplement_id]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one backlog recovery supplement for {supplement_id}, found {len(matches)}")
    return matches[0]


def validate_supplement_boundary(
    repo: Path,
    packet: dict[str, Any],
    data: dict[str, Any],
    *,
    require_installed: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request_id = str(packet.get("recoveryRequestId") or "")
    supplement_id = str(packet.get("supplementId") or "")
    hold = recovery_hold(data, request_id)
    wave_id = str(packet.get("targetWave") or "")
    wave = taskctl.wave_map(data).get(wave_id) or {}
    amendment_reference = (packet.get("targetAmendmentAuthority") or {}).get("amendmentApproval") or {}
    amendment_id = str(amendment_reference.get("id") or "")
    amendment = taskctl.wave_amendment_map(data).get(amendment_id) or {}
    bootstrap = amendment.get("bootstrap") or {}
    activation = packet.get("activationBoundary") or {}
    blocked_task = taskctl.index_backlog(data)[3].get(str(activation.get("blockedTaskId") or "")) or {}
    installed = [item for item in hold.get("supplements", []) if item.get("id") == supplement_id]
    if packet.get("schemaVersion") == "2.0-recovery-supplement-proposal":
        validate_preappend_supplement_boundary(
            repo,
            packet,
            data,
            hold=hold,
            wave=wave,
            blocked_task=blocked_task,
            installed=installed,
            require_installed=require_installed,
        )
        return hold, {}
    exact_activation = (
        hold.get("id") != (packet.get("baseRecoveryAuthority") or {}).get("holdId")
        or hold.get("status") != activation.get("holdStatus")
        or (hold.get("bootstrap") or {}).get("status") != "APPROVED"
        or wave.get("id") != wave_id
        or (wave.get("campaign") or {}).get("status") != activation.get("waveStatus")
        or (wave.get("campaign") or {}).get("scope") != activation.get("waveScope")
        or amendment.get("id") != activation.get("amendmentId")
        or (amendment.get("lifecycle") or {}).get("status") != activation.get("amendmentLifecycle")
        or bootstrap.get("status") != activation.get("bootstrapStatus")
        or len(amendment.get("tasks") or []) != activation.get("materializedTaskCount")
        or blocked_task.get("status") != activation.get("blockedTaskStatus")
    )
    terminal_history = bool(
        require_installed
        and len(installed) == 1
        and ((installed[0].get("bootstrap") or {}).get("status")) == "APPROVED"
        and hold.get("id") == (packet.get("baseRecoveryAuthority") or {}).get("holdId")
        and hold.get("status") == "RELEASED"
        and (hold.get("bootstrap") or {}).get("status") == "APPROVED"
        and wave.get("id") == wave_id
        and (wave.get("campaign") or {}).get("status") == "PAUSED"
        and amendment.get("id") == activation.get("amendmentId")
        and (amendment.get("lifecycle") or {}).get("status") == "ADOPTED"
        and (amendment.get("completion") or {}).get("status") == "APPROVED"
    )
    if exact_activation and not terminal_history:
        raise SystemExit("Recovery supplement activation boundary differs from the stopped approved state")
    amendment_approval_path = str(amendment_reference.get("path") or "")
    amendment_approval = amendment.get("approval_reference") or {}
    if (
        amendment_approval_path != amendment_approval.get("path")
        or amendment_reference.get("sha256") != amendment_approval.get("sha256")
        or amendment_reference.get("introductionCommit") != amendment_approval.get("introduction_commit")
    ):
        raise SystemExit("Recovery supplement target amendment approval differs from the backlog")
    amendment_approval_file = safe_repo_path(repo, amendment_approval_path, label="Target amendment approval")
    amendment_approval_payload = amendment_approval_file.read_bytes()
    if sha256(amendment_approval_payload) != amendment_reference.get("sha256"):
        raise SystemExit("Recovery supplement target amendment approval hash mismatch")
    introduction = str(amendment_reference.get("introductionCommit") or "")
    require_commit(repo, introduction, label="Target amendment approval introduction")
    if taskctl.git_blob(repo, introduction, amendment_approval_path) != amendment_approval_payload:
        raise SystemExit("Recovery supplement target amendment approval differs from its introduction blob")
    target_bootstrap = (packet.get("targetAmendmentAuthority") or {}).get("bootstrap") or {}
    actual_evidence = (bootstrap.get("evidence") or [{}])[0]
    if (
        target_bootstrap.get("id") != bootstrap.get("id")
        or target_bootstrap.get("candidateCommit") != bootstrap.get("implementation_commit")
        or target_bootstrap.get("evidence", {}).get("path") != actual_evidence.get("path")
        or target_bootstrap.get("evidence", {}).get("sha256") != actual_evidence.get("sha256")
        or target_bootstrap.get("evidence", {}).get("commit") != actual_evidence.get("commit")
    ):
        raise SystemExit("Recovery supplement target amendment bootstrap authority differs from the backlog")
    for field in ("candidateCommit", "reviewedStateCommit", "approvedProjectionCommit"):
        require_commit(repo, str(target_bootstrap.get(field) or ""), label=f"Target amendment bootstrap {field}")
    ecr = (packet.get("targetAmendmentAuthority") or {}).get("changeRequestPacket") or {}
    ecr_relative = str(ecr.get("path") or "")
    ecr_path = safe_repo_path(
        repo,
        ecr_relative,
        label="Target ECR packet",
        designated_prefix="planning/enabler-change-requests",
    )
    ecr_payload = ecr_path.read_bytes()
    ecr_commit = str(ecr.get("commit") or "")
    require_commit(repo, ecr_commit, label="Target ECR packet commit")
    if sha256(ecr_payload) != ecr.get("sha256") or taskctl.git_blob(repo, ecr_commit, ecr_relative) != ecr_payload:
        raise SystemExit("Recovery supplement target ECR packet hash/blob mismatch")
    if require_installed and len(installed) != 1:
        raise SystemExit(f"Recovery supplement {supplement_id} is not installed in the active hold")
    if not require_installed and installed:
        raise SystemExit(f"Recovery supplement {supplement_id} is already installed")
    if not require_installed:
        trigger = packet.get("triggerEvidence") or {}
        backlog_payload = (repo / "planning" / "backlog.yaml").read_bytes()
        if sha256(backlog_payload) != trigger.get("backlogSha256"):
            raise SystemExit("Recovery supplement trigger backlog is stale; no transition was written")
    return hold, amendment


def validate_preappend_supplement_boundary(
    repo: Path,
    packet: dict[str, Any],
    data: dict[str, Any],
    *,
    hold: dict[str, Any],
    wave: dict[str, Any],
    blocked_task: dict[str, Any],
    installed: list[dict[str, Any]],
    require_installed: bool,
) -> None:
    """Validate a v2 supplement without fabricating the blocked amendment in backlog state."""
    activation = packet.get("activationBoundary") or {}
    transition = packet.get("controlTransition") or {}
    target = packet.get("targetAmendmentAuthority") or {}
    amendment_reference = target.get("amendmentApproval") or {}
    amendment_id = str(amendment_reference.get("id") or "")
    control = data.get("control_plane") or {}
    expected_revision_value = (
        transition.get("successorRevision") if require_installed else transition.get("predecessorRevision")
    )
    if not isinstance(expected_revision_value, int):
        raise SystemExit("Supplement control transition revision is missing or malformed")
    expected_revision = expected_revision_value
    exact = (
        hold.get("id") == (packet.get("baseRecoveryAuthority") or {}).get("holdId")
        and hold.get("status") == activation.get("holdStatus") == "ACTIVE"
        and (hold.get("bootstrap") or {}).get("status") == "APPROVED"
        and wave.get("id") == packet.get("targetWave")
        and (wave.get("campaign") or {}).get("status") == activation.get("waveStatus") == "PAUSED"
        and (wave.get("campaign") or {}).get("scope") == activation.get("waveScope") == "wave"
        and activation.get("amendmentBacklogStatus") == "ABSENT"
        and amendment_id not in taskctl.wave_amendment_map(data)
        and target.get("backlogPresence") is False
        and blocked_task.get("status") == activation.get("blockedTaskStatus") == "BLOCKED"
        and control.get("revision") == expected_revision
        and control.get("minimum_tool_revision") == expected_revision
    )
    if not exact:
        raise SystemExit("Recovery supplement activation boundary differs from the stopped pre-append state")
    if require_installed:
        if len(installed) != 1:
            raise SystemExit(f"Recovery supplement {packet.get('supplementId')} is not installed")
        installed_transition = installed[0]
        if installed_transition.get("predecessor_control_revision") != transition.get(
            "predecessorRevision"
        ) or installed_transition.get("successor_control_revision") != transition.get("successorRevision"):
            raise SystemExit("Installed recovery supplement transition differs from its exact packet")
    elif installed:
        raise SystemExit(f"Recovery supplement {packet.get('supplementId')} is already installed")

    approval_relative = str(amendment_reference.get("path") or "")
    approval_path = safe_repo_path(
        repo,
        approval_relative,
        label="Pre-append target amendment approval",
        designated_prefix="planning/wave-amendment-approvals",
    )
    approval_payload = approval_path.read_bytes()
    introduction = str(amendment_reference.get("introductionCommit") or "")
    require_commit(repo, introduction, label="Pre-append amendment approval introduction")
    if (
        sha256(approval_payload) != amendment_reference.get("sha256")
        or taskctl.git_blob(repo, introduction, approval_relative) != approval_payload
    ):
        raise SystemExit("Pre-append target amendment approval hash/blob mismatch")
    approval = json.loads(approval_payload)
    ecr = target.get("changeRequestPacket") or {}
    if (
        approval.get("status") != "APPROVED"
        or approval.get("amendmentId") != amendment_id
        or approval.get("changeRequestId") != ecr.get("id")
        or approval.get("targetWave") != packet.get("targetWave")
    ):
        raise SystemExit("Pre-append target amendment approval identity or status mismatch")

    ecr_relative = str(ecr.get("path") or "")
    ecr_path = safe_repo_path(
        repo,
        ecr_relative,
        label="Pre-append target ECR packet",
        designated_prefix="planning/enabler-change-requests",
    )
    ecr_payload = ecr_path.read_bytes()
    ecr_commit = str(ecr.get("commit") or "")
    require_commit(repo, ecr_commit, label="Pre-append target ECR packet commit")
    if (
        sha256(ecr_payload) != ecr.get("sha256")
        or taskctl.git_blob(repo, ecr_commit, ecr_relative) != ecr_payload
        or (approval.get("packet") or {}).get("commit") != ecr_commit
    ):
        raise SystemExit("Pre-append target ECR packet hash/blob/approval binding mismatch")

    bootstrap = target.get("bootstrap") or {}
    candidate = str(bootstrap.get("candidateCommit") or "")
    require_commit(repo, candidate, label="Pre-append amendment bootstrap candidate")
    evidence = bootstrap.get("evidence") or {}
    evidence_relative = str(evidence.get("path") or "")
    evidence_path = safe_repo_path(
        repo,
        evidence_relative,
        label="Pre-append amendment bootstrap evidence",
        designated_prefix="artifacts/evidence",
    )
    evidence_payload = evidence_path.read_bytes()
    evidence_document = json.loads(evidence_payload)
    if (
        evidence.get("commit") != candidate
        or sha256(evidence_payload) != evidence.get("sha256")
        or evidence_document.get("taskId") != bootstrap.get("id")
        or evidence_document.get("commit") != candidate
    ):
        raise SystemExit("Pre-append amendment bootstrap evidence identity/hash mismatch")
    if not require_installed:
        trigger = packet.get("triggerEvidence") or {}
        if sha256((repo / "planning/backlog.yaml").read_bytes()) != trigger.get("backlogSha256"):
            raise SystemExit("Recovery supplement trigger backlog is stale; no transition was written")


def validate_target_materialization_projection(
    repo: Path,
    packet: dict[str, Any],
    data: dict[str, Any],
    *,
    allow_unapproved_supplement_gate: bool = False,
) -> dict[str, Any]:
    """Prove the exact amendment materialization delta without writing canonical state."""
    target = packet.get("targetAmendmentAuthority") or {}
    amendment_id = str((target.get("amendmentApproval") or {}).get("id") or "")
    if packet.get("schemaVersion") == "2.0-recovery-supplement-proposal":
        hold = recovery_hold(data, str(packet.get("recoveryRequestId") or ""))
        supplement = recovery_supplement(hold, str(packet.get("supplementId") or ""))
        bootstrap_status = str((supplement.get("bootstrap") or {}).get("status") or "")
        if amendment_id in taskctl.wave_amendment_map(data):
            raise SystemExit("Pre-append target projection refuses fabricated amendment state")
        if bootstrap_status != "APPROVED" and not allow_unapproved_supplement_gate:
            raise SystemExit("Pre-append target projection requires an independently approved supplement")
        target_bootstrap = target.get("bootstrap") or {}
        return {
            "amendment": amendment_id,
            "bootstrapUnit": target_bootstrap.get("id"),
            "candidateCommit": target_bootstrap.get("candidateCommit"),
            "evidence": target_bootstrap.get("evidence"),
            "backlogPresence": False,
            "appendOrExecutionPerformed": False,
            "authorizationGate": (
                None
                if bootstrap_status == "APPROVED"
                else "latest supplemental bootstrap must be independently APPROVED"
            ),
        }
    projected = copy.deepcopy(taskctl.serializable_backlog(data))
    amendment = taskctl.wave_amendment_map(projected).get(amendment_id) or {}
    approval, amendment_packet, _payload = taskctl.load_amendment_authority(repo, amendment_id)
    taskctl.require_amendment_packet_integrity(repo, amendment, approval, amendment_packet)
    if (amendment.get("lifecycle") or {}).get("status") != "APPROVED" or amendment.get("tasks"):
        raise SystemExit("Target materialization projection requires the exact unmaterialized approved amendment")
    authorized = [str(item) for item in approval.get("authorizedTaskIds", [])]
    packet_tasks = amendment_packet.get("taskInventory") or []
    if [str(item.get("id")) for item in packet_tasks] != authorized:
        raise SystemExit("Target materialization projection task inventory differs from its approval")
    amendment["tasks"] = [taskctl.materialized_amendment_task(amendment_id, item) for item in packet_tasks]
    taskctl.append_amendment_event(
        amendment,
        "MATERIALIZED",
        "recoveryctl:read-only-projection",
        "Read-only exact approved task-inventory projection.",
    )
    wave_id = str(amendment.get("target_wave") or "")
    wave = taskctl.wave_map(projected).get(wave_id) or {}
    campaign = wave.get("campaign") or {}
    campaign["scope"] = "amendment-hold"
    indexed = taskctl.index_backlog(projected)
    errors = taskctl.validate(*indexed, repo=repo)
    hold = recovery_hold(projected, str(packet.get("recoveryRequestId") or ""))
    expected_unapproved_gate = (
        f"{hold.get('id')}: unapproved latest recovery supplement requires the exact repair amendment "
        "to remain unmaterialized under ordinary Wave scope"
    )
    authorization_gate = None
    if allow_unapproved_supplement_gate and errors == [expected_unapproved_gate]:
        authorization_gate = "latest supplemental bootstrap must be independently APPROVED"
        errors = []
    if errors:
        raise SystemExit("Target materialization projection is invalid:\n- " + "\n- ".join(errors))
    activation = packet.get("activationBoundary") or {}
    projected_tasks = indexed[3]
    blocked = projected_tasks.get(str(activation.get("blockedTaskId") or "")) or {}
    if (
        not authorized
        or campaign.get("status") != "PAUSED"
        or campaign.get("scope") != "amendment-hold"
        or blocked.get("status") != "BLOCKED"
        or hold.get("status") != "ACTIVE"
        or (amendment.get("lifecycle") or {}).get("status") != "MATERIALIZED"
        or (amendment.get("campaign") is not None)
    ):
        raise SystemExit("Target materialization projection changed state outside the approved stopped boundary")
    return {
        "amendment": amendment_id,
        "materializedTaskIds": authorized,
        "waveStatus": campaign.get("status"),
        "waveScope": campaign.get("scope"),
        "blockedTaskId": activation.get("blockedTaskId"),
        "blockedTaskStatus": blocked.get("status"),
        "holdId": hold.get("id"),
        "holdStatus": hold.get("status"),
        "activationOrClaimPerformed": False,
        "authorizationGate": authorization_gate,
    }


def validate_supplement(
    repo: Path,
    supplement_id: str,
    *,
    require_approved: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    approval, packet, _approval_payload, _packet_payload = load_supplement_authority(repo, supplement_id)
    _payload, data, _capabilities, _slices, _tasks, _gates = backlog_state(repo)
    hold, _amendment = validate_supplement_boundary(repo, packet, data, require_installed=True)
    errors = taskctl.recovery_hold_errors(data, repo)
    if errors:
        raise SystemExit("Invalid supplemental governance recovery hold:\n- " + "\n- ".join(errors))
    supplement = recovery_supplement(hold, supplement_id)
    validate_supplement_bootstrap_history(repo, packet, approval, hold, supplement)
    if require_approved and approval.get("status") != "APPROVED":
        raise SystemExit(f"{supplement_id} is not approved")
    return approval, packet, hold, supplement


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
    target_waves = {
        str(hold.get("target_wave")) for hold in (prior_data.get("control_plane") or {}).get("recovery_holds", [])
    }
    taskctl.save_validated(
        str(path),
        data,
        expected_sha256=sha256(payload),
        expected_identity=taskctl.identity_snapshot(prior_data),
        expected_amendment_identity=taskctl.amendment_identity_snapshot(prior_data),
        expected_approved_waves=taskctl.approved_wave_snapshot(prior_data),
        expected_amendment_history=taskctl.amendment_history_snapshot(prior_data),
        expected_task_review_history=taskctl.task_review_history_snapshot(prior_data),
        expected_wave_checkpoint_history=taskctl.wave_checkpoint_history_snapshot(prior_data),
        expected_recovery_history=taskctl.recovery_history_snapshot(prior_data),
        expected_released_recovery_holds=taskctl.released_recovery_hold_snapshot(prior_data),
        expected_frozen_waves=taskctl.exact_record_snapshot(
            prior_data,
            "waves",
            identities=target_waves,
        ),
        expected_frozen_wave_bases=taskctl.exact_record_snapshot(
            prior_data,
            "wave_approval_bases",
            identity_field="wave_id",
        ),
        expected_frozen_amendments=taskctl.exact_record_snapshot(prior_data, "wave_amendments"),
        repo=repo,
    )


def validate_start_boundary(
    repo: Path,
    packet: dict[str, Any],
    data: dict[str, Any],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
) -> None:
    """Validate the exact stopped state before appending a recovery authority."""
    request_id = str(packet.get("recoveryRequestId") or "")
    wave_id = str(packet.get("targetWave") or "")
    frozen = packet.get("frozenBoundary") or {}
    wave = taskctl.wave_map(data).get(wave_id) or {}
    campaign = wave.get("campaign") or {}
    task = tasks.get(str(frozen.get("taskId") or "")) or {}
    gate = gates.get(str(frozen.get("releaseGate") or "")) or {}
    existing_holds = (data.get("control_plane") or {}).get("recovery_holds", [])
    expected_request = f"GRR-{len(existing_holds) + 1:04d}"
    if request_id != expected_request:
        raise SystemExit(f"Recovery request must be the next consecutive identity {expected_request}")
    if any(hold.get("status") != "RELEASED" for hold in existing_holds):
        raise SystemExit("Every predecessor recovery hold must be terminally RELEASED")
    if taskctl.active_recovery_holds(data):
        raise SystemExit("A governance recovery hold is already ACTIVE")
    control = data.get("control_plane") or {}
    if control.get("revision") not in {5, taskctl.RECOVERY_BASE_REVISION} or (
        control.get("minimum_tool_revision") != control.get("revision")
    ):
        raise SystemExit("Recovery bootstrap start requires a supported exact predecessor control revision")
    if control.get("active_amendment") is not None:
        raise SystemExit("Recovery bootstrap start requires no active amendment")
    if campaign.get("status") != "PAUSED" or campaign.get("scope") != "wave" or campaign.get("lease") is not None:
        raise SystemExit("Recovery bootstrap start requires the exact quiescent paused Wave boundary")
    if campaign.get("branch") != frozen.get("branch") or git_output(repo, "branch", "--show-current") != frozen.get(
        "branch"
    ):
        raise SystemExit("Recovery bootstrap start branch differs from the frozen Wave boundary")
    if any(item.get("status") in {"IN_PROGRESS", "REVIEW"} for item in tasks.values()):
        raise SystemExit("Recovery bootstrap start requires every task to be quiescent")
    if any(
        (item.get("lifecycle") or {}).get("status") != "ADOPTED"
        for item in data.get("wave_amendments", [])
        if item.get("target_wave") == wave_id
    ):
        raise SystemExit("Recovery bootstrap start requires every predecessor amendment to be ADOPTED")
    if (
        frozen.get("waveStatus") != campaign.get("status")
        or frozen.get("waveScope") != campaign.get("scope")
        or frozen.get("wavePauseCategory") != campaign.get("pause_category")
        or frozen.get("taskStatus") != task.get("status")
        or frozen.get("taskRecoveryControl") != task.get("recovery_control")
        or frozen.get("releaseGateStatus") != gate.get("status")
    ):
        raise SystemExit("Recovery packet frozen Wave/task/gate boundary differs from the backlog")
    released = next(
        (hold for hold in existing_holds if hold.get("id") == frozen.get("releasedHoldId")),
        None,
    )
    adopted = taskctl.wave_amendment_map(data).get(str(frozen.get("adoptedAmendment") or "")) or {}
    checkpoints = {str(item.get("id")) for item in wave.get("checkpoints", [])}
    if (
        released is None
        or released.get("status") != frozen.get("releasedHoldStatus")
        or (adopted.get("lifecycle") or {}).get("status") != "ADOPTED"
        or frozen.get("securityCheckpoint") not in checkpoints
    ):
        raise SystemExit(
            "Recovery packet frozen predecessor hold/amendment/checkpoint boundary differs from the backlog"
        )
    pause_commit = str(frozen.get("pauseRecordCommit") or "")
    require_commit(repo, pause_commit, label="Recovery pause record")
    pause_blob = taskctl.git_blob(repo, pause_commit, "planning/backlog.yaml")
    head_blob = taskctl.git_blob(repo, git_output(repo, "rev-parse", "HEAD"), "planning/backlog.yaml")
    if pause_blob is None or sha256(pause_blob) != frozen.get("backlogSha256") or head_blob != pause_blob:
        raise SystemExit("Current backlog differs from the immutable frozen recovery boundary")


def command_bootstrap_start(args: argparse.Namespace) -> None:
    approval, packet, approval_payload, packet_payload = load_recovery_authority(args.repo, args.request)
    require_clean(args.repo)
    approval_relative = f"planning/governance-recovery-approvals/{args.request}.json"
    approval_introduction = taskctl.approval_introduction_commit(args.repo, approval_relative)
    if not approval_introduction:
        raise SystemExit("Recovery approval introduction is unavailable")
    head = git_output(args.repo, "rev-parse", "HEAD")
    if head == approval_introduction or not taskctl.git_is_ancestor(args.repo, approval_introduction, head):
        raise SystemExit("Recovery bootstrap controller must strictly descend from the approval introduction")
    backlog_payload, data, _capabilities, _slices, tasks, gates = backlog_state(args.repo)
    validate_authority_chain(args.repo, packet, data)
    validate_start_boundary(args.repo, packet, data, tasks, gates)
    implementer = taskctl.normalized_identity(args.agent, "Recovery bootstrap implementer")
    wave = taskctl.wave_map(data).get(str(packet.get("targetWave"))) or {}
    if implementer != (wave.get("campaign") or {}).get("owner"):
        raise SystemExit("Recovery bootstrap implementer must own the paused target Wave")
    control = data.get("control_plane") or {}
    packet_reference = approval.get("packet") or {}
    bootstrap = packet.get("bootstrapUnit") or {}
    post = packet.get("postBootstrap") or {}
    hold = {
        "id": (packet.get("controlHold") or {}).get("id"),
        "recovery_request_id": args.request,
        "target_wave": packet.get("targetWave"),
        "status": "ACTIVE",
        "approval_reference": {
            "path": approval_relative,
            "sha256": sha256(approval_payload),
            "introduction_commit": approval_introduction,
        },
        "packet_reference": {
            "path": packet_reference.get("path"),
            "sha256": sha256(packet_payload),
            "commit": packet_reference.get("commit"),
        },
        "bootstrap": {
            "id": bootstrap.get("id"),
            "status": "IN_PROGRESS",
            "implementer": implementer,
            "implementation_commit": None,
            "submission_branch": None,
            "evidence": None,
            "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
            "current_submission": None,
            "attempts": [],
        },
        "supplements": [],
        "post_bootstrap": {
            "required_change_request_id": post.get("requiredChangeRequestId"),
            "required_amendment_id": post.get("requiredAmendmentId"),
            "required_proposed_task_ids": post.get("requiredProposedTaskIds"),
            "execution_authority": False,
        },
        "release_conditions": list((packet.get("controlHold") or {}).get("releaseConditions", [])),
        "created_at": taskctl.utc_now(),
        "released_at": None,
    }
    control.setdefault("recovery_holds", []).append(hold)
    control["revision"] = taskctl.RECOVERY_BASE_REVISION
    control["minimum_tool_revision"] = taskctl.RECOVERY_BASE_REVISION
    save_backlog(args.repo, backlog_payload, data)
    print(f"Installed {hold['id']}/{bootstrap.get('id')}; {packet.get('targetWave')} remains PAUSED")


def evidence_relative(repo: Path, value: str, request_id: str, bootstrap_id: str) -> tuple[str, Path]:
    pattern = (
        rf"planning/governance-recovery-approvals/{re.escape(bootstrap_id)}"
        rf"(?:\.remediation-[0-9]{{2}})?\.evidence\.json"
    )
    if re.fullmatch(pattern, value) is None:
        raise SystemExit(
            f"Recovery evidence must use the approved control-artifact path for {request_id}/{bootstrap_id}"
        )
    return taskctl.canonical_control_artifact_path(
        repo,
        value,
        prefix="planning/governance-recovery-approvals",
        label="Recovery evidence",
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


def supplement_evidence_relative(repo: Path, value: str, bootstrap_id: str) -> tuple[str, Path]:
    pattern = (
        rf"planning/governance-recovery-approvals/{re.escape(bootstrap_id)}"
        rf"(?:\.remediation-[0-9]{{2}})?\.evidence\.json"
    )
    if re.fullmatch(pattern, value) is None:
        raise SystemExit(f"Supplemental recovery evidence must use the canonical {bootstrap_id} path")
    return taskctl.canonical_control_artifact_path(
        repo,
        value,
        prefix="planning/governance-recovery-approvals",
        label="Supplemental recovery evidence",
    )


def supplement_evidence_document(
    repo: Path,
    supplement_id: str,
    packet: dict[str, Any],
    approval: dict[str, Any],
    evidence_value: str,
    candidate: str,
    *,
    lineage_base: str | None = None,
    expected_branch: str | None = None,
    require_current_branch: bool = True,
) -> tuple[dict[str, Any], bytes, str]:
    request_id = str(packet.get("recoveryRequestId") or "")
    bootstrap = packet.get("supplementalBootstrap") or {}
    bootstrap_id = str(bootstrap.get("id") or "")
    relative, path = supplement_evidence_relative(repo, evidence_value, bootstrap_id)
    document, payload = load_json(path, "supplemental recovery bootstrap evidence")
    schema_path = (
        repo / "planning" / "governance-recovery-requests" / "governance-recovery-supplement-evidence.schema.json"
    )
    errors = schema_errors(document, schema_path)
    if errors:
        raise SystemExit("Supplemental recovery evidence schema validation failed:\n- " + "\n- ".join(errors))
    approval_intro = taskctl.approval_introduction_commit(
        repo, f"planning/governance-recovery-approvals/{supplement_id}.json"
    )
    expected_base = str(approval_intro) if lineage_base is None else str(lineage_base)
    if (
        document.get("recoveryRequestId") != request_id
        or document.get("supplementId") != supplement_id
        or document.get("bootstrapUnit") != bootstrap_id
    ):
        raise SystemExit("Supplemental recovery evidence request/supplement/bootstrap identity mismatch")
    if document.get("baseCommit") != expected_base or document.get("candidateCommit") != candidate:
        raise SystemExit("Supplemental recovery evidence base/candidate binding mismatch")
    declared_branch = str(document.get("branch") or "")
    if not declared_branch.startswith("codex/"):
        raise SystemExit("Supplemental recovery evidence must name a codex branch")
    if expected_branch is not None and declared_branch != expected_branch:
        raise SystemExit("Supplemental recovery evidence branch differs from the frozen submission branch")
    if require_current_branch and declared_branch != git_output(repo, "branch", "--show-current"):
        raise SystemExit("Supplemental recovery evidence must name the current codex branch")
    require_commit(repo, expected_base, ancestor_of=candidate, label="Supplemental recovery evidence base")
    require_commit(repo, candidate, label="Supplemental recovery evidence candidate")
    actual_paths = sorted(
        line
        for line in git_output(repo, "diff", "--name-only", f"{expected_base}..{candidate}", "--").splitlines()
        if line
    )
    declared_paths = sorted(str(item) for item in document.get("changedPaths", []))
    if declared_paths != actual_paths:
        raise SystemExit("Supplemental recovery evidence changedPaths differs from the exact Git diff")
    patterns = [str(item) for item in bootstrap.get("authorizedPaths", [])]
    for changed in actual_paths:
        safe_repo_path(repo, changed, label="Changed supplemental recovery path", require_exists=False)
        if not path_authorized(changed, patterns):
            raise SystemExit(f"Supplemental recovery candidate changed an unauthorized path: {changed}")
    if [item.get("criterion") for item in document.get("requiredOutcomes", [])] != bootstrap.get("requiredOutcomes"):
        raise SystemExit("Supplemental recovery evidence does not map every required outcome exactly and in order")
    if [item.get("criterion") for item in document.get("acceptanceCriteria", [])] != packet.get("acceptanceCriteria"):
        raise SystemExit("Supplemental recovery evidence does not map every acceptance criterion exactly and in order")
    if document.get("unverifiedItems") != []:
        raise SystemExit("Supplemental recovery evidence may not retain unverified items")
    commands = [str(item.get("command")) for item in document.get("checks", [])]
    if len(commands) != len(set(commands)) or any(
        item.get("result") != "passed" for item in document.get("checks", [])
    ):
        raise SystemExit("Supplemental recovery evidence checks must be unique and passing")
    return document, payload, relative


def validate_supplement_bootstrap_history(
    repo: Path,
    packet: dict[str, Any],
    approval: dict[str, Any],
    hold: dict[str, Any],
    supplement: dict[str, Any],
) -> None:
    ledger_errors = taskctl.recovery_review_history_errors(
        repo,
        hold,
        packet,
        supplement=supplement,
    )
    if ledger_errors:
        raise SystemExit("Invalid supplemental recovery review history:\n- " + "\n- ".join(ledger_errors))
    bootstrap = supplement.get("bootstrap") or {}
    bootstrap_id = str(bootstrap.get("id") or "")
    attempts = bootstrap.get("attempts") or []
    prior_candidate: str | None = None
    prior_open: set[str] = set()
    blocking_ids: set[str] = set()
    for attempt in attempts:
        attempt_id = str(attempt.get("id") or "")
        candidate = str(attempt.get("implementation_commit") or "")
        evidence = attempt.get("evidence") or {}
        if evidence.get("commit") != candidate:
            raise SystemExit(f"{bootstrap_id}/{attempt_id} evidence commit differs from its frozen candidate")
        _document, evidence_payload, evidence_path = supplement_evidence_document(
            repo,
            str(packet.get("supplementId") or ""),
            packet,
            approval,
            str(evidence.get("path") or ""),
            candidate,
            lineage_base=prior_candidate,
            expected_branch=str(attempt.get("submission_branch") or ""),
            require_current_branch=False,
        )
        if evidence.get("path") != evidence_path or evidence.get("sha256") != sha256(evidence_payload):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} frozen evidence reference differs from its file")
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
        ledger, ledger_payload = load_json(ledger_path, "supplemental recovery review ledger")
        review_schema = (
            repo / "planning" / "governance-recovery-requests" / "governance-recovery-supplement-review.schema.json"
        )
        schema_failures = schema_errors(ledger, review_schema)
        if schema_failures:
            raise SystemExit(
                "Supplemental recovery review schema validation failed:\n- " + "\n- ".join(schema_failures)
            )
        if ledger_reference.get("sha256") != sha256(ledger_payload):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review ledger hash mismatch")
        projected_review = attempt.get("review") or {}
        expected = {
            "recoveryRequestId": packet.get("recoveryRequestId"),
            "supplementId": packet.get("supplementId"),
            "bootstrapUnit": bootstrap_id,
            "attemptId": attempt_id,
            "candidateCommit": candidate,
            "reviewer": projected_review.get("reviewer"),
            "result": projected_review.get("result"),
            "evidence": {"path": evidence_path, "sha256": sha256(evidence_payload)},
        }
        if any(ledger.get(field) != value for field, value in expected.items()):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review ledger differs from the frozen attempt")
        require_commit(repo, str(ledger.get("reviewedStateCommit") or ""), label=f"{bootstrap_id} reviewed state")
        if projected_review.get("reviewer") == attempt.get("implementer"):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review is not independent")
        findings = ledger.get("findings") or []
        closures = ledger.get("closures") or []
        closure_ids = {str(item.get("findingId") or "") for item in closures if isinstance(item, dict)}
        finding_ids = {str(item.get("id") or "") for item in findings if isinstance(item, dict)}
        if len(closure_ids) != len(closures) or not closure_ids.issubset(prior_open):
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review closures are not append-only")
        if len(finding_ids) != len(findings) or "" in finding_ids:
            raise SystemExit(f"{bootstrap_id}/{attempt_id} review findings are invalid or duplicated")
        prior_open = (prior_open - closure_ids) | finding_ids
        blocking_ids.update(str(item.get("id")) for item in findings if item.get("blocking") is True)
        if ledger.get("result") == "approved" and prior_open & blocking_ids:
            raise SystemExit(f"{bootstrap_id}/{attempt_id} approval retains an open blocking finding")
        prior_candidate = candidate
    status = str(bootstrap.get("status") or "")
    if attempts and status != "REVIEW":
        last = attempts[-1]
        if status != REVIEW_RESULTS.get(str((last.get("review") or {}).get("result") or "")):
            raise SystemExit(f"{bootstrap_id} status differs from the last immutable review")
        for field in ("implementation_commit", "submission_branch", "evidence", "review"):
            if bootstrap.get(field) != last.get(field):
                raise SystemExit(f"{bootstrap_id} {field} projection differs from its last immutable attempt")
    current = bootstrap.get("current_submission")
    if status == "REVIEW" and current:
        candidate = str(current.get("candidate_commit") or "")
        evidence = bootstrap.get("evidence") or {}
        lineage = str(attempts[-1].get("implementation_commit")) if attempts else None
        _document, evidence_payload, evidence_path = supplement_evidence_document(
            repo,
            str(packet.get("supplementId") or ""),
            packet,
            approval,
            str(evidence.get("path") or ""),
            candidate,
            lineage_base=lineage,
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


def validate_bootstrap_history(
    repo: Path,
    packet: dict[str, Any],
    approval: dict[str, Any],
    hold: dict[str, Any],
) -> None:
    """Revalidate every frozen evidence/ledger pair and its live projection."""
    ledger_errors = taskctl.recovery_review_history_errors(repo, hold, packet)
    if ledger_errors:
        raise SystemExit("Invalid recovery review history:\n- " + "\n- ".join(ledger_errors))
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


def command_supplement_start(args: argparse.Namespace) -> None:
    approval, packet, _approval_payload, packet_payload = load_supplement_authority(args.repo, args.supplement)
    require_supplement_workspace(args.repo, packet)
    backlog_payload, data, _capabilities, _slices, _tasks, _gates = backlog_state(args.repo)
    validate_supplement_boundary(args.repo, packet, data, require_installed=False)
    control = data.get("control_plane") or {}
    transition = packet.get("controlTransition") or {
        "predecessorRevision": 4,
        "successorRevision": 6,
    }
    predecessor = int(transition.get("predecessorRevision") or 0)
    successor = int(transition.get("successorRevision") or 0)
    if successor <= predecessor or successor > taskctl.CONTROL_TOOL_REVISION:
        raise SystemExit("Supplement control transition is not strictly increasing or supported")
    if control.get("revision") != predecessor or control.get("minimum_tool_revision") != predecessor:
        raise SystemExit(f"Supplement installation requires the exact predecessor control revision {predecessor}")
    request_id = str(packet.get("recoveryRequestId") or "")
    hold = recovery_hold(data, request_id)
    existing = hold.get("supplements", [])
    expected_id = f"{request_id}.S{len(existing) + 1:02d}"
    if args.supplement != expected_id:
        raise SystemExit(f"Recovery supplement must be the next consecutive identity {expected_id}")
    bootstrap_id = str((packet.get("supplementalBootstrap") or {}).get("id") or "")
    expected_bootstrap = f"{request_id}.B{len(existing) + 1:02d}"
    if bootstrap_id != expected_bootstrap:
        raise SystemExit(f"Supplemental bootstrap must be the next consecutive identity {expected_bootstrap}")
    implementer = taskctl.normalized_identity(args.agent, "Supplemental recovery implementer")
    packet_reference = approval.get("packet") or {}
    approval_relative = f"planning/governance-recovery-approvals/{args.supplement}.json"
    approval_introduction = taskctl.approval_introduction_commit(args.repo, approval_relative)
    if not approval_introduction:
        raise SystemExit("Supplemental recovery approval introduction is unavailable")
    installed_supplement = {
        "id": args.supplement,
        "predecessor_control_revision": predecessor,
        "packet_reference": {
            "path": packet_reference.get("path"),
            "sha256": sha256(packet_payload),
            "commit": packet_reference.get("commit"),
        },
        "approval_reference": {
            "path": approval_relative,
            "sha256": sha256((args.repo / approval_relative).read_bytes()),
            "introduction_commit": approval_introduction,
        },
        "bootstrap": {
            "id": bootstrap_id,
            "status": "IN_PROGRESS",
            "implementer": implementer,
            "implementation_commit": None,
            "submission_branch": None,
            "evidence": None,
            "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
            "current_submission": None,
            "attempts": [],
        },
        "created_at": taskctl.utc_now(),
    }
    if packet.get("schemaVersion") == "2.0-recovery-supplement-proposal":
        installed_supplement["successor_control_revision"] = successor
    hold.setdefault("supplements", []).append(installed_supplement)
    for other_hold in control.get("recovery_holds", []):
        other_hold.setdefault("supplements", [])
    control["revision"] = successor
    control["minimum_tool_revision"] = successor
    save_backlog(args.repo, backlog_payload, data)
    print(f"Installed {args.supplement}/{bootstrap_id}; W1 and ordinary execution remain paused")


def command_supplement_validate(args: argparse.Namespace) -> None:
    _approval, packet, hold, supplement = validate_supplement(
        args.repo,
        args.supplement,
        require_approved=args.require_approved,
    )
    target_amendment = ((packet.get("targetAmendmentAuthority") or {}).get("amendmentApproval") or {}).get("id")
    bootstrap_status = (supplement.get("bootstrap") or {}).get("status")
    _payload, data, _capabilities, _slices, _tasks, _gates = backlog_state(args.repo)
    projection = None
    if hold.get("status") == "ACTIVE":
        projection = validate_target_materialization_projection(
            args.repo,
            packet,
            data,
            allow_unapproved_supplement_gate=bootstrap_status != "APPROVED",
        )
    print(
        f"Valid {args.supplement}: bootstrap={(supplement.get('bootstrap') or {}).get('status')}; "
        f"hold={hold.get('status')}; target={target_amendment}"
    )
    if projection is not None:
        print("Read-only materialization projection: " + json.dumps(projection, sort_keys=True))
    else:
        print("Terminal historical authority: materialization projection is no longer executable")


def command_supplement_status(args: argparse.Namespace) -> None:
    _approval, packet, hold, supplement = validate_supplement(args.repo, args.supplement)
    bootstrap = supplement.get("bootstrap") or {}
    print(
        yaml.safe_dump(
            {
                "recoveryRequest": packet.get("recoveryRequestId"),
                "supplement": args.supplement,
                "hold": hold.get("id"),
                "holdStatus": hold.get("status"),
                "bootstrap": {"id": bootstrap.get("id"), "status": bootstrap.get("status")},
                "executionAuthority": "supplemental-bootstrap-only; amendment materialization remains denied",
            },
            sort_keys=False,
        ).rstrip()
    )


def freeze_supplement_submission(args: argparse.Namespace, *, remediation: bool) -> None:
    approval, packet, _hold, supplement = validate_supplement(args.repo, args.supplement)
    bootstrap = supplement.get("bootstrap") or {}
    expected_status = {"CHANGES_REQUESTED", "BLOCKED"} if remediation else {"IN_PROGRESS"}
    if bootstrap.get("status") not in expected_status:
        raise SystemExit(f"Supplemental bootstrap {bootstrap.get('id')} is not eligible for submission")
    candidate = str(args.implementation_commit)
    if candidate != git_output(args.repo, "rev-parse", "HEAD"):
        raise SystemExit("Supplemental recovery implementation commit must equal current HEAD")
    agent = taskctl.normalized_identity(args.agent, "Supplemental recovery implementer")
    if agent != bootstrap.get("implementer"):
        raise SystemExit("Supplemental recovery implementer must retain the installed identity")
    prior_candidate = str(bootstrap.get("implementation_commit") or "") if remediation else None
    if remediation:
        require_commit(args.repo, str(prior_candidate), ancestor_of=candidate, label="Prior supplemental candidate")
        if prior_candidate == candidate:
            raise SystemExit("Supplemental recovery remediation must be a strict descendant")
    bootstrap_id = str(bootstrap.get("id") or "")
    expected_evidence = (
        f"planning/governance-recovery-approvals/{bootstrap_id}.remediation-"
        f"{len(bootstrap.get('attempts') or []):02d}.evidence.json"
        if remediation
        else f"planning/governance-recovery-approvals/{bootstrap_id}.evidence.json"
    )
    if str(args.evidence) != expected_evidence:
        raise SystemExit(f"Supplemental recovery evidence path must be {expected_evidence}")
    require_supplement_workspace(args.repo, packet, transition_untracked={expected_evidence})
    document, evidence_payload, relative = supplement_evidence_document(
        args.repo,
        args.supplement,
        packet,
        approval,
        args.evidence,
        candidate,
        lineage_base=prior_candidate,
    )
    backlog_payload, data, _capabilities, _slices, _tasks, _gates = backlog_state(args.repo)
    mutable = recovery_supplement(recovery_hold(data, str(packet.get("recoveryRequestId"))), args.supplement)[
        "bootstrap"
    ]
    attempt_id = f"R{len(mutable.get('attempts') or []) + 1:02d}"
    reference = {
        "type": "governance-recovery-supplement-evidence",
        "path": relative,
        "sha256": sha256(evidence_payload),
        "commit": candidate,
        "recorded_at": taskctl.utc_now(),
    }
    mutable.update(
        status="REVIEW",
        implementation_commit=candidate,
        submission_branch=document.get("branch"),
        evidence=reference,
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


def supplement_review_ledger(
    args: argparse.Namespace,
    packet: dict[str, Any],
    bootstrap: dict[str, Any],
) -> tuple[dict[str, Any], bytes, str]:
    current = bootstrap.get("current_submission") or {}
    attempt_id = str(current.get("attempt_id") or "")
    expected_relative = f"planning/governance-recovery-approvals/{bootstrap.get('id')}.review-{attempt_id}.json"
    if str(args.from_path) != expected_relative:
        raise SystemExit(f"Supplemental recovery review ledger path must be {expected_relative}")
    _relative, path = taskctl.canonical_control_artifact_path(
        args.repo,
        expected_relative,
        prefix="planning/governance-recovery-approvals",
        label="Supplemental recovery review ledger",
    )
    ledger, payload = load_json(path, "supplemental recovery review ledger")
    review_schema = (
        args.repo / "planning" / "governance-recovery-requests" / "governance-recovery-supplement-review.schema.json"
    )
    failures = schema_errors(ledger, review_schema)
    if failures:
        raise SystemExit("Supplemental recovery review schema validation failed:\n- " + "\n- ".join(failures))
    required = {
        "recoveryRequestId": packet.get("recoveryRequestId"),
        "supplementId": packet.get("supplementId"),
        "bootstrapUnit": bootstrap.get("id"),
        "attemptId": attempt_id,
        "candidateCommit": current.get("candidate_commit"),
        "reviewedStateCommit": git_output(args.repo, "rev-parse", "HEAD"),
    }
    if any(ledger.get(field) != value for field, value in required.items()):
        raise SystemExit("Supplemental recovery review ledger differs from the frozen submission")
    reviewer = taskctl.normalized_identity(str(ledger.get("reviewer") or ""), "Supplemental recovery reviewer")
    if reviewer != taskctl.normalized_identity(args.reviewer, "Supplemental recovery reviewer"):
        raise SystemExit("Supplemental recovery review actor differs from the ledger")
    if reviewer == bootstrap.get("implementer"):
        raise SystemExit("Supplemental recovery review must be independent")
    result = str(ledger.get("result") or "")
    if result not in REVIEW_RESULTS:
        raise SystemExit("Supplemental recovery review result is invalid")
    reference = bootstrap.get("evidence") or {}
    if ledger.get("evidence") != {"path": reference.get("path"), "sha256": reference.get("sha256")}:
        raise SystemExit("Supplemental recovery review evidence differs from the frozen submission")
    findings = ledger.get("findings") or []
    closures = ledger.get("closures") or []
    ordering = [SEVERITY_ORDER.get(str(item.get("severity")), 99) for item in findings if isinstance(item, dict)]
    if len(ordering) != len(findings) or ordering != sorted(ordering):
        raise SystemExit("Supplemental recovery findings must be valid and severity-ranked")
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
            raise SystemExit("Supplemental recovery review contains an invalid finding")
        finding_ids.add(finding_id)
    prior_open: set[str] = set()
    prior_blocking: set[str] = set()
    for attempt in bootstrap.get("attempts", []):
        prior_ledger, _payload = load_json(args.repo / (attempt.get("ledger") or {}).get("path", ""), "prior review")
        prior_open.difference_update(str(item.get("findingId")) for item in prior_ledger.get("closures", []))
        prior_open.update(str(item.get("id")) for item in prior_ledger.get("findings", []))
        prior_blocking.update(
            str(item.get("id")) for item in prior_ledger.get("findings", []) if item.get("blocking") is True
        )
    closure_ids = [str(item.get("findingId") or "") for item in closures if isinstance(item, dict)]
    if (
        len(closure_ids) != len(closures)
        or len(closure_ids) != len(set(closure_ids))
        or not set(closure_ids).issubset(prior_open)
    ):
        raise SystemExit("Supplemental recovery review closures are not append-only")
    open_after = (prior_open - set(closure_ids)) | finding_ids
    blocking = prior_blocking | {str(item.get("id")) for item in findings if item.get("blocking") is True}
    if result == "approved" and (findings or open_after & blocking):
        raise SystemExit("Supplemental recovery approval cannot introduce or retain blocking findings")
    return ledger, payload, expected_relative


def command_supplement_review(args: argparse.Namespace) -> None:
    _approval, packet, _hold, supplement = validate_supplement(args.repo, args.supplement)
    bootstrap = supplement.get("bootstrap") or {}
    if bootstrap.get("status") != "REVIEW" or not bootstrap.get("current_submission"):
        raise SystemExit("Supplemental recovery bootstrap is not awaiting review")
    expected_relative = (
        f"planning/governance-recovery-approvals/{bootstrap.get('id')}.review-"
        f"{bootstrap['current_submission']['attempt_id']}.json"
    )
    require_supplement_workspace(args.repo, packet, transition_untracked={expected_relative})
    ledger, ledger_payload, relative = supplement_review_ledger(args, packet, bootstrap)
    backlog_payload, data, _capabilities, _slices, _tasks, _gates = backlog_state(args.repo)
    mutable = recovery_supplement(
        recovery_hold(data, str(packet.get("recoveryRequestId"))),
        args.supplement,
    )["bootstrap"]
    result = str(ledger.get("result"))
    review = {
        "reviewer": str(ledger.get("reviewer")),
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
    print(f"Supplemental recovery review {mutable['attempts'][-1]['id']}: {mutable['status']}")


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
    if str(args.evidence) != expected_name:
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
    relative = str(args.from_path)
    if relative != expected_relative:
        raise SystemExit(f"Recovery review ledger path must be {expected_relative}")
    _relative, path = taskctl.canonical_control_artifact_path(
        args.repo,
        relative,
        prefix="planning/governance-recovery-approvals",
        label="Recovery review ledger",
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
    if hold.get("status") != "ACTIVE":
        raise SystemExit(f"Recovery hold {hold.get('id')} is already terminally RELEASED")
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
    start = sub.add_parser("bootstrap-start")
    start.add_argument("request")
    start.add_argument("--agent", required=True)
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
    supplement_start = sub.add_parser("supplement-start")
    supplement_start.add_argument("supplement")
    supplement_start.add_argument("--agent", required=True)
    supplement_validate = sub.add_parser("supplement-validate")
    supplement_validate.add_argument("supplement")
    supplement_validate.add_argument("--require-approved", action="store_true")
    supplement_status = sub.add_parser("supplement-status")
    supplement_status.add_argument("supplement")
    supplement_submit = sub.add_parser("supplement-submit")
    supplement_submit.add_argument("supplement")
    supplement_submit.add_argument("--agent", required=True)
    supplement_submit.add_argument("--implementation-commit", required=True)
    supplement_submit.add_argument("--evidence", required=True)
    supplement_resubmit = sub.add_parser("supplement-resubmit")
    supplement_resubmit.add_argument("supplement")
    supplement_resubmit.add_argument("--agent", required=True)
    supplement_resubmit.add_argument("--implementation-commit", required=True)
    supplement_resubmit.add_argument("--evidence", required=True)
    supplement_review = sub.add_parser("supplement-review")
    supplement_review.add_argument("supplement")
    supplement_review.add_argument("--reviewer", required=True)
    supplement_review.add_argument("--from", dest="from_path", required=True)
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
    elif args.command == "bootstrap-start":
        command_bootstrap_start(args)
    elif args.command == "bootstrap-submit":
        freeze_submission(args, remediation=False)
    elif args.command == "bootstrap-resubmit":
        freeze_submission(args, remediation=True)
    elif args.command == "bootstrap-review":
        if taskctl.normalized_identity(args.reviewer, "Recovery bootstrap reviewer") == "":
            raise SystemExit("Recovery bootstrap reviewer is required")
        command_bootstrap_review(args)
    elif args.command == "supplement-start":
        command_supplement_start(args)
    elif args.command == "supplement-validate":
        command_supplement_validate(args)
    elif args.command == "supplement-status":
        command_supplement_status(args)
    elif args.command == "supplement-submit":
        freeze_supplement_submission(args, remediation=False)
    elif args.command == "supplement-resubmit":
        freeze_supplement_submission(args, remediation=True)
    elif args.command == "supplement-review":
        command_supplement_review(args)
    elif args.command == "release":
        taskctl.normalized_identity(args.agent, "Recovery release actor")
        command_release(args)
    else:
        parser.error("Unsupported recovery command")


if __name__ == "__main__":
    main()
