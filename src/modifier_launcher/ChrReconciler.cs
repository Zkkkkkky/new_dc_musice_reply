using System;
using System.Diagnostics;
using System.IO;

namespace NewDcExpandedModifierLauncher
{
    internal sealed class RomSnapshot
    {
        public string Path;
        public byte[] Shadow;
        public byte[] Active;
        public long Length;
        public long LastWriteUtcTicks;
    }

    internal sealed class ReconcileResult
    {
        public byte[] Output;
        public int ShadowToActive;
        public int ActiveToShadow;
        public int Conflicts;

        public int SynchronizedBytes
        {
            get { return ShadowToActive + ActiveToShadow; }
        }
    }

    internal static class ChrReconciler
    {
        internal const int ExpectedRomSize = 0x140010;
        internal const int ChrSize = 0x40000;
        internal const int ShadowOffset = 0x080010;
        internal const int ActiveOffset = 0x100010;

        internal static RomSnapshot Capture(string path)
        {
            byte[] rom = ReadAndValidate(path);
            FileInfo info = new FileInfo(path);
            RomSnapshot snapshot = new RomSnapshot();
            snapshot.Path = System.IO.Path.GetFullPath(path);
            snapshot.Shadow = Slice(rom, ShadowOffset, ChrSize);
            snapshot.Active = Slice(rom, ActiveOffset, ChrSize);
            snapshot.Length = info.Length;
            snapshot.LastWriteUtcTicks = info.LastWriteTimeUtc.Ticks;
            return snapshot;
        }

        internal static ReconcileResult Reconcile(RomSnapshot baseline, byte[] current)
        {
            ValidateRom(current);
            if (baseline == null || baseline.Shadow == null || baseline.Active == null ||
                baseline.Shadow.Length != ChrSize || baseline.Active.Length != ChrSize)
                throw new InvalidDataException("缺少有效的保存前 CHR 快照。");

            byte[] output = (byte[])current.Clone();
            int shadowToActive = 0;
            int activeToShadow = 0;
            int conflicts = 0;

            for (int relative = 0; relative < ChrSize; relative++)
            {
                byte oldShadow = baseline.Shadow[relative];
                byte oldActive = baseline.Active[relative];
                byte newShadow = current[ShadowOffset + relative];
                byte newActive = current[ActiveOffset + relative];
                bool shadowChanged = newShadow != oldShadow;
                bool activeChanged = newActive != oldActive;

                if (shadowChanged && !activeChanged)
                {
                    output[ActiveOffset + relative] = newShadow;
                    shadowToActive++;
                }
                else if (!shadowChanged && activeChanged)
                {
                    output[ShadowOffset + relative] = newActive;
                    activeToShadow++;
                }
                else if (shadowChanged && activeChanged && newShadow != newActive)
                {
                    conflicts++;
                }
            }

            ReconcileResult result = new ReconcileResult();
            result.Output = output;
            result.ShadowToActive = shadowToActive;
            result.ActiveToShadow = activeToShadow;
            result.Conflicts = conflicts;
            return result;
        }

        internal static ReconcileResult ReconcileFileInPlace(
            RomSnapshot baseline,
            string currentPath)
        {
            byte[] current = ReadAndValidate(currentPath);
            ReconcileResult result = Reconcile(baseline, current);
            if (result.Conflicts != 0)
                return result;
            if (result.SynchronizedBytes != 0)
                ReplaceFileAtomically(currentPath, result.Output);
            return result;
        }

        internal static void ReconcileCopy(
            string baselinePath,
            string currentPath,
            string outputPath)
        {
            string baselineFull = System.IO.Path.GetFullPath(baselinePath);
            string currentFull = System.IO.Path.GetFullPath(currentPath);
            string outputFull = System.IO.Path.GetFullPath(outputPath);
            if (string.Equals(outputFull, baselineFull, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(outputFull, currentFull, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("测试输出不得覆盖输入 ROM。");

            RomSnapshot baseline = Capture(baselineFull);
            byte[] current = ReadAndValidate(currentFull);
            ReconcileResult result = Reconcile(baseline, current);
            if (result.Conflicts != 0)
                throw new InvalidDataException(
                    "检测到 " + result.Conflicts + " 个双向 CHR 冲突，未生成输出。");
            string parent = System.IO.Path.GetDirectoryName(outputFull);
            if (!string.IsNullOrEmpty(parent))
                Directory.CreateDirectory(parent);
            File.WriteAllBytes(outputFull, result.Output);
        }

        internal static byte[] ReadAndValidate(string path)
        {
            byte[] data;
            using (FileStream stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete))
            {
                if (stream.Length != ExpectedRomSize)
                    throw new InvalidDataException(
                        "ROM 大小必须为 1,310,736 字节，当前为 " + stream.Length + " 字节。");
                data = new byte[stream.Length];
                int total = 0;
                while (total < data.Length)
                {
                    int read = stream.Read(data, total, data.Length - total);
                    if (read == 0)
                        throw new EndOfStreamException("读取 ROM 时提前结束。");
                    total += read;
                }
            }
            ValidateRom(data);
            return data;
        }

        internal static void ValidateRom(byte[] data)
        {
            if (data == null || data.Length != ExpectedRomSize)
                throw new InvalidDataException("ROM 不是本项目的 1 MiB PRG 扩容格式。");
            if (data[0] != 0x4E || data[1] != 0x45 || data[2] != 0x53 || data[3] != 0x1A)
                throw new InvalidDataException("文件不是有效的 iNES ROM。");
            int mapper = (data[6] >> 4) | (data[7] & 0xF0);
            bool trainer = (data[6] & 0x04) != 0;
            if (data[4] != 0x40 || data[5] != 0x20 || mapper != 194 || trainer)
            {
                throw new InvalidDataException(
                    "只支持无 Trainer、Mapper 194、1 MiB PRG、256 KiB CHR 的扩容 ROM。");
            }
        }

        private static byte[] Slice(byte[] source, int offset, int length)
        {
            byte[] result = new byte[length];
            Buffer.BlockCopy(source, offset, result, 0, length);
            return result;
        }

        private static void ReplaceFileAtomically(string path, byte[] data)
        {
            string fullPath = System.IO.Path.GetFullPath(path);
            string directory = System.IO.Path.GetDirectoryName(fullPath);
            string temporary = System.IO.Path.Combine(
                directory,
                ".newdc-chr-sync-" + Process.GetCurrentProcess().Id + ".tmp");
            if (File.Exists(temporary))
                File.Delete(temporary);
            try
            {
                using (FileStream stream = new FileStream(
                    temporary,
                    FileMode.CreateNew,
                    FileAccess.Write,
                    FileShare.None,
                    65536,
                    FileOptions.WriteThrough))
                {
                    stream.Write(data, 0, data.Length);
                    stream.Flush(true);
                }
                File.Replace(temporary, fullPath, null, true);
            }
            finally
            {
                if (File.Exists(temporary))
                    File.Delete(temporary);
            }
        }
    }
}
