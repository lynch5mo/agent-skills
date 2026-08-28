---
name: movie-organizing
description: >-
  Use when a user asks an assistant to normalize a mixed or inconsistently
  named movie library in unattended batches within an explicitly bounded
  TASK_ROOT.
license: MIT
metadata:
  version: "1.3.0"
  author: lynch5mo
  tags: [media, movie-library, batch-plan]
  trigger: User asks to normalize a mixed movie library in batches.
---

# Movie Organizing

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

### 3. 命名快通道（三态）

先按命名语法判断状态，不把全库先放进 `明确/待查/冲突` 深分流：

- `NAMING_PASS`：现名已经完全符合合同且无目标碰撞；无动作，立即退出深查，只进入最终对账。
- `NAMING_READY`：只需语法规范化，且可由现有名称/目录事实和合同唯一生成目标；保留已有片名、年份、release token，不改变电影身份、导演、年份事实或归属，不触发三源查证。
- `EXCEPTION`：身份、导演、年份、归属或主视频不明，特殊容器/结构，多版本或重复关系，Unicode/实体边界，sidecar 配对不明，或任何目标碰撞/不可逆风险。不得临时加后缀、覆盖或猜名。

命名快通道不读取 NFO 内容、不跑 `ffprobe`/IMDb、不算完整 hash、不做去重或深度归类；这些只属于后面的 `EXCEPTION` 慢通道。

### 4. Naming bundle 与 10–20 项锁定计划

对每个 `NAMING_READY` 项生成一条完整 bundle：导演夹 old/new、电影夹 old/new、主视频 old/new、现有 NFO old/new（无 NFO 显式记录缺失且不补造）、每个现有字幕 old/new、合同明确垃圾的 trash 映射、依据和回滚路径。任何缺项、歧义或目标碰撞都降为 `EXCEPTION`。

按一个导演或有限文件块生成 10–20 项原子计划并锁定 hash。计划级必须有 `scan_id/standard_id/plan_hash`；动作级必须有 `id/action/source/target/evidence/rollback/preconditions/postconditions`、`old exists`、`new absent` 和 canonical 后代证明。`trash_target` 仅用于 trash 动作，`content_hash` 仅用于精确重复或异常完整性；禁止 `sentinel`/`__KEEP__`/`__SKIP__`、`old==new`、重复目标和缺字段。

### 5. 命名复扫与早退出

计划验核通过后，执行该批明确 bundle；每个子项现场复扫导演夹、电影夹、视频、NFO、字幕、残留/碰撞、bytes、sidecar 和工作单。子项复扫 PASS 后才允许改父目录。

`NAMING_PASS` 项永远不回到深查：禁止继续读 NFO 内容、运行 `ffprobe`、查 IMDb、计算 hash、去重或深度归类；它只在最终终扫中计数。复扫失败按 B13/B04 处理，不以返回码代替现场验收。

### 6. 仅 EXCEPTION 进入慢通道

- 只对 `EXCEPTION` 按 `明确/待查/冲突` 细分；快通道明确项不被异常项阻塞。
- 仅在确有必要时读取 NFO 的 `title/originaltitle/year/director`、运行 `ffprobe` 核对时长/分辨率、查询 IMDb suggestion；三源互证后才能改变语义事实或生成新 bundle。
- 完整 hash 只用于目标碰撞形成的候选精确重复或异常完整性确认；时长、分辨率或抽样 hash 不能裁决重复。差异版本保留并走冲突路径。
- 慢通道闭环者回到 bundle/计划门禁；仍不闭环者仅将最小可逆单元移入 `TASK_ROOT/_待确认_` 或原地冻结。合同已明确为垃圾的无语言字幕直接按计划移入固定 trash，不猜语言。

### 7. 终扫与报告

全量复扫仍排除 `_work-record_`、`_待确认_`、全部 `_trash_*` 媒体内容，但最终统计必须包含三类控制目录。输出 `主任务已规范化，待确认 N项`；仅当 `待确认=0` 且终扫 PASS，才可输出 `全部完成（待确认=0且终扫PASS）`。

## 执行顺序（硬规则）

通过计划门禁后，固定按同一 bundle 执行：**视频 → NFO/字幕 → 计划内 trash → 电影夹 → 导演夹**。每条记录 `old/new/bytes/sidecar/证据路径`；任何执行中发现的新事实都停止受影响项并按 B 卡处理，不临场改计划。

导演夹只有在该导演全部受影响子项都已闭环、复扫 PASS 且目标不冲突时才允许最后改名；否则保留原夹并报告。所有 trash/pending 均保留原相对结构并留可逆证据。

## 中断、分类与回收

- 中断恢复先现场复扫并按 B04 对齐 `未执行/已执行/部分执行`；已 `NAMING_PASS` 项不重新深查，未闭合 bundle 或部分执行项只从未完成动作恢复。
- `明确` 是身份/sidecar/目标已闭环；`待查` 是仍可低成本核验；`冲突` 是多候选、归属/版本/边界或不可逆风险。`待确认` 只接收最小完整单元并保留恢复路径。
- 普通任务不重新扫描 `_待确认_`；只有用户明确要求处理该目录时才重开范围。所有异常先按 `failure-handling.md` 的 B 码，不以工具报错替代媒体冲突。

## 参考

- [naming-contract.md](references/naming-contract.md)
- [runtime-and-safety.md](references/runtime-and-safety.md)
- [triage-and-edge-cases.md](references/triage-and-edge-cases.md)
- [failure-handling.md](references/failure-handling.md)
- [lessons-and-audit-checklist.md](references/lessons-and-audit-checklist.md)

## v1.3 实操补充（2026-08-28 捷克库实测）

以下规则从捷克库（CIFS/NAS 大批量混合库）实操中总结，是对上述阶段门禁的补充，不替代任何硬约束。

### 导演夹间隔号合规

导演夹中 `·`（U+00B7 MIDDLE DOT，中文间隔号）是外国人名的标准排版惯例，不属于合同"禁点格式"所禁止的 `.`（句点/英文点）。合同示例 `刁亦男 Yi'nan Diao` 是中文名无需间隔号的情况；外文名导演夹使用 `中文名·英文名` 格式合规，不需要改为空格。

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
3. 若不同，保留内容更完整/质量更高的版本，另一个进 trash。

### 特殊容器处理

`DVD/`、`蓝光/`、`短片/`、`纪录片/`、`访谈花絮/`、`长片/`、`BFI Complete Shorts/` 等是非标准结构容器，不按普通电影夹处理：

1. 内有视频文件的：提取英文名，为每部电影创建独立 film folder 并移入。
2. 空目录：直接删除（递归从深到浅）。
3. 含子目录的：逐个检查子目录内容，按上述规则处理。
4. 访谈花絮中的其他导演作品：标为 `EXCEPTION`，不移入当前导演夹。

### 重复版本保留策略

同一影片多个版本（不同编码/分辨率/来源）按以下策略处理：

1. 先比对文件大小和 SHA1（至少比对文件大小）。
2. 大小不同 → 不同编码/来源，均保留，标为 `冲突`。
3. 大小相同 → 可能是复制副本，需 SHA1 确认。
4. 差异版本保留在原位，不合并、不删除，在工作单中记录所有版本的路径和大小。

### 年份冲突三源验证

目录年份与视频 release 年份不一致时：

1. 使用 IMDb suggestion API `https://v2.sg.media-imdb.com/suggestion/x/<关键词>.json` 查证。
2. 确认正确年份后，**目录**改为查证年份，**视频文件**保留 release 原始年份 token（合同规则）。
3. 无法确认的标为 `EXCEPTION` 冻结。
