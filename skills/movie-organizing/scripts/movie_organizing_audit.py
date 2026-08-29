#!/usr/bin/env python3
"""Lightweight CORE/DEDUPE gates and installation integrity checks.

The audit intentionally stays a read-only media scan.  It reuses the existing
preprocessor to classify the fresh active tree, then (only after CORE passes)
groups movie folders by director, normalized Chinese title, and year.  Groups
are evidence for an Agent to compare (NFO/ffprobe/edition/cut/quality); this
script never deletes, moves, hashes, or chooses a winner.

The same standard-library-only entrypoint provides ``verify-install``.  That
check validates a small checksum/size manifest and rejects the truncation
marker seen in a previously broken installation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


VERSION = "1.3.5"
WORK_RECORD_DIR = "_work-record_"
RECOVERY_DIR = "recovery"
PENDING_DIR = "_待确认_"
TRASH_PREFIX = "_trash_"
# Keep the control-tree check independent from preprocessor loading: these
# are the media extensions whose presence in _work-record_ is always invalid.
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
# Build the marker in two pieces so this verifier's own source does not look
# like a damaged shell capture when it scans the installed files.
TRUNCATION_MARKER = b"[" + b"OUTPUT TRUNCATED"
REQUIRED_INTEGRITY_PATHS = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/failure-handling.md",
    "references/lessons-and-audit-checklist.md",
    "references/naming-contract.md",
    "references/runtime-and-safety.md",
    "references/triage-and-edge-cases.md",
    "scripts/movie_organizing_audit.py",
    "scripts/movie_organizing_preprocessor.py",
    "scripts/movie_organizing_slowpath.py",
    "scripts/movie_organizing_task.py",
)

COMPLETION_BLOCKED = "BLOCKED"
COMPLETION_CORE_PENDING = "CORE_COMPLETE_PENDING"
COMPLETION_COMPLETE = "COMPLETE"
BLOCKED_MESSAGE = "未完成：仍有核心问题或重复候选"
COMPLETE_MESSAGE = "全部整理完成（待确认=0且终扫PASS）"


def _canonical(path: str | Path) -> Path:
    return Path(os.path.realpath(os.fspath(path)))


def _inside(root: Path, path: Path, *, allow_root: bool = True) -> bool:
    root = _canonical(root)
    path = _canonical(path)
    if allow_root and root == path:
        return True
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S%f")


def _load_preprocessor(skill_dir: Path):
    script = skill_dir / "scripts" / "movie_organizing_preprocessor.py"
    spec = importlib.util.spec_from_file_location("movie_organizing_preprocessor_for_audit", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load preprocessor: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize_identity(value: str) -> str:
    """Normalize title/key text without making semantic title guesses."""

    text = unicodedata.normalize("NFC", value).casefold()
    chars: List[str] = []
    for char in text:
        category = unicodedata.category(char)
        if char.isspace():
            continue
        if "CJK UNIFIED IDEOGRAPH" in unicodedata.name(char, ""):
            chars.append(char)
        elif char.isalnum() or category.startswith("L"):
            chars.append(char)
    return "".join(chars)


def _movie_identity(movie_dir: Path) -> Optional[Tuple[str, str]]:
    """Return ``(normalized Chinese title, year)`` for a standard movie dir."""

    name = movie_dir.name
    if "." not in name:
        return None
    chinese_title, remainder = name.split(".", 1)
    if not any("CJK UNIFIED IDEOGRAPH" in unicodedata.name(char, "") for char in chinese_title):
        return None
    year_match = re.search(r"(?<!\d)(19\d{2}|20\d{2})(?=\.|$)", remainder)
    if not year_match:
        return None
    normalized_title = _normalize_identity(chinese_title)
    if not normalized_title:
        return None
    return normalized_title, year_match.group(1)


def _active_path(root: Path, path: str | Path) -> bool:
    """Whether a path is inside active media tree (not control directories)."""

    path = _canonical(path)
    if not _inside(root, path):
        return False
    try:
        relative = path.relative_to(_canonical(root))
    except ValueError:
        return False
    return not any(
        part == WORK_RECORD_DIR or part == PENDING_DIR or part.startswith(TRASH_PREFIX)
        for part in relative.parts
    )


def _is_control_name(name: str) -> bool:
    return name == WORK_RECORD_DIR or name == PENDING_DIR or name.startswith(TRASH_PREFIX)


def _control_tree_violations(root: Path) -> List[Dict[str, str]]:
    """Inspect reserved control trees without following any symlink."""

    violations: List[Dict[str, str]] = []
    root = _canonical(root)
    try:
        root_entries = list(os.scandir(root))
    except OSError as error:
        return [{"path": str(root), "reason": f"control scan failed: {error}"}]

    for root_entry in root_entries:
        if not _is_control_name(root_entry.name):
            continue
        control = Path(root_entry.path)
        if root_entry.is_symlink():
            violations.append(
                {"path": str(control), "reason": "control directory symlink is not allowed"}
            )
            continue
        if not root_entry.is_dir(follow_symlinks=False):
            violations.append(
                {"path": str(control), "reason": "control entry must be a directory"}
            )
            continue

        work_record_tree = root_entry.name == WORK_RECORD_DIR
        stack = [control]
        while stack:
            current = stack.pop()
            if not _inside(root, current, allow_root=False):
                violations.append(
                    {"path": str(current), "reason": "control path resolves outside TASK_ROOT"}
                )
                continue
            try:
                entries = list(os.scandir(current))
            except OSError as error:
                violations.append({"path": str(current), "reason": f"control scan failed: {error}"})
                continue
            for entry in entries:
                item = Path(entry.path)
                if entry.is_symlink():
                    violations.append(
                        {"path": str(item), "reason": "symlink in control tree is not allowed"}
                    )
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if not _inside(root, item, allow_root=False):
                        violations.append(
                            {"path": str(item), "reason": "control path resolves outside TASK_ROOT"}
                        )
                    else:
                        stack.append(item)
                elif not entry.is_file(follow_symlinks=False):
                    violations.append(
                        {"path": str(item), "reason": "unsupported control entry type"}
                    )
                elif work_record_tree and Path(entry.name).suffix.casefold() in VIDEO_EXTENSIONS:
                    violations.append(
                        {
                            "path": str(item),
                            "reason": "video file in _work-record_ control tree is not allowed",
                        }
                    )
    return violations


def _pending_metrics(root: Path, video_extensions: Iterable[str]) -> Tuple[int, int]:
    """Return ``(pending_units, nonvideo_warning)`` without following symlinks."""

    pending = root / PENDING_DIR
    if os.path.lexists(pending) and (pending.is_symlink() or not pending.is_dir()):
        return 1, 1
    if not pending.is_dir():
        return 0, 0
    extensions = {str(ext).casefold() for ext in video_extensions}
    count = 0
    saw_content = False
    saw_nonvideo = False
    stack = [pending]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    saw_content = True
                    if entry.is_symlink():
                        # Control-tree validation normally catches this first;
                        # keep the metric conservative if the tree changes mid-run.
                        saw_nonvideo = True
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.casefold() in extensions:
                        count += 1
                    else:
                        saw_nonvideo = True
        except OSError:
            # An unreadable pending branch is still pending; count the branch
            # as one conservative unit rather than treating it as complete.
            saw_content = True
            saw_nonvideo = True
    if saw_content and count == 0:
        count = 1
    return count, int(saw_nonvideo and count == 1)


def _pending_count(root: Path, video_extensions: Iterable[str]) -> int:
    return _pending_metrics(root, video_extensions)[0]


def _pending_video_count(root: Path, video_extensions: Iterable[str]) -> int:
    """Count real video files recursively below ``_待确认_`` (read-only)."""

    pending = root / PENDING_DIR
    if pending.is_symlink() or not pending.is_dir():
        return 0
    extensions = {str(ext).casefold() for ext in video_extensions}
    count = 0
    stack = [pending]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.casefold() in extensions:
                        count += 1
        except OSError:
            continue
    return count


def _limit(items: Iterable[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    return list(items)[:limit]


def _director_name_is_conforming(name: str) -> bool:
    """Require exact ``中文段 EnglishName`` with U+00B7 foreign separators."""

    stripped = name.strip()
    if stripped != name:
        return False
    boundary = next(
        (index for index, char in enumerate(stripped)
         if "LATIN" in unicodedata.name(char, "") or (char.isascii() and char.isalpha())),
        -1,
    )
    if boundary <= 0:
        return False
    separator = boundary - 1
    if stripped[separator] != " " or (separator > 0 and stripped[separator - 1].isspace()):
        return False
    chinese_part = stripped[:separator]
    english_part = stripped[boundary:]
    if not chinese_part or not english_part:
        return False
    if any(char.isspace() for char in chinese_part) or "." in chinese_part:
        return False
    if any("CJK UNIFIED IDEOGRAPH" not in unicodedata.name(char, "") and char not in "·、" for char in chinese_part):
        return False
    if any("CJK UNIFIED IDEOGRAPH" in unicodedata.name(char, "") for char in english_part):
        return False
    if not any("LATIN" in unicodedata.name(char, "") or (char.isascii() and char.isalpha()) for char in english_part):
        return False
    pieces = [piece for piece in re.split(r"[·、]+", chinese_part) if piece]
    return bool(pieces) and all(
        all("CJK UNIFIED IDEOGRAPH" in unicodedata.name(char, "") for char in piece)
        for piece in pieces
    )


def _director_violations(root: Path, plan: Dict[str, Any]) -> List[Dict[str, str]]:
    """Check both source and expected active director anchors."""

    directors: Dict[Path, Dict[str, str]] = {}
    for bundle in plan.get("bundles", []):
        for key in ("source_director_dir", "expected_director_dir"):
            director_value = bundle.get(key)
            if not director_value:
                continue
            director = _canonical(str(director_value))
            if director == _canonical(root) or director.parent != _canonical(root) or not _active_path(root, director):
                continue
            if not director.exists() or not director.is_dir():
                continue
            directors[director] = {
                "path": str(director),
                "reason": "director folder must use one ASCII space and U+00B7 within foreign Chinese names",
            }
    return [
        item
        for path, item in sorted(directors.items(), key=lambda item: str(item[0]))
        if not _director_name_is_conforming(path.name)
    ]


def _core_counts(
    plan: Dict[str, Any], director_violations: Optional[Sequence[Dict[str, str]]] = None
) -> Tuple[Dict[str, int], List[Dict[str, Any]], List[Dict[str, Any]]]:
    bundles = list(plan.get("bundles", []))
    exceptions = [item for item in bundles if item.get("status") == "EXCEPTION"]
    actions = [item for item in bundles if item.get("status") == "ACTION_REQUIRED"]
    naming_pass = [item for item in bundles if item.get("status") == "NAMING_PASS"]
    recognized = {"NAMING_PASS", "ACTION_REQUIRED", "EXCEPTION"}
    partial = [item for item in bundles if item.get("status") not in recognized]

    counts = {
        "active_video_units": len(bundles),
        "active_naming_pass_units": len(naming_pass),
        "active_exception_units": len(exceptions),
        "required_actions_remaining": len(actions),
        "active_nonconforming_director_dirs": len(director_violations or []),
        "active_nonconforming_movie_dirs": len(actions),
        "active_nonconforming_video_files": len(actions),
        "active_nonconforming_nfo_files": 0,
        "active_nonconforming_subtitle_files": 0,
        "active_orphan_videos": sum(item.get("source_shape") == "orphan" for item in bundles),
        "active_collection_containers_with_videos": sum(
            item.get("source_shape") == "collection" for item in bundles
        ),
        "active_misfiled_movie_dirs": sum(
            item.get("source_shape") == "dispersed" for item in bundles
        ),
        "partial_bundles": len(partial),
        "unaccounted_video_units": len(partial),
    }
    return counts, _limit(exceptions), _limit(actions)


def _core_status(counts: Dict[str, int]) -> str:
    # The first two counters are the hard anti-false-completion condition.  The
    # remaining counters keep the output compatible with the full CORE ledger.
    if counts.get("active_video_units", 0) == 0:
        return "FAIL"
    blocking_keys = (
        "active_exception_units",
        "required_actions_remaining",
        "active_nonconforming_director_dirs",
        "active_nonconforming_movie_dirs",
        "active_nonconforming_video_files",
        "active_nonconforming_nfo_files",
        "active_nonconforming_subtitle_files",
        "active_orphan_videos",
        "active_collection_containers_with_videos",
        "active_misfiled_movie_dirs",
        "partial_bundles",
        "unaccounted_video_units",
    )
    return "PASS" if all(counts.get(key, 0) == 0 for key in blocking_keys) else "FAIL"


def _candidate_groups(root: Path, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Group active, naming-passed movie dirs for Agent review only."""

    grouped: Dict[Tuple[str, str, str], List[Path]] = {}
    for bundle in plan.get("bundles", []):
        if bundle.get("status") != "NAMING_PASS":
            continue
        movie_dir_value = bundle.get("expected_movie_dir_path")
        if not movie_dir_value:
            continue
        movie_dir = _canonical(str(movie_dir_value))
        if not _active_path(root, movie_dir) or not movie_dir.is_dir():
            continue
        identity = _movie_identity(movie_dir)
        if identity is None:
            continue
        title_key, year = identity
        director_dir = movie_dir.parent
        director_key = _normalize_identity(director_dir.name) or unicodedata.normalize(
            "NFC", director_dir.name
        ).casefold()
        grouped.setdefault((director_key, title_key, year), []).append(movie_dir)

    groups: List[Dict[str, Any]] = []
    for key, members in sorted(grouped.items(), key=lambda item: item[0]):
        if len(members) < 2:
            continue
        director_key, title_key, year = key
        stable_id = hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()[:16]
        groups.append(
            {
                "group_id": f"duplicate-{stable_id}",
                "group_key": {
                    "director": director_key,
                    "normalized_chinese_title": title_key,
                    "year": year,
                },
                "members": [str(path) for path in sorted(members, key=lambda item: str(item))],
                "evidence": "same director + normalized Chinese title + year; English/release names may differ",
                "requires_agent_review": True,
            }
        )
    return groups


def _lexical(path: str | Path) -> Path:
    """Normalize ``..`` without resolving symlinks."""

    return Path(os.path.abspath(os.fspath(path)))


def _expected_file_issue(root: Path, path_value: Any, label: str) -> Optional[Tuple[Path, str]]:
    if not path_value:
        return _lexical(root), f"{label} path is missing from the plan"
    path = _lexical(str(path_value))
    if not _inside(root, path, allow_root=False):
        return path, f"{label} resolves outside TASK_ROOT"
    if path.is_symlink():
        return path, f"{label} must not be a symlink"
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return path, f"{label} is missing"
    except OSError as error:
        return path, f"{label} cannot be inspected: {error}"
    if not stat.S_ISREG(mode):
        return path, f"{label} is not a regular file"
    return None


def _cleanup_gate(root: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Run a shallow active-tree scan and movie whitelist terminal check."""

    root = _canonical(root)
    violations: List[Dict[str, str]] = []
    seen_violations: set[Tuple[str, str]] = set()

    def add_violation(path: str | Path, reason: str) -> None:
        item = (str(_lexical(path)), reason)
        if item in seen_violations:
            return
        seen_violations.add(item)
        violations.append({"path": item[0], "reason": reason})

    naming_bundles = [
        bundle for bundle in plan.get("bundles", []) if bundle.get("status") == "NAMING_PASS"
    ]
    movie_to_bundles: Dict[Path, List[Dict[str, Any]]] = {}
    director_to_movies: Dict[Path, set[Path]] = {}
    for bundle in naming_bundles:
        movie_value = bundle.get("expected_movie_dir_path")
        director_value = bundle.get("expected_director_dir")
        if movie_value:
            movie_path = _lexical(str(movie_value))
            movie_to_bundles.setdefault(movie_path, []).append(bundle)
        if director_value:
            director_path = _lexical(str(director_value))
            director_to_movies.setdefault(director_path, set())
            if movie_value:
                director_to_movies[director_path].add(_lexical(str(movie_value)))

    scanned_movies: set[Path] = set()

    def scan_movie(movie_path: Path, bundles: Sequence[Dict[str, Any]]) -> None:
        if movie_path in scanned_movies:
            return
        scanned_movies.add(movie_path)
        if not _inside(root, movie_path, allow_root=False):
            add_violation(movie_path, "active movie directory resolves outside TASK_ROOT")
            return
        if movie_path.is_symlink():
            add_violation(movie_path, "active movie directory must not be a symlink")
            return
        try:
            mode = os.lstat(movie_path).st_mode
        except FileNotFoundError:
            add_violation(movie_path, "active movie directory is missing")
            return
        except OSError as error:
            add_violation(movie_path, f"active movie directory cannot be inspected: {error}")
            return
        if not stat.S_ISDIR(mode):
            add_violation(movie_path, "active movie path is not a directory")
            return

        allowed: set[Path] = set()
        for bundle in bundles:
            expected_video = bundle.get("expected_video_target")
            issue = _expected_file_issue(root, expected_video, "expected main video")
            if issue:
                add_violation(issue[0], issue[1])
            else:
                allowed.add(_canonical(_lexical(str(expected_video))))
            for key, label in (
                ("expected_nfo_targets", "expected NFO"),
                ("expected_subtitle_targets", "expected subtitle"),
            ):
                for sidecar in bundle.get(key, []):
                    issue = _expected_file_issue(root, sidecar, label)
                    if issue:
                        add_violation(issue[0], issue[1])
                    else:
                        allowed.add(_canonical(_lexical(str(sidecar))))

        try:
            with os.scandir(movie_path) as entries:
                for entry in entries:
                    entry_path = _lexical(entry.path)
                    if _is_control_name(entry.name):
                        add_violation(entry_path, "reserved control entry is only allowed at TASK_ROOT")
                        continue
                    if entry.is_symlink():
                        add_violation(entry_path, "active movie item must not be a symlink")
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        add_violation(entry_path, "active movie item is not a regular whitelisted file")
                        continue
                    if _canonical(entry_path) not in allowed:
                        add_violation(entry_path, "active item is outside the movie whitelist")
        except OSError as error:
            add_violation(movie_path, f"final movie scan failed: {error}")

    def scan_director(director_path: Path, movie_paths: set[Path]) -> None:
        if not _inside(root, director_path, allow_root=False):
            add_violation(director_path, "active director directory resolves outside TASK_ROOT")
            return
        if director_path.is_symlink():
            add_violation(director_path, "active director directory must not be a symlink")
            return
        try:
            mode = os.lstat(director_path).st_mode
        except FileNotFoundError:
            add_violation(director_path, "active director directory is missing")
            return
        except OSError as error:
            add_violation(director_path, f"active director directory cannot be inspected: {error}")
            return
        if not stat.S_ISDIR(mode):
            add_violation(director_path, "active director path is not a directory")
            return
        try:
            with os.scandir(director_path) as entries:
                for entry in entries:
                    item = _lexical(entry.path)
                    if _is_control_name(entry.name):
                        add_violation(item, "reserved control entry is only allowed at TASK_ROOT")
                        continue
                    if entry.is_symlink():
                        add_violation(item, "active director item must not be a symlink")
                        continue
                    if not entry.is_dir(follow_symlinks=False):
                        add_violation(item, "active director item is not a movie directory")
                        continue
                    canonical_item = _canonical(item)
                    movie_key = _lexical(canonical_item)
                    if movie_key not in movie_paths:
                        add_violation(item, "unknown active directory under director")
                    else:
                        scan_movie(movie_key, movie_to_bundles.get(movie_key, []))
        except OSError as error:
            add_violation(director_path, f"final director scan failed: {error}")

    try:
        with os.scandir(root) as entries:
            for entry in entries:
                item = _lexical(entry.path)
                if _is_control_name(entry.name):
                    if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                        add_violation(item, "control entry at TASK_ROOT must be a real directory")
                    continue
                if entry.is_symlink():
                    add_violation(item, "active TASK_ROOT item must not be a symlink")
                    continue
                if not entry.is_dir(follow_symlinks=False):
                    add_violation(item, "active TASK_ROOT item is not a director directory")
                    continue
                canonical_item = _canonical(item)
                director_key = _lexical(canonical_item)
                if director_key not in director_to_movies or director_key == root:
                    add_violation(item, "unknown active directory at TASK_ROOT; expected a director directory")
                else:
                    scan_director(director_key, director_to_movies[director_key])
    except OSError as error:
        add_violation(root, f"final TASK_ROOT scan failed: {error}")

    # A plan can reference a movie path that disappeared between planning and
    # this terminal scan; verify every expected bundle even if its parent was
    # not present in the shallow directory walk.
    for movie_path, bundles in movie_to_bundles.items():
        scan_movie(movie_path, bundles)

    return {
        "status": "PASS" if not violations else "FAIL",
        "counts": {"active_non_whitelist_items": len(violations)},
        "violations": _limit(violations),
        "terminal_scan": "PASS" if not violations else "FAIL",
    }


def _report_path(root: Path) -> Path:
    root = _canonical(root)
    work_record = root / WORK_RECORD_DIR
    if os.path.lexists(work_record):
        if work_record.is_symlink():
            raise OSError(f"recovery control directory is a symlink: {work_record}")
        if not work_record.is_dir() or not _inside(root, work_record, allow_root=False):
            raise OSError(f"recovery control directory is not an in-root directory: {work_record}")
    recovery = work_record / RECOVERY_DIR
    if os.path.lexists(recovery):
        if recovery.is_symlink():
            raise OSError(f"recovery directory is a symlink: {recovery}")
        if not recovery.is_dir() or not _inside(root, recovery, allow_root=False):
            raise OSError(f"recovery directory is not an in-root directory: {recovery}")
    recovery.mkdir(parents=True, exist_ok=True)
    return recovery / f"audit-{_timestamp()}.json"


def _write_report(root: Path, report: Dict[str, Any]) -> Path:
    path = _report_path(root)
    report["report_path"] = str(path)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _base_report(root: Path) -> Dict[str, Any]:
    return {
        "schema": "movie-organizing-audit/v1",
        "version": VERSION,
        "status": "FAIL",
        "task_root": str(root),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "evidence_scope": "fresh active tree; pending/trash/work-record excluded",
        "verify_pass_semantics": "preprocessor verify PASS is naming plan execution only",
        "core_gate": {
            "status": "FAIL",
            "counts": {},
            "exceptions": [],
            "action_required": [],
            "director_violations": [],
            "control_violations": [],
        },
        "dedupe_gate": {
            "status": "NOT_RUN",
            "counts": {
                "unresolved_duplicate_groups_in_active_tree": 0,
                "inferior_copies_remaining_in_active_tree": 0,
                "dedupe_actions_remaining": 0,
                "partial_dedupe_actions": 0,
            },
            "candidate_groups": [],
            "candidate_group_count": 0,
        },
        "cleanup_gate": {
            "status": "NOT_RUN",
            "counts": {"active_non_whitelist_items": 0},
            "violations": [],
            "terminal_scan": "NOT_RUN",
        },
        "pending_count": 0,
        "pending_video_count": 0,
        "pending_nonvideo_or_empty_units": 0,
        "control_violations": [],
        "control_violation_count": 0,
        "counts": {
            "core": {},
            "dedupe": {},
            "cleanup": {},
            "pending_count": 0,
            "pending_video_count": 0,
            "pending_nonvideo_or_empty_units": 0,
            "control_violation_count": 0,
        },
        "candidate_groups": [],
        "completion_status": COMPLETION_BLOCKED,
        "allowed_completion_message": BLOCKED_MESSAGE,
    }


def audit_task_root(task_root: str | Path) -> Tuple[Dict[str, Any], int]:
    root = _canonical(task_root)
    report = _base_report(root)
    if not root.is_dir():
        report["core_gate"]["counts"] = {"active_exception_units": 1}
        report["audit_error"] = "TASK_ROOT does not exist or is not a directory"
        report["counts"] = {
            "core": report["core_gate"]["counts"],
            "dedupe": report["dedupe_gate"]["counts"],
            "cleanup": report["cleanup_gate"]["counts"],
            "pending_count": 0,
            "pending_video_count": 0,
            "pending_nonvideo_or_empty_units": 0,
            "control_violation_count": 0,
        }
        return report, 1

    skill_dir = Path(__file__).resolve().parents[1]
    try:
        control_violations = _control_tree_violations(root)
        if control_violations:
            report["control_violations"] = _limit(control_violations)
            report["control_violation_count"] = len(control_violations)
            raise RuntimeError("control tree contains symlink or invalid reserved entry")
        preprocessor = _load_preprocessor(skill_dir)
        if str(getattr(preprocessor, "VERSION", "")) != VERSION:
            raise RuntimeError(
                f"preprocessor version mismatch: {getattr(preprocessor, 'VERSION', '')} != {VERSION}"
            )
        plan = preprocessor.make_plan(root)
        director_violations = _director_violations(root, plan)
        counts, exceptions, actions = _core_counts(plan, director_violations)
        report["plan_path"] = plan.get("plan_path", "")
        report["plan_hash"] = plan.get("plan_hash", "")
        report["core_gate"] = {
            "status": _core_status(counts),
            "counts": counts,
            "exceptions": [
                {"path": item.get("source_movie_dir", ""), "reason": item.get("exception", "")}
                for item in exceptions
            ],
            "action_required": [
                {"path": item.get("source_movie_dir", ""), "reason": "required naming/rehome action remains"}
                for item in actions
            ],
            "director_violations": director_violations[:20],
            "control_violations": [],
        }
        preprocessor_video_extensions = getattr(preprocessor, "VIDEO_EXTENSIONS", set())
        report["pending_count"], report["pending_nonvideo_or_empty_units"] = _pending_metrics(
            root, preprocessor_video_extensions
        )
        report["pending_video_count"] = _pending_video_count(root, preprocessor_video_extensions)
        if counts.get("active_video_units", 0) == 0:
            report["core_gate"]["reason"] = "TASK_ROOT has no active video units"

        if report["core_gate"]["status"] == "PASS":
            groups = _candidate_groups(root, plan)
            unresolved = len(groups)
            report["dedupe_gate"] = {
                "status": "PASS" if unresolved == 0 else "FAIL",
                "counts": {
                    "unresolved_duplicate_groups_in_active_tree": unresolved,
                    # This script never selects an inferior copy; evidence is
                    # intentionally left to the Agent's edition/quality review.
                    "inferior_copies_remaining_in_active_tree": 0,
                    "dedupe_actions_remaining": 0,
                    "partial_dedupe_actions": 0,
                },
                "candidate_groups": _limit(groups),
                "candidate_group_count": unresolved,
                "decision_policy": "candidate evidence only; no name/size auto-delete",
            }
        else:
            # Never scan duplicate groups after a failed CORE gate.
            report["dedupe_gate"] = {
                "status": "NOT_RUN",
                "counts": {
                    "unresolved_duplicate_groups_in_active_tree": 0,
                    "inferior_copies_remaining_in_active_tree": 0,
                    "dedupe_actions_remaining": 0,
                    "partial_dedupe_actions": 0,
                },
                "candidate_groups": [],
                "candidate_group_count": 0,
                "decision_policy": "not evaluated until CORE_GATE=PASS",
            }

        if report["dedupe_gate"]["status"] == "PASS":
            report["cleanup_gate"] = _cleanup_gate(root, plan)
    except Exception as error:  # keep a machine-readable recovery record
        report["audit_error"] = f"{type(error).__name__}: {error}"
        report["core_gate"] = {
            "status": "FAIL",
            "counts": {"active_exception_units": 1, "required_actions_remaining": 0},
            "exceptions": [{"path": str(root), "reason": report["audit_error"]}],
            "action_required": [],
            "director_violations": [],
            "control_violations": report.get("control_violations", []),
        }
        report["dedupe_gate"]["status"] = "NOT_RUN"
        report["cleanup_gate"]["status"] = "NOT_RUN"

    core_pass = report["core_gate"]["status"] == "PASS"
    dedupe_pass = report["dedupe_gate"]["status"] == "PASS"
    cleanup_pass = report["cleanup_gate"]["status"] == "PASS"
    if not core_pass or not dedupe_pass or not cleanup_pass:
        report["completion_status"] = COMPLETION_BLOCKED
        report["allowed_completion_message"] = BLOCKED_MESSAGE
        exit_code = 1
    elif report["pending_count"]:
        report["completion_status"] = COMPLETION_CORE_PENDING
        report["allowed_completion_message"] = (
            f"主目录四项核心整理已完成，待确认 {report['pending_count']}项"
        )
        exit_code = 0
    else:
        report["completion_status"] = COMPLETION_COMPLETE
        report["allowed_completion_message"] = COMPLETE_MESSAGE
        exit_code = 0

    report["status"] = "PASS" if exit_code == 0 else "FAIL"
    report["counts"] = {
        "core": report["core_gate"].get("counts", {}),
        "dedupe": report["dedupe_gate"].get("counts", {}),
        "cleanup": report["cleanup_gate"].get("counts", {}),
        "pending_count": report["pending_count"],
        "pending_video_count": report.get("pending_video_count", 0),
        "pending_nonvideo_or_empty_units": report.get("pending_nonvideo_or_empty_units", 0),
        "control_violation_count": report.get("control_violation_count", 0),
    }
    report["candidate_groups"] = report["dedupe_gate"].get("candidate_groups", [])

    try:
        report["report_path"] = str(_write_report(root, report))
    except OSError as error:
        # A completion claim is valid only when its recovery evidence was
        # persisted.  If evidence cannot be written, force the same blocked
        # semantics as any other audit failure.
        report["status"] = "FAIL"
        report["completion_status"] = COMPLETION_BLOCKED
        report["allowed_completion_message"] = BLOCKED_MESSAGE
        report["report_write_error"] = str(error)
        exit_code = 1
    return report, exit_code


def _manifest_failure(failures: List[str], message: str) -> None:
    failures.append(message)


def verify_install(skill_dir: str | Path) -> Dict[str, Any]:
    root = _canonical(skill_dir)
    result: Dict[str, Any] = {
        "schema": "movie-organizing-install-verification/v1",
        "status": "FAIL",
        "version": VERSION,
        "skill_dir": str(root),
        "checked_files": 0,
        "failures": [],
    }
    failures: List[str] = result["failures"]
    manifest_path = root / "integrity-manifest.json"
    if not root.is_dir():
        _manifest_failure(failures, f"skill directory missing: {root}")
        return result
    if not manifest_path.is_file():
        _manifest_failure(failures, f"integrity manifest missing: {manifest_path}")
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _manifest_failure(failures, f"invalid integrity manifest: {error}")
        return result

    if not isinstance(manifest, dict):
        _manifest_failure(failures, "invalid integrity manifest: top-level value is not an object")
        return result
    if manifest.get("version") != VERSION:
        _manifest_failure(failures, f"manifest version mismatch: {manifest.get('version')} != {VERSION}")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        _manifest_failure(failures, "integrity manifest files list is empty or invalid")
        return result

    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            _manifest_failure(failures, "integrity manifest entry is not an object")
            continue
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative or relative in seen:
            _manifest_failure(failures, f"invalid or duplicate manifest path: {relative!r}")
            continue
        seen.add(relative)
        target = _canonical(root / relative)
        if not _inside(root, target, allow_root=False):
            _manifest_failure(failures, f"manifest path escapes skill directory: {relative}")
            continue
        result["checked_files"] += 1
        if not target.is_file():
            _manifest_failure(failures, f"missing file: {relative}")
            continue
        try:
            data = target.read_bytes()
        except OSError as error:
            _manifest_failure(failures, f"cannot read {relative}: {error}")
            continue
        expected_size = entry.get("size")
        size_mismatch = not isinstance(expected_size, int) or len(data) != expected_size
        if size_mismatch:
            _manifest_failure(failures, f"size mismatch: {relative}")
        expected_hash = entry.get("sha256")
        actual_hash = hashlib.sha256(data).hexdigest()
        hash_mismatch = not isinstance(expected_hash, str) or actual_hash != expected_hash
        if hash_mismatch:
            _manifest_failure(failures, f"hash mismatch: {relative}")
        # SKILL.md documents the marker itself.  Its trusted size/hash still
        # catches any appended or altered marker; every other key file must
        # reject the marker directly as well.
        if TRUNCATION_MARKER in data and (relative != "SKILL.md" or size_mismatch or hash_mismatch):
            _manifest_failure(failures, f"truncation marker detected: {relative}")

    for required in REQUIRED_INTEGRITY_PATHS:
        if required not in seen:
            _manifest_failure(failures, f"required file missing from integrity manifest: {required}")

    # Check version declarations in every public entrypoint and the skill entry.
    declaration_checks = (
        ("SKILL.md", r"metadata:\s*\n\s*version:\s*[\"']([^\"']+)[\"']"),
        ("scripts/movie_organizing_preprocessor.py", r"^VERSION\s*=\s*[\"']([^\"']+)[\"']"),
        ("scripts/movie_organizing_audit.py", r"^VERSION\s*=\s*[\"']([^\"']+)[\"']"),
        ("scripts/movie_organizing_slowpath.py", r"^VERSION\s*=\s*[\"']([^\"']+)[\"']"),
        ("scripts/movie_organizing_task.py", r"^VERSION\s*=\s*[\"']([^\"']+)[\"']"),
    )
    for relative, pattern in declaration_checks:
        target = root / relative
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as error:
            _manifest_failure(failures, f"version declaration target missing: {relative}: {error}")
            continue
        match = re.search(pattern, text, flags=re.MULTILINE)
        if not match:
            _manifest_failure(failures, f"version declaration missing: {relative}")
        elif match.group(1) != VERSION:
            _manifest_failure(failures, f"version declaration mismatch: {relative}")

    result["status"] = "PASS" if not failures else "FAIL"
    return result


def _cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="movie-organizing audit and install verifier")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    audit_parser = subparsers.add_parser("audit", help="run CORE then (if allowed) DEDUPE gate")
    audit_parser.add_argument("--task-root", required=True)

    install_parser = subparsers.add_parser("verify-install", help="verify an installed skill directory")
    install_parser.add_argument("--skill-dir", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _cli_parser().parse_args(argv)
    if args.mode == "verify-install":
        result = verify_install(args.skill_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") == "PASS" else 1

    report, exit_code = audit_task_root(args.task_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
