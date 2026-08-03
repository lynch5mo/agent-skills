---
name: pay-peng-video-transcription
description: End-to-end pipeline for transcribing 付鹏 (Pay Peng) series audio/video content with Whisper, producing aligned transcripts and Markdown documents.
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  category: knowledge-management
---

# 付鹏系列音/视频转写流水线

## 路径与环境

| 项 | 路径/值 |
|---|---|
| NAS 主库 | `192.168.10.32` (TrueNAS, user: `lynch5mo`) |
| SSH key | `~/.ssh/id_ed25519_agentkb` |
| 工作根目录 (NAS) | `/mnt/lynch5mo-pool/agent-kb/browse/agent-kb/raw/inbox/付鹏系列/` |
| 本地挂载点 | `/Volumes/lynch5mo-pool/agent-kb/browse/agent-kb/raw/inbox/付鹏系列/` |
| 转写脚本 | `ops/scripts/transcribe_video.py` |
| MD 转换脚本 | `ops/scripts/convert_transcripts_to_md.py` |

> ⚠️ **硬性依赖：脚本硬编码了 `/Volumes/lynch5mo-pool/...` 路径，必须先在 Finder 中挂载 NAS 卷才能运行。**

## 环境限制（重要）

- **NAS 本地无法直接跑 Whisper**：TrueNAS 禁用 apt，无 pip、无 ffmpeg、无 torch。只有 Python 3.11.2 + numpy。
- **必须借助本地 Mac**：本地 Mac 已安装 Whisper (`openai-whisper`) 和 ffmpeg。
- NAS 硬件：4 核 CPU，即使能装包也远慢于本地。

## 进度检查命令

每次继续工作前，先跑这一组检查：

```bash
# SSH 到 NAS 检查
ssh -i ~/.ssh/id_ed25519_agentkb lynch5mo@192.168.10.32 "
cd /mnt/lynch5mo-pool/agent-kb/browse/agent-kb/raw/inbox/付鹏系列/
echo 'MP3: ' \$(find . -name '*.mp3' | wc -l)
echo 'TXT: ' \$(find . -name '*.txt' | wc -l)
echo 'Video:' \$(find . \( -iname '*.mp4' -o -iname '*.avi' -o -iname '*.mov' -o -iname '*.mkv' -o -iname '*.flv' \) | wc -l)
echo 'SRT: ' \$(find . -name '*.srt' | wc -l)
echo 'TSV: ' \$(find . -name '*.tsv' | wc -l)
"
```

**预期当前状态**（基线）：
- Audio: 233 MP3 → 233 TXT ✅ 已完成
- Video: 688 视频文件，约 98GB → 1 SRT 测试产物 ⏳ 未启动

## 运行步骤

### 阶段 1：音频转写（已完成，仅作参考）

```bash
# 在本地 Mac 上执行，NAS 已挂载
whisper /Volumes/lynch5mo-pool/.../*.mp3 \
  --model small \
  --language zh \
  --initial_prompt "以下是付鹏的财经世界音频，讨论金融市场、宏观经济、美联储政策、流动性风险、债券收益率、汇率、大宗商品、原油、黄金、日元套利、通胀通缩、货币政策等话题。" \
  --output_format txt
```

### 阶段 2：视频转写（待启动）

先确认 NAS 已挂载到 `/Volumes/lynch5mo-pool/`，然后：

```bash
# Dry run 预览
python3 ops/scripts/transcribe_video.py --dry-run

# 正式运行（small 模型，中文金融内容）
python3 ops/scripts/transcribe_video.py --model small
```

输出：`transcripts_video/` 下的 `.srt` + `.tsv`。

### 阶段 3：Markdown 转换

```bash
python3 ops/scripts/convert_transcripts_to_md.py
```

输出：`transcripts_md/` 下的 `.md`，包含 frontmatter 和时间戳。

### 阶段 4：时间轴整理

- 以文章内部标注的发布时间为准
- 不做按月拆分的物理文件夹
- 从早到晚排列

## 已知 Bug 与修复（生产实战记录）

### Bug 1：子目录未自动创建（已修复）
- **现象**：`Error processing xxx.mp4: [Errno 2] No such file or directory: ...transcripts_video/xxx.srt`
- **原因**：`transcribe_video.py` 的 `process_one()` 没有创建输出子目录
- **修复**：在调用 `transcribe_video()` 前加入 `out_base.parent.mkdir(parents=True, exist_ok=True)`
- **补丁位置**：`ops/scripts/transcribe_video.py` line ~156

### Bug 2：日志重复（未修复，不影响功能）
- **现象**：日志每行出现两次
- **原因**：`transcribe_video.py` 的 `log()` 同时 `print()` 到 stdout 又直接写文件；而 `runner.sh` 又用 `>>` 把 stdout 追加到同一日志文件
- **解决**：不影响转写，可忽略；如要修复，删除 `log()` 中的 `print()` 或改 `runner.sh` 去掉 `>>` 重定向

### Bug 3：重复进程启动
- **现象**：`Found 688 videos` 等日志开头出现两次
- **原因**：background 启动 runner 时 Hermes 的 bash wrapper 和实际脚本同时运行
- **解决**：启动后立刻用 `ps aux | grep -E 'whisper|transcribe'` 确认只有一个 Python 进程（PID 最高那个）

## 后台运行最佳实践

视频批量数量大（688 个，~98GB），建议用 Hermes background 启动 + cron 监控模式：

```bash
# 1. 创建 runner 脚本
cat > /tmp/whisper_video_runner.sh << 'RUNEOF'
#!/bin/bash
cd /Volumes/lynch5mo-pool/agent-kb/browse/agent-kb/raw/inbox/付鹏系列/
export PYTHONUNBUFFERED=1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting video transcription batch" >> whisper_video_batch.log
python3 /Users/lynch5mo/Documents/LLM/agent-kb/ops/scripts/transcribe_video.py --model small >> whisper_video_batch.log 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Batch completed" >> whisper_video_batch.log
RUNEOF
chmod +x /tmp/whisper_video_runner.sh

# 2. 用 Hermes background 启动（单实例）
# 启动后确认 PID 只有一个 Python 进程
ps aux | grep -E 'whisper|transcribe' | grep -v grep

# 3. 监控日志
tail -f /Volumes/lynch5mo-pool/agent-kb/browse/agent-kb/raw/inbox/付鹏系列/whisper_video_batch.log

# 4. 进度统计脚本
cat > /tmp/whisper_progress.sh << 'PROGEOF'
#!/bin/bash
BASE="/Volumes/lynch5mo-pool/agent-kb/browse/agent-kb/raw/inbox/付鹏系列"
TOTAL=688
DONE=$(find "$BASE/transcripts_video" -name '*.srt' 2>/dev/null | wc -l | tr -d ' ')
REMAIN=$((TOTAL - DONE))
PCT=$(awk "BEGIN {printf \"%.1f\", $DONE * 100 / $TOTAL}")
echo "已完成: $DONE / $TOTAL ($PCT%) | 剩余 $REMAIN"
echo "最近: $(tail -1 \"$BASE/whisper_video_batch.log\" 2>/dev/null | cut -c1-80)"
PROGEOF
chmod +x /tmp/whisper_progress.sh
```

## 阶段 5：批量编译入库 agent-kb（已完成 2026-05-01）

转写产物（TXT + SRT + MD）需批量编译为 `wiki/summaries/finance/` 下的 summary 页面。

### 5.1 素材状态基线

```bash
# 执行前检查
find /Volumes/lynch5mo-pool/.../付鹏系列/ -name "*.txt" | wc -l        # 音频转写  ~234
find /Volumes/lynch5mo-pool/.../付鹏系列/transcripts_video/ -name "*.srt" | wc -l  # 视频转写 ~490
find /Volumes/lynch5mo-pool/.../付鹏系列/transcripts_md/ -name "*.md" | wc -l     # 已有 MD  ~161
```

### 5.2 核心难点与解决方案

| 难点 | 现象 | 解决方案 |
|------|------|----------|
| **多来源重复** | 同一期内容可能同时存在于 txt、srt、md 三种格式 | 按标题字符串去重，只保留一个 item；优先级：md > srt > txt |
| **ID 提取混乱** | `【123】标题`、`付鹏说123`、`标题【123】`、纯日期前缀、无编号等 | 多策略 fallback：1) 匹配 `【\d+】` 或 `[【\[](\d+)[】\]]` 2) 匹配 `付鹏说\s*(\d+)` 3) hash(title) 生成 6 位十六进制 ID |
| **标题污染** | 大量推广文本：`【更多精品课程请加微信xxx】`、`（添加微信xxx送福利）`、`- 华尔街见闻` | 用简单字符串操作（非 regex）循环清除，避免中文特殊字符在 regex 中的编译问题 |
| **文件名碰撞** | 不同来源的相同标题生成相同文件名 | 命名格式：`标题-ID.md`，确保唯一性 |
| **路径陷阱** | NAS `browse/agent-kb/` 是工作副本，不是知识库 | 编译输出必须写到 `/Users/lynch5mo/Documents/LLM/agent-kb/wiki/summaries/finance/` |

### 5.3 编译脚本核心逻辑（Python）

```python
import os, re
from datetime import datetime

nas_base = "/Volumes/lynch5mo-pool/agent-kb/browse/agent-kb/raw/inbox/付鹏系列"
wiki_output = "/Users/lynch5mo/Documents/LLM/agent-kb/wiki/summaries/finance"

# 1. 收集所有素材（跳过 transcripts_ 子目录的深层遍历）
items_by_title = {}
for root, dirs, files in os.walk(nas_base):
    if "transcripts_" in root:  # 避免重复遍历已处理目录
        continue
    for f in files:
        if f.endswith(".txt"):  # 音频转写
            title = os.path.splitext(f)[0].strip()
            items_by_title[title] = {...}

# 2. 同理收集 srt、md（只有标题不存在时才加入，实现去重）

# 3. 标题清理（字符串操作优于 regex 处理中文特殊字符）
def sanitize_title(title):
    while '【更多精品课程请加微信' in name:
        start = name.index('【更多精品课程请加微信')
        end = name.find('】', start)
        name = name[:start] + name[end+1 if end!=-1 else len(name):]
    # 同理清除 （添加微信...）、- 华尔街见闻 等后缀
    return name.strip()[:80]

# 4. ID 提取（多策略 fallback）
def extract_id(title):
    m = re.search(r'[【\[](\d+)[】\]]', title)
    if m: return m.group(1)
    m = re.search(r'付鹏说\s*(\d+)', title)
    if m: return m.group(1)
    return f"{hash(title) & 0xFFFFFF:06x}"

# 5. 内容读取与格式化
#    - txt: 直接读取
#    - srt: 清除时间码和序号行
#    - md: 剥离 frontmatter

# 6. 生成 summary-first 格式（5 章固定）
#    摘要 / 要点(前10句提取) / 实体(词典匹配) / 概念(词典匹配) / 原文摘录
```

### 5.4 编译产物规范

```yaml
# frontmatter 示例
---
sources:
  - raw/inbox/付鹏系列/xxx.txt
updated_at: 2026-05-01
domain: finance
original_title: "原始文件名"
canonical_title: "清理后标题"
title_filter_mode: kept
confidence: medium
review_status: auto-compiled
compiled_by: agent
task_id: TASK-20260501-022132
---
```

### 5.5 导航收口更新

编译完成后必须更新以下文件：
1. `wiki/maps/finance.md` — 新增"付鹏系列"专区，列出代表性内容链接
2. `wiki/index.md` — Recent Summaries 添加付鹏代表性文章
3. `wiki/log.md` — 追加审计日志

### 5.6 审批流程

付鹏系列入库必须经过审批（硬性约束）：
1. 生成 `classification-proposal-{task_id}.md`（列出所有标题及建议域）
2. 用户在聊天窗口确认 `approved: finance`
3. 生成 `classification-approval-{task_id}.md`
4. 执行编译

## 时间估计（small 模型本地 Mac CPU）

| 场景 | 时间 |
|---|---|
| 实测速率 | ~**1.5 分钟/个**（标准 10 分钟视频） |
| 688 个视频总估 | ~**17 小时** |
| 含多集/长片走偏差 | 可能到 20-30 小时 |

> 注：此次修复前的旧估计"5-10 分钟/个"偏保守了很多。small 模型在 Apple Silicon/较新 Intel 上实际比预估快 3-5 倍。

## 关键脚本说明

**`transcribe_video.py`**
- 硬编码路径，仅能在挂载了 NAS 的 Mac 上运行
- 自动 `ffmpeg` 提取音频轨道为 tmp wav
- 支持 `--dry-run` 模式
- 跳过已存在的 srt/tsv 避免重复处理
- 日志写入 `whisper_video_batch.log`

**`convert_transcripts_to_md.py`**
- 输入：`.txt` (音频) 和 `.srt`/`.tsv` (视频)
- 输出：`transcripts_md/*.md`
- 自动从文件名提取时间标签

## Tags
- whisper
- video
- transcription
- pay-peng
- truenas
- nas-mount-required
