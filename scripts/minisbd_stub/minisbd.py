"""空壳 minisbd：避免误走 MiniSBD 联网下载。"""
from __future__ import annotations


class SBDetect:
    def __init__(self, *args, **kwargs):
        self.lang = args[0] if args else "en"

    def sentences(self, text: str):
        return [text] if text else [""]


class models:
    cache_dir = ""

    @staticmethod
    def list_models():
        return []
