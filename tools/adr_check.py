#!/usr/bin/env python3
"""Validate ADR records and require coverage for changed protected paths."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml


ADR_ID = re.compile(r"^ADR-\d{4}$")
REQUIRED_SECTIONS = ["## Context", "## Candidates", "## Decision", "## Consequences", "## Verification", "## Task links"]
ACTIVE_CHANGE_STATES = {"Proposed", "Accepted"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_adr(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError(f"{path.as_posix()} must begin with YAML front matter")
    metadata = yaml.safe_load(parts[1])
    if not isinstance(metadata, dict):
        raise ValueError(f"{path.as_posix()} front matter must be a mapping")
    return metadata, parts[2]


def task_ids(backlog: dict[str, Any]) -> set[str]:
    return {
        task["id"]
        for capability in backlog["capabilities"]
        for slice_ in capability["slices"]
        for task in slice_["tasks"]
    }


def validate_registry(repo: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    index = load_json(repo / "docs" / "adr" / "index.json")
    allowed_states = set(index.get("allowedStates", []))
    expected_states = {"Proposed", "Accepted", "Rejected", "Superseded"}
    if allowed_states != expected_states:
        errors.append("ADR index states must be Proposed, Accepted, Rejected, and Superseded")
    entries = index.get("records", [])
    indexed_ids = [entry.get("id") for entry in entries]
    if len(indexed_ids) != len(set(indexed_ids)):
        errors.append("ADR index contains duplicate identifiers")

    adr_dir = repo / "docs" / "adr"
    actual_paths = {
        path.relative_to(repo).as_posix()
        for path in adr_dir.glob("ADR-[0-9][0-9][0-9][0-9]-*.md")
    }
    indexed_paths = {entry.get("path") for entry in entries}
    for path in sorted(actual_paths - indexed_paths):
        errors.append(f"unindexed ADR file: {path}")
    for path in sorted(indexed_paths - actual_paths):
        errors.append(f"ADR index references missing file: {path}")

    backlog = yaml.safe_load((repo / "planning" / "backlog.yaml").read_text(encoding="utf-8"))
    valid_tasks = task_ids(backlog)
    records: dict[str, dict[str, Any]] = {}
    for entry in entries:
        relative = entry.get("path")
        if relative not in actual_paths:
            continue
        try:
            metadata, body = parse_adr(repo / relative)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(str(exc))
            continue
        adr_id = metadata.get("id")
        if not isinstance(adr_id, str) or not ADR_ID.fullmatch(adr_id):
            errors.append(f"{relative} has invalid ADR id {adr_id!r}")
            continue
        records[adr_id] = {"metadata": metadata, "body": body, "path": relative}
        for field in ("title", "status", "date", "decision_scope", "affected_paths"):
            if not metadata.get(field):
                errors.append(f"{adr_id} lacks required field {field}")
        if metadata.get("status") not in expected_states:
            errors.append(f"{adr_id} has unsupported status {metadata.get('status')!r}")
        if entry.get("id") != adr_id or entry.get("title") != metadata.get("title") or entry.get("status") != metadata.get("status"):
            errors.append(f"{adr_id} metadata does not match its index entry")
        links = metadata.get("linked_tasks") or []
        if entry.get("linkedTasks") != links:
            errors.append(f"{adr_id} linked tasks do not match its index entry")
        unknown_tasks = sorted(set(links) - valid_tasks)
        if not links or unknown_tasks:
            errors.append(f"{adr_id} must link existing backlog tasks; unknown={unknown_tasks}")
        if metadata.get("status") == "Accepted" and not metadata.get("deciders"):
            errors.append(f"{adr_id} Accepted state requires deciders")
        if metadata.get("status") == "Superseded" and not metadata.get("superseded_by"):
            errors.append(f"{adr_id} Superseded state requires superseded_by")
        for section in REQUIRED_SECTIONS:
            if section not in body:
                errors.append(f"{adr_id} lacks required section {section}")

    for adr_id, record in records.items():
        metadata = record["metadata"]
        successor = metadata.get("superseded_by")
        if successor and successor not in records:
            errors.append(f"{adr_id} references unknown successor {successor}")
        for predecessor in metadata.get("supersedes") or []:
            if predecessor not in records:
                errors.append(f"{adr_id} supersedes unknown ADR {predecessor}")

    policy = load_json(repo / "architecture-protected-paths.json")
    patterns = [entry.get("pattern") for entry in policy.get("paths", [])]
    if not patterns or len(patterns) != len(set(patterns)):
        errors.append("protected architecture paths must be non-empty and unique")
    for entry in policy.get("paths", []):
        if not entry.get("pattern") or not entry.get("reason"):
            errors.append("each protected architecture path requires pattern and reason")
    return errors, records


def protected_matches(repo: Path, changed_path: str) -> list[str]:
    policy = load_json(repo / "architecture-protected-paths.json")
    return [
        entry["pattern"]
        for entry in policy["paths"]
        if fnmatch.fnmatchcase(changed_path, entry["pattern"])
    ]


def validate_change_set(
    repo: Path,
    changed_paths: list[str],
    records: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    normalized = {path.replace("\\", "/") for path in changed_paths}
    changed_records = [record for record in records.values() if record["path"] in normalized]
    for changed_path in sorted(normalized):
        protected_by = protected_matches(repo, changed_path)
        if not protected_by:
            continue
        covering = []
        for record in changed_records:
            metadata = record["metadata"]
            if metadata.get("status") not in ACTIVE_CHANGE_STATES:
                continue
            if any(fnmatch.fnmatchcase(changed_path, pattern) for pattern in metadata.get("affected_paths", [])):
                covering.append(metadata["id"])
        if not covering:
            errors.append(
                f"protected architecture change {changed_path!r} ({protected_by}) lacks a changed, indexed Proposed or Accepted ADR with matching affected_paths"
            )
    return errors


def git_changed_paths(repo: Path, base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}..{head}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--changed-file", action="append", default=[])
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    errors, records = validate_registry(repo)
    changed_paths = list(args.changed_file)
    if args.base:
        try:
            changed_paths.extend(git_changed_paths(repo, args.base, args.head))
        except RuntimeError as exc:
            errors.append(str(exc))
    if changed_paths:
        errors.extend(validate_change_set(repo, changed_paths, records))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    suffix = f"; {len(set(changed_paths))} changed paths inspected" if changed_paths else ""
    print(f"ADR registry: pass - {len(records)} indexed records{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
