"""翻译服务：默认离线 Argos（本机模型）；可选联网 deep-translator。"""
from __future__ import annotations

import os
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from app.paths import app_root, is_frozen, models_dir


@dataclass
class ContrastLine:
    source: str
    translation: str
    source_lang: str
    target_lang: str


import threading

_argos_ready = False
_argos_error: Optional[str] = None
_sbd_patched = False
# 缓存 Translation，避免每行重复初始化
_translation_cache: Dict[Tuple[str, str], object] = {}

# 启动预加载状态（供托盘/右侧栏展示）
_model_loaded = False
_model_loading = False
_model_status = "离线翻译模型未加载"
_model_error: Optional[str] = None
_preload_lock = threading.Lock()


def is_model_ready() -> bool:
    """离线翻译模型是否已预热完成。"""
    return _model_loaded


def is_model_loading() -> bool:
    """是否正在后台加载模型。"""
    return _model_loading


def get_model_status() -> str:
    """给人看的模型状态文案。"""
    return _model_status


def get_model_error() -> Optional[str]:
    return _model_error


def _split_sentences_offline(text: str) -> List[str]:
    """纯本地分句：OCR/对照翻译场景足够，不依赖 Stanza/MiniSBD 联网模型。"""
    import re

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


def _patch_offline_sbd() -> None:
    """猴子补丁：让 Argos 分句永不触发网络下载 / 重模型加载。"""
    global _sbd_patched
    if _sbd_patched:
        return
    try:
        import argostranslate.sbd as sbd

        def _split(self, text: str) -> List[str]:
            return _split_sentences_offline(text)

        for name in (
            "OfflineSentencizer",
            "MiniSBDSentencizer",
            "StanzaSentencizer",
            "SpacySentencizerSmall",
        ):
            cls = getattr(sbd, name, None)
            if cls is not None:
                cls.split_sentences = _split
                if hasattr(cls, "lazy_detector"):
                    cls.lazy_detector = lambda self: None  # type: ignore
                if hasattr(cls, "lazy_pipeline"):
                    cls.lazy_pipeline = lambda self: None  # type: ignore
        _sbd_patched = True
    except Exception:
        pass


def setup_offline_env() -> None:
    """把 Argos 数据目录指到绿色包内，并强制离线分句（避免 Stanza 联网下载）。"""
    os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
    os.environ.setdefault("ARGOS_STANZA_AVAILABLE", "0")
    # 修复：任何残留联网请求尽快失败，避免界面一直转圈
    try:
        socket.setdefaulttimeout(5)
    except Exception:
        pass

    root = models_dir()
    installed = root / "argos_installed"
    downloads = root / "argos_cache"
    installed.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(parents=True, exist_ok=True)
    try:
        import argostranslate.settings as settings

        settings.package_data_dir = installed
        settings.package_dirs = [installed]
        settings.downloads_dir = downloads
        if hasattr(settings, "data_dir"):
            settings.data_dir = root / "argos_data"
            settings.data_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(settings, "ChunkType"):
            settings.chunk_type = settings.ChunkType.MINISBD
        settings.stanza_available = False
        _patch_offline_sbd()
    except Exception:
        pass


def _already_installed(installed_dir: Path) -> bool:
    """已有 en↔zh 安装目录则跳过解压，避免每次卡住。"""
    if not installed_dir.is_dir():
        return False
    names = {p.name for p in installed_dir.iterdir() if p.is_dir()}
    has_en_zh = any(n.startswith("translate-en_zh") for n in names)
    has_zh_en = any(n.startswith("translate-zh_en") for n in names)
    return has_en_zh and has_zh_en


def _install_from_argos_models(argos_pkg) -> int:
    """从 .argosmodel 安装到 argos_installed，返回成功安装尝试次数。"""
    import argostranslate.package as package

    count = 0
    if not argos_pkg.exists():
        return 0
    for f in sorted(argos_pkg.glob("*.argosmodel")):
        try:
            package.install_from_path(str(f))
            count += 1
        except Exception:
            count += 1
    return count


def ensure_offline_packages(progress=None) -> Tuple[bool, str]:
    """检查离线包；若只有 .argosmodel 则自动安装到本机目录。"""
    global _argos_ready, _argos_error
    if _argos_ready:
        return True, "离线翻译就绪"

    if progress:
        progress("正在初始化离线翻译环境...")
    setup_offline_env()
    try:
        if progress:
            progress("正在加载离线翻译引擎（首次稍慢）...")
        import argostranslate.translate as translate

        root = models_dir()
        argos_pkg = root / "argos"
        installed_dir = root / "argos_installed"

        if not any(argos_pkg.glob("*.argosmodel")) and not any(installed_dir.glob("*")):
            if progress:
                progress("正在查找并复制离线模型...")
            _try_bootstrap_models_next_to_exe()
            root = models_dir()
            argos_pkg = root / "argos"
            installed_dir = root / "argos_installed"
            setup_offline_env()

        # 关键：已安装则不再解压 .argosmodel（解压两包约 150MB，易造成假死）
        if not _already_installed(installed_dir):
            if progress:
                progress("正在安装离线语言模型（仅首次）...")
            _install_from_argos_models(argos_pkg)
        elif progress:
            progress("离线语言模型已就绪，跳过安装")

        installed = translate.get_installed_languages()
        codes = {lang.code for lang in installed}
        has_en = "en" in codes
        has_zh = "zh" in codes or any(c.startswith("zh") for c in codes)
        if has_en and has_zh:
            _argos_ready = True
            return True, "离线翻译就绪（Argos en-zh）"

        if is_frozen():
            tip = (
                "缺少离线翻译模型。\n"
                f"请把完整 models 文件夹复制到：\n{app_root()}\n"
                "即与 ShotPortable.exe 同级，目录结构：\n"
                "  ShotPortable.exe\n"
                "  models\\argos\\*.argosmodel\n"
                "  models\\argos_installed\\...\n"
                "开发机可先运行：python scripts\\download_models.py"
            )
        else:
            tip = (
                "缺少离线翻译模型。请运行：\n"
                "  .\\.venv\\Scripts\\python.exe scripts\\download_models.py\n"
                f"模型目录：{argos_pkg}"
            )
        _argos_error = tip
        return False, _argos_error
    except Exception as ex:
        _argos_error = f"离线翻译初始化失败: {ex}"
        return False, _argos_error


def _try_bootstrap_models_next_to_exe() -> None:
    """打包运行时：若 exe 旁无模型，尝试从已知源目录复制。"""
    dest = app_root() / "models"
    if (dest / "argos").exists() and any((dest / "argos").glob("*.argosmodel")):
        return

    candidates = [
        Path(__file__).resolve().parent.parent / "models",
        app_root().parent / "ShotPortable" / "models",
        Path(r"D:\Test\ShotPortable\models"),
    ]
    for src in candidates:
        if not src.is_dir():
            continue
        has_model = any(src.joinpath("argos").glob("*.argosmodel")) if (src / "argos").exists() else False
        has_installed = (src / "argos_installed").is_dir() and any((src / "argos_installed").iterdir())
        if not (has_model or has_installed):
            continue
        try:
            if dest.exists():
                for name in ("argos", "argos_installed"):
                    s = src / name
                    d = dest / name
                    if s.exists():
                        if d.exists():
                            shutil.rmtree(d, ignore_errors=True)
                        shutil.copytree(s, d)
            else:
                shutil.copytree(src, dest)
            return
        except Exception:
            continue


def detect_lang(text: str) -> str:
    if not text or not text.strip():
        return "en"
    han = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in text if ("a" <= ch.lower() <= "z"))
    return "zh" if han >= latin else "en"


def _get_cached_translation(src: str, dst: str):
    """获取并缓存双向 Translation 对象。"""
    key = (src, dst)
    if key in _translation_cache:
        return _translation_cache[key]

    import argostranslate.translate as translate

    installed = translate.get_installed_languages()
    from_lang = next((l for l in installed if l.code == src or l.code.startswith(src)), None)
    to_lang = next((l for l in installed if l.code == dst or l.code.startswith(dst)), None)
    if from_lang is None or to_lang is None:
        raise RuntimeError(f"未找到离线语言包：{src} → {dst}")
    translation = from_lang.get_translation(to_lang)
    if translation is None:
        raise RuntimeError(f"未找到离线翻译链路：{src} → {dst}")
    _translation_cache[key] = translation
    return translation


def _offline_translate(text: str, src: str, dst: str) -> str:
    ok, msg = ensure_offline_packages()
    if not ok:
        raise RuntimeError(msg)
    setup_offline_env()

    src = "zh" if src.startswith("zh") else src
    dst = "zh" if dst.startswith("zh") else dst
    translation = _get_cached_translation(src, dst)
    return translation.translate(text)


def preload_offline_models(progress=None) -> Tuple[bool, str]:
    """
    启动时预加载离线翻译模型（英↔中）。
    首次会稍慢；完成后对照翻译可直接用。
    """
    global _model_loaded, _model_loading, _model_status, _model_error

    with _preload_lock:
        if _model_loaded:
            return True, "离线翻译模型已就绪"

        _model_loading = True
        _model_error = None

        def p(msg: str) -> None:
            global _model_status
            _model_status = msg
            if progress:
                progress(msg)

        try:
            p("正在加载离线翻译模型…")
            ok, msg = ensure_offline_packages(progress=p)
            if not ok:
                _model_error = msg
                _model_status = "离线翻译模型加载失败"
                return False, msg

            # 强制创建 CTranslate2 Translator（真正耗时点）
            p("正在加载英→中模型…")
            en_zh = _get_cached_translation("en", "zh")
            _ = en_zh.translate("Hello")

            p("正在加载中→英模型…")
            zh_en = _get_cached_translation("zh", "en")
            _ = zh_en.translate("你好")

            _model_loaded = True
            _model_status = "离线翻译模型已就绪，可以使用对照翻译"
            p(_model_status)
            return True, _model_status
        except Exception as ex:
            _model_error = str(ex)
            _model_status = f"离线翻译模型加载失败：{ex}"
            p(_model_status)
            return False, _model_status
        finally:
            _model_loading = False


def _online_translate(text: str, src: str, dst: str) -> str:
    from deep_translator import GoogleTranslator

    source = "zh-CN" if src == "zh" else "en"
    target = "zh-CN" if dst == "zh" else "en"
    return GoogleTranslator(source=source, target=target).translate(text)


def translate_contrast(
    lines: Iterable[str],
    use_online: bool = False,
    progress=None,
) -> List[ContrastLine]:
    items = [l.strip() for l in lines if l and l.strip()]
    out: List[ContrastLine] = []
    mode = "联网" if use_online else "离线本机"
    if progress:
        progress(f"翻译通道：{mode}")

    if not use_online:
        # 未预热时先明确提示「加载模型」，避免误以为卡在 1/N
        if not _model_loaded:
            if progress:
                progress("正在加载离线翻译模型（首次较慢，请稍候）…")
            ok, msg = preload_offline_models(progress=progress)
            if not ok:
                return [ContrastLine(x, f"[翻译失败: {msg}]", detect_lang(x), "en") for x in items]
        elif progress:
            progress("离线翻译模型已就绪，开始逐行翻译…")

    for i, line in enumerate(items, 1):
        if progress:
            progress(f"正在翻译 {i}/{len(items)}（{mode}）…")
        src = detect_lang(line)
        dst = "en" if src == "zh" else "zh"
        try:
            if use_online:
                tr = _online_translate(line, src, dst)
            else:
                tr = _offline_translate(line, src, dst)
        except Exception as ex:
            tr = f"[翻译失败: {ex}]"
        out.append(ContrastLine(line, tr.strip(), src, dst))
    return out


def format_contrast(lines: List[ContrastLine]) -> str:
    parts = []
    for x in lines:
        parts.append(x.source)
        parts.append(x.translation)
        parts.append("")
    return "\n".join(parts).strip()
