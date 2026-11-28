#!/usr/bin/env python3
"""MinerU middle_json -> 页锚点 Markdown，含配图取舍、题注归属与页眉页脚修正。

用法：
    python3 mineru_render.py --zip book.zip --out book.md --figures-dir figs
    python3 mineru_render.py --middle-json middle.json --mapping figs/mapping.json --out book.md

设计要点见 skill 正文第五节、第六节。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

SKIP_TYPES = {"page_number"}
FIGTAG = re.compile(r"^图\s*(\d+)\s*[-–—]?\s*(\d+)?\s*(.*)$")
MENTION = re.compile(r"图\s*(\d+)\s*[-–—]\s*(\d+)")
PUNCT = re.compile(r"[。，；：！？]")


def inline(parts):
    out = []
    for p in parts:
        if not isinstance(p, dict):
            out.append(str(p))
            continue
        t = p.get("type")
        if t == "text":
            c = p.get("content", "")
            out.append("".join(map(str, c)) if isinstance(c, list) else str(c))
        elif t == "equation_inline":
            out.append(f"${(p.get('content') or '').strip()}$")
        elif t == "image_inline":
            out.append("〔图〕")
        else:
            c = p.get("content", "")
            out.append("".join(map(str, c)) if isinstance(c, list) else str(c))
    return "".join(out).strip()


def block_text(b):
    return inline(b.get("content", []))


def child_caption(b, kinds):
    for c in b.get("content", []):
        if isinstance(c, dict) and c.get("type") in kinds:
            return inline(c.get("content", []))
    return ""


def figure_meta(b):
    path = ""
    for c in b.get("content", []):
        if isinstance(c, dict) and c.get("image_path"):
            path = c["image_path"]
            break
    bb = b.get("bbox") or [0, 0, 0, 0]
    return path, bb, (bb[2] - bb[0]) * (bb[3] - bb[1])


def line_art(path):
    """白底线条图：白像素高、中间调少、墨量不为零。用于兜住图号印在图内的图表。"""
    try:
        a = np.asarray(Image.open(path).convert("L"), dtype=np.uint8)
    except Exception:
        return False
    if a.size == 0:
        return False
    white = float((a >= 235).mean())
    mid = float(((a > 80) & (a < 235)).mean())
    dark = float((a <= 80).mean())
    return white >= 0.72 and mid <= 0.25 and dark >= 0.015


def caption_candidates(blocks):
    """页内「图N-M 标题」块；合并被拆成「图2-1」+「循环流量图」的两块。"""
    caps, merge_next = {}, {}
    for i, b in enumerate(blocks):
        t = block_text(b).strip()
        m = FIGTAG.match(t)
        if not m or len(t) > 40 or t.endswith("。"):
            continue
        cap, nxt = t, None
        if len(re.sub(r"\s", "", t)) <= 6 and i + 1 < len(blocks):
            following = block_text(blocks[i + 1]).strip()
            if following and len(following) <= 24 and not PUNCT.search(following):
                num = m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
                cap, nxt = f"图{num} {following}", i + 1
        caps[i] = cap
        if nxt is not None:
            merge_next[i] = nxt
    return caps, merge_next


def pick_caption(blocks, caps, idx):
    b = blocks[idx]
    y0, y1, x0, x1 = b["bbox"][1], b["bbox"][3], b["bbox"][0], b["bbox"][2]
    best, bestd = None, 0.13
    for j, cap in caps.items():
        if j == idx:
            continue
        bb = blocks[j]["bbox"]
        if min(bb[2], x1) - max(bb[0], x0) <= 0:
            continue
        d = min(abs(bb[3] - y0), abs(bb[1] - y1))
        if d < bestd:
            best, bestd = (j, cap, bb[1] < y0), d
    return best


def page_mentions(blocks):
    seen = []
    for b in blocks:
        bb = b.get("bbox") or [0, 0, 0, 0]
        for m in MENTION.finditer(block_text(b)):
            key = f"图{m.group(1)}-{m.group(2)}"
            if all(k != key for k, _a, _b in seen):
                seen.append((key, bb[1], bb[3]))
    return seen


def build_mapping(mid, zip_path, figures_dir):
    """给每个图块起名字并导出裁图。返回 {image_path: [name, page, bbox]}。"""
    mapping = {}
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(zip_path) if zip_path else None
    for pg in mid["pages"]:
        page = pg["page_idx"] + 1
        seq = 0
        for b in pg.get("blocks") or []:
            if b["type"] not in ("image", "chart"):
                continue
            seq += 1
            path, bb, _area = figure_meta(b)
            if not path:
                continue
            name = f"p{page:03d}-{b['type']}{seq}.jpg"
            mapping[path] = [name, page, [round(v, 4) for v in bb]]
            target = figures_dir / name
            if zf and not target.exists():
                try:
                    target.write_bytes(zf.read(path))
                except KeyError:
                    pass
    return mapping


def render(mid, mapping, figures_dir, drop, out_md):
    buf, kept, dropped, review = [], 0, 0, []
    for pg in mid["pages"]:
        n = pg["page_idx"] + 1
        blocks = pg.get("blocks") or []
        caps, merge_next = caption_candidates(blocks)
        consumed = set()
        mentions = page_mentions(blocks)
        captioned = []
        for cap in caps.values():
            m = MENTION.match(cap)
            if m:
                captioned.append(f"图{m.group(1)}-{m.group(2)}")
        unmatched = [(k, a, b) for k, a, b in mentions if k not in captioned]
        buf.append(f"\n<!-- PDF p.{n} -->\n")
        for idx, b in enumerate(blocks):
            if idx in consumed or b["type"] in SKIP_TYPES:
                continue
            if b["type"] in ("header", "footer"):
                t = block_text(b)
                if not t or (len(t) <= 40 and not PUNCT.search(t)):
                    continue
                buf.append(t + "\n\n")
                continue

            if b["type"] in ("image", "chart"):
                path, bb, area = figure_meta(b)
                name = (mapping.get(path) or [None])[0]
                if not name or name in drop:
                    dropped += 1
                    continue
                cap = child_caption(b, {"image_caption", "chart_caption"})
                if cap and not FIGTAG.match(cap.strip()):
                    cap = ""
                foot = child_caption(b, {"image_footnote", "chart_footnote"})
                cap_above = True
                if not cap:
                    near = pick_caption(blocks, caps, idx)
                    if near:
                        j, cap, cap_above = near
                        consumed.add(j)
                        if j in merge_next:
                            consumed.add(merge_next[j])
                label = cap if cap else ""
                if label and foot:
                    label = f"{label}；{foot}"
                numbered = bool(FIGTAG.match(label.strip()))
                crop = Path(figures_dir) / name
                art = crop.exists() and line_art(crop)
                if not numbered and art and area >= 0.01:
                    for k, my0, my1 in list(unmatched):
                        if min(abs(my0 - b["bbox"][3]), abs(my1 - b["bbox"][1])) <= 0.08:
                            label, numbered = k, True
                            unmatched.remove((k, my0, my1))
                            break
                if area < 0.008:        # 只有图号标签的细条，不是图
                    dropped += 1
                    continue
                essential = numbered or b["type"] == "chart" or (art and area >= 0.01)
                if not essential or (not label and area < 0.01 and not art):
                    dropped += 1
                    continue
                kept += 1
                if not label:
                    review.append({"name": name, "page": n})
                flags = ("C" if cap_above else "-") + ("N" if numbered else "-")
                buf.append(f"@@FIG:{name}@{label}@{flags}@@\n\n")
                continue

            if b["type"] == "table":
                cap = child_caption(b, {"table_caption"})
                foot = child_caption(b, {"table_footnote"})
                body = ""
                for c in b.get("content", []):
                    if isinstance(c, dict) and c.get("type") == "table_body":
                        body = (c.get("content") or "").strip()
                txt = "\n\n".join(x for x in (cap, body, foot) if x)
            elif b["type"] == "equation":
                txt = "$$\n" + (b.get("content") or "").strip() + "\n$$"
            elif b["type"] == "doc_title":
                txt = "# " + block_text(b)
            elif b["type"] == "paragraph_title":
                lvl = min(int(b.get("level") or 2), 4)
                txt = "#" * max(lvl, 2) + " " + block_text(b)
            elif b["type"] == "aside_text":
                t = block_text(b)
                txt = "" if not t or re.fullmatch(r"[\d\s]{1,6}", t) else f"> 旁注：{t}"
            else:
                txt = block_text(b)

            if not txt or re.fullmatch(r"\d{1,4}", txt.strip()):
                continue
            buf.append(txt + "\n\n")

    Path(out_md).write_text("".join(buf))
    return kept, dropped, review


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", help="mineru-kit parse --format zip 产物")
    ap.add_argument("--middle-json", help="已解包的 middle_json.json")
    ap.add_argument("--mapping", help="图块映射 JSON；不存在则按 --zip 自动生成")
    ap.add_argument("--figures-dir", default="figures", help="裁图输出目录")
    ap.add_argument("--out", required=True, help="输出 Markdown")
    ap.add_argument("--drop", help="人工确认要剔除的图名清单（每行一个）")
    ap.add_argument("--report", help="图块清单 JSON 输出路径")
    args = ap.parse_args()

    if args.middle_json:
        mid = json.loads(Path(args.middle_json).read_text())
    elif args.zip:
        mid = json.loads(zipfile.ZipFile(args.zip).read("middle_json.json"))
    else:
        sys.exit("需要 --zip 或 --middle-json")

    mapping_path = Path(args.mapping) if args.mapping else Path(args.figures_dir) / "mapping.json"
    if mapping_path.exists():
        mapping = json.loads(mapping_path.read_text())
    else:
        mapping = build_mapping(mid, args.zip, args.figures_dir)
        mapping_path.parent.mkdir(parents=True, exist_ok=True)
        mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=1))

    drop = set()
    if args.drop:
        drop = {line.strip() for line in Path(args.drop).read_text().splitlines() if line.strip()}

    kept, dropped, review = render(mid, mapping, args.figures_dir, drop, args.out)
    print(f"pages={len(mid['pages'])} kept={kept} dropped={dropped} needs_review={len(review)}")
    if args.report:
        Path(args.report).write_text(json.dumps(
            {"kept": kept, "dropped": dropped, "needs_review": review}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
