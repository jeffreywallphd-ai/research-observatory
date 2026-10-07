"""Build the pinned parser admission/geometry derivative from local sources.

No dependency resolution or download occurs. Every upstream archive is pinned;
the only parser changes are the tracked native and QPDF patches and admission
header. Build logs and machine paths stay in the caller's local output folder.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

from plugin_worker_runtime_build import REPO, WorkerBuildError, _digest

INPUTS = REPO / "workers/document/parser-native-inputs.json"


def extract_source(archive: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise WorkerBuildError("parser-native-output-must-be-fresh")
    with tarfile.open(archive) as source:
        members = source.getmembers()
        if len(members) > 100000 or sum(m.size for m in members) > 1024 * 1024 * 1024:
            raise WorkerBuildError("parser-native-source-oversize")
        names = set()
        for item in members:
            path = PurePosixPath(item.name)
            if (
                path.is_absolute()
                or not path.parts
                or any(p in {"..", "."} for p in path.parts)
                or "\\" in item.name
                or ":" in item.name
                or not (item.isfile() or item.isdir())
                or item.name.casefold() in names
            ):
                raise WorkerBuildError("parser-native-source-invalid")
            names.add(item.name.casefold())
        target.mkdir(parents=True)
        source.extractall(target, members=members, filter="data")


def apply_source_patch(root: Path, patch: bytes) -> list[dict]:
    lines = patch.decode("utf-8", errors="strict").splitlines()
    receipts, index = [], 0
    while index < len(lines):
        if not lines[index].startswith("--- a/") or not lines[index + 1].startswith("+++ b/"):
            raise WorkerBuildError("parser-native-patch-invalid")
        name = lines[index][6:]
        if (
            lines[index + 1][6:] != name
            or PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
            or "\\" in name
            or ":" in name
        ):
            raise WorkerBuildError("parser-native-patch-invalid")
        path = root / name
        original_bytes = path.read_bytes()
        original = original_bytes.decode("utf-8").splitlines()
        output: list[str] = []
        position = 0
        index += 2
        while index < len(lines) and not lines[index].startswith("--- "):
            match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*", lines[index])
            if match is None:
                raise WorkerBuildError("parser-native-patch-invalid")
            index += 1
            body = []
            while index < len(lines) and not lines[index].startswith(("@@", "--- ")):
                if lines[index][:1] not in {" ", "+", "-"}:
                    raise WorkerBuildError("parser-native-patch-invalid")
                body.append(lines[index])
                index += 1
            old = [line[1:] for line in body if line[0] in {" ", "-"}]
            new = [line[1:] for line in body if line[0] in {" ", "+"}]
            start = int(match[1]) - 1
            if (
                start < position
                or original[start : start + len(old)] != old
                or (len(old), len(new)) != (int(match[2] or 1), int(match[4] or 1))
                or int(match[3]) - 1 != len(output) + start - position
            ):
                raise WorkerBuildError("parser-native-patch-context-mismatch")
            output.extend(original[position:start])
            output.extend(new)
            position = start + len(old)
        output.extend(original[position:])
        derived = ("\n".join(output) + "\n").encode()
        path.write_bytes(derived)
        receipts.append(
            {
                "path": name,
                "originalSha256": hashlib.sha256(original_bytes).hexdigest(),
                "derivedSha256": hashlib.sha256(derived).hexdigest(),
            }
        )
    return receipts


def prepare_sources(inputs: Path, output: Path) -> tuple[Path, dict]:
    if output.exists() or output.is_symlink():
        raise WorkerBuildError("parser-native-output-must-be-fresh")
    manifest = json.loads(INPUTS.read_bytes())
    for item in manifest["inputs"]:
        path = inputs / item["archive"]
        if (
            path.is_symlink()
            or path.is_junction()
            or path.stat().st_size != item["bytes"]
            or _digest(path) != item["sha256"]
        ):
            raise WorkerBuildError("parser-native-source-mismatch")
    output.mkdir(parents=True)
    roots = {}
    for item in manifest["inputs"]:
        extract_source(inputs / item["archive"], output / item["name"])
        roots[item["name"]] = output / item["name"]
    native = roots["docling"] / "docling_parse-7.16.0"
    patches = {}
    for name, root in (("docling-parser-native", native), ("qpdf-parser-buffer", roots["qpdf"])):
        patch = (REPO / f"workers/document/{name}.patch").read_bytes()
        patches[name] = {"sha256": hashlib.sha256(patch).hexdigest(), "changes": apply_source_patch(root, patch)}
    header = REPO / "workers/document/parser_pdf_admission.h"
    shutil.copy2(header, native / "src/parse/qpdf/ro_admission.h")
    offline = []
    for filename, name, count in (
        ("extlib_cxxopts.cmake", "cxxopts", 1),
        ("extlib_freetype.cmake", "freetype", 1),
        ("extlib_jpeg.cmake", "jpeg", 1),
        ("extlib_json.cmake", "json", 1),
        ("extlib_lcms2.cmake", "lcms2", 2),
        ("extlib_openjpeg.cmake", "openjpeg", 1),
        ("extlib_qpdf_v12.cmake", "qpdf", 1),
        ("extlib_utf8.git.cmake", "utf8", 1),
        ("extlib_loguru.cmake", "loguru", 1),
    ):
        path = native / "cmake" / filename
        before = path.read_text()
        after, changed = re.subn(
            r"GIT_REPOSITORY[^\n]+\n\s*GIT_TAG[^\n]+",
            'DOWNLOAD_COMMAND ""\n        UPDATE_COMMAND ""\n        SOURCE_DIR "' + roots[name].as_posix() + '"',
            before,
        )
        if changed != count:
            raise WorkerBuildError("parser-native-offline-context-mismatch")
        path.write_text(after, newline="\n")
        offline.append(filename)
    path = native / "cmake/extlib_blend2d.cmake"
    before = path.read_text()
    for name in ("asmjit", "blend2d"):
        before, count = re.subn(
            r"GIT_REPOSITORY https://github.com/" + name + r"/" + name + r"\.git\n"
            r"(?:\s*#[^\n]*\n)*\s*GIT_TAG[^\n]+",
            'DOWNLOAD_COMMAND ""\n        UPDATE_COMMAND ""\n        SOURCE_DIR "' + roots[name].as_posix() + '"',
            before,
        )
        if count != 1:
            raise WorkerBuildError("parser-native-offline-context-mismatch")
    path.write_text(before, newline="\n")
    offline.append(path.name)
    return native, {
        "inputsManifestSha256": _digest(INPUTS),
        "inputs": manifest["inputs"],
        "patches": patches,
        "admissionHeaderSha256": _digest(header),
        "offlineBuildFiles": offline,
    }


def build_parser_native(*, inputs: Path, output: Path, python: Path, python_library: Path, cmake: Path) -> Path:
    source, receipt = prepare_sources(inputs, output / "sources")
    pybind = output / "sources/pybind/pybind11/share/cmake/pybind11"

    def run(label, args):
        with (output / (label + ".log")).open("wb") as log:
            result = subprocess.run(
                [str(cmake), *map(str, args)],
                cwd=output,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=1200,
                check=False,
            )
        if result.returncode:
            raise WorkerBuildError("parser-native-build-failed-" + label)

    environment = dict(os.environ)
    zlib = output / "zlib-install"
    environment["CMAKE_PREFIX_PATH"] = str(zlib)
    run(
        "zlib-configure",
        [
            "-S",
            output / "sources/zlib",
            "-B",
            output / "zlib-build",
            "-G",
            "Visual Studio 17 2022",
            "-A",
            "x64",
            "-DZLIB_COMPAT=ON",
            "-DZLIB_ENABLE_TESTS=OFF",
            "-DBUILD_SHARED_LIBS=OFF",
            "-DCMAKE_INSTALL_PREFIX=" + str(zlib),
        ],
    )
    run("zlib-build", ["--build", output / "zlib-build", "--config", "Release", "--parallel", "4"])
    run("zlib-install", ["--install", output / "zlib-build", "--config", "Release"])
    include = subprocess.check_output(
        [str(python), "-B", "-c", 'import sysconfig;print(sysconfig.get_path("include"))'], text=True
    ).strip()
    if not (pybind / "pybind11Config.cmake").is_file():
        raise WorkerBuildError("parser-native-pybind-missing")
    run(
        "parser-configure",
        [
            "-S",
            source,
            "-B",
            output / "build",
            "-G",
            "Visual Studio 17 2022",
            "-A",
            "x64",
            "-DCMAKE_BUILD_TYPE=Release",
            "-Dpybind11_DIR=" + str(pybind),
            "-DPYBIND11_FINDPYTHON=ON",
            "-DPython_EXECUTABLE=" + str(python),
            "-DPython_INCLUDE_DIR=" + include,
            "-DPython_LIBRARY=" + str(python_library),
            "-DRO_PARSER_ZLIB_INCLUDE=" + str(zlib / "include"),
            "-DRO_PARSER_ZLIB_LIBRARY=" + str(zlib / "lib/zlibstatic.lib"),
            "-DZLIB_ROOT=" + str(zlib),
            "-DZLIB_INCLUDE_DIR=" + str(zlib / "include"),
            "-DZLIB_LIBRARY=" + str(zlib / "lib/zlibstatic.lib"),
            "-DFETCHCONTENT_FULLY_DISCONNECTED=ON",
            "-DFETCHCONTENT_UPDATES_DISCONNECTED=ON",
            "-DFETCHCONTENT_SOURCE_DIR_BLEND2D=" + str(output / "sources/blend2d"),
            "-DFETCHCONTENT_SOURCE_DIR_LOGURUGITREPO=" + str(output / "sources/loguru"),
        ],
    )
    run(
        "parser-build",
        ["--build", output / "build", "--config", "Release", "--target", "pdf_parsers", "--parallel", "4"],
    )
    libraries = list((output / "build").rglob("pdf_parsers*.pyd"))
    if len(libraries) != 1:
        raise WorkerBuildError("parser-native-build-output-invalid")
    receipt.update(
        schemaVersion="1.0",
        documentType="parser-native-admission-build",
        version="7.16.0",
        extensionSha256BeforeSigning=_digest(libraries[0]),
        cmakeSha256=_digest(cmake),
        pythonImportLibrarySha256=_digest(python_library),
    )
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return libraries[0]
