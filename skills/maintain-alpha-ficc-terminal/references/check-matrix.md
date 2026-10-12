# Alpha-FICC 维护检查矩阵

## 目的

使用有界、受治理的服务端证据判断服务、Provider、刷新任务和数据 freshness。检查结果只产生严重度候选；权限由 repair policy 独立决定。

## 每轮确定性 probe

调用现有接口，不复制检查实现：

```bash
python3 <skill-root>/scripts/run_maintenance_probe.py \
  --repo-root <production-root> \
  --api-base http://127.0.0.1:8001 \
  --runtime-root <runtime-root> \
  --deadline-s 100 \
  --dry-run
```

`collect_probe()` 的总时限不超过 100 秒，单个 HTTP canary 默认 5 秒，组合输出上限为 16384 字节。读取标准化字段：`id`、`status`、`latency_ms`、`evidence`、`error_type`、`repair_hint`。

| 层面 | 当前确定性检查 | 每轮判断 | 修复后必须复核 |
| --- | --- | --- | --- |
| API | `api.health` | 状态、延迟、结构有效性 | 真实 `/api/health` 与受影响 API |
| Provider | `providers.connectivity`、`providers.health` | DNS/TLS/认证/限流/上游错误类别 | 受治理入口恢复；不直连 Provider |
| 数据目录 | `data_catalog.series` | 代表性读取、响应结构和延迟 | 受影响序列可读、数据点实际推进 |
| 组件数据 | `component.health`、`component_datasets.health` | 组件报告与 API health | 受影响 dataset 的发布/覆盖状态 |
| 刷新 | `refresh.health`、`refresh.low_frequency` | lane 失败、due/backlog、连续失败 | job 成功、候选减少、下一 run 正常 |
| Freshness | refresh 证据与代表性 series | `stale_tail`、空 payload、成功但未推进 | 最近 observation 与 release-aware 日期 |

## 同轮确认

1. 首次异常后等待 1–3 分钟。
2. 只重跑受影响的 bounded check；最多两次。
3. 上述 attempts 和等待窗口都是上限，不是配额。每次等待前按 run hard deadline 计算剩余时间，并至少预留 60 秒用于分类、A3 publication outcome（如适用）、maintenance ledger/local report、cron final output 和 Discord render；另预留 25 秒给 targeted check。
4. 若剩余预算不足以覆盖 `wait + 25 秒 check + 60 秒 reporting`，不开始该次确认，记录 unconfirmed/observed 并按时报告。五分钟运行在 100 秒初始 probe 后最多执行一次 60 秒等待和一次 targeted check；不得执行两次三分钟等待。
5. 将任务失败与服务/数据影响关联。网络抖动或一次 Provider 超时不等于代码缺陷。
6. P0/P1 经确认后立即路由，不等待下一 30 分钟 cron。
7. 无法确认时记录 unconfirmed/observed，禁止修复。
8. 若 A3 的远端可见性无法在 hard deadline 内验证，记 `remote_not_visible` 与 local path，再写 final ledger/Discord；不得为了赶时限提前渲染 `builder_required`。

## 严重度候选

| 严重度 | 证据示例 | 注意 |
| --- | --- | --- |
| P0 | 核心 API、数据库或关键入口整体不可用 | 仍需单独判断 A1/A2/A3。 |
| P1 | low-frequency 连续失败且关键数据 `stale_tail`；多个关键 Provider 异常 | 紧急不等于可改 forbidden surface。 |
| P2 | 单 Provider、单 dataset 或单 API 性能退化 | 可观察、A1 或满足全部门的 A2。 |
| P3 | 偶发失败、容量趋势、证书临期 | 通常记录并观察。 |
| healthy | 所有 bounded checks 正常 | 仍需完整报告。 |

`classify_checks()` 的 `authority_candidate` 只供参考。Skill 必须再读取路径、版本、权限、测试和回滚门。

## Frequency-aware freshness

不要统一用“超过 24 小时”。分别按 daily、weekly、monthly、quarterly、annual 的交易日、发布日期和 Provider release calendar 判断，并结合：

- `coverageStatus` / `recommendedAction`；
- 最近 observation 时间；
- 最近成功 refresh run；
- 数据是否实际推进，而不只看进程退出码；
- 关键 canary 的缺口、异常回撤和空 payload。

## 深检扩展

| 频率 | 追加检查 | 约束 |
| --- | --- | --- |
| 每日 | `scripts/provider_probe_matrix.sh`、refresh 成功率、backlog、遗漏 timer、磁盘/数据库增长 | 严格超时和输出上限。 |
| 每周 | `scripts/verify_postgresql_data_layer.py`、查询延迟、备份恢复证据、HEAD/部署漂移 | 默认只读；schema/index 改动转 A3。 |
| 刷新后 | `scripts/diagnose_observation_refresh_health.py`、代表性序列、component health | 进程成功与数据推进分别验收。 |

## 永久禁用的探测捷径

- 不调用 `/api/terminal-chart-actions/pending`；它会 drain 队列。
- 不用浏览器、React state 或 session storage 猜测服务状态。
- 不直连 FRED、Yahoo、Akshare、BEA、BLS、EIA 等 Provider API。
- 不为检查临时提升 Hermes、借用其他 Agent 凭据或执行 proposal accept/reject。
- 不做无界全库扫描，不保存自由文本错误、响应秘密或原始命令环境。
