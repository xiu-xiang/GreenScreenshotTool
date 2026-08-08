using ScreenshotTool.App;
using ScreenshotTool.Controls;
using ScreenshotTool.Models;
using ScreenshotTool.Services;

namespace ScreenshotTool.Forms;

/// <summary>
/// 截图编辑器：左侧画布标注，右侧内嵌显示 OCR/翻译结果（通信回传）
/// </summary>
public sealed class EditorForm : Form
{
    private readonly Bitmap _baseImage;
    private readonly List<AnnotationItem> _items = new();
    private readonly Stack<AnnotationItem> _redo = new();
    private DrawToolType _tool = DrawToolType.Rectangle;
    private Color _drawColor = Color.Red;
    private int _thickness = 3;
    private bool _drawing;
    private Point _start;
    private Point _current;
    private AnnotationItem? _preview;

    private readonly PictureBox _canvas;
    private readonly ToolStrip _toolbar;
    private readonly Panel _canvasHost;
    private readonly SplitContainer _split;
    private readonly ResultSidePanel _resultPanel;
    private readonly ResultMessenger _messenger = new();
    private readonly OcrTranslateWorker _worker;
    private readonly StatusStrip _statusStrip;
    private readonly ToolStripStatusLabel _statusLabel;
    private bool _busy;

    public EditorForm(Bitmap image)
    {
        _baseImage = image;
        _worker = new OcrTranslateWorker(_messenger);

        Text = "截图编辑";
        Icon = AppIcon.Get();
        StartPosition = FormStartPosition.CenterScreen;
        KeyPreview = true;
        MinimumSize = new Size(800, 520);
        // 预留右侧结果栏宽度
        Width = Math.Min(Screen.PrimaryScreen!.WorkingArea.Width - 40, Math.Max(960, image.Width + 420));
        Height = Math.Min(Screen.PrimaryScreen.WorkingArea.Height - 40, Math.Max(560, image.Height + 160));
        BackColor = Color.FromArgb(45, 45, 48);

        _toolbar = BuildToolbar();

        _statusStrip = new StatusStrip { BackColor = Color.FromArgb(37, 37, 38), ForeColor = Color.White };
        _statusLabel = new ToolStripStatusLabel("就绪") { Spring = true, TextAlign = ContentAlignment.MiddleLeft };
        _statusStrip.Items.Add(_statusLabel);

        // 修复：构造时控件宽度尚未就绪，不能设置过大的 PanelMinSize（会触发 SplitterDistance 异常）
        _split = new SplitContainer
        {
            Dock = DockStyle.Fill,
            Orientation = Orientation.Vertical,
            BackColor = Color.FromArgb(30, 30, 30),
            SplitterWidth = 6,
            Panel2Collapsed = true
        };

        _canvasHost = new Panel
        {
            Dock = DockStyle.Fill,
            AutoScroll = true,
            BackColor = Color.FromArgb(30, 30, 30)
        };

        _canvas = new PictureBox
        {
            SizeMode = PictureBoxSizeMode.AutoSize,
            BackColor = Color.Transparent,
            Cursor = Cursors.Cross
        };
        _canvas.MouseDown += Canvas_MouseDown;
        _canvas.MouseMove += Canvas_MouseMove;
        _canvas.MouseUp += Canvas_MouseUp;
        _canvas.Paint += Canvas_Paint;
        _canvasHost.Controls.Add(_canvas);

        // 右侧结果侧栏：订阅通信通道，直接显示返回结果
        _resultPanel = new ResultSidePanel(_messenger);
        _resultPanel.CollapseRequested += () => _split.Panel2Collapsed = true;
        _messenger.StatusChanged += s =>
        {
            if (IsDisposed) return;
            if (InvokeRequired) { BeginInvoke(() => _statusLabel.Text = s); return; }
            _statusLabel.Text = s;
        };
        _messenger.BusyChanged += busy =>
        {
            if (IsDisposed) return;
            if (InvokeRequired) { BeginInvoke(() => SetBusy(busy)); return; }
            SetBusy(busy);
        };
        _messenger.ResultReceived += _ =>
        {
            if (IsDisposed) return;
            void ShowPanel()
            {
                EnsureResultPanelVisible();
            }
            if (InvokeRequired) BeginInvoke(ShowPanel);
            else ShowPanel();
        };

        _split.Panel1.Controls.Add(_canvasHost);
        _split.Panel2.Controls.Add(_resultPanel);

        Controls.Add(_split);
        Controls.Add(_statusStrip);
        Controls.Add(_toolbar);

        // 窗体显示且完成布局后，再设置分栏最小尺寸与初始折叠
        Shown += (_, _) =>
        {
            ApplySplitSafeLayout(collapsePanel2: true);
        };

        RenderCanvasImage();
        UpdateToolChecked();
    }

    /// <summary>
    /// 安全设置 SplitContainer：仅在宽度足够时调整 MinSize / SplitterDistance
    /// </summary>
    private void ApplySplitSafeLayout(bool collapsePanel2)
    {
        if (_split.IsDisposed) return;

        // 先折叠可避免未布局时校验失败
        if (collapsePanel2)
            _split.Panel2Collapsed = true;

        var width = _split.Width;
        if (width < 100)
            return;

        // 保证 Panel1Min + Panel2Min + Splitter < Width
        var panel1Min = Math.Min(200, Math.Max(80, width / 5));
        var panel2Min = Math.Min(220, Math.Max(80, width / 5));
        if (panel1Min + panel2Min + _split.SplitterWidth >= width)
        {
            panel1Min = 60;
            panel2Min = 60;
        }

        try
        {
            _split.Panel1MinSize = panel1Min;
            _split.Panel2MinSize = panel2Min;
        }
        catch (InvalidOperationException)
        {
            // 尺寸临界时忽略，保持默认
        }

        if (collapsePanel2)
            return;

        // 展开时把右侧大约留 340px
        var distance = width - 340;
        var min = _split.Panel1MinSize;
        var max = width - _split.Panel2MinSize - _split.SplitterWidth;
        if (max <= min) return;
        distance = Math.Clamp(distance, min, max);
        try
        {
            _split.SplitterDistance = distance;
        }
        catch (InvalidOperationException)
        {
            // 布局过程中偶发失败，忽略
        }
    }

    private ToolStrip BuildToolbar()
    {
        var bar = new ToolStrip
        {
            GripStyle = ToolStripGripStyle.Hidden,
            ImageScalingSize = new Size(20, 20),
            Padding = new Padding(6, 4, 6, 4),
            BackColor = Color.FromArgb(37, 37, 38),
            ForeColor = Color.White
        };

        bar.Items.Add(MakeToolButton("矩形", DrawToolType.Rectangle));
        bar.Items.Add(MakeToolButton("椭圆", DrawToolType.Ellipse));
        bar.Items.Add(MakeToolButton("箭头", DrawToolType.Arrow));
        bar.Items.Add(MakeToolButton("画笔", DrawToolType.Pen));
        bar.Items.Add(MakeToolButton("文字", DrawToolType.Text));
        bar.Items.Add(MakeToolButton("马赛克", DrawToolType.Mosaic));
        bar.Items.Add(new ToolStripSeparator());

        var colorBtn = new ToolStripButton("颜色") { DisplayStyle = ToolStripItemDisplayStyle.Text };
        colorBtn.Click += (_, _) =>
        {
            using var dlg = new ColorDialog { Color = _drawColor, FullOpen = true };
            if (dlg.ShowDialog(this) == DialogResult.OK)
                _drawColor = dlg.Color;
        };
        bar.Items.Add(colorBtn);

        var thick = new ToolStripComboBox("粗细") { DropDownStyle = ComboBoxStyle.DropDownList, Width = 60 };
        thick.Items.AddRange(new object[] { "1", "2", "3", "5", "8" });
        thick.SelectedIndex = 2;
        thick.SelectedIndexChanged += (_, _) =>
        {
            if (int.TryParse(thick.Text, out var t)) _thickness = t;
        };
        bar.Items.Add(new ToolStripLabel("线宽"));
        bar.Items.Add(thick);
        bar.Items.Add(new ToolStripSeparator());

        var undo = new ToolStripButton("撤销");
        undo.Click += (_, _) => Undo();
        bar.Items.Add(undo);

        var redo = new ToolStripButton("重做");
        redo.Click += (_, _) => Redo();
        bar.Items.Add(redo);
        bar.Items.Add(new ToolStripSeparator());

        var copy = new ToolStripButton("复制图片");
        copy.Click += (_, _) => CopyToClipboard();
        bar.Items.Add(copy);

        var save = new ToolStripButton("保存");
        save.Click += (_, _) => SaveImage();
        bar.Items.Add(save);
        bar.Items.Add(new ToolStripSeparator());

        var ocr = new ToolStripButton("提取文字");
        ocr.Click += async (_, _) => await RunOcrTranslateAsync(translate: false);
        bar.Items.Add(ocr);

        var tr = new ToolStripButton("对照翻译");
        tr.Click += async (_, _) => await RunOcrTranslateAsync(translate: true);
        bar.Items.Add(tr);

        var toggle = new ToolStripButton("结果栏");
        toggle.Click += (_, _) =>
        {
            if (_split.Panel2Collapsed)
                EnsureResultPanelVisible();
            else
                _split.Panel2Collapsed = true;
        };
        bar.Items.Add(toggle);

        return bar;
    }

    /// <summary>
    /// 展开右侧结果栏（类似图示左右分栏）
    /// </summary>
    private void EnsureResultPanelVisible()
    {
        _resultPanel.Visible = true;
        if (_split.Panel2Collapsed)
        {
            // 先按安全规则设置尺寸，再展开
            ApplySplitSafeLayout(collapsePanel2: false);
            _split.Panel2Collapsed = false;
            ApplySplitSafeLayout(collapsePanel2: false);
        }
    }

    /// <summary>
    /// 在当前窗口内启动识别/翻译，结果经 Messenger 回传到侧栏
    /// </summary>
    private async Task RunOcrTranslateAsync(bool translate)
    {
        if (_busy) return;
        EnsureResultPanelVisible();
        using var bmp = Compose();
        await _worker.RunAsync(bmp, translate).ConfigureAwait(true);
    }

    private void SetBusy(bool busy)
    {
        _busy = busy;
        UseWaitCursor = busy;
        foreach (ToolStripItem item in _toolbar.Items)
        {
            if (item.Text is "提取文字" or "对照翻译")
                item.Enabled = !busy;
        }
    }

    private ToolStripButton MakeToolButton(string text, DrawToolType tool)
    {
        var btn = new ToolStripButton(text)
        {
            CheckOnClick = true,
            Tag = tool,
            DisplayStyle = ToolStripItemDisplayStyle.Text
        };
        btn.Click += (_, _) =>
        {
            _tool = tool;
            UpdateToolChecked();
            _canvas.Cursor = tool == DrawToolType.Text ? Cursors.IBeam : Cursors.Cross;
        };
        return btn;
    }

    private void UpdateToolChecked()
    {
        foreach (ToolStripItem item in _toolbar.Items)
        {
            if (item is ToolStripButton btn && btn.Tag is DrawToolType t)
                btn.Checked = t == _tool;
        }
    }

    private void RenderCanvasImage()
    {
        _canvas.Image?.Dispose();
        _canvas.Image = (Bitmap)_baseImage.Clone();
    }

    private void Canvas_Paint(object? sender, PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        foreach (var item in _items)
            DrawAnnotation(g, item);
        if (_preview != null)
            DrawAnnotation(g, _preview);
    }

    private void Canvas_MouseDown(object? sender, MouseEventArgs e)
    {
        if (e.Button != MouseButtons.Left) return;

        if (_tool == DrawToolType.Text)
        {
            AddTextAnnotation(e.Location);
            return;
        }

        _drawing = true;
        _start = e.Location;
        _current = e.Location;
        _preview = new AnnotationItem
        {
            Tool = _tool,
            Start = _start,
            End = _current,
            Color = _drawColor,
            Thickness = _thickness
        };
        if (_tool == DrawToolType.Pen)
            _preview.PenPoints.Add(_start);
    }

    private void Canvas_MouseMove(object? sender, MouseEventArgs e)
    {
        if (!_drawing || _preview == null) return;
        _current = e.Location;
        _preview.End = _current;
        if (_tool == DrawToolType.Pen)
            _preview.PenPoints.Add(_current);
        _canvas.Invalidate();
    }

    private void Canvas_MouseUp(object? sender, MouseEventArgs e)
    {
        if (!_drawing || _preview == null) return;
        _drawing = false;
        _preview.End = e.Location;

        var tooSmall = _preview.Tool != DrawToolType.Pen
                       && Math.Abs(_preview.End.X - _preview.Start.X) < 3
                       && Math.Abs(_preview.End.Y - _preview.Start.Y) < 3;
        if (!tooSmall && (_preview.Tool != DrawToolType.Pen || _preview.PenPoints.Count > 1))
        {
            _items.Add(_preview);
            _redo.Clear();
        }
        _preview = null;
        _canvas.Invalidate();
    }

    private void AddTextAnnotation(Point location)
    {
        using var dlg = new TextInputDialog();
        if (dlg.ShowDialog(this) != DialogResult.OK || string.IsNullOrWhiteSpace(dlg.InputText))
            return;

        _items.Add(new AnnotationItem
        {
            Tool = DrawToolType.Text,
            Start = location,
            End = location,
            Color = _drawColor,
            Text = dlg.InputText,
            Font = new Font("Microsoft YaHei UI", 14, FontStyle.Bold)
        });
        _redo.Clear();
        _canvas.Invalidate();
    }

    private static void DrawAnnotation(Graphics g, AnnotationItem item)
    {
        using var pen = new Pen(item.Color, item.Thickness)
        {
            EndCap = System.Drawing.Drawing2D.LineCap.Round,
            StartCap = System.Drawing.Drawing2D.LineCap.Round
        };

        switch (item.Tool)
        {
            case DrawToolType.Rectangle:
            {
                var r = Normalize(item.Start, item.End);
                g.DrawRectangle(pen, r);
                break;
            }
            case DrawToolType.Ellipse:
            {
                var r = Normalize(item.Start, item.End);
                g.DrawEllipse(pen, r);
                break;
            }
            case DrawToolType.Arrow:
                DrawArrow(g, pen, item.Start, item.End);
                break;
            case DrawToolType.Pen:
                if (item.PenPoints.Count > 1)
                    g.DrawLines(pen, item.PenPoints.ToArray());
                break;
            case DrawToolType.Text:
                if (!string.IsNullOrEmpty(item.Text))
                {
                    using var brush = new SolidBrush(item.Color);
                    g.DrawString(item.Text, item.Font ?? SystemFonts.DefaultFont, brush, item.Start);
                }
                break;
            case DrawToolType.Mosaic:
            {
                var r = Normalize(item.Start, item.End);
                const int block = 8;
                for (int y = r.Top; y < r.Bottom; y += block)
                for (int x = r.Left; x < r.Right; x += block)
                {
                    var tone = ((x / block + y / block) % 2 == 0)
                        ? Color.FromArgb(180, 100, 100, 100)
                        : Color.FromArgb(180, 60, 60, 60);
                    using var b = new SolidBrush(tone);
                    g.FillRectangle(b, x, y, Math.Min(block, r.Right - x), Math.Min(block, r.Bottom - y));
                }
                break;
            }
        }
    }

    private static void DrawArrow(Graphics g, Pen pen, Point start, Point end)
    {
        g.DrawLine(pen, start, end);
        var angle = Math.Atan2(end.Y - start.Y, end.X - start.X);
        const double arrowLen = 14;
        const double arrowAngle = Math.PI / 7;
        var p1 = new Point(
            (int)(end.X - arrowLen * Math.Cos(angle - arrowAngle)),
            (int)(end.Y - arrowLen * Math.Sin(angle - arrowAngle)));
        var p2 = new Point(
            (int)(end.X - arrowLen * Math.Cos(angle + arrowAngle)),
            (int)(end.Y - arrowLen * Math.Sin(angle + arrowAngle)));
        using var brush = new SolidBrush(pen.Color);
        g.FillPolygon(brush, new[] { end, p1, p2 });
    }

    private static Rectangle Normalize(Point a, Point b) =>
        new(Math.Min(a.X, b.X), Math.Min(a.Y, b.Y), Math.Abs(a.X - b.X), Math.Abs(a.Y - b.Y));

    private void Undo()
    {
        if (_items.Count == 0) return;
        var last = _items[^1];
        _items.RemoveAt(_items.Count - 1);
        _redo.Push(last);
        _canvas.Invalidate();
    }

    private void Redo()
    {
        if (_redo.Count == 0) return;
        _items.Add(_redo.Pop());
        _canvas.Invalidate();
    }

    private Bitmap Compose()
    {
        var bmp = (Bitmap)_baseImage.Clone();
        using var g = Graphics.FromImage(bmp);
        g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        foreach (var item in _items)
            DrawAnnotation(g, item);
        return bmp;
    }

    private void CopyToClipboard()
    {
        using var bmp = Compose();
        Clipboard.SetImage(bmp);
        _statusLabel.Text = "图片已复制到剪贴板";
    }

    private void SaveImage()
    {
        using var dlg = new SaveFileDialog
        {
            Title = "保存截图",
            Filter = "PNG 图片|*.png|JPEG 图片|*.jpg|BMP 图片|*.bmp",
            FileName = $"截图_{DateTime.Now:yyyyMMdd_HHmmss}.png"
        };
        if (dlg.ShowDialog(this) != DialogResult.OK) return;

        using var bmp = Compose();
        var ext = Path.GetExtension(dlg.FileName).ToLowerInvariant();
        var format = ext switch
        {
            ".jpg" or ".jpeg" => System.Drawing.Imaging.ImageFormat.Jpeg,
            ".bmp" => System.Drawing.Imaging.ImageFormat.Bmp,
            _ => System.Drawing.Imaging.ImageFormat.Png
        };
        bmp.Save(dlg.FileName, format);
        _statusLabel.Text = "已保存：" + dlg.FileName;
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        // 结果侧栏拥有焦点时，放行 Ctrl+C/A，供自由选中复制
        if (_resultPanel.ContainsFocus && e.Control && e.KeyCode is Keys.C or Keys.A)
        {
            base.OnKeyDown(e);
            return;
        }

        if (e.Control && e.KeyCode == Keys.Z) { Undo(); e.Handled = true; }
        if (e.Control && e.KeyCode == Keys.Y) { Redo(); e.Handled = true; }
        if (e.Control && e.KeyCode == Keys.S) { SaveImage(); e.Handled = true; }
        if (e.Control && e.KeyCode == Keys.C) { CopyToClipboard(); e.Handled = true; }
        if (e.KeyCode == Keys.Escape) Close();
        base.OnKeyDown(e);
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        _worker.Cancel();
        _baseImage.Dispose();
        _canvas.Image?.Dispose();
        base.OnFormClosed(e);
    }
}

/// <summary>
/// 简单文字输入框
/// </summary>
internal sealed class TextInputDialog : Form
{
    private readonly TextBox _box;
    public string InputText => _box.Text;

    public TextInputDialog()
    {
        Text = "输入文字";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterParent;
        MinimizeBox = false;
        MaximizeBox = false;
        ClientSize = new Size(360, 120);

        _box = new TextBox { Left = 12, Top = 16, Width = 336 };
        var ok = new Button { Text = "确定", DialogResult = DialogResult.OK, Left = 180, Top = 60, Width = 80 };
        var cancel = new Button { Text = "取消", DialogResult = DialogResult.Cancel, Left = 268, Top = 60, Width = 80 };
        AcceptButton = ok;
        CancelButton = cancel;
        Controls.AddRange(new Control[] { _box, ok, cancel });
    }
}
