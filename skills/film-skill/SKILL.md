---
name: film-skill
description: Operate screenplay projects inside the canonical Agent-KB safely, including source intake and formal import for Scrivener .scriv projects, PDF, DOCX, Word, old outlines, old drafts, and reference screenplays; scene-unit audits; screenplay-format checks; turning user outlines into structured scene breakdowns and screenplay drafts; deconstructing old drafts for iterative revision; and analyzing reference screenplays for craft patterns. Use when Codex needs to inspect, diagnose, summarize, validate, create AI task/report artifacts, build screenplay assets, or draft/revise under write/film without modifying source scenes before explicit user approval.
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
---

# film-skill

Use this skill for screenplay projects in `/Users/lynch5mo/Work Documents/LLM/agent-kb`.

## Intake Entry

Start imported-source work from `write/film/00_intake.md`. Keep original files in the user's NAS main-library `raw/inbox/<batch-id>/`; prefer `film-<date>-<source>` batch names for Film. For Scrivener `.scriv`, PDF, DOCX, or Word files, read prepared Markdown/text under `_prepared_md/` or generated import reports when available.

## Workflow

1. `cd /Users/lynch5mo/Work Documents/LLM/agent-kb`.
2. Read `outputs/recovery/upgrade-preflight-20260701-screenplay-kb-baseline.md` if the task changes structure, templates, scripts, or Skill/MCP behavior.
3. For PDF, DOCX, old-outline, old-script, or reference-script intake, start from `write/film/00_intake.md` and use exact NAS or mirrored `raw/inbox/<batch-id>/` source paths.
4. Locate the target `project_id` under `write/film/`.
5. Read the project's `00_project.md` and `agent-policy.md`.
6. If the task is project-level, create or read an `ai-workspace/tasks/AI-TASK-*.md` task card.
7. Read only paths allowed by `agent-policy.md` and the task card.
8. Write only to `ai-workspace/`, `ideas/`, `conversations/`, or `outputs/review/film/<project_id>/` unless the user explicitly authorizes more.
9. Never overwrite `scenes/` by default. Put suggested rewrites in `ai-workspace/rewrite-candidates/`.
10. Before calling any scene "complete", apply `references/scene-unit-contract.md` and `references/screenplay-format-contract.md`.
11. Run `python3 scripts/screenplay_kb_check.py --project <project_id>` before claiming completion.
12. Before final response, append the current project-related chat to today's continuous log under `conversations/`.
13. Leave an Agent task summary under `outputs/review/agent_task_summaries/<Agent>/`.

## Conversation Backups

Every project-related chat with an Agent is a Film project asset. Save it under the target project before final response whenever the task touches a `FILM-*` project. Use one continuous file per project per day so intermittent discussion remains readable in order.

Use this path shape:

```text
write/film/<project_id>/conversations/CONV-YYYYMMDD.md
```

Rules:

- The filename is local date only, e.g. `CONV-20260702.md`.
- `type` must be `conversation_log`.
- If today's file exists, append a new time-block. Do not create separate topic/session files for the same date.
- Use a section heading like `## HH:MM-HH:MM Agent · Topic` for each appended discussion block.
- Preserve the full visible chat content inside the time-block. Do not replace the backup with a summary.
- Keep summaries, decisions, and produced asset links below that time-block's transcript; they are secondary.
- If the Agent cannot access earlier parts of today's conversation, say so inside the appended block under `coverage_note`; do not claim the daily log is complete.
- Do not put conversation backups in `ai-workspace/reports/`; that folder is for analysis outputs, while `conversations/` is the raw project memory layer.

## Ideas

Use `ideas/` for long-form Agent ideas that emerge during discussion: distilled points, creative directions, structural judgments, options, and open questions the user may want to return to. This is not the raw chat log and not a formal proposal.

Use this path shape:

```text
write/film/<project_id>/ideas/IDEA-YYYYMMDD-001-<slug>.md
```

Rules:

- `type` must be `idea_note`.
- Keep the idea tied back to `source_conversation: conversations/CONV-YYYYMMDD.md` when it came from a chat.
- Use `ideas/` when the Agent has generated a substantial thought worth preserving outside the raw transcript.
- Do not put rewrite candidates here. Scene rewrites stay in `ai-workspace/rewrite-candidates/`.
- Do not put task/status reports here. Reports stay in `ai-workspace/reports/`.

## V1 Priority

This skill is structure-first and approval-gated, not analysis-only.

Default to these three workflows:

1. Outline to screenplay:
   - ingest the user's outline;
   - deconstruct the outline into acts, sequences, scenes, and unresolved gaps;
   - create or propose scene breakdowns, scene goals, character bios, background/world bible, and other screenplay assets;
   - wait for user confirmation on the framework;
   - only then draft scenes or a full screenplay within the confirmed framework.

2. Existing draft to revision:
   - ingest the user's finished or partial script;
   - deconstruct it into scenes, scene goals, character bios, outline, clues, and structural diagnosis;
   - discuss a revision plan with the user;
   - only then produce rewrite candidates or apply authorized changes.

3. Reference screenplay analysis:
   - ingest a mature/reference screenplay as reference-only material;
   - deconstruct it into screenplay assets and craft patterns;
   - extract reusable techniques for the user and Agent to learn from;
   - do not merge its characters, scenes, or source text into a creative project.

Do not jump from outline or imported text directly to final screenplay. First build the scene map and asset layer. Source `scenes/` may be modified only after explicit user approval; before approval, put drafts and rewrites in `ai-workspace/` as candidates.

For prose-like old drafts, do not treat narrative paragraphs as screenplay scenes. First run `scene_unit_audit` to split continuous time/place units, then `screenplay_format_check` on sample or target scenes. A scene-map, beat table, or scene design note is not a completed screenplay page.

For third-party or reference scripts, mark outputs as `reference_analysis` or `technique_extraction`. Do not treat reference material as the user's draft, do not rewrite it, and do not write it directly to `wiki/`.

## Scrivener Import

For `.scriv` packages, first run a read-only import assessment. Do not create or overwrite formal `scenes/` directly from Scrivener output.

```bash
python3 scripts/import_scrivener_project.py --scriv "/path/to/project.scriv"
```

The script parses `.scrivx`, follows Binder order, converts `Files/Data/*/content.rtf` with macOS `textutil`, strips Scrivener placeholders such as `<$ScrKeepWithNext>`, and writes:

- `outputs/review/film/scrivener-import-<项目名>/manifest.tsv`
- `outputs/review/film/scrivener-import-<项目名>/draft-preview.md`
- `outputs/review/film/scrivener-import-<项目名>/import-report.md`

Only after the user confirms the import mapping should an Agent create a formal Film project or write candidate scenes. Preserve Scrivener hierarchy for interactive scripts; do not flatten branches into a normal linear screenplay without explicit approval.

After the user explicitly confirms formal import, run:

```bash
python3 scripts/formal_import_scrivener_project.py --scriv "/path/to/project.scriv" --project "项目名"
```

Rules for formal import:

- Use the user-facing Chinese title as the project name. The script normalizes it to `FILM-项目名`.
- The script refuses to overwrite an existing `write/film/FILM-*` project.
- It mechanically imports included Scrivener `Screenplay` text items into `scenes/`, creates `00_project.md`, `agent-policy.md`, `source-cards/`, `ideas/`, `outline/imported-scene-map.md`, `characters/`, `ai-workspace/`, and a Longform `manuscript.md`.
- It preserves Binder order. Do not merge, delete, or creatively rewrite imported text during this step.
- If a text item lacks a recognizable scene heading, the script inserts `内    待确认地点    待确认` and marks `source_scene_heading_inferred: yes`; the next task must be `scene_unit_audit`.
- After import, run `python3 scripts/screenplay_kb_check.py --project "FILM-项目名"` and fix only mechanical structure/format issues needed for the checker. Do not rewrite story content in the import step.

## Scrivener Export

Use Scrivener export only for user-owned Film projects. Do not hand-write a minimal `.scrivx` package. Scrivener expects a full project package with Settings, compile/script-format files, Binder metadata, `Files/Data`, and backup/index files that match a real saved project.

Export with the template-backed script:

```bash
python3 scripts/export_scrivener_project.py --project "FILM-项目名" --output "write/film/FILM-项目名/exports/项目名-v0.1-scrivener-full-export.scriv" --overwrite
```

Rules for export:

- The exporter must copy a known-good Scrivener template package, preserve its top-level `.scrivx` structure, settings, section types, script format, front matter, characters, places, notes, research, template sheets, and trash.
- Replace only the `Screenplay` DraftFolder children with the Film project's ordered scenes.
- Replace the `Characters` folder children from `write/film/<project_id>/characters/*.md`. Never keep template characters such as another project's driver/passenger placeholders.
- Scene order must come from `write/film/<project_id>/manuscript.md` Longform frontmatter when present; otherwise sort `scenes/S*.md`.
- Each exported scene must be `Type="Text"`, `IncludeInCompile=Yes`, `TextMode=Script`, and must write only the scene's `## 剧本正文` section into `Files/Data/<UUID>/content.rtf`.
- Each exported character must be `Type="Text"`, `IncludeInCompile=No`, use a character-sheet icon when available, and write the character note body without YAML frontmatter into `Files/Data/<UUID>/content.rtf`.
- Remove stale `.lock` files from the copied package. Remove stale `binder.backup` and regenerate it from the new `.scrivx`.
- After the final `.scrivx` is written, parse all Binder UUIDs and delete any `Files/Data/<UUID>/` directory whose UUID is not in the Binder. Otherwise Scrivener will open the package with a "Recovered Files" warning.
- Do not export AI notes, scene goals, reports, rewrite-candidate metadata, or Markdown scaffolding into Scrivener screenplay text.
- Verify the package by parsing the generated `.scrivx`, counting `Screenplay` children, checking `Characters` titles match the Film project, checking `Settings/scriptformat.xml` and `Settings/compile.xml`, checking no `.lock` files remain, checking `Files/Data` has zero orphan directories, and round-tripping through `scripts/import_scrivener_project.py`.

## Longform Index

Use Obsidian Longform for manual screenplay ordering and manuscript compilation when the user asks to manage, sort, or merge scenes in Obsidian.

For a project whose scene files live in `write/film/<project_id>/scenes/`, create or repair one Longform index file at `write/film/<project_id>/manuscript.md`.

The index file must contain exactly one YAML frontmatter block at the top. Do not append a second `--- ... ---` block in the note body.

Required Longform shape:

```yaml
---
longform:
  format: scenes
  title: 项目名
  draftTitle: v0.1
  workflow: Default Workflow
  sceneFolder: scenes
  scenes:
    - S001_场名
    - S002_场名
  ignoredFiles: []
---
```

Do not put the Longform index inside `scenes/` when the scene files live in its parent folder. Longform 2.1 filters scenes by checking the Obsidian adapter path for `sceneFolder`; parent-relative values such as `..` are unreliable. Use a project-root `manuscript.md` with `sceneFolder: scenes`.

Generate the `scenes` list from actual `S*.md` files, sorted by filename, without the `.md` suffix. Missing numbers such as `S043` / `S044` are allowed; Longform follows list order, not numeric continuity.

For final screenplay export, do not concatenate full scene Markdown. Longform manages ordering; the export must keep only each scene's `## 剧本正文` section and output plain text (`.txt`) so Markdown preview does not turn dialogue indentation into code blocks.

Final export setup:

1. Ensure `scripts/longform/screenplay-body-only.js` exists in the Agent-KB repo. Do not edit the Longform plugin itself.
2. Set `.obsidian/plugins/longform/data.json` `userScriptFolder` to `scripts/longform`.
3. Use a Longform workflow with these steps, in order:
   - `scripts/longform/screenplay-body-only.js`
   - `remove-links`
   - `concatenate-text` with separator `\n\n`
   - `write-to-note` with target `exports/<项目名>-<draftTitle>-reading_print.txt`
4. Reload Longform, then run `longform:longform-compile-current`.
5. Verify the output has no `场景意图`, `修改记录`, Markdown headings, or frontmatter:
   `rg -n "场景意图|修改记录|^# |^## |^---$" exports/<file>.txt`

## PDF Export

Use the local Obsidian plugin `screenplay-pdf-export` for print-ready PDF output. It wraps `scripts/export_screenplay_pdf.py`, reads the current Film project's `manuscript.md`, keeps only each scene's `## 剧本正文`, writes HTML under `exports/`, then renders PDF with local Chrome headless.

The Obsidian command defaults to a shooting-print style export: scene numbers beside scene headings and page numbers in the footer. The output path is `exports/<项目名>-<draftTitle>-shooting_print.pdf`.

PDF export includes a first-page cover with the screenplay title and `author` from `00_project.md` (or a blank `作者：` line if unset), then screenplay pages, then a final `剧终` marker after the last scene.

Run from Obsidian with command `screenplay-pdf-export:export-screenplay-pdf`. The script can also be run directly:

```bash
python3 scripts/export_screenplay_pdf.py --manuscript write/film/<project_id>/manuscript.md --scene-numbers --page-numbers
```

For reading-print output without scene numbers, omit `--scene-numbers`. Verify PDF output with `pdfinfo`, `pdftotext`, and render spot-checks with `pdftoppm`.

## Pitfalls

### Project naming: use Chinese characters, not pinyin

The user explicitly requires project directory names in Chinese characters, not pinyin or English transliteration.

- ✅ Correct: `FILM-命运的那边`
- ❌ Wrong: `FILM-MINGYUNNABIAN`

The `project_id` in frontmatter must match the directory name exactly after the `FILM-` prefix. Directory rename requires updating all frontmatter `project_id` fields and Dataview path references in the project's files.

### Source material classification: narrative prose = possible outline

When the source material is narrative prose (story-like paragraphs, no screenplay format elements), do not assume it is a "completed script." It may be a **story outline** (故事大纲/文学剧本大纲). The distinction determines the correct workflow:

| If it is… | First task |
|-----------|-----------|
| An outline | `outline_deconstruction` → scene breakdown |
| A completed script | `draft_deconstruction` → revision plan |

Signal: if the text reads like a short story with no INT./EXT. scene headings, character cues, or dialogue formatting, present it to the user as "this looks like an outline" and let them confirm before committing to a workflow.

### Worldbuilding: rules before characters before scenes

When adapting existing material into a new setting/world, or building a world from scratch:

1. ❌ Do not jump to scene-level adaptation immediately — mapping every old scene to a new equivalent produces shallow world dressing.
2. ❌ Do not start from characters either — character logic follows from world logic. "不要从人物倒推世界观，这样容易越走越歪。"
3. ✅ First define the world's operating rules using the **Q1–Q5 framework** (see `references/worldbuilding-methodology.md`):
   - Q1: Where do basic necessities come from?
   - Q2: What is the material exchange direction between layers?
   - Q3: What is the nature of the value equivalent (currency)?
   - Q4: What is the vertical social structure?
   - Q5: What is the population's base state?
4. ✅ Then let characters find their natural positions within those rules.
5. ✅ Only then write scenes.

If the user stops you mid-adaptation and says "we're not there yet," you jumped too fast. Pull back to the world layer. Do not propose character-specific details until Q1–Q5 have at least a provisional answer.

### Format testing: start small, iterate with checker

When testing a new screenplay format rule, do not attempt a full rewrite. Instead:

1. Create a task card with explicit format constraints and allowed read paths.
2. Write a single scene sample into `rewrite-candidates/`.
3. Run `screenplay_kb_check.py` and check the error list.
4. Fix and re-run before scaling to more samples.
5. Only declare the format proven after a scene sample passes the checker with zero errors.

## Project Shape

Canonical project directory:

```text
write/film/FILM-项目名/
├── 00_project.md
├── agent-policy.md
├── bible/
├── outline/
├── characters/
├── scenes/
├── clues/
├── source-cards/
├── ideas/
├── conversations/
├── ai-workspace/
├── versions/
└── exports/
```

Different `FILM-*` projects are closed creative worlds. Do not share characters, scenes, clues, source cards, or rewrite candidates across projects. Reusable methods go to `wiki/summaries/film/` only through the normal approval flow.

For imported reference scripts, use a separate project or task scope. The source text may be read only when the user explicitly provides or selects it in the task card. Store derived summaries, maps, and classification reports in `ai-workspace/` or `outputs/review/film/<project_id>/`.

## References

- `references/project-contract.md`: project layout and object fields.
- `references/agent-task-contract.md`: task card and permission flow.
- `references/scene-unit-contract.md`: what counts as one film scene.
- `references/screenplay-format-contract.md`: standard screenplay draft text rules.
- `references/scene-audit-and-format-test-protocol.md`: full-play audit methodology (keep/split/confirm) and 4-round format testing protocol.
- `references/report-types.md`: report and rewrite output types.
- `references/worldbuilding-methodology.md`: Q1–Q5 worldbuilding framework — define a world's logic before writing characters or scenes.
- `references/permission-boundary.md`: read/write boundaries and forbidden operations.

## Templates

Reusable Markdown templates live in the Agent-KB repo at `write/templates/film/`. Portable copies are also bundled in this skill under `templates/`.
