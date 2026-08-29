# Runtime and Safety Details

仅在远程卷、FUSE、路径字符、回收站边界问题或执行顺序需要核对时读取本文件。

## 统一前提

1. 任务动作仅在 `TASK_ROOT` 后代（canonical）内执行。
2. 越界判定只用 `Path.resolve()` + 实体关系，不接受字符串前缀。
3. 默认只做可逆 `mv`；除命名合同明确允许，禁止 `rm`、`rm -rf`、`rmdir`（`.DS_Store`、`._*` 除外）。

## 初扫与快通道边界

- 初扫只收路径、目录层级、文件名/类型、视频/NFO/字幕存在性、结构异常和目标碰撞所需信息。
- 初扫禁止读 NFO 内容、跑 `ffprobe`、查 IMDb、算完整 hash、去重或深度归类；文件系统可枚举所有条目，但推理按同类模式和 10–20 项批次进行。
- `NAMING_PASS` 只在 `CORE_GATE` 前进入命名对账，不读 NFO、跑 `ffprobe`/IMDb、算 hash、去重或深查；CORE 通过后必须与所有 active 电影一起进入跨目录 DEDUPE 候选扫描。
- `ACTION_REQUIRED` 只覆盖唯一可判定的语法改名，以及确定的单片 `orphan`/`dispersed` leaf 建夹或 rehome；多视频合集、特殊容器或归属不明一律是 `EXCEPTION`，进入慢通道，不得无动作通过。
- 目标碰撞必须进入 `EXCEPTION`；不得临时加后缀、覆盖或改写锁定计划。

## Expected 路径与来源形态

- 每个视频单元在分类前都要记录 `expected_director_dir`、`expected_movie_dir`、`expected_video_path`、现有 NFO 的 `expected_nfo_path`、字幕的 `expected_subtitle_paths` 和 `source_shape`；缺失 sidecar 明确记录缺失，不造文件。
- `source_shape` 仅取 `standard`（导演直下标准层级且路径精确）、`orphan`（视频不在电影夹）、`dispersed`（影片散落、挂在错误导演层级或位于任意 wrapper 深度）或 `collection`（合集容器含多个影片/导演单元）。
- 期望路径必须由命名合同和已闭环的身份/导演/年份/release 事实逐字生成；无法唯一推导时记录缺失原因并进入 `EXCEPTION`，不得用占位动作代替。

## 工具与执行

- FUSE/远程场景：先确认 mount/uid/可写，再执行写动作。
- `sudo` 仅用于明确授权与必要分批；先保证工作单与计划可写。执行前需排除 `_trash_*` 的临时目录影响，按 TASK_ROOT 内唯一可写隔离策略处理。
- `ffprobe`、抽样 hash、长度/分辨率只作 `EXCEPTION` 或 CORE 后去重的旁证，不替代 naming-contract 与实扫；CORE 前完整 hash 仅用于目标碰撞候选或异常完整性，CORE 后去重可按完整 hash+清单确认精确重复。
- 系统性挂载或权限故障视为任务阻塞，不做猜测性继续执行。

## FUSE、Unicode 与路径形态

- 大卷禁止全树 `find/os.walk`；按 `TASK_ROOT` 子范围分块扫描。
- 看到 `Errno 39`、双实体、路径不可达：只用 `os.scandir()` 返回实体做比对，不拼装 NFC/NFD 变体。
- 可达性依据 `exists/stat/repr + bytes/hash`；`inode` 只在同卷稳定场景辅助，不作为唯一依据。
- 单条动作失败按 `failure-handling.md` 的故障码处理，不做路径猜测重试。

## Sidecar、父目录与清场

- `ACTION_REQUIRED` 先形成同一条 bundle：expected 路径、`source_director_dir`/`expected_director_dir`、`source_shape`、主视频、现有同 stem NFO（缺失则记录，不补造）、每个带语言标识字幕、电影夹/导演夹 old/new，以及必要 `mkdir`/`rehome`；身份不确定时不要在快通道猜配对。
- 通过计划门禁后固定执行：**必要目标目录（计划内 `mkdir`）→ 视频改名/rehome → NFO/字幕 → 电影夹定位/改名 → 已证明为空的 wrapper 骨架一次性可逆归档到 `_work-record_/flattened-empty/` → 导演夹定位/改名 → 现场复扫**。对已有容器仍子项先、父目录后；普通 trash 不在命名序列内。
- wrapper 只允许在其全部可确定影片移出后、递归确认无文件/媒体/symlink 且只剩空目录骨架时归档；未知文件、异常单元、目标碰撞或无法证明为空时相关单元整体 `EXCEPTION`、零 mutation。导演夹只有全部受影响子项闭环、wrapper 归档完成、复扫 PASS 且目标不冲突时才允许改名；否则若旧夹/影片单元仍在 active tree，`CORE_GATE` 必须失败。
- 身份/配对不确定时：普通且非 `TASK_ROOT`/非导演 anchor 的异常 source 若含 unknown/child/multi-video，source 容器本身就是最小完整可逆单元，整体移入 `TASK_ROOT/_待确认_`，禁止只抽一个视频留下残骸；`TASK_ROOT` 或导演 anchor 不得整体移动，只能按明确 main video + 唯一 sidecar 隔离。此边界不等于扩大整个导演或整批媒体；若系统故障无法移动则原地冻结且 CORE_GATE 必须失败。
- 回收统一到 `TASK_ROOT/_trash_<task-id>_<YYYYMMDD>/...`，并保持原相对路径；计划中必须预先锁定目标。合同已明确为垃圾的无语言字幕仅在 `DEDUPE_GATE=PASS` 后按计划 `mv`，不得猜语言。
- `_work-record_`、`_work-record_/recovery/`、`_待确认_`、`_trash_*` 均为可写且在任务内。

## mkdir/rehome 与核心门禁

- `mkdir` 仅允许为已锁定的 `expected_director_dir`、`expected_movie_dir` 或 `_work-record_/flattened-empty` 建立 canonical `TASK_ROOT` 后代；目标必须不存在（已有真实、非 symlink、in-root archive 父目录可复用），父目录必须已通过前置动作，动作有证据和回滚。回滚不得 `rmdir`；任务创建的空目录只能可逆 `mv` 到本任务 trash。
- `rehome`/改名动作必须满足 `old exists`、`new absent`、两者均为 TASK_ROOT canonical 后代；完成后现场证明 old absent、new exists 且逐字等于对应 expected 路径，视频字节和 sidecar 关系不变。
- `CORE_GATE` 只在以下 active 计数全部为 0 时通过：`active_nonconforming_director_dirs`、`active_nonconforming_movie_dirs`、`active_nonconforming_video_files`、`active_nonconforming_nfo_files`、`active_nonconforming_subtitle_files`、`active_orphan_videos`、`active_collection_containers_with_videos`、`active_misfiled_movie_dirs`、`required_actions_remaining`、`partial_bundles`、`unaccounted_video_units`。旧项因系统故障留在 active tree 或原地冻结均使门禁失败。
- 已安全完整移入 `_待确认_` 且记录 pending 目标、来源和恢复路径的单元标记为 `accounted_pending`：不计入 active 违规项，也不计入 `unaccounted_video_units`。`unaccounted_video_units` 只统计既没有 active 最终路径、也没有完整 pending 目标/来源/恢复记录的单元；冻结或旧项留在 active tree 时 CORE_GATE 不得通过。

## 去重门禁与质量证据

- 仅 `CORE_GATE=PASS` 后执行去重；`DEDUPE_GATE` 只核 active media tree（排除 `_待确认_` 与全部 `_trash_*` 媒体内容）；先按影片身份分组，再确认相同 `edition/cut`。不同剪辑、版本或内容不得合并。
- 精确重复必须完整文件 hash 与清单一致；质量重复按可验证排序 `4K > 1080p > 720p`，同分辨率再比较可验证的码率/画质证据，不能只凭文件名或文件大小。
- 质量唯一胜出者保留，较差副本只能可逆 `mv` 到固定 trash，保留原相对路径、证据和回滚。证据不闭环、时长/版本有实质差异或质量无法唯一排序时，若候选组可安全整体隔离则移入 `_待确认_`，记录 `pending_duplicate_groups`，不得自动淘汰。候选组留在 active tree 时 DEDUPE_GATE 失败；整体隔离后不阻塞其他 active 影片继续去重、普通清理和终扫。
- `DEDUPE_GATE` 的 active 计数 `unresolved_duplicate_groups_in_active_tree`、`inferior_copies_remaining_in_active_tree`、`dedupe_actions_remaining`、`partial_dedupe_actions` 必须全部为 0；`pending_duplicate_groups` 仅用于报告，不阻塞其他 active 影片，但待确认>0 时永远不能报告全部整理完成。未通过不得普通清理或终扫。
- 无法裁决的重复关系整体移入 `_待确认_` 后不计入 active DEDUPE 计数，但必须记录 `pending_duplicate_groups` 与来源/恢复证据。

## 执行前校验（逐条）

1. 公共动作字段为 `id/action/target/evidence/rollback/preconditions/postconditions`；`rename`/`rehome`/`trash` 另需 `source`，`mkdir` 不设置伪 `source`。改名/rehome 为 `old exists`、`new absent`、`target parent exists`；`mkdir` 为锁定的 canonical 目标不存在且父目录已就绪。
2. `old/new` 与计划逐字一致，且同为 TASK_ROOT 后代；完成复扫必须有 `old absent + new exists + expected path exact`。
3. `bytes/hash`、sidecar 关系可追溯；每条有证据和回滚路径；mkdir 回滚不使用 `rmdir`。
4. CORE 前完整 hash 仅用于目标碰撞候选精确重复或异常完整性确认；CORE 后按 DEDUPE_GATE 的同片同剪辑规则使用。

任一条件不满足不执行，并立即按对应故障卡处理后再继续明确项。
