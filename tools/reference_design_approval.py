"""Authenticate pre-Wave reference publication; never grant Wave execution."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath

import yaml
from ui_reference_check import INVENTORY_EXCLUSIONS, canonical_payload

DESIGN_APPROVAL_AUTHORITY_KEYS = frozenset(
    {
        "design_approval_record",
        "design_approval_record_sha256",
        "design_approval_record_introduction_commit",
    }
)
RECORD_KEYS = {"schemaVersion", "kind", "referenceId", "approvedBy", "approvedAt", "scope", "proposal", "basis"}
METADATA_KEYS = {"status", "approval_kind", "approved_by", "approved_at", "approval_basis", "authority"}


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError("Git identity, ancestry, or clean-input check failed")
    return result.stdout


def _path(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not any(part in value for part in ("\\", ":", "//"))
        and not value.startswith("/")
        and str(PurePosixPath(value)) == value
        and all(part not in {".", ".."} for part in PurePosixPath(value).parts)
    )


def _inventory(repo: Path, revision: str, prefix: str) -> set[str]:
    result = set()
    for entry in _git(repo, "ls-tree", "-r", "-z", revision, "--", prefix).split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        mode, kind, _ = metadata.decode().split()
        name = path.decode().removeprefix(prefix + "/")
        if mode not in {"100644", "100755"} or kind != "blob" or not _path(name):
            raise ValueError("reference inventory contains redirected or nonregular content")
        if not name.startswith("previews/") and "__pycache__" not in name and name not in INVENTORY_EXCLUSIONS:
            result.add(name)
    return result


def authority_shape_errors(authority: object, reference_id: str) -> list[str]:
    if not isinstance(authority, dict) or set(authority) != DESIGN_APPROVAL_AUTHORITY_KEYS:
        return ["design approval authority fields must be exact"]
    if (
        not re.fullmatch(r"RO-UI-[A-Z0-9.-]+", reference_id)
        or authority["design_approval_record"] != f"planning/reference-approvals/{reference_id}.json"
        or not re.fullmatch(r"[0-9a-f]{64}", str(authority["design_approval_record_sha256"]))
        or not re.fullmatch(r"[0-9a-f]{40}", str(authority["design_approval_record_introduction_commit"]))
    ):
        return ["design approval authority identity or digest is invalid"]
    return []


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate approval record field")
        result[key] = value
    return result


def _consuming_publications(repo: Path, revision: str, path: str, record_hash: str) -> set[str]:
    """Count introductions across all reachable branches, not inherited merges."""
    matches: dict[str, bool] = {}

    def uses_record(commit: str) -> bool:
        if commit not in matches:
            if not _git(repo, "ls-tree", commit, "--", path).strip():
                matches[commit] = False
            else:
                value = yaml.safe_load(_git(repo, "show", f"{commit}:{path}"))
                authority = value.get("authority") if isinstance(value, dict) else None
                matches[commit] = (
                    isinstance(authority, dict) and authority.get("design_approval_record_sha256") == record_hash
                )
        return matches[commit]

    consumers = set()
    for commit in _git(repo, "log", "--full-history", "--format=%H", revision, "--", path).decode().split():
        if uses_record(commit):
            parents = _git(repo, "rev-list", "--parents", "-n", "1", commit).decode().split()[1:]
            if not any(uses_record(parent) for parent in parents):
                consumers.add(commit)
    return consumers


def design_authority_bound_approval_errors(
    repo: Path,
    approval: dict,
    approval_commit: str,
    approval_path: str,
    *,
    reference_revision: str | None = None,
) -> list[str]:
    """Prove immutable human record -> exact proposal -> metadata-only publication."""
    label = "Pre-Wave reference design approval"
    authority = approval.get("authority")
    errors = authority_shape_errors(authority, str(approval.get("reference_id", "")))
    if errors:
        return [f"{label}: {error}" for error in errors]
    assert isinstance(authority, dict)  # The exact-shape check above established this.
    try:
        package_revision = reference_revision or approval_commit
        if package_revision != approval_commit:
            # The later tree cannot repair an unapproved original publication.
            original_errors = design_authority_bound_approval_errors(repo, approval, approval_commit, approval_path)
            if original_errors:
                return original_errors
            _git(repo, "merge-base", "--is-ancestor", approval_commit, package_revision)
        if approval_path != "design/ui-reference/APPROVAL.yaml" or not re.fullmatch(r"[0-9a-f]{40}", approval_commit):
            raise ValueError("publication path or commit is invalid")
        record_path = authority["design_approval_record"]
        introduction = authority["design_approval_record_introduction_commit"]
        raw = _git(repo, "show", f"{introduction}:{record_path}")
        if hashlib.sha256(raw).hexdigest() != authority["design_approval_record_sha256"]:
            raise ValueError("owner record digest differs")
        if (
            _git(repo, "diff-tree", "--root", "--no-commit-id", "--name-status", "-r", introduction, "--", record_path)
            .decode()
            .strip()
            != f"A\t{record_path}"
        ):
            raise ValueError("owner record is not bound to its introduction")
        for revision in (approval_commit, "HEAD"):
            if _git(repo, "show", f"{revision}:{record_path}") != raw:
                raise ValueError("owner record changed after its introduction")
            if _git(repo, "log", "-1", "--format=%H", revision, "--", record_path).decode().strip() != introduction:
                raise ValueError("owner record history changed after its introduction")
            if not _git(repo, "ls-tree", revision, "--", record_path).startswith(b"100644 blob "):
                raise ValueError("owner record must be regular committed text")
        _git(repo, "diff", "--quiet", "--no-ext-diff", "HEAD", "--", record_path)
        record = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(record, dict) or set(record) != RECORD_KEYS:
            raise ValueError("owner record fields must be exact")
        if (
            record["schemaVersion"] != "1.0"
            or record["kind"] != "ui-reference-design-approval"
            or record["scope"] != "reference-publication-and-plan-binding-only"
            or record["referenceId"] != approval.get("reference_id")
            or not re.fullmatch(r"human:[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", str(record["approvedBy"]))
            or not isinstance(record["basis"], str)
            or not record["basis"].strip()
        ):
            raise ValueError("owner record identity, human, or scope is invalid")
        datetime.fromisoformat(record["approvedAt"])
        proposal = record["proposal"]
        if not isinstance(proposal, dict) or set(proposal) != {"commit", "path", "packageSha256"}:
            raise ValueError("proposal binding fields must be exact")
        candidate, prefix = proposal["commit"], proposal["path"]
        if (
            not re.fullmatch(r"[0-9a-f]{40}", str(candidate))
            or not _path(prefix)
            or not prefix.startswith("planning/")
            or prefix.endswith("/")
            or not re.fullmatch(r"[0-9a-f]{64}", str(proposal["packageSha256"]))
        ):
            raise ValueError("proposal binding is invalid")
        _git(repo, "merge-base", "--is-ancestor", candidate, introduction)
        _git(repo, "merge-base", "--is-ancestor", introduction, approval_commit)
        if introduction in {candidate, approval_commit}:
            raise ValueError("owner record must follow proposal and precede publication")
        parents = _git(repo, "rev-list", "--parents", "-n", "1", approval_commit).decode().split()[1:]
        if len(parents) != 1:
            raise ValueError("publication must have one predecessor")
        prior = yaml.safe_load(_git(repo, "show", f"{parents[0]}:{approval_path}"))
        if (
            not isinstance(prior, dict)
            or approval.get("supersedes") != prior.get("reference_id")
            or prior.get("reference_id") == approval.get("reference_id")
        ):
            raise ValueError("publication does not exactly supersede its predecessor")
        if _consuming_publications(
            repo, package_revision, approval_path, authority["design_approval_record_sha256"]
        ) != {approval_commit}:
            raise ValueError("owner approval must have exactly one reachable consuming publication")

        source_manifest = yaml.safe_load(_git(repo, "show", f"{candidate}:{prefix}/REFERENCE_MANIFEST.yaml"))
        target_manifest = yaml.safe_load(
            _git(repo, "show", f"{package_revision}:design/ui-reference/REFERENCE_MANIFEST.yaml")
        )
        if not isinstance(source_manifest, dict) or not isinstance(target_manifest, dict):
            raise ValueError("reference manifests must be objects")
        names = source_manifest.get("governed_files")
        hashes = source_manifest.get("file_hashes")
        if (
            source_manifest.get("status") != "proposed"
            or source_manifest.get("reference_id") != record["referenceId"]
            or not isinstance(names, list)
            or not names
            or any(not _path(name) for name in names)
            or len(set(names)) != len(names)
            or "APPROVAL.yaml" not in names
            or "REFERENCE_MANIFEST.yaml" in names
            or not isinstance(hashes, dict)
            or set(names) != set(hashes)
        ):
            raise ValueError("proposal inventory or identity is invalid")
        if _inventory(repo, candidate, prefix) != set(names) or _inventory(
            repo, package_revision, "design/ui-reference"
        ) != set(names):
            raise ValueError("actual reference inventory differs from the approved proposal")
        observed = {}
        for name in names:
            source = canonical_payload(name, _git(repo, "show", f"{candidate}:{prefix}/{name}"))
            target = canonical_payload(name, _git(repo, "show", f"{package_revision}:design/ui-reference/{name}"))
            observed[name] = hashlib.sha256(source).hexdigest()
            if name == "APPROVAL.yaml":
                source_approval = yaml.safe_load(source)
                target_approval = yaml.safe_load(target)
                if (
                    not isinstance(source_approval, dict)
                    or source_approval.get("status") != "proposed"
                    or source_approval.get("reference_id") != record["referenceId"]
                    or source_approval.get("version") != source_manifest.get("version")
                    or any(
                        source_approval.get(key) is not None
                        for key in ("approved_by", "approved_at", "approval_basis", "authority")
                    )
                ):
                    raise ValueError("source approval is not an exact unapproved proposal")
                expected = {**source_approval, **{key: approval.get(key) for key in METADATA_KEYS}}
                if (
                    target_approval != approval
                    or target_approval != expected
                    or approval.get("status") != "approved"
                    or approval.get("approval_kind") != "human"
                    or approval.get("approved_by") != record["approvedBy"]
                    or approval.get("approved_at") != record["approvedAt"]
                ):
                    raise ValueError("publication changed reviewed scope or human authority")
                approval_hash = hashlib.sha256(target).hexdigest()
            elif source != target:
                raise ValueError("publication changed nonmetadata proposal content")
        if (
            observed != hashes
            or hashlib.sha256(
                json.dumps(observed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            != proposal["packageSha256"]
        ):
            raise ValueError("proposal package differs from the owner's exact decision")
        expected_manifest = {
            **source_manifest,
            "status": "approved",
            "file_hashes": {**hashes, "APPROVAL.yaml": approval_hash},
        }
        if target_manifest != expected_manifest:
            raise ValueError("publication manifest changed beyond approval metadata")
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError, yaml.YAMLError) as exc:
        return [f"{label}: {exc}"]
    return []
