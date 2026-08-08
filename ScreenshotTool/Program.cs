using ScreenshotTool.App;

namespace ScreenshotTool;

/// <summary>
/// 程序入口：启动托盘应用，注册全局热键
/// </summary>
static class Program
{
    [STAThread]
    static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        // 单实例：避免重复注册热键
        using var mutex = new Mutex(true, "ScreenshotTool.Portable.SingleInstance", out bool createdNew);
        if (!createdNew)
        {
            MessageBox.Show("截图工具已在运行中。\n默认热键：Ctrl+Alt+A", "提示",
                MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        Application.Run(new TrayAppContext());
    }
}
