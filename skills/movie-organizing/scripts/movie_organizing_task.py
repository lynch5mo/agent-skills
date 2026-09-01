#!/usr/bin/env python3
"""Read-only workflow gate; emits one allowed command and never mutates media."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import shlex
import stat
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
VERSION = "1.3.6"
FIXED_STEPS = ("verify_install", "scope_lock", "inventory", "naming_contract", "preprocess", "exception_resolution", "core_gate", "nfo_gate", "dedupe_gate", "cleanup_final_audit")
STOP_PHASE = "STOP_RECOVERY_REQUIRED"
STOP_PENDING_PHASE = "STOP_PENDING_CONFIRMATION"
WORK_RECORD_DIR, RECOVERY_DIR = "_work-record_", "recovery"
PRE_SCHEMA = "movie-organizing-preprocessor/v1"
PRE_RESULT_SCHEMA = "movie-organizing-preprocessor/result/v1"
AUDIT_SCHEMA = "movie-organizing-audit/v1"
SLOW_TEMPLATE_SCHEMA = "movie-organizing-slowpath/template/v1"
SLOW_PLAN_SCHEMA = "movie-organizing-slowpath/plan/v1"
SLOW_RESULT_SCHEMA = "movie-organizing-slowpath/result/v1"
NFO_PLAN_SCHEMA = "movie-organizing-nfo/plan/v1"
NFO_RESULT_SCHEMA = "movie-organizing-nfo/result/v1"
PRE_SEAL_SCHEMA = "movie-organizing-preprocessor/seal/v1"
DECISION_SCHEMAS = {"movie-organizing-slowpath/decisions/v1", "movie-organizing-decisions/v1"}
SCRIPT_DIR = Path(__file__).resolve().parent
PREPROCESSOR, AUDIT, SLOWPATH, NFO, SKILL_DIR = (SCRIPT_DIR / "movie_organizing_preprocessor.py", SCRIPT_DIR / "movie_organizing_audit.py", SCRIPT_DIR / "movie_organizing_slowpath.py", SCRIPT_DIR / "movie_organizing_nfo.py", SCRIPT_DIR.parent)
def _canonical(path: str | Path) -> Path:
    return Path(os.path.realpath(os.fspath(path)))

def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return path != root
def _recovery_dir(root: Path) -> Tuple[Optional[Path], Optional[str]]:
    work, recovery = root / WORK_RECORD_DIR, root / WORK_RECORD_DIR / RECOVERY_DIR
    for directory in (work, recovery):
        try:
            mode = os.lstat(directory).st_mode
        except FileNotFoundError:
            continue
        except OSError as error:
            return None, f"cannot inspect recovery control path: {error}"
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode) or not _inside(root, _canonical(directory)):
            return None, f"recovery control path is not a real in-root directory: {directory}"
    return (recovery if recovery.is_dir() else None), None
def _recovery_records(root: Path) -> List[Tuple[int, Path, Dict[str, Any]]]:
    recovery, error = _recovery_dir(root)
    if error or recovery is None:
        return []
    try:
        entries = list(os.scandir(recovery))
    except OSError:
        return []
    result: List[Tuple[int, Path, Dict[str, Any]]] = []
    for entry in entries:
        path = Path(entry.path)
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False) or path.suffix.casefold() != ".json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            mtime = os.lstat(path).st_mtime_ns
        except (OSError, ValueError):
            continue
        if isinstance(value, dict):
            result.append((mtime, path, value))
    return sorted(result, key=lambda item: (item[0], item[1].name))
def _latest(records: Iterable[Tuple[int, Path, Dict[str, Any]]], predicate) -> Optional[Tuple[int, Path, Dict[str, Any]]]:
    values = [item for item in records if predicate(item[2])]
    return max(values, key=lambda item: (item[0], item[1].name)) if values else None
def _is_pre_plan(value: Dict[str, Any]) -> bool:
    return value.get("schema") == PRE_SCHEMA and value.get("plan_kind") == "naming"
def _is_nfo_plan(value: Dict[str, Any]) -> bool:
    return value.get("schema") == NFO_PLAN_SCHEMA
def _is_batch_seal(value: Dict[str, Any]) -> bool:
    return value.get("schema") == PRE_SEAL_SCHEMA and value.get("mode") == "seal"
def _is_formal(value: Dict[str, Any]) -> bool:
    return value.get("schema") in {PRE_RESULT_SCHEMA, SLOW_RESULT_SCHEMA, NFO_RESULT_SCHEMA} and (value.get("mode") == "verify" or (value.get("mode") == "apply" and value.get("dry_run") is not True))
def _next(*argv: str | Path) -> Dict[str, Any]:
    values = [str(value) for value in argv]
    return {"argv": values, "command": shlex.join(values)}
def _pre(mode: str, root: Path, plan: Optional[Path] = None, dry_run: bool = False) -> Dict[str, Any]:
    argv: List[str | Path] = [sys.executable, PREPROCESSOR, mode, "--task-root", root]
    if plan is not None:
        argv += ["--plan", _canonical(plan)]
    if dry_run:
        argv.append("--dry-run")
    return _next(*argv)
def _nfo(mode: str, root: Path, plan: Optional[Path] = None, dry_run: bool = False) -> Dict[str, Any]:
    argv: List[str | Path] = [sys.executable, NFO, mode, "--task-root", root]
    if plan is not None:
        argv += ["--plan", _canonical(plan)]
    if dry_run:
        argv.append("--dry-run")
    return _next(*argv)
def _audit(root: Path) -> Dict[str, Any]:
    return _next(sys.executable, AUDIT, "audit", "--task-root", root)
def _slow(mode: str, root: Path, *, audit: Optional[Path] = None, phase: Optional[str] = None,
          template: Optional[Path] = None, decisions: Optional[Path] = None, plan: Optional[Path] = None,
          dry_run: bool = False) -> Dict[str, Any]:
    argv: List[str | Path] = [sys.executable, SLOWPATH, mode, "--task-root", root]
    for flag, value in (("--audit", audit), ("--phase", phase), ("--template", template),
                        ("--decisions", decisions), ("--plan", plan)):
        if value is not None:
            argv += [flag, _canonical(value) if isinstance(value, Path) else value]
    if dry_run:
        argv.append("--dry-run")
    return _next(*argv)
def _artifact_path(item: Tuple[int, Path, Dict[str, Any]], field: str) -> Path:
    value = item[2].get(field)
    return _canonical(value) if isinstance(value, str) and value else _canonical(item[1])
def _blocking_failure(records: List[Tuple[int, Path, Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    plans = _latest(records, lambda value: _is_pre_plan(value) or value.get("schema") in {SLOW_PLAN_SCHEMA, NFO_PLAN_SCHEMA})
    audit = _latest(records, lambda value: value.get("schema") == AUDIT_SCHEMA)
    formal = _latest(records, lambda value: _is_formal(value) and value.get("schema") != NFO_RESULT_SCHEMA)
    failures = [item for item in records if _is_formal(item[2]) and item[2].get("status") == "FAIL"]
    if not failures:
        return None
    hard_failures = [item for item in failures if bool(item[2].get("manual_recovery_required")) or item[2].get("rollback_status") != "PASS"]
    if hard_failures:
        return max(hard_failures, key=lambda item: (item[0], item[1].name))[2]
    if plans is not None:
        failures = [item for item in failures if item[2].get("plan_hash") == plans[2].get("plan_hash")]
    if not failures:
        return None
    failure = max(failures, key=lambda item: (item[0], item[1].name))
    if formal is not None and formal[0] > failure[0]:
        return None
    if plans is not None and plans[0] > failure[0]:
        return None
    if audit is not None and audit[0] > failure[0]:
        return None
    return None
def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
def _prerequisites(root: Path) -> Tuple[bool, str]:
    try:
        audit = _load_module(AUDIT, "movie_organizing_task_audit")
        result = audit.verify_install(SKILL_DIR)
        if not isinstance(result, dict) or result.get("status") != "PASS":
            failures = result.get("failures", []) if isinstance(result, dict) else []
            return False, "install verification failed: " + "; ".join(map(str, failures[:3]))
        pre = _load_module(PREPROCESSOR, "movie_organizing_task_preprocessor")
        actual = pre._contract_hash()
        expected = getattr(pre, "EXPECTED_NAMING_CONTRACT_SHA256", "")
        if not actual or actual != expected:
            return False, "naming-contract hash mismatch"
    except Exception as error:
        return False, f"read-only prerequisite check failed: {error}"
    return True, ""
def _audit_state(root: Path, item: Tuple[int, Path, Dict[str, Any]]) -> Tuple[str, Optional[Dict[str, Any]], str]:
    value = item[2]
    if not isinstance(value.get("task_root"), str) or _canonical(value["task_root"]) != root:
        return STOP_PHASE, None, "audit task_root does not match TASK_ROOT"
    core = value.get("core_gate") if isinstance(value.get("core_gate"), dict) else {}
    nfo = value.get("nfo_gate") if isinstance(value.get("nfo_gate"), dict) else {}
    dedupe = value.get("dedupe_gate") if isinstance(value.get("dedupe_gate"), dict) else {}
    counts = core.get("counts") if isinstance(core.get("counts"), dict) else {}
    active_count = counts.get("active_video_units")
    try:
        pending_count = int(value.get("pending_video_count", 0) or 0)
    except (TypeError, ValueError):
        pending_count = 0
    blocker_lists = (core.get("action_required"), core.get("exceptions"), core.get("director_violations"),
                     core.get("control_violations"), value.get("control_violations"))
    try:
        no_core_blockers = not any(blocker_lists) and all(
            int(raw or 0) == 0 for key, raw in counts.items() if key != "active_video_units"
        )
    except (TypeError, ValueError):
        no_core_blockers = False
    if active_count == 0:
        if pending_count > 0 and no_core_blockers:
            return STOP_PENDING_PHASE, None, f"当前任务无可继续自动处理的影片，待确认 {pending_count} 项；audit 仍 BLOCKED，不能声称完成"
        return STOP_PHASE, None, "audit has no active video units; recovery is required and no automatic action is allowed"
    try:
        naming_backlog = bool(core.get("action_required")) or bool(core.get("director_violations")) or any(int(counts.get(key, 0) or 0) > 0 for key in ("required_actions_remaining", "active_nonconforming_director_dirs", "active_nonconforming_movie_dirs", "active_nonconforming_video_files", "active_nonconforming_nfo_files", "active_nonconforming_subtitle_files"))
    except (TypeError, ValueError):
        naming_backlog = True
    if naming_backlog:
        return "preprocess", _pre("plan", root), "audit still reports deterministic naming backlog"
    # NFO is a separate hard gate.  A legacy hand-written audit record that
    # predates v1.3.6 has no nfo_gate and is retained for read-only recovery
    # compatibility; every fresh audit emits the gate explicitly.
    if nfo and nfo.get("status") != "PASS":
        return "nfo_gate", _nfo("plan", root), "audit requires a fresh NFO identity plan"
    if value.get("completion_status") in {"COMPLETE", "CORE_COMPLETE_PENDING"}:
        return "cleanup_final_audit", None, ""
    if value.get("completion_status") == "BLOCKED" or value.get("status") == "FAIL":
        if core.get("status") != "PASS":
            return "exception_resolution", _slow("template", root, audit=_artifact_path(item, "report_path"), phase="core_exception"), ""
        if dedupe.get("status") != "PASS":
            return "dedupe_gate", _slow("template", root, audit=_artifact_path(item, "report_path"), phase="dedupe"), ""
        return STOP_PHASE, None, "audit is blocked at cleanup gate; inspect the audit before mutating"
    return "core_gate", _audit(root), "audit completion state is missing or invalid"
def _state(records: List[Tuple[int, Path, Dict[str, Any]]], root: Path) -> Tuple[str, Optional[Dict[str, Any]], str]:
    failure = _blocking_failure(records)
    if failure is not None:
        return STOP_PHASE, None, str(failure.get("error_summary", "formal recovery record is FAIL"))
    audit = _latest(records, lambda value: value.get("schema") == AUDIT_SCHEMA)
    naming = _latest(records, _is_pre_plan)
    nfo_plan = _latest(records, _is_nfo_plan)
    nfo_result_any = _latest(records, lambda value: value.get("schema") == NFO_RESULT_SCHEMA and value.get("mode") in {"apply", "verify"})
    nfo_anchor = max((item for item in (nfo_plan, nfo_result_any) if item), key=lambda item: (item[0], item[1].name), default=None)
    slow_plan = _latest(records, lambda value: value.get("schema") == SLOW_PLAN_SCHEMA)
    slow_template = _latest(records, lambda value: value.get("schema") == SLOW_TEMPLATE_SCHEMA)
    slow_result_any = _latest(records, lambda value: value.get("schema") == SLOW_RESULT_SCHEMA and value.get("mode") in {"apply", "verify"})
    slow_anchor = max((item for item in (slow_plan, slow_template, slow_result_any) if item), key=lambda item: (item[0], item[1].name), default=None)
    naming_result = _latest(records, lambda value: value.get("schema") == PRE_RESULT_SCHEMA and naming is not None and value.get("plan_hash") == naming[2].get("plan_hash") and value.get("mode") in {"apply", "verify"})
    naming_anchor = max((item for item in (naming, naming_result) if item), key=lambda item: (item[0], item[1].name), default=None)
    slow_is_newer = slow_anchor is not None and (naming_anchor is None or slow_anchor[0] > naming_anchor[0])
    if naming is not None and not slow_is_newer:
        if not isinstance(naming[2].get("plan_hash"), str) or not naming[2].get("plan_hash") or _canonical(str(naming[2].get("task_root", ""))) != root:
            return STOP_PHASE, None, "naming plan record is missing a matching task_root or plan_hash"
        if (audit is not None and audit[0] >= naming[0]
                and audit[2].get("plan_hash") == naming[2].get("plan_hash")):
            return _audit_state(root, audit)
        result = _latest(records, lambda value: value.get("schema") == PRE_RESULT_SCHEMA and value.get("plan_hash") == naming[2].get("plan_hash") and value.get("mode") in {"apply", "verify"})
        if result is None and audit is not None and audit[0] > naming[0]:
            return _audit_state(root, audit)
        if result is None or result[0] < naming[0]:
            return "preprocess", _pre("apply", root, _artifact_path(naming, "plan_path"), dry_run=True), ""
        value = result[2]
        if value.get("status") not in {"PASS", "FAIL"}:
            return STOP_PHASE, None, "naming recovery record has an invalid status"
        if value.get("status") == "FAIL":
            if audit is not None and audit[0] > result[0]:
                return _audit_state(root, audit)
            return "preprocess", _pre("plan", root), "automatic rollback completed; create a fresh naming plan"
        if value.get("mode") == "apply" and value.get("dry_run") is True:
            return "preprocess", _pre("apply", root, _artifact_path(naming, "plan_path")), ""
        if value.get("mode") == "apply":
            return "preprocess", _pre("verify", root, _artifact_path(naming, "plan_path")), ""
        if value.get("mode") == "verify" and value.get("status") == "PASS":
            summary = naming[2].get("summary") if isinstance(naming[2].get("summary"), dict) else {}
            if bool(summary.get("large_library_mode")) or bool(naming[2].get("large_library_mode")):
                seal = _latest(records, lambda candidate: _is_batch_seal(candidate) and candidate.get("plan_hash") == naming[2].get("plan_hash"))
                if seal is None or seal[0] < result[0]:
                    return "preprocess", _pre("seal", root, _artifact_path(naming, "plan_path")), "formal naming verify PASS must be sealed before the next batch"
            if int(summary.get("deferred_action_units", 0) or 0) > 0:
                return "preprocess", _pre("plan", root), "sealed bounded batch still has deferred units; create a fresh plan"
            if audit is not None and audit[0] > result[0]:
                return _audit_state(root, audit)
            return "core_gate", _audit(root), ""

    # NFO has the same guarded dry-run/apply/verify chain as naming.  A newer
    # audit supersedes an old NFO plan and causes the gate to be replanned.
    if nfo_plan is not None and (audit is None or (nfo_anchor is not None and nfo_anchor[0] > audit[0])):
        if not isinstance(nfo_plan[2].get("plan_hash"), str) or not nfo_plan[2].get("plan_hash") or _canonical(str(nfo_plan[2].get("task_root", ""))) != root:
            return STOP_PHASE, None, "NFO plan record is missing a matching task_root or plan_hash"
        nfo_result = _latest(records, lambda value: value.get("schema") == NFO_RESULT_SCHEMA and value.get("plan_hash") == nfo_plan[2].get("plan_hash") and value.get("mode") in {"apply", "verify"})
        if nfo_result is None or nfo_result[0] < nfo_plan[0]:
            return "nfo_gate", _nfo("apply", root, _artifact_path(nfo_plan, "plan_path"), dry_run=True), ""
        nfo_value = nfo_result[2]
        if nfo_value.get("status") not in {"PASS", "FAIL"}:
            return STOP_PHASE, None, "NFO recovery record has an invalid status"
        if nfo_value.get("status") == "FAIL":
            if nfo_value.get("rollback_status") == "PASS" and not bool(nfo_value.get("manual_recovery_required")):
                return "nfo_gate", _nfo("plan", root), "NFO batch rolled back; create a fresh identity plan"
            return STOP_PHASE, None, str(nfo_value.get("error_summary", "NFO recovery failed"))
        if nfo_value.get("mode") == "apply" and nfo_value.get("dry_run") is True:
            return "nfo_gate", _nfo("apply", root, _artifact_path(nfo_plan, "plan_path")), ""
        if nfo_value.get("mode") == "apply":
            return "nfo_gate", _nfo("verify", root, _artifact_path(nfo_plan, "plan_path")), ""
        if nfo_value.get("mode") == "verify" and nfo_value.get("status") == "PASS":
            pending = int(nfo_value.get("pending_count", 0) or 0)
            isolated = int(nfo_value.get("pending_isolation_count", 0) or 0)
            expected_isolated = int(nfo_value.get("pending_isolation_expected", 0) or 0)
            if pending and (isolated < pending or expected_isolated < pending) and (audit is None or audit[0] <= nfo_result[0]):
                # A PENDING_* identity is allowed to continue only after the
                # official plan has moved that complete movie unit into the
                # task-scoped _待确认_ directory and verify has proved the
                # move.  A blocked/colliding unit is an explicit terminal
                # stop; otherwise a fresh audit would rediscover it forever.
                return STOP_PENDING_PHASE, None, f"NFO 身份无法唯一锁定且待确认隔离未完成（{pending} 项）；路径冲突或漂移需人工处理"
            deferred = int(nfo_value.get("deferred_count", 0) or 0)
            if deferred > 0:
                # Do not run a full-tree audit while the NFO inventory still
                # has deferred units: that audit would correctly report their
                # missing locks and send us back to the first batch forever.
                # The next fresh NFO plan advances by skipping identity locks
                # already sealed by the preceding formal verify.
                return "nfo_gate", _nfo("plan", root), f"NFO bounded batch verified; continue with {deferred} deferred units"
            if audit is not None and audit[0] > nfo_result[0]:
                return _audit_state(root, audit)
            return "core_gate", _audit(root), ""

    if slow_template is not None and (slow_plan is None or slow_template[0] > slow_plan[0]):
        if audit is not None and audit[0] > slow_template[0]:
            return _audit_state(root, audit)
        phase = str(slow_template[2].get("phase", ""))
        if phase not in {"core_exception", "dedupe"}:
            return STOP_PHASE, None, "slowpath template phase is invalid"
        decisions = _latest(records, lambda value: value.get("schema") in DECISION_SCHEMAS and value.get("phase") == phase and value.get("task_root") in {None, str(root)})
        phase_name = "exception_resolution" if phase == "core_exception" else "dedupe_gate"
        if decisions is None or decisions[0] < slow_template[0]:
            return phase_name, None, "awaiting semantic decisions; no filesystem action is allowed"
        return phase_name, _slow("plan", root, audit=_canonical(str(slow_template[2].get("audit_path", ""))), template=_artifact_path(slow_template, "template_path"), decisions=_canonical(decisions[1])), ""

    if slow_plan is not None:
        if not isinstance(slow_plan[2].get("plan_hash"), str) or not slow_plan[2].get("plan_hash") or _canonical(str(slow_plan[2].get("task_root", ""))) != root:
            return STOP_PHASE, None, "slowpath plan record is missing a matching task_root or plan_hash"
        result = _latest(records, lambda value: value.get("schema") == SLOW_RESULT_SCHEMA and value.get("plan_hash") == slow_plan[2].get("plan_hash") and value.get("mode") in {"apply", "verify"})
        phase_name = "exception_resolution" if slow_plan[2].get("phase") == "core_exception" else "dedupe_gate"
        if result is None and audit is not None and audit[0] > slow_plan[0]:
            return _audit_state(root, audit)
        if result is None or result[0] < slow_plan[0]:
            return phase_name, _slow("apply", root, plan=_artifact_path(slow_plan, "plan_path"), dry_run=True), ""
        value = result[2]
        if value.get("status") not in {"PASS", "FAIL"}:
            return STOP_PHASE, None, "slowpath recovery record has an invalid status"
        if value.get("status") == "FAIL":
            return phase_name, _audit(root), "automatic rollback completed; create a fresh audit before rebuilding the slow plan"
        if value.get("mode") == "apply" and value.get("dry_run") is True:
            return phase_name, _slow("apply", root, plan=_artifact_path(slow_plan, "plan_path")), ""
        if value.get("mode") == "apply":
            return phase_name, _slow("verify", root, plan=_artifact_path(slow_plan, "plan_path")), ""
        if value.get("mode") == "verify" and value.get("status") == "PASS":
            if audit is not None and audit[0] > result[0]:
                return _audit_state(root, audit)
            return "core_gate", _audit(root), ""

    formal = _latest(records, _is_formal)
    if formal is not None:
        value = formal[2]
        if value.get("status") == "FAIL" and value.get("rollback_status") == "PASS" and not bool(value.get("manual_recovery_required")):
            if audit is not None and audit[0] > formal[0]:
                return _audit_state(root, audit)
            return "preprocess", _pre("plan", root), "automatic rollback completed; create a fresh naming plan"
        if value.get("mode") == "apply" and value.get("dry_run") is True:
            return "preprocess", _pre("apply", root, _artifact_path(formal, "plan_path")), ""
        if value.get("mode") == "apply":
            return "preprocess", _pre("verify", root, _artifact_path(formal, "plan_path")), ""
        if value.get("mode") == "verify" and value.get("status") == "PASS":
            return "core_gate", _audit(root), ""
    if audit is not None:
        return _audit_state(root, audit)
    return STOP_PHASE, None, "no recognized recovery record; recovery state cannot authorize another action"


def _naming_verify_pass(records: List[Tuple[int, Path, Dict[str, Any]]]) -> bool:
    naming = _latest(records, _is_pre_plan)
    if naming is None:
        return False
    result = _latest(records, lambda value: value.get("schema") == PRE_RESULT_SCHEMA
                      and value.get("plan_hash") == naming[2].get("plan_hash")
                      and value.get("mode") in {"apply", "verify"})
    return bool(result and result[0] >= naming[0] and result[2].get("mode") == "verify"
                and result[2].get("status") == "PASS")
def _stop(base: Dict[str, Any], error: str) -> Dict[str, Any]:
    return {**base, "status": "FAIL", "phase": STOP_PHASE, "completed_steps": [], "next_allowed": None, "error": error}
def task_state(task_root: str | Path, *, mode: str) -> Dict[str, Any]:
    lexical_root = Path(os.path.abspath(os.fspath(task_root)))
    try:
        root_mode = os.lstat(lexical_root).st_mode
    except OSError:
        root_mode = None
    root = _canonical(lexical_root)
    base: Dict[str, Any] = {"version": VERSION, "task_root": str(root), "steps": list(FIXED_STEPS)}
    if root_mode is None or stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode) or not root.is_dir():
        return _stop(base, "TASK_ROOT does not exist or is not a real directory")
    recovery, recovery_error = _recovery_dir(root)
    if recovery_error:
        return _stop(base, recovery_error)
    records = _recovery_records(root)
    if not records:
        ok, error = _prerequisites(root)
        if ok:
            phase, next_allowed = "inventory", _pre("plan", root)
            payload = {**base, "status": "PASS", "phase": phase,
                       "completed_steps": ["verify_install", "scope_lock", "naming_contract"],
                       "next_allowed": next_allowed}
            return payload
        return _stop(base, error or "read-only prerequisite check failed")
    phase, next_allowed, error = _state(records, root)
    completed = list(FIXED_STEPS[:FIXED_STEPS.index(phase)]) if phase in FIXED_STEPS else []
    if "preprocess" in completed and not _naming_verify_pass(records):
        completed = completed[:FIXED_STEPS.index("preprocess")]
    payload = {**base, "status": "FAIL" if phase in {STOP_PHASE, STOP_PENDING_PHASE} else "PASS", "phase": phase,
               "completed_steps": completed, "next_allowed": next_allowed}
    if error:
        payload["error"] = error
    return payload
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="movie-organizing repeatable task entrypoint")
    parser.add_argument("mode", choices=("start", "status"))
    parser.add_argument("--task-root", required=True)
    args = parser.parse_args(argv)
    payload = task_state(args.task_root, mode=args.mode)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "PASS" else 1
if __name__ == "__main__":
    raise SystemExit(main())
