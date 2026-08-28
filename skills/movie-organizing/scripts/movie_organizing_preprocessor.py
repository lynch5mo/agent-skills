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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


VERSION = "1.3.3"
EXPECTED_NAMING_CONTRACT_SHA256 = "639eece9c338efedabcb4a2c0b951cf00f202f95e1890776e35dd31a53c3d6c0"

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


def _canonical(path: str | Path) -> Path:
    """Return a canonical path without requiring it to exist."""

    return Path(os.path.realpath(os.fspath(path)))


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


def _name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _conflicting_name(parent: Path, name: str) -> Optional[str]:
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


def _extract_cn_before_english(text: str) -> str:
    """Extract a Chinese title before an English/ASCII title."""

    match = re.search(r"[A-Za-z]", text)
    if match:
        candidate = text[: match.start()]
    else:
        candidate = text
    candidate = _clean_cn(candidate)
    return candidate if _is_cjk(candidate) else ""


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
    expected_movie_dir: str = "",
    expected_movie_dir_path: str = "",
    expected_video_target: str = "",
) -> Dict[str, object]:
    return {
        "source_movie_dir": str(parent),
        "expected_director_dir": str(parent.parent),
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
    source_shape = "standard" if is_standard else "orphan"
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
            )
        if dir_year != parsed["year"]:
            return _empty_bundle(parent, video, source_shape, "year mismatch between directory and video")
        if cn_from_video and cn_from_video != cn_from_dir:
            return _empty_bundle(parent, video, source_shape, "conflicting Chinese title sources")
        chinese_title = cn_from_dir
        location = parent.parent
    else:
        # An orphan means a direct video in a director folder. Root-level and
        # nested container videos are deliberately not guessed into a folder.
        relative_parts = parent.relative_to(task_root).parts if _inside(task_root, parent) else ()
        if parent == task_root:
            return _empty_bundle(parent, video, "orphan", "scope: root-level orphan has no director folder")
        if len(relative_parts) != 1:
            return _empty_bundle(parent, video, "collection", "scope: nested video is not a direct director orphan")
        if cn_from_video and cn_from_nfo and cn_from_video != cn_from_nfo:
            return _empty_bundle(parent, video, "orphan", "conflicting Chinese title sources")
        chinese_title = cn_from_video or cn_from_nfo
        if not chinese_title:
            return _empty_bundle(parent, video, "orphan", "no reliable Chinese title source for orphan")
        location = parent

    normalized_stem = parsed["normalized_stem"]
    expected_video_name = f"{normalized_stem}{video.suffix}"
    expected_dir_name = f"{chinese_title}.{normalized_stem}"
    source_dir = parent
    target_dir = location / expected_dir_name
    expected_video_target = target_dir / expected_video_name

    if not _inside(task_root, target_dir, allow_root=False):
        return _empty_bundle(
            parent,
            video,
            source_shape,
            "scope: expected target is outside TASK_ROOT",
            expected_movie_dir=expected_dir_name,
            expected_movie_dir_path=str(target_dir),
            expected_video_target=str(expected_video_target),
        )
    if target_dir != source_dir and target_dir.exists():
        return _empty_bundle(
            parent,
            video,
            source_shape,
            f"target exists: {target_dir}",
            expected_movie_dir=expected_dir_name,
            expected_movie_dir_path=str(target_dir),
            expected_video_target=str(expected_video_target),
        )
    if target_dir != source_dir:
        sibling_collision = _conflicting_name(target_dir.parent, target_dir.name)
        if sibling_collision:
            return _empty_bundle(
                parent,
                video,
                source_shape,
                f"Unicode/case collision with target directory: {sibling_collision}",
                expected_movie_dir=expected_dir_name,
                expected_movie_dir_path=str(target_dir),
                expected_video_target=str(expected_video_target),
            )

    child_collision = _conflicting_name(source_dir, expected_video_name)
    if child_collision:
        return _empty_bundle(
            parent,
            video,
            source_shape,
            f"Unicode/case collision with target video: {child_collision}",
            expected_movie_dir=expected_dir_name,
            expected_movie_dir_path=str(target_dir),
            expected_video_target=str(expected_video_target),
        )

    sidecars = _collect_sidecars(parent, video, video.stem, normalized_stem, target_dir)
    invalid_sidecar = next(
        (
            item
            for item in sidecars
            if item["kind"] in {"subtitle_invalid", "sidecar_unrelated"}
        ),
        None,
    )
    if invalid_sidecar:
        reason = (
            "subtitle language marker is ambiguous"
            if invalid_sidecar["kind"] == "subtitle_invalid"
            else "unrelated NFO/subtitle sidecar is not attributable"
        )
        return _empty_bundle(
            parent,
            video,
            source_shape,
            f"{reason}: {invalid_sidecar['source']}",
            expected_movie_dir=expected_dir_name,
            expected_movie_dir_path=str(target_dir),
            expected_video_target=str(expected_video_target),
        )
    seen_sidecar_targets: set[str] = set()
    for sidecar in sidecars:
        target = _canonical(sidecar["target"])
        source = _canonical(sidecar["source"])
        target_key = _name_key(Path(sidecar["target"]).name)
        if target_key in seen_sidecar_targets:
            return _empty_bundle(
                parent,
                video,
                source_shape,
                f"ambiguous sidecar target: {sidecar['target']}",
                expected_movie_dir=expected_dir_name,
                expected_movie_dir_path=str(target_dir),
                expected_video_target=str(expected_video_target),
            )
        seen_sidecar_targets.add(target_key)
        if target.exists() and target != source:
            return _empty_bundle(
                parent,
                video,
                source_shape,
                f"target sidecar exists: {target}",
                expected_movie_dir=expected_dir_name,
                expected_movie_dir_path=str(target_dir),
                expected_video_target=str(expected_video_target),
            )
        sibling_collision = _conflicting_name(
            source_dir if is_standard else target_dir,
            Path(sidecar["target"]).name,
        )
        if sibling_collision:
            return _empty_bundle(
                parent,
                video,
                source_shape,
                f"Unicode/case collision with target sidecar: {sibling_collision}",
                expected_movie_dir=expected_dir_name,
                expected_movie_dir_path=str(target_dir),
                expected_video_target=str(expected_video_target),
            )

    actions: List[Dict[str, object]] = []
    action_number = 1
    if is_standard:
        # Rename children first, then rename the enclosing movie folder. This
        # avoids an empty legacy directory and keeps each bundle reversible.
        child_video_target = source_dir / expected_video_name
        if _canonical(video) != _canonical(child_video_target):
            actions.append(
                _action(
                    f"a{action_number}",
                    "move_file",
                    source=video,
                    target=child_video_target,
                    evidence="video stem normalized from filename",
                    rollback="rename target back to source",
                    preconditions=["source exists", "target absent", "both paths under TASK_ROOT"],
                    postconditions=["source absent", "target exists"],
                )
            )
            action_number += 1
        for sidecar in sidecars:
            source = Path(sidecar["source"])
            target = source_dir / Path(sidecar["target"]).name
            if _canonical(source) == _canonical(target):
                continue
            actions.append(
                _action(
                    f"a{action_number}",
                    "move_file",
                    source=source,
                    target=target,
                    evidence=f"{sidecar['kind']} follows normalized video basename",
                    rollback="rename target back to source",
                    preconditions=["source exists", "target absent", "bundle member is same-stem sidecar"],
                    postconditions=["source absent", "target exists"],
                )
            )
            action_number += 1
        if _canonical(target_dir) != _canonical(source_dir):
            actions.append(
                _action(
                    f"a{action_number}",
                    "rename_dir",
                    source=source_dir,
                    target=target_dir,
                    evidence="legacy/incomplete movie folder normalized from CN title + video stem",
                    rollback="rename target directory back to source directory",
                    preconditions=["source directory exists", "target directory absent", "target is sibling under TASK_ROOT"],
                    postconditions=["source directory absent", "target directory exists"],
                )
            )
    else:
        # Orphans are placed directly under their existing director folder;
        # never create an English-only or out-of-scope temporary folder.
        actions.append(
            _action(
                f"a{action_number}",
                "mkdir",
                source=None,
                target=target_dir,
                evidence="reliable CN source from filename prefix or same-stem NFO",
                rollback="leave empty directory for manual reversible handling",
                preconditions=["target absent", "parent director folder exists", "target under TASK_ROOT"],
                postconditions=["target directory exists"],
            )
        )
        action_number += 1
        bundle_moves = [(video, expected_video_target, "video")]
        bundle_moves.extend((Path(item["source"]), Path(item["target"]), item["kind"]) for item in sidecars)
        for source, target, kind in bundle_moves:
            actions.append(
                _action(
                    f"a{action_number}",
                    "move_file",
                    source=source,
                    target=Path(target),
                    evidence=f"{kind} moved as one movie bundle",
                    rollback="rename target back to source",
                    preconditions=["source exists", "target absent", "source and target under TASK_ROOT"],
                    postconditions=["source absent", "target exists"],
                )
            )
            action_number += 1

    source_nfo_paths = [item["source"] for item in sidecars if item["kind"] == "nfo"]
    source_subtitle_paths = [item["source"] for item in sidecars if item["kind"] == "subtitle"]
    expected_nfo_targets = [item["target"] for item in sidecars if item["kind"] == "nfo"]
    expected_subtitle_targets = [item["target"] for item in sidecars if item["kind"] == "subtitle"]

    status = "NAMING_PASS" if not actions else "ACTION_REQUIRED"
    return {
        "source_movie_dir": str(parent),
        "expected_director_dir": str(location),
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


def _plan_signature(bundles: Iterable[Dict[str, object]]) -> str:
    payload = json.dumps(list(bundles), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _mark_exception(bundle: Dict[str, object], reason: str) -> None:
    bundle["status"] = "EXCEPTION"
    bundle["exception"] = reason
    bundle["actions"] = []


def _destination_key(path: str | Path) -> Tuple[str, str]:
    destination = _canonical(path)
    return str(_canonical(destination.parent)), _name_key(destination.name)


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
    summary = {
        "total_units": len(bundles),
        "naming_pass": sum(item["status"] == "NAMING_PASS" for item in bundles),
        "action_required": sum(item["status"] == "ACTION_REQUIRED" for item in bundles),
        "exception": sum(item["status"] == "EXCEPTION" for item in bundles),
        "planned_actions": sum(len(item["actions"]) for item in bundles),
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
        "task_root": str(root),
        "standard_id": "movie-organizing",
        "naming_contract_sha256": contract_hash,
        "scan_id": scan_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "bundles": bundles,
    }
    report["plan_hash"] = _plan_signature(bundles)

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
    else:
        report["plan_path"] = ""
    return report


def _validate_action(
    action: Dict[str, object], root: Path, planned_dirs: Optional[set[Path]] = None
) -> Optional[str]:
    name = str(action.get("action", action.get("type", "")))
    target = _canonical(str(action.get("target", "")))
    source_value = action.get("source")
    source = _canonical(str(source_value)) if source_value else None
    if not _inside(root, target, allow_root=False):
        return f"outside task root: {target}"
    if source is not None and not _inside(root, source, allow_root=False):
        return f"outside task root: {source}"
    if name not in {"mkdir", "move_file", "rename_dir"}:
        return f"unsupported action: {name}"
    if planned_dirs is None:
        planned_dirs = set()
    if name == "mkdir":
        if target.exists():
            return f"mkdir target exists: {target}"
        if not target.parent.is_dir():
            return f"mkdir parent missing: {target.parent}"
    elif name == "move_file":
        if source is None or not source.is_file():
            return f"missing source: {source}"
        if target.exists():
            return f"target exists: {target}"
        if not target.parent.is_dir() and _canonical(target.parent) not in planned_dirs:
            return f"target parent missing: {target.parent}"
    else:
        if source is None or not source.is_dir():
            return f"missing source directory: {source}"
        if target.exists():
            return f"target directory exists: {target}"
        if not target.parent.is_dir() and _canonical(target.parent) not in planned_dirs:
            return f"target parent missing: {target.parent}"
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
        if bundle.get("source_shape") == "standard" and source_dir != expected_dir and source_dir.exists():
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
    if plan.get("standard_id") != "movie-organizing":
        return "plan standard_id mismatch"
    if plan.get("naming_contract_sha256") != EXPECTED_NAMING_CONTRACT_SHA256:
        return "plan naming-contract hash mismatch"
    plan_hash = plan.get("plan_hash")
    if not isinstance(plan_hash, str) or not plan_hash:
        return "plan hash missing"
    if plan_hash != _plan_signature(plan.get("bundles", [])):
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
    if plan.get("standard_id") != "movie-organizing":
        return "plan standard_id mismatch"
    if plan.get("naming_contract_sha256") != EXPECTED_NAMING_CONTRACT_SHA256:
        return "plan naming-contract hash mismatch"
    if not isinstance(plan.get("scan_id"), str) or not plan.get("scan_id"):
        return "plan scan_id missing"
    if not isinstance(plan.get("bundles"), list):
        return "plan bundles missing or invalid"
    return _plan_integrity_error(plan, root)


def _fresh_plan_error(plan: Dict[str, object], root: Path) -> Optional[str]:
    try:
        fresh = make_plan(root, persist=False)
    except (OSError, ValueError) as error:
        return f"fresh plan failed: {error}"
    for field in ("task_root", "version", "standard_id", "naming_contract_sha256", "scan_id", "plan_hash"):
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
            missing.extend(_verify_bundle(bundle, root_path))
    return {
        "status": "PASS" if not missing else "FAIL",
        "naming_plan_only": True,
        "missing": missing,
        "error_summary": "; ".join(missing),
    }


def apply_plan(plan: Dict[str, object], root: str | Path, dry_run: bool = False) -> Dict[str, object]:
    root_path = _canonical(root)
    plan_root = _canonical(str(plan.get("task_root", "")))
    if plan_root != root_path:
        return {
            "status": "FAIL",
            "executed_actions": 0,
            "error_summary": "plan task_root mismatch or outside task root",
        }

    actions: List[Dict[str, object]] = []
    planned_dirs: set[Path] = set()
    for bundle in plan.get("bundles", []):
        if bundle.get("status") != "ACTION_REQUIRED":
            continue
        for action in bundle.get("actions", []):
            failure = _validate_action(action, root_path, planned_dirs)
            if failure:
                return {"status": "FAIL", "executed_actions": 0, "error_summary": failure}
            actions.append(action)
            if str(action.get("action", action.get("type", ""))) == "mkdir":
                planned_dirs.add(_canonical(str(action["target"])))

    integrity_error = _plan_integrity_error(plan, root_path)
    if integrity_error:
        return {"status": "FAIL", "executed_actions": 0, "error_summary": integrity_error}

    if dry_run:
        return {
            "status": "PASS",
            "dry_run": True,
            "planned_actions": len(actions),
            "executed_actions": 0,
            "error_summary": "",
        }

    executed = 0
    try:
        for action in actions:
            name = str(action.get("action", action.get("type", "")))
            target = _canonical(str(action["target"]))
            if name == "mkdir":
                target.mkdir()
            else:
                source = _canonical(str(action["source"]))
                source.rename(target)
            executed += 1
    except OSError as error:
        return {"status": "FAIL", "executed_actions": executed, "error_summary": f"apply failed: {error}"}

    verification = verify_plan(plan, root_path)
    if verification["status"] != "PASS":
        return {
            "status": "FAIL",
            "executed_actions": executed,
            "error_summary": "post-apply verification failed: " + str(verification["error_summary"]),
        }
    return {"status": "PASS", "executed_actions": executed, "error_summary": ""}


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
    parser.add_argument("mode", choices=("plan", "apply", "verify"))
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
