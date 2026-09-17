using System;
using System.Drawing;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;

namespace ExpandedChrSync
{
    internal sealed class ChrAnalysis
    {
        public int ShadowOffset;
        public int ActiveOffset;
        public int Size;
        public int MismatchCount;
        public int FirstShadowDifference;
        public int LastShadowDifference;
    }

    internal sealed class SyncResult
    {
        public ChrAnalysis Analysis;
        public string SourceHash;
        public string OutputHash;
    }

    internal static class RomSync
    {
        public const int ExpectedFileSize = 0x140010;
        public const int ShadowOffset = 0x080010;
        public const int ActiveOffset = 0x100010;
        public const int ChrSize = 0x040000;

        private static void ValidateRom(byte[] data)
        {
            if (data.Length < 16 || data[0] != 0x4E || data[1] != 0x45 ||
                data[2] != 0x53 || data[3] != 0x1A)
                throw new InvalidDataException("不是有效的 iNES ROM。");

            int flags6 = data[6];
            int flags7 = data[7];
            if ((flags7 & 0x0C) == 0x08)
                throw new InvalidDataException("暂不支持 NES 2.0 文件头。");
            if ((flags6 & 0x04) != 0)
                throw new InvalidDataException("带 Trainer 的 ROM 不属于已验证布局。");

            int mapper = (flags6 >> 4) | (flags7 & 0xF0);
            int prgSize = data[4] * 0x4000;
            int chrSize = data[5] * 0x2000;
            if (mapper != 194)
                throw new InvalidDataException(string.Format("需要 Mapper 194，当前是 Mapper {0}。", mapper));
            if (prgSize != 0x100000)
                throw new InvalidDataException("只能处理 1 MiB PRG 扩容 ROM。");
            if (chrSize != ChrSize)
                throw new InvalidDataException("需要 256 KiB CHR。");
            if (data.Length != ExpectedFileSize)
                throw new InvalidDataException(
                    string.Format("文件大小应为 0x{0:X}，当前是 0x{1:X}。", ExpectedFileSize, data.Length));
        }

        public static ChrAnalysis Analyze(byte[] data)
        {
            ValidateRom(data);
            ChrAnalysis analysis = new ChrAnalysis();
            analysis.ShadowOffset = ShadowOffset;
            analysis.ActiveOffset = ActiveOffset;
            analysis.Size = ChrSize;
            analysis.FirstShadowDifference = -1;
            analysis.LastShadowDifference = -1;

            for (int relative = 0; relative < ChrSize; relative++)
            {
                if (data[ShadowOffset + relative] == data[ActiveOffset + relative])
                    continue;
                analysis.MismatchCount++;
                if (analysis.FirstShadowDifference < 0)
                    analysis.FirstShadowDifference = ShadowOffset + relative;
                analysis.LastShadowDifference = ShadowOffset + relative;
            }
            return analysis;
        }

        private static string Sha256(byte[] data)
        {
            using (SHA256 algorithm = SHA256.Create())
            {
                byte[] hash = algorithm.ComputeHash(data);
                StringBuilder builder = new StringBuilder(hash.Length * 2);
                for (int index = 0; index < hash.Length; index++)
                    builder.Append(hash[index].ToString("X2"));
                return builder.ToString();
            }
        }

        private static bool SamePath(string left, string right)
        {
            return string.Equals(
                Path.GetFullPath(left), Path.GetFullPath(right), StringComparison.OrdinalIgnoreCase);
        }

        public static SyncResult SaveSynchronizedCopy(string sourcePath, string destinationPath)
        {
            if (SamePath(sourcePath, destinationPath))
                throw new InvalidOperationException("为保护源 ROM，请另存为新文件。");

            byte[] original = File.ReadAllBytes(sourcePath);
            ChrAnalysis analysis = Analyze(original);
            byte[] output = (byte[])original.Clone();
            Buffer.BlockCopy(original, ShadowOffset, output, ActiveOffset, ChrSize);

            int changed = 0;
            int outside = 0;
            for (int index = 0; index < original.Length; index++)
            {
                if (original[index] == output[index])
                    continue;
                changed++;
                if (index < ActiveOffset || index >= ActiveOffset + ChrSize)
                    outside++;
            }
            if (changed != analysis.MismatchCount || outside != 0)
                throw new InvalidOperationException(
                    string.Format("CHR 同步边界验证失败：changed={0}, outside={1}。", changed, outside));

            string destinationDirectory = Path.GetDirectoryName(Path.GetFullPath(destinationPath));
            if (!Directory.Exists(destinationDirectory))
                Directory.CreateDirectory(destinationDirectory);
            string temporaryPath = Path.Combine(
                destinationDirectory,
                "." + Path.GetFileName(destinationPath) + "." + Guid.NewGuid().ToString("N") + ".tmp");
            try
            {
                File.WriteAllBytes(temporaryPath, output);
                if (File.Exists(destinationPath))
                    File.Replace(temporaryPath, destinationPath, null);
                else
                    File.Move(temporaryPath, destinationPath);
            }
            finally
            {
                if (File.Exists(temporaryPath))
                    File.Delete(temporaryPath);
            }

            byte[] written = File.ReadAllBytes(destinationPath);
            ChrAnalysis finalAnalysis = Analyze(written);
            if (finalAnalysis.MismatchCount != 0)
                throw new InvalidOperationException(
                    string.Format("保存后两份 CHR 仍有 {0} 字节不同。", finalAnalysis.MismatchCount));
            string outputHash = Sha256(output);
            if (!string.Equals(Sha256(written), outputHash, StringComparison.Ordinal))
                throw new InvalidOperationException("保存后 ROM 哈希与内存结果不一致。");

            SyncResult result = new SyncResult();
            result.Analysis = analysis;
            result.SourceHash = Sha256(original);
            result.OutputHash = outputHash;
            return result;
        }
    }

    internal sealed class MainForm : Form
    {
        private Button syncButton;
        private Label fileLabel;
        private Label layoutLabel;
        private Label diffLabel;
        private Label statusLabel;
        private string sourcePath;
        private ChrAnalysis analysis;

        public MainForm(string initialPath)
        {
            Text = "扩容 ROM 全 CHR 旧区→新区同步工具 1.1";
            ClientSize = new Size(760, 420);
            MinimumSize = new Size(720, 430);
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Microsoft YaHei UI", 9F);

            Label title = new Label();
            title.Text = "扩容 ROM 全 CHR 同步";
            title.Font = new Font(Font.FontFamily, 16F, FontStyle.Bold);
            title.AutoSize = true;
            title.Location = new Point(20, 18);
            Controls.Add(title);

            Label description = new Label();
            description.Text =
                "适用于：原版旧偏移修改器将图形写入 0x080010–0x0C000F\r\n" +
                "操作：将完整 256 KiB 旧 CHR 影子复制到 0x100010–0x14000F 活动 CHR";
            description.AutoSize = true;
            description.Location = new Point(22, 58);
            Controls.Add(description);

            Button openButton = new Button();
            openButton.Text = "1. 选择 ROM";
            openButton.Size = new Size(120, 34);
            openButton.Location = new Point(22, 105);
            openButton.Click += delegate { SelectRom(); };
            Controls.Add(openButton);

            syncButton = new Button();
            syncButton.Text = "2. 同步并另存";
            syncButton.Size = new Size(150, 34);
            syncButton.Location = new Point(152, 105);
            syncButton.Enabled = false;
            syncButton.Click += delegate { SynchronizeAndSave(); };
            Controls.Add(syncButton);

            GroupBox resultBox = new GroupBox();
            resultBox.Text = "检查结果";
            resultBox.Location = new Point(22, 150);
            resultBox.Size = new Size(716, 130);
            resultBox.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            Controls.Add(resultBox);

            fileLabel = MakeLabel(new Point(14, 25), new Size(685, 34));
            fileLabel.Text = "请选择经旧修改器保存的扩容 ROM。";
            resultBox.Controls.Add(fileLabel);
            layoutLabel = MakeLabel(new Point(14, 62), new Size(685, 22));
            resultBox.Controls.Add(layoutLabel);
            diffLabel = MakeLabel(new Point(14, 91), new Size(685, 24));
            diffLabel.ForeColor = Color.FromArgb(154, 52, 18);
            resultBox.Controls.Add(diffLabel);

            GroupBox warningBox = new GroupBox();
            warningBox.Text = "不要混用";
            warningBox.Location = new Point(22, 292);
            warningBox.Size = new Size(716, 80);
            warningBox.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            Controls.Add(warningBox);
            Label warning = MakeLabel(new Point(14, 23), new Size(685, 48));
            warning.ForeColor = Color.FromArgb(185, 28, 28);
            warning.Text =
                "只能在原版旧偏移修改器保存后使用。\r\n" +
                "若修改器已直接写活动 CHR，再做旧→新同步会覆盖新修改。";
            warningBox.Controls.Add(warning);

            statusLabel = MakeLabel(new Point(22, 385), new Size(715, 25));
            statusLabel.Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Bottom;
            statusLabel.Text = "源 ROM 始终保留，同步结果只能另存。";
            Controls.Add(statusLabel);

            if (!string.IsNullOrEmpty(initialPath))
                Shown += delegate { OpenRom(initialPath); };
        }

        private static Label MakeLabel(Point location, Size size)
        {
            Label label = new Label();
            label.Location = location;
            label.Size = size;
            label.AutoEllipsis = true;
            return label;
        }

        private void SelectRom()
        {
            using (OpenFileDialog dialog = new OpenFileDialog())
            {
                dialog.Title = "选择扩容 ROM";
                dialog.Filter = "NES ROM (*.nes)|*.nes|所有文件 (*.*)|*.*";
                if (dialog.ShowDialog(this) == DialogResult.OK)
                    OpenRom(dialog.FileName);
            }
        }

        private void OpenRom(string path)
        {
            try
            {
                byte[] data = File.ReadAllBytes(path);
                ChrAnalysis loadedAnalysis = RomSync.Analyze(data);
                sourcePath = path;
                analysis = loadedAnalysis;
                fileLabel.Text = path;
                layoutLabel.Text = string.Format(
                    "旧 CHR：0x{0:X6}–0x{1:X6}  |  活动 CHR：0x{2:X6}–0x{3:X6}",
                    loadedAnalysis.ShadowOffset,
                    loadedAnalysis.ShadowOffset + loadedAnalysis.Size - 1,
                    loadedAnalysis.ActiveOffset,
                    loadedAnalysis.ActiveOffset + loadedAnalysis.Size - 1);
                if (loadedAnalysis.MismatchCount == 0)
                {
                    diffLabel.Text = "两份 CHR 完全一致，无需同步。如图片确已改动，修改可能在 PRG 指针/排列表中。";
                    syncButton.Enabled = false;
                    statusLabel.Text = "当前 ROM 已同步，未生成无意义副本。";
                }
                else
                {
                    diffLabel.Text = string.Format(
                        "需同步 {0} 字节；旧区差异范围 0x{1:X6}–0x{2:X6}。",
                        loadedAnalysis.MismatchCount,
                        loadedAnalysis.FirstShadowDifference,
                        loadedAnalysis.LastShadowDifference);
                    syncButton.Enabled = true;
                    statusLabel.Text = "已就绪。输出将另存，不覆盖当前 ROM。";
                }
            }
            catch (Exception error)
            {
                sourcePath = null;
                analysis = null;
                syncButton.Enabled = false;
                MessageBox.Show(this, error.Message, "无法使用该 ROM", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void SynchronizeAndSave()
        {
            if (string.IsNullOrEmpty(sourcePath) || analysis == null || analysis.MismatchCount == 0)
                return;
            DialogResult confirm = MessageBox.Show(
                this,
                "确认将旧 CHR 作为权威数据，覆盖活动 CHR？\r\n\r\n" +
                "只有刚使用原版旧偏移修改器时才应选“是”。",
                "确认同步方向",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Warning);
            if (confirm != DialogResult.Yes)
                return;

            using (SaveFileDialog dialog = new SaveFileDialog())
            {
                dialog.Title = "另存同步后的 ROM";
                dialog.Filter = "NES ROM (*.nes)|*.nes|所有文件 (*.*)|*.*";
                dialog.DefaultExt = "nes";
                dialog.InitialDirectory = Path.GetDirectoryName(sourcePath);
                dialog.FileName = Path.GetFileNameWithoutExtension(sourcePath) + "_CHR已同步.nes";
                if (dialog.ShowDialog(this) != DialogResult.OK)
                    return;
                try
                {
                    SyncResult result = RomSync.SaveSynchronizedCopy(sourcePath, dialog.FileName);
                    statusLabel.Text = string.Format(
                        "已生成：{0}  |  同步 {1} 字节",
                        dialog.FileName,
                        result.Analysis.MismatchCount);
                    MessageBox.Show(
                        this,
                        string.Format(
                            "同步完成，源 ROM 未覆盖。\r\n\r\n" +
                            "实际更新：{0} 字节\r\n输出 SHA-256：{1}",
                            result.Analysis.MismatchCount,
                            result.OutputHash),
                        "同步完成",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information);
                }
                catch (Exception error)
                {
                    MessageBox.Show(this, error.Message, "同步失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
        }
    }

    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            if (args.Length == 4 && string.Equals(args[0], "--self-test", StringComparison.OrdinalIgnoreCase))
            {
                try
                {
                    SyncResult result = RomSync.SaveSynchronizedCopy(args[1], args[2]);
                    string report = string.Format(
                        "mismatchCount={0}\r\nsourceSha256={1}\r\noutputSha256={2}\r\n",
                        result.Analysis.MismatchCount,
                        result.SourceHash,
                        result.OutputHash);
                    File.WriteAllText(args[3], report, new UTF8Encoding(false));
                    return 0;
                }
                catch (Exception error)
                {
                    try
                    {
                        File.WriteAllText(args[3], "error=" + error.ToString(), new UTF8Encoding(false));
                    }
                    catch
                    {
                    }
                    return 2;
                }
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            string initialPath = args.Length > 0 ? args[0] : null;
            Application.Run(new MainForm(initialPath));
            return 0;
        }
    }
}

