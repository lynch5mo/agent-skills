# 课程与阅读学习执行流程

本文件是原 `agent-kb-workflow` Skill 的课程与阅读扩展，不是独立 Skill。知识库契约优先于本文件。

## 1. 触发条件

用户出现以下任一意图时加载本流程：

- 新增、处理、继续、暂停或恢复一门课程；
- 新增、处理、继续、暂停或恢复一本书；
- 处理课程视频、音频、转写、课件、原书、书摘或章节；
- 请求章节拆解、课程分析、阅读扩展、知识导图或学习进度；
- 讨论与某门课程或某本书相关的问题，并需要保存互动结果。

## 2. 开工读取顺序

课程与书籍的用户投料真源固定为：

- 课程：`/mnt/lynch5mo-pool/agent-kb/browse/agent-kb/raw/courses/`
- 书籍：`/mnt/lynch5mo-pool/agent-kb/browse/agent-kb/raw/books/`

`/Users/lynch5mo/Work Documents/LLM/agent-kb` 是 macOS canonical 编译工作副本，不是用户投料入口。不得要求用户把课程视频或原书复制到本机路径。

1. 确认 canonical Agent-KB 编译仓根目录并同步 Git。
2. 读取 `schema/AGENT_RULES.md`。
3. 读取 `schema/learning_collections_contract.md`。
4. 通过 NAS 主库清点课程或书籍对象目录；NAS browse 工作区只按对象读取，不执行全库 pull、reset、clean 或覆盖。
5. 从 `ops/data/learning/items.csv` 定位 `collection_id`。
6. 读取对象的 `README.md` 与 `course.yaml|book.yaml`。
7. 读取 `_prepared/manifest.yaml`；不存在时先做材料清点。
8. 读取 NAS 对象的 `artifacts/manifest.yaml` 与 Git `ops/data/learning/artifacts/<collection_id>.yaml`；不存在时建立空 manifest/index。
9. 读取 `ops/data/learning/progress/<collection_id>.yaml`；不存在时从模板建立。
10. 读取 collection map、相关 domain summary 和必要 raw source。

大型视频、音频、原书、预处理结果和对象专属 Agent 产物都留在同一 NAS 对象目录。Git 只持久化规则、进度、稳定知识与 artifact 路径/哈希索引。处理文件时使用临时工作区，并在上传、校验和索引更新后清理临时正文。

## 3. 文件与语言决策

### 中文材料

- 书籍或文本：提取、清理、章节切分，不翻译。
- 视频或音频：生成中文转写并校验。
- 使用 `translation_strategy: none` 与 `translation_status: not_required`。

### 英文材料

- 英文书籍：提取 → 章节切分 → 中文翻译 → 中文质量检查。
- 英文转写：中文翻译 → 中文质量检查。
- 英文视频或音频：英文转写 → 转写校验 → 中文翻译 → 中文质量检查。
- 默认 `translation_strategy: full`。

### 中英混合材料

- 保留原中文。
- 只翻译英文片段。
- 保持段落、章节、页码、课次或时间戳对齐。

### 不可违反的边界

- 原书、原媒体和原转写保持不变。
- 译文、提取稿和转写放在对象目录 `_prepared/`。
- 不强制生成中英对照学习稿。
- 无法读取、转写或翻译时进入 `blocked` 并报告真实原因。

## 4. 预处理状态

```text
pending
→ extracting | transcribing
→ translating（需要中文化时）
→ qa
→ ready
```

任一阶段可进入 `blocked`，解决后回到原阶段。

`_prepared/manifest.yaml` 记录每个源文件、处理状态、输出、覆盖率、锚点和已知缺口。

默认完整预处理后再开放整个对象。用户明确选择滚动方式时，每个单元仍必须先完成自身中文材料，才能进入 `unit_status: ready`。

## 5. 学习结构

- 课程优先按模块和课次拆分。
- 书籍优先按独立论证单元的章节或章节组拆分。
- 每个单元都有稳定 `unit_id`。
- 单元前置依赖未满足时保持 `planned`。

单元状态：

```text
planned → ready → active → completed → review_due → reviewed
```

预处理完成不等于学习完成。只有用户真实学习、互动或明确确认后，才推进学习状态。

## 6. 弹性持续排程

固定 `schedule_mode: flexible_sustained`。

初始计划至少读取：

- 用户目标；
- `weekly_capacity_minutes`；
- 单元数量、依赖和预计用时；
- 材料准备状态；
- 已知截止日期。

日常安排：

- 尽量提供每日最小行动。
- 单日没有完成不算失败，不清零、不制造补签。
- 时间更多时可以提前完成已 `ready` 单元。
- 每轮使用实际用时校准预计用时。

落后时按固定顺序重排：

1. 缩小单次任务；
2. 移动复习节点；
3. 调整当周容量；
4. 最后调整预计完成时间。

任意时刻都要能回答：

- 当前学到哪里；
- `next_action` 是什么；
- 为什么安排这一步；
- 哪些内容待复习；
- 哪些材料或依赖仍被阻塞。

## 7. 每轮学习闭环

### 开始前

1. 读取当前单元、薄弱点和 `next_action`。
2. 检查单元中文材料是否 `ready`。
3. 根据用户今天可用时间缩放任务。

### 互动中

- 解答问题时引用对应章节、页码、课次或时间戳。
- 把不确定结论标记为待核对。
- 区分作者观点、课程观点、Agent 分析和用户判断。

### 结束后

更新：

- `actual_minutes`
- `unit_status`
- `understanding: unknown|low|medium|high`
- `open_questions`
- `next_review_at`
- `next_action`
- `replan_reason`

## 8. 产物路由

- 原料和完整对话：NAS 主库对象目录 `raw/courses/<id>/` 或 `raw/books/<id>/`。
- 提取、转写和中文译文：对象目录 `_prepared/`。
- 单次高价值问答：同一 NAS 对象的 `artifacts/qa/`。
- 章节分析、逻辑整合和复盘：同一 NAS 对象的 `artifacts/analysis/`。
- Canvas、Mermaid、图片导图：同一 NAS 对象的 `artifacts/maps/`。
- 对象专属扩展阅读：同一 NAS 对象的 `artifacts/extensions/`。
- NAS 产物清单：同一对象的 `artifacts/manifest.yaml`。
- Git 控制面索引：`ops/data/learning/artifacts/<collection_id>.yaml`，只保存 NAS 路径、大小、`sha256`、生成者和时间。
- 稳定单源知识：审批后进入 `wiki/summaries/<domain>/`。
- 跨章节、跨课程或跨书综合：晋升审批后进入 `wiki/syntheses/`。

对象专属产物正文只保存一份。不得在 `write/assets/learning/`、`write/drafts/learning/` 或 `outputs/qa/learning/` 留第二份正文。完整聊天不能直接当作稳定知识页，导图不能替代 summary。

### 8.1 产物写入事务

1. 在临时目录生成产物，保留 `collection_id` 与 `unit_id`。
2. 按格式校验；Canvas 必须是合法 JSON，Markdown 必须可读。
3. 上传到 NAS 对象的对应 `artifacts/` 子目录。
4. 从 NAS 端计算并核对 `sha256` 和字节数。
5. 同步更新 NAS `artifacts/manifest.yaml` 与 Git artifact 索引。
6. 更新进度文件中的证据路径为 NAS 绝对路径。
7. 删除临时正文，再报告完成。

NAS 不可用时进入 `blocked`：不得把 Git 旧目录当成永久替代，不得更新索引为未落盘路径，也不得声称产物已保存。

## 9. 暂停、恢复与完成

暂停时保留当前单元、理解度、问题、复习点和下一步。

恢复时：

1. 检查对象材料和预处理状态是否变化；
2. 读取最后学习时间；
3. 长时间中断先安排简短回顾；
4. 根据当前可用时间重新计算本周任务；
5. 从原位置继续，不清零。

对象只有在所有必需单元完成、必要复习结束，并由用户确认学习目标达到后，才能进入 `completed`。

最终综合仍是草稿或晋升候选；未经分类或晋升审批不得直接写入 `wiki/`。

## 10. 完成回报

每次回报至少包含：

- 预处理状态；
- 当前学习单元；
- 本轮真实进度；
- 理解薄弱点；
- 下一步行动；
- 计划是否重排以及原因；
- 新增产物路径；
- NAS manifest 与 Git artifact 索引状态；
- 需要用户确认的事项。
