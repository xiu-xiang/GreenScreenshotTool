namespace ScreenshotTool.Models;

/// <summary>
/// 单条标注数据（支持撤销/重做）
/// </summary>
public class AnnotationItem
{
    public DrawToolType Tool { get; set; }
    public Point Start { get; set; }
    public Point End { get; set; }
    public Color Color { get; set; } = Color.Red;
    public int Thickness { get; set; } = 3;
    public string Text { get; set; } = string.Empty;
    public Font? Font { get; set; }
    public List<Point> PenPoints { get; set; } = new();
}
