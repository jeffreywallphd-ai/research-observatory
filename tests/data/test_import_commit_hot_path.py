"""Measured hot-path regressions without changing publication authority."""

import unittest
from unittest.mock import patch

from research_observatory_core import import_preview_repository, repositories
from research_observatory_core.ports.import_previews import PreviewDraftChange, PreviewProblem

from tests.data import test_import_commit_publication as publication


class ImportCommitHotPathTests(unittest.TestCase):
    def setUp(self):
        self.case = publication.ImportCommitPublicationTests(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_canonical_publication_uses_fixed_compiled_statements(self):
        self.case.fixture.append()
        with patch.object(repositories, "_execute", wraps=repositories._execute) as compiled:
            output = self.case.publish()
        self.assertEqual(output.revision_id, self.case.fixture.repository.manifest(output.revision_id).revision_id)
        self.assertEqual((1, 1, 2, 1, 2), self.case.counts()[3:])
        self.assertEqual(0, compiled.call_count, "fixed aggregate queries must not compile per record")

    def test_draft_record_read_does_not_compile_the_same_query_per_ordinal(self):
        execute = import_preview_repository._execute
        compiled_rows = []

        def other_queries(connection, sql, **parameters):
            if "SELECT record_key, record_json FROM import_parse_records" in " ".join(sql.split()):
                compiled_rows.append(parameters)
            return execute(connection, sql, **parameters)

        f = self.case.fixture
        with patch.object(import_preview_repository, "_execute", side_effect=other_queries):
            page = f.repository.draft_page(f.inputs.preview.preview_id, revision=1, after=0, limit=100)
        self.assertEqual(f.inputs.record_count, len(page))
        self.assertEqual([], compiled_rows, "fixed record lookup must not compile per ordinal")

    def prepared_pages(self):
        f = self.case.fixture
        f.queue.cancel(f.claim, now=f.fixture.now, reason_code="synthetic-replace")
        self.case.prepare_another(b"title,doi\n" + b"Synthetic,10.99999/EXAMPLE\n" * 205)
        self.assertEqual(200, f.append(after=100))
        self.assertEqual(206, f.append(after=200))
        return f

    def test_identity_verification_uses_one_fresh_transaction_per_page(self):
        f = self.prepared_pages()
        expected = f.repository.prepared_identity(f.inputs, claim=f.claim, actor=f.actor)
        prepared_connections, record_connections = [], []
        prepared, record = f.repository._prepared, f.repository._record

        def observe_prepared(connection, *args, **kwargs):
            prepared_connections.append(connection)
            return prepared(connection, *args, **kwargs)

        def observe_record(connection, *args, **kwargs):
            record_connections.append(connection)
            return record(connection, *args, **kwargs)

        with (
            patch.object(
                import_preview_repository,
                "open_canonical_database",
                wraps=import_preview_repository.open_canonical_database,
            ) as opened,
            patch.object(f.repository, "_prepared", side_effect=observe_prepared),
            patch.object(f.repository, "_record", side_effect=observe_record),
        ):
            actual = f.repository._verified_identity(
                f.inputs, f.claim, f.actor, lambda: f.actor.occurred_at, None, lambda action: action()
            )
        self.assertEqual(expected, actual)
        self.assertEqual(4, opened.call_count, "initial authority plus one protected open for each of three pages")
        self.assertEqual(4, len(prepared_connections))
        self.assertEqual(4, len({id(connection) for connection in prepared_connections}))
        self.assertEqual(206, len(record_connections))
        for ordinal, connection in enumerate(record_connections):
            self.assertIs(connection, prepared_connections[1 + ordinal // 100])
        self.assertEqual((0, 0, 0, 0), self.case.counts()[3:7])

    def test_revision_changed_between_verification_pages_is_rejected(self):
        f = self.prepared_pages()
        guarded_actions = 0

        def guard(action):
            nonlocal guarded_actions
            guarded_actions += 1
            if guarded_actions == 3:  # Initial authority and page one have completed.
                f.repository.revise_draft(
                    f.inputs.preview.preview_id,
                    PreviewDraftChange(expected_revision=1, actor=f.fixture.fixture.actor),
                )
            return action()

        with self.assertRaisesRegex(PreviewProblem, "preview-draft-revision-conflict"):
            f.repository._verified_identity(f.inputs, f.claim, f.actor, lambda: f.actor.occurred_at, None, guard)
        self.assertEqual(3, guarded_actions)
        self.assertEqual((0, 0, 0, 0), self.case.counts()[3:7])


if __name__ == "__main__":
    unittest.main()
