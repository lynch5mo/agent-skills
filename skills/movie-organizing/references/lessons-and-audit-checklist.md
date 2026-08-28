# Lessons and Audit Checklist

本文件仅作为短防回归索引；它不改变命名合同或阶段门禁。

实操风险点只提供候选识别与证据，必须服从命名合同、CORE/DEDUPE 门禁和可逆安全边界。

## v1.3.4 核心门禁风险总表（每批执行前后核对）

1. `TASK_ROOT` 已锁定且无越界路径（含 symlink 解析）；只有一份工作单，恢复先现场复扫。
2. 初扫仅有路径、层级、文件名/类型、视频/NFO/字幕存在性、结构异常和碰撞信息；没有读 NFO 内容、跑 `ffprobe`/IMDb、完整 hash、去重或深度归类。
3. `naming-contract` 已全文读取并锁合同 hash/`standard_id`；不能以摘要或旧任务替代。
4. 每个视频单元先记录 `source_director_dir`、`expected_director_dir`、`expected_movie_dir`、`expected_video_path`、NFO/字幕 expected 路径和 `source_shape`，再判唯一三态 `NAMING_PASS`、`ACTION_REQUIRED` 或 `EXCEPTION`。
5. `NAMING_PASS` 只有实际路径逐字等于全部 expected 路径、`source_shape=standard` 且结构无异常；它仅表示命名阶段合格，CORE 前不深查，CORE 后必须参加统一 DEDUPE 候选扫描；不得凭“看起来规范”自报。
6. `ACTION_REQUIRED` 有完整 bundle（导演夹、电影夹、视频、现有 NFO 或明确缺失记录、每个字幕、mkdir/rehome、预锁 trash 映射、证据、回滚）；孤立/分散/合集须逐片建夹并 rehome。任意 wrapper 深度的可确定 leaf 均须拍平；wrapper 全部移空后才可一次性可逆归档到 `_work-record_/flattened-empty/`，未知文件、symlink 或异常单元不得部分移动。
7. 批次限制 10–20 个视频单元；计划具备 `scan_id/standard_id/plan_hash`；公共动作字段为 `id/action/target/evidence/rollback/preconditions/postconditions`，仅 rename/rehome/trash 另需 `source`，mkdir 不带伪 source；canonical/old exists/new absent 或 mkdir 目标不存在，复扫为 old absent + new exists + expected exact；无 `old==new`、重复目标或 sentinel。
8. 目标碰撞、语义变化、特殊结构或配对不明均进入 `EXCEPTION`；无法闭环的最小完整电影单元入 `_待确认_`，原地冻结使 CORE_GATE 失败。
9. `CORE_GATE` 前禁止普通清理/去重；CORE 通过后所有 active 电影（含 `NAMING_PASS`）先按身份及同一 edition/cut 去重。完整 hash+清单只用于精确重复；质量按 `4K > 1080p > 720p`，同分辨率须有码率/画质证据，不得凭文件名/大小。
10. 去重较差副本只能可逆 `mv` 到固定 trash 并保留证据/回滚；无法裁决的重复关系整体进 `_待确认_` 后记 `pending_duplicate_groups`，不计入 active DEDUPE 计数但阻止全部完成；`unresolved_duplicate_groups_in_active_tree`、`inferior_copies_remaining_in_active_tree`、`dedupe_actions_remaining`、`partial_dedupe_actions` 全为 0 才过 `DEDUPE_GATE`。
11. CORE active 计数 `active_nonconforming_director_dirs`、`active_nonconforming_movie_dirs`、`active_nonconforming_video_files`、`active_nonconforming_nfo_files`、`active_nonconforming_subtitle_files`、`active_orphan_videos`、`active_collection_containers_with_videos`、`active_misfiled_movie_dirs`、`required_actions_remaining`、`partial_bundles`、`unaccounted_video_units` 全为 0；安全完整移入 `_待确认_` 且具备 pending 目标/来源/恢复记录的单元标记 `accounted_pending`，不计 active 违规或 `unaccounted_video_units`；该值只统计既无 active 最终路径又无完整 pending 记录的单元。旧项留在 active tree 或冻结不算通过。
12. 核心执行顺序为必要目标目录（mkdir）→ 视频 → NFO/字幕 → 电影夹 → wrapper 空骨架可逆归档 → 导演夹（每导演一次）→ 现场复扫；CORE_GATE 后才去重/DEDUPE_GATE，再普通 trash/清理和终扫。
13. `DEDUPE_GATE` 未通过不得普通清理或终扫；trash/pending 均在 TASK_ROOT 内且可逆，冲突不删不覆盖，待确认只收最小完整单元。
14. 完成语义只能是：CORE 未过则不得声称完成；active CORE、active DEDUPE、普通清理和终扫均 PASS 但待确认>0 仅报“主目录四项核心整理已完成，待确认 N项”；只有待确认=0 且 CORE/DEDUPE/清理/终扫均 PASS 才报“全部整理完成（待确认=0且终扫PASS）”。

## 对照到故障卡

- 范围与阶段控制：`B01`, `B02`, `B04`, `B14`
- 计划与执行一致性：`B03`, `B13`
- FUSE/路径/字符：`B05`, `B06`
- 身份与 sidecar：`B07`, `B09`
- 去重与版本：`B08`
- 回收与恢复：`B10`
- 权限与系统性错误：`B11`, `B12`
- 未建模问题：`Bxx`

## v1.3 实操风险点（捷克库实测）

11. 括号式→点式转换前，必须确认视频文件存在且可提取英文名；提取失败的进 EXCEPTION，不猜名。
12. 中文视频文件名清理时，正则必须正确分离中文前缀和英文部分，避免误删有效 token（如年份前的英文名）。
13. CIFS/NAS 上大小写重命名可能产生双目录伪影（inode 不同但内容相同）；检测到双目录时跳过并标记冲突，不强制合并。
14. 特殊容器（DVD/蓝光/短片/纪录片/访谈花絮）内的文件需逐个判断归属，不盲目移入当前导演夹；其他导演作品标 EXCEPTION。
15. 重复版本比对可先用文件大小筛选；大小不同不能据此判重复或淘汰，须按身份/同一 edition/cut 与 CORE 后质量证据裁决。
16. IMDb 年份验证后，只改目录年份，视频文件的 release 年份 token 必须保留（合同规则）。
17. 批量重命名时，若目标路径已存在（含仅大小写不同），必须先检查是否为 CIFS 伪影，不能直接覆盖或报错终止。

## 可选扩展

如需溯源细节，请查 [failure-handling.md](failure-handling.md)。
