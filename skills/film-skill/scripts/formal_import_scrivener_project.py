#!/usr/bin/env python3
"""Create a FILM-* project from a Scrivener .scriv assessment source."""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TODAY = "2026-07-01"
TIME_RE = re.compile(r"^(?:日|夜|白天|黑夜|清晨|早晨|上午|中午|下午|傍晚|黄昏|凌晨|深夜|午夜)$")
CUE_NAMES = {"司机", "女人", "女乘客", "中年男子", "中年男人"}


def load_scrivener_module():
    path = Path(__file__).resolve().with_name("import_scrivener_project.py")
    spec = importlib.util.spec_from_file_location("import_scrivener_project", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"{path}: cannot load import_scrivener_project.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def project_id_for(name: str) -> str:
    name = re.sub(r"^film-", "", name.strip(), flags=re.I)
    name = re.sub(r"^FILM-", "", name)
    return f"FILM-{name}"


def safe_filename(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|#\[\]]+', "", value).strip()
    return re.sub(r"\s+", "", value) or "未命名"


def scene_slug(title: str, index: int, used: set[str]) -> str:
    short = re.split(r"[，。；;,.（(]", title.strip(), maxsplit=1)[0]
    short = (safe_filename(short)[:16] or f"场景{index:03d}")
    base = short
    suffix = 2
    while short in used:
        short = f"{base}{suffix}"[:20]
        suffix += 1
    used.add(short)
    return short


def canonical_heading(line: str) -> tuple[str, str, str, str] | None:
    raw = line.strip()
    standard = re.match(r"^(内外景|内景|外景|内|外|室内|室外)\s+(.+?)\s+(\S+)\s*$", raw)
    if standard:
        io, loc, time = standard.groups()
        io = "内外" if io == "内外景" else ("内" if io in {"内景", "室内"} else ("外" if io in {"外景", "室外"} else io))
        return f"{io}    {loc.strip()}    {time.strip()}", io, loc.strip(), time.strip()

    parts = [p.strip() for p in re.split(r"\s{2,}", raw) if p.strip()]
    if len(parts) >= 3 and TIME_RE.match(parts[1]):
        loc, time, io_part = parts[0], parts[1], parts[2]
        io = "内外" if ("内" in io_part and "外" in io_part) else ("外" if "外" in io_part else "内")
        match = re.search(r"[（(]([^）)]+)[）)]", io_part)
        if match:
            loc = f"{loc}（{match.group(1)}）"
        return f"{io}    {loc}    {time}", io, loc, time
    return None


def normalize_body(text: str, scriv_module) -> tuple[str, tuple[str, str, str, str], bool]:
    lines = text.splitlines()
    out: list[str] = []
    heading: tuple[str, str, str, str] | None = None
    inferred = False
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if heading is None and stripped and scriv_module.looks_like_scene_heading(stripped):
            parsed = canonical_heading(stripped)
            if parsed:
                out.append(parsed[0])
                heading = parsed
                i += 1
                continue
        if stripped in CUE_NAMES or any(stripped.startswith(name + marker) for name in CUE_NAMES for marker in ("（", "(")):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip():
                out.append(" " * 16 + stripped)
                i = j
                continue
            out.append(f"（残稿孤立词 {stripped}）")
            i += 1
            continue
        if out and out[-1].startswith(" " * 16) and stripped:
            out.append(" " * 8 + stripped)
            i += 1
            continue
        out.append(line)
        i += 1

    if heading is None:
        heading = ("内    待确认地点    待确认", "内", "待确认地点", "待确认")
        out = [heading[0], ""] + out
        inferred = True
    return "\n".join(out).strip() + "\n", heading, inferred


def title_page(items) -> tuple[str, str]:
    for item in items:
        if item.category == "Front Matter" and "Title Page" in item.path and item.text:
            parts = re.findall(r"<([^>]+)>", item.text)
            return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")
    return "", ""


def write_project(root: Path, scriv: Path, project_name: str, draft_category: str) -> Path:
    scriv_module = load_scrivener_module()
    scriv_root, items = scriv_module.project_items(scriv)
    project_id = project_id_for(project_name)
    project_title = project_id.removeprefix("FILM-")
    project_dir = root / "write" / "film" / project_id
    if project_dir.exists():
        raise SystemExit(f"{project_dir}: already exists; refusing to overwrite")

    scene_items = [item for item in items if item.category == draft_category and item.text.strip() and item.include != "No"]
    if not scene_items:
        raise SystemExit(f"No included text items found in category {draft_category!r}")
    character_items = [item for item in items if item.category == "Characters" and item.text.strip()]
    source_title, author = title_page(items)

    for rel in (
        "bible", "outline", "characters", "scenes", "clues", "source-cards", "conversations",
        "ai-workspace/tasks", "ai-workspace/reports", "ai-workspace/rewrite-candidates",
        "versions", "exports",
    ):
        (project_dir / rel).mkdir(parents=True, exist_ok=True)

    (project_dir / "00_project.md").write_text(f"""---
type: project
domain: film
project_id: {project_id}
project: {project_title}
author: {author}
status: imported_draft
project_mode: deconstruction
format: screenplay
source_title: {source_title}
source_format: Scrivener .scriv
source_scrivener_path: {q(str(scriv))}
current_version: v0.1
created_at: {TODAY}
updated_at: {TODAY}
created_by: Codex ($film-skill)
---

# {project_title}

## 项目原则

- 一个 project 是一个封闭创作宇宙。
- 本项目来自 Scrivener 正文导入，后续修改先进入 `ai-workspace/rewrite-candidates/`。
- 当前 `scenes/` 是导入稿，不等于已完成的标准拍摄稿。

## 来源与模式

- 来源：`{scriv}`
- 模式：`deconstruction`，先保留旧稿结构，再做场单位审计、格式校正和修改方案。

## 当前版本状态

| 资产类型 | 数量 | 状态 |
|---------|:---:|------|
| Scrivener 正文场景 | {len(scene_items)} | 已导入，待场单位审计 |
| 人物原始卡 | {len(character_items)} | 已导入，待整理小传 |
| 素材卡 | 1 | 已导入 |
""", encoding="utf-8")

    (project_dir / "agent-policy.md").write_text(f"""---
type: agent_policy
domain: film
project_id: {project_id}
project: {project_title}
updated_at: {TODAY}
---

default_read:
  - 00_project.md
  - bible/
  - outline/
  - characters/
  - scenes/
  - clues/
  - source-cards/
  - conversations/

default_write:
  - ai-workspace/
  - conversations/
  - outputs/review/film/{project_id}/

requires_explicit_approval:
  - frontmatter_bulk_update
  - export_generation
  - version_snapshot
  - overwrite_imported_scenes

forbidden:
  - delete_files
  - rename_project_files
  - write_wiki_directly
  - read_other_projects_by_default
""", encoding="utf-8")

    (project_dir / "bible" / "premise.md").write_text(f"""---
type: bible_note
domain: film
project_id: {project_id}
project: {project_title}
status: imported_stub
updated_at: {TODAY}
---

# Premise

从 Scrivener 项目导入。当前只保留来源和结构，故事前提待后续拆解。
""", encoding="utf-8")

    used: set[str] = set()
    scene_entries: list[str] = []
    scene_rows: list[tuple[str, str, int, bool, str, str, str]] = []
    for index, item in enumerate(scene_items, 1):
        title = item.path.split(" / ")[-1]
        scene_id = f"S{index:03d}"
        slug = scene_slug(title, index, used)
        filename = f"{scene_id}_{slug}.md"
        body, heading, inferred = normalize_body(item.text, scriv_module)
        _, _, location, time = heading
        scene_entries.append(filename[:-3])
        scene_rows.append((scene_id, filename, item.order, inferred, location, time, title))
        status = "imported_needs_scene_unit_audit" if inferred else "imported_needs_format_review"
        (project_dir / "scenes" / filename).write_text(f"""---
type: scene
domain: film
project_id: {project_id}
project: {project_title}
scene_id: {scene_id}
sequence: {index:03d}
status: {status}
location: {q(location)}
time: {q(time)}
characters: []
conflict:
purpose: {q(title.replace(chr(10), " ").strip())}
emotional_turn:
clues: []
related_notes:
  - {q("Scrivener Binder: " + item.path)}
source_kind: scrivener_import
source_uuid: {item.uuid}
source_order: {item.order}
source_scene_heading_inferred: {"yes" if inferred else "no"}
version: v0.1
updated_at: {TODAY}
---

# {scene_id} {slug}

## 场景意图

- Scrivener 原始标题：{title}
- 导入状态：{"缺少显式场头，已添加待确认场头。" if inferred else "保留原文并标准化首行场头。"}

## 剧本正文

{body}
## 修改记录

| 版本 | 日期 | 修改内容 |
|------|------|---------|
| v0.1 | {TODAY} | 从 Scrivener 项目导入 |
""", encoding="utf-8")

    for index, item in enumerate(character_items, 1):
        name = item.path.split(" / ")[-1]
        filename_name = "女人" if name == "女乘客" else safe_filename(name)
        (project_dir / "characters" / f"C{index:03d}_{filename_name}.md").write_text(f"""---
type: character
domain: film
project_id: {project_id}
project: {project_title}
character_id: C{index:03d}
role: imported
desire:
fear:
status: imported_raw
source_kind: scrivener_import
updated_at: {TODAY}
---

# C{index:03d} {name}

## 原始人物卡

{item.text.strip()}

## 待整理

- 人物小传
- 欲望/恐惧/矛盾
- 与场景的对应关系
""", encoding="utf-8")

    (project_dir / "manuscript.md").write_text(
        "---\nlongform:\n  format: scenes\n"
        f"  title: {project_title}\n  draftTitle: v0.1\n  workflow: Default Workflow\n  sceneFolder: scenes\n  scenes:\n"
        + "".join(f"    - {entry}\n" for entry in scene_entries)
        + "  ignoredFiles: []\n---\n",
        encoding="utf-8",
    )

    (project_dir / "source-cards" / "SRC001_Scrivener原始项目.md").write_text(f"""---
type: source_card
domain: film
project_id: {project_id}
project: {project_title}
source_id: SRC001
source_paths:
  - {q(str(scriv))}
derived_from: Scrivener .scriv 项目
usable_for:
  - scene_unit_audit
  - draft_deconstruction
  - revision
status: consumed
updated_at: {TODAY}
---

# SRC001 {project_title} · Scrivener 原始项目

- 文件：`{scriv}`
- Scrivener Creator：`{scriv_root.attrib.get("Creator", "")}`
- Scrivener Modified：`{scriv_root.attrib.get("Modified", "")}`
""", encoding="utf-8")

    (project_dir / "outline" / "imported-scene-map.md").write_text(
        "---\ntype: outline\ndomain: film\n"
        f"project_id: {project_id}\nproject: {project_title}\noutline_id: OUT-001\n"
        f"outline_kind: scrivener_scene_map\nstatus: imported\nversion: v0.1\nupdated_at: {TODAY}\n---\n\n"
        "# Scrivener 导入场景表\n\n"
        "| scene_id | 文件 | Scrivener order | 场头 | 地点 | 时间 | 原始标题 |\n"
        "|---|---|---:|---|---|---|---|\n"
        + "".join(
            f"| {sid} | `{fn}` | {order} | {'待确认' if inferred else '已识别'} | {loc} | {tm} | {title.replace('|', '／')} |\n"
            for sid, fn, order, inferred, loc, tm, title in scene_rows
        ),
        encoding="utf-8",
    )

    report = f"""---
type: ai_report
domain: film
project_id: {project_id}
project: {project_title}
report_kind: scrivener_formal_import
status: completed
created_by: Codex
created_at: {TODAY}
---

# Scrivener 正式导入报告

已将 `{scriv}` 导入为正式 Film 项目 `{project_id}`。

- 导入场景：{len(scene_items)} 个
- 导入人物原始卡：{len(character_items)} 个
- 自带可识别中文场头：{sum(1 for _, _, _, inferred, _, _, _ in scene_rows if not inferred)} 个
- 缺少显式场头，已添加待确认场头：{sum(1 for _, _, _, inferred, _, _, _ in scene_rows if inferred)} 个

下一步运行全片 `scene_unit_audit`。
"""
    (project_dir / "ai-workspace" / "tasks" / f"AI-TASK-{TODAY.replace('-', '')}-scrivener-formal-import.md").write_text(f"""---
type: ai_task
domain: film
project_id: {project_id}
project: {project_title}
task_id: AI-TASK-{TODAY.replace('-', '')}-scrivener-formal-import
task_kind: scrivener_formal_import
status: completed
created_at: {TODAY}
created_by: human
---

# Scrivener Formal Import

将 Scrivener 项目导入为正式 Film 项目。
""", encoding="utf-8")
    (project_dir / "ai-workspace" / "reports" / f"AI-{TODAY.replace('-', '')}-scrivener-formal-import.md").write_text(report, encoding="utf-8")
    out_dir = root / "outputs" / "review" / "film" / project_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scrivener-formal-import.md").write_text(report, encoding="utf-8")
    return project_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a Scrivener .scriv package into a formal FILM-* project.")
    parser.add_argument("--scriv", required=True, help="Path to .scriv package")
    parser.add_argument("--project", required=True, help="Chinese project name, e.g. 夜车 or FILM-夜车")
    parser.add_argument("--draft-category", default="Screenplay", help="Top-level Scrivener Binder category to import")
    parser.add_argument("--root", default=str(ROOT), help="Agent-KB root; defaults to this repository")
    args = parser.parse_args()
    project_dir = write_project(Path(args.root).expanduser(), Path(args.scriv).expanduser(), args.project, args.draft_category)
    print(project_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
