"""Bounded private-pipe control frames for the Windows isolated worker."""

from __future__ import annotations

import json
import re
from typing import Any, BinaryIO

MAX_CONTROL_FRAME = 1_048_576
MAX_BINARY_FRAME = 10 * 1_048_576


class FrameError(ValueError):
    """A malformed or unauthorized control frame."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrameError("control-frame-duplicate-key")
        result[key] = value
    return result


def encode_frame(value: dict[str, Any]) -> bytes:
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if not 0 < len(raw) <= MAX_CONTROL_FRAME:
        raise FrameError("control-frame-length-invalid")
    return len(raw).to_bytes(4, "big") + raw


def decode_frame(data: bytes, *, expected_nonce: str | None, expected_sequence: int) -> dict[str, Any]:
    if len(data) < 4:
        raise FrameError("control-frame-length-missing")
    length = int.from_bytes(data[:4], "big")
    if not 0 < length <= MAX_CONTROL_FRAME or len(data) != 4 + length:
        raise FrameError("control-frame-length-invalid")
    try:
        value = json.loads(data[4:].decode("utf-8"), object_pairs_hook=_unique_object)
    except FrameError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise FrameError("control-frame-json-invalid") from exc
    if not isinstance(value, dict) or value.get("protocolVersion") != "1.0":
        raise FrameError("control-frame-version-invalid")
    nonce = value.get("jobNonce")
    if not isinstance(nonce, str) or re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        raise FrameError("control-frame-nonce-invalid")
    if expected_nonce is not None and nonce != expected_nonce:
        raise FrameError("control-frame-nonce-mismatch")
    if type(value.get("sequence")) is not int or value["sequence"] != expected_sequence:
        raise FrameError("control-frame-sequence-mismatch")
    if not isinstance(value.get("operation"), str) or not value["operation"]:
        raise FrameError("control-frame-operation-invalid")
    return value


def read_frame(stream: BinaryIO, *, expected_nonce: str | None, expected_sequence: int) -> dict[str, Any]:
    prefix = stream.read(4)
    if len(prefix) != 4:
        raise FrameError("control-frame-length-missing")
    length = int.from_bytes(prefix, "big")
    if not 0 < length <= MAX_CONTROL_FRAME:
        raise FrameError("control-frame-length-invalid")
    payload = stream.read(length)
    return decode_frame(prefix + payload, expected_nonce=expected_nonce, expected_sequence=expected_sequence)


def write_frame(stream: BinaryIO, value: dict[str, Any]) -> None:
    stream.write(encode_frame(value))
    stream.flush()


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise FrameError("binary-frame-truncated")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_binary_frame(stream: BinaryIO) -> bytes:
    prefix = _read_exact(stream, 4)
    length = int.from_bytes(prefix, "big")
    if length > MAX_BINARY_FRAME:
        raise FrameError("binary-frame-length-invalid")
    return _read_exact(stream, length)


def write_binary_frame(stream: BinaryIO, value: bytes) -> None:
    if not isinstance(value, bytes) or len(value) > MAX_BINARY_FRAME:
        raise FrameError("binary-frame-length-invalid")
    stream.write(len(value).to_bytes(4, "big"))
    stream.write(value)
    stream.flush()
