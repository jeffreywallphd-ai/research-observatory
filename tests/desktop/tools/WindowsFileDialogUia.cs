// Bounded UI Automation helper for an exact app-owned native file picker.
// Inspect remains read-only. Act fails closed unless the exact dialog and one
// enabled File name / action control are established at runtime.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;

public static class WindowsFileDialogUia
{
    private const uint GwOwner = 4;
    private const string ExpectedOwnerTitle = "Research Observatory — SYNTHETIC T01 document-drop";
    private const string ExpectedOwnerClass = "Tauri Window";
    private const string ExpectedTitle = "Choose a document to attach";
    private const string ExpectedClass = "#32770";
    private const string SourceName = "document-drop-source.txt";
    private const string SourceSha256 = "b83fc32249fefc9f92520155a0f78353d02a23365d582bb39bc060c096890d91";
    private const uint BmClick = 0x00F5;
    private const uint SmtoAbortIfHung = 0x0002;
    private const uint SmtoErrorOnExit = 0x0020;
    private const uint NativeSendTimeoutMs = 1000;

    private delegate bool EnumWindowsCallback(IntPtr window, IntPtr state);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsCallback callback, IntPtr state);

    [DllImport("user32.dll")]
    private static extern bool EnumChildWindows(IntPtr parent, EnumWindowsCallback callback, IntPtr state);

    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr window);

    [DllImport("user32.dll")]
    private static extern bool IsWindow(IntPtr window);

    [DllImport("user32.dll")]
    private static extern bool IsWindowEnabled(IntPtr window);

    [DllImport("user32.dll")]
    private static extern IntPtr GetDlgItem(IntPtr dialog, int controlId);

    [DllImport("user32.dll")]
    private static extern int GetDlgCtrlID(IntPtr window);

    [DllImport("user32.dll")]
    private static extern IntPtr GetParent(IntPtr window);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr window, StringBuilder result, int capacity);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr window, StringBuilder result, int capacity);

    [DllImport("user32.dll")]
    private static extern IntPtr GetWindow(IntPtr window, uint command);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    [DllImport("user32.dll", EntryPoint = "SendMessageTimeoutW", SetLastError = true)]
    private static extern IntPtr SendMessageTimeoutW(IntPtr window, uint message,
        IntPtr wParam, IntPtr lParam, uint flags, uint timeoutMs, out IntPtr messageResult);

    private static string Text(IntPtr window, bool className)
    {
        StringBuilder text = new StringBuilder(256);
        int length = className ? GetClassName(window, text, text.Capacity)
            : GetWindowText(window, text, text.Capacity);
        return length > 0 ? text.ToString() : "";
    }

    private static IntPtr ExactDialog(long ownerHwnd, int ownerPid, int timeoutMs)
    {
        if (ownerHwnd == 0 || ownerPid <= 0 || timeoutMs < 1000 || timeoutMs > 15000)
            throw new ArgumentException("dialog-request-invalid");
        IntPtr owner = new IntPtr(ownerHwnd);
        uint rootPid;
        if (!IsWindow(owner) || !IsWindowVisible(owner)
            || GetWindowThreadProcessId(owner, out rootPid) == 0 || rootPid != (uint)ownerPid
            || Text(owner, false) != ExpectedOwnerTitle || Text(owner, true) != ExpectedOwnerClass)
            throw new InvalidOperationException("dialog-owner-invalid");
        Stopwatch clock = Stopwatch.StartNew();
        do
        {
            List<IntPtr> candidates = new List<IntPtr>();
            EnumWindows(delegate(IntPtr window, IntPtr state)
            {
                uint dialogPid;
                if (IsWindowVisible(window)
                    && GetWindow(window, GwOwner) == owner
                    && GetWindowThreadProcessId(window, out dialogPid) != 0
                    && dialogPid == (uint)ownerPid
                    && Text(window, true) == ExpectedClass
                    && Text(window, false) == ExpectedTitle)
                    candidates.Add(window);
                return true;
            }, IntPtr.Zero);
            if (candidates.Count > 1)
                throw new InvalidOperationException("dialog-ambiguous");
            if (candidates.Count == 1)
                return candidates[0];
            Thread.Sleep(100);
        } while (clock.ElapsedMilliseconds < timeoutMs);
        throw new InvalidOperationException("dialog-unavailable");
    }

    private sealed class Controls
    {
        public AutomationElement FileName;
        public AutomationElement Open;
        public AutomationElement OpenByName;
        public AutomationElement Cancel;
        public int Edits;
        public int Buttons;
        public int SplitButtons;
        public int FileNameMatches;
        public int OpenMatches;
        public int FileNameIdCount;
        public int OpenIdCount;
        public int OpenNameMatches;
        public int CancelIdCount;
        public bool FileNameIdEnabled;
        public bool FileNameIdOffscreen;
        public bool OpenIdEnabled;
        public bool OpenIdOffscreen;
        public bool FileNameIdValuePattern;
        public bool OpenIdInvokePattern;
        public bool OpenNameInvokePattern;
        public bool CancelIdInvokePattern;
        public List<string> EditIds = new List<string>();
        public List<string> ButtonIds = new List<string>();
        public List<Dictionary<string, object>> ActionCandidates = new List<Dictionary<string, object>>();
        public bool ActionCandidatesTruncated;
        public bool IdOkPresent;
        public bool IdOkDirectChild;
        public bool IdOkSameProcess;
        public bool IdOkVisible;
        public bool IdOkEnabled;
        public string IdOkClass = "<other>";
        public string IdOkNameClass = "other";
    }

    private static string SafeId(string automationId)
    {
        if (String.IsNullOrEmpty(automationId) || automationId.Length > 8)
            return "<other>";
        foreach (char value in automationId)
            if (value < '0' || value > '9')
                return "<other>";
        return automationId;
    }

    // Closed vocabulary: arbitrary UIA names can contain user file and folder names.
    private static string SafeActionName(string name)
    {
        if (name == null)
            return "other";
        switch (name.Trim())
        {
            case "Open":
            case "&Open":
            case "Open...":
            case "Open…":
                return "open";
            case "Select":
            case "&Select":
                return "select";
            case "OK":
            case "&OK":
                return "ok";
            default:
                return "other";
        }
    }

    private static Controls LocateControls(IntPtr dialog)
    {
        AutomationElement root = AutomationElement.FromHandle(dialog);
        if (root == null)
            throw new InvalidOperationException("dialog-uia-unavailable");
        Controls result = new Controls();
        IntPtr idOk = GetDlgItem(dialog, 1);
        uint dialogPid;
        uint idOkPid;
        bool dialogPidKnown = GetWindowThreadProcessId(dialog, out dialogPid) != 0;
        result.IdOkPresent = idOk != IntPtr.Zero && IsWindow(idOk);
        if (result.IdOkPresent)
        {
            result.IdOkDirectChild = GetParent(idOk) == dialog;
            result.IdOkSameProcess = dialogPidKnown
                && GetWindowThreadProcessId(idOk, out idOkPid) != 0 && idOkPid == dialogPid;
            result.IdOkVisible = IsWindowVisible(idOk);
            result.IdOkEnabled = IsWindowEnabled(idOk);
            result.IdOkClass = Text(idOk, true) == "Button" ? "Button" : "<other>";
            result.IdOkNameClass = SafeActionName(Text(idOk, false));
        }
        AutomationElementCollection descendants = root.FindAll(TreeScope.Descendants, Condition.TrueCondition);
        foreach (AutomationElement element in descendants)
        {
            AutomationElement.AutomationElementInformation current;
            try { current = element.Current; }
            catch (ElementNotAvailableException) { continue; }
            if (current.ControlType == ControlType.Edit)
            {
                result.Edits++;
                result.EditIds.Add(SafeId(current.AutomationId));
                if (current.AutomationId == "1148")
                {
                    object pattern;
                    result.FileNameIdCount++;
                    result.FileNameIdEnabled = current.IsEnabled;
                    result.FileNameIdOffscreen = current.IsOffscreen;
                    result.FileNameIdValuePattern = element.TryGetCurrentPattern(ValuePattern.Pattern, out pattern);
                }
                // Windows common-dialog File name control (cmb13 edit).
                if (current.AutomationId == "1148" && current.IsEnabled && !current.IsOffscreen)
                {
                    result.FileNameMatches++;
                    result.FileName = element;
                }
            }
            else if (current.ControlType == ControlType.Button)
            {
                result.Buttons++;
                result.ButtonIds.Add(SafeId(current.AutomationId));
                if (current.AutomationId == "1")
                {
                    object pattern;
                    result.OpenIdCount++;
                    result.OpenIdEnabled = current.IsEnabled;
                    result.OpenIdOffscreen = current.IsOffscreen;
                    result.OpenIdInvokePattern = element.TryGetCurrentPattern(InvokePattern.Pattern, out pattern);
                }
                // The common-dialog accept button (IDOK).
                if (current.AutomationId == "1" && current.IsEnabled && !current.IsOffscreen)
                {
                    result.OpenMatches++;
                    result.Open = element;
                }
                if (current.Name == "Open" && current.IsEnabled && !current.IsOffscreen)
                {
                    object pattern;
                    result.OpenNameMatches++;
                    result.OpenNameInvokePattern = element.TryGetCurrentPattern(InvokePattern.Pattern, out pattern);
                    result.OpenByName = element;
                }
                if (current.AutomationId == "2")
                {
                    object pattern;
                    result.CancelIdCount++;
                    result.CancelIdInvokePattern = element.TryGetCurrentPattern(InvokePattern.Pattern, out pattern);
                    if (current.IsEnabled && !current.IsOffscreen)
                        result.Cancel = element;
                }
            }
            if (current.ControlType == ControlType.Button
                || current.ControlType == ControlType.SplitButton)
            {
                if (current.ControlType == ControlType.SplitButton)
                    result.SplitButtons++;
                if (result.ActionCandidates.Count >= 64)
                {
                    result.ActionCandidatesTruncated = true;
                    continue;
                }
                try
                {
                    object pattern;
                    bool invokes = element.TryGetCurrentPattern(InvokePattern.Pattern, out pattern);
                    bool matchesIdOk = result.IdOkPresent && result.IdOkDirectChild
                        && result.IdOkSameProcess && current.NativeWindowHandle != 0
                        && current.NativeWindowHandle == unchecked((int)idOk.ToInt64());
                    result.ActionCandidates.Add(new Dictionary<string, object> {
                        { "type", current.ControlType == ControlType.SplitButton ? "split-button" : "button" },
                        { "id", SafeId(current.AutomationId) },
                        { "nameClass", SafeActionName(current.Name) },
                        { "enabled", current.IsEnabled },
                        { "offscreen", current.IsOffscreen },
                        { "invokePattern", invokes },
                        { "matchesIdOk", matchesIdOk },
                    });
                }
                catch (ElementNotAvailableException) { /* Diagnostic only. */ }
                catch (InvalidOperationException) { /* Diagnostic only. */ }
                catch (COMException) { /* Diagnostic only. */ }
            }
        }
        return result;
    }

    private static Dictionary<string, object> Diagnostic(Controls controls)
    {
        return new Dictionary<string, object> {
            { "dialogExactOwnerAndPid", true },
            { "editCount", controls.Edits },
            { "buttonCount", controls.Buttons },
            { "splitButtonCount", controls.SplitButtons },
            { "fileNameMatches", controls.FileNameMatches },
            { "openMatches", controls.OpenMatches },
            { "fileNameIdCount", controls.FileNameIdCount },
            { "openIdCount", controls.OpenIdCount },
            { "openNameMatches", controls.OpenNameMatches },
            { "cancelIdCount", controls.CancelIdCount },
            { "fileNameIdEnabled", controls.FileNameIdEnabled },
            { "fileNameIdOffscreen", controls.FileNameIdOffscreen },
            { "openIdEnabled", controls.OpenIdEnabled },
            { "openIdOffscreen", controls.OpenIdOffscreen },
            { "fileNameIdValuePattern", controls.FileNameIdValuePattern },
            { "openIdInvokePattern", controls.OpenIdInvokePattern },
            { "openNameInvokePattern", controls.OpenNameInvokePattern },
            { "cancelIdInvokePattern", controls.CancelIdInvokePattern },
            { "editAutomationIds", controls.EditIds },
            { "buttonAutomationIds", controls.ButtonIds },
            { "actionCandidates", controls.ActionCandidates },
            { "actionCandidatesTruncated", controls.ActionCandidatesTruncated },
            { "idOkPresent", controls.IdOkPresent },
            { "idOkDirectChild", controls.IdOkDirectChild },
            { "idOkSameProcess", controls.IdOkSameProcess },
            { "idOkVisible", controls.IdOkVisible },
            { "idOkEnabled", controls.IdOkEnabled },
            { "idOkClass", controls.IdOkClass },
            { "idOkNameClass", controls.IdOkNameClass },
            { "fileNameValuePattern", controls.FileNameIdValuePattern },
            { "openInvokePattern", controls.OpenIdInvokePattern },
        };
    }

    private static bool FileNameReady(Controls controls)
    {
        return controls.FileNameIdCount == 1 && controls.FileNameMatches == 1
            && controls.FileNameIdValuePattern;
    }

    private static bool OpenReady(Controls controls)
    {
        bool exactOpen = controls.OpenIdCount == 1 && controls.OpenMatches == 1
            && controls.OpenIdInvokePattern;
        bool namedOpen = controls.OpenIdCount == 0 && controls.OpenNameMatches == 1
            && controls.OpenNameInvokePattern;
        return exactOpen || namedOpen;
    }

    private static Controls ReadyControls(IntPtr dialog, int timeoutMs, string phase)
    {
        Stopwatch clock = Stopwatch.StartNew();
        Controls controls;
        do
        {
            controls = LocateControls(dialog);
            if (controls.CancelIdCount > 1
                || (phase != "cancel" && (controls.FileNameIdCount > 1
                    || controls.OpenIdCount > 1 || controls.OpenNameMatches > 1)))
                throw new InvalidOperationException("dialog-ambiguous");
            bool exactCancel = controls.CancelIdCount == 1 && controls.Cancel != null
                && controls.CancelIdInvokePattern;
            if ((phase == "cancel" && exactCancel)
                || (phase == "file-name" && FileNameReady(controls))
                || (phase == "open" && FileNameReady(controls) && OpenReady(controls)))
                return controls;
            Thread.Sleep(100);
        } while (IsWindow(dialog) && clock.ElapsedMilliseconds < timeoutMs);
        return controls;
    }

    public static string Inspect(long ownerHwnd, int ownerPid, int timeoutMs)
    {
        IntPtr dialog = ExactDialog(ownerHwnd, ownerPid, timeoutMs);
        return new JavaScriptSerializer().Serialize(Diagnostic(ReadyControls(dialog, timeoutMs, "open")));
    }

    private static void RequireSyntheticFixture(string fixtureRoot)
    {
        if (String.IsNullOrWhiteSpace(fixtureRoot) || !Path.IsPathRooted(fixtureRoot))
            throw new InvalidOperationException("synthetic-fixture-invalid");
        string root = Path.GetFullPath(fixtureRoot).TrimEnd(Path.DirectorySeparatorChar);
        if (!Path.GetFileName(root).StartsWith("directory-dialog-drop-", StringComparison.Ordinal))
            throw new InvalidOperationException("synthetic-fixture-invalid");
        string temporary = Path.Combine(root, "temporary");
        string source = Path.Combine(temporary, SourceName);
        foreach (string path in new[] { root, temporary, source })
        {
            FileAttributes attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReparsePoint) != 0)
                throw new InvalidOperationException("synthetic-source-reparse-point");
        }
    }

    private static string SyntheticSource(string fixtureRoot, out FileStream held)
    {
        RequireSyntheticFixture(fixtureRoot);
        string source = Path.Combine(Path.GetFullPath(fixtureRoot), "temporary", SourceName);
        held = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (held.Length <= 0 || held.Length > 8192)
            throw new InvalidOperationException("synthetic-source-size-invalid");
        using (SHA256 sha = SHA256.Create())
        {
            string digest = BitConverter.ToString(sha.ComputeHash(held)).Replace("-", "").ToLowerInvariant();
            if (digest != SourceSha256)
                throw new InvalidOperationException("synthetic-source-digest-mismatch");
        }
        return source;
    }

    // The OS-owned direct IDOK child is the only select target. An ID or label
    // found elsewhere in the dialog tree cannot substitute for this HWND.
    private static IntPtr ExactNativeOpenButton(IntPtr dialog, int ownerPid, IntPtr expectedButton)
    {
        if (!IsWindow(dialog) || GetForegroundWindow() != dialog)
            throw new InvalidOperationException("dialog-native-open-control-unproven");
        uint dialogPid;
        uint dialogThread = GetWindowThreadProcessId(dialog, out dialogPid);
        IntPtr idOk = GetDlgItem(dialog, 1);
        if (dialogThread == 0 || dialogPid != (uint)ownerPid
            || idOk == IntPtr.Zero || !IsWindow(idOk)
            || (expectedButton != IntPtr.Zero && idOk != expectedButton)
            || GetParent(idOk) != dialog || GetDlgCtrlID(idOk) != 1)
            throw new InvalidOperationException("dialog-native-open-control-unproven");
        List<IntPtr> directIdOkChildren = new List<IntPtr>();
        EnumChildWindows(dialog, delegate(IntPtr child, IntPtr state)
        {
            if (GetParent(child) == dialog && GetDlgCtrlID(child) == 1)
                directIdOkChildren.Add(child);
            return true;
        }, IntPtr.Zero);
        if (directIdOkChildren.Count != 1 || directIdOkChildren[0] != idOk)
            throw new InvalidOperationException("dialog-native-open-control-unproven");
        uint idOkPid;
        uint idOkThread = GetWindowThreadProcessId(idOk, out idOkPid);
        if (idOkThread == 0 || idOkPid != dialogPid || idOkThread != dialogThread
            || !IsWindowVisible(idOk) || !IsWindowEnabled(idOk)
            || Text(idOk, true) != "Button" || SafeActionName(Text(idOk, false)) != "open")
            throw new InvalidOperationException("dialog-native-open-control-unproven");
        return idOk;
    }

    private static void ClickExactNativeOpen(IntPtr idOk)
    {
        uint ignoredPid;
        uint targetThread = GetWindowThreadProcessId(idOk, out ignoredPid);
        // SendMessageTimeout cannot bound a call to our own message queue.
        if (targetThread == 0 || targetThread == GetCurrentThreadId())
            throw new InvalidOperationException("dialog-native-open-control-unproven");
        IntPtr messageResult;
        if (SendMessageTimeoutW(idOk, BmClick, IntPtr.Zero, IntPtr.Zero,
            SmtoAbortIfHung | SmtoErrorOnExit, NativeSendTimeoutMs, out messageResult) == IntPtr.Zero)
            throw new InvalidOperationException("dialog-native-open-send-failed");
    }

    private static AutomationElement ExactCancel(Controls controls)
    {
        if (controls.CancelIdCount != 1 || controls.Cancel == null || !controls.CancelIdInvokePattern)
            throw new InvalidOperationException("dialog-cancel-control-unproven");
        return controls.Cancel;
    }

    private static string SafeFailure(Exception error)
    {
        if (error is InvalidOperationException)
        {
            switch (error.Message)
            {
                case "dialog-owner-invalid":
                case "dialog-ambiguous":
                case "dialog-unavailable":
                case "dialog-uia-unavailable":
                case "dialog-cancel-control-unproven":
                case "dialog-file-name-control-unproven":
                case "dialog-open-control-unproven":
                case "dialog-native-open-control-unproven":
                case "dialog-native-open-uia-unproven":
                case "dialog-native-open-send-failed":
                case "dialog-not-foreground":
                case "dialog-value-not-set":
                case "dialog-did-not-close":
                case "synthetic-fixture-invalid":
                case "synthetic-source-reparse-point":
                case "synthetic-source-size-invalid":
                case "synthetic-source-digest-mismatch":
                    return error.Message;
            }
        }
        return "dialog-action-failed";
    }

    public static string Act(string action, long ownerHwnd, int ownerPid, int timeoutMs, string fixtureRoot)
    {
        Dictionary<string, object> result = new Dictionary<string, object> {
            { "kind", "windows-file-dialog-uia" },
            { "action", action },
            { "status", "incomplete" },
            { "dialogExactOwnerAndPid", false },
            { "sourceSha256", action == "select" ? SourceSha256 : null },
        };
        FileStream held = null;
        Controls controls = null;
        IntPtr dialog = IntPtr.Zero;
        IntPtr idOk = IntPtr.Zero;
        ValuePattern selectedValue = null;
        string selectedSource = null;
        string controlPhase = "find-dialog";
        try
        {
            if (action != "select" && action != "cancel")
                throw new InvalidOperationException("dialog-action-invalid");
            dialog = ExactDialog(ownerHwnd, ownerPid, timeoutMs);
            result["dialogExactOwnerAndPid"] = true;
            if (GetForegroundWindow() != dialog)
                throw new InvalidOperationException("dialog-not-foreground");
            controlPhase = action == "cancel" ? "cancel" : "file-name";
            controls = action == "cancel" ? ReadyControls(dialog, timeoutMs, "cancel")
                : ReadyControls(dialog, timeoutMs, "file-name");
            if (action == "select")
            {
                if (!FileNameReady(controls))
                    throw new InvalidOperationException("dialog-file-name-control-unproven");
                selectedSource = SyntheticSource(fixtureRoot, out held);
                object valueObject;
                if (!controls.FileName.TryGetCurrentPattern(ValuePattern.Pattern, out valueObject))
                    throw new InvalidOperationException("dialog-file-name-control-unproven");
                selectedValue = (ValuePattern)valueObject;
                if (!controls.FileName.Current.IsEnabled || controls.FileName.Current.IsOffscreen)
                    throw new InvalidOperationException("dialog-file-name-control-unproven");
                if (ExactDialog(ownerHwnd, ownerPid, 1000) != dialog
                    || GetForegroundWindow() != dialog)
                    throw new InvalidOperationException("dialog-owner-invalid");
                selectedValue.SetValue(selectedSource);
                if (selectedValue.Current.Value != selectedSource)
                    throw new InvalidOperationException("dialog-value-not-set");
                held.Dispose();
                held = null;
                controlPhase = "open";
                if (ExactDialog(ownerHwnd, ownerPid, 1000) != dialog)
                    throw new InvalidOperationException("dialog-owner-invalid");
                idOk = ExactNativeOpenButton(dialog, ownerPid, IntPtr.Zero);
            }
            if (action == "select")
            {
                if (selectedValue.Current.Value != selectedSource
                    || !controls.FileName.Current.IsEnabled
                    || controls.FileName.Current.IsOffscreen)
                    throw new InvalidOperationException("dialog-value-not-set");
                if (ExactDialog(ownerHwnd, ownerPid, 1000) != dialog
                    || GetForegroundWindow() != dialog)
                    throw new InvalidOperationException("dialog-owner-invalid");
                ExactNativeOpenButton(dialog, ownerPid, idOk);
                ClickExactNativeOpen(idOk);
            }
            else
            {
                AutomationElement target = ExactCancel(controls);
                if (ExactDialog(ownerHwnd, ownerPid, 1000) != dialog
                    || GetForegroundWindow() != dialog)
                    throw new InvalidOperationException("dialog-owner-invalid");
                if (!target.Current.IsEnabled || target.Current.IsOffscreen)
                    throw new InvalidOperationException("dialog-cancel-control-unproven");
                object invokeObject;
                if (!target.TryGetCurrentPattern(InvokePattern.Pattern, out invokeObject))
                    throw new InvalidOperationException("dialog-open-control-unproven");
                ((InvokePattern)invokeObject).Invoke();
            }
            Stopwatch clock = Stopwatch.StartNew();
            while (IsWindow(dialog) && clock.ElapsedMilliseconds < timeoutMs)
                Thread.Sleep(100);
            if (IsWindow(dialog))
                throw new InvalidOperationException("dialog-did-not-close");
            result["status"] = action == "select" ? "selected" : "cancelled";
            result["dialogClosed"] = true;
            result["sourceDigestVerified"] = action == "select";
        }
        catch (Exception error)
        {
            result["failureCode"] = SafeFailure(error);
            result["controlPhase"] = controlPhase;
            if (dialog != IntPtr.Zero && IsWindow(dialog))
            {
                try { controls = LocateControls(dialog); }
                catch (Exception) { /* Retain the last safe snapshot if UIA vanished. */ }
            }
            if (controls != null)
                result["controlDiagnostic"] = Diagnostic(controls);
        }
        finally
        {
            if (held != null)
                held.Dispose();
        }
        return new JavaScriptSerializer().Serialize(result);
    }
}
