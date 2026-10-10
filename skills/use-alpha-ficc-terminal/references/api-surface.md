# Alpha-FICC Agent API Surface

Use this as a routing map. Prefer the high-level workflow in `SKILL.md` first.

## Base URLs

| Context | Base |
| --- | --- |
| API container or server host | `http://127.0.0.1:8001` |
| Public web proxy | `https://alpha-ficc.lynch5mo.xyz/api` |
| LAN web proxy | `http://192.168.10.33:5174/api` |

The helper script accepts either style. If the base ends with `/api`, pass endpoints as `/api/...` or without `/api`; the script normalizes the URL.

## Auth

| Caller | Headers |
| --- | --- |
| External Agent | `Authorization: Bearer <agent-token>` plus `X-Alpha-FICC-Agent: <agent-id>`; add `X-Alpha-FICC-Device: <device-id>` for device-bound credentials |
| Browser/user | login token or web session |

Token environment variables:

```text
ALPHA_FICC_CODEX_AGENT_TOKEN
ALPHA_FICC_HERMES_AGENT_TOKEN
ALPHA_FICC_CLAUDE_AGENT_TOKEN
ALPHA_FICC_PI_AGENT_TOKEN
ALPHA_FICC_DEEPSEEK_HARNESS_AGENT_TOKEN
ALPHA_FICC_REASONIX_AGENT_TOKEN
ALPHA_FICC_AGENT_CREDENTIALS
ALPHA_FICC_<NEW_AGENT>_AGENT_TOKEN
ALPHA_FICC_AGENT_TOKEN
ALPHA_FICC_TOKEN_FILE
```

Never print token values or derived token fingerprints.

## Current Context And Data

| Capability | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| Current `/comparison` context | `GET /api/comparison/current/context` | user or Agent | Alias for latest `scopeKey=comparison:current`; writes receipt for Agent reads. |
| Active comparison page instances | `GET /api/comparison/page-instances?activeWithinSeconds=300` | user or Agent | Read-only heartbeat list for targeted pushes. Contains page labels, workspace ids, panel counts, timestamps, and consumer client identity, not chart values. |
| Current crypto context | `GET /api/crypto-market/current/context` | user or Agent | Alias for latest `scopeKey=crypto-analysis:current`. |
| Full chart data | `GET /api/comparison/current/chart-data` | public read, use Agent contract | Use `context.chartDataRequest`; set `localFirst=true&dataPolicy=agent-local-first`. |
| Crypto market overview | `GET /api/crypto-market/overview` | public read | Live snapshot, not production observation write. |

## Catalog And Data Discovery

| Capability | Endpoint | Notes |
| --- | --- | --- |
| Comparison tree | `GET /api/comparison/catalog/tree` | Use for chartable hierarchy. |
| Comparison catalog items | `GET /api/comparison/catalog/items?path=...` | List/select series under a known tree path. |
| Unified catalog | `GET /api/data-catalog/series` | PostgreSQL-backed terminal table. |
| Unified search | `GET /api/data-search?q=...` | General read-only search by query string. |
| Observations | `GET /api/data-catalog/observations?seriesKey=...` | Read-only observation lookup. |
| Component datasets | `GET /api/component-datasets` | Governed component dataset inventory. |
| Component chart data | `GET /api/component-datasets/chart-data?group=...` | Dedicated component payloads. |
| Provider native roots/tree/nodes | `/api/provider-native/*` | Provider inventory, read-only. |
| Chart datafeed series | `GET /api/chart-datafeed/series` | Lower-level line chart data. |
| Yield surface | `GET /api/chart-datafeed/yield-surface` | Curve surface payload. |

## Knowledge And Research Model Loop

| Capability | Surface | Notes |
| --- | --- | --- |
| Canonical Agent-KB read | `/Users/lynch5mo/Work Documents/LLM/agent-kb` | Local repo, summary-first knowledge plane. Preflight before read/write. |
| KB preflight | `alpha_ficc_terminal.py kb-preflight` | Verifies canonical path and git state; network pull remains a separate explicit operation. |
| KB search | `alpha_ficc_terminal.py kb-search <query> --domain finance` | Local read-only search over `wiki/`, `write/`, and `outputs/`. |
| Run analysis | `POST /api/actions/run-analysis` | Artifact-first execution path when model specs are available. |
| Research model proposal | `POST/GET /api/model-proposals` | Proposal path; governance applies. |
| Research models | `POST/GET /api/research-models` | Model library surface; do not silently overwrite old versions. |
| Research loop V1 | `POST/GET /api/research-loop/v1/proposals` | Market-verified proposal loop. |
| Research loop V2 | `/api/research-loop/v2/cases`, `/models/from-v1-proposal`, `/runs`, `/runs/{id}/validate` | Case/model/run/validation loop. |
| Workspace sessions | `POST/GET /api/workspace-sessions` | Artifact/workspace continuation context. |

## Terminal Chart And Annotation Actions

| Capability | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| Queue chart action | `POST /api/terminal-chart-actions` | external Agent token | Supports `add_series_to_chart`, `add_chart_annotations`, `remove_chart_annotations`, and `remove_chart_panel`. Use optional `target.pageInstanceId` for page-targeted delivery. Panel removal targets must include `workspaceId`, `panelId`, and optional `reason`; the server resolves one owner only from a unique applied `add_series_to_chart` result `createdPanelIds` diff and accepts only that authenticated Agent. |
| Action ledger | `GET /api/agent-actions/{actionId}` | user or Agent | Source of truth for `queued/delivered/applied/failed/cancelled`. |
| Action list | `GET /api/agent-actions?source=external-codex&limit=20` | user or Agent | Use for recent records; not a queue drain. |
| Cancel queued action | `POST /api/agent-actions/{actionId}/cancel` | user or Agent | Cannot cancel already final actions. |
| Browser queue drain | `GET /api/terminal-chart-actions/pending` | browser user | Do not call from Agent unless deliberately simulating browser consumption. |
| Chart annotations | `GET /api/chart-annotations?...&includeArchived=false` | user or Agent | Query active applied annotations by default; `includeArchived=true` returns the latest archived tombstones for audit. Detail GET follows the same default. This is append-only projection, not physical DELETE. |
| Archive chart annotations | `POST /api/chart-annotations/archive` | authenticated browser user or external Agent token | Body is target-shaped: `workspaceId`, non-empty `annotationRefs`, optional `reason`. External Agents may archive only their own unlocked records; browser users may archive unlocked records. |
| Review packet | `GET /api/chart-annotation-review-packet?...` | user or Agent | Creates review context from annotations. |
| Rule compilation | `POST /api/chart-annotation-rule-compilations` | external Agent token | V3 annotation-to-rule path. |
| Validation run | `POST /api/chart-annotation-validation-runs` | external Agent token | V3 rule validation path. |

`add_chart_annotations` requires an explicit y-axis binding for every annotation
except `vertical-line`: provide at least one of `objectId`, `sourceId`, or
`axisId`. `axisSide` is auxiliary display metadata and is not a binding. The
stable binding errors are `ANNOTATION_AXIS_BINDING_REQUIRED`,
`ANNOTATION_AXIS_BINDING_NOT_FOUND`, and `ANNOTATION_AXIS_BINDING_AMBIGUOUS`.
Legacy resolution is retained only for already-stored single-axis annotations
whose target panel has exactly one unique visible axis; new external actions
must provide an explicit binding.

`remove_chart_annotations` rejects mixed refs atomically (no partial tombstones).
Stable archive errors are `ANNOTATION_OWNER_MISMATCH`, `ANNOTATION_LOCKED`,
`AMBIGUOUS_ANNOTATION_ID`, `ANNOTATION_WORKSPACE_MISMATCH`, and
`CHART_ANNOTATION_NOT_FOUND`. Repeating an already archived ref is idempotent
and reports `alreadyArchived` without appending another tombstone.

`remove_chart_panel` is an atomic cascade: the selected panel, every object in
that panel, and every unlocked annotation in that panel disappear together;
objects are never moved to another panel. The final panel is protected. Stable
panel errors are `LAST_PANEL_REMOVAL_FORBIDDEN`, `PANEL_NOT_FOUND`,
`PANEL_HAS_LOCKED_ANNOTATIONS`, `PANEL_OWNERSHIP_REQUIRED`, and
`PANEL_OWNER_MISMATCH`. Agent ownership is resolved only from a unique,
applied `add_series_to_chart` result whose browser-computed
`createdPanelIds` contains the requested panel and whose `workspaceId` matches;
target snapshots, `result.workspace`, and full `result.panelIds` are not
creation evidence. Unknown, legacy (missing `createdPanelIds`), or conflicting
history is rejected.
The browser stages the cascade, reports `removedAnnotationRefs` for append-only
tombstones, and commits local state only after the server reports an applied
ledger event. Moving panel contents is not part of deletion; a future move
operation must use a distinct action.

## Headless Render And Telegram

| Capability | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| Create render job | `POST /api/agent-render-jobs` | external Agent token | Use when browser terminal is offline or mobile output is needed. Set `delivery.notify=false` or top-level `sendTelegram=false` for silent rendering. Response includes `chartSummary`. |
| Get render job | `GET /api/agent-render-jobs/{jobId}` | user or Agent | Inspect status/artifacts. |
| Download PNG | `GET /api/agent-render-jobs/{jobId}/artifact?kind=terminal|chart` | user or Agent | Protected artifact API. `fallback` is accepted as a compatibility alias for `chart`. |
| Telegram send artifact | `POST /api/telegram/send-artifact` | Hermes token | Hermes-only retry/send. |
| Delivery result | `POST /api/agent-render-jobs/{jobId}/delivery-result` | Hermes token | Local relay feedback. |

### 当前图完整快照与 chart-image

| Capability | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| Publish context with snapshot | `POST /api/agent-visible-chart-contexts` | user or Agent | 同一次发布携带 `renderSnapshot`（完整 workspace、完整点集、按 objectId 的派生结果、可见范围、显示环境与渲染根尺寸）。响应返回 `renderSnapshotRef`、`renderAvailability`、`renderRequest`。该路由 body 上限为 `ALPHA_FICC_MAX_RENDER_SNAPSHOT_BYTES`（默认 16MB），与全局 1MB 分开。 |
| Read current context | `GET /api/comparison/current/context` | user or Agent | 摘要只带 `renderSnapshotRef`、`renderSnapshotMeta`、`renderAvailability`、`renderRequest`，不携带点集。 |
| Read one context | `GET /api/agent-visible-chart-contexts/{contextId}` | user or Agent | 遵守 visibility，不可见或过期返回 NOT_FOUND。 |
| List active pages | `GET /api/comparison/page-instances?activeWithinSeconds=300` | user or Agent | 每项含 `contextId`、`renderSnapshotRef`、`renderAvailability`、`renderRequest`、`panelIds`，用于指定真实页面而不猜测。 |
| Create snapshot job | `POST /api/agent-render-jobs` with `target.renderSnapshotRef` | external Agent token | 需要 `render:create`；带快照引用时还需要 `research:read`，并按上下文 visibility 与 expiry 校验。创建时固定快照；`viewConsistency=snapshot-replay`。 |
| Job artifact | `GET /api/agent-render-jobs/{jobId}/artifact?kind=terminal|chart` | user or Agent | 只发布实际有效 PNG 的 URL。 |

`renderMode=terminalScreenshot` 保留为兼容协议字段，实际取图复用程序已有“保存图片”导出功能，产物是图表 PNG，含图例、支持的标注与原有品牌页脚。页面标题、筛选区、按钮、工具栏与侧栏不进入图片；后台回放页面只是恢复固定输入的运行环境。

### 图表图片导出事实与能力检查

`chart-image` 对普通 Agent 封装创建、等待和下载；手工 API 主要用于接口诊断。显式序列/生成规格不要求当前页面；只有当前图来源解析 `renderSnapshotRef`。图表原有导出方法保持复用，静默任务不会修改用户网页。

`GET /api/agent-render-jobs/{jobId}` 返回实际任务事实，使用 `render:read` 和当前 Agent 自己的凭据：

| 字段 | Agent 应如何判断 |
| --- | --- |
| `artifactReady`、`artifactUrl` | 有效产物已经发布；下载仍须鉴权 |
| `fidelity`、`usedFallback` | 默认期望 `terminal`、`false`；简化图须明确说明 |
| `viewConsistency` | 规格生成为 `generated`；完整快照回放为 `snapshot-replay` |
| `artifactProducedBy`、`exportMethod` | 原有保存图片导出均为 `chartImageExporterRef` |
| `usedScreenshotApi` | 原有导出应为 `false` |
| `exportOutputScope`、`exportPanelScope` | 工作区图表合成范围，以及是否过滤了真实单面板 |
| `exportWidth`、`exportHeight`、`exportPixelRatio` | 实际 PNG 尺寸与导出倍率；不从网页 DPR 推断 |
| `screenshotStatus` | 兼容状态字段，不能单独证明图片来源或输出范围 |

CLI 成功 JSON 返回 jobId、来源、保真度、localPath、verification 与 `imageDelivery=not_attempted`，当前不返回 exportMethod 等导出字段；需要时按 jobId 查询。旧 job 不会因服务升级重新导出；新功能验收应新建任务。

目标服务未部署、helper 缺少 `chart-image`，或新任务没有导出事实时报告实际能力缺口。不要改调用模式制造成功，也不要把 `terminalScreenshot` 当作截图 API 使用许可。

### 当前图请求示例

```json
{
  "jobId": "agent_render_codex_20261009_...",
  "renderMode": "terminalScreenshot",
  "strictData": true,
  "delivery": {"channel": "artifactOnly", "notify": false},
  "target": {
    "renderSnapshotRef": "render_snapshot_xxxxxxxx",
    "contextId": "...",
    "pageInstanceId": "...",
    "panelId": "optional-real-panel-id"
  }
}
```

快照存储：`runtime/agent_render_snapshots.jsonl`，可用环境变量 `ALPHA_FICC_AGENT_RENDER_SNAPSHOTS_PATH` 重定向。同一 snapshotRef 内容不同会被拒绝（`RENDER_SNAPSHOT_REF_CONFLICT`），相同内容重试幂等。

## V4 Observation And Revision Loop

| Capability | Endpoint | Auth |
| --- | --- | --- |
| External evidence | `POST /api/external-evidence` | external Agent token |
| Assess evidence | `POST /api/external-evidence/{evidenceId}/assess` | external Agent token |
| Impact mapping | `POST /api/impact-mappings` | external Agent token |
| Observation task | `POST /api/observation-tasks` | external Agent token |
| Run observation | `POST /api/observation-tasks/{taskId}/run` | external Agent token |
| Revision proposal | `POST /api/revision-proposals` | external Agent token |
| Accept/reject revision | `POST /api/revision-proposals/{id}/accept|reject` | operator/admin only |

## V5 Research OS

| Capability | Endpoint | Auth |
| --- | --- | --- |
| Watch policy | `POST/GET /api/model-watch-policies` | user or Agent depending route |
| Evaluate policy | `POST /api/model-watch-policies/{policyId}/evaluate` | Agent supported |
| Run plan execute/cancel | `POST /api/autonomous-run-plans/{runPlanId}/execute|cancel` | Agent supported; cancel-own boundary |
| Replay run | `POST /api/autonomous-runs/{autonomousRunId}/replay` | Agent supported |
| Health recompute | `POST /api/model-health-scores/recompute` | Agent supported |
| Digest create/send | `POST /api/research-daily-digests`, `POST /api/research-daily-digests/{digestId}/send` | Agent supported |
| Promotion proposal | `POST /api/knowledge-promotion-proposals` | Agent supported |
| Accept/reject promotion | `POST /api/knowledge-promotion-proposals/{id}/accept|reject` | operator/admin only |
| Scheduler tick | `POST /api/research-os/scheduler/tick` | scoped Agent allowed only with bounded `limit <= 1` |
