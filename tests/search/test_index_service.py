"""Core index commands without a UI; protected DB/FTS, synthetic Native fixture."""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core import storage  # noqa: E402
from research_observatory_core.corpus.membership import CorpusDecision  # noqa: E402
from research_observatory_core.derivative_keys import VaultDerivativeKeyProvider  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.lexical_index_repository import (  # noqa: E402
    CoreLexicalIndexService,
    IndexCleanupPending,
    IndexServiceProblem,
)
from research_observatory_core.lexical_index_store import ProtectedLexicalStore  # noqa: E402
from research_observatory_core.parsing.contracts import TextProjection  # noqa: E402
from research_observatory_core.search import parse_query  # noqa: E402

from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402
from tests.search import test_index_sources as fixtures  # noqa: E402
from tests.search.test_derivative_keys import MemoryVault  # noqa: E402


class IndexServiceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.IndexSourceTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.canonical = storage._database_protection_configuration().provider
        assert self.canonical is not None
        self.vault = MemoryVault()
        self.keys = VaultDerivativeKeyProvider(self.vault, profile_id="fixture", database_keys=self.canonical)
        self.service = CoreLexicalIndexService(self.f.sources, self.keys, self.canonical)
        self.addCleanup(self.service.close)
        self.subject = self.f.sources.metadata_subject(self.f.corpus.source)
        self.grant = self.f.permit(self.subject, corpus_membership=True)

    def decide(self, item, command, value):
        actor = self.f.corpus.actor

        def build(current):
            return CorpusDecision(
                decision_id=new_uuid_v7(),
                project_id=current.project_id,
                item_id=current.item_id,
                previous_revision_id=current.revision_id,
                next_revision_id=new_uuid_v7(),
                dimension="membership",
                command=command,
                previous_value=current.membership,
                next_value=value,
                previous_decision_revision_id=current.decision_revision_id,
                actor_id=actor.actor_id,
                reason_code="synthetic-index-regression",
                protocol_revision_id=actor.intent_revision_id,
                evidence_revision_ids=(self.f.corpus.source.source_revision_id,),
                occurred_at=actor.occurred_at,
            )

        return self.f.corpus.repository.decide(
            item.item_id,
            expected_revision_id=item.revision_id,
            command_id=new_uuid_v7(),
            command_sha256="e" * 64,
            actor=actor,
            build=build,
        )

    def test_committed_membership_changes_update_same_generation_and_withdrawal_removes_text(self):
        first = self.service.rebuild()
        included = self.decide(self.f.item, "include", "included")
        updated = self.service.synchronize()
        self.assertEqual(first.generation_id, updated.generation_id)
        self.assertGreater(updated.checkpoint, first.checkpoint)
        self.assertEqual((included.item_id,), self.service.match(parse_query("decisions:included")))
        self.decide(included, "withdraw", "withdrawn")
        self.assertEqual((), self.service.match(parse_query("identifiers:synthetic")))
        removed = self.service.synchronize()
        self.assertEqual(first.generation_id, removed.generation_id)
        self.assertEqual(0, removed.entry_count)

    def test_private_commit_interruption_retries_after_an_additional_source_change(self):
        first = self.service.rebuild()
        included = self.decide(self.f.item, "include", "included")

        def interrupt(name):
            if name == "incremental-derivative-committed":
                raise RuntimeError("synthetic acknowledgement interruption")

        with (
            patch("research_observatory_core.lexical_index_repository._index_step", side_effect=interrupt),
            self.assertRaises(IndexServiceProblem),
        ):
            self.service.synchronize()
        selected = self.service.catalog.selected()
        assert selected is not None
        self.assertEqual(first.checkpoint, selected.checkpoint)
        with self.assertRaises(IndexServiceProblem):
            self.service.match(parse_query("identifiers:synthetic"))
        recovered = self.service.synchronize()
        self.assertGreater(recovered.checkpoint, first.checkpoint)
        self.assertEqual((included.item_id,), self.service.match(parse_query("decisions:included")))
        self.decide(included, "withdraw", "withdrawn")
        with (
            patch("research_observatory_core.lexical_index_repository._index_step", side_effect=interrupt),
            self.assertRaises(IndexServiceProblem),
        ):
            self.service.synchronize()

        # A new lawful item arrives after the private removal, before its
        # canonical acknowledgement. Recovery must use the new source head.
        def build():
            item, path = self.f.corpus._build_item()
            return item.model_copy(update={"work_revision_id": self.f.attachments.work_revision_id}), path

        second = self.f.corpus._create(build=build)
        recovered = self.service.synchronize()
        self.assertEqual(self.service.catalog.watermark(), recovered.checkpoint)
        self.assertEqual((second.item_id,), self.service.match(parse_query("identifiers:synthetic")))

    def test_idle_writer_expiry_and_reopened_service_reacquire_fresh_fences(self):
        now = datetime.now(UTC)
        self.service.catalog.now = lambda: now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        first = self.service.rebuild()
        epoch = self.service._leases[first.generation_id].epoch
        now += timedelta(seconds=31)
        included = self.decide(self.f.item, "include", "included")
        self.service.synchronize()
        self.assertGreater(self.service._leases[first.generation_id].epoch, epoch)
        self.service.close()
        now += timedelta(seconds=31)
        self.decide(included, "withdraw", "withdrawn")
        assert self.canonical is not None
        reopened = CoreLexicalIndexService(self.f.sources, self.keys, self.canonical)
        self.addCleanup(reopened.close)
        reopened.catalog.now = self.service.catalog.now
        recovered = reopened.synchronize()
        self.assertEqual(self.service.catalog.watermark(), recovered.checkpoint)
        self.assertEqual((), reopened.match(parse_query("identifiers:synthetic")))

    def test_permission_expiry_after_fts_match_discards_buffered_results(self):
        expiry = (datetime.now(UTC) + timedelta(minutes=2)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        self.f.permit(self.subject, previous=self.grant.revision_id, corpus_membership=True, expires_at=expiry)
        self.service.rebuild()
        now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        self.service.catalog.now = lambda: now
        original = ProtectedLexicalStore.match

        def expire_after_match(store, query, entries, items):
            nonlocal now
            result = original(store, query, entries, items)
            self.assertEqual((self.f.item.item_id,), result)
            now = expiry
            return result

        with patch.object(ProtectedLexicalStore, "match", expire_after_match), self.assertRaises(IndexServiceProblem):
            self.service.match(parse_query("identifiers:synthetic"))

    def test_unindexed_current_item_cannot_become_a_false_boolean_negative(self):
        self.service.rebuild()

        def build():
            item, path = self.f.corpus._build_item()
            return item.model_copy(update={"work_revision_id": self.f.attachments.work_revision_id}), path

        second = self.f.corpus._create(build=build)
        with self.assertRaises(IndexServiceProblem):
            self.service.match(parse_query("NOT identifiers:synthetic"))
        self.service.synchronize()
        self.assertEqual((), self.service.match(parse_query("NOT identifiers:synthetic")))
        self.assertEqual(
            tuple(sorted((self.f.item.item_id, second.item_id))),
            self.service.match(parse_query("identifiers:synthetic")),
        )

    def test_encrypted_clone_with_new_file_identity_is_not_the_selected_owned_file(self):
        first = self.service.rebuild()
        path = self.service.root / "indexes" / ("lexical-" + first.generation_id + ".sqlite3")
        original = path.stat().st_ino
        replacement = path.with_suffix(".synthetic-copy")
        shutil.copyfile(path, replacement)
        os.replace(replacement, path)
        self.assertNotEqual(original, path.stat().st_ino)
        with self.assertRaises(IndexServiceProblem):
            self.service.match(parse_query("identifiers:synthetic"))
        with self.assertRaises(IndexServiceProblem):
            self.service.synchronize()

    def test_late_cancellation_inside_promotion_fence_preserves_previous_selection(self):
        first = self.service.rebuild()
        stopped = False
        original = self.service._revalidator

        def revalidator(validation, **kwargs):
            check = original(validation, **kwargs)

            def cancel(db):
                nonlocal stopped
                stopped = True
                check(db)

            return cancel

        with (
            patch.object(self.service, "_revalidator", side_effect=revalidator),
            self.assertRaises(IndexServiceProblem),
        ):
            self.service.rebuild(cancelled=lambda: stopped)
        selected = self.service.catalog.selected()
        assert selected is not None
        self.assertEqual(first.selection_id, selected.selection_id)
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))

    def test_headless_rebuild_matches_fresh_generation_and_revocation_blocks_before_purge(self):
        first = self.service.rebuild()
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))
        second = self.service.rebuild()
        self.assertNotEqual(first.generation_id, second.generation_id)
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))
        self.f.permit(self.subject, previous=self.grant.revision_id, index="denied")
        self.assertEqual((), self.service.match(parse_query("identifiers:synthetic")))
        self.service.synchronize()
        self.assertEqual((), self.service.match(parse_query("identifiers:synthetic")))

    def test_projection_search_spans_nodes_retains_uncovered_text_and_deduplicates_overlap(self):
        def change(value):
            template = value["nodes"][0]
            value["nodes"] = []
            for number, (start, end) in enumerate(((0, 5), (6, 10), (0, 5))):
                node = deepcopy(template)
                node["stagedId"], node["order"] = "synthetic-node-" + str(number), number
                node["text"]["normalizedRange"] = {"start": start, "end": end}
                node["text"]["rawRanges"] = [{"start": start, "end": end}]
                node["locator"]["rawRanges"] = [{"start": start, "end": end}]
                value["nodes"].append(node)

        parsed = self.f.f.parse("alpha beta hidden", change=change)
        accepted = self.f.f.repository.accept(self.f.f.command(parsed))
        denied = self.service.rebuild()
        with ProtectedLexicalStore(self.service.root, denied.scope, self.keys) as store:
            self.assertEqual(0, store._db.execute("SELECT count(*) FROM search_rows WHERE full_text<>''").fetchone()[0])
        self.assertEqual((), self.service.match(parse_query("full-text:hidden")))
        self.f.permit(self.f.f.f.candidate.rights_subject, previous=self.f.f.f.policy.revision_id)
        text = tuple(row for row in self.f.sources.capture(self.f.item.item_id).rows if row.full_text)
        self.assertEqual(1, len(text))
        self.assertEqual(accepted.structure.text_projections[0].projection_id, text[0].projection_id)
        self.assertEqual("alpha beta hidden", text[0].full_text)
        self.service.rebuild()
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query('full-text:"alpha beta"')))
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("full-text:hidden")))

    def test_phrase_never_joins_separate_accepted_projections(self):
        def change(value):
            template = value["nodes"][0]
            value["textProjections"], value["nodes"] = [], []
            for number, raw in enumerate(("alpha", "beta alpha")):
                projection = "synthetic-projection-" + str(number)
                value["textProjections"].append(
                    TextProjection.from_raw(projection, raw).model_dump(mode="json", by_alias=True)
                )
                node = deepcopy(template)
                node["stagedId"], node["order"] = "synthetic-node-" + str(number), number
                node["text"] = {
                    "projectionId": projection,
                    "normalizedRange": {"start": 0, "end": len(raw)},
                    "rawRanges": [{"start": 0, "end": len(raw)}],
                }
                node["locator"] = {
                    "kind": "text",
                    "projectionId": projection,
                    "rawRanges": [{"start": 0, "end": len(raw)}],
                }
                value["nodes"].append(node)

        parsed = self.f.f.parse("unused original projection", change=change)
        self.f.f.repository.accept(self.f.f.command(parsed))
        self.f.permit(self.f.f.f.candidate.rights_subject, previous=self.f.f.f.policy.revision_id)
        text = tuple(row for row in self.f.sources.capture(self.f.item.item_id).rows if row.full_text)
        self.assertEqual(2, len(text))
        self.assertEqual(2, len({row.projection_id for row in text}))
        self.service.rebuild()
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("full-text:alpha")))
        self.assertEqual(
            self.service.match(parse_query("full-text:alpha OR full-text:alpha")),
            self.service.match(parse_query("full-text:alpha")),
        )
        self.assertEqual((), self.service.match(parse_query('full-text:"alpha beta"')))
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("full-text:alpha AND full-text:beta")))

        def build():
            item, path = self.f.corpus._build_item()
            return item.model_copy(update={"work_revision_id": self.f.attachments.work_revision_id}), path

        second = self.f.corpus._create(build=build)
        self.service.synchronize()
        calls = []
        original = ProtectedLexicalStore.match

        def observe(store, query, entries, items):
            calls.append((len(entries), len(items)))
            return original(store, query, entries, items)

        # A lowered working-set bound exercises real disjoint item batching;
        # it is not a production-capacity or performance qualification.
        with (
            patch("research_observatory_core.lexical_index_repository._MAX_QUERY_BATCH_ENTRIES", 4),
            patch.object(ProtectedLexicalStore, "match", observe),
        ):
            expected = tuple(sorted((self.f.item.item_id, second.item_id)))
            self.assertEqual(expected, self.service.match(parse_query("full-text:alpha AND full-text:beta")))
            self.assertEqual(expected, self.service.match(parse_query('NOT full-text:"alpha beta"')))
        self.assertEqual([(3, 1)] * 4, calls)

    def test_failed_empty_initialization_can_retire_owned_partial_files_and_rebuild(self):
        first = self.service.rebuild()
        lease = self.service.begin_rebuild()
        with (
            patch.object(ProtectedLexicalStore, "_initialize", side_effect=RuntimeError("synthetic bootstrap fault")),
            self.assertRaises(IndexServiceProblem),
        ):
            self.service.run_build(lease)
        selected = self.service.catalog.selected()
        assert selected is not None
        self.assertEqual(first.generation_id, selected.generation_id)
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))
        replacement = self.service.rebuild()
        self.assertNotEqual(first.generation_id, replacement.generation_id)
        failed_path = self.service.root / "indexes" / ("lexical-" + lease.generation_id + ".sqlite3")
        self.assertFalse(failed_path.exists())
        self.assertFalse(any(failed_path.parent.glob(failed_path.name + "-*")))

    def test_partial_bootstrap_preserves_unknown_mixed_case_names_before_revoke(self):
        lease = self.service.begin_rebuild()
        with (
            patch.object(ProtectedLexicalStore, "_initialize", side_effect=RuntimeError("synthetic bootstrap fault")),
            self.assertRaises(IndexServiceProblem),
        ):
            self.service.run_build(lease)
        snapshot = self.service.catalog.get(lease.generation_id)
        path = self.service.root / "indexes" / ("lexical-" + lease.generation_id + ".sqlite3")
        unknown = path.with_name(path.name.upper() + "-Unowned")
        unknown.write_bytes(b"synthetic unowned bytes")
        before = {entry.name: entry.read_bytes() for entry in path.parent.iterdir()}
        with self.assertRaises(IndexServiceProblem):
            self.service.retire(lease.generation_id)
        self.assertEqual(before, {entry.name: entry.read_bytes() for entry in path.parent.iterdir()})
        with self.keys.lease(snapshot.scope, create=False) as key:
            self.assertEqual(snapshot.derivative_key_version, key.version)

    @unittest.skipUnless(os.name == "nt", "W3 actual Windows kernel bootstrap cleanup")
    def test_owned_child_bootstrap_crash_phases_retire_without_losing_previous_selection(self):
        assert isinstance(self.canonical, InMemoryDatabaseKeyProvider)
        first = self.service.rebuild()
        phases = (
            "created-main",
            "created--wal",
            "created--shm",
            "created--journal",
            "witness-committed",
            "retained-main",
            "retained--wal",
            "retained--shm",
            "retained--journal",
            "guards-acquired",
            "schema-transaction-open",
            "schema-before-commit",
            "empty-schema-initialized",
            "initialization-acknowledged",
        )
        for phase in phases:
            with self.subTest(phase=phase):
                lease = self.service.begin_rebuild()
                scope = self.service.catalog.get(lease.generation_id).scope
                self.service.catalog.cancel(lease)
                payload = {
                    "root": str(self.service.root),
                    "scope": asdict(scope),
                    "bootstrapPhase": phase,
                    "actor": asdict(self.service.sources.documents.actor()),
                    "canonicalMaterial": list(self.canonical.active_material_for_test(self.service.project)),
                    "records": [
                        {"reference": asdict(reference), "version": record.version, "material": list(material)}
                        for reference, (record, material) in self.vault.values.items()
                    ],
                }
                env = os.environ.copy()
                env.update({name: str(self.service.root) for name in ("TEMP", "TMP", "TMPDIR", "SQLITE_TMPDIR")})
                result = subprocess.run(
                    [sys.executable, "-B", str(ROOT / "tests/search/lexical_crash_child.py")],
                    input=json.dumps(payload).encode(),
                    capture_output=True,
                    timeout=45,
                    env=env,
                )
                self.assertEqual(73, result.returncode, result.stderr.decode(errors="replace"))
                selected = self.service.catalog.selected()
                assert selected is not None
                self.assertEqual(first.generation_id, selected.generation_id)
                self.assertEqual(
                    phase == "initialization-acknowledged", self.service.catalog.initialized(lease.generation_id)
                )
                path = self.service.root / "indexes" / ("lexical-" + lease.generation_id + ".sqlite3")
                if phase.startswith("created-") or phase == "witness-committed":
                    self.assertFalse(any(path.parent.glob(path.name + "*")))
                original_clock = self.service.catalog.now
                self.service.catalog.now = lambda: (
                    (datetime.now(UTC) + timedelta(seconds=31))
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z")
                )
                try:
                    self.service.retire(lease.generation_id)
                finally:
                    self.service.catalog.now = original_clock
                self.assertFalse(any(path.parent.glob(path.name + "*")))
                self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))

    def test_failed_shadow_preserves_previous_selection_and_cancelled_build_resumes(self):
        first = self.service.rebuild()
        with self.assertRaises(IndexServiceProblem):
            self.service.rebuild(cancelled=lambda: True)
        selected = self.service.catalog.selected()
        assert selected is not None
        self.assertEqual(first.generation_id, selected.generation_id)
        lease = self.service.begin_rebuild()
        self.addCleanup(lease.close)
        with self.assertRaises(IndexServiceProblem):
            self.service.run_build(lease, cancelled=lambda: True)
        self.assertEqual("Incomplete", self.service.catalog.get(lease.generation_id).stage)
        resumed = self.service.resume(lease.generation_id)
        self.assertEqual(lease.generation_id, resumed.generation_id)
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))

    def test_regrant_after_pending_recheck_is_observed_as_a_committed_source_change(self):
        self.service.rebuild()
        denied = self.f.permit(self.subject, previous=self.grant.revision_id, index="denied")
        self.service.synchronize()
        # Force the existing bounded propagation path with one real corpus
        # dependency; this is not a production-scale threshold qualification.
        with patch("research_observatory_core.rights_repository._MAX_EXACT_RECHECKS", 0):
            self.f.permit(self.subject, previous=denied.revision_id)
        self.service.synchronize()
        scope = self.f.attachments.rights.recheck_scope(self.subject, actor=self.f.f.actor)
        assert scope is not None
        self.assertEqual("pending", scope.disposition)
        checkpoint = self.service.catalog.watermark()
        for _ in range(16):
            scope = self.f.attachments.rights.advance_rechecks(self.subject, actor=self.f.f.actor, batch_size=1)
            assert scope is not None
            if scope.disposition != "pending":
                break
        self.assertNotEqual("pending", scope.disposition)
        self.assertGreater(self.service.catalog.watermark(), checkpoint)
        self.service.synchronize()
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))

    def test_deselected_generation_retires_key_and_owned_files_only(self):
        first = self.service.rebuild()
        second = self.service.rebuild()
        self.service.retire(first.generation_id)
        self.assertEqual("Retired", self.service.catalog.get(first.generation_id).stage)
        old = self.service.root / "indexes" / ("lexical-" + first.generation_id + ".sqlite3")
        self.assertFalse(old.exists())
        self.assertFalse(any(old.parent.glob(old.name + "-*")))
        with self.keys.lease(first.scope, create=False) as replacement:
            self.assertNotEqual(first.derivative_key_version, replacement.version)
        with self.assertRaises(IndexServiceProblem):
            self.service.retire(second.generation_id)
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))

    def test_real_canonical_rekey_rebuild_recovers_and_retires_owned_old_sidecars(self):
        first = self.service.rebuild()
        path = self.service.root / "indexes" / ("lexical-" + first.generation_id + ".sqlite3")
        # Empty owned WAL/SHM names model a drained connection whose process
        # did not finish sidecar disposition. The old encrypted main is real.
        for suffix in ("-wal", "-shm"):
            path.with_name(path.name + suffix).touch(exist_ok=False)
        report = storage.rekey_protected_database(
            self.service.database, project_id=self.service.project, operation_id="3" * 32
        )
        self.assertEqual("rekeyed", report.outcome)
        with self.assertRaises(IndexServiceProblem):
            self.service.match(parse_query("identifiers:synthetic"))
        second = self.service.rebuild()
        self.assertNotEqual(first.scope.canonical_key_version, second.scope.canonical_key_version)
        self.assertEqual("Retired", self.service.catalog.get(first.generation_id).stage)
        self.assertFalse(path.exists())
        self.assertFalse(any(path.parent.glob(path.name + "-*")))
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))

    def test_live_reader_defers_retirement_before_key_revoke_then_normal_drain_allows_retry(self):
        first = self.service.rebuild()
        ready, release = threading.Event(), threading.Event()
        failures = []

        def reader():
            try:
                with ProtectedLexicalStore(self.service.root, first.scope, self.keys):
                    ready.set()
                    if not release.wait(45):
                        raise AssertionError("synthetic reader was not released")
            except BaseException as error:
                failures.append(error)
                ready.set()

        thread = threading.Thread(target=reader)
        thread.start()
        try:
            self.assertTrue(ready.wait(10))
            self.assertEqual([], failures)
            with self.assertRaises(IndexCleanupPending) as result:
                self.service.rebuild()
            selected = self.service.catalog.selected()
            assert selected is not None
            self.assertEqual(selected.generation_id, result.exception.selected_generation_id)
            self.assertNotEqual(first.generation_id, selected.generation_id)
            started = time.monotonic()
            with self.assertRaises(IndexServiceProblem):
                self.service.retire(first.generation_id)
            self.assertLess(time.monotonic() - started, 5)
            with self.keys.lease(first.scope, create=False) as old:
                self.assertEqual(first.derivative_key_version, old.version)
        finally:
            release.set()
            thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], failures)
        self.service.collect_obsolete()
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))

    def test_retirement_retry_after_key_revocation_needs_no_destroyed_key(self):
        first = self.service.rebuild()
        old = self.service.root / "indexes" / ("lexical-" + first.generation_id + ".sqlite3")

        def interrupt(name):
            if name == "retirement-key-revoked":
                raise RuntimeError("synthetic retirement interruption")

        with (
            patch("research_observatory_core.lexical_index_repository._index_step", side_effect=interrupt),
            self.assertRaises(IndexServiceProblem),
        ):
            self.service.rebuild()
        selected = self.service.catalog.selected()
        assert selected is not None
        self.assertNotEqual(first.generation_id, selected.generation_id)
        self.assertTrue(old.exists())
        self.assertFalse(any(old.parent.glob(old.name + "-*")))
        self.service.collect_obsolete()
        self.assertFalse(old.exists())
        self.assertEqual((self.f.item.item_id,), self.service.match(parse_query("identifiers:synthetic")))


if __name__ == "__main__":
    unittest.main()
