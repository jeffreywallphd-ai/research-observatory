"""Real encrypted object/SQLCipher/native-session/attempt fences; synthetic output."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.document_attachment_repository import LocalParserArtifactStager  # noqa: E402
from research_observatory_core.document_parser_runtime import InstalledNativeWorker, InstalledParser  # noqa: E402
from research_observatory_core.parsing.contracts import RawParserArtifact  # noqa: E402
from research_observatory_core.parsing.requests import ParseRequest  # noqa: E402
from research_observatory_core.parsing.selection import (  # noqa: E402
    ParserRegistry,
    RegisteredParser,
    SelectionSource,
    select_parser,
    selection_sha256,
)
from research_observatory_core.ports.object_store import ObjectNotFound, ObjectPutCommand  # noqa: E402
from research_observatory_core.ports.parsing import ParseProblem  # noqa: E402
from research_observatory_core.repositories import _SqliteWorkflowQueueRepository  # noqa: E402
from research_observatory_core.storage import CanonicalConnection, StorageProblem, open_canonical_database  # noqa: E402
from research_observatory_core.workflow_contracts import workflow_record_sha256  # noqa: E402
from research_observatory_core.workflow_executor import prepare_workflow_job  # noqa: E402

from tests.parsing import test_protected_parse_source as protected  # noqa: E402
from tests.workflows import test_local_workflow_executor as workflows  # noqa: E402


class ParserArtifactTests(unittest.TestCase):
    def setUp(self):
        f = self.f = protected.ProtectedParseSourceTests(methodName="runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.permit()
        self.database = f.fixture.corpus.database
        self.objects = f.fixture.store
        self.queue = _SqliteWorkflowQueueRepository(self.database, f.source.project_id)
        definition, snapshot, job_id = workflows.runnable_contracts()
        document = json.loads(json.dumps([definition, snapshot]).replace(workflows.PROJECT_ID, f.source.project_id))
        definition, snapshot = document
        definition["steps"][0]["activityType"] = (
            "source-acquisition"
            if self._testMethodName == "test_unrelated_admitted_job_cannot_execute_parser"
            else "document-parse"
        )
        snapshot["definition"]["contentHash"] = workflow_record_sha256(definition)
        self.queue.enqueue(
            prepare_workflow_job(
                definition,
                snapshot,
                job_id=job_id,
                concurrency_class="document",
                priority=0,
                available_at="2026-08-30T12:02:00.000Z",
            ),
            actor=workflows.SYSTEM,
        )
        claim = self.queue.claim_next(
            worker_id=workflows.WORKER_A,
            concurrency_classes=("document",),
            now="2026-08-30T12:02:00.000Z",
            lease_duration_ms=30_000,
        )
        assert claim is not None
        self.claim = claim
        self.queue.start(claim, now="2026-08-30T12:02:00.100Z")
        value = f.request.model_dump(mode="json", by_alias=True)
        value["binding"]["attempt"].update(jobId=claim.job_id, attemptId=claim.attempt_id)
        self.request = ParseRequest.model_validate(value)
        self.now = "2026-08-30T12:02:00.200Z"
        self.raw = b'{"synthetic-private-output":"local only"}'
        self.media = "application/vnd.research-observatory.native-structure+json"
        self.stager = self.make_stager(claim)

    def make_stager(self, claim):
        def guard(action):
            return self.f.preview.service.in_native_session(
                self.f.preview.root,
                self.f.source.project_id,
                self.f.session,
                action,
            )

        return LocalParserArtifactStager(
            self.database,
            self.objects,
            claim=claim,
            request=self.request,
            actor=lambda: self.f.actor,
            guard=guard,
            now=lambda: self.now,
        )

    def stage(self, *, stager=None, cancelled=lambda: False):
        return (stager or self.stager)(self.request, self.raw, media_type=self.media, cancelled=cancelled)

    def rows(self, table):
        with open_canonical_database(self.database, expected_project_id=self.f.source.project_id) as connection:
            if table == "workflow_attempt_artifacts":
                return tuple(
                    tuple(row)
                    for row in connection.execute(
                        "SELECT * FROM workflow_attempt_artifacts WHERE job_id=?",
                        (self.claim.job_id,),
                    )
                )
            return tuple(tuple(row) for row in connection.execute("SELECT * FROM " + table))

    def test_retained_raw_receipt_is_encrypted_durable_and_does_not_advance_original(self):
        before = self.rows("document_attachment_assertions")
        original = self.f.canonical()
        receipt = self.stage()
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), receipt.object_sha256)
        self.assertEqual(len(self.raw), receipt.byte_length)
        self.assertEqual(before, self.rows("document_attachment_assertions"))
        self.assertEqual(original, tuple(row for row in self.f.canonical() if row in original))
        self.assertEqual("project-encrypted-v1", self.objects.metadata(receipt.object_sha256).protection_profile)
        self.assertEqual(1, self.objects.metadata(receipt.object_sha256).reference_count)
        artifacts = self.rows("workflow_attempt_artifacts")
        self.assertEqual(2, len(artifacts))
        # Reopening SQLCipher and the queue preserves the original attempt output.
        restored = _SqliteWorkflowQueueRepository(self.database, self.f.source.project_id)
        self.assertEqual("running", restored.get(self.claim.job_id).state)
        outputs = self.rows("workflow_attempt_artifacts")
        self.assertEqual("retained-incomplete", outputs[0][6])
        self.assertIn(receipt.stage_id, [row[3] for row in outputs])
        manifest = next(row for row in outputs if row[8].endswith("parser-attempt+json"))
        with open_canonical_database(self.database, expected_project_id=self.f.source.project_id) as connection:
            digest = connection.execute(
                "SELECT object_sha256 FROM documents WHERE revision_id=?", (manifest[4],)
            ).fetchone()[0]
        with self.objects.open(digest, purpose="test-verification") as stream:
            retained = json.loads(stream.read())
        self.assertEqual(self.request, ParseRequest.model_validate(retained["request"]))
        self.assertEqual(receipt.object_sha256, retained["expectedRaw"]["sha256"])
        self.assertEqual("retained-parser-attempt-intent", retained["documentType"])
        self.assertNotIn(self.raw, self.database.read_bytes())
        # The private payload is absent from every file in the disposable project.
        for path in Path(self.f.preview.root).rglob("*"):
            if path.is_file():
                self.assertNotIn(self.raw, path.read_bytes())

    def test_rights_and_session_denial_publish_no_receipt_or_canonical_artifact(self):
        original = self.f.canonical()
        self.f.permit(derive="denied")
        with self.assertRaises(ParseProblem):
            self.stage()
        self.assertEqual(original, self.f.canonical())
        self.assertEqual((), self.rows("workflow_attempt_artifacts"))
        self.f.permit()
        self.f.preview.service.detach(self.f.preview.root)
        with self.assertRaises(ParseProblem):
            self.stage()
        self.assertEqual(original, self.f.canonical())

    def test_stale_lease_forged_capability_and_durable_cancel_cannot_publish(self):
        original = self.f.canonical()
        for forged in (replace(self.claim, lease_token="invalid"), replace(self.claim, activity_type="forged")):
            with self.subTest(field=forged.activity_type), self.assertRaises(ParseProblem):
                self.stage(stager=self.make_stager(forged))
        self.now = "2026-08-30T12:02:31.000Z"
        with self.assertRaises(ParseProblem):
            self.stage()
        self.now = "2026-08-30T12:02:00.200Z"
        self.queue.request_cancellation(
            self.claim.job_id,
            actor=workflows.SYSTEM,
            now=self.now,
            reason_code="user-cancel",
            interruption_kind="user-cancel",
        )
        with self.assertRaises(ParseProblem):
            self.stage()
        self.assertEqual(original, self.f.canonical())
        self.assertEqual((), self.rows("workflow_attempt_artifacts"))

    def test_current_rights_are_rechecked_after_encryption_and_failed_publication_rolls_back(self):
        original = self.f.canonical()
        put = self.objects.put_parser_artifact

        def revoke(raw, command, inspector, **kwargs):
            def inspect(*args):
                result = inspector(*args)
                self.f.permit(derive="denied")
                return result

            return put(raw, command, inspect, **kwargs)

        with (
            patch.object(type(self.objects), "put_parser_artifact", side_effect=revoke),
            self.assertRaises(ParseProblem),
        ):
            self.stage()
        self.assertEqual(original, self.f.canonical())
        self.assertEqual((), self.rows("workflow_attempt_artifacts"))
        with self.assertRaises(ObjectNotFound):
            self.objects.metadata(hashlib.sha256(self.raw).hexdigest())
        self.f.permit()
        with (
            patch.object(
                self.stager._queue, "_stage_artifact_with_connection", side_effect=RuntimeError("PRIVATE-FAILURE")
            ),
            self.assertRaises(ParseProblem) as problem,
        ):
            self.stage()
        self.assertNotIn("PRIVATE", str(problem.exception))
        self.assertEqual(original, self.f.canonical())
        self.assertEqual((), self.rows("workflow_attempt_artifacts"))

    def test_cancellation_after_encryption_cannot_publish(self):
        original = self.f.canonical()
        stopped = False
        put = self.objects.put_parser_artifact

        def stop(raw, command, inspector, **kwargs):
            nonlocal stopped

            def inspect(*args):
                nonlocal stopped
                result = inspector(*args)
                stopped = True
                return result

            return put(raw, command, inspect, **kwargs)

        with patch.object(type(self.objects), "put_parser_artifact", side_effect=stop), self.assertRaises(ParseProblem):
            self.stage(cancelled=lambda: stopped)
        self.assertEqual(original, self.f.canonical())
        self.assertEqual((), self.rows("workflow_attempt_artifacts"))

    def test_failure_between_manifest_and_raw_preserves_only_the_truthful_intent(self):
        stage = self.stager._queue._stage_artifact_with_connection

        def fail_raw(connection, claim, **kwargs):
            if kwargs["artifact"].media_type == self.media:
                raise RuntimeError("synthetic failure before raw publication")
            return stage(connection, claim, **kwargs)

        with (
            patch.object(self.stager._queue, "_stage_artifact_with_connection", side_effect=fail_raw),
            self.assertRaises(ParseProblem),
        ):
            self.stage()
        artifacts = self.rows("workflow_attempt_artifacts")
        self.assertEqual(1, len(artifacts))
        self.assertTrue(artifacts[0][8].endswith("parser-attempt+json"))
        with self.assertRaises(ObjectNotFound):
            self.objects.open(hashlib.sha256(self.raw).hexdigest(), purpose="test-verification")

    def test_raw_commit_failure_does_not_damage_a_preexisting_shared_object(self):
        digest = hashlib.sha256(self.raw).hexdigest()
        self.objects.put(
            BytesIO(self.raw),
            ObjectPutCommand(
                media_type=self.media,
                rights_status="allowed",
                protection_profile="project-encrypted-v1",
                retention_class="project-lifetime",
                creation_source="test-fixture",
                created_at=self.f.actor.occurred_at,
            ),
        )
        before = self.objects.metadata(digest)
        execute = CanonicalConnection.execute
        failed = False

        def fail_raw_commit(connection, sql, *args, **kwargs):
            nonlocal failed
            if (
                sql == "COMMIT"
                and execute(
                    connection,
                    "SELECT COUNT(*) FROM workflow_attempt_artifacts WHERE job_id=? AND media_type=?",
                    (self.claim.job_id, self.media),
                ).fetchone()[0]
            ):
                failed = True
                raise StorageProblem("synthetic raw commit failure")
            return execute(connection, sql, *args, **kwargs)

        with patch.object(CanonicalConnection, "execute", new=fail_raw_commit), self.assertRaises(ParseProblem):
            self.stage()
        self.assertTrue(failed)
        self.assertEqual(before, self.objects.metadata(digest))
        with self.objects.open(digest, purpose="test-verification") as stream:
            self.assertEqual(self.raw, stream.read())
        self.assertEqual(1, len(self.rows("workflow_attempt_artifacts")))

    def test_actual_commit_failure_never_returns_a_rolled_back_receipt(self):
        original = self.f.canonical()
        execute = CanonicalConnection.execute
        failed = False

        def reject_commit(connection, sql, *args, **kwargs):
            nonlocal failed
            if (
                sql == "COMMIT"
                and execute(
                    connection,
                    "SELECT COUNT(*) FROM workflow_attempt_artifacts WHERE job_id=?",
                    (self.claim.job_id,),
                ).fetchone()[0]
            ):
                failed = True
                raise StorageProblem("synthetic commit failure")
            return execute(connection, sql, *args, **kwargs)

        with patch.object(CanonicalConnection, "execute", new=reject_commit), self.assertRaises(ParseProblem):
            self.stage()
        self.assertTrue(failed)
        self.assertEqual(original, self.f.canonical())
        self.assertEqual((), self.rows("workflow_attempt_artifacts"))

    def test_manifest_substitution_cannot_publish_different_raw_bytes(self):
        first = self.stage()
        rows = self.rows("workflow_attempt_artifacts")
        intent = next(row for row in rows if row[8].endswith("parser-attempt+json"))
        with open_canonical_database(self.database, expected_project_id=self.f.source.project_id) as connection:
            digest = connection.execute(
                "SELECT object_sha256 FROM documents WHERE revision_id=?", (intent[4],)
            ).fetchone()[0]
        metadata = self.objects.metadata(digest)
        receipt = RawParserArtifact(
            stage_id=intent[3], object_sha256=digest, byte_length=metadata.byte_length, media_type=metadata.media_type
        )
        different = b'{"synthetic-private-output":"substitution"}'
        with self.assertRaises(ParseProblem):
            self.stager._retain(
                self.request, different, media_type=self.media, cancelled=lambda: False, manifest=receipt
            )
        self.assertEqual(rows, self.rows("workflow_attempt_artifacts"))
        with self.assertRaises(ObjectNotFound):
            self.objects.metadata(hashlib.sha256(different).hexdigest())
        with self.objects.open(first.object_sha256, purpose="test-verification") as stream:
            self.assertEqual(self.raw, stream.read())

    def test_real_restart_and_new_attempt_preserve_prior_raw_and_exact_request(self):
        first = self.stage()
        rows = self.rows("workflow_attempt_artifacts")
        recovered = _SqliteWorkflowQueueRepository(self.database, self.f.source.project_id)
        self.assertEqual(1, recovered.recover_expired(now="2026-08-30T12:02:31.000Z", actor=workflows.SYSTEM))
        claim = recovered.claim_next(
            worker_id=workflows.WORKER_B,
            concurrency_classes=("document",),
            now="2026-08-30T12:03:31.000Z",
            lease_duration_ms=30_000,
        )
        self.assertIsNotNone(claim)
        assert claim is not None
        recovered.start(claim, now="2026-08-30T12:03:31.100Z")
        self.now = "2026-08-30T12:03:31.200Z"
        value = self.request.model_dump(mode="json", by_alias=True)
        value["binding"]["attempt"].update(jobId=claim.job_id, attemptId=claim.attempt_id)
        self.request = ParseRequest.model_validate(value)
        second = self.stage(stager=self.make_stager(claim))
        self.assertNotEqual(first.stage_id, second.stage_id)
        self.assertEqual(first.object_sha256, second.object_sha256)
        all_rows = self.rows("workflow_attempt_artifacts")
        self.assertEqual(4, len(all_rows))
        self.assertEqual({row[3] for row in rows}, {row[3] for row in all_rows if row[0] == self.claim.attempt_id})
        self.assertEqual(2, self.objects.metadata(first.object_sha256).reference_count)
        with self.objects.open(first.object_sha256, purpose="test-verification") as stream:
            self.assertEqual(self.raw, stream.read())

    def test_stale_or_cancelled_attempt_is_rejected_before_runtime_execution(self):
        from unittest.mock import Mock

        runtime = Mock()
        worker = InstalledNativeWorker(runtime, InstalledParser(object(), self.request.binding.producer), self.stager)
        self.now = "2026-08-30T12:02:31.000Z"
        with self.assertRaises(ParseProblem):
            worker.parse_source(self.request, BytesIO(b"synthetic"), cancelled=lambda: False)
        runtime.run.assert_not_called()
        self.now = "2026-08-30T12:02:00.200Z"
        self.queue.request_cancellation(
            self.claim.job_id,
            actor=workflows.SYSTEM,
            now=self.now,
            reason_code="user-cancel",
            interruption_kind="user-cancel",
        )
        with self.assertRaises(ParseProblem):
            worker.parse_source(self.request, BytesIO(b"synthetic"), cancelled=lambda: False)
        runtime.run.assert_not_called()
        self.assertEqual((), self.rows("workflow_attempt_artifacts"))

    def test_exact_parent_selected_request_cannot_be_substituted_within_attempt(self):
        producer = self.request.binding.producer.model_copy(update={"configuration_sha256": "f" * 64})
        selection = select_parser(
            (SelectionSource(self.f.source, "available", "primary"),),
            ParserRegistry((RegisteredParser(producer, "available"),)),
            primary_attachment_id=self.f.source.attachment_id,
        )
        different = ParseRequest(
            schema_version="1.0",
            selection=selection,
            binding=self.request.binding.model_copy(
                update={"producer": producer, "selection_sha256": selection_sha256(selection)}
            ),
        )
        with self.assertRaises(ParseProblem):
            self.stager.validate_request(different)
        with self.assertRaises(ParseProblem):
            self.stager(different, self.raw, media_type=self.media, cancelled=lambda: False)
        self.assertEqual((), self.rows("workflow_attempt_artifacts"))

    def test_unrelated_admitted_job_cannot_execute_parser(self):
        from unittest.mock import Mock

        runtime = Mock()
        worker = InstalledNativeWorker(runtime, InstalledParser(object(), self.request.binding.producer), self.stager)
        with self.assertRaises(ParseProblem):
            worker.parse_source(self.request, BytesIO(b"synthetic"), cancelled=lambda: False)
        runtime.run.assert_not_called()
        self.assertEqual((), self.rows("workflow_attempt_artifacts"))


if __name__ == "__main__":
    unittest.main()
