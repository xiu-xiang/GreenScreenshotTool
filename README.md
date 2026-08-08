# 截图工具（C# WinForms）

本分支为 **C# 版本**。主功能分支请切换到 `main`（Python 绿色便携版）。

## 分支说明

| 分支 | 内容 |
|------|------|
| `main` | Python 绿色便携版（推荐，默认离线、模型可打包） |
| `csharp` | **本分支** — .NET 8 WinForms |

## 功能概要

- 托盘 + 全局热键截图
- 标注、保存、OCR（PaddleOCR）、对照翻译
- 设置中可配置热键与本地 LibreTranslate 地址/端口

## 运行

```powershell
cd ScreenshotTool
dotnet run -c Release
```

或打开 `ScreenshotTool.slnx` 用 Visual Studio 编译。

## 说明

- OCR 依赖 NuGet：`PaddleOCRSharp` + `Paddle.Runtime.win_x64`（发布时会复制 `inference/`）
- 本地翻译默认 `http://127.0.0.1:端口`，需自行启动 LibreTranslate；或设置中允许在线降级
- 更完整的「免环境绿色包」请使用 `main` 分支 Python 版
