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

    private delegate bool EnumWindowsCallback(IntPtr window, IntPtr state);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsCallback callback, IntPtr state);

    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr window);

    [DllImport("user32.dll")]
    private static extern bool IsWindow(IntPtr window);

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

    private static Controls LocateControls(IntPtr dialog)
    {
        AutomationElement root = AutomationElement.FromHandle(dialog);
        if (root == null)
            throw new InvalidOperationException("dialog-uia-unavailable");
        Controls result = new Controls();
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
        }
        return result;
    }

    private static Dictionary<string, object> Diagnostic(Controls controls)
    {
        return new Dictionary<string, object> {
            { "dialogExactOwnerAndPid", true },
            { "editCount", controls.Edits },
            { "buttonCount", controls.Buttons },
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

    private static AutomationElement ExactAction(Controls controls, string action)
    {
        if (action == "cancel")
        {
            if (controls.CancelIdCount != 1 || controls.Cancel == null || !controls.CancelIdInvokePattern)
                throw new InvalidOperationException("dialog-cancel-control-unproven");
            return controls.Cancel;
        }
        if (!FileNameReady(controls))
            throw new InvalidOperationException("dialog-file-name-control-unproven");
        if (controls.OpenIdCount == 1 && controls.OpenMatches == 1 && controls.OpenIdInvokePattern)
            return controls.Open;
        if (controls.OpenIdCount == 0 && controls.OpenNameMatches == 1 && controls.OpenNameInvokePattern)
            return controls.OpenByName;
        throw new InvalidOperationException("dialog-open-control-unproven");
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
                string source = SyntheticSource(fixtureRoot, out held);
                object valueObject;
                if (!controls.FileName.TryGetCurrentPattern(ValuePattern.Pattern, out valueObject))
                    throw new InvalidOperationException("dialog-file-name-control-unproven");
                ValuePattern value = (ValuePattern)valueObject;
                if (!controls.FileName.Current.IsEnabled || controls.FileName.Current.IsOffscreen)
                    throw new InvalidOperationException("dialog-file-name-control-unproven");
                if (ExactDialog(ownerHwnd, ownerPid, 1000) != dialog
                    || GetForegroundWindow() != dialog)
                    throw new InvalidOperationException("dialog-owner-invalid");
                value.SetValue(source);
                if (value.Current.Value != source)
                    throw new InvalidOperationException("dialog-value-not-set");
                held.Dispose();
                held = null;
                controlPhase = "open";
                controls = ReadyControls(dialog, timeoutMs, "open");
            }
            AutomationElement target = ExactAction(controls, action);
            if (ExactDialog(ownerHwnd, ownerPid, 1000) != dialog
                || GetForegroundWindow() != dialog)
                throw new InvalidOperationException("dialog-owner-invalid");
            if (!target.Current.IsEnabled || target.Current.IsOffscreen)
                throw new InvalidOperationException(action == "select"
                    ? "dialog-open-control-unproven" : "dialog-cancel-control-unproven");
            object invokeObject;
            if (!target.TryGetCurrentPattern(InvokePattern.Pattern, out invokeObject))
                throw new InvalidOperationException("dialog-open-control-unproven");
            ((InvokePattern)invokeObject).Invoke();
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
