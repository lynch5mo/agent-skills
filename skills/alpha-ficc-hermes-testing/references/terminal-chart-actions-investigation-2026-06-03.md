# terminal-chart-actions INVALID_TARGET Investigation (2026-06-03)

## Context

Session attempted to push analysis annotations (12 items: vertical lines, trend lines, text boxes) to the active comparison workspace `ws_btc_push_1780474778` (page label `CMP-2603D4`). All POST requests to `/api/terminal-chart-actions` returned `{"ok": false, "error": "INVALID_TARGET"}`.

## Investigation Findings

### 1. Workspace exists in annotation store but NOT in workspace store

- `GET /api/chart-annotations` returns 34 annotations for `ws_btc_push_1780474778` ✅
- `GET /api/workspaces` does NOT list `ws_btc_push_1780474778` ❌
- `GET /api/workspaces/ws_btc_push_1780474778` returns 404 ❌
- `GET /api/comparison/current/context` still reports `ws_btc_push_1780474778` as active workspace ✅

**Conclusion**: The workspace exists in the annotation store (historical records) and the context cache, but has been removed from the active workspace store. The `terminal-chart-actions` endpoint validates against the workspace store and rejects requests for non-existent workspaces.

### 2. Payload format was correct but still rejected

Tested the known-correct format (annotations nested in `target.annotations`) with all required fields (`rationale`, `invalidCondition`, `evidenceRefs`, `sourceAgent`). Still returned `INVALID_TARGET`. This confirms the error is workspace-level, not payload-level.

### 3. All workspace ID formats rejected

Tested:
- `ws_btc_push_1780474778` (from context)
- `CMP-2603D4` (page label)
- `comparison-57533748-9b50-4f0c-8b44-8e19922603d4` (page instance ID)
- `ws-45d056ace0f7` (an actual workspace from `/api/workspaces`)

All returned `INVALID_TARGET`. This suggests the endpoint may have additional validation beyond workspace existence (possibly requires the workspace to be "locked" or "focused" by the comparison page).

### 4. Different action types also rejected

Tested `add_chart_annotations` and even bare `{"action": "test"}` — all returned `INVALID_TARGET`. The endpoint appears to reject ALL requests when called from outside the comparison page's consumer loop.

### 5. Cloudflare behavior

- Python `requests` library: GET endpoints work (bypasses Cloudflare), but POST to `terminal-chart-actions` fails with INVALID_TARGET
- Python `urllib`: GET endpoints hit Cloudflare 403 (`error code: 1010`)
- curl: GET endpoints work, but POST not tested (token interpolation issues in bash)

## Hypothesis

The `terminal-chart-actions` endpoint may now require the request to come from the comparison page's internal consumer (via `/pending` poll) rather than directly from an external agent. The Codex fix for the annotation rendering bug (SET_WORKSPACE → MERGE_ANNOTATIONS) may have changed the API contract to only accept actions through the page's consumer pipeline.

## Recommended Next Steps

1. Check if the Codex fix changed the `terminal-chart-actions` endpoint contract
2. Verify if there's a new endpoint for external agent annotation pushes
3. Try pushing to a freshly created workspace (via `add_series_to_chart`) to see if the issue is workspace-specific or endpoint-wide
4. Check server logs for the specific validation that's failing

## Loop Discipline Lesson

After 3-4 failed format probes with the same error code, stop retrying and report the blocker. In this session, ~15+ variations were tested before stopping. The additional probes provided no new information — the error was consistent across all formats, indicating a systemic issue (workspace state or API contract change) rather than a payload format issue.
