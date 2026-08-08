#!/usr/bin/env python3
"""Validate the repository architecture map and dependency contract."""

from __future__ import annotations

import argparse
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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
