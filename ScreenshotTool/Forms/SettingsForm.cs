using ScreenshotTool.App;
using ScreenshotTool.Native;
using ScreenshotTool.Services;

namespace ScreenshotTool.Forms;

/// <summary>
/// 设置窗体：快捷键 + 本地翻译主机/端口（端口可调）
/// </summary>
public sealed class SettingsForm : Form
{
    private readonly AppSettings _settings;
    private readonly TextBox _hotkeyBox;
    private readonly TextBox _hostBox;
    private readonly NumericUpDown _portBox;
    private readonly Label _urlPreview;
    private readonly CheckBox _chkLocal;
    private readonly CheckBox _chkFallback;
    private readonly Label _hint;
    private readonly Label _probeLabel;
    private uint _modifiers;
    private Keys _key;

    public SettingsForm(AppSettings settings)
    {
        _settings = settings;
        settings.NormalizeHostPort();
        _modifiers = settings.HotkeyModifiers;
        _key = settings.Key;

        Text = "设置";
        Icon = AppIcon.Get();
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterScreen;
        MinimizeBox = false;
        MaximizeBox = false;
        ClientSize = new Size(480, 400);
        BackColor = Color.FromArgb(45, 45, 48);
        ForeColor = Color.White;
        Font = new Font("Microsoft YaHei UI", 9f);

        var lblHotkey = new Label
        {
            Text = "截图快捷键（点击输入框后按下组合键）",
            Left = 20, Top = 18, Width = 440, ForeColor = Color.White
        };

        _hint = new Label
        {
            Left = 20, Top = 78, Width = 440, Height = 22,
            ForeColor = Color.FromArgb(180, 180, 180),
            Text = "至少包含 Ctrl / Alt / Shift 之一"
        };

        _hotkeyBox = new TextBox
        {
            Left = 20, Top = 44, Width = 340, Height = 28,
            ReadOnly = true,
            BackColor = Color.FromArgb(62, 62, 66),
            ForeColor = Color.White,
            Text = AppSettings.FormatHotkey(_modifiers, _key),
            Cursor = Cursors.Hand
        };
        _hotkeyBox.KeyDown += HotkeyBox_KeyDown;
        _hotkeyBox.KeyPress += (_, e) => e.Handled = true;
        _hotkeyBox.GotFocus += (_, _) => _hint.Text = "请按下新的快捷键组合...";
        _hotkeyBox.LostFocus += (_, _) => _hint.Text = "至少包含 Ctrl / Alt / Shift 之一";

        var btnClear = MakeButton("恢复默认", 370, 42, 90);
        btnClear.Click += (_, _) =>
        {
            _modifiers = HotkeyManager.MOD_CONTROL | HotkeyManager.MOD_ALT;
            _key = Keys.A;
            _hotkeyBox.Text = AppSettings.FormatHotkey(_modifiers, _key);
        };

        var lblTranslate = new Label
        {
            Text = "本地翻译服务（LibreTranslate）",
            Left = 20, Top = 110, Width = 440,
            ForeColor = Color.White,
            Font = new Font("Microsoft YaHei UI", 9f, FontStyle.Bold)
        };

        _chkLocal = new CheckBox
        {
            Text = "使用本地服务翻译",
            Left = 20, Top = 138, Width = 180,
            Checked = settings.UseLocalTranslate,
            ForeColor = Color.White,
            BackColor = Color.Transparent
        };

        _chkFallback = new CheckBox
        {
            Text = "本地失败时允许在线降级",
            Left = 220, Top = 138, Width = 220,
            Checked = settings.AllowOnlineFallback,
            ForeColor = Color.White,
            BackColor = Color.Transparent
        };

        var lblHost = new Label
        {
            Text = "主机",
            Left = 20, Top = 178, Width = 40,
            ForeColor = Color.FromArgb(200, 200, 200)
        };

        _hostBox = new TextBox
        {
            Left = 60, Top = 174, Width = 180, Height = 28,
            BackColor = Color.FromArgb(62, 62, 66),
            ForeColor = Color.White,
            Text = settings.LibreTranslateHost
        };
        _hostBox.TextChanged += (_, _) => RefreshUrlPreview();

        var lblPort = new Label
        {
            Text = "端口",
            Left = 260, Top = 178, Width = 40,
            ForeColor = Color.FromArgb(200, 200, 200)
        };

        // 端口独立可调：1~65535，避免 5000 被占用
        _portBox = new NumericUpDown
        {
            Left = 300, Top = 174, Width = 90, Height = 28,
            Minimum = 1,
            Maximum = 65535,
            Value = Math.Clamp(settings.LibreTranslatePort, 1, 65535),
            BackColor = Color.FromArgb(62, 62, 66),
            ForeColor = Color.White,
            BorderStyle = BorderStyle.FixedSingle
        };
        _portBox.ValueChanged += (_, _) => RefreshUrlPreview();

        var btnProbe = MakeButton("检测", 400, 172, 60);
        btnProbe.Click += async (_, _) => await ProbeAsync();

        _urlPreview = new Label
        {
            Left = 20, Top = 212, Width = 440, Height = 22,
            ForeColor = Color.FromArgb(120, 200, 255),
            Text = ""
        };

        _probeLabel = new Label
        {
            Left = 20, Top = 240, Width = 440, Height = 56,
            ForeColor = Color.FromArgb(180, 180, 180),
            Text = "若提示「积极拒绝」：本地服务未启动。\n请运行 scripts\\start-libretranslate.ps1，或勾选在线降级。"
        };

        var btnStartHint = MakeButton("启动说明", 20, 300, 90);
        btnStartHint.Click += (_, _) =>
        {
            MessageBox.Show(this,
                "本地翻译需要先启动 LibreTranslate：\n\n" +
                "方式一（推荐 Docker）：\n" +
                "  .\\scripts\\start-libretranslate.ps1\n" +
                "  .\\scripts\\start-libretranslate.ps1 -Port 5001\n\n" +
                "方式二（Python）：\n" +
                "  pip install libretranslate\n" +
                "  libretranslate --host 127.0.0.1 --port 5000\n\n" +
                "启动后在本页点「检测」，通过后再对照翻译。\n" +
                "若暂时不启动本地服务，请勾选「本地失败时允许在线降级」。",
                "启动本地翻译", MessageBoxButtons.OK, MessageBoxIcon.Information);
        };

        var btnOk = MakeButton("保存", 280, 340, 80);
        btnOk.BackColor = Color.FromArgb(0, 122, 204);
        btnOk.Click += (_, _) => SaveAndClose();

        var btnCancel = MakeButton("取消", 380, 340, 80);
        btnCancel.DialogResult = DialogResult.Cancel;

        AcceptButton = btnOk;
        CancelButton = btnCancel;
        Controls.AddRange(new Control[]
        {
            lblHotkey, _hotkeyBox, btnClear, _hint,
            lblTranslate, _chkLocal, _chkFallback,
            lblHost, _hostBox, lblPort, _portBox, btnProbe,
            _urlPreview, _probeLabel, btnStartHint, btnOk, btnCancel
        });

        RefreshUrlPreview();
    }

    private void RefreshUrlPreview()
    {
        var host = string.IsNullOrWhiteSpace(_hostBox.Text) ? "127.0.0.1" : _hostBox.Text.Trim();
        var port = (int)_portBox.Value;
        _urlPreview.Text = $"完整地址：http://{host}:{port}";
    }

    private static Button MakeButton(string text, int left, int top, int width) => new()
    {
        Text = text,
        Left = left,
        Top = top,
        Width = width,
        Height = 30,
        FlatStyle = FlatStyle.Flat,
        ForeColor = Color.White,
        BackColor = Color.FromArgb(62, 62, 66)
    };

    private void HotkeyBox_KeyDown(object? sender, KeyEventArgs e)
    {
        e.SuppressKeyPress = true;
        e.Handled = true;

        if (e.KeyCode is Keys.ControlKey or Keys.ShiftKey or Keys.Menu
            or Keys.LWin or Keys.RWin or Keys.None)
            return;

        uint mod = 0;
        if (e.Control) mod |= HotkeyManager.MOD_CONTROL;
        if (e.Alt) mod |= HotkeyManager.MOD_ALT;
        if (e.Shift) mod |= HotkeyManager.MOD_SHIFT;

        if (mod == 0)
        {
            _hint.Text = "请至少同时按下 Ctrl、Alt 或 Shift 之一作为修饰键。";
            _hint.ForeColor = Color.Orange;
            return;
        }

        _modifiers = mod;
        _key = e.KeyCode;
        _hotkeyBox.Text = AppSettings.FormatHotkey(_modifiers, _key);
        _hint.ForeColor = Color.FromArgb(180, 180, 180);
        _hint.Text = $"已捕获：{_hotkeyBox.Text}";
    }

    private async Task ProbeAsync()
    {
        var temp = BuildTempSettings();
        _probeLabel.ForeColor = Color.FromArgb(180, 180, 180);
        _probeLabel.Text = $"正在检测 {temp.GetNormalizedLibreUrl()} ...";

        using var svc = new TranslateService(temp);
        var (ok, msg) = await svc.ProbeLocalAsync().ConfigureAwait(true);
        _probeLabel.ForeColor = ok ? Color.LightGreen : Color.Orange;
        _probeLabel.Text = msg;
    }

    private AppSettings BuildTempSettings() => new()
    {
        LibreTranslateHost = string.IsNullOrWhiteSpace(_hostBox.Text) ? "127.0.0.1" : _hostBox.Text.Trim(),
        LibreTranslatePort = (int)_portBox.Value,
        UseLocalTranslate = true,
        AllowOnlineFallback = false
    };

    private void SaveAndClose()
    {
        var temp = new AppSettings { HotkeyModifiers = _modifiers, HotkeyKey = (int)_key };
        if (!temp.IsHotkeyValid())
        {
            MessageBox.Show(this, "快捷键无效，请重新设置。", "提示",
                MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var host = _hostBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(host))
            host = "127.0.0.1";

        var port = (int)_portBox.Value;
        if (port is < 1 or > 65535)
        {
            MessageBox.Show(this, "端口必须在 1～65535 之间。", "提示",
                MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        _settings.HotkeyModifiers = _modifiers;
        _settings.HotkeyKey = (int)_key;
        _settings.LibreTranslateHost = host;
        _settings.LibreTranslatePort = port;
        _settings.UseLocalTranslate = _chkLocal.Checked;
        _settings.AllowOnlineFallback = _chkFallback.Checked;
        _settings.Save();

        DialogResult = DialogResult.OK;
        Close();
    }
}
