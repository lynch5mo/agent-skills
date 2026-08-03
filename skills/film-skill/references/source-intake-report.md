# Source Intake Assessment Report — Template

Target: `outputs/review/film/YYYY-MM-DD-screenplay-source-intake-<标题>.md`

## Required Sections

### Frontmatter

```yaml
---
title: <标题> — 导入评估报告
type: source_intake_report
domain: film
status: draft
created_at: <YYYY-MM-DD>
created_by: Hermes ($film-skill)
source_file: raw/inbox/<file>.doc
prepared_md: raw/inbox/_prepared_md/<file>.md
---
```

### 1. File Type Judgment

Mandatory verdict table:

| Item | Value |
|------|-------|
| **Type** | 旧剧本 / 旧大纲 / 参考剧本 / 其他 |
| **Format** | 叙事体 / 标准剧本格式 / 场景大纲 / 其他 |
| **Creator** | 编剧名 |
| **Creation date** | 原始创建时间 |
| **Completion** | 已完成 / 未完成 / 片段 |
| **Source** | 来源路径 |

Plus an explicit statement: "这是一个旧剧本，不是大纲，不是参考资料，不是其他类型材料" (or equivalent confirming the specific classification).

### 2. Readability Assessment

| Item | Status |
|------|--------|
| textutil extraction | ✅ / ❌ |
| Chinese readability | 良好 / 有乱码 / 不可读 |
| Paragraphs preserved | ✅ / 需清理 |
| Cleaned MD written | ✅ at `raw/inbox/_prepared_md/<file>.md` |

### 3. Suitability for Film Project

✅ 适合 / ❌ 不适合 + reason.

Include notes on quality level, format challenges, thematic summary.

### 4. Suggested project_id

Format: `FILM-<拼音>` (no Chinese chars in ID).

### 5. Next Workflow Step

| Input type → First task | Recommendation |
|-------------------------|---------------|
| 旧大纲 | `outline_deconstruction` |
| 已写剧本 (completed draft) | `draft_deconstruction` |
| 成熟参考剧本 | `reference_script_analysis` |
| 来源不清的文件 | `source_intake` |

### 6. Content Summary

Brief synopsis: characters, plot arc, themes.

## Verified Pattern (2026-07-01)

In the first real intake, the source `.doc` was not at the Agent-KB path — it existed on SynologyDrive at:
- `/Users/lynch5mo/SynologyDrive/创作/剧作/命运的那边.doc`
- `/Users/lynch5mo/SynologyDrive/创作/曾经完成的剧本/命运的那边.doc`

Both were identical. Workflow: SynologyDrive → copy to Agent-KB `raw/inbox/` → textutil extract → clean MD → write report.

The file was a 2008 narrative screenplay (completed draft) — no standard script format, but full story arc present. Classified as "旧剧本" → recommended `draft_deconstruction`.
