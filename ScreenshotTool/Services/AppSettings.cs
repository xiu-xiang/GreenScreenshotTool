using System.Text.Json;
using System.Text.RegularExpressions;
using ScreenshotTool.Native;

namespace ScreenshotTool.Services;

/// <summary>
/// 应用设置（绿色便携：保存在程序目录 settings.json）
/// </summary>
public sealed class AppSettings
{
    private static readonly string SettingsPath =
        Path.Combine(AppContext.BaseDirectory, "settings.json");

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true
    };

    /// <summary>修饰键：Ctrl/Alt/Shift 组合</summary>
    public uint HotkeyModifiers { get; set; } = HotkeyManager.MOD_CONTROL | HotkeyManager.MOD_ALT;

    /// <summary>主键（Keys 枚举值）</summary>
    public int HotkeyKey { get; set; } = (int)Keys.A;

    /// <summary>本地翻译主机（默认 127.0.0.1）</summary>
    public string LibreTranslateHost { get; set; } = "127.0.0.1";

    /// <summary>本地翻译端口（可调整，避免 5000 被占用）</summary>
    public int LibreTranslatePort { get; set; } = 5000;

    /// <summary>
    /// 完整地址（由主机+端口生成，兼容旧配置）
    /// </summary>
    public string LibreTranslateUrl { get; set; } = "http://127.0.0.1:5000";

    /// <summary>是否优先使用本地翻译服务</summary>
    public bool UseLocalTranslate { get; set; } = true;

    /// <summary>本地不可用时是否允许降级到在线翻译（默认开启，避免 5000 未启动就无法用）</summary>
    public bool AllowOnlineFallback { get; set; } = true;

    public static AppSettings Load()
    {
        try
        {
            if (File.Exists(SettingsPath))
            {
                var json = File.ReadAllText(SettingsPath);
                var s = JsonSerializer.Deserialize<AppSettings>(json, JsonOptions);
                if (s != null && s.HotkeyKey != 0)
                {
                    s.NormalizeHostPort();
                    return s;
                }
            }
        }
        catch
        {
            // 损坏时回退默认
        }

        var defaults = new AppSettings();
        defaults.SyncUrlFromHostPort();
        try { defaults.Save(); } catch { /* 忽略只读目录 */ }
        return defaults;
    }

    public void Save()
    {
        NormalizeHostPort();
        SyncUrlFromHostPort();

        var json = JsonSerializer.Serialize(this, JsonOptions);
        File.WriteAllText(SettingsPath, json);

        // 同步一份到 models/translate/config.json
        try
        {
            var dir = Path.Combine(AppContext.BaseDirectory, "models", "translate");
            Directory.CreateDirectory(dir);
            var lite = new
            {
                libreTranslateHost = LibreTranslateHost,
                libreTranslatePort = LibreTranslatePort,
                libreTranslateUrl = LibreTranslateUrl,
                useLocalTranslate = UseLocalTranslate,
                allowOnlineFallback = AllowOnlineFallback,
                comment = "主机与端口可在设置页分别调整；端口被占用时改 LibreTranslatePort 即可"
            };
            File.WriteAllText(
                Path.Combine(dir, "config.json"),
                JsonSerializer.Serialize(lite, JsonOptions));
        }
        catch
        {
            // 同步失败不影响主配置
        }
    }

    /// <summary>
    /// 校正主机/端口：优先独立字段，其次从旧 URL 解析
    /// </summary>
    public void NormalizeHostPort()
    {
        if (string.IsNullOrWhiteSpace(LibreTranslateHost))
            LibreTranslateHost = "127.0.0.1";

        // 端口非法时尝试从 URL 解析，再不行回退 5000
        if (LibreTranslatePort is < 1 or > 65535)
        {
            if (TryParseUrl(LibreTranslateUrl, out _, out var p) && p is >= 1 and <= 65535)
                LibreTranslatePort = p;
            else
                LibreTranslatePort = 5000;
        }

        // 若主机仍是默认且 URL 含自定义主机，则从 URL 回填（兼容旧配置）
        if (TryParseUrl(LibreTranslateUrl, out var host, out var port))
        {
            if (string.Equals(LibreTranslateHost, "127.0.0.1", StringComparison.OrdinalIgnoreCase)
                && !string.IsNullOrWhiteSpace(host)
                && !string.Equals(host, "127.0.0.1", StringComparison.OrdinalIgnoreCase)
                && LibreTranslatePort == 5000)
            {
                LibreTranslateHost = host;
            }

            // 旧配置只有 URL、没有独立 port 字段时（反序列化为 0 已处理），用 URL 端口
            // 若当前 port 仍是默认 5000，但 URL 端口不同，且主机一致，采用 URL 端口
            if (port is >= 1 and <= 65535
                && string.Equals(LibreTranslateHost, host, StringComparison.OrdinalIgnoreCase)
                && LibreTranslatePort == 5000
                && port != 5000)
            {
                LibreTranslatePort = port;
            }
        }

        LibreTranslateHost = LibreTranslateHost.Trim();
        SyncUrlFromHostPort();
    }

    public void SyncUrlFromHostPort()
    {
        var host = string.IsNullOrWhiteSpace(LibreTranslateHost) ? "127.0.0.1" : LibreTranslateHost.Trim();
        var port = LibreTranslatePort is >= 1 and <= 65535 ? LibreTranslatePort : 5000;
        LibreTranslatePort = port;
        LibreTranslateHost = host;
        LibreTranslateUrl = $"http://{host}:{port}";
    }

    private static bool TryParseUrl(string? url, out string host, out int port)
    {
        host = "127.0.0.1";
        port = 5000;
        if (string.IsNullOrWhiteSpace(url)) return false;

        var text = url.Trim();
        if (!text.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
            && !text.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            text = "http://" + text;

        if (Uri.TryCreate(text, UriKind.Absolute, out var uri)
            && !string.IsNullOrWhiteSpace(uri.Host))
        {
            host = uri.Host;
            port = uri.IsDefaultPort ? (uri.Scheme == "https" ? 443 : 80) : uri.Port;
            // LibreTranslate 常见默认仍按 5000 理解：无端口时用 5000
            if (uri.IsDefaultPort && uri.Scheme == "http")
                port = 5000;
            return true;
        }

        // 兜底：host:port
        var m = Regex.Match(text, @"^(?:https?://)?([^:/]+)(?::(\d+))?", RegexOptions.IgnoreCase);
        if (!m.Success) return false;
        host = m.Groups[1].Value;
        if (m.Groups[2].Success && int.TryParse(m.Groups[2].Value, out var p))
            port = p;
        return !string.IsNullOrWhiteSpace(host);
    }

    public Keys Key => (Keys)HotkeyKey;

    public string HotkeyDisplay => FormatHotkey(HotkeyModifiers, Key);

    public static string FormatHotkey(uint modifiers, Keys key)
    {
        var parts = new List<string>();
        if ((modifiers & HotkeyManager.MOD_CONTROL) != 0) parts.Add("Ctrl");
        if ((modifiers & HotkeyManager.MOD_ALT) != 0) parts.Add("Alt");
        if ((modifiers & HotkeyManager.MOD_SHIFT) != 0) parts.Add("Shift");
        parts.Add(KeyToText(key));
        return string.Join("+", parts);
    }

    public static string KeyToText(Keys key)
    {
        return key switch
        {
            Keys.PageUp => "PageUp",
            Keys.PageDown => "PageDown",
            Keys.Oemtilde => "`",
            Keys.OemMinus => "-",
            Keys.Oemplus => "=",
            Keys.OemOpenBrackets => "[",
            Keys.OemCloseBrackets => "]",
            Keys.OemPipe => "\\",
            Keys.OemSemicolon => ";",
            Keys.OemQuotes => "'",
            Keys.Oemcomma => ",",
            Keys.OemPeriod => ".",
            Keys.OemQuestion => "/",
            _ when key >= Keys.D0 && key <= Keys.D9 => ((char)('0' + (key - Keys.D0))).ToString(),
            _ when key >= Keys.A && key <= Keys.Z => key.ToString(),
            _ when key >= Keys.F1 && key <= Keys.F24 => key.ToString(),
            _ => key.ToString()
        };
    }

    public bool IsHotkeyValid()
    {
        var mod = HotkeyModifiers & (HotkeyManager.MOD_CONTROL | HotkeyManager.MOD_ALT | HotkeyManager.MOD_SHIFT);
        if (mod == 0) return false;
        if (HotkeyKey == 0) return false;
        var k = (Keys)HotkeyKey;
        if (k is Keys.ControlKey or Keys.ShiftKey or Keys.Menu or Keys.LWin or Keys.RWin)
            return false;
        return true;
    }

    /// <summary>
    /// 规范化本地服务地址（始终由主机+端口生成）
    /// </summary>
    public string GetNormalizedLibreUrl()
    {
        NormalizeHostPort();
        return LibreTranslateUrl.TrimEnd('/');
    }
}
