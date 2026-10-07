"""A native stderr pipe must not deadlock or retain private library diagnostics."""

import ctypes
import os
import sys
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "services/core-api/src")]
from workers.windows import connector_launcher as parent  # noqa: E402


@unittest.skipUnless(sys.platform == "win32", "Windows anonymous-pipe boundary")
class WorkerStderrTests(unittest.TestCase):
    def check_pipe(self, length, expected):
        import msvcrt

        reader, writer = os.pipe()
        outcome = []
        failures = []

        def write():
            try:
                for _ in range(length // 4096):
                    os.write(writer, b"private-synthetic-marker".ljust(4096, b"x"))
            except OSError:
                failures.append("writer-failed")
            finally:
                os.close(writer)

        function = parent._discard_worker_stderr
        kernel, *_ = parent.win._api()
        writer_thread = threading.Thread(target=write, daemon=True)
        reader_thread = threading.Thread(
            target=lambda: outcome.append(function(kernel, msvcrt.get_osfhandle(reader))), daemon=True
        )
        try:
            reader_thread.start()
            writer_thread.start()
            reader_thread.join(3)
            writer_thread.join(3)
            self.assertFalse(reader_thread.is_alive(), "stderr reader blocked")
            self.assertFalse(writer_thread.is_alive(), "stderr writer blocked")
            self.assertEqual(outcome, [expected])
            self.assertEqual(failures, [])
            self.assertFalse(ctypes.get_last_error() not in {0, 109, 232})
        finally:
            os.close(reader)

    def test_more_than_pipe_capacity_is_discarded_without_content_receipt(self):
        self.check_pipe(128 * 1024, None)

    def test_excessive_stderr_has_only_a_bounded_failure_code(self):
        self.check_pipe(1024 * 1024 + 4096, "lpac-worker-stderr-limit")


if __name__ == "__main__":
    unittest.main()
