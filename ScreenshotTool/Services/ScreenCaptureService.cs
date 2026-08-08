namespace ScreenshotTool.Services;

/// <summary>
/// 屏幕捕获服务：支持多显示器虚拟桌面
/// </summary>
public static class ScreenCaptureService
{
    /// <summary>
    /// 捕获整个虚拟屏幕（所有显示器）
    /// </summary>
    public static Bitmap CaptureVirtualScreen()
    {
        var bounds = SystemInformation.VirtualScreen;
        var bmp = new Bitmap(bounds.Width, bounds.Height);
        using var g = Graphics.FromImage(bmp);
        g.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size);
        return bmp;
    }

    /// <summary>
    /// 按矩形裁剪位图（坐标相对于虚拟屏幕）
    /// </summary>
    public static Bitmap Crop(Bitmap source, Rectangle rect)
    {
        rect.Intersect(new Rectangle(0, 0, source.Width, source.Height));
        if (rect.Width <= 0 || rect.Height <= 0)
            throw new ArgumentException("截图区域无效");

        var result = new Bitmap(rect.Width, rect.Height);
        using var g = Graphics.FromImage(result);
        g.DrawImage(source, new Rectangle(0, 0, rect.Width, rect.Height), rect, GraphicsUnit.Pixel);
        return result;
    }
}
