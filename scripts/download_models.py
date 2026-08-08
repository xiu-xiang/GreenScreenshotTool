"""下载并安装离线 Argos 中英模型到 models/（随绿色包分发）。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ARGOS_RAW = ROOT / "models" / "argos"
ARGOS_INSTALLED = ROOT / "models" / "argos_installed"
ARGOS_RAW.mkdir(parents=True, exist_ok=True)
ARGOS_INSTALLED.mkdir(parents=True, exist_ok=True)


def main():
    print("配置 Argos 安装目录为绿色包 models/argos_installed ...")
    import argostranslate.settings as settings
    import argostranslate.package as package
    import argostranslate.translate as translate

    settings.package_data_dir = ARGOS_INSTALLED
    settings.package_dirs = [ARGOS_INSTALLED]
    settings.downloads_dir = ROOT / "models" / "argos_cache"
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)

    print("更新包索引...")
    package.update_package_index()
    available = package.get_available_packages()
    wanted = {("en", "zh"), ("zh", "en")}
    found = [p for p in available if (p.from_code, p.to_code) in wanted]
    if len(found) < 2:
        print("索引中未找到完整 en<->zh，相关包：")
        for p in available:
            if "zh" in (p.from_code, p.to_code) or "en" in (p.from_code, p.to_code):
                print(f"  {p.from_code}->{p.to_code}")
        raise SystemExit(1)

    for pkg in found:
        print(f"下载 {pkg.from_code}->{pkg.to_code} ...")
        path = Path(pkg.download())
        dest = ARGOS_RAW / path.name
        shutil.copy2(path, dest)
        print(f"  原始包: {dest} ({dest.stat().st_size // 1024} KB)")
        print("  安装到 models/argos_installed ...")
        package.install_from_path(str(dest))

    langs = translate.get_installed_languages()
    print("已安装语言:", [f"{l.code}:{l.name}" for l in langs])
    # 冒烟
    sample = translate.translate("Hello world", "en", "zh")
    print("冒烟翻译 Hello world ->", sample)
    print("完成。发布时请把整个 models 目录一并打包。")


if __name__ == "__main__":
    main()
