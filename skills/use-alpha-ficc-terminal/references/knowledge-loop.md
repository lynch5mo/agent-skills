# Agent-KB And Observation Model Loop

Use this reference when Alpha-FICC work requires knowledge retrieval, learning summaries, framework synthesis, observation models, model revision, or knowledge promotion.

## Principle

Alpha-FICC has three planes:

```text
Agent-KB = research cognition plane
Alpha-FICC data layer = governed market data plane
Agent runtime = interpreter and proposal engine
```

The stable loop is:

```text
Agent-KB Query
  -> EvidencePack
  -> ExtractedClaim
  -> KnowledgeFrameworkSpec
  -> ObservationModel
  -> Terminal Chart/Data Artifact
  -> V4 Observation/Revision
  -> V5 Digest/KnowledgePromotionProposal
```

Do not reduce this loop to a one-shot chart action.

## Canonical Agent-KB Rules

- Canonical macOS repo: `/Users/lynch5mo/Work Documents/LLM/agent-kb`.
- Never use `/Users/lynch5mo/AgentWorkspaces/Hammers/agent-kb`.
- Before any KB read/write operation, run from the canonical repo:

```bash
cd "/Users/lynch5mo/Work Documents/LLM/agent-kb"
git pull --rebase origin main
git status --short --branch
```

If the repo has unrelated unstaged changes and pull is blocked, report the blocker and avoid writing KB records. Do not stash, reset, or clean without explicit instruction.

Layer semantics:

| Layer | Meaning |
| --- | --- |
| `raw/` | source intake only |
| `wiki/` | compiled knowledge |
| `write/` | drafting and user-facing articles |
| `outputs/` | reports, task summaries, audits, runtime records |

Default compilation is summary-first. Do not write compiled `wiki/` pages unless the required classification approval exists. Agent runtime usually creates proposals or output-layer records, not direct wiki facts.

## Retrieval Workflow

1. Run preflight:
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py kb-preflight
   ```
2. Search locally:
   ```bash
   python3 skills/use-alpha-ficc-terminal/scripts/alpha_ficc_terminal.py kb-search "黄金 实际利率 Money View" --domain finance --limit 8
   ```
3. Read the smallest relevant set of KB files.
4. Preserve source paths in the analysis.
5. Mark whether each source is a compiled summary, concept/entity/map, draft, or runtime output.

Preferred read order:

1. `wiki/summaries/<domain>/`
2. `wiki/concepts/<domain>/`
3. `wiki/entities/<domain>/`
4. `wiki/maps/<domain>/`
5. `write/drafts/` or `write/publish/` only when the user is asking about authored narratives
6. `outputs/` for runtime decisions, reports, audits, and prior task summaries

## Learning Summary Shape

Convert KB material into this compact structure:

```json
{
  "InternalKnowledgeSource": [
    {
      "source_id": "iks-short-name",
      "source_type": "agent_kb_summary",
      "title": "source title",
      "path": "/Users/lynch5mo/Work Documents/LLM/agent-kb/wiki/summaries/finance/...",
      "snapshot_date": "2026-06-11"
    }
  ],
  "ExtractedClaim": [
    {
      "claim_id": "claim-short-name",
      "source_id": "iks-short-name",
      "statement": "可被终端数据观察或验证的一句话。",
      "confidence": "low|medium|high",
      "tags": ["gold", "real-rates"]
    }
  ]
}
```

Avoid vague summaries. Each claim should either inform a model variable, regime condition, invalidation condition, or user-facing narrative.

## Framework-To-Observation Model

Turn extracted claims into:

```json
{
  "KnowledgeFrameworkSpec": {
    "framework_id": "framework-topic-v1",
    "objective": "研究目标",
    "core_thesis": "核心框架",
    "claim_ids": ["claim-a"],
    "causal_links": [
      {
        "from": "REAL_RATE_10Y",
        "to": "GOLD_FUTURES",
        "direction": "negative_short_term",
        "logic": "实际利率上行提高黄金机会成本。"
      }
    ],
    "regime_conditions": [
      "健康多头：黄金上行、实际利率下行、美元走弱。",
      "outside money 重估：黄金上行但实际利率不降。"
    ]
  },
  "ObservationModel": {
    "watchVariables": ["fred:DFII10", "yfinance:GC=F", "fred:DTWEXBGS"],
    "watchWindow": {"start": "2025-01-01", "end": "2026-06-11"},
    "expectedDirection": "claim-specific",
    "validationPlan": "用 /api/comparison/current/chart-data 或 chart-datafeed series 检查方向、背离和 regime。",
    "invalidationConditions": [
      "黄金上涨完全由实际利率下行解释时，不支持 outside money 重估假设。"
    ],
    "chartPlan": {
      "seriesIds": ["yfinance:GC=F", "fred:DFII10", "fred:DTWEXBGS"],
      "formulaIds": [],
      "window": "3Y",
      "granularity": "D"
    }
  }
}
```

## Terminal Validation

After the observation model exists:

1. Search/select terminal series ids.
2. Fetch local-first chart data.
3. Generate or push a chart.
4. Add annotations only after real `workspaceId`/`panelId` are known.
5. Report whether the terminal evidence supports, contradicts, or leaves the KB-derived claim inconclusive.

Do not present a KB-derived framework as market-validated until terminal data has been checked.

## V4/V5 Persistence

Use V4 when an event or model observation should be tracked:

```text
ExternalEvidence
  -> SourceAssessment
  -> ImpactMapping
  -> ObservationTask
  -> ObservationRun
  -> ModelHealthDelta
  -> RevisionProposal
```

Use V5 when ongoing monitoring or operating cadence is needed:

```text
ModelWatchPolicy
  -> TriggerEvaluation
  -> AutonomousRunPlan
  -> AutonomousRun
  -> ModelHealthScore
  -> ResearchDailyDigest
  -> KnowledgePromotionProposal
```

Promotion remains proposal-only:

- `targetDomain`: one of `finance`, `ai`, `film`, `lifeos`, `knowledge`.
- `targetLayer`: usually `outputs` or `wiki_candidate`.
- `kbWriteMode`: `proposal_only`.
- Agent may create proposal, but operator/admin must accept/reject.

## Reporting

For research/model answers, include:

- KB sources used.
- Claims extracted.
- Framework or observation model generated.
- Terminal data/charts used for validation.
- What is supported, contradicted, or inconclusive.
- Whether any V4/V5 proposal was created, with ids.
- What was not written to KB and why.
