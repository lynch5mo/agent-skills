# Triage and Edge Cases

本文件规定来源形态、异常慢通道和 CORE 后去重的快速路由；默认先计算 expected 路径再分类，不把全库预先分成三档。

## Expected 路径与命名快通道

- 每个视频单元先记录 `source_director_dir`、`expected_director_dir`、`expected_movie_dir`、`expected_video_path`、现有 NFO 的 `expected_nfo_path`、字幕的 `expected_subtitle_paths` 和 `source_shape`（`standard`/`orphan`/`dispersed`/`collection`），再分类。
- **`NAMING_PASS`**：仅当所有存在的导演夹、电影夹、视频、NFO、字幕实际路径逐字等于对应 expected 路径，缺失 sidecar 已显式记录、`source_shape=standard`、结构正确且无碰撞；无动作。它只表示命名阶段合格，CORE 前不深查；CORE 通过后仍须参加全量跨目录 DEDUPE 候选扫描。
- **`ACTION_REQUIRED`**：身份、导演、年份、归属和 sidecar 事实唯一，但需要合同规定的语法规范化，或为确定的单片 `orphan`/`dispersed` leaf、缺标准目录；必须生成完整 bundle，计划内 `mkdir`、改名和 rehome，不能无动作通过。director 下任意有限深度的确定性单视频 leaf 统一拍平到 director root。
- 多视频合集、DVD/蓝光等特殊容器、合集拆分需要语义判断，或导演/归属不明，均为 `EXCEPTION`；不得把整个合集标成 `ACTION_REQUIRED`，不得在快通道先整夹移动。进入 slowpath 的 `pending_isolation` 时，普通且非 `TASK_ROOT`/非导演 anchor 的 source 若含 unknown/child/multi-video，必须整体作为最小可逆单元移入当前 `_待确认_`，不能抽片留残骸；`TASK_ROOT`/导演 anchor 仍只隔离明确 main video + 唯一 sidecar。
- **`EXCEPTION`**：语义事实、特殊结构、sidecar 配对、Unicode/实体、版本关系或目标碰撞存在不确定性；不得在快通道猜名、覆盖或加后缀。

快通道禁止读 NFO 内容、运行 `ffprobe`/IMDb、计算完整 hash、去重或深度归类；查证只按需用于 EXCEPTION，去重只在 CORE_GATE 后进行（包括此前 `NAMING_PASS` 的 active 电影）。

对 `dispersed` 的确定单片 leaf，复用或计划内创建标准导演夹，建立标准电影夹并将主视频及 sidecar rehome 到 expected 路径；任意 wrapper 深度不构成拒绝理由。多视频 `collection` 先作为 `EXCEPTION` 交 slowpath 逐片确认，不能整夹快移。全部可确定 leaf 移出后，最上层 wrapper 若已证明只剩空目录骨架，则一次性可逆归档到 `_work-record_/flattened-empty/`；未知文件、symlink 或异常单元使相关单元整体 `EXCEPTION`，不得部分拍平。整合集不得原样留在 active tree 后算完成。

## EXCEPTION 慢通道分流

1. **明确**：`TASK_ROOT` 内，身份、导演与 sidecar 已闭环，目标可唯一复算；查证后回到 naming bundle/计划门禁。
2. **待查**：可通过最小 NFO、`ffprobe` 或 IMDb suggestion 核验；不闭环前不得执行，也不得扩大为整个导演或整批媒体待确认。普通异常 source 的整容器隔离只按上一条 source 边界执行。
3. **冲突**：多候选、归属歧义、版本差异、不可逆路径风险、目标碰撞或边界故障；先记录证据，记录后必须隔离最小完整电影单元并按 `failure-handling.md` 处理；只有系统故障导致不可移动时才原地冻结，且 CORE/DEDUPE 门禁持续失败。

三档只对 `EXCEPTION` 使用，且不阻塞已经通过快通道的批次。

无法闭环的孤立、分散或合集影片，按 source 边界移入 `TASK_ROOT/_待确认_`：普通非 anchor 异常容器含 unknown/child/multi-video 时整体移容器，TASK_ROOT/导演 anchor 只移明确 main video + 唯一 sidecar；两者都不扩大到整个导演或整批媒体。系统故障无法移动时原地冻结，`CORE_GATE` 保持失败。

## CORE 后去重、版本与差异

- 只有 `CORE_GATE=PASS` 后进入去重；`DEDUPE_GATE` 只核 active media tree（排除 `_待确认_` 与全部 `_trash_*` 媒体内容）；先按影片身份分组，再确认同一 `edition/cut`。不同剪辑、版本或内容不得合并。
- 精确重复须完整文件 hash 与清单一致；质量排序按可验证证据 `4K > 1080p > 720p`，同分辨率比较可验证码率/画质，不能仅凭文件名或大小。
- 质量唯一胜出者保留，较差副本只可逆 `mv` 到固定 trash 并保留原相对路径、证据、回滚；任意差异、证据不闭环或质量无法唯一排序时，Agent 选择 `dedupe_pending`，由 slowpath 将候选组整体安全隔离到当前 TASK_ROOT/_待确认_，不得自动淘汰。候选组留在 active tree 时 DEDUPE_GATE 失败；整体隔离后不阻塞其他 active 影片继续去重、普通清理和终扫。
- `rehome_unit` 只提交 `candidate_id`、`resolved_director_name`、`resolved_chinese_title`，可选 `main_video_name`；Agent 不提交 `action/source/target`，电影目录和文件路径由脚本根据命名合同推导。
- DEDUPE_GATE 的 active 计数 `unresolved_duplicate_groups_in_active_tree`、`inferior_copies_remaining_in_active_tree`、`dedupe_actions_remaining`、`partial_dedupe_actions` 必须全为 0；`pending_duplicate_groups` 仅用于报告，不阻塞其他 active 影片，但待确认>0 时永远不能报告全部整理完成，否则按 B08 处理。

## 主视频与 sidecar

- 主视频与 NFO/字幕/sidecar 采用同级、同 stem、同电影夹事实闭环；快通道只在现有事实可保留时配对，不凭扩展名或最长文件猜主视频。
- 合同已明确判为垃圾的无语言标识字幕（如 `video.srt`）在 `DEDUPE_GATE=PASS` 后按计划预锁 `trash_target`，可逆移入 `TASK_ROOT/_trash_<task-id>_<YYYYMMDD>/`；不得猜语言或提前清理。
- sidecar 身份/配对不确定时，随其最小完整电影单元进入 `_待确认_`；`TASK_ROOT/_待确认_` 严格按最小结构存放。

## 字符与结构异常

- 空格、单引号、重音、特殊字符问题先按实体可达性/逐字路径验证，不做 NFC/NFD 猜名。
- `Errno39`、双实体、跨卷不可达直接映射到 B05；多视频、DVD/蓝光结构、合集或父目录目标碰撞进入 EXCEPTION。

## 括号式→点式转换（v1.3）

以下实操补充仅作识别与证据，命名合同仍是唯一权威；确定的改名、建夹、rehome 必须走 `ACTION_REQUIRED` 计划和 CORE/DEDUPE 门禁，合集/特殊容器仍走 `EXCEPTION` slowpath，不能绕过安全边界。大量电影夹使用 `中文名 英文名 (年份)` 格式（括号式），需转为合同格式 `中文名.英文 Name.年份`（点式）。

**转换条件（全部满足才可自动执行）：**
1. 同目录下存在视频文件（mkv/mp4/avi/iso）。
2. 可从视频文件名提取英文名（正则 `^([A-Za-z].+?)\.(\d{4})\.` 或 `^([A-Za-z].+?)\s+(\d{4})\s`）。
3. 提取的英文名非空且长度 ≥ 2。
4. 新路径不存在同级碰撞。

**转换步骤：**
1. 提取英文名，将其中的 `.` 替换为空格（年份及之后保持点分隔）。
2. 生成新名：`中文名.英文名.年份`。
3. 仅在 `ACTION_REQUIRED` 计划内受控执行 rename/rehome（实现可用 `os.rename`），验证新路径存在且旧路径消失，并核对 expected path exact。
4. 无法提取英文名的标为 `EXCEPTION`，不猜名。

## 中文视频文件名清理（v1.3）

视频文件名中不应有中文（合同规定"文件名里不要中文"）。

**清理条件：**
1. 文件扩展名为视频类型（mkv/mp4/avi/iso）。
2. 文件名以中文字符开头（`\u4e00-\u9fff`）。

**清理步骤：**
1. 正则分离：`^([\u4e00-\u9fff\u3000-\u303f\uff00-\uffef、·]+)[\s.](.+)$`
2. 保留第2组（英文/原文部分），将其中的 `.` 替换为空格（年份后保持点分隔）。
3. 若分离失败或结果为空，标为 `EXCEPTION`。

## CIFS 大小写双目录伪影（v1.3）

在 CIFS/SMB 挂载的 NAS 上，仅大小写不同的目录名可能同时存在（不同 inode，内容相同）。

**检测方式：**
1. 目标路径已存在时，检查源路径和目标路径的 inode 是否不同。
2. 若 inode 不同且文件列表完全一致（名称+大小），判定为 CIFS 伪影。

**处理方式：**
- 跳过该重命名，标记为冲突。
- 不强制合并，不删除任一版本。
- 在工作单中记录双目录路径和 inode。

## 特殊容器归位（v1.3）

`DVD/`、`蓝光/`、`短片/`、`纪录片/`、`访谈花絮/`、`长片/`、`BFI Complete Shorts/` 等是非标准结构容器。

**处理流程：**
1. 有视频文件的：为每部电影创建独立 film folder（从视频文件名提取英文名），移入。
2. 空目录：仅在 `DEDUPE_GATE=PASS` 且计划已预锁固定 trash 目标后可逆 `mv` 到任务 trash；禁止直接递归删除（`.DS_Store`/`._*` 仍按合同例外处理）。
3. 有子目录的：逐个检查，按括号式/点式规则处理。
4. 访谈花絮中的其他导演作品：标为 `EXCEPTION`，将最小完整单元移入 `_待确认_`，不移入当前导演夹；仅系统故障导致不可移动时原地冻结且 CORE_GATE 失败。

## 年份冲突三源验证（v1.3）

目录年份与视频 release 年份不一致时，用 IMDb suggestion API 验证。

**验证方式：**
1. `curl -s "https://v2.sg.media-imdb.com/suggestion/x/<关键词>.json"` 仅用于取得候选结果。
2. 第一条结果的 `y` 只能作为候选，必须与 NFO、`ffprobe` 和目录事实完成三源互证，不得单独作为确认年份。

**修正规则：**
- 目录年份改为确认年份。
- 视频文件保留 release 原始年份 token（合同规则）。
- 无法确认的标为 `EXCEPTION`，将最小完整单元移入 `_待确认_`；仅系统故障导致不可移动时原地冻结且 CORE_GATE 失败。

## 跨任务根与回收旁路

- 跨任务根移动/跨国合并一律判冲突，不得直接转移；合集先在 `TASK_ROOT` 内由 slowpath 逐片确认，再由脚本拆为可闭环小单元。
- `.DS_Store`、`._*` 仅在 `DEDUPE_GATE=PASS` 后按命名合同直接删除；其余垃圾优先可逆 `mv` 到固定 `TASK_ROOT/_trash_<task-id>_<YYYYMMDD>/`，并预锁目标。
- 无法确认归属项不得跨任务根回收或重排；未覆盖场景按 `failure-handling.md` 的 `Bxx` 继续。
