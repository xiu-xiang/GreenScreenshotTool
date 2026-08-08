using ScreenshotTool.Services;

namespace ScreenshotTool.Forms;

/// <summary>
/// 全屏遮罩框选截图（类似微信：拖拽自由确定区域）
/// </summary>
public sealed class SelectionForm : Form
{
    private readonly Bitmap _screen;
    private readonly Rectangle _virtualBounds;
    private Point _start;
    private Point _current;
    private bool _dragging;
    private Rectangle _selection;

    public Bitmap? CapturedImage { get; private set; }

    public SelectionForm()
    {
        _virtualBounds = SystemInformation.VirtualScreen;
        _screen = ScreenCaptureService.CaptureVirtualScreen();

        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.Manual;
        Bounds = _virtualBounds;
        TopMost = true;
        DoubleBuffered = true;
        Cursor = Cursors.Cross;
        KeyPreview = true;
        ShowInTaskbar = false;
        BackColor = Color.Black;
        // 使用背景图绘制，避免闪烁
        BackgroundImage = _screen;
        BackgroundImageLayout = ImageLayout.None;
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (e.KeyCode == Keys.Escape)
        {
            DialogResult = DialogResult.Cancel;
            Close();
        }
        base.OnKeyDown(e);
    }

    protected override void OnMouseDown(MouseEventArgs e)
    {
        if (e.Button == MouseButtons.Left)
        {
            _dragging = true;
            _start = e.Location;
            _current = e.Location;
            _selection = Rectangle.Empty;
        }
        else if (e.Button == MouseButtons.Right)
        {
            DialogResult = DialogResult.Cancel;
            Close();
        }
        base.OnMouseDown(e);
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        if (_dragging)
        {
            _current = e.Location;
            _selection = NormalizeRect(_start, _current);
            Invalidate();
        }
        base.OnMouseMove(e);
    }

    protected override void OnMouseUp(MouseEventArgs e)
    {
        if (e.Button == MouseButtons.Left && _dragging)
        {
            _dragging = false;
            _selection = NormalizeRect(_start, e.Location);
            if (_selection.Width >= 5 && _selection.Height >= 5)
            {
                CapturedImage = ScreenCaptureService.Crop(_screen, _selection);
                DialogResult = DialogResult.OK;
                Close();
            }
            else
            {
                _selection = Rectangle.Empty;
                Invalidate();
            }
        }
        base.OnMouseUp(e);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        // 半透明遮罩
        using (var dim = new SolidBrush(Color.FromArgb(120, 0, 0, 0)))
            g.FillRectangle(dim, ClientRectangle);

        if (_selection.Width > 0 && _selection.Height > 0)
        {
            // 选区高亮：重新绘制原图区域
            g.SetClip(_selection);
            g.DrawImage(_screen, ClientRectangle);
            g.ResetClip();

            using var pen = new Pen(Color.FromArgb(0, 174, 255), 2);
            g.DrawRectangle(pen, _selection.X, _selection.Y, _selection.Width - 1, _selection.Height - 1);

            // 尺寸提示
            var tip = $"{_selection.Width} x {_selection.Height}";
            var tipSize = g.MeasureString(tip, Font);
            var tipRect = new RectangleF(
                _selection.X,
                Math.Max(0, _selection.Y - tipSize.Height - 6),
                tipSize.Width + 10,
                tipSize.Height + 4);
            using (var tipBg = new SolidBrush(Color.FromArgb(200, 0, 0, 0)))
                g.FillRectangle(tipBg, tipRect);
            g.DrawString(tip, Font, Brushes.White, tipRect.X + 5, tipRect.Y + 2);
        }

        // 底部提示
        const string help = "拖拽选择区域 | Esc/右键 取消 | 松手完成截图";
        var hs = g.MeasureString(help, Font);
        g.DrawString(help, Font, Brushes.White,
            (ClientSize.Width - hs.Width) / 2,
            ClientSize.Height - 40);
    }

    private static Rectangle NormalizeRect(Point a, Point b)
    {
        return new Rectangle(
            Math.Min(a.X, b.X),
            Math.Min(a.Y, b.Y),
            Math.Abs(a.X - b.X),
            Math.Abs(a.Y - b.Y));
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            BackgroundImage = null;
            _screen.Dispose();
            // CapturedImage 交由编辑器接管，此处不释放
        }
        base.Dispose(disposing);
    }
}
