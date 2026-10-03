// Disposable Windows-only OLE drag source for real desktop integration checks.
// It does not send WM_DROPFILES or call any target application command.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

public static class WindowsOleFileDrag
{
    private const uint AncestorRoot = 2;

    [StructLayout(LayoutKind.Sequential)]
    private struct Point
    {
        public int X;
        public int Y;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool GetCursorPos(out Point point);

    [DllImport("user32.dll")]
    private static extern IntPtr WindowFromPoint(Point point);

    [DllImport("user32.dll")]
    private static extern IntPtr GetAncestor(IntPtr window, uint flags);

    [DllImport("user32.dll")]
    private static extern IntPtr GetParent(IntPtr window);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr window, StringBuilder className, int capacity);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    private sealed class QuietSourceForm : Form
    {
        protected override bool ShowWithoutActivation { get { return true; } }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams parameters = base.CreateParams;
                parameters.ExStyle |= 0x08000000; // WS_EX_NOACTIVATE
                return parameters;
            }
        }
    }

    private static bool AtWindow(int x, int y, IntPtr root)
    {
        Point point = new Point { X = x, Y = y };
        IntPtr child = WindowFromPoint(point);
        return child != IntPtr.Zero && GetAncestor(child, AncestorRoot) == root;
    }

    private static string JsonString(string value)
    {
        StringBuilder escaped = new StringBuilder("\"");
        foreach (char character in value)
        {
            if (character == '"' || character == '\\')
                escaped.Append('\\').Append(character);
            else if (character < 0x20)
                escaped.Append("\\u").Append(((int)character).ToString("x4"));
            else
                escaped.Append(character);
        }
        return escaped.Append('"').ToString();
    }

    // Path-free Windows hit-test evidence. The arrays align leaf-to-root and
    // compare each HWND's ownership with the supplied application root.
    public static string DescribeTargetAtPoint(int x, int y, long expectedRoot)
    {
        IntPtr root = new IntPtr(expectedRoot);
        IntPtr leaf = WindowFromPoint(new Point { X = x, Y = y });
        uint rootProcess;
        uint rootThread = GetWindowThreadProcessId(root, out rootProcess);
        List<string> classes = new List<string>();
        List<string> sameProcess = new List<string>();
        List<string> sameThread = new List<string>();
        IntPtr current = leaf;
        bool reachedRoot = false;
        for (int depth = 0; depth < 16 && current != IntPtr.Zero; depth++)
        {
            StringBuilder className = new StringBuilder(256);
            int length = GetClassName(current, className, className.Capacity);
            classes.Add(JsonString(length > 0 ? className.ToString() : "<unavailable>"));
            uint processId;
            uint threadId = GetWindowThreadProcessId(current, out processId);
            sameProcess.Add(processId != 0 && processId == rootProcess ? "true" : "false");
            sameThread.Add(threadId != 0 && threadId == rootThread ? "true" : "false");
            if (current == root)
            {
                reachedRoot = true;
                break;
            }
            current = GetParent(current);
        }
        return "{\"classChainLeafToRoot\":[" + String.Join(",", classes.ToArray())
            + "],\"sameProcessAsRoot\":[" + String.Join(",", sameProcess.ToArray())
            + "],\"sameThreadAsRoot\":[" + String.Join(",", sameThread.ToArray())
            + "],\"rootReached\":" + (reachedRoot ? "true" : "false") + "}";
    }

    // The caller must run PowerShell -STA in the same interactive Windows session
    // as the destination. The result deliberately excludes source paths.
    public static string Run(string[] paths, int x, int y, long expectedRoot, int timeoutMs)
    {
        if (paths == null || paths.Length < 1 || paths.Length > 4 || timeoutMs < 1000 || timeoutMs > 15000)
            throw new ArgumentException("drag-request-invalid");
        IntPtr root = new IntPtr(expectedRoot);
        if (root == IntPtr.Zero || !AtWindow(x, y, root))
        {
            Console.Error.WriteLine("ole-drag-target-mismatch-hit=" + DescribeTargetAtPoint(x, y, expectedRoot));
            throw new InvalidOperationException("drag-target-window-mismatch");
        }
        Console.Error.WriteLine("ole-drag-target-verified");

        Point previous;
        if (!GetCursorPos(out previous))
            throw new InvalidOperationException("cursor-unavailable-win32-" + Marshal.GetLastWin32Error());
        Console.Error.WriteLine("ole-drag-input-desktop-verified");

        DragDropEffects effect = DragDropEffects.None;
        string failure = null;
        bool motionHitTestMatched = false;
        string motionTarget = "null";
        bool dropRequested = false;
        Stopwatch elapsed = Stopwatch.StartNew();
        using (QuietSourceForm source = new QuietSourceForm())
        {
            source.ShowInTaskbar = false;
            source.StartPosition = FormStartPosition.Manual;
            // Begin over our own tiny source HWND so the first OLE target is
            // never an unrelated application or the receiver itself.
            source.Bounds = new Rectangle(10, 10, 20, 20);
            source.TopMost = true;
            source.Shown += delegate
            {
                source.BeginInvoke((Action)delegate
                {
                    try
                    {
                        DataObject data = new DataObject();
                        data.SetData(DataFormats.FileDrop, false, paths);
                        int phase = 0;
                        int queryCount = 0;
                        source.QueryContinueDrag += delegate(object sender, QueryContinueDragEventArgs eventArgs)
                        {
                            int current = Volatile.Read(ref phase);
                            if (Interlocked.Increment(ref queryCount) <= 3)
                                Console.Error.WriteLine("ole-drag-query-phase=" + current);
                            eventArgs.Action = current >= 3 ? DragAction.Cancel
                                : current == 2 ? DragAction.Drop : DragAction.Continue;
                        };
                        Thread motion = new Thread(delegate()
                        {
                            try
                            {
                                Thread.Sleep(100);
                                if (!SetCursorPos(x, y))
                                    throw new InvalidOperationException("cursor-move-unavailable");
                                motionHitTestMatched = AtWindow(x, y, root);
                                motionTarget = DescribeTargetAtPoint(x, y, expectedRoot);
                                Volatile.Write(ref phase, 1);
                                Console.Error.WriteLine("ole-drag-moved-to-target-hit=" + motionHitTestMatched);
                                Thread.Sleep(120);
                                dropRequested = true;
                                Volatile.Write(ref phase, 2);
                                Console.Error.WriteLine("ole-drag-drop-requested");
                                Thread.Sleep(timeoutMs);
                                if (Volatile.Read(ref phase) == 2)
                                {
                                    failure = "drag-timeout";
                                    Volatile.Write(ref phase, 3);
                                }
                            }
                            catch (Exception)
                            {
                                failure = "drag-motion-failed";
                                Volatile.Write(ref phase, 3);
                            }
                        });
                        motion.IsBackground = true;
                        if (!SetCursorPos(20, 20))
                            throw new InvalidOperationException("cursor-start-unavailable");
                        motion.Start();
                        Console.Error.WriteLine("ole-drag-loop-enter");
                        effect = source.DoDragDrop(data, DragDropEffects.Copy);
                        Console.Error.WriteLine("ole-drag-loop-exit");
                        Volatile.Write(ref phase, 4);
                    }
                    catch (Exception) { failure = "drag-source-failed"; }
                    finally { source.Close(); }
                });
            };
            Application.Run(source);
        }
        SetCursorPos(previous.X, previous.Y);
        elapsed.Stop();
        return "{\"kind\":\"windows-ole-file-drag\",\"sourceCount\":" + paths.Length
            + ",\"initialTargetWindowConfirmed\":true"
            + ",\"motionHitTestMatched\":" + (motionHitTestMatched ? "true" : "false")
            + ",\"motionTarget\":" + motionTarget
            + ",\"dropRequested\":" + (dropRequested ? "true" : "false")
            + ",\"effect\":\"" + effect.ToString() + "\""
            + ",\"elapsedMilliseconds\":" + elapsed.ElapsedMilliseconds
            + ",\"failureCode\":" + (failure == null ? "null" : "\"" + failure.Replace("\"", "") + "\"") + "}";
    }
}
