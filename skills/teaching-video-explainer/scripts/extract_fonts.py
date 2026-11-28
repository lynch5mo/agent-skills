#!/usr/bin/env python3
"""从 macOS 系统 ttc 里提取字形，转成 woff2 放进工程。

HyperFrames 的 lint 只认 @font-face / Google Fonts / 内置别名表，
直接写系统字体名会报 font_family_without_font_face。
所以必须把字形文件带进工程，用 url() 引用。

用法:
    python extract_fonts.py --out assets/fonts
    python extract_fonts.py --out assets/fonts --preset minimal
    python extract_fonts.py --list          # 看系统里有哪些

依赖 fonttools 与 brotli：
    uv run --with fonttools --with brotli python extract_fonts.py ...
"""
from __future__ import annotations

import argparse
import pathlib
import sys

# 预设：教学视频只需要两套字体，四档字重
PRESETS = {
    "minimal": [
        ("/System/Library/Fonts/Supplemental/Songti.ttc", 6, "SongtiSC-Regular"),
        ("/System/Library/Fonts/Supplemental/Songti.ttc", 1, "SongtiSC-Bold"),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0, "HiraginoSansGB-W3"),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2, "HiraginoSansGB-W6"),
    ],
}

# 生成的 CSS 片段，贴进 <head>
CSS_TEMPLATE = """@font-face{{font-family:"Song";src:url("assets/fonts/SongtiSC-Regular.woff2") format("woff2");font-weight:400;font-display:block}}
@font-face{{font-family:"Song";src:url("assets/fonts/SongtiSC-Bold.woff2") format("woff2");font-weight:700;font-display:block}}
@font-face{{font-family:"Hei";src:url("assets/fonts/HiraginoSansGB-W3.woff2") format("woff2");font-weight:400;font-display:block}}
@font-face{{font-family:"Hei";src:url("assets/fonts/HiraginoSansGB-W6.woff2") format("woff2");font-weight:700;font-display:block}}"""


def list_faces() -> None:
    from fontTools.ttLib import TTCollection

    for path in ("/System/Library/Fonts/Supplemental/Songti.ttc",
                 "/System/Library/Fonts/Hiragino Sans GB.ttc",
                 "/System/Library/Fonts/STHeiti Medium.ttc"):
        p = pathlib.Path(path)
        if not p.exists():
            continue
        coll = TTCollection(str(p), lazy=True)
        print(f"\n{path}  ({len(coll.fonts)} faces)")
        for i, f in enumerate(coll.fonts):
            names = {n.nameID: n.toUnicode() for n in f["name"].names if n.nameID in (2, 4, 6)}
            print(f"  [{i}] {names.get(4)}  |  {names.get(6)}  |  {names.get(2)}")


def extract(preset: str, out_dir: pathlib.Path) -> None:
    from fontTools.ttLib import TTCollection

    out_dir.mkdir(parents=True, exist_ok=True)
    for src, idx, name in PRESETS[preset]:
        path = pathlib.Path(src)
        if not path.exists():
            sys.exit(f"找不到字体文件：{src}")
        coll = TTCollection(str(path), lazy=False)
        font = coll.fonts[idx]
        font.flavor = "woff2"
        dst = out_dir / f"{name}.woff2"
        font.save(str(dst))
        print(f"{name:22s} {dst.stat().st_size // 1024:>6d} KB")

    print("\n把下面这段贴进 <head>：\n")
    print(CSS_TEMPLATE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="assets/fonts")
    ap.add_argument("--preset", default="minimal", choices=sorted(PRESETS))
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        list_faces()
    else:
        extract(args.preset, pathlib.Path(args.out))


if __name__ == "__main__":
    main()
