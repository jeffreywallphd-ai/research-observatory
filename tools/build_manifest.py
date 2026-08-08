#!/usr/bin/env python3
"""Validate version contracts and emit a deterministic provenance build manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

VERSION_PATH = "packaging/product-version.json"
VERSION_SCHEMA_PATH = "packaging/product-version.schema.json"
INPUTS_PATH = "packaging/build-inputs.json"
COMPONENT_SCHEMA_PATH = "packaging/component-manifest.schema.json"
BUILD_SCHEMA_PATH = "packaging/build-manifest.schema.json"
REPORT_ROOT = "artifacts/tmp"
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
EXPECTED_COMPONENTS = frozenset(
    {
        ("desktop", "desktop", "apps/desktop/component-manifest.json"),
        ("core-api", "sidecar", "services/core-api/component-manifest.json"),
        ("worker-fabric", "sidecar", "workers/component-manifest.json"),
    }
)
EXPECTED_LOCKS = frozenset({("cargo", "Cargo.lock"), ("pnpm", "pnpm-lock.yaml"), ("uv", "uv.lock")})
GitRunner = Callable[..., subprocess.CompletedProcess[bytes]]


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def identified_set(entries: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(entries, key=lambda item: (str(item.get("id")), str(item.get("path"))))
    return {"setId": f"sha256:{sha256(canonical_json_bytes(ordered))}", "entries": ordered}


def safe_snapshot(repo: Path, raw_path: Any) -> tuple[bytes | None, str | None]:
    if not isinstance(raw_path, str):
        return None, "path must be a string"
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or ".." in pure.parts or "\\" in raw_path:
        return None, f"unsafe repository path: {raw_path!r}"
    lexical = repo.joinpath(*pure.parts)
    try:
        before = lexical.lstat()
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(repo)
    except (OSError, ValueError) as exc:
        return None, f"path does not resolve inside repository: {raw_path}: {exc}"
    if resolved != lexical or not resolved.is_file():
        return None, f"path must be a nonredirected file: {raw_path}"
    try:
        payload = resolved.read_bytes()
        after = lexical.lstat()
    except OSError as exc:
        return None, f"cannot read {raw_path}: {exc}"
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or lexical.resolve(strict=True) != resolved:
        return None, f"path changed while being read: {raw_path}"
    return payload, None


def parse_json(payload: bytes, label: str) -> tuple[Any | None, str | None]:
    try:
        return json.loads(payload.decode("utf-8")), None
    except (UnicodeError, json.JSONDecodeError) as exc:
        return None, f"cannot parse {label} as UTF-8 JSON: {exc}"


def load_json(repo: Path, path: str) -> tuple[Any | None, bytes | None, str | None]:
    payload, read_error = safe_snapshot(repo, path)
    if read_error or payload is None:
        return None, payload, read_error
    value, parse_error = parse_json(payload, path)
    return value, payload, parse_error


def schema_errors(value: Any, schema: Any, label: str) -> list[str]:
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return [f"invalid {label} schema: {exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    failures = sorted(validator.iter_errors(value), key=lambda error: [str(part) for part in error.path])
    return [
        f"{label}.{'.'.join(str(part) for part in failure.path) or '<root>'}: {failure.message}" for failure in failures
    ]


def expected_component(component: dict[str, Any], version: str) -> dict[str, Any]:
    major, minor, _ = version.split(".", maxsplit=2)
    return {
        "schemaVersion": "1.0",
        "documentType": "component-version-manifest",
        "componentId": component["id"],
        "componentKind": component["kind"],
        "version": version,
        "productVersionSource": VERSION_PATH,
        "compatibilityLine": f"{major}.{minor}",
    }


def configured_components(inputs: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    raw_components = inputs.get("components")
    if not isinstance(raw_components, list):
        return [], ["build inputs components must be an array"]
    components: list[dict[str, str]] = []
    errors: list[str] = []
    identities: list[tuple[str, str, str]] = []
    for component in raw_components:
        if not isinstance(component, dict) or set(component) != {"id", "kind", "manifestPath"}:
            errors.append("component input must contain exactly id, kind, and manifestPath")
            continue
        identity = (component.get("id"), component.get("kind"), component.get("manifestPath"))
        if not all(isinstance(value, str) for value in identity):
            errors.append("component input id, kind, and manifestPath must be strings")
            continue
        typed_identity = (str(identity[0]), str(identity[1]), str(identity[2]))
        identities.append(typed_identity)
        components.append({"id": typed_identity[0], "kind": typed_identity[1], "manifestPath": typed_identity[2]})
    if len(identities) != len(EXPECTED_COMPONENTS) or frozenset(identities) != EXPECTED_COMPONENTS:
        errors.append("build inputs must contain exactly the canonical desktop, Core API, and worker components")
    return components, errors


def repository_schema_paths(repo: Path) -> list[str]:
    paths: list[str] = []
    for path in repo.rglob("*.schema.json"):
        relative = path.relative_to(repo)
        if relative.parts[0].startswith(".") or relative.parts[0] == "artifacts":
            continue
        paths.append(relative.as_posix())
    return sorted(paths)


def source_contract(repo: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    version_document, _, version_error = load_json(repo, VERSION_PATH)
    version_schema, _, version_schema_error = load_json(repo, VERSION_SCHEMA_PATH)
    inputs, _, inputs_error = load_json(repo, INPUTS_PATH)
    component_schema, _, component_schema_error = load_json(repo, COMPONENT_SCHEMA_PATH)
    for label, error in (
        ("product version", version_error),
        ("product version schema", version_schema_error),
        ("build inputs", inputs_error),
        ("component manifest schema", component_schema_error),
    ):
        if error:
            errors.append(f"{label}: {error}")
    if errors:
        return None, None, [], errors
    if (
        not isinstance(version_document, dict)
        or not isinstance(version_schema, dict)
        or not isinstance(component_schema, dict)
    ):
        return None, None, [], ["product version, product version schema, and component schema must be objects"]
    errors.extend(schema_errors(version_document, version_schema, "productVersion"))
    if not isinstance(inputs, dict):
        return version_document, None, [], [*errors, "build inputs must be an object"]
    if set(inputs) != {
        "schemaVersion",
        "documentType",
        "components",
        "dependencyLocks",
        "schemaPaths",
        "modelManifests",
    }:
        errors.append("build inputs must contain only the governed top-level fields")
    if inputs.get("schemaVersion") != "1.0" or inputs.get("documentType") != "build-manifest-inputs":
        errors.append("build inputs identity is invalid")
    version = version_document.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        errors.append("product version must be semantic version text")
        return version_document, inputs, [], errors

    try:
        package = json.loads((repo / "package.json").read_text(encoding="utf-8"))
        python_project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
        cargo = tomllib.loads((repo / "Cargo.toml").read_text(encoding="utf-8"))
        mirrors = {
            "package.json": package.get("version"),
            "pyproject.toml": python_project.get("project", {}).get("version"),
            "Cargo.toml": cargo.get("workspace", {}).get("package", {}).get("version"),
        }
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        mirrors = {}
        errors.append(f"cannot read ecosystem version mirrors: {exc}")
    for path, mirror in mirrors.items():
        if mirror != version:
            errors.append(f"{path} version {mirror!r} must mirror authoritative product version {version!r}")

    components_config, component_input_errors = configured_components(inputs)
    errors.extend(component_input_errors)
    component_manifests: list[dict[str, Any]] = []
    if not component_input_errors:
        for component in components_config:
            manifest, _, manifest_error = load_json(repo, component["manifestPath"])
            if manifest_error or not isinstance(manifest, dict):
                errors.append(f"{component.get('id')}: {manifest_error or 'component manifest must be an object'}")
                continue
            errors.extend(schema_errors(manifest, component_schema, f"component[{component['id']}]"))
            expected = expected_component(component, version)
            if manifest != expected:
                errors.append(f"{component['id']}: component manifest is not the exact generated version contract")
            component_manifests.append(manifest)
    compatibility = {manifest.get("compatibilityLine") for manifest in component_manifests}
    versions = {manifest.get("version") for manifest in component_manifests}
    if len(compatibility) != 1 or len(versions) != 1:
        errors.append("desktop and sidecar component versions are incompatible")

    configured_schemas = inputs.get("schemaPaths")
    if not isinstance(configured_schemas, list) or any(not isinstance(path, str) for path in configured_schemas):
        errors.append("schemaPaths must be a string array")
    elif len(configured_schemas) != len(set(configured_schemas)):
        errors.append("schemaPaths must not contain duplicate paths")
    elif sorted(configured_schemas) != repository_schema_paths(repo):
        errors.append("build inputs schemaPaths must exactly inventory every repository schema")
    dependency_locks = inputs.get("dependencyLocks")
    if not isinstance(dependency_locks, list):
        errors.append("dependencyLocks must be an array")
    else:
        lock_identities: list[tuple[str, str]] = []
        for lock in dependency_locks:
            if not isinstance(lock, dict) or set(lock) != {"id", "path"}:
                errors.append("dependency lock input must contain exactly id and path")
                continue
            identity = (lock.get("id"), lock.get("path"))
            if not all(isinstance(value, str) for value in identity):
                errors.append("dependency lock id and path must be strings")
                continue
            lock_identities.append((str(identity[0]), str(identity[1])))
        if len(lock_identities) != len(EXPECTED_LOCKS) or frozenset(lock_identities) != EXPECTED_LOCKS:
            errors.append("dependencyLocks must contain exactly the Cargo, pnpm, and uv lockfiles")
    if not isinstance(inputs.get("modelManifests"), list):
        errors.append("modelManifests must be an array")
    try:
        changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
        for fragment in ("# Changelog", "## [Unreleased]", f"## [{version}]"):
            if fragment not in changelog:
                errors.append(f"CHANGELOG.md is missing {fragment!r}")
    except OSError as exc:
        errors.append(f"cannot read CHANGELOG.md: {exc}")
    return version_document, inputs, component_manifests, errors


def git_command(repo: Path, arguments: list[str], runner: GitRunner) -> tuple[bytes | None, str | None]:
    try:
        result = runner(["git", *arguments], cwd=repo, capture_output=True, check=False)
    except OSError as exc:
        return None, f"Git command is unavailable: {exc}"
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        return None, f"git {' '.join(arguments)} failed: {stderr or result.returncode}"
    return result.stdout, None


def git_source(repo: Path, runner: GitRunner = subprocess.run) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    commit, commit_error = git_command(repo, ["rev-parse", "--verify", "HEAD"], runner)
    timestamp, timestamp_error = git_command(repo, ["show", "-s", "--format=%cI", "HEAD"], runner)
    epoch, epoch_error = git_command(repo, ["show", "-s", "--format=%ct", "HEAD"], runner)
    status, status_error = git_command(repo, ["status", "--porcelain=v1", "-z", "--untracked-files=all"], runner)
    for error in (commit_error, timestamp_error, epoch_error, status_error):
        if error:
            errors.append(error)
    if errors or None in (commit, timestamp, epoch, status):
        return None, errors
    assert commit is not None and timestamp is not None and epoch is not None and status is not None
    commit_text = commit.decode("ascii", errors="replace").strip()
    timestamp_text = timestamp.decode("utf-8", errors="replace").strip()
    try:
        epoch_value = int(epoch.decode("ascii").strip())
    except ValueError:
        return None, ["Git commit epoch is not an integer"]
    dirty_paths: list[str] = []
    records = status.split(b"\0")
    if records and records[-1] == b"":
        records.pop()
    index = 0
    while index < len(records):
        record = records[index]
        if len(record) < 4 or record[2:3] != b" ":
            errors.append("Git status returned a malformed porcelain record")
            break
        dirty_paths.append(record[3:].decode("utf-8", errors="replace").replace("\\", "/"))
        if b"R" in record[:2] or b"C" in record[:2]:
            index += 1
            if index >= len(records) or not records[index]:
                errors.append("Git status omitted a rename/copy source path")
                break
            dirty_paths.append(records[index].decode("utf-8", errors="replace").replace("\\", "/"))
        index += 1
    if not re.fullmatch(r"[0-9a-f]{40}", commit_text):
        errors.append("Git commit must be a full lowercase SHA-1 identifier")
    return {
        "commit": commit_text,
        "commitTimestamp": timestamp_text,
        "sourceDateEpoch": epoch_value,
        "dirty": bool(dirty_paths),
        "dirtyPaths": sorted(set(dirty_paths)),
    }, errors


def hashed_entries(repo: Path, items: Any, kind: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(items, list):
        return [], [f"{kind} inputs must be an array"]
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "path"}:
            errors.append(f"{kind} input must contain exactly id and path")
            continue
        item_id = item.get("id")
        path = item.get("path")
        if not isinstance(item_id, str) or not item_id or not isinstance(path, str) or not path:
            errors.append(f"{kind} input id and path must be non-empty strings")
            continue
        if item_id in seen_ids or path in seen_paths:
            errors.append(f"{kind} inputs must have unique ids and paths")
            continue
        seen_ids.add(item_id)
        seen_paths.add(path)
        payload, read_error = safe_snapshot(repo, path)
        if read_error or payload is None:
            errors.append(f"{kind} {item_id}: {read_error}")
            continue
        entries.append({"id": item_id, "path": path, "sha256": sha256(payload)})
    return entries, errors


def generate_build_manifest(repo: Path, runner: GitRunner = subprocess.run) -> tuple[dict[str, Any] | None, list[str]]:
    repo = repo.resolve(strict=True)
    version_document, inputs, components, errors = source_contract(repo)
    if errors or version_document is None or inputs is None:
        return None, errors
    source, git_errors = git_source(repo, runner)
    errors.extend(git_errors)
    dependencies, dependency_errors = hashed_entries(repo, inputs["dependencyLocks"], "dependency lock")
    errors.extend(dependency_errors)
    schema_entries: list[dict[str, Any]] = []
    for path in inputs["schemaPaths"]:
        schema, payload, schema_error = load_json(repo, path)
        if schema_error or payload is None or not isinstance(schema, dict):
            errors.append(f"schema {path}: {schema_error or 'schema must be an object'}")
            continue
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            errors.append(f"schema {path} requires a stable $id")
            continue
        schema_entries.append({"id": schema_id, "path": path, "sha256": sha256(payload)})
    schema_ids = [entry["id"] for entry in schema_entries]
    if len(schema_ids) != len(set(schema_ids)):
        errors.append("repository schemas must have unique stable $id values")
    model_entries, model_errors = hashed_entries(repo, inputs["modelManifests"], "model manifest")
    errors.extend(model_errors)
    if errors or source is None:
        return None, errors
    version = version_document["version"]
    dirty_suffix = ".dirty" if source["dirty"] else ""
    manifest: dict[str, Any] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-build-manifest",
        "productVersion": version,
        "buildIdentity": f"{version}+g{source['commit'][:7]}{dirty_suffix}",
        "source": source,
        "components": sorted(components, key=lambda item: item["componentId"]),
        "dependencies": identified_set(dependencies),
        "schemas": identified_set(schema_entries),
        "modelManifests": identified_set(model_entries),
    }
    manifest["manifestId"] = f"sha256:{sha256(canonical_json_bytes(manifest))}"
    build_schema, _, build_schema_error = load_json(repo, BUILD_SCHEMA_PATH)
    if build_schema_error or not isinstance(build_schema, dict):
        return None, [f"build manifest schema: {build_schema_error or 'schema must be an object'}"]
    errors.extend(schema_errors(manifest, build_schema, "buildManifest"))
    return (manifest if not errors else None), errors


def safe_output_path(repo: Path, raw_path: Path) -> Path:
    destination = raw_path if raw_path.is_absolute() else repo / raw_path
    destination = destination.absolute()
    report_root = (repo / REPORT_ROOT).resolve(strict=True)
    try:
        destination.parent.resolve(strict=True).relative_to(report_root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"build manifest output must remain under {REPORT_ROOT}: {raw_path}") from exc
    return destination


def atomic_write_json(destination: Path, value: Any) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=destination.parent, prefix=destination.name, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        assert temporary is not None
        os.replace(temporary, destination)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def synchronize_component_manifests(repo: Path) -> list[str]:
    """Regenerate canonical component manifests from the product version authority."""
    repo = repo.resolve(strict=True)
    version_document, _, version_error = load_json(repo, VERSION_PATH)
    version_schema, _, schema_error = load_json(repo, VERSION_SCHEMA_PATH)
    inputs, _, inputs_error = load_json(repo, INPUTS_PATH)
    errors = [error for error in (version_error, schema_error, inputs_error) if error]
    if errors:
        return errors
    if not isinstance(version_document, dict) or not isinstance(version_schema, dict) or not isinstance(inputs, dict):
        return ["product version, product version schema, and build inputs must be objects"]
    errors.extend(schema_errors(version_document, version_schema, "productVersion"))
    version = version_document.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        errors.append("product version must be semantic version text")
    components, component_errors = configured_components(inputs)
    errors.extend(component_errors)
    destinations: list[tuple[Path, dict[str, Any]]] = []
    if not errors:
        assert isinstance(version, str)
        for component in components:
            relative = PurePosixPath(component["manifestPath"])
            destination = repo.joinpath(*relative.parts)
            try:
                resolved_parent = destination.parent.resolve(strict=True)
                resolved_parent.relative_to(repo)
                if resolved_parent != destination.parent:
                    raise ValueError("parent directory is redirected")
                if destination.exists() and (
                    destination.resolve(strict=True) != destination or not destination.is_file()
                ):
                    raise ValueError("destination is redirected or is not a file")
            except (OSError, ValueError) as exc:
                errors.append(f"cannot safely generate {component['manifestPath']}: {exc}")
                continue
            destinations.append((destination, expected_component(component, version)))
    if errors:
        return errors
    for destination, manifest in destinations:
        try:
            atomic_write_json(destination, manifest)
        except OSError as exc:
            errors.append(f"cannot write {destination.relative_to(repo).as_posix()}: {exc}")
            break
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--write-components",
        action="store_true",
        help="regenerate the three component manifests from the authoritative product version",
    )
    args = parser.parse_args()
    repo = Path(args.repo).resolve(strict=True)
    if args.write_components:
        synchronization_errors = synchronize_component_manifests(repo)
        for error in synchronization_errors:
            print(f"ERROR: {error}")
        if synchronization_errors:
            print("Component manifests: FAIL")
            return 1
    manifest, errors = generate_build_manifest(repo)
    for error in errors:
        print(f"ERROR: {error}")
    if manifest is None:
        print("Build manifest: FAIL")
        return 1
    if args.output:
        try:
            atomic_write_json(safe_output_path(repo, args.output), manifest)
        except (OSError, ValueError) as exc:
            print(f"ERROR: cannot write build manifest: {exc}")
            return 2
    state = "dirty" if manifest["source"]["dirty"] else "clean"
    print(f"Build manifest: PASS - {manifest['buildIdentity']} ({state})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
