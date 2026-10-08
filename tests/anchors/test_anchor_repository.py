"""Real encrypted persistence/current native authority; synthetic accepted IR."""

import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.anchors.contracts import AnchorSelection  # noqa: E402
from research_observatory_core.source_anchor_repository import LocalSourceAnchorRepository  # noqa: E402
from research_observatory_core.document_revisions import DocumentRevisionProblem  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.object_store import _object_relative_path  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.documents import test_document_revision_repository as revision_fixtures  # noqa: E402


class AnchorRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.f = revision_fixtures.DocumentRevisionRepositoryTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        result = self.f.parse("First synthetic passage. Second synthetic passage.")
        self.accepted = self.f.repository.accept(self.f.command(result))
        self.selection = AnchorSelection(
            revision_id=self.accepted.revision_id,
            node_id=self.accepted.structure.nodes[0].node_id,
            normalized_range={"start": 25, "end": 49},
        )
        self.command = new_uuid_v7()
        self.repository = self.reopen()

    def reopen(self):
        return LocalSourceAnchorRepository(self.f.reopen())

    def test_restart_reads_exact_encrypted_anchor_with_atomic_provenance_dependencies(self):
        before = self.f.counts()
        anchor = self.repository.create(self.command, self.selection)
        self.assertEqual("Second synthetic passage", anchor.target.quote.exact)
        self.assertEqual(self.accepted.revision_id, anchor.target.revision_id)
        self.assertEqual(anchor, self.reopen().read(anchor.anchor_id))
        after = self.f.counts()
        for table in ("aggregate_revisions", "provenance_events", "outbox_events"):
            self.assertEqual(before[table] + 1, after[table])
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            self.assertEqual(
                "document",
                db.execute(
                    "SELECT aggregate_kind FROM aggregate_revisions WHERE revision_id=?", (anchor.anchor_revision_id,)
                ).fetchone()[0],
            )
        self.assertEqual((anchor.anchor_id,), self.reopen().list(self.accepted.revision_id))

    def test_exact_retry_has_one_publication_changed_selection_conflicts(self):
        anchor = self.repository.create(self.command, self.selection)
        before = self.f.counts()
        self.assertEqual(anchor, self.reopen().create(self.command, self.selection))
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.create(self.command, self.selection.model_copy(update={"node_id": new_uuid_v7()}))
        self.assertEqual(before, self.f.counts())

    def test_concurrent_native_session_retries_publish_one_anchor(self):
        before = self.f.counts()
        start = threading.Barrier(2)

        def create():
            start.wait(timeout=10)
            return self.reopen().create(self.command, self.selection)

        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(create) for _ in range(2)]
            left, right = [attempt.result(timeout=30) for attempt in attempts]
        self.assertEqual(left, right)
        after = self.f.counts()
        for table in ("aggregate_revisions", "provenance_events", "outbox_events"):
            self.assertEqual(before[table] + 1, after[table])
        self.assertEqual((left.anchor_id,), self.repository.list(self.accepted.revision_id))

    def test_closed_native_session_denies_read_and_replay_without_republication(self):
        anchor = self.repository.create(self.command, self.selection)
        before = self.f.counts()
        self.f.f.preview.service.detach(self.f.f.preview.root)
        for action in (
            lambda: self.repository.read(anchor.anchor_id),
            lambda: self.repository.create(self.command, self.selection),
        ):
            with self.assertRaises(DocumentRevisionProblem):
                action()
        self.assertEqual(before, self.f.counts())

    def test_removed_canonical_outbox_denies_an_otherwise_readable_context(self):
        anchor = self.repository.create(self.command, self.selection)
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            db.execute("DELETE FROM outbox_events WHERE idempotency_key=?", ("document.anchor." + self.command,))
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.read(anchor.anchor_id)

    def test_common_read_authenticates_context_without_original_or_whole_ir(self):
        anchor = self.repository.create(self.command, self.selection)
        with (
            patch(
                "research_observatory_core.document_revision_repository.LocalDocumentRevisionRepository._accepted",
                side_effect=AssertionError("whole accepted IR must not be read for a retained anchor"),
            ),
            patch(
                "research_observatory_core.object_store._verified_stored_reader",
                wraps=__import__(
                    "research_observatory_core.object_store", fromlist=["_verified_stored_reader"]
                )._verified_stored_reader,
            ) as reader,
        ):
            restored = self.reopen().read(anchor.anchor_id)
        self.assertEqual(anchor, restored)
        self.assertEqual(1, reader.call_count)
        self.assertEqual("application/vnd.research-observatory.source-anchor+json", reader.call_args.args[3].media_type)

    def test_new_accepted_head_does_not_move_old_anchor(self):
        anchor = self.repository.create(self.command, self.selection)
        result = self.f.parse("Changed later synthetic source representation.")
        later = self.f.repository.accept(self.f.command(result, expected=self.accepted.revision_id))
        self.assertNotEqual(anchor.target.revision_id, later.revision_id)
        self.assertEqual(anchor, self.reopen().read(anchor.anchor_id))

    def test_changed_rights_deny_read_list_and_replay(self):
        anchor = self.repository.create(self.command, self.selection)
        self.f.f.permit(derive="denied")
        for action in (
            lambda: self.repository.read(anchor.anchor_id),
            lambda: self.repository.list(self.accepted.revision_id),
            lambda: self.repository.create(self.command, self.selection),
        ):
            with self.assertRaises(DocumentRevisionProblem):
                action()

    def test_changed_actor_denies_creation_without_publication(self):
        self.f.actor = replace(self.f.actor, actor_id=new_uuid_v7())
        before = self.f.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.create(self.command, self.selection)
        self.assertEqual(before, self.f.counts())

    def test_precommit_failure_leaves_no_anchor_or_durable_event(self):
        before = self.f.counts()
        with (
            patch(
                "research_observatory_core.source_anchor_repository._publication_step",
                side_effect=RuntimeError("synthetic interruption"),
            ),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.repository.create(self.command, self.selection)
        self.assertEqual(before, self.f.counts())
        self.assertEqual((), self.repository.list(self.accepted.revision_id))
        self.assertIsNotNone(self.repository.create(self.command, self.selection))

    def test_corrupt_context_denies_without_quarantining_original(self):
        anchor = self.repository.create(self.command, self.selection)
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            digest = db.execute(
                "SELECT object_sha256 FROM documents WHERE revision_id=?", (anchor.anchor_revision_id,)
            ).fetchone()[0]
        path = self.f.f.fixture.project_root / "objects" / _object_relative_path(self.accepted.project_id, digest)
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.read(anchor.anchor_id)
        with closing(open_canonical_database(self.f.database, expected_project_id=self.accepted.project_id)) as db:
            self.assertEqual(
                "available",
                db.execute(
                    "SELECT storage_state FROM object_records WHERE object_sha256=?", (self.f.f.source.object_sha256,)
                ).fetchone()[0],
            )

    def test_reader_revision_choices_and_outline_keep_exact_source_without_PDF_reads(self):
        result = self.f.parse("Later synthetic paragraph.")
        later = self.f.repository.accept(self.f.command(result, expected=self.accepted.revision_id))
        choices = self.repository.reader_revisions(self.f.f.source.attachment_id)
        self.assertEqual(self.f.f.source, choices.source)
        self.assertEqual(
            (later.revision_id, self.accepted.revision_id), tuple(r.revision_id for r in choices.revisions)
        )
        with patch(
            "research_observatory_core.object_store._verified_stored_reader",
            wraps=__import__(
                "research_observatory_core.object_store", fromlist=["_verified_stored_reader"]
            )._verified_stored_reader,
        ) as reader:
            outline = self.repository.outline(self.accepted.revision_id)
        self.assertEqual("accepted-structured-text", outline.view_kind)
        self.assertEqual(self.accepted.revision_id, outline.revision_id)
        self.assertEqual(self.accepted.structure.nodes[0].node_id, outline.nodes[0].node_id)
        self.assertEqual("First synthetic passage. Second synthetic passage.", outline.nodes[0].preview)
        self.assertTrue(
            all(call.args[3].object_sha256 != self.f.f.source.object_sha256 for call in reader.call_args_list)
        )
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.outline(self.accepted.revision_id, after_node_id=new_uuid_v7())


if __name__ == "__main__":
    unittest.main(verbosity=2)
