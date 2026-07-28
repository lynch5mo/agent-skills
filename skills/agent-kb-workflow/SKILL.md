---
name: agent-kb-workflow
description: "Complete agent-kb knowledge management workflow — ingest and query knowledge, manage PDF and series compilation, and assist course learning or book reading with Chinese-first preprocessing, translation to Chinese, flexible study progress, review, conversation synthesis, and knowledge-map routing. Use whenever the user mentions agent-kb, knowledge-base ingestion, a course, a book, reading, lessons, chapters, study progress, transcripts, or learning recovery."
license: MIT
metadata:
  version: "1.1.0"
  author: Hermes Agent
  platforms: [linux, macos, windows]
  hermes:
    tags: [knowledge-management, agent-kb, wiki, obsidian, compilation, dedup, concepts, course-learning, reading, study-planning]
    related_skills: [obsidian, llm-wiki]
---

# Agent-KB Workflow

Complete knowledge management workflow for agent-kb — a summary-first compilation chain that ingests PDFs, text series, and documents into an interlinked Obsidian-compatible wiki with Model Cards, Parameters, and Playbooks.

## Architecture Overview

```
Layer 1: Summary-first compilation (summaries, entities, concepts)
Layer 2: Pre-distillation (raw/clippings/)
Layer 3: Research cognition (Model Card → Parameter → Playbook → ComparisonView)
Layer 4: Learning control (course/reading preprocessing → progress → review)
```

### Key Rules (Apply to ALL Phases)
- NAS stores, Agent machine compiles
- Never announce completion before evidence
- All seed objects must have real sources
- Series ID is the canonical bridge between KB and workstation
- Concept links MUST use `[[...]]` wiki-link format (code format `` `概念` `` is prohibited)
- Never write to wiki/ without user approval
- Course and reading tasks use this existing Skill; do not create a competing learning Skill
- Chinese sources pass through without translation; English content becomes Chinese working material in preprocessing
- Never overwrite original source files with transcripts, extraction, or translation output
- Preprocessing readiness is not learning completion; update learning progress only from real user interaction
- Use flexible sustained scheduling: weekly capacity first, daily minimum action when practical, and no failure reset for a missed day

---

## Phase 1: PDF Ingestion (was `agent-kb-pdf-ingestion-workflow`)

Two modes: **incremental** (new files only) and **full rebuild** (reprocess all, triggered by keywords like `全量`, `rebuild all`).

### Pipeline
1. Navigate to KB root
2. Run `openclaw_pdf_prepare.sh` (prerequisite — text extraction, OCR for image PDFs)
3. Run `hammers_kb.sh` (summary, entities, concepts, auto-classification)
4. Review results

### PDF Preprocessing
- Dependencies: `poppler`, `mupdf`, `tesseract` with `chi_sim` language pack
- For image-type PDFs (<100 chars extracted): `pdftoppm` → `tesseract chi_sim+eng`
- OCR text cleaning: remove inter-character spaces, platform headers, ads

### Batch Import (48-PDF verified)
Preprocess → batch create approval files + execute ingest → clean duplicates → update domain map → lint + git push.

### NAS Sync
Remote inbox from TrueNAS (`192.168.10.32`) via SSH/SCP.

Full content archived at `agent-kb-pdf-ingestion-workflow`.

---

## Phase 2: Deduplication (was `agent-kb-summary-dedupe`)

### Pattern Recognition
- Pattern 1: `{base}.md` vs `{base}-2.md` (enhanced with PDF metadata) — candidates for dedup
- Pattern 2: Date/sequence numbers — NOT duplicates

### Collision Types
- **A**: True duplicate
- **B**: Same title, different source
- **C**: Same source, different pipeline
- **D**: Same title, different numeric ID

**Rule**: `-N` suffix files are NOT always duplicates. Blind deletion can lose valid content.

### Process
Detect → analyze sizes → verify difference → create dedup script → execute → verify → report → commit+push → lint.

Full content archived at `agent-kb-summary-dedupe`.

---

## Phase 3: Empty Summary Fix (was `agent-kb-empty-summary-fix`)

### Root Cause
`extract_text()` uses `textutil` which fails on Chinese PDFs. Preprocessing (`openclaw_pdf_prepare.sh`) correctly extracts text to `_prepared_md/*.md` but ingest script doesn't read them.

### Fix
Modify `extract_text()` to check for preprocessed files first, extract from `## Extracted Text` block, fall back to direct extraction.

### Recovery
Identify empty files → delete → re-run ingest with approval file.

Full content archived at `agent-kb-empty-summary-fix`.

---

## Phase 4: Domain Reclassification (was `agent-kb-domain-reclassification`)

Move files between domains while fixing ALL reference types.

### Four Reference Types to Fix
1. File migration across `wiki/summaries/`, `wiki/entities/`, `wiki/concepts/`
2. Frontmatter `domain:` field
3. Path references in cross-links (global replace across all wiki .md files)
4. Domain tags in file body (`## Domain` section)

### Obsidian Graph Pollution Fix
Obsidian depends on file-internal link paths, NOT frontmatter domain field. Fix `.obsidian/app.json` userIgnoreFilters and `workspace.json` lastOpenFiles.

### Process
11-step process from proposal generation through git commit + push + Obsidian vault sync.

Full content archived at `agent-kb-domain-reclassification`.

---

## Phase 5: Batch Remediation (was `agent-kb-batch-remediation`)

Systematic multi-batch cleanup in 7 ordered batches:

| Batch | Purpose |
|-------|---------|
| 0 | Inventory & Baseline |
| 1 | Main Chain Convergence (delete redundant files, regenerate maps) |
| 2 | Pre-distillation Layer (`raw/clippings/` scaffolding) |
| 3 | Research Cognition + First Seed |
| 4 | Proposal Templates |
| 5 | Advanced Objects (Orchestrator Playbook, placeholders) |
| 6 | Pre-integration Health Check |

Full content archived at `agent-kb-batch-remediation`.

---

## Phase 6: Domain Concept Linking (was `agent-kb-domain-concept-linking`)

Build standardized concept links and concept pages for domains with summaries but empty/low-quality concept layers.

### Process
1. Build term dictionary (canonical → aliases per domain)
2. Domain-wide scan and count
3. Update Concepts block with standardized `[[...]]` wiki-links
4. Create concept pages (threshold-based: >100 summaries → ≥5 citations; 20-100 → ≥3; <20 → ≥2)
5. Update domain map

Full content archived at `agent-kb-domain-concept-linking`.

---

## Phase 7: Domain Map Fix (was `agent-kb-fix-domain-maps`)

Fix domain maps auto-indexing for two-hop reachability: `index.md → domain_map.md → summary.md`.

### Critical Discovery
When filenames contain `)`, `]`, `(`, `[`, standard markdown regex truncates link targets. **Must use angle-bracket format**: `[text](<target>)`.

### Lint Script Patch
`summary_slugs_from_map()` and `find_links()` must support angle-bracket format.

### Expected Outcome
Three metrics all zero: `pages_not_reachable_from_index=0`, `summaries_missing_from_domain_map=0`, `broken_summary_links=0`.

Full content archived at `agent-kb-fix-domain-maps`.

---

## Phase 8: Research Cognition Layer (was `agent-kb-research-cognition-layer-setup`)

Set up Model Cards, Parameters, Playbooks, ComparisonViews, and Response Templates.

### Object Relationship Chain
```
Summary → Model Card → Parameter Card → Playbook (Atomic/Orchestrator) → ComparisonView → Artifact
```

### 10-Step Setup
Create directories → navigation map → seed Model Card → Parameter Cards → Atomic Playbook → ComparisonView → Response Template → Orchestrator Playbook (optional) → proposal templates → update index.md.

### Model Card Requirements
Complex frontmatter with `variables` (primary/derived/proxy), `parameters`, `applicability`, `failure_modes`, `confidence` block (mandatory dynamic confidence with `analyst_judgement`, `runtime_score`, `downgrade_triggers`).

### Critical Rules
- Series ID is canonical bridge
- Seed-first not template-first
- Proposal-first for all new cognition objects
- ComparisonView separate from Playbook
- Orchestrator max depth = 1

Full content archived at `agent-kb-research-cognition-layer-setup`.

---

## Phase 9: Series Compilation SOP (was `agent-kb-series-compilation-sop`)

Complete SOP for compiling large text series (e.g., 付鹏系列, Game Theory series) into agent-kb.

> **📄 Quick reference**: Load `references/series-compilation-sop.md` via
> `skill_view(name="agent-kb-workflow", file_path="references/series-compilation-sop.md")`
> for the complete SOP with extended details and pitfalls.

### 8-Step Flow (Strict Order)
1. **Title Filter → generate manifest**
   - List all files, deduplicate (Re-Upload vs original — keep larger/revised)
   - Write `raw/manifests/series-manifest-<series>.md`
2. **Classification Proposal → generate proposal**
   - Present domain reasoning in chat; if user already stated domain, respect it
3. **Wait for approval → user confirms in chat**
   - Write `raw/manifests/classification-approval-<task-id>.md` with `approved: yes`
   - **Never write to wiki/ before this file exists**
4. **Precheck → readability, dedup** (MD5 hash: IDENTICAL/SIMILAR/DIFFERENT)
5. **Compile (summary-first)**
   - **SRT → MD**: strip timestamps, place in `<domain>/` or `_prepared_md/`
   - One source → one summary at `wiki/summaries/<domain>/<title>-<id>.md`
6. **Concept Linking** → `[[concepts/finance/概念|概念]]` wiki-link format (not code backticks)
7. **Navigation/Lint → update maps, check three zero-metrics**
8. **Closeout → git commit + push**

### Dedup Rules
Extract pure text → normalize → MD5 hash. Verdicts: IDENTICAL, SIMILAR, DIFFERENT, MOSTLY_IDENTICAL.
**Re-Upload handling**: compare file sizes and line counts; keep larger/revised version; document in manifest.

### Format Conversion
SRT → MD (strip timestamps and sequence numbers), HTML → MD (extract rich_media_content, preserve image order), TSV → MD (keep text column only).

### Absolutely Prohibited
- No writing to wiki/ without approval
- No large files in Git main repo
- No 6th top-level domain
- No code format for concepts (use `[[wiki-links]]`)
- No skipping the classification approval step
- No entity/concept pages below reuse threshold (≥5 summaries)

### Known Pitfalls
- **skill_view SOP lookup failure**: `references/standards/Series Compilation SOP.md` does NOT exist — SOP content is inline here. Use the new `references/series-compilation-sop.md` file instead.
- **SRT language register**: spoken-word text contains colloquialisms, fragments, and repetition — normal, not a quality issue.
- **Large examination episodes**: mid-terms and final exams are 2-3× longer than standard episodes.
- **Tool constraint: batch write failure**: `write_file` times out beyond ~8K tokens (~50 lines of Markdown). Write one summary per call, never concatenated batches. When delegation/subagent times out during compilation, fall back to manual single-file writes + `python3 -c` terminal validation scripts. See `references/series-compilation-sop.md` Pitfall 6 for full workarounds including terminal output truncation patterns.

Full content archived at `agent-kb-series-compilation-sop`.

---

## Phase 10: Author Framework Synthesis (was `agent-kb-author-framework-synthesis`)

Synthesize an author's complete research framework from auto-compiled wiki summaries.

### 5-Phase Analysis
1. **Scope & Categorize** — count files by source category, year, duplicates
2. **Statistical Pattern Extraction** — concept frequency analysis
3. **Stratified Sampling** — time periods, size, source categories (target ~15-20 files)
4. **Thematic Synthesis** — 5 sections: Core Research Framework, Knowledge System Construction, Trading Strategy System, Evolution Trajectory, Methodological Essence
5. **Write the Synthesis** — direct quotes, concept page mapping, statistical evidence, gap admission

### Key Insight
Truncated auto-compiled summaries are still useful — opening paragraphs contain thesis, concept links reflect full text, titles are rich. Triangulate title + concept links + summary text.

Full content archived at `agent-kb-author-framework-synthesis`.

---

## Phase 11: Film / Screenplay Source Intake

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

---

## Phase 12: Course and Reading Learning Workflow

Use this phase when the user adds, continues, pauses, resumes, analyzes, or discusses:

- a course, lesson, lecture, video, transcript, or syllabus;
- a book, chapter, excerpt, or reading plan;
- study progress, review timing, learning questions, or knowledge maps tied to one learning object.

Load the full procedure before acting:

> **📄 Required reference**: `references/learning-collections-workflow.md`

Core route:

```text
object entry
→ file and language inventory
→ Chinese-ready preprocessing
→ unit structure
→ flexible sustained plan
→ real learning interaction
→ progress and next-action update
→ review
→ approved knowledge promotion
```

The canonical Agent-KB rules remain authoritative. Read, in order:

1. `schema/AGENT_RULES.md`
2. `schema/learning_collections_contract.md`
3. the object metadata and progress file
4. the relevant user or Agent handbook

Do not mark a lesson or chapter learned merely because the Agent translated, summarized, or analyzed it.
