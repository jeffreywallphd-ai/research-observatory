"""Bounded inspection of a user-selected connector archive before trust.

Inspection is data parsing, not publisher admission. Only the existing signed
package verifier can authorize execution after a locally trusted key is found.
ZIP metadata never supplies a path for extraction or a worker payload.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field

from .plugin_manifest import PluginManifest, _reject_constant, _unique_object

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_FILE_BYTES = 16 * 1024 * 1024
_MAX_PACKAGE_BYTES = 64 * 1024 * 1024


class PluginPackageIntakeProblem(ValueError):
    def __init__(self, code: str = "plugin-archive-invalid") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class InspectedPluginArchive:
    manifest: PluginManifest
    manifest_bytes: bytes = field(repr=False)
    signature: bytes = field(repr=False)
    files: dict[str, bytes] = field(repr=False)
    manifest_sha256: str
    package_sha256: str
    signature_sha256: str


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def inspect_plugin_archive(raw: bytes) -> InspectedPluginArchive:
    """Inspect only exact declared files, with bounded in-memory decompression."""

    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_ARCHIVE_BYTES:
        raise PluginPackageIntakeProblem("plugin-archive-size-invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r", allowZip64=False) as archive:
            members = archive.infolist()
            if not 3 <= len(members) <= 130 or len({item.filename.casefold() for item in members}) != len(members):
                raise PluginPackageIntakeProblem()
            names = {item.filename for item in members}
            if "manifest.json" not in names or "manifest.sig" not in names:
                raise PluginPackageIntakeProblem()
            for item in members:
                if (
                    item.is_dir()
                    or item.flag_bits & 0x1
                    or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or item.file_size > _MAX_FILE_BYTES
                    or item.filename.startswith("/")
                    or "\\" in item.filename
                    or any(part in {"", ".", ".."} for part in item.filename.split("/"))
                    or ((item.external_attr >> 16) & 0o170000) == 0o120000
                ):
                    raise PluginPackageIntakeProblem()
            info = {item.filename: item for item in members}
            if info["manifest.json"].file_size > _MAX_MANIFEST_BYTES or info["manifest.sig"].file_size != 64:
                raise PluginPackageIntakeProblem()
            manifest_bytes = archive.read("manifest.json")
            signature = archive.read("manifest.sig")
            if not 0 < len(manifest_bytes) <= _MAX_MANIFEST_BYTES or len(signature) != 64:
                raise PluginPackageIntakeProblem()
            document = json.loads(
                manifest_bytes.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant
            )
            manifest = PluginManifest.model_validate(document)
            declared = {item.path: item.sha256 for item in manifest.files}
            if names != {"manifest.json", "manifest.sig", *declared}:
                raise PluginPackageIntakeProblem()
            files: dict[str, bytes] = {}
            total = 0
            digest = hashlib.sha256(b"research-observatory-connector-package-v1\x00")
            for path in sorted(declared):
                item = info[path]
                if item.file_size > _MAX_FILE_BYTES:
                    raise PluginPackageIntakeProblem()
                body = archive.read(path)
                total += len(body)
                if total > _MAX_PACKAGE_BYTES or len(body) != item.file_size or _sha(body) != declared[path]:
                    raise PluginPackageIntakeProblem()
                files[path] = body
                encoded = path.encode("utf-8")
                digest.update(len(encoded).to_bytes(4, "big"))
                digest.update(encoded)
                digest.update(len(body).to_bytes(8, "big"))
                digest.update(body)
            return InspectedPluginArchive(
                manifest=manifest,
                manifest_bytes=manifest_bytes,
                signature=signature,
                files=files,
                manifest_sha256=_sha(manifest_bytes),
                package_sha256="sha256:" + digest.hexdigest(),
                signature_sha256=_sha(signature),
            )
    except PluginPackageIntakeProblem:
        raise
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        OSError,
    ):
        raise PluginPackageIntakeProblem() from None
