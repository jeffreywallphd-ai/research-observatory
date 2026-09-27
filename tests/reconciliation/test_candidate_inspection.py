"""Historical candidate evidence remains distinct from current membership."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.reconciliation.decisions import ReviewCommand, ReviewPlan, SourcePartition

from tests.reconciliation import test_batch_publication as fixtures


class CandidateInspectionTests(unittest.TestCase):
    def setUp(self):
        self.batch = fixtures.BatchPublicationTests(methodName="runTest")
        self.batch.setUp()
        self.addCleanup(self.batch.doCleanups)
        self.output = self.batch.publish()

    def test_split_keeps_candidate_evidence_and_exposes_changed_membership(self):
        repository, fixture = self.batch.f.repository, self.batch.f
        before = repository.inspect_candidates(self.output.revision_id, after=0, limit=1, resolve=fixture.resolve)
        schema = json.loads(
            (
                Path(__file__).resolve().parents[2] / "packages/contracts/scholarly-records/candidate-page.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(before.model_dump(mode="json", by_alias=True))
        self.assertEqual("unchanged", before.membership_state)
        self.assertEqual("unaffected", before.dependency_state)
        self.assertEqual(2, before.record_count)
        self.assertEqual(1, before.candidate_count)
        self.assertIsNone(before.next_after)
        content = repository.candidate_set(self.output.revision_id, resolve=fixture.resolve)
        canonical_work = content.members[0].canonical_work
        assert canonical_work is not None
        work = canonical_work.work_id
        context = repository.review_context((work,), resolve=fixture.resolve)
        members = context.works[0].assertion_revision_ids
        plan = ReviewPlan(
            action="split",
            works=context.works,
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(group="retained", existing_work_id=work, assertion_revision_ids=members[:1]),
                SourcePartition(group="separate", existing_work_id=None, assertion_revision_ids=members[1:]),
            ),
            aliases=(),
            conflict_disposition="retain-all",
            evidence_sha256=context.evidence_sha256,
            rationale="Synthetic review separates two sources while retaining evidence.",
        )
        preview = repository.preview_review(plan, actor=fixture.actor, resolve=fixture.resolve)
        repository.review(
            ReviewCommand(command_id=new_uuid_v7(), plan=plan, expected_preview_sha256=preview.preview_sha256),
            actor=fixture.actor,
            resolve=fixture.resolve,
        )
        after = repository.inspect_candidates(self.output.revision_id, after=0, limit=1, resolve=fixture.resolve)
        self.assertEqual(before.items, after.items)
        self.assertEqual("changed", after.membership_state)
        self.assertEqual("requires-review", after.dependency_state)
        self.assertEqual(content, repository.candidate_set(self.output.revision_id, resolve=fixture.resolve))
        self.assertEqual(
            (), repository.inspect_candidates(self.output.revision_id, after=1, limit=1, resolve=fixture.resolve).items
        )
