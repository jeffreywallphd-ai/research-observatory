"""Measured hot-path regressions without changing publication authority."""

import unittest
from unittest.mock import patch

from research_observatory_core import import_preview_repository, repositories

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


if __name__ == "__main__":
    unittest.main()
