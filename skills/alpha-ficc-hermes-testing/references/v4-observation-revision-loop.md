# Alpha-FICC V4 Observation/Revision Loop

2026-05-26 通过官方脚本 `scripts/verify_v4_observation_revision_loop.py` 验证（deployed-head=549fb91f8）。

## 全链路流程

```
ExternalEvidence → SourceAssessment → ImpactMapping → ObservationTask → ObservationRun → ModelHealthDelta → RevisionProposal
```

## V4 端点（完整列表）

| 方法 | 端点 | 用途 |
|------|------|------|
| POST | `/api/external-evidence` | 创建 external evidence 条目 |
| GET | `/api/external-evidence/{evidenceId}` | 回读 evidence |
| POST | `/api/external-evidence/{evidenceId}/assess` | 创建 source assessment (关联证据) |
| POST | `/api/impact-mappings` | 创建 impact mapping (关联证据+评估) |
| GET | `/api/impact-mappings/{mappingId}` | 回读 mapping |
| POST | `/api/observation-tasks` | 创建 observation task |
| GET | `/api/observation-tasks/{taskId}` | 回读 task |
| POST | `/api/observation-tasks/{taskId}/run` | 执行 observation run |
| GET | `/api/observation-runs/{runId}` | 回读 run |
| GET | `/api/model-health-deltas` | 列出 model health deltas |
| GET | `/api/model-health-deltas/{healthDeltaId}` | 回读 health delta |
| POST | `/api/revision-proposals` | 创建 revision proposal |
| GET | `/api/revision-proposals/{proposalId}` | 回读 proposal |
| POST | `/api/revision-proposals/{proposalId}/accept` | 接受 proposal (需 operator/admin) |
| POST | `/api/revision-proposals/{proposalId}/reject` | 拒绝 proposal (需 operator/admin) |

V3 validation run 作为中间依赖（V4 observation run 需要 validationRunId）：
| POST | `/api/chart-annotation-validation-runs` | 创建 V3 validation run |

## Schema 版本

| 对象 | schemaVersion |
|------|---------------|
| externalEvidenceItem | `alpha-ficc-external-evidence-item-v1` |
| sourceAssessment | `alpha-ficc-source-assessment-v1` |
| impactMapping | `alpha-ficc-impact-mapping-v1` |
| observationTask | `alpha-ficc-observation-task-v1` |
| observationRun | `alpha-ficc-observation-run-v1` |
| modelHealthDelta | `alpha-ficc-model-health-delta-v1` |
| revisionProposal | `alpha-ficc-revision-proposal-v1` |

## ID 前缀约定

| 对象 | 前缀 | 例子 |
|------|------|------|
| evidenceId | `eei_` | `eei_usdcnh_policy_event_001` |
| assessmentId | `sa_` | `sa_usdcnh_policy_event_001` |
| impactMappingId | `im_` | `im_usdcnh_policy_event_001` |
| taskId | `obs_` | `obs_usdcnh_policy_event_001` |
| runId | `orun_` | `orun_usdcnh_policy_event_001` |
| healthDeltaId | `mhd_` | `mhd_usdcnh_policy_event_001` |
| revisionProposalId | `rp_` | `rp_usdcnh_policy_event_001` |

## V4 认证模型

与 V2 research-loop 端点（`/api/research-loop/evidence` 等需 `_require_operator_or_admin`）不同，**V4 端点接受 agent token**。

| 端点 | Agent token | JWT operator/admin |
|------|-------------|-------------------|
| POST `/api/external-evidence` | ✅ 201 | ✅ 201 |
| POST `/api/external-evidence/{id}/assess` | ✅ 201 | ✅ 201 |
| POST `/api/impact-mappings` | ✅ 201 | ✅ 201 |
| POST `/api/observation-tasks` | ✅ 201 | ✅ 201 |
| POST `/api/observation-tasks/{id}/run` | ✅ 201 | ✅ 201 |
| POST `/api/revision-proposals` | ✅ 201 | ✅ 201 |
| POST `/api/revision-proposals/{id}/accept` | ❌ 401/403 | ✅ 200 |
| POST `/api/revision-proposals/{id}/reject` | ❌ 401/403 | ✅ 200 |

认证头格式：
```
Authorization: Bearer <token>
X-Alpha-FICC-Agent: hermes
```

## 执行方式

### 容器内执行（推荐 — 环境变量完整）

```bash
docker exec alpha-ficc-api python scripts/verify_v4_observation_revision_loop.py \
  --base-url http://127.0.0.1:8001 \
  --agent hermes \
  --timeout 20
```

容器内有正确的 `ALPHA_FICC_HERMES_AGENT_TOKEN` 环境变量，无需额外配置。

### SSH 透传执行（Shell 转义注意）

```bash
ssh -o BatchMode=yes lynch5mo@192.168.10.33 \
  "docker exec alpha-ficc-api python scripts/verify_v4_observation_revision_loop.py \
  --base-url http://127.0.0.1:8001 --agent hermes --timeout 20"
```

⚠️ 复杂命令建议封装到 wrapper shell script，避免 shell 转义问题。

### 仅校验 fixture contract（不触发 HTTP）

```bash
docker exec alpha-ficc-api python scripts/verify_v4_observation_revision_loop.py --contract-only
```

## 预期输出

```
=== Verify: Alpha-FICC V4 Observation Revision Loop ===
[PASS] contract: /app/tests/fixtures/external_evidence_usdcnh_policy_event.json
[PASS] contract: /app/tests/fixtures/agent_observation_task_usdcnh.json
[PASS] HTTP smoke: external evidence -> assessment -> impact mapping -> observation run -> health delta -> revision proposal
EXIT_CODE=0
```

## V4 验收标准

| 条件 | 通过标志 |
|------|---------|
| exit code | 0 |
| 两条 [PASS] contract 输出 | 出现 |
| [PASS] HTTP smoke 全链路输出 | 出现完整行 |
| revision proposal 创建 | HTTP 201，proposalId 以 `rp_` 开头 |
| proposal 初始状态 | `draft` 或 `submitted` |
| agent token accept/reject | 返回 401 或 403 |
| baseModelVersionId 未被改写 | GET 回读与创建时一致 |

## 已知坑

### 不要写临时脚本
仓库中已经有 `scripts/verify_v4_observation_revision_loop.py`。如果不是在仓库中找到的，说明还没部署到该 commit。先告知用户，不要自创脚本。部署后 (`deployed-head=<hash>`) 再执行。

### 不要改写 HTTP 4xx 为"预期通过"
如果脚本失败并返回 401，如实报告失败。不要替用户做"agent token 本来就不能 access"的推理修正。验收脚本自己定义了什么算 pass 什么算 fail。

### 返回原始输出
用户要求的是 raw stdout/stderr，不是加注释的版本。摘要后加简要事实陈述即可。
