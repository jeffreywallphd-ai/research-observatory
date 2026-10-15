"""Commit command/claim authority; no canonical publication is claimed here."""

import unittest
from dataclasses import replace

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.commit_workflow import (
    COMMIT_ACTIVITY,
    CommitJobInput,
    bind_commit_claim,
    build_commit_job,
)
from research_observatory_core.ports.import_previews import PreviewProblem
from research_observatory_core.ports.workflow_executor import WorkflowActor

from tests.service import test_import_summary_workflow as summary_fixture


class ImportCommitWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = summary_fixture.ImportSummaryWorkflowTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        summary = self.fixture.inputs()
        values = summary.model_dump()
        values.pop("algorithm")
        self.inputs = CommitJobInput(**values, request_id=new_uuid_v7())
        self.queue = self.fixture.queue
        self.now = self.fixture.fixture.now
        self.actor = WorkflowActor(self.fixture.fixture.actor, "human", "local-researcher")

    def enqueue(self, inputs=None):
        return self.queue.enqueue(
            build_commit_job(inputs or self.inputs, actor=self.actor, now=self.now), actor=self.actor
        )

    def test_request_replay_is_distinct_from_scientific_identity(self):
        submission = build_commit_job(self.inputs, actor=self.actor, now=self.now)
        first = self.queue.enqueue(submission, actor=self.actor)
        self.assertEqual(first.job_id, self.queue.enqueue(submission, actor=self.actor).job_id)
        changed = self.inputs.model_copy(update={"draft_revision": self.inputs.draft_revision + 1})
        self.assertEqual(self.inputs.idempotency_key, changed.idempotency_key)
        self.assertNotEqual(self.inputs.configuration_hash, changed.configuration_hash)
        from research_observatory_core.ports.workflow_executor import WorkflowQueueProblem

        with self.assertRaises(WorkflowQueueProblem):
            self.enqueue(changed)
        fresh_request = self.inputs.model_copy(update={"request_id": new_uuid_v7()})
        self.assertNotEqual(first.job_id, self.enqueue(fresh_request).job_id)

    def test_exact_claim_accepts_but_changed_inputs_or_claims_deny(self):
        job = self.enqueue()
        claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.now,
            lease_duration_ms=30000,
            activity_types=(COMMIT_ACTIVITY,),
        )
        authority = self.queue.authority(job.job_id)
        self.assertEqual(self.inputs, bind_commit_claim(authority, claim, self.inputs))
        for change in ({"activity_type": "local-import-draft-summary"}, {"command_fingerprint": "sha256:" + "f" * 64}):
            with self.subTest(change=change), self.assertRaises(PreviewProblem):
                bind_commit_claim(authority, replace(claim, **change), self.inputs)
        for input_change in (
            {"draft_revision": self.inputs.draft_revision + 1},
            {"previous_manifest_revision_id": new_uuid_v7()},
            {"request_id": new_uuid_v7()},
            {"parse_attempt_id": new_uuid_v7()},
        ):
            with self.subTest(change=input_change), self.assertRaises(PreviewProblem):
                bind_commit_claim(authority, claim, self.inputs.model_copy(update=input_change))

    def test_continuation_requires_exact_cancelled_predecessor(self):
        original = self.enqueue()
        self.queue.request_cancellation(
            original.job_id,
            actor=self.actor,
            now=self.now,
            reason_code="synthetic-cancel",
            interruption_kind="user-cancel",
        )
        continued = self.fixture.retry(original, 1)
        claim = self.queue.claim_next(
            worker_id=new_uuid_v7(),
            concurrency_classes=("document",),
            now=self.now,
            lease_duration_ms=30000,
            activity_types=(COMMIT_ACTIVITY,),
        )
        authority = self.queue.authority(continued.job_id)
        with self.assertRaises(PreviewProblem):
            bind_commit_claim(authority, claim, self.inputs)
        previous = self.queue.get(original.job_id), self.queue.authority(original.job_id)
        self.assertEqual(self.inputs, bind_commit_claim(authority, claim, self.inputs, predecessor=previous))
        substituted = replace(previous[0], state="succeeded"), previous[1]
        with self.assertRaises(PreviewProblem):
            bind_commit_claim(authority, claim, self.inputs, predecessor=substituted)


class ProtectedProfileQueueLineageTests(unittest.TestCase):
    def test_legacy_and_new_profiles_survive_queue_reload_and_do_not_duplicate_scientific_records(self):
        import hashlib
        import json
        from contextlib import closing
        from dataclasses import replace
        from pathlib import Path

        from research_observatory_core.ingestion.commit_activity import ImportCommitActivity
        from research_observatory_core.ingestion.commit_workflow import CommitJobInput, commit_job_input
        from research_observatory_core.ingestion.import_summaries import SUMMARY_ACTIVITY
        from research_observatory_core.ingestion.preview_activity import ImportPreviewActivity
        from research_observatory_core.ingestion.preview_workflow import (
            ACTIVITY,
            PreviewDelimitedJobInput,
            PreviewIntentContext,
            PreviewJobInput,
            bind_preview_claim,
            build_preview_job,
            preview_job_input,
        )
        from research_observatory_core.ingestion.protected_import_profiles import (
            LEGACY_LIMITS_HASH,
            PROTECTED_LIMITS_HASH,
        )
        from research_observatory_core.ingestion.summary_activity import ImportSummaryActivity
        from research_observatory_core.ingestion.summary_workflow import (
            SummaryJobInput,
            bind_summary_claim,
            build_summary_job,
            summary_job_input,
        )
        from research_observatory_core.ports.import_previews import PreviewDraftChange
        from research_observatory_core.repositories import (
            create_sqlite_unit_of_work_factory,
            sqlite_workflow_admission_binding,
            sqlite_workflow_queue_repository,
        )
        from research_observatory_core.storage import open_canonical_database
        from research_observatory_core.workflow_executor import (
            LocalAdmissionController,
            LocalWorkerSupervisor,
            ProjectWorkerPolicy,
            WorkerCapacity,
            WorkerResources,
        )

        from tests.data import test_import_preview_repository as data_fixture

        data = data_fixture.ImportPreviewRepositoryTests(methodName="runTest")
        lifecycle: unittest.TestCase = data
        lifecycle.setUp()
        self.addCleanup(lifecycle.tearDown)
        repository = data.repository()
        frozen = json.loads(
            (Path(__file__).parents[1] / "fixtures/imports/protected-preview-legacy120-authority-v1.json").read_text()
        )
        context = frozen["syntheticContext"]
        intent = PreviewIntentContext.model_validate_json(json.dumps(context["intent"]))
        raw = b"title,doi\nSynthetic,10.99999/EXAMPLE\n"
        now = "2026-08-30T12:02:00.000Z"
        database = data.project / "state/project.sqlite3"
        shared_mapping = None
        source_ids = None

        def run_job(kind: str, inputs: PreviewJobInput | PreviewDelimitedJobInput | SummaryJobInput | CommitJobInput):
            # Reconstruct the durable queue/admission before every activity, as
            # on an ordinary reader reload. Project/Intent/policy guard is an
            # explicit synthetic data-fixture boundary, not principal evidence.
            queue = sqlite_workflow_queue_repository(data.project, intent.project_id)
            if isinstance(inputs, SummaryJobInput):
                submission = build_summary_job(inputs, actor=data_fixture.worker_fixture.SYSTEM, now=now)
            elif isinstance(inputs, CommitJobInput):
                submission = build_commit_job(inputs, actor=data_fixture.worker_fixture.SYSTEM, now=now)
            else:
                submission = build_preview_job(inputs, actor=data_fixture.worker_fixture.SYSTEM, now=now)

            def bind(
                authority,
                claim,
                selected: PreviewJobInput | PreviewDelimitedJobInput | SummaryJobInput | CommitJobInput,
            ):
                if isinstance(selected, SummaryJobInput):
                    return bind_summary_claim(authority, claim, selected)
                if isinstance(selected, CommitJobInput):
                    return bind_commit_claim(authority, claim, selected)
                return bind_preview_claim(authority, claim, selected)

            job = queue.enqueue(submission, actor=data_fixture.worker_fixture.SYSTEM)
            self.assertEqual("runnable", job.state)
            demand = WorkerResources(1, 64 * 1024**2, 0, 1024**2)
            admission = sqlite_workflow_admission_binding(
                queue,
                controller=LocalAdmissionController(interactive_reserve=demand),
                policy=ProjectWorkerPolicy(intent.project_id, demand, {"document": demand}, {"document": 1}),
            )
            admission = replace(admission, capacity=lambda: WorkerCapacity(4, 1024**3, 0, 1024**3))

            def handler(execution, claim):
                authority = queue.authority(claim.job_id)
                self.assertEqual(inputs, bind(authority, claim, inputs))
                preview = inputs.preview if isinstance(inputs, (SummaryJobInput, CommitJobInput)) else inputs
                other = (
                    LEGACY_LIMITS_HASH if preview.parser_limits_hash == PROTECTED_LIMITS_HASH else PROTECTED_LIMITS_HASH
                )
                changed = preview.model_copy(update={"parser_limits_hash": other})
                forged = (
                    inputs.model_copy(update={"preview": changed})
                    if isinstance(inputs, (SummaryJobInput, CommitJobInput))
                    else changed
                )
                with self.assertRaises(PreviewProblem):
                    bind(authority, claim, forged)
                activity: ImportPreviewActivity | ImportSummaryActivity | ImportCommitActivity
                if isinstance(inputs, (PreviewJobInput, PreviewDelimitedJobInput)):
                    activity = ImportPreviewActivity(
                        preview_id=inputs.preview_id,
                        repository=repository,
                        store=data.store(),
                        unit_of_work=create_sqlite_unit_of_work_factory(database, intent.project_id),
                        guard=lambda action: action(),
                        trace_id="5" * 32,
                    )
                elif isinstance(inputs, SummaryJobInput):
                    activity = ImportSummaryActivity(
                        inputs=inputs,
                        repository=repository,
                        unit_of_work=create_sqlite_unit_of_work_factory(database, intent.project_id),
                        guard=lambda action: action(),
                        trace_id="5" * 32,
                    )
                else:
                    activity = ImportCommitActivity(
                        inputs=inputs, repository=repository, guard=lambda action: action(), trace_id="5" * 32
                    )
                return activity(execution, claim)

            worker = LocalWorkerSupervisor(
                queue,
                {kind: handler},
                concurrency_limits={"document": 1},
                now=lambda: now,
                recovery_actor=data_fixture.worker_fixture.SYSTEM,
                admission=admission,
                activity_types=(kind,),
            )
            completed = worker.run_available()
            self.assertEqual(1, len(completed))
            self.assertEqual("succeeded", completed[0].state, completed[0].diagnostic_code)
            return job.job_id

        for variant in ("missing-comma", "v1-comma", None):
            with self.subTest(variant=variant):
                preview = data.create_legacy(variant) if variant is not None else data.create()
                for index, chunk in enumerate(data.retain(raw), 1):
                    repository.append_chunk(preview, ordinal=index, chunk=chunk)
                state = repository.seal(
                    preview,
                    source_sha256=hashlib.sha256(raw).hexdigest(),
                    byte_length=len(raw),
                    chunk_count=1,
                    actor=data.actor(),
                )
                expected_hash = LEGACY_LIMITS_HASH if variant is not None else PROTECTED_LIMITS_HASH
                parsed = preview_job_input(state, intent, context["policyHash"], context["resumeEpoch"])
                self.assertEqual(expected_hash, parsed.parser_limits_hash)
                run_job(ACTIVITY, parsed)
                draft = repository.revise_draft(
                    preview, PreviewDraftChange(expected_revision=0, mapping=shared_mapping, actor=data.actor())
                )
                shared_mapping = draft.authority.mapping
                state = repository.read(preview)
                summary = summary_job_input(state, draft, intent, context["policyHash"], context["resumeEpoch"])
                run_job(SUMMARY_ACTIVITY, summary)
                self.assertIsNotNone(data.repository().summary(preview, revision=1))
                inputs = commit_job_input(
                    state,
                    draft,
                    intent,
                    context["policyHash"],
                    context["resumeEpoch"],
                    request_id=new_uuid_v7(),
                    previous_manifest_revision_id=None,
                )
                saved = repository.save_commit_request(inputs, actor=data.actor())
                self.assertEqual(saved, data.repository().commit_request(inputs.request_id))
                job_id = run_job(COMMIT_ACTIVITY, saved.inputs)
                manifest = data.repository().accepted_manifest(saved.inputs, job_id=job_id)
                self.assertEqual(2, manifest.record_count)
                self.assertEqual(saved, data.repository().commit_request(inputs.request_id))
                self.assertEqual(
                    expected_hash, data.repository().commit_request(inputs.request_id).inputs.preview.parser_limits_hash
                )
                with closing(open_canonical_database(database, expected_project_id=intent.project_id)) as connection:
                    current_ids = connection.execute(
                        "SELECT revision_id FROM import_source_records ORDER BY revision_id"
                    ).fetchall()
                if source_ids is None:
                    source_ids = current_ids
                    self.assertEqual(1, len(source_ids))
                else:
                    self.assertEqual(source_ids, current_ids)
