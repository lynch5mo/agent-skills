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
| External Agent | `Authorization: Bearer <agent-token>` plus `X-Alpha-FICC-Agent: <agent-id>` |
| Browser/user | login token or web session |

Token environment variables:

```text
ALPHA_FICC_CODEX_AGENT_TOKEN
ALPHA_FICC_HERMES_AGENT_TOKEN
ALPHA_FICC_CLAUDE_AGENT_TOKEN
ALPHA_FICC_<NEW_AGENT>_AGENT_TOKEN
ALPHA_FICC_AGENT_TOKEN
ALPHA_FICC_TOKEN_FILE
```

Never print token values or derived token fingerprints.

## Current Context And Data

| Capability | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| Current `/comparison` context | `GET /api/comparison/current/context` | user or Agent | Alias for latest `scopeKey=comparison:current`; writes receipt for Agent reads. |
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
| Queue chart action | `POST /api/terminal-chart-actions` | external Agent token | Supports `add_series_to_chart` and `add_chart_annotations`. |
| Action ledger | `GET /api/agent-actions/{actionId}` | user or Agent | Source of truth for `queued/delivered/applied/failed/cancelled`. |
| Action list | `GET /api/agent-actions?source=external-codex&limit=20` | user or Agent | Use for recent records; not a queue drain. |
| Cancel queued action | `POST /api/agent-actions/{actionId}/cancel` | user or Agent | Cannot cancel already final actions. |
| Browser queue drain | `GET /api/terminal-chart-actions/pending` | browser user | Do not call from Agent unless deliberately simulating browser consumption. |
| Chart annotations | `GET /api/chart-annotations?...` | user or Agent | Query stored applied annotations. |
| Review packet | `GET /api/chart-annotation-review-packet?...` | user or Agent | Creates review context from annotations. |
| Rule compilation | `POST /api/chart-annotation-rule-compilations` | external Agent token | V3 annotation-to-rule path. |
| Validation run | `POST /api/chart-annotation-validation-runs` | external Agent token | V3 rule validation path. |

## Headless Render And Telegram

| Capability | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| Create render job | `POST /api/agent-render-jobs` | external Agent token | Use when browser terminal is offline or mobile output is needed. |
| Get render job | `GET /api/agent-render-jobs/{jobId}` | user or Agent | Inspect status/artifacts. |
| Download PNG | `GET /api/agent-render-jobs/{jobId}/artifact?kind=terminal` | user or Agent | Protected artifact API. |
| Telegram send artifact | `POST /api/telegram/send-artifact` | Hermes token | Hermes-only retry/send. |
| Delivery result | `POST /api/agent-render-jobs/{jobId}/delivery-result` | Hermes token | Local relay feedback. |

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
