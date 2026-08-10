"""开发启动入口。"""
import os

# 修复：尽早禁用 Argos/Stanza 联网分句，避免离线翻译触发模型下载
os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
os.environ.setdefault("ARGOS_STANZA_AVAILABLE", "0")

# 尽早注入空壳，防止缺 stanza 直接失败
from app.translate_service import _install_offline_stubs, setup_offline_env

_install_offline_stubs()
setup_offline_env()

from app.main import run

if __name__ == "__main__":
    raise SystemExit(run())
