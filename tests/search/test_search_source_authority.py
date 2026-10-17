"""Real import draft writes invalidate a read without fabricating outbox events."""

import sys
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.lexical_input_repository import source_authority_epoch  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402

from tests.data import test_import_preview_drafts as fixtures  # noqa: E402


class SearchSourceAuthorityTests(unittest.TestCase):
    def test_each_preview_draft_and_record_decision_advances_transactional_epoch(self):
        fixture = fixtures.ImportPreviewDraftTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        first, _ = fixture.accepted()
        second, records = fixture.accepted()
        repository = fixture.repository()
        project = fixture.fixture.project

        def head():
            with closing(open_canonical_database(project / "state/project.sqlite3")) as db:
                identity = db.execute("SELECT project_id FROM projects").fetchone()[0]
                return (
                    source_authority_epoch(db, identity),
                    db.execute("SELECT coalesce(max(sequence),0) FROM search_changes").fetchone()[0],
                )

        # One preview's larger revision cannot hide another preview's next write.
        for revision in range(4):
            fixture.change(first, revision)
        before, watermark = head()
        fixture.change(second, 0)
        after, current = head()
        self.assertGreater(after, before)
        self.assertEqual(watermark, current)
        from research_observatory_core.ingestion.import_drafts import review_record

        fixture.change(second, 1, decisions=(review_record(records[1], included=False, fields=()),))
        decision_epoch, current = head()
        self.assertGreater(decision_epoch, after)
        self.assertEqual(watermark, current)
        self.assertEqual(2, repository.draft(second).revision)


if __name__ == "__main__":
    unittest.main()
