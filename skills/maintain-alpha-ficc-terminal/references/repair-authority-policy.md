# 修复权限策略

## 不变量

- 严重度和权限分开：P0/P1 可以是 A3，P3 也只能执行明确允许的 A1。
- 每轮最多一个 repair class、一个动作；A1 与 A2 不混用。
- 运行中的 Hermes 不能扩展 `repair-policy.json`。allowlist 只能通过独立审查、测试和提交改变。
- 任一前置条件未知或失败即 fail closed 到 A3。

## A1：固定运行态动作

只允许 `repair-policy.json.a1_actions` 中的 ID 与固定 argv：

- `refresh_daily`
- `refresh_low_frequency`
- `refresh_catchup`
- `restart_api`
- `restart_web`
- `restart_hermes_relay`

禁止参数拼接、任意 shell、PostgreSQL/Cloudflare 重启、主机 reboot、清理、权限变更和未声明服务。动作前后必须记录版本化 action、退出码、有界输出与命名验证。执行器缺失或 dry-run/测试未验证时，A1 不可用。

## A2：受限代码修补

所有条件必须同时成立：

1. 只有一个 failure domain，问题可稳定复现。
2. 修改恰好落在 `a2_allowed_production_globs`；测试只落在 `a2_allowed_test_globs`。
3. 不命中任何 `forbidden_globs`。`scripts/api_server.py` 初始阶段始终是 A3，即使只改一行。
4. 不改变 API contract、认证/scopes、schema、金融 identity/lineage/单位/频率、治理语义、UI 或依赖。
5. source clone 干净，`HEAD`、已 fetch 的 `origin/main`、起始 base 和生产 `.deployed-head` 满足部署门。
6. 先有稳定失败测试，再有修复后通过、相关回归和真实服务/数据验收。
7. candidate 是 base 的单一 descendant commit；只含允许的一个 production 文件和一个 test 文件。
8. 逐条通过下述 canonical diff/path/filesystem gate；文件数和行数不超过 JSON limits。
9. push 前再次 fetch；`origin/main` 仍精确等于 base。
10. 有精确部署清单、归档、旧 `.deployed-head` 和可执行回滚。

固定 Git/部署路径：

1. 在独立 source clone 从确认的 `origin/main` 建 `hermes-maint/<incident_id>`。
2. RED test → 最小修复 → GREEN/回归 → diff gate → Lore commit。
3. 再次 fetch。远端未变时只允许非强制 push；分支保护拒绝也转 A3。
4. 部署器只同步 gate 批准的精确文件，先归档目标文件与 `.deployed-head`。
5. 重建受影响服务并做真实验收；全部成功后才更新 `.deployed-head`。
6. 验收失败立即恢复归档、重建旧版本、验证回滚并转 A3。

### Canonical diff/path/filesystem gate

`repair-policy.json.a2_candidate_gate` 是 Task 6 必须直接实现的机器契约。只接受 base 到 candidate 的 `git diff --name-status` 记录，并逐项执行：

1. 只接受单路径状态 `M`。拒绝 add/delete/rename/copy/typechange/unmerged/unknown/broken，以及 submodule 和 binary；不把 rename/copy 降格成普通 modify。
2. path 必须是未经清理或重写的 canonical repo-relative POSIX path。拒绝 absolute、空 segment、`.`、`..` 和非 POSIX separator；禁止用 `normpath()` 先消解 traversal 再匹配。
3. 在 base commit 用 Git tree 查询确认 production 与 test 路径均已跟踪，object 为 blob，mode 仅 `100644|100755`。生成文件、新增文件和 base 不存在的路径均拒绝。
4. 在 source clone 从 root 到 leaf 对每个组件执行 `lstat`；任何 parent/leaf symlink 都拒绝。leaf 必须是 single-link regular file（`st_nlink == 1`），且 realpath 必须 containment 于 source clone realpath。
5. canonical path 通过后才使用 `segment_aware_glob_v1`。`*` 不跨 `/`，`**` 才跨 segment；production 与 test 分别命中相应 allowlist，并且所有路径都必须再通过 forbidden list，决策是 allowlist match **且** zero forbidden match。
6. 执行 JSON 中全部 positive/negative test vectors。Traversal、nested path、symlink parent/leaf、rename/copy/typechange/delete、untracked/generated、submodule、binary 和 forbidden match 任一不能拒绝时，A2 executor 不可用，转 A3。

### 远端漂移门

- 编辑前发现 drift：不编辑、不暂存、不准备 patch、不部署，直接 A3。
- candidate 形成后发现 drift：不 rebase、merge、cherry-pick、force/force-with-lease、自动解冲突或部署；保留脱敏证据并转 A3。
- 生产目录无 `.git`，永远不在其中形成代码修补或 Git 操作。

## A3：Building Agent 文件化交接

任一条件触发 A3：

- forbidden path、跨模块/架构、UI、依赖、认证/权限、数据库/schema/migration；
- 金融数据定义、identity、lineage、单位、频率或批量历史重写；
- 无法复现、无失败测试、无真实验收、无精确回滚；
- dirty clone、版本不一致、远端变化、冲突或 push 拒绝；
- 自动修复失败、回滚失败或回滚后仍复现；
- 必要 helper、policy 或权限不存在。

A3 允许继续有界只读取证；禁止代码、Git、部署、服务和身份修改。使用稳定 incident 去重生成 Agent-KB Hermes report。只有远端可见才称已交接；push 冲突写 `handoff_push_failed`，禁止强推。Hermes 不创建或唤醒 Mac task。

## 禁止项

- force push、force-with-lease、自动 rebase/merge/cherry-pick/conflict resolution。
- 直接编辑 Git-less production root。
- 运行时修改 allowlist、limits、scopes、身份或 cron secret reference。
- `/api/terminal-chart-actions/pending`、直接 Provider API、proposal accept/reject。
- 数据库迁移、批量数据重写、依赖升级、跨模块重构。

## 压力下的错误理由

| 错误理由 | 策略结论 |
| --- | --- |
| “只改一行，报表马上要用。” | 行数与时限不改变路径和 remote-drift gate。 |
| “先保存一个未推送补丁。” | 已知 drift/forbidden 后准备补丁也是编辑，禁止。 |
| “服务已恢复，所以可以写 healthy。” | 服务状态不是维护完成状态；先通过报告门。 |
| “没有业务 action，不需要 maintenance ledger。” | 每轮都有 run record、local report、cron output 和 Discord prepared。 |
| “先通知负责人，稍后补 Agent-KB。” | 泛化通知不等于去重、远端可见的文件化交接。 |
| “临时 admin，做完再降权。” | 临时提权仍违反身份边界。 |
