"""翻译服务：默认离线 Argos（本机模型）；可选联网 deep-translator。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from app.paths import models_dir


@dataclass
class ContrastLine:
    source: str
    translation: str
    source_lang: str
    target_lang: str


_argos_ready = False
_argos_error: Optional[str] = None


def setup_offline_env() -> None:
    """把 Argos 数据目录指到绿色包内，实现免安装离线运行。"""
    installed = models_dir() / "argos_installed"
    downloads = models_dir() / "argos_cache"
    installed.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(parents=True, exist_ok=True)
    try:
        import argostranslate.settings as settings

        settings.package_data_dir = installed
        settings.package_dirs = [installed]
        settings.downloads_dir = downloads
        # 部分版本还会读 data_dir
        if hasattr(settings, "data_dir"):
            settings.data_dir = models_dir() / "argos_data"
            settings.data_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def ensure_offline_packages() -> Tuple[bool, str]:
    """检查离线包；若只有 .argosmodel 则自动安装到本机目录。"""
    global _argos_ready, _argos_error
    if _argos_ready:
        return True, "离线翻译就绪"
    setup_offline_env()
    try:
        import argostranslate.package as package
        import argostranslate.translate as translate

        # 从随包 .argosmodel 安装（绿色发布必备）
        argos_pkg = models_dir() / "argos"
        if argos_pkg.exists():
            for f in sorted(argos_pkg.glob("*.argosmodel")):
                try:
                    package.install_from_path(str(f))
                except Exception:
                    pass

        installed = translate.get_installed_languages()
        codes = {lang.code for lang in installed}
        # 中文可能是 zh
        has_en = "en" in codes
        has_zh = "zh" in codes or any(c.startswith("zh") for c in codes)
        if has_en and has_zh:
            _argos_ready = True
            return True, "离线翻译就绪（Argos en-zh）"
        _argos_error = (
            "缺少离线翻译模型。请运行：\n"
            "  .\\.venv\\Scripts\\python.exe scripts\\download_models.py\n"
            f"模型目录：{argos_pkg}"
        )
        return False, _argos_error
    except Exception as ex:
        _argos_error = f"离线翻译初始化失败: {ex}"
        return False, _argos_error


def detect_lang(text: str) -> str:
    if not text or not text.strip():
        return "en"
    han = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in text if ("a" <= ch.lower() <= "z"))
    return "zh" if han >= latin else "en"


def _offline_translate(text: str, src: str, dst: str) -> str:
    ok, msg = ensure_offline_packages()
    if not ok:
        raise RuntimeError(msg)
    import argostranslate.translate as translate

    # Argos 中文代码一般为 zh
    src = "zh" if src.startswith("zh") else src
    dst = "zh" if dst.startswith("zh") else dst
    return translate.translate(text, src, dst)


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
    for i, line in enumerate(items, 1):
        if progress:
            progress(f"正在翻译 {i}/{len(items)}（{mode}）...")
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


def _mostly_non_lang(text: str) -> bool:
    letters = len(re.findall(r"[A-Za-z\u4e00-\u9fff]", text))
    return letters == 0 or (len(text) <= 3 and letters <= 1)
