using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using GTranslate.Translators;

namespace ScreenshotTool.Services;

/// <summary>
/// 翻译服务：优先本地 LibreTranslate；本地未启动时自动降级在线（可配置）
/// </summary>
public sealed class TranslateService : IDisposable
{
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(12) };
    private readonly AggregateTranslator _translator = new();
    private readonly AppSettings _settings;
    private readonly string _libreUrl;

    /// <summary>本批次实际通道：local / online</summary>
    private string _activeChannel = "local";

    public TranslateService(AppSettings? settings = null)
    {
        _settings = settings ?? AppSettings.Load();
        _libreUrl = ResolveLibreUrl(_settings);
    }

    public string LocalUrl => _libreUrl;
    public bool UseLocal => _settings.UseLocalTranslate;

    private static string ResolveLibreUrl(AppSettings settings)
    {
        var env = Environment.GetEnvironmentVariable("LIBRETRANSLATE_URL");
        if (!string.IsNullOrWhiteSpace(env))
            return env.Trim().TrimEnd('/');
        return settings.GetNormalizedLibreUrl();
    }

    public static string DetectLang(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return "en";
        int han = 0, latin = 0;
        foreach (var ch in text)
        {
            if (ch >= 0x4E00 && ch <= 0x9FFF) han++;
            else if (char.IsLetter(ch) && ch < 128) latin++;
        }
        return han >= latin ? "zh" : "en";
    }

    public async Task<(bool Ok, string Message)> ProbeLocalAsync(CancellationToken ct = default)
    {
        try
        {
            using var resp = await _http.GetAsync(_libreUrl.TrimEnd('/') + "/languages", ct)
                .ConfigureAwait(false);
            if (resp.IsSuccessStatusCode)
                return (true, $"本地服务可用：{_libreUrl}");
            return (false, $"本地服务响应异常 HTTP {(int)resp.StatusCode}：{_libreUrl}");
        }
        catch (Exception ex)
        {
            return (false, BuildLocalDownMessage(ex));
        }
    }

    private string BuildLocalDownMessage(Exception ex)
    {
        return $"无法连接 {_libreUrl}（{ShortError(ex)}）。\n" +
               "请先启动本地服务：scripts\\start-libretranslate.ps1\n" +
               "或在设置中勾选「本地失败时允许在线降级」。";
    }

    private static string ShortError(Exception ex)
    {
        var msg = ex.InnerException?.Message ?? ex.Message;
        if (msg.Contains("积极拒绝", StringComparison.Ordinal) ||
            msg.Contains("refused", StringComparison.OrdinalIgnoreCase))
            return "连接被拒绝，服务未启动或端口不对";
        return msg;
    }

    /// <summary>
    /// 逐行对照翻译
    /// </summary>
    public async Task<IReadOnlyList<ContrastLine>> TranslateContrastAsync(
        IEnumerable<string> lines,
        IProgress<string>? progress = null,
        CancellationToken ct = default)
    {
        var result = new List<ContrastLine>();
        var list = lines.Where(l => !string.IsNullOrWhiteSpace(l)).ToList();

        // 批次开始时探测一次本地，避免每行都报「积极拒绝」
        _activeChannel = "online";
        if (_settings.UseLocalTranslate)
        {
            progress?.Report($"正在检测本地翻译 {_libreUrl} ...");
            var (ok, msg) = await ProbeLocalAsync(ct).ConfigureAwait(false);
            if (ok)
            {
                _activeChannel = "local";
                progress?.Report($"本地翻译可用：{_libreUrl}");
            }
            else if (_settings.AllowOnlineFallback)
            {
                _activeChannel = "online";
                progress?.Report("本地未启动，已自动改用在线翻译");
            }
            else
            {
                // 严格本地模式：整批返回明确指引，避免刷屏
                var tip = BuildLocalDownMessage(new InvalidOperationException(msg));
                progress?.Report("本地翻译不可用");
                return list.Select(l => new ContrastLine(l.Trim(), tip, DetectLang(l), DetectLang(l) == "zh" ? "en" : "zh"))
                    .ToList();
            }
        }

        int i = 0;
        foreach (var line in list)
        {
            ct.ThrowIfCancellationRequested();
            i++;
            var channelTip = _activeChannel == "local" ? $"本地 {_libreUrl}" : "在线";
            progress?.Report($"正在翻译 {i}/{list.Count}（{channelTip}）...");

            var srcLang = DetectLang(line);
            var dstLang = srcLang == "zh" ? "en" : "zh";
            var translated = await TranslateAsync(line, srcLang, dstLang, ct).ConfigureAwait(false);
            result.Add(new ContrastLine(line.Trim(), translated.Trim(), srcLang, dstLang));
        }
        return result;
    }

    public async Task<string> TranslateAsync(string text, string from, string to, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(text)) return string.Empty;
        if (IsMostlyNonLanguage(text)) return text;

        if (_activeChannel == "local")
        {
            try
            {
                var local = await TranslateViaLibreAsync(text, from, to, ct).ConfigureAwait(false);
                if (!string.IsNullOrWhiteSpace(local)) return local!;
            }
            catch (Exception ex)
            {
                // 运行中途本地掉线：若允许则切在线
                if (_settings.AllowOnlineFallback)
                {
                    _activeChannel = "online";
                }
                else
                {
                    return $"[本地翻译失败: {ShortError(ex)}] 请运行 scripts\\start-libretranslate.ps1";
                }
            }
        }

        try
        {
            var fromCode = from == "zh" ? "zh-CN" : "en";
            var toCode = to == "zh" ? "zh-CN" : "en";
            var result = await _translator.TranslateAsync(text, toCode, fromCode).ConfigureAwait(false);
            return result.Translation;
        }
        catch (Exception ex)
        {
            return $"[在线翻译失败: {ex.Message}]";
        }
    }

    private async Task<string?> TranslateViaLibreAsync(string text, string from, string to, CancellationToken ct)
    {
        var url = _libreUrl.TrimEnd('/') + "/translate";
        var payload = new
        {
            q = text,
            source = from == "zh" ? "zh" : "en",
            target = to == "zh" ? "zh" : "en",
            format = "text"
        };

        using var resp = await _http.PostAsJsonAsync(url, payload, ct).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        await using var stream = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
        using var doc = await JsonDocument.ParseAsync(stream, cancellationToken: ct).ConfigureAwait(false);
        if (doc.RootElement.TryGetProperty("translatedText", out var t))
            return t.GetString();
        return null;
    }

    private static bool IsMostlyNonLanguage(string text)
    {
        var letters = text.Count(char.IsLetter);
        return letters == 0 || (text.Length <= 3 && letters <= 1);
    }

    public static string FormatContrastText(IEnumerable<ContrastLine> lines)
    {
        var sb = new StringBuilder();
        foreach (var line in lines)
        {
            sb.AppendLine(line.Source);
            sb.AppendLine(line.Translation);
            sb.AppendLine();
        }
        return sb.ToString().TrimEnd();
    }

    public void Dispose() => _http.Dispose();
}

public sealed record ContrastLine(string Source, string Translation, string SourceLang, string TargetLang);
