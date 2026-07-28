# 课程与阅读学习执行流程

本文件是原 `agent-kb-workflow` Skill 的课程与阅读扩展，不是独立 Skill。知识库内 `schema/AGENT_RULES.md` 与 `schema/learning_collections_contract.md` 优先于本文件。

## 1. 触发条件

用户出现以下任一意图时加载本流程：

- 新增、处理、继续、暂停或恢复一门课程或一本书；
- 处理视频、音频、字幕、课件、原书、书摘或章节；
- 请求翻译、章节拆解、课程分析、阅读扩展、知识导图或学习进度；
- 讨论与某门课程或某本书相关的问题，并需要保存互动结果。

## 2. 权威入口与读取顺序

用户投料入口：

- 课程：`/mnt/lynch5mo-pool/agent-kb/browse/agent-kb/raw/courses/`
- 书籍：`/mnt/lynch5mo-pool/agent-kb/browse/agent-kb/raw/books/`

macOS canonical Git repo：

```text
/Users/lynch5mo/Work Documents/LLM/agent-kb
```

开工顺序：

1. 在 canonical repo 同步 Git 并核对工作树。
2. 读取 `schema/AGENT_RULES.md`。
3. 读取 `schema/learning_collections_contract.md`。
4. 通过 NAS 清点指定课程或书籍对象，不对整个 NAS browse 执行 `git clean`。
5. 读取对象 `README.md`、`course.yaml|book.yaml`。
6. 读取 `_prepared/manifest.yaml` 与 `assets/manifest.yaml`。
7. 读取 `ops/data/learning/progress/<collection_id>.yaml`。
8. 读取当前单元的中文材料、对话、分析和导图。
9. 必要时再读取 collection map、domain summary 或 NAS 大型原料。

本机、NAS browse、手机和外部 Agent 使用同一个 Git 仓库相对路径。不同 clone 是同一版本的同步工作副本，不是互相独立的知识副本。

## 3. 文件类型与大小分流

固定阈值：

```yaml
git_track_max_bytes: 25000000
```

必须读取真实字节数：

| 文件 | 路由 |
|---|---|
| 视频、音频 | 无论大小都 NAS-only |
| 原书 PDF、EPUB、MOBI 等 | 无论大小都 NAS-only |
| 字幕、课件 `size_bytes <= 25000000` | 默认 Git 跟踪 |
| 字幕、课件 `size_bytes > 25000000` | NAS-only，在 manifest 记录相对路径、大小和 SHA-256 |
| 轻量清理稿、中文译文、Markdown 对话 | 默认 Git 跟踪 |
| QA、分析、导图、扩展阅读 | 对象 `assets/`，默认 Git 跟踪 |

不得凭扩展名或主观感觉判断“大文件”；先读取 `size_bytes`。视频、音频和原书不适用阈值例外。

## 4. 文件与语言决策

### 中文材料

- 书籍或文本：提取、清理、章节切分，不翻译成英文。
- 视频或音频：生成中文转写并校验。
- 使用 `translation_strategy: none`、`translation_status: not_required`。

### 英文材料

- 英文书籍：提取 → 章节切分 → 中文翻译 → 中文 QA。
- 英文字幕：中文翻译 → 中文 QA。
- 英文视频/音频：英文转写 → 转写校验 → 中文翻译 → 中文 QA。
- 默认 `translation_strategy: full`；用户明确按单元推进时可用 `rolling`。

### 中英混合材料

- 保留原中文，只翻译英文片段。
- 保持段落、章节、页码、课次或时间戳对齐。

原书、原媒体和原转写不得被覆盖。译文、提取稿和转写放在对象 `_prepared/`；默认学习材料不强制中英双语。

## 5. 预处理与真实学习

预处理状态：

```text
pending
→ extracting | transcribing
→ translating
→ qa
→ ready
```

任一阶段可进入 `blocked`。`_prepared/manifest.yaml` 记录输入、输出、语言、覆盖率、锚点和缺口。

预处理完成不等于学习完成。只有用户真实学习、互动或明确确认后，才能推进：

```text
planned → ready → active → completed → review_due → reviewed
```

## 6. 弹性持续排程

固定 `schedule_mode: flexible_sustained`：

- 以 `weekly_capacity_minutes` 为主要约束；
- 尽量提供每日最小行动，但单日中断不算失败；
- 时间更多时可提前学习后续 `ready` 单元；
- 每轮用实际用时校准后续预计用时。

落后时依次：

1. 缩小单次任务；
2. 移动复习节点；
3. 调整当周容量；
4. 最后调整预计完成时间。

每轮结束更新 `actual_minutes`、`understanding`、`open_questions`、`next_review_at`、`next_action` 和 `replan_reason`。

## 7. 对象资产路由

- 高价值问答：`assets/qa/`
- 章节/课次分析、逻辑整合和复盘：`assets/analysis/`
- Canvas、Mermaid、图片导图：`assets/maps/`
- 对象专属扩展阅读：`assets/extensions/`
- 唯一资产清单：`assets/manifest.yaml`

Git 资产项使用仓库相对路径：

```yaml
asset_id: map-lesson-01
kind: map
unit_id: lesson-01
storage: git
repo_path: raw/courses/course-example-2026/assets/maps/example.canvas
size_bytes: 1234
sha256: 64位小写十六进制
created_by: AgentName
created_at: YYYY-MM-DD
```

写入事务：

1. 在对象 `assets/<kind>/` 生成或更新正文。
2. Canvas 校验合法 JSON；Markdown 校验来源锚点。
3. 确认 `repo_path` 未越出本对象 `assets/`。
4. 计算真实字节数和 SHA-256。
5. 更新唯一 `assets/manifest.yaml`。
6. 按真实互动更新学习进度。
7. commit + push；成功后各端拉取同一版本。

不得恢复 NAS `artifacts/` 或全局 `ops/data/learning/artifacts/<collection_id>.yaml`。不得在 `write/assets/learning/`、`write/drafts/learning/` 或 `outputs/qa/learning/` 留第二份正文。

## 8. 故障处理

- NAS 不可用：只阻塞必须读取原视频、原音频、原书或 NAS-only 大课件的步骤；已有 Git 译文、对话、资产和进度仍可使用。
- Git push 失败：保留本地提交或工作树，标记 `sync_pending`；恢复后先 pull/rebase 再 push。
- 多 Agent 冲突：显式解决 Git 冲突，禁止最后写入静默覆盖。
- 资产校验失败：不更新 manifest，不删除可恢复的旧正文，输出差异。

## 9. 知识晋升

对象内对话和资产不是稳定知识。只有来源清楚、结论稳定且已有 `approved: yes` 分类或晋升审批时，才能进入：

- 单源知识：`wiki/summaries/<domain>/`
- 跨章节/课程/书籍综合：`wiki/syntheses/`

导图不能替代 summary，完整聊天不能直接伪装为稳定知识。

## 10. 完成回报

每次回报至少包含：

- 预处理状态与当前学习单元；
- 本轮真实学习进度和理解薄弱点；
- 下一步行动及重排原因；
- 新增或更新的对象资产路径；
- `assets/manifest.yaml` 状态；
- Git commit/push 或 `sync_pending` 状态；
- 仍需 NAS 的原料依赖；
- 需要用户确认的知识晋升事项。

