"""Project action order must not let sequential viewer operations starve writers."""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from research_observatory_core.project_action_mutex import FairProjectActionMutex


class ViewerMetadataFairnessTests(unittest.TestCase):
    def test_waiting_metadata_action_enters_before_the_next_viewer_action(self):
        mutex = FairProjectActionMutex()
        order = []
        ready, release = threading.Event(), threading.Event()
        with ThreadPoolExecutor(max_workers=2) as executor:

            def writer():
                ready.set()
                with mutex:
                    order.append("metadata")

            def reads():
                # Acquiring twice checks existing reentrant project actions.
                with mutex, mutex:
                    order.append("range-one")
                    release.wait(2)
                with mutex:
                    order.append("range-two")

            active = executor.submit(reads)
            deadline = time.monotonic() + 2
            while not order:
                self.assertLess(time.monotonic(), deadline)
                threading.Event().wait(0.005)
            metadata = executor.submit(writer)
            self.assertTrue(ready.wait(2))
            while mutex.waiting_count() != 1:
                self.assertLess(time.monotonic(), deadline)
                threading.Event().wait(0.005)
            release.set()
            active.result(timeout=2)
            metadata.result(timeout=2)
        self.assertEqual(["range-one", "metadata", "range-two"], order)

    def test_exception_releases_owner_and_non_owner_cannot_release_it(self):
        mutex = FairProjectActionMutex()
        with self.assertRaises(ValueError), mutex:
            raise ValueError("synthetic action failure")
        with mutex, ThreadPoolExecutor(max_workers=1) as executor:
            failed_release = executor.submit(mutex.__exit__, None, None, None)
            with self.assertRaises(RuntimeError):
                failed_release.result(timeout=2)
        with mutex:
            self.assertEqual(0, mutex.waiting_count())


if __name__ == "__main__":
    unittest.main(verbosity=2)
