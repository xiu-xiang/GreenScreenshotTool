using ScreenshotTool.Services;

namespace ScreenshotTool.Controls;

/// <summary>
/// 编辑器内嵌结果侧栏：直接显示 OCR / 对照翻译，支持自由选中复制
/// </summary>
public sealed class ResultSidePanel : UserControl
{
    private readonly ResultMessenger _messenger;
    private readonly RichTextBox _view;
    private readonly Label _title;
    private readonly Label _status;
    private readonly Button _btnCopy;
    private readonly Button _btnCopyAll;
    private readonly Button _btnExport;
    private readonly Button _btnClose;
    private string _exportText = string.Empty;

    /// <summary>
    /// 用户点击收起时通知宿主折叠右侧栏
    /// </summary>
    public event Action? CollapseRequested;

    private static readonly Color Bg = Color.FromArgb(32, 32, 36);
    private static readonly Color SourceColor = Color.FromArgb(78, 201, 176);
    private static readonly Color TransColor = Color.FromArgb(230, 230, 230);

    public ResultSidePanel(ResultMessenger messenger)
    {
        _messenger = messenger;
        Dock = DockStyle.Fill;
        BackColor = Bg;
        MinimumSize = new Size(260, 100);

        _title = new Label
        {
            Dock = DockStyle.Top,
            Height = 32,
            Text = "提取结果",
            TextAlign = ContentAlignment.MiddleLeft,
            Padding = new Padding(10, 0, 0, 0),
            ForeColor = Color.White,
            BackColor = Color.FromArgb(45, 45, 48),
            Font = new Font("Microsoft YaHei UI", 9.5f, FontStyle.Bold)
        };

        _status = new Label
        {
            Dock = DockStyle.Bottom,
            Height = 26,
            TextAlign = ContentAlignment.MiddleLeft,
            Padding = new Padding(10, 0, 0, 0),
            ForeColor = Color.FromArgb(180, 180, 180),
            BackColor = Color.FromArgb(45, 45, 48),
            Text = "可选中文本后 Ctrl+C / 右键复制"
        };

        _view = new RichTextBox
        {
            Dock = DockStyle.Fill,
            ReadOnly = true,
            BorderStyle = BorderStyle.None,
            BackColor = Bg,
            ForeColor = TransColor,
            Font = CreateMonoFont(10.5f),
            WordWrap = true,
            DetectUrls = false,
            ScrollBars = RichTextBoxScrollBars.Vertical,
            // 允许自由划选；失焦时仍保留选区高亮
            HideSelection = false,
            ShortcutsEnabled = true,
            Cursor = Cursors.IBeam
        };

        // 右键菜单：复制选中 / 全选 / 复制全部
        var menu = new ContextMenuStrip();
        var miCopy = new ToolStripMenuItem("复制选中(&C)", null, (_, _) => CopySelectionOrAll(preferSelection: true))
        {
            ShortcutKeys = Keys.Control | Keys.C,
            ShowShortcutKeys = true
        };
        var miSelectAll = new ToolStripMenuItem("全选(&A)", null, (_, _) =>
        {
            _view.Focus();
            _view.SelectAll();
        })
        {
            ShortcutKeys = Keys.Control | Keys.A
        };
        var miCopyAll = new ToolStripMenuItem("复制全部", null, (_, _) => CopySelectionOrAll(preferSelection: false));
        menu.Items.AddRange(new ToolStripItem[] { miCopy, miSelectAll, new ToolStripSeparator(), miCopyAll });
        menu.Opening += (_, _) =>
        {
            miCopy.Enabled = _view.SelectionLength > 0;
        };
        _view.ContextMenuStrip = menu;

        // 显式处理 Ctrl+C / Ctrl+A，避免被父窗体抢走
        _view.KeyDown += View_KeyDown;

        var actions = new FlowLayoutPanel
        {
            Dock = DockStyle.Top,
            Height = 36,
            Padding = new Padding(6, 4, 6, 2),
            BackColor = Color.FromArgb(45, 45, 48),
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false
        };

        _btnCopy = MakeButton("复制选中");
        _btnCopy.Click += (_, _) => CopySelectionOrAll(preferSelection: true);

        _btnCopyAll = MakeButton("复制全部");
        _btnCopyAll.Click += (_, _) => CopySelectionOrAll(preferSelection: false);

        _btnExport = MakeButton("导出");
        _btnExport.Click += (_, _) => ExportText();

        _btnClose = MakeButton("收起");
        _btnClose.Click += (_, _) => CollapseRequested?.Invoke();

        actions.Controls.AddRange(new Control[] { _btnCopy, _btnCopyAll, _btnExport, _btnClose });

        Controls.Add(_view);
        Controls.Add(_status);
        Controls.Add(actions);
        Controls.Add(_title);

        _messenger.StatusChanged += OnStatus;
        _messenger.BusyChanged += OnBusy;
        _messenger.ResultReceived += OnResult;
    }

    /// <summary>
    /// 结果文本框是否拥有焦点（供编辑器判断是否放行 Ctrl+C）
    /// </summary>
    public bool HasTextFocus => _view.Focused || ContainsFocus && ActiveControl == _view;

    private void View_KeyDown(object? sender, KeyEventArgs e)
    {
        if (e.Control && e.KeyCode == Keys.C)
        {
            CopySelectionOrAll(preferSelection: true);
            e.Handled = true;
            e.SuppressKeyPress = true;
        }
        else if (e.Control && e.KeyCode == Keys.A)
        {
            _view.SelectAll();
            e.Handled = true;
            e.SuppressKeyPress = true;
        }
    }

    /// <summary>
    /// 优先复制当前选中文本；无选中时按需复制全部
    /// </summary>
    private void CopySelectionOrAll(bool preferSelection)
    {
        string text;
        if (preferSelection && _view.SelectionLength > 0)
        {
            text = _view.SelectedText;
            _status.Text = $"已复制选中（{text.Length} 字）";
        }
        else
        {
            text = string.IsNullOrWhiteSpace(_exportText) ? _view.Text : _exportText;
            if (string.IsNullOrWhiteSpace(text))
            {
                _status.Text = "没有可复制的内容";
                return;
            }
            if (preferSelection && _view.SelectionLength == 0)
            {
                _status.Text = "请先用鼠标选中要复制的文本";
                return;
            }
            _status.Text = "已复制全部文本";
        }

        try
        {
            Clipboard.SetText(text);
        }
        catch (Exception ex)
        {
            _status.Text = "复制失败：" + ex.Message;
        }
    }

    private static Button MakeButton(string text) => new()
    {
        Text = text,
        AutoSize = true,
        FlatStyle = FlatStyle.Flat,
        ForeColor = Color.White,
        BackColor = Color.FromArgb(62, 62, 66),
        Margin = new Padding(3, 0, 3, 0),
        Padding = new Padding(8, 2, 8, 2),
        Cursor = Cursors.Hand
    };

    private static Font CreateMonoFont(float size)
    {
        foreach (var name in new[] { "Cascadia Mono", "Consolas", "Courier New" })
        {
            try
            {
                var font = new Font(name, size, FontStyle.Regular, GraphicsUnit.Point);
                if (string.Equals(font.Name, name, StringComparison.OrdinalIgnoreCase))
                    return font;
                font.Dispose();
            }
            catch { /* 尝试下一种 */ }
        }
        return new Font(FontFamily.GenericMonospace, size);
    }

    private void OnStatus(string status)
    {
        if (IsDisposed) return;
        if (InvokeRequired) { BeginInvoke(() => OnStatus(status)); return; }
        _status.Text = status;
    }

    private void OnBusy(bool busy)
    {
        if (IsDisposed) return;
        if (InvokeRequired) { BeginInvoke(() => OnBusy(busy)); return; }
        _btnCopy.Enabled = !busy;
        _btnCopyAll.Enabled = !busy;
        _btnExport.Enabled = !busy;
        UseWaitCursor = busy;
    }

    private void OnResult(ResultMessage msg)
    {
        if (IsDisposed) return;
        if (InvokeRequired) { BeginInvoke(() => OnResult(msg)); return; }

        Visible = true;
        _title.Text = msg.Kind switch
        {
            ResultKind.ContrastTranslate => "对照翻译",
            ResultKind.Ocr => "提取文字",
            ResultKind.Error => "错误",
            _ => "提取结果"
        };

        _view.Clear();
        if (msg.Kind == ResultKind.Clear)
        {
            _exportText = string.Empty;
            return;
        }

        foreach (var line in msg.Lines)
            AppendLine(line.Text, line.Color);

        // 渲染结束后取消选区，便于用户重新划选
        _view.SelectionStart = 0;
        _view.SelectionLength = 0;
        _view.SelectionColor = TransColor;

        _exportText = msg.PlainText;
        if (!string.IsNullOrEmpty(msg.Status))
            _status.Text = msg.Status + "　·　可划选后 Ctrl+C 复制";
    }

    private void AppendLine(string text, Color color)
    {
        _view.SelectionStart = _view.TextLength;
        _view.SelectionLength = 0;
        _view.SelectionColor = color;
        _view.AppendText(text + Environment.NewLine);
    }

    private void ExportText()
    {
        // 若有选中，优先导出选中内容
        var text = _view.SelectionLength > 0
            ? _view.SelectedText
            : (string.IsNullOrWhiteSpace(_exportText) ? _view.Text : _exportText);
        if (string.IsNullOrWhiteSpace(text)) return;

        using var dlg = new SaveFileDialog
        {
            Filter = "文本文件|*.txt",
            FileName = $"结果_{DateTime.Now:yyyyMMdd_HHmmss}.txt"
        };
        if (dlg.ShowDialog(FindForm()) != DialogResult.OK) return;
        File.WriteAllText(dlg.FileName, text);
        _status.Text = "已导出";
    }

    public static Color ColorSource => SourceColor;
    public static Color ColorTranslation => TransColor;
    public static Color ColorWarn => Color.Orange;

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _messenger.StatusChanged -= OnStatus;
            _messenger.BusyChanged -= OnBusy;
            _messenger.ResultReceived -= OnResult;
        }
        base.Dispose(disposing);
    }
}
