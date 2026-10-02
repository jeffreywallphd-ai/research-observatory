"""Fixed entry point for a packaged, zero-capability Windows LPAC connector.

Only the trusted parent selects and stages ``plugin/connector.py``. The worker
receives bounded input bytes, opaque job identity and scientific operations over
its inherited pipes. It has no listener and no network or filesystem broker.
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO

from workers.windows.protocol import (
    MAX_BINARY_FRAME,
    read_binary_frame,
    read_frame,
    write_binary_frame,
    write_frame,
)

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_OPERATIONS = frozenset({"lookup", "search", "references", "citations", "open-access-locations", "repository-metadata"})
_CALL_KEYS = frozenset({"operation", "identifier", "query", "repositoryId", "cursor", "pageSize", "credentialScope"})


class WorkerProtocolError(ValueError):
    """The private parent/worker protocol was violated."""


def _validate_request(request: dict[str, Any]) -> None:
    if (
        set(request)
        != {
            "protocolVersion",
            "jobNonce",
            "sequence",
            "operation",
            "invocationId",
            "connectorOperation",
            "inputSha256",
            "pluginSha256",
            "inputLength",
        }
        or request["operation"] != "invoke"
    ):
        raise WorkerProtocolError("worker-request-invalid")
    if not isinstance(request["invocationId"], str) or not 0 < len(request["invocationId"]) <= 128:
        raise WorkerProtocolError("worker-invocation-invalid")
    if request["connectorOperation"] not in _OPERATIONS:
        raise WorkerProtocolError("worker-operation-invalid")
    for key in ("inputSha256", "pluginSha256"):
        if not isinstance(request[key], str) or _DIGEST.fullmatch(request[key]) is None:
            raise WorkerProtocolError("worker-digest-invalid")
    if type(request["inputLength"]) is not int or not 0 <= request["inputLength"] <= MAX_BINARY_FRAME:
        raise WorkerProtocolError("worker-input-length-invalid")


def _load_connector(asset_root: Path, expected_sha256: str) -> Callable[..., bytes]:
    entry = asset_root / "plugin" / "connector.py"
    if entry.is_symlink() or entry.is_junction() or not entry.is_file():
        raise WorkerProtocolError("worker-entry-invalid")
    source = entry.read_bytes()
    if len(source) > 16 * 1_048_576 or hashlib.sha256(source).hexdigest() != expected_sha256:
        raise WorkerProtocolError("worker-entry-hash-mismatch")
    package_root = asset_root / "plugin-assets"
    if not package_root.is_dir() or package_root.is_symlink() or package_root.is_junction():
        raise WorkerProtocolError("worker-assets-invalid")
    sys.path.insert(0, str(package_root))
    namespace: dict[str, Any] = {"__name__": "research_observatory_plugin", "__file__": str(entry)}
    exec(compile(source, str(entry), "exec"), namespace)
    invoke = namespace.get("invoke")
    if not callable(invoke):
        raise WorkerProtocolError("worker-entry-invoke-missing")
    return invoke


def run_worker(stdin: BinaryIO, stdout: BinaryIO, *, asset_root: Path) -> None:
    request = read_frame(stdin, expected_nonce=None, expected_sequence=0)
    _validate_request(request)
    input_data = read_binary_frame(stdin)
    if len(input_data) != request["inputLength"] or hashlib.sha256(input_data).hexdigest() != request["inputSha256"]:
        raise WorkerProtocolError("worker-input-hash-mismatch")
    invoke = _load_connector(asset_root, request["pluginSha256"])
    nonce = request["jobNonce"]
    next_sequence = 1

    def broker(call: dict[str, Any]) -> bytes:
        nonlocal next_sequence
        if not isinstance(call, dict) or not 0 < len(call) <= len(_CALL_KEYS) or not set(call) <= _CALL_KEYS:
            raise WorkerProtocolError("worker-broker-call-shape-invalid")
        if next_sequence > 127:
            raise WorkerProtocolError("worker-broker-call-limit")
        write_frame(
            stdout,
            {
                "protocolVersion": "1.0",
                "jobNonce": nonce,
                "sequence": next_sequence,
                "operation": "broker-call",
                "call": call,
            },
        )
        reply = read_frame(stdin, expected_nonce=nonce, expected_sequence=next_sequence + 1)
        if set(reply) != {"protocolVersion", "jobNonce", "sequence", "operation", "responseLength", "responseSha256"}:
            raise WorkerProtocolError("worker-broker-reply-invalid")
        if reply["operation"] != "broker-result" or type(reply["responseLength"]) is not int:
            raise WorkerProtocolError("worker-broker-reply-invalid")
        response = read_binary_frame(stdin)
        if (
            len(response) != reply["responseLength"]
            or not isinstance(reply["responseSha256"], str)
            or hashlib.sha256(response).hexdigest() != reply["responseSha256"]
        ):
            raise WorkerProtocolError("worker-broker-reply-invalid")
        next_sequence += 2
        return response

    output = invoke(input_data, broker, request["connectorOperation"])
    if not isinstance(output, bytes) or len(output) > MAX_BINARY_FRAME:
        raise WorkerProtocolError("worker-output-invalid")
    write_frame(
        stdout,
        {
            "protocolVersion": "1.0",
            "jobNonce": nonce,
            "sequence": next_sequence,
            "operation": "invoke-result",
            "outputLength": len(output),
            "outputSha256": hashlib.sha256(output).hexdigest(),
        },
    )
    write_binary_frame(stdout, output)


def main() -> int:
    asset_root = getattr(sys, "_MEIPASS", None)
    if not isinstance(asset_root, str):
        return 2
    try:
        run_worker(sys.stdin.buffer, sys.stdout.buffer, asset_root=Path(asset_root))
    except BaseException:
        # The parent maps this bounded status to a durable, content-free failure.
        # A plugin exception must never put a traceback or protected bytes on IPC.
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
