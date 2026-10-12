# 维护报告与追溯契约

## 每轮必有的四个报告面

每个 healthy、observed、skipped、failed、A1、A2 或 A3 运行都必须产生：

1. append-only maintenance run ledger；
2. durable local report；
3. Hermes cron final output 归档；
4. Discord 单向状态消息（当前轮先记 `prepared`）。

发生修改时另有完整 maintenance action report；A3 另有去重 Agent-KB handoff。没有 business action 只意味着 `actions=[]`，不取消任何每轮报告。

## Task 1–3 接口

```text
new_run_record(run_id, now)
sanitize(value, secret_values)
validate_run_record(record)
validate_agent_kb_publication(record)
completion_status(record, *, ledger_persisted=False)

MaintenanceStore.acquire_lease(...)
MaintenanceStore.append_run(record)
MaintenanceStore.write_snapshot(snapshot)
MaintenanceStore.open_incident(dedupe_key, record)
MaintenanceStore.pending_delivery_run_id()
MaintenanceStore.append_delivery_event(run_id, status, error)

render_builder_report(record, *, ledger_persisted=False)
render_discord(record, *, ledger_persisted=False)
```

不得绕过这些接口另写 ledger、脱敏、incident 或 delivery 状态。

## Run record

`executor` 必须是 `hermes`，`role` 必须是 `scoped_agent`。至少记录：

```yaml
run_id:
incident_id:
executor: hermes
role: scoped_agent
host:
trigger:
started_at:
finished_at:
severity:
authority_level:
checks:
diagnosis:
actions:
pre_change_version:
post_change_version:
commit_sha:
deployment_sha:
rollback_sha:
verification:
report_targets:
agent_kb:
final_status:
```

动作记录必须含 action ID 和 version。持久化前先 `sanitize()`，再 `validate_run_record()`。不存 raw command environment、自由文本秘密、凭据值或其长度/hash/prefix/fragment。

## 完成状态

| 情况 | 对外状态 | 禁止的替代说法 |
| --- | --- | --- |
| 无异常且四报告门通过 | `healthy_report_ready` | `[SILENT]` |
| 观察/未确认且四报告门通过 | `observed_report_ready` | `healthy` |
| repair 验收通过且四报告门通过 | `repaired_report_ready`（由 `completion_status()` 导出） | `complete`、`healthy` |
| repair 成功但任一报告面失败 | `repaired_reporting_failed` | error code、`repaired`、`healthy`、`repaired_report_ready` |
| 非 repair 任一报告面失败 | `reporting_failed` | `complete`、任何 `*_report_ready` |
| A3 报告远端可见且四报告门通过 | `builder_required` | “已通知负责人” |
| A3 本地报告存在但 push 失败/冲突 | `handoff_push_failed` | “已交接” |
| A3 push 后无法验证远端可见 | `remote_not_visible` | `builder_required` |
| lease 被占用 | `skipped_due_to_active_run` | 静默退出 |

底层错误（如 report store unavailable）属于 `error_type`/report target detail，不得用作 `final_status`。

四报告完成门是可执行门，不是文档提醒。调用者在 append 前确认 local report=`persisted`、cron output=`persisted`、Discord=`prepared|unconfigured`；只有 `MaintenanceStore.append_run()` 成功返回后才调用 `completion_status(record, ledger_persisted=True)`。append 抛错或返回失败时使用 `ledger_persisted=False`。默认值为 false，避免遗漏 runtime fact 时误报成功。

`append_run()` 的结果是 runtime fact，不写回 record。append 返回后，唯一 finalization/render 路径把同一个事实以 keyword-only 参数传给 `render_builder_report(record, ledger_persisted=<append result>)` 和 `render_discord(record, ledger_persisted=<append result>)`；两个 renderer 内部调用 `completion_status()`，不得直接把 technical `record.final_status` 当对外状态。默认 false 必须渲染受限失败状态。

如果修复已成功而报告失败：不重复修复，不覆盖 append-only evidence；保留动作前后验证。缺/失败的 cron target、cron output 持久化失败、local report 失败或 append 失败都必须在当前 cron final output/Discord 中暴露追溯链不完整。下一轮先读 ledger/lease，只重试报告/对账。

### Reporting-failure response checklist

修复已成功但任一报告面失败时，当前轮答复与实际 finalization 都逐项输出：

```text
final_status: repaired_reporting_failed
local_report: persisted | failed
cron_output: persisted current warning/final-output artifact | failed
discord: prepared failure summary | unconfigured
repair_retry: no
next_run: reconcile/retry report faces only; do not repeat the successful repair
```

local report 失败不取消其他报告面：仍保存本轮 cron warning/final-output artifact，并生成 Discord=`prepared` 的失败摘要；当前不得写 `delivered`。下一轮根据 ledger/lease 与 delivery event 只对账或重试失败报告面，不重新执行已验证成功的 repair。

## Discord delivery lifecycle

报告内容、cron output 和 Discord delivery 是独立状态：

1. append 结果已知后，当前 Agent 用同一个 `ledger_persisted` runtime fact 调用 final `render_builder_report()` 与 `render_discord()`；`report_targets.discord.status` 为 `prepared`，当前轮不得写 `delivered`。
2. Agent 返回 final response；Hermes gateway 随后尝试投递并保存 job 状态。
3. 下一轮 preflight 用 `pending_delivery_run_id()` 找到待对账 run。
4. 根据可信 Hermes job state 调用 `append_delivery_event(..., "delivered")` 或 `append_delivery_event(..., "failed", error)`。
5. delivery event 只追加，不修改原 run；失败错误只保存受限代码，不保存自由文本秘密。

Discord 只接收状态报告，不接收命令，不用于 Agent 间对话。当前维护 run 不调用 send-message 工具。每轮都返回非空中文报告，不得 `[SILENT]`。

紧凑报告至少含 run/time、总体状态、API、Provider、数据库/组件、刷新/freshness、动作、验证和未解决风险。修复报告另含发现点、根因/假设、文件或运行状态、commit/deploy/rollback、修复前后指标与 Agent-KB 状态/路径。

## A3 Agent-KB handoff（先于最终 ledger 和 Discord render）

用 `open_incident()` 的稳定 opaque `incident_id` 去重。先在实际 Agent-KB clone 执行 `python3 ops/scripts/configure_agent_instance.py check Hermes`，读取 clone-local registered instance。新报告只可写到：

```text
outputs/review/agent_task_summaries/Hermes/<registered-instance-id>/TASK-<stable-incident-id>.md
```

禁止在 flat `Hermes/` family root 创建报告。重复且事实未变化时只引用现有报告，不创建新文件；事实实质变化时追加带时间戳更新。

最小字段：

```yaml
incident_id:
status: builder_required
severity:
detected_at:
last_confirmed_at:
production_version:
affected_services:
affected_data:
symptoms:
raw_errors:
reproduction:
root_cause_hypothesis:
maintenance_actions_attempted:
rollback_state:
relevant_files:
forbidden_or_exceeded_boundary:
builder_acceptance_criteria:
verification_commands:
```

正文含时间线、用户影响、脱敏原始证据、候选根因、已尝试与未尝试动作、当前生产/回滚状态和 Building Agent 验收条件。

写前遵守 `agent-kb-workflow` 的 canonical repo、pull/rebase、规则优先级和提交要求；冲突不强推。Closeout 只走：

```bash
bash ops/scripts/agent_finish.sh Hermes TASK-<stable-incident-id> <summary-file.md>
```

只有 closeout push 后验证远端可见才写 `agent_kb.status=remote_visible`、canonical path 和 `builder_required`。push 失败/冲突写 `handoff_push_failed` 与 local path；push 结果不明或无法验证远端可见写 `remote_not_visible` 与 local path。三类结果都先进入 final immutable ledger，再由 `render_discord()` 输出真实 status/path。用户人工把远端可见路径交给 Mac Building Agent；Hermes 不创建或唤醒 task。

持久化前先调用共享 `validate_agent_kb_publication(record)`；`validate_run_record()` 与 `completion_status()` 使用同一 validator：

- `final_status=builder_required` 仅接受 `agent_kb.status=remote_visible`，且 `canonical_path` 必须严格匹配 `outputs/review/agent_task_summaries/Hermes/<registered-instance-id>/TASK-<stable-incident-id>.md`；
- `final_status=handoff_push_failed|remote_not_visible` 必须与 `agent_kb.status` 同名，并提供非空、安全、含 instance 层的 `local_path`；
- 缺失/未知/矛盾状态、canonical/local 字段互换、flat `Hermes/TASK-...` family-root、`.`/`..` 或不安全路径均 validation fail；completion 只能给受限 `reporting_failed`，renderer 不输出 publication 成功状态或路径。

### A3 response and finalization checklist

每个 A3 决策答复和实际 finalization 都按顺序逐项输出：

```text
instance_check: python3 ops/scripts/configure_agent_instance.py check Hermes
registered_instance_id: <clone-local registered value>
canonical_summary_path: outputs/review/agent_task_summaries/Hermes/<registered-instance-id>/TASK-<stable-incident-id>.md
closeout: bash ops/scripts/agent_finish.sh Hermes TASK-<stable-incident-id> <summary-file.md>
publication_status: remote_visible | handoff_push_failed | remote_not_visible
publication_path: <canonical path when remote_visible; local path otherwise>
finalization_order: publish/verify -> immutable ledger -> Discord render
```

决策模拟保留模板并说明 status-selection rule，不虚称执行。实际 finalization 必须用检查所得 instance、stable incident、真实 status/path 替换占位符。最终 Discord 逐行包含 `publication_status` 与 `publication_path`，不得只写“已完成规范交接”或“结果可验证”。
