using ScreenshotTool.Controls;

namespace ScreenshotTool.Services;

/// <summary>
/// OCR/翻译后台任务：完成后通过 ResultMessenger 把结果回传给编辑器侧栏
/// </summary>
public sealed class OcrTranslateWorker
{
    private readonly ResultMessenger _messenger;
    private CancellationTokenSource? _cts;

    public OcrTranslateWorker(ResultMessenger messenger) => _messenger = messenger;

    /// <summary>
    /// 提取文字；若 translate=true 则继续对照翻译
    /// </summary>
    public async Task RunAsync(Bitmap image, bool translate)
    {
        _cts?.Cancel();
        _cts = new CancellationTokenSource();
        var ct = _cts.Token;

        _messenger.PublishBusy(true);
        _messenger.Publish(new ResultMessage { Kind = ResultKind.Clear });
        _messenger.PublishStatus(translate ? "正在识别并翻译（PaddleOCR）..." : "正在 OCR 识别（PaddleOCR 中英模型）...");

        try
        {
            using var ocr = new OcrService();
            if (!ocr.IsModelReady)
            {
                _messenger.Publish(new ResultMessage
                {
                    Kind = ResultKind.Error,
                    Status = "缺少 OCR 模型",
                    PlainText = $"未找到模型：{ocr.ModelPath}",
                    Lines = new[]
                    {
                        new StyledLine("未找到 PaddleOCR 模型文件。", ResultSidePanel.ColorWarn),
                        new StyledLine("请重新编译/发布程序（inference 目录应由 NuGet 自动复制）。", ResultSidePanel.ColorTranslation),
                        new StyledLine(ocr.ModelPath, ResultSidePanel.ColorSource)
                    }
                });
                return;
            }

            // 后台线程识别（引擎全局复用）；首次加载模型可能稍慢
            using var workBmp = (Bitmap)image.Clone();
            var ocrResult = await Task.Run(() =>
            {
                using var engine = new OcrService();
                return engine.ExtractText(workBmp);
            }, ct).ConfigureAwait(true);

            ct.ThrowIfCancellationRequested();

            if (!translate)
            {
                _messenger.Publish(new ResultMessage
                {
                    Kind = ResultKind.Ocr,
                    Status = $"识别完成：{ocrResult.Lines.Count} 行，置信度 {ocrResult.Confidence:P0}",
                    PlainText = ocrResult.FullText,
                    Lines = ocrResult.Lines
                        .Select(l => new StyledLine(l, ResultSidePanel.ColorSource))
                        .ToList()
                });
                return;
            }

            // 识别完成先展示原文，再异步填充对照翻译
            _messenger.Publish(new ResultMessage
            {
                Kind = ResultKind.Ocr,
                Status = $"识别完成，开始对照翻译（{ocrResult.Lines.Count} 行）...",
                PlainText = ocrResult.FullText,
                Lines = ocrResult.Lines
                    .Select(l => new StyledLine(l, ResultSidePanel.ColorSource))
                    .ToList()
            });

            using var translator = new TranslateService();
            var progress = new Progress<string>(s => _messenger.PublishStatus(s));
            var contrast = await translator.TranslateContrastAsync(ocrResult.Lines, progress, ct)
                .ConfigureAwait(true);

            var styled = new List<StyledLine>();
            foreach (var line in contrast)
            {
                styled.Add(new StyledLine("// " + line.Source, ResultSidePanel.ColorSource));
                styled.Add(new StyledLine(line.Translation, ResultSidePanel.ColorTranslation));
                styled.Add(new StyledLine(string.Empty, ResultSidePanel.ColorTranslation));
            }

            _messenger.Publish(new ResultMessage
            {
                Kind = ResultKind.ContrastTranslate,
                Status = $"对照翻译完成：{contrast.Count} 行",
                PlainText = TranslateService.FormatContrastText(contrast),
                Lines = styled
            });
        }
        catch (OperationCanceledException)
        {
            _messenger.PublishStatus("已取消");
        }
        catch (Exception ex)
        {
            _messenger.Publish(new ResultMessage
            {
                Kind = ResultKind.Error,
                Status = "处理失败",
                PlainText = ex.Message,
                Lines = new[] { new StyledLine(ex.Message, ResultSidePanel.ColorWarn) }
            });
        }
        finally
        {
            _messenger.PublishBusy(false);
        }
    }

    public void Cancel() => _cts?.Cancel();
}
