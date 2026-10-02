"""Stream one authenticated document into the application-signed LPAC worker.

The caller owns the encrypted source stage and its read lease. This launcher
receives only a decrypted stream, sends bounded private-pipe frames, and never
writes document bytes to a filesystem path.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO

from workers.document.inspection import MAX_DOCUMENT_BYTES, DocumentInspection, DocumentInspectionError

from . import connector_launcher
from . import lpac_launcher as win
from .protocol import MAX_DOCUMENT_CHUNK, encode_frame
from .recovery_guardian import GuardianError
from .runtime_inventory import RuntimeInventoryError, SignedWorkerRuntime, load_installed_worker_runtime

_INSPECTION_MEMORY_MIB = 1024
_INSPECTION_WALL_SECONDS = 120
_REJECTION_CODES = frozenset(
    {"unsupported-format", "password-protected", "unsafe-content", "oversize", "malformed-content", "format-mismatch"}
)
_FORMAT_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "jats": "application/xml",
    "tei": "application/xml",
    "xml": "application/xml",
    "html": "text/html",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate verdict key")
        result[key] = value
    return result


def _document_dialogue(
    kernel: Any,
    parent_stdin: int,
    parent_stdout: int,
    request: dict[str, Any],
    source: BinaryIO,
    cancel: Callable[[], bool] | None,
) -> tuple[bytes, int]:
    win._write(kernel, parent_stdin, encode_frame(request))
    digest = hashlib.sha256()
    length = 0
    while True:
        if cancel is not None and cancel():
            raise win.LPACError("lpac-worker-cancelled")
        chunk = source.read(MAX_DOCUMENT_CHUNK)
        if not isinstance(chunk, bytes) or len(chunk) > MAX_DOCUMENT_CHUNK:
            raise win.LPACError("lpac-document-source-invalid")
        if not chunk:
            break
        length += len(chunk)
        if length > MAX_DOCUMENT_BYTES:
            raise win.LPACError("lpac-document-oversize")
        digest.update(chunk)
        connector_launcher._write_binary(kernel, parent_stdin, chunk)
    connector_launcher._write_binary(kernel, parent_stdin, b"")
    win._write(
        kernel,
        parent_stdin,
        encode_frame(
            {
                "protocolVersion": "1.0",
                "jobNonce": request["jobNonce"],
                "sequence": 1,
                "operation": "inspect-end",
                "inputLength": length,
                "inputSha256": digest.hexdigest(),
            }
        ),
    )
    frame = connector_launcher._read_control(kernel, parent_stdout, request["jobNonce"], 2)
    if set(frame) != {"protocolVersion", "jobNonce", "sequence", "operation", "outputLength", "outputSha256"}:
        raise win.LPACError("lpac-document-result-invalid")
    output = connector_launcher._read_binary(kernel, parent_stdout)
    if (
        frame["operation"] != "invoke-result"
        or type(frame["outputLength"]) is not int
        or frame["outputLength"] != len(output)
        or not isinstance(frame["outputSha256"], str)
        or frame["outputSha256"] != hashlib.sha256(output).hexdigest()
    ):
        raise win.LPACError("lpac-document-result-invalid")
    return output, 0


def _decode_verdict(raw: bytes) -> DocumentInspection:
    if len(raw) > 2048:
        raise DocumentInspectionError("worker-unavailable")
    try:
        value = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("invalid JSON constant")),
        )
    except UnicodeError, ValueError:
        raise DocumentInspectionError("worker-unavailable") from None
    if not isinstance(value, dict):
        raise DocumentInspectionError("worker-unavailable")
    if (
        set(value) == {"status", "code"}
        and value["status"] == "rejected"
        and isinstance(value["code"], str)
        and value["code"] in _REJECTION_CODES
    ):
        raise DocumentInspectionError(value["code"])
    if (
        set(value) != {"status", "format", "mediaType", "sizeBytes", "sha256"}
        or value["status"] != "accepted"
        or not isinstance(value["format"], str)
        or value["format"] not in _FORMAT_MEDIA_TYPES
        or value["mediaType"] != _FORMAT_MEDIA_TYPES[value["format"]]
        or type(value["sizeBytes"]) is not int
        or not 0 < value["sizeBytes"] <= MAX_DOCUMENT_BYTES
        or not isinstance(value["sha256"], str)
        or len(value["sha256"]) != 64
        or any(char not in "0123456789abcdef" for char in value["sha256"])
    ):
        raise DocumentInspectionError("worker-unavailable")
    return DocumentInspection(value["format"], value["mediaType"], value["sizeBytes"], value["sha256"])


def inspect_document(
    source: BinaryIO,
    *,
    filename: str,
    declared_media_type: str | None = None,
    cancel: Callable[[], bool] | None = None,
) -> DocumentInspection:
    """Return a verdict only from the exact signed, zero-capability worker.

    The trusted caller must supply a verified stream of the encrypted staged
    bytes and compare the returned digest/length before canonical publication.
    """

    if not hasattr(source, "read") or not isinstance(filename, str) or not filename or "\x00" in filename:
        raise DocumentInspectionError("unsupported-format")
    extension = ntpath.splitext(ntpath.basename(filename))[1].casefold()
    if len(extension) > 16 or any(char not in ".abcdefghijklmnopqrstuvwxyz0123456789" for char in extension):
        raise DocumentInspectionError("unsupported-format")
    if declared_media_type is not None and not isinstance(declared_media_type, str):
        raise DocumentInspectionError("unsupported-format")
    if cancel is not None and cancel():
        raise DocumentInspectionError("cancelled")
    nonce = secrets.token_hex(16)

    def prepare_request(_image: Path) -> dict[str, Any]:
        return {
            "protocolVersion": "1.0",
            "jobNonce": nonce,
            "sequence": 0,
            "operation": "inspect-document",
            "extension": extension,
            "declaredMediaType": declared_media_type,
        }

    def dialogue(kernel: Any, stdin: int, stdout: int, request: dict[str, Any]) -> tuple[bytes, int]:
        return _document_dialogue(kernel, stdin, stdout, request, source, cancel)

    try:
        runtime: SignedWorkerRuntime = load_installed_worker_runtime()
        result = connector_launcher._run_signed_worker(
            runtime,
            prepare_request=prepare_request,
            dialogue=dialogue,
            memory_mib=_INSPECTION_MEMORY_MIB,
            wall_seconds=_INSPECTION_WALL_SECONDS,
            cancelled=cancel,
        )
    except (RuntimeInventoryError, GuardianError, win.LPACError) as exc:
        if cancel is not None and cancel():
            raise DocumentInspectionError("cancelled") from None
        if isinstance(exc, win.LPACError) and str(exc) == "lpac-document-oversize":
            raise DocumentInspectionError("oversize") from None
        raise DocumentInspectionError("worker-unavailable") from None
    return _decode_verdict(result.output)
