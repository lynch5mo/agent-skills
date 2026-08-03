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
  --panel-title "人民币汇率压力框架"
```

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

Use when the user is not watching the live web terminal or needs a Telegram/mobile artifact.

```json
{
  "jobId": "codex_render_rmb_pressure_20260611_001",
  "actionId": "codex_render_rmb_pressure_20260611_001",
  "source": "external-codex",
  "renderMode": "terminalScreenshot",
  "delivery": {
    "channel": "telegram",
    "mode": "artifactOnly"
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

Replace `--agent hermes` with `--agent codex` or `--agent claude` when validating those identities.

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

1. Pick a lowercase Agent id.
2. Add `ALPHA_FICC_<AGENT>_AGENT_TOKEN`.
3. Add `ALPHA_FICC_<AGENT>_AGENT_SCOPES`.
4. Register the Agent id in the server allowlist.
5. Rebuild/restart API.
6. Verify context read, chart action, ledger, render job if needed, V4, and V5.
7. Write a project report and Agent-KB runtime summary if this is a substantive completed task.
