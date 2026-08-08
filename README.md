# 绿色便携截图工具（Python）

Win10+ x64 绿色截图工具：**默认离线本机运行**，OCR + 中英对照翻译模型可随包分发；可在编辑器中临时切换联网翻译。

## 分支说明

| 分支 | 内容 |
|------|------|
| `main` | **Python 版（主分支）** — 本目录 |
| `csharp` | C# WinForms 版 |

## 功能

- 全局热键框选截图（默认 `Ctrl+Alt+A`）
- 标注：矩形 / 椭圆 / 箭头 / 画笔 / 文字 / 马赛克
- 保存 / 复制图片
- 离线 OCR（RapidOCR）
- 离线对照翻译（Argos en↔zh），结果侧栏可划选复制
- 每次启动强制离线；勾选「本次使用联网翻译」仅影响当前会话

## 开发运行

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\download_models.py
.\.venv\Scripts\python.exe run.py
```

## 绿色发布

```powershell
.\scripts\build_portable.ps1
```

输出：`dist\ShotPortable-Green\`，拷贝整个文件夹到目标电脑运行 `ShotPortable.exe` 即可（无需安装 Python/Docker）。

## 说明

- 大体积模型不纳入 Git，请用 `scripts\download_models.py` 下载后再发布
- 详见 [使用说明.txt](./使用说明.txt)
