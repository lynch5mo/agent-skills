#!/usr/bin/env python3
"""
V2.7 Full Acceptance — Reusable template.
Usage: adjust ts/IDs and POST to Alpha-FICC API.

Two modes:
  SSH mode:    scp to server, run via ssh, use "http://127.0.0.1:8001/api"
  Local mode:  run locally, read token from .env, use "https://alpha-ficc.lynch5mo.xyz/api"
"""
import json, os, pathlib, ssl, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────────
USE_LOCAL_TOKEN = True  # False = read from server's .env
API = "http://127.0.0.1:8001/api" if not USE_LOCAL_TOKEN else "https://alpha-ficc.lynch5mo.xyz/api"

# ── Token ────────────────────────────────────────────────────
token = ""
if USE_LOCAL_TOKEN:
    # Read from local .env (Python binary parsing — NOT grep/os.getenv)
    with open("/Users/lynch5mo/.hermes/profiles/codex/.env", "rb") as f:
        for line in f.read().split(b"\n"):
            if line.startswith(b"ALPHA_FICC_HERMES_AGENT_TOKEN="):
                t = line.split(b"=", 1)[1].strip()
                token = t.decode("utf-8", errors="replace")
                if token.startswith('"') and token.endswith('"'): token = token[1:-1]
                elif token.startswith("'") and token.endswith("'"): token = token[1:-1]
                break
else:
    # Read from server's .env
    import pathlib as _pl
    for raw_line in _pl.Path("/home/lynch5mo/alpha-ficc/.env").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("ALPHA_FICC_HERMES_AGENT_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

if not token:
    print(json.dumps({"ok": False, "problems": ["TOKEN_NOT_FOUND"]}))
    sys.exit(1)

# ── HTTP helper ──────────────────────────────────────────────
def deep_get(d, *keys):
    for k in keys:
        if isinstance(d, dict): d = d.get(k)
        else: return None
    return d

def req(method, url, body=None):
    headers = {
        "Accept": "application/json",
        "User-Agent": "Alpha-FICC-Hermes-Wrapper/1.0",
        "X-Alpha-FICC-Agent": "hermes",
        "Authorization": f"Bearer {token}",
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    if body: headers["Content-Type"] = "application/json"

    # SSL bypass for public API
    if USE_LOCAL_TOKEN:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))

    for attempt in range(3):
        try:
            r = urllib.request.Request(url, data=payload, headers=headers, method=method)
            if USE_LOCAL_TOKEN:
                with opener.open(r, timeout=30) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
            else:
                with urllib.request.urlopen(r, timeout=30) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try: data = json.loads(raw or "{}")
            except: data = {"raw": raw}
            return exc.code, data
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            if attempt < 2: time.sleep(2 ** attempt)
            else: raise
    return 0, {}

def poll_until(aid, timeout_s=60, label=""):
    start = time.time()
    last_status = None
    events = []
    while time.time() - start < timeout_s:
        s, r = req("GET", f"{API}/agent-actions/{aid}")
        if s == 200 and r.get("status"):
            last_status = r["status"]
            events = [e.get("eventType") for e in r.get("events", []) if e.get("eventType")]
            if last_status in ("applied", "failed"): break
        elif s == 404: break
        time.sleep(3)
    return last_status, events

# ── Main ─────────────────────────────────────────────────────
j = json
ts = int(datetime.now(timezone.utc).timestamp() * 1000)

# ===== Step 1: Chart =====
import uuid
widget_suffix = str(uuid.uuid4())[:8]
ws_id = f"ws_v27_test_{ts}"
panel_fx = f"panel_fx_{widget_suffix}"
panel_rates = f"panel_rates_{widget_suffix}"
chart_aid = f"hermes_v27_test_chart_{ts}"
annot_aid = f"hermes_v27_test_annot_{ts}"
aset_id = f"aset_v27_test_{ts}"

step1 = {
    "actionId": chart_aid, "actionType": "add_series_to_chart",
    "source": "external-hermes", "agent": "hermes",
    "note": "V2.7 acceptance chart",
    "target": {
        "seriesIds": ["yfinance:USDCNH=X", "fred:DTWEXBGS", "fred:DGS10", "akshare:bond_china_cgb_10y"],
        "formulaIds": ["us_cn_spread"],
        "window": "3Y", "granularity": "D", "panelMode": "appendPanel",
        "panelTitle": "人民币汇率压力框架", "panelKind": "macro",
        "workspace": {
            "id": ws_id,
            "panels": [
                {"id": panel_fx, "title": "人民币汇率与美元压力", "kind": "macro", "heightWeight": 1.2},
                {"id": panel_rates, "title": "中美利差与长端利率", "kind": "policy", "heightWeight": 1.0, "zeroLine": True},
            ],
            "objects": [
                {"id": "obj-a", "sourceId": "yfinance:USDCNH=X", "panelId": panel_fx, "axisSide": "left", "label": "USD/CNH", "unit": "rate", "color": "#dc2626"},
                {"id": "obj-b", "sourceId": "fred:DTWEXBGS", "panelId": panel_fx, "axisSide": "right", "label": "美元指数代理", "unit": "index", "color": "#2563eb"},
                {"id": "obj-c", "sourceId": "fred:DGS10", "panelId": panel_rates, "axisSide": "left", "label": "美国10Y", "unit": "percent", "color": "#7c3aed"},
                {"id": "obj-d", "sourceId": "akshare:bond_china_cgb_10y", "panelId": panel_rates, "axisSide": "left", "label": "中国10Y", "unit": "percent", "color": "#16a34a"},
                {"id": "obj-e", "sourceId": "us_cn_spread", "sourceType": "formula", "panelId": panel_rates, "axisSide": "right", "label": "中美利差", "unit": "percent", "color": "#0f766e"},
            ],
            "timeWindow": {"preset": "3Y", "granularity": "D"}, "chartMode": "absolute",
        },
    },
}

s1s, s1r = req("POST", f"{API}/terminal-chart-actions", step1)
print(j.dumps({"step": 1, "http": s1s, "ok": s1r.get("ok")}), flush=True)
if s1s >= 400: print(j.dumps({"ok": False, "problems": [s1r.get("error", "")]})); sys.exit(1)

cs, ce = poll_until(chart_aid, 120)
print(j.dumps({"step": 2, "status": cs}), flush=True)
if cs != "applied": print(j.dumps({"ok": False, "problems": ["chart not applied"]})); sys.exit(1)

# ===== Step 3: Annotations with REAL IDs =====
step3 = {
    "actionId": annot_aid, "actionType": "add_chart_annotations",
    "source": "external-hermes", "agent": "hermes",
    "note": "V2.7 annotations",
    "target": {
        "workspaceId": ws_id, "annotationSetId": aset_id,
        "caseId": f"case_{ts}", "runId": f"run_{ts}", "artifactRef": f"art_{ts}",
        "applyMode": "append", "focus": True,
        "annotations": [
            {"id": f"ann_t_{ts}", "type": "trend-line", "panelId": panel_fx,
             "sourceId": "yfinance:USDCNH=X", "axisSide": "left",
             "points": [{"x": "2024-09-30", "y": 7.02}, {"x": "2025-04-10", "y": 7.36}],
             "text": "USDCNH 上行压力趋势线", "color": "#dc2626", "lineWidth": 2, "lineStyle": "dashed",
             "rationale": "低点抬升且美元指数偏强", "confidence": "high", "locked": True,
             "invalidCondition": "若 USDCNH 跌破 7.02 且美元指数不再走强，则该压力线判断失效。",
             "validationHint": {"window": "2025-04-10/2026-06-30", "metric": "USDCNH close",
                               "expected": "维持在 7.10 上方", "invalidIf": "连续 5 个交易日收盘低于 7.02"},
             "evidenceRefs": ["yfinance:USDCNH=X", "fred:DTWEXBGS", "fred:DGS10"], "sourceAgent": "hermes", "visible": True},
            {"id": f"ann_e_{ts}", "type": "ellipse", "panelId": panel_fx,
             "sourceId": "fred:DTWEXBGS", "axisSide": "right",
             "points": [{"x": "2025-03-01", "y": 95}, {"x": "2025-05-31", "y": 108}],
             "text": "美元指数压力放大区间", "color": "#f97316", "lineWidth": 2, "lineStyle": "solid",
             "rationale": "美元指数在该区间内持续高企", "confidence": "medium",
             "invalidCondition": "若 DXY 跌破 95 且美联储转向鸽派，则该压力区间判断失效。",
             "validationHint": {"window": "2025-03-01/2026-06-30", "metric": "DXY close",
                               "expected": "DXY 维持在 95 上方", "invalidIf": "DXY 连续 10 个交易日低于 95"},
             "evidenceRefs": ["fred:DTWEXBGS", "fred:DGS10"], "sourceAgent": "hermes", "visible": True},
            {"id": f"ann_v_{ts}", "type": "vertical-line", "panelId": panel_fx,
             "sourceId": "yfinance:USDCNH=X", "axisSide": "left",
             "points": [{"x": "2025-04-22", "y": 6.95}, {"x": "2025-04-22", "y": 7.45}],
             "text": "政策预期切换点", "color": "#2563eb", "lineWidth": 1.5, "lineStyle": "dotted",
             "rationale": "该时点附近政策信号变化频繁", "confidence": "low",
             "invalidCondition": "若前后 10 个交易日波动无显著变化，则该时间窗口解释力不足。",
             "evidenceRefs": ["yfinance:USDCNH=X", "fred:DTWEXBGS"], "sourceAgent": "hermes", "visible": True},
            {"id": f"ann_x_{ts}", "type": "text", "panelId": panel_fx,
             "sourceId": "yfinance:USDCNH=X", "axisSide": "left",
             "points": [{"x": "2025-05-20", "y": 7.31}],
             "text": "人民币压力不是单一汇率结论，而是美元、利差、政策预期、资本流动共同传导",
             "color": "#111827", "rationale": "框架性注释", "confidence": "high",
             "invalidCondition": "若后续观察变量新增且原规则不再覆盖主要驱动项，则该注释失效。",
             "evidenceRefs": ["fred:DTWEXBGS", "fred:DGS10", "fred:DGS2"], "sourceAgent": "hermes", "visible": True},
        ],
    },
}
s3s, s3r = req("POST", f"{API}/terminal-chart-actions", step3)
print(j.dumps({"step": 3, "http": s3s, "ok": s3r.get("ok")}), flush=True)
if s3s >= 400: print(j.dumps({"ok": False, "problems": [s3r.get("error", "")]})); sys.exit(1)

as_, ae = poll_until(annot_aid, 120)
print(j.dumps({"step": 4, "status": as_}), flush=True)
if as_ != "applied": print(j.dumps({"ok": False, "problems": [f"annot {as_}"]})); sys.exit(1)

# ===== Step 5: Query =====
s5a_s, s5a_r = req("GET", f"{API}/chart-annotations?annotationSetId={aset_id}")
annots = []
if isinstance(s5a_r, dict):
    for k in ["annotations", "data", "results", "items"]:
        if isinstance(s5a_r.get(k), list): annots = s5a_r[k]; break
ac = len(annots)
vhc = sum(1 for a in annots if isinstance(a.get("annotation", a), dict) and a.get("annotation", a).get("validationHint"))
print(j.dumps({"step": "5a", "count": ac, "vh": vhc}), flush=True)

s5b_s, s5b_r = req("GET", f"{API}/chart-annotation-review-packet?annotationSetId={aset_id}")
sm = s5b_r.get("summary", {}) if isinstance(s5b_r, dict) else {}
hyps = s5b_r.get("hypotheses", []) if isinstance(s5b_r, dict) else []
warns = s5b_r.get("warnings", []) if isinstance(s5b_r, dict) else []
pid = s5b_r.get("packetId", "")
print(j.dumps({"step": "5b", "ac": sm.get("annotationCount"), "vcc": sm.get("validationCandidateCount"), "hc": len(hyps)}), flush=True)

# ===== Step 6: Validation run =====
s6b = {"agent": "hermes", "source": "external-hermes", "mode": "evaluate_available",
       "packet": {"reviewPacketId": pid, "annotationSetId": aset_id, "hypotheses": [h.get("hypothesisId") for h in hyps]},
       "asOf": "2026-06-30"}
s6s, s6r = req("POST", f"{API}/chart-annotation-validation-runs", s6b)
vrid = s6r.get("runId", "") if isinstance(s6r, dict) else ""
print(j.dumps({"step": 6, "http": s6s, "runId": vrid}), flush=True)

# ===== Step 7: Results =====
vrs = None; vrc = 0; vvd = {}; vsam = []
if vrid:
    for _ in range(15):
        s7a_s, s7a_r = req("GET", f"{API}/chart-annotation-validation-runs/{vrid}")
        vrs = s7a_r.get("status", "") if isinstance(s7a_r, dict) else ""
        if vrs in ("completed", "failed", "error"): break
        time.sleep(3)
    vl = []
    for ep in [f"/chart-annotation-validation-runs/{vrid}/results",
               f"/chart-annotation-validations?runId={vrid}"]:
        s, r = req("GET", f"{API}{ep}")
        if isinstance(r, dict):
            for k in ["results", "data", "items", "validations"]:
                if isinstance(r.get(k), list): vl = r[k]; break
        elif isinstance(r, list): vl = r
        if vl: break
    vrc = len(vl)
    for v in vl:
        if isinstance(v, dict):
            vd = v.get("verdict") or v.get("conclusion") or "unknown"
            vvd[vd] = vvd.get(vd, 0) + 1
    vsam = vl[:3]

ok = (as_ == "applied" and ac >= 4 and sm.get("validationCandidateCount", 0) >= 2 and vrid and vrc >= 2)
smry = {
    "ok": ok,
    "chartAction": {"status": cs, "eventTypes": ce},
    "annotationAction": {"status": as_, "eventTypes": ae},
    "annotationStore": {"count": ac, "validationHintCount": vhc},
    "reviewPacket": {"annotationCount": sm.get("annotationCount"), "validationCandidateCount": sm.get("validationCandidateCount"),
                     "hypothesisCount": len(hyps), "warnings": [w.get("code") for w in warns]},
    "validationRun": {"http": s6s, "runId": vrid, "status": vrs, "resultCount": vrc},
    "validationResults": {"count": vrc, "verdicts": vvd, "sample": vsam},
    "problems": [],
}
if not ok:
    ps = []
    if as_ != "applied": ps.append(f"annotStatus={as_}")
    if ac < 4: ps.append(f"annotCount={ac}")
    if sm.get("validationCandidateCount", 0) < 2: ps.append(f"vcc={sm.get('validationCandidateCount')}")
    if not vrid: ps.append("noValRunId")
    elif vrc < 2: ps.append(f"valRc={vrc}")
    smry["problems"] = ps

print(json.dumps(smry, ensure_ascii=False))
