---
name: movie-organizing
description: >-
  Use when a user asks an assistant to normalize, rehome, enrich, or deduplicate
  a mixed movie library within an explicitly bounded TASK_ROOT.
license: MIT
metadata:
  version: "1.3.6"
  author: lynch5mo
  tags: [media, movie-library, batch-plan, nfo]
  trigger: User asks to normalize, rehome, enrich NFO, deduplicate, or quality-select a movie library.
---

# Movie Organizing v1.3.6

这是固定顺序的轻量手册，不是让 Agent 自由发挥的系统。所有写操作只能由随 Skill
提供的脚本产生；Agent 只锁定范围、读取命名合同、提交语义决定和复核 JSON。

## 不可违反的硬规则

- `TASK_ROOT` 必须由用户明确给出并锁定；不得升到父目录、跨国家或跨任务根。
- 每次开始、恢复或上下文压缩后先运行 `movie_organizing_task.py status`，只执行 JSON
  `next_allowed`；`STOP_RECOVERY_REQUIRED`、`STOP_PENDING_CONFIRMATION` 或
  `next_allowed=null` 时停止写操作。
- 禁止 Agent 手写 `mv`/`rm`/`rmdir`、自制脚本、修改 action/source/target、编造 plan 或
  API ID。唯一允许的写入口是本 Skill 的官方脚本。
- `references/naming-contract.md` 是唯一命名权威。导演、电影夹、视频、NFO、字幕的既有
  规则必须原样执行，不得在对话里另造规则。
- 普通确定性命名、孤立视频建夹、分散项归类和嵌套 leaf 拍平必须由预处理器完成；异常才
  走 slowpath；去重只能在 CORE_GATE 和 NFO_GATE 都 PASS 后进行。
- 普通批次最多 20 个视频单元。active 视频 >20、导演数 >3 或预估动作 >50 时强制
  `large_library_mode`：一个导演、最多 10 个视频单元；slowpath 异常批次最多 5 项。
- 任何不确定单元只可移到当前 `TASK_ROOT/_待确认_`；NFO 身份不确定由官方 NFO 计划将
  完整电影夹保留导演路径后可逆隔离。目标冲突、symlink、漂移或隔离未验证时停止，不能猜名。
- 正式 apply/verify 失败由脚本自动回滚；回滚失败必须报告 `manual_recovery_required`。

## 十步固定流程（不可跳步）

`movie_organizing_task.py` 是唯一控制面；它返回完整步骤和唯一下一条允许命令：

1. `verify_install`：验证 Skill 文件、版本和 checksum。
2. `scope_lock`：锁定 `TASK_ROOT`，检查 canonical 路径、恢复目录和控制目录安全。
3. `inventory`：只读枚举层级、文件类型、视频/NFO/字幕存在性和结构形态；不读 NFO 内容、
   不查数据库、不跑 ffprobe、不算完整 hash。
4. `naming_contract`：全文读取 [naming-contract.md](references/naming-contract.md)，记录
   合同 hash/`standard_id`。
5. `preprocess`：运行命名预处理器的 `plan → dry-run → apply → verify`；大库每批再 `seal`。
6. `exception_resolution`：只对 `EXCEPTION` 使用 slowpath，提交语义决定，不提交路径动作。
7. `core_gate`：fresh audit 的 CORE 计数清零后才继续。
8. `nfo_gate`：用官方 TMDb 匹配并补同 stem NFO；每批 `plan → dry-run → apply → verify`，
   身份锁定或完整 pending 隔离后才能继续。
9. `dedupe_gate`：按数据库身份、edition/cut 和质量证据去重；不确定整组待确认。
10. `cleanup_final_audit`：只在 CORE/DEDUPE/NFO 通过后执行合同允许的清理和终扫。

开始（只读）以及恢复（唯一依据）：

```bash
SKILL_DIR="/path/to/movie-organizing"
TASK_ROOT="/absolute/path/user-gave"
python3 "$SKILL_DIR/scripts/movie_organizing_task.py" start --task-root "$TASK_ROOT"
python3 "$SKILL_DIR/scripts/movie_organizing_task.py" status --task-root "$TASK_ROOT"
```

严格按 JSON 的 `next_allowed.argv` 运行；`command` 只是展示。脚本结果和最新 recovery JSON
是事实，Agent 的自然语言不是事实。

## 命名预处理器（第 5 步）

```bash
SCRIPT="$SKILL_DIR/scripts/movie_organizing_preprocessor.py"
python3 "$SCRIPT" plan --task-root "$TASK_ROOT"
python3 "$SCRIPT" apply --task-root "$TASK_ROOT" --dry-run --plan <该次输出的plan_path>
python3 "$SCRIPT" apply --task-root "$TASK_ROOT" --plan <同一plan_path>
python3 "$SCRIPT" verify --task-root "$TASK_ROOT" --plan <同一plan_path>
```

大库正式命名 verify PASS 后必须：

```bash
python3 "$SCRIPT" seal --task-root "$TASK_ROOT" --plan <同一plan_path>
```

`NAMING_PASS` 只表示路径/形态已符合命名合同，不表示 NFO 或去重完成；`ACTION_REQUIRED`
必须执行；`EXCEPTION` 禁止猜名。视频
`Dablova past.1962.720p.HDTV.x264-DON.mkv` 的电影夹必须是
`是魔鬼的陷阱.Dablova past.1962.720p.HDTV.x264-DON/`。导演夹下任意有限深度的确定性单视频
leaf 都要拍平，wrapper 只有确认为空后才可可逆归档。

## NFO 身份门禁（第 8 步）

```bash
NFO="$SKILL_DIR/scripts/movie_organizing_nfo.py"
python3 "$NFO" plan --task-root "$TASK_ROOT"
python3 "$NFO" apply --task-root "$TASK_ROOT" --dry-run --plan <该次输出的plan_path>
python3 "$NFO" apply --task-root "$TASK_ROOT" --plan <同一plan_path>
python3 "$NFO" verify --task-root "$TASK_ROOT" --plan <同一plan_path>
python3 "$SKILL_DIR/scripts/movie_organizing_audit.py" audit --task-root "$TASK_ROOT"  # 仅本批 deferred=0 时
```

脚本以最终规范化视频 stem 提取标题/年份，结合导演目录和可用 ffprobe 时长，通过 TMDb v3
`search/movie` → `movie/{id}` → `alternative_titles`/`credits`/`external_ids` 严格过滤。
标题只做 Unicode、重音、标点归一；年份和导演必须相符；过滤后恰好一个候选才 `AUTO_CREATE`。
0 个、多个、已有 NFO ID 冲突、解析/API/ffprobe 失败均为 `PENDING_*`，禁止 Agent 手写 XML、
猜 ID 或覆盖现有 NFO。

新 NFO 先进入 `_work-record_/nfo-staging/`，验证 XML、ID、stem 和 hash 后原子落盘。正式
verify PASS 才生成 `nfo-identity-lock-*.json`；fresh NFO_GATE 还必须核对视频指纹、NFO hash、
TMDb ID 和 identity-lock，旧 NFO 不能仅凭标签自证。

选中批次的 `PENDING_*` 由同一事务生成 `pending_isolation`，把完整电影夹移动到当前任务根的
`_待确认_/原导演路径/原电影夹`，记录 source/target/tree hash/evidence/rollback，并在 verify
证明源消失、目标完整后再 fresh audit。隔离冲突或验证失败才 `STOP_PENDING_CONFIRMATION`；
隔离完整则继续剩余批次；大库仍有 `deferred_count` 时先按 identity-lock 跳过已核验条目并生成下一批，
全部批次结束后才 fresh full-tree audit。大库清单/进度只写 `_work-record_/inventory.jsonl`、`progress.json`，
不得把全量清单装进上下文。

细节见 [nfo-and-large-library.md](references/nfo-and-large-library.md)。

## 异常、去重和完成语义

第 6 步只用 [movie_organizing_slowpath.py](scripts/movie_organizing_slowpath.py) 的语义模板；
`core_exception` 仅允许 `pending_isolation`/`rehome_unit`，`dedupe` 仅允许有身份、版本和
质量证据的 `dedupe_keep` 或安全的 `dedupe_pending`。slowpath 模板/决定/计划/audit 任一路径
或 hash 漂移，脚本零 mutation 失败。

```bash
python3 "$SKILL_DIR/scripts/movie_organizing_audit.py" audit --task-root "$TASK_ROOT"
```

只认最新 audit recovery JSON。CORE 未过，DEDUPE 和 cleanup 均 `NOT_RUN`；NFO_GATE 未过，
DEDUPE 也不得运行。低质量副本只能可逆移动到
`TASK_ROOT/_trash_<task-id>_<YYYYMMDD>/` 并保留证据，绝不删除或覆盖。合同允许的垃圾清理和
终扫必须在两道核心门禁、NFO 和去重都 PASS 后进行。

只有脚本报告才能决定话术：active 影片为 0 且仅剩待确认视频时保持
`STOP_PENDING_CONFIRMATION`、`next_allowed=null`；仍有待确认但其余门禁 PASS 时只能报告主目录
完成且待确认数量；待确认=0、CORE/NFO/DEDUPE/cleanup/终扫均 PASS 才能报告全部完成。

## 参考卡路由

- [naming-contract.md](references/naming-contract.md)：唯一命名规范（不得改写）。
- [nfo-and-large-library.md](references/nfo-and-large-library.md)：NFO 匹配、identity-lock、pending 隔离和大库批次。
- [failure-handling.md](references/failure-handling.md)：跳步、漂移、回滚、假完成和历史 bug。
- [runtime-and-safety.md](references/runtime-and-safety.md)：FUSE/权限/Unicode/sidecar/trash 安全。
- [triage-and-edge-cases.md](references/triage-and-edge-cases.md)：合集、孤立、嵌套 leaf、版本和去重。
- [lessons-and-audit-checklist.md](references/lessons-and-audit-checklist.md)：每批前后最小核对表。

任何参考卡与命名合同、脚本门禁冲突时，以命名合同和脚本实际返回为准；先停止当前动作，
记录 recovery，再按故障码恢复。
