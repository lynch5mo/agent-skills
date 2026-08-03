# Alpha-FICC API 认证模型参考

2026-05-26 通过源码分析 + HTTP smoke test 确认。

## 认证方法分类

### 1. `_require_operator_or_admin()`

验证 `Authorization: Bearer <token>` 为 JWT user token，且 user.role 为 `operator` 或 `admin`。

```python
# 伪代码
def _require_operator_or_admin(self):
    token = self._get_token_from_request()
    user = access_boundary.verify_token(token)  # JWT only
    if not user: return 401 invalid_token
    if user.role not in ("operator", "admin"): return 403 forbidden
```

**使用端点**（按 `scripts/api_server.py` line numbers）：
- POST `/api/research-loop/v1/proposals` (L25114)
- POST `/api/research-loop/v1/proposals/{id}` (L25076)
- POST `/api/research-loop/evidence` (L25663)
- POST `/api/research-loop/hypotheses` (L25631)
- POST `/api/research-loop/hypotheses/{id}/feedback` (L25692)
- POST `/api/research-loop/hypotheses/{id}/market-validation` (L25692)
- POST `/api/research-loop/v2/revision-proposals/{id}/accept|reject` (L25436)
- POST `/api/actions/run-analysis` (L24997)
- POST `/api/research-loop/v1/proposals/{id}/run` (L25464)

**Agent token 行为**：返回 401 `{"error": "invalid_token"}` — agent token 不是 JWT，`verify_token` 失败。

### 2. `_authorize_research_loop_v2(operation=...)`

先尝试 JWT（`_authorize_agent_or_user`），fallback 到外部 agent token：

```python
def _authorize_agent_or_user(self, *, allowed_agents=None):
    token = self._get_token_from_request()
    if token:
        user = access_boundary.verify_token(token)
        if user: return {"kind": "user", "user": user}
    # Fallback: external agent auth
    agent = _extract_external_agent_credentials(self)
    if _agent_auth_configured() and provided_token:
        agent = _match_external_agent_token(...)
        if agent: return {"kind": "agent", "agent": agent}
    return 401
```

Agent token 走通后，检查 scope：

```python
if auth_ctx.get("kind") == "agent":
    required_scope = RESEARCH_LOOP_V2_REQUIRED_SCOPES.get(operation, "")
    if required_scope and not _external_agent_has_scope(agent, required_scope):
        return 403 AGENT_SCOPE_REQUIRED
```

**Scope 映射**（`RESEARCH_LOOP_V2_REQUIRED_SCOPES`）：
- `read` → `research:read`
- `write` → `research:write`
- `run` → `research:run`
- `validate` → `research:validate`
- `propose_revision` → `research:propose_revision`

**使用端点**：
- POST `/api/research-loop/v2/cases`
- POST `/api/research-loop/v2/models/from-v1-proposal`
- POST `/api/research-loop/v2/runs`
- POST `/api/research-loop/v2/runs/{id}/validate`
- POST `/api/research-loop/v2/revision-proposals`

### 3. `_check_auth()`

仅接受 JWT user token，无 agent fallback：

```python
def _check_auth(self):
    token = self._get_token_from_request()
    user = access_boundary.verify_token(token)  # JWT only
    if not user: return 401
    # Also checks if user is disabled
```

**使用端点**：
- POST `/api/model-proposals`
- POST `/api/model-proposals/{key}/accept`
- POST `/api/model-proposals/{key}/reject`
- POST `/api/research-models`
- POST `/api/research-models/{key}/versions`
- POST `/api/admin/research-models/{key}/disable`

---

## Agent token 身份流程

1. 请求携带：
   - `Authorization: Bearer <token>`（JWT 或 agent token）
   - `X-Alpha-FICC-Agent: hermes`
   - `X-Alpha-FICC-Agent-Key: <token>`（冗余）

2. `_extract_external_agent_credentials()`：
   - 读取 `X-Alpha-FICC-Agent` 规范化 agent 名
   - 读取 `X-Alpha-FICC-Agent-Key` 或 `Authorization Bearer token`

3. `_match_external_agent_token()`：
   - 遍历 `EXTERNAL_AGENT_IDS` 查找匹配的 token
   - 使用 `secrets.compare_digest` 防止时序攻击
   - Token 来源：`ALPHA_FICC_AGENT_API_KEYS` 环境变量（JSON 或 key=value）或 per-agent `ALPHA_FICC_{AGENT}_AGENT_TOKEN` 环境变量

4. Agent 名称规范化（`_normalize_external_agent_id`）：
   - 包含 `hermes` → 返回 `"hermes"`
   - 包含 `claude`/`cloud`/`anthropic` → 返回 `"claude"`
   - 包含 `codex`/`openai`/`gpt` → 返回 `"codex"`

---

## Agent Scope 配置

环境变量（当前状态 2026-05-26）：

| 变量 | 值 |
|------|-----|
| `ALPHA_FICC_HERMES_AGENT_SCOPES` | 未设置 |
| `ALPHA_FICC_CODEX_AGENT_SCOPES` | `research:read,research:write,research:run,research:propose_revision,render:create,render:read` |
| `ALPHA_FICC_CLAUDE_AGENT_SCOPES` | `research:read,research:write,research:run,research:propose_revision,render:create,render:read` |

Scope 可以设置通配符 `*`（所有操作）或前缀通配 `research:*`（所有 research 操作）。

---

## 测试验证模式

### V2 research-loop 端点（旧）

| 端点 | Agent token 预期 | JWT operator/admin 预期 |
|------|-----------------|------------------------|
| POST `/api/research-loop/evidence` | 401 | 201 |
| POST `/api/research-loop/hypotheses` | 401 | 201 |
| POST `/api/research-loop/v2/revision-proposals` | 201（有 scope）or 403（无 scope） | 201 |
| POST `/api/research-loop/v2/revision-proposals/{id}/accept` | 401/403 | 200 |
| POST `/api/research-loop/v2/revision-proposals/{id}/reject` | 401/403 | 200 |

### V4 observation/revision loop 端点（新 — 见 `v4-observation-revision-loop.md`）

| 端点 | Agent token 预期 | JWT operator/admin 预期 |
|------|-------------|-------------------|
| POST `/api/external-evidence` | 201 | 201 |
| POST `/api/external-evidence/{id}/assess` | 201 | 201 |
| POST `/api/impact-mappings` | 201 | 201 |
| POST `/api/observation-tasks` | 201 | 201 |
| POST `/api/revision-proposals` | 201 | 201 |
| POST `/api/revision-proposals/{id}/accept` | 401/403 | 200 |
| POST `/api/revision-proposals/{id}/reject` | 401/403 | 200 |

⚠️ V4 端点接受 agent token（无需 scope），与 V2 research-loop 端点不同。`accept/reject` 仍保留给 operator/admin。

---

## 关键源码位置

- `scripts/api_server.py` 是当前运行的 API 服务器
- auth 方法定义：L20511-20615
- `_require_operator_or_admin`: L24968-24996
- `_authorize_research_loop_v2`: L20615-20655
- `_authorize_agent_or_user`: L20592-20614
- `_extract_external_agent_credentials`: L1504
- `_match_external_agent_token`: L1513
- `_external_agent_has_scope`: L1486
- `_configured_external_agent_scopes`: L1453
- RESOURCE V2 scope constants: L110-115
