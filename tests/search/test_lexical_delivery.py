"""Current protected search pages, opaque exact-run cursors and real selectors."""

import base64
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core.lexical_delivery import CoreLexicalResultService  # noqa: E402
from research_observatory_core.lexical_index_repository import IndexServiceProblem  # noqa: E402

from tests.search.fixture_support import SearchRunFixture  # noqa: E402


class LexicalDeliveryTests(SearchRunFixture):
    def test_complete_stable_pages_explanation_and_cross_run_cursor_denial(self):
        for _ in range(2):

            def build():
                item, path = self.f.corpus._build_item()
                return item.model_copy(update={"work_revision_id": self.f.attachments.work_revision_id}), path

            self.f.corpus._create(build=build)
        self.service.rebuild()
        job, _, (record, _) = self.execute(self.inputs())
        delivery = CoreLexicalResultService(self.repo)
        first = delivery.page(job.job_id, limit=1)
        self.assertEqual(3, first.execution.result_count)
        self.assertEqual(record.content.search_run_id, first.execution.search_run_id)
        self.assertEqual(1, len(first.hits))
        second_job, _, _ = self.execute(self.inputs())
        second = delivery.page(job.job_id, after=first.next_cursor, limit=2)
        self.assertIsNone(second.next_cursor)
        complete = delivery.page(job.job_id)
        self.assertEqual(complete.hits, (*first.hits, *second.hits))
        self.assertEqual(
            tuple(sorted(hit.item_id for hit in complete.hits)), tuple(hit.item_id for hit in complete.hits)
        )
        explanation = delivery.explain(job.job_id, first.hits[0].item_id)
        self.assertAlmostEqual(first.hits[0].score, sum(value.score for value in explanation.components))
        self.assertTrue(explanation.components)
        self.assertNotIn("probability", explanation.model_dump_json())
        with self.assertRaises(IndexServiceProblem):
            delivery.page(second_job.job_id, after=first.next_cursor)
        raw = json.loads(base64.urlsafe_b64decode(first.next_cursor + "=" * (-len(first.next_cursor) % 4)))
        raw["lastScore"] = "0x1.0p+99"
        changed = base64.urlsafe_b64encode(json.dumps(raw, separators=(",", ":")).encode()).decode().rstrip("=")
        with self.assertRaises(IndexServiceProblem):
            delivery.page(job.job_id, after=changed)
        self.f.permit(self.subject, previous=self.grant.revision_id, corpus_membership=True, index="denied")
        with self.assertRaises(IndexServiceProblem):
            delivery.page(job.job_id)

    def test_text_preview_has_exact_source_and_only_real_contained_node_selection(self):
        parsed = self.f.f.parse("Synthetic café passage with searchable text")
        accepted = self.f.f.repository.accept(self.f.f.command(parsed))
        self.f.permit(self.f.f.f.candidate.rights_subject, previous=self.f.f.f.policy.revision_id)
        self.service.rebuild()
        job, _, _ = self.execute(self.inputs(query="full-text:café"))
        hit = CoreLexicalResultService(self.repo).page(job.job_id).hits[0]
        self.assertEqual("full-text", hit.snippet.field)
        self.assertTrue(hit.snippet.highlights)
        self.assertEqual(accepted.revision_id, hit.source.revision_id)
        self.assertEqual(accepted.result.binding.source, hit.source.source)
        if hit.source.selection is not None:
            selection = hit.source.selection
            node = next(value for value in accepted.structure.nodes if value.node_id == selection.node_id)
            self.assertIsNotNone(node.text)
            self.assertLessEqual(node.text.normalized_range.start, selection.normalized_range.start)
            self.assertLessEqual(selection.normalized_range.end, node.text.normalized_range.end)


if __name__ == "__main__":
    unittest.main()
