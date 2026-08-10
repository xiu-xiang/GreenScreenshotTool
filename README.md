# 绿色便携截图工具（Python）

Win10+ x64 绿色截图工具：**默认离线本机运行**，OCR + 中英对照翻译模型可随包分发；可在编辑器中临时切换联网翻译。

仓库：https://github.com/xiu-xiang/GreenScreenshotTool

## 分支说明

| 分支 | 内容 |
|------|------|
| `main` | **Python 版（主分支）** — 本目录 |
| `csharp` | C# WinForms 版 |

## 功能

- 全局热键框选截图（默认 `Ctrl+Alt+A`）
- 标注：矩形 / 椭圆 / 箭头 / 画笔 / 文字 / 马赛克
- 保存 / 复制图片
- 离线 OCR（RapidOCR / ONNX）
- 离线对照翻译（Argos en↔zh），结果在编辑器右侧栏，可划选复制
- **启动后后台预加载翻译模型**；右侧栏 / 托盘提示「加载中 → 已就绪」
- 每次启动强制离线；勾选「本次使用联网翻译」仅影响当前会话

## 开发运行

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\download_models.py
.\.venv\Scripts\python.exe run.py
# 或双击：启动开发版.bat
```

## 绿色发布

```powershell
.\scripts\build_portable.ps1
```

输出：`dist\ShotPortable-Green\`（同时整理 `dist\ShotPortable\`）。

把**整个文件夹**拷到目标电脑，运行 `ShotPortable.exe`（无需安装 Python / Docker）。精简后发布包约 **1GB 内**，目录要点：

```
ShotPortable.exe
使用说明.txt
models\argos_installed\...
_internal\...
```

构建脚本会自动：

1. 确保离线模型已下载
2. PyInstaller 打包（排除 torch/spacy/stanza）
3. 只拷贝运行时 `argos_installed`（不带 `.argosmodel` 与 cache）
4. 覆盖离线分句模块；禁止 ctranslate2 导入 torch
5. 再剔除误打进包的 torch/spacy 等膨胀目录

## 离线翻译说明

- 模型不进 Git，请用 `scripts\download_models.py` 下载后再发布
- 启动即后台预热英↔中模型；未就绪时点「对照翻译」会等待加载完成后自动开始
- 分句使用本地正则，不依赖 Stanza / MiniSBD 网络下载
- 若提示缺少模型：把 `models\argos_installed` 放到与 exe 同级

## 详细说明

见 [使用说明.txt](./使用说明.txt)
