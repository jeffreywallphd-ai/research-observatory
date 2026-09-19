"""100k-record generated-source benchmark; never collects the result batch."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
import tracemalloc
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.ingestion.reference_imports import (  # noqa: E402
    ImportLimits,
    ImportSession,
    ImportSource,
)


class RepeatingSource:
    def __init__(self, header: bytes, record: bytes, count: int):
        self.header, self.record, self.count = header, record, count
        self.position = 0
        self.length = len(header) + len(record) * count

    def read(self, size: int = -1) -> bytes:
        if not 0 < size <= 8192:
            raise AssertionError("unbounded input read")
        remaining = min(size, self.length - self.position)
        result = b""
        if self.position < len(self.header):
            result = self.header[self.position : self.position + remaining]
            self.position += len(result)
            remaining -= len(result)
        if remaining:
            offset = (self.position - len(self.header)) % len(self.record)
            repeated = self.record * ((offset + remaining) // len(self.record) + 1)
            result += repeated[offset : offset + remaining]
            self.position += remaining
        return result


class ReferenceImportStreamingTests(unittest.TestCase):
    def test_100k_ris_bibtex_csv_records_with_bounded_peak_memory(self):
        samples = {
            "ris": (b"", b"TY  - JOUR\nTI  - Synthetic\nER  -\n"),
            "bibtex": (b"", b"@article{a,title={Synthetic}}\n"),
            "csv": (b"title,DOI\n", b"Synthetic,10.99999/fixture\n"),
        }
        measurements = []
        for format_name, (header, record) in samples.items():
            digest = hashlib.sha256(header)
            for _ in range(100000):
                digest.update(record)
            source = ImportSource("generated-synthetic", digest.hexdigest())
            for repetition in range(2):
                tracemalloc.start()
                started = time.perf_counter()
                run = ImportSession(
                    RepeatingSource(header, record, 100000), source, format_name, limits=ImportLimits(max_seconds=600)
                )
                count = sum(item.kind == "record" for item in run.records())
                elapsed = time.perf_counter() - started
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                self.assertEqual(100000, count)
                self.assertTrue(run.complete)
                self.assertEqual(0, run.error_count)
                self.assertLess(peak, 16 * 1024 * 1024, "Batch buffering violates the streaming budget")
                measurements.append(
                    {
                        "format": format_name,
                        "repetition": repetition + 1,
                        "records": count,
                        "seconds": round(elapsed, 6),
                        "peakTracedBytes": peak,
                    }
                )
                print(json.dumps(measurements[-1]), flush=True)
        print(
            json.dumps(
                {
                    "fixtureVersion": "synthetic-repeated-metadata-v1",
                    "platform": platform.system(),
                    "architecture": platform.machine(),
                    "processor": platform.processor(),
                    "python": platform.python_version(),
                    "repetitions": 2,
                    "method": "first and immediate repeat in one process; tracemalloc enabled; no OS cold-cache claim",
                    "memoryRegressionCeilingBytes": 16 * 1024 * 1024,
                    "latency": "descriptive baseline, not a release latency claim",
                    "measurements": measurements,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    unittest.main()
