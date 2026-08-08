"""路径工具：开发目录 / PyInstaller 打包目录统一解析。"""
from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """程序根目录（打包后为 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """资源根（打包后可能在 _MEIPASS 或 exe 旁）。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return app_root()
    return app_root()


def models_dir() -> Path:
    """优先使用 exe 旁 models（绿色分发），否则用资源内 models。"""
    external = app_root() / "models"
    if external.exists():
        return external
    return resource_root() / "models"


def settings_path() -> Path:
    return app_root() / "settings.json"
