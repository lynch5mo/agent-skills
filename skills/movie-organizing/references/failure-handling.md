# Failure Handling

## 使用规则（先行）

1. 先判断是否触发系统性阻塞（挂载/权限/跨卷不可达/全局不可写）；若满足，任务停止并记录阻塞原因。
2. 若不满足系统性阻塞，按对应 B 码只处理**当前条目**（`entry`），记录证据后继续同批可明确条目。
3. 所有处置均在 `TASK_ROOT` 内完成；`_待确认_` 只接收最小可逆单元。
4. 当前条目执行前先写入统一工作单；未写清楚的条目不许继续执行。
5. 故障卡处理只允许一次性必要回退，不代替阶段门禁。

## 新顺序的故障边界

- 初扫若读取 NFO 内容、运行 `ffprobe`/IMDb、计算完整 hash、去重或做深度归类，视为 B02 阶段跳步；应回到轻量文件名清单并重建扫描证据。
- 先计算 expected 路径和 `source_shape` 再判命名状态：`NAMING_PASS` 在命名阶段只做 exact-path 复扫并进入 CORE 对账，CORE 通过后与全部 active 电影一起进入 DEDUPE 候选扫描；`ACTION_REQUIRED` 必须有完整 naming bundle；只有 `EXCEPTION` 才进入 `明确/待查/冲突` 与有限查证。
- `CORE_GATE` 前，`NAMING_PASS` 不得因恢复、父目录改名或其他条目异常而重新深查；CORE 通过后它必须与全部 active 电影一起参加 DEDUPE 候选扫描。未闭合 bundle、目标碰撞和部分执行按相应 B 卡单项隔离。
- `CORE_GATE` 未通过不得清理、去重或发完成语义；`DEDUPE_GATE` 未通过不得普通 trash 或终扫。
- 安全完整移入 `_待确认_` 且有 pending 目标、来源和恢复记录的单元标记为 `accounted_pending`：不计入 active 违规或 `unaccounted_video_units`；`unaccounted_video_units` 只统计既无 active 最终路径、又无完整 pending 记录的单元。系统故障导致单元只能原地冻结时，门禁必须失败。

## B01 范围越界

- 触发：计划/执行目标不在 `TASK_ROOT` 后代（含 symlink 解析后）。
- 禁止：将整批媒体迁移到待确认、将越界计划留在任务内继续执行、在上级目录建 pending/trash。
- 处理：
  1) 停该条；2) 现场复扫受影响条目；3) 重建该批**最小**计划，只含本次受影响项；4) 将越界条目按 B03 重构后继续。
- 通过：重建计划内所有条目都 canonical 落在任务内。
- 未通过：未确认条目停止该条；不影响其他明确条目。

## B02 阶段跳步

- 触发：门禁缺失/未 PASS 却进入下一阶段、用工作单进度替代逐阶段验收，或在初扫/命名快通道读取 NFO 内容、运行 `ffprobe`/IMDb、计算完整 hash、去重/清理或深度归类。
- 禁止：跳过未通过阶段执行、直接发终态报告。
- 处理：回退到最近未通过阶段，补齐产物并复盘；若规模过大可将未闭环项重组成更小固定批次从阶段1重走。
- 通过：阶段链完整通过。
- 未通过：明确项不得越界；其余明确项可在其自身阶段闭环后继续。

## B03 计划漂移与无效动作

- 触发：`scan_id/standard_id/plan_hash` 缺失或不一致；bundle 缺 `expected_*`/`source_shape`、导演夹/电影夹/视频/NFO/字幕/必要 mkdir/rehome 任一项；动作缺公共字段 `id/action/target/evidence/rollback/preconditions/postconditions`；`rename`/`rehome`/`trash` 缺 `source`，或 `mkdir` 带伪 `source`；`old==new`；重复目标；包含 `sentinel`/`__KEEP__`/`__SKIP__`。
- 禁止：自动剔除异常项后继续执行、将异常直接打为待确认。
- 处理：停止该批执行；按当前扫描重建本批计划（含新 hash）；保留受影响条目并重新门禁。
- 通过：新计划字段齐全（含 plan 级与动作级字段）且可执行、无冲突目标。
- 未通过：只停止该条/该批，并进入对应 B 卡，不要求新任务根授权。

## B04 中断恢复

- 触发：重启后批次状态不清，或命名复扫/父目录改名中断导致 bundle 部分执行。
- 禁止：盲目重跑整批。
- 处理：先复扫；对每条标注 `未执行`/`已执行`/`部分执行`；已执行条目做 `old/new/sidecar/expected/evidence` 校验，要求 old absent + new exists；未完成条目按 B 卡处理。去重中断还要核对四项 DEDUPE 计数。
- 补充：`CORE_GATE` 前已 `NAMING_PASS` 项保持早退出，不重新读取 NFO、运行 `ffprobe`/IMDb、计算 hash、去重或深度归类；CORE 后统一进入候选扫描，Agent 再按证据核对 edition/cut/质量。
- 通过：现场状态与工作单对齐后从未完成条目恢复。
- 未通过：仅该条冻结/待确认，明确项继续。

## B05 FUSE / Errno39 / 双实体

- 触发：实体不可达、跨卷实体错乱、路径实体分叉。
- 禁止：自行构造 NFC/NFD 路径重试；无穷重试；把 inode 当唯一依据；执行中 `rmdir`。
- 处理顺序（严格）：
  1) 停该条所有写操作；
  2) 用 `os.scandir()` 重新枚举实体与可达性，必要时再补 `os.listdir()`；
  3) 若路径有真实子项且该批计划已锁定，先按锁定计划处理子项；
  4) 若仅剩空壳，CORE 阶段不得提前清理；仅在 `DEDUPE_GATE` 通过且计划已预锁定 `trash` 后，最多尝试一次可逆 `mv` 到任务内 `trash`；
  5) 仍失败或 old/new 出现无法唯一确认的双实体时，仅冻结/待确认，不得原地散乱移动，`inode` 不可裁决；
  6) 任一系统性异常可升级为任务阻塞。
- 通过：单条路径映射稳定、可达且与计划一致；`bytes+必要时完整 hash` + 可达证据可复核。
- 未通过：该条入待确认或冻结；系统性异常可升级到任务阻塞。

## B06 路径字符/Unicode 实体问题

- 触发：空格、单引号、重音、特殊字符导致读写失败。
- 禁止：拼字符字符串猜测路径；命令行临时尝试路径。
- 处理：以 `scandir` 返回实体为准校验；导演中文译名只按可唯一解析的 v1.3.3 迁移分隔符规则把 ASCII 空格/`.` 改为 U+00B7 `·`，不猜姓名。目标存在、Unicode/case 碰撞或边界不明时不改名，相关导演及子项转 `EXCEPTION`。
- 通过：逐字与实体路径一致，证据链完整。
- 未通过：该条冻结或待确认，不扩大范围。

## B07 主视频 / 身份误判

- 触发：按扩展名、时长、或主观优先级判断主视频，或把语义不确定项、多视频合集/特殊容器、孤立/分散结构错误放入 `NAMING_PASS`/`ACTION_REQUIRED`。
- 禁止：猜测改名/移动。
- 处理：确定的单片孤立/分散 leaf 可走命名 bundle；多视频合集/特殊容器和归属不明只在 EXCEPTION slowpath 以 naming-contract、`NFO`、同夹 sidecar、文件字节与目录结构逐片闭环；普通且非 `TASK_ROOT`/非导演 anchor 的异常 source 含 unknown/child/multi-video 时，pending 隔离必须整体移动该 source 容器，不能抽视频留残骸；`TASK_ROOT`/导演 anchor 只可隔离明确 main video + 唯一 sidecar，不能扩大整个导演或整批媒体；纯语法 `ACTION_REQUIRED` 不改变现有身份事实。
- 通过：主视频与 sidecar/身份映射闭环。
- 未通过：进入待确认或冻结；旧导演夹/影片单元仍在 active tree 时 CORE_GATE 失败；同任务其余明确项继续。

## B08 重复与多版本误判

- 触发：在 `CORE_GATE` 前去重；仅凭文件名、大小、时长、分辨率或抽样 hash 判重复；未先按身份和 edition/cut 分组；或质量证据不闭环却淘汰副本。
- 禁止：以 `full-hash` 外的方式判为精确重复；把不同剪辑/版本/内容合并；对差异版本删改；在 `DEDUPE_GATE` 前普通清理。
- 处理：仅 `CORE_GATE=PASS` 后进入 DEDUPE；先按影片身份分组，再确认同一 `edition/cut`。精确重复须完整文件 hash+清单一致；质量比较按 `4K > 1080p > 720p`，同分辨率须有可验证码率/画质证据。质量唯一胜出者保留，较差副本可逆 `mv` 到固定 trash 并记录原相对路径/证据/回滚；证据不闭环、实质差异或质量无法唯一排序时保留并将候选最小单元移 `_待确认_`，不得自动淘汰。
- 通过：`unresolved_duplicate_groups_in_active_tree`、`inferior_copies_remaining_in_active_tree`、`dedupe_actions_remaining`、`partial_dedupe_actions` 全为 0，且 active 现场与工作单一致。
- 无法裁决的重复关系若整体移入 `_待确认_`，改记 `pending_duplicate_groups`，不计入 active DEDUPE 计数；候选仍在 active tree 时 `unresolved_duplicate_groups_in_active_tree` 非零，不能通过。
- 未通过：任一 active 计数非零、动作部分执行或无法安全隔离时，停止普通清理/终扫；可安全隔离的未决候选不阻塞其他 active 影片继续，系统故障只能冻结且 DEDUPE_GATE 失败。

## B09 sidecar 同步误配

- 触发：sidecar basename 不配或跨夹映射；或命名合同已明确该 sidecar（如无语言标识的 `video.srt`）为垃圾。
- 禁止：侧重主视频改名并拖累其余文件。
- 处理：先闭环主视频；合同明确为垃圾的 sidecar 在 `DEDUPE_GATE=PASS` 后按预锁 `trash_target` 可逆 `mv`；身份/配对不确定时将主视频及 sidecar 组成的最小完整电影单元入 `TASK_ROOT/_待确认_`。
- 通过：主视频闭环且 sidecar 可复核配对，或合同明确为垃圾的 sidecar 已在 DEDUPE_GATE 后留下可逆 `mv` 证据。
- 未通过：未决单元留在 active tree 或无法证明 expected sidecar 路径时，CORE_GATE 失败；系统故障只能冻结。

## B10 trash 冲突与可逆恢复

- 触发：`old/new/trash` 冲突、basename 冲突、不可逆映射。
- 禁止：执行中临时换垃圾目录。
- 处理：trash 路径在 DEDUPE_GATE 后预定义为 `TASK_ROOT/_trash_<task-id>_<YYYYMMDD>/...` 并保留原相对结构；冲突触发 B03 重建，命名/去重动作不得临场换目录。
- 通过：`trash` 与恢复关系一一绑定、可逆验证。
- 未通过：该条冻结/待确认，其他明确条目继续。

## B11 权限与证据不可写

- 触发：`work-record`、`evidence` 或关键路径不可写。
- 禁止：工作单不可写还执行写动作；向外部旁路写入。
- 处理：
  1) 工作单/证据全局不可写：任务停；
  2) 仅单个 `evidence` 文件不可写：改写 `TASK_ROOT/_work-record_/recovery/` 下唯一新证据文件并更新工作单，重算工作单 hash。
- 通过：全局可追溯且工作单可持续更新。
- 未通过：该任务阻塞；明确项不能继续写。

## B12 报错重试策略

- 触发：同一动作持续报错。
- 禁止：全部错误都重试。
- 处理：按故障卡分流；仅故障卡定义的瞬态异常可做一次受控重试，否则直接转入条目级待确认/冻结。
- 通过：重试后现场复扫通过且无新增异常。
- 未通过：仅该条停住，记录一次性结论继续其他明确项。

## B13 假完成

- 触发：工作单/Agent 声称完成但任一 expected 路径不精确、旧名/非规范 NFO/字幕仍在、孤立视频/合集容器/错误导演归属仍在 active tree，或任一 CORE/DEDUPE 计数（含 `active_nonconforming_nfo_files`、`active_nonconforming_subtitle_files`、`unresolved_duplicate_groups_in_active_tree`）非零；也包括“扫描完成”“计划生成”“命令零退出”被当作动作完成、原地冻结被当作待确认归零，或 active 影片为 0 且只剩待确认视频却声称核心完成。
- 不可合理化：扫描完成 ≠ 改名完成；计划生成 ≠ 动作执行；命令零退出 ≠ 现场 PASS；旧名仍在 ≠ 完成；原地冻结 ≠ 待确认归零。
- 禁止：用返回码、工作单状态或“看起来规范”替代现场核验；不得在 CORE_GATE/DEDUPE_GATE 未通过时发完成语义。active 影片为 0 且只剩待确认视频时保持 `STOP_PENDING_CONFIRMATION`、`next_allowed=null`，只能报告“无可继续自动处理，待确认 N 项”。
- 处理：回到 B04；恢复未执行项，逐条核验 `old/new/sidecar/expected`，重算 CORE/DEDUPE 计数，更新工作单与批次状态。多层 wrapper 只有在全部可确定 leaf 已移出、递归无文件/媒体/symlink、只剩空目录骨架时，才可按计划一次性可逆改名到 `_work-record_/flattened-empty/`；wrapper 残留未知内容或异常单元时零 mutation，不能以“拍平完成”自报。
- 通过：现场扫描、expected 路径、计划、工作单及全部门禁计数完全一致。
- 未通过：该条回到待确认或冻结；冻结项仍在 active tree 时门禁保持失败，其它明确条目继续。

## B14 单项异常阻塞

- 触发：单条错误影响批次，需区分系统性与实体性。
- 禁止：默认任务级停摆。
- 处理：先按症状映射到 B05/B11/Bxx；仅不明确的单项进入待确认/冻结，不影响明确项。
- 通过：异常项隔离且其余条目闭环。
- 未通过：若升级为系统性阻塞，任务停止并等待决策。

## Bxx 未知故障

- 触发：规则库外新故障。
- 禁止：先做最小媒体动作。
- 处理：停当前条；若可安全且不扩大范围，移该条最小完整电影单元到 `TASK_ROOT/_待确认_`；若不可移动则原地冻结并明确 CORE/DEDUPE 门禁失败；记录原因+证据+恢复路径。
- 通过：不扩大范围、证据可复核，继续其他明确项。
- 未通过：任务级阻塞，等待用户决策。
