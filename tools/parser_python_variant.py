"""One pinned parser-only optional Dateutil registry compatibility derivative."""

from __future__ import annotations

import difflib
import hashlib
import json
import shutil
from pathlib import Path

from plugin_worker_runtime_build import REPO, WorkerBuildError

DATEUTIL_SOURCE_SHA256 = "c49b335a04b0135c4fc7f1c98f86647a9cae902fe1372d35e9631c5e16d1681f"
DATEUTIL_PATCH_SHA256 = "486ed79668de54a067137859b22bba19b143cb5704289d6cda712127d8c28ec1"
DATEUTIL_PATCH = REPO / "workers/document/dateutil-parser-registry.patch"


def dateutil_registry_variant(source: bytes) -> bytes:
    patch = DATEUTIL_PATCH.read_bytes()
    if hashlib.sha256(source).hexdigest() != DATEUTIL_SOURCE_SHA256:
        raise WorkerBuildError("parser-dateutil-source-mismatch")
    if hashlib.sha256(patch).hexdigest() != DATEUTIL_PATCH_SHA256:
        raise WorkerBuildError("parser-dateutil-patch-mismatch")
    original = source.decode("utf-8", errors="strict")
    before = "def _settzkeyname():\n    handle = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)\n"
    after = """def _settzkeyname():
    try:
        handle = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
    except PermissionError:
        # The isolated offline parser has no Windows registry capability.
        # dateutil.tz already treats ImportError as optional tzwin unavailability.
        raise ImportError("Windows registry time zones unavailable") from None
"""
    if original.count(before) != 1:
        raise WorkerBuildError("parser-dateutil-patch-context-mismatch")
    derived = original.replace(before, after)
    expected = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            derived.splitlines(keepends=True),
            fromfile="dateutil/tz/win.py",
            tofile="dateutil/tz/win.py",
        )
    ).encode("utf-8")
    if patch != expected:
        raise WorkerBuildError("parser-dateutil-patch-context-mismatch")
    return derived.encode("utf-8")


def prepare_dateutil_variant(package: Path, output: Path) -> Path:
    """Copy an isolated source overlay; never change the installed input."""

    if output.exists() or output.is_symlink() or package.name != "dateutil":
        raise WorkerBuildError("parser-dateutil-overlay-invalid")
    original = package / "tz/win.py"
    derived = dateutil_registry_variant(original.read_bytes())
    files = sorted(p for p in package.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    if any(p.is_symlink() or p.is_junction() for p in (package, *package.rglob("*"))):
        raise WorkerBuildError("parser-dateutil-source-redirect")
    source_hashes = {p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    output.mkdir(parents=True)
    shutil.copytree(package, output / "dateutil", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (output / "dateutil/tz/win.py").write_bytes(derived)
    copied = {
        p.relative_to(output / "dateutil").as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (output / "dateutil").rglob("*")
        if p.is_file()
    }
    expected = dict(source_hashes)
    expected["tz/win.py"] = hashlib.sha256(derived).hexdigest()
    if copied != expected or source_hashes != {
        p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    }:
        raise WorkerBuildError("parser-dateutil-overlay-integrity")
    receipt = {
        "schemaVersion": "1.0",
        "documentType": "parser-only-dateutil-source-variant",
        "version": "2.9.0.post0",
        "sourceFiles": source_hashes,
        "derivedSourceSha256": expected["tz/win.py"],
        "patchSha256": DATEUTIL_PATCH_SHA256,
    }
    (output / "build-receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return output
