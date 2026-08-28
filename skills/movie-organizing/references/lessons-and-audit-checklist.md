# Lessons and Audit Checklist

本文件仅作为短防回归索引；它不改变命名合同或阶段门禁。

## v1.2 快通道风险总表（每批执行前后核对）

1. `TASK_ROOT` 已锁定且无越界路径（含 symlink 解析）；只有一份工作单，恢复先现场复扫。
2. 初扫仅有路径、层级、文件名/类型、视频/NFO/字幕存在性、结构异常和碰撞信息；没有读 NFO 内容、跑 `ffprobe`/IMDb、完整 hash、去重或深度归类。
3. `naming-contract` 已全文读取并锁合同 hash/`standard_id`；不能以摘要或旧任务替代。
4. 每项先判 `NAMING_PASS`、`NAMING_READY` 或 `EXCEPTION`；全库不得先进入 `明确/待查/冲突` 深分流。
5. `NAMING_PASS` 只做命名复扫和最终对账，绝不重新深查；`NAMING_READY` 有完整 bundle（导演夹、电影夹、视频、现有 NFO 或明确缺失记录、每个字幕、垃圾映射、证据、回滚）。
6. 批次限制 10–20 项；计划具备 `scan_id/standard_id/plan_hash`、完整动作字段、canonical/`old exists`/`new absent`，无 `old==new`、重复目标或 sentinel。
7. 目标碰撞、语义变化、特殊结构或配对不明均进入 `EXCEPTION`；不得加后缀、覆盖或临场改计划。
8. 只有 `EXCEPTION` 才按 `明确/待查/冲突` 做最小 NFO/ffprobe/IMDb 查证；完整 hash 仅目标碰撞候选重复或异常完整性。
9. 执行顺序为视频 → NFO/字幕 → 计划内 trash → 电影夹 →（全部受影响子项复扫 PASS 后）导演夹；每条复扫 `old/new/bytes/sidecar` 并更新同一工作单。
10. trash/pending 均在 TASK_ROOT 内且可逆；冲突原地记录，待确认只收最小单元；最终语义只能是 `主任务已规范化，待确认 N项`，或在待确认=0 且终扫 PASS 时 `全部完成（待确认=0且终扫PASS）`。

## 对照到故障卡

- 范围与阶段控制：`B01`, `B02`, `B04`, `B14`
- 计划与执行一致性：`B03`, `B13`
- FUSE/路径/字符：`B05`, `B06`
- 身份与 sidecar：`B07`, `B09`
- 去重与版本：`B08`
- 回收与恢复：`B10`
- 权限与系统性错误：`B11`, `B12`
- 未建模问题：`Bxx`

## 可选扩展

如需溯源细节，请查 [failure-handling.md](failure-handling.md)。
