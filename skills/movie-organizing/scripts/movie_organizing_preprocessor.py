#!/usr/bin/env python3
"""Deterministic, reversible preprocessor for ``movie-organizing``.

The preprocessor handles only facts that can be derived from paths and a
single main video filename. It produces a machine-readable plan, applies
safe rename/move bundles when explicitly requested, and verifies the exact
post-state. Identity, director attribution, collections, special containers
and duplicate selection remain ``EXCEPTION`` work for the agent.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import stat
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


VERSION = "1.3.6"
EXPECTED_NAMING_CONTRACT_SHA256 = "c4a50e6cf92c230da3ad5e19092d80167b5379b6fd34eb919f8db7a6cf5c3a12"
MAX_SELECTED_ACTION_UNITS = 20
LARGE_LIBRARY_VIDEO_THRESHOLD = 20
LARGE_LIBRARY_DIRECTOR_THRESHOLD = 3
LARGE_LIBRARY_ACTION_THRESHOLD = 50
LARGE_LIBRARY_BATCH_LIMIT = 10

VIDEO_EXTENSIONS = {
    ".avi",
    ".iso",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".rmvb",
    ".ts",
    ".wmv",
}
SUBTITLE_EXTENSIONS = {".ass", ".idx", ".srt", ".ssa", ".sub", ".sup", ".vtt"}
WORK_RECORD_DIR = "_work-record_"
PENDING_DIR = "_待确认_"
TRASH_PREFIX = "_trash_"
EXCLUDED_NAMES = {WORK_RECORD_DIR, PENDING_DIR}


def _timestamp() -> str:
    """Return a collision-resistant local timestamp for recovery filenames."""

    return datetime.now().strftime("%Y%m%dT%H%M%S%f")


def _canonical(path: str | Path) -> Path:
    """Return a canonical path without requiring it to exist."""

    return Path(os.path.realpath(os.fspath(path)))


def _lexical(path: str | Path) -> Path:
    """Normalize ``..`` without resolving symlinks."""

    return Path(os.path.abspath(os.fspath(path)))


def _inside(root: str | Path, path: str | Path, *, allow_root: bool = True) -> bool:
    root_path = _canonical(root)
    path_path = _canonical(path)
    if allow_root and path_path == root_path:
        return True
    try:
        path_path.relative_to(root_path)
    except ValueError:
        return False
    return True


def _validate_recovery_tree(task_root: str | Path) -> None:
    """Reject recovery control paths that could redirect writes outside root."""

    root = _canonical(task_root)
    work_record = root / WORK_RECORD_DIR
    if os.path.lexists(work_record):
        if os.path.islink(work_record):
            raise OSError(f"recovery control directory is a symlink: {work_record}")
        if not work_record.is_dir() or not _inside(root, work_record, allow_root=False):
            raise OSError(f"recovery control directory is not an in-root directory: {work_record}")

    recovery = work_record / "recovery"
    if os.path.lexists(recovery):
        if os.path.islink(recovery):
            raise OSError(f"recovery directory is a symlink: {recovery}")
        if not recovery.is_dir() or not _inside(root, recovery, allow_root=False):
            raise OSError(f"recovery directory is not an in-root directory: {recovery}")


def _is_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _clean_cn(text: str) -> str:
    return text.strip().strip(" .-_\t\r\n")


def _is_latin_letter(char: str) -> bool:
    name = unicodedata.name(char, "")
    return "LATIN" in name or (char.isascii() and char.isalpha())


def _director_parts(name: str) -> Optional[Tuple[str, str]]:
    """Split a director directory at an unambiguous Latin-name boundary."""

    stripped = name.strip()
    boundary = next((index for index, char in enumerate(stripped) if _is_latin_letter(char)), -1)
    if boundary <= 0:
        return None
    chinese_part = stripped[:boundary].strip().rstrip(".").strip()
    english_part = stripped[boundary:].strip()
    if not chinese_part or not english_part or not _is_cjk(chinese_part):
        return None
    if _is_cjk(english_part) or not any(_is_latin_letter(char) for char in english_part):
        return None
    # Only the documented separator characters are accepted in the Chinese
    # segment.  A stray symbol would make automatic identity inference unsafe.
    allowed = set(" ·、.")
    if any(not (_is_cjk(char) or char in allowed) for char in chinese_part):
        return None
    pieces = [piece for piece in re.split(r"[ .·、]+", chinese_part) if piece]
    if any(not _is_cjk(piece) for piece in pieces):
        return None
    if any(char in chinese_part for char in " .·、") and len(pieces) < 2:
        # A single contiguous native Chinese name is valid; separators without
        # at least two CJK fragments are ambiguous and stay EXCEPTION.
        return None
    return chinese_part, english_part


def _normalize_director_chinese_part(value: str) -> str:
    """Normalize foreign-name separators without changing native names."""

    normalized_parts: List[str] = []
    for part in value.split("、"):
        part = part.strip()
        if not part:
            continue
        # A Chinese segment that is already contiguous is a native Chinese
        # name; retain it.  Spaces or ASCII dots between two or more CJK
        # fragments indicate a v1.3.3 transliteration migration and become
        # the contract's middle dot.
        if re.search(r"[ .]", part):
            part = re.sub(r"[ .]+", "·", part)
            part = re.sub(r"·+", "·", part).strip("·")
        normalized_parts.append(part)
    return "、".join(normalized_parts)


def _normalize_director_name(name: str) -> Optional[str]:
    """Return the deterministic contract form, or ``None`` when ambiguous."""

    parts = _director_parts(name)
    if parts is None:
        # Legacy non-Chinese director anchors remain untouched here; the audit
        # still reports them as non-conforming when they contain active media.
        return name.strip() if not _is_cjk(name) else None
    chinese_part, english_part = parts
    chinese_part = _normalize_director_chinese_part(chinese_part)
    return f"{chinese_part} {english_part}"


def _name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _conflicting_name(parent: Path, name: str, *, ignore: Optional[Path] = None) -> Optional[str]:
    """Find a sibling with the same case/Unicode-normalized name."""

    wanted = _name_key(name)
    try:
        entries = os.scandir(parent)
    except OSError:
        return None
    with entries as iterator:
        for entry in iterator:
            if entry.name == name:
                continue
            if ignore is not None and _canonical(entry.path) == _canonical(ignore):
                continue
            if _name_key(entry.name) == wanted:
                return entry.name
    return None


def _normalize_title(title: str) -> str:
    """Normalize only the English title portion before the year."""

    title = title.replace(".", " ").replace("_", " ")
    return " ".join(title.split())


def _parse_video_stem(stem: str) -> Optional[Dict[str, str]]:
    """Parse ``Title.YEAR.release...`` and optional Chinese filename prefix."""

    raw = stem.strip()
    chinese_prefix = ""
    body = raw
    first_dot = raw.find(".")
    if first_dot > 0 and _is_cjk(raw[:first_dot]):
        chinese_prefix = _clean_cn(raw[:first_dot])
        body = raw[first_dot + 1 :]

    # A year is a segment boundary, not an arbitrary four-digit substring.
    match = re.search(r"(?<!\d)(19\d{2}|20\d{2})(?=\.|\s|$)", body)
    if not match:
        return None
    title = body[: match.start()].rstrip(" ._\t")
    if not title:
        return None
    year = match.group(1)
    tail = body[match.end() :]
    if tail and not tail.startswith("."):
        # Accept a space-delimited release tail but emit the contract's dot
        # separator; the original token text is otherwise retained.
        tail = "." + tail.strip()
    normalized_title = _normalize_title(title)
    if not normalized_title:
        return None
    normalized_stem = f"{normalized_title}.{year}{tail}"
    return {
        "title": title,
        "normalized_title": normalized_title,
        "year": year,
        "tail": tail,
        "normalized_stem": normalized_stem,
        "chinese_prefix": chinese_prefix,
    }


def _is_allowed_chinese_title_char(char: str) -> bool:
    """Return whether a legacy Chinese title character is contract-safe."""

    if _is_cjk(char) or char in {" ", "\u3000", "·"}:
        return True
    codepoint = ord(char)
    # CJK punctuation and the full-width punctuation block are valid title
    # glyphs, while ASCII/Latin/Cyrillic letters remain deliberately excluded.
    return 0x3000 <= codepoint <= 0x303F or 0xFF01 <= codepoint <= 0xFF65


def _extract_cn_before_english(text: str) -> str:
    """Extract a Chinese title before an English/ASCII title."""

    boundary = next((index for index, char in enumerate(text) if _is_latin_letter(char)), -1)
    if boundary >= 0:
        candidate = text[:boundary]
    else:
        candidate = text
    candidate = _clean_cn(candidate)
    if not _is_cjk(candidate):
        return ""
    if any(not _is_allowed_chinese_title_char(char) for char in candidate):
        return ""
    return candidate


def _parse_movie_dir(name: str) -> Optional[Tuple[str, str]]:
    """Return ``(Chinese title, year)`` for supported legacy/current names."""

    # Legacy: ``中文名 English Name (YYYY)``. Keep all Chinese words before
    # the first ASCII letter; do not collapse or invent title text.
    bracket = re.search(r"\s*\(((?:19|20)\d{2})\)\s*$", name)
    if bracket:
        base = name[: bracket.start()].rstrip()
        cn = _extract_cn_before_english(base)
        if cn:
            return cn, bracket.group(1)

    # Current/incomplete point style: ``中文名.English Name.YYYY[.release]``.
    if "." in name:
        cn_part, rest = name.split(".", 1)
        cn = _clean_cn(cn_part)
        if _is_cjk(cn):
            parsed = _parse_video_stem(rest)
            if parsed:
                return cn, parsed["year"]
    return None


def _read_nfo_chinese(path: Path) -> str:
    """Read only a same-stem NFO title field as a reliable CN source."""

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    for tag in ("title", "originaltitle", "sorttitle"):
        pattern = rf"<\s*{tag}\b[^>]*>(.*?)<\s*/\s*{tag}\s*>"
        for match in re.finditer(pattern, content, flags=re.IGNORECASE | re.DOTALL):
            candidate = html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
            candidate = " ".join(candidate.split())
            if _is_cjk(candidate):
                return candidate
    return ""


def _find_same_stem_nfo(parent: Path, stem: str) -> Optional[Path]:
    wanted = f"{stem}.nfo".casefold()
    try:
        entries = os.scandir(parent)
    except OSError:
        return None
    with entries as iterator:
        for entry in iterator:
            if entry.is_file(follow_symlinks=False) and entry.name.casefold() == wanted:
                return Path(entry.path)
    return None


def _has_child_directory(parent: Path) -> bool:
    """Detect containers/collections without reading their contents."""

    try:
        entries = os.scandir(parent)
    except OSError:
        return True
    with entries as iterator:
        # Reserved control directories are audited separately at the terminal
        # cleanup gate; they must not turn an otherwise valid movie bundle into
        # a collection EXCEPTION before that gate can report the violation.
        return any(
            entry.is_dir(follow_symlinks=False) and not (
                entry.name == WORK_RECORD_DIR
                or entry.name == PENDING_DIR
                or entry.name.startswith(TRASH_PREFIX)
            )
            for entry in iterator
        )


def _collect_sidecars(
    parent: Path, source_video: Path, source_stem: str, target_stem: str, target_dir: Path
) -> List[Dict[str, str]]:
    """Return only exact same-stem NFO and subtitle bundle members."""

    result: List[Dict[str, str]] = []
    prefix = f"{source_stem}.".casefold()
    try:
        entries = os.scandir(parent)
    except OSError:
        return result
    with entries as iterator:
        for entry in iterator:
            if not entry.is_file(follow_symlinks=False):
                continue
            source = Path(entry.path)
            if source == source_video:
                continue
            lower_name = entry.name.casefold()
            if lower_name == f"{source_stem}.nfo".casefold():
                target = target_dir / f"{target_stem}.nfo"
                result.append({"kind": "nfo", "source": str(source), "target": str(target)})
                continue
            if lower_name.startswith(prefix) and source.suffix.casefold() in SUBTITLE_EXTENSIONS:
                suffix = entry.name[len(source_stem) :]
                language_match = re.fullmatch(
                    r"\.(zh|chn|chn0|chs|cht|eng)(\.[^.]+)", suffix, flags=re.IGNORECASE
                )
                if not language_match:
                    # A subtitle without a recognized language marker cannot be
                    # renamed safely because adding one would invent metadata.
                    result.append(
                        {
                            "kind": "subtitle_invalid",
                            "source": str(source),
                            "target": "",
                        }
                    )
                    continue
                marker = language_match.group(1).casefold()
                marker = {"zh": "chs", "chn": "chs", "chn0": "chs"}.get(marker, marker)
                suffix = f".{marker}{language_match.group(2)}"
                target = target_dir / f"{target_stem}{suffix}"
                result.append({"kind": "subtitle", "source": str(source), "target": str(target)})
                continue
            # Any other NFO/subtitle in a movie unit is not safely attributable.
            if source.suffix.casefold() == ".nfo" or source.suffix.casefold() in SUBTITLE_EXTENSIONS:
                result.append({"kind": "sidecar_unrelated", "source": str(source), "target": ""})
    return sorted(result, key=lambda item: item["source"])


def _action(
    action_id: str,
    action_name: str,
    *,
    target: Path,
    source: Optional[Path],
    evidence: str,
    rollback: str,
    preconditions: Sequence[str],
    postconditions: Sequence[str],
) -> Dict[str, object]:
    item: Dict[str, object] = {
        "id": action_id,
        "action": action_name,
        "type": action_name,
        "target": str(target),
        "evidence": evidence,
        "rollback": rollback,
        "preconditions": list(preconditions),
        "postconditions": list(postconditions),
    }
    if source is not None:
        item["source"] = str(source)
    return item


def _empty_bundle(
    parent: Path,
    video: Optional[Path],
    source_shape: str,
    reason: str,
    *,
    source_director_dir: Optional[Path] = None,
    expected_director_dir: Optional[Path] = None,
    expected_movie_dir: str = "",
    expected_movie_dir_path: str = "",
    expected_video_target: str = "",
) -> Dict[str, object]:
    source_director = source_director_dir or parent.parent
    expected_director = expected_director_dir or source_director
    return {
        "source_movie_dir": str(parent),
        "source_director_dir": str(source_director),
        "expected_director_dir": str(expected_director),
        "status": "EXCEPTION",
        "source_shape": source_shape,
        "expected_movie_dir": expected_movie_dir or parent.name,
        "expected_movie_dir_path": expected_movie_dir_path,
        "expected_video_source": str(video) if video else str(parent / "<missing>"),
        "expected_video_target": expected_video_target,
        "expected_nfo_targets": [],
        "expected_nfo_path": "",
        "expected_subtitle_targets": [],
        "expected_subtitle_paths": [],
        "source_nfo_paths": [],
        "source_subtitle_paths": [],
        "actions": [],
        "exception": reason,
    }


def _build_bundle(parent: Path, videos: Sequence[Path], task_root: Path) -> Dict[str, object]:
    if len(videos) != 1:
        reason = "multi-video unit; collections and multi-version units stay EXCEPTION"
        return _empty_bundle(parent, videos[0] if videos else None, "collection", reason)

    video = videos[0]
    parsed = _parse_video_stem(video.stem)
    if parsed is None:
        return _empty_bundle(parent, video, "orphan", "video filename has no deterministic title/year")

    dir_info = _parse_movie_dir(parent.name)
    is_standard = dir_info is not None
    relative_parts = parent.relative_to(task_root).parts if _inside(task_root, parent) else ()
    if not relative_parts:
        return _empty_bundle(parent, video, "orphan", "scope: root-level orphan has no director folder")

    legacy_root_movie = len(relative_parts) == 1 and is_standard
    if legacy_root_movie:
        source_director = task_root
        expected_director = task_root
    else:
        source_director = task_root / relative_parts[0]
        normalized_director = _normalize_director_name(source_director.name)
        if normalized_director is None:
            source_shape = "dispersed" if len(relative_parts) > 1 else "orphan"
            return _empty_bundle(
                parent,
                video,
                source_shape,
                "director name has no unambiguous Chinese/Latin boundary or valid separators",
                source_director_dir=source_director,
                expected_director_dir=source_director,
            )
        expected_director = task_root / normalized_director

    # A direct movie child of the director anchor is already in the standard
    # shape.  Only one or more wrapper levels below that child are dispersed
    # and therefore need a rehome to the director root.
    nested = not legacy_root_movie and len(relative_parts) > 2
    source_shape = "standard" if is_standard and not nested else ("dispersed" if nested else "orphan")
    dir_year = dir_info[1] if dir_info else ""
    cn_from_dir = dir_info[0] if dir_info else ""
    cn_from_video = parsed["chinese_prefix"]
    # NFO contents are read only for an orphan that actually needs a reliable
    # Chinese source; ordinary standard folders use filename/path facts only.
    nfo_path = _find_same_stem_nfo(parent, video.stem) if not is_standard else None
    cn_from_nfo = _read_nfo_chinese(nfo_path) if nfo_path else ""

    if is_standard:
        if _has_child_directory(parent):
            return _empty_bundle(
                parent,
                video,
                "collection",
                "special/container subdirectory present; keep DVD/BDMV/collection for Agent",
                source_director_dir=source_director,
                expected_director_dir=expected_director,
            )
        if dir_year != parsed["year"]:
            return _empty_bundle(
                parent, video, source_shape, "year mismatch between directory and video",
                source_director_dir=source_director, expected_director_dir=expected_director,
            )
        if cn_from_video and cn_from_video != cn_from_dir:
            return _empty_bundle(
                parent, video, source_shape, "conflicting Chinese title sources",
                source_director_dir=source_director, expected_director_dir=expected_director,
            )
        chinese_title = cn_from_dir
    else:
        if cn_from_video and cn_from_nfo and cn_from_video != cn_from_nfo:
            return _empty_bundle(
                parent, video, source_shape, "conflicting Chinese title sources",
                source_director_dir=source_director, expected_director_dir=expected_director,
            )
        chinese_title = cn_from_video or cn_from_nfo
        if not chinese_title:
            return _empty_bundle(
                parent, video, source_shape, "no reliable Chinese title source for orphan",
                source_director_dir=source_director, expected_director_dir=expected_director,
            )

    normalized_stem = parsed["normalized_stem"]
    expected_video_name = f"{normalized_stem}{video.suffix}"
    expected_dir_name = f"{chinese_title}.{normalized_stem}"
    source_dir = parent
    staging_dir = source_director / expected_dir_name
    target_dir = expected_director / expected_dir_name
    expected_video_target = target_dir / expected_video_name

    def empty(reason: str) -> Dict[str, object]:
        return _empty_bundle(
            parent,
            video,
            source_shape,
            reason,
            source_director_dir=source_director,
            expected_director_dir=expected_director,
            expected_movie_dir=expected_dir_name,
            expected_movie_dir_path=str(target_dir),
            expected_video_target=str(expected_video_target),
        )

    if not _inside(task_root, target_dir, allow_root=False):
        return empty("scope: expected target is outside TASK_ROOT")
    if staging_dir != source_dir and staging_dir.exists():
        return empty(f"target exists: {staging_dir}")
    if target_dir != source_dir and target_dir.exists() and target_dir != staging_dir:
        return empty(f"target exists: {target_dir}")
    if staging_dir != source_dir:
        sibling_collision = _conflicting_name(staging_dir.parent, staging_dir.name)
        if sibling_collision:
            return empty(f"Unicode/case collision with target directory: {sibling_collision}")

    child_collision = _conflicting_name(source_dir, expected_video_name)
    if child_collision:
        return empty(f"Unicode/case collision with target video: {child_collision}")

    sidecars = _collect_sidecars(parent, video, video.stem, normalized_stem, target_dir)
    invalid_sidecar = next(
        (item for item in sidecars if item["kind"] in {"subtitle_invalid", "sidecar_unrelated"}), None
    )
    if invalid_sidecar:
        reason = "subtitle language marker is ambiguous" if invalid_sidecar["kind"] == "subtitle_invalid" else "unrelated NFO/subtitle sidecar is not attributable"
        return empty(f"{reason}: {invalid_sidecar['source']}")
    seen_sidecar_targets: set[str] = set()
    for sidecar in sidecars:
        target = _canonical(sidecar["target"])
        source = _canonical(sidecar["source"])
        target_key = _name_key(Path(sidecar["target"]).name)
        if target_key in seen_sidecar_targets:
            return empty(f"ambiguous sidecar target: {sidecar['target']}")
        seen_sidecar_targets.add(target_key)
        if target.exists() and target != source:
            return empty(f"target sidecar exists: {target}")
        sibling_collision = _conflicting_name(source_dir if is_standard else staging_dir, Path(sidecar["target"]).name)
        if sibling_collision:
            return empty(f"Unicode/case collision with target sidecar: {sibling_collision}")

    actions: List[Dict[str, object]] = []
    action_number = 1
    if is_standard:
        child_video_target = source_dir / expected_video_name
        if _canonical(video) != _canonical(child_video_target):
            actions.append(_action(
                f"a{action_number}", "move_file", source=video, target=child_video_target,
                evidence="video stem normalized from filename", rollback="rename target back to source",
                preconditions=["source exists", "target absent", "both paths under TASK_ROOT"],
                postconditions=["source absent", "target exists"],
            ))
            action_number += 1
        for sidecar in sidecars:
            source = Path(sidecar["source"])
            target = source_dir / Path(sidecar["target"]).name
            if _canonical(source) == _canonical(target):
                continue
            actions.append(_action(
                f"a{action_number}", "move_file", source=source, target=target,
                evidence=f"{sidecar['kind']} follows normalized video basename", rollback="rename target back to source",
                preconditions=["source exists", "target absent", "bundle member is same-stem sidecar"],
                postconditions=["source absent", "target exists"],
            ))
            action_number += 1
        if _canonical(staging_dir) != _canonical(source_dir):
            actions.append(_action(
                f"a{action_number}", "rename_dir", source=source_dir, target=staging_dir,
                evidence="legacy/incomplete movie folder normalized and rehomed to director anchor",
                rollback="rename target directory back to source directory",
                preconditions=["source directory exists", "target directory absent", "target is under source director anchor"],
                postconditions=["source directory absent", "target directory exists"],
            ))
    else:
        actions.append(_action(
            f"a{action_number}", "mkdir", source=None, target=staging_dir,
            evidence="reliable CN source from filename prefix or same-stem NFO",
            rollback="leave empty directory for manual reversible handling",
            preconditions=["target absent", "parent director folder exists", "target under TASK_ROOT"],
            postconditions=["target directory exists"],
        ))
        action_number += 1
        bundle_moves = [(video, staging_dir / expected_video_name, "video")]
        bundle_moves.extend((Path(item["source"]), staging_dir / Path(item["target"]).name, item["kind"]) for item in sidecars)
        for source, target, kind in bundle_moves:
            actions.append(_action(
                f"a{action_number}", "move_file", source=source, target=Path(target),
                evidence=f"{kind} moved as one movie bundle", rollback="rename target back to source",
                preconditions=["source exists", "target absent", "source and target under TASK_ROOT"],
                postconditions=["source absent", "target exists"],
            ))
            action_number += 1

    source_nfo_paths = [item["source"] for item in sidecars if item["kind"] == "nfo"]
    source_subtitle_paths = [item["source"] for item in sidecars if item["kind"] == "subtitle"]
    expected_nfo_targets = [item["target"] for item in sidecars if item["kind"] == "nfo"]
    expected_subtitle_targets = [item["target"] for item in sidecars if item["kind"] == "subtitle"]
    status = "NAMING_PASS" if not actions else "ACTION_REQUIRED"
    return {
        "source_movie_dir": str(parent),
        "source_director_dir": str(source_director),
        "expected_director_dir": str(expected_director),
        "status": status,
        "source_shape": source_shape,
        "expected_movie_dir": expected_dir_name,
        "expected_movie_dir_path": str(target_dir),
        "expected_video_source": str(video),
        "expected_video_target": str(expected_video_target),
        "expected_nfo_targets": expected_nfo_targets,
        "expected_nfo_path": expected_nfo_targets[0] if expected_nfo_targets else "",
        "expected_subtitle_targets": expected_subtitle_targets,
        "expected_subtitle_paths": expected_subtitle_targets,
        "source_nfo_paths": source_nfo_paths,
        "source_subtitle_paths": source_subtitle_paths,
        "actions": actions,
        "exception": "",
    }


def _collect_scan(task_root: Path) -> Dict[Path, List[Path]]:
    """Enumerate direct files in every directory using one scandir traversal."""

    videos_by_parent: Dict[Path, List[Path]] = {}
    stack = [task_root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in EXCLUDED_NAMES or entry.name.startswith(TRASH_PREFIX):
                        continue
                    stack.append(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                file_path = Path(entry.path)
                if file_path.suffix.casefold() in VIDEO_EXTENSIONS:
                    videos_by_parent.setdefault(current, []).append(file_path)
    return {
        parent: sorted(paths, key=lambda path: str(path))
        for parent, paths in videos_by_parent.items()
    }


def _contract_hash() -> str:
    contract = Path(__file__).resolve().parents[1] / "references" / "naming-contract.md"
    try:
        return hashlib.sha256(contract.read_bytes()).hexdigest()
    except OSError:
        return ""


def _plan_signature(
    bundles: Iterable[Dict[str, object]],
    wrapper_actions: Optional[Iterable[Dict[str, object]]] = None,
    director_actions: Optional[Iterable[Dict[str, object]]] = None,
    metadata: Optional[Dict[str, object]] = None,
) -> str:
    payload_object: object = list(bundles)
    if wrapper_actions is not None or director_actions is not None:
        payload_object = {
            "bundles": list(payload_object),
            "wrapper_actions": list(wrapper_actions or []),
            "director_actions": list(director_actions or []),
        }
    if metadata is not None:
        payload_object = {"payload": payload_object, "metadata": metadata}
    payload = json.dumps(payload_object, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _mark_exception(bundle: Dict[str, object], reason: str) -> None:
    bundle["status"] = "EXCEPTION"
    bundle["exception"] = reason
    bundle["actions"] = []


def _write_large_library_checkpoints(
    root: Path,
    plan: Dict[str, object],
    inventory_payload: Sequence[Dict[str, object]],
) -> None:
    """Persist compact machine-readable checkpoints for long-running batches.

    These files are continuity aids only.  They never authorize completion;
    ``audit`` must rescan the live tree before the next batch is opened.
    """

    work = root / WORK_RECORD_DIR
    work.mkdir(parents=True, exist_ok=True)
    inventory_path = work / "inventory.jsonl"
    inventory_lines: List[str] = []
    bundles = plan.get("bundles", [])
    bundle_by_parent = {
        str(item.get("source_movie_dir", "")): item
        for item in bundles
        if isinstance(item, dict)
    }
    for item in inventory_payload:
        parent = str(item.get("parent", ""))
        bundle = bundle_by_parent.get(parent, {})
        inventory_lines.append(
            json.dumps(
                {
                    "parent": parent,
                    "videos": item.get("videos", []),
                    "status": bundle.get("status", "UNACCOUNTED"),
                    "source_shape": bundle.get("source_shape", ""),
                    "director": bundle.get("source_director_dir", ""),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    temporary_inventory = inventory_path.with_name(
        f".{inventory_path.name}.tmp-{os.getpid()}-{_timestamp()}"
    )
    temporary_inventory.write_text(
        "\n".join(inventory_lines) + ("\n" if inventory_lines else ""),
        encoding="utf-8",
    )
    temporary_inventory.replace(inventory_path)

    summary = plan.get("summary", {}) if isinstance(plan.get("summary"), dict) else {}
    progress = {
        "schema": "movie-organizing-progress/v1",
        "version": VERSION,
        "task_root": str(root),
        "large_library_mode": bool(plan.get("large_library_mode")),
        "sealed": False,
        "current_batch": {
            "plan_hash": plan.get("plan_hash", ""),
            "director": plan.get("batch_director", ""),
            "selected_units": summary.get("selected_units", 0),
            "batch_limit": plan.get("batch_limit", MAX_SELECTED_ACTION_UNITS),
        },
        "counts": {
            "total_units": summary.get("total_units", 0),
            "active_video_count": summary.get("active_video_count", 0),
            "remaining_action_units": summary.get("action_required", 0),
            "deferred_action_units": summary.get("deferred_action_units", 0),
        },
        "next_allowed": "preprocess",
    }
    progress_path = work / "progress.json"
    temporary_progress = progress_path.with_name(
        f".{progress_path.name}.tmp-{os.getpid()}-{_timestamp()}"
    )
    temporary_progress.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_progress.replace(progress_path)


def _mark_batch_sealed(root: Path, plan: Dict[str, object], seal_path: Path) -> None:
    """Mark one batch sealed only after ``seal_plan`` passed formal verify."""

    _validate_recovery_tree(root)
    work = root / WORK_RECORD_DIR
    progress_path = work / "progress.json"
    if not progress_path.is_file() or progress_path.is_symlink():
        raise OSError("large-library progress checkpoint is missing or unsafe")
    try:
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise OSError(f"large-library progress checkpoint is invalid: {error}") from error
    if not isinstance(progress, dict):
        raise OSError("large-library progress checkpoint must be an object")
    current = progress.get("current_batch") if isinstance(progress.get("current_batch"), dict) else {}
    if current.get("plan_hash") != plan.get("plan_hash"):
        raise OSError("large-library progress checkpoint plan hash drifted before seal")
    progress.update(
        {
            "sealed": True,
            "sealed_plan_hash": plan.get("plan_hash", ""),
            "sealed_result_path": str(seal_path),
            "sealed_at": datetime.now().isoformat(timespec="seconds"),
            "next_allowed": "audit",
        }
    )
    temporary = progress_path.with_name(f".{progress_path.name}.tmp-{os.getpid()}-{_timestamp()}")
    temporary.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(progress_path)


def _destination_key(path: str | Path) -> Tuple[str, str]:
    destination = _canonical(path)
    return str(_canonical(destination.parent)), _name_key(destination.name)


def _bundle_wrapper(bundle: Dict[str, object], root: Path) -> Optional[Path]:
    """Return the topmost wrapper below a director anchor, if any."""

    source_value = bundle.get("source_movie_dir")
    director_value = bundle.get("source_director_dir")
    if not source_value or not director_value:
        return None
    source = _canonical(str(source_value))
    director = _canonical(str(director_value))
    if (
        director == _canonical(root)
        or not _inside(root, director, allow_root=False)
        or not _inside(root, source, allow_root=False)
    ):
        return None
    try:
        relative = source.relative_to(director).parts
    except ValueError:
        return None
    if not relative:
        return None
    if len(relative) == 1:
        # A direct standard movie directory is itself the movie unit, not a
        # wrapper.  A non-standard/orphan directory containing a loose video
        # is a real wrapper and may be archived once its contents move out.
        if bundle.get("source_shape") in {"orphan", "dispersed"} and _parse_movie_dir(source.name) is None:
            return source
        return None
    return director / relative[0]


def _archive_wrapper_target(root: Path, wrapper: Path) -> Path:
    stable_key = hashlib.sha256(str(_canonical(wrapper)).encode("utf-8")).hexdigest()[:12]
    return root / WORK_RECORD_DIR / "flattened-empty" / f"{stable_key}-{wrapper.name}"


def _wrapper_files_are_accounted(
    wrapper: Path, bundles: Sequence[Dict[str, object]]
) -> Tuple[bool, str]:
    """Prove a wrapper will contain only empty directories after child moves."""

    known_files = set()
    for bundle in bundles:
        for key in ("expected_video_source", "source_nfo_paths", "source_subtitle_paths"):
            value = bundle.get(key)
            values = value if isinstance(value, list) else [value]
            for path_value in values:
                if path_value:
                    known_files.add(_canonical(str(path_value)))
    stack = [wrapper]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            return False, f"wrapper scan failed: {error}"
        for entry in entries:
            item = Path(entry.path)
            if entry.is_symlink():
                return False, f"wrapper contains symlink: {item}"
            if entry.is_dir(follow_symlinks=False):
                stack.append(item)
                continue
            if entry.is_file(follow_symlinks=False):
                if _canonical(item) not in known_files:
                    return False, f"wrapper contains unaccounted file: {item}"
                continue
            return False, f"wrapper contains unsupported entry: {item}"
    return True, ""


def _wrapper_is_empty_skeleton(wrapper: Path) -> Tuple[bool, str]:
    """Recheck a wrapper immediately before archive; never follow links."""

    wrapper = _lexical(wrapper)
    try:
        mode = os.lstat(wrapper).st_mode
    except OSError as error:
        return False, f"wrapper cannot be inspected immediately before archive: {error}"
    if not stat.S_ISDIR(mode):
        return False, f"wrapper is not a real directory immediately before archive: {wrapper}"

    stack = [wrapper]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            return False, f"wrapper cannot be rescanned immediately before archive: {error}"
        for entry in entries:
            item = _lexical(entry.path)
            try:
                item_mode = os.lstat(item).st_mode
            except OSError as error:
                return False, f"wrapper entry cannot be inspected immediately before archive: {error}"
            if stat.S_ISLNK(item_mode):
                return False, f"wrapper changed after bundle actions; symlink found: {item}"
            if stat.S_ISDIR(item_mode):
                stack.append(item)
                continue
            return False, f"wrapper changed after bundle actions; non-directory entry found: {item}"
    return True, ""


def _mark_director_target_collisions(root: Path, bundles: Sequence[Dict[str, object]]) -> None:
    """Mark every unit of a director whose normalized target is occupied."""

    groups: Dict[Path, List[Dict[str, object]]] = {}
    for bundle in bundles:
        source_value = bundle.get("source_director_dir")
        if source_value:
            groups.setdefault(_canonical(str(source_value)), []).append(bundle)
    target_owners: Dict[Tuple[str, str], Path] = {}
    for source, group in groups.items():
        expected_value = group[0].get("expected_director_dir")
        if not expected_value:
            continue
        expected = _canonical(str(expected_value))
        if source == expected:
            continue
        target_key = _destination_key(expected)
        owner = target_owners.get(target_key)
        if owner is not None and owner != source:
            for item in groups[owner] + group:
                _mark_exception(item, f"multiple source directors normalize to target: {expected}")
            continue
        target_owners[target_key] = source
        if expected.exists() or _conflicting_name(expected.parent, expected.name, ignore=source):
            for item in group:
                _mark_exception(item, f"target director exists or collides: {expected}")


def _plan_wrapper_actions(root: Path, bundles: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    groups: Dict[Path, List[Dict[str, object]]] = {}
    for bundle in bundles:
        wrapper = _bundle_wrapper(bundle, root)
        if wrapper is not None:
            groups.setdefault(_canonical(wrapper), []).append(bundle)
    safe: List[Tuple[Path, List[Dict[str, object]]]] = []
    for wrapper, group in sorted(groups.items(), key=lambda item: str(item[0])):
        if any(item.get("status") == "EXCEPTION" for item in group):
            for item in group:
                _mark_exception(item, "wrapper contains an unresolved movie unit; flatten is all-or-nothing")
            continue
        # A wrapper cannot be archived while one of its ACTION_REQUIRED
        # children has been deferred to a later <=20-unit batch.  Moving the
        # selected children is safe, but the wrapper must remain in place until
        # every child has been handled.
        if any(
            item.get("status") == "ACTION_REQUIRED"
            and item.get("selected_for_apply") is not True
            for item in group
        ):
            continue
        accounted, reason = _wrapper_files_are_accounted(wrapper, group)
        if not accounted:
            for item in group:
                _mark_exception(item, reason)
            continue
        target = _archive_wrapper_target(root, wrapper)
        if target.exists() or _conflicting_name(target.parent, target.name):
            for item in group:
                _mark_exception(item, f"flattened-empty archive target collision: {target}")
            continue
        safe.append((wrapper, group))
    if not safe:
        return []
    archive_parent = root / WORK_RECORD_DIR / "flattened-empty"
    if os.path.lexists(archive_parent):
        if archive_parent.is_symlink() or not archive_parent.is_dir() or not _inside(root, archive_parent, allow_root=False):
            for _wrapper, group in safe:
                for item in group:
                    _mark_exception(item, f"flattened-empty archive parent is not a real in-root directory: {archive_parent}")
            return []
        actions: List[Dict[str, object]] = []
    else:
        actions = [_action(
            "wrapper-mkdir",
            "mkdir",
            source=None,
            target=archive_parent,
            evidence="create reversible archive for proven empty wrapper skeletons",
            rollback="move archive directory back under TASK_ROOT/_work-record_",
            preconditions=["target absent", "_work-record_ is an in-root directory"],
            postconditions=["target directory exists"],
        )]
    for wrapper, _group in safe:
        target = _archive_wrapper_target(root, wrapper)
        key = hashlib.sha256(str(wrapper).encode("utf-8")).hexdigest()[:12]
        actions.append(_action(
            f"wrapper-archive-{key}",
            "rename_dir",
            source=wrapper,
            target=target,
            evidence="all child movie bundles rehomed; wrapper proven empty directory skeleton",
            rollback="rename flattened-empty archive back to original wrapper path",
            preconditions=["all child movie actions succeeded", "source has no files or symlinks", "target absent"],
            postconditions=["source wrapper absent", "archive skeleton exists under _work-record_"],
        ))
    return actions


def _plan_director_actions(root: Path, bundles: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    groups: Dict[Path, List[Dict[str, object]]] = {}
    for bundle in bundles:
        source_value = bundle.get("source_director_dir")
        if source_value:
            groups.setdefault(_canonical(str(source_value)), []).append(bundle)
    actions: List[Dict[str, object]] = []
    for source, group in sorted(groups.items(), key=lambda item: str(item[0])):
        expected_value = group[0].get("expected_director_dir")
        if not expected_value:
            continue
        expected = _canonical(str(expected_value))
        if source == expected or any(
            item.get("status") == "EXCEPTION"
            or (
                item.get("status") == "ACTION_REQUIRED"
                and item.get("selected_for_apply") is not True
            )
            for item in group
        ):
            continue
        if not source.is_dir() or expected.exists() or _conflicting_name(expected.parent, expected.name, ignore=source):
            for item in group:
                _mark_exception(item, f"director rename blocked by target collision or missing source: {expected}")
            continue
        key = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:12]
        actions.append(_action(
            f"director-rename-{key}",
            "rename_dir",
            source=source,
            target=expected,
            evidence="v1.3.3 separator migration: normalize foreign Chinese name segments to U+00B7",
            rollback="rename normalized director directory back to source directory",
            preconditions=["all child bundle actions and wrapper archives succeeded", "source director exists", "target absent"],
            postconditions=["source director absent", "normalized director exists"],
        ))
    return actions


def make_plan(task_root: str | Path, *, persist: bool = True) -> Dict[str, object]:
    root = _canonical(task_root)
    if not root.is_dir():
        raise ValueError("TASK_ROOT does not exist or is not a directory")
    contract_hash = _contract_hash()
    if not contract_hash or contract_hash != EXPECTED_NAMING_CONTRACT_SHA256:
        raise ValueError("naming-contract hash mismatch or missing")
    _validate_recovery_tree(root)

    scanned = _collect_scan(root)
    bundles = [
        _build_bundle(parent, videos, root)
        for parent, videos in sorted(scanned.items(), key=lambda item: str(item[0]))
    ]
    # Two independent units planning the same destination cannot be applied
    # safely as a batch. Isolate both before any mutation.
    destination_owners: Dict[Tuple[str, str], Dict[str, object]] = {}
    for bundle in bundles:
        if bundle.get("status") not in {"NAMING_PASS", "ACTION_REQUIRED"}:
            continue
        destination_value = bundle.get("expected_movie_dir_path")
        source_value = bundle.get("source_movie_dir")
        if not destination_value or not source_value:
            continue
        destination_key = _destination_key(str(destination_value))
        owner = destination_owners.get(destination_key)
        if owner and owner.get("source_movie_dir") != source_value:
            _mark_exception(bundle, f"target collision with {owner.get('source_movie_dir')}")
            _mark_exception(owner, f"target collision with {source_value}")
        else:
            destination_owners[destination_key] = bundle
    # A director target collision is a batch-level conflict: no child of that
    # director may mutate while the parent cannot be renamed safely.
    _mark_director_target_collisions(root, bundles)
    # Keep the complete inventory in the plan, but select a bounded batch of
    # ACTION_REQUIRED units for this apply.  Large libraries are deliberately
    # narrowed to one director and ten units so a long-running Agent never
    # carries a whole library in context.  Deferred units remain
    # ACTION_REQUIRED (never a false NAMING_PASS) and are selected by the next
    # fresh plan after this batch is verified.
    action_units = [
        item
        for item in bundles
        if item.get("status") == "ACTION_REQUIRED"
    ]
    director_keys = sorted(
        {
            str(item.get("source_director_dir", ""))
            for item in bundles
            if item.get("source_director_dir")
        }
    )
    estimated_actions = sum(len(item.get("actions", [])) for item in bundles)
    # ``bundles`` are filesystem units and a collection bundle can contain
    # several active videos.  Large-library mode is triggered by the actual
    # active video count, not merely by the number of parent directories.
    active_video_count = sum(
        len(videos)
        for videos in scanned.values()
    )
    large_library_mode = bool(
        active_video_count > LARGE_LIBRARY_VIDEO_THRESHOLD
        or len(director_keys) > LARGE_LIBRARY_DIRECTOR_THRESHOLD
        or estimated_actions > LARGE_LIBRARY_ACTION_THRESHOLD
    )
    batch_director = ""
    if large_library_mode and action_units:
        action_directors = sorted(
            {
                str(item.get("source_director_dir", ""))
                for item in action_units
                if item.get("source_director_dir")
            }
        )
        batch_director = action_directors[0] if action_directors else ""
    for item in bundles:
        item["selected_for_apply"] = False
    selected_action_units = (
        [
            item
            for item in action_units
            if str(item.get("source_director_dir", "")) == batch_director
        ][:LARGE_LIBRARY_BATCH_LIMIT]
        if large_library_mode
        else action_units[:MAX_SELECTED_ACTION_UNITS]
    )
    for item in selected_action_units:
        item["selected_for_apply"] = True
    wrapper_actions = _plan_wrapper_actions(root, bundles)
    director_actions = _plan_director_actions(root, bundles)
    summary = {
        "total_units": len(bundles),
        "naming_pass": sum(item["status"] == "NAMING_PASS" for item in bundles),
        "action_required": sum(item["status"] == "ACTION_REQUIRED" for item in bundles),
        "exception": sum(item["status"] == "EXCEPTION" for item in bundles),
        "selected_action_units": sum(
            item.get("status") == "ACTION_REQUIRED"
            and item.get("selected_for_apply") is True
            for item in bundles
        ),
        "deferred_action_units": sum(
            item.get("status") == "ACTION_REQUIRED"
            and item.get("selected_for_apply") is not True
            for item in bundles
        ),
        "planned_actions": (
            sum(
                len(item["actions"])
                for item in bundles
                if item.get("status") == "ACTION_REQUIRED"
                and item.get("selected_for_apply") is True
            )
            + len(wrapper_actions)
            + len(director_actions)
        ),
        "wrapper_archives": sum(1 for item in wrapper_actions if item.get("action") == "rename_dir"),
        "director_renames": len(director_actions),
        "large_library_mode": large_library_mode,
        "director_count": len(director_keys),
        "active_video_count": active_video_count,
        "estimated_actions": estimated_actions,
        "batch_limit": LARGE_LIBRARY_BATCH_LIMIT if large_library_mode else MAX_SELECTED_ACTION_UNITS,
        "batch_director": batch_director,
        "selected_units": len(selected_action_units),
    }
    inventory_payload = [
        {"parent": str(parent), "videos": [str(video) for video in videos]}
        for parent, videos in sorted(scanned.items(), key=lambda item: str(item[0]))
    ]
    scan_id = hashlib.sha256(
        json.dumps(inventory_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    report: Dict[str, object] = {
        "schema": "movie-organizing-preprocessor/v1",
        "version": VERSION,
        "plan_kind": "naming",
        "task_root": str(root),
        "standard_id": "movie-organizing",
        "naming_contract_sha256": contract_hash,
        "scan_id": scan_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "bundles": bundles,
        "wrapper_actions": wrapper_actions,
        "director_actions": director_actions,
        "large_library_mode": large_library_mode,
        "batch_limit": LARGE_LIBRARY_BATCH_LIMIT if large_library_mode else MAX_SELECTED_ACTION_UNITS,
        "batch_director": batch_director,
    }
    report["plan_hash"] = _plan_signature(
        bundles,
        wrapper_actions,
        director_actions,
        metadata={
            "large_library_mode": large_library_mode,
            "batch_limit": report["batch_limit"],
            "batch_director": batch_director,
            "summary": summary,
        },
    )

    if persist:
        _validate_recovery_tree(root)
        recovery = root / WORK_RECORD_DIR / "recovery"
        recovery.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        report_path = recovery / f"plan-{timestamp}.json"
        report["plan_path"] = str(report_path)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _write_large_library_checkpoints(root, report, inventory_payload)
    else:
        report["plan_path"] = ""
    return report


def _validate_action(
    action: Dict[str, object], root: Path, planned_dirs: Optional[set[Path]] = None
) -> Optional[str]:
    name = str(action.get("action", action.get("type", "")))
    target_lexical = _lexical(str(action.get("target", "")))
    target = _canonical(target_lexical)
    source_value = action.get("source")
    source_lexical = _lexical(str(source_value)) if source_value else None
    source = _canonical(source_lexical) if source_lexical is not None else None
    try:
        target_mode = os.lstat(target_lexical).st_mode
    except FileNotFoundError:
        target_mode = None
    except OSError as error:
        return f"target cannot be inspected: {error}"
    if target_mode is not None and stat.S_ISLNK(target_mode):
        return f"target must not be a symlink: {target_lexical}"
    if source_lexical is not None:
        try:
            source_mode = os.lstat(source_lexical).st_mode
        except FileNotFoundError:
            source_mode = None
        except OSError as error:
            return f"source cannot be inspected: {error}"
        if source_mode is not None and stat.S_ISLNK(source_mode):
            return f"source must not be a symlink: {source_lexical}"
    if not _inside(root, target, allow_root=False):
        return f"outside task root: {target}"
    if source is not None and not _inside(root, source, allow_root=False):
        return f"outside task root: {source}"
    if name not in {"mkdir", "move_file", "rename_dir", "rename_path"}:
        return f"unsupported action: {name}"
    if planned_dirs is None:
        planned_dirs = set()
    if name == "mkdir":
        if target_mode is not None:
            return f"mkdir target exists: {target_lexical}"
        if not target_lexical.parent.is_dir() and _canonical(target_lexical.parent) not in planned_dirs:
            return f"mkdir parent missing: {target_lexical.parent}"
    elif name == "move_file":
        if source is None or source_mode is None or not stat.S_ISREG(source_mode):
            return f"missing source: {source_lexical if source_lexical is not None else source}"
        if target_mode is not None:
            return f"target exists: {target_lexical}"
        if not target_lexical.parent.is_dir() and _canonical(target_lexical.parent) not in planned_dirs:
            return f"target parent missing: {target_lexical.parent}"
    elif name == "rename_path":
        if source is None or source_mode is None:
            return f"missing source path: {source_lexical if source_lexical is not None else source}"
        if target_mode is not None:
            return f"target exists: {target_lexical}"
        if not target_lexical.parent.is_dir() and _canonical(target_lexical.parent) not in planned_dirs:
            return f"target parent missing: {target_lexical.parent}"
    else:
        if source is None or source_mode is None or not stat.S_ISDIR(source_mode):
            return f"missing source directory: {source_lexical if source_lexical is not None else source}"
        if target_mode is not None:
            return f"target directory exists: {target_lexical}"
        if not target_lexical.parent.is_dir() and _canonical(target_lexical.parent) not in planned_dirs:
            return f"target parent missing: {target_lexical.parent}"
    return None


def _verify_bundle(bundle: Dict[str, object], root: Path) -> List[str]:
    problems: List[str] = []
    expected_dir = _canonical(str(bundle.get("expected_movie_dir_path", "")))
    expected_video = _canonical(str(bundle.get("expected_video_target", "")))
    if not expected_dir.is_dir():
        problems.append(f"missing target dir: {expected_dir}")
    if not expected_video.is_file():
        problems.append(f"missing target video: {expected_video}")
    for key in ("expected_nfo_targets", "expected_subtitle_targets"):
        for target_value in bundle.get(key, []):
            target = _canonical(str(target_value))
            if not target.is_file():
                problems.append(f"missing target sidecar: {target}")

    if bundle.get("status") == "ACTION_REQUIRED":
        source_video_value = bundle.get("expected_video_source")
        if source_video_value:
            source_video = _canonical(str(source_video_value))
            if source_video != expected_video and source_video.exists():
                problems.append(f"old source still exists: {source_video}")
        source_dir = _canonical(str(bundle.get("source_movie_dir", "")))
        # For an orphan bundle, source_movie_dir is the director container
        # itself and must remain after the loose video is moved into its new
        # movie directory.  Standard/dispersed leaves, by contrast, are the
        # legacy movie directories that must disappear.
        if bundle.get("source_shape") != "orphan" and source_dir != expected_dir and source_dir.exists():
            problems.append(f"old movie dir still exists: {source_dir}")
        expected_targets = {
            _canonical(str(target))
            for key in ("expected_nfo_targets", "expected_subtitle_targets")
            for target in bundle.get(key, [])
        }
        for key in ("source_nfo_paths", "source_subtitle_paths"):
            for source_value in bundle.get(key, []):
                source = _canonical(str(source_value))
                if source.exists() and source not in expected_targets:
                    problems.append(f"old sidecar still exists: {source}")
    return problems


def _plan_integrity_error(plan: Dict[str, object], root: Path) -> Optional[str]:
    plan_root = _canonical(str(plan.get("task_root", "")))
    if plan_root != root:
        return "plan task_root does not exactly match provided TASK_ROOT"
    if plan.get("schema") != "movie-organizing-preprocessor/v1":
        return "plan schema mismatch"
    if plan.get("version") != VERSION:
        return "plan version mismatch"
    if plan.get("plan_kind") != "naming":
        return "plan_kind must be naming; slow_channel plans are not executable by the naming preprocessor"
    if plan.get("slow_channel") is True:
        return "slow_channel plans are not executable by the naming preprocessor"
    if plan.get("standard_id") != "movie-organizing":
        return "plan standard_id mismatch"
    if plan.get("naming_contract_sha256") != EXPECTED_NAMING_CONTRACT_SHA256:
        return "plan naming-contract hash mismatch"
    for key in ("wrapper_actions", "director_actions"):
        if not isinstance(plan.get(key, []), list):
            return f"plan {key} missing or invalid"
    bundles = plan.get("bundles")
    if not isinstance(bundles, list):
        return "plan bundles missing or invalid"
    for index, bundle in enumerate(bundles):
        if not isinstance(bundle, dict):
            return f"plan bundle {index} is not an object"
        if not isinstance(bundle.get("selected_for_apply"), bool):
            return f"plan bundle {index} selected_for_apply must be boolean"
    plan_hash = plan.get("plan_hash")
    if not isinstance(plan_hash, str) or not plan_hash:
        return "plan hash missing"
    if plan_hash != _plan_signature(
        plan.get("bundles", []),
        plan.get("wrapper_actions", []),
        plan.get("director_actions", []),
        metadata={
            "large_library_mode": plan.get("large_library_mode", False),
            "batch_limit": plan.get("batch_limit", MAX_SELECTED_ACTION_UNITS),
            "batch_director": plan.get("batch_director", ""),
            "summary": plan.get("summary", {}),
        },
    ):
        return "plan hash mismatch"
    return None


def _plan_argument_error(plan: object, supplied_path: str | Path, root: Path) -> Optional[str]:
    """Validate the explicit on-disk plan before any apply/verify work."""

    if not isinstance(plan, dict):
        return "plan JSON must be an object"
    supplied = Path(os.path.abspath(os.fspath(supplied_path)))
    if supplied.is_symlink():
        return "plan file must not be a symlink"
    try:
        mode = os.lstat(supplied).st_mode
    except OSError as error:
        return f"plan file cannot be inspected: {error}"
    if not stat.S_ISREG(mode):
        return "plan file must be a regular file"
    if not _inside(root, supplied, allow_root=False):
        return "plan file must be inside TASK_ROOT/_work-record_/recovery"
    recovery = root / WORK_RECORD_DIR / "recovery"
    try:
        # Check the canonical entity, not just the lexical spelling: a
        # symlinked child directory under recovery must not smuggle a plan
        # from an alternate in-root location into the execution path.
        _canonical(supplied).relative_to(_canonical(recovery))
    except ValueError:
        return "plan file must be inside TASK_ROOT/_work-record_/recovery"
    declared_path = plan.get("plan_path")
    if not isinstance(declared_path, str) or not declared_path:
        return "plan_path missing"
    if _canonical(declared_path) != _canonical(supplied):
        return "plan_path does not match the supplied plan file"
    if plan.get("schema") != "movie-organizing-preprocessor/v1":
        return "plan schema mismatch"
    if plan.get("version") != VERSION:
        return "plan version mismatch"
    if plan.get("plan_kind") != "naming":
        return "plan rejected: plan_kind must be naming; slow_channel plans are not executable"
    if plan.get("slow_channel") is True:
        return "plan rejected: slow_channel plans are not executable"
    if plan.get("standard_id") != "movie-organizing":
        return "plan standard_id mismatch"
    if plan.get("naming_contract_sha256") != EXPECTED_NAMING_CONTRACT_SHA256:
        return "plan naming-contract hash mismatch"
    if not isinstance(plan.get("scan_id"), str) or not plan.get("scan_id"):
        return "plan scan_id missing"
    if not isinstance(plan.get("bundles"), list):
        return "plan bundles missing or invalid"
    for index, bundle in enumerate(plan["bundles"]):
        if not isinstance(bundle, dict):
            return f"plan bundle {index} is not an object"
        if not isinstance(bundle.get("selected_for_apply"), bool):
            return f"plan bundle {index} selected_for_apply must be boolean"
    return _plan_integrity_error(plan, root)


def _fresh_plan_error(plan: Dict[str, object], root: Path) -> Optional[str]:
    try:
        fresh = make_plan(root, persist=False)
    except (OSError, ValueError) as error:
        return f"fresh plan failed: {error}"
    for field in (
        "task_root",
        "version",
        "plan_kind",
        "standard_id",
        "naming_contract_sha256",
        "scan_id",
        "plan_hash",
    ):
        if field == "task_root":
            if _canonical(str(plan.get(field, ""))) != _canonical(str(fresh.get(field, ""))):
                return "plan task_root does not match the fresh TASK_ROOT"
        elif plan.get(field) != fresh.get(field):
            return f"plan {field} does not match the fresh TASK_ROOT scan"
    return None


def _matching_recovery_result(
    root: Path, plan_hash: str, *, mode: str, dry_run: Optional[bool]
) -> bool:
    """Find a generated result record without following links or leaving recovery."""

    recovery = root / WORK_RECORD_DIR / "recovery"
    if not recovery.is_dir() or recovery.is_symlink():
        return False
    try:
        entries = list(os.scandir(recovery))
    except OSError:
        return False
    for entry in entries:
        path = Path(entry.path)
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            continue
        if path.suffix.casefold() != ".json":
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        if record.get("schema") != "movie-organizing-preprocessor/result/v1":
            continue
        if record.get("mode") != mode or record.get("status") != "PASS":
            continue
        if record.get("task_root") != str(root) or record.get("plan_hash") != plan_hash:
            continue
        if dry_run is not None and record.get("dry_run") is not dry_run:
            continue
        return True
    return False


def _verify_auxiliary_actions(plan: Dict[str, object], root: Path) -> List[str]:
    problems: List[str] = []
    for key in ("wrapper_actions", "director_actions"):
        for action in plan.get(key, []):
            name = str(action.get("action", action.get("type", "")))
            target = _canonical(str(action.get("target", "")))
            source_value = action.get("source")
            source = _canonical(str(source_value)) if source_value else None
            if name == "mkdir" and not target.is_dir():
                problems.append(f"missing auxiliary directory target: {target}")
            elif name == "rename_dir":
                if source is not None and source.exists():
                    problems.append(f"old auxiliary directory still exists: {source}")
                if not target.is_dir():
                    problems.append(f"missing auxiliary directory target: {target}")
    return problems


def verify_plan(plan: Dict[str, object], root: str | Path) -> Dict[str, object]:
    root_path = _canonical(root)
    integrity_error = _plan_integrity_error(plan, root_path)
    if integrity_error:
        return {
            "status": "FAIL",
            "naming_plan_only": True,
            "missing": [integrity_error],
            "error_summary": integrity_error,
        }
    missing: List[str] = []
    for bundle in plan.get("bundles", []):
        if bundle.get("status") in {"NAMING_PASS", "ACTION_REQUIRED"}:
            # A bounded plan intentionally carries deferred ACTION_REQUIRED
            # units for inventory continuity.  They are not part of this
            # apply/verify batch and must not make the selected batch fail.
            if (
                bundle.get("status") == "ACTION_REQUIRED"
                and bundle.get("selected_for_apply") is False
            ):
                continue
            missing.extend(_verify_bundle(bundle, root_path))
    missing.extend(_verify_auxiliary_actions(plan, root_path))
    return {
        "status": "PASS" if not missing else "FAIL",
        "naming_plan_only": True,
        "missing": missing,
        "error_summary": "; ".join(missing),
    }


def _empty_apply_recovery(*, status: str = "PASS") -> Dict[str, object]:
    """Return explicit recovery fields for an apply with no mutations."""

    return {
        "rollback_status": status,
        "rolled_back_actions": 0,
        "manual_recovery_required": status == "FAIL",
        "action_journal": [],
    }


def _rollback_executed_actions(
    root: Path,
    plan: Dict[str, object],
    executed_actions: Sequence[Dict[str, object]],
    action_journal: List[Dict[str, object]],
) -> Tuple[str, int, bool, str]:
    """Reverse successful actions without deleting anything.

    Rename/move actions are returned to their original source path.  Directories
    created by this plan must be empty before being moved into a recoverable
    rollback archive; a non-empty or otherwise unsafe target leaves the caller
    with an explicit manual-recovery requirement.
    """

    if not executed_actions:
        return "PASS", 0, False, ""

    plan_hash = str(plan.get("plan_hash", "unknown"))
    rollback_root = root / WORK_RECORD_DIR / "recovery" / f"rollback-{plan_hash}"
    try:
        _validate_recovery_tree(root)
        rollback_root.mkdir(parents=True, exist_ok=True)
        if not rollback_root.is_dir() or rollback_root.is_symlink() or not _inside(
            root, rollback_root, allow_root=False
        ):
            raise OSError(f"rollback directory is not a real in-root directory: {rollback_root}")
    except OSError as error:
        return "FAIL", 0, True, f"rollback setup failed: {error}"

    rolled_back = 0
    errors: List[str] = []
    # Journal entries are one-per-successful action.  Update each entry in
    # place so the final record remains compact and directly auditable.
    journal_by_id = {str(item.get("id")): item for item in action_journal}
    for reverse_index, action in enumerate(reversed(executed_actions), start=1):
        action_id = str(action.get("id", ""))
        name = str(action.get("action", action.get("type", "")))
        target = _lexical(str(action.get("target", "")))
        source_value = action.get("source")
        source = _lexical(str(source_value)) if source_value else None
        try:
            if name == "mkdir":
                mode = os.lstat(target).st_mode
                if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
                    raise OSError(f"created directory is not a real directory: {target}")
                with os.scandir(target) as entries:
                    if next(entries, None) is not None:
                        raise OSError(f"created directory is not empty: {target}")
                rollback_target = rollback_root / f"{reverse_index:04d}-{target.name}"
                if os.path.lexists(rollback_target):
                    raise OSError(f"rollback target already exists: {rollback_target}")
                target.rename(rollback_target)
            elif name in {"move_file", "rename_dir", "rename_path"} and source is not None:
                target_mode = os.lstat(target).st_mode
                if stat.S_ISLNK(target_mode):
                    raise OSError(f"rollback source is a symlink: {target}")
                if os.path.lexists(source):
                    raise OSError(f"rollback destination already exists: {source}")
                if not source.parent.is_dir():
                    raise OSError(f"rollback destination parent is missing: {source.parent}")
                target.rename(source)
            else:
                raise OSError(f"unsupported rollback action: {name}")
        except (OSError, StopIteration) as error:
            errors.append(f"{action_id or name}: {error}")
            journal_by_id.get(action_id, {}).update(
                {"status": "ROLLBACK_FAILED", "rollback_error": str(error)}
            )
            continue
        rolled_back += 1
        journal_by_id.get(action_id, {}).update({"status": "ROLLED_BACK"})

    if errors:
        return "FAIL", rolled_back, True, "; ".join(errors)
    return "PASS", rolled_back, False, ""


def execute_action_plan(
    plan: Dict[str, object],
    root: str | Path,
    actions: Sequence[Dict[str, object]],
    *,
    dry_run: bool = False,
    verify_callback: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Dict[str, object]:
    """Execute a bounded generic action list with the preprocessor rollback engine.

    The slow channel uses ``mkdir`` and ``rename_path`` only.  Keeping the
    preflight, immediate re-check, action journal, and reverse rollback here
    prevents it from growing a second mutation engine while preserving the
    naming preprocessor's existing ``apply_plan`` behavior.
    """

    root_path = _canonical(root)
    if _canonical(str(plan.get("task_root", ""))) != root_path:
        return {
            "status": "FAIL",
            "executed_actions": 0,
            "error_summary": "plan task_root mismatch or outside task root",
            **_empty_apply_recovery(),
        }

    planned_dirs: set[Path] = set()
    for action in actions:
        if not isinstance(action, dict):
            return {
                "status": "FAIL",
                "executed_actions": 0,
                "error_summary": "action must be an object",
                **_empty_apply_recovery(),
            }
        failure = _validate_action(action, root_path, planned_dirs)
        if failure:
            return {
                "status": "FAIL",
                "executed_actions": 0,
                "error_summary": failure,
                **_empty_apply_recovery(),
            }
        if str(action.get("action", action.get("type", ""))) == "mkdir":
            planned_dirs.add(_canonical(str(action["target"])))

    if dry_run:
        return {
            "status": "PASS",
            "dry_run": True,
            "planned_actions": len(actions),
            "executed_actions": 0,
            "error_summary": "",
            "rollback_status": "NOT_RUN",
            "rolled_back_actions": 0,
            "manual_recovery_required": False,
            "action_journal": [],
        }

    executed_actions: List[Dict[str, object]] = []
    action_journal: List[Dict[str, object]] = []
    executed = 0
    for action in actions:
        failure = _validate_action(action, root_path, planned_dirs)
        if failure:
            rollback_status, rolled_back, manual_recovery, rollback_error = _rollback_executed_actions(
                root_path, plan, executed_actions, action_journal
            )
            details = f"apply blocked: {failure}"
            if rollback_error:
                details += f"; rollback: {rollback_error}"
            return {
                "status": "FAIL",
                "executed_actions": executed,
                "error_summary": details,
                "rollback_status": rollback_status,
                "rolled_back_actions": rolled_back,
                "manual_recovery_required": manual_recovery,
                "action_journal": action_journal,
            }
        name = str(action.get("action", action.get("type", "")))
        target = _lexical(str(action.get("target", "")))
        try:
            if name == "mkdir":
                target.mkdir()
            else:
                source = _lexical(str(action["source"]))
                source.rename(target)
        except OSError as error:
            rollback_status, rolled_back, manual_recovery, rollback_error = _rollback_executed_actions(
                root_path, plan, executed_actions, action_journal
            )
            details = f"apply failed: {error}"
            if rollback_error:
                details += f"; rollback: {rollback_error}"
            return {
                "status": "FAIL",
                "executed_actions": executed,
                "error_summary": details,
                "rollback_status": rollback_status,
                "rolled_back_actions": rolled_back,
                "manual_recovery_required": manual_recovery,
                "action_journal": action_journal,
            }
        executed += 1
        executed_actions.append(action)
        action_journal.append(
            {
                "id": str(action.get("id", "")),
                "action": name,
                "source": str(action.get("source", "")),
                "target": str(action.get("target", "")),
                "status": "APPLIED",
            }
        )

    if verify_callback is not None:
        try:
            verification = verify_callback()
        except Exception as error:  # pragma: no cover - defensive boundary
            verification = {"status": "FAIL", "error_summary": f"verification raised: {error}"}
        if not isinstance(verification, dict) or verification.get("status") != "PASS":
            rollback_status, rolled_back, manual_recovery, rollback_error = _rollback_executed_actions(
                root_path, plan, executed_actions, action_journal
            )
            details = "post-apply verification failed: " + str(
                verification.get("error_summary", "verification failed")
                if isinstance(verification, dict)
                else "verification returned invalid result"
            )
            if rollback_error:
                details += f"; rollback: {rollback_error}"
            return {
                "status": "FAIL",
                "executed_actions": executed,
                "error_summary": details,
                "rollback_status": rollback_status,
                "rolled_back_actions": rolled_back,
                "manual_recovery_required": manual_recovery,
                "action_journal": action_journal,
            }

    return {
        "status": "PASS",
        "planned_actions": len(actions),
        "executed_actions": executed,
        "error_summary": "",
        "rollback_status": "NOT_RUN",
        "rolled_back_actions": 0,
        "manual_recovery_required": False,
        "action_journal": action_journal,
    }


def apply_plan(plan: Dict[str, object], root: str | Path, dry_run: bool = False) -> Dict[str, object]:
    root_path = _canonical(root)
    plan_root = _canonical(str(plan.get("task_root", "")))
    if plan_root != root_path:
        return {
            "status": "FAIL",
            "executed_actions": 0,
            "error_summary": "plan task_root mismatch or outside task root",
            **_empty_apply_recovery(),
        }

    bundle_actions: List[Dict[str, object]] = []
    planned_dirs: set[Path] = set()
    for bundle in plan.get("bundles", []):
        if (
            bundle.get("status") != "ACTION_REQUIRED"
            or bundle.get("selected_for_apply") is False
        ):
            continue
        for action in bundle.get("actions", []):
            failure = _validate_action(action, root_path, planned_dirs)
            if failure:
                return {
                    "status": "FAIL",
                    "executed_actions": 0,
                    "error_summary": failure,
                    **_empty_apply_recovery(),
                }
            bundle_actions.append(action)
            if str(action.get("action", action.get("type", ""))) == "mkdir":
                planned_dirs.add(_canonical(str(action["target"])))

    wrapper_actions = list(plan.get("wrapper_actions", []))
    director_actions = list(plan.get("director_actions", []))
    for phase_actions in (wrapper_actions, director_actions):
        for action in phase_actions:
            failure = _validate_action(action, root_path, planned_dirs)
            if failure:
                return {
                    "status": "FAIL",
                    "executed_actions": 0,
                    "error_summary": failure,
                    **_empty_apply_recovery(),
                }
            if str(action.get("action", action.get("type", ""))) == "mkdir":
                planned_dirs.add(_canonical(str(action["target"])))

    integrity_error = _plan_integrity_error(plan, root_path)
    if integrity_error:
        return {
            "status": "FAIL",
            "executed_actions": 0,
            "error_summary": integrity_error,
            **_empty_apply_recovery(),
        }

    if dry_run:
        return {
            "status": "PASS",
            "dry_run": True,
            "planned_actions": len(bundle_actions) + len(wrapper_actions) + len(director_actions),
            "executed_actions": 0,
            "error_summary": "",
            "rollback_status": "NOT_RUN",
            "rolled_back_actions": 0,
            "manual_recovery_required": False,
            "action_journal": [],
        }

    executed = 0
    executed_actions: List[Dict[str, object]] = []
    action_journal: List[Dict[str, object]] = []

    def execute_phase(phase_actions: Sequence[Dict[str, object]], phase_name: str) -> Optional[str]:
        nonlocal executed
        for action in phase_actions:
            # The filesystem may change between global preflight and this
            # action. Re-lstat source/target immediately before every mutate.
            failure = _validate_action(action, root_path, planned_dirs)
            if failure:
                return failure
            name = str(action.get("action", action.get("type", "")))
            if phase_name == "wrapper" and name == "rename_dir":
                source = _lexical(str(action["source"]))
                safe, reason = _wrapper_is_empty_skeleton(source)
                if not safe:
                    return reason
            target = _lexical(str(action["target"]))
            try:
                if name == "mkdir":
                    target.mkdir()
                else:
                    source = _lexical(str(action["source"]))
                    source.rename(target)
            except OSError as error:
                return f"apply failed: {error}"
            executed += 1
            executed_actions.append(action)
            action_journal.append(
                {
                    "id": str(action.get("id", "")),
                    "action": name,
                    "source": str(action.get("source", "")),
                    "target": str(action.get("target", "")),
                    "status": "APPLIED",
                }
            )
        return None

    for phase_name, phase_actions in (
        ("bundle", bundle_actions),
        ("wrapper", wrapper_actions),
        ("director", director_actions),
    ):
        phase_error = execute_phase(phase_actions, phase_name)
        if phase_error:
            rollback_status, rolled_back, manual_recovery, rollback_error = _rollback_executed_actions(
                root_path, plan, executed_actions, action_journal
            )
            details = f"{phase_name} phase blocked: {phase_error}"
            if rollback_error:
                details += f"; rollback: {rollback_error}"
            return {
                "status": "FAIL",
                "executed_actions": executed,
                "error_summary": details,
                "rollback_status": rollback_status,
                "rolled_back_actions": rolled_back,
                "manual_recovery_required": manual_recovery,
                "action_journal": action_journal,
            }

    verification = verify_plan(plan, root_path)
    if verification["status"] != "PASS":
        rollback_status, rolled_back, manual_recovery, rollback_error = _rollback_executed_actions(
            root_path, plan, executed_actions, action_journal
        )
        details = "post-apply verification failed: " + str(verification["error_summary"])
        if rollback_error:
            details += f"; rollback: {rollback_error}"
        return {
            "status": "FAIL",
            "executed_actions": executed,
            "error_summary": details,
            "rollback_status": rollback_status,
            "rolled_back_actions": rolled_back,
            "manual_recovery_required": manual_recovery,
            "action_journal": action_journal,
        }
    return {
        "status": "PASS",
        "executed_actions": executed,
        "error_summary": "",
        "rollback_status": "NOT_RUN",
        "rolled_back_actions": 0,
        "manual_recovery_required": False,
        "action_journal": action_journal,
    }


def _write_result(root: Path, mode: str, plan: Dict[str, object], result: Dict[str, object]) -> Path:
    _validate_recovery_tree(root)
    recovery = root / WORK_RECORD_DIR / "recovery"
    recovery.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    result_path = recovery / f"result-{mode}-{timestamp}.json"
    record: Dict[str, object] = {
        "schema": "movie-organizing-preprocessor/result/v1",
        "version": VERSION,
        "mode": mode,
        "task_root": str(root),
        "plan_path": str(plan.get("plan_path", "")),
        "plan_hash": str(plan.get("plan_hash", "")),
        **result,
    }
    result_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result_path


def seal_plan(plan: Dict[str, object], root: str | Path) -> Dict[str, object]:
    """Seal one verified large-library naming batch without claiming the task done."""

    root_path = _canonical(root)
    integrity_error = _plan_integrity_error(plan, root_path)
    if integrity_error:
        return {"status": "FAIL", "mode": "seal", "batch_sealed": False, "error_summary": integrity_error}
    if not _matching_recovery_result(root_path, str(plan.get("plan_hash", "")), mode="verify", dry_run=None):
        return {
            "status": "FAIL",
            "mode": "seal",
            "batch_sealed": False,
            "error_summary": "formal naming verify PASS is required before sealing a batch",
        }
    verification = verify_plan(plan, root_path)
    if verification.get("status") != "PASS":
        return {
            "status": "FAIL",
            "mode": "seal",
            "batch_sealed": False,
            "error_summary": "fresh naming verify failed before seal: " + str(verification.get("error_summary", "")),
        }
    summary = plan.get("summary", {}) if isinstance(plan.get("summary"), dict) else {}
    return {
        "status": "PASS",
        "mode": "seal",
        "batch_sealed": True,
        "large_library_mode": bool(plan.get("large_library_mode")),
        "plan_hash": plan.get("plan_hash", ""),
        "next_batch_required": int(summary.get("deferred_action_units", 0) or 0) > 0,
        "deferred_action_units": int(summary.get("deferred_action_units", 0) or 0),
        "error_summary": "",
    }


def _write_seal_result(root: Path, plan: Dict[str, object], result: Dict[str, object]) -> Path:
    _validate_recovery_tree(root)
    recovery = root / WORK_RECORD_DIR / "recovery"
    recovery.mkdir(parents=True, exist_ok=True)
    path = recovery / f"seal-{_timestamp()}.json"
    record = {
        "schema": "movie-organizing-preprocessor/seal/v1",
        "version": VERSION,
        "mode": "seal",
        "task_root": str(root),
        "plan_path": str(plan.get("plan_path", "")),
        "plan_hash": str(plan.get("plan_hash", "")),
        **result,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if result.get("status") == "PASS":
        try:
            _mark_batch_sealed(root, plan, path)
        except OSError as error:
            # Keep the on-disk seal record honest if the checkpoint cannot be
            # updated; a PASS seal must never survive without sealed progress.
            failed_record = {
                **record,
                "status": "FAIL",
                "batch_sealed": False,
                "error_summary": f"sealed progress update failed: {error}",
            }
            path.write_text(json.dumps(failed_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            raise
    return path


def _cli_summary(report: Dict[str, object]) -> Dict[str, object]:
    bundles = report.get("bundles", [])
    exceptions = [
        {"path": item.get("source_movie_dir", ""), "reason": item.get("exception", "")}
        for item in bundles
        if item.get("status") == "EXCEPTION"
    ]
    return {
        "status": "PASS",
        "version": report.get("version"),
        "plan_path": report.get("plan_path"),
        "plan_hash": report.get("plan_hash"),
        "summary": report.get("summary", {}),
        "exception_count": len(exceptions),
        "exceptions": exceptions[:20],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="movie-organizing deterministic preprocessor")
    parser.add_argument("mode", choices=("plan", "apply", "verify", "seal"))
    parser.add_argument("--task-root", required=True)
    parser.add_argument("--plan")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    task_root = _canonical(args.task_root)

    if args.mode == "plan":
        try:
            report = make_plan(task_root)
        except (OSError, ValueError) as error:
            result = {
                "status": "FAIL",
                "version": VERSION,
                "error_summary": f"plan write failed: {error}",
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(_cli_summary(report), ensure_ascii=False, indent=2))
        return 0

    if not args.plan:
        result = {
            "status": "FAIL",
            "version": VERSION,
            "mode": args.mode,
            "executed_actions": 0,
            "error_summary": "--plan is required for apply/verify; refusing to generate one implicitly",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    try:
        _validate_recovery_tree(task_root)
    except OSError as error:
        result = {
            "status": "FAIL",
            "version": VERSION,
            "mode": args.mode,
            "executed_actions": 0,
            "error_summary": f"recovery write blocked: {error}",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        result = {
            "status": "FAIL",
            "version": VERSION,
            "mode": args.mode,
            "executed_actions": 0,
            "error_summary": f"plan read failed: {error}",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    plan_error = _plan_argument_error(plan, args.plan, task_root)
    if plan_error:
        result = {
            "status": "FAIL",
            "version": VERSION,
            "mode": args.mode,
            "executed_actions": 0,
            "error_summary": f"plan rejected: {plan_error}",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    if args.mode == "seal":
        result = seal_plan(plan, task_root)
        result["mode"] = "seal"
        try:
            result["result_path"] = str(_write_seal_result(task_root, plan, result))
        except OSError as error:
            result.update({"status": "FAIL", "error_summary": f"seal result write failed: {error}"})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") == "PASS" else 1

    if args.mode == "apply":
        freshness_error = _fresh_plan_error(plan, task_root)
        if freshness_error:
            result = {
                "status": "FAIL",
                "executed_actions": 0,
                "error_summary": freshness_error,
            }
        elif not args.dry_run and not _matching_recovery_result(
            task_root, str(plan.get("plan_hash", "")), mode="apply", dry_run=True
        ):
            result = {
                "status": "FAIL",
                "executed_actions": 0,
                "error_summary": "successful dry-run recovery evidence is required before formal apply",
            }
        else:
            result = apply_plan(plan, task_root, dry_run=args.dry_run)
            result["dry_run"] = bool(args.dry_run)
    else:
        if not _matching_recovery_result(
            task_root, str(plan.get("plan_hash", "")), mode="apply", dry_run=False
        ):
            result = {
                "status": "FAIL",
                "naming_plan_only": True,
                "executed_actions": 0,
                "error_summary": "successful formal apply recovery evidence is required before verify",
            }
        else:
            result = verify_plan(plan, task_root)
    result["mode"] = args.mode
    try:
        result_path = _write_result(task_root, args.mode, plan, result)
        result["result_path"] = str(result_path)
    except OSError as error:
        result["status"] = "FAIL"
        previous_summary = str(result.get("error_summary", "")).strip()
        write_summary = f"result write failed: {error}"
        result["error_summary"] = f"{previous_summary}; {write_summary}" if previous_summary else write_summary
        result["result_write_error"] = str(error)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
