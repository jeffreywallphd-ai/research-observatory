"""Select four allowed logical processors without wasting available cores.

Windows topology only informs preference; the caller's allowed mask and the
four-processor ceiling always determine authority. Unavailable/unsupported
topology uses the previous deterministic first-four-bit allocation.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any


def _first_bits(allowed: int, count: int = 4) -> int:
    result = 0
    for _ in range(count):
        if not allowed:
            break
        bit = allowed & -allowed
        result |= bit
        allowed ^= bit
    return result


def _distinct_cores(allowed: int, cores: list[tuple[int, int]]) -> int:
    union = 0
    for efficiency, mask in cores:
        if type(efficiency) is not int or not 0 <= efficiency <= 255 or type(mask) is not int or not 0 < mask < 1 << 64:
            raise ValueError("parser-cpu-topology-invalid")
        if union & mask:
            raise ValueError("parser-cpu-topology-invalid")
        union |= mask
    if not cores or allowed & ~union:
        raise ValueError("parser-cpu-topology-incomplete")
    selected = 0
    for _efficiency, mask in sorted(cores, key=lambda item: (-item[0], item[1] & -item[1])):
        available = mask & allowed
        if available:
            selected |= available & -available
        if selected.bit_count() == 4:
            break
    selected |= _first_bits(allowed & ~selected, 4 - selected.bit_count())
    return selected


def _logical_cores(kernel: Any) -> list[tuple[int, int]]:
    # GetProcessAffinityMask identifies a single process group. A multi-group
    # process cannot safely use a mask from another group as the same mask.
    kernel.GetProcessGroupAffinity.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.WORD),
        ctypes.POINTER(wintypes.WORD),
    ]
    kernel.GetProcessGroupAffinity.restype = wintypes.BOOL
    count = wintypes.WORD(64)
    groups = (wintypes.WORD * 64)()
    if not kernel.GetProcessGroupAffinity(kernel.GetCurrentProcess(), ctypes.byref(count), groups) or count.value != 1:
        raise ValueError("parser-cpu-groups-unsupported")
    group = groups[0]
    kernel.GetLogicalProcessorInformationEx.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetLogicalProcessorInformationEx.restype = wintypes.BOOL
    length = wintypes.DWORD()
    if kernel.GetLogicalProcessorInformationEx(0, None, ctypes.byref(length)) or ctypes.get_last_error() != 122:
        raise ValueError("parser-cpu-topology-unavailable")
    if not 0 < length.value <= 1_048_576:
        raise ValueError("parser-cpu-topology-invalid")
    buffer = ctypes.create_string_buffer(length.value)
    if not kernel.GetLogicalProcessorInformationEx(0, buffer, ctypes.byref(length)) or length.value > len(buffer):
        raise ValueError("parser-cpu-topology-unavailable")
    return _decode_cores(buffer.raw[: length.value], group)


def _decode_cores(wire: bytes, group: int) -> list[tuple[int, int]]:
    cores = []
    offset = 0
    while offset < len(wire):
        if len(wire) - offset < 48:
            raise ValueError("parser-cpu-topology-invalid")
        relationship = int.from_bytes(wire[offset : offset + 4], "little")
        size = int.from_bytes(wire[offset + 4 : offset + 8], "little")
        group_count = int.from_bytes(wire[offset + 30 : offset + 32], "little")
        if relationship != 0 or size != 48 or group_count != 1:
            raise ValueError("parser-cpu-topology-invalid")
        mask = int.from_bytes(wire[offset + 32 : offset + 40], "little")
        observed_group = int.from_bytes(wire[offset + 40 : offset + 42], "little")
        if observed_group == group:
            cores.append((wire[offset + 9], mask))
        offset += size
    return cores


def parser_cpu_affinity(kernel: Any, allowed: int) -> int:
    if type(allowed) is not int or not 0 < allowed < 1 << 64 or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise ValueError("parser-cpu-affinity-invalid")
    try:
        return _distinct_cores(allowed, _logical_cores(kernel))
    except AttributeError, OSError, ValueError:
        return _first_bits(allowed)
