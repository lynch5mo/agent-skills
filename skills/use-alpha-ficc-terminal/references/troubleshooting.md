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

If multiple `/comparison` pages are open, use `GET /api/comparison/page-instances` and enqueue with `target.pageInstanceId`, or use `enqueue-series --target-current-page`.

If targeting reports `TARGET_PAGE_NOT_ACTIVE`, the latest shared context is stale. Refresh or reopen `/comparison`; do not push to the stale page.

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

- Read `requiredScope`, `authenticatedAgent`, and `deviceId` from the structured error body or helper output.
- Add the narrow scoped permission required by the endpoint.
- Do not elevate the Agent to operator/admin.

The current external Agent helper preserves `details.requiredScope`; do not infer the missing scope from just the string `agent_scope_required`.

## Public Base URL Fails But Server-Local Works

Use the right base for the execution context:

- Inside API container/server host: `http://127.0.0.1:8001`.
- From web-origin proxy: `https://alpha-ficc.lynch5mo.xyz/api`.
- From LAN web proxy: `http://192.168.10.33:5174/api`.

Do not assume `127.0.0.1:8001` is reachable from the Mac or public internet.

## Cloudflare `error code: 1010`

Meaning: Cloudflare rejected the request before it reached Alpha-FICC. This is commonly caused by a
Python `urllib` default User-Agent.

Fix:

- Set an explicit User-Agent such as `Alpha-FICC-Agent/<agent-id> skill/use-alpha-ficc-terminal`.
- Do not treat the HTML 1010 response as an Alpha-FICC token or scope failure.
- If the request has no explicit UA, set one in the HTTP client before retrying.

## V5 Digest Is `send_failed`

If `failureReason` is present, this can still be a valid, traceable delivery failure. Report `send_failed + failureReason` rather than treating the whole Research OS run as failed.

## V4 Smoke Times Out At 20 Seconds

Known acceptance baseline uses `--timeout 60` for V4 observation/revision verification.

## chart-image 当前图与快照

先区分来源：没有打开网页、但要求按指标出新图时使用 `--series` 或 `--workspace-file`，不需要补当前上下文。用户要求原有当前图时，缺失快照须说明限制；改为新生成需要符合用户意图，不能声称取到了原图。

| 错误码 | 含义与处理 |
| --- | --- |
| `CONTEXT_UNAVAILABLE` | 没有当前 /comparison 上下文。需要原图时重新发布完整快照；需要按指标新出图时直接使用显式生成来源。 |
| `CONTEXT_AMBIGUOUS` | 多个活动页面发布到同一 scope。用 `--page-instance` 或 `--context` 明确指定，不要猜测。 |
| `CONTEXT_PAGE_NOT_FOUND` | 指定页面没有活动快照。先在该页面刷新 /comparison。 |
| `CONTEXT_NOT_VISIBLE` | 指定 contextId 不存在或对该 Agent 不可见。 |
| `CONTEXT_PAGE_MISMATCH` | `--context` 与 `--page-instance` 指向不同页面。 |
| `CONTEXT_RENDER_NOT_AVAILABLE` | 上下文没有完整可渲染快照，查看 `renderAvailability.reasons`。需要原图时修复快照发布；新生成不能冒充当前原图。 |
| `RENDER_REQUEST_ENDPOINT_NOT_ALLOWED` | 服务端给出的 renderRequest 端点不在允许列表。不要跟随任意 URL。 |
| `PANEL_NOT_FOUND` | 指定面板不在该快照内。用 `/api/comparison/page-instances` 的 `panelIds` 核对真实 panelId。 |
| `RENDER_SNAPSHOT_NOT_FOUND` | 快照引用不存在或已被清理。重新发布当前图。 |
| `RENDER_SNAPSHOT_NOT_VISIBLE` | 快照存在但对当前 Agent 不可见或已过期。不要用其他 Agent 的身份读取。 |
| `RENDER_SNAPSHOT_BINDING_MISMATCH` | ref 与 contextId / pageInstanceId / workspaceId 不匹配。用同一次发布的自描述 renderRequest。 |
| `RENDER_SNAPSHOT_SOURCE_AMBIGUOUS` | 生成规格内混入快照引用。改用上下文来源，或移除规格内引用并显式生成；API 引用放在 `target` 或请求顶层。 |
| `UNSUPPORTED_GENERATION_SPEC` | 规格版本不支持；首次创建与已有任务重试都拒绝，不会忽略规格后返回旧任务。 |
| `SNAPSHOT_SCOPE_OVERRIDE` | 上下文来源不接受 `--window` / `--granularity` 覆盖。显式生成才使用这些参数。 |
| `DISPLAY_NOT_REPRODUCED` | 回放无法把渲染区域复现到快照记录的宽度。这不是可以忽略的差异，任务会失败而不是输出尺寸不符的图。 |
| `REQUIRED_FIDELITY_UNAVAILABLE` | 程序原有图表图片导出不可用，只剩简化图。默认失败；`--allow-fallback` 或 `--mode chart` 才采用，并会标明简化图；不以网页截图替代。 |
| `ARTIFACT_INVALID` | 下载内容不是有效 PNG 或与元数据不一致。已有目标文件不会被破坏。 |
| `OUTPUT_EXISTS` | 目标文件已存在。显式 `--overwrite` 才替换。 |
| `JOB_WAIT_TIMEOUT` | 整体等待期限到达。用 `--job <jobId>` 续查，不要换编号重建。 |
| `SOURCE_CONFLICT` | 来源混用，或 `--panel` 用于生成/job 来源。选择一组来源；生成面板在规格中定义。 |
| `JOB_ID_CONFLICT` | 同一编号的内容或身份已改变。改图用新 jobId；续取使用原编号和原身份。 |
| `ARTIFACT_NOT_READY` | 任务结束却没有有效产物。读取 job 的 events/error，不把状态字符串当作有图。 |
| `ARTIFACT_DOWNLOAD_FAILED` | 网络、鉴权或服务错误。修复原因后用原 jobId 续取；不要把请求失败的页面保存成 PNG。 |
| `OUTPUT_WRITE_FAILED` | 目标目录不可写或磁盘写入失败。选择可写输出路径并用原任务续取。 |

## 图表导出、旧版本与聊天附图

| 现象 | 判断与处理 |
| --- | --- |
| helper 不识别 `chart-image` | 当前运行时加载了旧脚本。更新完整 Skill 目录，包括 references、scripts、assets、agents，再检查 `chart-image --help`。 |
| 新任务只有 captured，没有 exportMethod | 尚未证明使用原有保存图片；检查服务和前端部署是否匹配。不能靠字段名或裁剪截图补验收。 |
| job 的 screenshotError 包含 exporter 未就绪、下载超时或非法 PNG | 核对原保存按钮与后台服务版本，查看导出失败记录。导出失败不切换页面截图；简化图仅在用户明确接受时使用。 |
| 升级后 `--job` 仍拿到旧网页截图 | 续取返回历史文件是正常语义；新建 job 才会执行当前导出。 |
| job 下载成功，聊天没有图 | `imageDelivery=not_attempted`。本机用绝对 localPath 嵌入；远端/手机由宿主上传真实附件。宿主没有附件能力时如实报告未交付。 |
| 多面板结果是一张图片 | 原有 exporter 合成所有目标面板；取当前单面板用真实 `--panel`，生成单面板在规格中只保留该面板和对应对象。 |
| 图片尺寸与网页/DPR 不同 | 图片使用原有导出宽度和倍率。核对 exportWidth/exportHeight/exportPixelRatio 与 PNG，不能据网页尺寸认定导出错误。 |
