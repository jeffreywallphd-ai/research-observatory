"""Complete source enumeration binds the frozen queue and owner page boundaries."""

import unittest
from unittest.mock import patch

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import MappedField
from research_observatory_core.ports.import_previews import PreviewDraftChange
from research_observatory_core.reconciliation.batch import SOURCE_ACTIVITIES, InventorySnapshot
from research_observatory_core.reconciliation.batch_inventory import collect_batch_sources
from research_observatory_core.reconciliation.contracts import ReconciliationProblem

from tests.reconciliation import test_owner_inventory as fixtures


class BatchInventoryTests(unittest.TestCase):
    def setUp(self):
        self.owner = fixtures.ImportOwnerInventoryTests(methodName="runTest")
        self.owner.setUp()
        self.addCleanup(self.owner.doCleanups)
        self.f = self.owner.fixture.fixture
        self.owner.permitted_draft()
        self.job = self.f.service.schedule_commit(self.f.root, self.f.preview, revision=2, request_id=new_uuid_v7())
        self.f.service.run_pending()
        self.snapshot = InventorySnapshot.from_queue(self.f.queue.accepted_snapshot(activity_types=SOURCE_ACTIVITIES))

    def collect(self, snapshot=None):
        return collect_batch_sources(
            snapshot or self.snapshot,
            root=self.f.root,
            queue=self.f.queue,
            imports=self.f.service,
            connectors=self.f.service,
            checkpoint=lambda: None,
            page_size=1,
        )

    def test_frozen_inventory_exhausts_excluded_rows_and_excludes_later_arrivals(self):
        first = self.collect()
        self.assertEqual(1, len(first))
        selected = self.f.repository.draft_page(self.f.preview, revision=2, after=1, limit=1)[0]
        fields = (
            *(item for item in selected.decision.fields if item.name != "title"),
            MappedField(name="title", value="Changed synthetic title", source_field_index=None, origin="correction"),
        )
        self.f.repository.revise_draft(
            self.f.preview,
            PreviewDraftChange(
                expected_revision=2,
                actor=self.f.actor,
                decisions=(selected.decision.model_copy(update={"fields": fields}),),
            ),
        )
        self.f.service.schedule_commit(self.f.root, self.f.preview, revision=3, request_id=new_uuid_v7())
        self.f.service.run_pending()
        self.assertEqual(first, self.collect())
        latest = InventorySnapshot.from_queue(self.f.queue.accepted_snapshot(activity_types=SOURCE_ACTIVITIES))
        self.assertNotEqual(self.snapshot, latest)
        self.assertEqual(2, len(self.collect(latest)))

    def test_incomplete_or_substituted_owner_stream_cannot_claim_complete_inventory(self):
        pages = tuple(self.f.service.reconciliation_pages(self.f.root, self.job.job_id, limit=1))
        for wrong in (
            (),
            pages[:1],
            (pages[0], pages[1].model_copy(update={"addresses": ()})),
            (pages[0], pages[1].model_copy(update={"job_id": new_uuid_v7()})),
            (pages[0], pages[1].model_copy(update={"output_revision_id": new_uuid_v7()})),
        ):
            with (
                self.subTest(pages=len(wrong)),
                patch.object(self.f.service, "reconciliation_pages", return_value=iter(wrong)),
                self.assertRaises(ReconciliationProblem),
            ):
                self.collect()

    def test_count_limits_include_excluded_rows_and_jobs(self):
        for name in ("MAX_INVENTORY_JOBS", "MAX_SCANNED_ROWS"):
            with (
                self.subTest(name=name),
                patch("research_observatory_core.reconciliation.batch_inventory." + name, 0),
                self.assertRaises(ReconciliationProblem),
            ):
                self.collect()
