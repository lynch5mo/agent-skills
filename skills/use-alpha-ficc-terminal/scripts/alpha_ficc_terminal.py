#!/usr/bin/env python3
"""Agent-safe helper for the Alpha-FICC terminal API."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://alpha-ficc.lynch5mo.xyz/api"
DEFAULT_KB_ROOT = "/Users/lynch5mo/Work Documents/LLM/agent-kb"


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


def _agent_env_key(agent: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in agent.upper()).strip("_")
    return f"ALPHA_FICC_{normalized}_AGENT_TOKEN"


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
    if args.token_file:
        token_path = Path(args.token_file).expanduser()
    elif os.environ.get("ALPHA_FICC_TOKEN_FILE"):
        token_path = Path(os.environ["ALPHA_FICC_TOKEN_FILE"]).expanduser()
    else:
        token_path = None

    token = ""
    if token_path and token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()

    if not token:
        token = (
            os.environ.get(_agent_env_key(args.agent))
            or os.environ.get("ALPHA_FICC_AGENT_TOKEN")
            or ""
        ).strip()

    if required and not token:
        raise TerminalError(
            "Missing Agent token. Set ALPHA_FICC_<AGENT>_AGENT_TOKEN, "
            "ALPHA_FICC_AGENT_TOKEN, ALPHA_FICC_TOKEN_FILE, or --token-file."
        )
    return token


def _headers(args: argparse.Namespace, *, require_token: bool, json_body: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": f"Alpha-FICC-Agent/{args.agent} skill/use-alpha-ficc-terminal",
    }
    token = _read_token(args, required=require_token)
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Alpha-FICC-Agent"] = args.agent
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
        return {
            "ok": False,
            "status": status,
            "error": payload.get("error") or payload,
        }
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
    target: dict[str, Any] = {
        "seriesIds": _split_csv_and_args(args.series),
        "formulaIds": _split_csv_and_args(args.formulas),
        "window": args.window,
        "granularity": args.granularity,
    }
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
        "pendingCount": response.get("pendingCount"),
        "authenticatedAgent": response.get("authenticatedAgent"),
        "ledgerEndpoint": f"/api/agent-actions/{action_id}",
        "rawError": response.get("error") if status >= 400 else None,
    }
    _print_json(safe_summary)
    return 0 if status < 400 and response.get("ok", True) is not False else 1


def _read_payload(path: str) -> dict[str, Any]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TerminalError("Payload JSON must be an object.")
    return payload


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
    parser = argparse.ArgumentParser(description="Agent-safe Alpha-FICC terminal API helper.")
    parser.add_argument("--agent", default=os.environ.get("ALPHA_FICC_AGENT_ID", "codex"), help="Agent id, e.g. codex/hermes/claude.")
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
    enqueue.set_defaults(func=cmd_enqueue_series)

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
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except TerminalError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
