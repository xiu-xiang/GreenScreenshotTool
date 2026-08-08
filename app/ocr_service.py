"""离线 OCR：RapidOCR（ONNX），模型随包分发，无需联网。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image


@dataclass
class OcrResult:
    full_text: str
    lines: List[str]
    confidence: float


_engine = None
_init_error: Optional[str] = None


def _get_engine():
    global _engine, _init_error
    if _engine is not None:
        return _engine
    if _init_error:
        raise RuntimeError(_init_error)
    try:
        from rapidocr_onnxruntime import RapidOCR

        # 使用包内置中英模型，绿色发布时由 PyInstaller 收集
        _engine = RapidOCR()
        return _engine
    except Exception as ex:
        _init_error = f"OCR 引擎初始化失败: {ex}"
        raise RuntimeError(_init_error) from ex


def extract_text(image: Image.Image) -> OcrResult:
    """从 PIL 图像提取文字行。"""
    engine = _get_engine()
    # 转 RGB numpy
    rgb = image.convert("RGB")
    arr = np.array(rgb)
    result, _elapse = engine(arr)
    if not result:
        return OcrResult("", [], 0.0)

    # RapidOCR: [box, text, score]
    items = []
    for item in result:
        if len(item) < 3:
            continue
        box, text, score = item[0], str(item[1]).strip(), float(item[2])
        if not text:
            continue
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append((sum(ys) / len(ys), min(xs), text, score))

    items.sort(key=lambda x: (x[0], x[1]))
    lines = _merge_lines(items)
    conf = float(np.mean([i[3] for i in items])) if items else 0.0
    return OcrResult("\n".join(lines), lines, conf)


def _merge_lines(items: List[Tuple[float, float, str, float]]) -> List[str]:
    if not items:
        return []
    lines: List[List[str]] = []
    cur = [items[0][2]]
    cur_y = items[0][0]
    for cy, _lx, text, _sc in items[1:]:
        if abs(cy - cur_y) <= 18:
            cur.append(text)
        else:
            lines.append(cur)
            cur = [text]
            cur_y = cy
    lines.append(cur)

    out = []
    for parts in lines:
        if len(parts) == 1:
            out.append(parts[0])
        else:
            # 中文相邻不加空格
            s = parts[0]
            for p in parts[1:]:
                if _is_cjk(s[-1]) and _is_cjk(p[0]):
                    s += p
                else:
                    s += " " + p
            out.append(s)
    return out


def _is_cjk(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF
