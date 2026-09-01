#!/usr/bin/env python3
"""Bounded, decision-only slow channel for movie-organizing.

The deterministic preprocessor owns ordinary naming.  This entrypoint only
turns an Agent's semantic decision (``pending_isolation``, ``rehome_unit`` or
``dedupe_keep``) into a small, auditable action plan.  The actual filesystem
executor and rollback implementation are shared with the preprocessor.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


VERSION = "1.3.6"
AUDIT_SCHEMA = "movie-organizing-audit/v1"
TEMPLATE_SCHEMA = "movie-organizing-slowpath/template/v1"
PLAN_SCHEMA = "movie-organizing-slowpath/plan/v1"
DECISION_SCHEMAS = {
    "movie-organizing-slowpath/decisions/v1",
    "movie-organizing-decisions/v1",
}
RESULT_SCHEMA = "movie-organizing-slowpath/result/v1"
AUDIT_VERSION = "1.3.6"
WORK_RECORD_DIR = "_work-record_"
RECOVERY_DIR = "recovery"
PENDING_DIR = "_待确认_"
MAX_ITEMS = 20
LARGE_MAX_ITEMS = 5
CORE_PHASE = "core_exception"
DEDUPE_PHASE = "dedupe"
ALLOWED_PHASES = {CORE_PHASE, DEDUPE_PHASE}
CORE_DECISIONS = {"pending_isolation", "rehome_unit"}
DEDUPE_DECISIONS = {"dedupe_keep", "dedupe_pending"}
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
FORBIDDEN_DECISION_FIELDS = {
    "action",
    "actions",
    "source",
    "sources",
    "target",
    "targets",
    "from",
    "to",
    "move",
    "rename",
    "delete",
    "copy",
}


class SlowpathError(ValueError):
    """A user-fixable slow-channel contract violation."""


def _canonical(path: str | Path) -> Path:
    return Path(os.path.realpath(os.fspath(path)))


def _lexical(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _inside(root: str | Path, path: str | Path, *, allow_root: bool = False) -> bool:
    root_path = _canonical(root)
    path_path = _canonical(path)
    if allow_root and root_path == path_path:
        return True
    try:
        path_path.relative_to(root_path)
    except ValueError:
        return False
    return path_path != root_path


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S%f")


def _ensure_root(task_root: str | Path) -> Path:
    root = _canonical(task_root)
    if not root.is_dir() or root.is_symlink():
        raise SlowpathError("TASK_ROOT does not exist or is not a real directory")
    return root


def _ensure_recovery(root: Path) -> Path:
    work_record = root / WORK_RECORD_DIR
    recovery = work_record / RECOVERY_DIR
    for directory in (work_record, recovery):
        if os.path.lexists(directory):
            mode = os.lstat(directory).st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise SlowpathError(f"recovery control path is not a real directory: {directory}")
        else:
            directory.mkdir()
    if not _inside(root, recovery):
        raise SlowpathError("recovery directory is outside TASK_ROOT")
    return recovery


def _recovery_file(root: Path, value: str | Path, label: str) -> Path:
    recovery = _ensure_recovery(root)
    supplied = _lexical(value)
    if supplied.is_symlink():
        raise SlowpathError(f"{label} must not be a symlink")
    if not _inside(root, supplied) or not _inside(recovery, supplied):
        raise SlowpathError(f"{label} must be inside TASK_ROOT/_work-record_/recovery")
    try:
        mode = os.lstat(supplied).st_mode
    except OSError as error:
        raise SlowpathError(f"{label} cannot be inspected: {error}") from error
    if not stat.S_ISREG(mode):
        raise SlowpathError(f"{label} must be a regular file")
    return supplied


def _read_json(root: Path, value: str | Path, label: str) -> Tuple[Path, Dict[str, Any]]:
    path = _recovery_file(root, value, label)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SlowpathError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise SlowpathError(f"{label} must contain a JSON object")
    return path, payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_hash(value: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_audit(root: Path, value: str | Path) -> Tuple[Path, Dict[str, Any], str]:
    path, audit = _read_json(root, value, "audit report")
    if audit.get("schema") != AUDIT_SCHEMA:
        raise SlowpathError("audit schema mismatch")
    audit_root = audit.get("task_root")
    if not isinstance(audit_root, str) or _canonical(audit_root) != root:
        raise SlowpathError("audit task_root does not match TASK_ROOT")
    declared_path = audit.get("report_path")
    if not isinstance(declared_path, str) or _canonical(declared_path) != _canonical(path):
        raise SlowpathError("audit report_path does not match supplied audit path")
    if audit.get("version") != AUDIT_VERSION:
        raise SlowpathError(f"audit version mismatch: {audit.get('version')} != {AUDIT_VERSION}")
    return path, audit, _sha256(path)


def _candidate_id(phase: str, source: str, evidence: str) -> str:
    digest = hashlib.sha256(f"{phase}|{source}|{evidence}".encode("utf-8")).hexdigest()[:16]
    return f"{phase}-{digest}"


def _safe_active_path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SlowpathError(f"{label} is missing")
    lexical = _lexical(value)
    try:
        mode = os.lstat(lexical).st_mode
    except FileNotFoundError:
        mode = None
    except OSError as error:
        raise SlowpathError(f"{label} cannot be inspected: {error}") from error
    if mode is not None and stat.S_ISLNK(mode):
        raise SlowpathError(f"{label} must not be a symlink")
    path = _canonical(lexical)
    if not _inside(root, path):
        raise SlowpathError(f"{label} is outside TASK_ROOT")
    try:
        relative = path.relative_to(root)
    except ValueError as error:  # pragma: no cover - guarded by _inside
        raise SlowpathError(f"{label} is outside TASK_ROOT") from error
    if any(
        part == WORK_RECORD_DIR or part == PENDING_DIR or part.startswith("_trash_")
        for part in relative.parts
    ):
        raise SlowpathError(f"{label} must refer to the active media tree")
    return path


def _safe_candidate_container(root: Path, value: Any, label: str) -> Path:
    """Validate a read-only candidate container, allowing TASK_ROOT itself."""

    if not isinstance(value, str) or not value:
        raise SlowpathError(f"{label} is missing")
    lexical = _lexical(value)
    try:
        mode = os.lstat(lexical).st_mode
    except OSError as error:
        raise SlowpathError(f"{label} cannot be inspected: {error}") from error
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise SlowpathError(f"{label} must be a real directory")
    path = _canonical(lexical)
    if path != root and not _inside(root, path):
        raise SlowpathError(f"{label} is outside TASK_ROOT")
    if path != root:
        relative = path.relative_to(root)
        if any(
            part == WORK_RECORD_DIR or part == PENDING_DIR or part.startswith("_trash_")
            for part in relative.parts
        ):
            raise SlowpathError(f"{label} must refer to the active media tree")
    return path


def _extract_template_items(root: Path, audit: Dict[str, Any], phase: str) -> List[Dict[str, Any]]:
    if phase == CORE_PHASE:
        gate = audit.get("core_gate")
        if not isinstance(gate, dict):
            raise SlowpathError("audit core_gate is missing")
        raw: List[Dict[str, Any]] = []
        for kind, key in (("exception", "exceptions"), ("action_required", "action_required")):
            values = gate.get(key, [])
            if not isinstance(values, list):
                raise SlowpathError(f"audit core_gate.{key} is not a list")
            for entry in values:
                if not isinstance(entry, dict):
                    raise SlowpathError("audit core candidate is not an object")
                source = _safe_candidate_container(root, entry.get("path"), "core candidate path")
                evidence = entry.get("reason")
                if not isinstance(evidence, str) or not evidence:
                    raise SlowpathError("core candidate evidence is missing")
                raw.append(
                    {
                        "candidate_id": _candidate_id(phase, str(source), evidence),
                        "phase": phase,
                        "kind": kind,
                        "source": str(source),
                        "evidence": evidence,
                    }
                )
        return raw

    if phase == DEDUPE_PHASE:
        gate = audit.get("dedupe_gate")
        if not isinstance(gate, dict):
            raise SlowpathError("audit dedupe_gate is missing")
        groups = gate.get("candidate_groups", [])
        if not isinstance(groups, list):
            raise SlowpathError("audit dedupe_gate.candidate_groups is not a list")
        raw = []
        for group in groups:
            if not isinstance(group, dict):
                raise SlowpathError("dedupe candidate is not an object")
            members = group.get("members")
            if not isinstance(members, list) or not members:
                raise SlowpathError("dedupe candidate members are missing")
            safe_members = [str(_safe_active_path(root, member, "dedupe member")) for member in members]
            group_id = group.get("group_id")
            evidence = group.get("evidence", "")
            if not isinstance(group_id, str) or not group_id:
                group_id = _candidate_id(phase, "|".join(safe_members), str(evidence))
            raw.append(
                {
                    "candidate_id": group_id,
                    "phase": phase,
                    "kind": "dedupe_candidate",
                    "members": safe_members,
                    "evidence": str(evidence),
                    "group_key": group.get("group_key", {}),
                }
            )
        return raw

    raise SlowpathError(f"unsupported phase: {phase}")


def make_template(task_root: str | Path, audit_path: str | Path, phase: str, limit: int = MAX_ITEMS) -> Dict[str, Any]:
    root = _ensure_root(task_root)
    if phase not in ALLOWED_PHASES:
        raise SlowpathError(f"unsupported phase: {phase}")
    if not isinstance(limit, int) or limit < 1 or limit > MAX_ITEMS:
        raise SlowpathError(f"template limit must be between 1 and {MAX_ITEMS}")
    audit_file, audit, audit_hash = _load_audit(root, audit_path)
    large_library_mode = bool(audit.get("large_library_mode"))
    effective_limit = min(limit, LARGE_MAX_ITEMS) if large_library_mode else limit
    items = _extract_template_items(root, audit, phase)[:effective_limit]
    payload: Dict[str, Any] = {
        "schema": TEMPLATE_SCHEMA,
        "version": VERSION,
        "task_root": str(root),
        "phase": phase,
        "audit_path": str(audit_file),
        "audit_sha256": audit_hash,
        "items": items,
        "item_count": len(items),
        "max_items": effective_limit if large_library_mode else MAX_ITEMS,
        "large_library_mode": large_library_mode,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    recovery = _ensure_recovery(root)
    template_path = recovery / f"slow-template-{phase}-{_timestamp()}.json"
    payload["template_hash"] = _json_hash(payload)
    payload["template_path"] = str(template_path)
    _write_json(template_path, payload)
    return {
        "status": "PASS",
        "version": VERSION,
        "phase": phase,
        "template_path": str(template_path),
        "template_hash": payload["template_hash"],
        "item_count": len(items),
        "max_items": effective_limit if large_library_mode else MAX_ITEMS,
        "audit_path": str(audit_file),
        "audit_sha256": audit_hash,
    }


def _validate_template(root: Path, path: Path, template: Dict[str, Any], audit_path: Path, audit_hash: str) -> List[Dict[str, Any]]:
    if template.get("schema") != TEMPLATE_SCHEMA:
        raise SlowpathError("template schema mismatch")
    if template.get("version") != VERSION:
        raise SlowpathError("template version mismatch")
    if _canonical(str(template.get("task_root", ""))) != root:
        raise SlowpathError("template task_root does not match TASK_ROOT")
    phase = template.get("phase")
    if phase not in ALLOWED_PHASES:
        raise SlowpathError("template phase is invalid")
    if _canonical(str(template.get("audit_path", ""))) != _canonical(audit_path):
        raise SlowpathError("template audit path drift")
    if template.get("audit_sha256") != audit_hash:
        raise SlowpathError("template audit hash drift")
    declared_path = template.get("template_path")
    if not isinstance(declared_path, str) or _canonical(declared_path) != _canonical(path):
        raise SlowpathError("template_path does not match supplied template")
    template_hash = template.get("template_hash")
    if not isinstance(template_hash, str) or not template_hash:
        raise SlowpathError("template hash is missing")
    without_hash = dict(template)
    without_hash.pop("template_hash", None)
    # The recovery filename is transport metadata.  It must not be part of
    # the semantic hash, so copying a valid template to another recovery
    # filename does not change its meaning.
    without_hash.pop("template_path", None)
    if template_hash != _json_hash(without_hash):
        raise SlowpathError("template hash mismatch")
    large_library_mode = bool(template.get("large_library_mode"))
    max_items = LARGE_MAX_ITEMS if large_library_mode else MAX_ITEMS
    items = template.get("items")
    if not isinstance(items, list):
        raise SlowpathError("template items are missing or invalid")
    if len(items) > max_items:
        raise SlowpathError(f"template contains more than {max_items} items")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SlowpathError(f"template item {index} is not an object")
        if not isinstance(item.get("candidate_id"), str) or not item["candidate_id"]:
            raise SlowpathError(f"template item {index} candidate_id is missing")
        if item.get("phase") != phase:
            raise SlowpathError(f"template item {index} phase mismatch")
        if phase == CORE_PHASE:
            _safe_candidate_container(root, item.get("source"), f"template item {index} source")
        else:
            members = item.get("members")
            if not isinstance(members, list) or not members:
                raise SlowpathError(f"template item {index} members are missing")
            for member in members:
                _safe_active_path(root, member, f"template item {index} member")
    return items


def _load_decisions(root: Path, path: Path, phase: str) -> List[Dict[str, Any]]:
    _path, decisions = _read_json(root, path, "decisions")
    if decisions.get("schema") not in DECISION_SCHEMAS:
        raise SlowpathError("decisions schema mismatch")
    if decisions.get("version") not in (None, VERSION):
        raise SlowpathError("decisions version mismatch")
    if decisions.get("task_root") is not None and _canonical(str(decisions["task_root"])) != root:
        raise SlowpathError("decisions task_root does not match TASK_ROOT")
    if decisions.get("phase") != phase:
        raise SlowpathError("decisions phase does not match template phase")
    entries = decisions.get("items", decisions.get("decisions"))
    if not isinstance(entries, list):
        raise SlowpathError("decisions items are missing or invalid")
    if len(entries) > MAX_ITEMS:
        raise SlowpathError(f"decisions contain more than {MAX_ITEMS} items")
    allowed_extra = {
        CORE_PHASE: {
            "evidence",
            "reason",
            "main_video_name",
            "resolved_director_name",
            "resolved_chinese_title",
        },
        DEDUPE_PHASE: {
            "keep_member",
            "keep_movie_dir",
            "same_identity",
            "same_edition_cut",
            "quality_evidence",
            "full_hash_evidence",
            "evidence",
            "reason",
        },
    }[phase]
    base_fields = {"candidate_id", "decision"}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SlowpathError(f"decision {index} is not an object")
        if any(key in entry for key in FORBIDDEN_DECISION_FIELDS):
            raise SlowpathError(f"decision {index} contains direct action/path fields")
        unknown = set(entry) - base_fields - allowed_extra
        if unknown:
            raise SlowpathError(f"decision {index} contains unsupported fields: {sorted(unknown)}")
        if not isinstance(entry.get("candidate_id"), str) or not entry["candidate_id"]:
            raise SlowpathError(f"decision {index} candidate_id is missing")
        if not isinstance(entry.get("decision"), str) or not entry["decision"]:
            raise SlowpathError(f"decision {index} decision is missing")
        if phase == CORE_PHASE and entry["decision"] == "rehome_unit":
            evidence = entry.get("evidence")
            if not isinstance(evidence, str) or not evidence.strip():
                raise SlowpathError(f"decision {index} rehome_unit requires non-empty evidence")
        if phase == CORE_PHASE and entry["decision"] == "pending_isolation":
            reason = entry.get("reason", entry.get("evidence"))
            if not isinstance(reason, str) or not reason.strip():
                raise SlowpathError(f"decision {index} pending_isolation requires non-empty reason/evidence")
        if phase == DEDUPE_PHASE and entry["decision"] == "dedupe_keep":
            if entry.get("same_identity") is not True:
                raise SlowpathError(f"decision {index} requires same_identity=true")
            if entry.get("same_edition_cut") is not True:
                raise SlowpathError(f"decision {index} requires same_edition_cut=true")
            quality = entry.get("quality_evidence")
            if isinstance(quality, str):
                quality_present = bool(quality.strip())
            elif isinstance(quality, (list, dict)):
                quality_present = bool(quality)
            else:
                quality_present = False
            if not quality_present:
                raise SlowpathError(f"decision {index} requires non-empty quality_evidence")
        if phase == DEDUPE_PHASE and entry["decision"] == "dedupe_pending":
            if entry.get("keep_member") is not None or entry.get("keep_movie_dir") is not None:
                raise SlowpathError(f"decision {index} dedupe_pending must not select a winner")
            reason = entry.get("reason", entry.get("evidence"))
            if not isinstance(reason, str) or not reason.strip():
                raise SlowpathError(f"decision {index} dedupe_pending requires a non-empty reason")
    return entries


def _action(
    action_id: str,
    name: str,
    target: Path,
    *,
    source: Optional[Path] = None,
    evidence: str,
    rollback: str,
    preconditions: Sequence[str],
    postconditions: Sequence[str],
) -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "id": action_id,
        "action": name,
        "target": str(target),
        "evidence": evidence,
        "rollback": rollback,
        "preconditions": list(preconditions),
        "postconditions": list(postconditions),
    }
    if source is not None:
        value["source"] = str(source)
    return value


def _mkdir_actions(parent: Path, target: Path, prefix: str, actions: List[Dict[str, Any]]) -> None:
    """Append missing target parents in ancestor-first order.

    Existing real directories are already-satisfied ancestors.  Files and
    symlinks at any existing path component remain hard failures, as does a
    target outside ``parent``.
    """

    parent = _lexical(parent)
    target = _lexical(target)
    if target == parent:
        return
    if not _inside(parent, target, allow_root=False):
        raise SlowpathError(f"target parent is outside planned root: {target}")
    already_planned = {
        _canonical(str(action.get("target")))
        for action in actions
        if action.get("action") == "mkdir" and action.get("target")
    }
    missing: List[Path] = []
    current = target
    while current != parent and _canonical(current) not in already_planned:
        if os.path.lexists(current):
            try:
                mode = os.lstat(current).st_mode
            except OSError as error:
                raise SlowpathError(f"target ancestor cannot be inspected: {current}: {error}") from error
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise SlowpathError(f"target ancestor is not a real directory: {current}")
        else:
            missing.append(current)
        current = current.parent
    if current != parent and _canonical(current) not in already_planned:
        raise SlowpathError(f"target parent is outside planned root: {target}")
    for index, directory in enumerate(reversed(missing), start=1):
        actions.append(
            _action(
                f"{prefix}-mkdir-{index}",
                "mkdir",
                directory,
                evidence="slowpath target directory derived from semantic decision",
                rollback="rename created empty directory into recovery rollback archive",
                preconditions=["target absent", "target under TASK_ROOT"],
                postconditions=["target directory exists"],
            )
        )
        already_planned.add(_canonical(directory))


def _find_bundle_for_source(root: Path, source: Path) -> Dict[str, Any]:
    script = Path(__file__).resolve().with_name("movie_organizing_preprocessor.py")
    spec = importlib.util.spec_from_file_location("movie_organizing_slowpath_preprocessor", script)
    if spec is None or spec.loader is None:
        raise SlowpathError("cannot load naming preprocessor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        plan = module.make_plan(root, persist=False)
    except (OSError, ValueError) as error:
        raise SlowpathError(f"fresh naming plan failed: {error}") from error
    for bundle in plan.get("bundles", []):
        if not isinstance(bundle, dict):
            continue
        if _canonical(str(bundle.get("source_movie_dir", ""))) == source:
            return bundle
    raise SlowpathError("candidate source is not present in the fresh naming plan")


def _basename_choice(value: Any, label: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise SlowpathError(f"{label} must be a non-empty basename")
    if Path(value).name != value or "/" in value or "\\" in value or "\x00" in value:
        raise SlowpathError(f"{label} must be a basename inside the candidate unit")
    return value


def _inspect_candidate_unit(root: Path, container: Path, main_video_name: Any = None) -> Dict[str, Any]:
    """Inspect only direct children; never infer a winner from a container."""

    selected_name = _basename_choice(main_video_name, "main_video_name")
    try:
        entries = list(os.scandir(container))
    except OSError as error:
        raise SlowpathError(f"candidate container cannot be scanned: {error}") from error
    videos: List[Path] = []
    child_dirs: List[Path] = []
    files: List[Path] = []
    for entry in entries:
        path = _lexical(entry.path)
        try:
            mode = os.lstat(path).st_mode
        except OSError as error:
            raise SlowpathError(f"candidate entry cannot be inspected: {path}: {error}") from error
        if stat.S_ISLNK(mode):
            raise SlowpathError(f"candidate container contains a symlink: {path}")
        if stat.S_ISDIR(mode):
            child_dirs.append(path)
        elif stat.S_ISREG(mode):
            files.append(path)
            if path.suffix.casefold() in VIDEO_EXTENSIONS:
                videos.append(path)
        else:
            raise SlowpathError(f"candidate container contains unsupported entry: {path}")
    videos.sort(key=lambda path: path.name.casefold())
    if selected_name is None:
        if len(videos) != 1:
            raise SlowpathError("candidate has multiple or no videos; main_video_name is required")
        selected = videos[0]
    else:
        matches = [video for video in videos if video.name == selected_name]
        if len(matches) != 1:
            raise SlowpathError("main_video_name does not identify exactly one direct video")
        selected = matches[0]

    prefix = f"{selected.stem}.".casefold()
    nfo: List[Path] = []
    subtitles: List[Tuple[Path, str]] = []
    ambiguous_sidecars: List[Path] = []
    associated: set[Path] = {selected}
    subtitle_target_keys: set[str] = set()
    for path in files:
        if path == selected:
            continue
        lower_name = path.name.casefold()
        if lower_name == f"{selected.stem}.nfo".casefold():
            nfo.append(path)
            associated.add(path)
            continue
        if lower_name.startswith(prefix) and path.suffix.casefold() in SUBTITLE_EXTENSIONS:
            suffix = path.name[len(selected.stem) :]
            language_match = re.fullmatch(
                r"\.(zh|chn|chn0|chs|cht|eng)(\.[^.]+)", suffix, flags=re.IGNORECASE
            )
            if not language_match:
                ambiguous_sidecars.append(path)
                continue
            marker = language_match.group(1).casefold()
            marker = {"zh": "chs", "chn": "chs", "chn0": "chs"}.get(marker, marker)
            normalized_suffix = f".{marker}{language_match.group(2)}"
            if normalized_suffix.casefold() in subtitle_target_keys:
                raise SlowpathError("selected video has ambiguous duplicate subtitle sidecars")
            subtitle_target_keys.add(normalized_suffix.casefold())
            subtitles.append((path, normalized_suffix))
            associated.add(path)
            continue
    if len(nfo) > 1:
        raise SlowpathError("selected video has ambiguous duplicate NFO sidecars")
    unknown_files = [path for path in files if path not in associated]
    return {
        "videos": videos,
        "selected": selected,
        "child_dirs": child_dirs,
        "nfo": nfo,
        "subtitles": subtitles,
        "ambiguous_sidecars": ambiguous_sidecars,
        "unknown_files": unknown_files,
        "leaf": (
            len(videos) == 1
            and len(child_dirs) == 0
            and len(unknown_files) == 0
            and len(ambiguous_sidecars) == 0
        ),
    }


def _looks_like_director_anchor(root: Path, source: Path, preprocessor: Any) -> bool:
    """Conservatively protect director anchors from whole-directory moves."""

    if source == root or source.parent == root:
        return True
    try:
        if preprocessor._parse_movie_dir(source.name) is not None:
            return False
        if not preprocessor._is_cjk(source.name):
            return False
        return preprocessor._normalize_director_name(source.name) is not None
    except AttributeError:
        return False


def _validate_director_choice(root: Path, value: Any, preprocessor: Any) -> Path:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise SlowpathError("resolved_director_name is required")
    if Path(value).name != value or "/" in value or "\\" in value or "\x00" in value:
        raise SlowpathError("resolved_director_name must be one standard directory name")
    normalized = preprocessor._normalize_director_name(value)
    if normalized != value:
        raise SlowpathError("resolved_director_name is not already in the naming-contract form")
    target = root / value
    if not _inside(root, target, allow_root=False) or value in {WORK_RECORD_DIR, PENDING_DIR} or value.startswith("_trash_"):
        raise SlowpathError("resolved_director_name targets a reserved or unsafe directory")
    return target


def _validate_chinese_title(value: Any, preprocessor: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SlowpathError("resolved_chinese_title is required")
    title = value.strip()
    if any(not preprocessor._is_allowed_chinese_title_char(char) for char in title):
        raise SlowpathError("resolved_chinese_title contains unsupported characters")
    if not preprocessor._is_cjk(title):
        raise SlowpathError("resolved_chinese_title must contain Chinese characters")
    return title


def _build_semantic_rehome_actions(
    root: Path,
    source: Path,
    decision: Dict[str, Any],
    index: int,
    preprocessor: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    inspected = _inspect_candidate_unit(root, source, decision.get("main_video_name"))
    # A TASK_ROOT/director anchor may contain several independent orphan
    # videos (and the control directory at TASK_ROOT).  An explicit basename
    # selects only one such unit; never move the anchor or its siblings.  Any
    # ordinary movie/container must still be a minimal leaf for semantic
    # rehome, so dirty wrappers, unknown files, child directories, and
    # multi-video containers are routed to pending isolation instead.
    anchor_selection = (
        decision.get("main_video_name") is not None
        and _looks_like_director_anchor(root, source, preprocessor)
    )
    if not inspected["leaf"] and not anchor_selection:
        raise SlowpathError(
            "semantic rehome requires a minimal leaf; use pending_isolation for dirty or multi-video containers"
        )
    selected = inspected["selected"]
    parsed = preprocessor._parse_video_stem(selected.stem)
    if not isinstance(parsed, dict):
        raise SlowpathError("selected video filename has no deterministic title/year")
    director = _validate_director_choice(root, decision.get("resolved_director_name"), preprocessor)
    chinese_title = _validate_chinese_title(decision.get("resolved_chinese_title"), preprocessor)
    agent_evidence = str(decision["evidence"]).strip()
    normalized_stem = str(parsed.get("normalized_stem", ""))
    if not normalized_stem:
        raise SlowpathError("selected video filename has no normalized stem")
    target_dir = director / f"{chinese_title}.{normalized_stem}"
    if not _inside(root, target_dir, allow_root=False):
        raise SlowpathError("semantic rehome target is outside TASK_ROOT")
    if target_dir.exists() or os.path.lexists(target_dir):
        raise SlowpathError("semantic rehome target movie directory already exists")
    if inspected["ambiguous_sidecars"]:
        raise SlowpathError("selected video sidecar pairing is ambiguous")
    leaf_rename = (
        inspected["leaf"]
        and source != root
        and not _looks_like_director_anchor(root, source, preprocessor)
    )
    file_specs: List[Tuple[Path, str, str]] = [
        (selected, f"{normalized_stem}{selected.suffix}", "video")
    ]
    if inspected["nfo"]:
        file_specs.append((inspected["nfo"][0], f"{normalized_stem}.nfo", "NFO"))
    file_specs.extend(
        (sidecar, f"{normalized_stem}{suffix}", "subtitle")
        for sidecar, suffix in inspected["subtitles"]
    )
    target_names: set[str] = set()
    for _source_file, filename, _kind in file_specs:
        key = filename.casefold()
        if key in target_names:
            raise SlowpathError("semantic rehome target has duplicate bundle names")
        target_names.add(key)
    actions: List[Dict[str, Any]] = []
    if leaf_rename:
        _mkdir_actions(root, director, f"u{index}", actions)
    else:
        _mkdir_actions(root, target_dir, f"u{index}", actions)
    checks: Dict[str, List[str]] = {"source_absent": [], "targets_exist": [str(target_dir)]}
    for file_index, (source_file, filename, kind) in enumerate(file_specs, start=1):
        final_target = target_dir / filename
        if os.path.lexists(final_target) and final_target != source_file:
            raise SlowpathError(f"semantic rehome {kind} target already exists")
        staging_target = source / filename if leaf_rename else final_target
        if os.path.lexists(staging_target) and staging_target != source_file:
            raise SlowpathError(f"semantic rehome {kind} staging target already exists")
        if staging_target != source_file:
            actions.append(
                _action(
                    f"u{index}-rehome-{kind.casefold()}-{file_index}",
                    "rename_path",
                    staging_target,
                    source=source_file,
                    evidence=(
                        "Agent resolved director and Chinese title; video stem/year/release came from selected filename; "
                        f"Agent evidence: {agent_evidence}"
                        if kind == "video"
                        else f"unique same-stem {kind} follows selected video; Agent evidence: {agent_evidence}"
                    ),
                    rollback="rename target back to source",
                    preconditions=["selected bundle member exists", "target absent", "paths under TASK_ROOT"],
                    postconditions=["source member absent", "normalized bundle member exists"],
                )
            )
        checks["source_absent"].append(str(source_file))
        checks["targets_exist"].append(str(final_target))
    if leaf_rename:
        actions.append(
            _action(
                f"u{index}-rehome-leaf",
                "rename_path",
                target_dir,
                source=source,
                evidence="minimal leaf normalized in place, then flattened into resolved director root",
                rollback="rename target leaf back to source",
                preconditions=["source is a minimal leaf", "target absent", "leaf and target under TASK_ROOT"],
                postconditions=["old leaf absent", "resolved movie directory exists"],
            )
        )
        checks["source_absent"].append(str(source))
    return actions, {
        "candidate_id": "",
        "decision": "rehome_unit",
        "resolved_director_name": director.name,
        "resolved_chinese_title": chinese_title,
        "main_video_name": selected.name,
        "evidence": agent_evidence,
        "checks": checks,
    }


def _build_core_actions(root: Path, item: Dict[str, Any], decision: Dict[str, Any], index: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    source = _safe_candidate_container(root, item.get("source"), "core candidate source")
    if not source.exists() or source.is_symlink():
        raise SlowpathError("core candidate source is missing or is a symlink")
    choice = decision["decision"]
    preprocessor = _load_preprocessor_module()
    decision_evidence = str(
        decision.get("reason", decision.get("evidence", ""))
    ).strip()
    actions: List[Dict[str, Any]] = []
    checks: Dict[str, List[str]] = {"source_absent": [], "targets_exist": []}
    if choice == "pending_isolation":
        explicit_main = decision.get("main_video_name") is not None
        is_anchor = _looks_like_director_anchor(root, source, preprocessor)
        # Ordinary candidate containers are isolated as a whole, regardless
        # of whether they are minimal leaves.  This preserves notes, nested
        # directories, and every video in a dirty wrapper for later review;
        # no main-video choice is needed (or allowed to cause a partial move).
        if not is_anchor:
            target = root / PENDING_DIR / f"{item['candidate_id']}-{source.name}"
            if os.path.lexists(target):
                raise SlowpathError("pending isolation target already exists")
            _mkdir_actions(root, target.parent, f"u{index}", actions)
            actions.append(
                _action(
                    f"u{index}-pending-rename",
                    "rename_path",
                    target,
                    source=source,
                    evidence=decision_evidence,
                    rollback="rename target back to source",
                    preconditions=[
                        "source is a non-anchor candidate container",
                        "target absent",
                        "source and target under TASK_ROOT",
                    ],
                    postconditions=[
                        "source absent",
                        "pending target exists with all original contents",
                    ],
                )
            )
            checks["source_absent"].append(str(source))
            checks["targets_exist"].append(str(target))
        else:
            # TASK_ROOT and director anchors can contain independent orphan
            # videos.  They must never be displaced as a whole; an explicit
            # basename selects only one video and its uniquely paired sidecars.
            if not explicit_main:
                raise SlowpathError(
                    "pending_isolation requires main_video_name for TASK_ROOT or a director anchor"
                )
            inspected = _inspect_candidate_unit(root, source, decision.get("main_video_name"))
            if inspected["ambiguous_sidecars"]:
                raise SlowpathError("selected video sidecar pairing is ambiguous")
            selected = inspected["selected"]
            parsed = preprocessor._parse_video_stem(selected.stem)
            derived_name = str(parsed.get("normalized_stem", "")) if isinstance(parsed, dict) else selected.stem
            if not derived_name or Path(derived_name).name != derived_name:
                raise SlowpathError("selected video has no safe derived pending name")
            target = root / PENDING_DIR / f"{item['candidate_id']}-{derived_name}"
            if os.path.lexists(target):
                raise SlowpathError("pending isolation target already exists")
            _mkdir_actions(root, target.parent, f"u{index}", actions)
            _mkdir_actions(root, target, f"u{index}-selected", actions)
            checks["targets_exist"].append(str(target))
            selected_files: List[Tuple[Path, str]] = [(selected, selected.name)]
            selected_files.extend((path, path.name) for path in inspected["nfo"])
            selected_files.extend((path, path.name) for path, _suffix in inspected["subtitles"])
            for selected_index, (selected_path, filename) in enumerate(selected_files, start=1):
                target_file = target / filename
                actions.append(
                    _action(
                        f"u{index}-pending-file-{selected_index}",
                        "rename_path",
                        target_file,
                        source=selected_path,
                        evidence=decision_evidence,
                        rollback="rename pending file back to source",
                        preconditions=["selected file exists", "target absent", "paths under TASK_ROOT"],
                        postconditions=["selected source absent", "pending file exists"],
                    )
                )
                checks["source_absent"].append(str(selected_path))
                checks["targets_exist"].append(str(target_file))
    elif choice == "rehome_unit":
        semantic_requested = any(
            key in decision
            for key in ("resolved_director_name", "resolved_chinese_title", "main_video_name")
        )
        bundle: Dict[str, Any] = {}
        if not semantic_requested:
            bundle = _find_bundle_for_source(root, source)
        if semantic_requested or bundle.get("status") == "EXCEPTION":
            generated, semantic_item = _build_semantic_rehome_actions(
                root, source, decision, index, preprocessor
            )
            semantic_item["candidate_id"] = item["candidate_id"]
            return generated, semantic_item
        if bundle.get("status") != "ACTION_REQUIRED":
            raise SlowpathError("rehome_unit requires an ACTION_REQUIRED naming bundle or complete semantic fields")
        bundle_actions = bundle.get("actions")
        if not isinstance(bundle_actions, list) or not bundle_actions:
            raise SlowpathError("rehome_unit naming bundle has no executable actions")
        for action_index, original in enumerate(bundle_actions, start=1):
            if not isinstance(original, dict):
                raise SlowpathError("naming bundle action is not an object")
            name = str(original.get("action", original.get("type", "")))
            target = _canonical(str(original.get("target", "")))
            if name == "mkdir":
                actions.append(
                    _action(
                        f"u{index}-mkdir-{action_index}",
                        "mkdir",
                        target,
                        evidence=str(original.get("evidence", "derived naming bundle")),
                        rollback="rename created empty directory into recovery rollback archive",
                        preconditions=["target absent", "target under TASK_ROOT"],
                        postconditions=["target directory exists"],
                    )
                )
                continue
            if name not in {"move_file", "rename_dir", "rename_path"}:
                raise SlowpathError(f"unsupported naming bundle action for slowpath: {name}")
            original_source = _safe_active_path(root, original.get("source"), "naming bundle source")
            actions.append(
                _action(
                    f"u{index}-rename-{action_index}",
                    "rename_path",
                    target,
                    source=original_source,
                    evidence=(
                        f"{original.get('evidence', 'derived naming bundle')}; Agent evidence: {decision_evidence}"
                    ),
                    rollback="rename target back to source",
                    preconditions=["source exists", "target absent", "source and target under TASK_ROOT"],
                    postconditions=["source absent", "target exists"],
                )
            )
            checks["source_absent"].append(str(original_source))
            checks["targets_exist"].append(str(target))
        expected_dir = bundle.get("expected_movie_dir_path")
        if isinstance(expected_dir, str) and expected_dir:
            checks["targets_exist"].append(str(_safe_active_path(root, expected_dir, "expected movie directory")))
    else:
        raise SlowpathError(f"decision {choice} is not allowed in core_exception phase")
    plan_item: Dict[str, Any] = {
        "candidate_id": item["candidate_id"],
        "decision": choice,
        "checks": checks,
    }
    if "reason" in decision:
        plan_item["reason"] = decision["reason"]
    if "evidence" in decision:
        plan_item["evidence"] = decision["evidence"]
    return actions, plan_item


def _build_dedupe_actions(root: Path, item: Dict[str, Any], decision: Dict[str, Any], index: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    members = item.get("members")
    if not isinstance(members, list) or not members:
        raise SlowpathError("dedupe candidate members are missing")
    member_paths = [_safe_active_path(root, member, "dedupe member") for member in members]
    keep_value = decision.get("keep_member", decision.get("keep_movie_dir"))
    choice = decision["decision"]
    if choice == "dedupe_pending":
        pending_group = root / PENDING_DIR / str(item["candidate_id"])
        if os.path.lexists(pending_group):
            raise SlowpathError("dedupe_pending target group already exists")
        actions: List[Dict[str, Any]] = []
        _mkdir_actions(root, pending_group, f"g{index}", actions)
        checks: Dict[str, List[str]] = {"source_absent": [], "targets_exist": [str(pending_group)]}
        names: set[str] = set()
        for loser_index, member in enumerate(member_paths, start=1):
            if not member.is_dir() or member.is_symlink():
                raise SlowpathError("dedupe_pending members must be real movie directories")
            if member.name.casefold() in names:
                raise SlowpathError("dedupe_pending member directory name collision")
            names.add(member.name.casefold())
            target = pending_group / member.name
            if os.path.lexists(target):
                raise SlowpathError("dedupe_pending member target already exists")
            actions.append(
                _action(
                    f"g{index}-pending-{loser_index}",
                    "rename_path",
                    target,
                    source=member,
                    evidence=str(
                        decision.get(
                            "reason",
                            decision.get("evidence", "Agent marked duplicate identity/edition unresolved"),
                        )
                    ),
                    rollback="rename pending duplicate back to source",
                    preconditions=["member exists", "target absent", "paths under TASK_ROOT"],
                    postconditions=["member absent from active tree", "pending member exists"],
                )
            )
            checks["source_absent"].append(str(member))
            checks["targets_exist"].append(str(target))
        return actions, {
            "candidate_id": item["candidate_id"],
            "decision": "dedupe_pending",
            "reason": str(decision.get("reason", decision.get("evidence", ""))),
            "checks": checks,
        }
    keep = _safe_active_path(root, keep_value, "dedupe keep member")
    if keep not in member_paths:
        raise SlowpathError("dedupe keep member must be one of the template members")
    losers = [member for member in member_paths if member != keep]
    if not losers:
        raise SlowpathError("dedupe_keep requires at least one loser")
    trash_root = root / f"_trash_{item['candidate_id'][:16]}_{datetime.now().strftime('%Y%m%d')}"
    actions: List[Dict[str, Any]] = []
    _mkdir_actions(root, trash_root, f"g{index}", actions)
    semantic_evidence = {
        "same_identity": decision.get("same_identity"),
        "same_edition_cut": decision.get("same_edition_cut"),
        "quality_evidence": decision.get("quality_evidence"),
    }
    if "full_hash_evidence" in decision:
        semantic_evidence["full_hash_evidence"] = decision.get("full_hash_evidence")
    if decision.get("evidence") is not None:
        semantic_evidence["evidence"] = decision.get("evidence")
    if decision.get("reason") is not None:
        semantic_evidence["reason"] = decision.get("reason")
    evidence_text = json.dumps(semantic_evidence, ensure_ascii=False, sort_keys=True)
    checks: Dict[str, List[str]] = {"source_absent": [], "targets_exist": [str(keep)]}
    for loser_index, loser in enumerate(losers, start=1):
        relative = loser.relative_to(root)
        target = trash_root / relative
        _mkdir_actions(root, target.parent, f"g{index}-loser{loser_index}", actions)
        actions.append(
            _action(
                f"g{index}-trash-{loser_index}",
                "rename_path",
                target,
                source=loser,
                evidence=evidence_text,
                rollback="rename trash target back to source",
                preconditions=["loser exists", "trash target absent", "paths under TASK_ROOT"],
                postconditions=["loser absent from active tree", "trash target exists"],
            )
        )
        checks["source_absent"].append(str(loser))
        checks["targets_exist"].append(str(target))
    plan_item: Dict[str, Any] = {
        "candidate_id": item["candidate_id"],
        "decision": "dedupe_keep",
        "keep_member": str(keep),
        "checks": checks,
    }
    for field in (
        "same_identity",
        "same_edition_cut",
        "quality_evidence",
        "full_hash_evidence",
        "evidence",
        "reason",
    ):
        if field in decision:
            plan_item[field] = decision[field]
    return actions, plan_item


def _validate_actions(root: Path, actions: Sequence[Dict[str, Any]]) -> None:
    script = Path(__file__).resolve().with_name("movie_organizing_preprocessor.py")
    spec = importlib.util.spec_from_file_location("movie_organizing_slowpath_action_validator", script)
    if spec is None or spec.loader is None:
        raise SlowpathError("cannot load naming preprocessor validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    planned_dirs: set[Path] = set()
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise SlowpathError(f"action {index} is not an object")
        name = str(action.get("action", ""))
        if name not in {"mkdir", "rename_path"}:
            raise SlowpathError(f"slowpath action {index} is not reversible rename/mkdir")
        failure = module._validate_action(action, root, planned_dirs)
        if failure:
            raise SlowpathError(f"action {index} rejected: {failure}")
        if name == "mkdir":
            planned_dirs.add(_canonical(str(action["target"])))


def _plan_payload(
    root: Path,
    audit_path: Path,
    audit_hash: str,
    audit_core_status: str,
    template_path: Path,
    template: Dict[str, Any],
    decisions_path: Path,
    decisions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    phase = str(template["phase"])
    items = list(template["items"])
    by_id = {item["candidate_id"]: item for item in items}
    if len(by_id) != len(items):
        raise SlowpathError("template contains duplicate candidate_id values")
    decision_by_id = {entry["candidate_id"]: entry for entry in decisions}
    if len(decision_by_id) != len(decisions):
        raise SlowpathError("decisions contain duplicate candidate_id values")
    if set(decision_by_id) != set(by_id):
        raise SlowpathError("decisions must provide exactly one semantic decision per candidate")
    allowed = CORE_DECISIONS if phase == CORE_PHASE else DEDUPE_DECISIONS
    for entry in decisions:
        if entry["decision"] not in allowed:
            raise SlowpathError(f"decision {entry['decision']} is not allowed in phase {phase}")

    actions: List[Dict[str, Any]] = []
    plan_items: List[Dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        entry = decision_by_id[item["candidate_id"]]
        if phase == CORE_PHASE:
            generated, plan_item = _build_core_actions(root, item, entry, index)
        else:
            generated, plan_item = _build_dedupe_actions(root, item, entry, index)
        actions.extend(generated)
        plan_items.append(plan_item)

    _validate_actions(root, actions)
    candidate_snapshot: List[Dict[str, Any]] = []
    for item in items:
        snapshot: Dict[str, Any] = {
            "candidate_id": item["candidate_id"],
            "phase": phase,
        }
        if phase == CORE_PHASE:
            snapshot["source"] = str(
                _safe_candidate_container(root, item.get("source"), "planned candidate source")
            )
        else:
            snapshot["members"] = sorted(
                str(_safe_active_path(root, member, "planned dedupe member"))
                for member in item.get("members", [])
            )
        candidate_snapshot.append(snapshot)
    payload: Dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "version": VERSION,
        "task_root": str(root),
        "phase": phase,
        "audit_path": str(audit_path),
        "audit_sha256": audit_hash,
        "audit_core_status": audit_core_status,
        "template_path": str(template_path),
        "template_hash": str(template.get("template_hash", "")),
        "decisions_path": str(decisions_path),
        "candidate_snapshot": candidate_snapshot,
        "items": plan_items,
        "actions": actions,
        "max_items": MAX_ITEMS,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    payload["plan_hash"] = _json_hash(payload)
    return payload


def make_plan(
    task_root: str | Path,
    audit_path: str | Path,
    template_path: str | Path,
    decisions_path: str | Path,
) -> Dict[str, Any]:
    root = _ensure_root(task_root)
    audit_file, audit, audit_hash = _load_audit(root, audit_path)
    template_file, template = _read_json(root, template_path, "template")
    items = _validate_template(root, template_file, template, audit_file, audit_hash)
    if len(items) > MAX_ITEMS:
        raise SlowpathError(f"template contains more than {MAX_ITEMS} items")
    decisions_file, decisions_payload = _read_json(root, decisions_path, "decisions")
    decisions = _load_decisions(root, decisions_file, str(template["phase"]))
    if str(template["phase"]) == DEDUPE_PHASE:
        core_gate = audit.get("core_gate")
        if not isinstance(core_gate, dict) or core_gate.get("status") != "PASS":
            raise SlowpathError("dedupe_keep requires audit CORE_GATE=PASS")
    payload = _plan_payload(
        root,
        audit_file,
        audit_hash,
        str(audit.get("core_gate", {}).get("status", ""))
        if isinstance(audit.get("core_gate"), dict)
        else "",
        template_file,
        template,
        decisions_file,
        decisions,
    )
    recovery = _ensure_recovery(root)
    plan_file = recovery / f"slow-plan-{template['phase']}-{_timestamp()}.json"
    payload["plan_path"] = str(plan_file)
    _write_json(plan_file, payload)
    return {
        "status": "PASS",
        "version": VERSION,
        "phase": payload["phase"],
        "plan_path": str(plan_file),
        "plan_hash": payload["plan_hash"],
        "planned_actions": len(payload["actions"]),
        "item_count": len(payload["items"]),
    }


def _load_plan(root: Path, value: str | Path) -> Tuple[Path, Dict[str, Any]]:
    path, plan = _read_json(root, value, "plan")
    if plan.get("schema") != PLAN_SCHEMA:
        raise SlowpathError("plan schema mismatch")
    if plan.get("version") != VERSION:
        raise SlowpathError("plan version mismatch")
    if _canonical(str(plan.get("task_root", ""))) != root:
        raise SlowpathError("plan task_root does not match TASK_ROOT")
    if plan.get("phase") not in ALLOWED_PHASES:
        raise SlowpathError("plan phase is invalid")
    if _canonical(str(plan.get("plan_path", ""))) != _canonical(path):
        raise SlowpathError("plan_path does not match supplied plan")
    actions = plan.get("actions")
    items = plan.get("items")
    if not isinstance(actions, list) or not isinstance(items, list):
        raise SlowpathError("plan actions/items are missing or invalid")
    if len(items) > MAX_ITEMS:
        raise SlowpathError(f"plan contains more than {MAX_ITEMS} items")
    snapshots = plan.get("candidate_snapshot")
    if not isinstance(snapshots, list) or len(snapshots) != len(items):
        raise SlowpathError("plan candidate snapshot is missing or does not match items")
    item_ids = {item.get("candidate_id") for item in items if isinstance(item, dict)}
    snapshot_ids = {item.get("candidate_id") for item in snapshots if isinstance(item, dict)}
    if item_ids != snapshot_ids or len(snapshot_ids) != len(snapshots):
        raise SlowpathError("plan candidate snapshot ids do not match items")
    if not isinstance(plan.get("audit_core_status"), str) or not plan["audit_core_status"]:
        raise SlowpathError("plan audit CORE status is missing")
    if not isinstance(plan.get("template_hash"), str) or not plan["template_hash"]:
        raise SlowpathError("plan template hash is missing")
    plan_hash = plan.get("plan_hash")
    if not isinstance(plan_hash, str) or not plan_hash:
        raise SlowpathError("plan hash is missing")
    without_hash = dict(plan)
    without_hash.pop("plan_hash", None)
    without_hash.pop("plan_path", None)
    # Plan hashes intentionally cover all semantic and action fields.  The
    # path itself is recovery metadata and can differ only by file name.
    expected_hash = _json_hash(without_hash)
    if plan_hash != expected_hash:
        raise SlowpathError("plan hash mismatch")
    return path, plan


def _rebuild_plan_semantics(root: Path, plan: Dict[str, Any]) -> None:
    """Re-derive actions from the bound audit/template/decisions files.

    A plan hash detects accidental corruption, but an Agent could otherwise
    edit an action and recompute that hash.  Rebuilding from the immutable
    semantic inputs makes such an edit fail before the executor is reached.
    """

    audit_path_value = plan.get("audit_path")
    template_path_value = plan.get("template_path")
    decisions_path_value = plan.get("decisions_path")
    if not all(isinstance(value, str) and value for value in (audit_path_value, template_path_value, decisions_path_value)):
        raise SlowpathError("plan semantic input paths are missing")
    audit_path, audit, audit_hash = _load_audit(root, audit_path_value)
    if audit_hash != plan.get("audit_sha256"):
        raise SlowpathError("plan audit hash drift")
    template_path, template = _read_json(root, template_path_value, "template")
    _validate_template(root, template_path, template, audit_path, audit_hash)
    if str(template.get("phase")) != str(plan.get("phase")):
        raise SlowpathError("plan/template phase drift")
    if template.get("template_hash") != plan.get("template_hash"):
        raise SlowpathError("plan template hash drift")
    decisions_path, _decisions_payload = _read_json(root, decisions_path_value, "decisions")
    decisions = _load_decisions(root, decisions_path, str(template["phase"]))
    expected = _plan_payload(
        root,
        audit_path,
        audit_hash,
        str(audit.get("core_gate", {}).get("status", ""))
        if isinstance(audit.get("core_gate"), dict)
        else "",
        template_path,
        template,
        decisions_path,
        decisions,
    )
    semantic_fields = (
        "phase",
        "audit_path",
        "audit_sha256",
        "audit_core_status",
        "template_path",
        "template_hash",
        "decisions_path",
        "candidate_snapshot",
        "items",
        "actions",
        "max_items",
    )
    for field in semantic_fields:
        if plan.get(field) != expected.get(field):
            raise SlowpathError(f"plan semantic field drift: {field}")


def _result_records(root: Path) -> Iterable[Tuple[Path, Dict[str, Any]]]:
    recovery = _ensure_recovery(root)
    try:
        entries = list(os.scandir(recovery))
    except OSError:
        return []
    records: List[Tuple[Path, Dict[str, Any]]] = []
    for entry in entries:
        path = Path(entry.path)
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False) or path.suffix.casefold() != ".json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(value, dict) and value.get("schema") == RESULT_SCHEMA:
            records.append((path, value))
    return records


def _has_result(root: Path, plan_hash: str, *, mode: str, dry_run: Optional[bool]) -> bool:
    candidates: List[Tuple[float, Path, Dict[str, Any]]] = []
    for path, record in _result_records(root):
        if record.get("plan_hash") != plan_hash or record.get("mode") != mode:
            continue
        if dry_run is not None and record.get("dry_run") is not dry_run:
            continue
        if record.get("status") != "PASS":
            continue
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            stamp = 0
        candidates.append((stamp, path, record))
    return bool(candidates)


def _verify_effects(plan: Dict[str, Any], root: Path) -> Dict[str, Any]:
    problems: List[str] = []
    for item in plan.get("items", []):
        checks = item.get("checks", {}) if isinstance(item, dict) else {}
        for value in checks.get("source_absent", []):
            lexical = _lexical(str(value))
            path = _canonical(lexical)
            if os.path.lexists(lexical):
                problems.append(f"source still exists: {path}")
        for value in checks.get("targets_exist", []):
            lexical = _lexical(str(value))
            path = _canonical(lexical)
            if (
                not _inside(root, path)
                or not os.path.exists(lexical)
                or os.path.islink(lexical)
            ):
                problems.append(f"target missing or unsafe: {path}")
    return {
        "status": "PASS" if not problems else "FAIL",
        "missing": problems,
        "error_summary": "; ".join(problems),
    }


def _load_preprocessor_module():
    script = Path(__file__).resolve().with_name("movie_organizing_preprocessor.py")
    spec = importlib.util.spec_from_file_location("movie_organizing_slowpath_shared_preprocessor", script)
    if spec is None or spec.loader is None:
        raise SlowpathError("cannot load shared preprocessor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_audit_module():
    script = Path(__file__).resolve().with_name("movie_organizing_audit.py")
    spec = importlib.util.spec_from_file_location("movie_organizing_slowpath_official_audit", script)
    if spec is None or spec.loader is None:
        raise SlowpathError("cannot load official movie-organizing audit")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fresh_audit_matches_plan(root: Path, plan: Dict[str, Any]) -> Dict[str, str]:
    """Re-scan the active tree and prove the planned candidates still exist.

    The original audit is evidence for planning, not a lease on the tree.
    A fresh official audit is deliberately read-only with respect to media;
    its recovery report is retained as apply evidence.  Only the selected
    candidates are compared, so a larger queue remains batchable under the
    hard twenty-item limit.
    """

    audit_module = _load_audit_module()
    try:
        report, exit_code = audit_module.audit_task_root(root)
    except Exception as error:  # pragma: no cover - defensive boundary
        raise SlowpathError(f"fresh official audit failed: {error}") from error
    if not isinstance(report, dict):
        raise SlowpathError("fresh official audit returned invalid report")
    report_path_value = report.get("report_path")
    if not isinstance(report_path_value, str) or not report_path_value:
        raise SlowpathError("fresh official audit did not persist a report")
    fresh_path, fresh_report, fresh_hash = _load_audit(root, report_path_value)
    core_gate = fresh_report.get("core_gate")
    if not isinstance(core_gate, dict):
        raise SlowpathError("fresh official audit CORE gate is missing")
    current_core_status = str(core_gate.get("status", ""))
    expected_core_status = str(plan.get("audit_core_status", ""))
    if expected_core_status and current_core_status != expected_core_status:
        raise SlowpathError(
            "fresh official audit CORE status drift: "
            f"{current_core_status} != {expected_core_status}"
        )
    phase = str(plan.get("phase", ""))
    if phase == DEDUPE_PHASE and current_core_status != "PASS":
        raise SlowpathError("dedupe_keep requires fresh audit CORE_GATE=PASS")

    fresh_items = _extract_template_items(root, fresh_report, phase)
    fresh_by_id = {str(item.get("candidate_id")): item for item in fresh_items}
    if len(fresh_by_id) != len(fresh_items):
        raise SlowpathError("fresh official audit contains duplicate candidate ids")
    snapshots = plan.get("candidate_snapshot")
    if not isinstance(snapshots, list) or len(snapshots) > MAX_ITEMS:
        raise SlowpathError("plan candidate snapshot is missing or exceeds batch limit")
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict):
            raise SlowpathError(f"plan candidate snapshot {index} is invalid")
        candidate_id = snapshot.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise SlowpathError(f"plan candidate snapshot {index} candidate_id is missing")
        current = fresh_by_id.get(candidate_id)
        if current is None:
            raise SlowpathError(f"fresh audit candidate/tree drift: {candidate_id} is missing")
        if phase == CORE_PHASE:
            expected_source = _safe_candidate_container(
                root, snapshot.get("source"), f"plan candidate snapshot {index} source"
            )
            current_source = _safe_candidate_container(
                root, current.get("source"), f"fresh candidate {candidate_id} source"
            )
            if expected_source != current_source:
                raise SlowpathError(f"fresh audit candidate/tree drift: {candidate_id} source changed")
        else:
            expected_members = sorted(
                str(_safe_active_path(root, member, f"plan candidate snapshot {index} member"))
                for member in snapshot.get("members", [])
            )
            current_members = sorted(
                str(_safe_active_path(root, member, f"fresh candidate {candidate_id} member"))
                for member in current.get("members", [])
            )
            if expected_members != current_members:
                raise SlowpathError(f"fresh audit candidate/tree drift: {candidate_id} members changed")
    return {
        "audit_path": str(fresh_path),
        "audit_sha256": fresh_hash,
        "core_status": current_core_status,
        "audit_exit_code": str(exit_code),
    }


def _write_result(root: Path, mode: str, plan: Dict[str, Any], result: Dict[str, Any], *, dry_run: Optional[bool] = None) -> Path:
    recovery = _ensure_recovery(root)
    record: Dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "version": VERSION,
        "mode": mode,
        "task_root": str(root),
        "plan_path": str(plan.get("plan_path", "")),
        "plan_hash": str(plan.get("plan_hash", "")),
        **result,
    }
    evidence: List[Dict[str, Any]] = []
    for item in plan.get("items", []):
        if not isinstance(item, dict):
            continue
        evidence_record: Dict[str, Any] = {
            "candidate_id": item.get("candidate_id"),
            "decision": item.get("decision"),
        }
        for field in (
            "same_identity",
            "same_edition_cut",
            "quality_evidence",
            "full_hash_evidence",
            "evidence",
            "reason",
        ):
            if field in item:
                evidence_record[field] = item[field]
        evidence.append(evidence_record)
    record["decision_evidence"] = evidence
    if dry_run is not None:
        record["dry_run"] = dry_run
    path = recovery / f"slow-result-{mode}-{_timestamp()}.json"
    _write_json(path, record)
    return path


def apply_plan(task_root: str | Path, plan_path: str | Path, *, dry_run: bool = False) -> Dict[str, Any]:
    root = _ensure_root(task_root)
    _plan_file, plan = _load_plan(root, plan_path)
    try:
        fresh_audit = _fresh_audit_matches_plan(root, plan)
        _rebuild_plan_semantics(root, plan)
    except SlowpathError as error:
        result: Dict[str, Any] = {
            "status": "FAIL",
            "dry_run": dry_run,
            "planned_actions": len(plan.get("actions", [])),
            "executed_actions": 0,
            "error_summary": str(error),
            "rollback_status": "NOT_RUN",
            "rolled_back_actions": 0,
            "manual_recovery_required": False,
            "action_journal": [],
        }
        result_path = _write_result(root, "apply", plan, result, dry_run=dry_run)
        result["result_path"] = str(result_path)
        return result
    if not dry_run and not _has_result(root, str(plan["plan_hash"]), mode="apply", dry_run=True):
        result: Dict[str, Any] = {
            "status": "FAIL",
            "dry_run": False,
            "planned_actions": len(plan.get("actions", [])),
            "executed_actions": 0,
            "error_summary": "successful dry-run recovery evidence is required before formal apply",
            "rollback_status": "NOT_RUN",
            "rolled_back_actions": 0,
            "manual_recovery_required": False,
            "action_journal": [],
            "fresh_audit_path": fresh_audit["audit_path"],
            "fresh_audit_sha256": fresh_audit["audit_sha256"],
        }
        result_path = _write_result(root, "apply", plan, result, dry_run=False)
        result["result_path"] = str(result_path)
        return result

    module = _load_preprocessor_module()
    callback = None if dry_run else lambda: _verify_effects(plan, root)
    result = module.execute_action_plan(
        plan,
        root,
        plan.get("actions", []),
        dry_run=dry_run,
        verify_callback=callback,
    )
    result["dry_run"] = dry_run
    result["fresh_audit_path"] = fresh_audit["audit_path"]
    result["fresh_audit_sha256"] = fresh_audit["audit_sha256"]
    result_path = _write_result(root, "apply", plan, result, dry_run=dry_run)
    result["result_path"] = str(result_path)
    return result


def verify_plan(task_root: str | Path, plan_path: str | Path) -> Dict[str, Any]:
    root = _ensure_root(task_root)
    _plan_file, plan = _load_plan(root, plan_path)
    if not _has_result(root, str(plan["plan_hash"]), mode="apply", dry_run=False):
        result: Dict[str, Any] = {
            "status": "FAIL",
            "error_summary": "successful formal apply recovery evidence is required before verify",
            "missing": [],
        }
        result_path = _write_result(root, "verify", plan, result)
        result["result_path"] = str(result_path)
        return result
    result = _verify_effects(plan, root)
    result_path = _write_result(root, "verify", plan, result)
    result["result_path"] = str(result_path)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="movie-organizing bounded semantic slow channel")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    template = subparsers.add_parser("template", help="extract a bounded decision template from a fresh audit")
    template.add_argument("--task-root", required=True)
    template.add_argument("--audit", required=True)
    template.add_argument("--phase", choices=sorted(ALLOWED_PHASES), required=True)
    template.add_argument("--limit", type=int, default=MAX_ITEMS)

    plan = subparsers.add_parser("plan", help="turn semantic decisions into a validated action plan")
    plan.add_argument("--task-root", required=True)
    plan.add_argument("--audit", required=True)
    plan.add_argument("--template", required=True)
    plan.add_argument("--decisions", required=True)

    apply = subparsers.add_parser("apply", help="dry-run or formally apply a slow plan")
    apply.add_argument("--task-root", required=True)
    apply.add_argument("--plan", required=True)
    apply.add_argument("--dry-run", action="store_true")

    verify = subparsers.add_parser("verify", help="verify a formally applied slow plan")
    verify.add_argument("--task-root", required=True)
    verify.add_argument("--plan", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.mode == "template":
            result = make_template(args.task_root, args.audit, args.phase, args.limit)
        elif args.mode == "plan":
            result = make_plan(args.task_root, args.audit, args.template, args.decisions)
        elif args.mode == "apply":
            result = apply_plan(args.task_root, args.plan, dry_run=args.dry_run)
        else:
            result = verify_plan(args.task_root, args.plan)
    except (OSError, SlowpathError, ValueError) as error:
        result = {
            "status": "FAIL",
            "version": VERSION,
            "error_summary": str(error),
            "planned_actions": 0,
            "executed_actions": 0,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
