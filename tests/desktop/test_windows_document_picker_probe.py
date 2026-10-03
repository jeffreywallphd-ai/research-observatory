"""Operation-scoped picker evidence accepts cancellation before selection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/desktop/tools"))

import run_windows_document_drop_probe as drop  # noqa: E402
from run_windows_document_picker_probe import exact_stage_pair  # noqa: E402

CANCEL_OPERATION = "01a1001f-caed-7a8b-8163-b6760593f112"
SELECT_OPERATION = "01a1001f-e009-74be-be23-c1f397ed34fd"
CANDIDATE = "01a1001f-e010-74be-be23-c1f397ed34fd"


def stage(kind: str, operation: str, status: str, candidate: str | None) -> dict[str, object]:
    event: dict[str, object] = {
        "kind": kind,
        "operationId": operation,
        "status": status,
        "candidateId": candidate,
        "code": None,
    }
    if kind == "document-drop-probe-stage-finish":
        event.update(
            {
                "protectedClosureEntered": True,
                "protectedCommitSucceeded": True,
                "eventEmitSucceeded": True,
                "deliveryCode": None,
            }
        )
    return event


class PickerOperationPartitionTests(unittest.TestCase):
    def test_cancel_then_select_matches_distinct_pairs_despite_finish_order(self) -> None:
        fixture = SimpleNamespace(
            picker_results=[
                {"operationId": CANCEL_OPERATION, "status": "cancelled", "candidateId": None},
            ],
            stage=[
                stage("document-drop-probe-stage-finish", CANCEL_OPERATION, "cancelled", None),
                stage("document-drop-probe-stage-result", CANCEL_OPERATION, "cancelled", None),
            ],
        )
        self.assertEqual(
            exact_stage_pair(fixture, stage_start=0, picker_start=0, expected_status="cancelled"),
            (CANCEL_OPERATION, None),
        )
        fixture.picker_results.append({"operationId": SELECT_OPERATION, "status": "selected", "candidateId": CANDIDATE})
        fixture.stage.extend(
            [
                stage("document-drop-probe-stage-result", SELECT_OPERATION, "candidate", CANDIDATE),
                stage("document-drop-probe-stage-finish", SELECT_OPERATION, "candidate", CANDIDATE),
            ]
        )
        self.assertEqual(
            exact_stage_pair(fixture, stage_start=2, picker_start=1, expected_status="selected"),
            (SELECT_OPERATION, CANDIDATE),
        )

    def test_wrong_operation_or_duplicate_pair_is_adverse(self) -> None:
        fixture = SimpleNamespace(
            picker_results=[{"operationId": SELECT_OPERATION, "status": "selected", "candidateId": CANDIDATE}],
            stage=[
                stage("document-drop-probe-stage-result", CANCEL_OPERATION, "candidate", CANDIDATE),
                stage("document-drop-probe-stage-finish", SELECT_OPERATION, "candidate", CANDIDATE),
            ],
        )
        with self.assertRaises(drop.ProbeFailure):
            exact_stage_pair(fixture, stage_start=0, picker_start=0, expected_status="selected")
        fixture.stage.append(stage("document-drop-probe-stage-result", SELECT_OPERATION, "candidate", CANDIDATE))
        with self.assertRaises(drop.ProbeFailure):
            exact_stage_pair(fixture, stage_start=0, picker_start=0, expected_status="selected")


if __name__ == "__main__":
    unittest.main()
