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
    """资源根（打包后可能在 _MEIPASS/_internal 或 exe 旁）。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return app_root()
    return app_root()


def _looks_like_models(path: Path) -> bool:
    """判断目录是否已包含可用离线翻译模型。"""
    if not path.is_dir():
        return False
    # 已安装包或原始 .argosmodel 任一存在即可
    installed = path / "argos_installed"
    if installed.is_dir() and any(installed.iterdir()):
        return True
    argos = path / "argos"
    if argos.is_dir() and any(argos.glob("*.argosmodel")):
        return True
    return False


def models_dir() -> Path:
    """
    查找 models 目录，优先级：
    1) exe 旁 models（绿色分发推荐位置）
    2) _internal/models（PyInstaller 资源）
    3) 开发源码旁 models
    若都不含模型文件，仍返回 exe 旁 models，便于提示放置位置。
    """
    candidates = [
        app_root() / "models",
        resource_root() / "models",
        app_root() / "_internal" / "models",
    ]
    # 去重且保持顺序
    seen = set()
    ordered: list[Path] = []
    for c in candidates:
        key = str(c.resolve()) if c.exists() else str(c)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(c)

    for c in ordered:
        if _looks_like_models(c):
            return c

    # 默认落点：exe 旁，方便用户拷贝 models
    preferred = app_root() / "models"
    preferred.mkdir(parents=True, exist_ok=True)
    return preferred


def settings_path() -> Path:
    return app_root() / "settings.json"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
