# V3 Rule Compiler — Acceptance Test Record (2026-05-25, updated 2nd session)

## Summary

The V3 rule compiler endpoints are deployed and responding. Two key findings:

1. ✅ **Hypothesis-based compilation works**: Existing hypothesis `hyp_v3_server_smoke_1779707287` was compiled into accepted rule `vr_37529666459842e1` (run `rcr_92070aa275644a24`).
2. ❌ **Standalone draft compilation does NOT work**: All standalone draft formats (`metric` as string, `metric` as object, with/without `draftId`, with/without `hypothesisId`) return the same 5 error codes and 0 accepted.

## Correct Rule Format (from GET /rules)

The existing accepted rule has this exact format:

```json
{
  "ruleId": "vr_37529666459842e1",
  "status": "accepted",
  "metric": {
    "field": "close",
    "sourceId": "yfinance:USDCNH=X"
  },
  "operator": ">=",
  "threshold": 7.1,
  "window": {
    "start": "2026-05-25",
    "end": "2026-06-30"
  },
  "aggregation": "last",
  "draftId": "vrd_v3_server_smoke_1779707287",
  "annotationId": "ann_v3_server_smoke_1779707287",
  "hypothesisId": "hyp_v3_server_smoke_1779707287"
}
```

Key structural points:
- `metric` is an **object** `{"field": "close", "sourceId": "..."}`, NOT a string
- `operator` is `">="`, NOT `"above"` / `"gt"` / `"greater_than"`
- `window` is an **object** `{"start": "2026-05-25", "end": "2026-06-30"}`, NOT a string or preset
- `aggregation`: `"last"` (possibly other values like `"first"`, `"avg"`)
- The rule is tied to an `annotationId` and `hypothesisId` that already exist

## Standalone Draft Compilation — All Attempts Failed

Every tested standalone draft format returned the same 5 aggregated errors:

```json
{
  "status": "failed",
  "acceptedCount": 0,
  "rejectedCount": 3,
  "summary": {
    "compileSuccessRate": 0.0,
    "topErrorCodes": [
      "RULE_WINDOW_INVALID",
      "RULE_MISSING_METRIC",
      "RULE_SOURCE_UNRESOLVED",
      "RULE_FIELD_UNAVAILABLE",
      "RULE_OPERATOR_UNSUPPORTED"
    ]
  }
}
```

### Tested Formats (all failed)

| # | Schema | Draft Format Detail |
|---|--------|-------------------|
| A | flat | metric="close", direction="above", window="2025-04-10/2026-06-30" |
| B | condition obj | condition={metric,operator,value}, window as start/end |
| C | field + operator | field="value", operator="lt", window="1Y" |
| D | nested | validationRule={metric,operator,value,window} |
| E | minimal | condition="close > 7.10", window="1Y" |
| F | exact match | metric={field,sourceId}, operator=">=", window={start,end}, aggregation="last" |
| G | F + draftId | Same as F + draftId field |
| H | G + hypothesisId | Same as G + hypothesisId link |
| I | today start | Same as F with start=today (not 2025) |
| J | I + input + hypothesisId | Same as I + input.hypothesisIds reference |

### Root Cause Hypothesis

The rule compiler appears to require drafts to be **derived from existing annotations/hypotheses** — the `annotationId`, `hypothesisId`, and `annotationSetId` are mandatory linking fields. Standalone rules without annotation provenance are rejected by the compiler. The `drafts` field in the POST body might be intended for server-side processing where each draft is automatically annotated, not for free-form rule submission.

Suggested next step: complete end-to-end flow:
1. Create annotations with validationHint
2. POST add_chart_annotations → applied → review packet generated → hypotheses created
3. POST rule compilation with `input.hypothesisIds` referencing the newly created hypotheses
4. Server extracts rules from validationHints automatically

## Correct Local Token Reading

ALPHA_FICC_HERMES_AGENT_TOKEN exists in `/Users/lynch5mo/.hermes/profiles/codex/.env` as a 142-character string (includes `,hermes-local-` suffix). **Must read via Python binary parsing** — grep truncates to 13 chars, os.getenv returns empty/stale.

```python
with open("/Users/lynch5mo/.hermes/profiles/codex/.env", "rb") as f:
    for line in f.read().split(b"\n"):
        if line.startswith(b"ALPHA_FICC_HERMES_AGENT_TOKEN="):
            t = line.split(b"=", 1)[1].strip()
            token = t.decode("utf-8", errors="replace")
            if token.startswith('"') and token.endswith('"'): token = token[1:-1]
            break
```

Token characteristics:
- LENGTH: 142
- HAS_COMMA: true
- HAS_HERMES_LOCAL: true
- SHA256_PREFIX: 8ae63206c990

## API Endpoint Details

### POST /api/chart-annotation-rule-compilations

**Request** (hypothesis-based, known working):
```json
{
  "source": "external-hermes",
  "agent": "hermes",
  "note": "recompile from hypothesis",
  "annotationSetId": "aset_v3_recompile",
  "input": {
    "annotationSetId": "aset_v3_server_smoke_1779707287",
    "hypothesisIds": ["hyp_v3_server_smoke_1779707287"],
    "reviewPacketId": "arp_v3_server_smoke_1779707287"
  }
}
```

**Response** (known working, HTTP 201):
```json
{
  "ok": true,
  "runId": "rcr_92070aa275644a24",
  "status": "completed",
  "draftCount": 1,
  "acceptedCount": 1,
  "rejectedCount": 0,
  "acceptedRules": ["..."],
  "run": { "status": "completed", ... }
}
```

**Response keys from failed run**: `ok`, `runId`, `status`, `draftCount`, `acceptedCount`, `rejectedCount`, `run`, `acceptedRules`
- When compilation fails, `acceptedRules` is an empty array `[]`
- When compilation fails, `rejectedDrafts` / `acceptedDrafts` keys are absent (not `null`, completely missing)
- The `run.status` field is `"failed"` when the compilation run fails

### GET /api/chart-annotation-validation-rules?limit=5

- HTTP 200
- Response: `{"ok": true, "count": 1, "rules": [...]}`
- Rules are in `response.rules[]`, each with full lint result including `lintResult.normalizedRule`

### POST /api/chart-annotation-validation-runs (ruleSource mode)

- HTTP 201
- `ruleSource: "accepted_rules_first"`, `compileIfMissing: false`
- Returns `runId`, `status: "completed"` immediately
- `resultCount: 4` with all `verdict: "inconclusive"` and `failureReason: "RULE_NOT_STRUCTURED"` (because hints are validationHint not validationRule)
- `acceptedRuleAppliedCount: 0` — the existing accepted rule was not matched to any annotation

## Known Issues

1. **Standalone draft compilation not working**: See root cause hypothesis above. All draft formats return the same 5 errors.
2. **Local token reading**: Must use Python binary parsing, NOT grep/os.getenv.
3. **SSH daemon hangs after long Python scripts**: If SSH hangs with "Connection timed out during banner exchange" while port 22 is reachable, restart sshd on the server console.
4. **RULE_NOT_STRUCTURED in validation results**: Mechanical evaluator expects `validationRule` field, not `validationHint`. The validationHint is for human-readable hypothesis generation; V2.8+ will bridge this.
