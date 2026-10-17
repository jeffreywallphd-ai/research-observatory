"""Actual protected Windows close, foreground progress and failure drain."""

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped] # noqa: E402
from research_observatory_core.lexical_index_store import LexicalStoreProblem  # noqa: E402
from research_observatory_core.ports.derivative_keys import DerivativeKeyProblem  # noqa: E402
from research_observatory_core.search import parse_query  # noqa: E402

from tests.search.fixture_support import ProtectedIndexFixture  # noqa: E402
from tests.search.test_derivative_keys import PROJECT  # noqa: E402
from tests.search.test_protected_lexical_store import row  # noqa: E402


class IndexCloseLifetimeTests(ProtectedIndexFixture):
    def test_close_allows_foreground_progress_and_preserves_protected_wal_reopen(self):
        store = self.store(create=True)
        store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
        stop, ready = threading.Event(), threading.Event()
        gaps = []

        def foreground():
            previous = time.perf_counter()
            ready.set()
            while not stop.wait(0.01):
                current = time.perf_counter()
                gaps.append(current - previous)
                previous = current
            gaps.append(time.perf_counter() - previous)

        worker = threading.Thread(target=foreground)
        worker.start()
        self.assertTrue(ready.wait(1))
        try:
            started = time.perf_counter()
            store.close()
            elapsed = time.perf_counter() - started
        finally:
            stop.set()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertLess(max(gaps), 1.8, "close starved the foreground Python thread")
        self.assertLess(elapsed, 1.8, "close exceeded the existing Native response deadline")
        with self.store() as reopened:
            self.assertEqual("wal", reopened._db.execute("PRAGMA journal_mode").fetchone()[0])
            self.assertEqual(1, reopened.checkpoint)
            self.assertEqual((PROJECT,), reopened.match(parse_query("title:cafe"), (row().entry_id,), (PROJECT,)))
        self.assertEqual([store._guard.path.name], [path.name for path in (self.root / "indexes").iterdir()])

    def test_failed_readonly_companion_still_closes_writer_key_and_guards(self):
        store = self.store(create=True)
        store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
        original = sqlcipher.connect
        attempts = []

        def connect(database, *args, **kwargs):
            if "mode=ro" in database:
                attempts.append(database)
                raise OSError("synthetic readonly-open failure")
            return original(database, *args, **kwargs)

        with (
            patch("research_observatory_core.lexical_index_store.sqlcipher.connect", connect),
            self.assertRaises(LexicalStoreProblem),
        ):
            store.close()
        self.assertEqual(1, len(attempts))
        with self.assertRaises(sqlcipher.ProgrammingError):
            store._db.execute("SELECT 1")
        with self.assertRaises(DerivativeKeyProblem):
            store._key.assert_current(self.scope)
        self.assertFalse(store._guard._locked)
        with self.store() as reopened:
            self.assertEqual(1, reopened.checkpoint)
            reopened.integrity_check()

    def test_companion_is_genuinely_readonly_and_remains_inside_all_file_holds(self):
        store = self.store(create=True)
        store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
        original = sqlcipher.connect
        readers, denied = [], []

        class ReadOnlyProbe(sqlcipher.Connection):
            def execute(connection, statement, *args):
                if statement == "PRAGMA query_only=ON":
                    store._guard.check()
                    with self.assertRaises(sqlcipher.OperationalError):
                        super(ReadOnlyProbe, connection).execute("CREATE TABLE forbidden_probe(value)")
                    denied.append(True)
                if statement == "BEGIN":
                    for path in store._guard._files:
                        with self.assertRaises(PermissionError):
                            path.rename(path.with_name(path.name + "-forbidden-move"))
                return super().execute(statement, *args)

        def connect(database, *args, **kwargs):
            if "mode=ro" in database:
                kwargs["factory"] = ReadOnlyProbe
                reader = original(database, *args, **kwargs)
                readers.append(reader)
                return reader
            return original(database, *args, **kwargs)

        with patch("research_observatory_core.lexical_index_store.sqlcipher.connect", connect):
            store.close()
        self.assertEqual([True], denied)
        self.assertEqual(1, len(readers))
        with self.assertRaises(sqlcipher.ProgrammingError):
            readers[0].execute("SELECT 1")
        self.assertFalse(store._guard._locked)

    def test_failed_companion_read_closes_both_consumers_before_releasing_holds(self):
        store = self.store(create=True)
        store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
        original = sqlcipher.connect
        readers = []

        class FailingRead(sqlcipher.Connection):
            def execute(connection, statement, *args):
                if statement.startswith("SELECT singleton"):
                    raise OSError("synthetic companion read failure")
                return super().execute(statement, *args)

            def close(connection):
                store._guard.check()
                store._key.assert_current(self.scope)
                return super().close()

        def connect(database, *args, **kwargs):
            if "mode=ro" in database:
                kwargs["factory"] = FailingRead
                reader = original(database, *args, **kwargs)
                readers.append(reader)
                return reader
            return original(database, *args, **kwargs)

        with (
            patch("research_observatory_core.lexical_index_store.sqlcipher.connect", connect),
            self.assertRaises(LexicalStoreProblem),
        ):
            store.close()
        self.assertEqual(1, len(readers))
        for connection in (store._db, *readers):
            with self.assertRaises(sqlcipher.ProgrammingError):
                connection.execute("SELECT 1")
        self.assertFalse(store._guard._locked)
        with self.assertRaises(DerivativeKeyProblem):
            store._key.assert_current(self.scope)

    def test_revoked_key_does_not_gain_close_only_read_authority(self):
        store = self.store(create=True)
        store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
        self.keys.revoke(self.scope, expected_version=store._key.version)
        with self.assertRaises(LexicalStoreProblem):
            store.close()
        with self.assertRaises(sqlcipher.ProgrammingError):
            store._db.execute("SELECT 1")
        self.assertFalse(store._guard._locked)


if __name__ == "__main__":
    unittest.main()
