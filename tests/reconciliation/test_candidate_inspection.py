"""Historical candidate evidence remains distinct from current membership."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.reconciliation.decisions import ReviewCommand, ReviewPlan, SourcePartition
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository

from tests.reconciliation import test_batch_publication as fixtures


class CandidateInspectionTests(unittest.TestCase):
    def test_prioritized_pages_keep_original_order_after_membership_split_and_reopen(self):
        fixture = fixtures.BatchPublicationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        output, pairs = fixture.publish_prioritized_batch()
        repository, source = fixture.f.repository, fixture.f
        content = repository.candidate_set(output.revision_id, resolve=source.resolve)
        work = content.members[0].canonical_work
        assert work is not None
        context = repository.review_context((work.work_id,), resolve=source.resolve)
        members = context.works[0].assertion_revision_ids
        self.assertEqual(2, len(members))
        plan = ReviewPlan(
            action="split",
            works=context.works,
            unassigned_assertion_revision_ids=(),
            partitions=(
                SourcePartition(group="retained", existing_work_id=work.work_id, assertion_revision_ids=members[:1]),
                SourcePartition(group="separate", existing_work_id=None, assertion_revision_ids=members[1:]),
            ),
            aliases=(),
            conflict_disposition="retain-all",
            evidence_sha256=context.evidence_sha256,
            rationale="Synthetic split changes impact while retaining the historical review order.",
        )
        preview = repository.preview_review(plan, actor=source.actor, resolve=source.resolve)
        repository.review(
            ReviewCommand(command_id=new_uuid_v7(), plan=plan, expected_preview_sha256=preview.preview_sha256),
            actor=source.actor,
            resolve=source.resolve,
        )
        fixture.f.repository = SqliteReconciliationRepository(source.database, source.project)
        observed = list(pairs[:0])
        cursor = 0
        while True:
            page = fixture.f.repository.inspect_candidates(
                output.revision_id, after=cursor, limit=1, resolve=source.resolve
            )
            self.assertEqual("changed", page.membership_state)
            self.assertEqual("requires-review", page.dependency_state)
            observed.extend(page.items)
            if page.next_after is None:
                break
            self.assertEqual(cursor + 1, page.next_after)
            cursor = page.next_after
        self.assertEqual(pairs, tuple(observed))
        self.assertEqual(content, fixture.f.repository.candidate_set(output.revision_id, resolve=source.resolve))

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
