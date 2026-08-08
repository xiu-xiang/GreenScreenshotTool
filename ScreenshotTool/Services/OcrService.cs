using System.Drawing.Drawing2D;
using System.Text;
using PaddleOCRSharp;

namespace ScreenshotTool.Services;

/// <summary>
/// OCR 服务：优先使用开源 PaddleOCR（中文友好，模型随 NuGet 嵌入 inference/）
/// </summary>
public sealed class OcrService : IDisposable
{
    private static readonly object Sync = new();
    private static PaddleOCREngine? _engine;
    private static string? _initError;

    private readonly string _inferencePath;

    public OcrService()
    {
        _inferencePath = Path.Combine(AppContext.BaseDirectory, "inference");
    }

    /// <summary>
    /// Paddle 默认模型是否已随程序输出
    /// </summary>
    public bool IsModelReady =>
        Directory.Exists(_inferencePath)
        && (Directory.Exists(Path.Combine(_inferencePath, "PP-OCRv6_small_det_infer"))
            || Directory.Exists(Path.Combine(_inferencePath, "PP-OCRv5_mobile_det_infer")))
        && File.Exists(Path.Combine(_inferencePath, "ppocr_keys.txt"));

    public string ModelPath => _inferencePath;

    public string EngineName => "PaddleOCR (PP-OCR)";

    private static PaddleOCREngine GetEngine()
    {
        if (_engine != null) return _engine;
        lock (Sync)
        {
            if (_engine != null) return _engine;
            if (!string.IsNullOrEmpty(_initError))
                throw new InvalidOperationException(_initError);

            try
            {
                // 针对屏幕截图/中英混合优化参数
                var param = new OCRParameter
                {
                    use_gpu = false,
                    enable_mkldnn = true,
                    det = true,
                    rec = true,
                    cls = true, // 方向分类，提升倾斜/竖排中文
                    use_angle_cls = true,
                    max_side_len = 1440, // 更大边长，保留小字细节
                    det_db_thresh = 0.3f,
                    det_db_box_thresh = 0.45f, // 略降阈值，减少漏检
                    det_db_unclip_ratio = 1.8f,
                    cpu_math_library_num_threads = Math.Clamp(Environment.ProcessorCount / 2, 2, 8),
                    rec_batch_num = 8
                };

                // config=null：使用程序目录 inference 下默认中英模型
                _engine = new PaddleOCREngine(null, param);
                return _engine;
            }
            catch (Exception ex)
            {
                _initError = "PaddleOCR 引擎初始化失败：" + ex.Message;
                throw new InvalidOperationException(_initError, ex);
            }
        }
    }

    /// <summary>
    /// 从位图提取文字（按阅读顺序分行）
    /// </summary>
    public OcrResult ExtractText(Bitmap image)
    {
        if (!IsModelReady)
            throw new InvalidOperationException(
                $"未找到 PaddleOCR 模型，期望目录：{_inferencePath}\n请重新编译发布（模型由 NuGet 自动复制）。");

        var engine = GetEngine();

        // 小图放大，显著提升中文小字准确率
        using var prepared = PrepareForOcr(image);
        var raw = engine.DetectText(prepared);
        if (raw?.TextBlocks == null || raw.TextBlocks.Count == 0)
            return new OcrResult(string.Empty, Array.Empty<string>(), 0f);

        // 按坐标排序并合并为自然阅读行
        var lines = BuildReadingLines(raw.TextBlocks);
        var full = string.Join(Environment.NewLine, lines);
        var conf = raw.TextBlocks.Average(b => b.Score);

        return new OcrResult(full, lines, conf);
    }

    /// <summary>
    /// 预处理：小分辨率截图放大，利于中文识别
    /// </summary>
    private static Bitmap PrepareForOcr(Bitmap source)
    {
        float scale = 1f;
        // IDE/注释类截图字号通常偏小，适当放大
        if (source.Width < 700 || source.Height < 320)
            scale = 2.2f;
        else if (source.Width < 1100 || source.Height < 500)
            scale = 1.6f;
        else if (source.Width < 1600)
            scale = 1.25f;

        if (Math.Abs(scale - 1f) < 0.01f)
            return (Bitmap)source.Clone();

        var w = Math.Max(1, (int)(source.Width * scale));
        var h = Math.Max(1, (int)(source.Height * scale));
        var bmp = new Bitmap(w, h, System.Drawing.Imaging.PixelFormat.Format24bppRgb);
        using var g = Graphics.FromImage(bmp);
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        g.SmoothingMode = SmoothingMode.HighQuality;
        g.PixelOffsetMode = PixelOffsetMode.HighQuality;
        g.CompositingQuality = CompositingQuality.HighQuality;
        g.Clear(Color.White);
        g.DrawImage(source, 0, 0, w, h);
        return bmp;
    }

    /// <summary>
    /// 将检测框按从上到下、从左到右合并成文本行
    /// </summary>
    private static List<string> BuildReadingLines(IEnumerable<TextBlock> blocks)
    {
        var items = blocks
            .Where(b => !string.IsNullOrWhiteSpace(b.Text))
            .Select(b =>
            {
                var ys = b.BoxPoints.Select(p => p.Y).ToArray();
                var xs = b.BoxPoints.Select(p => p.X).ToArray();
                return new
                {
                    Text = b.Text.Trim(),
                    Top = ys.Min(),
                    Bottom = ys.Max(),
                    Left = xs.Min(),
                    CenterY = ys.Average()
                };
            })
            .OrderBy(i => i.CenterY)
            .ThenBy(i => i.Left)
            .ToList();

        var lines = new List<string>();
        if (items.Count == 0) return lines;

        var current = new List<string> { items[0].Text };
        var lineTop = items[0].Top;
        var lineBottom = items[0].Bottom;

        for (int i = 1; i < items.Count; i++)
        {
            var item = items[i];
            var lineHeight = Math.Max(8, lineBottom - lineTop);
            // 垂直重叠较多则视为同一行（中英文混排常见）
            var sameLine = item.CenterY >= lineTop - lineHeight * 0.35
                           && item.CenterY <= lineBottom + lineHeight * 0.35;

            if (sameLine)
            {
                current.Add(item.Text);
                lineTop = Math.Min(lineTop, item.Top);
                lineBottom = Math.Max(lineBottom, item.Bottom);
            }
            else
            {
                lines.Add(JoinLine(current));
                current = new List<string> { item.Text };
                lineTop = item.Top;
                lineBottom = item.Bottom;
            }
        }

        if (current.Count > 0)
            lines.Add(JoinLine(current));

        return lines.Where(l => !string.IsNullOrWhiteSpace(l)).ToList();
    }

    private static string JoinLine(List<string> parts)
    {
        if (parts.Count == 1) return parts[0];
        var sb = new StringBuilder();
        for (int i = 0; i < parts.Count; i++)
        {
            if (i > 0)
            {
                var prev = parts[i - 1];
                var next = parts[i];
                // 中文之间不加空格，中英/数字交界保留空格
                bool needSpace = NeedsSpace(prev[^1], next[0]);
                if (needSpace) sb.Append(' ');
            }
            sb.Append(parts[i]);
        }
        return sb.ToString();
    }

    private static bool NeedsSpace(char a, char b)
    {
        bool aHan = IsCjk(a);
        bool bHan = IsCjk(b);
        if (aHan && bHan) return false;
        if (char.IsWhiteSpace(a) || char.IsWhiteSpace(b)) return false;
        return true;
    }

    private static bool IsCjk(char c) =>
        c >= 0x4E00 && c <= 0x9FFF
        || c >= 0x3400 && c <= 0x4DBF
        || c >= 0x3000 && c <= 0x303F;

    public void Dispose()
    {
        // 引擎全局复用，避免每次识别重新加载模型（耗时大）
    }

    /// <summary>
    /// 进程退出时可释放共享引擎
    /// </summary>
    public static void Shutdown()
    {
        lock (Sync)
        {
            _engine?.Dispose();
            _engine = null;
            _initError = null;
        }
    }
}

/// <summary>
/// OCR 识别结果
/// </summary>
public sealed record OcrResult(string FullText, IReadOnlyList<string> Lines, float Confidence);
