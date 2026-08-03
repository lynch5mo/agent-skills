# Annotation Append Rendering Bug (2026-06-03)

## Bug Report Summary

When `add_chart_annotations` actions are applied via the terminal chart actions API with `applyMode: append`, the annotations are stored in the backend annotation store but **not rendered by the frontend** until the user performs a hard refresh (Cmd+Shift+R).

## Reproduction

1. Push chart via `POST /api/terminal-chart-actions` (add_series_to_chart) → workspace opens, data renders ✅
2. Push batch 1 annotations (append) → applied ✅ → frontend renders ✅
3. Push batch 2 annotations (append) → applied ✅ → backend store confirms (count, status=active, visible=true) ✅ → **frontend does NOT render** ❌
4. Hard refresh (Cmd+Shift+R) → batch 2 annotations appear ✅

## Root Cause

The issue is in the frontend state management chain:

```
applyTerminalChartAnnotations (Comparison.jsx ~line 3968)
  → merges annotations into workspace object
  → setOpenWorkspaceIntent(workspace with merged annotations)
    → ChartWorkspace useEffect (line 1334)
      → normalizeOpenedWorkspace(intent.workspace)
        → dispatch({ type: 'SET_WORKSPACE', payload: opened })
          → chartWorkspaceReducer replaces entire state
```

The problem: `workspaceStateRef.current` may not preserve annotations from batch 1 when batch 2 arrives. The `SET_WORKSPACE` dispatch replaces the entire state, and if the intent payload doesn't carry ALL annotations (both old and new), previous ones are lost.

In `applyTerminalChartAnnotations`:
```javascript
const existingAnnotations = Array.isArray(workspace.annotations) ? workspace.annotations : []
// workspace = workspaceStateRef.current — may not have batch 1 annotations!
const nextAnnotations = [...existingAnnotations, ...normalizedAnnotations]
```

If `workspaceStateRef.current.annotations` is empty (annotations were loaded via a different path), only batch 2 annotations end up in the state.

## Backend Verification

All annotations ARE stored correctly:
- `GET /api/chart-annotations?actionId=...` returns correct count
- Each annotation: `status: active`, `visible: true`, correct `workspaceId`, `panelId`
- The annotation store is not the problem

## Suggested Fix

In `Comparison.jsx`, after `applyTerminalChartAnnotations` completes:

1. Re-fetch annotations from backend:
   ```
   GET /api/chart-annotations?workspaceId={workspaceId}
   ```
2. Merge fetched annotations into `workspaceStateRef.current.annotations`
3. Trigger state update via `setWorkspaceStateVersion`

Alternatively, in `ChartWorkspace.jsx`, ensure `onStateUpdate` callback preserves annotations through the normalize → dispatch → state cycle.

## Temporary Workaround

After pushing annotations via API, tell user to Cmd+Shift+R to force frontend to reload workspace with all annotations.

## Related: Workspace ID Tracking

When pushing annotations, the workspace ID must come from `GET /api/comparison/current/context` (the active workspace on the comparison page), NOT from the chart action response. The comparison page may be on a different workspace if the user has multiple tabs.

Correct flow:
1. Push chart action → get workspaceId from response
2. Wait for chart applied
3. Ask user to click "分享给 Agent"
4. `GET /api/comparison/current/context` → get `workspace.workspaceId`
5. Use this workspaceId for annotations
