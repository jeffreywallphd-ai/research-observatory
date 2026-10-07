"""Build the fixed offline CPU parser, retaining the connector's smaller profile.

Inputs are already downloaded hash-pinned wheels/assets and the qualified
CPython source variant. Signing uses the caller's existing external tools.
This tool performs no dependency resolution, download or trust-key creation.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from parser_native_build import build_parser_native  # noqa: E402
from parser_pe_variant import remove_inert_dll_manifests  # noqa: E402
from parser_python_variant import prepare_dateutil_variant  # noqa: E402
from parser_socket_build import build_parser_overlapped, build_parser_socket  # noqa: E402
from plugin_worker_runtime_build import (  # noqa: E402
    REPO,
    WorkerBuildError,
    _digest,
    _invoke,
    _manifest_free,
    verify_source_variant,
)

from workers.document.parser_package import VERSIONS  # noqa: E402
from workers.windows.runtime_inventory import (  # noqa: E402
    MAX_PARSER_INVENTORY_BYTES,
    MAX_PARSER_RUNTIME_BYTES,
    MAX_PARSER_RUNTIME_FILES,
    PARSER_IMAGE_DIRECTORY,
    PARSER_IMAGE_NAME,
    PARSER_IMAGE_PATH,
    PARSER_LAUNCH_PROFILE,
    SignedWorkerRuntime,
    verify_worker_runtime,
)


def build(
    *,
    archive: Path,
    source_root: Path,
    python: Path,
    assets: Path,
    output: Path,
    pe_signer: Path,
    pe_verifier: Path,
    inventory_signer: Path,
    application_public_key: Path,
    msbuild: Path,
    native_inputs: Path,
    cmake: Path,
) -> None:
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise WorkerBuildError("parser-build-requires-windows-x64")
    if output.exists() or output.is_symlink():
        raise WorkerBuildError("parser-build-output-must-be-fresh")
    verify_source_variant(archive.resolve(strict=True), source_root.resolve(strict=True))
    manifest_path = REPO / "workers/document/parser-assets.json"
    manifest = json.loads(manifest_path.read_bytes())
    for entry in manifest["files"]:
        path = assets / entry["path"]
        if not path.is_file() or _digest(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise WorkerBuildError("parser-asset-hash-mismatch")
    output.mkdir(parents=True)
    parser_socket = build_parser_socket(
        archive=archive, source_root=source_root, output=output / "parser-socket", msbuild=msbuild
    )
    parser_overlapped = build_parser_overlapped(
        archive=archive, source_root=source_root, output=output / "parser-overlapped", msbuild=msbuild
    )
    source_overlay = prepare_dateutil_variant(
        python.parent.parent / "Lib/site-packages/dateutil", output / "parser-python"
    )
    parser_native = build_parser_native(
        inputs=native_inputs,
        output=output / "parser-native",
        python=python,
        python_library=source_root / "PCbuild/amd64/python314.lib",
        cmake=cmake,
    )
    command = [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--noupx",
        "--contents-directory",
        "_internal",
        "--name",
        PARSER_IMAGE_NAME,
        "--paths",
        str(source_overlay),
        "--paths",
        str(REPO),
        "--paths",
        str(REPO / "services/core-api/src"),
        "--distpath",
        str(output / "dist"),
        "--workpath",
        str(output / "work"),
        "--specpath",
        str(output / "spec"),
    ]
    # Docling's factories load selected models/backends dynamically. Freeze the
    # Python modules and their package data rather than shipping a mutable venv.
    for module in ("docling", "docling_core", "docling_parse", "docling_ibm_models", "transformers"):
        command.extend(("--collect-all", module))
    for name in VERSIONS:
        command.extend(("--copy-metadata", name))
    # The pinned torchvision release uses stable C++ library names newer than
    # PyInstaller's _C hook. These are loaded by torch.ops, not Python imports.
    command.extend(("--collect-binaries", "torchvision"))
    for name in ("_C_stable.pyd", "image_stable.pyd"):
        library = python.parent.parent / "Lib/site-packages/torchvision" / name
        if not library.is_file():
            raise WorkerBuildError("parser-torchvision-library-missing")
        command.extend(("--add-binary", f"{library}:torchvision"))
    command.append(str(REPO / "workers/windows/parser_worker.py"))
    with (output / "pyinstaller.log").open("wb") as log:
        result = subprocess.run(command, cwd=REPO, stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False)
    if result.returncode:
        raise WorkerBuildError("parser-pyinstaller-build-failed")
    _assemble_package(
        frozen_image=output / "dist" / PARSER_IMAGE_NAME,
        source_root=source_root,
        assets=assets,
        output=output,
        pe_signer=pe_signer,
        pe_verifier=pe_verifier,
        inventory_signer=inventory_signer,
        application_public_key=application_public_key,
        parser_socket=parser_socket,
        parser_overlapped=parser_overlapped,
        python_variant_receipt=source_overlay / "build-receipt.json",
        parser_native=parser_native,
    )


def _assemble_package(
    *,
    frozen_image: Path,
    source_root: Path,
    assets: Path,
    output: Path,
    pe_signer: Path,
    pe_verifier: Path,
    inventory_signer: Path,
    application_public_key: Path,
    parser_socket: Path | None = None,
    parser_overlapped: Path | None = None,
    python_variant_receipt: Path | None = None,
    parser_native: Path | None = None,
) -> None:
    manifest_path = REPO / "workers/document/parser-assets.json"
    manifest = json.loads(manifest_path.read_bytes())
    package = output / "package"
    if package.exists():
        raise WorkerBuildError("parser-build-output-must-be-fresh")

    def notice_folders(directory: str, names: list[str]) -> list[str]:
        if Path(directory).as_posix().endswith("/transformers/models"):
            # These pinned model factories discover classes by reading their
            # sealed Python files. Other modules remain in the frozen PYZ;
            # their unselected source trees are not parser inputs.
            return [
                name
                for name in names
                if (Path(directory) / name).is_dir()
                and name not in {"auto", "rt_detr", "rt_detr_v2", "encoder_decoder"}
            ]
        return ["licenses"] if directory.endswith(".dist-info") and "licenses" in names else []

    # Keep the artifact filename, but shorten its package directory so native
    # dependencies' legacy path APIs work under an AppContainer-hosted install.
    shutil.copytree(frozen_image, package / PARSER_IMAGE_DIRECTORY, ignore=notice_folders)
    image = package / PARSER_IMAGE_PATH
    internal = image.parent / "_internal"
    if parser_native is None:
        raise WorkerBuildError("parser-native-admission-derivative-missing")
    native_receipt = parser_native.parents[2] / "build-receipt.json"
    observed_native = json.loads(native_receipt.read_bytes())
    native_targets = list((internal / "docling_parse").glob("pdf_parsers*.pyd"))
    if (
        len(native_targets) != 1
        or observed_native["extensionSha256BeforeSigning"] != _digest(parser_native)
        or observed_native["inputsManifestSha256"] != _digest(REPO / "workers/document/parser-native-inputs.json")
        or observed_native["admissionHeaderSha256"] != _digest(REPO / "workers/document/parser_pdf_admission.h")
        or any(
            observed_native["patches"][name]["sha256"] != _digest(REPO / f"workers/document/{name}.patch")
            for name in ("docling-parser-native", "qpdf-parser-buffer")
        )
    ):
        raise WorkerBuildError("parser-native-admission-build-mismatch")
    shutil.copy2(parser_native, native_targets[0])
    shutil.copy2(native_receipt, internal / "parser-native-build.json")
    for name in (
        "docling-parser-native.patch",
        "qpdf-parser-buffer.patch",
        "parser_pdf_admission.h",
        "parser-native-inputs.json",
    ):
        shutil.copy2(REPO / "workers/document" / name, internal / name)
    # Torch imports its compile-package declarations even for eager inference.
    # A pre-existing, sealed empty namespace avoids temporary-directory
    # discovery. Compilation is disabled; OS ACLs still deny every write.
    cache = internal / "torch-disabled-cache"
    cache.mkdir()
    (cache / "DISABLED.txt").write_text("Read-only namespace. Torch compilation and cache writes are disabled.\n")
    build_root = source_root / "PCbuild/amd64"
    core = build_root / "python314.dll"
    _manifest_free(core)
    shutil.copy2(core, internal / "python314.dll")
    # Only standard-library extensions use the qualified CPython variant.
    # Third-party native payload stays intact; admitted DLL manifests are
    # handled separately by the closed resource-only derivative policy below.
    source_extensions = {p.name.casefold(): p for p in build_root.glob("*.pyd")}
    for target in internal.rglob("*.pyd"):
        source = source_extensions.get(target.name.casefold())
        if source is not None:
            _manifest_free(source)
            shutil.copy2(source, target)
    # The source-built _ssl/_hashlib extensions link these exact DLL names,
    # rather than the differently named binaries from the host Python install.
    for name in ("libssl-3.dll", "libcrypto-3.dll"):
        _manifest_free(build_root / name)
        shutil.copy2(build_root / name, internal / name)
    for module, extension in (("socket", parser_socket), ("overlapped", parser_overlapped)):
        if extension is None:
            raise WorkerBuildError("parser-native-derivative-missing")
        _manifest_free(extension)
        receipt = json.loads((extension.parent.parent / "build-receipt.json").read_bytes())
        if receipt["module"] != f"_{module}" or receipt["extensionSha256BeforeSigning"] != _digest(extension):
            raise WorkerBuildError("parser-native-build-receipt-mismatch")
        shutil.copy2(extension, internal / f"_{module}.pyd")
        shutil.copy2(extension.parent.parent / "build-receipt.json", internal / f"parser-{module}-build.json")
        shutil.copy2(REPO / f"workers/document/cpython-parser-{module}.patch", internal / f"parser-{module}.patch")
    if python_variant_receipt is None:
        raise WorkerBuildError("parser-python-derivative-missing")
    shutil.copy2(python_variant_receipt, internal / "parser-dateutil-build.json")
    shutil.copy2(REPO / "workers/document/dateutil-parser-registry.patch", internal / "parser-dateutil.patch")
    shutil.copy2(REPO / "workers/document/parser-manifests.json", internal / "parser-manifests.json")
    variants = []
    for target in sorted(internal.rglob("*")):
        if target.suffix.casefold() in {".dll", ".pyd"}:
            relative = target.relative_to(internal).as_posix()
            transformed = remove_inert_dll_manifests(target, relative_path=relative)
            if transformed is not None:
                variants.append({"path": relative, **transformed})
    (internal / "parser-native-variants.json").write_text(json.dumps(variants, indent=2) + "\n", encoding="utf-8")
    for source in (source_root / "LICENSE", *sorted((REPO / "workers/document/notices").glob("*.txt"))):
        target = internal / "notices" / source.name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)
    for name, source in (
        ("parser-config.json", REPO / "workers/document/parser-config.json"),
        ("parser-assets.json", manifest_path),
        ("parser-runtime.lock", REPO / "workers/document/requirements-parser.lock"),
    ):
        shutil.copy2(source, internal / name)
    for entry in manifest["files"]:
        if _digest(assets / entry["path"]) != entry["sha256"]:
            raise WorkerBuildError("parser-asset-hash-mismatch")
        target = internal / "parser-assets" / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(assets / entry["path"], target)
    # Preserve every bundled upstream notice byte under a bounded filename.
    # License folder depth is not part of a native import path; Windows' normal
    # path budget must also hold in the staged LPAC package.
    notice_index = []
    native_sources = parser_native.parents[2] / "sources"
    for source in sorted(native_sources.rglob("*")):
        if source.is_file() and source.name.casefold().startswith(("license", "copying", "copyright", "notice")):
            if source.is_symlink() or source.is_junction():
                raise WorkerBuildError("parser-native-notice-redirect")
            digest = _digest(source)
            target = internal / "notices" / f"{digest}.txt"
            if not target.exists():
                shutil.copy2(source, target)
            notice_index.append(
                {
                    "original": "native-source/" + source.relative_to(native_sources).as_posix(),
                    "bundled": target.relative_to(internal).as_posix(),
                    "sha256": digest,
                }
            )
    source_internal = frozen_image / "_internal"
    for folder in sorted(source_internal.glob("*.dist-info/licenses")):
        for original in sorted(p for p in folder.rglob("*") if p.is_file()):
            digest = _digest(original)
            target = internal / "notices" / f"{digest}.txt"
            target.parent.mkdir(exist_ok=True)
            if not target.exists():
                shutil.copy2(original, target)
            notice_index.append(
                {
                    "original": original.relative_to(source_internal).as_posix(),
                    "bundled": target.relative_to(internal).as_posix(),
                    "sha256": digest,
                }
            )
    (internal / "notice-index.json").write_text(json.dumps(notice_index, indent=2) + "\n", encoding="utf-8")
    files = sorted(p for p in package.rglob("*") if p.is_file())
    if len(files) > MAX_PARSER_RUNTIME_FILES or sum(p.stat().st_size for p in files) > MAX_PARSER_RUNTIME_BYTES:
        raise WorkerBuildError("parser-package-oversize")
    for target in files:
        if target.suffix.casefold() in {".exe", ".dll", ".pyd"}:
            _invoke(pe_signer, target)
            _invoke(pe_verifier, target)
    inventory = {
        "schemaVersion": "2.0",
        "documentType": "application-signed-lpac-parser-package",
        "launchProfile": PARSER_LAUNCH_PROFILE,
        "imagePath": PARSER_IMAGE_PATH,
        "files": [{"path": p.relative_to(package).as_posix(), "sha256": _digest(p)} for p in files],
    }
    raw = (json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(raw) > MAX_PARSER_INVENTORY_BYTES:
        raise WorkerBuildError("parser-inventory-oversize")
    (output / "inventory.json").write_bytes(raw)
    _invoke(inventory_signer, output / "inventory.json", output / "inventory.sig")
    verify_worker_runtime(
        SignedWorkerRuntime(package, raw, (output / "inventory.sig").read_bytes(), application_public_key.read_bytes()),
        profile="parser",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "archive",
        "source-root",
        "python",
        "assets",
        "output",
        "pe-signer",
        "pe-verifier",
        "inventory-signer",
        "application-public-key",
        "msbuild",
        "native-inputs",
        "cmake",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    build(**vars(args))


if __name__ == "__main__":
    main()
