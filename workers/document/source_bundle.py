"""Read-only source introspection for bytecode already frozen in the parser.

PyTorch's freezer hook duplicates source files for inspect/JIT. Keep the exact
public source bytes in one signed package archive; never extract them to disk.
This loader supplies source text only and does not load or execute new modules.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import zipfile
from io import BytesIO
from pathlib import Path

SOURCE_PACKAGES = frozenset({"torch", "torchvision", "docling", "docling_core", "docling_ibm_models"})
MAX_SOURCE_BYTES = 64 * 1_048_576
MAX_MEMBER_BYTES = 4 * 1_048_576
MAX_SOURCE_FILES = 4096
_PART = re.compile(r"[A-Za-z0-9_]+(?:\.py)?\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")


class SourceBundleError(ValueError):
    """Content-free source-package failure."""


def source_path(name: str) -> bool:
    parts = name.split("/")
    return (
        len(parts) >= 2
        and parts[0] in SOURCE_PACKAGES
        and parts[-1].endswith(".py")
        and all(_PART.fullmatch(part) is not None for part in parts)
    )


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def install_source_loader(root: Path, loader_type) -> None:
    """Add source introspection to the existing frozen loader, not execution."""
    valid = False
    try:
        if not root.is_absolute() or root.is_symlink() or root.is_junction():
            raise ValueError
        index_path, archive_path = root / "parser-source-index.json", root / "parser-sources.zip"
        if any(path.is_symlink() or path.is_junction() for path in (index_path, archive_path)):
            raise ValueError
        with index_path.open("rb") as stream:
            index_bytes = stream.read(2 * 1_048_576 + 1)
        if len(index_bytes) > 2 * 1_048_576:
            raise ValueError
        index = json.loads(index_bytes, object_pairs_hook=_object)
        if (
            set(index) != {"schemaVersion", "documentType", "archiveSha256", "files"}
            or index["schemaVersion"] != "1.0"
            or index["documentType"] != "pinned-parser-python-sources"
            or not isinstance(index["archiveSha256"], str)
            or _DIGEST.fullmatch(index["archiveSha256"]) is None
            or type(index["files"]) is not list
            or not 0 < len(index["files"]) <= MAX_SOURCE_FILES
        ):
            raise ValueError
        expected = {}
        folded = set()
        for item in index["files"]:
            if (
                type(item) is not dict
                or set(item) != {"path", "sha256", "bytes"}
                or not isinstance(item["path"], str)
                or not source_path(item["path"])
                or item["path"].casefold() in folded
                or not isinstance(item["sha256"], str)
                or _DIGEST.fullmatch(item["sha256"]) is None
                or type(item["bytes"]) is not int
                or not 0 <= item["bytes"] <= MAX_MEMBER_BYTES
            ):
                raise ValueError
            expected[item["path"]] = item
            folded.add(item["path"].casefold())
        if sum(item["bytes"] for item in expected.values()) > MAX_SOURCE_BYTES:
            raise ValueError
        with archive_path.open("rb") as stream:
            archived = stream.read(MAX_SOURCE_BYTES + 1)
        if len(archived) > MAX_SOURCE_BYTES or hashlib.sha256(archived).hexdigest() != index["archiveSha256"]:
            raise ValueError
        archive = zipfile.ZipFile(BytesIO(archived))
        members = archive.infolist()
        if len(members) != len(expected) or {item.filename for item in members} != set(expected):
            raise ValueError
        for item in members:
            if (
                item.flag_bits & 1
                or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                or item.file_size != expected[item.filename]["bytes"]
                or item.is_dir()
            ):
                raise ValueError
        valid = True
    except Exception:
        pass
    if not valid:
        raise SourceBundleError("parser-source-bundle-invalid")
    original = loader_type.get_source

    def get_source(loader, fullname):
        available = original(loader, fullname)
        if available is not None:
            return available
        selected = None
        try:
            path = Path(loader.path)
            relative = path.relative_to(root).as_posix()
            item = expected.get(relative)
            if item is None:
                return None
            wire = archive.read(relative)
            if len(wire) != item["bytes"] or hashlib.sha256(wire).hexdigest() != item["sha256"]:
                raise ValueError
            selected = importlib.util.decode_source(wire)
        except Exception:
            pass
        if selected is None:
            raise SourceBundleError("parser-source-bundle-invalid")
        return selected

    loader_type.get_source = get_source


def install_frozen_sources(root: Path) -> None:
    import pyimod02_importers  # type: ignore[import-not-found]

    install_source_loader(root, pyimod02_importers.PyiFrozenLoader)
