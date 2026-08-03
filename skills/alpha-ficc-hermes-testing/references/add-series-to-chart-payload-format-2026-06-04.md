# add_series_to_chart INVALID_TARGET — Caller Format Root Cause (2026-06-04)

## Context

Attempted to add `fred:DFII05` (5Y TIPS yield) to an existing comparison workspace via `POST /api/terminal-chart-actions` with `actionType: "add_series_to_chart"`. All attempts returned `{"ok": false, "error": "INVALID_TARGET"}` regardless of payload variation.

## Root Cause: Caller Sent a Non-Canonical Body

Hermes did this because the current profile mainly reaches Alpha-FICC through generic terminal/curl execution plus skill instructions, not a strong typed `terminal_chart_action_enqueue` tool. Older skill text used "payload" as a generic name for the HTTP JSON body, which made the model produce a top-level `payload` field in the API body.

The `_normalize_terminal_chart_action_body()` function in `scripts/api_server.py` (line 22593) extracts the target like this:

```python
target = body.get("target") if isinstance(body.get("target"), dict) else body
```

It then looks for series/formula IDs inside `target` (lines 22594-22601):

```python
series_ids = target.get("seriesIds") or target.get("series_ids") or []
formula_ids = target.get("formulaIds") or target.get("formula_ids") or []
```

**The problem**: the failing Hermes request sent data in `body.payload`, not the Alpha-FICC canonical `body.target`:

```json
// Non-compliant Hermes request:
{
    "actionType": "add_series_to_chart",
    "workspaceId": "ws_xxx",
    "payload": {
        "formula": "fred:DFII05",
        "label": "5Y TIPS"
    }
}

// Canonical Alpha-FICC request for a FRED series:
{
    "actionType": "add_series_to_chart",
    "source": "external-hermes",
    "target": {
        "seriesIds": ["fred:DFII05"],
        "workspaceId": "ws_xxx"
    }
}
```

When `body.get("target")` returns `None` (key doesn't exist), the code falls back to `target = body`. But `body` has `"payload"` not `"seriesIds"`/`"formulaIds"`, so both arrays end up empty → triggers `INVALID_TARGET` at line 22626-22627.

## Two Issues

1. **Key name mismatch**: Agent sends `payload`, the contract requires `target`
2. **Value format mismatch**: Agent sends `formula: "fred:DFII05"`; `fred:DFII05` is a FRED series id and belongs in `seriesIds: ["fred:DFII05"]`, not `formulaIds`

## Additional Observations

- `add_chart_annotations` works because it has completely separate handling (line 22412-22588) with its own target extraction logic
- The `_handle_action()` method (line 31692-31710) follows the same `target.seriesIds` / `target.formulaIds` contract for the legacy `/api/action` endpoint

## Correct Fix

See bug report: `/Users/lynch5mo/Work Documents/Alpha-FICC/docs/bugs/2026-06-04-add-series-to-chart-INVALID_TARGET.md`

Do not treat this as a server bug unless a canonical `target.seriesIds` / `target.formulaIds` request also fails.

The fix is to make Hermes use the Alpha-FICC tool schema. In skill docs and scripts, call this an "HTTP request body" rather than "payload" unless referring to Python's local `payload` variable:

Hard rule: the `POST /api/terminal-chart-actions` request body must not contain a top-level `payload` field.

```json
{
    "actionType": "add_series_to_chart",
    "source": "external-hermes",
    "target": {
        "seriesIds": ["fred:DFII05"],
        "window": "10Y",
        "granularity": "D"
    }
}
```

## Temporary Workaround

1. Confirm Hermes loaded the current `config/agent-tools/alpha-ficc-http-tools.json`
2. Send only canonical `target` request bodies for terminal chart actions

## Loop Discipline

When the same error persists across 3-4 variants, stop guessing. First compare the attempted request against the handbook/schema. Only escalate to service-side investigation after a canonical `target` request fails.
