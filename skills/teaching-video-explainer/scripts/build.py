#!/usr/bin/env python3
"""把 config.json + timeline.json 填进 skeleton.html，生成可渲染的 index.html。

用法:
    python build.py --config config.json --timeline timeline.json \
                    --skeleton assets/skeleton.html --out ./index.html \
                    --audio-dir audio

config.json 最小示例见 assets/config.example.json。

设计约定：
  - 坐标系由 map.origin / map.kx / map.ky 决定，右上方为正
  - 曲线点用数据坐标给，脚本负责插值与映射
  - 文案按占位符名给，缺项留空而不是报错（便于先跑通再补）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from curve import pchip_path, pchip_sample, path_length, tangent  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--skeleton", default=str(
        pathlib.Path(__file__).resolve().parent.parent / "assets" / "skeleton.html.tpl"),
        help="默认用技能自带模板；不要把它复制到工程根目录，否则会被当成第二个 composition 入口")
    ap.add_argument("--out", default="index.html")
    ap.add_argument("--audio-dir", default="audio")
    args = ap.parse_args()

    cfg = json.loads(pathlib.Path(args.config).read_text(encoding="utf-8"))
    tl = json.loads(pathlib.Path(args.timeline).read_text(encoding="utf-8"))
    total = tl["total"]
    seg = tl["seg"]

    ox, oy = cfg["map"]["origin"]
    kx, ky = cfg["map"]["kx"], cfg["map"]["ky"]

    def P(x, y):
        return (round(ox + x * kx, 1), round(oy - y * ky, 1))

    # ── 曲线 ──
    pts = [P(*p) for p in cfg["curve_points"]]
    d = pchip_path(pts)
    length = round(path_length(pts))

    # ── 网格与刻度 ──
    grid = []
    for gx in cfg.get("grid_x", []):
        x = round(ox + gx * kx, 1)
        grid.append(f'<line x1="{x}" y1="200" x2="{x}" y2="960" class="grid"/>')
    for gy in cfg.get("grid_y", []):
        y = round(oy - gy * ky, 1)
        grid.append(f'<line x1="700" y1="{y}" x2="1824" y2="{y}" class="grid"/>')

    ticks = []
    for v in cfg.get("ticks_x", []):
        x = round(ox + v * kx, 1)
        ticks.append(f'<text x="{x}" y="986" class="tick">{v}</text>')
    for v in cfg.get("ticks_y", []):
        y = round(oy - v * ky, 1)
        ticks.append(f'<text x="{ox - 22}" y="{y + 8}" class="tick end">{v}</text>')
    ticks = "".join(ticks)

    # ── 关键点 ──
    pa = P(*cfg["points"]["A"])
    pb = P(*cfg["points"]["B"])

    # ── 游标轨迹与切线 ──
    (s0, t0), (s1, t1) = cfg["cursor_start"], cfg["cursor_end"]
    steps = cfg.get("cursor_steps", 12)
    path = []
    if s0 == s1:
        for i in range(steps + 1):
            x, y, _, _ = pchip_sample(pts, s0, t0 + (t1 - t0) * i / steps)
            path.append([round(x, 1), round(y, 1)])
    else:
        first = [pchip_sample(pts, s0, t0 + (1 - t0) * i / 6) for i in range(7)]
        path.extend([round(p[0], 1), round(p[1], 1)] for p in first)
        for sgi in range(s0 + 1, s1):
            for i in range(1, 7):
                p = pchip_sample(pts, sgi, i / 6)
                path.append([round(p[0], 1), round(p[1], 1)])
        for i in range(1, steps + 1):
            p = pchip_sample(pts, s1, t1 * i / steps)
            path.append([round(p[0], 1), round(p[1], 1)])

    tan_pts = tangent(pts, cfg.get("tan_at", [1, 0.5])[0], cfg.get("tan_at", [1, 0.5])[1],
                      cfg.get("tan_half", 140))

    # ── 读数数字带 ──
    rows_a = cfg.get("readout_rows_a") or cfg.get("readout_rows") or list(range(0, 101, 10))
    rows_b = cfg.get("readout_rows_b") or rows_a
    rows_a_html = "".join(f"<span>{v}</span>" for v in rows_a)
    rows_b_html = "".join(f"<span>{v}</span>" for v in rows_b)

    # ── 音频元素：必须直接挂在 root 下 ──
    audio = []
    for sid, (a, b) in seg.items():
        audio.append(
            f'<audio id="a-{sid}" src="{args.audio_dir}/{sid}.wav" '
            f'data-start="{a}" data-duration="{round(b - a, 2)}" data-track-index="9"></audio>')
    audio_html = "\n".join(audio)

    # ── 卡片窗口：给个安全默认值，避免与收口页重叠 ──
    card_t = cfg.get("card_start", seg["s4"][0] + 2.2)
    card_d = cfg.get("card_duration", max(2.0, seg["s4"][1] - card_t))
    w_t = round(seg["s5"][0] + 0.9, 2)
    w_d = round(total - w_t, 2)

    repl = {
        "__TOTAL__": f"{total:.2f}",
        "__GRID__": "".join(grid),
        "__TICKS__": ticks,
        "__CURVE__": d,
        "__LEN__": str(length),
        "__AXIS_X__": cfg.get("axis_x", ""),
        "__AXIS_Y__": cfg.get("axis_y", ""),
        "__KICKER__": cfg.get("kicker", ""),
        "__BADGE__": cfg.get("badge", ""),
        "__AX__": str(pa[0]), "__AY__": str(pa[1]),
        "__BX__": str(pb[0]), "__BY__": str(pb[1]),
        "__ROWS_A__": rows_a_html,
        "__ROWS_B__": rows_b_html,
        "__R1__": cfg.get("readout_labels", ["量 A", "量 B"])[0],
        "__R2__": cfg.get("readout_labels", ["量 A", "量 B"])[1],
        "__U1__": cfg.get("readout_units", ["", ""])[0],
        "__U2__": cfg.get("readout_units", ["", ""])[1],
        "__CARD_T__": f"{card_t:.2f}",
        "__CARD_D__": f"{card_d:.2f}",
        "__CARD_BODY__": cfg.get("card_body", ""),
        "__W_T__": f"{w_t:.2f}",
        "__W_D__": f"{w_d:.2f}",
        "__END_TITLE__": cfg.get("end_title", ""),
        "__AUDIO__": audio_html,
        "__TLJSON__": json.dumps({
            "total": total, "seg": seg, "path": path,
            "tan": list(tan_pts[:4]), "len": length,
        }, ensure_ascii=False),
    }
    for i, w in enumerate(cfg.get("words", [])[:5], start=1):
        repl[f"__W{i}__"] = w
    for i in range(len(cfg.get("words", [])), 5):
        repl[f"__W{i + 1}__"] = ""

    for key in ("hl1", "hl2", "hl3", "bd2", "dl3"):
        repl[f"__{key.upper()}__"] = cfg.get("texts", {}).get(key, "")

    html = pathlib.Path(args.skeleton).read_text(encoding="utf-8")
    for k, v in repl.items():
        html = html.replace(k, v)

    leftovers = [m for m in ("__TOTAL__", "__CURVE__", "__AUDIO__", "__TLJSON__") if m in html]
    if leftovers:
        sys.exit(f"占位符未替换干净：{leftovers}")

    pathlib.Path(args.out).write_text(html, encoding="utf-8")
    print(f"生成 {args.out}")
    print(f"  总长 {total:.2f}s  曲线弧长 {length}  游标 {len(path)} 点")
    if set(seg) - {"s1", "s2", "s3", "s4", "s5"}:
        print(f"  注意：骨架只认 s1–s5，时间轴里多出的段不会被排进动画："
              f"{sorted(set(seg) - {'s1','s2','s3','s4','s5'})}")


if __name__ == "__main__":
    main()
