#!/usr/bin/env python3
"""Inspect a Scrivener .scriv project and prepare an import report."""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCENE_HEADING_RE = re.compile(r"^(?:\d+\s+)?(?:INT/EXT\.|INT\.|EXT\.|内景/外景|内/外|内外景|内景|外景|内|外|室内|室外)(?:\s|$)", re.I)
CN_TIME_RE = r"(?:日|夜|白天|黑夜|清晨|早晨|上午|中午|下午|傍晚|黄昏|凌晨|深夜|午夜)"
CN_SPACE_SCENE_HEADING_RE = re.compile(
    rf"^[^\n。！？；：:，,]{{1,40}}\s{{2,}}{CN_TIME_RE}\s+"
    r"(?:内景|外景|内外景|内/外|内部|外部|内|外)(?:[（(][^）)]{1,40}[）)])?$"
)
SCRIVENER_TOKEN_RE = re.compile(r"<\\?\$Scr[^>]*>")


@dataclass
class Item:
    order: int
    category: str
    path: str
    uuid: str
    item_type: str
    include: str
    mode: str
    content_path: Path | None
    text: str


def text(node: ET.Element, path: str) -> str:
    found = node.find(path)
    return (found.text or "").strip() if found is not None else ""


def clean_text(value: str) -> str:
    value = SCRIVENER_TOKEN_RE.sub("", value).replace("\u00a0", " ")
    lines = [line.rstrip() for line in value.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def rtf_to_text(path: Path) -> str:
    if not path.exists():
        return ""
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return clean_text(result.stdout)


def safe_name(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]+", "_", value).strip()
    return re.sub(r"\s+", "-", value) or "scrivener-project"


def looks_like_scene_heading(line: str) -> bool:
    line = line.strip()
    return bool(SCENE_HEADING_RE.match(line) or CN_SPACE_SCENE_HEADING_RE.match(line))


def iter_items(scriv: Path, node: ET.Element, category: str, parents: list[str], counter: list[int]) -> list[Item]:
    title = text(node, "Title") or node.attrib.get("UUID", "")
    uuid = node.attrib.get("UUID", "")
    current_path = parents + [title]
    data_dir = scriv / "Files" / "Data" / uuid
    content_path = data_dir / "content.rtf"
    body = rtf_to_text(content_path) if content_path.exists() else ""

    items: list[Item] = []
    counter[0] += 1
    items.append(
        Item(
            order=counter[0],
            category=category,
            path=" / ".join(current_path),
            uuid=uuid,
            item_type=node.attrib.get("Type", ""),
            include=text(node, "./MetaData/IncludeInCompile") or "-",
            mode=text(node, "./TextSettings/TextMode") or "-",
            content_path=content_path if content_path.exists() else None,
            text=body,
        )
    )
    children = node.find("Children")
    if children is not None:
        for child in children.findall("BinderItem"):
            items.extend(iter_items(scriv, child, category, current_path, counter))
    return items


def load_project(scriv: Path) -> tuple[ET.Element, Path]:
    candidates = sorted(scriv.glob("*.scrivx"))
    if not candidates:
        raise SystemExit(f"{scriv}: missing .scrivx")
    return ET.parse(candidates[0]).getroot(), candidates[0]


def project_items(scriv: Path) -> tuple[ET.Element, list[Item]]:
    root, _ = load_project(scriv)
    counter = [0]
    items: list[Item] = []
    for top in root.findall("./Binder/BinderItem"):
        category = text(top, "Title") or top.attrib.get("Type", "")
        items.extend(iter_items(scriv, top, category, [], counter))
    return root, items


def write_manifest(items: list[Item], output: Path) -> None:
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["order", "category", "path", "uuid", "type", "include", "mode", "chars", "lines", "scene_heading", "first_line"])
        for item in items:
            nonempty = [line.strip() for line in item.text.splitlines() if line.strip()]
            first = nonempty[0] if nonempty else ""
            has_scene_heading = any(looks_like_scene_heading(line) for line in nonempty[:3])
            writer.writerow(
                [
                    item.order,
                    item.category,
                    item.path,
                    item.uuid,
                    item.item_type,
                    item.include,
                    item.mode,
                    len(item.text),
                    len(item.text.splitlines()),
                    "yes" if has_scene_heading else "no",
                    first[:120],
                ]
            )


def write_draft_preview(items: list[Item], output: Path) -> None:
    draft_items = [item for item in items if item.category == "Screenplay" and item.text and item.include != "No"]
    parts = ["# Scrivener Draft Preview", ""]
    for index, item in enumerate(draft_items, 1):
        title = item.path.split(" / ")[-1]
        parts.extend([f"## {index:03d} {title}", "", item.text, ""])
    output.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def write_report(scriv: Path, root: ET.Element, items: list[Item], out_dir: Path, report: Path) -> None:
    draft = [item for item in items if item.category == "Screenplay"]
    draft_text = [item for item in draft if item.text and item.include != "No"]
    scene_like = []
    for item in draft_text:
        nonempty = [line.strip() for line in item.text.splitlines() if line.strip()]
        if any(looks_like_scene_heading(line) for line in nonempty[:3]):
            scene_like.append(item)
    by_category: dict[str, int] = {}
    for item in items:
        by_category[item.category] = by_category.get(item.category, 0) + 1

    lines = [
        "---",
        f"title: {scriv.name} — Scrivener 导入评估报告",
        "type: source_intake_report",
        "domain: film",
        "status: draft",
        "created_at: 2026-07-01",
        "created_by: Codex ($film-skill)",
        f"source_file: {scriv}",
        "---",
        "",
        f"# {scriv.name} — Scrivener 导入评估报告",
        "",
        "## 结论",
        "",
        "可以导入。该 `.scriv` 包含可解析的 `.scrivx` Binder 结构和可用 `textutil` 转换的 RTF 正文。",
        "",
        "第一阶段建议只做单向导入预览：先生成项目结构、场景清单和正文预览，经确认后再写入正式 Film 项目。",
        "",
        "## 项目信息",
        "",
        f"- Scrivener version: {root.attrib.get('Creator', '')}",
        f"- Author: {root.attrib.get('Author', '')}",
        f"- Modified: {root.attrib.get('Modified', '')}",
        f"- Source: `{scriv}`",
        f"- Output dir: `{out_dir.relative_to(ROOT)}`",
        "",
        "## Binder 统计",
        "",
        "| Category | Items |",
        "|---|---:|",
    ]
    for category, count in sorted(by_category.items()):
        lines.append(f"| {category} | {count} |")
    lines.extend(
        [
            "",
            "## Draft 统计",
            "",
            f"- Screenplay Binder items: {len(draft)}",
            f"- Draft text items with content: {len(draft_text)}",
            f"- Scene-heading-like items: {len(scene_like)}",
            "",
            "## 文件产物",
            "",
            f"- Manifest: `{(out_dir / 'manifest.tsv').relative_to(ROOT)}`",
            f"- Draft preview: `{(out_dir / 'draft-preview.md').relative_to(ROOT)}`",
            "",
            "## 建议映射",
            "",
            "- `Screenplay` → 候选 `scenes/` 与 Longform 顺序。",
            "- `Characters` → 候选 `characters/`。",
            "- `Places` → 候选 `bible/locations` 或 `bible/`。",
            "- `Notes` / `Research` → `source-cards/` 或 `ai-workspace/reports/`。",
            "",
            "## 风险",
            "",
            "- Scrivener 里的父级 Text 可能既有正文又有子节点，正式导入前需要确认是否把父级当作 section 还是 scene。",
            "- 互动剧分支会保留 Binder 层级；不能简单线性化后当成普通电影场次。",
            "- RTF 转 TXT 会丢失部分富文本样式；剧本格式应以场头、缩进、Binder 顺序和后续校验为准。",
        ]
    )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a Scrivener .scriv project for Film import.")
    parser.add_argument("--scriv", required=True, help="Path to .scriv package")
    parser.add_argument("--output-dir", help="Output directory under the Agent-KB repo")
    args = parser.parse_args()

    scriv = Path(args.scriv).expanduser()
    if not scriv.exists() or not scriv.is_dir():
        raise SystemExit(f"{scriv}: not a readable .scriv directory")
    if not shutil_which_textutil():
        raise SystemExit("textutil not found; Scrivener RTF extraction requires macOS textutil")

    root, items = project_items(scriv)
    slug = safe_name(scriv.stem)
    out_dir = Path(args.output_dir) if args.output_dir else ROOT / "outputs" / "review" / "film" / f"scrivener-import-{slug}"
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    write_manifest(items, out_dir / "manifest.tsv")
    write_draft_preview(items, out_dir / "draft-preview.md")
    write_report(scriv, root, items, out_dir, out_dir / "import-report.md")

    print(out_dir.relative_to(ROOT))
    return 0


def shutil_which_textutil() -> bool:
    return subprocess.run(["/usr/bin/which", "textutil"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
