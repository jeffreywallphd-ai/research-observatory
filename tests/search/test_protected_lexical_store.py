"""Actual SQLCipher FTS; synthetic rows/key doubles are not Native/DPAPI proof."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.derivative_keys import VaultDerivativeKeyProvider  # noqa: E402
from research_observatory_core.lexical_index_io import IndexPathProblem, assert_retired_absent  # noqa: E402
from research_observatory_core.lexical_index_store import (  # noqa: E402
    IndexRow,
    LexicalIndexCancelled,
    LexicalStoreProblem,
    ProtectedLexicalStore,
    recover_retired_generation,
)
from research_observatory_core.ports.derivative_keys import DerivativeKeyScope, DerivativePurpose  # noqa: E402
from research_observatory_core.search import parse_query  # noqa: E402

from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402
from tests.search.test_derivative_keys import GENERATION, PROJECT, MemoryVault  # noqa: E402

PRIVATE = "SYNTHETIC_PRIVATE_INDEX_SENTINEL_café_7614"


def row(item=PROJECT, text=PRIVATE, **changes):
    return replace(
        IndexRow(
            entry_id=hashlib.sha256(item.encode()).hexdigest(),
            item_id=item,
            work_id=PROJECT,
            work_revision_id=PROJECT,
            source_revision_id=PROJECT,
            authority_sha256="a" * 64,
            title=text,
            year=2024,
        ),
        **changes,
    )


class ProtectedLexicalStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "indexes").mkdir()
        self.canonical = InMemoryDatabaseKeyProvider()
        with self.canonical.active_key(PROJECT, create=True) as key:
            version = key.version
        self.scope = DerivativeKeyScope(PROJECT, GENERATION, DerivativePurpose.LEXICAL, version, "a" * 64)
        self.vault = MemoryVault()
        self.keys = VaultDerivativeKeyProvider(self.vault, profile_id="fixture", database_keys=self.canonical)

    def store(self, create=False):
        return ProtectedLexicalStore(self.root, self.scope, self.keys, create=create)

    def test_encrypted_real_fts_update_remove_reopen_and_same_mirror_integrity(self):
        with self.store(create=True) as store:
            self.assertEqual(2, store.connection_profile()["temp_store"])
            self.assertEqual(0, store.connection_profile()["trusted_schema"])
            store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
            self.assertEqual((PROJECT,), store.match(parse_query("title:cafe"), (row().entry_id,), (PROJECT,)))
            self.assertEqual((), store.match(parse_query("cafe"), (), (PROJECT,)))
            self.assertEqual((PROJECT,), store.match(parse_query("NOT cafe"), (), (PROJECT,)))
            store.integrity_check()
            store.apply((row(text="replacement"),), (), expected_checkpoint=1, checkpoint=2)
            self.assertEqual((), store.match(parse_query("cafe"), (row().entry_id,), (PROJECT,)))
            self.assertEqual((PROJECT,), store.match(parse_query("replacement"), (row().entry_id,), (PROJECT,)))
            self.assertFalse(any(PRIVATE.encode() in file.read_bytes() for file in (self.root / "indexes").iterdir()))
        with self.store() as store:
            self.assertEqual(2, store.checkpoint)
            self.assertEqual((PROJECT,), store.match(parse_query("replacement"), (row().entry_id,), (PROJECT,)))
            store.apply((), (row().entry_id,), expected_checkpoint=2, checkpoint=3)
            store.integrity_check()
            self.assertEqual((), store.match(parse_query("replacement"), (row().entry_id,), (PROJECT,)))
        self.assertEqual(["lexical-" + GENERATION + ".sqlite3"], [f.name for f in (self.root / "indexes").iterdir()])

    def test_checkpoint_cas_and_transaction_failure_do_not_advance_or_lose_old_rows(self):
        with self.store(create=True) as store:
            store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
            with self.assertRaises(LexicalStoreProblem):
                store.apply((row(text="replacement"),), (), expected_checkpoint=0, checkpoint=2)
            self.assertEqual(1, store.checkpoint)
            self.assertEqual((PROJECT,), store.match(parse_query("cafe"), (row().entry_id,), (PROJECT,)))

    def test_single_leaf_returns_one_item_for_multiple_permitted_rows(self):
        first = row(text="alpha")
        second = replace(first, entry_id="b" * 64, source_revision_id=GENERATION)
        entries = (first.entry_id, second.entry_id)
        with self.store(create=True) as store:
            store.apply((first, second), (), expected_checkpoint=0, checkpoint=1)
            for query in ("alpha", "title:alpha", "year:2024"):
                with self.subTest(query=query):
                    self.assertEqual((PROJECT,), store.match(parse_query(query), entries, (PROJECT,)))
                    self.assertEqual(
                        store.match(parse_query(query + " OR " + query), entries, (PROJECT,)),
                        store.match(parse_query(query), entries, (PROJECT,)),
                    )

    def test_ancestor_close_failure_releases_the_generation_mutex(self):
        store = self.store(create=True)
        guard = store._guard
        assert guard is not None
        ancestors = guard._ancestors
        ancestors.close()

        class FailedAncestors:
            def close(self):
                raise OSError("synthetic ancestor-close failure")

        guard._ancestors = FailedAncestors()
        try:
            with self.assertRaises(LexicalStoreProblem):
                store.close()
            acquired = []

            def another_reader():
                ready = guard._lock.acquire(timeout=0.3)
                acquired.append(ready)
                if ready:
                    guard._lock.release()

            thread = threading.Thread(target=another_reader)
            thread.start()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual([True], acquired)
        finally:
            guard._ancestors = ancestors
            guard.close(clean_sidecars=False)

    def test_bootstrap_refuses_each_existing_role_without_adopting_or_removing_it(self):
        path = self.root / "indexes" / ("lexical-" + GENERATION + ".sqlite3")
        for role in ("", "-wal", "-shm", "-journal"):
            with self.subTest(role=role):
                unknown = path.with_name(path.name + role)
                unknown.write_bytes(b"synthetic preexisting unowned bytes")
                identity = unknown.stat().st_ino
                try:
                    with self.assertRaises(LexicalStoreProblem):
                        self.store(create=True)
                    self.assertEqual([unknown], list(path.parent.iterdir()))
                    self.assertEqual(identity, unknown.stat().st_ino)
                    self.assertEqual(b"synthetic preexisting unowned bytes", unknown.read_bytes())
                finally:
                    unknown.unlink()

    def test_bootstrap_handoff_refuses_substitution_before_sqlcipher_open(self):
        path = self.root / "indexes" / ("lexical-" + GENERATION + ".sqlite3")
        moved = path.with_name(path.name + "-synthetic-moved")
        observed = []

        def substitute(name):
            if name == "retained--journal":
                path.rename(moved)
                path.write_bytes(b"synthetic unowned replacement")
                observed.append(path.stat().st_ino)

        with (
            patch("research_observatory_core.lexical_index_io._bootstrap_step", side_effect=substitute),
            patch("research_observatory_core.lexical_index_store.sqlcipher.connect") as connect,
            self.assertRaises(LexicalStoreProblem),
        ):
            self.store(create=True)
        connect.assert_not_called()
        self.assertEqual([path.stat().st_ino], observed)
        self.assertEqual(b"synthetic unowned replacement", path.read_bytes())
        self.assertEqual(b"", moved.read_bytes())

    def test_complete_projection_preserves_phrase_across_long_discarded_punctuation(self):
        text = "alpha " + "!" * 70000 + " beta"
        value = row(
            text="",
            full_text=text,
            document_revision_id=PROJECT,
            element_id=PROJECT,
            projection_id=PROJECT,
            normalized_start=0,
            normalized_end=len(text),
        )
        with self.store(create=True) as store:
            store.stage((value,), ())
            store.finish_build(1)
            self.assertEqual(
                (PROJECT,), store.match(parse_query('full-text:"alpha beta"'), (value.entry_id,), (PROJECT,))
            )

    def test_complete_projection_larger_than_update_batch_stages_atomically(self):
        text = "alpha " + "!" * (6 * 1024 * 1024) + " beta"
        value = row(
            text="",
            full_text=text,
            document_revision_id=PROJECT,
            element_id=PROJECT,
            projection_id=PROJECT,
            normalized_start=0,
            normalized_end=len(text),
        )
        with self.store(create=True) as store:
            store.stage((value,), ())
            self.assertFalse(store.sealed)
            store.finish_build(1)
            self.assertEqual(
                (PROJECT,), store.match(parse_query('full-text:"alpha beta"'), (value.entry_id,), (PROJECT,))
            )
            with self.assertRaises(LexicalStoreProblem):
                store.apply((value,), (), expected_checkpoint=1, checkpoint=2)
            self.assertEqual(1, store.checkpoint)
            store.integrity_check()

    def test_shadow_chunks_remain_unreadable_until_sealed_and_resume_idempotently(self):
        with self.store(create=True) as store:
            store.stage((row(),), ())
            with self.assertRaises(LexicalStoreProblem):
                store.match(parse_query("cafe"), (row().entry_id,), (PROJECT,))
        with self.store() as store:
            self.assertEqual(0, store.checkpoint)
            self.assertEqual((row().entry_id,), store.entry_ids(PROJECT))
            store.stage((row(),), ())
            store.finish_build(4)
            self.assertEqual(1, store.projection().entry_count)
            self.assertEqual((PROJECT,), store.match(parse_query("cafe"), (row().entry_id,), (PROJECT,)))
            with self.assertRaises(LexicalStoreProblem):
                store.stage((row(text="unapproved late shadow write"),), ())

    def test_wrong_manifest_scope_key_and_preexisting_redirect_fail_closed(self):
        with self.store(create=True):
            pass
        for scope in (replace(self.scope, lifecycle_sha256="b" * 64), replace(self.scope, project_id=GENERATION)):
            with (
                self.assertRaises(LexicalStoreProblem),
                ProtectedLexicalStore(self.root, scope, self.keys, create=False),
            ):
                pass
        with self.assertRaises(LexicalStoreProblem), self.store(create=True):
            pass
        # Same-directory hardlink is sufficient to prove link-count denial;
        # actual Windows junction/changed-volume tests belong to principal proof.
        database = self.root / "indexes" / ("lexical-" + GENERATION + ".sqlite3")
        (self.root / "alias.sqlite3").hardlink_to(database)
        with self.assertRaises(LexicalStoreProblem), self.store():
            pass

    def test_integrity_checks_actual_fts_tokens_against_mirror(self):
        with self.store(create=True) as store:
            value = row()
            store.apply((value,), (), expected_checkpoint=0, checkpoint=1)
            store._db.execute(
                "INSERT INTO search_fts(search_fts,rowid,title,abstract,full_text,authors,venue,identifiers,tags,"
                "decisions) "
                "SELECT 'delete',rowid,title,abstract,full_text,authors,venue,identifiers,tags,decisions FROM "
                "search_rows"
            )
            self.assertEqual(1, store._db.execute("SELECT count(*) FROM search_rows").fetchone()[0])
            with self.assertRaises(LexicalStoreProblem):
                store.integrity_check()

    def test_existing_rollback_journal_is_rejected_before_open(self):
        journal = self.root / "indexes" / ("lexical-" + GENERATION + ".sqlite3-journal")
        journal.write_bytes(b"synthetic unowned journal")
        with self.assertRaises(LexicalStoreProblem), self.store(create=True):
            pass
        self.assertEqual(b"synthetic unowned journal", journal.read_bytes())

    def test_preexisting_hardlinked_wal_is_preserved_and_rejected(self):
        with self.store(create=True) as store:
            store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
        outside = self.root / "synthetic-unowned-sidecar"
        outside.write_bytes(b"synthetic unowned bytes")
        wal = self.root / "indexes" / ("lexical-" + GENERATION + ".sqlite3-wal")
        wal.hardlink_to(outside)
        with self.assertRaises(LexicalStoreProblem):
            self.store()
        self.assertEqual(b"synthetic unowned bytes", outside.read_bytes())
        self.assertEqual(outside.stat().st_ino, wal.stat().st_ino)

    @unittest.skipUnless(os.name == "nt", "W3 actual Windows junction boundary")
    def test_actual_redirected_indexes_and_dangling_retired_names_are_denied(self):
        indexes = self.root / "indexes"
        outside = self.root / "synthetic-other-directory"
        outside.mkdir()
        self.assertEqual([], list(indexes.iterdir()))
        indexes.rmdir()
        result = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(indexes), str(outside)],
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(0, result.returncode, "owned synthetic junction creation failed")
        try:
            self.assertTrue(os.path.isjunction(indexes))
            with self.assertRaises(LexicalStoreProblem):
                self.store(create=True)
            self.assertEqual([], list(outside.iterdir()))
        finally:
            if os.path.isjunction(indexes):
                os.rmdir(indexes)
            indexes.mkdir()
        for suffix in ("", "-wal"):
            path = indexes / ("lexical-" + GENERATION + ".sqlite3" + suffix)
            result = subprocess.run(
                ["cmd", "/d", "/c", "mklink", "/J", str(path), str(self.root / "synthetic-missing-target")],
                capture_output=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(0, result.returncode, "owned synthetic dangling junction creation failed")
            try:
                with self.assertRaises(IndexPathProblem):
                    assert_retired_absent(self.root, GENERATION)
                self.assertTrue(os.path.isjunction(path))
            finally:
                if os.path.isjunction(path):
                    os.rmdir(path)

    def test_retired_recovery_authenticates_before_io_and_has_no_search_commands(self):
        with self.store(create=True) as store:
            store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
            identity = store.file_identity
        with self.keys.lease(self.scope, create=False) as key:
            version = key.version
        with self.canonical.staged_rekey(PROJECT, "2" * 32, create=True):
            pass
        self.canonical.activate_rekey(PROJECT, "2" * 32, expected_active_version=self.scope.canonical_key_version)
        allowed = True

        def authorize(actual):
            if not allowed or actual != identity:
                raise LexicalStoreProblem("synthetic retired ownership denied")

        path = self.root / "indexes" / ("lexical-" + GENERATION + ".sqlite3")
        before = path.read_bytes()
        with self.assertRaises(LexicalStoreProblem):
            recover_retired_generation(self.root, self.scope, self.keys, expected_version="0" * 32, authorize=authorize)
        self.assertEqual(before, path.read_bytes())
        self.assertFalse(any(path.parent.glob(path.name + "-*")))
        with ProtectedLexicalStore(self.root, self.scope, self.keys, _retirement=(version, authorize)) as recovered:
            for action in (
                lambda: recovered.match(parse_query("cafe"), (row().entry_id,), (PROJECT,)),
                recovered.projection,
                lambda: recovered.entry_ids(PROJECT),
                lambda: recovered.item_matches(PROJECT, (row(),)),
                lambda: recovered.stage((), ()),
                lambda: recovered.finish_build(1),
                lambda: recovered.apply((), (), expected_checkpoint=1, checkpoint=2),
            ):
                with self.subTest(action=action), self.assertRaises(LexicalStoreProblem):
                    action()
            recovered.integrity_check()
            allowed = False
            with self.assertRaises(LexicalStoreProblem):
                recovered.integrity_check()
            allowed = True
        recovery: Callable[..., object] = recover_retired_generation
        self.assertIsNone(recovery(self.root, self.scope, self.keys, expected_version=version, authorize=authorize))
        allowed = False
        before = path.read_bytes()
        with self.assertRaises(LexicalStoreProblem):
            recover_retired_generation(self.root, self.scope, self.keys, expected_version=version, authorize=authorize)
        self.assertEqual(before, path.read_bytes())
        self.assertFalse(any(path.parent.glob(path.name + "-*")))

    def test_owned_child_crash_replays_populated_encrypted_wal(self):
        with self.store(create=True) as store:
            store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
        payload = {
            "root": str(self.root),
            "scope": asdict(self.scope),
            "canonicalMaterial": list(self.canonical.active_material_for_test(PROJECT)),
            "records": [
                {"reference": asdict(reference), "version": record.version, "material": list(material)}
                for reference, (record, material) in self.vault.values.items()
            ],
        }
        env = os.environ.copy()
        env.update({name: str(self.root) for name in ("TEMP", "TMP", "TMPDIR", "SQLITE_TMPDIR")})
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tests/search/lexical_crash_child.py")],
            cwd=self.root,
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=45,
            env=env,
        )
        self.assertEqual(73, result.returncode, result.stderr.decode(errors="replace"))
        wal = self.root / "indexes" / ("lexical-" + GENERATION + ".sqlite3-wal")
        self.assertGreater(wal.stat().st_size, 0)
        self.assertNotIn(b"synthetic crash replacement", wal.read_bytes())
        with self.store() as store:
            self.assertEqual(2, store.checkpoint)
            store.integrity_check()
            self.assertEqual((PROJECT,), store.match(parse_query("replacement"), (row().entry_id,), (PROJECT,)))
            self.assertEqual((), store.match(parse_query("cafe"), (row().entry_id,), (PROJECT,)))

    def test_cancellation_and_batch_byte_limit_preserve_committed_checkpoint(self):
        cancelled = False
        with ProtectedLexicalStore(self.root, self.scope, self.keys, create=True, cancelled=lambda: cancelled) as store:
            store.apply((row(),), (), expected_checkpoint=0, checkpoint=1)
            cancelled = True
            with self.assertRaises(LexicalIndexCancelled):
                store.apply((row(text="late replacement"),), (), expected_checkpoint=1, checkpoint=2)
            cancelled = False
            self.assertEqual(1, store.checkpoint)
            self.assertEqual((PROJECT,), store.match(parse_query("cafe"), (row().entry_id,), (PROJECT,)))
            too_large = tuple(
                row(entry_id=hashlib.sha256(str(i).encode()).hexdigest(), text="x" * 1_048_576) for i in range(5)
            )
            with self.assertRaises(LexicalStoreProblem):
                store.apply(too_large, (), expected_checkpoint=1, checkpoint=2)
            self.assertEqual(1, store.checkpoint)


if __name__ == "__main__":
    unittest.main()
