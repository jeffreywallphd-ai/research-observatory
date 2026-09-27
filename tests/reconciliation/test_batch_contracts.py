"""Durable duplicate jobs bind a frozen inventory and unchanged ranking authority."""

import unittest

from pydantic import ValidationError
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.preview_workflow import PreviewIntentContext
from research_observatory_core.ports.workflow_executor import WorkflowAcceptedBoundary, WorkflowAcceptedSnapshot
from research_observatory_core.reconciliation.batch import SOURCE_ACTIVITIES, BatchInput, InventorySnapshot


class BatchContractTests(unittest.TestCase):
    def test_batch_binds_accepted_intent_project_epoch_and_frozen_scoring(self):
        project = new_uuid_v7()
        inputs = BatchInput(
            request_id=new_uuid_v7(),
            project_id=project,
            actor_id=new_uuid_v7(),
            intent=PreviewIntentContext(
                project_id=project,
                domain_project_id=project,
                intent_id=new_uuid_v7(),
                revision_id=new_uuid_v7(),
                content_hash="sha256:" + "a" * 64,
                status="accepted",
            ),
            policy_sha256="sha256:" + "b" * 64,
            session_epoch="c" * 32,
            inventory=InventorySnapshot(project_id=project, activity_types=SOURCE_ACTIVITIES, boundaries=()),
        )
        restored = BatchInput.model_validate_json(inputs.model_dump_json(by_alias=True))
        self.assertEqual(inputs, restored)
        self.assertEqual(inputs.configuration_hash, restored.configuration_hash)
        for change in (
            {"project_id": new_uuid_v7()},
            {"scoring_sha256": "0" * 64},
            {"identifier_normalizer": "invented"},
            {"intent": inputs.intent.model_copy(update={"status": "draft"})},
        ):
            with self.subTest(change=tuple(change)), self.assertRaises(ValidationError):
                BatchInput.model_validate(inputs.model_copy(update=change))

    def test_snapshot_round_trip_keeps_exact_queue_fingerprint(self):
        original = WorkflowAcceptedSnapshot(
            new_uuid_v7(),
            ("local-import-commit", "scholarly-connector-page"),
            (WorkflowAcceptedBoundary("rfc8785.sha256.v2", 42, new_uuid_v7(), "sha256:" + "a" * 64),),
        )
        portable = InventorySnapshot.from_queue(original)
        restored = InventorySnapshot.model_validate_json(portable.model_dump_json(by_alias=True))
        self.assertEqual(original, restored.queue_snapshot())
        self.assertEqual(original.fingerprint, restored.queue_snapshot().fingerprint)
        for key, value in (("sequence", True), ("sequence", 0), ("checkpointId", new_uuid_v7().upper())):
            raw = portable.model_dump(mode="json", by_alias=True)
            raw["boundaries"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValidationError):
                InventorySnapshot.model_validate(raw)
        raw = portable.model_dump(mode="json", by_alias=True)
        raw["activityTypes"] = ["source-acquisition"]
        with self.assertRaises(ValidationError):
            InventorySnapshot.model_validate(raw)
