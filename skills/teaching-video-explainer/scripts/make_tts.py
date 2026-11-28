#!/usr/bin/env python3
"""旁白 JSON -> 每段 wav + 绝对时间轴。

用法:
    python make_tts.py narration.json --out ./audio --timeline timeline.json

narration.json:
    {"voice": "zh-CN-YunjianNeural", "rate": "-4%", "gap": 0.5,
     "sections": [{"id": "s1", "text": "..."}, ...]}

输出 timeline.json 含 total 与每段 [start, end]，后续画面时间点全部以它为准。
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys


def need(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        sys.exit(f"缺少 {binary}。edge-tts 用 `uv tool install edge-tts` 安装，ffmpeg 用 `brew install ffmpeg`。")
    return path


def probe(path: pathlib.Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    return round(float(out), 3)


def synth(text: str, voice: str, rate: str, out_mp3: pathlib.Path) -> None:
    # edge-tts 的 --rate 若写成 "--rate -4%"，会被当成独立参数报错，必须用等号形式
    subprocess.run(
        ["edge-tts", f"--voice={voice}", f"--rate={rate}",
         "--text", text, "--write-media", str(out_mp3)],
        check=True, capture_output=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("narration")
    ap.add_argument("--out", default="audio")
    ap.add_argument("--timeline", default="timeline.json")
    ap.add_argument("--keep-mp3", action="store_true")
    args = ap.parse_args()

    need("edge-tts")
    need("ffmpeg")
    need("ffprobe")

    spec = json.loads(pathlib.Path(args.narration).read_text(encoding="utf-8"))
    voice = spec.get("voice", "zh-CN-YunjianNeural")
    rate = spec.get("rate", "-4%")
    gap = float(spec.get("gap", 0.5))

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    t = 0.0
    rows = []
    for sec in spec["sections"]:
        sid = sec["id"]
        mp3 = out_dir / f"{sid}.mp3"
        wav = out_dir / f"{sid}.wav"
        synth(sec["text"], voice, rate, mp3)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
                        "-ar", "44100", "-ac", "1", str(wav)], check=True)
        dur = probe(wav)
        rows.append({"id": sid, "start": round(t, 2), "end": round(t + dur, 2),
                     "duration": dur, "text": sec["text"]})
        print(f"{sid}  {dur:6.2f}s  {t:6.2f} → {t + dur:6.2f}")
        t += dur + gap
        if not args.keep_mp3:
            mp3.unlink(missing_ok=True)

    total = round(rows[-1]["end"], 2)
    timeline = {
        "total": total,
        "voice": voice,
        "rate": rate,
        "gap": gap,
        "sections": rows,
        "seg": {r["id"]: [r["start"], r["end"]] for r in rows},
    }
    pathlib.Path(args.timeline).write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n总长 {total:.2f}s  ({len(rows)} 段, 间隔 {gap}s)")
    if total > 150:
        print("提示：超过 150 秒，建议拆成两集或删减旁白。", file=sys.stderr)
    print(f"时间轴 -> {args.timeline}")


if __name__ == "__main__":
    main()
