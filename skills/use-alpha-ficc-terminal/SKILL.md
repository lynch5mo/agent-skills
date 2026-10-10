---
name: use-alpha-ficc-terminal
description: "用于操作或排查 Alpha-FICC 终端：读取当前图表和本地优先数据，推图或标注，通过 chart-image 生成或获取图表 PNG 并在聊天中附图，以及与终端相关的 Agent-KB、V4/V5 研究和 scoped Agent 接入。单纯知识库查询、金融概念问答或一般 Telegram 排障不触发。"
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
---

# Use Alpha-FICC Terminal

## 图表图片：先选择入口

| 用户意图 | Agent 使用方式 |
| --- | --- |
| 没开网页，按需求生成图并贴在聊天中 | `chart-image --series ...`；需要指定面板、轴、颜色或标注时用 `--workspace-file` 生成规格 |
| 把当前网页图发来 | `chart-image` 默认读取当前图的完整快照；指定页面用 `--context` 或 `--page-instance` |
| 只取当前图中的一个面板 | 上下文来源加 `--panel`，使用该快照里的真实 panelId |
| 上次等待或下载中断，继续取同一张图 | `chart-image --job <jobId>`，保留原任务编号 |
| 改数据、时间范围、颜色或标注后重新出图 | 修改保存的生成规格并创建新任务；旧 job 续取只返回原产物 |
| 修改正在打开的网页图表 | `enqueue-series` 或图表标注 action，并按 actionId 核对 applied 结果 |

图表图片复用程序已有“保存图片”导出。后台页面恢复固定输入后调用原 exporter，产物只含图表及原有导出元素，不使用页面或 DOM 截图，也不在导出失败时改用截图。`terminalScreenshot` 是兼容协议名，不能按字面把它理解成网页截图。

仅生成或取图时直接走本节入口；知识检索、观察模型和 V4/V5 只在用户的研究任务需要时执行。无浏览器生成使用显式来源，不依赖当前页面或网页 action 队列。

具体命令、可复制的双面板规格、结果核对和聊天附图步骤见 [references/workflows.md](references/workflows.md) 的第 5A 节；失败恢复见 [references/troubleshooting.md](references/troubleshooting.md)。先核对实际 helper 是否有 `chart-image`、当前服务的新 job 是否返回导出事实，不能用本地验收记录代替部署能力检查。

## Core Contract

Treat Alpha-FICC as a governed financial terminal, not as a generic web data scraper.

- Use the current Agent identity (`codex`, `hermes`, `claude`, `pi-agent`, `deepseek-harness`, `reasonix`, or a newly approved Agent id) and that Agent's own scoped token.
- Keep the Agent type identity and device credential separate: one Agent id may have multiple device-bound tokens. The device id is not a new Agent type.
- When a device credential is bound, send `X-Alpha-FICC-Device: <device-id>`. Never reuse one device token on another device.
- Do not print token values, token lengths, token hashes, prefixes, passwords, cookies, or admin/operator credentials.
- Treat `/Users/lynch5mo/Work Documents/LLM/agent-kb` as the only valid macOS Agent-KB repository. Never use quarantined or stale copies.
- For financial research that needs internal knowledge, retrieve relevant Agent-KB sources and connect claims to an observation model. Ordinary chart operations and connectivity diagnosis do not require this research loop.
- Keep KB writes proposal-first. Agent may create knowledge promotion or revision proposals; do not directly write Agent-KB `wiki/` or accept/reject governance decisions.
- Read the user's current terminal chart through `GET /api/comparison/current/context`; never inspect browser state directly.
- List active comparison page instances through `GET /api/comparison/page-instances` when more than one browser page may be open.
- Treat `agentId` / `deviceId` as the action producer and `consumerClientId` / `consumerDeviceLabel` as the browser page that consumes the action. They are different identities when an Agent pushes to another device.
- Fetch complete current-chart data through `GET /api/comparison/current/chart-data` using `context.chartDataRequest`. For explicit chart generation, let the render service resolve and freeze terminal data.
- Do not call provider APIs such as FRED, Yahoo, Akshare, BEA, BLS, or EIA directly from the Agent path.
- Queue terminal chart work through `POST /api/terminal-chart-actions`; verify through `GET /api/agent-actions/{actionId}`.
- Do not call `GET /api/terminal-chart-actions/pending` during normal Agent work. It drains the browser queue.
- Use real `workspaceId`, `pageInstanceId`, and `panelId` from current context or applied ledger results. Do not hardcode panel ids.
- Agent-created proposals are allowed where scoped; accept/reject governance actions remain operator/admin decisions.
- Any custom HTTP client must send an explicit `User-Agent`. Python `urllib` default UA is blocked by Cloudflare with `error code: 1010`.
- Record separately whether an image was rendered, downloaded and delivered into the current chat. A download means a valid local file exists; `imageDelivery=not_attempted` means the host still has to attach it.
- Treat `renderSnapshotRef` as the only proof of a reproducible current chart. A non-empty reference is not enough: the snapshot must carry full points, the real workspace, panels and the actual display environment.

## Local Token Files

The Skill helper auto-discovers the current Agent's local token file when `--token-file` is omitted:

```text
~/.alpha-ficc/codex-agent.token
~/.alpha-ficc/claude-agent.token
~/.alpha-ficc/pi-agent.token
~/.alpha-ficc/deepseek-harness.token
~/.alpha-ficc/reasonix.token
```

For device-bound credentials, prefer the device-specific file before the Agent-level fallback:

```text
~/.alpha-ficc/deepseek-harness.mac.token
~/.alpha-ficc/deepseek-harness.android.token
```

When no device id is supplied and exactly one device-specific file exists, the helper selects it automatically. Pass `--device-id` explicitly when more than one device credential is present.

Hermes continues to use its existing `ALPHA_FICC_HERMES_AGENT_TOKEN` environment. Never print token values, token lengths, prefixes, or hashes.

## Workflow

只执行当前目标需要的步骤。普通终端动作不自动附加知识库研究或写入；读取资料不授权 pull、归档、提交或推送。相同会话中环境未变的健康结果可以复用，图表或图片结果仍按实际 actionId 或 jobId 核验。

1. Establish base URL and identity.
   Use `ALPHA_FICC_API_BASE_URL` or `ALPHA_FICC_BASE_URL`, and set `ALPHA_FICC_DEVICE_ID` when this device has its own credential. Server-local API usually uses `http://127.0.0.1:8001`; web proxy bases often end with `/api`, such as `https://alpha-ficc.lynch5mo.xyz/api` or `http://192.168.10.33:5174/api`.

2. Run a non-secret health check.
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex health
   ```

3. Retrieve relevant internal knowledge when the requested financial research or observation-model construction needs it. Ordinary chart reads, image export and network diagnosis skip this step.
   从 canonical 仓库检查路径和状态，再检索相关知识。先确认 preflight 工具的副作用；只读任务不得调用会 pull、写配置或同步的入口，可用只读 git status 替代同步型 preflight。
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py kb-preflight
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py kb-search "黄金 actual rate Money View" --domain finance
   ```
   Convert useful KB material into `InternalKnowledgeSource`, `ExtractedClaim`, `KnowledgeFrameworkSpec`, and only then into an observation model. See `references/knowledge-loop.md`.

4. Read the current chart context before reasoning about the user's open terminal chart.
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex context
   ```

5. Fetch complete chart data from the context request when calculations need real history.
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex chart-data
   ```

6. Bind knowledge-derived hypotheses to terminal data and model observables.
   Use KB claims to choose variables, expected directions, regimes, invalidation conditions, and validation windows. Use terminal data to test whether the current market state supports, contradicts, or leaves the model inconclusive.

7. Push a chart to the live `/comparison` terminal when the user wants visible terminal state changes.
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex enqueue-series \
     --series yfinance:USDCNH=X fred:DTWEXBGS fred:DGS10 \
     --formulas us_cn_spread \
     --window 3Y \
     --granularity D \
     --panel-title "人民币汇率压力框架" \
     --target-current-page
   ```
   `--target-current-page` reads the current context, verifies that the page still has a recent heartbeat, and binds the action to that page instance. It avoids another open `/comparison` page stealing the action. If no recent heartbeat exists, refresh `/comparison` first.
   Report the endpoint, safe payload summary, returned `actionId`, and where the user should observe it (`/comparison`).

8. Poll the ledger by `actionId` until the terminal result is clear.
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex action <actionId>
   ```
   A successful live terminal path is `queued -> delivered -> applied`. If it stays `queued`, the web page probably is not consuming the queue.

9. Use V4/V5 only after the model has explicit evidence and observables.
   V4 records external evidence, source assessment, impact mapping, observation tasks/runs, health deltas, and revision proposals. V5 runs watch policies, autonomous plans, health scoring, digests, and knowledge promotion proposals. Agent execution remains scoped; accept/reject stays operator/admin.

10. 取图与生成图统一使用 `chart-image`。它创建静默任务、等待、验证并下载 PNG；默认要求原有图表导出，拒绝简化降级。来源选择与完整命令见第 5A 节。只有用户明确接受简化图时才使用 `--allow-fallback` 或 `--mode chart`。

11. 将下载的真实 PNG 交给当前聊天宿主附图。CLI 的 `ok=true` 只表示下载成功，`imageDelivery` 初始为 `not_attempted`。本机 Codex 使用绝对 `localPath` 嵌入；远端或手机宿主上传真实附件。Hermes 的 Telegram 发送入口和回执仅供其自己的身份使用，下载路径或需要鉴权的 URL 不能代替实际图片交付。

## References

Load only the reference needed for the task:

- `references/workflows.md`：第 5A 节包含 `chart-image` 场景选择、生成规格模板、导出事实核对、聊天附图与连续改图；其他章节提供上下文、数据、推图、标注、V4/V5 与新 Agent 接入模板。
- `references/knowledge-loop.md`: Agent-KB retrieval, learning summary, knowledge framework, observation model, V4/V5 promotion/revision loop, and KB safety rules.
- `references/api-surface.md`: endpoint matrix with auth boundaries and preferred Agent usage.
- `references/troubleshooting.md`: common errors, queue states, and recovery paths.

按当前动作读取操作手册相关章节；只有比较部署验收基线时才读取历史验收报告：

- `docs/operations/alpha-ficc-agent-terminal-access-handbook.md`
- `docs/reports/2026-05-26-alpha-ficc-v5-hermes-full-loop-acceptance-report.md`

## Reporting Contract

When the user asks for an actual terminal call, report:

- Agent identity used.
- API base used, without tokens.
- Endpoint and method.
- Payload summary with identifiers and counts, not secrets.
- KB sources used, extracted claims, framework assumptions, model observables, and invalidation conditions.
- Returned `actionId`, `contextId`, `jobId`, or `artifactRef`.
- Ledger status and next observable location.
- Known gaps, such as `queued` waiting for `/comparison`, missing current context, or send failure with `failureReason`.

图片任务另外说明来源是显式生成、当前快照还是旧 job；引用实际 jobId，核对 `fidelity`、`viewConsistency`、`usedFallback` 和有效文件，并记录是否真正附入当前聊天。需要诊断导出方式时读取 job 的 `exportMethod`、`usedScreenshotApi`、范围与尺寸；CLI 成功 JSON 当前不包含这些导出字段。

## Verification

For Skill changes, run:

```bash
uv run /Users/lynch5mo/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/use-alpha-ficc-terminal
uv run skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --help
uv run skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py chart-image --help
uv run python -m py_compile skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py
```

For live Alpha-FICC verification, use the repository's existing smoke scripts when credentials and environment are available:

```bash
python3 scripts/verify_agent_visible_chart_context.py --help
python3 scripts/verify_agent_action_ledger.py
python3 scripts/verify_v5_research_os_contract.py --help
```
