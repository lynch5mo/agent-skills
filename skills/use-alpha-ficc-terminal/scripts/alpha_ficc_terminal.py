#!/usr/bin/env python3
"""Agent-safe helper for the Alpha-FICC terminal API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import zlib
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://alpha-ficc.lynch5mo.xyz/api"
DEFAULT_KB_ROOT = "/Users/lynch5mo/Work Documents/LLM/agent-kb"
CHART_GENERATION_SPEC_SCHEMA_VERSION = "alpha-ficc-chart-generation-spec-v1"
DEFAULT_CHART_WAIT_TIMEOUT = 180.0
CHART_WAIT_BACKOFF_SECONDS = (1.0, 2.0, 3.0, 5.0)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHART_IMAGE_TERMINAL_MODE = "terminalScreenshot"
CHART_IMAGE_CHART_MODE = "chart"
# Self-describing render requests are only honoured for these local endpoints.
ALLOWED_RENDER_REQUEST_ENDPOINTS = {"/api/agent-render-jobs"}

AGENT_ALIASES = {
    "codex": ("codex", "openai", "gpt"),
    "hermes": ("hermes",),
    "claude": ("claude", "cloud", "anthropic"),
    "pi-agent": ("pi-agent", "piagent", "pi"),
    "deepseek-harness": ("deepseek-harness", "deepseekharness", "deepseek", "dsh"),
    "reasonix": ("reasonix",),
}
AGENT_TOKEN_ENV = {
    "codex": "ALPHA_FICC_CODEX_AGENT_TOKEN",
    "hermes": "ALPHA_FICC_HERMES_AGENT_TOKEN",
    "claude": "ALPHA_FICC_CLAUDE_AGENT_TOKEN",
    "pi-agent": "ALPHA_FICC_PI_AGENT_TOKEN",
    "deepseek-harness": "ALPHA_FICC_DEEPSEEK_HARNESS_AGENT_TOKEN",
    "reasonix": "ALPHA_FICC_REASONIX_AGENT_TOKEN",
}


def _project_root() -> Path:
    try:
        return Path(__file__).resolve().parents[3]
    except Exception:
        return Path.cwd()


def _load_env_file() -> None:
    candidates: list[Path] = []
    if os.environ.get("ALPHA_FICC_ENV_FILE"):
        candidates.append(Path(os.environ["ALPHA_FICC_ENV_FILE"]).expanduser())
    candidates.append(_project_root() / ".local" / "alpha-ficc-terminal-agent.env")
    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export "):].strip()
            if "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        break


class TerminalError(RuntimeError):
    pass


class _AgentArgumentParser(argparse.ArgumentParser):
    """Argument parser that surfaces usage errors as structured JSON instead of a bare exit.

    argparse normally prints usage and exits with code 2, which leaves callers with no
    parseable result. Raising TerminalError lets main() emit one final JSON object on
    stdout while argparse still prints the diagnostic to stderr.
    """

    def error(self, message: str):  # pragma: no cover - trivial delegation
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise TerminalError(f"argument error: {message}")


def _normalize_agent_id(agent: str) -> str:
    text = "".join(ch if ch.isalnum() else "-" for ch in str(agent or "").strip().lower()).strip("-")
    if not text:
        return ""
    compact = "".join(ch for ch in text if ch.isalnum())
    for canonical, aliases in AGENT_ALIASES.items():
        if text in aliases or compact in {alias.replace("-", "") for alias in aliases}:
            return canonical
    return text


def _canonical_agent(agent: str) -> str:
    return _normalize_agent_id(agent) or "codex"


def _agent_env_key(agent: str) -> str:
    normalized = _normalize_agent_id(agent)
    if normalized in AGENT_TOKEN_ENV:
        return AGENT_TOKEN_ENV[normalized]
    fallback = "".join(ch if ch.isalnum() else "_" for ch in normalized.upper()).strip("_")
    return f"ALPHA_FICC_{fallback}_AGENT_TOKEN"


def _default_token_paths(agent: str, device_id: str = "") -> list[Path]:
    canonical = _canonical_agent(agent)
    home = Path.home()
    paths: list[Path] = []
    if device_id:
        paths.append(home / ".alpha-ficc" / f"{canonical}.{device_id}.token")
    else:
        device_files = sorted((home / ".alpha-ficc").glob(f"{canonical}.*.token"))
        if len(device_files) == 1:
            paths.append(device_files[0])
    paths.extend([
        home / ".alpha-ficc" / f"{canonical}.token",
        home / ".alpha-ficc" / f"{canonical}-agent.token",
    ])
    return paths


def _device_id(args: argparse.Namespace) -> str:
    return str(
        args.device_id
        or os.environ.get("ALPHA_FICC_DEVICE_ID")
        or ""
    ).strip().lower()


def _base_url(args: argparse.Namespace) -> str:
    value = (
        args.base_url
        or os.environ.get("ALPHA_FICC_API_BASE_URL")
        or os.environ.get("ALPHA_FICC_BASE_URL")
        or DEFAULT_BASE_URL
    )
    return value.rstrip("/")


def _url(base_url: str, endpoint: str) -> str:
    endpoint = "/" + endpoint.lstrip("/")
    if base_url.endswith("/api") and endpoint.startswith("/api/"):
        endpoint = endpoint[len("/api") :]
    return f"{base_url}{endpoint}"


def _read_token(args: argparse.Namespace, *, required: bool) -> str:
    agent = _canonical_agent(args.agent)
    device_id = _device_id(args)
    token = ""
    if args.token_file:
        explicit_path = Path(args.token_file).expanduser()
        if explicit_path.exists():
            token = explicit_path.read_text(encoding="utf-8").strip()
    else:
        for token_path in _default_token_paths(agent, device_id):
            if not token_path.exists():
                continue
            token = token_path.read_text(encoding="utf-8").strip()
            if token:
                break

        if not token:
            token = str(os.environ.get(_agent_env_key(agent), "") or "").strip()

        if not token:
            configured_agent = _normalize_agent_id(os.environ.get("ALPHA_FICC_AGENT_ID", ""))
            legacy_token_file = str(os.environ.get("ALPHA_FICC_TOKEN_FILE", "") or "").strip()
            if legacy_token_file and (not configured_agent or configured_agent == agent):
                legacy_path = Path(legacy_token_file).expanduser()
                if legacy_path.exists():
                    token = legacy_path.read_text(encoding="utf-8").strip()

    if not token:
        token = str(os.environ.get("ALPHA_FICC_AGENT_TOKEN", "") or "").strip()

    if required and not token:
        raise TerminalError(
            "Missing Agent token. Set ALPHA_FICC_<AGENT>_AGENT_TOKEN, "
            "ALPHA_FICC_AGENT_TOKEN, ALPHA_FICC_TOKEN_FILE, or --token-file."
        )
    return token


def _headers(args: argparse.Namespace, *, require_token: bool, json_body: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": (
            f"Alpha-FICC-Agent/{_canonical_agent(args.agent)}"
            f"{('/' + _device_id(args)) if _device_id(args) else ''}"
            " skill/use-alpha-ficc-terminal"
        ),
    }
    token = _read_token(args, required=require_token)
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Alpha-FICC-Agent"] = _canonical_agent(args.agent)
        if _device_id(args):
            headers["X-Alpha-FICC-Device"] = _device_id(args)
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _request_json(
    args: argparse.Namespace,
    method: str,
    endpoint: str,
    *,
    payload: dict[str, Any] | None = None,
    require_token: bool = True,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        _url(_base_url(args), endpoint),
        method=method.upper(),
        data=body,
        headers=_headers(args, require_token=require_token, json_body=payload is not None),
    )
    try:
        with urlopen(req, timeout=args.timeout) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
    except (TimeoutError, socket.timeout) as exc:
        raise TerminalError(f"HTTP request timed out: {method.upper()} {endpoint}") from exc
    except (URLError, OSError) as exc:
        raise TerminalError(f"HTTP request failed: {method.upper()} {endpoint}: {exc}") from exc

    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise TerminalError(f"Non-JSON response from {method.upper()} {endpoint}: {raw[:500]}") from exc
    if not isinstance(parsed, dict):
        raise TerminalError(f"JSON response is not an object from {method.upper()} {endpoint}")
    return status, parsed


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _response_or_error(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    if status >= 400:
        raw_error = payload.get("error")
        error_obj = raw_error if isinstance(raw_error, dict) else {}
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        if not details and isinstance(error_obj.get("details"), dict):
            details = error_obj["details"]
        code = (
            str(payload.get("code") or error_obj.get("code") or "").strip()
            or (str(raw_error).strip() if isinstance(raw_error, str) else "")
        )
        message = str(payload.get("message") or error_obj.get("message") or "").strip()
        response = {
            "ok": False,
            "status": status,
            "error": raw_error or payload,
        }
        if code:
            response["code"] = code
        if message:
            response["message"] = message
        if details:
            response["details"] = details
            required_scope = str(details.get("requiredScope") or "").strip()
            authenticated_agent = str(details.get("authenticatedAgent") or "").strip()
            device_id = str(details.get("deviceId") or "").strip()
            if required_scope:
                response["requiredScope"] = required_scope
            if authenticated_agent:
                response["authenticatedAgent"] = authenticated_agent
            if device_id:
                response["deviceId"] = device_id
        return response
    return payload


def _extract_context(payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else payload
    if not isinstance(context, dict):
        return {}
    return context


def _context_summary(context: dict[str, Any]) -> dict[str, Any]:
    workspace = context.get("workspace") if isinstance(context.get("workspace"), dict) else {}
    selection = context.get("selection") if isinstance(context.get("selection"), dict) else {}
    summary = context.get("chartDataSummary") if isinstance(context.get("chartDataSummary"), dict) else {}
    latest_values = summary.get("latestValues") if isinstance(summary.get("latestValues"), list) else []
    return {
        "ok": True,
        "contextId": context.get("contextId"),
        "scopeKey": context.get("scopeKey"),
        "workspaceId": workspace.get("workspaceId"),
        "panelIds": workspace.get("panelIds") or [],
        "seriesIds": selection.get("seriesIds") or [],
        "formulaIds": selection.get("formulaIds") or [],
        "chartOperations": selection.get("chartOperations") or [],
        "latestValues": latest_values[:12],
        "chartDataRequest": context.get("chartDataRequest") or {},
        "dataAccessPolicy": context.get("dataAccessPolicy") or {},
    }


def cmd_health(args: argparse.Namespace) -> int:
    status, payload = _request_json(args, "GET", "/api/health", require_token=False)
    _print_json(_response_or_error(status, payload))
    return 0 if status < 400 else 1


def _get_current_context(args: argparse.Namespace) -> tuple[int, dict[str, Any], dict[str, Any]]:
    status, payload = _request_json(args, "GET", "/api/comparison/current/context", require_token=True)
    context = _extract_context(payload) if status < 400 else {}
    return status, payload, context


def cmd_context(args: argparse.Namespace) -> int:
    status, payload, context = _get_current_context(args)
    if status >= 400:
        _print_json(_response_or_error(status, payload))
        return 1
    _print_json(payload if args.raw else _context_summary(context))
    return 0


def _chart_data_endpoint_from_context(context: dict[str, Any]) -> str:
    request = context.get("chartDataRequest") if isinstance(context.get("chartDataRequest"), dict) else {}
    endpoint = str(request.get("endpoint") or "/api/comparison/current/chart-data").strip()
    query = {
        "series": request.get("series") or ",".join(request.get("seriesIds") or []),
        "formulas": request.get("formulas") or ",".join(request.get("formulaIds") or []),
        "window": request.get("window") or "1Y",
        "granularity": request.get("granularity") or "D",
        "limit": request.get("limit") or "",
        "localFirst": "true",
        "dataPolicy": "agent-local-first",
    }
    query = {key: value for key, value in query.items() if value not in (None, "")}
    separator = "&" if "?" in endpoint else "?"
    return f"{endpoint}{separator}{urlencode(query, doseq=False)}"


def _chart_data_summary(payload: dict[str, Any]) -> dict[str, Any]:
    series = payload.get("series") if isinstance(payload.get("series"), list) else []
    skipped = payload.get("skippedSeries") if isinstance(payload.get("skippedSeries"), list) else []
    latest_values = []
    point_count = 0
    for item in series:
        if not isinstance(item, dict):
            continue
        points = item.get("points") if isinstance(item.get("points"), list) else []
        point_count += len(points)
        latest = points[-1] if points else None
        latest_values.append({
            "id": item.get("id") or item.get("seriesId"),
            "label": item.get("label"),
            "pointCount": len(points),
            "latest": latest,
        })
    return {
        "ok": True,
        "source": payload.get("source"),
        "seriesCount": len(series),
        "pointCount": point_count,
        "skippedCount": len(skipped),
        "skippedSeries": skipped[:20],
        "latestValues": latest_values[:12],
        "notes": payload.get("notes") or [],
        "warnings": payload.get("warnings") or [],
        "meta": payload.get("meta") or {},
    }


def cmd_chart_data(args: argparse.Namespace) -> int:
    status, context_payload, context = _get_current_context(args)
    if status >= 400:
        _print_json(_response_or_error(status, context_payload))
        return 1
    endpoint = _chart_data_endpoint_from_context(context)
    data_status, data_payload = _request_json(args, "GET", endpoint, require_token=False)
    if data_status >= 400:
        _print_json(_response_or_error(data_status, data_payload))
        return 1
    _print_json(data_payload if args.raw else _chart_data_summary(data_payload))
    return 0


def _split_csv_and_args(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            cleaned = part.strip()
            if cleaned:
                result.append(cleaned)
    return result


def _default_action_id(agent: str, prefix: str) -> str:
    return f"{agent}_{prefix}_{time.strftime('%Y%m%d_%H%M%S')}"


def cmd_enqueue_series(args: argparse.Namespace) -> int:
    action_id = args.action_id or _default_action_id(args.agent, "chart")
    source = args.source or f"external-{args.agent}"
    target_page_instance_id = str(args.page_instance_id or "").strip()
    target_workspace_id = ""
    if args.target_current_page:
        status, payload, context = _get_current_context(args)
        if status >= 400:
            _print_json(_response_or_error(status, payload))
            return 1
        page_instance = context.get("pageInstance") if isinstance(context.get("pageInstance"), dict) else {}
        workspace = context.get("workspace") if isinstance(context.get("workspace"), dict) else {}
        target_page_instance_id = str(
            page_instance.get("pageInstanceId")
            or workspace.get("pageInstanceId")
            or ""
        ).strip()
        target_workspace_id = str(workspace.get("workspaceId") or "").strip()
        if not target_page_instance_id:
            _print_json({
                "ok": False,
                "error": "TARGET_PAGE_INSTANCE_NOT_FOUND",
                "message": "Current comparison context did not include pageInstanceId.",
            })
            return 1
        pages_status, pages_payload = _request_json(
            args,
            "GET",
            "/api/comparison/page-instances?activeWithinSeconds=300&limit=100",
            require_token=True,
        )
        if pages_status >= 400:
            _print_json(_response_or_error(pages_status, pages_payload))
            return 1
        active_page_ids = {
            str(item.get("pageInstanceId") or "").strip()
            for item in (pages_payload.get("items") or [])
            if isinstance(item, dict)
        }
        if target_page_instance_id not in active_page_ids:
            _print_json({
                "ok": False,
                "error": "TARGET_PAGE_NOT_ACTIVE",
                "message": (
                    "Current comparison context is stale and no recent page heartbeat is active. "
                    "Refresh /comparison before targeting the current page."
                ),
                "pageInstanceId": target_page_instance_id,
            })
            return 1
    target: dict[str, Any] = {
        "seriesIds": _split_csv_and_args(args.series),
        "formulaIds": _split_csv_and_args(args.formulas),
        "window": args.window,
        "granularity": args.granularity,
    }
    if target_page_instance_id:
        target["pageInstanceId"] = target_page_instance_id
    if target_workspace_id:
        target["workspaceId"] = target_workspace_id
    if args.panel_mode:
        target["panelMode"] = args.panel_mode
    if args.panel_title:
        target["panelTitle"] = args.panel_title
    if args.panel_kind:
        target["panelKind"] = args.panel_kind
    payload = {
        "actionId": action_id,
        "actionType": "add_series_to_chart",
        "source": source,
        "note": args.note or "",
        "target": target,
    }
    status, response = _request_json(args, "POST", "/api/terminal-chart-actions", payload=payload, require_token=True)
    safe_summary = {
        "ok": status < 400 and bool(response.get("ok", True)),
        "status": status,
        "endpoint": "POST /api/terminal-chart-actions",
        "actionId": action_id,
        "actionType": "add_series_to_chart",
        "source": source,
        "target": target,
        "targetedPageInstanceId": target_page_instance_id,
        "targetedWorkspaceId": target_workspace_id,
        "pendingCount": response.get("pendingCount"),
        "authenticatedAgent": response.get("authenticatedAgent"),
        "ledgerEndpoint": f"/api/agent-actions/{action_id}",
        "rawError": response.get("error") if status >= 400 else None,
    }
    if status >= 400:
        safe_summary.update(_response_or_error(status, response))
    _print_json(safe_summary)
    return 0 if status < 400 and response.get("ok", True) is not False else 1


def _read_payload(path: str) -> dict[str, Any]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TerminalError("Payload JSON must be an object.")
    return payload


# ── chart-image: generate or fetch a real chart image ────────────────────────


def _new_job_id(agent: str) -> str:
    stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    canonical = "".join(ch if ch.isalnum() else "-" for ch in _canonical_agent(agent))
    return f"agent_render_{canonical}_{stamp}_{secrets.token_hex(4)}"


def _chart_image_failure(
    *,
    stage: str,
    error_code: str,
    message: str,
    recoverable: bool,
    started: float,
    job_id: str = "",
    last_job_status: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "ok": False,
        "stage": stage,
        "errorCode": error_code,
        "message": message,
        "recoverable": bool(recoverable),
        "jobId": job_id or None,
        "lastJobStatus": last_job_status or None,
        "imageDelivery": "not_attempted",
        "elapsedMs": int((time.monotonic() - started) * 1000),
    }
    if extra:
        result.update(extra)
    return result


def _chart_image_sources(args: argparse.Namespace) -> list[str]:
    sources: list[str] = []
    if args.from_context or args.context or args.page_instance:
        sources.append("context")
    if _split_csv_and_args(args.series) or _split_csv_and_args(args.formulas):
        sources.append("series")
    if args.workspace_file:
        sources.append("workspace")
    if args.job:
        sources.append("job")
    return sources


def _read_workspace_source(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).expanduser().read_text(encoding="utf-8")
    document = json.loads(text)
    if not isinstance(document, dict):
        raise TerminalError("workspace file must contain a JSON object.")
    return document


def _build_generation_spec(
    document: dict[str, Any],
    *,
    window: str = "",
    granularity: str = "",
) -> dict[str, Any]:
    """Normalize a workspace file into a ChartGenerationSpec wrapper.

    A spec document is used as given (its own window/granularity win). A raw workspace
    document is wrapped, and only unspecified scope falls back to the request defaults.
    """

    nested = document.get("chartGenerationSpec") or document.get("generationSpec")
    if isinstance(nested, dict):
        candidate = nested
    else:
        candidate = document

    declared_schema = str(candidate.get("schemaVersion") or candidate.get("schema_version") or "").strip()
    if declared_schema and declared_schema != CHART_GENERATION_SPEC_SCHEMA_VERSION:
        raise TerminalError(f"unsupported chart generation spec schemaVersion: {declared_schema}")

    workspace = candidate.get("workspace") if isinstance(candidate.get("workspace"), dict) else None
    if workspace is None and (isinstance(candidate.get("objects"), list) or isinstance(candidate.get("panels"), list)):
        workspace = candidate
        candidate = {}
    if not isinstance(workspace, dict) or not workspace:
        raise TerminalError("workspace file must contain a workspace object with panels/objects.")

    spec: dict[str, Any] = {
        "schemaVersion": CHART_GENERATION_SPEC_SCHEMA_VERSION,
        "workspace": workspace,
    }
    title = str(candidate.get("title") or document.get("title") or "").strip()
    if title:
        spec["title"] = title
    spec_window = str(candidate.get("window") or window or "").strip()
    spec_granularity = str(candidate.get("granularity") or granularity or "").strip()
    if spec_window:
        spec["window"] = spec_window
    if spec_granularity:
        spec["granularity"] = spec_granularity
    for key in ("chartData", "frozenChartData", "renderSnapshotRef"):
        if candidate.get(key) is not None:
            spec[key] = candidate[key]
    return spec


def _png_facts_from_bytes(raw: bytes) -> dict[str, Any] | None:
    """Validate a downloaded PNG with the standard library only.

    Signature and dimensions are not enough: every chunk CRC, the presence of image data,
    the zlib stream and the exact scanline size are checked so a corrupt or placeholder
    file cannot be reported as a valid delivery.
    """

    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 8 + 25:
        return None
    raw = bytes(raw)
    if not raw.startswith(PNG_SIGNATURE):
        return None

    offset = 8
    width = height = None
    bit_depth = color_type = None
    idat = bytearray()
    saw_iend = False
    chunk_index = 0
    legal_bit_depths = {
        0: (1, 2, 4, 8, 16),
        2: (8, 16),
        3: (1, 2, 4, 8),
        4: (8, 16),
        6: (8, 16),
    }
    while offset + 8 <= len(raw):
        length = int.from_bytes(raw[offset:offset + 4], "big")
        chunk_type = raw[offset + 4:offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        if data_end + 4 > len(raw):
            return None
        data = raw[data_start:data_end]
        stored_crc = int.from_bytes(raw[data_end:data_end + 4], "big")
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != stored_crc:
            return None
        if chunk_type == b"IHDR":
            # IHDR must be the first chunk and appear exactly once.
            if chunk_index != 0 or length != 13 or width is not None:
                return None
            width = int.from_bytes(data[0:4], "big")
            height = int.from_bytes(data[4:8], "big")
            bit_depth = data[8]
            color_type = data[9]
            if data[10] != 0 or data[11] != 0 or data[12] != 0:
                return None
            if width <= 0 or height <= 0:
                return None
            if bit_depth not in legal_bit_depths.get(color_type, ()):  # legal depth/type pair
                return None
        elif chunk_type == b"IDAT":
            idat.extend(data)
        elif chunk_type == b"IEND":
            # IEND is empty and ends the file; trailing bytes are not part of the image.
            if length != 0 or data_end + 4 != len(raw):
                return None
            saw_iend = True
            break
        chunk_index += 1
        offset = data_end + 4

    if not saw_iend or width is None or height is None or not idat:
        return None
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    try:
        decompressed = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    row_bytes = (width * channels * bit_depth + 7) // 8
    if len(decompressed) != height * (row_bytes + 1):
        return None
    for row in range(height):
        if decompressed[row * (row_bytes + 1)] > 4:
            return None
    return {
        "mediaType": "image/png",
        "byteSize": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "width": width,
        "height": height,
    }


def _download_artifact_bytes(args: argparse.Namespace, url: str) -> tuple[int, bytes, str]:
    headers = {
        **_headers(args, require_token=True),
        "Accept": "image/png,application/octet-stream;q=0.9",
    }
    req = Request(_url(_base_url(args), url), method="GET", headers=headers)
    try:
        with urlopen(req, timeout=args.timeout) as response:
            return int(getattr(response, "status", 200)), response.read(), str(response.headers.get("Content-Type") or "")
    except HTTPError as exc:
        return int(exc.code), exc.read(), str(exc.headers.get("Content-Type") or "")
    except (TimeoutError, socket.timeout) as exc:
        raise TerminalError(f"artifact download timed out: {url}") from exc
    except (URLError, OSError) as exc:
        raise TerminalError(f"artifact download failed: {url}: {exc}") from exc


def _write_bytes_atomically(target: Path, raw: bytes) -> None:
    """Write via a same-directory temp file so an existing delivery is never corrupted."""

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f".{target.name}.{secrets.token_hex(6)}.tmp")
    try:
        with open(tmp_path, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _chart_image_job_from_response(response: dict[str, Any]) -> dict[str, Any]:
    job = response.get("job")
    return job if isinstance(job, dict) else response


def _is_chart_image_failure(value: Any) -> bool:
    """A structured failure carries ok=false plus an errorCode; job records carry neither."""

    return isinstance(value, dict) and value.get("ok") is False and "errorCode" in value


def _chart_image_result_from_error(status: int, payload: dict[str, Any], *, stage: str, started: float, job_id: str) -> dict[str, Any]:
    normalized = _response_or_error(status, payload)
    return _chart_image_failure(
        stage=stage,
        error_code=str(normalized.get("code") or "RENDER_REQUEST_REJECTED"),
        message=str(normalized.get("message") or f"render request rejected with HTTP {status}"),
        recoverable=status >= 500,
        started=started,
        job_id=job_id,
        extra={"status": status},
    )


def cmd_chart_image(args: argparse.Namespace) -> int:
    started = time.monotonic()
    # Global --timeout stays the compatibility default; chart-image can narrow it per request.
    args.timeout = int(args.http_timeout or args.timeout)
    wait_timeout = (
        DEFAULT_CHART_WAIT_TIMEOUT
        if args.wait_timeout is None
        else max(0.0, float(args.wait_timeout))
    )

    result = _run_chart_image(args, started=started, wait_timeout=wait_timeout)
    _print_json(result)
    return 0 if result.get("ok") else 1


def _run_chart_image(args: argparse.Namespace, *, started: float, wait_timeout: float) -> dict[str, Any]:
    sources = _chart_image_sources(args)
    if not sources:
        # Default entry is the current chart; task 2 implements full snapshot replay.
        sources = ["context"]
    if len(sources) > 1:
        return _chart_image_failure(
            stage="cli",
            error_code="SOURCE_CONFLICT",
            message=f"chart-image sources are mutually exclusive, got: {', '.join(sources)}",
            recoverable=False,
            started=started,
        )
    source = sources[0]

    if args.job and (args.window or args.granularity):
        return _chart_image_failure(
            stage="cli",
            error_code="SOURCE_CONFLICT",
            message="--job cannot be combined with --window or --granularity.",
            recoverable=False,
            started=started,
            job_id=args.job,
        )
    if args.panel and source != "context":
        return _chart_image_failure(
            stage="cli",
            error_code="SOURCE_CONFLICT",
            message="--panel only applies to the current-chart source; generated charts use the spec workspace.",
            recoverable=False,
            started=started,
        )

    request_mode = CHART_IMAGE_CHART_MODE if (args.mode or "terminal") == "chart" else CHART_IMAGE_TERMINAL_MODE
    job_id = str(args.job or args.job_id or _new_job_id(args.agent)).strip()

    if source == "job":
        job = _fetch_job(args, job_id, started=started)
        if _is_chart_image_failure(job):
            return job
        job_record = job
        request_mode = str(job_record.get("renderMode") or request_mode)
    else:
        body_result = _build_chart_image_request(
            args,
            source=source,
            job_id=job_id,
            request_mode=request_mode,
            started=started,
        )
        if _is_chart_image_failure(body_result):
            return body_result
        endpoint, body = body_result
        created = _post_render_job(args, endpoint=endpoint, body=body, job_id=job_id, started=started)
        if _is_chart_image_failure(created):
            return created
        job_record = created

    waited = _wait_for_job(args, job_record, job_id=job_id, started=started, wait_timeout=wait_timeout)
    if waited.get("ok") is False:
        return waited
    job_record = waited["job"]

    fidelity = str(job_record.get("fidelity") or "")
    used_fallback = bool(job_record.get("usedFallback"))
    allow_simplified = bool(args.allow_fallback) or request_mode == CHART_IMAGE_CHART_MODE
    if request_mode == CHART_IMAGE_TERMINAL_MODE and fidelity != "terminal" and not allow_simplified:
        return _chart_image_failure(
            stage="render",
            error_code="REQUIRED_FIDELITY_UNAVAILABLE",
            message=(
                "Terminal chart image export is unavailable for this job; the only valid artifact is a "
                "simplified chart. Re-run with --allow-fallback or --mode chart to accept it."
            ),
            recoverable=True,
            started=started,
            job_id=job_id,
            last_job_status=str(job_record.get("status") or ""),
            extra={"fidelity": fidelity or None, "usedFallback": used_fallback},
        )

    artifact_url = str(job_record.get("artifactUrl") or "")
    if not job_record.get("artifactReady") or not artifact_url:
        return _chart_image_failure(
            stage="render",
            error_code="ARTIFACT_NOT_READY",
            message="The render job finished without a valid PNG artifact.",
            recoverable=True,
            started=started,
            job_id=job_id,
            last_job_status=str(job_record.get("status") or ""),
        )

    output_path = Path(args.out).expanduser() if args.out else Path.cwd() / f"{job_id}.png"
    if output_path.exists() and not args.overwrite:
        return _chart_image_failure(
            stage="output",
            error_code="OUTPUT_EXISTS",
            message=f"Target file already exists: {output_path}. Pass --overwrite to replace it.",
            recoverable=True,
            started=started,
            job_id=job_id,
        )

    expected = {}
    metadata = job_record.get("artifactMetadata")
    if isinstance(metadata, dict) and isinstance(metadata.get(fidelity), dict):
        expected = metadata[fidelity]

    try:
        status, raw, content_type = _download_artifact_bytes(args, artifact_url)
    except TerminalError as exc:
        return _chart_image_failure(
            stage="download",
            error_code="ARTIFACT_DOWNLOAD_FAILED",
            message=str(exc),
            recoverable=True,
            started=started,
            job_id=job_id,
        )
    if status >= 400:
        return _chart_image_failure(
            stage="download",
            error_code="ARTIFACT_DOWNLOAD_FAILED",
            message=f"artifact download returned HTTP {status}",
            recoverable=status >= 500,
            started=started,
            job_id=job_id,
            extra={"status": status},
        )

    facts = _png_facts_from_bytes(raw)
    if not facts:
        return _chart_image_failure(
            stage="download",
            error_code="ARTIFACT_INVALID",
            message="Downloaded artifact is not a valid PNG image.",
            recoverable=True,
            started=started,
            job_id=job_id,
            extra={"contentType": content_type or None},
        )
    metadata_matched: bool | None = None
    if expected:
        expected_bytes = expected.get("byteSize")
        expected_sha = str(expected.get("sha256") or "")
        metadata_matched = True
        if isinstance(expected_bytes, int) and expected_bytes != facts["byteSize"]:
            metadata_matched = False
        if expected_sha and expected_sha != facts["sha256"]:
            metadata_matched = False
        if not metadata_matched:
            return _chart_image_failure(
                stage="download",
                error_code="ARTIFACT_INVALID",
                message="Downloaded PNG does not match the artifact metadata for this job.",
                recoverable=True,
                started=started,
                job_id=job_id,
                extra={"verification": {**facts, "metadataMatched": False}},
            )

    try:
        _write_bytes_atomically(output_path, raw)
    except OSError as exc:
        return _chart_image_failure(
            stage="output",
            error_code="OUTPUT_WRITE_FAILED",
            message=f"Could not write {output_path}: {exc}",
            recoverable=True,
            started=started,
            job_id=job_id,
        )

    warnings: list[str] = []
    if request_mode == CHART_IMAGE_TERMINAL_MODE and fidelity != "terminal":
        warnings.append(
            "SIMPLIFIED_FALLBACK: terminal chart image export unavailable; delivered simplified chart, "
            "layout/annotation fidelity is lower."
        )

    return {
        "ok": True,
        "jobId": job_id,
        "artifactRef": job_record.get("artifactRef"),
        "status": job_record.get("status"),
        "requestMode": request_mode,
        "fidelity": fidelity or None,
        "viewConsistency": job_record.get("viewConsistency"),
        "usedFallback": used_fallback,
        "artifactUrl": artifact_url,
        "localPath": str(output_path.resolve()),
        "verification": {**facts, "metadataMatched": metadata_matched},
        "sourceSnapshot": job_record.get("sourceSnapshot"),
        "chartSummary": job_record.get("chartSummary"),
        "warnings": warnings,
        "delivery": {"notify": False},
        "imageDelivery": "not_attempted",
        "elapsedMs": int((time.monotonic() - started) * 1000),
    }


def _context_page_instance_id(context: dict[str, Any]) -> str:
    page_instance = context.get("pageInstance") if isinstance(context.get("pageInstance"), dict) else {}
    workspace = context.get("workspace") if isinstance(context.get("workspace"), dict) else {}
    return str(
        page_instance.get("pageInstanceId")
        or workspace.get("pageInstanceId")
        or ""
    ).strip()


def _render_request_from_context(
    context: dict[str, Any],
    *,
    args: argparse.Namespace,
    started: float,
    job_id: str,
) -> Any:
    """Validate the context's self-describing render request and build the job target."""

    render_request = context.get("renderRequest") if isinstance(context.get("renderRequest"), dict) else {}
    target = render_request.get("target") if isinstance(render_request.get("target"), dict) else {}
    snapshot_ref = str(
        context.get("renderSnapshotRef") or target.get("renderSnapshotRef") or ""
    ).strip()
    availability = context.get("renderAvailability") if isinstance(context.get("renderAvailability"), dict) else {}
    if not render_request or not target or not snapshot_ref or availability.get("renderable") is False:
        return _chart_image_failure(
            stage="source",
            error_code="CONTEXT_RENDER_NOT_AVAILABLE",
            message=(
                "The current chart context does not expose a complete, renderable snapshot "
                f"(reasons={availability.get('reasons') or ['NO_SNAPSHOT']}). Generate explicitly with "
                "--series, --formulas or --workspace-file."
            ),
            recoverable=True,
            started=started,
            job_id=job_id,
            extra={
                "contextId": context.get("contextId") or None,
                "renderAvailability": availability or None,
            },
        )

    endpoint = str(render_request.get("endpoint") or "").strip()
    method = str(render_request.get("method") or "POST").strip().upper()
    if (
        method != "POST"
        or not endpoint.startswith("/api/")
        or endpoint not in ALLOWED_RENDER_REQUEST_ENDPOINTS
    ):
        # Never follow an arbitrary URL from a server-provided request.
        return _chart_image_failure(
            stage="source",
            error_code="RENDER_REQUEST_ENDPOINT_NOT_ALLOWED",
            message=f"Refusing a render request for endpoint {endpoint or '(empty)'} (method {method}).",
            recoverable=False,
            started=started,
            job_id=job_id,
            extra={"endpoint": endpoint or None},
        )

    panel_id = str(args.panel or "").strip()
    available_panels = [
        str(panel) for panel in (availability.get("panelIds") or []) if str(panel or "").strip()
    ]
    if panel_id and available_panels and panel_id not in available_panels:
        return _chart_image_failure(
            stage="source",
            error_code="PANEL_NOT_FOUND",
            message=f"Panel {panel_id} is not part of the current chart snapshot.",
            recoverable=False,
            started=started,
            job_id=job_id,
            extra={"panelId": panel_id, "panelIds": available_panels},
        )

    merged_target = {
        key: value
        for key, value in target.items()
        if value not in (None, "")
    }
    merged_target["renderSnapshotRef"] = snapshot_ref
    if panel_id:
        merged_target["panelId"] = panel_id
    return endpoint, merged_target


def _resolve_current_chart_source(args: argparse.Namespace, *, started: float, job_id: str) -> Any:
    """Resolve the current-chart source into (endpoint, target) without guessing."""

    page_instance_id = str(args.page_instance or "").strip()
    context_id = str(args.context or "").strip()

    if context_id:
        status, payload = _request_json(
            args,
            "GET",
            f"/api/agent-visible-chart-contexts/{context_id}",
            require_token=True,
        )
        if status == 404:
            return _chart_image_failure(
                stage="source",
                error_code="CONTEXT_NOT_VISIBLE",
                message=f"Context {context_id} was not found or is not visible to this Agent.",
                recoverable=False,
                started=started,
                job_id=job_id,
                extra={"contextId": context_id},
            )
        if status >= 400:
            return _chart_image_result_from_error(status, payload, stage="source", started=started, job_id=job_id)
        context = payload.get("context") if isinstance(payload.get("context"), dict) else payload
        if page_instance_id and _context_page_instance_id(context) != page_instance_id:
            return _chart_image_failure(
                stage="source",
                error_code="CONTEXT_PAGE_MISMATCH",
                message="--context and --page-instance refer to different comparison pages.",
                recoverable=False,
                started=started,
                job_id=job_id,
                extra={
                    "contextId": context_id,
                    "contextPageInstanceId": _context_page_instance_id(context) or None,
                    "requestedPageInstanceId": page_instance_id,
                },
            )
        return _render_request_from_context(context, args=args, started=started, job_id=job_id)

    if page_instance_id:
        status, payload = _request_json(
            args,
            "GET",
            "/api/comparison/page-instances?activeWithinSeconds=300&limit=100",
            require_token=True,
        )
        if status >= 400:
            return _chart_image_result_from_error(status, payload, stage="source", started=started, job_id=job_id)
        items = [
            item for item in (payload.get("items") if isinstance(payload.get("items"), list) else [])
            if isinstance(item, dict) and str(item.get("pageInstanceId") or "").strip() == page_instance_id
        ]
        if not items:
            return _chart_image_failure(
                stage="source",
                error_code="CONTEXT_PAGE_NOT_FOUND",
                message=(
                    f"No active comparison page {page_instance_id} with a snapshot. "
                    "Refresh /comparison on that page first."
                ),
                recoverable=True,
                started=started,
                job_id=job_id,
                extra={"pageInstanceId": page_instance_id},
            )
        entry = items[0]
        context = {
            "contextId": entry.get("contextId"),
            "pageInstance": {"pageInstanceId": entry.get("pageInstanceId"), "label": entry.get("label")},
            "renderSnapshotRef": entry.get("renderSnapshotRef"),
            "renderAvailability": entry.get("renderAvailability"),
            "renderRequest": entry.get("renderRequest"),
        }
        return _render_request_from_context(context, args=args, started=started, job_id=job_id)

    status, payload = _request_json(
        args,
        "GET",
        "/api/comparison/current/context",
        require_token=True,
    )
    if status == 404:
        return _chart_image_failure(
            stage="source",
            error_code="CONTEXT_UNAVAILABLE",
            message="No current /comparison context is available; generate explicitly with --series.",
            recoverable=True,
            started=started,
            job_id=job_id,
        )
    if status >= 400:
        return _chart_image_result_from_error(status, payload, stage="source", started=started, job_id=job_id)
    context = _extract_context(payload)

    pages_status, pages_payload = _request_json(
        args,
        "GET",
        "/api/comparison/page-instances?activeWithinSeconds=300&limit=100",
        require_token=True,
    )
    active_pages = [
        str(item.get("pageInstanceId") or "").strip()
        for item in (pages_payload.get("items") if isinstance(pages_payload.get("items"), list) else [])
        if isinstance(item, dict) and str(item.get("pageInstanceId") or "").strip()
    ] if pages_status < 400 else []
    if len(active_pages) > 1:
        return _chart_image_failure(
            stage="source",
            error_code="CONTEXT_AMBIGUOUS",
            message=(
                f"{len(active_pages)} active comparison pages publish to this scope; "
                "specify --page-instance or --context instead of guessing."
            ),
            recoverable=True,
            started=started,
            job_id=job_id,
            extra={"activePageInstanceIds": active_pages},
        )
    return _render_request_from_context(context, args=args, started=started, job_id=job_id)


def _fetch_job(args: argparse.Namespace, job_id: str, *, started: float) -> dict[str, Any]:
    try:
        status, payload = _request_json(args, "GET", f"/api/agent-render-jobs/{job_id}", require_token=True)
    except TerminalError as exc:
        return _chart_image_failure(
            stage="lookup",
            error_code="JOB_LOOKUP_FAILED",
            message=str(exc),
            recoverable=True,
            started=started,
            job_id=job_id,
        )
    if status == 404:
        return _chart_image_failure(
            stage="lookup",
            error_code="JOB_NOT_FOUND",
            message=f"No render job found for jobId {job_id}.",
            recoverable=False,
            started=started,
            job_id=job_id,
        )
    if status >= 400:
        return _chart_image_result_from_error(status, payload, stage="lookup", started=started, job_id=job_id)
    return _chart_image_job_from_response(payload)


def _build_chart_image_request(
    args: argparse.Namespace,
    *,
    source: str,
    job_id: str,
    request_mode: str,
    started: float,
) -> Any:
    body: dict[str, Any] = {
        "jobId": job_id,
        "source": f"external-{_canonical_agent(args.agent)}",
        "renderMode": request_mode,
        "delivery": {"channel": "artifactOnly", "notify": False},
        # New generation calls demand complete data: no silently trimmed charts and no
        # silent window/granularity rewriting. Legacy callers keep the old defaults.
        "strictData": True,
    }

    if source == "context":
        if args.window or args.granularity:
            return _chart_image_failure(
                stage="cli",
                error_code="SOURCE_CONFLICT",
                message="--window/--granularity cannot override a current-chart snapshot.",
                recoverable=False,
                started=started,
                job_id=job_id,
            )
        resolution = _resolve_current_chart_source(args, started=started, job_id=job_id)
        if _is_chart_image_failure(resolution):
            return resolution
        endpoint, target = resolution
        body["target"] = target
        body["renderSnapshotRef"] = target.get("renderSnapshotRef")
        return endpoint, body

    if source == "series":
        series_ids = _split_csv_and_args(args.series)
        formula_ids = _split_csv_and_args(args.formulas)
        if not series_ids and not formula_ids:
            return _chart_image_failure(
                stage="cli",
                error_code="NO_SOURCE",
                message="Provide at least one --series or --formulas identifier.",
                recoverable=False,
                started=started,
                job_id=job_id,
            )
        body["target"] = {
            "seriesIds": series_ids,
            "formulaIds": formula_ids,
            "window": args.window or "3Y",
            "granularity": args.granularity or "D",
        }
        return "/api/agent-render-jobs", body

    if source == "workspace":
        try:
            document = _read_workspace_source(args.workspace_file)
            spec = _build_generation_spec(document, window=args.window, granularity=args.granularity)
        except TerminalError as exc:
            return _chart_image_failure(
                stage="source",
                error_code="INVALID_WORKSPACE_FILE",
                message=str(exc),
                recoverable=False,
                started=started,
                job_id=job_id,
            )
        except (OSError, json.JSONDecodeError) as exc:
            return _chart_image_failure(
                stage="source",
                error_code="INVALID_WORKSPACE_FILE",
                message=f"Could not read workspace file: {exc}",
                recoverable=False,
                started=started,
                job_id=job_id,
            )
        body["chartGenerationSpec"] = spec
        return "/api/agent-render-jobs", body

    return _chart_image_failure(
        stage="cli",
        error_code="NO_SOURCE",
        message="No chart-image source was resolved.",
        recoverable=False,
        started=started,
        job_id=job_id,
    )


def _post_render_job(
    args: argparse.Namespace,
    *,
    endpoint: str,
    body: dict[str, Any],
    job_id: str,
    started: float,
) -> dict[str, Any]:
    try:
        status, response = _request_json(args, "POST", endpoint, payload=body, require_token=True)
    except TerminalError as exc:
        # Unclear network outcome: fall back to polling the known jobId instead of guessing.
        print(f"chart-image: POST {endpoint} did not return cleanly ({exc}); polling jobId {job_id}", file=sys.stderr)
        fetched = _fetch_job(args, job_id, started=started)
        if isinstance(fetched, dict) and fetched.get("ok") is False and fetched.get("errorCode") == "JOB_NOT_FOUND":
            return _chart_image_failure(
                stage="create",
                error_code="CREATE_OUTCOME_UNKNOWN",
                message=(
                    "Render POST timed out and the jobId is not known to the server; "
                    "retry with the same jobId once the server is reachable."
                ),
                recoverable=True,
                started=started,
                job_id=job_id,
            )
        return fetched
    if status >= 400:
        return _chart_image_result_from_error(status, response, stage="create", started=started, job_id=job_id)
    return _chart_image_job_from_response(response)


def _wait_for_job(
    args: argparse.Namespace,
    job_record: dict[str, Any],
    *,
    job_id: str,
    started: float,
    wait_timeout: float,
) -> dict[str, Any]:
    status_name = str(job_record.get("status") or "")
    attempts = 0
    while True:
        if status_name in {"rendered", "sent", "send_failed"}:
            return {"ok": True, "job": job_record}
        if status_name in {"render_failed", "cancelled"}:
            error = job_record.get("error") if isinstance(job_record.get("error"), dict) else {}
            return _chart_image_failure(
                stage="render",
                error_code=str(error.get("code") or "RENDER_FAILED"),
                message=str(error.get("message") or f"Render job ended as {status_name}."),
                recoverable=True,
                started=started,
                job_id=job_id,
                last_job_status=status_name,
            )
        if time.monotonic() - started >= wait_timeout:
            return _chart_image_failure(
                stage="wait",
                error_code="JOB_WAIT_TIMEOUT",
                message=(
                    f"Job did not reach a terminal state within {int(wait_timeout)}s. "
                    f"Continue later with --job {job_id}."
                ),
                recoverable=True,
                started=started,
                job_id=job_id,
                last_job_status=status_name,
            )
        delay = CHART_WAIT_BACKOFF_SECONDS[min(attempts, len(CHART_WAIT_BACKOFF_SECONDS) - 1)]
        attempts += 1
        time.sleep(delay)
        fetched = _fetch_job(args, job_id, started=started)
        if _is_chart_image_failure(fetched):
            return fetched
        job_record = fetched
        status_name = str(job_record.get("status") or status_name)


def cmd_action(args: argparse.Namespace) -> int:
    status, payload = _request_json(args, "GET", f"/api/agent-actions/{args.action_id}", require_token=True)
    _print_json(_response_or_error(status, payload))
    return 0 if status < 400 else 1


def cmd_get(args: argparse.Namespace) -> int:
    status, payload = _request_json(args, "GET", args.endpoint, require_token=args.auth)
    _print_json(_response_or_error(status, payload))
    return 0 if status < 400 else 1


def cmd_post(args: argparse.Namespace) -> int:
    payload = _read_payload(args.payload)
    status, response = _request_json(args, "POST", args.endpoint, payload=payload, require_token=True)
    _print_json(_response_or_error(status, response))
    return 0 if status < 400 else 1


def _kb_root(args: argparse.Namespace) -> Path:
    root = Path(args.kb_root or os.environ.get("ALPHA_FICC_AGENT_KB_ROOT") or DEFAULT_KB_ROOT).expanduser()
    try:
        return root.resolve()
    except Exception:
        return root


def _run_git(args: list[str], *, cwd: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=8,
            check=False,
        )
    except Exception as exc:
        return 1, str(exc)
    return int(result.returncode), (result.stdout or "").strip()


def _kb_layer(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return "outside"
    parts = rel.parts
    if not parts:
        return "root"
    if parts[0] in {"raw", "wiki", "write", "outputs"}:
        if parts[0] == "wiki":
            return "/".join(parts[: min(len(parts), 3)])
        return "/".join(parts[: min(len(parts), 2)])
    return parts[0]


def _kb_layer_bonus(relative_path: str) -> int:
    if relative_path.startswith("wiki/summaries/"):
        return 100
    if relative_path.startswith("wiki/concepts/"):
        return 80
    if relative_path.startswith("wiki/entities/"):
        return 70
    if relative_path.startswith("wiki/maps/"):
        return 60
    if relative_path.startswith("write/"):
        return 25
    if relative_path.startswith("outputs/review/user_summaries/"):
        return 15
    if relative_path.startswith("outputs/"):
        return -20
    return 0


def cmd_kb_preflight(args: argparse.Namespace) -> int:
    root = _kb_root(args)
    canonical = Path(DEFAULT_KB_ROOT).resolve()
    exists = root.exists()
    is_canonical = root == canonical
    git_top = ""
    status_lines: list[str] = []
    git_ok = False
    if exists:
        code, top = _run_git(["rev-parse", "--show-toplevel"], cwd=root)
        git_ok = code == 0
        git_top = top
        code, status = _run_git(["status", "--short", "--branch"], cwd=root)
        if code == 0 and status:
            status_lines = status.splitlines()
    dirty = any(line and not line.startswith("## ") for line in status_lines)
    _print_json({
        "ok": exists and is_canonical and git_ok,
        "canonicalRoot": str(canonical),
        "checkedRoot": str(root),
        "exists": exists,
        "isCanonicalRoot": is_canonical,
        "gitTopLevel": git_top,
        "gitStatus": status_lines[:80],
        "dirty": dirty,
        "requiredBeforeKbReadWrite": [
            "cd /Users/lynch5mo/Work Documents/LLM/agent-kb",
            "git pull --rebase origin main",
            "git status --short --branch",
        ],
        "writePolicy": "Do not write Agent-KB wiki/raw directly from Agent runtime; use proposal/output-layer records unless explicitly authorized.",
    })
    return 0 if exists and is_canonical and git_ok else 1


def _iter_kb_files(root: Path, domain: str) -> list[Path]:
    domain = (domain or "").strip()
    candidates = [
        root / "wiki" / "summaries" / domain,
        root / "wiki" / "concepts" / domain,
        root / "wiki" / "entities" / domain,
        root / "wiki" / "maps" / domain,
    ] if domain else []
    candidates.extend([
        root / "wiki" / "summaries",
        root / "wiki" / "concepts",
        root / "wiki" / "entities",
        root / "wiki" / "maps",
        root / "write",
        root / "outputs",
    ])
    seen: set[Path] = set()
    files: list[Path] = []
    for base in candidates:
        if not base.exists() or not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            try:
                resolved = path.resolve()
            except Exception:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(resolved)
    return files


def _snippet(text: str, terms: list[str], *, width: int = 180) -> str:
    lower = text.lower()
    positions = [lower.find(term.lower()) for term in terms if term and lower.find(term.lower()) >= 0]
    if not positions:
        return text[:width].replace("\n", " ").strip()
    pos = min(positions)
    start = max(0, pos - width // 3)
    end = min(len(text), start + width)
    return text[start:end].replace("\n", " ").strip()


def cmd_kb_search(args: argparse.Namespace) -> int:
    root = _kb_root(args)
    canonical = Path(DEFAULT_KB_ROOT).resolve()
    if root != canonical:
        raise TerminalError(f"Refusing non-canonical Agent-KB root: {root}")
    if not root.exists():
        raise TerminalError(f"Agent-KB root not found: {root}")
    terms = [part.strip() for part in args.query.split() if part.strip()]
    if not terms:
        raise TerminalError("kb-search requires at least one query term.")

    results: list[dict[str, Any]] = []
    max_bytes = max(1000, int(args.max_bytes))
    for path in _iter_kb_files(root, args.domain):
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
        except Exception:
            continue
        rel = str(path.relative_to(root))
        haystack = f"{rel}\n{raw}".lower()
        title = ""
        for line in raw.splitlines()[:20]:
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break
        title_and_path = f"{rel}\n{title}".lower()
        score = _kb_layer_bonus(rel)
        for term in terms:
            term_lower = term.lower()
            score += min(haystack.count(term_lower), 8) * 10
            if term_lower in title_and_path:
                score += 25
        if score <= 0:
            continue
        results.append({
            "score": score,
            "path": str(path),
            "relativePath": rel,
            "layer": _kb_layer(path, root),
            "title": title or path.stem,
            "snippet": _snippet(raw, terms),
        })

    results.sort(key=lambda item: (-int(item["score"]), item["relativePath"]))
    _print_json({
        "ok": True,
        "query": args.query,
        "domain": args.domain,
        "root": str(root),
        "count": min(len(results), args.limit),
        "totalMatches": len(results),
        "items": results[: args.limit],
        "note": "Read the smallest relevant source files before generating claims; keep source paths in the observation model.",
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = _AgentArgumentParser(description="Agent-safe Alpha-FICC terminal API helper.")
    parser.add_argument("--agent", default=os.environ.get("ALPHA_FICC_AGENT_ID", "codex"), help="Agent id, e.g. codex/hermes/claude/pi-agent/deepseek-harness/reasonix.")
    parser.add_argument("--device-id", default=os.environ.get("ALPHA_FICC_DEVICE_ID", ""), help="Optional device id, e.g. mac/ubuntu-desktop/android.")
    parser.add_argument("--base-url", default="", help="API base, with or without trailing /api.")
    parser.add_argument("--token-file", default="", help="Optional file containing the Agent token.")
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("ALPHA_FICC_TIMEOUT", "20")), help="HTTP timeout seconds.")
    sub = parser.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health", help="GET /api/health without requiring a token.")
    health.set_defaults(func=cmd_health)

    context = sub.add_parser("context", help="Read current /comparison Agent-visible context.")
    context.add_argument("--raw", action="store_true", help="Print raw server JSON.")
    context.set_defaults(func=cmd_context)

    chart_data = sub.add_parser("chart-data", help="Fetch full chart data using context.chartDataRequest.")
    chart_data.add_argument("--raw", action="store_true", help="Print raw chart-data JSON.")
    chart_data.set_defaults(func=cmd_chart_data)

    enqueue = sub.add_parser("enqueue-series", help="Queue add_series_to_chart for /comparison.")
    enqueue.add_argument("--series", nargs="*", default=[], help="Series ids, comma-separated or space-separated.")
    enqueue.add_argument("--formulas", nargs="*", default=[], help="Formula ids, comma-separated or space-separated.")
    enqueue.add_argument("--window", default="1Y")
    enqueue.add_argument("--granularity", default="D")
    enqueue.add_argument("--panel-mode", default="appendPanel")
    enqueue.add_argument("--panel-title", default="")
    enqueue.add_argument("--panel-kind", default="macro")
    enqueue.add_argument("--action-id", default="")
    enqueue.add_argument("--source", default="")
    enqueue.add_argument("--note", default="")
    target_page = enqueue.add_mutually_exclusive_group()
    target_page.add_argument(
        "--page-instance-id",
        default="",
        help="Target one /comparison page instance instead of whichever page polls first.",
    )
    target_page.add_argument(
        "--target-current-page",
        action="store_true",
        help="Read the current comparison context and target its pageInstanceId automatically.",
    )
    enqueue.set_defaults(func=cmd_enqueue_series)

    chart_image = sub.add_parser(
        "chart-image",
        help="Generate or fetch a real chart PNG, then download it with the Agent credential.",
    )
    chart_image.add_argument("--series", nargs="*", default=[], help="Series ids, comma- or space-separated.")
    chart_image.add_argument("--formulas", nargs="*", default=[], help="Formula ids, comma- or space-separated.")
    chart_image.add_argument("--workspace-file", default="", help="ChartGenerationSpec or raw workspace JSON file, or '-' for stdin.")
    chart_image.add_argument("--job", default="", help="Continue an existing render job by jobId.")
    chart_image.add_argument(
        "--from-context",
        action="store_true",
        help="Use the current /comparison chart (default source; needs complete snapshot support).",
    )
    chart_image.add_argument("--context", default="", help="Explicit contextId for the current-chart source.")
    chart_image.add_argument("--page-instance", default="", help="Explicit pageInstanceId for the current-chart source.")
    chart_image.add_argument("--panel", default="", help="Real panelId inside the selected chart snapshot.")
    chart_image.add_argument(
        "--mode",
        choices=["terminal", "chart"],
        default="",
        help="terminal (default) uses the existing chart image exporter (legacy protocol: terminalScreenshot); chart is an explicit simplified render.",
    )
    chart_image.add_argument("--allow-fallback", action="store_true", help="Accept a simplified chart when the terminal chart image export fails.")
    chart_image.add_argument("--window", default="", help="Explicit-generation window; defaults to 3Y when omitted.")
    chart_image.add_argument("--granularity", default="", help="Explicit-generation granularity; defaults to D when omitted.")
    chart_image.add_argument("--out", default="", help="Output PNG path; defaults to <jobId>.png in the current directory.")
    chart_image.add_argument("--overwrite", action="store_true", help="Replace an existing target file.")
    chart_image.add_argument("--job-id", default="", help="Pre-fixed jobId for idempotent creation and retry.")
    chart_image.add_argument("--http-timeout", type=int, default=0, help="Per-request HTTP timeout; defaults to --timeout.")
    chart_image.add_argument("--wait-timeout", type=float, default=DEFAULT_CHART_WAIT_TIMEOUT, help="Overall deadline for create/wait/download.")
    chart_image.add_argument("--json", action="store_true", help="Explicitly select JSON stdout (already the default).")
    chart_image.set_defaults(func=cmd_chart_image)

    action = sub.add_parser("action", help="Get /api/agent-actions/{actionId}.")
    action.add_argument("action_id")
    action.set_defaults(func=cmd_action)

    get = sub.add_parser("get", help="Generic GET endpoint.")
    get.add_argument("endpoint")
    get.add_argument("--auth", action="store_true", help="Require Agent auth headers.")
    get.set_defaults(func=cmd_get)

    post = sub.add_parser("post", help="Generic POST endpoint with JSON payload.")
    post.add_argument("endpoint")
    post.add_argument("--payload", required=True, help="JSON file path, or '-' for stdin.")
    post.set_defaults(func=cmd_post)

    kb_preflight = sub.add_parser("kb-preflight", help="Check canonical Agent-KB root and local git state.")
    kb_preflight.add_argument("--kb-root", default="", help="Override Agent-KB root; must resolve to the canonical root for normal use.")
    kb_preflight.set_defaults(func=cmd_kb_preflight)

    kb_search = sub.add_parser("kb-search", help="Read-only local Agent-KB markdown search.")
    kb_search.add_argument("query", help="Whitespace-separated search terms.")
    kb_search.add_argument("--domain", default="finance", help="Preferred KB domain, e.g. finance/ai/film/lifeos/knowledge.")
    kb_search.add_argument("--limit", type=int, default=10)
    kb_search.add_argument("--max-bytes", type=int, default=200000, help="Maximum bytes read from each markdown file.")
    kb_search.add_argument("--kb-root", default="", help="Override Agent-KB root; must resolve to the canonical root.")
    kb_search.set_defaults(func=cmd_kb_search)

    return parser


def main(argv: list[str] | None = None) -> int:
    _load_env_file()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except TerminalError as exc:
        _print_json({
            "ok": False,
            "stage": "cli",
            "errorCode": "CLI_ARGUMENT_ERROR",
            "error": str(exc),
            "message": str(exc),
            "recoverable": False,
        })
        return 2
    try:
        return int(args.func(args))
    except TerminalError as exc:
        _print_json({
            "ok": False,
            "stage": "cli",
            "errorCode": "CLI_ERROR",
            "error": str(exc),
            "message": str(exc),
            "recoverable": True,
        })
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
