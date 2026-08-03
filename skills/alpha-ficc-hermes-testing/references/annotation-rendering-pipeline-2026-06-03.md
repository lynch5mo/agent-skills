# Annotation Rendering Pipeline Analysis (2026-06-03)

## Summary
Annotations pushed via `POST /api/terminal-chart-actions` (add_chart_annotations) are stored correctly in the backend but fail to render on the comparison page due to a frontend timing issue in `EChartsWorkspaceRenderer.jsx`.

## Backend Chain (all working)
1. POST add_chart_annotations → HTTP 200, ok: true
2. Poll /api/agent-actions/{actionId} → status: applied
3. GET /api/chart-annotations?actionId=... → count: 9, all status=active, visible=true
4. Review packet → annotationCount: 9, lockedCount: 9

## Frontend Rendering Chain
```
setOpenWorkspaceIntent (workspace includes annotations)
  → ChartWorkspace useEffect consumes intent (line 1334)
    → normalizeOpenedWorkspace() extracts source.annotations (line 290-327)
      → dispatch({ type: 'SET_WORKSPACE', payload: opened })
        → chartWorkspaceReducer: state.annotations = payload.annotations.map(normalizeAnnotation)
          → visibleAnnotations useMemo: filter(annotations, a => a.visible !== false)
            → renderAnnotationGraphics useCallback: rebuilds on visibleAnnotations change
              → useEffect [option, renderAnnotationGraphics] → requestAnimationFrame → renderAnnotationGraphics()
                → buildAnnotationChildren(chart, panels, objects, visibleAnnotations, ...)
                  → toPixelPoint() / toPixelX() → chart.convertToPixel()
```

## Failure Point
`toPixelPoint()` (line 192) calls `chart.convertToPixel(coordinateRef, [point.x, point.y])`. If the chart's coordinate system isn't ready (data not fully rendered in DOM), this returns NaN → function returns null → `buildAnnotationChildren` silently skips the annotation.

Similarly `toPixelX()` (line 202) wraps convertToPixel in try/catch, falls back to toPixelPoint, also returns null.

## Key Code Locations (EChartsWorkspaceRenderer.jsx)
- Line 445: `buildAnnotationChildren()` - iterates annotations, calls toPixelPoint/toPixelX
- Line 460: `if (!rect) return` - skips if grid rect unavailable
- Line 467: `if (!Number.isFinite(x)) continue` - skips panel if x conversion fails
- Line 192: `toPixelPoint()` - convertToPixel wrapper, returns null on failure
- Line 202: `toPixelX()` - convertToPixel with fallback, returns null on failure
- Line 825: `renderAnnotationGraphics()` - called via requestAnimationFrame after option change
- Line 1192: `data-alpha-ficc-annotation-count={visibleAnnotations.length}` - debug attribute

## workspacePanelId Mismatch
When Codex creates a workspace on the comparison page, the active workspace switches. Annotation actions use the active workspace (not the target.workspaceId in payload) to resolve panelIds. This causes INVALID_ANNOTATION_PANEL errors.

Error payload shows: `availablePanelIds: ["panel-codex-repro-main"]` vs `requestedPanelIds: ["panel-btc-gold", ...]`
