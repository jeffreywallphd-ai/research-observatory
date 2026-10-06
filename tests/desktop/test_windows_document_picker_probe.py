"""Operation-scoped picker evidence accepts cancellation before selection."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/desktop/tools"))

import run_windows_document_drop_probe as drop  # noqa: E402
import run_windows_document_picker_probe as picker  # noqa: E402

CANCEL_OPERATION = "01a1001f-caed-7a8b-8163-b6760593f112"
SELECT_OPERATION = "01a1001f-e009-74be-be23-c1f397ed34fd"
CANDIDATE = "01a1001f-e010-74be-be23-c1f397ed34fd"


class PickerSourceFixtureTests(unittest.TestCase):
    def test_reparse_entry_is_denied_before_following_its_target(self) -> None:
        class ReparseEntry:
            def lstat(self) -> SimpleNamespace:
                return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)

            def is_symlink(self) -> bool:
                return False

            def resolve(self, *, strict: bool) -> Path:
                raise AssertionError("reparse target must not be followed")

        self.assertFalse(picker._exact_fixture_entry(cast(Path, ReparseEntry()), Path("synthetic"), directory=False))

    def test_copy_is_exactly_under_admitted_projects_root_and_preserves_seed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="directory-dialog-drop-") as location:
            root = Path(location)
            (root / "projects").mkdir()
            temporary = root / "temporary"
            temporary.mkdir()
            seed = temporary / picker.SOURCE_NAME
            payload = b"test-owned document source\n"
            seed.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            with patch.object(drop, "SYNTHETIC_SOURCE_SHA256", digest):
                selected = picker.prepare_picker_source(root)
                self.assertEqual(selected, root / "projects" / picker.SOURCE_NAME)
                self.assertEqual(selected.read_bytes(), payload)
                self.assertEqual(seed.read_bytes(), payload)
                with self.assertRaises(drop.ProbeFailure):
                    picker.prepare_picker_source(root)

    def test_wrong_seed_digest_denies_copy_without_leaking_a_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="directory-dialog-drop-") as location:
            root = Path(location)
            (root / "projects").mkdir()
            temporary = root / "temporary"
            temporary.mkdir()
            (temporary / picker.SOURCE_NAME).write_bytes(b"wrong test-owned source")
            with self.assertRaises(drop.ProbeFailure) as denied:
                picker.prepare_picker_source(root)
            self.assertEqual(str(denied.exception), "synthetic-source-digest-mismatch")
            self.assertFalse((root / "projects" / picker.SOURCE_NAME).exists())


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

    def test_selects_only_the_admitted_projects_copy(self) -> None:
        fixture_guard = self.source.split("private static void RequireSyntheticFixture(", 1)[1]
        fixture_guard = fixture_guard.split("private static string SyntheticSource(", 1)[0]
        source_opener = self.source.split("private static string SyntheticSource(", 1)[1]
        source_opener = source_opener.split("private static IntPtr ExactNativeOpenButton(", 1)[0]
        self.assertIn('string projects = Path.Combine(root, "projects")', fixture_guard)
        self.assertIn("new[] { root, projects, source }", fixture_guard)
        self.assertIn('Path.Combine(Path.GetFullPath(fixtureRoot), "projects", SourceName)', source_opener)
        self.assertNotIn('"temporary"', source_opener)

    def test_exact_filename_and_native_idok_are_rechecked_before_single_send(self) -> None:
        source = self.action.index("SyntheticSource(fixtureRoot, out held)")
        set_value = self.action.index("selectedValue.SetValue(selectedSource)")
        native_open = self.action.index("ExactNativeOpenButton(dialog, ownerPid, IntPtr.Zero)")
        same_dialog = self.action.index("ExactDialog(ownerHwnd, ownerPid, 1000)")
        source_recheck = self.action.index("selectedValue.Current.Value != selectedSource", native_open)
        same_dialog_before_send = self.action.index("ExactDialog(ownerHwnd, ownerPid, 1000)", native_open)
        native_recheck = self.action.index("ExactNativeOpenButton(dialog, ownerPid, idOk)")
        send = self.action.index("ClickExactNativeOpen(idOk)")
        self.assertLess(source, set_value)
        self.assertLess(same_dialog, set_value)
        self.assertIn("GetForegroundWindow() != dialog", self.action[source:set_value])
        self.assertLess(set_value, native_open)
        self.assertLess(native_open, source_recheck)
        self.assertLess(source_recheck, same_dialog_before_send)
        self.assertLess(same_dialog_before_send, native_recheck)
        self.assertLess(native_recheck, send)
        self.assertIn('ReadyControls(dialog, timeoutMs, "file-name")', self.action[:set_value])
        self.assertIn("GetForegroundWindow() != dialog", self.action[same_dialog_before_send:send])
        self.assertEqual(self.action.count("ClickExactNativeOpen(idOk)"), 1)
        self.assertEqual(self.action.count("((InvokePattern)invokeObject).Invoke()"), 1)

    def test_select_has_one_bounded_exact_native_action_and_no_fallback(self) -> None:
        self.assertIn("GetDlgItem(dialog, 1)", self.source)
        self.assertIn("GetDlgCtrlID(idOk)", self.source)
        native_send = self.source.split("private static void ClickExactNativeOpen(", 1)[1]
        native_send = native_send.split("private static AutomationElement ExactCancel(", 1)[0]
        self.assertEqual(native_send.count("SendMessageTimeoutW("), 1)
        self.assertIn("SendMessageTimeoutW(idOk, BmClick", native_send)
        self.assertIn("SmtoAbortIfHung | SmtoErrorOnExit", native_send)
        self.assertIn("NativeSendTimeoutMs", native_send)
        self.assertIn("dialog-native-open-send-failed", native_send)
        self.assertNotIn("NativeOpenFromHandle", self.action)
        self.assertNotIn("SetActiveWindow", self.source)
        self.assertNotIn("SendInput", self.source)
        self.assertNotIn("PostMessage", self.source)

    def test_adverse_native_result_retains_only_sanitized_control_state(self) -> None:
        self.assertIn('result["controlDiagnostic"] = Diagnostic(controls)', self.action)
        self.assertIn('result["controlPhase"] = controlPhase', self.action)
        self.assertIn('case "dialog-native-open-send-failed":', self.source)
        self.assertIn("SafeId(current.AutomationId)", self.source)

    @unittest.skipUnless(os.name == "nt", "Windows UI Automation helper")
    def test_accept_diagnostic_redacts_unknown_control_names(self) -> None:
        source_path = str(ROOT / "tests/desktop/tools/WindowsFileDialogUia.cs").replace("'", "''")
        script = f"""
Add-Type -ErrorAction Stop -Path '{source_path}' -ReferencedAssemblies @(
    'UIAutomationClient', 'UIAutomationTypes', 'System.Web.Extensions', 'System'
)
$method = [WindowsFileDialogUia].GetMethod(
    'SafeActionName', [Reflection.BindingFlags]'Static, NonPublic'
)
if ($null -eq $method) {{ throw 'classifier-missing' }}
$names = @('Open', '&Open', 'Open...', 'Select', 'OK',
  'secret-participant.txt', 'document-drop-source.txt')
$values = foreach ($name in $names) {{
    $arguments = New-Object 'object[]' 1
    $arguments[0] = [string]$name
    $method.Invoke($null, $arguments)
}}
$failure = [WindowsFileDialogUia].GetMethod(
    'SafeFailure', [Reflection.BindingFlags]'Static, NonPublic'
)
$failureArguments = New-Object 'object[]' 1
$failureArguments[0] = [InvalidOperationException]::new('secret-participant.txt')
$failureCode = $failure.Invoke($null, $failureArguments)
$failureArguments[0] = [InvalidOperationException]::new('dialog-native-open-send-failed')
$sendFailureCode = $failure.Invoke($null, $failureArguments)
$native = [WindowsFileDialogUia].GetMethod(
    'ExactNativeOpenButton', [Reflection.BindingFlags]'Static, NonPublic'
)
$nativeArguments = New-Object 'object[]' 3
$nativeArguments[0] = [IntPtr]::Zero
$nativeArguments[1] = [int]1
$nativeArguments[2] = [IntPtr]::Zero
$nativeDenial = $null
try {{ [void]$native.Invoke($null, $nativeArguments) }}
catch {{
    if ($null -eq $_.Exception.InnerException) {{ throw }}
    $failureArguments[0] = $_.Exception.InnerException
    $nativeDenial = $failure.Invoke($null, $failureArguments)
}}
ConvertTo-Json -InputObject @{{names=@($values); failure=$failureCode;
  sendFailure=$sendFailureCode; nativeDenial=$nativeDenial}} -Compress
"""
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(completed.stdout.strip(), f"stdout empty; stderr={completed.stderr!r}")
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "names": ["open", "open", "open", "select", "ok", "other", "other"],
                "failure": "dialog-action-failed",
                "sendFailure": "dialog-native-open-send-failed",
                "nativeDenial": "dialog-native-open-control-unproven",
            },
            f"stdout={completed.stdout!r}; stderr={completed.stderr!r}",
        )

    def test_accept_diagnostic_remains_read_only_and_includes_split_button_and_idok(self) -> None:
        diagnostic = self.source.split("private static Dictionary<string, object> Diagnostic(", 1)[1]
        diagnostic = diagnostic.split("private static bool FileNameReady(", 1)[0]
        action_selector = self.source.split("private static AutomationElement ExactCancel(", 1)[1]
        action_selector = action_selector.split("private static string SafeFailure(", 1)[0]
        self.assertIn("ControlType.SplitButton", self.source)
        self.assertIn("GetDlgItem(dialog, 1)", self.source)
        self.assertIn("actionCandidates", diagnostic)
        self.assertIn("idOk", diagnostic)
        self.assertNotIn("current.Name", diagnostic)
        self.assertNotIn(".Invoke()", diagnostic)
        self.assertNotIn("IdOk", action_selector)
        self.assertNotIn("ActionCandidates", action_selector)


if __name__ == "__main__":
    unittest.main()
