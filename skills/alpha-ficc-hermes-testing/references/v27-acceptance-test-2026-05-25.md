# V2.7 Full Acceptance Test — 2026-05-25

## Session Summary

Executed the complete V2.7 end-to-end acceptance test: chart → annotations → review packet → hypothesis generation → market validation run → results query.

**Verdict: ✅ PASS**

## Key Discovery: Workspace ID Auto-Generation

**The `workspace.id` you specify in `add_series_to_chart` payload is IGNORED by the server.**

The API always returns an auto-generated ID like `terminal-workspace-xxxxx`. You MUST extract the real ID from the POST response and use it in all subsequent annotation actions.

### Extraction Pattern

Access the POST response dict (not the ledger/event — the initial HTTP response):

```
POST response → action → target → workspace → id
or
POST response → action → result → data → workspace → id
```

Panel IDs you specify **ARE preserved**. Only the workspace ID is auto-generated.

## Step-by-step Test Flow

### Step 1: Chart (add_series_to_chart)
- **Payload**: Full workspace definition with custom panel IDs (`panel_a_<ts>`, `panel_b_<ts>`)
- **Response**: HTTP 200, `ok: true`, `pendingCount: 1`
- **Extract**: `workspaceId` and `panelIds` from POST response

### Step 2: Poll Chart Applied
- Poll `GET /api/agent-actions/{chartActionId}` until `status=applied`
- Expected eventTypes: `["queued", "delivered", "applied"]`
- ⚠️ **Timing**: If comparison page is already open but not consuming, ask user to refresh `/comparison`

### Step 3: Annotations (add_chart_annotations)
- **Critical**: Use EXTRACTED `workspaceId` and panel IDs — never hardcode
- **Critical**: ALL annotations need `invalidCondition` field (including text and vertical-line types)
- **Critical**: `target.annotations` array within the `target` object
- **Response**: HTTP 200, `ok: true`

### Step 4: Poll Annotations Applied
- Same as Step 2, polling annotation action ID

### Step 5: Query
- **GET /chart-annotations**: Returns `{ok: true, count: 4, annotations: [...]}`
  - Annotation detail is at `annotations[i].annotation.*`, NOT `annotations[i].*`
- **GET /chart-annotation-review-packet**: Returns nested structure
  - `summary.annotationCount`, `summary.validationCandidateCount`
  - `coverage.validationHintCoverage.ratio`
  - `hypotheses` array, `warnings` array

### Step 6: Validation Run
- `POST /api/chart-annotation-validation-runs`
- Expected HTTP 201, `runId` returned

### Step 7: Results Query
- Poll `GET /api/chart-annotation-validation-runs/{runId}` for status
- Query results via `GET /api/chart-annotation-validation-runs/{runId}/results`
- Fallback: `GET /api/chart-annotation-validations?runId={runId}`

## Error Code Progression from Session

During debugging, the following error progression was observed as root causes were fixed:

| Error | Root Cause | Fix |
|-------|-----------|-----|
| `INVALID_ANNOTATION_PANEL` | Panel IDs don't match current workspace | Extract real IDs from chart POST response |
| `INVALID_ANNOTATION_INVALIDCONDITION_3` | Text annotation (index 3) missing `invalidCondition` | Add to all annotation types |
| `INVALID_ANNOTATION_INVALIDCONDITION_2` | Vertical-line (index 2) missing `invalidCondition` | Same fix |
| SSL errors (`UNEXPECTED_EOF_WHILE_READING`) | Cloudflare TLS issue | Switch to internal API `http://127.0.0.1:8001/api` |

## Validation Results Detail

Both hypotheses returned `verdict: "inconclusive"` with `failureReason: "RULE_NOT_STRUCTURED"`.

```json
{
  "failureDetail": {
    "code": "RULE_NOT_STRUCTURED",
    "message": "Only structured validationRule can be mechanically evaluated."
  },
  "hypothesisId": "hyp_<uuid>",
  "rule": {},
  "verdict": "inconclusive",
  "runId": "mvrun_<uuid>"
}
```

This is expected: the current V2.7 mechanical evaluator requires a `validationRule` field (structured rules), not the `validationHint` field (human-readable descriptions). The `validationHint` is used for hypothesis generation and review packets, but mechanical evaluation requires a different format. This is a known V2.7 design boundary; V2.8+ will bridge this gap.

## Comparison Page Consumption Behavior

The `/comparison` SPA polls `GET /api/terminal-chart-actions/pending` to discover new actions. Key observations:

1. **Polling trigger**: Initial page load / manual browser refresh. If the page loads with an empty queue, subsequently queued actions are not automatically discovered until the next refresh.
2. **Race condition with stale queue**: Multiple previous failed attempts leave queued actions that get consumed FIFO between chart and annotation, changing active workspace.
3. **Solution**:
   - Flush queue first (dummy chart → poll applied → repeat until pendingCount=1)
   - Then ask user to refresh /comparison to re-establish polling connection
   - Then post real chart + annotations in quick succession

## Workspace & Panel ID Debugging

The applied event from the ledger (`GET /agent-actions/{id}` → applied event → `result`) contains:
- `result.workspaceId` — the real workspace ID used by the comparison page
- `result.mode` — `"workspace"` (not "appendPanel")
- NOT panel IDs — panels are embedded in the workspace definition under the action's `target.workspace.panels`

When debugging `INVALID_ANNOTATION_PANEL`:
1. Check pendingCount — if > 1, drain queue
2. Verify the chart action POST response workspace ID matches what's used in annotations
3. Verify panel IDs exist in the chart action's workspace definition
4. Ask user to refresh /comparison page
