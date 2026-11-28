#!/usr/bin/env python3
"""给没有文本题注的图补裁标题行：向上扩到印刷标题，向下扩到 (a)/(b) 子标题。

用法：
    python3 recrop_figures.py --pdf book.pdf --zip book.zip --md book.md \
        --mapping figures/mapping.json --out-dir figures-recrop [--limit 5]

只处理 Markdown 里没有「图N-M」题注的图；有题注的图按 --pad-top 小幅留白。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

FIGRE = re.compile(r"图\s*\d+\s*[-–—]\s*\d+")
TEXTY = ("text", "paragraph_title", "aside_text", "doc_title", "header", "table")


def placed_figures(md_path):
    md = Path(md_path).read_text()
    return {n: l for n, l in re.findall(r"@@FIG:([^@]+)@([^@]*)@[CF][N-]@@", md)}


def render_pages(pdf, pages, cache, dpi):
    cache.mkdir(parents=True, exist_ok=True)
    todo = [p for p in sorted(pages) if not (cache / f"p{p:03d}.png").exists()]
    ranges = []
    for p in todo:
        if ranges and p == ranges[-1][1] + 1:
            ranges[-1][1] = p
        else:
            ranges.append([p, p])
    for a, b in ranges:
        subprocess.run(["pdftoppm", "-f", str(a), "-l", str(b), "-r", str(dpi), "-gray", "-png",
                        pdf, str(cache / "x")], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for f in cache.glob("x-*.png"):
        target = cache / f"p{f.stem.split('-')[-1]}.png"
        if not target.exists():
            f.rename(target)
    return cache


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--zip", required=True, help="提供版面块，用于避开上方文字块")
    ap.add_argument("--md", required=True, help="渲染后的 Markdown，含 @@FIG: 占位符")
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 张，便于试跑")
    ap.add_argument("--cache", default="/tmp/scanned-book-ocr/pages")
    ap.add_argument("--pad-top", type=float, default=0.004)
    args = ap.parse_args()

    placed = placed_figures(args.md)
    mapping = json.loads(Path(args.mapping).read_text())
    by_name = {v[0]: (v[1], v[2]) for v in mapping.values()}
    need = [n for n in placed if not FIGRE.match((placed[n] or "").strip())]
    if args.limit:
        need = need[: args.limit]
    if not need:
        print("no caption-less figures")
        return

    mid = json.loads(zipfile.ZipFile(args.zip).read("middle_json.json"))
    blocks = {p["page_idx"] + 1: p.get("blocks") or [] for p in mid["pages"]}
    cache = render_pages(args.pdf, sorted({by_name[n][0] for n in need}), Path(args.cache), args.dpi)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def work(name):
        page, bbox = by_name[name]
        img = cache / f"p{page:03d}.png"
        if not img.exists():
            return None
        im = Image.open(img).convert("L")
        w, h = im.size
        x0, y0, x1, y1 = bbox
        top = max(0.0, y0 - (0.045 if name in need else args.pad_top))
        for b in blocks.get(page, []):
            if b["type"] not in TEXTY:
                continue
            bb = b["bbox"]
            if bb[3] <= y0 + 0.002 and bb[3] > top:
                top = max(bb[3] + 0.004, y0 - 0.045)
        bottom = min(1.0, y1 + 0.03)
        for b in blocks.get(page, []):
            if b["type"] not in TEXTY:
                continue
            bb = b["bbox"]
            if bb[1] >= y1 - 0.002 and bb[1] < bottom:
                bottom = max(y1 + 0.004, bb[1] - 0.004)
        box = (int(max(0, x0 - 0.006) * w), int(top * h),
               int(min(1, x1 + 0.006) * w), int(min(1, bottom) * h))
        im.crop(box).save(out / name, quality=90)
        return name

    done = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(work, need):
            done += 1 if r else 0
    print(f"recropped={done} of {len(need)} -> {out}")


if __name__ == "__main__":
    main()
