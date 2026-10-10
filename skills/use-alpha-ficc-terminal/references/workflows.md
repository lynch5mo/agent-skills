# Alpha-FICC Agent Workflows

## 1. Current Terminal Read

Use when the user asks what is on the open `/comparison` chart.

```bash
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex context
```

Expected successful summary fields:

- `contextId`
- `scopeKey`
- `workspaceId`
- `panelIds`
- `seriesIds`
- `formulaIds`
- `latestValues`
- `chartDataRequest`
- `dataAccessPolicy`

If the response is `AGENT_VISIBLE_CHART_CONTEXT_NOT_FOUND`, ask the user to open `/comparison`, load the chart, and use "分享给 Agent" or automatic sync. Do not call `/pending`.

## 2. Full Chart Data From Context

Use this after context read when analysis needs historical points.

```bash
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex chart-data
```

The command reads `context.chartDataRequest`, normalizes the endpoint, and requests data with `localFirst=true&dataPolicy=agent-local-first`.

For raw JSON:

```bash
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex chart-data --raw > /tmp/alpha-ficc-chart-data.json
```

## 3. Push Series To Live Comparison Terminal

Use when the user asks to generate or add a chart in the web terminal.

```bash
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex enqueue-series \
  --series yfinance:USDCNH=X fred:DTWEXBGS fred:DGS10 akshare:bond_china_cgb_10y \
  --formulas us_cn_spread \
  --window 3Y \
  --granularity D \
  --panel-mode appendPanel \
  --panel-title "人民币汇率压力框架" \
  --target-current-page
```

Use `--page-instance-id <id>` when the target page was selected from `GET /api/comparison/page-instances`. Without either targeting option, any open `/comparison` page can consume the action first.

Report:

- `POST /api/terminal-chart-actions`
- action type: `add_series_to_chart`
- series/formula ids and time window
- returned `actionId`
- ledger query endpoint: `GET /api/agent-actions/{actionId}`
- observation location: `/comparison`

## 4. Add Chart Annotations

Use when the user asks to mark causal steps, events, thresholds, or explanation groups on an existing chart.

Required sequence:

1. Read current context.
2. Confirm `workspace.workspaceId` and candidate `panelIds`.
3. If the chart was just created by an Agent action, prefer real panel ids from the applied ledger result.
4. Build an `add_chart_annotations` payload.
5. Post it with the same action queue.
6. Verify `GET /api/agent-actions/{actionId}` and optionally `GET /api/chart-annotations?workspaceId=...`.

Payload shape:

```json
{
  "actionId": "codex_annotation_usdcnh_20260611_001",
  "actionType": "add_chart_annotations",
  "source": "external-codex",
  "target": {
    "workspaceId": "workspace-from-context",
    "annotations": [
      {
        "annotationId": "ann_usdcnh_001",
        "panelId": "panel-from-context-or-applied-result",
        "kind": "vertical_time_marker",
        "date": "2026-05-26",
        "label": "共同时间分割",
        "text": "同一天跨 panel 标注，解释冲击传导。",
        "validationHint": {
          "seriesId": "fred:DGS10",
          "operator": ">",
          "threshold": 4
        }
      }
    ]
  }
}
```

Vertical time markers that explain a shared event should be repeated across all relevant panels.

## 5. Headless Render Job

普通聊天取图使用下节 `chart-image`，由 helper 负责创建、等待和下载。只有需要检查底层接口或 Hermes 投递时才手工提交本节 payload。`terminalScreenshot` 是兼容模式名，当前实现使用原有图表图片导出。

```json
{
  "jobId": "codex_render_rmb_pressure_20260611_001",
  "actionId": "codex_render_rmb_pressure_20260611_001",
  "source": "external-codex",
  "renderMode": "terminalScreenshot",
  "delivery": {
    "channel": "artifactOnly",
    "mode": "artifactOnly",
    "notify": false
  },
  "narrative": {
    "title": "人民币汇率压力框架",
    "summary": "USDCNH、美元指数、美国利率与中美利差的同屏比较。"
  },
  "target": {
    "seriesIds": ["yfinance:USDCNH=X", "fred:DTWEXBGS", "fred:DGS10"],
    "formulaIds": ["us_cn_spread"],
    "window": "3Y",
    "granularity": "D"
  }
}
```

Command:

```bash
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex post /api/agent-render-jobs --payload render-job.json
```

Then inspect:

```bash
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex get /api/agent-render-jobs/<jobId>
```

`notify=false`, top-level `sendTelegram=false`, and `channel=artifactOnly` all suppress Telegram delivery. The response echoes the effective `notify` value and `chartSummary`.

## 5A. chart-image：取当前图或按需生成并下载

### 准备与能力核对

`chart-image` 创建静默任务、等待有效产物、校验并下载 PNG，stdout 只有一条最终 JSON。普通出图不需要先查询 Agent-KB、推送网页 action 或打开用户浏览器。后台服务自己的隔离渲染环境不要求用户打开网页。

以下命令以本机 Codex 安装目录为例。将 `afc_skill_dir` 改为当前运行时实际加载的完整 Skill 目录，将 `afc_agent_id` 改为当前 Agent 的已注册身份。项目内使用时可将目录设为项目的 `skills/use-alpha-ficc-terminal`。脚本、references 与 assets 一起更新，不要只复制 `SKILL.md`。设备绑定凭据通过全局 `--device-id` 或已有环境配置指定。

```bash
afc_skill_dir="$HOME/.codex/skills/use-alpha-ficc-terminal"
afc_agent_id="codex"
uv run "$afc_skill_dir/scripts/alpha_ficc_terminal.py" --agent "$afc_agent_id" chart-image --help
```

先使用当前 Agent 自己的凭据与已确认的 API base。helper 没有 `chart-image` 时更新完整 Skill；服务版本未知时按本节导出事实核对。无浏览器生成、当前快照与聊天附件各自需要对应能力，不能把本地测试通过解释为生产已上线。

### 没开网页：按需求生成

四组来源互斥：当前图、显式序列或公式、生成规格或 raw workspace、已有 jobId。无参数默认取当前图；用户在外面要求新图时，显式传序列或生成规格，不使用这个默认来源。

只需指定指标与时间范围：

```bash
uv run "$afc_skill_dir/scripts/alpha_ficc_terminal.py" --agent "$afc_agent_id" chart-image \
  --series fred:DGS10 fred:DTWEXBGS --window 3Y --granularity M --out ./macro.png
```

默认参数是 3Y / D，只有用户未指定才补默认。服务端从终端数据层本地优先读取并固定数据；Agent 不直连 FRED 等数据商，不用当前页面判断本次生成的指标或范围。

需要指定面板、轴、线色、线型或标注时，使用配套的 [双面板生成规格模板](../assets/chart-generation-spec.example.json)：

```bash
cp "$afc_skill_dir/assets/chart-generation-spec.example.json" ./chart-generation-spec.json
uv run "$afc_skill_dir/scripts/alpha_ficc_terminal.py" --agent "$afc_agent_id" chart-image \
  --workspace-file ./chart-generation-spec.json --out ./two-panels.png
```

按用户需求修改任务目录中的规格，不修改已安装模板。规格包含 `schemaVersion=alpha-ficc-chart-generation-spec-v1`、`window`、`granularity` 和 `workspace`；面板在 `workspace.panels` 中定义，曲线在 `workspace.objects` 中以 `sourceId`、`panelId`、`axisSide`、`color`、`lineStyle` 等字段绑定。规格自己的 window/granularity 优先；更改范围时同时更新 workspace.timeWindow。新生成工作区可以定义自己的对象与面板 id；当前图取图必须使用快照中的真实 id。

标注放在 `workspace.annotations`。使用真实日期、数值和对象/坐标轴绑定，不能捏造坐标；支持范围和绑定规则见本文第 4 节。公式和运算只使用终端支持的 id/表达式；缺少必要数据或计算结果时报告失败，不删掉目标曲线后交付。

生成规格不携带 `renderSnapshotRef`。当前图引用由上下文来源解析，API 放在 `target` 或请求顶层并执行权限与快照校验；混合来源返回 `RENDER_SNAPSHOT_SOURCE_AMBIGUOUS`。

### 已有网页图：取快照或指定面板

当前图需要网页已发布完整快照。来源查询遵守当前上下文接口；多页面时用 `page-instances` 或上下文返回值选择真实页面与面板，不操作浏览器 React state。

```bash
uv run "$afc_skill_dir/scripts/alpha_ficc_terminal.py" --agent "$afc_agent_id" chart-image --out ./current.png
uv run "$afc_skill_dir/scripts/alpha_ficc_terminal.py" --agent "$afc_agent_id" chart-image \
  --page-instance <pageInstanceId> --panel <realPanelId> --out ./panel.png
uv run "$afc_skill_dir/scripts/alpha_ficc_terminal.py" --agent "$afc_agent_id" chart-image \
  --context <contextId> --out ./current.png
```

上下文来源不接受 `--window` / `--granularity` 覆盖；`--panel` 仅用于上下文来源。已接受任务的输入已经固定，来源页面之后更新或关闭不改变该任务。创建新任务时仍须能解析有权限、未过期的快照；没有快照不能声称还原了原图。

### 核对导出并附入聊天

默认终端图复用程序“保存图片”：`ChartWorkspace` → `chartImageExporterRef` → ECharts 导出与图例/品牌合成。只保留图表、坐标轴、图例、支持的标注和原有水印/品牌页脚；网页标题、筛选区、操作按钮和侧栏不进入图片。原有 exporter 自带的图表复位图标与底部缩放条沿用。

核对 CLI 的 `ok=true`、`fidelity=terminal`、`usedFallback=false`、有效 `verification` 和真实 `localPath`。`viewConsistency=generated` 表示按规格生成，`snapshot-replay` 表示当前图完整快照；不要把两者混报。查看图片确认用户要求的曲线、范围、面板及标注实际存在。

首次使用目标服务或排查旧图时，用实际 jobId 检查导出事实：

```bash
uv run "$afc_skill_dir/scripts/alpha_ficc_terminal.py" --agent "$afc_agent_id" get \
  "/api/agent-render-jobs/<jobId>" --auth
```

核对 job 的 `artifactReady=true`、`artifactProducedBy=chartImageExporterRef`、`exportMethod=chartImageExporterRef`、`usedScreenshotApi=false`、`exportOutputScope` 和实际 PNG 宽高/倍率。多面板导出是一张合成图片；真实单面板范围另有 `exportPanelScope` 标记。默认逻辑宽 1800、倍率 2，实际高度随面板变化；源网页 DPR 不能当作导出倍率。

这些导出字段在 job 查询结果中，当前 CLI 成功 JSON 不携带它们。只有 `renderMode=terminalScreenshot`、`screenshotStatus=captured` 或一个合法 PNG，不能证明调用了原有导出。缺少导出事实的新任务须报告服务版本或链路待核验，不能自行用网页截图替代。

下载、宿主附图是两个步骤。CLI 的 `imageDelivery=not_attempted` 不表示已经贴图：

- 本机 Codex：使用成功结果里的绝对 `localPath`，格式为 `![图表说明](</absolute/path/chart.png>)`；路径有空格时保留尖括号。
- 远端或手机聊天：由当前宿主的附件或媒体工具上传实际 PNG。宿主缺少这项能力时明确报告“已生成并下载，当前聊天尚未附图”，不把服务器路径或需要鉴权的 URL 当作可见图片。
- Hermes Telegram：在用户要求该渠道投递时，使用自己身份的 `send-artifact` 和 delivery-result 流程；普通 `chart-image` 使用 `delivery.notify=false`，不会自动发送 Telegram。

### 续取与连续改图

超时或下载中断保留 jobId；用原任务续取，不重新生成：

```bash
uv run "$afc_skill_dir/scripts/alpha_ficc_terminal.py" --agent "$afc_agent_id" chart-image \
  --job <jobId> --wait-timeout 300 --out ./same-artifact.png
```

改数据、范围、样式或标注时修改保存的规格，创建新 jobId。纯样式变化可复用已经保存的完整固定数据；没有保存数据时须说明新任务按数据层当前数据生成，不能承诺只改样式。旧 job 续取返回原文件，包括升级前的旧网页截图；要得到新导出必须新建任务。

同一 jobId 同内容可重试，内容或身份改变会冲突；`--job-id` 用于事先固定新任务编号，`--job` 用于续取。输出文件已存在时，选择新路径或明确使用 `--overwrite`。`--http-timeout` 是单次请求限制，`--wait-timeout` 是本次整体等待限制。

默认不接受简化降级。只有用户明确接受简化图时才用 `--allow-fallback` 或 `--mode chart`，并说明结果的实际 fidelity 与较低保真范围。失败按 `stage`、`errorCode`、`message`、`recoverable`、`jobId`、`lastJobStatus` 报告，恢复入口见 troubleshooting。

## 5B. 当前图完整快照发布与回放

网页 `/comparison` 在发布 agent-visible 上下文时，同一次发布携带 `renderSnapshot`：完整 workspace（面板、对象、轴、颜色、线型、单位、标注）、未预算的完整点集、按 objectId 的派生运算结果、实际可见范围与实际渲染区域尺寸和显示环境。

服务端保存不可变快照并返回 `renderSnapshotRef`。上下文摘要只带引用、修订与自描述能力：

```json
{
  "renderSnapshotRef": "render_snapshot_xxxxxxxx",
  "renderSnapshotMeta": {"dataRevision": "...", "workspaceRevision": "...", "panelIds": ["..."], "completeness": {"totalPoints": 3840}},
  "renderAvailability": {"renderable": true, "reasons": [], "panelIds": ["..."], "display": {"supported": true}},
  "renderRequest": {
    "endpoint": "/api/agent-render-jobs",
    "method": "POST",
    "target": {"contextId": "...", "pageInstanceId": "...", "renderSnapshotRef": "render_snapshot_xxxxxxxx"},
    "suggestedRenderMode": "terminalScreenshot",
    "supportedScopes": ["workspace", "panel"]
  }
}
```

创建任务时把 `target.renderSnapshotRef`（可加 `target.panelId`）交给 `POST /api/agent-render-jobs`，并带 `strictData` 与 `delivery.notify=false`。服务端在创建时解析并固定快照；之后页面更新、关闭或上下文过期都不改变已接受任务，也不会重新取最新行情。

固定显示环境：回放按快照记录的 viewport、设备像素比、主题、语言和实际渲染根宽度恢复图表状态。渲染根是 flex 子元素，回放同时固定 flex 基线与宽度；无法复现时返回 `DISPLAY_NOT_REPRODUCED`。就绪后的图片导出及聊天附图沿用第 5A 节流程。

panel 取图只保留该真实面板及其对象、轴和标注，id 不变；workspace 默认整张工作区。

## 6. Catalog Search

Use catalog endpoints to discover chartable ids, then pass ids to chart-data or chart actions.

```bash
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py get "/api/data-search?q=DGS10&page=1&pageSize=10"
```

For production table search:

```bash
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py get "/api/data-catalog/series?q=DGS10&page=1&pageSize=10"
```

For comparison catalog items, pass a known `path` from `/api/comparison/catalog/tree`:

```bash
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py get "/api/comparison/catalog/items?path=美国/利率与债券/国债收益率&page=1&pageSize=20&availability=with_data"
```

## 7. V4/V5 Research OS

Use repository smoke scripts for contract verification:

```bash
docker exec alpha-ficc-api python scripts/verify_v5_research_os_contract.py --base-url http://127.0.0.1:8001 --agent hermes --timeout 20
docker exec alpha-ficc-api python scripts/verify_v5_research_os_scheduler.py --base-url http://127.0.0.1:8001 --agent hermes --timeout 20
docker exec alpha-ficc-api python scripts/verify_v5_research_os_digest.py --base-url http://127.0.0.1:8001 --agent hermes --timeout 20
docker exec alpha-ficc-api python scripts/verify_v4_observation_revision_loop.py --base-url http://127.0.0.1:8001 --agent hermes --timeout 60
```

Replace `--agent hermes` with `--agent codex`, `--agent claude`, `--agent pi-agent`, `--agent deepseek-harness`, or `--agent reasonix` when validating those identities.

## 8. Knowledge-To-Observation Loop

Use this when the user asks for research, interpretation, learning from the knowledge base, or an observation model.

1. Run KB preflight and search.
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py kb-preflight
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py kb-search "人民币 压力 美债 美元" --domain finance
   ```
2. Read only the relevant KB summaries or drafts from the canonical Agent-KB path.
3. Extract claims with source paths and confidence.
4. Convert claims into a `KnowledgeFrameworkSpec`.
5. Convert the framework into an observation model:
   - watch variables
   - expected direction
   - regime conditions
   - validation window
   - invalidation conditions
   - chart series/formula ids
6. Fetch terminal data and chart the observables.
7. If the observation should persist, use V4/V5 proposals rather than directly editing KB `wiki/`.

See `references/knowledge-loop.md` for the full contract.

## 9. New Agent Onboarding

Do not reuse existing tokens.

The current canonical ids are `codex`, `hermes`, `claude`, `pi-agent`, `deepseek-harness`, and `reasonix`.

1. Pick a lowercase canonical Agent id.
2. Register the Agent id in `scripts/lib/external_agents.py` plus the token/scope env maps.
3. Keep the Agent-level token/scope env vars for legacy or single-device use, for example `ALPHA_FICC_PI_AGENT_TOKEN`.
4. For multi-device Agents, issue one device credential per machine:

```bash
python3 scripts/provision_external_agent_token.py --agent pi-agent --device-id mac
python3 scripts/provision_external_agent_token.py --agent pi-agent --device-id ubuntu-desktop
python3 scripts/provision_external_agent_token.py --agent deepseek-harness --device-id android --scopes research:read,render:create,render:read
```

For Hermes, add one or more `--hermes-env-file` paths so the device token is written into the Hermes profile environment automatically:

```bash
python3 scripts/provision_external_agent_token.py --agent hermes --device-id ubuntu-desktop \
  --hermes-env-file ~/.hermes/profiles/codex/.env \
  --hermes-env-file ~/.alpha-ficc/agent.env
```

5. The provisioner writes a device entry into `ALPHA_FICC_AGENT_CREDENTIALS` and a local `0600` file such as `~/.alpha-ficc/pi-agent.mac.token`; never print the secret.
6. Pass `ALPHA_FICC_AGENT_CREDENTIALS` through `docker-compose.alpha.yml` and the production server `.env`.
7. Install the Skill helper for that Agent and use `--agent <id> --device-id <device>` so the helper sends `X-Alpha-FICC-Device` and selects the device token file.
8. Rebuild/restart API.
9. Verify context read, chart action, ledger, render job if needed, V4, and V5.
10. Write a project report and Agent-KB runtime summary if this is a substantive completed task.
