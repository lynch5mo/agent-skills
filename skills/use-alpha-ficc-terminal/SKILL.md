---
name: use-alpha-ficc-terminal
description: "Use when Codex, Claude Code, Hermes, or any external Agent needs to operate the Alpha-FICC financial terminal or research loop: retrieve Agent-KB knowledge, summarize learning into evidence and frameworks, generate or revise observation models, read current /comparison or crypto chart context, fetch local-first chart data, search terminal catalogs, queue chart or annotation actions, create headless chart render jobs, use V4/V5 Research OS endpoints, verify agent-action ledger state, troubleshoot terminal access, or onboard a new scoped Agent."
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
---

# Use Alpha-FICC Terminal

## Core Contract

Treat Alpha-FICC as a governed financial terminal, not as a generic web data scraper.

- Use the current Agent identity (`codex`, `hermes`, `claude`, or a newly approved Agent id) and that Agent's own scoped token.
- Do not print token values, token lengths, token hashes, prefixes, passwords, cookies, or admin/operator credentials.
- Treat `/Users/lynch5mo/Work Documents/LLM/agent-kb` as the only valid macOS Agent-KB repository. Never use quarantined or stale copies.
- Use Agent-KB as the research cognition plane: retrieve summaries/concepts/entities/maps, extract claims, build a framework, then turn the framework into an observation model before drawing conclusions.
- Keep KB writes proposal-first. Agent may create knowledge promotion or revision proposals; do not directly write Agent-KB `wiki/` or accept/reject governance decisions.
- Read the user's current terminal chart through `GET /api/comparison/current/context`; never inspect browser state directly.
- Fetch complete chart data only through `GET /api/comparison/current/chart-data` using `context.chartDataRequest`.
- Do not call provider APIs such as FRED, Yahoo, Akshare, BEA, BLS, or EIA directly from the Agent path.
- Queue terminal chart work through `POST /api/terminal-chart-actions`; verify through `GET /api/agent-actions/{actionId}`.
- Do not call `GET /api/terminal-chart-actions/pending` during normal Agent work. It drains the browser queue.
- Use real `workspaceId`, `pageInstanceId`, and `panelId` from current context or applied ledger results. Do not hardcode panel ids.
- Agent-created proposals are allowed where scoped; accept/reject governance actions remain operator/admin decisions.

## Workflow

1. Establish base URL and identity.
   Use `ALPHA_FICC_API_BASE_URL` or `ALPHA_FICC_BASE_URL`. Server-local API usually uses `http://127.0.0.1:8001`; web proxy bases often end with `/api`, such as `https://alpha-ficc.lynch5mo.xyz/api` or `http://192.168.10.33:5174/api`.

2. Run a non-secret health check.
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex health
   ```

3. Retrieve internal knowledge when the task involves research, explanation, model construction, validation, or "why" reasoning.
   First perform KB preflight from the canonical repo, then search relevant finance knowledge.
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
     --panel-title "人民币汇率压力框架"
   ```
   Report the endpoint, safe payload summary, returned `actionId`, and where the user should observe it (`/comparison`).

8. Poll the ledger by `actionId` until the terminal result is clear.
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --agent codex action <actionId>
   ```
   A successful live terminal path is `queued -> delivered -> applied`. If it stays `queued`, the web page probably is not consuming the queue.

9. Use V4/V5 only after the model has explicit evidence and observables.
   V4 records external evidence, source assessment, impact mapping, observation tasks/runs, health deltas, and revision proposals. V5 runs watch policies, autonomous plans, health scoring, digests, and knowledge promotion proposals. Agent execution remains scoped; accept/reject stays operator/admin.

10. For offline/mobile chart delivery, create a render job instead of relying on the live browser queue.
   Use `POST /api/agent-render-jobs`; Hermes-only Telegram delivery uses `POST /api/telegram/send-artifact` and delivery-result callbacks.

## References

Load only the reference needed for the task:

- `references/workflows.md`: concrete payload templates for reading context, fetching data, pushing series, adding annotations, render jobs, V4/V5, and onboarding new Agents.
- `references/knowledge-loop.md`: Agent-KB retrieval, learning summary, knowledge framework, observation model, V4/V5 promotion/revision loop, and KB safety rules.
- `references/api-surface.md`: endpoint matrix with auth boundaries and preferred Agent usage.
- `references/troubleshooting.md`: common errors, queue states, and recovery paths.

Use the project handbook for detailed historical context when needed:

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

## Verification

For Skill changes, run:

```bash
python3 /Users/lynch5mo/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/use-alpha-ficc-terminal
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py --help
python3 -m py_compile skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py
python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py kb-preflight
```

For live Alpha-FICC verification, use the repository's existing smoke scripts when credentials and environment are available:

```bash
python3 scripts/verify_agent_visible_chart_context.py --help
python3 scripts/verify_agent_action_ledger.py
python3 scripts/verify_v5_research_os_contract.py --help
```
