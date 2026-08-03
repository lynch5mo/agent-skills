# Annotation Workspace ID 匹配陷阱 (2026-06-03)

## 问题描述

标注 push 返回 ok=true, applied，annotation store 里有 active 记录，但图表上看不到标注。

## 根因

标注绑定的 workspaceId 与 comparison 页面当前显示的 workspace 不一致。

## 场景复现

### 场景 1：replaceSelection 创建新 workspace

1. Agent 推 chart action（`replaceSelection: true`）→ 创建新 workspace `ws_btc_push_xxx`
2. comparison 页面仍显示旧 workspace `ws_btc_final_yyy`
3. Agent 推 annotations → 绑定到 `ws_btc_push_xxx`
4. 用户在 `ws_btc_final_yyy` 上看不到标注

### 场景 2：Codex 调试创建了新 workspace

1. Codex 调试时创建了 `ws-codex-repro-annotation`
2. comparison 页面切到了该 workspace
3. Agent 的标注推到 `ws_btc_final_...`，但页面在 `ws-codex-repro-annotation`
4. 报 `INVALID_ANNOTATION_PANEL: panelId does not exist in resolved workspace`
5. 错误信息显示 `availablePanelIds: ["panel-codex-repro-main", ...]`

## 正确做法

```python
# 1. 推 chart action
chart_resp = POST /api/terminal-chart-actions (add_series_to_chart)
chart_action_id = chart_resp["action"]["actionId"]

# 2. 等 applied
poll_until_applied(chart_action_id)

# 3. MUST 读当前 context 拿活跃 workspaceId
context_resp = GET /api/comparison/current/context
ws_id = context_resp["context"]["workspace"]["workspaceId"]
# ⚠️ 不要用 chart action response 里的 workspaceId！

# 4. 推标注到活跃 workspace
POST /api/terminal-chart-actions (add_chart_annotations, target.workspaceId = ws_id)
```

## 排查清单

1. `GET /api/comparison/current/context` → 检查 `workspace.workspaceId`
2. `GET /api/chart-annotations?actionId=...` → 检查 annotation 的 `workspaceId`
3. 两者是否一致？如果不一致，标注在正确的 workspace 里但页面在另一个 workspace

## Annotation 渲染时序 Bug (2026-06-03, Codex 修复)

### 现象

标注入库成功（annotation store 里有 active 记录），但图表上看不到。

### 根因

`renderAnnotationGraphics` 在 ECharts 坐标系统就绪前被调用，`toPixelPoint()`/`toPixelX()` 坐标转换全部返回 null，标注被静默跳过。

### 前端链路

```
setOpenWorkspaceIntent (含 annotations)
  → ChartWorkspace useEffect → normalizeOpenedWorkspace() → dispatch SET_WORKSPACE
    → state.annotations 更新 → visibleAnnotations useMemo → renderAnnotationGraphics
      → buildAnnotationChildren() → toPixelPoint() 坐标转换 ← 此处失败
```

### 关键代码位置

- `EChartsWorkspaceRenderer.jsx` line 825: `renderAnnotationGraphics` useCallback
- `EChartsWorkspaceRenderer.jsx` line 810: `visibleAnnotations` useMemo
- `EChartsWorkspaceRenderer.jsx` line 445: `buildAnnotationChildren` function
- `EChartsWorkspaceRenderer.jsx` line 192: `toPixelPoint` → `chart.convertToPixel()` 失败返回 null
- `EChartsWorkspaceRenderer.jsx` line 202: `toPixelX` → 同上

### 修复方向

在 `renderAnnotationGraphics` 中检测如果 `visibleAnnotations.length > 0` 但渲染 children 为空时，延迟重试或监听 chart `finished` 事件。

### 排查方法

1. 检查 annotation store：`GET /api/chart-annotations?actionId=...` 确认 status=active
2. 检查 chart container 的 `data-alpha-ficc-annotation-count` 属性是否 > 0
3. 检查 comparison context 的 workspaceId 是否与标注绑定的 workspaceId 一致
