#!/usr/bin/env python3
"""Validate screenplay project structure in Agent-KB.

The checker is intentionally small and read-only. It reports structural issues
for FILM-* projects and the template project, but never rewrites files.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILM_ROOT = ROOT / "write" / "film"
SCENE_HEADING_RE = re.compile(
    r"^\s*(?:\d{1,4}\s+)?(?:\*\*)?\s*(?:INT/EXT\.|INT\.|EXT\.|内外景|内景|外景|内|外|室内|室外)(?:\s|$)",
    re.IGNORECASE,
)
SCENE_HEADING_WIDE_SPACING_RE = re.compile(
    r"^\s*(?:\d{1,4}\s+)?(?:\*\*)?\s*(?:INT/EXT\.|INT\.|EXT\.|内外景|内景|外景|内|外|室内|室外)(?: {4,}|　{2,}).+(?: {4,}|　{2,})\S+\s*$",
    re.IGNORECASE,
)
SUBBEAT_HEADING_RE = re.compile(r"^###\s+\d+(?:\.\d+)+")
COLON_DIALOGUE_RE = re.compile(r"^\s*[\w\u4e00-\u9fff（）()·]{1,12}：\S")
CHARACTER_CUE_RE = re.compile(r"^\s*[\u4e00-\u9fffA-Z][\u4e00-\u9fffA-Z0-9·（）() ]{0,11}\s*$")
PARENTHETICAL_RE = re.compile(r"^\s*[（(].+[）)]\s*$")
CHARACTER_CUE_MIN_INDENT = 16
DIALOGUE_MIN_INDENT = 8


def parse_frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    data: dict[str, object] = {}
    current_key: str | None = None
    for raw_line in text[4:end].splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("  - ") and current_key:
            value = line[4:].strip().strip('"')
            data.setdefault(current_key, [])
            if isinstance(data[current_key], list):
                data[current_key].append(value)
            continue
        if ":" not in line:
            current_key = None
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value == "":
            data[key] = []
        elif value == "[]":
            data[key] = []
        else:
            data[key] = value.strip('"')
    return data


def project_dirs(project_filter: str | None) -> list[Path]:
    if not FILM_ROOT.exists():
        return []
    dirs = [p for p in FILM_ROOT.iterdir() if p.is_dir()]
    candidates = [p for p in dirs if (p / "00_project.md").exists() or (p / "agent-policy.md").exists()]
    if project_filter:
        candidates = [
            p
            for p in candidates
            if p.name == project_filter
            or p.name.startswith(project_filter + "-")
            or frontmatter_project_id(p) == project_filter
        ]
    return sorted(candidates)


def frontmatter_project_id(project_dir: Path) -> str | None:
    for name in ("00_project.md", "agent-policy.md"):
        path = project_dir / name
        if path.exists():
            value = parse_frontmatter(path).get("project_id")
            if isinstance(value, str) and value:
                return value
    return None


def expect(condition: bool, errors: list[str], path: Path, message: str) -> None:
    if not condition:
        errors.append(f"{path.relative_to(ROOT)}: {message}")


def check_required_project(project_dir: Path, errors: list[str]) -> str | None:
    project_id = frontmatter_project_id(project_dir)
    expect((project_dir / "00_project.md").exists(), errors, project_dir, "missing 00_project.md")
    expect((project_dir / "agent-policy.md").exists(), errors, project_dir, "missing agent-policy.md")
    for dirname in (
        "bible",
        "outline",
        "characters",
        "scenes",
        "clues",
        "source-cards",
        "ai-workspace/tasks",
        "ai-workspace/reports",
        "ai-workspace/rewrite-candidates",
        "versions",
        "exports",
    ):
        expect((project_dir / dirname).exists(), errors, project_dir / dirname, "missing required directory")
    expect(bool(project_id), errors, project_dir, "missing project_id")
    if project_id and project_dir.name.startswith("FILM-"):
        expected_prefix = "-".join(project_dir.name.split("-")[:2])
        expect(project_id == expected_prefix, errors, project_dir, f"project_id {project_id!r} does not match directory prefix {expected_prefix!r}")
    return project_id


def check_typed_files(
    project_dir: Path,
    project_id: str,
    dirname: str,
    expected_type: str,
    id_key: str,
    errors: list[str],
) -> None:
    seen: dict[str, Path] = {}
    for path in sorted((project_dir / dirname).glob("*.md")):
        fm = parse_frontmatter(path)
        expect(fm.get("type") == expected_type, errors, path, f"expected type: {expected_type}")
        expect(fm.get("project_id") == project_id, errors, path, f"expected project_id: {project_id}")
        value = fm.get(id_key)
        expect(isinstance(value, str) and bool(value), errors, path, f"missing {id_key}")
        if isinstance(value, str) and value:
            if value in seen:
                errors.append(f"{path.relative_to(ROOT)}: duplicate {id_key} {value!r}; first seen at {seen[value].relative_to(ROOT)}")
            seen[value] = path


def check_scene_sequences(project_dir: Path, errors: list[str]) -> None:
    seen: dict[str, Path] = {}
    for path in sorted((project_dir / "scenes").glob("*.md")):
        fm = parse_frontmatter(path)
        value = fm.get("sequence")
        if not isinstance(value, str) or not value:
            errors.append(f"{path.relative_to(ROOT)}: missing sequence")
            continue
        if value in seen:
            errors.append(f"{path.relative_to(ROOT)}: duplicate sequence {value!r}; first seen at {seen[value].relative_to(ROOT)}")
        seen[value] = path


def project_character_names(project_dir: Path) -> set[str]:
    names: set[str] = set()
    for path in sorted((project_dir / "characters").glob("*.md")):
        stem = path.stem
        if "_" in stem:
            names.add(stem.split("_", 1)[1])
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                parts = line[2:].strip().split(maxsplit=1)
                if len(parts) == 2:
                    names.add(parts[1])
                break
    return names


def screenplay_body_lines(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    body: list[tuple[int, str]] = []
    in_body = False
    for line_number, line in enumerate(lines, 1):
        if line.strip() == "## 剧本正文":
            in_body = True
            continue
        if in_body and line.startswith("## "):
            break
        if in_body:
            body.append((line_number, line))
    return body


def indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def cue_base_name(line: str) -> str:
    return re.split(r"[（(]", line.strip(), maxsplit=1)[0].strip()


def check_dialogue_block(
    body: list[tuple[int, str]],
    index: int,
    errors: list[str],
    path: Path,
    character_names: set[str],
) -> bool:
    line_number, line = body[index]
    if SCENE_HEADING_RE.match(line) or not CHARACTER_CUE_RE.match(line):
        return False
    if cue_base_name(line) not in character_names:
        return False
    if indent_width(line) < CHARACTER_CUE_MIN_INDENT:
        errors.append(f"{path.relative_to(ROOT)}:{line_number}: character cue must be centered/indented as a dialogue block")
        return True
    if index + 1 >= len(body) or body[index + 1][1].strip() == "":
        errors.append(f"{path.relative_to(ROOT)}:{line_number}: character cue must be followed directly by parenthetical or dialogue, not a blank line")
        return True

    next_line_number, next_line = body[index + 1]
    if indent_width(next_line) < DIALOGUE_MIN_INDENT:
        errors.append(f"{path.relative_to(ROOT)}:{next_line_number}: dialogue or parenthetical must be indented as a dialogue block")
        return True
    if PARENTHETICAL_RE.match(next_line):
        if index + 2 >= len(body) or body[index + 2][1].strip() == "":
            errors.append(f"{path.relative_to(ROOT)}:{next_line_number}: parenthetical must be followed directly by dialogue")
            return True
        dialogue_line_number, dialogue_line = body[index + 2]
        if indent_width(dialogue_line) < DIALOGUE_MIN_INDENT:
            errors.append(f"{path.relative_to(ROOT)}:{dialogue_line_number}: dialogue must be indented as a dialogue block")
            return True
    return True


def check_screenplay_body_contract(path: Path, errors: list[str], *, one_heading: bool, character_names: set[str]) -> None:
    body = screenplay_body_lines(path)
    if not body:
        errors.append(f"{path.relative_to(ROOT)}: missing ## 剧本正文 section")
        return
    if not any(line.strip() for _, line in body):
        return

    headings = [(line_number, line) for line_number, line in body if SCENE_HEADING_RE.match(line)]
    if not headings:
        errors.append(f"{path.relative_to(ROOT)}: screenplay body missing scene heading")
    elif one_heading and len(headings) > 1:
        errors.append(
            f"{path.relative_to(ROOT)}:{headings[1][0]}: screenplay body has {len(headings)} scene headings; split into separate scene files or move sequence notes to outline/"
        )
    for line_number, line in headings:
        if indent_width(line) != 0:
            errors.append(f"{path.relative_to(ROOT)}:{line_number}: scene heading must start at the left action margin")
            break
        if not SCENE_HEADING_WIDE_SPACING_RE.match(line):
            errors.append(
                f"{path.relative_to(ROOT)}:{line_number}: scene heading must separate interior/exterior, location, and time with at least 4 spaces or 2 full-width spaces"
            )
            break

    blank_run = 0
    for line_number, line in body:
        if line.strip():
            blank_run = 0
            continue
        blank_run += 1
        if blank_run > 1:
            errors.append(f"{path.relative_to(ROOT)}:{line_number}: screenplay body should use single blank lines only; scene spacing is handled by export")
            break

    for line_number, line in body:
        if SUBBEAT_HEADING_RE.match(line):
            errors.append(f"{path.relative_to(ROOT)}:{line_number}: screenplay body contains markdown beat heading; keep beats outside draft text")
            break

    for line_number, line in body:
        if COLON_DIALOGUE_RE.match(line):
            errors.append(f"{path.relative_to(ROOT)}:{line_number}: screenplay dialogue should use a standalone character cue, not 角色：对白")
            break

    for index in range(len(body)):
        if check_dialogue_block(body, index, errors, path, character_names):
            break


def check_scene_screenplay_contract(project_dir: Path, errors: list[str]) -> None:
    character_names = project_character_names(project_dir)
    for path in sorted((project_dir / "scenes").glob("*.md")):
        check_screenplay_body_contract(path, errors, one_heading=True, character_names=character_names)


def check_rewrite_candidates(project_dir: Path, errors: list[str]) -> None:
    character_names = project_character_names(project_dir)
    for path in sorted((project_dir / "ai-workspace" / "rewrite-candidates").glob("*.md")):
        fm = parse_frontmatter(path)
        if fm.get("type") == "rewrite_candidate":
            check_screenplay_body_contract(path, errors, one_heading=True, character_names=character_names)


def check_agent_files(project_dir: Path, project_id: str, errors: list[str]) -> None:
    task_paths = sorted((project_dir / "ai-workspace" / "tasks").glob("*.md"))
    report_paths = sorted((project_dir / "ai-workspace" / "reports").glob("*.md"))
    if report_paths and not task_paths:
        errors.append(f"{(project_dir / 'ai-workspace' / 'tasks').relative_to(ROOT)}: missing AI task card for existing AI reports")
    for path in task_paths:
        fm = parse_frontmatter(path)
        expect(fm.get("type") == "ai_task", errors, path, "expected type: ai_task")
        expect(fm.get("project_id") == project_id, errors, path, f"expected project_id: {project_id}")
        expect(bool(fm.get("allowed_read_paths")), errors, path, "missing allowed_read_paths")
        expect(bool(fm.get("allowed_write_paths")), errors, path, "missing allowed_write_paths")
    for path in report_paths:
        fm = parse_frontmatter(path)
        expect(fm.get("type") == "ai_report", errors, path, "expected type: ai_report")
        expect(fm.get("project_id") == project_id, errors, path, f"expected project_id: {project_id}")
    for path in sorted(project_dir.rglob("*.md")):
        fm = parse_frontmatter(path)
        if fm.get("type") == "rewrite_candidate":
            expect("scenes" not in path.relative_to(project_dir).parts, errors, path, "rewrite_candidate must not live under scenes/")


def check_boundary(project_dir: Path, project_id: str, errors: list[str]) -> None:
    other_project_pattern = re.compile(r"FILM-(?!TEMPLATE\b)[A-Z0-9]+")
    for path in sorted(project_dir.rglob("*.md")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "related_notes" not in line and "FILM-" not in line:
                continue
            for match in other_project_pattern.findall(line):
                if match != project_id:
                    errors.append(f"{path.relative_to(ROOT)}:{i}: possible cross-project reference to {match}")
    wiki_film = ROOT / "wiki" / "summaries" / "film"
    if wiki_film.exists():
        for path in wiki_film.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            if "project_id: FILM-" in text:
                errors.append(f"{path.relative_to(ROOT)}: project draft marker found in wiki summary")


def check_project(project_dir: Path) -> list[str]:
    errors: list[str] = []
    project_id = check_required_project(project_dir, errors)
    if not project_id:
        return errors
    check_typed_files(project_dir, project_id, "outline", "outline", "outline_id", errors)
    check_typed_files(project_dir, project_id, "scenes", "scene", "scene_id", errors)
    check_typed_files(project_dir, project_id, "characters", "character", "character_id", errors)
    check_typed_files(project_dir, project_id, "clues", "clue", "clue_id", errors)
    check_typed_files(project_dir, project_id, "source-cards", "source_card", "source_id", errors)
    check_scene_sequences(project_dir, errors)
    check_scene_screenplay_contract(project_dir, errors)
    check_rewrite_candidates(project_dir, errors)
    check_agent_files(project_dir, project_id, errors)
    check_boundary(project_dir, project_id, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Agent-KB screenplay project structure.")
    parser.add_argument("--project", help="Project id or project directory name to validate.")
    args = parser.parse_args()

    projects = project_dirs(args.project)
    if args.project and not projects:
        print(f"no matching project: {args.project}", file=sys.stderr)
        return 2
    errors: list[str] = []
    for project_dir in projects:
        errors.extend(check_project(project_dir))
    if errors:
        print("screenplay_kb_check: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"screenplay_kb_check: OK ({len(projects)} project(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
