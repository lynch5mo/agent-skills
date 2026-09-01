#!/usr/bin/env python3
"""Deterministic TMDb identity matching and same-stem NFO completion.

The Agent never writes NFO XML or chooses an ID.  It invokes this standard
library-only entrypoint, which accepts only a unique TMDb match and keeps all
other units explicitly pending.  The script intentionally does not modify
existing NFO files; an existing malformed or conflicting file is a review
item, not an invitation to overwrite user data.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


VERSION = "1.3.6"
NFO_PLAN_SCHEMA = "movie-organizing-nfo/plan/v1"
NFO_RESULT_SCHEMA = "movie-organizing-nfo/result/v1"
NFO_GATE_SCHEMA = "movie-organizing-nfo/audit/v1"
WORK_RECORD_DIR = "_work-record_"
RECOVERY_DIR = "recovery"
STAGING_DIR = "nfo-staging"
PENDING_DIR = "_待确认_"
TRASH_PREFIX = "_trash_"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
RUNTIME_TOLERANCE_MINUTES = 5
NORMAL_BATCH_LIMIT = 20
LARGE_BATCH_LIMIT = 10


class NfoApiError(RuntimeError):
    """A network, credential, API, or JSON failure that cannot be guessed."""


class NfoPlanError(ValueError):
    """A plan or filesystem contract violation."""


def _canonical(path: str | Path) -> Path:
    return Path(os.path.realpath(os.fspath(path)))


def _lexical(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _inside(root: Path, path: Path, *, allow_root: bool = True) -> bool:
    root = _canonical(root)
    path = _canonical(path)
    if allow_root and root == path:
        return True
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return path != root


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S%f")


def _json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{_timestamp()}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _ensure_recovery(root: Path) -> Path:
    root = _canonical(root)
    if not root.is_dir() or root.is_symlink():
        raise NfoPlanError("TASK_ROOT does not exist or is not a real directory")
    work = root / WORK_RECORD_DIR
    recovery = work / RECOVERY_DIR
    for directory in (work, recovery):
        if os.path.lexists(directory):
            mode = os.lstat(directory).st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode) or not _inside(root, _canonical(directory), allow_root=False):
                raise NfoPlanError(f"recovery control path is not a real in-root directory: {directory}")
        else:
            directory.mkdir()
    return recovery


def _ensure_staging_parent(root: Path, *, create: bool = True) -> Path:
    """Validate ``_work-record_/nfo-staging`` before any staging write."""

    work = root / WORK_RECORD_DIR
    staging = work / STAGING_DIR
    if os.path.lexists(staging):
        mode = os.lstat(staging).st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode) or not _inside(root, _canonical(staging), allow_root=False):
            raise NfoPlanError(f"NFO staging directory is not a real in-root directory: {staging}")
    elif create:
        if not work.is_dir() or work.is_symlink():
            raise NfoPlanError(f"work-record directory is not a real directory: {work}")
        staging.mkdir()
    return staging


def _safe_recovery_file(root: Path, value: str | Path, label: str) -> Path:
    recovery = _ensure_recovery(root)
    path = _lexical(value)
    if path.is_symlink():
        raise NfoPlanError(f"{label} must not be a symlink")
    if not _inside(root, path, allow_root=False) or not _inside(recovery, path, allow_root=False):
        raise NfoPlanError(f"{label} must be inside TASK_ROOT/_work-record_/recovery")
    try:
        mode = os.lstat(path).st_mode
    except OSError as error:
        raise NfoPlanError(f"{label} cannot be inspected: {error}") from error
    if not stat.S_ISREG(mode):
        raise NfoPlanError(f"{label} must be a regular file")
    return path


def _load_preprocessor():
    path = Path(__file__).resolve().parent / "movie_organizing_preprocessor.py"
    spec = importlib.util.spec_from_file_location("movie_organizing_nfo_preprocessor", path)
    if spec is None or spec.loader is None:
        raise NfoPlanError(f"cannot load naming preprocessor: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract_hash() -> str:
    path = Path(__file__).resolve().parents[1] / "references" / "naming-contract.md"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _normalise_title(value: str) -> str:
    """Compare titles without treating accents, punctuation, or case as identity."""

    text = unicodedata.normalize("NFKD", value).casefold()
    chars: List[str] = []
    for char in text:
        if unicodedata.combining(char):
            continue
        category = unicodedata.category(char)
        name = unicodedata.name(char, "")
        if "CJK UNIFIED IDEOGRAPH" in name or char.isalnum() or category.startswith("L"):
            chars.append(char)
    return "".join(chars)


def _normalise_person(value: str) -> str:
    return _normalise_title(value)


def _title_matches(value: str, variants: Iterable[str]) -> bool:
    wanted = _normalise_title(value)
    return bool(wanted) and any(wanted == _normalise_title(candidate) for candidate in variants if candidate)


def _parse_video(video: Path, preprocessor: Any) -> Optional[Dict[str, str]]:
    parser = getattr(preprocessor, "_parse_video_stem", None)
    if not callable(parser):
        return None
    parsed = parser(video.stem)
    if not isinstance(parsed, dict):
        return None
    if not parsed.get("title") or not parsed.get("year"):
        return None
    return {
        "title": str(parsed["title"]),
        "year": str(parsed["year"]),
        "normalized_stem": str(parsed.get("normalized_stem", video.stem)),
    }


def _director_name(movie_dir: Path, preprocessor: Any) -> str:
    parts = getattr(preprocessor, "_director_parts", None)
    if callable(parts):
        parsed = parts(movie_dir.parent.name)
        if parsed:
            return str(parsed[1])
    # A conforming director folder always has a CJK prefix and a Latin name;
    # returning an empty value makes the match pending instead of guessing.
    return ""


def _movie_cn_title(movie_dir: Path, preprocessor: Any) -> str:
    parser = getattr(preprocessor, "_parse_movie_dir", None)
    if callable(parser):
        parsed = parser(movie_dir.name)
        if parsed:
            return str(parsed[0])
    value = movie_dir.name.split(".", 1)[0]
    return value if any("CJK UNIFIED IDEOGRAPH" in unicodedata.name(char, "") for char in value) else ""


def _probe_runtime(video: Path) -> Optional[int]:
    """Return ffprobe's rounded duration, or None when ffprobe is unavailable."""

    executable = shutil.which("ffprobe")
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [executable, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(video)],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise NfoApiError(f"ffprobe failed: {error}") from error
    if completed.returncode != 0:
        raise NfoApiError("ffprobe returned a non-zero status")
    try:
        duration = float(completed.stdout.strip())
    except (TypeError, ValueError) as error:
        raise NfoApiError("ffprobe returned an invalid duration") from error
    if duration <= 0:
        raise NfoApiError("ffprobe returned a non-positive duration")
    return int(round(duration / 60.0))


def _tmdb_request(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Call one official TMDb v3 endpoint; the key is never returned or logged."""

    api_key = os.environ.get("TMDB_API_KEY", "").strip()
    if not api_key:
        raise NfoApiError("TMDB_API_KEY is not configured")
    query = dict(params or {})
    query["api_key"] = api_key
    url = f"{TMDB_BASE_URL}{path}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as error:
        raise NfoApiError(f"TMDb request failed for {path}: {type(error).__name__}") from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise NfoApiError(f"TMDb returned invalid JSON for {path}") from error
    if not isinstance(payload, dict):
        raise NfoApiError(f"TMDb returned a non-object response for {path}")
    return payload


def _candidate_directors(credits: Dict[str, Any]) -> List[str]:
    crew = credits.get("crew", []) if isinstance(credits, dict) else []
    if not isinstance(crew, list):
        return []
    result = []
    for item in crew:
        if not isinstance(item, dict) or str(item.get("job", "")).casefold() != "director":
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            result.append(name.strip())
    return result


def _candidate_year(candidate: Dict[str, Any]) -> str:
    date = candidate.get("release_date")
    return str(date)[:4] if isinstance(date, str) and len(date) >= 4 else ""


def _candidate_metadata(result: Dict[str, Any], parsed: Dict[str, str], director: str, runtime: Optional[int]) -> Optional[Dict[str, Any]]:
    """Return a fully cross-checked candidate, or None when it is excluded."""

    raw_id = result.get("id")
    try:
        tmdb_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    search_titles = [result.get("title"), result.get("original_title")]
    if not _title_matches(parsed["title"], [str(value) for value in search_titles if value]):
        alternatives = _tmdb_request(f"/movie/{tmdb_id}/alternative_titles", {"country": "US"})
        titles = alternatives.get("titles", []) if isinstance(alternatives, dict) else []
        alternative_values = [item.get("title") for item in titles if isinstance(item, dict)]
        if not _title_matches(parsed["title"], [str(value) for value in alternative_values if value]):
            return None

    details = _tmdb_request(f"/movie/{tmdb_id}", {"language": "en-US"})
    if _candidate_year(details) != parsed["year"]:
        return None
    details_titles = [details.get("title"), details.get("original_title")]
    if not _title_matches(parsed["title"], [str(value) for value in details_titles if value]):
        alternatives = _tmdb_request(f"/movie/{tmdb_id}/alternative_titles", {"country": "US"})
        titles = alternatives.get("titles", []) if isinstance(alternatives, dict) else []
        alternative_values = [item.get("title") for item in titles if isinstance(item, dict)]
        if not _title_matches(parsed["title"], [str(value) for value in alternative_values if value]):
            return None

    credits = _tmdb_request(f"/movie/{tmdb_id}/credits", {"language": "en-US"})
    directors = _candidate_directors(credits)
    if not director or not directors or not any(
        _normalise_person(director) == _normalise_person(value) for value in directors
    ):
        return None
    tmdb_runtime = details.get("runtime")
    try:
        tmdb_runtime_value = int(tmdb_runtime) if tmdb_runtime is not None else None
    except (TypeError, ValueError):
        tmdb_runtime_value = None
    if runtime is not None and tmdb_runtime_value is not None and abs(runtime - tmdb_runtime_value) > RUNTIME_TOLERANCE_MINUTES:
        return None

    external = _tmdb_request(f"/movie/{tmdb_id}/external_ids", {})
    imdb_id = external.get("imdb_id") if isinstance(external, dict) else None
    return {
        "tmdb_id": tmdb_id,
        "imdb_id": str(imdb_id) if isinstance(imdb_id, str) and imdb_id.startswith("tt") else "",
        "title": str(details.get("title") or result.get("title") or ""),
        "original_title": str(details.get("original_title") or result.get("original_title") or parsed["title"]),
        "year": parsed["year"],
        "runtime": tmdb_runtime_value,
        "directors": directors,
    }


def _match_video(video: Path, movie_dir: Path, preprocessor: Any) -> Tuple[str, Dict[str, Any]]:
    parsed = _parse_video(video, preprocessor)
    director = _director_name(movie_dir, preprocessor)
    if parsed is None or not director:
        return "PENDING_PARSE", {"reason": "video title/year or director cannot be parsed deterministically"}
    try:
        runtime = _probe_runtime(video)
        search = _tmdb_request(
            "/search/movie",
            {"query": parsed["title"], "year": parsed["year"], "language": "en-US", "include_adult": "false", "page": 1},
        )
        results = search.get("results", [])
        if not isinstance(results, list):
            raise NfoApiError("TMDb search results are not a list")
        candidates: List[Dict[str, Any]] = []
        seen_ids: set[int] = set()
        for result in results:
            if not isinstance(result, dict):
                raise NfoApiError("TMDb search result is not an object")
            raw_id = result.get("id")
            try:
                candidate_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if candidate_id in seen_ids:
                continue
            seen_ids.add(candidate_id)
            metadata = _candidate_metadata(result, parsed, director, runtime)
            if metadata is not None:
                candidates.append(metadata)
    except NfoApiError as error:
        return "PENDING_API", {"reason": str(error)}

    if len(candidates) == 1:
        return "MATCHED", {"metadata": candidates[0], "parsed": parsed, "director": director, "runtime": runtime}
    if not candidates:
        return "PENDING_NOT_FOUND", {"reason": "no unique TMDb candidate matched title/year/director/runtime"}
    return "PENDING_AMBIGUOUS", {
        "reason": "more than one TMDb candidate matched title/year/director/runtime",
        "candidate_tmdb_ids": [item["tmdb_id"] for item in candidates],
    }


def _nfo_id(root: ET.Element) -> Optional[int]:
    for node in root.findall("uniqueid"):
        kind = str(node.get("type", "")).casefold()
        if kind != "tmdb":
            continue
        try:
            return int((node.text or "").strip())
        except (TypeError, ValueError):
            return None
    return None


def _nfo_imdb_id(root: ET.Element) -> str:
    for node in root.findall("uniqueid"):
        if str(node.get("type", "")).casefold() != "imdb":
            continue
        value = (node.text or "").strip()
        if value.startswith("tt"):
            return value
    return ""


def _parse_nfo(path: Path) -> Tuple[Optional[ET.Element], str]:
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as error:
        return None, f"NFO XML is malformed or unreadable: {type(error).__name__}"
    root = tree.getroot()
    if root.tag.casefold() != "movie":
        return None, "NFO root element is not <movie>"
    return root, ""


def _verify_locked_identity(
    tmdb_id: int,
    imdb_id: str,
    parsed: Dict[str, str],
    director: str,
) -> Tuple[str, Dict[str, Any]]:
    """Re-check an existing NFO ID against TMDb before accepting it."""

    if not director:
        return "PENDING_EXISTING_NFO", {"reason": "director folder cannot be parsed for existing NFO verification", "tmdb_id": tmdb_id}
    try:
        details = _tmdb_request(f"/movie/{tmdb_id}", {"language": "en-US"})
        if _candidate_year(details) != parsed["year"]:
            return "PENDING_EXISTING_NFO", {"reason": "existing NFO TMDb ID year conflicts with video", "tmdb_id": tmdb_id}
        titles = [details.get("title"), details.get("original_title")]
        if not _title_matches(parsed["title"], [str(value) for value in titles if value]):
            alternatives = _tmdb_request(f"/movie/{tmdb_id}/alternative_titles", {"country": "US"})
            raw_titles = alternatives.get("titles", []) if isinstance(alternatives, dict) else []
            values = [item.get("title") for item in raw_titles if isinstance(item, dict)]
            if not _title_matches(parsed["title"], [str(value) for value in values if value]):
                return "PENDING_EXISTING_NFO", {"reason": "existing NFO TMDb ID title conflicts with video", "tmdb_id": tmdb_id}
        credits = _tmdb_request(f"/movie/{tmdb_id}/credits", {"language": "en-US"})
        directors = _candidate_directors(credits)
        if not directors or not any(_normalise_person(director) == _normalise_person(value) for value in directors):
            return "PENDING_EXISTING_NFO", {"reason": "existing NFO TMDb ID director conflicts with director folder", "tmdb_id": tmdb_id}
        if imdb_id:
            external = _tmdb_request(f"/movie/{tmdb_id}/external_ids", {})
            resolved = external.get("imdb_id") if isinstance(external, dict) else None
            if isinstance(resolved, str) and resolved and resolved != imdb_id:
                return "PENDING_EXISTING_NFO", {"reason": "existing NFO IMDb ID conflicts with TMDb", "tmdb_id": tmdb_id}
    except NfoApiError as error:
        return "PENDING_API", {"reason": str(error), "tmdb_id": tmdb_id}
    return "KEEP_EXISTING", {"tmdb_id": tmdb_id, "imdb_id": imdb_id, "identity_verified": True}


def _existing_nfo_status(path: Path, parsed: Dict[str, str], movie_dir: Path, preprocessor: Any) -> Tuple[str, Dict[str, Any]]:
    root, error = _parse_nfo(path)
    if root is None:
        return "PENDING_EXISTING_NFO", {"reason": error}
    tmdb_id = _nfo_id(root)
    if tmdb_id is None:
        return "PENDING_EXISTING_NFO", {"reason": "existing NFO has no valid TMDb uniqueid"}
    nfo_year = (root.findtext("year") or "").strip()
    if nfo_year and nfo_year != parsed["year"]:
        return "PENDING_EXISTING_NFO", {"reason": "existing NFO year conflicts with video year", "tmdb_id": tmdb_id}
    original = (root.findtext("originaltitle") or "").strip()
    if original and not _title_matches(parsed["title"], [original]):
        return "PENDING_EXISTING_NFO", {"reason": "existing NFO originaltitle conflicts with video title", "tmdb_id": tmdb_id}
    director = _director_name(movie_dir, preprocessor)
    return _verify_locked_identity(tmdb_id, _nfo_imdb_id(root), parsed, director)


def _build_nfo_xml(movie_title: str, metadata: Dict[str, Any]) -> bytes:
    root = ET.Element("movie")
    ET.SubElement(root, "title").text = movie_title
    ET.SubElement(root, "originaltitle").text = str(metadata.get("original_title") or "")
    ET.SubElement(root, "year").text = str(metadata.get("year") or "")
    for director in metadata.get("directors", []):
        if director:
            ET.SubElement(root, "director").text = str(director)
    runtime = metadata.get("runtime")
    if runtime:
        ET.SubElement(root, "runtime").text = str(runtime)
    ET.SubElement(root, "uniqueid", {"type": "tmdb", "default": "true"}).text = str(metadata["tmdb_id"])
    if metadata.get("imdb_id"):
        ET.SubElement(root, "uniqueid", {"type": "imdb"}).text = str(metadata["imdb_id"])
    try:
        ET.indent(root, space="  ")
    except AttributeError:  # pragma: no cover - Python 3.8 compatibility
        pass
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def _file_fingerprint(path: Path) -> Dict[str, Any]:
    try:
        stat_result = os.lstat(path)
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    except OSError as error:
        raise NfoPlanError(f"cannot inspect fingerprint path {path}: {error}") from error
    if stat.S_ISLNK(stat_result.st_mode):
        raise NfoPlanError(f"fingerprint path must not be a symlink: {path}")
    return {"path": str(path), "exists": True, "size": stat_result.st_size, "mtime_ns": stat_result.st_mtime_ns}


def _fingerprint(entries: Iterable[Dict[str, Any]]) -> str:
    values = []
    for entry in entries:
        values.append(_file_fingerprint(Path(str(entry["source_video"]))))
        values.append(_file_fingerprint(Path(str(entry["target_path"]))))
    return _json_hash(values)


def _tree_fingerprint(path: Path) -> str:
    """Fingerprint a movie directory without reading media bytes.

    Pending isolation is a rename, not a copy.  The relative entry list plus
    lstat metadata is enough to prove that the same complete tree arrived at
    the pending target while keeping large video files out of the context and
    avoiding an expensive full-content hash.
    """

    try:
        root_mode = os.lstat(path).st_mode
    except OSError as error:
        raise NfoPlanError(f"cannot inspect pending source: {path}: {error}") from error
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise NfoPlanError(f"pending source must be a real directory: {path}")
    values: List[Dict[str, Any]] = []
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            children = sorted(os.scandir(current), key=lambda entry: entry.name)
        except OSError as error:
            raise NfoPlanError(f"cannot scan pending source: {current}: {error}") from error
        for child in children:
            child_path = Path(child.path)
            try:
                mode = os.lstat(child_path).st_mode
            except OSError as error:
                raise NfoPlanError(f"cannot inspect pending source entry: {child_path}: {error}") from error
            if stat.S_ISLNK(mode):
                raise NfoPlanError(f"pending source contains a symlink: {child_path}")
            relative = child_path.relative_to(path).as_posix()
            values.append(
                {
                    "relative": relative,
                    "kind": "dir" if stat.S_ISDIR(mode) else "file" if stat.S_ISREG(mode) else "other",
                    "size": int(getattr(os.stat(child_path, follow_symlinks=False), "st_size", 0)),
                    "mtime_ns": int(getattr(os.stat(child_path, follow_symlinks=False), "st_mtime_ns", 0)),
                }
            )
            if stat.S_ISDIR(mode):
                stack.append(child_path)
            elif not stat.S_ISREG(mode):
                raise NfoPlanError(f"pending source contains unsupported entry: {child_path}")
    return _json_hash(values)


def _pending_root(root: Path) -> Path:
    """Validate the task-scoped pending root without creating it."""

    pending = root / PENDING_DIR
    if os.path.lexists(pending):
        mode = os.lstat(pending).st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode) or not _inside(root, _canonical(pending), allow_root=False):
            raise NfoPlanError(f"pending directory is not a real in-root directory: {pending}")
    return pending


def _pending_target(root: Path, source: Path, entry_index: int) -> Path:
    """Derive a collision-resistant target while preserving director context."""

    root = _canonical(root)
    source = _lexical(source)
    if source == root or not _inside(root, _canonical(source), allow_root=False):
        raise NfoPlanError(f"pending source is outside TASK_ROOT: {source}")
    if any(part in {WORK_RECORD_DIR, PENDING_DIR} or part.startswith(TRASH_PREFIX) for part in source.relative_to(root).parts):
        raise NfoPlanError(f"pending source is not in the active media tree: {source}")
    try:
        source_mode = os.lstat(source).st_mode
    except OSError as error:
        raise NfoPlanError(f"pending source cannot be inspected: {source}: {error}") from error
    if stat.S_ISLNK(source_mode) or not stat.S_ISDIR(source_mode):
        raise NfoPlanError(f"pending source must be a real movie directory: {source}")
    parent_relative = source.parent.relative_to(root)
    # Keep the original director (and any explicitly scoped subpath) under
    # TASK_ROOT/_待确认_; only the movie unit itself is moved.
    target = root / PENDING_DIR / parent_relative / source.name
    if target == source or not _inside(root, _canonical(target), allow_root=False):
        raise NfoPlanError(f"pending target is outside TASK_ROOT: {target}")
    return target


def _pending_action_static_error(action: Dict[str, Any], root: Path) -> Optional[str]:
    """Validate immutable action shape without requiring pre-apply paths."""

    source = _lexical(str(action.get("source", "")))
    target = _lexical(str(action.get("target", "")))
    if action.get("action") != "pending_isolation":
        return "pending action has unsupported action type"
    if source == target:
        return "pending source and target must differ"
    if not _inside(root, _canonical(source), allow_root=False):
        return "pending source is outside TASK_ROOT"
    if not _inside(root, _canonical(target), allow_root=False):
        return "pending target is outside TASK_ROOT"
    try:
        source_relative = source.relative_to(root)
        relative = target.relative_to(root)
    except ValueError:
        return "pending target is outside TASK_ROOT"
    if any(part == WORK_RECORD_DIR or part == PENDING_DIR or part.startswith(TRASH_PREFIX) for part in source_relative.parts):
        return "pending source is not in the active media tree"
    if not relative.parts or relative.parts[0] != PENDING_DIR:
        return "pending target must be under TASK_ROOT/_待确认_"
    if any(part == WORK_RECORD_DIR or part == PENDING_DIR or part.startswith(TRASH_PREFIX) for part in relative.parts[1:]):
        return "pending target contains a reserved path component"
    return None


def _pending_action_error(action: Dict[str, Any], root: Path) -> Optional[str]:
    source = _lexical(str(action.get("source", "")))
    target = _lexical(str(action.get("target", "")))
    static_error = _pending_action_static_error(action, root)
    if static_error:
        return static_error
    try:
        source_mode = os.lstat(source).st_mode
    except FileNotFoundError:
        return f"pending source is missing: {source}"
    except OSError as error:
        return f"pending source cannot be inspected: {error}"
    if stat.S_ISLNK(source_mode) or not stat.S_ISDIR(source_mode):
        return f"pending source is not a real directory: {source}"
    if os.path.lexists(target):
        return f"pending target already exists: {target}"
    try:
        if _tree_fingerprint(source) != action.get("source_tree_hash"):
            return f"pending source tree drifted: {source}"
    except NfoPlanError as error:
        return str(error)
    # Every existing ancestor must be a real directory.  Missing ancestors are
    # created by the transaction one at a time, never through a symlinked
    # parent.
    current = target.parent
    missing: List[Path] = []
    while current != root:
        if os.path.lexists(current):
            try:
                mode = os.lstat(current).st_mode
            except OSError as error:
                return f"pending target parent cannot be inspected: {error}"
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                return f"pending target parent is not a real directory: {current}"
            break
        missing.append(current)
        current = current.parent
    if current != root and not _inside(root, _canonical(current), allow_root=False):
        return "pending target parent escapes TASK_ROOT"
    return None


def _entry_base(bundle: Dict[str, Any], root: Path, selected: bool) -> Dict[str, Any]:
    video = Path(str(bundle.get("expected_video_target", "")))
    movie_dir = Path(str(bundle.get("expected_movie_dir_path", "")))
    parsed = _parse_video(video, _load_preprocessor()) if video else None
    target = video.with_suffix(".nfo")
    return {
        "source_video": str(video),
        "target_path": str(target),
        "movie_dir": str(movie_dir),
        "director_dir": str(movie_dir.parent),
        "parsed_title": parsed["title"] if parsed else "",
        "parsed_year": parsed["year"] if parsed else "",
        "expected_stem": video.stem,
        "selected": selected,
        "status": "PENDING_PARSE" if parsed is None else "PENDING_NOT_FOUND",
        "reason": "",
    }


def make_plan(task_root: str | Path, *, persist: bool = True) -> Dict[str, Any]:
    root = _canonical(task_root)
    preprocessor = _load_preprocessor()
    contract_hash = _contract_hash()
    expected_contract = str(getattr(preprocessor, "EXPECTED_NAMING_CONTRACT_SHA256", ""))
    if contract_hash == "" or contract_hash != expected_contract:
        raise NfoPlanError("naming-contract hash mismatch or missing")
    _pending_root(root)
    # Validate both recovery and staging control directories before creating
    # any staging file.  A symlink here must fail closed, never redirecting a
    # write outside TASK_ROOT.
    if persist:
        _ensure_recovery(root)
        _ensure_staging_parent(root, create=True)
    naming_plan = preprocessor.make_plan(root, persist=False)
    bundles = [item for item in naming_plan.get("bundles", []) if item.get("status") == "NAMING_PASS"]
    large = bool(naming_plan.get("large_library_mode") or naming_plan.get("summary", {}).get("large_library_mode"))
    sorted_bundles = sorted(bundles, key=lambda item: str(item.get("expected_video_target", "")))
    # A large-library plan carries the complete inventory, but each new plan
    # must advance to the next batch.  A previously verified identity lock is
    # durable evidence, so it is not selected again unless its live video/NFO
    # fingerprint has drifted.  This keeps the next plan deterministic after a
    # context restart and prevents repeatedly re-planning the first ten files.
    unlocked: List[Dict[str, Any]] = []
    locked_keys: set[str] = set()
    for bundle in sorted_bundles:
        video = Path(str(bundle.get("expected_video_target", "")))
        target = video.with_suffix(".nfo")
        locked = False
        if target.is_file() and not target.is_symlink():
            parsed_nfo, _error = _parse_nfo(target)
            tmdb_id = _nfo_id(parsed_nfo) if parsed_nfo is not None else None
            if isinstance(tmdb_id, int):
                locked = _lock_matches(root, video, target, tmdb_id)
        if not locked:
            unlocked.append(bundle)
        else:
            locked_keys.add(str(bundle.get("expected_video_target", "")))

    selected_keys: set[str]
    if large:
        directors = sorted({str(item.get("expected_director_dir", "")) for item in unlocked})
        first_director = directors[0] if directors else ""
        selected_keys = {
            str(item.get("expected_video_target", ""))
            for item in unlocked
            if str(item.get("expected_director_dir", "")) == first_director
        }
        selected_keys = set(sorted(selected_keys)[:LARGE_BATCH_LIMIT])
    else:
        selected_keys = {
            str(item.get("expected_video_target", ""))
            for item in unlocked[:NORMAL_BATCH_LIMIT]
        }

    entries: List[Dict[str, Any]] = []
    staging_root: Optional[Path] = None
    for bundle in sorted_bundles:
        video = Path(str(bundle.get("expected_video_target", "")))
        movie_dir = Path(str(bundle.get("expected_movie_dir_path", "")))
        parsed = _parse_video(video, preprocessor)
        if parsed is None:
            entry = _entry_base(bundle, root, str(video) in selected_keys)
            entries.append(entry)
            continue
        target = video.with_suffix(".nfo")
        entry = {
            "source_video": str(video),
            "target_path": str(target),
            "movie_dir": str(movie_dir),
            "director_dir": str(movie_dir.parent),
            "parsed_title": parsed["title"],
            "parsed_year": parsed["year"],
            "expected_stem": video.stem,
            "selected": str(video) in selected_keys,
            "status": (
                "PENDING_NOT_FOUND"
                if str(video) in selected_keys
                else "KEEP_EXISTING"
                if str(video) in locked_keys
                else "DEFERRED_BATCH"
            ),
            "reason": "",
        }
        if not entry["selected"]:
            entries.append(entry)
            continue
        if os.path.lexists(target):
            if target.is_symlink():
                entry.update({"status": "PENDING_EXISTING_NFO", "reason": "same-stem NFO is a symlink"})
                entries.append(entry)
                continue
            status, details = _existing_nfo_status(target, parsed, movie_dir, preprocessor)
            entry.update(details)
            entry["status"] = status
            entries.append(entry)
            continue
        # Any other NFO in the final movie directory is not safely attributable.
        try:
            unrelated = [item for item in movie_dir.iterdir() if item.is_file() and item.suffix.casefold() == ".nfo"]
        except OSError as error:
            entry.update({"status": "PENDING_API", "reason": f"cannot inspect movie directory: {error}"})
            entries.append(entry)
            continue
        if unrelated:
            entry.update({"status": "PENDING_EXISTING_NFO", "reason": "unrelated NFO exists in movie directory"})
            entries.append(entry)
            continue
        status, details = _match_video(video, movie_dir, preprocessor)
        entry.update(details)
        entry["status"] = status
        if status == "MATCHED":
            metadata = details["metadata"]
            if staging_root is None and persist:
                staging_root = root / WORK_RECORD_DIR / STAGING_DIR / _timestamp()
                staging_root.mkdir(parents=True, exist_ok=True)
            xml_bytes = _build_nfo_xml(_movie_cn_title(movie_dir, preprocessor), metadata)
            stable = hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:20]
            staging_path = staging_root / f"{stable}.nfo" if staging_root is not None else Path("")
            if staging_root is not None:
                staging_path.write_bytes(xml_bytes)
            entry["tmdb_id"] = metadata["tmdb_id"]
            entry["imdb_id"] = metadata.get("imdb_id", "")
            entry["staging_path"] = str(staging_path) if staging_root is not None else ""
            entry["staging_sha256"] = _sha256_bytes(xml_bytes) if staging_root is not None else ""
            entry["status"] = "AUTO_CREATE"
            entry.pop("metadata", None)
            entry.pop("parsed", None)
            entry.pop("runtime", None)
        entries.append(entry)

    pending_actions: List[Dict[str, Any]] = []
    pending_targets: set[str] = set()
    pending_isolation_blocked = 0
    for index, entry in enumerate(entries):
        if not entry.get("selected") or not str(entry.get("status", "")).startswith("PENDING"):
            continue
        source = Path(str(entry.get("source_video", ""))).parent
        try:
            target = _pending_target(root, source, index)
            target_key = _json_hash(str(target))
            if target_key in pending_targets:
                raise NfoPlanError(f"pending target collides with another unresolved movie: {target}")
            pending_targets.add(target_key)
            if os.path.lexists(target):
                raise NfoPlanError(f"pending target already exists: {target}")
            source_tree_hash = _tree_fingerprint(source)
            action_id = "pending-" + hashlib.sha256(f"{source}\n{target}".encode("utf-8")).hexdigest()[:16]
            pending_actions.append(
                {
                    "id": action_id,
                    "action": "pending_isolation",
                    "source": str(source),
                    "target": str(target),
                    "source_tree_hash": source_tree_hash,
                    "evidence": str(entry.get("reason", "NFO identity is not uniquely verified")),
                    "rollback": "rename target back to source",
                    "preconditions": ["source movie directory exists", "target absent", "source and target under TASK_ROOT"],
                    "postconditions": ["source absent", "complete movie directory exists under TASK_ROOT/_待确认_"],
                    "entry_index": index,
                }
            )
            entry["pending_isolation"] = {"source": str(source), "target": str(target), "action_id": action_id}
        except (NfoPlanError, OSError) as error:
            pending_isolation_blocked += 1
            entry["pending_isolation_status"] = "BLOCKED"
            entry["pending_isolation_reason"] = str(error)

    counts = {
        "total_units": len(entries),
        "selected_units": sum(bool(entry.get("selected")) for entry in entries),
        "auto_create": sum(entry.get("status") == "AUTO_CREATE" for entry in entries),
        "keep_existing": sum(entry.get("status") == "KEEP_EXISTING" for entry in entries),
        "pending": sum(str(entry.get("status", "")).startswith("PENDING") for entry in entries),
        "deferred": sum(entry.get("status") == "DEFERRED_BATCH" for entry in entries),
        "pending_isolation": len(pending_actions),
        "pending_isolation_blocked": pending_isolation_blocked,
    }
    payload: Dict[str, Any] = {
        "schema": NFO_PLAN_SCHEMA,
        "version": VERSION,
        "task_root": str(root),
        "standard_id": "movie-organizing",
        "naming_contract_sha256": contract_hash,
        "large_library_mode": large,
        "batch_limit": LARGE_BATCH_LIMIT if large else NORMAL_BATCH_LIMIT,
        "batch_director": next((entry.get("director_dir", "") for entry in entries if entry.get("selected")), ""),
        "source_fingerprint": _fingerprint(entries),
        "counts": counts,
        "pending_actions": pending_actions,
        "entries": entries,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    payload["plan_hash"] = _json_hash({key: value for key, value in payload.items() if key not in {"plan_hash", "plan_path", "generated_at"}})
    if persist:
        recovery = _ensure_recovery(root)
        plan_path = recovery / f"nfo-plan-{_timestamp()}.json"
        payload["plan_path"] = str(plan_path)
        _write_json(plan_path, payload)
        _write_checkpoints(root, payload)
    else:
        payload["plan_path"] = ""
    return payload


def _write_checkpoints(root: Path, plan: Dict[str, Any]) -> None:
    work = root / WORK_RECORD_DIR
    work.mkdir(parents=True, exist_ok=True)
    inventory = work / "inventory.jsonl"
    lines = []
    for entry in plan.get("entries", []):
        lines.append(json.dumps({
            "video": entry.get("source_video", ""),
            "movie_dir": entry.get("movie_dir", ""),
            "director_dir": entry.get("director_dir", ""),
            "nfo_status": entry.get("status", ""),
        }, ensure_ascii=False, sort_keys=True))
    temporary = inventory.with_name(f".{inventory.name}.tmp-{os.getpid()}-{_timestamp()}")
    temporary.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    temporary.replace(inventory)
    progress = {
        "schema": "movie-organizing-progress/v1",
        "version": VERSION,
        "task_root": str(root),
        "large_library_mode": bool(plan.get("large_library_mode")),
        "current_batch": {
            "plan_hash": plan.get("plan_hash", ""),
            "director": plan.get("batch_director", ""),
            "selected_units": plan.get("counts", {}).get("selected_units", 0),
        },
        "sealed": False,
        "next_allowed": "nfo_gate",
    }
    _write_json(work / "progress.json", progress)


def _plan_integrity_error(plan: Dict[str, Any], supplied: Optional[Path], root: Path) -> Optional[str]:
    if plan.get("schema") != NFO_PLAN_SCHEMA:
        return "NFO plan schema mismatch"
    if plan.get("version") != VERSION:
        return "NFO plan version mismatch"
    if _canonical(str(plan.get("task_root", ""))) != root:
        return "NFO plan task_root mismatch"
    if plan.get("standard_id") != "movie-organizing":
        return "NFO plan standard_id mismatch"
    if plan.get("naming_contract_sha256") != _contract_hash():
        return "NFO plan naming-contract hash mismatch"
    if supplied is not None:
        if plan.get("plan_path") is None or _canonical(str(plan.get("plan_path", ""))) != _canonical(supplied):
            return "NFO plan_path does not match supplied plan"
    entries = plan.get("entries")
    if not isinstance(entries, list):
        return "NFO plan entries are missing or invalid"
    pending_actions = plan.get("pending_actions", [])
    if not isinstance(pending_actions, list):
        return "NFO plan pending_actions are missing or invalid"
    action_ids: set[str] = set()
    action_entry_indexes: set[int] = set()
    for index, action in enumerate(pending_actions):
        if not isinstance(action, dict):
            return f"NFO pending action {index} is not an object"
        action_id = action.get("id")
        if not isinstance(action_id, str) or not action_id or action_id in action_ids:
            return f"NFO pending action {index} id is missing or duplicated"
        action_ids.add(action_id)
        entry_index = action.get("entry_index")
        if not isinstance(entry_index, int) or entry_index < 0 or entry_index >= len(entries):
            return f"NFO pending action {index} entry_index is invalid"
        action_entry_indexes.add(entry_index)
        if not isinstance(action.get("source_tree_hash"), str) or not action.get("source_tree_hash"):
            return f"NFO pending action {index} source_tree_hash is missing"
        pending_error = _pending_action_static_error(action, root)
        if pending_error:
            return f"NFO pending action {index}: {pending_error}"
        entry = entries[entry_index]
        if not str(entry.get("status", "")).startswith("PENDING") or entry.get("selected") is not True:
            return f"NFO pending action {index} is not bound to a selected PENDING entry"
        source_from_entry = _lexical(str(entry.get("source_video", ""))).parent
        if _canonical(str(action.get("source", ""))) != _canonical(source_from_entry):
            return f"NFO pending action {index} source is not bound to its selected video"
        try:
            expected_target = root / PENDING_DIR / source_from_entry.parent.relative_to(root) / source_from_entry.name
        except ValueError:
            return f"NFO pending action {index} source cannot derive an in-root target"
        if _canonical(str(action.get("target", ""))) != _canonical(expected_target):
            return f"NFO pending action {index} target is not the deterministic task-scoped location"
        bound = entry.get("pending_isolation")
        if not isinstance(bound, dict) or bound.get("action_id") != action_id:
            return f"NFO pending action {index} binding is missing or mismatched"
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return f"NFO entry {index} is not an object"
        for key in ("source_video", "target_path", "status"):
            if not isinstance(entry.get(key), str) or not entry.get(key):
                return f"NFO entry {index} {key} is missing"
        for key in ("source_video", "target_path"):
            if not _inside(root, _canonical(str(entry[key])), allow_root=False):
                return f"NFO entry {index} {key} is outside TASK_ROOT"
        if entry.get("status") == "AUTO_CREATE":
            staging = entry.get("staging_path")
            if not isinstance(staging, str) or not staging:
                return f"NFO entry {index} staging_path is missing"
            if not _inside(root / WORK_RECORD_DIR / STAGING_DIR, _canonical(staging), allow_root=False):
                return f"NFO entry {index} staging_path is outside nfo-staging"
            if not isinstance(entry.get("tmdb_id"), int):
                return f"NFO entry {index} tmdb_id is missing"
        if str(entry.get("status", "")).startswith("PENDING") and entry.get("selected") is True:
            if entry.get("pending_isolation_status") == "BLOCKED":
                continue
            bound = entry.get("pending_isolation")
            if not isinstance(bound, dict) or bound.get("action_id") not in action_ids:
                return f"NFO entry {index} selected PENDING isolation binding is missing"
    expected_hash = _json_hash({key: value for key, value in plan.items() if key not in {"plan_hash", "plan_path", "generated_at"}})
    if plan.get("plan_hash") != expected_hash:
        return "NFO plan hash mismatch"
    return None


def _freshness_error(plan: Dict[str, Any]) -> Optional[str]:
    try:
        current = _fingerprint(plan.get("entries", []))
    except NfoPlanError as error:
        return str(error)
    if current != plan.get("source_fingerprint"):
        return "NFO plan source fingerprint drifted; create a fresh plan"
    return None


def _validate_staging(entry: Dict[str, Any], root: Path) -> Tuple[Optional[ET.Element], str]:
    path = _lexical(str(entry.get("staging_path", "")))
    if not _inside(root / WORK_RECORD_DIR / STAGING_DIR, _canonical(path), allow_root=False):
        return None, "staging path escapes nfo-staging"
    try:
        mode = os.lstat(path).st_mode
    except OSError as error:
        return None, f"staging NFO cannot be inspected: {error}"
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        return None, "staging NFO must be a regular non-symlink file"
    try:
        data = path.read_bytes()
    except OSError as error:
        return None, f"staging NFO cannot be read: {error}"
    if _sha256_bytes(data) != entry.get("staging_sha256"):
        return None, "staging NFO hash mismatch"
    root_element, error = _parse_nfo(path)
    if root_element is None:
        return None, error
    if _nfo_id(root_element) != entry.get("tmdb_id"):
        return None, "staging NFO TMDb ID mismatch"
    target = Path(str(entry["target_path"]))
    if path.name != hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:20] + ".nfo":
        return None, "staging NFO stable name mismatch"
    return root_element, ""


def _rollback_archive(root: Path, plan: Dict[str, Any]) -> Path:
    """Create an in-root recovery archive for newly-created NFO artifacts."""

    recovery = _ensure_recovery(root)
    archive = recovery / f"nfo-rollback-{str(plan.get('plan_hash', 'unknown'))[:20]}-{_timestamp()}"
    archive.mkdir()
    if archive.is_symlink() or not _inside(root, _canonical(archive), allow_root=False):
        raise NfoPlanError(f"NFO rollback archive is not a real in-root directory: {archive}")
    return archive


def apply_plan(plan: Dict[str, Any], root: str | Path, *, dry_run: bool = False) -> Dict[str, Any]:
    root_path = _canonical(root)
    integrity = _plan_integrity_error(plan, None, root_path)
    if integrity:
        return {"status": "FAIL", "executed_actions": 0, "error_summary": integrity, "rollback_status": "NOT_RUN", "manual_recovery_required": False}
    freshness = _freshness_error(plan)
    if freshness:
        return {"status": "FAIL", "executed_actions": 0, "error_summary": freshness, "rollback_status": "NOT_RUN", "manual_recovery_required": False}
    actions = [entry for entry in plan.get("entries", []) if entry.get("status") == "AUTO_CREATE" and entry.get("selected") is True]
    pending_actions = [action for action in plan.get("pending_actions", []) if isinstance(action, dict)]
    for entry in actions:
        _element, error = _validate_staging(entry, root_path)
        if error:
            return {"status": "FAIL", "executed_actions": 0, "error_summary": error, "rollback_status": "NOT_RUN", "manual_recovery_required": False}
        target = _lexical(str(entry["target_path"]))
        if target.exists() or target.is_symlink():
            return {"status": "FAIL", "executed_actions": 0, "error_summary": f"NFO target already exists: {target}", "rollback_status": "NOT_RUN", "manual_recovery_required": False}
        if not target.parent.is_dir():
            return {"status": "FAIL", "executed_actions": 0, "error_summary": f"NFO target parent is missing: {target.parent}", "rollback_status": "NOT_RUN", "manual_recovery_required": False}
    for action in pending_actions:
        error = _pending_action_error(action, root_path)
        if error:
            return {
                "status": "FAIL",
                "executed_actions": 0,
                "pending_isolation_count": 0,
                "error_summary": error,
                "rollback_status": "NOT_RUN",
                "manual_recovery_required": False,
            }
    if dry_run:
        return {
            "status": "PASS",
            "dry_run": True,
            "planned_actions": len(actions) + len(pending_actions),
            "executed_actions": 0,
            "created_count": 0,
            "pending_isolation_count": 0,
            "pending_isolation_planned": len(pending_actions),
            "pending_count": plan.get("counts", {}).get("pending", 0),
            "deferred_count": plan.get("counts", {}).get("deferred", 0),
            "rollback_status": "NOT_RUN",
            "manual_recovery_required": False,
            "error_summary": "",
        }

    created: List[Tuple[Path, str]] = []
    isolated: List[Tuple[Dict[str, Any], List[Path]]] = []
    created_pending_dirs: List[Path] = []

    def create_pending_parents(target: Path) -> List[Path]:
        """Create missing pending ancestors one by one and return them."""

        missing: List[Path] = []
        current = target.parent
        while current != root_path and not os.path.lexists(current):
            missing.append(current)
            current = current.parent
        if current != root_path:
            mode = os.lstat(current).st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise NfoPlanError(f"pending target parent is not a real directory: {current}")
        created_parents: List[Path] = []
        for directory in reversed(missing):
            directory.mkdir()
            created_parents.append(directory)
        return created_parents

    def rollback_isolated(archive: Path) -> List[str]:
        errors: List[str] = []
        for action, created_parents in reversed(isolated):
            source = _lexical(str(action["source"]))
            target = _lexical(str(action["target"]))
            try:
                if target.is_symlink() or not target.is_dir() or source.exists() or source.is_symlink():
                    raise OSError(f"pending rollback path changed: {target} -> {source}")
                target.rename(source)
                for index, directory in enumerate(reversed(created_parents), start=1):
                    if not os.path.lexists(directory):
                        continue
                    if directory.is_symlink() or not directory.is_dir():
                        raise OSError(f"pending rollback parent changed: {directory}")
                    relative = directory.relative_to(root_path)
                    archive_target = archive / "pending-parents" / f"{index:04d}" / relative
                    archive_target.parent.mkdir(parents=True, exist_ok=True)
                    if os.path.lexists(archive_target):
                        raise OSError(f"pending rollback archive target exists: {archive_target}")
                    directory.rename(archive_target)
            except OSError as error:
                errors.append(f"{target}: {error}")
        return errors

    try:
        for entry in actions:
            target = _lexical(str(entry["target_path"]))
            staging = _lexical(str(entry["staging_path"]))
            if target.exists() or target.is_symlink():
                raise NfoPlanError(f"NFO target appeared during apply: {target}")
            temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}-{_timestamp()}")
            data = staging.read_bytes()
            temporary.write_bytes(data)
            temporary.replace(target)
            created.append((target, _sha256_bytes(data)))
        for action in pending_actions:
            source = _lexical(str(action["source"]))
            target = _lexical(str(action["target"]))
            created_parents = create_pending_parents(target)
            created_pending_dirs.extend(created_parents)
            if os.path.lexists(target):
                raise NfoPlanError(f"pending target appeared during apply: {target}")
            source.rename(target)
            isolated.append((action, created_parents))
    except (OSError, NfoPlanError) as error:
        rollback_errors: List[str] = []
        try:
            rollback_archive = _rollback_archive(root_path, plan)
        except (OSError, NfoPlanError) as archive_error:
            rollback_archive = None
            rollback_errors.append(f"rollback archive setup failed: {archive_error}")
        if rollback_archive is not None:
            rollback_errors.extend(rollback_isolated(rollback_archive))
        for index, (target, digest) in enumerate(reversed(created), start=1):
            try:
                if target.is_file() and _sha256_bytes(target.read_bytes()) == digest:
                    archive_target = rollback_archive / "nfo" / f"{index:04d}-{target.name}" if rollback_archive is not None else None
                    if archive_target is None:
                        raise OSError("rollback archive unavailable")
                    archive_target.parent.mkdir(parents=True, exist_ok=True)
                    if os.path.lexists(archive_target):
                        raise OSError(f"NFO rollback archive target exists: {archive_target}")
                    target.rename(archive_target)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        # A parent directory created for an isolation target is itself a
        # reversible artifact.  Keep it under the same archive; moving it
        # preserves any unexpected content.
        if rollback_archive is not None:
            for index, directory in enumerate(reversed(created_pending_dirs), start=1):
                if not os.path.lexists(directory):
                    continue
                try:
                    if directory.is_symlink() or not directory.is_dir():
                        raise OSError(f"pending rollback parent changed: {directory}")
                    relative = directory.relative_to(root_path)
                    archive_target = rollback_archive / "pending-parents-unclaimed" / f"{index:04d}" / relative
                    archive_target.parent.mkdir(parents=True, exist_ok=True)
                    if os.path.lexists(archive_target):
                        raise OSError(f"pending rollback archive target exists: {archive_target}")
                    directory.rename(archive_target)
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
        return {
            "status": "FAIL",
            "executed_actions": len(created) + len(isolated),
            "created_count": len(created),
            "pending_isolation_count": len(isolated),
            "error_summary": f"NFO apply failed: {error}",
            "rollback_status": "FAIL" if rollback_errors else "PASS",
            "manual_recovery_required": bool(rollback_errors),
            "rollback_errors": rollback_errors,
        }
    return {
        "status": "PASS",
        "executed_actions": len(created) + len(isolated),
        "created_count": len(created),
        "pending_isolation_count": len(isolated),
        "pending_isolation_sources": [str(action.get("source", "")) for action, _parents in isolated],
        "pending_isolation_targets": [str(action.get("target", "")) for action, _parents in isolated],
        "pending_count": plan.get("counts", {}).get("pending", 0),
        "deferred_count": plan.get("counts", {}).get("deferred", 0),
        "rollback_status": "NOT_RUN",
        "manual_recovery_required": False,
        "error_summary": "",
    }


def verify_plan(plan: Dict[str, Any], root: str | Path) -> Dict[str, Any]:
    root_path = _canonical(root)
    integrity = _plan_integrity_error(plan, None, root_path)
    if integrity:
        return {"status": "FAIL", "error_summary": integrity, "pending_count": 0}
    missing: List[str] = []
    verified = 0
    pending = 0
    deferred = 0
    for entry in plan.get("entries", []):
        status = entry.get("status")
        if status.startswith("PENDING"):
            pending += 1
            continue
        if status == "DEFERRED_BATCH":
            # A large-library NFO plan carries the complete inventory but only
            # mutates one bounded batch.  Deferred units are not unresolved
            # identities; they must be left for the next fresh plan rather
            # than turning the current batch into a false pending stop.
            deferred += 1
            continue
        target = _lexical(str(entry["target_path"]))
        if not target.is_file() or target.is_symlink():
            missing.append(f"missing NFO target: {target}")
            continue
        parsed, error = _parse_nfo(target)
        if parsed is None:
            missing.append(f"{target}: {error}")
            continue
        if _nfo_id(parsed) != entry.get("tmdb_id"):
            missing.append(f"{target}: TMDb ID does not match locked plan")
            continue
        if target.stem != Path(str(entry["source_video"])).stem:
            missing.append(f"{target}: NFO basename does not match video basename")
            continue
        verified += 1
    pending_isolation_verified = 0
    for action in plan.get("pending_actions", []):
        if not isinstance(action, dict):
            missing.append("invalid pending isolation action")
            continue
        source = _lexical(str(action.get("source", "")))
        target = _lexical(str(action.get("target", "")))
        if os.path.lexists(source):
            missing.append(f"pending source still exists: {source}")
            continue
        if target.is_symlink() or not target.is_dir():
            missing.append(f"pending target is missing or unsafe: {target}")
            continue
        try:
            if _tree_fingerprint(target) != action.get("source_tree_hash"):
                missing.append(f"pending target tree is incomplete or changed: {target}")
                continue
        except NfoPlanError as error:
            missing.append(str(error))
            continue
        pending_isolation_verified += 1
    return {
        "status": "PASS" if not missing else "FAIL",
        "verified_count": verified,
        "pending_count": pending,
        "deferred_count": deferred,
        "pending_isolation_count": pending_isolation_verified,
        "pending_isolation_expected": len(plan.get("pending_actions", [])),
        "pending_confirmation": bool(pending),
        "missing": missing,
        "error_summary": "; ".join(missing),
    }


def _write_identity_lock(root: Path, plan: Dict[str, Any], verification: Dict[str, Any]) -> Path:
    """Record the exact post-verify evidence used by the NFO gate.

    A lock is intentionally separate from ``progress.json``: it is created
    only after formal apply and verify PASS and includes live fingerprints so
    a later replacement cannot masquerade as the verified NFO.
    """

    if verification.get("status") != "PASS":
        raise NfoPlanError("cannot write identity lock before NFO verify PASS")
    locks: List[Dict[str, Any]] = []
    for entry in plan.get("entries", []):
        if entry.get("status") not in {"AUTO_CREATE", "KEEP_EXISTING"}:
            continue
        video = _lexical(str(entry.get("source_video", "")))
        nfo = _lexical(str(entry.get("target_path", "")))
        parsed, error = _parse_nfo(nfo)
        if parsed is None or _nfo_id(parsed) is None:
            raise NfoPlanError(f"cannot lock unverified NFO {nfo}: {error}")
        locks.append(
            {
                "video_path": str(video),
                "nfo_path": str(nfo),
                "video_fingerprint": _file_fingerprint(video),
                "nfo_sha256": _sha256_bytes(nfo.read_bytes()),
                "tmdb_id": _nfo_id(parsed),
            }
        )
    recovery = _ensure_recovery(root)
    path = recovery / f"nfo-identity-lock-{_timestamp()}.json"
    _write_json(
        path,
        {
            "schema": "movie-organizing-nfo/identity-lock/v1",
            "version": VERSION,
            "task_root": str(root),
            "plan_hash": plan.get("plan_hash", ""),
            "verified_at": datetime.now().isoformat(timespec="seconds"),
            "locks": locks,
        },
    )
    return path


def _identity_locks(root: Path) -> List[Dict[str, Any]]:
    recovery = root / WORK_RECORD_DIR / RECOVERY_DIR
    if not recovery.is_dir() or recovery.is_symlink():
        return []
    locks: List[Dict[str, Any]] = []
    try:
        entries = list(os.scandir(recovery))
    except OSError:
        return []
    for entry in entries:
        path = Path(entry.path)
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False) or not path.name.startswith("nfo-identity-lock-"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get("schema") != "movie-organizing-nfo/identity-lock/v1":
            continue
        if _canonical(str(payload.get("task_root", ""))) != root:
            continue
        value = payload.get("locks")
        if isinstance(value, list):
            locks.extend(item for item in value if isinstance(item, dict))
    return locks


def _lock_matches(root: Path, video: Path, nfo: Path, tmdb_id: int) -> bool:
    expected_video = _file_fingerprint(video)
    try:
        expected_nfo_sha = _sha256_bytes(nfo.read_bytes())
    except OSError:
        return False
    for lock in _identity_locks(root):
        if _canonical(str(lock.get("video_path", ""))) != _canonical(video):
            continue
        if _canonical(str(lock.get("nfo_path", ""))) != _canonical(nfo):
            continue
        if lock.get("tmdb_id") != tmdb_id or lock.get("nfo_sha256") != expected_nfo_sha:
            continue
        if lock.get("video_fingerprint") == expected_video:
            return True
    return False


def audit_nfo_tree(task_root: str | Path, naming_plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = _canonical(task_root)
    try:
        preprocessor = _load_preprocessor()
        plan = naming_plan or preprocessor.make_plan(root, persist=False)
    except Exception as error:
        return {"schema": NFO_GATE_SCHEMA, "version": VERSION, "status": "FAIL", "counts": {"active_video_units": 0, "active_missing_nfo_files": 0, "active_invalid_nfo_files": 1, "active_nfo_identity_conflicts": 0}, "items": [{"path": str(root), "reason": f"NFO audit could not load naming plan: {error}"}], "error_summary": str(error)}
    units = [item for item in plan.get("bundles", []) if item.get("status") == "NAMING_PASS"]
    missing = 0
    invalid = 0
    conflicts = 0
    unverified = 0
    items: List[Dict[str, str]] = []
    for bundle in units:
        video = Path(str(bundle.get("expected_video_target", "")))
        expected = video.with_suffix(".nfo")
        if os.path.lexists(expected) and expected.is_symlink():
            invalid += 1
            items.append({"path": str(expected), "reason": "same-stem NFO must not be a symlink"})
            continue
        if not expected.is_file():
            missing += 1
            items.append({"path": str(expected), "reason": "same-stem NFO is missing"})
            continue
        parsed, error = _parse_nfo(expected)
        if parsed is None or _nfo_id(parsed) is None:
            invalid += 1
            items.append({"path": str(expected), "reason": error or "NFO has no valid TMDb uniqueid"})
            continue
        parsed_video = _parse_video(video, preprocessor)
        nfo_year = (parsed.findtext("year") or "").strip()
        nfo_original = (parsed.findtext("originaltitle") or "").strip()
        if parsed_video and ((nfo_year and nfo_year != parsed_video["year"]) or (nfo_original and not _title_matches(parsed_video["title"], [nfo_original]))):
            conflicts += 1
            items.append({"path": str(expected), "reason": "NFO identity fields conflict with final video stem"})
            continue
        if not _lock_matches(root, video, expected, int(_nfo_id(parsed))):
            unverified += 1
            items.append({"path": str(expected), "reason": "NFO lacks matching formal identity-lock evidence or evidence drifted"})
    # An additional same-directory NFO is never silently ignored.
    for bundle in units:
        movie_dir = Path(str(bundle.get("expected_movie_dir_path", "")))
        expected = Path(str(bundle.get("expected_video_target", ""))).with_suffix(".nfo")
        try:
            extras = [item for item in movie_dir.iterdir() if item.is_file() and item.suffix.casefold() == ".nfo" and _canonical(item) != _canonical(expected)]
        except OSError:
            extras = []
        for extra in extras:
            conflicts += 1
            items.append({"path": str(extra), "reason": "unrelated or duplicate NFO in movie directory"})
    counts = {"active_video_units": len(units), "active_missing_nfo_files": missing, "active_invalid_nfo_files": invalid, "active_nfo_identity_conflicts": conflicts, "active_nfo_identity_unverified": unverified}
    status = "PASS" if units and missing == 0 and invalid == 0 and conflicts == 0 and unverified == 0 else "FAIL"
    return {"schema": NFO_GATE_SCHEMA, "version": VERSION, "status": status, "counts": counts, "items": items[:20], "item_count": len(items)}


def _matching_result(root: Path, plan_hash: str, mode: str, dry_run: Optional[bool]) -> bool:
    recovery = _ensure_recovery(root)
    try:
        entries = list(os.scandir(recovery))
    except OSError:
        return False
    for entry in entries:
        path = Path(entry.path)
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False) or path.suffix.casefold() != ".json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict) or value.get("schema") != NFO_RESULT_SCHEMA:
            continue
        if value.get("status") != "PASS" or value.get("mode") != mode or value.get("plan_hash") != plan_hash:
            continue
        if dry_run is not None and value.get("dry_run") is not dry_run:
            continue
        return True
    return False


def _write_result(root: Path, plan: Dict[str, Any], mode: str, result: Dict[str, Any]) -> Path:
    recovery = _ensure_recovery(root)
    path = recovery / f"nfo-result-{mode}-{_timestamp()}.json"
    record = {"schema": NFO_RESULT_SCHEMA, "version": VERSION, "mode": mode, "task_root": str(root), "plan_path": plan.get("plan_path", ""), "plan_hash": plan.get("plan_hash", ""), **result}
    _write_json(path, record)
    return path


def _cli_plan_summary(plan: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "PASS", "version": VERSION, "plan_path": plan.get("plan_path", ""), "plan_hash": plan.get("plan_hash", ""), "large_library_mode": plan.get("large_library_mode", False), "batch_director": plan.get("batch_director", ""), "counts": plan.get("counts", {})}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="movie-organizing deterministic TMDb NFO gate")
    parser.add_argument("mode", choices=("plan", "apply", "verify"))
    parser.add_argument("--task-root", required=True)
    parser.add_argument("--plan")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    root = _canonical(args.task_root)
    if args.mode == "plan":
        try:
            plan = make_plan(root)
        except (OSError, NfoPlanError, ValueError) as error:
            print(json.dumps({"status": "FAIL", "version": VERSION, "error_summary": f"NFO plan failed: {error}"}, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(_cli_plan_summary(plan), ensure_ascii=False, indent=2))
        return 0
    if not args.plan:
        print(json.dumps({"status": "FAIL", "version": VERSION, "mode": args.mode, "error_summary": "--plan is required"}, ensure_ascii=False, indent=2))
        return 1
    try:
        plan_path = _safe_recovery_file(root, args.plan, "NFO plan")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            raise NfoPlanError("NFO plan must contain an object")
        error = _plan_integrity_error(plan, plan_path, root)
        if error:
            raise NfoPlanError(error)
        if args.mode == "apply":
            if not args.dry_run and not _matching_result(root, str(plan["plan_hash"]), "apply", True):
                result = {"status": "FAIL", "executed_actions": 0, "error_summary": "successful NFO dry-run evidence is required before formal apply"}
            else:
                result = apply_plan(plan, root, dry_run=args.dry_run)
            result["dry_run"] = bool(args.dry_run)
        else:
            if not _matching_result(root, str(plan["plan_hash"]), "apply", False):
                result = {"status": "FAIL", "error_summary": "successful formal NFO apply evidence is required before verify", "pending_count": 0}
            else:
                result = verify_plan(plan, root)
                if result.get("status") == "PASS":
                    try:
                        result["identity_lock_path"] = str(_write_identity_lock(root, plan, result))
                    except (OSError, NfoPlanError) as error:
                        result = {
                            **result,
                            "status": "FAIL",
                            "error_summary": f"identity-lock write failed: {error}",
                        }
        result["mode"] = args.mode
        try:
            result["result_path"] = str(_write_result(root, plan, args.mode, result))
        except OSError as error:
            result.update({"status": "FAIL", "error_summary": f"NFO result write failed: {error}"})
    except (OSError, ValueError, NfoPlanError) as error:
        result = {"status": "FAIL", "version": VERSION, "mode": args.mode, "executed_actions": 0, "error_summary": f"NFO plan rejected: {error}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
