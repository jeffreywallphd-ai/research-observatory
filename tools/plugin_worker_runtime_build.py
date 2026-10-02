"""Build the fixed Windows LPAC worker from pinned inputs and sign exact bytes.

This tool never fetches dependencies or creates a trust identity. The caller
supplies a locally prepared CPython source build, an external PE signer and
verifier, and an external Ed25519 inventory signer. Outputs belong in ignored
local storage; no credential or private key is passed through this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pefile  # type: ignore[import-untyped]
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

REPO = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "143b1dddefaec3bd2e21e3b839b34a2b7fb9842272883c576420d605e9f30c63"
PATCHED_RC_SHA256 = "47a869fe938a2bb7c0ef8d5a4ed2fcf5d182faa52aea5ad347203c7fbbb86b3e"
PYTHON_VERSION = "3.14.6"
PYINSTALLER_VERSION = "6.21.0"
IMAGE_NAME = "research-observatory-plugin-worker-x86_64-pc-windows-msvc"
IMAGE_PATH = f"{IMAGE_NAME}/{IMAGE_NAME}.exe"
MAX_PACKAGE_BYTES = 256 * 1_048_576


class WorkerBuildError(RuntimeError):
    """A pinned input or signed output failed verification."""


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1_048_576), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_source_variant(archive: Path, source_root: Path) -> None:
    if _digest(archive) != SOURCE_SHA256:
        raise WorkerBuildError("cpython-source-archive-mismatch")
    if _digest(source_root / "PC" / "python_nt.rc") != PATCHED_RC_SHA256:
        raise WorkerBuildError("cpython-manifest-variant-mismatch")
    with tarfile.open(archive, "r:xz") as source:
        for member in source:
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if not parts or parts[0] != "Python-3.14.6" or len(parts) < 2:
                raise WorkerBuildError("cpython-source-archive-layout-invalid")
            relative = Path(*parts[1:])
            if relative == Path("PC/python_nt.rc"):
                continue
            expected = source.extractfile(member)
            actual = source_root / relative
            if expected is None or not actual.is_file() or actual.is_symlink() or actual.is_junction():
                raise WorkerBuildError("cpython-source-file-missing")
            if hashlib.sha256(expected.read()).hexdigest() != _digest(actual):
                raise WorkerBuildError("cpython-source-file-mismatch")


def _manifest_free(path: Path) -> None:
    image = pefile.PE(str(path), fast_load=False)
    try:
        if image.FILE_HEADER.Machine != 0x8664:
            raise WorkerBuildError("cpython-extension-architecture-invalid")
        resources = getattr(image, "DIRECTORY_ENTRY_RESOURCE", None)
        if resources is not None and any(entry.struct.Id == 24 for entry in resources.entries):
            raise WorkerBuildError("cpython-extension-manifest-present")
    finally:
        image.close()


def _invoke(executable: Path, *arguments: Path) -> None:
    if not executable.is_file():
        raise WorkerBuildError("signer-or-verifier-unavailable")
    command = [sys.executable, str(executable)] if executable.suffix.casefold() == ".py" else [str(executable)]
    result = subprocess.run(
        [*command, *(str(argument) for argument in arguments)], capture_output=True, timeout=120, check=False
    )
    if result.returncode:
        raise WorkerBuildError("signer-or-verifier-failed")


def _inventory(package: Path) -> bytes:
    entries: list[dict[str, str]] = []
    total = 0
    for path in sorted(package.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink() or path.is_junction():
            raise WorkerBuildError("worker-package-redirect-denied")
        if not path.is_file() and not path.is_dir():
            raise WorkerBuildError("worker-package-object-invalid")
        if path.is_file():
            total += path.stat().st_size
            if total > MAX_PACKAGE_BYTES:
                raise WorkerBuildError("worker-package-oversize")
            entries.append({"path": path.relative_to(package).as_posix(), "sha256": _digest(path)})
    if not any(entry["path"] == IMAGE_PATH for entry in entries):
        raise WorkerBuildError("worker-image-missing")
    return (
        json.dumps(
            {
                "schemaVersion": "1.0",
                "documentType": "application-signed-lpac-worker-package",
                "imagePath": IMAGE_PATH,
                "files": entries,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def build(
    archive: Path,
    source_root: Path,
    pyinstaller_python: Path,
    output: Path,
    pe_signer: Path,
    pe_verifier: Path,
    inventory_signer: Path,
    application_public_key: Path,
) -> None:
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise WorkerBuildError("worker-build-requires-windows-x64")
    if output.exists() or output.is_symlink():
        raise WorkerBuildError("worker-build-output-must-be-fresh")
    verify_source_variant(archive.resolve(strict=True), source_root.resolve(strict=True))
    output.mkdir(parents=True)
    build_root = source_root / "PCbuild" / "amd64"
    core = build_root / "python314.dll"
    if not core.is_file():
        raise WorkerBuildError("manifest-free-python-dll-missing")
    _manifest_free(core)
    version = subprocess.run(
        [
            str(pyinstaller_python),
            "-c",
            "import sys,PyInstaller;print(sys.version.split()[0]);print(PyInstaller.__version__)",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if version.returncode or version.stdout.splitlines() != [PYTHON_VERSION, PYINSTALLER_VERSION]:
        raise WorkerBuildError("worker-builder-version-mismatch")
    command = [
        str(pyinstaller_python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--noupx",
        "--contents-directory",
        "_internal",
        "--name",
        IMAGE_NAME,
        "--paths",
        str(REPO),
        "--distpath",
        str(output / "dist"),
        "--workpath",
        str(output / "work"),
        "--specpath",
        str(output / "spec"),
        str(REPO / "workers/windows/plugin_worker.py"),
    ]
    with (output / "pyinstaller.log").open("wb") as log:
        result = subprocess.run(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT, timeout=180, check=False)
    if result.returncode:
        raise WorkerBuildError("worker-pyinstaller-build-failed")
    package = output / "package"
    shutil.copytree(output / "dist" / IMAGE_NAME, package / IMAGE_NAME)
    image = package / IMAGE_PATH
    internal = image.parent / "_internal"
    bundled_core = internal / "python314.dll"
    if not image.is_file() or not bundled_core.is_file():
        raise WorkerBuildError("worker-bundle-layout-invalid")
    shutil.copy2(core, bundled_core)
    source_extensions = {path.name.casefold(): path for path in build_root.glob("*.pyd")}
    bundled_extensions = list(internal.rglob("*.pyd"))
    if not bundled_extensions:
        raise WorkerBuildError("worker-bundle-extensions-missing")
    for extension in bundled_extensions:
        source = source_extensions.get(extension.name.casefold())
        if source is None:
            raise WorkerBuildError("manifest-free-extension-missing")
        _manifest_free(source)
        shutil.copy2(source, extension)
    signed_targets = [image, bundled_core, *bundled_extensions]
    for target in signed_targets:
        _invoke(pe_signer, target)
        _invoke(pe_verifier, target)
    inventory = output / "inventory.json"
    inventory.write_bytes(_inventory(package))
    signature = output / "inventory.sig"
    _invoke(inventory_signer, inventory, signature)
    public = application_public_key.read_bytes()
    signed = signature.read_bytes()
    if len(public) != 32 or len(signed) != 64:
        raise WorkerBuildError("worker-inventory-signature-invalid")
    try:
        VerifyKey(public).verify(inventory.read_bytes(), signed)
    except BadSignatureError, ValueError, TypeError:
        raise WorkerBuildError("worker-inventory-signature-invalid") from None
    # A post-sign inventory is the sole runtime identity; every staged byte is
    # rehashed after signer mutations and again by the Core launcher at use.
    if inventory.read_bytes() != _inventory(package):
        raise WorkerBuildError("worker-post-sign-byte-mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--pyinstaller-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pe-signer", type=Path, required=True)
    parser.add_argument("--pe-verifier", type=Path, required=True)
    parser.add_argument("--inventory-signer", type=Path, required=True)
    parser.add_argument("--application-public-key", type=Path, required=True)
    args = parser.parse_args()
    build(
        args.source_archive,
        args.source_root,
        args.pyinstaller_python,
        args.output,
        args.pe_signer,
        args.pe_verifier,
        args.inventory_signer,
        args.application_public_key,
    )


if __name__ == "__main__":
    main()
