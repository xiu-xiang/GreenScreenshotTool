namespace ScreenshotTool.App;

/// <summary>
/// 统一加载应用图标（窗口 / 托盘）
/// </summary>
public static class AppIcon
{
    private static Icon? _cached;

    /// <summary>
    /// 获取应用图标；失败时回退系统图标
    /// </summary>
    public static Icon Get()
    {
        if (_cached != null) return _cached;

        try
        {
            var path = Path.Combine(AppContext.BaseDirectory, "Resources", "app.ico");
            if (File.Exists(path))
            {
                // 复制一份，避免文件锁定
                _cached = new Icon(path);
                return _cached;
            }
        }
        catch
        {
            // 忽略，走回退
        }

        _cached = SystemIcons.Application;
        return _cached;
    }

    /// <summary>
    /// 托盘用小图标
    /// </summary>
    public static Icon GetTrayIcon()
    {
        try
        {
            var path = Path.Combine(AppContext.BaseDirectory, "Resources", "app.ico");
            if (File.Exists(path))
                return new Icon(path, 16, 16);
        }
        catch
        {
            // 回退
        }
        return Get();
    }
}
