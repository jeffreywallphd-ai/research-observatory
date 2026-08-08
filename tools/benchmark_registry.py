#!/usr/bin/env python3
"""Validate and run the deterministic benchmark and golden-output registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

REGISTRY_PATH = "evaluation/registry.json"
REGISTRY_SCHEMA_PATH = "evaluation/registry.schema.json"
APPROVAL_SCHEMA_PATH = "evaluation/baseline-approval.schema.json"
APPROVAL_ROOT = "evaluation/approvals/"
BASELINE_ROOT = "evaluation/baselines/"
PROMPT_ROOT = "evaluation/prompts/"
REPORT_ROOT = "artifacts/tmp"
EXECUTOR_KIND = {
    "metadata-json-normalizer-v1": "golden-parsing",
    "json-schema-validation-v1": "contract-validation",
}
TRACKED_METADATA_FIELDS = ("abstract", "authors", "containerTitle", "issued")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_snapshot(repo: Path, raw_path: Any) -> tuple[Path | None, bytes | None, str | None]:
    if not isinstance(raw_path, str):
        return None, None, "path must be a string"
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or ".." in pure.parts or "\\" in raw_path:
        return None, None, f"unsafe repository path {raw_path!r}"
    lexical = repo.joinpath(*pure.parts)
    try:
        before = lexical.lstat()
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(repo)
    except (OSError, ValueError) as exc:
        return None, None, f"path does not resolve inside repository: {raw_path}: {exc}"
    if resolved != lexical:
        return None, None, f"path must not be a symbolic link or redirect: {raw_path}"
    if not resolved.is_file():
        return None, None, f"path is not a file: {raw_path}"
    try:
        payload = resolved.read_bytes()
        after = lexical.lstat()
        resolved_after = lexical.resolve(strict=True)
    except OSError as exc:
        return None, None, f"cannot read {raw_path}: {exc}"
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or resolved_after != resolved:
        return None, None, f"path changed while being read: {raw_path}"
    return resolved, payload, None


def parse_json(payload: bytes, label: str) -> tuple[Any | None, str | None]:
    try:
        return json.loads(payload.decode("utf-8")), None
    except (UnicodeError, json.JSONDecodeError) as exc:
        return None, f"cannot parse {label} as UTF-8 JSON: {exc}"


def document_schema_errors(value: Any, schema: Any, label: str) -> list[str]:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"invalid {label} schema: {exc.message}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda error: [str(part) for part in error.path])
    return [f"{label}.{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors]


def run_git(repo: Path, arguments: list[str]) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=repo,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None


def git_blob(repo: Path, revision: str, path: str) -> tuple[bytes | None, str | None]:
    present = run_git(repo, ["ls-tree", "--name-only", revision, "--", path])
    if present is None or present.returncode != 0:
        return None, f"cannot inspect Git tree {revision} for {path}"
    if not present.stdout.strip():
        return None, None
    blob = run_git(repo, ["show", f"{revision}:{path}"])
    if blob is None or blob.returncode != 0:
        return None, f"cannot read Git blob {revision}:{path}"
    return blob.stdout, None


def git_registry(repo: Path, revision: str) -> tuple[dict[str, Any] | None, str | None]:
    payload, read_error = git_blob(repo, revision, REGISTRY_PATH)
    if read_error or payload is None:
        return None, read_error
    value, parse_error = parse_json(payload, f"{revision}:{REGISTRY_PATH}")
    if parse_error or not isinstance(value, dict):
        return None, parse_error or f"{revision}:{REGISTRY_PATH} must be an object"
    return value, None


def registry_asset_specs(registry: dict[str, Any]) -> list[tuple[str, Any]]:
    specifications: list[tuple[str, Any]] = []
    benchmarks = registry.get("benchmarks")
    if not isinstance(benchmarks, list):
        return specifications
    for item in benchmarks:
        if not isinstance(item, dict):
            continue
        path_specifications = [item.get("dataset"), item.get("expected")]
        schemas = item.get("schemas")
        if isinstance(schemas, list):
            path_specifications.extend(schemas)
        for specification in path_specifications:
            if isinstance(specification, dict) and isinstance(specification.get("path"), str):
                specifications.append((specification["path"], specification.get("sha256")))
        prompt = item.get("prompt", {})
        if isinstance(prompt, dict) and isinstance(prompt.get("path"), str):
            specifications.append((prompt["path"], prompt.get("sha256")))
        baseline = item.get("baseline", {})
        if not isinstance(baseline, dict):
            continue
        history = baseline.get("history")
        lineages = [*history, baseline] if isinstance(history, list) else [baseline]
        for lineage in lineages:
            if not isinstance(lineage, dict):
                continue
            approval_path = lineage.get("approval", lineage.get("currentApproval"))
            approval_hash = lineage.get("approvalSha256", lineage.get("currentApprovalSha256"))
            if isinstance(approval_path, str):
                specifications.append((approval_path, approval_hash))
    return specifications


def baseline_lineage_errors(current: dict[str, Any], previous: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    current_benchmarks = current.get("benchmarks")
    if not isinstance(current_benchmarks, list):
        current_benchmarks = []
    current_items = {
        item["id"]: item for item in current_benchmarks if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if previous is None:
        return errors
    previous_benchmarks = previous.get("benchmarks")
    if not isinstance(previous_benchmarks, list):
        previous_benchmarks = []
    previous_items = {
        item["id"]: item for item in previous_benchmarks if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for removed in sorted(set(previous_items) - set(current_items)):
        errors.append(f"benchmark removal requires a governed deprecation workflow: {removed}")
    for benchmark_id, current_item in current_items.items():
        current_baseline = current_item.get("baseline")
        if not isinstance(current_baseline, dict):
            current_baseline = {}
        previous_item = previous_items.get(benchmark_id)
        if previous_item is None:
            if current_baseline.get("version") != 1:
                errors.append(f"{benchmark_id}: a new benchmark baseline must start at version 1")
            continue
        previous_prompt = previous_item.get("prompt")
        if not isinstance(previous_prompt, dict):
            previous_prompt = {}
        current_prompt = current_item.get("prompt")
        if not isinstance(current_prompt, dict):
            current_prompt = {}
        previous_prompt_identity = (previous_prompt.get("id"), previous_prompt.get("version"))
        current_prompt_identity = (current_prompt.get("id"), current_prompt.get("version"))
        if previous_prompt_identity == current_prompt_identity and previous_prompt != current_prompt:
            migrated_no_prompt = {**previous_prompt, "path": None}
            if not (
                previous_prompt_identity == ("none", "not-applicable")
                and previous_prompt.get("sha256") is None
                and current_prompt == migrated_no_prompt
            ):
                errors.append(f"{benchmark_id}: prompt content or path changed without a new prompt identity")
        previous_baseline = previous_item.get("baseline")
        if not isinstance(previous_baseline, dict):
            previous_baseline = {}
        previous_expected = previous_item.get("expected")
        if not isinstance(previous_expected, dict):
            previous_expected = {}
        current_expected = current_item.get("expected")
        if not isinstance(current_expected, dict):
            current_expected = {}
        old_path = previous_expected.get("path")
        new_path = current_expected.get("path")
        old_hash = previous_expected.get("sha256")
        new_hash = current_expected.get("sha256")
        if old_path == new_path and old_hash == new_hash:
            if current_baseline != previous_baseline:
                migrated_initial = {
                    **previous_baseline,
                    "expectedPath": old_path,
                    "currentApprovalSha256": None,
                }
                if not (
                    previous_baseline.get("version") == 1
                    and previous_baseline.get("history") == []
                    and previous_baseline.get("currentApproval") is None
                    and current_baseline == migrated_initial
                ):
                    errors.append(f"{benchmark_id}: baseline lineage changed without expected-output change")
            continue
        previous_history = previous_baseline.get("history")
        if not isinstance(previous_history, list):
            previous_history = []
        expected_history = [
            *previous_history,
            {
                "version": previous_baseline.get("version"),
                "expectedPath": old_path,
                "sha256": old_hash,
                "approval": previous_baseline.get("currentApproval"),
                "approvalSha256": previous_baseline.get("currentApprovalSha256"),
            },
        ]
        previous_version = previous_baseline.get("version")
        if type(previous_version) is not int:
            previous_version = 0
        if current_baseline.get("version") != previous_version + 1:
            errors.append(f"{benchmark_id}: changed baseline must increment exactly one version")
        if current_baseline.get("history") != expected_history:
            errors.append(f"{benchmark_id}: changed baseline must append the exact previous baseline to history")
        if not current_baseline.get("currentApproval"):
            errors.append(f"{benchmark_id}: changed baseline requires currentApproval")
    return errors


def approval_diff_errors(payload: bytes, context: str) -> list[str]:
    errors: list[str] = []
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeError:
        return [f"cannot decode Git approval changes for {context}"]
    for line in lines:
        fields = line.split("\t", maxsplit=1)
        if len(fields) != 2:
            continue
        status, path = fields
        if path.endswith(".json") and status != "A":
            errors.append(f"{context}: immutable baseline approval record was rewritten or removed: {path}")
    return errors


def historical_asset_errors(repo: Path, commit: str, registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path, expected_hash in registry_asset_specs(registry):
        payload, read_error = git_blob(repo, commit, path)
        if read_error:
            errors.append(read_error)
        elif payload is None:
            errors.append(f"{commit}: governed registry asset is missing: {path}")
        elif not isinstance(expected_hash, str) or sha256(payload) != expected_hash:
            errors.append(f"{commit}: governed registry asset SHA-256 mismatch: {path}")
    return errors


def historical_registry_schema_errors(repo: Path, commit: str, registry: dict[str, Any]) -> list[str]:
    schema_payload, read_error = git_blob(repo, commit, REGISTRY_SCHEMA_PATH)
    if read_error:
        return [read_error]
    if schema_payload is None:
        return [f"{commit}: historical benchmark registry schema is missing"]
    schema, parse_error = parse_json(schema_payload, f"{commit}:{REGISTRY_SCHEMA_PATH}")
    if parse_error or not isinstance(schema, dict):
        return [f"{commit}: {parse_error or 'historical benchmark registry schema must be an object'}"]
    return [f"{commit}: {error}" for error in document_schema_errors(registry, schema, "registry")]


def approval_tree_blobs(repo: Path, commit: str) -> tuple[dict[str, str], str | None]:
    tree = run_git(repo, ["ls-tree", "-r", commit, "--", "evaluation/approvals"])
    if tree is None or tree.returncode != 0:
        return {}, f"cannot inspect approval tree at governed commit {commit}"
    identities: dict[str, str] = {}
    for line in tree.stdout.splitlines():
        metadata, separator, raw_path = line.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            continue
        path = raw_path.decode("utf-8", errors="replace")
        if path.endswith(".json") and fields[1] == b"blob":
            identities[path] = fields[2].decode("ascii", errors="replace")
    return identities, None


def git_history_errors(repo: Path, current_registry: dict[str, Any]) -> list[str]:
    git_marker = repo / ".git"
    inside = run_git(repo, ["rev-parse", "--is-inside-work-tree"])
    if inside is None or inside.returncode != 0 or inside.stdout.strip() != b"true":
        return ["cannot inspect governed Git history in this checkout"] if git_marker.exists() else []
    shallow = run_git(repo, ["rev-parse", "--is-shallow-repository"])
    if shallow is None or shallow.returncode != 0:
        return ["cannot determine whether governed Git history is complete"]
    if shallow.stdout.strip() == b"true":
        return ["governed benchmark history requires a complete, non-shallow Git checkout"]
    head_result = run_git(repo, ["rev-parse", "--verify", "HEAD"])
    if head_result is None or head_result.returncode != 0:
        return ["cannot resolve HEAD while validating governed Git history"]
    head = head_result.stdout.decode("ascii", errors="replace").strip()

    commits_result = run_git(repo, ["rev-list", "--reverse", "--topo-order", head])
    if commits_result is None or commits_result.returncode != 0:
        return ["cannot enumerate complete reachable benchmark history"]

    errors: list[str] = []
    historical_paths = {path for path, _ in registry_asset_specs(current_registry)}
    registry_cache: dict[str, tuple[dict[str, Any] | None, list[str], bool]] = {}
    approval_identities: dict[str, dict[str, str]] = {}

    def cached_registry(revision: str) -> tuple[dict[str, Any] | None, list[str], bool]:
        if revision not in registry_cache:
            registry, parse_error = git_registry(repo, revision)
            snapshot_errors = [parse_error] if parse_error else []
            if registry is not None and not snapshot_errors:
                snapshot_errors.extend(historical_registry_schema_errors(repo, revision, registry))
            registry_cache[revision] = (registry, snapshot_errors, not snapshot_errors)
        return registry_cache[revision]

    for raw_commit in commits_result.stdout.splitlines():
        commit = raw_commit.decode("ascii", errors="replace")
        parents_result = run_git(repo, ["rev-list", "--parents", "-n", "1", commit])
        if parents_result is None or parents_result.returncode != 0:
            errors.append(f"cannot inspect parents of governed commit {commit}")
            continue
        parent_fields = parents_result.stdout.decode("ascii", errors="replace").split()
        parents = parent_fields[1:]
        current_at_commit, current_errors, current_valid = cached_registry(commit)
        errors.extend(current_errors)
        if current_at_commit is not None and current_valid:
            historical_paths.update(path for path, _ in registry_asset_specs(current_at_commit))
            errors.extend(historical_asset_errors(repo, commit, current_at_commit))

        transition_parents: list[str | None] = [*parents]
        if not transition_parents:
            transition_parents.append(None)
        for parent in transition_parents:
            previous_at_parent: dict[str, Any] | None = None
            previous_valid = True
            if parent:
                previous_at_parent, _, previous_valid = cached_registry(parent)
            edge = f"{commit}<-{parent or '<root>'}"
            if previous_valid and previous_at_parent is not None and current_at_commit is None and current_valid:
                errors.append(f"{edge}: benchmark registry was removed from reachable history")
            if current_at_commit is not None and current_valid and previous_valid:
                transition_errors = baseline_lineage_errors(
                    current_at_commit,
                    previous_at_parent if previous_at_parent is not None else {"benchmarks": []},
                )
                errors.extend(f"{edge}: {error}" for error in transition_errors)

            if parent:
                approval_diff = run_git(
                    repo,
                    ["diff", "--name-status", "--no-renames", parent, commit, "--", "evaluation/approvals"],
                )
            else:
                approval_diff = run_git(
                    repo,
                    [
                        "diff-tree",
                        "--root",
                        "--no-commit-id",
                        "--name-status",
                        "-r",
                        "--no-renames",
                        commit,
                        "--",
                        "evaluation/approvals",
                    ],
                )
            if approval_diff is None or approval_diff.returncode != 0:
                errors.append(f"cannot inspect approval changes on governed edge {edge}")
            else:
                errors.extend(approval_diff_errors(approval_diff.stdout, edge))

        approval_blobs, approval_tree_error = approval_tree_blobs(repo, commit)
        if approval_tree_error:
            errors.append(approval_tree_error)
        for path, blob in approval_blobs.items():
            approval_identities.setdefault(path, {}).setdefault(blob, commit)

    for path, identities in sorted(approval_identities.items()):
        if len(identities) > 1:
            origins = ", ".join(f"{blob}@{commit}" for blob, commit in sorted(identities.items()))
            errors.append(f"immutable approval path has multiple reachable blob identities: {path}: {origins}")

    relevant_paths = ["evaluation", *sorted(historical_paths)]
    status_result = run_git(repo, ["status", "--porcelain", "--", *relevant_paths])
    if status_result is None or status_result.returncode != 0:
        errors.append("cannot inspect governed benchmark worktree state")
    elif status_result.stdout.strip():
        head_registry, head_registry_error = git_registry(repo, head)
        if head_registry_error:
            errors.append(head_registry_error)
        else:
            transition_errors = baseline_lineage_errors(
                current_registry,
                head_registry if head_registry is not None else {"benchmarks": []},
            )
            errors.extend(f"worktree: {error}" for error in transition_errors)
        approval_diff = run_git(
            repo,
            ["diff", "--name-status", "--no-renames", head, "--", "evaluation/approvals"],
        )
        if approval_diff is None or approval_diff.returncode != 0:
            errors.append("cannot inspect worktree approval changes")
        else:
            errors.extend(approval_diff_errors(approval_diff.stdout, "worktree"))
    return errors


def approval_errors(
    repo: Path,
    assets: dict[str, bytes],
    benchmark_id: str,
    version: int,
    old_hash: str,
    new_hash: str,
    raw_path: Any,
    expected_approval_hash: Any,
) -> list[str]:
    if not isinstance(raw_path, str) or not raw_path.startswith(APPROVAL_ROOT) or not raw_path.endswith(".json"):
        return [f"{benchmark_id}: approval path must be a JSON file under {APPROVAL_ROOT}"]
    _, payload, path_error = safe_snapshot(repo, raw_path)
    if path_error or payload is None:
        return [f"{benchmark_id}: invalid approval: {path_error}"]
    assets[raw_path] = payload
    if not isinstance(expected_approval_hash, str) or sha256(payload) != expected_approval_hash:
        return [f"{benchmark_id}: approval SHA-256 does not match pinned lineage for {raw_path}"]
    approval, parse_error = parse_json(payload, f"approval {raw_path}")
    if parse_error or not isinstance(approval, dict):
        return [f"{benchmark_id}: {parse_error or 'approval must be an object'}"]
    _, schema_payload, schema_path_error = safe_snapshot(repo, APPROVAL_SCHEMA_PATH)
    if schema_path_error or schema_payload is None:
        return [f"{benchmark_id}: baseline approval schema: {schema_path_error}"]
    assets[APPROVAL_SCHEMA_PATH] = schema_payload
    approval_schema, schema_parse_error = parse_json(schema_payload, APPROVAL_SCHEMA_PATH)
    if schema_parse_error or not isinstance(approval_schema, dict):
        return [f"{benchmark_id}: {schema_parse_error or 'baseline approval schema must be an object'}"]
    errors = document_schema_errors(approval, approval_schema, f"approval[{benchmark_id}]")
    expected = {
        "schemaVersion": "1.0",
        "documentType": "baseline-approval",
        "status": "approved",
        "benchmarkId": benchmark_id,
        "fromVersion": version - 1,
        "toVersion": version,
        "oldSha256": old_hash,
        "newSha256": new_hash,
    }
    errors.extend(
        f"{benchmark_id}: approval {key} must equal {value!r}"
        for key, value in expected.items()
        if type(approval.get(key)) is not type(value) or approval.get(key) != value
    )
    approved_by = approval.get("approvedBy")
    generated_by = approval.get("generatedBy")
    if not isinstance(approved_by, str) or approved_by != approved_by.strip() or approved_by == "human:":
        errors.append(f"{benchmark_id}: approvedBy must use a nonempty normalized human: identity")
    if not isinstance(generated_by, str) or not generated_by.strip() or generated_by != generated_by.strip():
        errors.append(f"{benchmark_id}: generatedBy is required")
    if approved_by == generated_by:
        errors.append(f"{benchmark_id}: baseline generator cannot approve the same baseline")
    if not isinstance(approval.get("rationale"), str) or not approval["rationale"].strip():
        errors.append(f"{benchmark_id}: approval rationale is required")
    approved_at = approval.get("approvedAt")
    try:
        parsed_time = datetime.fromisoformat(approved_at) if isinstance(approved_at, str) else None
    except ValueError:
        parsed_time = None
    if parsed_time is None or parsed_time.tzinfo is None:
        errors.append(f"{benchmark_id}: approvedAt must be a timezone-aware ISO timestamp")
    return errors


def load_registry(repo: Path) -> tuple[dict[str, Any] | None, dict[str, bytes], list[str]]:
    repo = repo.resolve(strict=True)
    assets: dict[str, bytes] = {}
    errors: list[str] = []
    _, registry_payload, registry_path_error = safe_snapshot(repo, REGISTRY_PATH)
    _, schema_payload, schema_path_error = safe_snapshot(repo, REGISTRY_SCHEMA_PATH)
    if registry_path_error or registry_payload is None:
        errors.append(f"benchmark registry: {registry_path_error}")
    if schema_path_error or schema_payload is None:
        errors.append(f"benchmark registry schema: {schema_path_error}")
    if errors:
        return None, assets, errors
    assert registry_payload is not None and schema_payload is not None
    registry, registry_parse_error = parse_json(registry_payload, REGISTRY_PATH)
    schema, schema_parse_error = parse_json(schema_payload, REGISTRY_SCHEMA_PATH)
    if registry_parse_error:
        errors.append(registry_parse_error)
    if schema_parse_error:
        errors.append(schema_parse_error)
    if errors or not isinstance(registry, dict):
        return None, assets, errors or ["benchmark registry must be an object"]
    errors.extend(document_schema_errors(registry, schema, "registry"))
    if errors:
        return registry, assets, errors

    benchmarks = registry["benchmarks"]
    ids = [item["id"] for item in benchmarks]
    if len(ids) != len(set(ids)):
        errors.append("benchmark IDs must be unique")
    kinds = {item["kind"] for item in benchmarks}
    if not {"golden-parsing", "contract-validation"} <= kinds:
        errors.append("registry requires at least one golden-parsing and one contract-validation benchmark")
    for item in benchmarks:
        benchmark_id = item["id"]
        if EXECUTOR_KIND[item["executor"]] != item["kind"]:
            errors.append(f"{benchmark_id}: executor is incompatible with benchmark kind")
        canonical_baseline_path = f"{BASELINE_ROOT}{benchmark_id}.json"
        if item["expected"]["path"] != canonical_baseline_path:
            errors.append(f"{benchmark_id}: expected output must use canonical path {canonical_baseline_path}")
        path_specs = [item["dataset"], item["expected"], *item["schemas"]]
        for specification in path_specs:
            raw_path = specification["path"]
            _, payload, path_error = safe_snapshot(repo, raw_path)
            if path_error or payload is None:
                errors.append(f"{benchmark_id}: {path_error}")
                continue
            assets[raw_path] = payload
            if sha256(payload) != specification["sha256"]:
                errors.append(f"{benchmark_id}: SHA-256 mismatch for {raw_path}")
        prompt = item["prompt"]
        if prompt["id"] != "none":
            canonical_prompt_path = f"{PROMPT_ROOT}{prompt['id']}-{prompt['version']}.txt"
            if prompt["path"] != canonical_prompt_path:
                errors.append(f"{benchmark_id}: prompt must use canonical path {canonical_prompt_path}")
            _, prompt_payload, prompt_path_error = safe_snapshot(repo, prompt["path"])
            if prompt_path_error or prompt_payload is None:
                errors.append(f"{benchmark_id}: {prompt_path_error}")
            else:
                assets[prompt["path"]] = prompt_payload
                if sha256(prompt_payload) != prompt["sha256"]:
                    errors.append(f"{benchmark_id}: SHA-256 mismatch for {prompt['path']}")
        baseline = item["baseline"]
        if baseline["expectedPath"] != item["expected"]["path"]:
            errors.append(f"{benchmark_id}: baseline expectedPath must equal expected-output path")
        if baseline["sha256"] != item["expected"]["sha256"]:
            errors.append(f"{benchmark_id}: baseline hash must equal expected-output hash")
        version = baseline["version"]
        history = baseline["history"]
        if len(history) != version - 1:
            errors.append(f"{benchmark_id}: baseline history length must equal version minus one")
        for index, entry in enumerate(history, start=1):
            if entry["version"] != index:
                errors.append(f"{benchmark_id}: baseline history versions must be contiguous from 1")
            if entry["expectedPath"] != canonical_baseline_path:
                errors.append(f"{benchmark_id}: historical baseline paths must remain canonical")
        if version == 1 and (baseline["currentApproval"] is not None or baseline["currentApprovalSha256"] is not None):
            errors.append(f"{benchmark_id}: initial baseline must not claim a change approval or approval hash")
        if history and (history[0]["approval"] is not None or history[0]["approvalSha256"] is not None):
            errors.append(f"{benchmark_id}: version-1 history must not claim a change approval or approval hash")
        for history_index, entry in enumerate(history[1:], start=1):
            if not entry["approval"] or not entry["approvalSha256"]:
                errors.append(
                    f"{benchmark_id}: historical baseline version {entry['version']} requires pinned approval"
                )
                continue
            errors.extend(
                approval_errors(
                    repo,
                    assets,
                    benchmark_id,
                    entry["version"],
                    history[history_index - 1]["sha256"],
                    entry["sha256"],
                    entry["approval"],
                    entry["approvalSha256"],
                )
            )
        if version > 1:
            if not history:
                errors.append(f"{benchmark_id}: changed baseline requires prior history")
            elif not baseline["currentApproval"] or not baseline["currentApprovalSha256"]:
                errors.append(f"{benchmark_id}: changed baseline requires pinned currentApproval")
            else:
                if history[-1]["sha256"] == baseline["sha256"]:
                    errors.append(f"{benchmark_id}: baseline version cannot increment without output change")
                errors.extend(
                    approval_errors(
                        repo,
                        assets,
                        benchmark_id,
                        version,
                        history[-1]["sha256"],
                        baseline["sha256"],
                        baseline["currentApproval"],
                        baseline["currentApprovalSha256"],
                    )
                )
        if item["kind"] == "contract-validation" and len(item["schemas"]) != 1:
            errors.append(f"{benchmark_id}: contract benchmark requires exactly one schema")
        if item["kind"] == "golden-parsing" and item["schemas"]:
            errors.append(f"{benchmark_id}: golden parser does not consume a schema")
    errors.extend(git_history_errors(repo, registry))
    return registry, assets, errors


def normalized_issued(raw: Any) -> str | None:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        parts = raw.get("dateParts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list):
            values = parts[0]
            if values and all(isinstance(value, int) for value in values):
                return "-".join(f"{value:02d}" if index else str(value) for index, value in enumerate(values))
    return None


def normalize_metadata(payload: bytes) -> dict[str, Any]:
    source = json.loads(payload.decode("utf-8"))
    seen_dois: dict[str, str] = {}
    normalized: list[dict[str, Any]] = []
    for record in source["records"]:
        authors = []
        for author in record.get("authors", []):
            if author.get("literal"):
                authors.append(author["literal"])
            else:
                authors.append(", ".join(value for value in (author.get("family"), author.get("given")) if value))
        doi = record.get("doi")
        canonical_doi = doi.casefold() if isinstance(doi, str) else None
        duplicate_of = seen_dois.get(canonical_doi) if canonical_doi else None
        if canonical_doi and duplicate_of is None:
            seen_dois[canonical_doi] = record["fixtureId"]
        missing = sorted(field for field in TRACKED_METADATA_FIELDS if not record.get(field))
        normalized.append(
            {
                "id": record["fixtureId"],
                "title": record["title"],
                "authors": authors,
                "issued": normalized_issued(record.get("issued")),
                "containerTitle": record.get("containerTitle"),
                "doi": canonical_doi,
                "duplicateOf": duplicate_of,
                "missingFields": missing,
                "language": record.get("language"),
            }
        )
    return {"schemaVersion": "1.0", "records": normalized}


def validate_contract(dataset: bytes, schema_payload: bytes) -> dict[str, Any]:
    value = json.loads(dataset.decode("utf-8"))
    schema = json.loads(schema_payload.decode("utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    failures = sorted(validator.iter_errors(value), key=lambda error: [str(part) for part in error.path])
    messages = [
        f"{'.'.join(str(part) for part in failure.path) or '<root>'}: {failure.message}" for failure in failures
    ]
    return {
        "schemaId": schema.get("$id"),
        "valid": not messages,
        "errorCount": len(messages),
        "errors": messages,
    }


def run_benchmarks(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry, assets, errors = load_registry(repo)
    if errors or registry is None:
        return {
            "schemaVersion": "1.0",
            "documentType": "benchmark-run-report",
            "status": "FAIL",
            "registryVersion": registry.get("registryVersion") if registry else None,
            "errors": errors,
            "results": [],
        }, {}
    results: list[dict[str, Any]] = []
    actuals: dict[str, Any] = {}
    for item in registry["benchmarks"]:
        dataset = assets[item["dataset"]["path"]]
        if item["executor"] == "metadata-json-normalizer-v1":
            actual = normalize_metadata(dataset)
        else:
            schema_payload = assets[item["schemas"][0]["path"]]
            actual = validate_contract(dataset, schema_payload)
        expected, parse_error = parse_json(assets[item["expected"]["path"]], item["expected"]["path"])
        matches = parse_error is None and actual == expected
        actuals[item["id"]] = actual
        results.append(
            {
                "benchmarkId": item["id"],
                "kind": item["kind"],
                "status": "PASS" if matches else "FAIL",
                "datasetSha256": item["dataset"]["sha256"],
                "expectedSha256": item["expected"]["sha256"],
                "actualCanonicalSha256": sha256(canonical_json_bytes(actual)),
                "baselineVersion": item["baseline"]["version"],
                "tolerance": item["tolerance"],
                "metrics": {"exactMatch": 1 if matches else 0},
                "diagnostic": parse_error or (None if matches else "actual output differs from approved baseline"),
            }
        )
    status = "PASS" if all(result["status"] == "PASS" for result in results) else "FAIL"
    return {
        "schemaVersion": "1.0",
        "documentType": "benchmark-run-report",
        "status": status,
        "registryVersion": registry["registryVersion"],
        "errors": [],
        "results": results,
    }, actuals


def safe_output_path(repo: Path, raw_path: Path, allow_directory: bool = False) -> Path:
    destination = raw_path if raw_path.is_absolute() else repo / raw_path
    destination = destination.absolute()
    artifacts_root = (repo / "artifacts").resolve(strict=True)
    report_root_path = repo / REPORT_ROOT
    if not report_root_path.exists():
        report_root_path.mkdir()
    report_root = report_root_path.resolve(strict=True)
    if report_root != artifacts_root / "tmp" or not report_root.is_dir():
        raise ValueError(f"scratch root must not redirect outside repository artifacts: {report_root}")
    candidate = destination if allow_directory else destination.parent
    try:
        candidate.resolve(strict=False).relative_to(report_root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"output must remain under {REPORT_ROOT}: {raw_path}") from exc
    return destination


def atomic_write_json(destination: Path, value: Any) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f"{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        assert temporary is not None
        os.replace(temporary, destination)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--proposal-dir", type=Path)
    args = parser.parse_args()
    repo = Path(args.repo).resolve(strict=True)
    report, actuals = run_benchmarks(repo)
    for error in report["errors"]:
        print(f"ERROR: {error}")
    for result in report["results"]:
        print(f"{result['status']} [{result['benchmarkId']}] exactMatch={result['metrics']['exactMatch']}")
    if args.report:
        try:
            atomic_write_json(safe_output_path(repo, args.report), report)
        except (OSError, ValueError) as exc:
            print(f"ERROR: cannot write benchmark report: {exc}")
            return 2
    if args.proposal_dir and report["status"] == "FAIL" and actuals:
        try:
            proposal_dir = safe_output_path(repo, args.proposal_dir, allow_directory=True)
            for benchmark_id, actual in actuals.items():
                atomic_write_json(proposal_dir / f"{benchmark_id}.json", actual)
        except (OSError, ValueError) as exc:
            print(f"ERROR: cannot write benchmark proposals: {exc}")
            return 2
    print(
        f"Benchmark registry: {report['status']} - {len(report['results'])} executed, "
        f"registry v{report['registryVersion']}"
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
