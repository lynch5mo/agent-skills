#!/usr/bin/env python3
"""Collect bounded, read-only Alpha-FICC maintenance evidence."""

from __future__ import annotations

import argparse
import json
import os
import selectors
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from maintenance_contract import new_run_record, sanitize, validate_run_record


DEFAULT_DEADLINE_S = 100.0
DEFAULT_MAX_BYTES = 16_384
HTTP_TIMEOUT_S = 5.0


def _normalized_check(
    check_id: str,
    status: str,
    *,
    latency_ms: float = 0.0,
    evidence: Mapping[str, Any] | None = None,
    error_type: str = "",
    error: str = "",
    repair_hint: str = "observe",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "latency_ms": round(latency_ms, 3),
        "evidence": dict(evidence or {}),
        "error_type": error_type,
        "error": error,
        "repair_hint": repair_hint,
    }


def run_command(
    check_id: str, argv: Sequence[str], timeout_s: float, max_bytes: int
) -> dict[str, Any]:
    """Run one diagnostic with a wall-clock deadline and a combined output cap."""
    started = time.monotonic()
    deadline = started + max(0.0, timeout_s)
    limit = max(0, int(max_bytes))
    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        return {
            **_normalized_check(
                check_id,
                "failed",
                latency_ms=(time.monotonic() - started) * 1000,
                error_type=type(exc).__name__,
                error="命令无法启动",
                repair_hint="code_candidate",
            ),
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "exit_code": None,
        }

    selector = selectors.DefaultSelector()
    streams = {"stdout": process.stdout, "stderr": process.stderr}
    for stream in streams.values():
        assert stream is not None
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    truncated = False
    timed_out = False

    while selector.get_map():
        remaining_s = deadline - time.monotonic()
        if remaining_s <= 0:
            timed_out = True
            _kill_process_group(process)
            break
        events = selector.select(timeout=min(remaining_s, 0.1))
        for key, _ in events:
            chunk = os.read(key.fileobj.fileno(), 4096)
            name = "stdout" if key.fileobj is streams["stdout"] else "stderr"
            if not chunk:
                selector.unregister(key.fileobj)
                key.fileobj.close()
                continue
            remaining_bytes = limit - sum(len(value) for value in captured.values())
            if remaining_bytes > 0:
                captured[name].extend(chunk[:remaining_bytes])
            if len(chunk) > remaining_bytes:
                truncated = True
    if not timed_out and process.poll() is None:
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_group(process)
    _close_streams(selector, streams)
    if timed_out:
        try:
            process.wait(timeout=max(0.0, min(0.1, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            pass
    exit_code = process.poll()
    latency_ms = (time.monotonic() - started) * 1000
    stdout, stdout_truncated = _decode_bounded_utf8(bytes(captured["stdout"]))
    stderr, stderr_truncated = _decode_bounded_utf8(bytes(captured["stderr"]))
    truncated = truncated or stdout_truncated or stderr_truncated
    if timed_out:
        check = _normalized_check(
            check_id,
            "timeout",
            latency_ms=latency_ms,
            error_type="timeout",
            error="命令超过时限",
            repair_hint="retry",
        )
    elif exit_code == 0:
        check = _normalized_check(check_id, "ok", latency_ms=latency_ms)
    else:
        check = _normalized_check(
            check_id,
            "failed",
            latency_ms=latency_ms,
            error_type="exit_code",
            error="命令返回非零状态",
            repair_hint="code_candidate",
        )
    return {
        **check,
        "stdout": stdout,
        "stderr": stderr,
        "output_truncated": truncated,
        "exit_code": exit_code,
    }


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate a probe and its inherited-pipe descendants without waiting on them."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


def _close_streams(selector: selectors.BaseSelector, streams: Mapping[str, Any]) -> None:
    for stream in streams.values():
        if stream is None:
            continue
        try:
            selector.unregister(stream)
        except (KeyError, ValueError):
            pass
        stream.close()
    selector.close()


def _decode_bounded_utf8(raw: bytes) -> tuple[str, bool]:
    """Drop incomplete or invalid UTF-8 rather than expanding a byte-capped public value."""
    text = raw.decode("utf-8", errors="ignore")
    return text, len(text.encode("utf-8")) != len(raw)


def _api_url(api_base: str, path: str) -> str:
    base = api_base.rstrip("/")
    return f"{base}{path[4:]}" if base.endswith("/api") and path.startswith("/api/") else f"{base}{path}"


def _http_get(check_id: str, url: str, timeout_s: float, max_bytes: int) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + max(0.0, timeout_s)
    try:
        request = Request(url, method="GET", headers={"Accept": "application/json"})
        connect_remaining = deadline - time.monotonic()
        if connect_remaining <= 0:
            raise TimeoutError("HTTP connect deadline exceeded")
        with urlopen(request, timeout=connect_remaining) as response:
            raw = _read_http_body(response, max_bytes, deadline)
            truncated = len(raw) > max_bytes
            if truncated:
                return _normalized_check(
                    check_id,
                    "warning",
                    latency_ms=(time.monotonic() - started) * 1000,
                    evidence={"http_status": response.status, "output_truncated": True},
                    error_type="output_truncated",
                    error="HTTP 健康检查响应超过上限",
                    repair_hint="retry",
                )
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return _normalized_check(
                    check_id,
                    "failed",
                    latency_ms=(time.monotonic() - started) * 1000,
                    evidence={"http_status": response.status, "output_truncated": False},
                    error_type="invalid_json",
                    error="HTTP 健康检查响应无效",
                    repair_hint="code_candidate",
                )
            if not isinstance(payload, Mapping) or not isinstance(payload.get("status"), str):
                return _normalized_check(
                    check_id,
                    "failed",
                    latency_ms=(time.monotonic() - started) * 1000,
                    evidence={"http_status": response.status, "output_truncated": False},
                    error_type="invalid_schema",
                    error="HTTP 健康检查缺少状态字段",
                    repair_hint="code_candidate",
                )
            raw_status = payload["status"]
            response_status = raw_status if raw_status in {"ok", "warning", "failed", "error", "unavailable"} else "unknown"
            status = "ok" if 200 <= response.status < 300 and response_status == "ok" else "warning"
            return _normalized_check(
                check_id,
                status,
                latency_ms=(time.monotonic() - started) * 1000,
                evidence={
                    "http_status": response.status,
                    "response_status": response_status,
                    "output_truncated": truncated,
                },
                repair_hint="observe" if status == "ok" else "retry",
            )
    except HTTPError as exc:
        return _normalized_check(
            check_id,
            "failed",
            latency_ms=(time.monotonic() - started) * 1000,
            evidence={"http_status": exc.code},
            error_type="http_error",
            error="HTTP 健康检查失败",
            repair_hint="restart_service",
        )
    except (TimeoutError, socket.timeout, URLError) as exc:
        timeout = isinstance(exc, TimeoutError) or "timed out" in str(exc).lower()
        return _normalized_check(
            check_id,
            "timeout" if timeout else "failed",
            latency_ms=(time.monotonic() - started) * 1000,
            error_type="timeout" if timeout else type(exc).__name__,
            error="HTTP 健康检查超时" if timeout else "HTTP 健康检查不可达",
            repair_hint="retry" if timeout else "restart_service",
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _normalized_check(
            check_id,
            "failed",
            latency_ms=(time.monotonic() - started) * 1000,
            error_type=type(exc).__name__,
            error="HTTP 健康检查响应无效",
            repair_hint="code_candidate",
        )


def _read_http_body(response: Any, max_bytes: int, deadline: float) -> bytes:
    """Read no more than max_bytes + 1 while enforcing a monotonic absolute deadline."""
    raw = bytearray()
    while len(raw) <= max_bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTP read deadline exceeded")
        _set_response_timeout(response, remaining)
        try:
            chunk = response.read(1)
        except socket.timeout as exc:
            raise TimeoutError("HTTP read deadline exceeded") from exc
        if not chunk:
            break
        raw.extend(chunk)
    return bytes(raw)


def _set_response_timeout(response: Any, timeout_s: float) -> None:
    """Tighten each socket read to the remaining absolute deadline."""
    socket_object = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
    if socket_object is not None:
        socket_object.settimeout(max(0.001, timeout_s))


def _remaining(deadline: float, per_check_s: float) -> float:
    return min(per_check_s, max(0.0, deadline - time.monotonic()))


def _command_evidence(command: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "exit_code": command.get("exit_code"),
        "output_truncated": bool(command.get("output_truncated")),
    }


def _refresh_low_frequency_check(command: Mapping[str, Any]) -> dict[str, Any]:
    if command.get("status") != "ok":
        return _normalized_check(
            "refresh.low_frequency",
            str(command.get("status", "failed")),
            latency_ms=float(command.get("latency_ms", 0.0)),
            evidence=_command_evidence(command),
            error_type=str(command.get("error_type", "command_failed")),
            error="低频刷新健康诊断未完成",
            repair_hint="refresh_lane",
        )
    try:
        payload = json.loads(str(command.get("stdout", "")))
    except json.JSONDecodeError:
        return _normalized_check(
            "refresh.low_frequency",
            "failed",
            latency_ms=float(command.get("latency_ms", 0.0)),
            evidence=_command_evidence(command),
            error_type="invalid_json",
            error="低频刷新健康诊断格式无效",
            repair_hint="code_candidate",
        )
    if not isinstance(payload, Mapping) or not isinstance(payload.get("capacity"), Mapping):
        return _normalized_check(
            "refresh.low_frequency",
            "failed",
            latency_ms=float(command.get("latency_ms", 0.0)),
            evidence=_command_evidence(command),
            error_type="invalid_schema",
            error="低频刷新健康诊断结构无效",
            repair_hint="code_candidate",
        )
    capacity = payload["capacity"]
    report_status = str(payload.get("status", "failed"))
    status = "warning" if report_status == "warning" else "ok" if report_status == "ok" else "failed"
    return _normalized_check(
        "refresh.low_frequency",
        status,
        latency_ms=float(command.get("latency_ms", 0.0)),
        evidence={
            **_command_evidence(command),
            "low_frequency_due": capacity.get("low_frequency_due", 0),
            "estimated_runs_to_drain": capacity.get("estimated_low_frequency_runs_to_drain", 0),
        },
        repair_hint="refresh_lane" if status != "ok" else "observe",
    )


def _component_check(command: Mapping[str, Any]) -> dict[str, Any]:
    status = str(command.get("status", "failed"))
    if status == "ok":
        try:
            payload = json.loads(str(command.get("stdout", "")))
            status = "warning" if isinstance(payload, Mapping) and str(payload.get("status")) == "warning" else "ok" if isinstance(payload, Mapping) else "failed"
        except json.JSONDecodeError:
            status = "failed"
    return _normalized_check(
        "component.health",
        status,
        latency_ms=float(command.get("latency_ms", 0.0)),
        evidence=_command_evidence(command),
        error_type="" if status == "ok" else str(command.get("error_type") or "health_status"),
        error="" if status == "ok" else "组件数据集健康检查异常",
        repair_hint="observe" if status == "ok" else "refresh_lane",
    )


def collect_probe(repo_root: Path, api_base: str, runtime_root: Path, deadline_s: float) -> dict[str, Any]:
    """Compose existing diagnostics and safe HTTP canaries without performing repair."""
    root = Path(repo_root).resolve()
    artifacts = Path(runtime_root).resolve() / "probe-artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + min(max(0.0, deadline_s), DEFAULT_DEADLINE_S)
    checks: list[dict[str, Any]] = []
    commands = [
        (
            "refresh.health",
            [sys.executable, str(root / "scripts/diagnose_observation_refresh_health.py"), "--format", "json", "--sample", "10"],
            25.0,
        ),
        (
            "component.health",
            [
                sys.executable,
                str(root / "scripts/check_component_dataset_health.py"),
                "--skip-probe",
                "--fail-on",
                "none",
                "--report-dir",
                str(artifacts),
            ],
            25.0,
        ),
    ]
    for check_id, argv, per_check_s in commands:
        remaining = _remaining(deadline, per_check_s)
        if remaining <= 0:
            break
        result = run_command(check_id, argv, remaining, DEFAULT_MAX_BYTES)
        if check_id == "refresh.health":
            checks.append({key: value for key, value in result.items() if key not in {"stdout", "stderr"}})
            checks.append(_refresh_low_frequency_check(result))
        else:
            checks.append(_component_check(result))

    canaries = [
        ("api.health", "/api/health"),
        ("providers.connectivity", "/api/providers/connectivity"),
        ("providers.health", "/api/providers/health"),
        ("data_catalog.series", "/api/data-catalog/series?page=1&pageSize=1"),
        ("component_datasets.health", "/api/component-datasets/health"),
    ]
    for check_id, path in canaries:
        remaining = _remaining(deadline, HTTP_TIMEOUT_S)
        if remaining <= 0:
            break
        checks.append(_http_get(check_id, _api_url(api_base, path), remaining, DEFAULT_MAX_BYTES))
    return sanitize(
        {
            "probe_kind": "read_only",
            "deadline_s": min(max(0.0, deadline_s), DEFAULT_DEADLINE_S),
            "checks": checks,
            "artifact_dir": str(artifacts),
        }
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行只读、限时的 Alpha-FICC 维护探测。")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--runtime-root", type=Path, default=Path("runtime"))
    parser.add_argument("--deadline-s", type=float, default=DEFAULT_DEADLINE_S)
    parser.add_argument("--dry-run", action="store_true", help="仅采集只读证据，绝不执行修复。")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    record = new_run_record(f"probe-{now.strftime('%Y%m%dT%H%M%SZ')}", now)
    probe = collect_probe(args.repo_root, args.api_base, args.runtime_root, args.deadline_s)
    record.update(
        {
            "checks": probe["checks"],
            "final_status": "observed",
            "report_targets": {"discord": {"status": "prepared"}},
            "probe": {"kind": probe["probe_kind"], "dry_run": bool(args.dry_run)},
        }
    )
    safe_record = sanitize(record)
    print(json.dumps({"record": safe_record, "validation_errors": validate_run_record(safe_record)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
