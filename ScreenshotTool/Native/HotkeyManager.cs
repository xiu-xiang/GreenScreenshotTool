using System.Runtime.InteropServices;

namespace ScreenshotTool.Native;

/// <summary>
/// 全局热键注册（默认 Ctrl+Alt+A）
/// </summary>
public sealed class HotkeyManager : IDisposable
{
    public const int HotkeyId = 0x7001;
    private readonly IntPtr _handle;
    private bool _registered;

    [DllImport("user32.dll")]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll")]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    public const uint MOD_ALT = 0x0001;
    public const uint MOD_CONTROL = 0x0002;
    public const uint MOD_SHIFT = 0x0004;
    public const uint MOD_NOREPEAT = 0x4000;

    public HotkeyManager(IntPtr handle) => _handle = handle;

    /// <summary>
    /// 注册热键，返回是否成功
    /// </summary>
    public bool Register(uint modifiers, Keys key)
    {
        Unregister();
        _registered = RegisterHotKey(_handle, HotkeyId, modifiers | MOD_NOREPEAT, (uint)key);
        return _registered;
    }

    public void Unregister()
    {
        if (_registered)
        {
            UnregisterHotKey(_handle, HotkeyId);
            _registered = false;
        }
    }

    public void Dispose() => Unregister();
}
