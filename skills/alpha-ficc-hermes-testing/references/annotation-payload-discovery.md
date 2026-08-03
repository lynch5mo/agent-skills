# Alpha-FICC API Payload Discovery Record

## Session History

### 2026-05-25 — V2.6 add_chart_annotations Format Probe

**Context**: V2.6 actionType `add_chart_annotations` deployed. Initial POST with annotations as top-level field alongside `target` returned `INVALID_TARGET`.

**Probe Results**:

| Format | HTTP | Error | Interpretation |
|--------|------|-------|----------------|
| **A**: annotations inside `target.annotations` | 400 | `INVALID_ANNOTATION_RATIONALE_0` | Target structure valid! Anno 0 missing `rationale` |
| B: flat (no target wrapper) | 400 | `INVALID_TARGET` | Server expects `target` wrapper |
| C: `target` + separate `annotations` (both top-level) | 400 | `INVALID_TARGET` | Annotations must be inside target |
| D: minimal flat (workspaceId + annotations top-level) | 400 | `INVALID_TARGET` | Same as B |

**Winner**: Format A — annotations nested inside `target.annotations`.

### 2026-05-25 — V2.7 add_chart_annotations Validation Discovery

**Context**: V2.7 full acceptance test. Annotations POST succeeded (HTTP 200) but `INVALID_ANNOTATION_PANEL` on consumer apply. Iterative format refinement revealed:

1. **`invalidCondition` is required on ALL annotation types**, including `text` and `vertical-line`. Missing it on any annotation produces `INVALID_ANNOTATION_INVALIDCONDITION_N` (zero-based index).
2. Error progression was diagnostic:
   - `INVALID_ANNOTATION_INVALIDCONDITION_3` → text at index 3 missing field
   - `INVALID_ANNOTATION_INVALIDCONDITION_0` → trend-line at index 0 has issue after fixes

**Error Code Reference**:

| Error Code | Meaning | Action |
|-----------|---------|--------|
| `UNSUPPORTED_ACTION` | actionType not deployed | Deploy V2.6 branch |
| `INVALID_TARGET` | payload target structure wrong | Move annotations inside target |
| `INVALID_ANNOTATION_RATIONALE_N` | annotation[N] lacks `rationale` | Add rationale field |
| `INVALID_ANNOTATION_INVALIDCONDITION_N` | annotation[N] missing/incorrect `invalidCondition` | Add/format invalidCondition (all types) |
| `INVALID_ANNOTATION_PANEL` | `panelId` not in current comparison workspace | See panel matching section below |
| `INVALID_ANNOTATION_XXX_N` | annotation[N] field XXX invalid | Check field format |
| `AGENT_ACTION_NOT_FOUND` | actionId doesn't exist | Confirm action was accepted |
| `INVALID_ANNOTATION_*_N` | annotation[N] validation failure | Index is zero-based |

## Correct Payload Structure (V2.6/V2.7)

```json
{
  "actionId": "hermes_v263_annotations_<timestamp>",
  "actionType": "add_chart_annotations",
  "source": "external-hermes",
  "note": "...",
  "target": {
    "workspaceId": "extracted_terminal_workspace_id",
    "annotationSetId": "aset_hermes_<timestamp>",
    "caseId": "case_hermes_<timestamp>",
    "runId": "run_hermes_<timestamp>",
    "artifactRef": "artifact_hermes_<timestamp>",
    "applyMode": "append",
    "focus": true,
    "annotations": [
      {
        "id": "ann_unique_id",
        "type": "trend-line | ellipse | vertical-line | text",
        "panelId": "must_match_workspace_panel",
        "sourceId": "yfinance:USDCNH=X",
        "axisSide": "left | right",
        "points": [{"x": "YYYY-MM-DD", "y": NUM}],
        "text": "Display text",
        "color": "#hexcolor",
        "lineWidth": 2,
        "lineStyle": "dashed | solid | dotted",
        "rationale": "REQUIRED on all annotations",
        "confidence": "high | medium | low",
        "invalidCondition": "REQUIRED on ALL annotation types",
        "visible": true,
        "locked": true,
        "validationHint": {
          "window": "YYYY-MM-DD/YYYY-MM-DD",
          "metric": "metric name",
          "expected": "expected behavior",
          "invalidIf": "invalidation condition"
        },
        "evidenceRefs": ["sourceId1", "sourceId2"],
        "sourceAgent": "hermes"
      }
    ]
  }
}
```

## Panel Matching Problem

`INVALID_ANNOTATION_PANEL` occurs when the comparison page's current workspace does not contain the specified `panelId`. This is NOT a payload format issue.

**Root cause**: The `add_series_to_chart` endpoint auto-generates workspace IDs (`terminal-workspace-xxxxx`). The workspace ID specified in the payload (`ws_hermes_...`) is **ignored**. The annotation must target the auto-generated ID.

**Extract the real workspace ID** from the chart POST response:

```python
def deep_get(d, path):
    for p in path.split("."):
        if isinstance(d, dict):
            d = d.get(p)
        else:
            return None
    return d

ws_id = (deep_get(response, "action.target.workspace.id")
         or deep_get(response, "action.result.data.workspace.id"))
```

**Additional causes**:
1. `focus: true` does not reliably switch the comparison page workspace
2. Queue accumulation: stale pending chart actions consumed between chart and annotation, changing the active workspace
3. Dirty comparison page state (multiple tabs from earlier tests)

**Mitigation**:
- Flush queue before the real test: post a dummy chart action, poll until applied
- Minimize delay between chart POST and annotation POST
- Ask user to refresh `/comparison` page for a clean state

## Data Flow

```
Agent POST action → Queue (pendingCount++) → Web /comparison polls /pending
→ Consumer dequeues → status=applied → Data persisted
```

- `pendingCount` shows total queue depth (includes user-triggered actions from web UI)
- Actions stay `queued` if `/comparison` page consumer is not active
- `eventTypes` progression: `["queued", "delivered", "applied"]`
- `applied` event's `result` contains `workspaceId`, `seriesIds`, `formulaIds`, `panelTitle` (NOT panel IDs)

## V2.7 Validation Run Endpoints

### POST /api/chart-annotation-validation-runs

```json
{
  "agent": "hermes",
  "source": "external-hermes",
  "mode": "evaluate_available",
  "packet": {
    "reviewPacketId": "arp_<uuid>",
    "annotationSetId": "aset_...",
    "hypotheses": ["hyp_ann_..."]
  },
  "asOf": "2026-06-30"
}
```

Response: `{"runId": "vr_<uuid>", ...}`, HTTP 201/200.

### GET /api/chart-annotation-validation-runs/{runId}

Returns `{"status": "completed|failed|pending", ...}`. Poll every 3s up to 45s.

### GET /api/chart-annotation-validation-runs/{runId}/results

Returns results array. Each result has `verdict` or `conclusion`:
- `supported` — market data supports the hypothesis
- `contradicted` — market data contradicts
- `inconclusive` — cannot determine
- `data_unavailable` — insufficient data
- `pending` — not yet evaluated

### Fallback

```python
GET /api/chart-annotation-validations?runId={runId}
```

## Internal API Discovery (2026-05-25)

**Finding**: The Alpha-FICC server has an internal API at `http://127.0.0.1:8001/api`, accessible from SSH host.

**Docker containers**:
```
alpha-ficc-web      0.0.0.0:5174->5174/tcp   (comparison UI)
alpha-ficc-api      127.0.0.1:8001->8001/tcp  (API — internal only)
alpha-ficc-postgres 127.0.0.1:5432->5432/tcp  (database)
```

**Public API**: `https://alpha-ficc.lynch5mo.xyz/api` — goes through Cloudflare, subject to intermittent SSL failures (`SSL: UNEXPECTED_EOF_WHILE_READING`, `Temporary failure in name resolution`).

**Recommendation**: All Python test scripts run via SSH should use the internal API for reliability.

### SSL Compatibility Mode (when internal API unavailable)

```python
import ssl
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE
https_handler = urllib.request.HTTPSHandler(context=_ssl_ctx)
opener = urllib.request.build_opener(https_handler)
# Use opener.open() instead of urllib.request.urlopen()
```

## Review Packet Response Schema

**⚠️ Fields are NESTED — NOT at top level. `rp.get("annotationCount")` returns `None`.**

| Summary Field | Actual Path |
|--------------|-------------|
| annotationCount | `summary.annotationCount` |
| validationCandidateCount | `summary.validationCandidateCount` |
| lockedCount | `summary.lockedCount` |
| validationHintRatio | `coverage.validationHintCoverage.ratio` |
| hasMissingValidationHintWarning | derived: `any(w.code == "MISSING_VALIDATION_HINT" for w in warnings)` |
| hasHighPriorityHypothesis | derived: `any(h.priority == "high" for h in hypotheses)` |

### Python Extraction Pattern

```python
rp = response_dict
sm = rp.get("summary", {})
cv = rp.get("coverage", {})
hyps = rp.get("hypotheses", [])
warns = rp.get("warnings", [])

annotation_count = sm.get("annotationCount")
vcc = sm.get("validationCandidateCount")
locked_count = sm.get("lockedCount")
vh_ratio = cv.get("validationHintCoverage", {}).get("ratio")
has_missing_warning = any(w.get("code") == "MISSING_VALIDATION_HINT" for w in warns)
has_high_priority = any(h.get("priority") == "high" for h in hyps)
```

### GET /chart-annotations List

Response: `{"ok": true, "count": 4, "annotations": [...]}`

**⚠️ Annotation details are at `annotations[i].annotation.*`, NOT `annotations[i].*` directly.**

```python
annots = response.get("annotations", [])
first_id = annots[0].get("annotation", {}).get("id")  # correct
first_id = annots[0].get("id")  # WRONG — returns None
```

### GET /chart-annotations/{annotationId}

```python
detail = response.get("annotation", {})
ann_id = detail.get("id")
ann_source = detail.get("sourceAgent")
ann_locked = detail.get("locked")
ann_has_vh = detail.get("validationHint") is not None
```

## Workspace & Panel ID Extraction from Chart Response

**Critical discovery (2026-05-25)**: The `workspace.id` you specify in the chart action payload is **ignored** by the server. The API returns an auto-generated ID like `terminal-workspace-xxxxx`.

**Must extract the real workspaceId and panelIds from the POST response** for use in annotations:

```python
def deep_get(d, *keys):
    """Safely navigate nested dicts."""
    for k in keys:
        if isinstance(d, dict): d = d.get(k)
        else: return None
    return d

# After POST /api/terminal-chart-actions (add_series_to_chart):
# response = s1r (the POST response dict)

# Extract workspaceId from multiple possible locations
ws_id = (deep_get(response, "action", "target", "workspace", "id")
         or deep_get(response, "action", "result", "data", "workspace", "id")
         or "")

# Extract panel IDs from workspace.panels
panels = (deep_get(response, "action", "target", "workspace", "panels")
          or deep_get(response, "action", "result", "data", "workspace", "panels")
          or [])
panel_ids = list(set(p.get("id") for p in panels if isinstance(p, dict) and p.get("id")))

# Fallback: extract from workspace.objects.panelId
if not panel_ids:
    objs = (deep_get(response, "action", "target", "workspace", "objects")
            or deep_get(response, "action", "result", "data", "workspace", "objects")
            or [])
    panel_ids = list(set(o.get("panelId") for o in objs if isinstance(o, dict) and o.get("panelId")))
```

Then use these in annotations:

```python
annotation["panelId"] = panel_ids[0]  # first panel
annotation["panelId"] = panel_ids[1] if len(panel_ids) > 1 else panel_ids[0]  # second panel
```

**Also extract from applied event ledger** (verification step):

```python
# After polling agent-actions to applied
s2, r2 = req("GET", f"{api}/agent-actions/{chart_aid}", token)
for ev in r2.get("events", []):
    if ev.get("eventType") == "applied":
        applied_ws = deep_get(ev, "result", "workspaceId") or ws_id
        applied_panels = deep_get(ev, "result", "data", "workspace", "panels")
        # Also check target.workspace.panels
        target_panels = deep_get(r2, "target", "workspace", "panels")
```

## Error Code Reference

| Field | Required? | Notes |
|-------|-----------|-------|
| `actionId` | YES | Unique per request; include timestamp |
| `actionType` | YES | `add_series_to_chart` / `add_chart_annotations` |
| `source` | YES | Must be `external-hermes` |
| `rationale` | YES | On every annotation |
| `invalidCondition` | **YES** | On ALL annotations (all types incl text/vertical-line) |
| `validationHint` | No | Only needed for validation candidates |
| `visible` | Yes | Boolean |
| `locked` | No | Boolean; if omitted defaults to false |
| `confidence` | Yes | `high`, `medium`, or `low` |
| `evidenceRefs` | **YES** | Server returns `INVALID_ANNOTATION_EVIDENCE_REFS_N` without it (discovered 2026-06-03). Must be a list of sourceId strings, e.g. `["yfinance:BTC-USD", "fred:BAMLH0A0HYM2"]` |
| `sourceAgent` | Yes | Must be `hermes` |

## Acceptance Criteria (4-annotation set)

| Check | Expected |
|-------|----------|
| chartAction.ok | true |
| annotationAction.ok | true |
| ledger.status | "applied" |
| ledger.eventTypes | ["queued", "delivered", "applied"] |
| annotationStore.count | 4 |
| annotationDetail.annotationId | "ann_usdcnh_pressure_trend_001" (or timestamped variant) |
| annotationDetail.sourceAgent | "hermes" |
| annotationDetail.locked | true |
| annotationDetail.hasValidationHint | true |
| reviewPacket.annotationCount | 4 |
| reviewPacket.validationCandidateCount | 2 |
| reviewPacket.lockedCount | >= 1 |
| reviewPacket.validationHintRatio | 0.5 |
| reviewPacket.hasMissingValidationHintWarning | true |
| reviewPacket.hasHighPriorityHypothesis | true |
