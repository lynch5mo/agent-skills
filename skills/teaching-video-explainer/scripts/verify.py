#!/usr/bin/env python3
"""成片自检：规格、音轨、响度、解码完整性，并抽出关键帧供肉眼核对。

用法:
    python verify.py ../renders/out.mp4 --expect-duration 116
    python verify.py ../renders/out.mp4 --frames 5,30,60,90,113 --frame-dir /tmp/frames
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys


def ffprobe(path: pathlib.Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,channels,sample_rate",
         "-show_entries", "format=duration,size", "-of", "json", str(path)],
        capture_output=True, text=True).stdout
    return json.loads(out)


def loudness(path: pathlib.Path) -> tuple[float, float]:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True)
    mean = peak = 0.0
    for line in proc.stderr.splitlines():
        if "mean_volume:" in line:
            mean = float(line.split("mean_volume:")[1].split("dB")[0])
        if "max_volume:" in line:
            peak = float(line.split("max_volume:")[1].split("dB")[0])
    return mean, peak


def decode_errors(path: pathlib.Path) -> int:
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                          capture_output=True, text=True)
    return len([l for l in proc.stderr.splitlines() if l.strip()])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--expect-duration", type=float, default=None)
    ap.add_argument("--tolerance", type=float, default=1.0)
    ap.add_argument("--frames", default="")
    ap.add_argument("--frame-dir", default="/tmp/verify-frames")
    args = ap.parse_args()

    path = pathlib.Path(args.video).resolve()
    if not path.is_file():
        sys.exit(f"找不到文件：{path}")

    info = ffprobe(path)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    duration = float(info["format"]["duration"])
    size_mb = int(info["format"]["size"]) / 1024 / 1024

    ok = True
    print(f"文件      {path.name}  {size_mb:.1f} MB")
    if video:
        print(f"视频      {video['codec_name']} {video['width']}x{video['height']}")
        if (video["width"], video["height"]) != (1920, 1080):
            print("  ! 分辨率不是 1920x1080")
            ok = False
    else:
        print("  ! 没有视频流")
        ok = False

    if audio:
        print(f"音轨      {audio['codec_name']} {audio.get('channels')}ch {audio.get('sample_rate')}Hz")
    else:
        print("  ! 没有音轨，画面会是哑的")
        ok = False

    print(f"时长      {duration:.2f}s")
    if args.expect_duration:
        delta = abs(duration - args.expect_duration)
        flag = "OK" if delta <= args.tolerance else "偏差过大"
        print(f"预期      {args.expect_duration:.2f}s  差 {delta:.2f}s  {flag}")
        if delta > args.tolerance:
            ok = False

    if audio:
        mean, peak = loudness(path)
        print(f"响度      mean {mean:.1f} dB  peak {peak:.1f} dB")
        if peak > -1.0:
            print("  ! 峰值接近 0dB，可能削波")
            ok = False
        if mean < -40:
            print("  ! 平均响度过低，可能几乎无声")

    errs = decode_errors(path)
    print(f"解码错误  {errs}")
    if errs:
        ok = False

    if args.frames:
        out_dir = pathlib.Path(args.frame_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        made = []
        for t in [x.strip() for x in args.frames.split(",") if x.strip()]:
            dst = out_dir / f"frame-{t}s.png"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", t, "-i", str(path),
                            "-frames:v", "1", "-vf", "scale=640:-1", str(dst)], check=True)
            made.append(str(dst))
        print(f"抽帧      {len(made)} 张 -> {out_dir}")
        for m in made:
            print(f"  {m}")

    print("\n结论      " + ("通过" if ok else "有问题，见上面的 ! 标记"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
