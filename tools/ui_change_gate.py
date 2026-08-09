#!/usr/bin/env python3
"""Enforce design-first ordering and exact reference lineage for UI implementation changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

TEXT_SUFFIXES = frozenset(
    {".css", ".html", ".js", ".json", ".md", ".mjs", ".py", ".scss", ".ts", ".tsx", ".yaml", ".yml"}
)
REFERENCE_EXCLUSIONS = frozenset(
    {"REFERENCE_MANIFEST.yaml", "SHA256SUMS.txt", "VALIDATION_REPORT.md", "ui-reference-validation.json"}
)
HUMAN_ID = re.compile(r"^human:[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
EXPECTED_POLICY_SCALARS = {
    "schemaVersion": "1.0",
    "documentType": "ui-change-policy",
    "referenceRoot": "design/ui-reference",
    "approvalPath": "design/ui-reference/APPROVAL.yaml",
    "manifestPath": "design/ui-reference/REFERENCE_MANIFEST.yaml",
    "contractSchemaPath": "design/ui-change.schema.json",
    "contractRoot": "artifacts/evidence/ui-change",
}
EXPECTED_IMPLEMENTATION_ROOTS = {
    "apps/desktop/src",
    "modules/ui",
    "packages/ui-components",
    "packages/ui-tokens",
}
EXPECTED_IMPLEMENTATION_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".jpeg",
    ".jpg",
    ".json",
    ".jsx",
    ".mjs",
    ".png",
    ".scss",
    ".svg",
    ".ts",
    ".tsx",
    ".webp",
    ".woff",
    ".woff2",
}
EXPECTED_IGNORED_SUFFIXES = {
    ".d.ts",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
}
GATE_CONTROL_PATHS = frozenset(
    {
        ".github/pull_request_template.md",
        ".github/workflows/ci.yml",
        "architecture-protected-paths.json",
        "ci-policy.json",
        "design/ui-change.schema.json",
        "planning/backlog.schema.json",
        "quality-scope.json",
        "tools/ci_check.py",
        "tools/ui_change_gate.py",
        "tools/ui_accessibility_check.py",
        "tools/ui_conformance.py",
        "tools/ui_route_check.py",
        "tools/ui_token_check.py",
        "tools/ui_visual_regression_check.py",
        "tools/ui_workflow_check.py",
        "ui-change-policy.json",
        "verification/baselines/desktop-ui.json",
        "verification/desktop-ui-baseline.schema.json",
        "verification/desktop-ui.schema.json",
        "verification/extensions/desktop-ui.json",
        "verification-profiles.json",
    }
)
APPLICATION_ACTIVATION_PATHS = frozenset(
    {
        "quality-scope.json",
        "tools/ui_change_gate.py",
        "tools/ui_conformance.py",
        "verification/desktop-ui.schema.json",
        "verification/extensions/desktop-ui.json",
        "verification-profiles.json",
    }
)
REVIEW_HARDENING_ENVELOPES = frozenset(
    {
        frozenset(
            {
                "tests/desktop/test_desktop_app_check.py",
                "tests/desktop/test_ui_conformance.py",
                "tests/foundation/test_ui_change_gate.py",
                "tools/desktop_app_check.py",
                "tools/ui_change_gate.py",
                "tools/ui_conformance.py",
            }
        ),
        frozenset(
            {
                "tests/desktop/test_ui_conformance.py",
                "tests/foundation/test_ui_change_gate.py",
                "tools/ui_change_gate.py",
                "tools/ui_conformance.py",
            }
        ),
        frozenset({"tests/foundation/test_ui_change_gate.py", "tools/ui_change_gate.py"}),
    }
)
REVIEW_RECORD_ENVELOPE = frozenset(
    {"docs/planning-implementation-plan.md", "planning/backlog.yaml", "planning/status-summary.md"}
)
AGENT_REVIEWER = re.compile(r"^agent:[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")


def backlog_task(backlog: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    matches = [
        task
        for capability in backlog.get("capabilities", [])
        if isinstance(capability, dict)
        for slice_item in capability.get("slices", [])
        if isinstance(slice_item, dict)
        for task in slice_item.get("tasks", [])
        if isinstance(task, dict) and task.get("id") == task_id
    ]
    return matches[0] if len(matches) == 1 else None


def independent_review_hardening_errors(
    backlog: dict[str, Any], previous_backlog: dict[str, Any], task_id: str, paths: set[str]
) -> list[str]:
    if frozenset(paths) not in REVIEW_HARDENING_ENVELOPES:
        return [
            "post-implementation gate hardening must match one exact canonical implementation-and-regression envelope"
        ]
    task = backlog_task(backlog, task_id)
    previous_task = backlog_task(previous_backlog, task_id)
    if task is None or previous_task is None:
        return ["post-implementation gate hardening requires one exact task in both review-transition backlogs"]
    review = task.get("review")
    previous_review = previous_task.get("review")
    reviewer = review.get("reviewer") if isinstance(review, dict) else None
    owner = task.get("owner")
    if (
        task.get("status") != "IN_PROGRESS"
        or not isinstance(review, dict)
        or review.get("result") != "changes-requested"
        or not isinstance(reviewer, str)
        or AGENT_REVIEWER.fullmatch(reviewer) is None
        or re.sub(r"[^a-z0-9]", "", reviewer.removeprefix("agent:")) == re.sub(r"[^a-z0-9]", "", str(owner).lower())
    ):
        return [
            "post-implementation gate hardening requires a canonical independent agent CHANGES_REQUESTED "
            "record in the commit's parent backlog"
        ]
    if (
        previous_task.get("status") != "REVIEW"
        or not isinstance(previous_review, dict)
        or not review.get("reviewed_at")
        or review.get("reviewed_at") == previous_review.get("reviewed_at")
        or task.get("updated_at") != review.get("reviewed_at")
    ):
        return [
            "post-implementation gate hardening requires its immediate parent to introduce a distinct "
            "REVIEW-to-IN_PROGRESS independent review transition"
        ]
    return []


def application_activation_errors(
    repo: Path,
    base: str,
    head: str,
    protected_changes: list[str],
    contract: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if contract.get("changeKind") != "approved-reference-implementation":
        return ["UI implementation cannot change its own design-first gate controls in the same range"]
    commits = git(repo, "rev-list", "--reverse", "--topo-order", f"{base}..{head}").decode("ascii").splitlines()
    protected_positions: list[int] = []
    implementation_positions: list[int] = []
    paths_by_position: dict[int, set[str]] = {}
    for position, commit in enumerate(commits):
        paths = commit_paths(repo, commit)
        paths_by_position[position] = paths
        if paths & GATE_CONTROL_PATHS:
            protected_positions.append(position)
        if any(is_implementation_path(path, policy) for path in paths):
            implementation_positions.append(position)
    first_implementation = min(implementation_positions) if implementation_positions else None
    late_protected = (
        [position for position in protected_positions if position >= first_implementation]
        if first_implementation is not None
        else []
    )
    activation_positions = [position for position in protected_positions if position not in late_protected]
    if late_protected:
        for position in late_protected:
            try:
                parent = resolve_commit(repo, f"{commits[position]}^")
                if commit_paths(repo, parent) != REVIEW_RECORD_ENVELOPE:
                    raise ValueError("immediate parent is not the exact planning-only review-record commit")
                grandparent = resolve_commit(repo, f"{parent}^")
                backlog = yaml_object(blob(repo, parent, "planning/backlog.yaml"), "parent backlog")
                previous_backlog = yaml_object(
                    blob(repo, grandparent, "planning/backlog.yaml"), "pre-review parent backlog"
                )
                errors.extend(
                    independent_review_hardening_errors(
                        backlog, previous_backlog, str(contract.get("taskId")), paths_by_position[position]
                    )
                )
            except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
                errors.append(f"invalid post-implementation gate-hardening provenance: {exc}")
    if set(protected_changes) == APPLICATION_ACTIVATION_PATHS:
        try:
            base_activation = json_object(
                blob(repo, base, "verification/extensions/desktop-ui.json"), "base desktop UI activation"
            )
            head_activation = json_object(
                blob(repo, head, "verification/extensions/desktop-ui.json"), "desktop UI activation"
            )
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid first-application activation: {exc}")
            return errors
        expected_head = dict(base_activation)
        expected_head.update(
            {
                "mode": "approved-reference-application",
                "targetRoot": "apps/desktop/dist",
                "applicationRoot": "apps/desktop",
                "applicationManifestPath": "apps/desktop/dist/application-manifest.json",
            }
        )
        if base_activation.get("mode") != "approved-reference-fixture" or base_activation.get("targetRoot") != str(
            policy["referenceRoot"]
        ):
            errors.append("first-application activation requires the governed fixture mode at the task base")
        if head_activation != expected_head:
            errors.append(
                "first-application activation may only retarget the unchanged approved reference to the desktop build"
            )
        invalid_order = (
            not activation_positions
            or not implementation_positions
            or max(activation_positions) >= min(implementation_positions)
        )
        if invalid_order:
            errors.append("first-application gate activation must be committed before every UI implementation commit")
    elif not late_protected or len(late_protected) != len(protected_positions) or errors:
        errors.append(
            "UI implementation cannot change its own design-first gate controls without an exact independently "
            "reviewed post-implementation hardening commit"
        )
    return errors


def git(repo: Path, *args: str, allowed: tuple[int, ...] = (0,)) -> bytes:
    completed = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False, timeout=30)
    if completed.returncode not in allowed:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git {' '.join(args)} failed: {message or completed.returncode}")
    return completed.stdout


def resolve_commit(repo: Path, value: str) -> str:
    resolved = git(repo, "rev-parse", "--verify", "--end-of-options", f"{value}^{{commit}}")
    commit = resolved.decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"Git reference did not resolve to a full commit: {value!r}")
    return commit


def canonical_path(value: str) -> str:
    pure = PurePosixPath(value)
    if not value or value.startswith("/") or "\\" in value or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"noncanonical repository path: {value!r}")
    return pure.as_posix()


def blob(repo: Path, commit: str, path: str) -> bytes:
    canonical = canonical_path(path)
    return git(repo, "cat-file", "blob", f"{commit}:{canonical}")


def json_object(payload: bytes, name: str) -> dict[str, Any]:
    loaded = json.loads(payload.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return loaded


def require_canonical_policy(policy: dict[str, Any]) -> None:
    for field, scalar_expected in EXPECTED_POLICY_SCALARS.items():
        if policy.get(field) != scalar_expected:
            raise ValueError(f"ui-change-policy {field} must equal {scalar_expected!r}")
    expected_sets: dict[str, set[str]] = {
        "implementationRoots": EXPECTED_IMPLEMENTATION_ROOTS,
        "implementationExtensions": EXPECTED_IMPLEMENTATION_EXTENSIONS,
        "ignoredImplementationSuffixes": EXPECTED_IGNORED_SUFFIXES,
    }
    for field, expected in expected_sets.items():
        raw = policy.get(field)
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw) or set(raw) != expected:
            raise ValueError(f"ui-change-policy {field} must equal the canonical inventory")


def yaml_object(payload: bytes, name: str) -> dict[str, Any]:
    loaded = yaml.safe_load(payload.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{name} must contain a YAML mapping")
    return loaded


def changed_paths(repo: Path, base: str, head: str) -> set[str]:
    fields = git(repo, "diff", "--name-status", "-z", "--find-renames", "--find-copies", base, head, "--").split(b"\0")
    paths: set[str] = set()
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index].decode("ascii", errors="replace")
        index += 1
        count = 2 if status[:1] in {"R", "C"} else 1
        if index + count > len(fields):
            raise ValueError("Git returned a truncated name-status record")
        for raw in fields[index : index + count]:
            paths.add(canonical_path(raw.decode("utf-8")))
        index += count
    return paths


def tree_entry(repo: Path, commit: str, path: str) -> tuple[str, str] | None:
    canonical = canonical_path(path)
    records = [
        record for record in git(repo, "ls-tree", "-z", "--full-tree", commit, "--", canonical).split(b"\0") if record
    ]
    if not records:
        return None
    if len(records) != 1:
        raise ValueError(f"Git returned multiple tree entries for {canonical}")
    metadata, separator, raw_path = records[0].partition(b"\t")
    parts = metadata.decode("ascii", errors="replace").split()
    observed_path = raw_path.decode("utf-8") if separator else ""
    if len(parts) != 3 or observed_path != canonical:
        raise ValueError(f"Git returned a malformed tree entry for {canonical}")
    mode, kind, _ = parts
    return mode, kind


def implementation_object_errors(repo: Path, base: str, head: str, paths: list[str]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        observed = 0
        for label, commit in (("base", base), ("head", head)):
            entry = tree_entry(repo, commit, path)
            if entry is None:
                continue
            observed += 1
            mode, kind = entry
            if kind != "blob" or mode not in {"100644", "100755"}:
                errors.append(
                    f"governed UI implementation path must be a regular Git blob at {label}: {path} ({mode} {kind})"
                )
        if observed == 0:
            errors.append(f"governed UI implementation path is absent from both base and head: {path}")
    return errors


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode not in {0, 1}:
        raise ValueError(completed.stderr.decode("utf-8", errors="replace").strip() or "git merge-base failed")
    return completed.returncode == 0


def is_implementation_path(path: str, policy: dict[str, Any]) -> bool:
    roots = policy.get("implementationRoots")
    extensions = policy.get("implementationExtensions")
    ignored = policy.get("ignoredImplementationSuffixes")
    if not isinstance(roots, list) or not isinstance(extensions, list) or not isinstance(ignored, list):
        raise ValueError("ui-change-policy implementation path fields must be arrays")
    inside = any(path == root or path.startswith(f"{root}/") for root in roots if isinstance(root, str))
    return (
        inside
        and any(path.endswith(extension) for extension in extensions if isinstance(extension, str))
        and not any(path.endswith(suffix) for suffix in ignored if isinstance(suffix, str))
    )


def tree_files(repo: Path, commit: str, root: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    files: list[str] = []
    output = git(repo, "ls-tree", "-r", "-z", commit, "--", root)
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        parts = metadata.decode("ascii", errors="replace").split()
        path = raw_path.decode("utf-8") if separator else ""
        if len(parts) != 3 or not path:
            errors.append("Git returned a malformed UI-reference tree entry")
            continue
        mode, kind, _ = parts
        relative = PurePosixPath(path).relative_to(PurePosixPath(root)).as_posix()
        if relative.startswith("previews/") or "__pycache__" in relative or relative in REFERENCE_EXCLUSIONS:
            continue
        if mode == "120000" or kind != "blob":
            errors.append(f"UI-reference tree contains a redirected or non-file entry: {relative}")
            continue
        files.append(relative)
    return sorted(files), errors


def canonical_payload(path: str, payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n") if Path(path).suffix.lower() in TEXT_SUFFIXES else payload


def reference_state(repo: Path, commit: str, policy: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    approval_path = str(policy.get("approvalPath", ""))
    manifest_path = str(policy.get("manifestPath", ""))
    root = str(policy.get("referenceRoot", ""))
    try:
        approval_payload = blob(repo, commit, approval_path)
        manifest_payload = blob(repo, commit, manifest_path)
        approval = yaml_object(approval_payload, approval_path)
        manifest = yaml_object(manifest_payload, manifest_path)
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        return {}, [f"cannot load UI-reference state at {commit[:8]}: {exc}"]
    if approval.get("reference_id") != manifest.get("reference_id"):
        errors.append("UI-reference approval and manifest IDs differ")
    if approval.get("version") != manifest.get("version"):
        errors.append("UI-reference approval and manifest versions differ")
    if approval.get("status") != "approved" or manifest.get("status") != "approved":
        errors.append("UI-reference approval and manifest must both be approved")
    governed = manifest.get("governed_files")
    expected_hashes = manifest.get("file_hashes")
    if not isinstance(governed, list) or any(not isinstance(item, str) for item in governed):
        errors.append("UI-reference governed_files must be a string array")
        governed = []
    if not isinstance(expected_hashes, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in expected_hashes.items()
    ):
        errors.append("UI-reference file_hashes must be a string map")
        expected_hashes = {}
    inventory, inventory_errors = tree_files(repo, commit, root)
    errors.extend(inventory_errors)
    if sorted(governed) != inventory or set(expected_hashes) != set(governed):
        errors.append("UI-reference governed files and Git-tree inventory differ")
    observed: dict[str, str] = {}
    for relative in governed:
        try:
            payload = blob(repo, commit, f"{root}/{relative}")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        digest = hashlib.sha256(canonical_payload(relative, payload)).hexdigest()
        observed[relative] = digest
        if expected_hashes.get(relative) != digest:
            errors.append(f"UI-reference governed hash mismatch: {relative}")
    package_sha = hashlib.sha256(
        json.dumps(observed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "approval": approval,
        "manifest": manifest,
        "approvalPayload": approval_payload,
        "manifestPayload": manifest_payload,
        "referenceId": approval.get("reference_id"),
        "version": approval.get("version"),
        "packageSha256": package_sha,
    }, errors


def find_task(backlog: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for capability in backlog.get("capabilities", []):
        for slice_ in capability.get("slices", []):
            for task in slice_.get("tasks", []):
                if task.get("id") == task_id:
                    return task
    return None


def automatic_base(repo: Path, head_ref: str) -> str:
    """Use the sole active experience task base, otherwise the immediate parent."""
    head = resolve_commit(repo, head_ref)
    try:
        backlog = yaml_object(blob(repo, head, "planning/backlog.yaml"), "planning/backlog.yaml")
    except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot select UI change base from the authoritative backlog: {exc}") from exc
    active = [
        task
        for capability in backlog.get("capabilities", [])
        for slice_ in capability.get("slices", [])
        for task in slice_.get("tasks", [])
        if task.get("status") in {"IN_PROGRESS", "REVIEW"} and isinstance(task.get("experience_change"), dict)
    ]
    if len(active) > 1:
        identities = sorted(str(task.get("id")) for task in active)
        raise ValueError(f"ambiguous active UI experience tasks; supply an explicit immutable base: {identities}")
    if len(active) == 1:
        raw_base = active[0].get("base_sha")
        if not isinstance(raw_base, str) or not re.fullmatch(r"[0-9a-f]{40}", raw_base):
            raise ValueError(f"active UI experience task {active[0].get('id')} lacks a canonical base_sha")
        candidate = resolve_commit(repo, raw_base)
        if candidate == head or not is_ancestor(repo, candidate, head):
            raise ValueError(f"active UI experience task {active[0].get('id')} has an invalid base_sha range")
        return candidate
    return f"{head_ref}^"


def implementation_commits(repo: Path, base: str, head: str, policy: dict[str, Any]) -> list[str]:
    commits = git(repo, "rev-list", "--reverse", "--topo-order", f"{base}..{head}").decode("ascii").splitlines()
    result: list[str] = []
    for commit in commits:
        paths = commit_paths(repo, commit)
        if any(is_implementation_path(path, policy) for path in paths):
            result.append(commit)
    return result


def commit_paths(repo: Path, commit: str) -> set[str]:
    raw = git(repo, "diff-tree", "--root", "--no-commit-id", "--name-only", "-z", "-r", "-m", commit, "--")
    return {canonical_path(item.decode("utf-8")) for item in raw.split(b"\0") if item}


def validate(repo: Path, base_ref: str, head_ref: str = "HEAD") -> dict[str, Any]:
    errors: list[str] = []
    try:
        repo = repo.resolve(strict=True)
        base = resolve_commit(repo, base_ref)
        head = resolve_commit(repo, head_ref)
        if base == head or not is_ancestor(repo, base, head):
            raise ValueError("UI change base must be a strict ancestor of head")
        policy = json_object(blob(repo, head, "ui-change-policy.json"), "ui-change-policy.json")
        require_canonical_policy(policy)
        schema_path = str(policy.get("contractSchemaPath", ""))
        schema = json_object(blob(repo, head, schema_path), schema_path)
        changed = changed_paths(repo, base, head)
        try:
            base_policy = json_object(blob(repo, base, "ui-change-policy.json"), "base ui-change-policy.json")
            require_canonical_policy(base_policy)
        except UnicodeDecodeError, ValueError, json.JSONDecodeError:
            if "ui-change-policy.json" not in changed:
                raise
            base_policy = policy
        ui_files = sorted(
            path
            for path in changed
            if is_implementation_path(path, policy) or is_implementation_path(path, base_policy)
        )
        contract_root = str(policy.get("contractRoot", ""))
        contract_paths = sorted(
            path for path in changed if path.startswith(f"{contract_root}/") and path.endswith(".json")
        )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "base": base_ref, "head": head_ref, "errors": [str(exc)]}

    report: dict[str, Any] = {
        "ok": False,
        "base": base,
        "head": head,
        "uiFiles": ui_files,
        "contract": contract_paths[0] if len(contract_paths) == 1 else None,
        "changeKind": None,
        "referenceId": None,
        "referencePackageSha256": None,
        "errors": errors,
    }
    if not ui_files:
        if contract_paths:
            errors.append("UI change evidence is present but no governed UI implementation file changed")
        report["ok"] = not errors
        return report
    if len(contract_paths) != 1:
        errors.append(f"exactly one changed UI evidence contract is required; found {contract_paths}")
        return report
    try:
        errors.extend(implementation_object_errors(repo, base, head, ui_files))
    except ValueError as exc:
        errors.append(str(exc))
    protected_changes = sorted(changed & GATE_CONTROL_PATHS)

    contract_path = contract_paths[0]
    try:
        contract = json_object(blob(repo, head, contract_path), contract_path)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        return report
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for issue in sorted(validator.iter_errors(contract), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in issue.absolute_path) or "<root>"
        errors.append(f"{contract_path}:{location}: {issue.message}")
    if errors:
        return report

    if protected_changes:
        errors.extend(application_activation_errors(repo, base, head, protected_changes, contract, policy))
        if errors:
            return report

    task_id = str(contract["taskId"])
    expected_contract_path = f"{contract_root}/{task_id}.json"
    if contract_path != expected_contract_path or contract.get("contractPath") != contract_path:
        errors.append(f"UI evidence path must be {expected_contract_path}")
    if contract.get("changedFiles") != ui_files:
        errors.append("UI evidence changedFiles must exactly equal the sorted governed implementation change set")

    state, state_errors = reference_state(repo, head, policy)
    base_state, base_state_errors = reference_state(repo, base, policy)
    errors.extend(state_errors)
    errors.extend(f"base: {error}" for error in base_state_errors)
    reference = contract["reference"]
    report["changeKind"] = contract["changeKind"]
    report["referenceId"] = state.get("referenceId")
    report["referencePackageSha256"] = state.get("packageSha256")
    expected_reference = {
        "referenceId": state.get("referenceId"),
        "version": state.get("version"),
        "packageSha256": state.get("packageSha256"),
        "approvedBy": state.get("approval", {}).get("approved_by"),
        "previousReferenceId": state.get("approval", {}).get("supersedes"),
    }
    for key, expected in expected_reference.items():
        if reference.get(key) != expected:
            errors.append(f"UI evidence reference.{key} does not match the exact approved reference")

    try:
        approval_commit = resolve_commit(repo, str(reference["approvalCommit"]))
        if approval_commit != reference["approvalCommit"]:
            errors.append("reference.approvalCommit must be a full canonical commit SHA")
        if not is_ancestor(repo, approval_commit, head):
            errors.append("reference approval commit is not an ancestor of head")
        if str(policy["approvalPath"]) not in commit_paths(repo, approval_commit):
            errors.append("reference approval commit did not change the approval record")
        approval_payload = blob(repo, approval_commit, str(policy["approvalPath"]))
        if approval_payload != state.get("approvalPayload"):
            errors.append("reference approval record changed after the cited approval commit")
    except (KeyError, ValueError) as exc:
        errors.append(f"invalid reference approval commit: {exc}")
        approval_commit = ""

    try:
        backlog = yaml_object(blob(repo, head, "planning/backlog.yaml"), "planning/backlog.yaml")
        task = find_task(backlog, task_id)
    except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        errors.append(str(exc))
        task = None
    if task is None:
        errors.append(f"UI evidence task does not exist in the authoritative backlog: {task_id}")
    else:
        experience = task.get("experience_change")
        expected_experience = {
            "kind": contract["changeKind"],
            "contract_path": contract_path,
            "reference_id": reference["referenceId"],
            "reference_version": reference["version"],
            "reference_package_sha256": reference["packageSha256"],
            "reference_approval_commit": reference["approvalCommit"],
            "previous_reference_id": reference["previousReferenceId"],
            "implementation_agent": contract["implementationAgent"],
        }
        if experience != expected_experience:
            errors.append("task experience_change must exactly match the UI evidence lineage")
        if task.get("status") not in {"IN_PROGRESS", "REVIEW"}:
            errors.append("UI evidence task must be active in IN_PROGRESS or REVIEW state")
        if task.get("base_sha") != base:
            errors.append("UI evidence task base_sha must exactly equal the validated change base")
        implementation_identity = str(contract["implementationAgent"]).split(":", 1)[1]
        if task.get("owner") != implementation_identity:
            errors.append("UI evidence implementationAgent must identify the claimed task owner")

    reference_changed = sorted(path for path in changed if path.startswith(f"{policy['referenceRoot']}/"))
    kind = contract["changeKind"]
    if kind == "intentional-design-change":
        approval = state.get("approval", {})
        if base_state.get("referenceId") == state.get("referenceId"):
            errors.append("intentional UI change requires a newer approved reference than the base commit")
        if reference.get("previousReferenceId") != base_state.get("referenceId"):
            errors.append("intentional UI change previousReferenceId must equal the base reference ID")
        approved_by = approval.get("approved_by")
        if (
            approval.get("approval_kind") != "human"
            or not isinstance(approved_by, str)
            or not HUMAN_ID.fullmatch(approved_by)
        ):
            errors.append("intentional UI reference approval must be an explicit human:<identity> approval")
        implementation_identity = str(contract.get("implementationAgent", "")).split(":", 1)[-1].casefold()
        approval_identity = str(approved_by).split(":", 1)[-1].casefold()
        if approved_by == contract.get("implementationAgent") or approval_identity == implementation_identity:
            errors.append("the implementation agent cannot approve its own UI reference revision")
        if task is not None and task.get("review_gate") != "human-and-agent-review":
            errors.append("intentional UI implementation tasks require human-and-agent-review")
        if not reference_changed:
            errors.append("intentional UI change requires a governed reference revision in the change range")
        if approval_commit:
            if approval_commit == base or not is_ancestor(repo, base, approval_commit):
                errors.append("reference approval commit must occur after the pull-request base")
            approval_state, approval_errors = reference_state(repo, approval_commit, policy)
            errors.extend(f"approval commit: {error}" for error in approval_errors)
            if approval_state.get("packageSha256") != state.get("packageSha256"):
                errors.append("approved reference package changed after the approval commit")
            try:
                commits = implementation_commits(repo, base, head, policy)
            except ValueError as exc:
                errors.append(str(exc))
                commits = []
            for commit in commits:
                if commit == approval_commit or not is_ancestor(repo, approval_commit, commit):
                    errors.append(f"reference approval must strictly precede UI implementation commit {commit}")
    else:
        if base_state.get("referenceId") != state.get("referenceId") or base_state.get("packageSha256") != state.get(
            "packageSha256"
        ):
            errors.append(f"{kind} must use the unchanged approved reference from the base commit")
        if reference_changed:
            errors.append(f"{kind} cannot modify the governed UI reference")
        if kind == "defect-restoration" and task is not None and task.get("review_gate") != "human-and-agent-review":
            errors.append(
                "defect restoration requires human-and-agent-review to classify the change until governed "
                "implementation-conformance evidence is installed"
            )

    report["ok"] = not errors
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base", default=os.environ.get("UI_CHANGE_BASE_SHA"))
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        base = args.base or automatic_base(repo, args.head)
        result = validate(repo, base, args.head)
    except ValueError as exc:
        result = {"ok": False, "base": args.base, "head": args.head, "errors": [str(exc)]}
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
