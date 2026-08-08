#!/usr/bin/env python3
"""Validate the versioned W0-W5 repository skeleton without third-party packages."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


REQUIRED_MODULES = {
    "apps/desktop",
    "services/core-api",
    "workers",
    "packages/contracts",
    "packages/ui-tokens",
    "packages/ui-components",
    "tests/foundation",
    "tests/desktop",
    "tests/contracts",
    "tests/e2e",
    "tests/packaging",
    "packaging/windows",
}


def _safe_relative_path(raw: Any) -> PurePosixPath | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        return None
    return path


def _candidate_files(repo: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return [repo / Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]
    return [path for path in repo.rglob("*") if path.is_file() and ".git" not in path.parts]


def validate_repository(repo: Path, manifest_path: Path | None = None) -> list[str]:
    repo = repo.resolve()
    manifest_path = manifest_path or repo / "repository-structure.json"
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Cannot read repository structure contract: {exc}"]

    if manifest.get("schema_version") != "1.0":
        errors.append("repository-structure.json must use schema_version 1.0")
    modules = manifest.get("modules")
    if not isinstance(modules, list):
        return errors + ["repository-structure.json modules must be an array"]

    declared: dict[str, dict[str, Any]] = {}
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            errors.append(f"modules[{index}] must be an object")
            continue
        relative = _safe_relative_path(module.get("path"))
        if relative is None:
            errors.append(f"modules[{index}].path must be a safe repository-relative path")
            continue
        normalized = relative.as_posix()
        if normalized in declared:
            errors.append(f"Duplicate module declaration: {normalized}")
            continue
        declared[normalized] = module

        module_dir = repo.joinpath(*relative.parts)
        if not module_dir.is_dir():
            errors.append(f"Missing module directory: {normalized}")
            continue
        owner = module.get("owner")
        boundary = module.get("boundary")
        if not isinstance(owner, str) or not owner.strip():
            errors.append(f"Module {normalized} has no owner")
        if not isinstance(boundary, str) or not boundary.strip():
            errors.append(f"Module {normalized} has no boundary")
        readme = module_dir / "README.md"
        if not readme.is_file():
            errors.append(f"Module {normalized} has no README.md")
            continue
        content = readme.read_text(encoding="utf-8")
        if isinstance(owner, str) and f"Owner: {owner}" not in content:
            errors.append(f"Module {normalized} README does not name its declared owner")
        if "Boundary:" not in content:
            errors.append(f"Module {normalized} README does not document its boundary")

    for missing in sorted(REQUIRED_MODULES - set(declared)):
        errors.append(f"Required module is not declared: {missing}")

    deferred = manifest.get("deferred_implementation_paths", [])
    if not isinstance(deferred, list):
        errors.append("deferred_implementation_paths must be an array")
    else:
        for raw in deferred:
            relative = _safe_relative_path(raw)
            if relative is None:
                errors.append(f"Invalid deferred implementation path: {raw!r}")
            elif repo.joinpath(*relative.parts).exists():
                errors.append(f"Deferred implementation path must be absent: {relative.as_posix()}")

    suffixes = {str(value).lower() for value in manifest.get("forbidden_tracked_binary_suffixes", [])}
    generated_dirs = set(manifest.get("forbidden_tracked_generated_directories", []))
    for path in _candidate_files(repo):
        relative = path.relative_to(repo)
        if path.suffix.lower() in suffixes:
            errors.append(f"Tracked generated binary is forbidden: {relative.as_posix()}")
        if any(part in generated_dirs for part in relative.parts[:-1]):
            errors.append(f"Tracked file is inside a generated directory: {relative.as_posix()}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root")
    parser.add_argument("--manifest", help="Optional structure contract path")
    args = parser.parse_args()
    repo = Path(args.repo)
    manifest = Path(args.manifest) if args.manifest else None
    errors = validate_repository(repo, manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Repository structure: pass - {len(REQUIRED_MODULES)} required modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
