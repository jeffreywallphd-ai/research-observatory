"""Exact, application-signed file inventory for the isolated Windows worker.

The application public key is supplied by trusted installation configuration,
never by a plugin package. A development key is not embedded in product code.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from .file_paths import extended_path

WORKER_IMAGE_NAME = "research-observatory-plugin-worker-x86_64-pc-windows-msvc"
WORKER_IMAGE_PATH = f"{WORKER_IMAGE_NAME}/{WORKER_IMAGE_NAME}.exe"
MAX_RUNTIME_BYTES = 256 * 1_048_576
PARSER_IMAGE_NAME = "research-observatory-document-parser-x86_64-pc-windows-msvc"
PARSER_IMAGE_DIRECTORY = "parser"
PARSER_IMAGE_PATH = f"{PARSER_IMAGE_DIRECTORY}/{PARSER_IMAGE_NAME}.exe"
# Separate, parent-selected read-only model package. This does not increase the
# connector's envelope or grant the worker filesystem/network capabilities.
MAX_PARSER_RUNTIME_BYTES = 2 * 1024 * 1_048_576
# The first measured frozen CPU tree contains 7,379 files before notice
# compaction and selected model assets. 8,192 is a finite packaging envelope.
MAX_PARSER_RUNTIME_FILES = 8192
MAX_PARSER_INVENTORY_BYTES = 2 * 1_048_576
PARSER_LAUNCH_PROFILE = "ro-parser-cpu-1"
# W2 local application-build identity. Only this public key is tracked; its
# private signer remains in ignored local build storage. A release build must
# explicitly rotate the application pin and provide its separately governed
# signing identity before distribution.
APPLICATION_INVENTORY_PUBLIC_KEY = bytes.fromhex("ddda7ee95684848fb06f6424fba4a4a2b90f1ea2ece5529475aeee72e09a185a")
INSTALLED_WORKER_DIRECTORY = "plugin-worker"
INSTALLED_INVENTORY_NAME = "plugin-worker.inventory.json"
INSTALLED_SIGNATURE_NAME = "plugin-worker.inventory.sig"
INSTALLED_PARSER_DIRECTORY = "document-parser"
INSTALLED_PARSER_INVENTORY_NAME = "document-parser.inventory.json"
INSTALLED_PARSER_SIGNATURE_NAME = "document-parser.inventory.sig"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_PART = re.compile(r"[A-Za-z0-9._-]+\Z")
_WINDOWS_DEVICES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class RuntimeInventoryError(ValueError):
    """The signed runtime's signature, identity, paths or bytes are invalid."""


@dataclass(frozen=True, slots=True)
class SignedWorkerRuntime:
    package: Path
    inventory_bytes: bytes
    signature: bytes
    application_public_key: bytes


def load_installed_worker_runtime() -> SignedWorkerRuntime:
    """Load only the worker bundled beside this frozen Core executable."""

    if not getattr(sys, "frozen", False):
        raise RuntimeInventoryError("worker-runtime-unavailable")
    root = Path(sys.executable).parent
    try:
        inventory = (root / INSTALLED_INVENTORY_NAME).read_bytes()
        signature = (root / INSTALLED_SIGNATURE_NAME).read_bytes()
    except OSError:
        raise RuntimeInventoryError("worker-runtime-unavailable") from None
    runtime = SignedWorkerRuntime(
        root / INSTALLED_WORKER_DIRECTORY,
        inventory,
        signature,
        APPLICATION_INVENTORY_PUBLIC_KEY,
    )
    verify_worker_runtime(runtime)
    return runtime


def load_installed_parser_runtime() -> SignedWorkerRuntime:
    """Select the distinct parser bundle only beside the authenticated Core image."""
    if not getattr(sys, "frozen", False):
        raise RuntimeInventoryError("parser-runtime-unavailable")
    root = Path(sys.executable).parent
    try:
        runtime = SignedWorkerRuntime(
            root / INSTALLED_PARSER_DIRECTORY,
            (root / INSTALLED_PARSER_INVENTORY_NAME).read_bytes(),
            (root / INSTALLED_PARSER_SIGNATURE_NAME).read_bytes(),
            APPLICATION_INVENTORY_PUBLIC_KEY,
        )
    except OSError:
        raise RuntimeInventoryError("parser-runtime-unavailable") from None
    verify_worker_runtime(runtime, profile="parser")
    return runtime


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for name, item in pairs:
        if name in value:
            raise RuntimeInventoryError("worker-inventory-duplicate-key")
        value[name] = item
    return value


def _safe_path(text: str) -> bool:
    if not text or len(text) > 240 or text.startswith("/") or "\\" in text or ":" in text:
        return False
    for part in text.split("/"):
        if (
            part in {"", ".", ".."}
            or part.endswith((".", " "))
            or _SAFE_PART.fullmatch(part) is None
            or part.split(".", 1)[0].casefold() in _WINDOWS_DEVICES
        ):
            return False
    return True


def _safe_parser_path(text: str) -> bool:
    # Actual pinned wheel paths include CPU-version '+', the OOXML template
    # '[Content_Types].xml' and a bundled text notice containing a space. These
    # ASCII filename characters are not separators, redirects or ADS syntax.
    if any(
        part.endswith((".", " ")) or part.split(".", 1)[0].rstrip(" ").casefold() in _WINDOWS_DEVICES
        for part in text.split("/")
    ):
        return False
    return _safe_path(text.translate(str.maketrans("+[] ", "____")))


def _canonical_package_root(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise RuntimeInventoryError("worker-package-root-invalid")
    try:
        if any(part.is_symlink() or part.is_junction() for part in (path, *path.parents)):
            raise RuntimeInventoryError("worker-package-redirect-denied")
        root = path.resolve(strict=True)
    except OSError:
        raise RuntimeInventoryError("worker-package-root-invalid") from None
    if root != path or not root.is_dir():
        raise RuntimeInventoryError("worker-package-root-invalid")
    return root


def verify_worker_runtime(
    runtime: SignedWorkerRuntime, *, profile: Literal["connector", "parser"] = "connector",
    checkpoint: Callable[[], None] | None = None,
) -> Path:
    """Return the exact executable only after signature and full-tree checks."""

    if checkpoint is not None:
        checkpoint()

    if profile not in {"connector", "parser"}:
        raise RuntimeInventoryError("worker-profile-invalid")
    parsing = profile == "parser"
    inventory_limit = MAX_PARSER_INVENTORY_BYTES if parsing else 64 * 1024
    image_path = PARSER_IMAGE_PATH if parsing else WORKER_IMAGE_PATH
    if (
        not isinstance(runtime, SignedWorkerRuntime)
        or not isinstance(runtime.inventory_bytes, bytes)
        or not 0 < len(runtime.inventory_bytes) <= inventory_limit
        or not isinstance(runtime.signature, bytes)
        or len(runtime.signature) != 64
        or not isinstance(runtime.application_public_key, bytes)
        or len(runtime.application_public_key) != 32
    ):
        raise RuntimeInventoryError("worker-inventory-signature-invalid")
    try:
        VerifyKey(runtime.application_public_key).verify(runtime.inventory_bytes, runtime.signature)
    except BadSignatureError, ValueError, TypeError:
        raise RuntimeInventoryError("worker-inventory-signature-invalid") from None
    try:
        document = json.loads(runtime.inventory_bytes.decode("utf-8"), object_pairs_hook=_unique_object)
    except UnicodeError, ValueError, RecursionError:
        raise RuntimeInventoryError("worker-inventory-json-invalid") from None
    fields = {"schemaVersion", "documentType", "imagePath", "files"}
    if parsing:
        fields.add("launchProfile")
    if (
        not isinstance(document, dict)
        or set(document) != fields
        or document["schemaVersion"] != ("2.0" if parsing else "1.0")
        or document["documentType"]
        != ("application-signed-lpac-parser-package" if parsing else "application-signed-lpac-worker-package")
        or document["imagePath"] != image_path
        or (parsing and document["launchProfile"] != PARSER_LAUNCH_PROFILE)
        or not isinstance(document["files"], list)
        or not 0 < len(document["files"]) <= (MAX_PARSER_RUNTIME_FILES if parsing else 256)
    ):
        raise RuntimeInventoryError("worker-inventory-invalid")
    expected: dict[str, str] = {}
    folded_paths: set[str] = set()
    for entry in document["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise RuntimeInventoryError("worker-inventory-invalid")
        path, digest = entry["path"], entry["sha256"]
        if (
            not isinstance(path, str)
            or not (_safe_parser_path(path) if parsing else _safe_path(path))
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or path.casefold() in folded_paths
        ):
            raise RuntimeInventoryError("worker-inventory-invalid")
        expected[path] = digest
        folded_paths.add(path.casefold())
    required = {image_path}
    if parsing:
        required.update(
            f"{PARSER_IMAGE_DIRECTORY}/_internal/{name}"
            for name in ("parser-config.json", "parser-assets.json", "parser-runtime.lock")
        )
    if not required <= expected.keys() or any("/plugin/" in f"/{path}/" for path in expected):
        raise RuntimeInventoryError("worker-inventory-invalid")
    root = _canonical_package_root(runtime.package)
    identity = root.stat(follow_symlinks=False)
    actual: dict[str, str] = {}
    total = 0
    io_root = extended_path(root)
    for path in io_root.rglob("*"):
        if checkpoint is not None:
            checkpoint()
        if path.is_symlink() or path.is_junction():
            raise RuntimeInventoryError("worker-package-redirect-denied")
        if not path.is_file() and not path.is_dir():
            raise RuntimeInventoryError("worker-package-object-invalid")
        if path.is_file():
            total += path.stat().st_size
            if total > (MAX_PARSER_RUNTIME_BYTES if parsing else MAX_RUNTIME_BYTES):
                raise RuntimeInventoryError("worker-package-oversize")
            with path.open("rb") as source:
                digest = hashlib.sha256()
                while chunk := source.read(1_048_576):
                    if checkpoint is not None:
                        checkpoint()
                    digest.update(chunk)
                actual[path.relative_to(io_root).as_posix()] = digest.hexdigest()
            if len(actual) > (MAX_PARSER_RUNTIME_FILES if parsing else 256):
                raise RuntimeInventoryError("worker-package-oversize")
    if actual != expected:
        raise RuntimeInventoryError("worker-package-hash-mismatch")
    if _canonical_package_root(runtime.package) != root:
        raise RuntimeInventoryError("worker-package-root-invalid")
    final_identity = root.stat(follow_symlinks=False)
    if (identity.st_dev, identity.st_ino) != (final_identity.st_dev, final_identity.st_ino):
        raise RuntimeInventoryError("worker-package-identity-changed")
    return root / image_path
