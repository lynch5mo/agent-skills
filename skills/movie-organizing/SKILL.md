---
name: movie-organizing
description: >-
  Use when a user asks an assistant to normalize or deduplicate a mixed,
  inconsistently named, orphaned, dispersed, or collection-based movie library
  within an explicitly bounded TASK_ROOT.
license: MIT
metadata:
  version: "1.3.4"
  author: lynch5mo
  tags: [media, movie-library, batch-plan]
  trigger: User asks to normalize, rehome, deduplicate, or quality-select a mixed movie library in batches.
---

# Movie Organizing

## v1.3.4 入口完整性与固定命令顺序（硬门禁）

每个任务开始时，必须先验证已安装 Skill 的关键文件完整性；验证失败不得处理媒体。命令顺序固定为：

```bash
SKILL_DIR="/path/to/movie-organizing"
python3 "$SKILL_DIR/scripts/movie_organizing_audit.py" verify-install --skill-dir "$SKILL_DIR"
# 仅当上一步返回 PASS 后，才锁定 TASK_ROOT 并运行以下命令
SCRIPT="$SKILL_DIR/scripts/movie_organizing_preprocessor.py"
python3 "$SCRIPT" plan --task-root "$TASK_ROOT"
python3 "$SCRIPT" apply --task-root "$TASK_ROOT" --dry-run --plan <recovery/plan-*.json>
python3 "$SCRIPT" apply --task-root "$TASK_ROOT" --plan <recovery/plan-*.json>
python3 "$SCRIPT" verify --task-root "$TASK_ROOT" --plan <recovery/plan-*.json>
python3 "$SKILL_DIR/scripts/movie_organizing_audit.py" audit --task-root "$TASK_ROOT"
```

`verify-install` 使用 Skill 自带的标准库 checksum/size manifest，并拒绝 `[OUTPUT TRUNCATED` 等截断标记；它不读取或修改媒体。`preprocessor verify` 的 PASS 只代表命名计划执行验证（结果含 `naming_plan_only=true`），不代表任务完成。最终工作单和完成结论只能引用最后一次 `audit` 写入的 recovery JSON；不得手写或覆盖门禁计数。

`apply` 与 `verify` 必须显式传入该次 `plan` 输出的 `--plan`；计划文件必须是当前 `TASK_ROOT/_work-record_/recovery/` 下的 canonical、regular、非 symlink JSON，且 schema/version/standard_id/naming_contract_sha256/scan_id/plan_path 与当前生成合同一致。正式 apply（不带 `--dry-run`）只有在同一 TASK_ROOT、同一 plan_hash 的成功 dry-run recovery 证据已落盘时才可执行，否则零 mutation 失败；verify 只接受同一计划的成功正式 apply 证据，不能自行补生成计划或把局部 PASS 当成完成。

`audit` 先验证 TASK_ROOT 内 recovery/control 路径没有 symlink 或越界实体，再做 fresh active tree 的 `CORE_GATE`；随后仅在 CORE PASS 后让**所有 active 电影单元（包括 `NAMING_PASS`）**参加跨目录重复候选扫描，最后执行浅层 cleanup 终扫。pending/trash/work-record 均排除，非空 pending 即保留待确认计数。它只输出候选和证据，不按名称或大小自动删除。预处理器会把可确定的嵌套影片拍平到导演根；已证明只剩空目录骨架的 wrapper 会可逆归档到 `_work-record_/flattened-empty/`，不能把仍含文件、媒体或 symlink 的 wrapper 当作完成。

活动树没有任何主视频（`active_video_units=0`，包括只有空壳、pending 或 root trash 的根）时 CORE 必须失败并保持 BLOCKED。`_work-record_`、`_待确认_`、`_trash_*` 仅允许出现在 TASK_ROOT 根层；导演夹或电影夹中的同名条目属于 cleanup 违规，不能藏视频绕过终扫。
审计 JSON 固定包含 `core_gate`、`dedupe_gate`、`cleanup_gate`、`counts`、`candidate_groups`、`pending_count`、`completion_status`、`allowed_completion_message` 和 `report_path`；CORE 失败时 `dedupe_gate.status=NOT_RUN` 且命令返回非零。`completion_status` 只允许 `BLOCKED`、`CORE_COMPLETE_PENDING`、`COMPLETE`，后两态返回零；候选/异常/终扫清单最多各处理 10–20 项一批。

## 最高优先核心职责（CORE）

对 `TASK_ROOT` 内每个视频单元，必须依次完成并现场核验四项核心职责；扫描、计划、普通清理或报告都不能替代它们：

1. 所有保留影片的导演夹、电影夹、视频及现有 NFO/字幕均按 [naming-contract.md](references/naming-contract.md) 逐字规范命名；缺失 NFO 显式记录，不补造。
2. 每个孤立视频必须创建缺失的标准导演夹/电影夹，并把视频及其 sidecar 放入标准路径。
3. 每个分散影片或合集影片必须逐片确定所属导演，归入（或创建）正确的标准导演夹和电影夹。
4. 核心命名与归类通过 `CORE_GATE` 后，按影片身份及同一 edition/cut 分组去重，只保留证据支持的更高质量副本。

`CORE_GATE` 未通过时，不得说“完成”或“已规范化”；active CORE 与 active DEDUPE、普通垃圾清理和终扫均通过但有待确认项时，只能说“主目录四项核心整理已完成，待确认 N项”。只有待确认=0 且全部门禁与终扫通过，才可说“全部整理完成”。

## 入口与故障路由

异常先按 [failure-handling.md](references/failure-handling.md) 对应 B 码执行，不得先改文件。

| B码 | 场景 |
|---|---|
| B01 | 范围越界与越权路径 |
| B02 | 阶段跳步或门禁缺失 |
| B03 | 计划漂移与无效字段 |
| B04 | 中断恢复 |
| B05 | FUSE/挂载异常/双实体 |
| B06 | 路径字符与实体可达性 |
| B07 | 主视频身份误判 |
| B08 | 重复与多版本误判 |
| B09 | sidecar 失配 |
| B10 | trash 冲突与可逆恢复 |
| B11 | 权限或证据不可写 |
| B12 | 报错重试策略错误 |
| B13 | 假完成 |
| B14 | 单项异常阻塞全任务 |
| Bxx | 未识别故障 |

## 核心硬约束（所有阶段共用）

1. `TASK_ROOT` 由用户明确提供并锁定；不得提升到父目录或跨任务根迁移。
2. `TASK_ROOT` 本身不可改名、不可移动、不可删除。
3. `source/target/trash/pending/work-record/evidence` 必须是 `TASK_ROOT` 的 canonical 后代（`Path.resolve()` + 实体关系），不允许字符串前缀判断。
4. 每轮新任务必须完整读取 [naming-contract.md](references/naming-contract.md)，记录合同 hash 并形成标准卡版本。
5. 全量仅维护 `TASK_ROOT/_work-record_/_整理工作单.md`（任务单唯一）及 `TASK_ROOT/_work-record_/recovery/`（证据写失败回退）。
6. 除 naming-contract 明确允许的 `.DS_Store`、`._*` 外，处理动作默认只用可逆 `mv`，禁止 `rm`/`rmdir`。
7. 系统性挂载或权限故障时标记阻塞并暂停，不扩大范围。
8. `trash` 使用固定目录：`TASK_ROOT/_trash_<task-id>_<YYYYMMDD>/`，保留源相对结构。

## 固定顺序与阶段门禁

前一阶段未 PASS，不得进入下一阶段。无人值守只表示明确项可自动推进，不表示可以猜测语义或跳过门禁。

### 0. 任务根与恢复

- 锁定用户给出的 `TASK_ROOT`，核对 canonical 实体、挂载/FUSE、权限和路径可达性。
- `TASK_ROOT` 必须是活动直接子目录为导演夹的库段（用户通常给国家目录）；若给到仍包含洲/国家层的父目录，root 浅层终扫会阻塞，必须按各直接子范围分别运行，不得自行递归猜导演层。
- 读取唯一工作单并现场复扫未闭合批次；无工作单时建立一份。禁止用对话记忆续跑。
- 系统性挂载、权限或证据不可写按 B05/B11 停止；单项异常按对应 B 卡隔离。

### 1. 轻量文件名清单（只读）

- 在 `TASK_ROOT` 内分块枚举，排除 `_work-record_`、`_待确认_`、全部 `_trash_*` 及其子目录。
- 只记录路径、目录层级、文件名/类型、视频/NFO/字幕存在性、结构异常以及目标碰撞所需信息。
- 初扫明确禁止：读取 NFO 内容、运行 `ffprobe`、查 IMDb、计算完整 hash、去重或做深度身份/版本归类。文件系统可以枚举所有条目，但 Agent 只按同类模式和 10–20 项批次推理。
- 此阶段不判垃圾、不建目录、不改名、不移动、不删除；大卷遵循 `os.scandir()` 分块规则。

### 2. 完整命名合同

- 完整读取 [naming-contract.md](references/naming-contract.md)，锁定合同 hash、关键规则和本批 `standard_id`；不能用摘要或旧工作单替代。
- 合同仍是唯一命名权威：导演夹、电影夹、视频、NFO、字幕 basename、语言标识、年份冲突、release 保留、白名单和 trash 规则均以该文件为准。

### 3. 命名快通道（状态与 expected 路径）

#### 3.0 自动前置预处理（硬规则，必须先做）

在 Agent 对普通命名项作任何语义推理、手写 `mv` 或分类前，必须运行随 Skill 提供的标准库脚本
`skills/movie-organizing/scripts/movie_organizing_preprocessor.py`，并严格完成 **plan/dry-run → safe apply → verify**：

```bash
# SKILL_DIR 是已安装的 movie-organizing 目录；仓库开发时可设为
# /.../agent-skills/skills/movie-organizing，不依赖当前 shell 的 cwd。
SKILL_DIR="/path/to/movie-organizing"
SCRIPT="$SKILL_DIR/scripts/movie_organizing_preprocessor.py"
python3 "$SCRIPT" plan --task-root "$TASK_ROOT"
python3 "$SCRIPT" apply --task-root "$TASK_ROOT" --dry-run --plan <recovery/plan-*.json>
python3 "$SCRIPT" apply --task-root "$TASK_ROOT" --plan <recovery/plan-*.json>
python3 "$SCRIPT" verify --task-root "$TASK_ROOT" --plan <recovery/plan-*.json>
```

`plan` 的输出会给出唯一 `plan_path`；后两步必须使用该确切文件（不能凭 glob 猜旧计划）。
`apply` 与 `verify` 的输出同样会给出 `result_path`，对应的 JSON 记录包含 mode、plan hash、状态、
动作计数和错误摘要；缺失或篡改 `plan_hash` 时两步均在任何改动前失败。

脚本只使用 Python 3 标准库和一次轻量 `os.scandir()` 清单，计划与结果写入现有
`TASK_ROOT/_work-record_/recovery/`；对话只汇报计数、动作数和异常摘要。脚本支持的普通命名动作
不得由 Agent 另写命令替代。它硬性执行以下既有合同规则：从旧电影夹保留中文名，从主视频 stem
取得英文名、年份和年份后的完整 release 信息；英文标题内部点转空格，目标电影夹为
`<中文名>.<规范化视频 stem>`，视频扩展名不进入电影夹名。比如
`魔鬼的陷阱.Dablova past.1962/Dablova past.1962.720p.HDTV.x264-DON.mkv` 必须先得到
`魔鬼的陷阱.Dablova past.1962.720p.HDTV.x264-DON/`，视频名已合规则则保持不变。

导演夹会按合同确定性规范化：中文段与英文段之间恰好一个 ASCII 空格；v1.3.3 迁移格式中外国导演中文译名内部的 ASCII 空格/`.` 统一改为 U+00B7 `·`，已有 `·`、原生中文姓名和多导演 `、` 保留。若中英边界、中文姓名片段或分隔符不能唯一解析，输出 `EXCEPTION`，不猜名。导演同名目标碰撞、大小写/Unicode 碰撞或该导演任一子项异常时，禁止父目录改名。

导演夹下的孤立视频仅在视频中文前缀或同 stem NFO 的 title/originaltitle 提供可靠中文名时，才在
**该导演夹内**创建最终电影夹并连同明确 sidecar 移入；没有可靠中文名绝不猜名或创建英文-only 目录。
多视频/合集、DVD/BDMV、年份冲突、目标冲突、路径越界、Unicode/大小写歧义和无法提取中文名一律
输出 `EXCEPTION`，不修改。无 NFO 的普通电影可以通过；脚本不做导演归类、合集拆分、去重或 trash。

导演夹下任意有限深度的单视频 leaf（包括 `导演/outer1/outer2/电影夹/视频`）均可确定时拍平到
`TASK_ROOT/<规范导演夹>/<标准电影夹>/`。标准 leaf 的子文件先改名，再将电影夹跨 wrapper rehome；非标准 nested leaf 只有视频中文前缀或同 stem NFO 提供中文名时才建夹并移动。所有受影响 leaf 成功移出后，若最上层 wrapper 已证明无任何文件、媒体或 symlink、只剩空目录骨架，才将它**一次性可逆改名**到
`TASK_ROOT/_work-record_/flattened-empty/<稳定键>-<原名>/`，保留 rollback 证据；wrapper 有异常、未知文件、目标碰撞或无法证明为空时，相关单元整体 `EXCEPTION`，零 mutation。root-level video 仍为 `EXCEPTION`。

`ACTION_REQUIRED` 的脚本 apply 与 verify 均 PASS 后，Agent 才能继续本节后续的导演/合集慢通道；
`EXCEPTION` 只能按第 6 阶段处理，不能临场猜测。重复运行脚本必须保持幂等并得到
`NAMING_PASS`，不能把旧空电影夹留在 active tree。

先为每个视频单元计算并写入工作单，再按路径事实判断状态，不把全库先放进 `明确/待查/冲突` 深分流。至少记录：

- `source_director_dir`、`expected_director_dir`、`expected_movie_dir`、`expected_video_path`；
- 现有 NFO 的 `expected_nfo_path`（缺失也记录）和每个字幕的 `expected_subtitle_paths`；
- `source_shape`：`standard`、`orphan`、`dispersed` 或 `collection`。

这些字段必须在分类前生成，且基于命名合同、已闭环的身份/导演/年份/release 事实；缺失 NFO/字幕要明确记录缺失，不能用占位动作代替，字段缺失不得进入计划。

- `NAMING_PASS`：仅当所有存在的导演夹、电影夹、视频、NFO、字幕的**实际路径逐字等于对应 expected 路径**，缺失 sidecar 已显式记录、`source_shape=standard`、结构正确且无目标碰撞；无动作。nested leaf 不是 `standard`，即使电影夹名字正确也必须 rehome。它只表示命名阶段合格：在 `CORE_GATE` 之前不读取 NFO/运行 `ffprobe`/查 IMDb/算 hash，也不做去重；通过 CORE 后必须与其他 active 电影一起进入 `DEDUPE_GATE` 候选扫描。不得凭“看起来规范”自报。
- `ACTION_REQUIRED`：目标唯一但需要合同规定的语法规范化，或 `source_shape` 为 `orphan`、`dispersed`、`collection`，或缺失标准目录；必须按计划创建目录、改名并 rehome，不能当作无动作通过。纯语法动作仍须生成完整 bundle，不改变电影身份、导演、年份事实或 release token。
- `EXCEPTION`：身份、导演、年份、归属或主视频不明，特殊容器/结构，多版本或重复关系，Unicode/实体边界，sidecar 配对不明，或任何目标碰撞/不可逆风险。不得临时加后缀、覆盖或猜名。

命名快通道不读取 NFO 内容、不跑 `ffprobe`/IMDb、不算完整 hash、不做去重或深度归类；查证只属于 `EXCEPTION` 慢通道，去重只属于 `CORE_GATE` 之后的 DEDUPE 阶段。

### 4. Naming bundle 与 10–20 项锁定计划

对每个 `ACTION_REQUIRED` 视频单元生成一条完整 bundle：`source_director_dir`/`expected_director_dir`、`expected_*`、`source_shape`、导演夹 old/new、电影夹 old/new、主视频 old/new、现有 NFO old/new（无 NFO 显式记录缺失且不补造）、每个现有字幕 old/new、必要 `mkdir`/`rehome`、合同明确垃圾的预锁映射（此处只记录，不提前执行）、依据和回滚路径。计划另列每个 wrapper 的一次性 `rename_dir` 归档动作和每个导演唯一的 `rename_dir` 动作；任何缺项、歧义或目标碰撞都降为 `EXCEPTION`。

按一个导演或有限文件块生成 10–20 个视频单元的原子计划并锁定 hash。计划级必须有 `scan_id/standard_id/plan_hash`；公共动作字段必须有 `id/action/target/evidence/rollback/preconditions/postconditions`；`rename`/`rehome`/`trash` 另必须有 `source`，`mkdir` 不设置伪 `source`，只要求锁定 target 不存在且为 canonical `TASK_ROOT` 后代。改名/rehome 要求 `old exists`、`new absent`；回滚不得 `rmdir`，任务创建的空目录只能可逆 `mv` 到本任务 trash。`trash_target` 仅用于后续 trash 动作，`content_hash` 仅用于去重证据；禁止 `sentinel`/`__KEEP__`/`__SKIP__`、`old==new`、重复目标和缺字段。

### 5. 命名复扫与早退出

计划验核通过后，按形态执行该批明确 bundle：**必要目标目录（计划内 mkdir）→ 视频改名/rehome → NFO/字幕 → 电影夹定位/改名 → 所有受影响 wrapper 影片动作完成后一次性可逆归档空骨架 → 所有子项复扫 PASS 后每个导演只执行一次导演夹改名 → 现场复扫**。对已有容器仍坚持子项先、父目录后；每个子项现场复扫导演夹、电影夹、视频、NFO、字幕、残留/碰撞、bytes、sidecar 和工作单。每个执行项必须证明 old path 已消失、new path 已存在且逐字等于 expected path；wrapper 归档只能针对已证明无文件、媒体或 symlink 的空目录骨架，目标为 `TASK_ROOT/_work-record_/flattened-empty/`，不得删除或藏入未处理内容。此序列不执行普通 trash。

`NAMING_PASS` 项在 `CORE_GATE` 前不回到深查：禁止提前读 NFO 内容、运行 `ffprobe`、查 IMDb、计算 hash、去重或深度归类；它在 CORE 后与全部 active 电影一并接受候选扫描和 Agent 的版本/质量查证。复扫失败按 B13/B04 处理，不以返回码代替现场验收。

### 6. 仅 EXCEPTION 进入慢通道

- 只对 `EXCEPTION` 按 `明确/待查/冲突` 细分；快通道明确项不被异常项阻塞。
- 仅在确有必要时读取 NFO 的 `title/originaltitle/year/director`、运行 `ffprobe` 核对时长/分辨率、查询 IMDb suggestion；三源互证后才能改变语义事实或生成新 bundle。
- `CORE_GATE` 前，完整 hash 仅用于目标碰撞形成的候选精确重复或异常完整性确认；时长、分辨率或抽样 hash 不能裁决重复。去重必须等核心门通过后按下一阶段执行。
- 慢通道闭环者回到 bundle/计划门禁；仍不闭环者必须将最小完整电影单元移入 `TASK_ROOT/_待确认_` 并保留来源/恢复路径。若系统故障无法移动，只能原地冻结且 `CORE_GATE` 必须失败，不能把冻结项算作通过。合同已明确为垃圾的无语言字幕在普通清理阶段按预锁 trash 处理，不猜语言。

### 7. CORE_GATE（命名与归类门禁）

命名批次完成后必须全量复扫并计算以下 active 计数，全部为 `0` 才能通过 `CORE_GATE`：

`active_nonconforming_director_dirs`、`active_nonconforming_movie_dirs`、`active_nonconforming_video_files`、`active_nonconforming_nfo_files`、`active_nonconforming_subtitle_files`、`active_orphan_videos`、`active_collection_containers_with_videos`、`active_misfiled_movie_dirs`、`required_actions_remaining`、`partial_bundles`、`unaccounted_video_units`。

每个执行项还必须有 `old absent + new exists + expected path exact`。系统故障、权限故障或无法移动导致旧项仍在 active media tree 时，门禁失败；原地冻结不能把计数伪装为归零。未闭环的最小完整电影单元必须移入 `TASK_ROOT/_待确认_` 并在工作单中有来源/恢复路径，不能留在 active tree 后算通过。

已安全完整移入 `_待确认_` 且有完整 pending 目标、来源和恢复记录的单元标记为 `accounted_pending`：不计入 active 违规项，也不计入 `unaccounted_video_units`。`unaccounted_video_units` 只统计既没有 active 最终路径、也没有完整 pending 记录的单元；仍留在 active tree 的旧项或未执行动作一律使 CORE_GATE 失败。

### 8. DEDUPE_GATE（去重门禁）

仅在 `CORE_GATE=PASS` 后进入去重；`DEDUPE_GATE` 只核 active media tree（排除 `_待确认_` 与全部 `_trash_*` 媒体内容），普通清理不得提前。先按影片身份分组，再确认同一 `edition/cut`；不同剪辑、版本、内容不得合并。质量排序只接受可验证证据：`4K > 1080p > 720p`，同分辨率再比较可验证码率/画质；不得仅凭文件名或文件大小裁决。完全一致的精确重复须以完整文件 hash 与清单一致确认。

质量唯一胜出者保留，较差副本只可逆 `mv` 到固定 `TASK_ROOT/_trash_<task-id>_<YYYYMMDD>/`，保留原相对路径、证据和回滚；证据不闭环、时长/版本有实质差异或质量无法唯一排序时，若候选组可安全整体隔离则移入 `_待确认_`，记录 `pending_duplicate_groups`，不得自动淘汰。候选组留在 active tree 时 DEDUPE_GATE 失败；整体隔离后不阻塞其他 active 影片继续去重、普通清理和终扫。

以下 active 计数全部为 `0` 才能通过 `DEDUPE_GATE`：`unresolved_duplicate_groups_in_active_tree`、`inferior_copies_remaining_in_active_tree`、`dedupe_actions_remaining`、`partial_dedupe_actions`。`pending_duplicate_groups` 仅用于报告，不阻塞其他 active 影片继续，但待确认>0 时永远不能报告全部整理完成。系统故障导致候选仍在 active tree 时，`unresolved_duplicate_groups_in_active_tree` 非零，门禁失败。

无法裁决的重复关系整体移入 `_待确认_` 后不计入 active DEDUPE 计数，但必须记录 `pending_duplicate_groups` 与来源/恢复证据。

### 9. 普通清理、终扫与报告

`DEDUPE_GATE=PASS` 后，才执行命名合同已明确的普通垃圾 trash（以及允许直接删除的 `.DS_Store`、`._*`），使用预锁 `trash_target`、固定 trash 根和可逆证据；这一步不能反向修改核心路径。

`audit` 的 `cleanup_gate` 是最小终扫：仅在 CORE/DEDUPE 均 PASS 后浅扫 active TASK_ROOT、导演夹和 `NAMING_PASS` 电影夹；root 只允许计划中的导演夹，导演夹只允许计划中的电影夹，电影夹白名单只包括 expected 主视频、expected NFO 和 expected 字幕。缺失、非普通文件、symlink、海报、`.DS_Store`、`._*`、未知/空壳目录或其他条目均计入 `active_non_whitelist_items` 并使 cleanup FAIL；每个 expected 文件都要重新核验存在、regular、非 symlink 且 canonical 在 TASK_ROOT 内。CORE 或 DEDUPE 未通过时 cleanup 为 `NOT_RUN`。cleanup FAIL 时不得使用“终扫 PASS”完成语义，且脚本不自动删除任何条目。

全量复扫仍排除 `_work-record_`、`_待确认_`、全部 `_trash_*` 媒体内容，但最终统计必须包含三类控制目录。若 active CORE、active DEDUPE、普通清理和终扫均 PASS 但待确认>0，只能输出 `主目录四项核心整理已完成，待确认 N项`；仅当待确认=0、`CORE_GATE=PASS`、`DEDUPE_GATE=PASS`、上述普通清理完成、终扫 PASS 且无残留 required/partial/unaccounted 计数时，才可输出 `全部整理完成（待确认=0且终扫PASS）`。

## 执行顺序（硬规则）

通过计划门禁后，固定按同一 bundle 执行：**必要目标目录（计划内 mkdir）→ 视频 → NFO/字幕 → 电影夹定位/改名 → wrapper 空骨架可逆归档 → 每个导演唯一导演夹改名 → 现场复扫**；`CORE_GATE` 通过后才允许 **去重 → `DEDUPE_GATE` → 普通 trash/清理 → 终扫**。每条记录 `old/new/bytes/sidecar/expected path/证据路径`；任何执行中发现的新事实都停止受影响项并按 B 卡处理，不临场改计划。

导演夹只有在该导演全部受影响子项都已闭环、wrapper 已按规则归档、复扫 PASS 且目标不冲突时才允许最后改名；同一导演计划只生成一次 `rename_dir`。若旧夹/影片单元仍在 active tree，`CORE_GATE` 必须失败；可安全隔离时将最小完整单元移入 `_待确认_` 后主目录继续。所有 trash/pending/flattened-empty 均保留来源、目标和可逆证据。

## 中断、分类与回收

- 中断恢复先现场复扫并按 B04 对齐 `未执行/已执行/部分执行`；`CORE_GATE` 前已 `NAMING_PASS` 项不重新深查，CORE 后仍须参加统一 DEDUPE 候选扫描；未闭合 bundle 或部分执行项只从未完成动作恢复。
- `明确` 是身份/sidecar/目标已闭环；`待查` 是仍可低成本核验；`冲突` 是多候选、归属/版本/边界或不可逆风险。`待确认` 只接收最小完整单元并保留恢复路径。
- 普通任务不重新扫描 `_待确认_`；只有用户明确要求处理该目录时才重开范围。所有异常先按 `failure-handling.md` 的 B 码，不以工具报错替代媒体冲突。

## 参考

- [naming-contract.md](references/naming-contract.md)
- [runtime-and-safety.md](references/runtime-and-safety.md)
- [triage-and-edge-cases.md](references/triage-and-edge-cases.md)
- [failure-handling.md](references/failure-handling.md)
- [lessons-and-audit-checklist.md](references/lessons-and-audit-checklist.md)

## v1.3.4 实操补充（2026-08-28 捷克库实测）

以下规则从捷克库（CIFS/NAS 大批量混合库）实操中总结，是对上述阶段门禁的补充，不替代任何硬约束；命名合同、ACTION_REQUIRED bundle、CORE_GATE/DEDUPE_GATE 与可逆安全边界始终优先。

### 导演夹间隔号合规

导演夹中 `·`（U+00B7 MIDDLE DOT，中文间隔号）是外国人名中文译名内部的标准分隔符，且不同于电影/视频文件名中的 ASCII `.`。导演夹必须是 `中文段 EnglishName`，中英之间恰好一个 ASCII 空格；v1.3.3 迁移格式中可唯一解析的外国中文姓名片段使用 `·`，多导演使用 `、`，原生中文姓名不新增 `·`。已有 `·` 不得改掉；ASCII `.` 或姓名片段空格必须在预处理器中改为 `·`。边界、片段或字符不明确时输出 `EXCEPTION`，禁止猜名。

### 括号式→点式自动转换

大量电影夹使用 `中文名 英文名 (年份)` 格式，需转为合同格式 `中文名.英文 Name.年份`。转换规则：

1. 从同目录视频文件名提取英文名（正则 `^([A-Za-z].+?)\.(\d{4})\.` 或 `^([A-Za-z].+?)\s+(\d{4})\s`）。
2. 提取的英文名中的 `.` 替换为空格（保留年份后的点分隔）。
3. 无法从视频文件提取英文名的，标为 `EXCEPTION` 待查，不猜名。
4. 转换后验证：新目录不存在、旧目录存在、同级无碰撞。

### 中文视频文件名清理

视频文件名中不应有中文。处理方式：

1. 用正则 `^([\u4e00-\u9fff\u3000-\u303f\uff00-\uffef、·]+)\.(.+)$` 分离中文前缀和英文/原文部分。
2. 保留英文/原文部分，将 `.` 替换为空格（年份及之后保持点分隔）。
3. 若中文前缀后是空格分隔的英文（模式2），直接去掉中文前缀。
4. 无法分离的标为 `EXCEPTION`。

### CIFS/大小写双目录

在 CIFS 挂载的 NAS 上，仅大小写不同的目录名（如 `LiMITED` vs `LIMITED`）可能同时存在（inode 不同）。`mv` 会失败（"设备或资源忙"）。处理方式：

1. 检测两个目录是否同时存在且内容相同（字节比对）。
2. 若相同，视为 CIFS 大小写伪影，跳过并标记为冲突。
3. 若不同，先保留并记录候选；仅在 `CORE_GATE=PASS` 后按影片身份与同一 `edition/cut` 进入 `DEDUPE_GATE`，有可验证质量唯一胜出者时才将较差副本可逆移入固定 trash，不能凭目录内容或文件大小直接回收。

### 特殊容器处理

`DVD/`、`蓝光/`、`短片/`、`纪录片/`、`访谈花絮/`、`长片/`、`BFI Complete Shorts/` 等是非标准结构容器，不按普通电影夹处理：

1. 内有视频文件的：提取英文名，为每部电影创建独立 film folder 并移入。
2. 空目录：仅在 `DEDUPE_GATE=PASS` 且计划已预锁固定 trash 目标后可逆 `mv` 到任务 trash；禁止直接递归删除（`.DS_Store`/`._*` 仍按合同例外处理）。
3. 含子目录的：逐个检查子目录内容，按上述规则处理。
4. 访谈花絮中的其他导演作品：标为 `EXCEPTION`，将最小完整单元移入 `_待确认_`，不移入当前导演夹；仅系统故障导致不可移动时原地冻结且 CORE_GATE 失败。

### 重复版本保留策略

同一影片多个版本（不同编码/分辨率/来源）按以下策略处理：

1. 先比对文件大小和 SHA1（至少比对文件大小），但大小只作筛选，不能单独裁决重复或质量。
2. 大小不同 → 不能据此判为不同内容或淘汰，先均保留并标为 `冲突`，按身份/`edition/cut` 复核。
3. 大小相同 → 仅说明可能是复制副本；`DEDUPE_GATE` 后仍需完整 hash 与清单一致确认。
4. 差异版本不自动合并或删除；候选组可安全整体隔离时移入 `_待确认_` 并记录 `pending_duplicate_groups`，否则留在 active tree 使 DEDUPE_GATE 失败，工作单记录所有路径和大小。

### 年份冲突三源验证

目录年份与视频 release 年份不一致时：

1. 使用 IMDb suggestion API `https://v2.sg.media-imdb.com/suggestion/x/<关键词>.json` 查证。
2. 确认正确年份后，**目录**改为查证年份，**视频文件**保留 release 原始年份 token（合同规则）。
3. 无法确认的标为 `EXCEPTION`，将最小完整单元移入 `_待确认_`；仅系统故障导致不可移动时原地冻结且 CORE_GATE 失败。
