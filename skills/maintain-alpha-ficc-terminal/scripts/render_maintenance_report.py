"""Render sanitized Chinese maintenance reports without claiming Discord delivery."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from maintenance_contract import (
    completion_status,
    sanitize,
    validate_agent_kb_publication,
    validate_run_record,
)


def _safe_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return sanitize(record)


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-/]{0,119}$")
_SAFE_PATH = re.compile(r"^/?[A-Za-z0-9][A-Za-z0-9_.\-/]{0,239}$")


def _identifier(value: Any, fallback: str) -> str:
    text = str(value)
    return text if _SAFE_IDENTIFIER.fullmatch(text) else fallback


def _path(value: Any) -> str:
    if value is None:
        return "未记录"
    text = str(value)
    segments = text.removeprefix("/").split("/")
    if not _SAFE_PATH.fullmatch(text) or any(segment in {"", ".", ".."} for segment in segments):
        return "未记录"
    return text


def _agent_kb_publication(record: Mapping[str, Any]) -> str | None:
    if validate_agent_kb_publication(record):
        return None
    publication = record.get("agent_kb")
    if not isinstance(publication, Mapping):
        return None
    status = str(publication.get("status", "remote_not_visible"))
    if status == "remote_visible":
        return f"Agent-KB：remote_visible；远端路径：{_path(publication.get('canonical_path'))}"
    if status in {"handoff_push_failed", "remote_not_visible"}:
        return f"Agent-KB：{status}；本地路径：{_path(publication.get('local_path'))}"
    return "Agent-KB：remote_not_visible；本地路径：未记录"


def _outward_status(record: Mapping[str, Any], ledger_persisted: bool) -> str:
    return _identifier(
        completion_status(record, ledger_persisted=ledger_persisted),
        "reporting_failed",
    )


def _status_label(status: str) -> str:
    labels = {
        "healthy_report_ready": "healthy_report_ready（健康）",
        "repaired_report_ready": "repaired_report_ready（已修复完成）",
        "observed_report_ready": "observed_report_ready（已观察）",
    }
    return labels.get(status, status)


def _check_summary(record: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    failed: list[str] = []
    warnings: list[str] = []
    for check in record.get("checks", []):
        if not isinstance(check, Mapping):
            continue
        check_id = _identifier(check.get("id"), "未命名检查")
        status = str(check.get("status", "unknown"))
        status = status if status in {"failed", "timeout", "stale_tail", "warning", "ok"} else "unknown"
        if status in {"failed", "timeout", "stale_tail"}:
            error_type = _identifier(check.get("error_type"), "未分类")
            failed.append(f"{check_id}（{status}；错误类型：{error_type}）")
        elif status == "warning":
            warnings.append(f"{check_id}（warning）")
    return failed, warnings


def _changed_files(record: Mapping[str, Any]) -> str:
    files = record.get("changed_files", [])
    if not isinstance(files, list) or not files:
        return "未记录文件变更"
    return "、".join(_identifier(path, "已记录文件") for path in files)


def _verification(record: Mapping[str, Any]) -> str:
    items = record.get("verification", [])
    if not isinstance(items, list) or not items:
        return "未执行修改验证（只读探测）"
    return "；".join(_identifier(item.get("id"), "未命名验证") for item in items if isinstance(item, Mapping))


def render_discord(
    record: Mapping[str, Any], *, ledger_persisted: bool = False
) -> str:
    """Prepare, but never deliver, a compact Chinese Discord update."""
    safe = _safe_record(record)
    failed, warnings = _check_summary(safe)
    status = _outward_status(safe, ledger_persisted)
    status_label = _status_label(status)
    lines = [f"Alpha-FICC 维护：{status_label}"]
    lines.append("故障：" + ("、".join(failed) if failed else "无"))
    if warnings:
        lines.append("告警：" + "、".join(warnings))
    lines.append("修改：" + _changed_files(safe))
    lines.append("commit：" + ("已创建（标识已脱敏）" if safe.get("commit") else "未创建"))
    lines.append("部署：" + _identifier(safe.get("deployment"), "未执行"))
    lines.append("验证：" + _verification(safe))
    lines.append("回滚：" + ("已准备" if safe.get("rollback") else "不适用"))
    publication = _agent_kb_publication(safe)
    if publication:
        lines.append(publication)
    lines.append("Discord：仅 prepared，未发送。")
    return "\n".join(lines)


def render_builder_report(
    record: Mapping[str, Any], *, ledger_persisted: bool = False
) -> str:
    """Render the durable Chinese builder report using the Task 1 contract."""
    safe = _safe_record(record)
    failed, warnings = _check_summary(safe)
    violations = validate_run_record(safe)
    status = _outward_status(safe, ledger_persisted)
    lines = [
        "# Alpha-FICC Hermes 维护执行报告",
        "",
        f"- 运行：{_identifier(safe.get('run_id'), '未记录')}",
        f"- 状态：{_status_label(status)}",
        f"- 故障：{'、'.join(failed) if failed else '无'}",
        f"- 告警：{'、'.join(warnings) if warnings else '无'}",
        f"- 修改文件：{_changed_files(safe)}",
        f"- commit：{'已创建（标识已脱敏）' if safe.get('commit') else '未创建'}",
        f"- 部署：{_identifier(safe.get('deployment'), '未执行')}",
        f"- 验证：{_verification(safe)}",
        f"- 回滚：{'已准备' if safe.get('rollback') else '不适用'}",
    ]
    publication = _agent_kb_publication(safe)
    if publication:
        lines.append(f"- {publication}")
    lines.extend(
        [
            "- Discord：仅 prepared，未发送。",
            f"- 契约校验：{'通过' if not violations else '；'.join(violations)}",
        ]
    )
    return "\n".join(lines) + "\n"
