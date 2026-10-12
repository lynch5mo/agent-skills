# Ubuntu Hermes 运行契约

## 运行角色与路径

Hermes 是唯一执行主体，继续使用既有 scoped `hermes` 身份。`alpha-ficc-maintainer` 仅是运行/审计标签，不是新 API 身份或凭据。

| 用途 | 路径/来源 |
| --- | --- |
| 已安装 Skill | `~/.hermes/skills/maintain-alpha-ficc-terminal/` |
| Hermes cron wrapper | `~/.hermes/scripts/alpha-ficc-maintenance-probe.py` |
| A2 source clone | `/home/lynch5mo/alpha-ficc-maintainer-source` |
| 生产 artifact root | `/home/lynch5mo/alpha-ficc`（无 `.git`） |
| 维护 runtime root | 由 installer state 确认；不得猜测 |
| Cron output | `~/.hermes/cron/output/<job-id>/` |

代码、生产 artifact 和运行状态必须分离。凭据只通过现有 secret reference 使用，不复制进 Skill、cron prompt、installer state、日志或报告。

## Native cron

- Schedule：`every 30m`。
- Job：`Alpha-FICC 维修站半小时维护`，精确匹配并幂等 create/update，不重复创建。
- Skill：`maintain-alpha-ficc-terminal`。
- Pre-run：安装在 Hermes scripts 目录的受限 wrapper，硬时限 120 秒，内部 probe 总时限 100 秒。
- Delivery：`discord:<维修站目标>`；final response 后由 gateway 自动投递。
- 正常轮也返回中文报告，禁止 `[SILENT]`。

不要再创建 Alpha-FICC 独立的 30 分钟 systemd timer。只验证 Hermes gateway 常驻、cron next run、实际 output 和 Discord delivery。

安装器入口为仓库内的 `scripts/install_alpha_ficc_maintenance_skill.py`。它只在
`--apply` 时动作：先以固定参数读取 gateway/cron status，使用 staging 目录完整
替换 `~/.hermes/skills/maintain-alpha-ficc-terminal/` 与 `~/.hermes/scripts/alpha-ficc-maintenance-probe.py`，再通过 Hermes
原生 CLI 对账 cron。`--dry-run` 只输出计划，不创建目录、不读取或修改 Hermes
状态、不执行 readiness/A2 命令。

`--agent hermes` 的 Skill 根目录固定为 `<hermes_home>/skills`。CLI 保留
`--agents-home` 仅为旧调用方兼容参数；它不是 Hermes 的安装目标，安装器不会向
`.agents` 写入或创建 Skill，也不会自动删除已有的旧副本。

Hermes 真源是 `cron create` / `cron edit`。安装器的每个 Hermes CLI 子进程都使用
计划中固定的 `HERMES_HOME`；gateway status 必须包含 running marker，不能只看
零退出码。安装器只读取 `~/.hermes/cron/jobs.json`（严格大小、所有权、模式、
重复键/非有限数值和 JSON 值控制字符边界），按精确 job name 对账：0 个匹配使用
`create`，1 个匹配使用 `edit`，多于 1 个直接失败；绝不直接写 `jobs.json`、删除
重复任务或猜选某一份。成功后必须重新读取并精确验证 schedule、prompt、delivery、
skills、相对 script 和唯一 job id。若原生 cron 已成功变更而后续验证或本地 state
阶段失败，安装器会用固定 `cron remove` 或原 spec 的 `cron edit` 回滚；回滚无法
确认时必须报告 `reconciliation-required`，不能宣称安装完成。即使 `create`/`edit`
返回 nonzero、timeout 或 output-truncated，也必须先重读 jobs：能唯一识别变更就
回滚，无法唯一识别但可能已变更则直接进入 reconciliation-required。旧 job 的
snapshot 支持重复 `--skill`、`--clear-skills` 和空 script；其余失败恢复旧 Skill、
wrapper、配置与 installer state，并清理 staging/backup。

wrapper 同目录的 `alpha-ficc-maintenance-probe.json` 与 runtime 的
`installer-state.json` 都是 0600、单链接、当前用户拥有且有大小上限的严格 JSON；
wrapper 会拒绝重复键/`NaN`/`Infinity`，重算不含 fingerprint 字段的 canonical
SHA-256，并要求两份配置完全一致。wrapper 不接受调用方参数，也不从环境读取命令
或凭据；记录的 job id 必须唯一且精确匹配固定 job name。它以 timezone-aware ISO
时间维护 `last_reconciled_job_run_at`，只在新的 `last_run_at` 严格大于该值时消费；
`last_status=ok` 且无 `last_delivery_error` 才追加 `delivered`，其余只追加
`failed`/`delivery_failed`，错误正文不持久化。之后清理环境，仅保留固定 PATH 和
可选 HOME/LANG/LC*/TZ，以固定 `/usr/bin/python3 -I` argv、`deadline-s=100`、
`os.execv()` 运行已安装 probe。

`passive` 与 `a1` 永远保持 `a2_enabled=false`。`a2` 只能由固定
`/usr/local/libexec/alpha-ficc-a2 status --json` 返回的 root-owned、Hermes
不可写、未过期 readiness 与 verifier/base image/baseline/canonical remote/
Docker host/context/policy/control-plane 全部匹配的 JSON 开启；调用者不能提供
marker、status binary 或路径，安装器也不创建、刷新或修补 readiness。首次 Ubuntu
rollout 仍只允许 passive；本地 fake-runner 测试不构成真实 Ubuntu、Discord 或
production A2 证据。

## 每轮 preflight

1. 从 installer state 读取非秘密 job ID、runtime root、mode 和配置 fingerprint。
2. 从可信 Hermes job state 对账上一轮 `last_status`/`last_delivery_error`；通过 `MaintenanceStore` 追加 delivery event，不改原 run。
3. 确认 executor=`hermes`、record role=`scoped_agent`；不提权。
4. 获取 maintenance lease。active lease 时写 `skipped_due_to_active_run` 和报告，绝不并发 probe/repair。
5. 解析 production `.deployed-head`；A2 另检查 source clone clean `HEAD` 与 fetched `origin/main`。
6. 读取模式：`passive` 禁止 A1/A2；`a1` 只允许 A1；`a2` 仍须逐项通过 A2 policy，不能暗含 A1/A2 自动放宽。

过期 lease 可回收，但必须追加 previous holder=`abandoned` 事件。不得删除历史来“解锁”。

## 生产与 A2 source clone

- 生产 root 是部署 artifact，不是 source workspace；禁止在其中编辑、commit、checkout、rebase 或生成 patch。
- A2 只在干净 source clone 工作。开始和 push 前都 fetch `origin/main`。
- 远端 drift、dirty clone、branch protection 或冲突立即 A3；不 force/force-with-lease，不自动整合。
- 部署器只接收 gate 批准的 commit 和精确文件清单。apply 前归档目标文件与 `.deployed-head`；真实验收后才更新 deployed head。
- 验收失败恢复归档并重建旧版本；回滚也必须验证。

### A2 candidate gate

`check_maintenance_patch.py` 是 privileged A2 commit、push 与部署前的唯一机器门。Hermes 不能传入 source、remote、verifier、test path、argv、exit code 或 evidence；固定 launcher 从 `/var/lib/alpha-ficc-maintainer/a2` 加载 locked config/readiness/baseline/key。允许结果必须同时证明：

- checkout clean，`HEAD == candidate`，已 fetch 的 `origin/main == base`；
- candidate 的 parent 列表精确为一个 base，不允许 merge 或多 commit；
- `base..candidate` 的每条 `git diff --name-status` 精确为单路径 `M`；
- 每条路径未经 normalize 即是 canonical repo-relative POSIX path；
- production tree entry 与 candidate 必须精确为 mode `100644` 的 blob；
- clone 内从 root 到 leaf 没有 symlink，leaf 是 single-link regular file，realpath containment 成立；
- 路径命中对应 production/test allowlist 且不命中任何 forbidden glob；
- binary、submodule、add/delete/rename/copy/typechange、untracked/generated 与超限 diff 全部拒绝；
- 所有 Git object read 都使用 clean env + `GIT_NO_REPLACE_OBJECTS=1`，并拒绝 replace refs、grafts、alternates、commondir、shallow、remote helper 和 unexpected config；
- gate 从批准 diff 推导唯一 test path，并在 immutable verifier image 内以 non-root、read-only、network none、无 Docker socket/host secrets、`cap-drop=ALL`、`no-new-privileges`、资源限额和硬超时执行固定 pytest argv；
- verifier 自行生成并解析 bounded RED/GREEN JUnit（tests>0、RED failures>0/errors=0、GREEN failures=0/errors=0），绑定 runner/image/policy/base/candidate/test/argv/time 和 artifact digest；调用者自报 evidence 一律拒绝；
- JSON 中所有 positive/negative vectors 在当前实现上通过。

调用示例（A2 根目录由安装器固定，调用者不能覆盖）：

```bash
alpha-ficc-a2 evaluate \
  --base-oid "$base_oid" --candidate-oid "$candidate_oid"
```

只持久化带外部 HMAC 的 `allowed=true` gate artifact。该 artifact 的 `files` 是后续部署唯一允许的清单。发布只能由同一 deployment journal 的 `publishing` 事务触发；Hermes 不能单独调用 push。

### Dry-run-first 部署与回滚

Python deployer 只接受已持久化 gate id，不从工作树、`git diff`、glob、caller evidence 或调用方参数另行推导文件：

```bash
alpha-ficc-a2 dry-run --gate-id "$gate_id"
```

必须先保存并审查 dry-run JSON，再以相同 gate id 调用 `alpha-ficc-a2 apply`。dry-run 只消费既有 gate 与已持久化部署状态，零 fetch、零 network、零 source/deploy/固定 A2 根目录 write、零 Docker，不创建 bundle，也不写 `.deployed-head`。

apply 的固定顺序：

1. 拒绝 source/deploy/evidence/compose/target 的任何 symlink component、hardlink leaf 或 containment 失败；确认生产 `.deployed-head == base`，生产目标内容等于 gate 记录的 base blob。
2. 在 `/var/lib/alpha-ficc-maintainer/a2/deployments/<deployment-id>/` 先创建 durable journal 与 HMAC bundle；备份精确 production artifact/metadata、旧 image、old head 和 trusted compose。
3. 由 previous immutable API image digest 生成只含 `FROM`/`COPY` 的 context，只有一份 approved production `100644` Python file；`docker build --network=none` 不消费 source clone、production root、test 或完整 candidate tree。
4. 使用 generated image-only override 执行固定 `docker compose --no-build` runtime switch，再做固定 health/module/import/data freshness checks；production container 不运行 pytest。
5. 验收成功后才进入 `publishing`，调用 fixed non-force push；确认远端 candidate 后最后 fsync/rename `.deployed-head` 并提交 `committed`。进入 `publishing` 后的 push/确认/head fsync 异常或 `INT`/`TERM`/`HUP` 只能先查询 canonical ref：远端仍为 base 才允许 durable bundle offline rollback；远端为 candidate 时校验本地 image/file/health 并完成 head+`committed`；远端为 other/unavailable 或 head 仍不可写时保持 `publishing`，返回 `git_reconciliation_required` 与完整 phase/head/image/health/recovery 字段。进入 `publishing` 以前的故障才可直接 offline rollback。

人工回滚只需 privileged deployment id 与固定 A2 根目录中的受保护 bundle；不读取 source、不 fetch remote、不重跑 gate：

```bash
alpha-ficc-a2 rollback \
  --deployment-id "$deployment_id"
```

部署器不接受额外参数、shell command、用户给定 compose/test 命令、相对路径或 glob；不得使用 `eval`。apply/rollback 只能在同一 `flock` 与 maintenance lease 持有期间执行，bundle HMAC 绑定 lease/deployment-id 并拒绝 replay/traversal。

## Discord 状态对账

当前 run 只能写 `prepared`，因为 gateway 在 Agent final response 后投递。下一 run 或外部验收根据 job state 追加 `delivered`/`failed` event。不要把 P1、A3、healthy 等业务状态写进 delivery status 字段。

报告发送失败不回滚已经必要且成功的 P0 A1 恢复，但运行必须保留本地 evidence，标记 delivery failure，并在下一次成功消息补报。报告持久化失败则使用 reporting contract 的失败状态，不能宣告维护完成。

## 安全边界

- 不调用 `/api/terminal-chart-actions/pending`。
- 不提升或替换 Hermes 身份，不执行治理 accept/reject。
- 不授予任意 root shell；主机操作只能经固定 wrapper/最小 sudoers。
- 每个子检查有 timeout 和 byte cap；每轮单实例。
- Discord 是单向 report-only，不是远程 shell、命令机器人或跨 Agent 聊天。
- A3 只发布 Agent-KB handoff；Mac Building Agent 由用户人工启动。
- A3 必须在 final immutable maintenance ledger 和 Discord render 前完成 clone-local Hermes instance 检查、`agent_finish.sh` closeout 与远端可见性判定；最终消息只渲染已确定的 publication status/path。
