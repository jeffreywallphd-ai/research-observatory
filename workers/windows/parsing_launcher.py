"""Parent-owned source identity and bounded output from the fixed LPAC parser."""

from __future__ import annotations

import ctypes
import hashlib
import os
import secrets
import time
from collections.abc import Callable
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Any, BinaryIO

from . import connector_launcher as parent
from . import lpac_launcher as win
from .parser_worker import MAX_OUTPUT_BYTES, MAX_SOURCE_BYTES
from .protocol import MAX_DOCUMENT_CHUNK, encode_frame
from .runtime_inventory import SignedWorkerRuntime


@contextmanager
def _parser_slot(cancelled: Callable[[], bool] | None):
    """One parser across Core processes in this Windows logon session.

    A mutex has no source bytes. Default security keeps the handle outside the
    inherited worker allowlist; abandoned ownership is recovered after a crash.
    """
    if os.name != "nt":
        raise win.LPACError("lpac-parser-platform-unavailable")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateMutexW(None, False, "Local\\ResearchObservatory.DocumentParser.CPU.v1")
    if not handle:
        raise win.LPACError("lpac-parser-admission-unavailable")
    owned = False
    deadline = time.monotonic() + 900
    try:
        while not owned:
            if cancelled is not None and cancelled():
                raise win.LPACError("lpac-worker-cancelled")
            if time.monotonic() >= deadline:
                raise win.LPACError("lpac-worker-timeout")
            waited = kernel.WaitForSingleObject(handle, 50)
            if waited in (0, 0x80):
                owned = True
            elif waited != 0x102:
                raise win.LPACError("lpac-parser-admission-unavailable")
        yield
    finally:
        if owned:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def parse_document(
    runtime: SignedWorkerRuntime,
    source: BinaryIO,
    *,
    format: str,
    length: int,
    sha256: str,
    cancelled: Callable[[], bool] | None = None,
    operation: str = "parse-document",
    page_index: int | None = None,
) -> parent.WorkerResult:
    with _parser_slot(cancelled):
        return _parse_document(
            runtime,
            source,
            format=format,
            length=length,
            sha256=sha256,
            cancelled=cancelled,
            operation=operation,
            page_index=page_index,
        )


def _parse_document(
    runtime: SignedWorkerRuntime,
    source: BinaryIO,
    *,
    format: str,
    length: int,
    sha256: str,
    cancelled: Callable[[], bool] | None,
    operation: str = "parse-document",
    page_index: int | None = None,
) -> parent.WorkerResult:
    """Only the trusted caller chooses this distinct finite application profile.

    The caller must authorize the original and attempt before invocation and
    before staging/delivery. A worker echo never supplies a persistence receipt.
    """

    if format not in {"pdf", "docx", "jats", "tei", "xml", "html", "txt"} or type(length) is not int:
        raise win.LPACError("lpac-parser-source-invalid")
    if (
        operation not in {"parse-document", "inspect-pdf", "render-pdf-page"}
        or (operation != "parse-document" and format != "pdf")
        or (operation != "render-pdf-page" and page_index is not None)
        or (operation == "render-pdf-page" and (type(page_index) is not int or not 0 <= page_index < 500))
    ):
        raise win.LPACError("lpac-parser-source-invalid")
    if not 0 < length <= MAX_SOURCE_BYTES or len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise win.LPACError("lpac-parser-source-invalid")
    nonce = secrets.token_hex(16)

    def request(_image: Path) -> dict[str, Any]:
        frame = {
            "protocolVersion": "1.0",
            "jobNonce": nonce,
            "sequence": 0,
            "operation": operation,
            "format": format,
            "inputLength": length,
            "inputSha256": sha256,
        }
        if operation == "render-pdf-page":
            frame["pageIndex"] = page_index
        return frame

    def dialogue(kernel: Any, stdin: int, stdout: int, frame: dict[str, Any]) -> tuple[bytes, int]:
        win._write(kernel, stdin, encode_frame(frame))
        observed_length = 0
        digest = hashlib.sha256()
        while True:
            if cancelled is not None and cancelled():
                raise win.LPACError("lpac-worker-cancelled")
            chunk = source.read(MAX_DOCUMENT_CHUNK)
            if not isinstance(chunk, bytes) or len(chunk) > MAX_DOCUMENT_CHUNK:
                raise win.LPACError("lpac-parser-source-invalid")
            if not chunk:
                break
            observed_length += len(chunk)
            if observed_length > length:
                raise win.LPACError("lpac-parser-source-invalid")
            digest.update(chunk)
            parent._write_binary(kernel, stdin, chunk)
        if observed_length != length or digest.hexdigest() != sha256:
            raise win.LPACError("lpac-parser-source-invalid")
        parent._write_binary(kernel, stdin, b"")
        win._write(
            kernel,
            stdin,
            encode_frame({"protocolVersion": "1.0", "jobNonce": nonce, "sequence": 1, "operation": "parse-end"}),
        )
        response = parent._read_control(kernel, stdout, nonce, 2)
        if response.get("operation") == "parse-failure":
            if set(response) != {"protocolVersion", "jobNonce", "sequence", "operation", "code"} or response[
                "code"
            ] not in {
                "parser-failed",
                "parser-memory-limit",
                "parser-assets-unavailable",
                "parser-input-invalid",
                "parser-input-unsupported",
                "parser-resource-limit",
            }:
                raise win.LPACError("lpac-parser-output-invalid")
            raise win.LPACError("lpac-" + response["code"])
        if (
            set(response) != {"protocolVersion", "jobNonce", "sequence", "operation", "outputLength", "outputSha256"}
            or response["operation"] != "parse-result"
            or type(response["outputLength"]) is not int
            or not 0 < response["outputLength"] <= MAX_OUTPUT_BYTES
        ):
            raise win.LPACError("lpac-parser-output-invalid")
        output = bytearray()
        while True:
            size = int.from_bytes(parent._read_exact(kernel, stdout, 4), "big")
            if size > MAX_DOCUMENT_CHUNK or len(output) + size > response["outputLength"]:
                raise win.LPACError("lpac-parser-output-invalid")
            if not size:
                break
            output.extend(parent._read_exact(kernel, stdout, size))
        if len(output) != response["outputLength"] or hashlib.sha256(output).hexdigest() != response["outputSha256"]:
            raise win.LPACError("lpac-parser-output-invalid")
        return bytes(output), 0

    return parent._run_signed_worker(
        runtime,
        prepare_request=request,
        dialogue=dialogue,
        memory_mib=4096,
        wall_seconds=900,
        cancelled=cancelled,
        profile="parser",
    )
