namespace ScreenshotTool.Services;

/// <summary>
/// 结果通信通道：后台 OCR/翻译通过事件把结果回传到编辑器侧栏，无需新开窗口
/// </summary>
public sealed class ResultMessenger
{
    /// <summary>
    /// 状态文案更新（进度提示）
    /// </summary>
    public event Action<string>? StatusChanged;

    /// <summary>
    /// 纯文本/带样式行结果推送
    /// </summary>
    public event Action<ResultMessage>? ResultReceived;

    /// <summary>
    /// 忙碌状态变化（禁用按钮等）
    /// </summary>
    public event Action<bool>? BusyChanged;

    public void PublishStatus(string status) => StatusChanged?.Invoke(status);

    public void PublishBusy(bool busy) => BusyChanged?.Invoke(busy);

    public void Publish(ResultMessage message) => ResultReceived?.Invoke(message);
}

/// <summary>
/// 回传到界面的结果消息
/// </summary>
public sealed class ResultMessage
{
    public ResultKind Kind { get; init; }
    public string PlainText { get; init; } = string.Empty;
    public IReadOnlyList<StyledLine> Lines { get; init; } = Array.Empty<StyledLine>();
    public string? Status { get; init; }
}

public enum ResultKind
{
    Clear,
    Ocr,
    ContrastTranslate,
    Error
}

/// <summary>
/// 带颜色的一行文本
/// </summary>
public sealed record StyledLine(string Text, Color Color);
