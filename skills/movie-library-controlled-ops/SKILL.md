---
name: movie-library-controlled-ops
description: 处理“设计个人电影资料库控制面”“做只读扫描/决策包”“规划或审核 same-category exact duplicate dry-run/verify-op”“把结果写入 Agent-KB”这类任务。适用于 `/Users/lynch5mo/Work Documents/LLM` 下的 NAS 电影库受控文件管理。
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  argument_hint: "[scan|plan|verify|kb-sync] [optional path or operation-id]"
---

# Movie-library controlled ops

## When to use

- 用户要把个人电影收藏做成跨 Agent 的长期文件管理系统。
- 任务涉及 `/Volumes/115open/Media/Movie`、`movie-decision-pack-*`、`moviectl.py`、`verify-op`、`summarize-op`、`plan-exact-samecat`、`_review/duplicates`。
- 需要判断某批重复处理是否仍然只停留在 dry-run，还是已经形成 real OP。
- 需要把电影库规则、账本、操作归档写入 `/Users/lynch5mo/Work Documents/LLM/agent-kb`。

不要用于：

- Film 创作项目、影评知识库、海报/UI/MCP 设计。
- 直接大规模移动/删除电影文件且没有现成决策包或回滚方案的场景。
- 想靠全库 hash 或 ffprobe 先做重扫描的场景。

## Inputs / context to gather

1. 当前任务属于哪一层：
   - 控制面/规则设计
   - read-only 扫描与决策包
   - exact duplicate dry-run / real OP 核验
   - Agent-KB 落地与 scoped commit
2. 真实电影文件路径是否仍是 `/Volumes/115open/Media/Movie`。
3. 当前产物路径：
   - `movie-scan-*`
   - `movie-focused-scan-*`
   - `movie-decision-pack-*`
   - `movie-ops/OP-*`
   - `agent-kb/ops/data/movie-library/*`
4. 本轮是否只允许 dry-run。
5. 如果已有 OP，先确认它是 dry-run 还是 real OP。

## Procedure

1. 先固定边界。
   - 这是个人电影资料库/文件管理系统，不是创作 Film 项目。
   - 真实电影文件与 Agent-KB 必须分离：前者留在 NAS，后者只存规则、账本、脚本、归档。
2. 对扫描类任务先做只读分层。
   - 原始扫描只负责 inventory。
   - 再收敛出 focused scan。
   - 最后生成 decision pack，至少区分 exact duplicate、version upgrade、cross-directory overlap、sidecar 风险。
   - 第一阶段优先使用 listing/stat/文件名模式/size/目录结构；不要默认上全库 hash 或 ffprobe。
3. 对重复处理先判安全层级。
   - 默认只自动推进 `same-category exact duplicate`。
   - `cross-directory exact duplicate`、`version replacement`、`edition variant` 保留人工判断。
   - 如果 group 中恰有一个 `(1)` 路径，才适合 `plan-exact-samecat`。
4. 对 OP / dry-run 做合同核对。
   - `summarize-op` 必须能区分 dry-run 与 real OP。
   - dry-run 应显示 `Verified: N/A (dry-run)`，不要伪装成 `0/N`。
   - `verify-op` 必须按 `source_rel_path / target_rel_path / keep_rel_path` 读字段。
   - `rollback.sh` 必须是 guarded rollback，不含 `rm`。
5. 对 Agent-KB 落地按控制面思路写入。
   - 先看 `ops/handbooks/movie-library-agent-handbook.md`
   - 再看 `ops/data/movie-library/rules.md`、`ledger.csv`、`directors.csv`、`operations-index.md`
   - 脚本入口是 `ops/scripts/movie-library/moviectl.py`
   - OP 归档在 `outputs/review/movie-library/operations/`
6. 需要提交时做 scoped closeout。
   - 若 repo 有无关 dirty files，不要先清理全仓。
   - 只 stage 当前 movie-library 控制面文件。
   - 提交前用实际 `move-plan.csv` / `moved-manifest.csv` / `verify-after.md` 复核归档文本。

## Efficiency plan

1. 先判断任务是 scan、plan、verify、还是 kb-sync，不要把四层混读。
2. 先找 decision pack 或现成 OP 目录；有现成产物就优先复用，不重扫全库。
3. 只要任务仍是第一阶段，就不要扩展到 hash、ffprobe、apply/move 自动化。
4. 汇报时优先给用户可决策包、planned/skipped 数、验证结论和回滚边界，不贴大段原始扫描。

## Pitfalls and fixes

- 症状：任务越做越像创作知识库
  - 原因：忽略了“只是我整个电影收藏”的边界
  - 修复：回到文件管理/控制面，不扩展到创作层
- 症状：把原始扫描直接当决策包
  - 原因：没有先清洗 `sample`、`.bdmv/.mpls`、小文件、噪音命名
  - 修复：先产出 focused scan，再收敛 decision pack
- 症状：`verify-op` 通过，但实际字段读错
  - 原因：CSV 表头合同漂移
  - 修复：严格核对 `source_rel_path / target_rel_path / keep_rel_path`
- 症状：dry-run summary 看起来像真实执行失败
  - 原因：把 dry-run 和 real OP 用了同一套 `Verified` 语义
  - 修复：dry-run 明确显示 `Verified: N/A (dry-run)`
- 症状：`git pull --rebase` 被无关 dirty files 卡住
  - 原因：把全仓清洁度当成本轮 movie-library 交付前提
  - 修复：做 scoped commit/push，不碰无关文件

## Verification checklist

- 已确认这是电影库文件管理，不是 Film 创作层。
- 已确认真实电影文件路径和控制面路径分离。
- 若任务涉及扫描，已有原始包、聚焦包或决策包中的至少一层作为输入。
- 若任务涉及重复处理，已先确认是否仅限 `same-category exact duplicate`。
- 若任务涉及 OP 验证，已核对 dry-run/real OP 语义，并检查 `verify-op` 字段合同。
- 若任务涉及回滚，已确认 `rollback.sh` 不含 `rm`。
- 若任务涉及 Agent-KB 提交，已按 scoped file set closeout，没有扩散到无关 dirty files。
