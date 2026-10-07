"""Parser preference retains the allowed four-logical-processor boundary."""

import ctypes
import os
import struct
import sys
import unittest
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from workers.windows.parser_cpu_affinity import (  # noqa: E402
    _decode_cores,
    _distinct_cores,
    _logical_cores,
    parser_cpu_affinity,
)


class ParserCpuAffinityTests(unittest.TestCase):
    def test_topology_records_preserve_groups_and_reject_truncated_or_unknown_shapes(self):
        def core(mask, group, *, size=48, count=1, relationship=0):
            return struct.pack("<IIBB20sHQH6s", relationship, size, 1, 1, bytes(20), count, mask, group, bytes(6))

        wire = core(3, 0) + core(1, 1)
        self.assertEqual(_decode_cores(wire, 0), [(1, 3)])
        self.assertEqual(_decode_cores(wire, 1), [(1, 1)])
        for invalid in (wire[:-1], core(3, 0, size=0), core(3, 0, count=2), core(3, 0, relationship=4)):
            with self.subTest(wire=invalid), self.assertRaises(ValueError):
                _decode_cores(invalid, 0)

    def test_distinct_smt_cores_and_performance_preference(self):
        cores = [(1, 3), (1, 12), (1, 48), (1, 192), (1, 768), (1, 3072), (0, 4096)]
        self.assertEqual(_distinct_cores(8191, cores), 85)
        self.assertEqual(_distinct_cores(255, [(0, 3), (0, 12), (0, 48), (0, 192)]), 85)
        self.assertEqual(_distinct_cores(255, [(0, 1), (0, 2), (1, 12), (1, 48), (1, 64), (1, 128)]), 212)

    def test_restricted_affinity_and_fewer_available_cores_keep_the_ceiling(self):
        cores = [(1, 3), (1, 12), (1, 48), (1, 192)]
        for allowed in (1, 15, 170, 255, 128, 129):
            with self.subTest(allowed=allowed):
                selected = _distinct_cores(allowed, cores)
                self.assertEqual(selected & ~allowed, 0)
                self.assertEqual(selected.bit_count(), min(4, allowed.bit_count()))
        self.assertEqual(_distinct_cores(15, [(1, 3), (1, 12)]), 15)

    def test_unknown_overlapping_or_incomplete_topology_keeps_previous_fallback(self):
        for cores in ([], [(1, 3)], [(1, 7), (1, 12)], [(True, 15)], [(1, 0)], [(1, 1 << 64)]):
            with (
                self.subTest(cores=cores),
                patch("workers.windows.parser_cpu_affinity._logical_cores", return_value=cores),
            ):
                self.assertEqual(parser_cpu_affinity(object(), 255), 15)
        self.assertEqual(parser_cpu_affinity(object(), 255), 15)
        for allowed in (False, 0, -1, 1 << 64):
            with self.assertRaises(ValueError):
                parser_cpu_affinity(object(), allowed)

    @unittest.skipUnless(os.name == "nt", "Native Windows topology")
    def test_native_selection_is_a_bounded_subset_of_actual_parent_affinity(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetProcessAffinityMask.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t),
        ]
        kernel.GetProcessAffinityMask.restype = wintypes.BOOL
        allowed, system = ctypes.c_size_t(), ctypes.c_size_t()
        self.assertTrue(
            kernel.GetProcessAffinityMask(kernel.GetCurrentProcess(), ctypes.byref(allowed), ctypes.byref(system))
        )
        selected = parser_cpu_affinity(kernel, allowed.value)
        self.assertEqual(selected & ~allowed.value, 0)
        self.assertEqual(selected.bit_count(), min(4, allowed.value.bit_count()))
        eligible = [(efficiency, mask) for efficiency, mask in _logical_cores(kernel) if mask & allowed.value]
        if len(eligible) >= 4:
            self.assertEqual(sum(bool(mask & selected) for _efficiency, mask in eligible), 4)


if __name__ == "__main__":
    unittest.main()
