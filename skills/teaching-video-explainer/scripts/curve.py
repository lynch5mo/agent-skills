#!/usr/bin/env python3
"""曲线工具：单调三次插值（PCHIP）→ 贝塞尔，附带切线与等分采样。

为什么不用 Catmull-Rom：它会过冲，斜率不单调，画「越往右越陡」这类曲线时
会在数据点附近出现反弯。PCHIP 保证单调、无过冲，正合适画边界、成本曲线、
收益递减这类形状。

用法：
    from curve import pchip_path, pchip_sample, tangent, polyline

    pts = [(700,390), (1360,542), (1470,580), (1800,960)]   # 屏幕坐标
    d = pchip_path(pts)                    # 直接塞进 <path d="...">
    x, y, dx, dy = pchip_sample(pts, 1, 0.5)   # 第 2 段中点及导数
    tips = tangent(pts, 1, 0.5, half=150)      # 切线的六个坐标
"""
from __future__ import annotations

import math


def pchip_fit(pts):
    """返回 (xs, ys, slopes, spans)。slopes 是每点的 dy/dx。"""
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    n = len(xs)
    if n < 2:
        raise ValueError("至少需要两个点")
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    if any(v <= 0 for v in h):
        raise ValueError("x 必须严格递增，曲线不能回折")
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]

    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0                      # 极值点，斜率归零，避免过冲
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    return xs, ys, m, h


def pchip_path(pts) -> str:
    """生成 SVG path 的 d 属性。"""
    xs, ys, m, h = pchip_fit(pts)
    out = f"M {xs[0]:.1f} {ys[0]:.1f}"
    for i in range(len(xs) - 1):
        # 关键：x 方向偏移固定 h/3，只有 y 方向乘斜率。
        # 若写成 m*h/3 两边都乘，曲线会被压扁、切线方向全错。
        c1 = (xs[i] + h[i] / 3, ys[i] + m[i] * h[i] / 3)
        c2 = (xs[i + 1] - h[i] / 3, ys[i + 1] - m[i + 1] * h[i] / 3)
        out += f" C {c1[0]:.1f} {c1[1]:.1f}, {c2[0]:.1f} {c2[1]:.1f}, {xs[i + 1]:.1f} {ys[i + 1]:.1f}"
    return out


def pchip_sample(pts, seg: int, t: float):
    """第 seg 段（0 起）参数 t∈[0,1] 处的点与导数。"""
    xs, ys, m, h = pchip_fit(pts)
    if not 0 <= seg < len(xs) - 1:
        raise IndexError("seg 越界")
    x0, y0, x1, y1 = xs[seg], ys[seg], xs[seg + 1], ys[seg + 1]
    hh = h[seg]
    c1 = (x0 + hh / 3, y0 + m[seg] * hh / 3)
    c2 = (x1 - hh / 3, y1 - m[seg + 1] * hh / 3)
    u = 1 - t
    x = u**3 * x0 + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * x1
    y = u**3 * y0 + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * y1
    dx = 3 * u * u * (c1[0] - x0) + 6 * u * t * (c2[0] - c1[0]) + 3 * t * t * (x1 - c2[0])
    dy = 3 * u * u * (c1[1] - y0) + 6 * u * t * (c2[1] - c1[1]) + 3 * t * t * (y1 - c2[1])
    return x, y, dx, dy


def tangent(pts, seg: int, t: float, half: float = 140.0):
    """返回切线六元组 (x1,y1,x2,y2,cx,cy)，可直接喂给 <line>。"""
    x, y, dx, dy = pchip_sample(pts, seg, t)
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    return (round(x - ux * half, 1), round(y - uy * half, 1),
            round(x + ux * half, 1), round(y + uy * half, 1),
            round(x, 1), round(y, 1))


def polyline(pts, start=(0, 0.0), end=(1, 1.0), steps=12):
    """沿曲线等分取点，用于游标轨迹。

    start / end 是 (段号, 参数)。返回 [(x, y), ...]，
    直接写进 timeline 的 tl.set 序列，不要用 MotionPathPlugin。
    """
    out = []
    (s0, t0), (s1, t1) = start, end
    if s0 == s1:
        for i in range(steps + 1):
            x, y, _, _ = pchip_sample(pts, s0, t0 + (t1 - t0) * i / steps)
            out.append((round(x, 1), round(y, 1)))
        return out
    first = [pchip_sample(pts, s0, t0 + (1 - t0) * i / 6) for i in range(7)]
    out.extend((round(p[0], 1), round(p[1], 1)) for p in first)
    for seg in range(s0 + 1, s1):
        for i in range(1, 7):
            p = pchip_sample(pts, seg, i / 6)
            out.append((round(p[0], 1), round(p[1], 1)))
    for i in range(1, steps + 1):
        p = pchip_sample(pts, s1, t1 * i / steps)
        out.append((round(p[0], 1), round(p[1], 1)))
    return out


def path_length(pts, steps: int = 240) -> float:
    """近似弧长，供 stroke-dasharray 描线动画使用。"""
    L, prev = 0.0, None
    segs = len(pts) - 1
    for i in range(steps + 1):
        g = i / steps * segs
        si = min(int(g), segs - 1)
        x, y, _, _ = pchip_sample(pts, si, g - si)
        if prev:
            L += math.hypot(x - prev[0], y - prev[1])
        prev = (x, y)
    return L


if __name__ == "__main__":
    demo = [(700, 390), (1360, 542), (1470, 580), (1800, 960)]
    print("d =", pchip_path(demo))
    print("len =", round(path_length(demo)))
    for seg, tt in ((0, 0.5), (1, 0.5), (2, 0.5)):
        x, y, dx, dy = pchip_sample(demo, seg, tt)
        print(f"seg{seg} t={tt}  ({x:.0f},{y:.0f})  斜率 {dy / dx:.3f}")
