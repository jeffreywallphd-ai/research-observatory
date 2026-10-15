"""Exact import job binding and real durable-supervisor integration."""

from __future__ import annotations

import hashlib
import itertools
import json
import unittest
from dataclasses import replace
from pathlib import Path

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.preview_workflow import (
    ACTIVITY,
    PreviewIntentContext,
    PreviewJobInput,
    bind_preview_claim,
    build_preview_job,
    preview_job_input,
)
from research_observatory_core.ports.import_previews import PreviewActor, PreviewProblem
from research_observatory_core.repositories import (
    create_sqlite_unit_of_work_factory,
    sqlite_workflow_admission_binding,
    sqlite_workflow_queue_repository,
)
from research_observatory_core.workflow_contracts import workflow_snapshot_errors
from research_observatory_core.workflow_executor import (
    LocalAdmissionController,
    LocalWorkerSupervisor,
    ProjectWorkerPolicy,
    WorkerCapacity,
    WorkerResources,
    prepare_workflow_job,
)

from tests.data import test_import_preview_repository as fixture


class ImportPreviewWorkflowTests(unittest.TestCase):
    def test_frozen_comma_job_survives_queue_reload_without_definition_drift(self):
        # Literal output captured from f44e175c before delimiter integration.
        document = json.loads((Path(__file__).parents[1] / "fixtures/imports/preview-job-comma-v1.json").read_text())
        inputs = PreviewJobInput.model_validate(document["inputs"])
        old = document["submission"]
        submission = prepare_workflow_job(
            json.loads(old["definition_json"]),
            json.loads(old["snapshot_json"]),
            job_id=old["job_id"],
            concurrency_class="document",
            priority=0,
            available_at=old["available_at"],
        )
        self.assertEqual(old["command_fingerprint"], inputs.configuration_hash)
        self.assertEqual(old["definition_record_sha256"], submission.definition_record_sha256)
        queue = sqlite_workflow_queue_repository(self.fixture.project, inputs.project_id)
        queue.enqueue(submission, actor=fixture.worker_fixture.SYSTEM)
        # Reconstruct the adapter as on restart; do not rebuild the old definition.
        queue = sqlite_workflow_queue_repository(self.fixture.project, inputs.project_id)
        claim = queue.claim_next(
            worker_id=fixture.worker_fixture.WORKER_A,
            concurrency_classes=("document",),
            now=self.now,
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.assertEqual(inputs, bind_preview_claim(queue.authority(claim.job_id), claim, inputs))

    def test_noncomma_input_is_versioned_and_cannot_substitute_for_queued_comma(self):
        queue, claim = self.claimed()
        hashes = {self.input.configuration_hash}
        for delimiter in ("\t", ";"):
            state = self.state.model_copy(update={"delimiter": delimiter})
            selected = preview_job_input(state, self.intent, self.policy, self.epoch)
            self.assertEqual(delimiter, selected.delimiter)
            self.assertEqual("1.1", selected.schema_version)
            hashes.add(selected.configuration_hash)
            job = build_preview_job(selected, actor=fixture.worker_fixture.SYSTEM, now=self.now)
            self.assertEqual("1.1.0", json.loads(job.definition_json)["definitionVersion"])
            with self.assertRaises(PreviewProblem):
                bind_preview_claim(queue.authority(claim.job_id), claim, selected)
        self.assertEqual(3, len(hashes))

    def setUp(self):
        self.fixture = fixture.ImportPreviewRepositoryTests(methodName="runTest")
        lifecycle: unittest.TestCase = self.fixture
        lifecycle.setUp()
        self.addCleanup(lifecycle.tearDown)
        raw = b"title,doi\nSynthetic,10.99999/EXAMPLE\n"
        self.preview = self.fixture.create()
        for ordinal, chunk in enumerate(self.fixture.retain(raw), 1):
            self.fixture.repository().append_chunk(self.preview, ordinal=ordinal, chunk=chunk)
        self.state = self.fixture.repository().seal(
            self.preview,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            actor=self.fixture.actor(),
        )
        # Explicit synthetic references here; runtime composition must obtain
        # actual validated project-created intent and current privacy policy.
        self.intent = PreviewIntentContext(
            project_id=self.state.project_id,
            domain_project_id=new_uuid_v7(),
            intent_id=new_uuid_v7(),
            revision_id=new_uuid_v7(),
            content_hash="sha256:" + "1" * 64,
            status="draft",
        )
        self.policy = "sha256:" + "2" * 64
        self.epoch = "3" * 32
        self.input = preview_job_input(self.state, self.intent, self.policy, self.epoch)
        self.now = "2026-08-30T12:02:00.000Z"

    def submission(self):
        return build_preview_job(self.input, actor=fixture.worker_fixture.SYSTEM, now=self.now)

    def claimed(self):
        submission = self.submission()
        queue = sqlite_workflow_queue_repository(self.fixture.project, self.state.project_id)
        queue.enqueue(submission, actor=fixture.worker_fixture.SYSTEM)
        claim = queue.claim_next(
            worker_id=fixture.worker_fixture.WORKER_A,
            concurrency_classes=("document",),
            now=self.now,
            lease_duration_ms=30_000,
        )
        assert claim is not None
        return queue, claim

    def test_draft_context_and_exact_declarative_local_authority(self):
        submission = self.submission()
        definition, snapshot = json.loads(submission.definition_json), json.loads(submission.snapshot_json)
        self.assertEqual((), workflow_snapshot_errors(definition, snapshot))
        self.assertEqual(self.intent.revision_id, snapshot["intent"]["revisionId"])
        self.assertEqual("draft", self.input.intent.status)
        self.assertEqual("unknown", submission.progress_total_kind)
        self.assertEqual("records", submission.progress_unit)
        permissions = definition["steps"][0]["permissions"]
        self.assertEqual("none", permissions["network"])
        self.assertEqual("none", permissions["model"])
        self.assertNotIn(self.state.source_name, submission.snapshot_json)
        self.assertEqual([], snapshot["artifacts"])
        self.assertEqual(5, len(snapshot["history"]))

    def test_reloaded_claim_binds_source_intent_policy_epoch_and_worker_identity(self):
        queue, claim = self.claimed()
        authority = queue.authority(claim.job_id)
        self.assertEqual(self.input, bind_preview_claim(authority, claim, self.input))
        for changed in (
            self.input.model_copy(update={"source_sha256": "4" * 64}),
            self.input.model_copy(update={"resume_epoch": "4" * 32}),
            self.input.model_copy(update={"policy_hash": "sha256:" + "4" * 64}),
            self.input.model_copy(update={"intent": self.intent.model_copy(update={"status": "accepted"})}),
            self.input.model_copy(update={"project_id": new_uuid_v7()}),
        ):
            with self.subTest(changed=changed.model_dump()), self.assertRaises(PreviewProblem):
                bind_preview_claim(authority, claim, changed)
        with self.assertRaises(PreviewProblem):
            bind_preview_claim(authority, replace(claim, job_id=new_uuid_v7()), self.input)

    def test_cross_project_intent_and_unsealed_source_are_denied(self):
        with self.assertRaises(PreviewProblem):
            preview_job_input(
                self.state, self.intent.model_copy(update={"project_id": new_uuid_v7()}), self.policy, self.epoch
            )
        with self.assertRaises(PreviewProblem):
            preview_job_input(
                self.state.model_copy(update={"source_sha256": None}), self.intent, self.policy, self.epoch
            )

    def supervisor(self, queue, *, capacity=None, guard=None):
        from research_observatory_core.ingestion.preview_activity import ImportPreviewActivity

        ticks = itertools.count(0, 6)
        activity = ImportPreviewActivity(
            preview_id=self.preview,
            repository=self.fixture.repository(),
            store=self.fixture.store(),
            unit_of_work=create_sqlite_unit_of_work_factory(
                self.fixture.project / "state/project.sqlite3", self.state.project_id
            ),
            guard=guard or (lambda action: action()),
            trace_id="5" * 32,
            clock=lambda: float(next(ticks)),
        )

        def handler(context, claim):
            bind_preview_claim(queue.authority(claim.job_id), claim, self.input)
            return activity(context, claim)

        demand = WorkerResources(1, 64 * 1024 * 1024, 0, 1024 * 1024)
        controller = LocalAdmissionController(interactive_reserve=demand)
        admission = sqlite_workflow_admission_binding(
            queue,
            controller=controller,
            policy=ProjectWorkerPolicy(self.state.project_id, demand, {"document": demand}, {"document": 1}),
        )
        # Actual volume/database binding; deterministic capacity observations,
        # not a claim about platform resource measurements.
        admission = replace(admission, capacity=capacity or (lambda: WorkerCapacity(4, 1024**3, 0, 1024**3)))
        return LocalWorkerSupervisor(
            queue,
            {ACTIVITY: handler},
            concurrency_limits={"document": 1},
            now=lambda: self.now,
            recovery_actor=fixture.worker_fixture.SYSTEM,
            admission=admission,
            activity_types=(ACTIVITY,),
        )

    def test_import_worker_does_not_claim_other_document_activities(self):
        queue = sqlite_workflow_queue_repository(self.fixture.project, self.state.project_id)
        definition, snapshot, other_job = fixture.worker_fixture.runnable_contracts()
        snapshot["projectId"] = self.state.project_id
        queue.enqueue(
            prepare_workflow_job(
                definition,
                snapshot,
                job_id=other_job,
                concurrency_class="document",
                priority=100,
                available_at=self.now,
            ),
            actor=fixture.worker_fixture.SYSTEM,
        )
        submission = self.submission()
        imported = queue.enqueue(submission, actor=fixture.worker_fixture.SYSTEM)
        self.assertEqual(imported, queue.find_idempotency(submission.idempotency_key))
        self.assertIsNone(queue.find_idempotency("sha256:" + "f" * 64))
        self.assertEqual((imported,), queue.active_jobs(activity_type=ACTIVITY, after=None, limit=1))
        self.assertEqual((), queue.active_jobs(activity_type=ACTIVITY, after=imported.job_id, limit=1))
        self.assertEqual("succeeded", self.supervisor(queue).run_available()[0].state)
        self.assertEqual(0, queue.get(other_job).attempt_count)
        self.assertEqual((), queue.active_jobs(activity_type=ACTIVITY, after=None, limit=1))

    def test_supervisor_admission_heartbeat_receipt_and_completed_preview(self):
        queue = sqlite_workflow_queue_repository(self.fixture.project, self.state.project_id)
        job = queue.enqueue(self.submission(), actor=fixture.worker_fixture.SYSTEM)
        starved = self.supervisor(queue, capacity=lambda: WorkerCapacity(1, 1, 0, 1))
        self.assertEqual((), starved.run_available())
        self.assertEqual(0, queue.get(job.job_id).attempt_count)
        completed = self.supervisor(queue).run_available()
        self.assertEqual("succeeded", completed[0].state, completed[0].diagnostic_code)
        self.assertEqual(2, len(self.fixture.repository().records_page(self.preview, after=0, limit=10)))
        self.assertEqual((), self.supervisor(queue).run_available())
        self.assertEqual(1, queue.get(job.job_id).attempt_count)

    def test_expired_ordinary_attempt_replays_from_immutable_source(self):
        queue, first = self.claimed()
        queue.start(first, now=self.now)
        self.fixture.repository().begin_parse(
            self.preview,
            claim=first,
            actor=PreviewActor(actor_id=first.worker_id, trace_id="5" * 32, occurred_at=self.now),
        )
        self.now = "2026-08-30T12:03:00.000Z"
        self.assertEqual("succeeded", self.supervisor(queue).run_available()[0].state)
        self.assertEqual(2, queue.get(first.job_id).attempt_count)
        self.assertEqual((), self.supervisor(queue).run_available())

    def test_security_cancel_fences_pending_parse_and_late_outputs(self):
        queue, first = self.claimed()
        queue.start(first, now=self.now)
        queue.request_cancellation(
            first.job_id,
            actor=fixture.worker_fixture.SYSTEM,
            now=self.now,
            reason_code="application-locked",
            interruption_kind="security-lock",
        )
        self.now = "2026-08-30T12:04:00.000Z"
        self.assertEqual((), self.supervisor(queue).run_available())
        self.assertEqual("cancelled", queue.get(first.job_id).state)
        self.assertEqual(1, queue.get(first.job_id).attempt_count)
        with self.assertRaises(PreviewProblem):
            self.fixture.repository().records_page(self.preview, after=0, limit=10)


class ProtectedImportProfileCompatibilityTests(unittest.TestCase):
    def captured(self):
        return json.loads(
            (Path(__file__).parents[1] / "fixtures/imports/protected-preview-legacy120-authority-v1.json").read_text()
        )

    def fresh_claim(self, stage):
        data = fixture.ImportPreviewRepositoryTests(methodName="runTest")
        lifecycle: unittest.TestCase = data
        lifecycle.setUp()
        self.addCleanup(lifecycle.tearDown)
        old = stage["authority"]
        job = stage["job"]
        submission = prepare_workflow_job(
            json.loads(old["definition_json"]),
            json.loads(old["snapshot_json"]),
            job_id=job["job_id"],
            concurrency_class="document",
            priority=job["priority"],
            available_at=job["available_at"],
        )
        self.assertEqual(old["definition_record_sha256"], submission.definition_record_sha256)
        self.assertEqual(old["snapshot_record_sha256"], submission.snapshot_record_sha256)
        queue = sqlite_workflow_queue_repository(data.project, fixture.fixture.PROJECT_ID)
        queue.enqueue(submission, actor=fixture.worker_fixture.SYSTEM)
        claim = queue.claim_next(
            worker_id=fixture.worker_fixture.WORKER_A,
            concurrency_classes=("document",),
            now=job["available_at"],
            lease_duration_ms=30000,
        )
        self.assertIsNotNone(claim)
        return queue.authority(job["job_id"]), claim

    def test_new_creation_persists900_before_scheduling(self):
        from contextlib import closing

        from research_observatory_core.storage import open_canonical_database

        data = fixture.ImportPreviewRepositoryTests(methodName="runTest")
        lifecycle: unittest.TestCase = data
        lifecycle.setUp()
        self.addCleanup(lifecycle.tearDown)
        preview = data.create()
        with closing(
            open_canonical_database(
                data.project / "state/project.sqlite3", expected_project_id=fixture.fixture.PROJECT_ID
            )
        ) as connection:
            row = connection.execute(
                "SELECT text_value FROM settings WHERE setting_key=?", ("imports.preview." + preview,)
            ).fetchone()
        self.assertEqual("1.1", json.loads(row[0])["schemaVersion"])
        self.assertEqual("protected-preview-900s-v1", json.loads(row[0])["parserProfile"])
        self.assertEqual(
            "sha256:eee2a0c5d0b4c8a2ea8b13d393819f4807aa51f2b4ad95cc78168654dd122495",
            json.loads(row[0])["parserLimitsHash"],
        )

    def test_two_frozen_profiles_preserve_pure_default_and_all_other_limits(self):
        from dataclasses import asdict
        from typing import cast

        from research_observatory_core.ingestion.protected_import_profiles import (
            LEGACY_LIMITS_HASH,
            LEGACY_PROFILE,
            PROTECTED_LIMITS_HASH,
            PROTECTED_PROFILE,
            ParserProfile,
            profile_limits,
            profile_limits_hash,
        )
        from research_observatory_core.ingestion.reference_imports import ImportLimits

        old, new = profile_limits(LEGACY_PROFILE), profile_limits(PROTECTED_PROFILE)
        self.assertEqual(120.0, ImportLimits().max_seconds)
        self.assertEqual(120.0, old.max_seconds)
        self.assertEqual(900.0, new.max_seconds)
        self.assertIs(type(new.max_seconds), float)
        left, right = asdict(old), asdict(new)
        left.pop("max_seconds")
        right.pop("max_seconds")
        self.assertEqual(left, right)
        self.assertEqual(LEGACY_LIMITS_HASH, profile_limits_hash(LEGACY_PROFILE))
        self.assertEqual(PROTECTED_LIMITS_HASH, profile_limits_hash(PROTECTED_PROFILE))
        for unknown in ("", "legacy", "protected-preview-901s-v1", 900, None):
            with self.subTest(unknown=unknown), self.assertRaises(ValueError):
                # Deliberately violate the static profile type to prove runtime denial.
                profile_limits(cast(ParserProfile, unknown))

    def test_predecessor_input_schemas_remain_byte_equivalent(self):
        from research_observatory_core.ingestion.commit_workflow import CommitJobInput
        from research_observatory_core.ingestion.preview_workflow import PreviewDelimitedJobInput
        from research_observatory_core.ingestion.summary_workflow import SummaryJobInput

        for model in (PreviewJobInput, PreviewDelimitedJobInput, SummaryJobInput, CommitJobInput):
            with self.subTest(model=model.__name__):
                self.assertEqual(self.captured()["schemas"][model.__name__], model.model_json_schema())

    def test_old_unscheduled_inputs_and_all_queued_authorities_reconstruct_exactly(self):
        from research_observatory_core.ingestion.commit_workflow import (
            CommitJobInput,
            bind_commit_claim,
            commit_job_input,
        )
        from research_observatory_core.ingestion.preview_workflow import PreviewDelimitedJobInput
        from research_observatory_core.ingestion.protected_import_profiles import LEGACY_PROFILE
        from research_observatory_core.ingestion.summary_workflow import (
            SummaryJobInput,
            bind_summary_claim,
            summary_job_input,
        )
        from research_observatory_core.ports.import_previews import PreviewDraft, PreviewState

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

        document = self.captured()
        intent = PreviewIntentContext.model_validate_json(json.dumps(document["syntheticContext"]["intent"]))
        for case in document["cases"]:
            with self.subTest(variant=case["variant"]):
                state = PreviewState.model_validate_json(json.dumps(case["unscheduled"]["state"]))
                self.assertEqual(LEGACY_PROFILE, state.parser_profile)
                inputs = preview_job_input(
                    state,
                    intent,
                    document["syntheticContext"]["policyHash"],
                    document["syntheticContext"]["resumeEpoch"],
                )
                self.assertEqual(case["unscheduled"]["inputs"], inputs.model_dump(mode="json", by_alias=True))
                self.assertEqual(case["unscheduled"]["configurationHash"], inputs.configuration_hash)
                draft = PreviewDraft.model_validate_json(json.dumps(case["draft"]))
                summary = summary_job_input(state, draft, intent, inputs.policy_hash, inputs.resume_epoch)
                saved = case["savedCommitRequest"]["inputs"]
                commit = commit_job_input(
                    state,
                    draft,
                    intent,
                    inputs.policy_hash,
                    inputs.resume_epoch,
                    request_id=saved["requestId"],
                    previous_manifest_revision_id=saved["previousManifestRevisionId"],
                )
                self.assertEqual(case["pendingSummary"]["inputs"], summary.model_dump(mode="json", by_alias=True))
                self.assertEqual(saved, commit.model_dump(mode="json", by_alias=True))
                self.assertEqual(case["savedCommitRequest"]["configurationHash"], commit.configuration_hash)
                for selected, key in (
                    (inputs, "pendingPreview"),
                    (summary, "pendingSummary"),
                    (commit, "pendingCommit"),
                ):
                    authority, claim = self.fresh_claim(case[key])
                    self.assertEqual(selected, bind(authority, claim, selected))

    def test_known_new_hash_cannot_replace_old_queued_profile(self):
        from research_observatory_core.ingestion.protected_import_profiles import PROTECTED_LIMITS_HASH

        for case in self.captured()["cases"]:
            old = case["unscheduled"]["inputs"]
            model = (
                PreviewJobInput
                if old["schemaVersion"] == "1.0"
                else __import__(
                    "research_observatory_core.ingestion.preview_workflow", fromlist=["PreviewDelimitedJobInput"]
                ).PreviewDelimitedJobInput
            )
            inputs = model.model_validate_json(json.dumps(old))
            authority, claim = self.fresh_claim(case["pendingPreview"])
            with self.assertRaises(PreviewProblem):
                bind_preview_claim(
                    authority, claim, inputs.model_copy(update={"parser_limits_hash": PROTECTED_LIMITS_HASH})
                )
            for bad in ("sha256:" + "0" * 64, "sha256:" + "f" * 64):
                with self.assertRaises(ValueError):
                    model.model_validate_json(json.dumps({**old, "parserLimitsHash": bad}))

    def test_old_accepted_summary_receipts_keep_exact_fingerprint_and_version(self):
        from research_observatory_core.ingestion.import_summaries import (
            SummaryResult,
            summary_receipt_fingerprint,
            summary_receipt_version,
        )
        from research_observatory_core.ingestion.protected_import_profiles import (
            LEGACY_LIMITS_HASH,
            PROTECTED_LIMITS_HASH,
        )

        for case in self.captured()["cases"]:
            summary = case["acceptedSummary"]
            inputs = case["pendingSummary"]["inputs"]
            arguments = dict(
                project_id=summary["projectId"],
                preview_id=summary["previewId"],
                job_id=summary["jobId"],
                summary_attempt_id=summary["summaryAttemptId"],
                parse_attempt_id=summary["parseAttemptId"],
                draft_revision=summary["draftRevision"],
                source_sha256=inputs["preview"]["sourceSha256"],
                manifest_sha256=inputs["preview"]["manifestSha256"],
                result=SummaryResult.model_validate_json(json.dumps(summary["result"])),
            )
            original = next(
                row
                for row in case["summaryReceipt"]["material_dependencies"]
                if row["configuration_id"] == "import.draft-summary"
            )
            self.assertEqual(original["fingerprint"], summary_receipt_fingerprint(**arguments))
            self.assertEqual(
                original["fingerprint"], summary_receipt_fingerprint(**arguments, parser_limits_hash=LEGACY_LIMITS_HASH)
            )
            self.assertEqual(original["configuration_version"], summary_receipt_version(LEGACY_LIMITS_HASH))
            self.assertNotEqual(
                original["fingerprint"],
                summary_receipt_fingerprint(**arguments, parser_limits_hash=PROTECTED_LIMITS_HASH),
            )
            self.assertEqual("2.0.0", summary_receipt_version(PROTECTED_LIMITS_HASH))
            with self.assertRaises(ValueError):
                summary_receipt_fingerprint(**arguments, parser_limits_hash="sha256:" + "0" * 64)


if __name__ == "__main__":
    unittest.main()
