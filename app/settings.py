"""应用设置：每次启动强制默认离线本机；联网需在设置中手动开启。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.paths import settings_path


@dataclass
class AppSettings:
    # 热键：Ctrl+Alt+A
    hotkey: str = "ctrl+alt+a"
    # 每次启动都会重置为 False（离线）
    use_online: bool = False
    # 以下持久化
    window_width: int = 1100
    window_height: int = 720

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        base = cls()
        for k, v in data.items():
            if hasattr(base, k):
                setattr(base, k, v)
        return base


def load_settings() -> AppSettings:
    """加载设置，但强制本次运行为离线（绿色软件默认本机离线）。"""
    path = settings_path()
    s = AppSettings()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            s = AppSettings.from_dict(data)
        except Exception:
            s = AppSettings()
    # 关键要求：每次启动默认都是离线本机
    s.use_online = False
    return s


def save_settings(s: AppSettings) -> None:
    """保存时不把临时联网状态写成默认启动值（启动仍强制离线）。"""
    path = settings_path()
    data = s.to_dict()
    # 持久化里记录“用户曾用过联网”，但 load 仍会重置 use_online=False
    # 这里保存当前会话值供本次运行使用；启动时 load 会再强制离线
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
