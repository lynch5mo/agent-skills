---
name: movie-organizing
description: >-
  Use when a user asks an assistant to normalize, rehome, or deduplicate a
  mixed movie library within an explicitly bounded TASK_ROOT.
license: MIT
metadata:
  version: "1.3.5"
  author: lynch5mo
  tags: [media, movie-library, batch-plan]
  trigger: User asks to normalize, rehome, deduplicate, or quality-select a movie library.
---

# Movie Organizing v1.3.5

这是一个固定顺序的轻量手册，不是让 Agent 自由发挥的系统。所有写操作只能由随 Skill
提供的脚本产生；Agent 只锁定范围、读取命名合同、提交语义决定和复核 JSON。

## 先记住的硬规则

- `TASK_ROOT` 必须由用户明确给出并锁定；不得升到父目录、跨国家或跨任务根。
- 每次开始、恢复或上下文压缩后，先运行 `movie_organizing_task.py status`，只执行输出的
  `next_allowed`；`STOP_RECOVERY_REQUIRED` 或 `next_allowed=null` 时停止写操作。
- 禁止 Agent 手写 `mv`/`rm`/`rmdir`、自制 Python、修改 action/source/target、编造 plan，或从脚本导入私有函数。唯一允许的写入口是本 Skill 的四个脚本。
- 普通明确命名只能走预处理器；异常才走官方 slowpath；去重只能在 `CORE_GATE=PASS` 后进行。
- 每次只锁一个导演或有限批次，最多 20 个视频单元。未选中的 `ACTION_REQUIRED` 保持该状态，下一轮继续，不能自报完成。
- 任何不确定单元只可移到当前 `TASK_ROOT/_待确认_`，不能放到更高层；无法安全移动就原地冻结，门禁失败。
- 若 active 影片为 0 且只剩待确认视频，必须保持 `STOP_PENDING_CONFIRMATION`：audit 为 `BLOCKED`、task 的 `next_allowed=null`，只能等待用户，不能说核心完成或全部完成。
- 普通移动/改名必须可逆。失败由脚本自动回滚；回滚失败则停止并报告 `manual_recovery_required`。

## 固定九步（顺序不可改变）

`task.py` 是流程控制面；它返回完整九步和唯一下一条允许命令。下列九步是唯一流程：

1. `verify_install`：验证 Skill 文件、版本和 checksum。
2. `scope_lock`：锁定 `TASK_ROOT`，检查 canonical 路径、挂载和可写恢复目录。
3. `inventory`：只读枚举条目和层级，不读 NFO 内容、不跑 `ffprobe`/IMDb、不算完整 hash。
4. `naming_contract`：全文读取 [naming-contract.md](references/naming-contract.md)，记录合同 hash/`standard_id`；它是唯一命名权威。
5. `preprocess`：普通命名按最多 20 项反复 `plan → dry-run → apply → verify`。
6. `exception_resolution`：仅对 `EXCEPTION` 使用官方 slowpath；语义不确定不猜。
7. `core_gate`：fresh audit 的 `CORE_GATE` 全部计数为零后才可进入去重。
8. `dedupe_gate`：按身份、同一 edition/cut 和可验证质量证据去重。
9. `cleanup_final_audit`：只在 CORE/DEDUPE 都通过后做合同允许的清理和终扫。

开始命令（只读，不改媒体）：

```bash
SKILL_DIR="/path/to/movie-organizing"
TASK_ROOT="/absolute/path/user-gave"
python3 "$SKILL_DIR/scripts/movie_organizing_task.py" start --task-root "$TASK_ROOT"
```

随后每次恢复均先执行：

```bash
python3 "$SKILL_DIR/scripts/movie_organizing_task.py" status --task-root "$TASK_ROOT"
```

严格按 JSON 的 `next_allowed.argv` 运行；若运行时同时给出 `display_command` 或 `command`，
它们仅是展示，不得自行改写参数。不要凭对话记忆猜下一步。脚本结果和最新 recovery JSON
是事实，Agent 的自然语言不是事实。

## 第 1–4 步：安装、范围、清单和合同

```bash
python3 "$SKILL_DIR/scripts/movie_organizing_audit.py" verify-install --skill-dir "$SKILL_DIR"
```

安装校验不是媒体整理；失败即停止。安装通过后锁定 TASK_ROOT，确认 `_work-record_/recovery/`
可写且没有 symlink/越界实体。清单阶段只观察路径、文件类型、层级、视频/NFO/字幕存在性和
碰撞；不先把全库搬进人为的“明确/待查/冲突”目录。然后全文读取命名合同并保存 hash。

命名合同的既有规则必须原样执行：导演夹为 `中文名 EnglishName`，外国译名内部使用
U+00B7 `·`、多导演用 `、`；电影夹为 `中文名.规范化视频 stem`，英文标题单词用空格，
年份后的 release token 原样保留；视频文件不含中文；NFO 同视频 basename，字幕带语言标识。
缺 NFO/字幕要记录缺失，不造文件。例：视频
`Dablova past.1962.720p.HDTV.x264-DON.mkv` 的电影夹必须是
`是魔鬼的陷阱.Dablova past.1962.720p.HDTV.x264-DON/`。完整细节只看命名合同，不在本手册另造规则。

## 第 5 步：普通命名快通道（唯一入口）

运行随 Skill 提供的标准库预处理器；`plan` 输出的确切 `plan_path` 必须原样传给后续命令：

```bash
SCRIPT="$SKILL_DIR/scripts/movie_organizing_preprocessor.py"
python3 "$SCRIPT" plan --task-root "$TASK_ROOT"
python3 "$SCRIPT" apply --task-root "$TASK_ROOT" --dry-run --plan <该次输出的plan_path>
python3 "$SCRIPT" apply --task-root "$TASK_ROOT" --plan <同一plan_path>
python3 "$SCRIPT" verify --task-root "$TASK_ROOT" --plan <同一plan_path>
```

每个 `ACTION_REQUIRED` bundle 必须同时锁定 expected director/movie/video/NFO/subtitle 路径、
来源形态、目标碰撞检查和回滚证据。最多 20 个 selected 单元；deferred 单元仍是
`ACTION_REQUIRED`。正式 apply 或 verify 失败，脚本先自动回滚，Agent 只能查看 recovery，
不得临场补动作。成功后 fresh plan 仍有 `action_required>0` 就从第 5 步继续下一批；只有
正式 verify PASS 才能处理下一阶段。

三态含义固定：

- `NAMING_PASS`：路径逐字等于 expected、形态是标准 leaf、无碰撞；命名阶段无动作，但 CORE
  通过后必须参加全量去重。
- `ACTION_REQUIRED`：确定的语法改名、孤立视频建标准电影夹、分散项 rehome，或确定 leaf
  拍平；必须由预处理器计划执行，不能无动作通过。
- `EXCEPTION`：身份/导演/年份/sidecar、合集、多视频、特殊容器、Unicode/大小写、目标碰撞
  或版本关系不确定；禁止猜名、加后缀、覆盖或把它伪装成 PASS。

导演夹下任意有限深度的确定性单视频 leaf 都要拍平到标准导演根。leaf 和 sidecar 先完成，
所有内容移出且确认 wrapper 只剩空目录骨架后，才可一次性可逆归档到
`TASK_ROOT/_work-record_/flattened-empty/`。仍含未知文件、symlink 或异常单元时零 mutation。
导演夹只能在所有子项闭环、wrapper 处理完且现场复扫 PASS 后改名。

## 第 6 步：EXCEPTION 官方慢通道

Agent 不写路径动作，只填写模板中的语义决定。先取得 fresh audit，再运行：

```bash
SLOW="$SKILL_DIR/scripts/movie_organizing_slowpath.py"
python3 "$SLOW" template --task-root "$TASK_ROOT" --audit <fresh-audit.json> --phase core_exception
# Agent 只填写 template 里的 candidate_id + semantic decision，保存 decisions.json；rehome 时
# 只填 resolved_director_name、resolved_chinese_title，可选 main_video_name，绝不填路径。
python3 "$SLOW" plan --task-root "$TASK_ROOT" --audit <同一audit.json> \
  --template <template.json> --decisions <decisions.json>
python3 "$SLOW" apply --task-root "$TASK_ROOT" --plan <slow-plan.json> --dry-run
python3 "$SLOW" apply --task-root "$TASK_ROOT" --plan <同一slow-plan.json>
python3 "$SLOW" verify --task-root "$TASK_ROOT" --plan <同一slow-plan.json>
```

`core_exception` 只允许 `pending_isolation` 或 `rehome_unit`；无法闭环的最小完整单元移入
TASK_ROOT 内 `_待确认_`。`rehome_unit` 的导演名和中文片名由 Agent 以语义证据确定，路径由
脚本按命名合同推导。CORE 通过后，fresh audit 的 `dedupe` 模板允许 `dedupe_keep` 或
`dedupe_pending`：前者必须证明同一身份、同一 edition/cut，并提供非空质量证据；精确重复
还要完整 hash/清单证据，后者在证据不足时把整组安全隔离到当前 TASK_ROOT/_待确认_，不淘汰。
模板、决定、计划和 audit 的
路径/hash 任一漂移，脚本零 mutation 失败。

`pending_isolation` 的边界：普通 source 若既不是 `TASK_ROOT` 也不是导演 anchor，且含 unknown/child/multi-video，
必须把 source 容器整体作为最小可逆单元移入当前 `_待确认_`，不能只抽一个视频留下残骸；`TASK_ROOT`/导演 anchor
绝不整体移动，只能隔离明确的 main video + 唯一 sidecar。这个动作不扩大到整个导演或整批媒体。

## 第 7–9 步：门禁、去重、清理和完成话术

```bash
python3 "$SKILL_DIR/scripts/movie_organizing_audit.py" audit --task-root "$TASK_ROOT"
```

只认最新 audit recovery JSON。`CORE_GATE` 必须清零：非规范导演/电影/视频/NFO/字幕、孤立
视频、合集容器、错误归属、required actions、partial bundles、unaccounted units。CORE 未过，
`DEDUPE_GATE` 和 cleanup 均 `NOT_RUN`，不得去重或清理。

CORE PASS 后，按影片身份再按同一 edition/cut 分组。质量只用可验证证据（`4K > 1080p > 720p`，
同分辨率比较可验证码率/画质）；低质量副本只能可逆移到
`TASK_ROOT/_trash_<task-id>_<YYYYMMDD>/` 并保留证据。无法唯一裁决的组整体进 `_待确认_`，
active 中仍有未决组则 DEDUPE 失败。DEDUPE PASS 后才处理命名合同明确的垃圾和终扫；禁止用
`rm`/`rmdir` 替代脚本的可逆动作（仅合同允许的 `.DS_Store`、`._*` 例外）。

完成语义只能来自最新 audit JSON：CORE 未过不得说完成；active 影片为 0 且仅剩待确认视频时，
保持 `STOP_PENDING_CONFIRMATION`，只能报告“无可继续自动处理，待确认 N 项”；其他情况下 CORE/
DEDUPE/cleanup/终扫均 PASS 但待确认非零，才可说“主目录四项核心整理已完成，待确认 N 项”；只有
`completion_status=COMPLETE`、待确认为零且终扫 PASS，才能说“全部整理完成”。

## 出错时只查参考卡

- 范围、跳步、计划漂移、中断、假完成：见 [failure-handling.md](references/failure-handling.md)（B01–B04、B13）。
- FUSE/权限/Unicode/sidecar/trash：见 [runtime-and-safety.md](references/runtime-and-safety.md)。
- 合集、孤立、嵌套 leaf、版本和去重判定：见 [triage-and-edge-cases.md](references/triage-and-edge-cases.md)。
- 每批前后最小核对表：见 [lessons-and-audit-checklist.md](references/lessons-and-audit-checklist.md)。
- 命名规则唯一来源：[naming-contract.md](references/naming-contract.md)；不得改写或另造一套。

任何参考卡与命名合同、脚本门禁冲突时，以命名合同和脚本实际返回为准；先停止当前动作，
记录 recovery，再按故障码恢复。不要手写替代流程。
