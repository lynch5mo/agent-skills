---
name: scanned-book-ocr
description: 把扫描版书籍（无文字层的 PDF）转成带页码锚点、分章、配图在原位的 Markdown，并按「图表必要、照片与装饰不必要」的原则取舍配图。用于中文教材、外文原版扫描件、影印本入库或阅读前的预处理；不用于有文字层的普通 PDF、纯文本抽取或通用网页截取。
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  category: knowledge-management
---

# 扫描书 OCR 与配图取舍

扫描件没有文字层，任何"直接抽文本"的工具都会返回空白。本 Skill 的产出是：页锚点 Markdown、按章切分的文件、落在原版面位置的配图，以及可机器核验的清单。

## 一、何时用

用：

- 中文教材、影印书、扫描版专业书，需要可检索文本和可读的分章结构。
- 书里的图表是内容本体（经济学、统计学、工程手册），裁图必须回到原位。
- 结果要进 Agent-KB 阅读对象，或要交给模型长文阅读。

不用：

- PDF 有真实文字层（先 `pdftotext -f 1 -l 5 file.pdf - | wc -c` 判断，几十字节即无文字层）。
- 只需要几页 OCR，用系统级截图识别更快。

## 二、工具选型与依据

选 MinerU（opendatalab/MinerU，2026 年 4.2.x）。它做版面分析 + 识别 + 表格结构化 + 公式，输出中间 JSON，能恢复阅读顺序，而不是把整页当一行行文字。

实测对比，同一本 960 页的中文教材扫描件：

| 指标 | macOS Vision 逐个文本块 | MinerU basic |
|---|---|---|
| 长段落（≥40 字） | 2180 | 3748 |
| 碎片段落（<12 字） | 3429 | 421 |
| 页脚书名渗入正文 | 12 | 0 |
| 页边定义框 | 插进正文句子中间 | 独立成块 |
| 表格 | 文字碎片 | HTML 结构 |

档位选择：

- `basic`：抽取式（PP-DocLayoutV2 + PP-OCRv6 + 表格/公式模型），不生成，适合入库。
- `standard` / `advanced`：加 VLM（MinerU2.5 Pro GGUF）。版面复杂时更整齐，但会编造：实测在双栏目录页把同一条篇注释复制给同页每一章，属错误归属。知识入库不要用生成档，除非逐页人工复核。

不要用 tesseract 逐页硬跑整本书：没有版面分析，页眉页脚、页边框、图表标签会和正文串成一行，返工成本高于直接上 MinerU。

## 三、一次性配置

```bash
uv tool install --python 3.12 "mineru"          # 提供 ~/.local/bin/mineru-kit
~/.local/bin/mineru-kit hardware detect          # 确认设备与推荐档位（Apple Silicon 走 MPS）
MINERU_MODEL_SOURCE=huggingface \
  ~/.local/bin/mineru-kit models download --tier basic --small-backend torch
~/.local/bin/mineru-kit models verify --tier basic --small-backend torch
```

模型落在 `~/.mineru/models`（约 0.9 GB）。要求 VLM 档时再加：

```bash
~/.local/bin/mineru-kit models download --tier standard --small-backend torch --vlm-engine llama-cpp
```

注意两点：

- 模型由 MinerU 自己的下载器拉取，目录带哈希完成清单；手工搬运会破坏校验。若本机下载受限，可在服务器下载后整目录拷贝，再跑 `models verify`。
- `uv tool install` 是长期安装；临时试用用 `uv run --with mineru`。

## 四、处理流程

```text
扫描 PDF
→ mineru-kit parse 导出 zip（含 middle_json.json、markdown.md、images/）
→ scripts/mineru_render.py 把 middle_json 还原成页锚点 Markdown，并按规则取舍配图
→ scripts/split_chapters.py 按目录与章标题切分
→ scripts/recrop_figures.py 给没有文本题注的图补裁标题行
→ 按目标格式落库（Agent-KB 对象见第八节）
→ 核验清单逐条过一遍
```

解析命令：

```bash
MINERU_MODEL_SOURCE=local ~/.local/bin/mineru-kit parse "book.pdf" \
  --pages all --tier basic --format zip -o work/book.zip
```

960 页 M1 Max 约 30 分钟，basic 档约 1 秒/页。`--pages` 支持 `1-5,8,r1`，先跑 5 页验证质量再跑全书。

## 五、配图判定（核心）

原则：图表是内容，照片、漫画、页边装饰不是。经济学、统计类书籍的图就是论证本身，缺一张就断链。

保留：

1. 版面模型判为 `chart` 的块（模型图、数据图、示意图）。
2. 题注形如「图 N-M」「表 N-M」「专栏 N」的图块。
3. 白底线条图：白像素 ≥72%、中间调 ≤25%、墨量 ≥1.5%、面积 ≥1%。用于兜住"图号印在图里、文本层没有题注"的图。

剔除：照片、漫画、封面图、页边装饰符号、无题注且墨量极低的图形（典型的页边小图标）。

两个实测陷阱：

- 只按块类型判断会误杀。同一本书里，循环流量图被标为 `image`，生产可能性边界被标为 `chart`。类型只是三条件之一。
- 只看白底比例会误留漫画。漫画是线稿，白底比例 0.75 到 0.95，和图表重叠。墨量、面积、题注能挡掉大部分，剩下的靠看图确认；把拿不准的列进 `needs_review`，让主人过一遍缩略图墙，不要自己猜。

题注归属：

- 块内子题注优先，但只认「图 N-M」形式。版面模型常把坐标轴标签（如"冰淇淋蛋卷的数量（个）"）当题注，这类一律丢弃。
- 子题注不合格时，在页内找最近的「图 N-M」文字块，要求与图块 y 方向距离 ≤0.08 且横向重叠；被占用的题注块不要重复输出。
- 题注会被拆开：「图2-1」和「循环流量图」可能在页顶被识别成两个块，且被标成 header。合并相邻短块再判定。
- 图号印在带底纹方框里时，OCR 读不出（实测 tesseract 与 Vision 都失败）。不要往正文写猜出来的图号，改成把裁图向上扩到标题行，让标题留在图里，并在清单里标 `caption_in_image`。
- 多面板图（a/b 面板、多张并列）通常共享一个图号。宁可留空，也不要把同一编号分给不同面板。

## 六、页眉页脚误判

版面模型会把页顶、页底的长段正文标成 `header` / `footer`，整类丢弃会丢正文。实测一本 960 页的书因此丢了两册 105 段。

规则：`header` / `footer` 只有在「长度 ≤40 字且不含句读标点」时才当页眉页脚丢弃；其余按正文保留在原位。

## 七、核验清单

跑完必须逐条过：

1. 页数：渲染出的页锚点数等于 PDF 页数。
2. 章：章数与目录一致，章起始页含对应章号，章页区间连续无缺口。
3. 配图：正文图片链接数等于图文件数乘以引用次数，0 缺失；清单里的 sha256 与文件一致；无孤儿图。
4. 图位：每页图块数与正文图位置数一致；抽 5 到 8 页把原页渲染和落库结果并排看，确认图在正确的两段文字之间、题注在图上方或下方与原书一致。
5. 统计对比：长段落数、碎片段落数、页脚渗入数，与上一版工具做前后对比。
6. 低文本页：页数少不等于失败，多数是章末空白页与篇分隔页；逐页确认不是抽取失败。

## 八、与 Agent-KB 的衔接

目标仓库规则优先于本 Skill：`schema/AGENT_RULES.md`、`schema/learning_collections_contract.md`。

落地形态：

```text
raw/books/<collection_id>/
├── README.md
├── book.yaml
├── source-original/           # 原书 PDF，NAS-only，不进 Git
├── _prepared/
│   ├── manifest.yaml          # 抽取方法、页码锚点、配图策略、已知缺口
│   ├── extracted/full-text.md
│   ├── chapters/chNN-标题.md
│   ├── toc.md  front-matter.md  back-matter.md
└── assets/
    ├── manifest.yaml          # 每张图：页码、bbox、题注、size、sha256
    └── figures/
```

要点：

- 题注在图上方时写在图上方，用 bbox 的 y 判断，不按惯例硬编码。
- 每张图在 `assets/manifest.yaml` 记录 `page`、`bbox`、`caption`、`caption_in_image`、`needs_review`、`sha256`。
- 无文本题注的图要有 `needs_review: true`，并生成缩略图墙供人工过目。
- 中文原书不翻译：`translation_strategy: none`、`translation_status: not_required`。英文书在预处理层出中文材料。
- 写 `wiki/` 前先有 `approved: yes` 的分类审批；只做对象和登记时不需要审批。
- 提交后跑 lint，`new_violations` 必须为 0。

## 九、已知限制

- 公式与复杂表格的版面会被打散；表格能还原成 HTML，但跨页表与合并单元格可能错位。
- 图内的文字（坐标轴刻度、数据标签）不进文本层，检索不到。
- 双栏目录按块顺序还原，条目先后可能与纸书有偏差。
- 印刷页码与 PDF 物理页不同，锚点统一用 PDF 物理页，不要混。
- 扫描件质量差时先做去噪二值化，或标记 `needs-ocr`，不要产出糊掉的摘要。

## 十、脚本

| 脚本 | 作用 | 关键参数 |
|---|---|---|
| `scripts/mineru_render.py` | middle_json 转页锚点 Markdown，含配图取舍、题注归属、页眉页脚修正 | `--zip`/`--middle-json`、`--mapping`、`--figures-dir`、`--out`、`--drop` |
| `scripts/split_chapters.py` | 目录与章标题探测、章文件切分、前后辅文分离 | `--md`、`--out-dir`、`--titles` |
| `scripts/recrop_figures.py` | 无文本题注的图向上扩到标题行、向下扩到子标题 | `--pdf`、`--zip`、`--md`、`--mapping`、`--out-dir`、`--limit` |

`--mapping` 指向的 JSON 由渲染器生成：

```json
{"images/page_32_chart_2.jpg": ["p033-chart1.jpg", 33, [0.085, 0.162, 0.733, 0.445]]}
```

值依次是自己起的图名、PDF 物理页、版面 bbox（0 到 1 归一化）。
