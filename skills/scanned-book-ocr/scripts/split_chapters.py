#!/usr/bin/env python3
"""把页锚点 Markdown 切成章文件，并分出目录、前置与后置辅文。

用法：
    python3 split_chapters.py --md book.md --out-dir chapters
    python3 split_chapters.py --md book.md --out-dir chapters --titles titles.json --back-markers 术语表,索引

titles.json 形如 {"23": "一国收入的衡量", "24": "生活费用的衡量"}。不给则用 OCR 识别到的章标题。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CHAPTER = re.compile(r"^#{1,3}\s*第\s*(\d+)\s*章\s*(.*)$", re.M)
BACK = re.compile(r"^#{1,3}\s*(术语表|索引|译后记|附录|参考文献)")


def pages_of(md):
    out = {}
    for part in re.split(r"(?=<!-- PDF p\.\d+ -->)", md):
        m = re.match(r"<!-- PDF p\.(\d+) -->", part)
        if m:
            out[int(m.group(1))] = part
    return out


def toc_end(pages):
    """目录页：章节号引用密集且没有长段落。"""
    hits = [n for n in pages if n <= 40
            and len(re.findall(r"\d+\.\d+", pages[n])) >= 10
            and sum(1 for line in pages[n].split("\n") if len(line) > 150) == 0]
    return max(hits) if hits else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--titles", help='JSON: {"23": "一国收入的衡量"}')
    ap.add_argument("--back-markers", default="术语表,索引,译后记,附录,参考文献")
    ap.add_argument("--report", help="chapters.json 输出路径")
    args = ap.parse_args()

    md = Path(args.md).read_text()
    pages = pages_of(md)
    nums = sorted(pages)
    cutoff = toc_end(pages)
    titles = json.loads(Path(args.titles).read_text()) if args.titles else {}

    starts = []
    last = 0
    for n in nums:
        if n <= cutoff:
            continue
        head = pages[n][:600]
        m = CHAPTER.search(head)
        if not m:
            continue
        ch = int(m.group(1))
        if titles and str(ch) not in {str(k) for k in titles}:
            continue
        if ch <= last:
            continue
        starts.append((n, ch, m.group(2).strip()))
        last = ch

    markers = [x.strip() for x in args.back_markers.split(",") if x.strip()]
    back_start = None
    if starts:
        for n in nums:
            if n <= starts[-1][0]:
                continue
            if any(BACK.match(line) for line in pages[n].split("\n")):
                back_start = n
                break

    out = Path(args.out_dir)
    (out / "chapters").mkdir(parents=True, exist_ok=True)
    meta = {"toc_end": cutoff, "pdf_pages": max(nums), "back_start": back_start, "chapters": []}

    first = starts[0][0] if starts else max(nums)
    (out / "front-matter.md").write_text("".join(pages[p] for p in range(1, first) if p in pages))
    (out / "toc.md").write_text("".join(pages[p] for p in range(1, cutoff + 1) if p in pages))
    back = back_start or (starts[-1][0] if starts else max(nums))
    (out / "back-matter.md").write_text(
        "".join(pages[p] for p in range(back, max(nums) + 1) if p in pages))

    for i, (n, ch, ocr_title) in enumerate(starts):
        end = (starts[i + 1][0] - 1) if i + 1 < len(starts) else ((back_start or max(nums) + 1) - 1)
        title = titles.get(str(ch), ocr_title) or ocr_title
        body = "".join(pages[p] for p in range(n, end + 1) if p in pages)
        body = re.sub(r"^#+\s*第\s*" + str(ch) + r"\s*章[^\n]*\n?", "", body, count=1, flags=re.M).lstrip()
        name = f"ch{ch:02d}-{title.replace('/', '-').replace('：', '-')}.md"
        (out / "chapters" / name).write_text(f"# 第{ch}章 {title}\n\n" + body)
        meta["chapters"].append({"chapter": ch, "title": title,
                                 "pdf_start": n, "pdf_end": end, "file": name})

    report = Path(args.report) if args.report else out / "chapters.json"
    report.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"chapters={len(meta['chapters'])} toc_end={cutoff} back_start={back_start} "
          f"pages={max(nums)} -> {report}")


if __name__ == "__main__":
    main()
