"""空壳 stanza：绿色包不携带真实 stanza/torch，仅满足 import。"""
from __future__ import annotations

from types import SimpleNamespace


class Pipeline:
    """占位 Pipeline：不会联网、不加载模型。"""

    def __init__(self, *args, **kwargs):
        self.lang = kwargs.get("lang")

    def __call__(self, text: str):
        # 整段当作一句，真正分句由 OfflineSentencizer 负责
        return SimpleNamespace(sentences=[SimpleNamespace(text=text or "")])


def download(*args, **kwargs):
    return None
