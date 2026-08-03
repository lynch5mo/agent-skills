# Alpha-FICC Terminal Troubleshooting

## `AGENT_VISIBLE_CHART_CONTEXT_NOT_FOUND`

Meaning: the browser has not shared a current context for the requested scope.

Fix:

1. Open `/comparison`.
2. Load or switch the chart.
3. Click "分享给 Agent" or wait for automatic sync.
4. Retry `GET /api/comparison/current/context`.

Do not call `/api/terminal-chart-actions/pending`; it does not create context and it drains the action queue.

## Action Stays `queued`

Meaning: `POST /api/terminal-chart-actions` succeeded, but no browser page has consumed the queue.

Fix:

1. Ask the user to open `/comparison`.
2. Confirm the page is logged in and polling.
3. Keep checking `GET /api/agent-actions/{actionId}`.

Do not manually call `/pending` unless the explicit task is to simulate browser consumption.

## Action Is `delivered` But Not `applied`

Meaning: the browser consumed the action but did not report a final apply/fail event yet.

Fix:

1. Check the `/comparison` UI.
2. Query `GET /api/agent-actions/{actionId}` again after a short wait.
3. If it becomes `failed`, report the ledger error and payload summary.

## Annotation Fails Or Does Not Appear

Likely causes:

- Wrong `workspaceId`.
- Hardcoded or stale `panelId`.
- Annotation records not nested under the shape accepted by the current normalizer.

Fix:

1. Read current context.
2. If the target chart came from an Agent action, inspect the applied ledger result for real panel ids.
3. Post `add_chart_annotations` with real ids.
4. Verify `GET /api/chart-annotations?workspaceId=...`.

## `INVALID_AGENT_TOKEN`

Meaning: missing or mismatched Agent token.

Fix:

- Check that the current Agent id matches the token environment variable.
- Use `ALPHA_FICC_<AGENT>_AGENT_TOKEN`, `ALPHA_FICC_AGENT_TOKEN`, or `ALPHA_FICC_TOKEN_FILE`.
- Do not print or paste token material.
- Do not switch to an operator/admin token.

## `AGENT_SCOPE_REQUIRED`

Meaning: token is valid, but scopes are insufficient.

Fix:

- Add the narrow scoped permission required by the endpoint.
- Do not elevate the Agent to operator/admin.

## Public Base URL Fails But Server-Local Works

Use the right base for the execution context:

- Inside API container/server host: `http://127.0.0.1:8001`.
- From web-origin proxy: `https://alpha-ficc.lynch5mo.xyz/api`.
- From LAN web proxy: `http://192.168.10.33:5174/api`.

Do not assume `127.0.0.1:8001` is reachable from the Mac or public internet.

## V5 Digest Is `send_failed`

If `failureReason` is present, this can still be a valid, traceable delivery failure. Report `send_failed + failureReason` rather than treating the whole Research OS run as failed.

## V4 Smoke Times Out At 20 Seconds

Known acceptance baseline uses `--timeout 60` for V4 observation/revision verification.
