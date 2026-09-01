from __future__ import annotations

import copy
import json
import sys
import unittest
from hashlib import sha256
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
CORE_SRC = REPO / "services" / "core-api" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from research_observatory_core.workflow_contracts import (  # noqa: E402
    WORKFLOW_SCHEMA_SHA256,
    canonical_workflow_json,
    decode_legacy_operation_bridge,
    decode_workflow_definition,
    decode_workflow_snapshot,
    legacy_operation_bridge_errors,
    reconstruct_workflow_state,
    workflow_definition_errors,
    workflow_record_sha256,
    workflow_snapshot_errors,
    workflow_transition_allowed,
)

JsonRecord = dict[str, object]


class WorkflowContractTests(unittest.TestCase):
    root: Path
    schema_path: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = REPO / "packages" / "contracts" / "workflow"
        cls.schema_path = cls.root / "workflow-contract.schema.json"

    def fixture(self, name: str) -> JsonRecord:
        return cast(
            JsonRecord,
            json.loads((self.root / "fixtures" / name).read_text(encoding="utf-8")),
        )

    def definition(self) -> JsonRecord:
        return self.fixture("valid-workflow-definition.v1.json")

    def snapshot(self, profile: str = "local") -> JsonRecord:
        snapshot = self.fixture("valid-local-workflow-snapshot.v1.json")
        if profile == "server":
            snapshot["snapshotId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86d007"
            snapshot["executor"] = {
                "profile": "server",
                "adapterId": "server-conformant-workflow",
                "adapterVersion": "1.0.0",
                "contractVersion": "1.0.0",
            }
        return snapshot

    @staticmethod
    def items(snapshot: JsonRecord, key: str) -> list[JsonRecord]:
        return cast(list[JsonRecord], snapshot[key])

    def test_strict_schema_and_generated_runtime_accept_the_portable_definition(self) -> None:
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        definition = self.definition()
        self.assertEqual(
            [],
            list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(definition)),
        )
        self.assertEqual((), workflow_definition_errors(definition))
        decoded = decode_workflow_definition(definition)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        before = canonical_workflow_json(decoded)
        cast(list[JsonRecord], definition["steps"])[0]["activityType"] = "changed"
        self.assertEqual(before, canonical_workflow_json(decoded))
        self.assertNotIn("executor", before)
        self.assertNotIn("Temporal", before)
        self.assertNotIn("C:\\\\", before)

    def test_one_definition_is_conformant_for_local_and_server_executor_snapshots(self) -> None:
        definition = self.definition()
        expected_hash = workflow_record_sha256(definition)
        snapshots = [self.snapshot("local"), self.snapshot("server")]
        self.assertEqual("local", cast(JsonRecord, snapshots[0]["executor"])["profile"])
        self.assertEqual("server", cast(JsonRecord, snapshots[1]["executor"])["profile"])
        for snapshot in snapshots:
            with self.subTest(profile=cast(JsonRecord, snapshot["executor"])["profile"]):
                self.assertEqual(expected_hash, cast(JsonRecord, snapshot["definition"])["contentHash"])
                self.assertEqual((), workflow_snapshot_errors(definition, snapshot))
                self.assertIsNotNone(decode_workflow_snapshot(definition, snapshot))

        polluted = self.definition()
        polluted["executor"] = "sqlite"
        self.assertIsNone(decode_workflow_definition(polluted))

        path_smuggling = self.definition()
        cast(list[JsonRecord], path_smuggling["steps"])[0]["activityType"] = r"C:\tools\run.exe"
        self.assertIsNone(decode_workflow_definition(path_smuggling))

        future_version = self.definition()
        future_version["contractVersion"] = "2.0.0"
        self.assertIsNone(decode_workflow_definition(future_version))

    def test_ordered_history_reconstructs_exact_projection_after_restart(self) -> None:
        definition = self.definition()
        snapshot = self.snapshot()
        canonical = canonical_workflow_json(snapshot)
        restarted = cast(JsonRecord, json.loads(canonical))
        self.assertEqual((), workflow_snapshot_errors(definition, restarted))
        self.assertEqual(canonical, canonical_workflow_json(restarted))
        state = reconstruct_workflow_state(definition, restarted)
        self.assertEqual(restarted["state"], state["workflow-run"][cast(str, restarted["workflowRunId"])])
        for collection, entity_kind, id_key in (
            ("stepRuns", "workflow-step", "stepRunId"),
            ("jobs", "job", "jobId"),
            ("attempts", "job-attempt", "attemptId"),
            ("humanTasks", "human-task", "humanTaskId"),
        ):
            for item in self.items(restarted, collection):
                self.assertEqual(item["state"], state[entity_kind][cast(str, item[id_key])])

        missing = copy.deepcopy(snapshot)
        cast(list[object], missing["history"]).pop(10)
        self.assertIn("history-sequence-is-contiguous", workflow_snapshot_errors(definition, missing))

        wrong_projection = copy.deepcopy(snapshot)
        self.items(wrong_projection, "jobs")[0]["state"] = "failed"
        self.assertIn("history-reconstructs-current-state", workflow_snapshot_errors(definition, wrong_projection))

    def test_transition_progress_and_retry_invariants_fail_closed(self) -> None:
        definition = self.definition()
        snapshot = self.snapshot()
        self.assertFalse(workflow_transition_allowed("workflow-run", "succeeded", "running"))
        self.assertTrue(workflow_transition_allowed("job", "running", "retry-scheduled"))

        outbound = copy.deepcopy(snapshot)
        history = self.items(outbound, "history")
        last = copy.deepcopy(history[-1])
        last.update(
            {
                "eventId": "018f47a2-4d6b-7f78-9f2e-7fb76c86e099",
                "sequence": cast(int, outbound["sequence"]) + 1,
                "fromState": "succeeded",
                "toState": "running",
                "reasonCode": "restart-illegal",
            }
        )
        outbound["sequence"] = cast(int, outbound["sequence"]) + 1
        outbound["state"] = "running"
        history.append(last)
        self.assertIn("history-transition-is-allowed", workflow_snapshot_errors(definition, outbound))

        decreasing = copy.deepcopy(snapshot)
        attempt_events = [
            event
            for event in self.items(decreasing, "history")
            if event["entityType"] == "job-attempt" and event["progress"] is not None
        ]
        cast(JsonRecord, attempt_events[-1]["progress"])["completedUnits"] = 40
        self.assertIn("attempt-progress-is-monotonic", workflow_snapshot_errors(definition, decreasing))

        duplicate_success = copy.deepcopy(snapshot)
        attempts = self.items(duplicate_success, "attempts")
        attempts[0]["state"] = "succeeded"
        self.assertIn("job-has-at-most-one-succeeded-attempt", workflow_snapshot_errors(definition, duplicate_success))

        gap = copy.deepcopy(snapshot)
        self.items(gap, "attempts")[1]["attemptNumber"] = 3
        self.assertIn("attempt-numbers-are-contiguous", workflow_snapshot_errors(definition, gap))

        changed_command = copy.deepcopy(snapshot)
        jobs = self.items(changed_command, "jobs")
        duplicate_job = copy.deepcopy(jobs[0])
        duplicate_job.update(
            {
                "jobId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d099",
                "commandFingerprint": f"sha256:{'d' * 64}",
                "attemptIds": [],
                "currentAttemptId": None,
                "state": "pending",
            }
        )
        jobs.append(duplicate_job)
        self.assertIn(
            "job-idempotency-binds-command-fingerprint",
            workflow_snapshot_errors(definition, changed_command),
        )

    def test_reference_checkpoint_artifact_and_definition_substitutions_are_rejected(self) -> None:
        definition = self.definition()
        snapshot = self.snapshot()

        wrong_definition = copy.deepcopy(snapshot)
        cast(JsonRecord, wrong_definition["definition"])["contentHash"] = f"sha256:{'0' * 64}"
        self.assertIn("snapshot-binds-exact-definition", workflow_snapshot_errors(definition, wrong_definition))

        wrong_step = copy.deepcopy(snapshot)
        self.items(wrong_step, "stepRuns")[0]["stepKey"] = "substituted-step"
        self.assertIn("references-close-over-snapshot", workflow_snapshot_errors(definition, wrong_step))

        wrong_owner = copy.deepcopy(snapshot)
        self.items(wrong_owner, "attempts")[0]["jobId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86e099"
        self.assertIn("references-close-over-snapshot", workflow_snapshot_errors(definition, wrong_owner))

        wrong_checkpoint = copy.deepcopy(snapshot)
        self.items(wrong_checkpoint, "checkpoints")[0]["attemptId"] = self.items(wrong_checkpoint, "attempts")[0][
            "attemptId"
        ]
        self.assertIn(
            "checkpoint-order-and-owner-are-consistent",
            workflow_snapshot_errors(definition, wrong_checkpoint),
        )

        checkpoint_gap = copy.deepcopy(snapshot)
        self.items(checkpoint_gap, "checkpoints")[0]["checkpointSequence"] = 2
        self.assertIn(
            "checkpoint-order-and-owner-are-consistent",
            workflow_snapshot_errors(definition, checkpoint_gap),
        )

        uncommitted = copy.deepcopy(snapshot)
        output_id = cast(list[str], self.items(uncommitted, "jobs")[0]["outputArtifactIds"])[0]
        output = next(item for item in self.items(uncommitted, "artifacts") if item["artifactId"] == output_id)
        output["disposition"] = "retained-incomplete"
        self.assertIn("succeeded-output-artifacts-are-committed", workflow_snapshot_errors(definition, uncommitted))

    def test_completed_human_tasks_are_first_class_and_audit_bound(self) -> None:
        definition = self.definition()
        snapshot = self.snapshot()
        human_task = self.items(snapshot, "humanTasks")[0]
        decision = cast(JsonRecord, human_task["decision"])
        self.assertEqual("completed", human_task["state"])
        self.assertEqual("approved", decision["disposition"])

        missing = copy.deepcopy(snapshot)
        self.items(missing, "humanTasks")[0]["decision"] = None
        self.assertIn("completed-human-task-binds-decision", workflow_snapshot_errors(definition, missing))

        substituted = copy.deepcopy(snapshot)
        substitute_task = self.items(substituted, "humanTasks")[0]
        cast(JsonRecord, substitute_task["decision"])["decisionId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86e099"
        self.assertIn("human-decision-is-audit-bound", workflow_snapshot_errors(definition, substituted))

        overwritten = copy.deepcopy(snapshot)
        completion = next(
            event
            for event in self.items(overwritten, "history")
            if event["entityType"] == "human-task" and event["toState"] == "completed"
        )
        completion["decisionId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86e099"
        self.assertIn("human-decision-is-audit-bound", workflow_snapshot_errors(definition, overwritten))

        missing_evidence = copy.deepcopy(snapshot)
        missing_decision = cast(JsonRecord, self.items(missing_evidence, "humanTasks")[0]["decision"])
        missing_decision["evidenceArtifactIds"] = ["018f47a2-4d6b-7f78-9f2e-7fb76c86e099"]
        self.assertIn("human-decision-is-audit-bound", workflow_snapshot_errors(definition, missing_evidence))

        excluded_definition = copy.deepcopy(definition)
        human_step = next(step for step in self.items(excluded_definition, "steps") if step["kind"] == "human-task")
        cast(JsonRecord, human_step["humanTask"])["allowedDispositions"] = ["rejected"]
        excluded_disposition = copy.deepcopy(snapshot)
        cast(JsonRecord, excluded_disposition["definition"])["contentHash"] = workflow_record_sha256(
            excluded_definition
        )
        self.assertIn(
            "human-decision-is-audit-bound",
            workflow_snapshot_errors(excluded_definition, excluded_disposition),
        )

        for field, replacement in (
            (
                "requestedBy",
                {
                    "actorId": "018f47a2-4d6b-7f78-9f2e-7fb76c86e099",
                    "actorType": "system",
                    "role": "workflow-coordinator",
                },
            ),
            ("requestedAt", "2026-08-30T12:01:24.500Z"),
        ):
            with self.subTest(field=field):
                substituted_request = copy.deepcopy(snapshot)
                self.items(substituted_request, "humanTasks")[0][field] = replacement
                self.assertIn(
                    "human-decision-is-audit-bound",
                    workflow_snapshot_errors(definition, substituted_request),
                )

        substituted_claim = copy.deepcopy(snapshot)
        claim_event = next(
            event
            for event in self.items(substituted_claim, "history")
            if event["entityType"] == "human-task" and event["toState"] == "claimed"
        )
        cast(JsonRecord, claim_event["actor"])["actorId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86e099"
        self.assertIn(
            "human-decision-is-audit-bound",
            workflow_snapshot_errors(definition, substituted_claim),
        )

        duplicate_request = copy.deepcopy(snapshot)
        request_event = next(
            event
            for event in self.items(duplicate_request, "history")
            if event["entityType"] == "human-task" and event["toState"] == "requested"
        )
        replacement_event = self.items(duplicate_request, "history")[25]
        replacement_event.update(copy.deepcopy(request_event))
        replacement_event["eventId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86e026"
        replacement_event["sequence"] = 26
        self.assertIn(
            "human-decision-is-audit-bound",
            workflow_snapshot_errors(definition, duplicate_request),
        )

    def test_transition_event_identities_are_unique_across_restart_replay(self) -> None:
        definition = self.definition()
        snapshot = self.snapshot()
        duplicate = copy.deepcopy(snapshot)
        history = self.items(duplicate, "history")
        history[1]["eventId"] = history[0]["eventId"]

        self.assertIn("history-event-identities-are-unique", workflow_snapshot_errors(definition, duplicate))
        self.assertIsNone(decode_workflow_snapshot(definition, duplicate))
        self.assertIsNotNone(decode_workflow_snapshot(definition, json.loads(json.dumps(snapshot))))

    def test_legacy_operation_bridge_is_an_exact_projection_not_workflow_authority(self) -> None:
        snapshot = self.snapshot()
        bridge = self.fixture("valid-legacy-operation-bridge.v1.json")
        self.assertEqual((), legacy_operation_bridge_errors(snapshot, bridge))
        self.assertIsNotNone(decode_legacy_operation_bridge(snapshot, bridge))

        wrong_run = copy.deepcopy(bridge)
        wrong_run["workflowRunId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86e099"
        self.assertIn(
            "legacy-operation-bridge-binds-exact-workflow-projection",
            legacy_operation_bridge_errors(snapshot, wrong_run),
        )
        wrong_etag = copy.deepcopy(bridge)
        wrong_etag["etag"] = '"op-source-review-31"'
        self.assertIn("legacy-operation-bridge-etag-is-exact", legacy_operation_bridge_errors(snapshot, wrong_etag))

        wrong_sequence = copy.deepcopy(bridge)
        wrong_sequence["operationSequence"] = 31
        wrong_sequence["etag"] = '"op-source-review-31"'
        self.assertIn(
            "legacy-operation-bridge-binds-exact-workflow-projection",
            legacy_operation_bridge_errors(snapshot, wrong_sequence),
        )

    def test_security_lock_is_not_an_ordinary_auto_resumable_restart(self) -> None:
        definition = self.definition()
        snapshot = self.snapshot()
        snapshot["cancellation"] = {
            "requestedAt": "2026-08-30T12:01:26.500Z",
            "reasonCode": "application-locked",
            "interruptionKind": "security-lock",
        }
        self.assertIn("security-lock-does-not-auto-resume", workflow_snapshot_errors(definition, snapshot))

        partial = self.snapshot()
        partial["cancellation"] = {
            "requestedAt": "2026-08-30T12:01:26.500Z",
            "reasonCode": None,
            "interruptionKind": "ordinary-cancellation",
        }
        self.assertTrue(workflow_snapshot_errors(definition, partial))
        self.assertIsNone(decode_workflow_snapshot(definition, partial))

    def test_schema_hash_and_canonical_records_are_stable(self) -> None:
        canonical_schema = self.schema_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        self.assertEqual(sha256(canonical_schema.encode("utf-8")).hexdigest(), WORKFLOW_SCHEMA_SHA256)
        for value in (
            self.definition(),
            self.snapshot(),
            self.snapshot("server"),
            self.fixture("valid-legacy-operation-bridge.v1.json"),
        ):
            canonical = canonical_workflow_json(value)
            self.assertEqual(canonical, canonical_workflow_json(json.loads(canonical)))
            self.assertEqual(
                f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}",
                workflow_record_sha256(value),
            )


if __name__ == "__main__":
    unittest.main()
