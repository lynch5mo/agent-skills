---
name: movie-organizing
description: >-
  批量整理杂乱电影库：先中性扫描并建立本批标准，再按明确、待查、冲突三档分流；
  生成锁定的整批目标计划后分批执行和验证。继承 movie-folder-rename-cleanup
  的命名规范与硬安全规则；无 NFO 是原始状态，不自动补造。
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  tags: [media, movie-library, normalization, naming-convention, batch-plan]
  trigger: User asks to normalize, rename, clean, or restructure a mixed or messy
    movie library in batches, especially when files and folders are irregular,
    some lack NFO metadata, or the applicable standard must be confirmed before
    execution.
---

# Movie Organizing

本 Skill 是杂乱电影库的批量规范化流程。[references/naming-contract.md](references/naming-contract.md) 是命名、冲突缺失、夹内容白名单和查证闭环的唯一权威，内容忠实复制自旧 [movie-folder-rename-cleanup](../movie-folder-rename-cleanup/SKILL.md) 第一部分；旧链接仅用于溯源，不是运行依赖。两者的差异是：旧 Skill 是定版规则手册，本 Skill 增加从混合输入推导“本批标准卡”、三档分流、计划锁定和分批执行的上下文控制。

## 固定合同（始终加载）

0. **在生成本批标准卡或任何目标名之前必须完整读取 `references/naming-contract.md`**。它是唯一命名权威；下方条目只是安全摘要，不得扩展、修改或替代该合同。
1. 目录层级：`<媒体根>/<大洲>/<导演中文名 EnglishName>/<电影文件夹>/<文件>`。
2. 导演夹用 `中文名 EnglishName`，单词间空格，禁点格式，如 `刁亦男 Yi'nan Diao`。
3. 电影夹：`中文名.英文 Name.年份.尺寸.格式[.音轨]-发布组`，如 `太阳照常升起.The Sun Also Rises.2007.CHINESE.1080p.Blu.dts-fgt`。
4. 视频文件：`English Name.年份.尺寸.格式-发布组.ext`，文件名不带中文。
5. 英文名内部单词之间必须用空格；点只作段落分隔符。年份及之后 token 用点分隔。
6. NFO 与视频 basename 完全一致。字幕为视频 basename + 小写语言标识 + 原扩展名；语言标识 `.zh/.chn/.chn0` 统一为 `.chs`，`.cht`、`.eng` 保持不变。
7. 保持原大小写、release token 和发布组原样；不可考的发布组标 `Unk` 或省略。年份冲突时，目录用查证后的影片年份，视频文件保留 release 原始年份 token。年份、片名、归属、导演英文名不确定时进待查或单议，禁止猜名或补造元数据。
8. 夹内白名单只有视频、同名 NFO、同 basename 语言字幕；其他媒体装饰件、安装件、广告、sample、老副本等移入 `_trash_`。`.DS_Store` 和 `._*` 直接删。
9. 无 NFO 不是错误，也不阻塞整理；这是原始状态。不要生成占位 NFO、不要从文件名臆造 metadata，只把该项标记为 `no_nfo_ok` 并继续可用证据链。
10. 删除永不使用 `rm/rm -rf/rmdir/rm -d`；清场一律 `mv` 进回收站。不覆盖目标，不跨夹猜配 NFO 或字幕，异版字幕宁可回收站。FUSE/NFC/NFD、单引号路径、SSH 分块等操作约束必须遵守。
11. 每次真实变更前锁定计划；计划外发现立即停止受影响项，不复核不执行。

## 流程

### 1. 长期基线

先确认长期标准来源：`references/naming-contract.md`、用户当次指令、库内既有达标样本。该合同的具体格式是硬基线；用户显式覆盖只能收窄或补充，不得违反禁覆盖、禁删除、禁造名等安全合同。没有可确认基线时先向用户要样例或裁决，不进入批量改名。

### 2. 中性扫描

只读建立批次清单，不做判断性重命名。优先浅层 `os.scandir` 或等效 API，按大洲/导演分块；避免 FUSE 全树 `find/os.walk`。每条记录保留绝对路径、父目录、basename、扩展名、类型、大小、inode、NFC/NFD 形态、NFO/字幕伴生情况和明显异常。输出写到临时工作文件，主对话只放计数、分层样例和异常摘要。

### 3. 输入模式统计

把记录聚合成模式而不是逐条推理：

- 达标目录、达标视频、达标 NFO/字幕配对数量；
- 点式导演/电影名、中文入视频名、年份缺失或冲突、发布组缺失；
- 有 NFO、无 NFO、孤儿 NFO、多视频一 NFO；
- 字幕同名、异版、子夹嵌套、idx/sub 成对或残缺；
- 多版本、疑似重复、裸视频、身份不明件、NFC/NFD 双实体；
- 白名单外文件类型和路径层级。

每个模式给计数和 1–3 个逐字路径样例；高频模式抽样验证，低风险一致模式可批量归入明确档。

### 4. 本批标准卡

根据长期合同加统计结果生成一页决策卡，字段固定：

- 适用范围、批次边界、扫描快照 ID；
- 识别为明确、待查、冲突的数量与判定条件；
- 本批接受的 release token、音轨、发布组变体和无 NFO 处理方式；
- 目标层级、回收站路径、执行块大小；
- 需要用户拍板的例外和禁止自动处理的类型。

标准卡是后续分类的唯一基准。它不能新增命名格式，只能选择应用旧合同、标注不确定项或请求用户裁决。

### 5. 三档分流

- **明确**：长期合同和标准卡都能唯一确定目标名或动作。直接进入计划，不需要额外网络查证或昂贵 ffprobe；已有可靠 NFO/路径/统计证据即可。
- **待查**：缺少一个关键事实且可能通过夹内 NFO、ffprobe、IMDb suggestion 等低成本三源闭环解决。限制查证次数，仍不确定则升级单议。
- **待查（夹名与实片不符）**：旧合同要求以视频实片为准重新查证；用夹内 NFO、ffprobe 和 IMDb suggestion 三源闭环后写入计划。任一源矛盾或仍不能唯一确定时升级为冲突。
- **冲突**：多候选、多版本剪辑、重复、NFC/NFD 双实体、跨导演归属或任何安全歧义。原地不动，列证据等待用户拍板；不得为了推进批量而猜。

三档互不阻塞：异常项暂停并报告，明确项继续进入计划。

### 6. 整批目标计划

为明确项生成完整计划，包含旧路径、新路径、动作、依据、回滚路径、预计字节数/inode 和验证要求。待查和冲突项单独成清单，不混入执行队列。计划表必须展示新名字的逐字字符；执行参数与计划表完全一致。用户批准或确认既定授权后锁定计划哈希，之后不得静默修改。

### 7. 分批执行

按导演、目录数或文件数切块，小块顺序执行；SSH/FUSE 每块保持小输出并在失败时停止该块。执行顺序：先改文件和 sidecar，最后改目录；移动前核对 old exists/new absent/target exists。所有移出物保层级进入 `_trash_<区域>_<YYYYMMDD>/<任务说明>/`。

### 8. 每批验证

每块结束立即验证：目标存在、旧路径消失或留壳符合约定、inode 不变、字节数不变、NFO/字幕 basename 对齐、非白名单残留为 0、回收站清单可逆。全部通过才进入下一块；失败块回滚或隔离到待裁决，不扩大影响。批次完成后汇总残留、无 NFO 数量、待查、冲突和回收站路径。

## 命名闭环硬门槛（2026-08-27）

- 电影夹名、主视频 release stem、字幕 basename、NFO basename 必须作为**同一条命名合同记录**生成和执行；禁止先独立改电影夹、再用另一批脚本猜视频文件名。
- 每个普通影片计划必须逐字列出 `old_film_dir -> new_film_dir`、`old_video -> new_video`、每个 sidecar/NFO 的目标名；任何目标名未锁定、由启发式猜测或只写了父目录的项目都不得进入执行队列。
- 计划生成后，必须对目标快照运行严格合同校验；以下任一普通项仍存在就阻止执行或收口：`film_name_not_primary_stem`、已知年份却 `film_no_year`、`video_internal_title_dots`、`chinese_in_video`、`subtitle_missing_language_suffix`、`subtitle_not_primary_stem`。年份/片名/导演不确定时应进入 `待查/冲突`，不能用 allowlist 掩盖。
- `MULTI_VIDEO`、DVD/蓝光、BDMV/CERTIFICATE、合集和其它特殊容器只能逐路径给出结构理由后例外；例外只豁免结构，不豁免同一夹内已经明确的普通文件名错误。
- 去重、结构整理和命名规范化必须分开验收；去重完成不代表命名合规，问题数下降也不代表国家闭合。
- 每批执行后必须从最终现场路径重新生成合同复核；只要仍有可自动确定的普通命名问题，国家状态保持 `OPEN`，不得进入下一个国家。
- 若同一计划先改子文件、后改父电影夹，验证器必须把子文件的旧目标路径重定位到最终父目录后再检查；不得把父目录改名后的旧路径不存在误报为执行失败。
- 执行器在任何媒体变更前必须检查计划、manifest、回滚证据路径可写；发现旧 root-owned 证据文件时，必须改用新的唯一证据路径或先修复权限，禁止先执行后补证据。

## 计划外新模式

执行中发现未登记的新模式时：

1. 只暂停包含该模式的异常项；
2. 把模式、逐字样例、影响范围写入批次标准卡更新记录；
3. 判定已锁定但未执行的计划是否需要复核；
4. 已执行部分照常验证，不受新模式阻塞；
5. 用户批准更新后的标准与计划后再恢复相关项。

## 渐进披露

只在对应情况读取，正常批次不要一次加载全部参考：

- FUSE、SSH、ffprobe、回收站、特殊路径操作：[references/runtime-and-safety.md](references/runtime-and-safety.md)。
- 多版本、重复、NFC/NFD、裸视频、无中文片名等疑难分流：[references/triage-and-edge-cases.md](references/triage-and-edge-cases.md)。
- 需要历史事故背景或防回归检查表时：[references/lessons-and-audit-checklist.md](references/lessons-and-audit-checklist.md)。

旧 Skill 第八部分的战例属于背景资料；除非用于解释当前同类异常，不要复制进批次上下文。

## 追加教训（2026-08-26 法国库收尾批次）

- **目录改名 Errno 39 幻影**：源目录文件已全部移出后 rename 报 Directory not empty 是 FUSE 幻影；先 listdir 确认为空，再单独 mv 空壳进回收站即可成功。
- **孤立导演单部影片**：按"仅 1 部不强造导演夹"先例处理；但若用户明确批复"新建夹归位"，则新建 `中文名 EnglishName` 夹合法。
- **2025 新片三源闭环实操**：NFO tt 号 → IMDb suggestion 反查英文标题 → TMDb find API 取 zh-CN 标题/制片国家/导演 credits（TMDb 公开演示 key 可用于查询）。
- **中文发布组名**：用户裁决可舍弃组名或转拼音缩写（弯弯→WW）；低画质重复版直接回收优于改名保留。
- **短片容器结构偏好**：欧容短片容器用户倾向保留容器形态而非全部提级；提级前需问。
- **同片双夹先 SHA1 全量比对再裁决**：欧容 11 对"DVD 版 vs 发布组版"全部 SAME，证明是改名复制副本；ffprobe 时长/尺寸一致只是旁证，SHA 才是定案证据。
- **禁止哨兵目标名与重复目的地**：`__KEEP__`、`__SKIP__` 等只能表示“不改名”，绝不能进入 rename 目标；不改名项目必须从计划中省略。生成计划时必须断言所有目的地唯一，执行前必须拒绝任何会覆盖既有目标的 `os.rename`，不能用幂等逻辑掩盖目的地冲突。
