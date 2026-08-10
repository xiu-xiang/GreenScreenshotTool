"""开发启动入口。"""
import os

# 修复：尽早禁用 Argos/Stanza 联网分句，避免离线翻译触发模型下载
os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
os.environ.setdefault("ARGOS_STANZA_AVAILABLE", "0")

from app.main import run

if __name__ == "__main__":
    raise SystemExit(run())
