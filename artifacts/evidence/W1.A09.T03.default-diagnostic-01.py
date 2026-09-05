"""Read-only Shell/path facts; never enumerate folders or disclose account paths."""
import ctypes
import json
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))
from research_observatory_core.windows_credentials import _Guid, _guid  # noqa: E402

shell = ctypes.WinDLL("shell32", use_last_error=True)
ole = ctypes.WinDLL("ole32", use_last_error=True)
get = shell.SHGetKnownFolderPath
get.argtypes = (ctypes.POINTER(_Guid), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(wintypes.LPWSTR))
get.restype = ctypes.c_long
ole.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
ole.CoTaskMemFree.restype = None
paths = {}
facts = {}
for role, identity, flags in (
    ("actual", "F1B32785-6FBA-4FCF-9D55-7B8E7F157091", 0),
    ("default", "F1B32785-6FBA-4FCF-9D55-7B8E7F157091", 1024),
    ("programFiles", "905E63B6-C1BF-494E-B29C-65B732D3D21A", 0),
    ("programFilesX86", "7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E", 0),
    ("windows", "F38BF404-1D43-42F2-9305-67DE0B28FC23", 0),
):
    allocation = wintypes.LPWSTR()
    try:
        status = get(ctypes.byref(_guid(uuid.UUID(identity))), flags, None, ctypes.byref(allocation))
        facts[role] = {"hresult": status, "pathReturned": bool(allocation.value)}
        if status == 0 and allocation.value:
            paths[role] = Path(allocation.value)
    finally:
        ole.CoTaskMemFree(allocation)
if "actual" in paths and "default" in paths:
    facts["actualEqualsDefault"] = paths["actual"] == paths["default"]
    product = paths["actual"] / "Research Observatory"
    ancestors = []
    for position, directory in enumerate([*reversed(product.parents), product]):
        try:
            state = directory.lstat()
            ancestors.append({"position": position, "directory": directory.is_dir(),
                              "reparse": bool(state.st_file_attributes & 0x400),
                              "canonicalSpelling": directory.resolve(strict=True) == directory})
        except OSError as error:
            ancestors.append({"position": position, "error": type(error).__name__})
    facts["productAncestorMetadata"] = ancestors
    facts["insideInstallationRoot"] = any(
        product.is_relative_to(paths[role]) for role in ("programFiles", "programFilesX86", "windows") if role in paths
    )
print(json.dumps(facts, sort_keys=True))
