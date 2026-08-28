# Runtime and Safety Details

仅在远程卷、FUSE、路径字符、回收站边界问题或执行顺序需要核对时读取本文件。

## 统一前提

1. 任务动作仅在 `TASK_ROOT` 后代（canonical）内执行。
2. 越界判定只用 `Path.resolve()` + 实体关系，不接受字符串前缀。
3. 默认只做可逆 `mv`；除命名合同明确允许，禁止 `rm`、`rm -rf`、`rmdir`（`.DS_Store`、`._*` 除外）。

## 初扫与快通道边界

- 初扫只收路径、目录层级、文件名/类型、视频/NFO/字幕存在性、结构异常和目标碰撞所需信息。
- 初扫禁止读 NFO 内容、跑 `ffprobe`、查 IMDb、算完整 hash、去重或深度归类；文件系统可枚举所有条目，但推理按同类模式和 10–20 项批次进行。
- `NAMING_PASS` 只进入最终对账，不再读 NFO、跑 `ffprobe`/IMDb、算 hash、去重或深查。
- `NAMING_READY` 只能从现有事实按合同做唯一语法变换；语义事实变化或不确定即为 `EXCEPTION`，进入慢通道。
- 目标碰撞必须进入 `EXCEPTION`；不得临时加后缀、覆盖或改写锁定计划。

## 工具与执行

- FUSE/远程场景：先确认 mount/uid/可写，再执行写动作。
- `sudo` 仅用于明确授权与必要分批；先保证工作单与计划可写。执行前需排除 `_trash_*` 的临时目录影响，按 TASK_ROOT 内唯一可写隔离策略处理。
- FFprobe、抽样 hash、长度/分辨率只作慢通道旁证，不替代 naming-contract 与实扫；完整 hash 仅用于目标碰撞形成的候选精确重复或异常完整性。
- 系统性挂载或权限故障视为任务阻塞，不做猜测性继续执行。

## FUSE、Unicode 与路径形态

- 大卷禁止全树 `find/os.walk`；按 `TASK_ROOT` 子范围分块扫描。
- 看到 `Errno 39`、双实体、路径不可达：只用 `os.scandir()` 返回实体做比对，不拼装 NFC/NFD 变体。
- 可达性依据 `exists/stat/repr + bytes/hash`；`inode` 只在同卷稳定场景辅助，不作为唯一依据。
- 单条动作失败按 `failure-handling.md` 的故障码处理，不做路径猜测重试。

## Sidecar、父目录与清场

- `NAMING_READY` 先形成同一条 bundle：主视频、现有同 stem NFO（缺失则记录，不补造）、每个带语言标识字幕及电影夹/导演夹 old/new；身份不确定时不要在快通道猜配对。
- 通过计划门禁后固定执行：**视频 → NFO/字幕 → 计划内 trash → 电影夹 → 导演夹**。子项现场复扫 PASS 后才改父目录。
- 导演夹只有该导演全部受影响子项闭环、复扫 PASS 且目标不冲突时才允许改名；否则原地保留并报告。
- 身份/配对不确定时，仅将 sidecar 及其单文件移入 `TASK_ROOT/_待确认_`（原结构与恢复路径），不拖拽整电影。
- 回收统一到 `TASK_ROOT/_trash_<task-id>_<YYYYMMDD>/...`，并保持原相对路径；计划中必须预先锁定目标。合同已明确为垃圾的无语言字幕可直接按计划 `mv`，不得猜语言。
- `_work-record_`、`_work-record_/recovery/`、`_待确认_`、`_trash_*` 均为可写且在任务内。

## 执行前校验（逐条）

1. `old exists`、`new absent`、`target parent exists`。
2. `old/new` 与计划逐字一致，且同为 TASK_ROOT 后代。
3. `bytes/hash`、sidecar 关系可追溯；每条有证据和回滚路径。
4. 完整 hash 仅用于目标碰撞形成的候选精确重复或异常完整性确认。

任一条件不满足不执行，并立即按对应故障卡处理后再继续明确项。
