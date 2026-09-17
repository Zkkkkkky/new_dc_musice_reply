using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace NewDcExpandedModifierLauncher
{
    internal static class Program
    {
        private const int LauncherButtonId = 110;
        private const uint BmClick = 0x00F5;
        private const int SwHide = 0;
        private const int SwShow = 5;
        private const int SwRestore = 9;
        private const uint SwpNoSize = 0x0001;
        private const uint SwpNoActivate = 0x0010;
        private const uint SwpHideWindow = 0x0080;
        private const uint SwpNoOwnerZOrder = 0x0200;
        private const uint EventObjectCreate = 0x8000;
        private const uint EventObjectShow = 0x8002;
        private const uint WineventOutOfContext = 0x0000;
        private const int ObjidWindow = 0;
        private const uint WmQuit = 0x0012;
        private const int FilePollMilliseconds = 250;
        private const int FileStableMilliseconds = 800;
        private const string LauncherTitle = "SRW2修改器V1.5";
        private const string MainTitlePrefix = "SRW2扩容版修改器V1.0";
        private const string ExpectedEngineSha256 =
            "4C7F2980CC780253050174C7A6E00A506C7D1EA29E74B90128BDA9ABD9335947";

        private delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);
        private delegate void WinEventProc(
            IntPtr hook,
            uint eventType,
            IntPtr hwnd,
            int objectId,
            int childId,
            uint eventThread,
            uint eventTime);

        [StructLayout(LayoutKind.Sequential)]
        private struct Message
        {
            public IntPtr hwnd;
            public uint value;
            public IntPtr wParam;
            public IntPtr lParam;
            public uint time;
            public int pointX;
            public int pointY;
        }

        private static WinEventProc eventCallback;
        private static IntPtr eventHook = IntPtr.Zero;
        private static int engineProcessId;
        private static IntPtr hiddenLauncher = IntPtr.Zero;
        private static DateTime launcherReadyUtc = DateTime.MinValue;
        private static readonly ManualResetEvent HookReady = new ManualResetEvent(false);
        private static uint hookThreadId;
        private static Exception hookThreadError;

        private sealed class RomTracker
        {
            public string Path;
            public RomSnapshot Baseline;
            public long ObservedLength;
            public long ObservedWriteTicks;
            public DateTime PendingSinceUtc;
            public DateTime FirstFailureUtc;
        }

        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);

        [DllImport("user32.dll")]
        private static extern IntPtr GetDlgItem(IntPtr hwnd, int controlId);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int capacity);

        [DllImport("user32.dll")]
        private static extern int GetWindowTextLength(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern bool IsWindow(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern bool PostMessage(IntPtr hwnd, uint message, IntPtr wParam, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern bool ShowWindow(IntPtr hwnd, int command);

        [DllImport("user32.dll")]
        private static extern bool ShowWindowAsync(IntPtr hwnd, int command);

        [DllImport("user32.dll")]
        private static extern bool SetWindowPos(
            IntPtr hwnd,
            IntPtr insertAfter,
            int x,
            int y,
            int width,
            int height,
            uint flags);

        [DllImport("user32.dll")]
        private static extern bool SetForegroundWindow(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern IntPtr SetWinEventHook(
            uint eventMin,
            uint eventMax,
            IntPtr module,
            WinEventProc callback,
            uint processId,
            uint threadId,
            uint flags);

        [DllImport("user32.dll")]
        private static extern bool UnhookWinEvent(IntPtr hook);

        [DllImport("user32.dll")]
        private static extern int GetMessage(out Message message, IntPtr hwnd, uint minimum, uint maximum);

        [DllImport("user32.dll")]
        private static extern bool TranslateMessage(ref Message message);

        [DllImport("user32.dll")]
        private static extern IntPtr DispatchMessage(ref Message message);

        [DllImport("user32.dll")]
        private static extern bool PostThreadMessage(uint threadId, uint message, IntPtr wParam, IntPtr lParam);

        [DllImport("kernel32.dll")]
        private static extern uint GetCurrentThreadId();

        [STAThread]
        private static int Main(string[] args)
        {
            if (args.Length != 0)
                return RunCommandLine(args);

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
            string enginePath = Path.Combine(baseDirectory, "内部文件", "修改器核心.exe");
            try
            {
                ValidateEngine(enginePath);
                using (Process engine = StartEngineWithHiddenLauncher(enginePath, baseDirectory))
                {
                    try
                    {
                        return EnterMainWindow(engine);
                    }
                    finally
                    {
                        StopWindowHook();
                    }
                }
            }
            catch (Exception error)
            {
                MessageBox.Show(
                    "无法启动新DC扩容专用修改器：\r\n\r\n" + error.Message,
                    "新DC扩容专用修改器",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return 1;
            }
        }

        private static int RunCommandLine(string[] args)
        {
            try
            {
                if (args.Length == 4 &&
                    string.Equals(args[0], "--reconcile-copy", StringComparison.Ordinal))
                {
                    ChrReconciler.ReconcileCopy(args[1], args[2], args[3]);
                    return 0;
                }
                return 64;
            }
            catch
            {
                return 2;
            }
        }

        private static int EnterMainWindow(Process engine)
        {
            DateTime deadline = DateTime.UtcNow.AddSeconds(25);
            bool enterPosted = false;

            while (DateTime.UtcNow < deadline)
            {
                Application.DoEvents();
                if (engine.HasExited)
                    throw new InvalidOperationException("修改器核心在主界面出现前已经退出。");

                if (!enterPosted)
                {
                    IntPtr launcher = hiddenLauncher;
                    if (launcher == IntPtr.Zero || !IsWindow(launcher))
                    {
                        launcher = FindWindowForProcess(
                            engine.Id,
                            delegate(IntPtr hwnd)
                            {
                                return string.Equals(
                                    ReadWindowTitle(hwnd),
                                    LauncherTitle,
                                    StringComparison.Ordinal) &&
                                    GetDlgItem(hwnd, LauncherButtonId) != IntPtr.Zero;
                            });
                    }
                    if (launcher != IntPtr.Zero)
                    {
                        ConcealLauncher(launcher);
                        if (launcherReadyUtc == DateTime.MinValue)
                            launcherReadyUtc = DateTime.UtcNow;
                        if ((DateTime.UtcNow - launcherReadyUtc).TotalSeconds >= 3.0)
                        {
                            IntPtr enterButton = GetDlgItem(launcher, LauncherButtonId);
                            if (!PostMessage(enterButton, BmClick, IntPtr.Zero, IntPtr.Zero))
                                throw new InvalidOperationException("无法触发旧启动页的进入按钮。");
                            enterPosted = true;
                        }
                    }
                }

                IntPtr mainWindow = FindWindowForProcess(
                    engine.Id,
                    delegate(IntPtr hwnd)
                    {
                        return ReadWindowTitle(hwnd).StartsWith(
                            MainTitlePrefix,
                            StringComparison.Ordinal);
                    });
                if (mainWindow != IntPtr.Zero && IsWindow(mainWindow))
                {
                    StopWindowHook();
                    ShowWindow(mainWindow, SwRestore);
                    ShowWindow(mainWindow, SwShow);
                    SetForegroundWindow(mainWindow);
                    return MonitorRomSaves(engine, mainWindow);
                }
                Thread.Sleep(5);
            }

            try
            {
                if (!engine.HasExited)
                    engine.Kill();
            }
            catch
            {
                // The timeout error below is more useful than a cleanup error.
            }
            throw new TimeoutException("等待修改器主界面超时；隐藏的旧启动页已终止。");
        }

        private static int MonitorRomSaves(Process engine, IntPtr mainWindow)
        {
            RomTracker tracker = null;
            while (!engine.HasExited)
            {
                Application.DoEvents();
                if (mainWindow == IntPtr.Zero || !IsWindow(mainWindow))
                {
                    mainWindow = FindWindowForProcess(
                        engine.Id,
                        delegate(IntPtr hwnd)
                        {
                            return ReadWindowTitle(hwnd).StartsWith(
                                MainTitlePrefix,
                                StringComparison.Ordinal);
                        });
                }

                string romPath = ExtractRomPath(mainWindow);
                if (!string.IsNullOrEmpty(romPath) && File.Exists(romPath))
                    tracker = ObserveRomPath(tracker, romPath);
                if (tracker != null)
                    PollRomTracker(tracker, false);
                Thread.Sleep(FilePollMilliseconds);
            }

            if (tracker != null && tracker.PendingSinceUtc != DateTime.MinValue)
                PollRomTracker(tracker, true);
            return engine.ExitCode;
        }

        private static RomTracker ObserveRomPath(RomTracker tracker, string romPath)
        {
            string fullPath = Path.GetFullPath(romPath);
            if (tracker != null &&
                string.Equals(tracker.Path, fullPath, StringComparison.OrdinalIgnoreCase))
                return tracker;

            FileInfo info = new FileInfo(fullPath);
            bool recentFile = Math.Abs((DateTime.UtcNow - info.LastWriteTimeUtc).TotalSeconds) <= 10.0;
            RomSnapshot baseline = null;
            if (tracker != null && recentFile)
                baseline = tracker.Baseline;

            try
            {
                RomTracker next = new RomTracker();
                next.Path = fullPath;
                next.Baseline = baseline ?? ChrReconciler.Capture(fullPath);
                next.ObservedLength = info.Length;
                next.ObservedWriteTicks = info.LastWriteTimeUtc.Ticks;
                next.PendingSinceUtc = baseline == null ? DateTime.MinValue : DateTime.UtcNow;
                next.FirstFailureUtc = DateTime.MinValue;
                return next;
            }
            catch (Exception error)
            {
                MessageBox.Show(
                    "无法监控当前 ROM 的扩容 CHR 写入：\r\n\r\n" +
                    fullPath + "\r\n\r\n" + error.Message,
                    "新DC扩容专用修改器",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return null;
            }
        }

        private static void PollRomTracker(RomTracker tracker, bool force)
        {
            try
            {
                FileInfo info = new FileInfo(tracker.Path);
                if (!info.Exists)
                    return;
                if (info.Length != tracker.ObservedLength ||
                    info.LastWriteTimeUtc.Ticks != tracker.ObservedWriteTicks)
                {
                    tracker.ObservedLength = info.Length;
                    tracker.ObservedWriteTicks = info.LastWriteTimeUtc.Ticks;
                    tracker.PendingSinceUtc = DateTime.UtcNow;
                    tracker.FirstFailureUtc = DateTime.MinValue;
                    return;
                }
                if (tracker.PendingSinceUtc == DateTime.MinValue)
                    return;
                if (!force &&
                    (DateTime.UtcNow - tracker.PendingSinceUtc).TotalMilliseconds <
                    FileStableMilliseconds)
                    return;

                ReconcileResult result = ChrReconciler.ReconcileFileInPlace(
                    tracker.Baseline,
                    tracker.Path);
                if (result.Conflicts != 0)
                {
                    tracker.PendingSinceUtc = DateTime.MinValue;
                    MessageBox.Show(
                        "检测到 " + result.Conflicts +
                        " 个旧影子与活动 CHR 的双向冲突。为避免覆盖数据，本次没有自动同步：\r\n\r\n" +
                        tracker.Path,
                        "新DC扩容专用修改器",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Warning);
                    return;
                }

                tracker.Baseline = ChrReconciler.Capture(tracker.Path);
                tracker.ObservedLength = tracker.Baseline.Length;
                tracker.ObservedWriteTicks = tracker.Baseline.LastWriteUtcTicks;
                tracker.PendingSinceUtc = DateTime.MinValue;
                tracker.FirstFailureUtc = DateTime.MinValue;
                if (result.SynchronizedBytes != 0)
                {
                    MessageBox.Show(
                        "扩容 CHR 已自动同步。\r\n\r\n" +
                        "旧影子 → 活动 CHR：" + result.ShadowToActive + " 字节\r\n" +
                        "活动 CHR → 旧影子：" + result.ActiveToShadow + " 字节\r\n\r\n" +
                        tracker.Path,
                        "新DC扩容专用修改器",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information);
                }
            }
            catch (IOException error)
            {
                if (tracker.FirstFailureUtc == DateTime.MinValue)
                    tracker.FirstFailureUtc = DateTime.UtcNow;
                if (force || (DateTime.UtcNow - tracker.FirstFailureUtc).TotalSeconds >= 8.0)
                {
                    tracker.PendingSinceUtc = DateTime.MinValue;
                    MessageBox.Show(
                        "ROM 保存后无法完成扩容 CHR 自动同步：\r\n\r\n" +
                        tracker.Path + "\r\n\r\n" + error.Message,
                        "新DC扩容专用修改器",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                }
            }
            catch (Exception error)
            {
                tracker.PendingSinceUtc = DateTime.MinValue;
                MessageBox.Show(
                    "ROM 保存后扩容 CHR 自动同步失败：\r\n\r\n" +
                    tracker.Path + "\r\n\r\n" + error.Message,
                    "新DC扩容专用修改器",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }

        private static string ExtractRomPath(IntPtr mainWindow)
        {
            if (mainWindow == IntPtr.Zero || !IsWindow(mainWindow))
                return null;
            string title = ReadWindowTitle(mainWindow);
            if (!title.StartsWith(MainTitlePrefix, StringComparison.Ordinal))
                return null;
            string suffix = title.Substring(MainTitlePrefix.Length).Trim();
            while (suffix.StartsWith(":", StringComparison.Ordinal) ||
                   suffix.StartsWith("：", StringComparison.Ordinal) ||
                   suffix.StartsWith("-", StringComparison.Ordinal))
                suffix = suffix.Substring(1).Trim();
            int extension = suffix.LastIndexOf(".nes", StringComparison.OrdinalIgnoreCase);
            if (extension < 0)
                return null;
            string candidate = suffix.Substring(0, extension + 4).Trim();
            return Path.IsPathRooted(candidate) ? candidate : null;
        }

        private static Process StartEngineWithHiddenLauncher(string enginePath, string workingDirectory)
        {
            hiddenLauncher = IntPtr.Zero;
            launcherReadyUtc = DateTime.MinValue;
            engineProcessId = 0;
            StartWindowHook();

            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = enginePath;
            startInfo.WorkingDirectory = workingDirectory;
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = false;
            startInfo.WindowStyle = ProcessWindowStyle.Normal;
            Process engine = Process.Start(startInfo);
            if (engine == null)
            {
                StopWindowHook();
                throw new InvalidOperationException("修改器核心没有启动。");
            }
            engineProcessId = engine.Id;
            return engine;
        }

        private static void StartWindowHook()
        {
            hookThreadError = null;
            hookThreadId = 0;
            HookReady.Reset();
            Thread thread = new Thread(WindowHookThread);
            thread.Name = "旧启动页隐藏监听器";
            thread.IsBackground = true;
            thread.SetApartmentState(ApartmentState.STA);
            thread.Start();
            if (!HookReady.WaitOne(TimeSpan.FromSeconds(5)))
                throw new TimeoutException("启动页隐藏监听器没有及时就绪。");
            if (hookThreadError != null)
                throw new InvalidOperationException("无法启动启动页隐藏监听器。", hookThreadError);
        }

        private static void WindowHookThread()
        {
            try
            {
                hookThreadId = GetCurrentThreadId();
                eventCallback = OnWindowEvent;
                eventHook = SetWinEventHook(
                    EventObjectCreate,
                    EventObjectShow,
                    IntPtr.Zero,
                    eventCallback,
                    0,
                    0,
                    WineventOutOfContext);
                if (eventHook == IntPtr.Zero)
                {
                    throw new System.ComponentModel.Win32Exception(
                        Marshal.GetLastWin32Error(),
                        "无法安装启动页隐藏监听器。");
                }
                HookReady.Set();
                Message message;
                while (GetMessage(out message, IntPtr.Zero, 0, 0) > 0)
                {
                    TranslateMessage(ref message);
                    DispatchMessage(ref message);
                }
            }
            catch (Exception error)
            {
                hookThreadError = error;
                HookReady.Set();
            }
            finally
            {
                if (eventHook != IntPtr.Zero)
                {
                    UnhookWinEvent(eventHook);
                    eventHook = IntPtr.Zero;
                }
                hookThreadId = 0;
            }
        }

        private static void StopWindowHook()
        {
            uint threadId = hookThreadId;
            if (threadId != 0)
                PostThreadMessage(threadId, WmQuit, IntPtr.Zero, IntPtr.Zero);
        }

        private static void OnWindowEvent(
            IntPtr hook,
            uint eventType,
            IntPtr hwnd,
            int objectId,
            int childId,
            uint eventThread,
            uint eventTime)
        {
            if (objectId != ObjidWindow || hwnd == IntPtr.Zero)
                return;
            uint owner;
            GetWindowThreadProcessId(hwnd, out owner);
            if ((engineProcessId != 0 && owner != (uint)engineProcessId) ||
                !string.Equals(ReadWindowTitle(hwnd), LauncherTitle, StringComparison.Ordinal))
                return;

            ConcealLauncher(hwnd);
            hiddenLauncher = hwnd;
            if (launcherReadyUtc == DateTime.MinValue)
                launcherReadyUtc = DateTime.UtcNow;
        }

        private static void ConcealLauncher(IntPtr hwnd)
        {
            // The legacy VB program repeatedly shows its startup form while loading.
            // Moving it outside the virtual desktop as well as hiding it prevents the
            // Tieba/QQ page from flashing even if VB immediately calls Show again.
            SetWindowPos(
                hwnd,
                new IntPtr(1),
                -32000,
                -32000,
                0,
                0,
                SwpNoSize | SwpNoActivate | SwpHideWindow | SwpNoOwnerZOrder);
            ShowWindowAsync(hwnd, SwHide);
            ShowWindow(hwnd, SwHide);
        }

        private static IntPtr FindWindowForProcess(int processId, Predicate<IntPtr> predicate)
        {
            IntPtr result = IntPtr.Zero;
            EnumWindows(
                delegate(IntPtr hwnd, IntPtr lParam)
                {
                    uint owner;
                    GetWindowThreadProcessId(hwnd, out owner);
                    if (owner == (uint)processId && predicate(hwnd))
                    {
                        result = hwnd;
                        return false;
                    }
                    return true;
                },
                IntPtr.Zero);
            return result;
        }

        private static string ReadWindowTitle(IntPtr hwnd)
        {
            int length = GetWindowTextLength(hwnd);
            StringBuilder text = new StringBuilder(Math.Max(length + 1, 2));
            GetWindowText(hwnd, text, text.Capacity);
            return text.ToString();
        }

        private static void ValidateEngine(string path)
        {
            if (!File.Exists(path))
                throw new FileNotFoundException("缺少内部修改器核心。", path);

            string actual;
            using (SHA256 algorithm = SHA256.Create())
            using (FileStream stream = File.OpenRead(path))
            {
                actual = BitConverter.ToString(algorithm.ComputeHash(stream)).Replace("-", "");
            }
            if (!string.Equals(actual, ExpectedEngineSha256, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    "内部修改器核心校验失败。\r\n期望：" + ExpectedEngineSha256 +
                    "\r\n实际：" + actual);
            }
        }
    }
}
