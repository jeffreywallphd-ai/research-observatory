"""Operation-scoped picker evidence accepts cancellation before selection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/desktop/tools"))

import run_windows_document_drop_probe as drop  # noqa: E402
import run_windows_document_picker_probe as picker  # noqa: E402

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
            picker.exact_stage_pair(fixture, stage_start=0, picker_start=0, expected_status="cancelled"),
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
            picker.exact_stage_pair(fixture, stage_start=2, picker_start=1, expected_status="selected"),
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
            picker.exact_stage_pair(fixture, stage_start=0, picker_start=0, expected_status="selected")
        fixture.stage.append(stage("document-drop-probe-stage-result", SELECT_OPERATION, "candidate", CANDIDATE))
        with self.assertRaises(drop.ProbeFailure):
            picker.exact_stage_pair(fixture, stage_start=0, picker_start=0, expected_status="selected")


def action_state(*, count: int, enabled: bool, source: bool = True, pane: bool = True) -> dict[str, object]:
    return {
        "kind": "document-attachment-probe-action-state",
        "pickerAction": None,
        "commitAction": None,
        "candidateVisible": False,
        "paneVisible": pane,
        "sourceSelected": source,
        "pickerControlCount": count,
        "pickerControlEnabled": enabled,
    }


class ReadoutFixture:
    def __init__(self, states: list[dict[str, object]]) -> None:
        self.states = iter(states)
        self.last = states[-1]
        self.calls = 0

    def readout(self) -> tuple[dict[str, object], dict[str, object]]:
        self.calls += 1
        self.last = next(self.states, self.last)
        return {"uiPhase": 8, "uiError": None}, self.last


class PickerControlReadinessTests(unittest.TestCase):
    def test_exact_control_shape_and_async_enablement(self) -> None:
        disabled = action_state(count=1, enabled=False)
        enabled = action_state(count=1, enabled=True)
        self.assertEqual(picker.safe_picker_event(disabled), disabled)
        self.assertEqual(picker.safe_picker_event(enabled), enabled)
        fixture = ReadoutFixture([disabled, enabled])
        with patch.object(picker.time, "sleep"):
            picker.wait_for_picker_control(fixture, timeout=1)
        self.assertEqual(fixture.calls, 2)

    def test_missing_disabled_or_wrong_source_never_becomes_ready(self) -> None:
        for state in (
            action_state(count=0, enabled=False),
            action_state(count=1, enabled=False),
            action_state(count=1, enabled=True, source=False),
            action_state(count=1, enabled=True, pane=False),
        ):
            with self.subTest(state=state), self.assertRaises(drop.ProbeFailure):
                picker.wait_for_picker_control(ReadoutFixture([state]), timeout=0)

    def test_ambiguous_or_inconsistent_control_fails_closed(self) -> None:
        for state in (action_state(count=2, enabled=False), action_state(count=0, enabled=True)):
            with self.subTest(state=state), self.assertRaises(drop.ProbeFailure):
                picker.wait_for_picker_control(ReadoutFixture([state]), timeout=1)


class WindowsFileDialogActionContractTests(unittest.TestCase):
    source: str
    action: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (ROOT / "tests/desktop/tools/WindowsFileDialogUia.cs").read_text(encoding="utf-8")
        cls.action = cls.source.split("public static string Act(", 1)[1]

    def test_exact_filename_is_verified_and_set_before_open_is_required(self) -> None:
        source = self.action.index("SyntheticSource(fixtureRoot, out held)")
        set_value = self.action.index("value.SetValue(source)")
        ready_open = self.action.index('ReadyControls(dialog, timeoutMs, "open")')
        same_dialog = self.action.index("ExactDialog(ownerHwnd, ownerPid, 1000)")
        same_dialog_before_invoke = self.action.index("ExactDialog(ownerHwnd, ownerPid, 1000)", ready_open)
        invoke = self.action.index("((InvokePattern)invokeObject).Invoke()")
        self.assertLess(source, set_value)
        self.assertLess(same_dialog, set_value)
        self.assertIn("GetForegroundWindow() != dialog", self.action[source:set_value])
        self.assertLess(set_value, ready_open)
        self.assertLess(ready_open, same_dialog_before_invoke)
        self.assertLess(same_dialog_before_invoke, invoke)
        self.assertIn('ReadyControls(dialog, timeoutMs, "file-name")', self.action[:set_value])
        self.assertIn("GetForegroundWindow() != dialog", self.action[same_dialog_before_invoke:invoke])

    def test_adverse_uia_result_retains_only_sanitized_control_state(self) -> None:
        self.assertIn('result["controlDiagnostic"] = Diagnostic(controls)', self.action)
        self.assertIn('result["controlPhase"] = controlPhase', self.action)
        self.assertIn("SafeId(current.AutomationId)", self.source)


if __name__ == "__main__":
    unittest.main()
