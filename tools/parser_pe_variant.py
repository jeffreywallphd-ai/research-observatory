"""Remove narrowly admitted DLL manifests from the offline LPAC package.

Windows' activation machinery may deny loading these embedded manifests under
LPAC. Admit inert asInvoker manifests and the exact previously qualified CPython
manifest on named standard-library DLLs. Unknown assembly policy, dependencies,
elevations and executable manifests are never removed. Preserve original bytes
in the signed package receipt and verify native payload and resource identity.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import xml.etree.ElementTree as ET
from ctypes import wintypes
from pathlib import Path
from typing import Any

import pefile  # type: ignore[import-untyped]
from plugin_worker_runtime_build import REPO, WorkerBuildError, _digest

_ASM = "urn:schemas-microsoft-com:asm.v1"
_TRUST = "urn:schemas-microsoft-com:asm.v3"
_PYTHON_MANIFEST_SHA256 = "7193b1d7f106dea927ec1687ff840302d88f6d352452c7207c68446454a22ba2"
_STDLIB_VARIANTS = frozenset(
    {
        "_asyncio.pyd",
        "_ctypes.pyd",
        "_elementtree.pyd",
        "_multiprocessing.pyd",
        "_overlapped.pyd",
        "_queue.pyd",
        "_sqlite3.pyd",
        "_uuid.pyd",
        "_wmi.pyd",
        "_zoneinfo.pyd",
        "pyexpat.pyd",
        "python3.dll",
        "sqlite3.dll",
    }
)


def inert_dll_manifest(data: bytes) -> bool:
    if len(data) > 65536 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        return False
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return False
    if root.tag == f"{{{_ASM}}}assembly" and root.attrib == {"manifestVersion": "1.0"} and not list(root):
        return not (root.text or "").strip() and not (root.tail or "").strip()
    expected = [
        (_ASM, "assembly", {"manifestVersion": "1.0"}),
        (_TRUST, "trustInfo", {}),
        (_TRUST, "security", {}),
        (_TRUST, "requestedPrivileges", {}),
        (_TRUST, "requestedExecutionLevel", {"level": "asInvoker", "uiAccess": "false"}),
    ]
    node = root
    for index, (namespace, name, attributes) in enumerate(expected):
        if (
            node.tag != f"{{{namespace}}}{name}"
            or node.attrib != attributes
            or (node.text or "").strip()
            or (node.tail or "").strip()
        ):
            return False
        children = list(node)
        if index == len(expected) - 1:
            return not children
        if len(children) != 1:
            return False
        node = children[0]
    return False


def _native_payload(pe: Any) -> dict[str, object]:
    def fields(value: Any, ignored: set[str]) -> dict[str, object]:
        return {name: getattr(value, name) for row in value.__keys__ for name in row if name not in ignored}

    return {
        "machine": pe.FILE_HEADER.Machine,
        "entry": pe.OPTIONAL_HEADER.AddressOfEntryPoint,
        "fileHeader": fields(pe.FILE_HEADER, {"NumberOfSections", "TimeDateStamp"}),
        "optionalHeader": fields(pe.OPTIONAL_HEADER, {"CheckSum", "SizeOfImage", "SizeOfInitializedData"}),
        "sections": [
            (
                section.Name.rstrip(b"\0").decode("ascii"),
                section.VirtualAddress,
                section.Misc_VirtualSize,
                section.Characteristics,
                hashlib.sha256(section.get_data()).hexdigest(),
            )
            for section in pe.sections
            if section.Name.rstrip(b"\0") != b".rsrc"
        ],
        "directories": [
            (i, value.VirtualAddress, value.Size)
            for i, value in enumerate(pe.OPTIONAL_HEADER.DATA_DIRECTORY)
            if i not in {2, 4}
        ],
    }


def _section_integrity(pe: Any) -> None:
    mapped: list[tuple[int, int]] = []
    raw: list[tuple[int, int]] = []
    for section in pe.sections:
        low = section.VirtualAddress
        high = low + max(section.Misc_VirtualSize, section.SizeOfRawData)
        begin, end = section.PointerToRawData, section.PointerToRawData + section.SizeOfRawData
        if any(max(low, a) < min(high, b) for a, b in mapped) or any(max(begin, a) < min(end, b) for a, b in raw):
            raise WorkerBuildError("parser-section-overlap")
        mapped.append((low, high))
        if section.SizeOfRawData:
            raw.append((begin, end))


def _resources(pe: Any, *, allowed_padding_sha256: str | None = None) -> list[tuple[int | str, int | str, int, bytes]]:
    _section_integrity(pe)
    root = getattr(pe, "DIRECTORY_ENTRY_RESOURCE", None)
    if root is None:
        return []
    sections = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".rsrc"]
    if len(sections) != 1 or sections[0].Characteristics & 0x20000000:
        raise WorkerBuildError("parser-resource-native-overlap")
    section = sections[0]
    covered = bytearray(section.SizeOfRawData)

    def account(offset: int, length: int) -> None:
        first = offset - section.PointerToRawData
        if not 0 <= first <= first + length <= len(covered):
            raise WorkerBuildError("parser-resource-bookkeeping-outside-section")
        covered[first : first + length] = b"\1" * length

    def tree(node: Any) -> None:
        account(node.struct.get_file_offset(), node.struct.sizeof())
        for entry in node.entries:
            account(entry.struct.get_file_offset(), entry.struct.sizeof())
            if entry.name is not None:
                name_offset = pe.get_offset_from_rva(pe.OPTIONAL_HEADER.DATA_DIRECTORY[2].VirtualAddress)
                name_offset += entry.struct.NameOffset
                name_length = int.from_bytes(pe.__data__[name_offset : name_offset + 2], "little")
                account(name_offset, 2 + name_length * 2)
            if hasattr(entry, "directory"):
                tree(entry.directory)
            else:
                account(entry.data.struct.get_file_offset(), entry.data.struct.sizeof())
                data = entry.data.struct
                account(pe.get_offset_from_rva(data.OffsetToData), data.Size)

    tree(root)
    padding = bytes(byte if not admitted else 0 for byte, admitted in zip(section.get_data(), covered, strict=True))
    if (
        any(entry.name is None and entry.struct.Id == 24 for entry in root.entries)
        and any(padding)
        and hashlib.sha256(padding).hexdigest() != allowed_padding_sha256
    ):
        raise WorkerBuildError("parser-resource-unexplained-bytes")
    start, end = section.VirtualAddress, section.VirtualAddress + section.SizeOfRawData
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[2]
    if not start <= directory.VirtualAddress < directory.VirtualAddress + directory.Size <= end:
        raise WorkerBuildError("parser-resource-directory-outside-section")
    for index, directory in enumerate(pe.OPTIONAL_HEADER.DATA_DIRECTORY):
        if (
            index not in {2, 4}
            and directory.VirtualAddress
            and directory.Size
            and max(start, directory.VirtualAddress) < min(end, directory.VirtualAddress + directory.Size)
        ):
            raise WorkerBuildError("parser-resource-loader-overlap")
    ranges: list[tuple[int, int]] = []
    result = []
    for kind in root.entries:
        key = str(kind.name) if kind.name is not None else kind.struct.Id
        for name in kind.directory.entries:
            identifier = str(name.name) if name.name is not None else name.struct.Id
            for language in name.directory.entries:
                data = language.data.struct
                low, high = data.OffsetToData, data.OffsetToData + data.Size
                if not start <= low <= high <= end or any(max(low, a) < min(high, b) for a, b in ranges):
                    raise WorkerBuildError("parser-resource-payload-overlap")
                ranges.append((low, high))
                result.append((key, identifier, language.struct.Id, pe.get_data(low, data.Size)))
    return result


def remove_inert_dll_manifests(path: Path, *, relative_path: str) -> dict[str, object] | None:
    if path.suffix.casefold() not in {".dll", ".pyd"} or path.is_symlink() or path.is_junction():
        raise WorkerBuildError("parser-manifest-target-invalid")
    original_sha = _digest(path)
    policy = json.loads((REPO / "workers/document/parser-manifests.json").read_bytes())
    admitted = {entry["path"]: entry for entry in policy["files"]}
    if len(admitted) != len(policy["files"]):
        raise WorkerBuildError("parser-manifest-policy-duplicate")
    pe = pefile.PE(str(path), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
    resources = []
    before = _native_payload(pe)
    certificate_offset = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].get_file_offset()
    entry = admitted.get(relative_path)
    padding_sha = entry.get("resourcePaddingSha256") if entry is not None else None
    original_resources = _resources(pe, allowed_padding_sha256=padding_sha)
    for kind, name, language, raw in original_resources:
        if kind == 24:
            # The exact CPython 3.14.6 manifest is already the qualified base
            # variant's removed resource. Admit it only for named stdlib DLLs;
            # no approximate dependency/compatibility policy is accepted.
            known_python = (
                path.name.casefold() in _STDLIB_VARIANTS and hashlib.sha256(raw).hexdigest() == _PYTHON_MANIFEST_SHA256
            )
            if (
                name != 2
                or not isinstance(language, int)
                or (None if entry is None else {k: v for k, v in entry.items() if k != "resourcePaddingSha256"})
                != {
                    "path": relative_path,
                    "name": name,
                    "language": language,
                    "manifestSha256": hashlib.sha256(raw).hexdigest(),
                }
                or not (known_python or inert_dll_manifest(raw))
            ):
                pe.close()
                raise WorkerBuildError("parser-manifest-policy-unsupported")
            resources.append((name, language, raw))
    pe.close()
    if not resources:
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    kernel.BeginUpdateResourceW.restype = wintypes.HANDLE
    kernel.UpdateResourceW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.WORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.UpdateResourceW.restype = wintypes.BOOL
    kernel.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    kernel.EndUpdateResourceW.restype = wintypes.BOOL
    handle = kernel.BeginUpdateResourceW(str(path), False)
    if not handle:
        raise WorkerBuildError("parser-manifest-update-unavailable")
    committed = False
    try:
        for name, language, _raw in resources:
            if not kernel.UpdateResourceW(
                handle, ctypes.cast(24, wintypes.LPCWSTR), ctypes.cast(name, wintypes.LPCWSTR), language, None, 0
            ):
                raise WorkerBuildError("parser-manifest-update-failed")
        if not kernel.EndUpdateResourceW(handle, False):
            raise WorkerBuildError("parser-manifest-update-failed")
        committed = True
    finally:
        if not committed:
            kernel.EndUpdateResourceW(handle, True)
    # The derivative is re-signed by the application after this transformation.
    # Clear only the obsolete certificate directory; preserve overlay bytes.
    with path.open("r+b") as target:
        target.seek(certificate_offset)
        target.write(b"\0" * 8)
    after_pe = pefile.PE(str(path), fast_load=True)
    after_pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
    after = _native_payload(after_pe)
    remaining = _resources(after_pe)
    after_pe.close()
    if after != before or remaining != [item for item in original_resources if item[0] != 24]:
        raise WorkerBuildError("parser-manifest-native-payload-changed")
    return {
        "sourceSha256": original_sha,
        "variantSha256BeforeSigning": _digest(path),
        "nativePayload": before,
        "resourcePaddingSha256": padding_sha,
        "removed": [
            {
                "name": name,
                "language": language,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "originalBase64": base64.b64encode(raw).decode("ascii"),
            }
            for name, language, raw in resources
        ],
    }
