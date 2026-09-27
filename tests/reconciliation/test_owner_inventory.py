"""Owner paging preserves excluded ordinals and exact accepted source identity."""

import json
import unittest
from unittest.mock import patch

from research_observatory_core.connectors.broker import ConnectorBroker, ProviderRateController
from research_observatory_core.connectors.providers import map_response
from research_observatory_core.connectors.workflow import ACTIVITY
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.ports.import_previews import PreviewDraftChange
from research_observatory_core.reconciliation.contracts import ReconciliationProblem
from research_observatory_core.workflow_executor import WorkflowCancellationRequested

from tests.connectors.test_connector_workflow import ConnectorWorkflowFixture
from tests.connectors.test_scholarly_mapping import fixture as source_fixture
from tests.service.test_import_commit_service import ImportCommitServiceTests


class ImportOwnerInventoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ImportCommitServiceTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def permitted_draft(self):
        f = self.fixture.fixture
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
        selected = f.repository.draft_page(f.preview, revision=1, after=1, limit=1)[0]
        return f.repository.revise_draft(
            f.preview,
            PreviewDraftChange(
                expected_revision=1,
                actor=f.actor,
                decisions=(selected.decision.model_copy(update={"rights": rights}),),
            ),
        )

    def test_changed_request_cannot_borrow_old_manifest_but_same_identity_reuses(self):
        f = self.fixture.fixture
        self.permitted_draft()
        first = f.service.schedule_commit(f.root, f.preview, revision=2, request_id=new_uuid_v7())
        f.service.run_pending()
        original = f.queue.accepted_output(first.job_id).outputs[0]
        f.repository.revise_draft(f.preview, PreviewDraftChange(expected_revision=2, actor=f.actor))
        same = f.service.schedule_commit(f.root, f.preview, revision=3, request_id=new_uuid_v7())
        f.service.run_pending()
        self.assertEqual(original, f.queue.accepted_output(same.job_id).outputs[0])
        reused = f.service.reconciliation_sources(f.root, same.job_id, after=0, limit=100)
        self.assertEqual(1, len(reused.addresses))
        selected = f.repository.draft_page(f.preview, revision=3, after=1, limit=1)[0]
        f.repository.revise_draft(
            f.preview,
            PreviewDraftChange(
                expected_revision=3,
                actor=f.actor,
                decisions=(selected.decision.model_copy(update={"included": False}),),
            ),
        )
        changed = f.service.schedule_commit(f.root, f.preview, revision=4, request_id=new_uuid_v7())
        claim = f.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=f.fixture.now,
            lease_duration_ms=30000,
            activity_types=("local-import-commit",),
        )
        self.assertEqual(changed.job_id, claim.job_id)
        f.queue.start(claim, now=f.fixture.now)
        inputs = f.repository.latest_commit_request(f.preview).inputs
        actor = f.actor.model_copy(update={"actor_id": claim.worker_id})
        f.repository.begin_commit(inputs, claim=claim, actor=actor)
        after = 0
        while after < inputs.record_count:
            after = f.repository.append_commit_page(inputs, after=after, claim=claim, actor=actor)
        expected_identity = f.repository.prepared_identity(inputs, claim=claim, actor=actor)
        self.assertNotEqual(f.repository.manifest(original.revision_id).identity_sha256, expected_identity.sha256)
        # Generic queue completion accepts any canonical output. The import
        # owner must also establish this exact command's scientific meaning.
        f.queue.stage_artifact(claim, artifact=original, role="output", now=f.fixture.now)
        f.queue.complete(claim, outputs=(original,), now=f.fixture.now)
        with self.assertRaises(ReconciliationProblem):
            f.service.reconciliation_sources(f.root, changed.job_id, after=0, limit=100)

    def test_excluded_page_advances_and_included_address_survives_restart(self):
        owner = self.fixture
        f = owner.fixture
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
        selected = f.repository.draft_page(f.preview, revision=1, after=1, limit=1)[0]
        f.repository.revise_draft(
            f.preview,
            PreviewDraftChange(
                expected_revision=1,
                actor=f.actor,
                decisions=(selected.decision.model_copy(update={"rights": rights}),),
            ),
        )
        job = f.service.schedule_commit(f.root, f.preview, revision=2, request_id=owner.request)
        f.service.run_pending()
        first = f.service.reconciliation_sources(f.root, job.job_id, after=0, limit=1)
        self.assertEqual((), first.addresses)
        self.assertEqual(1, first.scanned_through)
        self.assertFalse(first.complete)
        second = f.service.reconciliation_sources(f.root, job.job_id, after=1, limit=1)
        self.assertEqual(1, len(second.addresses))
        self.assertEqual(2, second.addresses[0].ordinal)
        self.assertTrue(second.complete)
        binding = next(iter(f.service._bindings.values()))
        with patch.object(
            binding.adapters.previews, "accepted_manifest", wraps=binding.adapters.previews.accepted_manifest
        ) as verify:
            self.assertEqual((first, second), tuple(f.service.reconciliation_pages(f.root, job.job_id, limit=1)))
            self.assertEqual(1, verify.call_count)
        interrupted = f.service.reconciliation_pages(
            f.root, job.job_id, checkpoint=lambda: (_ for _ in ()).throw(WorkflowCancellationRequested())
        )
        with self.assertRaises(WorkflowCancellationRequested):
            next(interrupted)
        self.assertEqual("succeeded", f.queue.get(job.job_id).state)
        source = f.service.reconciliation_source(f.root, second.addresses[0])
        restarted = owner.restart()
        self.assertEqual(second, restarted.reconciliation_sources(f.root, job.job_id, after=1, limit=1))
        self.assertEqual(source, restarted.reconciliation_source(f.root, second.addresses[0]))
        with self.assertRaises(ReconciliationProblem):
            restarted.reconciliation_sources(f.root, job.job_id, after=3, limit=1)


class ConnectorOwnerInventoryTests(ConnectorWorkflowFixture):
    def test_historical_accepted_continuation_is_found_despite_newer_active_sibling(self):
        # This constructs retained historical acceptance through repository ports.
        # It is not permission or evidence for generic connector network retry.
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        self.rights = self.rights.model_copy(
            update={"rights": ImportRights(store=grant, inspect=grant, derive=grant, index=grant)}
        )
        preview, original = self.schedule()
        authority = self.connectors.authority(self.root, preview.preview_id)
        rates = ProviderRateController(clock=self.clock.monotonic)
        broker = ConnectorBroker(authority=authority, repository=self.repository, rates=rates, now=self.clock.now)
        body = json.dumps(source_fixture("openalex"), separators=(",", ":")).encode()
        page = broker._page(
            self.request,
            rates.bucket("openalex"),
            mapped=map_response(self.request, json.loads(body), retrieved_at=self.clock.now()),
            retrieved_at=self.clock.now(),
            body=body,
            retain=True,
        )
        authority.guard(
            self.request,
            "publication",
            lambda stamp: self.repository.publish(
                page,
                body=body,
                etag=None,
                last_modified=None,
                authority=stamp,
            ),
        )
        claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.clock.now(),
            lease_duration_ms=30000,
            activity_types=(ACTIVITY,),
        )
        self.queue.start(claim, now=self.clock.now())
        self.queue.fail(claim, now=self.clock.now(), error_code="invalid-input")
        failed = self.queue.task_center()[0]
        continued = self.queue.retry_as_continuation(
            original.job_id,
            expected_snapshot_revision=failed.snapshot_revision,
            expected_history_sequence=failed.revision,
            idempotency_key="3" * 32,
            actor=self.worker._actor(),
            now=self.clock.now(),
        )
        claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.clock.now(),
            lease_duration_ms=30000,
            activity_types=(ACTIVITY,),
        )
        self.queue.start(claim, now=self.clock.now())
        output = self.repository.output_reference(self.request)
        self.queue.stage_artifact(claim, artifact=output, role="output", now=self.clock.now())
        self.queue.complete(claim, outputs=(output,), now=self.clock.now())
        self.queue.retry_as_continuation(
            original.job_id,
            expected_snapshot_revision=failed.snapshot_revision,
            expected_history_sequence=failed.revision,
            idempotency_key="4" * 32,
            actor=self.worker._actor(),
            now=self.clock.now(),
        )
        address = self.worker.reconciliation_address(self.root, preview.preview_id, 0)
        self.assertEqual(output.revision_id, address.revision_id)
        source = self.worker.reconciliation_source(self.root, address)
        enumerated = self.worker.reconciliation_sources(self.root, continued.jobs[0].job_id, after=0, limit=1)
        self.assertEqual((address,), enumerated.addresses)
        self.worker.shutdown()
        self.connectors = self.consent_service()
        self.worker = self.worker_service()
        self.assertEqual(source, self.worker.reconciliation_source(self.root, address))
        self.assertEqual([], self.calls)

    def test_exact_accepted_owner_page_resolves_without_another_network_request(self):
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        self.rights = self.rights.model_copy(
            update={"rights": ImportRights(store=grant, inspect=grant, derive=grant, index=grant)}
        )
        preview, job = self.schedule()
        with self.assertRaises(ReconciliationProblem):
            self.worker.reconciliation_sources(self.root, job.job_id, after=0, limit=1)
        self.worker.run_pending()
        page = self.worker.reconciliation_sources(self.root, job.job_id, after=0, limit=1)
        self.assertEqual(1, len(page.addresses))
        self.assertEqual(preview.preview_id, page.addresses[0].context_id)
        self.assertEqual(0, page.addresses[0].ordinal)
        self.assertEqual(1, page.scanned_through)
        source = self.worker.reconciliation_source(self.root, page.addresses[0])
        self.worker.shutdown()
        self.connectors = self.consent_service()
        self.worker = self.worker_service()
        self.assertEqual(page, self.worker.reconciliation_sources(self.root, job.job_id, after=0, limit=1))
        self.assertEqual(source, self.worker.reconciliation_source(self.root, page.addresses[0]))
        self.assertEqual(1, len(self.calls))
        accepted = self.queue.accepted_output(job.job_id)
        self.assertEqual(ACTIVITY, accepted.activity_type)
        with self.assertRaises(ReconciliationProblem):
            self.worker.reconciliation_source(
                self.root, page.addresses[0].model_copy(update={"revision_id": new_uuid_v7()})
            )
        original = self.repository.operation(preview.preview_id)
        denied = original.model_copy(
            update={
                "preview": original.preview.model_copy(
                    update={
                        "retention": original.preview.retention.model_copy(
                            update={
                                "rights": original.preview.retention.rights.model_copy(
                                    update={
                                        "derive": original.preview.retention.rights.derive.model_copy(
                                            update={"value": "unknown", "basis": "not-reported"}
                                        )
                                    }
                                )
                            }
                        )
                    }
                )
            }
        )
        with patch.object(self.repository, "operation", return_value=denied), self.assertRaises(ReconciliationProblem):
            self.worker.reconciliation_sources(self.root, job.job_id, after=0, limit=1)
