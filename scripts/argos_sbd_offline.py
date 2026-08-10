"""打包后覆盖 argostranslate/sbd.py：纯本地分句，禁止 stanza/torch。"""
from __future__ import annotations

import re
from typing import List

from argostranslate.package import Package
from argostranslate.utils import info


class ISentenceBoundaryDetectionModel:
    pkg: Package

    def split_sentences(self, text: str) -> List[str]:
        raise NotImplementedError


def _split_offline(text: str) -> List[str]:
    """OCR/短句场景用正则分句，零网络、零重模型。"""
    text = (text or "").strip()
    if not text:
        return [""]
    chunks: List[str] = []
    for para in text.replace("\r\n", "\n").split("\n"):
        para = para.strip()
        if not para:
            continue
        parts = re.split(r"(?<=[。！？.!?;；])\s*", para)
        chunks.extend(p for p in parts if p and p.strip())
    return chunks or [text]


class OfflineSentencizer(ISentenceBoundaryDetectionModel):
    def __init__(self, pkg: Package = None):
        self.pkg = pkg

    def split_sentences(self, text: str) -> List[str]:
        info("OfflineSentencizer", text[:80] if text else "")
        return _split_offline(text)

    def __str__(self):
        return "OfflineSentencizer"


class SpacySentencizerSmall(OfflineSentencizer):
    pass


class MiniSBDSentencizer(OfflineSentencizer):
    LANGUAGE_CODE_MAPPING = {}

    def lazy_detector(self):
        return None


class StanzaSentencizer(OfflineSentencizer):
    LANGUAGE_CODE_MAPPING = {}

    def lazy_pipeline(self):
        return None


def get_sbd_package():
    return None


def detect_sentence(input_text, sbd_translation, sentence_length=250):
    return min(len(input_text), sentence_length)
