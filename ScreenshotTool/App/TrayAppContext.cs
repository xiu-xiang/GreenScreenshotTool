using ScreenshotTool.Forms;
using ScreenshotTool.Native;
using ScreenshotTool.Services;

namespace ScreenshotTool.App;

/// <summary>
/// 托盘常驻应用上下文
/// </summary>
public sealed class TrayAppContext : ApplicationContext
{
    private readonly NotifyIcon _tray;
    private readonly HiddenForm _hidden;
    private readonly HotkeyManager _hotkeys;
    private readonly AppSettings _settings;
    private readonly ToolStripMenuItem _captureItem;
    private bool _capturing;

    public TrayAppContext()
    {
        _settings = AppSettings.Load();

        _hidden = new HiddenForm();
        _hidden.HotkeyPressed += (_, _) => BeginCapture();
        _hidden.ShowInTaskbar = false;
        _hidden.WindowState = FormWindowState.Minimized;
        _hidden.Opacity = 0;
        _hidden.Show();
        _hidden.Hide();

        _hotkeys = new HotkeyManager(_hidden.Handle);

        _tray = new NotifyIcon
        {
            Text = $"截图工具 ({_settings.HotkeyDisplay})",
            Visible = true,
            // 使用自定义应用图标
            Icon = AppIcon.GetTrayIcon()
        };

        var menu = new ContextMenuStrip();
        _captureItem = new ToolStripMenuItem($"开始截图 ({_settings.HotkeyDisplay})", null, (_, _) => BeginCapture());
        menu.Items.Add(_captureItem);
        menu.Items.Add("设置...", null, (_, _) => OpenSettings());
        menu.Items.Add("关于", null, (_, _) => ShowAbout());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("退出", null, (_, _) => ExitThread());
        _tray.ContextMenuStrip = menu;
        _tray.DoubleClick += (_, _) => BeginCapture();

        // 托盘菜单创建完毕后再注册热键并刷新文案
        ApplyHotkey(showWarning: true);

        _tray.BalloonTipTitle = "截图工具已启动";
        _tray.BalloonTipText = $"按 {_settings.HotkeyDisplay} 开始截图，或双击托盘图标。";
        _tray.ShowBalloonTip(2500);
    }

    /// <summary>
    /// 按当前设置注册全局热键，并刷新托盘文案
    /// </summary>
    private bool ApplyHotkey(bool showWarning)
    {
        var ok = _hotkeys.Register(_settings.HotkeyModifiers, _settings.Key);
        var display = _settings.HotkeyDisplay;
        _tray.Text = $"截图工具 ({display})";
        _captureItem.Text = $"开始截图 ({display})";

        if (!ok && showWarning)
        {
            MessageBox.Show(
                $"热键 {display} 注册失败，可能被占用。\n请在「设置」中更换，或通过托盘菜单截图。",
                "截图工具", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        return ok;
    }

    private void OpenSettings()
    {
        using var dlg = new SettingsForm(_settings);
        if (dlg.ShowDialog() != DialogResult.OK) return;

        if (!ApplyHotkey(showWarning: true))
            return;

        _tray.BalloonTipTitle = "快捷键已更新";
        _tray.BalloonTipText = $"当前截图热键：{_settings.HotkeyDisplay}";
        _tray.ShowBalloonTip(2000);
    }

    private void BeginCapture()
    {
        if (_capturing) return;
        _capturing = true;
        try
        {
            using var overlay = new SelectionForm();
            if (overlay.ShowDialog() == DialogResult.OK && overlay.CapturedImage != null)
            {
                var editor = new EditorForm(overlay.CapturedImage);
                editor.Show();
            }
        }
        finally
        {
            _capturing = false;
        }
    }

    private void ShowAbout()
    {
        MessageBox.Show(
            "便携截图工具 v1.0\n\n" +
            "功能：框选截图、矩形/箭头/画笔/文字标注、保存、OCR 识字、中英对照翻译\n" +
            "OCR：开源 PaddleOCR（中英模型随程序嵌入 inference/）\n" +
            "翻译：优先本地 LibreTranslate，其次开源聚合客户端\n" +
            $"当前热键：{_settings.HotkeyDisplay}\n" +
            "可在托盘菜单「设置」中修改快捷键。",
            "关于", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    protected override void ExitThreadCore()
    {
        _hotkeys.Dispose();
        _tray.Visible = false;
        _tray.Dispose();
        _hidden.Dispose();
        base.ExitThreadCore();
    }
}

/// <summary>
/// 隐藏窗体：接收热键消息
/// </summary>
internal sealed class HiddenForm : Form
{
    private const int WM_HOTKEY = 0x0312;
    public event EventHandler? HotkeyPressed;

    public HiddenForm()
    {
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        Size = new Size(0, 0);
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == WM_HOTKEY && m.WParam.ToInt32() == HotkeyManager.HotkeyId)
            HotkeyPressed?.Invoke(this, EventArgs.Empty);
        base.WndProc(ref m);
    }
}
