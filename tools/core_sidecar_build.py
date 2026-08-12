"""Build and verify the versioned Windows Core API sidecar artifact."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from build_manifest import guarded_atomic_write_json
from jsonschema import Draft202012Validator

TARGET_TRIPLE = "x86_64-pc-windows-msvc"
CONTRACT_PATH = Path("services/core-api/packaging/sidecar-build.json")
SCHEMA_PATH = Path("packages/contracts/core-api/sidecar-artifact.schema.json")
ENTRY_SOURCE = Path("services/core-api/sidecar_entry.py")
SOURCE_ROOT = Path("services/core-api/src")
ALLOWED_CONTRACT_KEYS = {
    "schemaVersion",
    "documentType",
    "componentId",
    "componentVersion",
    "targetTriple",
    "pythonVersion",
    "builder",
    "entrypoint",
    "requiredModules",
    "maximumBytes",
}
ALLOWED_BUILDER_KEYS = {"name", "version", "mode", "upx", "contentsDirectory", "excludedModules"}


class SidecarBuildError(RuntimeError):
    """Actionable sidecar build or verification failure."""


def _is_redirect(path: Path) -> bool:
    try:
        return path.is_symlink() or path.is_junction()
    except OSError as exc:
        raise SidecarBuildError(f"cannot inspect path identity: {path}: {exc}") from exc


def _fixed_file(repo: Path, relative: Path) -> Path:
    candidate = repo / relative
    current = repo
    for part in relative.parts:
        current = current / part
        if _is_redirect(current):
            raise SidecarBuildError(f"redirected governed path is not allowed: {relative.as_posix()}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise SidecarBuildError(f"required governed file is unavailable: {relative.as_posix()}: {exc}") from exc
    if resolved != candidate or not candidate.is_file():
        raise SidecarBuildError(f"governed file must be a canonical regular file: {relative.as_posix()}")
    return candidate


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SidecarBuildError(f"{label} is not readable canonical UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SidecarBuildError(f"{label} must be a JSON object")
    return value


def load_build_contract(repo: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    contract = _load_json(_fixed_file(repo, CONTRACT_PATH), "sidecar build contract")
    if set(contract) != ALLOWED_CONTRACT_KEYS:
        raise SidecarBuildError("sidecar build contract has missing or unsupported fields")
    builder = contract.get("builder")
    if not isinstance(builder, dict) or set(builder) != ALLOWED_BUILDER_KEYS:
        raise SidecarBuildError("sidecar builder contract has missing or unsupported fields")
    expected = {
        "schemaVersion": "1.0",
        "documentType": "core-sidecar-build-contract",
        "componentId": "core-api",
        "targetTriple": TARGET_TRIPLE,
        "entrypoint": f"research-observatory-core-{TARGET_TRIPLE}.exe",
    }
    for field, value in expected.items():
        if contract.get(field) != value:
            raise SidecarBuildError(f"sidecar build contract field {field} must equal {value!r}")
    if builder != {
        "name": "PyInstaller",
        "version": "6.21.0",
        "mode": "onedir",
        "upx": False,
        "contentsDirectory": "research-observatory-core-runtime",
        "excludedModules": [
            "mypy",
            "pip",
            "pydantic.mypy",
            "pydantic.v1.mypy",
            "pytest",
            "setuptools",
            "yaml",
        ],
    }:
        raise SidecarBuildError("sidecar builder must be the approved PyInstaller 6.21.0 onedir/no-UPX profile")
    modules = contract.get("requiredModules")
    if (
        not isinstance(modules, list)
        or modules != sorted(set(modules))
        or not all(isinstance(item, str) and item for item in modules)
    ):
        raise SidecarBuildError("requiredModules must be a sorted unique non-empty string list")
    maximum = contract.get("maximumBytes")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 134_217_728:
        raise SidecarBuildError("maximumBytes must be an integer between 1 and 134217728")
    for field in ("componentVersion", "pythonVersion"):
        if not isinstance(contract.get(field), str) or not contract[field]:
            raise SidecarBuildError(f"{field} must be a non-empty string")
    return contract


def _inventory(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    files: list[dict[str, Any]] = []
    errors: list[str] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            errors.append(f"cannot enumerate artifact directory {directory.relative_to(root).as_posix() or '.'}: {exc}")
            continue
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                if entry.is_symlink() or _is_redirect(path):
                    errors.append(f"artifact redirects are not allowed: {relative}")
                elif entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                elif entry.is_file(follow_symlinks=False):
                    data = path.read_bytes()
                    files.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
                else:
                    errors.append(f"unsupported artifact entry type: {relative}")
            except OSError as exc:
                errors.append(f"cannot inspect artifact entry {relative}: {exc}")
    return sorted(files, key=lambda item: item["path"]), errors


def verify_artifact(
    artifact_root: Path,
    manifest: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    tool_repo = Path(__file__).resolve().parents[1]
    if schema is None:
        schema = _load_json(_fixed_file(tool_repo, SCHEMA_PATH), "sidecar artifact schema")
    if contract is None:
        contract = load_build_contract(tool_repo)
    schema_errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda error: list(error.path))
    for error in schema_errors:
        location = "/".join(str(part) for part in error.path) or "<root>"
        errors.append(f"artifact manifest schema violation at {location}: {error.message}")
    expected_identity = {
        "schemaVersion": contract["schemaVersion"],
        "documentType": "core-sidecar-artifact-manifest",
        "componentId": contract["componentId"],
        "componentVersion": contract["componentVersion"],
        "targetTriple": contract["targetTriple"],
        "pythonVersion": contract["pythonVersion"],
        "entrypoint": contract["entrypoint"],
    }
    for field, expected_value in expected_identity.items():
        if manifest.get(field) != expected_value:
            errors.append(f"artifact manifest {field} does not match the governed build contract")
    expected_builder = {
        field: contract["builder"][field] for field in ("name", "version", "mode", "upx", "excludedModules")
    }
    if manifest.get("builder") != expected_builder:
        errors.append("artifact manifest builder does not match the governed build contract")
    if not artifact_root.is_dir() or _is_redirect(artifact_root):
        return ["artifact root must be a present canonical directory"]
    inventory, inventory_errors = _inventory(artifact_root)
    errors.extend(inventory_errors)
    expected = manifest.get("files")
    if not isinstance(expected, list):
        return [*errors, "manifest files must be a list"]
    expected_by_path: dict[str, dict[str, Any]] = {}
    for item in expected:
        if isinstance(item, dict):
            path_value = item.get("path")
            if isinstance(path_value, str):
                if path_value in expected_by_path:
                    errors.append(f"artifact manifest contains a duplicate path: {path_value}")
                expected_by_path[path_value] = item
    actual_by_path: dict[str, dict[str, Any]] = {str(item["path"]): item for item in inventory}
    for path in sorted(expected_by_path.keys() - actual_by_path.keys()):
        errors.append(f"manifested artifact file is missing: {path}")
    for path in sorted(actual_by_path.keys() - expected_by_path.keys()):
        errors.append(f"unmanifested artifact file is present: {path}")
    for path in sorted(expected_by_path.keys() & actual_by_path.keys()):
        if expected_by_path[path] != actual_by_path[path]:
            errors.append(f"artifact bytes or digest changed: {path}")
    entrypoint = manifest.get("entrypoint")
    if isinstance(entrypoint, str) and entrypoint not in actual_by_path:
        errors.append(f"artifact entrypoint is missing: {entrypoint}")
    total = sum(item["bytes"] for item in inventory)
    if manifest.get("totalBytes") != total:
        errors.append("artifact totalBytes does not match exact inventory")
    return errors


def _check_build_host(contract: dict[str, Any], source_root: Path) -> None:
    if os.name != "nt" or platform.machine().casefold() not in {"amd64", "x86_64"}:
        raise SidecarBuildError("the release-authoritative sidecar build requires Windows x64")
    actual_python = platform.python_version()
    if actual_python != contract["pythonVersion"]:
        raise SidecarBuildError(f"sidecar build requires Python {contract['pythonVersion']}; found {actual_python}")
    try:
        pyinstaller = importlib.import_module("PyInstaller")
    except ImportError as exc:
        raise SidecarBuildError("PyInstaller is unavailable; run the frozen development dependency install") from exc
    if getattr(pyinstaller, "__version__", None) != contract["builder"]["version"]:
        raise SidecarBuildError("installed PyInstaller does not match the build contract")
    sys.path.insert(0, str(source_root))
    try:
        for module_name in contract["requiredModules"]:
            try:
                importlib.import_module(module_name)
            except ImportError as exc:
                raise SidecarBuildError(f"required build module is unavailable: {module_name}") from exc
    finally:
        sys.path.remove(str(source_root))


def _canonical_empty_output(repo: Path, output_root: Path) -> Path:
    output_root = output_root.absolute()
    scratch = repo / "artifacts" / "tmp"
    if not scratch.exists():
        parent = scratch.parent
        if parent.resolve(strict=True) != parent or _is_redirect(parent):
            raise SidecarBuildError("canonical artifacts parent is unavailable or redirected")
        scratch.mkdir()
    if scratch.resolve(strict=True) != scratch or _is_redirect(scratch):
        raise SidecarBuildError("canonical artifact scratch root is redirected")
    if output_root.parent.resolve(strict=True) != scratch.resolve(strict=True):
        raise SidecarBuildError("sidecar output must be a direct child of canonical artifacts/tmp")
    if output_root.exists():
        if _is_redirect(output_root) or not output_root.is_dir() or any(output_root.iterdir()):
            raise SidecarBuildError("sidecar output directory must be absent or an empty canonical directory")
    elif _is_redirect(output_root):
        raise SidecarBuildError("sidecar output directory must not be redirected")
    else:
        output_root.mkdir()
    return output_root


def build_sidecar(repo: Path, output_root: Path) -> tuple[Path, dict[str, Any]]:
    repo = repo.resolve(strict=True)
    contract = load_build_contract(repo)
    source_root = (repo / SOURCE_ROOT).resolve(strict=True)
    if source_root != repo / SOURCE_ROOT or _is_redirect(source_root):
        raise SidecarBuildError("Core API source root must be canonical and nonredirected")
    _check_build_host(contract, source_root)
    output_root = _canonical_empty_output(repo, output_root)
    entry_source = _fixed_file(repo, ENTRY_SOURCE)
    build_root = output_root / "build"
    dist_root = output_root / "dist"
    spec_root = output_root / "spec"
    build_root.mkdir()
    dist_root.mkdir()
    spec_root.mkdir()
    env_before = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        from PyInstaller.__main__ import run as pyinstaller_run  # type: ignore[import-untyped]

        arguments = [
            str(entry_source),
            "--name",
            contract["entrypoint"].removesuffix(".exe"),
            "--paths",
            str(source_root),
            "--onedir",
            "--console",
            "--noupx",
            "--clean",
            "--noconfirm",
            "--contents-directory",
            contract["builder"]["contentsDirectory"],
            "--distpath",
            str(dist_root),
            "--workpath",
            str(build_root),
            "--specpath",
            str(spec_root),
        ]
        for excluded_module in contract["builder"]["excludedModules"]:
            arguments.extend(["--exclude-module", excluded_module])
        pyinstaller_run(arguments)
    finally:
        if env_before is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = env_before
    artifact_root = dist_root / contract["entrypoint"].removesuffix(".exe")
    if not artifact_root.is_dir() or _is_redirect(artifact_root):
        raise SidecarBuildError("PyInstaller did not produce the expected canonical onedir artifact")
    inventory, errors = _inventory(artifact_root)
    if errors:
        raise SidecarBuildError("; ".join(errors))
    manifest = {
        "schemaVersion": "1.0",
        "documentType": "core-sidecar-artifact-manifest",
        "componentId": contract["componentId"],
        "componentVersion": contract["componentVersion"],
        "targetTriple": contract["targetTriple"],
        "pythonVersion": contract["pythonVersion"],
        "builder": {key: contract["builder"][key] for key in ("name", "version", "mode", "upx", "excludedModules")},
        "entrypoint": contract["entrypoint"],
        "totalBytes": sum(item["bytes"] for item in inventory),
        "files": inventory,
    }
    schema = _load_json(_fixed_file(repo, SCHEMA_PATH), "sidecar artifact schema")
    schema_errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda error: list(error.path))
    if schema_errors:
        raise SidecarBuildError(
            "generated artifact manifest is invalid: " + "; ".join(error.message for error in schema_errors)
        )
    if manifest["totalBytes"] > contract["maximumBytes"]:
        raise SidecarBuildError("sidecar artifact exceeds the approved maximumBytes")
    verification_errors = verify_artifact(artifact_root, manifest, schema=schema, contract=contract)
    if verification_errors:
        raise SidecarBuildError("; ".join(verification_errors))
    return artifact_root, manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("artifacts/tmp/core-sidecar"))
    parser.add_argument("--report", type=Path, default=Path("artifacts/tmp/core-sidecar-package.json"))
    return parser


def prepare_report_path(repo: Path, report: Path) -> Path:
    """Remove only a private canonical prior report and deny aliases."""
    scratch = repo / "artifacts" / "tmp"
    if not scratch.exists():
        parent = scratch.parent
        if parent.resolve(strict=True) != parent or _is_redirect(parent):
            raise SidecarBuildError("canonical artifacts parent is unavailable or redirected")
        scratch.mkdir()
    if scratch.resolve(strict=True) != scratch or _is_redirect(scratch):
        raise SidecarBuildError("canonical artifact scratch root is redirected")
    expected = scratch / "core-sidecar-package.json"
    if report.absolute() != expected.absolute():
        raise SidecarBuildError("report must be canonical artifacts/tmp/core-sidecar-package.json")
    try:
        metadata = os.lstat(report)
    except FileNotFoundError:
        return report
    except OSError as exc:
        raise SidecarBuildError(f"cannot inspect existing package report: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or _is_redirect(report):
        raise SidecarBuildError("existing package report must be a private canonical regular file")
    try:
        report.unlink()
    except OSError as exc:
        raise SidecarBuildError(f"cannot remove prior private package report: {exc}") from exc
    return report


def write_report_exclusive(repo: Path, report: Path, value: dict[str, Any]) -> None:
    """Publish a new report under locked canonical repository directories."""
    try:
        guarded_atomic_write_json(repo, report, value, repo / "artifacts" / "tmp")
    except (OSError, ValueError) as exc:
        raise SidecarBuildError(f"cannot publish package report in the canonical scratch root: {exc}") from exc


def main() -> int:
    arguments = _parser().parse_args()
    repo = arguments.repo.resolve(strict=True)
    output = arguments.output if arguments.output.is_absolute() else repo / arguments.output
    report = arguments.report if arguments.report.is_absolute() else repo / arguments.report
    report = prepare_report_path(repo, report)
    scratch = repo / "artifacts" / "tmp"
    if output.exists():
        if _is_redirect(output) or output.parent.resolve(strict=True) != scratch.resolve(strict=True):
            raise SidecarBuildError("existing output is outside or redirects the canonical scratch root")
        shutil.rmtree(output)
    artifact_root, manifest = build_sidecar(repo, output)
    executable = artifact_root / manifest["entrypoint"]
    completed = subprocess.run([executable, "--check"], capture_output=True, text=True, timeout=30, check=False)
    report_value = {
        "ok": completed.returncode == 0,
        "artifactRoot": artifact_root.relative_to(repo).as_posix(),
        "manifest": manifest,
        "configurationCheck": json.loads(completed.stdout) if completed.returncode == 0 else None,
    }
    write_report_exclusive(repo, report, report_value)
    if completed.returncode != 0:
        raise SidecarBuildError("frozen sidecar configuration check failed")
    print(json.dumps({"ok": True, "files": len(manifest["files"]), "totalBytes": manifest["totalBytes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
