"""Bounded request ownership and cancellation; no transport qualification claim."""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from research_observatory_core.document_viewer_ranges import (
    DocumentViewerRangePool,
    ViewerRangeKey,
    ViewerRangeProblem,
)
from research_observatory_core.ports.object_store import ObjectReadCancelled


class ViewerRangeAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.pool = DocumentViewerRangePool()
        self.executor = ThreadPoolExecutor(max_workers=12)
        self.addCleanup(self.executor.shutdown, wait=True, cancel_futures=True)
        self.addCleanup(self.pool.close)
        self.key = ViewerRangeKey("project", "session", "authority", "source", "attachment", "revision", 0, 16)

    def request(self, key, identity, read, stop=lambda: False):
        return self.executor.submit(self.pool.read, key, identity, read, cancellation_requested=stop)

    def wait_for_requests(self, count):
        deadline = time.monotonic() + 2
        while self.pool.pending_count(self.key.project_id) != count:
            if time.monotonic() >= deadline:
                self.fail("request registration did not reach the bounded test state")
            threading.Event().wait(0.005)

    def held_read(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []

        def read(stopped):
            calls.append(1)
            entered.set()
            while not release.wait(0.005):
                if stopped():
                    raise ObjectReadCancelled()
            if stopped():
                raise ObjectReadCancelled()
            return b"abcdefghijklmnop"

        return read, entered, release, calls

    def test_duplicate_ranges_share_one_read_but_one_cancellation_cannot_cancel_the_other(self):
        read, entered, release, calls = self.held_read()
        first = self.request(self.key, "one", read)
        self.assertTrue(entered.wait(2))
        second = self.request(self.key, "two", read)
        self.wait_for_requests(2)
        self.assertFalse(self.pool.cancel("other-project", self.key.session_id, "one"))
        self.assertFalse(self.pool.cancel(self.key.project_id, "other-session", "one"))
        self.assertTrue(self.pool.cancel(self.key.project_id, self.key.session_id, "one"))
        with self.assertRaises(ObjectReadCancelled):
            first.result(timeout=1)
        release.set()
        self.assertEqual(b"abcdefghijklmnop", second.result(timeout=2))
        self.assertEqual(1, len(calls))

    def test_distinct_authorities_sessions_and_copies_never_coalesce(self):
        read, entered, release, calls = self.held_read()
        first = self.request(self.key, "one", read)
        self.assertTrue(entered.wait(2))
        variants = (
            replace(self.key, authority_sha256="other-authority"),
            replace(self.key, session_id="other-session"),
            replace(self.key, attachment_id="other-copy"),
            replace(self.key, document_revision_id="other-revision"),
        )
        followers = [self.request(key, f"next-{index}", read) for index, key in enumerate(variants)]
        self.wait_for_requests(5)
        release.set()
        for future in (first, *followers):
            self.assertEqual(b"abcdefghijklmnop", future.result(timeout=2))
        self.assertEqual(5, len(calls))

    def test_only_eight_requests_can_wait_and_cancelled_queued_work_never_reads(self):
        read, entered, release, calls = self.held_read()
        active = self.request(self.key, "active", read)
        self.assertTrue(entered.wait(2))
        queued = []
        for index in range(8):
            key = replace(self.key, start=16 * (index + 1), end=16 * (index + 2))
            queued.append(self.request(key, f"queued-{index}", read))
        self.wait_for_requests(9)
        with self.assertRaisesRegex(ViewerRangeProblem, "queue-full"):
            self.pool.read(self.key, "overflow", read, cancellation_requested=lambda: False)
        self.assertTrue(self.pool.cancel(self.key.project_id, self.key.session_id, "queued-0"))
        with self.assertRaises(ObjectReadCancelled):
            queued[0].result(timeout=1)
        release.set()
        active.result(timeout=2)
        for future in queued[1:]:
            future.result(timeout=2)
        self.assertEqual(8, len(calls))

    def test_all_cancelled_followers_stop_owned_read_and_fresh_retry_is_independent(self):
        read, entered, _, calls = self.held_read()
        stopped = threading.Event()
        first = self.request(self.key, "one", read, stopped.is_set)
        self.assertTrue(entered.wait(2))
        second = self.request(self.key, "two", read, stopped.is_set)
        self.wait_for_requests(2)
        stopped.set()
        for future in (first, second):
            with self.assertRaises(ObjectReadCancelled):
                future.result(timeout=1)
        self.assertTrue(self.pool.drain(timeout=1))
        self.assertEqual(b"abcdefghijklmnop", self.pool.read(self.key, "retry", lambda _: b"abcdefghijklmnop"))
        self.assertEqual(1, len(calls))

    def test_project_without_an_active_read_can_queue_only_eight_requests(self):
        read, entered, release, _ = self.held_read()
        active = self.request(replace(self.key, project_id="other-project"), "other", read)
        self.assertTrue(entered.wait(2))
        queued = [self.request(self.key, f"queued-{index}", read) for index in range(8)]
        self.wait_for_requests(8)
        with self.assertRaisesRegex(ViewerRangeProblem, "queue-full"):
            self.pool.read(self.key, "overflow", read)
        release.set()
        for future in (active, *queued):
            future.result(timeout=2)

    def test_reused_in_flight_request_id_and_oversize_output_fail_closed(self):
        read, entered, release, _ = self.held_read()
        active = self.request(self.key, "one", read)
        self.assertTrue(entered.wait(2))
        with self.assertRaisesRegex(ViewerRangeProblem, "request-conflict"):
            self.pool.read(replace(self.key, start=16, end=32), "one", read)
        release.set()
        active.result(timeout=2)
        with self.assertRaisesRegex(ViewerRangeProblem, "response-invalid"):
            self.pool.read(self.key, "bad", lambda _: b"wrong-length")

    def test_stop_failure_and_close_deny_queued_and_active_delivery(self):
        read, entered, _, _ = self.held_read()
        active = self.request(self.key, "one", read)
        self.assertTrue(entered.wait(2))
        queued = self.request(replace(self.key, start=16, end=32), "two", read)
        self.wait_for_requests(2)
        self.assertTrue(self.pool.close(timeout=1))
        for future in (active, queued):
            with self.assertRaises(ObjectReadCancelled):
                future.result(timeout=1)
        with self.assertRaises(ObjectReadCancelled):
            self.pool.read(self.key, "closed", lambda _: b"abcdefghijklmnop")

        pool = DocumentViewerRangePool()
        self.addCleanup(pool.close)

        def unavailable():
            raise OSError("unavailable synthetic stop signal")

        with self.assertRaises(ObjectReadCancelled):
            pool.read(self.key, "failed-stop", lambda _: b"abcdefghijklmnop", cancellation_requested=unavailable)


if __name__ == "__main__":
    unittest.main(verbosity=2)
