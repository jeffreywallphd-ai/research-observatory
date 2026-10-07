"""Build only the offline parser's native socket import compatibility variant.

The qualified base source tree is never edited or rebuilt. One exact tracked
patch removes eager Winsock initialization; the real CPython types/C API remain.
LPAC, not this import change, establishes denial of native network operations.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from plugin_worker_runtime_build import REPO, WorkerBuildError, _digest, _manifest_free, verify_source_variant

SOURCE_SOCKET_SHA256 = "310f5e3ef77157f4856f50d508aacbf656e492d99feb88c228cb1dac48049fd2"
PATCH_SHA256 = "ec569790d350ad7232854798b4b758448c7fead449543886ef61842bd3b3bfcb"
PATCH = REPO / "workers/document/cpython-parser-socket.patch"
OVERLAPPED_SOURCE_SHA256 = "0ee00b7c26732c632fd2b711b62503215a25308cc5d615d46fbb173adcf47c35"
OVERLAPPED_PATCH_SHA256 = "b67ff6ad5ab4a8a21ee23a81f5572bf3cda44c78368ad8c41e35dea683eaa68a"
OVERLAPPED_PATCH = REPO / "workers/document/cpython-parser-overlapped.patch"
_NS = "http://schemas.microsoft.com/developer/msbuild/2003"


def patched_socket(source: bytes, patch: bytes) -> bytes:
    return _patched_source(source, patch, SOURCE_SOCKET_SHA256, PATCH_SHA256, "socketmodule.c")


def _patched_source(source: bytes, patch: bytes, source_sha: str, patch_sha: str, filename: str) -> bytes:
    if hashlib.sha256(source).hexdigest() != source_sha:
        raise WorkerBuildError("parser-socket-source-mismatch")
    if hashlib.sha256(patch).hexdigest() != patch_sha:
        raise WorkerBuildError("parser-socket-patch-mismatch")
    lines = patch.decode("utf-8", errors="strict").splitlines()
    if lines[:2] != [f"--- Modules/{filename}", f"+++ Modules/{filename}"]:
        raise WorkerBuildError("parser-socket-patch-invalid")
    original = source.decode("utf-8", errors="strict").splitlines()
    output: list[str] = []
    position, index = 0, 2
    while index < len(lines):
        match = re.fullmatch(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", lines[index])
        if match is None:
            raise WorkerBuildError("parser-socket-patch-invalid")
        index += 1
        body = []
        while index < len(lines) and not lines[index].startswith("@@"):
            if lines[index][:1] not in {" ", "+", "-"}:
                raise WorkerBuildError("parser-socket-patch-invalid")
            body.append(lines[index])
            index += 1
        old = [line[1:] for line in body if line[0] in {" ", "-"}]
        new = [line[1:] for line in body if line[0] in {" ", "+"}]
        start = int(match[1]) - 1
        if (
            (len(old), len(new)) != (int(match[2]), int(match[4]))
            or start < position
            or int(match[3]) - 1 != len(output) + start - position
            or original[start : start + len(old)] != old
        ):
            raise WorkerBuildError("parser-socket-patch-context-mismatch")
        output.extend(original[position:start])
        output.extend(new)
        position = start + len(old)
    output.extend(original[position:])
    return ("\n".join(output) + "\n").encode("utf-8")


def build_parser_socket(*, archive: Path, source_root: Path, output: Path, msbuild: Path) -> Path:
    return _build_parser_extension(
        archive=archive,
        source_root=source_root,
        output=output,
        msbuild=msbuild,
        module="_socket",
        filename="socketmodule.c",
        patch_file=PATCH,
        source_sha=SOURCE_SOCKET_SHA256,
        patch_sha=PATCH_SHA256,
    )


def build_parser_overlapped(*, archive: Path, source_root: Path, output: Path, msbuild: Path) -> Path:
    return _build_parser_extension(
        archive=archive,
        source_root=source_root,
        output=output,
        msbuild=msbuild,
        module="_overlapped",
        filename="overlapped.c",
        patch_file=OVERLAPPED_PATCH,
        source_sha=OVERLAPPED_SOURCE_SHA256,
        patch_sha=OVERLAPPED_PATCH_SHA256,
    )


def _build_parser_extension(
    *,
    archive: Path,
    source_root: Path,
    output: Path,
    msbuild: Path,
    module: str,
    filename: str,
    patch_file: Path,
    source_sha: str,
    patch_sha: str,
) -> Path:
    if output.exists() or output.is_symlink():
        raise WorkerBuildError("parser-socket-output-must-be-fresh")
    verify_source_variant(archive, source_root)
    original = source_root / "Modules" / filename
    patch = patch_file.read_bytes()
    derived = _patched_source(original.read_bytes(), patch, source_sha, patch_sha, filename)
    output.mkdir(parents=True)
    modules = output / "Modules"
    (modules / "clinic").mkdir(parents=True)
    (modules / filename).write_bytes(derived)
    for name in ("socketmodule.h", f"clinic/{filename}.h") if module == "_socket" else (f"clinic/{filename}.h",):
        shutil.copy2(source_root / "Modules" / name, modules / name)
    project = ET.parse(source_root / "PCbuild" / f"{module}.vcxproj")
    root = project.getroot()
    for item in root.iter(f"{{{_NS}}}Import"):
        value = item.attrib["Project"]
        if "$" not in value:
            item.set("Project", str(source_root / "PCbuild" / value))
    for item in root.iter(f"{{{_NS}}}ClCompile"):
        if "Include" in item.attrib:
            item.set("Include", str(modules / filename))
    for item in root.iter(f"{{{_NS}}}ResourceCompile"):
        if "Include" in item.attrib:
            item.set("Include", str(source_root / "PC/python_nt.rc"))
    for group in root.findall(f"{{{_NS}}}ItemGroup"):
        for item in list(group):
            if item.tag == f"{{{_NS}}}ProjectReference":
                group.remove(item)
    # Only link the existing qualified import library; no pythoncore build.
    group = ET.SubElement(root, f"{{{_NS}}}ItemDefinitionGroup")
    link = ET.SubElement(group, f"{{{_NS}}}Link")
    ET.SubElement(link, f"{{{_NS}}}AdditionalLibraryDirectories").text = (
        str(source_root / "PCbuild/amd64") + ";%(AdditionalLibraryDirectories)"
    )
    project_path = output / f"{module}.vcxproj"
    ET.register_namespace("", _NS)
    project.write(project_path, encoding="utf-8", xml_declaration=True)
    command = [
        str(msbuild),
        str(project_path),
        "/t:Build",
        "/p:Configuration=Release",
        "/p:Platform=x64",
        "/p:PlatformToolset=v145",
        "/p:BuildProjectReferences=false",
        f"/p:PySourcePath={source_root}\\",
        f"/p:OutDir={output / 'bin'}\\",
        f"/p:IntDir={output / 'obj'}\\",
        "/nologo",
        "/verbosity:minimal",
    ]
    before = {
        name: _digest(source_root / "PCbuild/amd64" / name)
        for name in ("python314.dll", "python314.lib", "_socket.pyd")
    }
    with (output / "build.log").open("wb") as log:
        result = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, timeout=180, check=False)
    if result.returncode:
        raise WorkerBuildError("parser-socket-build-failed")
    image = output / "bin" / f"{module}.pyd"
    _manifest_free(image)
    if before != {name: _digest(source_root / "PCbuild/amd64" / name) for name in before}:
        raise WorkerBuildError("parser-socket-base-mutated")
    receipt = {
        "schemaVersion": "1.0",
        "documentType": "parser-only-cpython-extension-build",
        "module": module,
        "sourceSha256": source_sha,
        "patchSha256": hashlib.sha256(patch).hexdigest(),
        "derivedSourceSha256": hashlib.sha256(derived).hexdigest(),
        "extensionSha256BeforeSigning": _digest(image),
        "compilerDriverSha256": _digest(msbuild),
        "baseArtifactsUnchanged": before,
        "abi": "cpython-3.14.6-windows-x86_64",
        "winsockAtImport": False,
    }
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return image
