#!/usr/bin/env python3
"""Validate the repository architecture map and dependency contract."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

REQUIRED_PROFILE_STATES = {
    "local": ("W0-W5", "release-authoritative-first"),
    "university": ("W10", "deferred-behind-release-gate"),
    "cloud": ("W11", "deferred-behind-release-gate"),
}
REQUIRED_STABLE_INTERFACES = {
    "portable-domain-contracts",
    "desktop-core-loopback-api",
    "worker-activity-contract",
    "academic-minimal-design-contract",
    "portable-project-bundle",
}
_DATABASE_MODULES = {"sqlite3", "sqlalchemy"}
_DATABASE_CALLS = {"connect", "cursor", "execute", "executemany", "executescript"}
_CONNECTION_AUTHORITIES = {"CanonicalConnection", "open_canonical_database"}


def _is_storage_module(module: str) -> bool:
    return module == "storage" or module.endswith(".storage")


def _is_concrete_repository_module(module: str) -> bool:
    parts = module.split(".")
    return bool(parts) and parts[-1] == "repositories" and (len(parts) < 2 or parts[-2] != "ports")


def _is_concrete_object_store_module(module: str) -> bool:
    parts = module.split(".")
    return bool(parts) and parts[-1] == "object_store" and (len(parts) < 2 or parts[-2] != "ports")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def core_data_boundary_errors(source_root: Path) -> list[str]:
    """Deny database dependencies and dynamic SQL outside Core data adapters."""

    root = Path(source_root)
    errors: list[str] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        is_adapter = relative in {"object_store.py", "repositories.py", "storage.py"} or "migrations" in parts
        is_port = "ports" in parts
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_level = alias.name.split(".")[0]
                    if (is_port or not is_adapter) and top_level in _DATABASE_MODULES:
                        errors.append(f"{relative}:{node.lineno}: database dependency outside adapter")
                    if not is_adapter and _is_storage_module(alias.name):
                        errors.append(f"{relative}:{node.lineno}: imports storage connection authority")
                    if not is_adapter and path.name != "main.py" and _is_concrete_repository_module(alias.name):
                        errors.append(f"{relative}:{node.lineno}: imports concrete repository adapter")
                    if not is_adapter and path.name != "main.py" and _is_concrete_object_store_module(alias.name):
                        errors.append(f"{relative}:{node.lineno}: imports concrete object-store adapter")
            elif isinstance(node, ast.ImportFrom):
                full_module = node.module or ""
                module = full_module.split(".")[0]
                imported = {alias.name for alias in node.names}
                if (is_port or not is_adapter) and module in _DATABASE_MODULES:
                    errors.append(f"{relative}:{node.lineno}: database dependency outside adapter")
                if is_port and full_module.split(".")[-1] in {"repositories", "storage"}:
                    errors.append(f"{relative}:{node.lineno}: port depends on concrete data adapter")
                if not is_adapter and _is_storage_module(full_module):
                    for authority in sorted(imported & _CONNECTION_AUTHORITIES):
                        errors.append(f"{relative}:{node.lineno}: imports {authority} connection authority")
                if (
                    not is_adapter
                    and "storage" in imported
                    and (not full_module or full_module.endswith("research_observatory_core"))
                ):
                    errors.append(f"{relative}:{node.lineno}: imports storage connection authority")
                if (
                    not is_adapter
                    and path.name != "main.py"
                    and (
                        _is_concrete_repository_module(full_module)
                        or (
                            "repositories" in imported
                            and (not full_module or full_module.endswith("research_observatory_core"))
                        )
                    )
                ):
                    errors.append(f"{relative}:{node.lineno}: business module imports concrete repository adapter")
                if (
                    not is_adapter
                    and path.name != "main.py"
                    and (
                        _is_concrete_object_store_module(full_module)
                        or (
                            "object_store" in imported
                            and (not full_module or full_module.endswith("research_observatory_core"))
                        )
                    )
                ):
                    errors.append(f"{relative}:{node.lineno}: business module imports concrete object-store adapter")
            elif (
                not is_adapter
                and isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _DATABASE_CALLS
            ):
                errors.append(f"{relative}:{node.lineno}: database call {node.func.attr} outside adapter")
    return errors


def validate_contract(repo: Path, contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    structure = load_json(repo / "repository-structure.json")
    generated = set(structure["forbidden_tracked_generated_directories"])

    areas = contract.get("repositoryAreas", [])
    area_paths = [area.get("path") for area in areas]
    if len(area_paths) != len(set(area_paths)):
        errors.append("repositoryAreas contains duplicate paths")
    actual_areas = {
        path.name
        for path in repo.iterdir()
        if path.is_dir() and not path.name.startswith(".") and path.name not in generated
    }
    missing_areas = sorted(actual_areas - set(area_paths))
    extra_areas = sorted(set(area_paths) - actual_areas)
    if missing_areas:
        errors.append(f"top-level repository areas lack architecture purpose: {missing_areas}")
    if extra_areas:
        errors.append(f"architecture contract declares absent top-level areas: {extra_areas}")
    for area in areas:
        if not str(area.get("purpose", "")).strip():
            errors.append(f"repository area {area.get('path')!r} lacks a purpose")

    modules = contract.get("modules", [])
    module_paths = [module.get("path") for module in modules]
    if len(module_paths) != len(set(module_paths)):
        errors.append("modules contains duplicate paths")
    required_modules = {module["path"] for module in structure["modules"]}
    missing_modules = sorted(required_modules - set(module_paths))
    extra_modules = sorted(set(module_paths) - required_modules)
    if missing_modules:
        errors.append(f"repository modules lack architecture rules: {missing_modules}")
    if extra_modules:
        errors.append(f"architecture contract declares ungoverned modules: {extra_modules}")

    support_targets = set(contract.get("supportTargets", {}))
    valid_targets = set(module_paths) | support_targets
    allowed_edges: set[tuple[str, str]] = set()
    for module in modules:
        path = module.get("path")
        if not str(module.get("purpose", "")).strip() or not str(module.get("layer", "")).strip():
            errors.append(f"module {path!r} must declare a purpose and layer")
        dependencies = module.get("allowedDependencies")
        if not isinstance(dependencies, list):
            errors.append(f"module {path!r} must declare allowedDependencies as a list")
            continue
        for dependency in dependencies:
            if dependency not in valid_targets:
                errors.append(f"module {path!r} allows unknown dependency {dependency!r}")
            if dependency == path:
                errors.append(f"module {path!r} cannot depend on itself")
            allowed_edges.add((path, dependency))

    prohibited = contract.get("prohibitedDependencies", [])
    prohibited_edges: set[tuple[str, str]] = set()
    for rule in prohibited:
        edge = (rule.get("from"), rule.get("to"))
        prohibited_edges.add(edge)
        if edge[0] not in module_paths or edge[1] not in module_paths:
            errors.append(f"prohibited dependency references unknown module: {edge}")
        if not str(rule.get("reason", "")).strip():
            errors.append(f"prohibited dependency {edge} lacks a reason")
    conflicts = sorted(allowed_edges & prohibited_edges)
    if conflicts:
        errors.append(f"dependencies are both allowed and prohibited: {conflicts}")

    interfaces = contract.get("stableInterfaces", [])
    interface_ids = {interface.get("id") for interface in interfaces}
    missing_interfaces = sorted(REQUIRED_STABLE_INTERFACES - interface_ids)
    if missing_interfaces:
        errors.append(f"stable interface list is incomplete: {missing_interfaces}")
    for interface in interfaces:
        for field in ("owner", "consumers", "contents", "changeControl"):
            if not interface.get(field):
                errors.append(f"stable interface {interface.get('id')!r} lacks {field}")

    profiles = {profile.get("id"): profile for profile in contract.get("deploymentProfiles", [])}
    if set(profiles) != set(REQUIRED_PROFILE_STATES):
        errors.append("deployment profiles must be exactly local, university, and cloud")
    for profile_id, (phase, status) in REQUIRED_PROFILE_STATES.items():
        profile = profiles.get(profile_id, {})
        if (profile.get("implementationPhase"), profile.get("status")) != (phase, status):
            errors.append(f"{profile_id} profile phase/status does not match the architecture baseline")
        for field in ("client", "projectAuthority", "networkBoundary", "infrastructureBoundary"):
            if not str(profile.get(field, "")).strip():
                errors.append(f"{profile_id} profile lacks {field}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    contract = load_json(repo / "architecture-boundaries.json")
    errors = validate_contract(repo, contract)
    errors.extend(core_data_boundary_errors(repo / "services" / "core-api" / "src" / "research_observatory_core"))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        "Architecture contract: pass - "
        f"{len(contract['repositoryAreas'])} areas, {len(contract['modules'])} modules, "
        f"{len(contract['stableInterfaces'])} stable interfaces, and 3 deployment profiles"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
