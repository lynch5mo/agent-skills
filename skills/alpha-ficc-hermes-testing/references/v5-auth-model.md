# V5 Research OS Auth Model

2026-05-26 基于部署头 `df7f8b767` 官方脚本验证。

## 关键发现

V5 与 V4 的认证模型有根本区别：

### V4 认证

V4 端点（`/api/external-evidence`, `/api/impact-mappings`, `/api/observation-tasks` 等）使用 `_authorize_agent_or_user()`，对 agent token 无 scope 检查。仅 accept/reject 使用 `_require_operator_or_admin()`。

### V5 认证

V5 端点全部使用 `_authorize_agent_or_user()`：

| 端点 | 认证函数 | Agent 可访问 |
|------|---------|------------|
| `/api/research-os/policies` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/evaluations` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/run-plans` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/scheduler/tick` | `_authorize_agent_or_user()` | ✅ 是（authKind=agent 断言） |
| `/api/research-os/scheduler/plans/{id}/execute` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/scheduler/plans/{id}/cancel` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/scheduler/plans/{id}/replay` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/scheduler/policies/{policyId}/cancel-all` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-os/health-scores/recompute` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/research-daily-digests/...` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/knowledge-promotion-proposals` | `_authorize_agent_or_user()` | ✅ 是 |
| `/api/knowledge-promotion-proposals/{id}/accept` | `_require_operator_or_admin()` | ❌ 否（401/403） |

## scheduler tick 的特殊性

scheduler tick 是 V5 中权限最敏感的端点。官方脚本 `verify_v5_research_os_scheduler.py` 在第 411-413 行断言：

```python
tick_payload = _http_json("POST", f"{base_url}/api/research-os/scheduler/tick", ...)
if tick_payload.get("dryRun") is not True:
    raise VerifyError("scheduler tick dryRun 应返回 dryRun=true")
tick_limit = int(tick_payload.get("tickLimit") or 0)
if tick_limit > 1:
    raise VerifyError(f"Agent scheduler tickLimit 必须 <= 1，实际: {tick_limit}")
if str(tick_payload.get("authKind") or "").strip().lower() != "agent":
    raise VerifyError("scheduler tick 应标记 authKind=agent")
if str(tick_payload.get("agent") or "").strip().lower() != agent:
    raise VerifyError("scheduler tick 返回的 agent 与认证 agent 不一致")
```

要求：
- HTTP 200 + `dryRun: true`
- `authKind: "agent"`（表示该 tick 是 agent 权限执行的，不是 operator 提权）
- `tickLimit <= 1`（单步 tick 安全约束）
- `agent` 字段匹配认证 agent

## scope 配置影响

`ALPHA_FICC_CODEX_AGENT_SCOPES` 和 `ALPHA_FICC_CLAUDE_AGENT_SCOPES` 已配置基础 research scope：
```
research:read,research:write,research:run,research:propose_revision,render:create,render:read
```

`ALPHA_FICC_HERMES_AGENT_SCOPES` 未设置。V5 端点在 `_authorize_agent_or_user()` 路径下不要求额外 scope，因此 Hermes agent token 仍可访问。
