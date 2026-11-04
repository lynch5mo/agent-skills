> Moved here on 2026-11-03 from `agent-kb-workflow` v1.10.0 Phase 11 (TASK-20261103-KB-RULES-REVIEW), so screenplay workflow lives in one Skill. Content unchanged; where it disagrees with `SKILL.md` or the other references in this Skill, those win.

# Agent-KB Film Source Intake (moved from agent-kb-workflow)

Agent-KB handles five domains: `finance`, `ai`, `film`, `lifeos`, `knowledge`. The `film` domain has its own intake workflow under `write/film/` separate from the general PDF/raw pipeline governed by earlier phases.

### Trigger
User references `$screenplay-kb-agent` or asks you to process a screenplay/剧本/大纲 file in the agent-kb.

### Workflow Routing (from `write/film/00_intake.md`)

| Input Type | First Task | Subsequent |
|-----------|-----------|------------|
| 旧大纲 (outline) | `outline_deconstruction` | `scene_breakdown` → `scene_goal_build` → `asset_build` → user confirms → `draft_completion` |
| 已写剧本 (completed script) | `draft_deconstruction` | `revision_plan` → user confirms → `revision_iteration` |
| 成熟参考剧本 | `reference_script_analysis` | `technique_extraction` → `classification_map` |
| 来源不清 | `source_intake` | judge type first |

### ⚠️ CRITICAL PITFALL: Chinese Screenplay Format Classification

**In Chinese screenwriting, a document written in narrative prose (叙事体) — with no SCENE HEADING, CHARACTER CUE, or DIALOGUE formatting — IS a standard 大纲 (outline/treatment), NOT a completed script.**

This is the single most common misclassification error. Western screenplay conventions (format = script) do NOT apply here. A Chinese 故事大纲 or 文学剧本 is written as a continuous narrative, yet it is a structural outline that maps to scenes. **Treat narrative-prose story documents as 大纲 unless the user explicitly says it's a finished script.**

Wrong classification → wrong workflow (draft_deconstruction instead of outline_deconstruction → scene_breakdown).

### Source File Prep (.doc/.docx)

Use macOS `textutil -convert txt` for .doc extraction, then write a cleaned Markdown version to `raw/inbox/_prepared_md/<title>.md`. Keep the original file at `raw/inbox/<title>.doc`.

### Film Project Scaffolding (after classification)

After a source is classified as 大纲/outline, create the FILM project:

1. **Create project directory**: `write/film/FILM-<PROJECT_ID>/` with subdirs: `bible/`, `outline/`, `characters/`, `scenes/`, `clues/`, `source-cards/`, `ai-workspace/reports/`, `ai-workspace/tasks/`, `ai-workspace/rewrite-candidates/`, `versions/`, `exports/`

2. **Write 00_project.md** — frontmatter with `type: project`, `project_id`, `project`, `status`, `format: screenplay`, `logline`, `theme`. Include Dataview tables for scenes, characters, clues, outline, reports.

3. **Write agent-policy.md** — `default_read`, `default_write`, `requires_explicit_approval`, `forbidden` sections. Copy patterns from `_template_project/agent-policy.md`.

4. **Write bible/premise.md** — story bible with 世界观, 核心冲突, 三幕结构, 主题关键词, 未决问题.

5. **Write outline/treatment.md** — full outline text with frontmatter (`type: outline`, `outline_id: OUT-001`, `outline_kind: treatment`). Include both a story summary/synopsis AND the original full text if imported from an external source.

6. **Produce 大分场表** — write as `ai-workspace/reports/AI-<date>-scene-breakdown-大分场表.md` with `type: ai_report`, `report_kind: scene_breakdown`. Required elements per scene:
    - 场号 (S001–S999), 场景名称, 地点, 时间
    - 主要人物, 事件概要 (1–2 sentence), 核心冲突, 页估
    - Include: total scene count, act structure breakdown, estimated runtime, conflict curve visualization

### Asset Generation Pipeline (after outline and 大分场表 are done)

Generate the following cards from the outline and scene breakdown. **Do not write scene full-text** (that comes later after user confirmation).

#### Character Cards (`characters/`)

One per core character, each with frontmatter:
```yaml
type: character
project_id: FILM-<ID>
character_id: C001
role: protagonist | sidekick | deuteragonist | antagonist
status: active
desire: <character's conscious goal>
fear: <deepest fear>
contradiction: <inner conflict>
secret: <hidden truth>
arc_start: <where they begin>
arc_end: <where they end>
appears_in: [S001, S002, ...]
```

Body sections: 表层目标, 深层欲望, 恐惧与缺陷, 人物弧线 (table preferred), **关键行为** (the 2–4 most defining actions in the story), 说话方式, 出场记录.

Key technique: Extract a brief **in-character quote** from the source material and place it as a pull-quote under the heading, to anchor the card in the actual text.

#### Scene Cards (`scenes/`)

One per scene from the 大分场表, with frontmatter:
```yaml
type: scene
project_id: FILM-<ID>
scene_id: S001
act: 1
sequence: 001
status: draft
location: <place>
time: 日 | 夜 | 黄昏 | 晨
characters: [C001, C002, ...]
conflict: <dramatic conflict in 8-12 words>
purpose: <scene function>
clues: [CL001, ...]
```

Body: 场景意图 (empty placeholder), 剧本正文 (empty placeholder), 修改记录 (empty placeholder).

#### Clue / Foreshadowing Cards (`clues/`)

For each major narrative thread that has a setup → payoff structure:
```yaml
type: clue
project_id: FILM-<ID>
clue_id: CL001
status: setup
setup_scene: S003
payoff_scene: S024
owner_character: C004
risk: high | medium | low
```

Body: 设置信息 (how the clue is planted visually/narratively), 回收计划 (how it pays off, what the audience should feel), 风险 (what could go wrong, suggested mitigations).

Not every clue needs its own card. Minimum threshold: the thread bridges at least 5 scenes and has a clear setup-to-payoff arc.

#### Source Card (`source-cards/`)

One card documenting the source material:
```yaml
type: source_card
project_id: FILM-<ID>
source_id: SRC001
source_paths: [path/to/original.doc, path/to/_prepared_md.md]
derived_from: 大纲 | 剧本 | 参考
usable_for: [character, scene, conflict, theme]
status: consumed
```

Body: 原始来源, 可用素材 (table), 禁止误用 (things NOT to do with this source).

### Validation

After generating all assets, run the structural validation:
```bash
python3 scripts/screenplay_kb_check.py --project FILM-<ID>
```

This checks:
- Required directories and files (bible/, outline/, characters/, scenes/, clues/, source-cards/, ai-workspace/, versions/, exports/)
- Frontmatter type/ID correctness per file
- Unique scene sequences
- Cross-project boundary violations
- ai_task/report format validity

**Pass the check before reporting completion.** If it fails, fix the frontmatter errors (usually missing `type:` or mismatched `project_id:`).

### Priority for Scene Drafting

From highest to lowest emotional return:
1. **Emotional climax** (e.g., the sacrificial death scene) — best first draft choice
2. **Action set piece** (e.g., the trade/escape scene) — biggest visual impact
3. **Opening scene** — establishes everything, good third choice
4. Remainder in sequence — fill in once the peaks are solid

Always ask the user which scene they want drafted first rather than defaulting to S001.
