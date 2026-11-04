---
name: agent-kb-workflow
description: "仅用于 canonical Agent-KB 中的查询、入库、对象学习、图谱策略或报告归档；普通书籍问答、阅读、翻译和转录不因题材自动触发。"
license: MIT
metadata:
  version: "1.12.0"
  author: Hermes Agent
  platforms: [linux, macos, windows, android]
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

### 按当前任务选择流程

只读查询只读取相关对象和必要约定，不生成报告、不更新学习进度、不提交推送；可以不同步，但回答中注明所依据的 `HEAD`。写入任务开工先跑 `bash ops/scripts/agent_start.sh`（规则原文：`schema/AGENT_RULES.md` §1 第 1 条）。写入、入库、归档和同步步骤仅在本次授权范围内执行；仅要求转录、翻译或回答问题，不附加知识编译。相同版本已读资料及有效验证结果可复用，输入变化后再检查。

### Key Rules (Apply to the relevant write/intake phase)

This Skill says how to work; it does not own the rules. Every "must / never" rule lives in `schema/AGENT_RULES.md` and `schema/*_contract.md`, and when they disagree with this Skill the repository wins (conflict order: `schema/AGENT_RULES.md` §0). Rule history: `schema/CHANGELOG.md`.

Repository rules you will hit most often (read the cited section, do not rely on this summary):
- Summary page format — 5 sections with equivalent Chinese/English headings, required frontmatter, no promotion lines in Summary/Key Points: `schema/AGENT_RULES.md` §4, §8
- File naming and duplicate pages — numeric source ID, else 6-char source hash; one summary per source: `schema/AGENT_RULES.md` §5
- Entity/concept links in summaries — relative Markdown links, never code backticks: `schema/AGENT_RULES.md` §4 item 6
- Concept/entity page thresholds — one table only: `schema/AGENT_RULES.md` §4.2
- Classification approval — monthly path `raw/manifests/<YYYY-MM>/`, pre-approval via `schema/source-preapproval.yaml`: `schema/AGENT_RULES.md` §7
- Large-domain navigation through generated topic maps: `schema/AGENT_RULES.md` §9; `ops/scripts/kb_topic_maps.py`
- Wiki change log — only wiki-changing events, monthly files, via `python3 ops/scripts/kb_wiki_log.py append ...`: `schema/AGENT_RULES.md` §11
- Lint — `new_violations` must be 0 (lint exits 3 otherwise); legacy backlog does not block: `schema/lint_contract.md` §4–§6
- Unreadable sources — mark `review_status: needs-ocr` + `quality_flag: garbled-source-text`: `schema/AGENT_RULES.md` §8 item 3
- Rule changes — record every `schema/` change in `schema/CHANGELOG.md`; `schema/source-preapproval.yaml` changes need lynch5mo's approval: `schema/AGENT_RULES.md` §0, §7

Workflow reminders:
- NAS stores, Agent machine compiles
- Learning intake source of truth is the NAS browse root:
  - courses: `/mnt/lynch5mo-pool/agent-kb/browse/agent-kb/raw/courses/`
  - books: `/mnt/lynch5mo-pool/agent-kb/browse/agent-kb/raw/books/`
- The macOS canonical repo is the Agent compilation worktree, not the user-facing course/book drop location
- Keep video, audio, and original books in their NAS object folder regardless of file size; never add them to Git
- Measure subtitle and slide files: `size_bytes <= 25000000` defaults to Git tracking, while larger files stay NAS-only with path, size, and SHA-256 in the object manifest
- Keep lightweight preprocessing, Markdown conversations, progress, and every object-specific question, analysis, map, and extension under the same object path in Git
- Store generated bodies under object `assets/`; `assets/manifest.yaml` is the single asset manifest
- Never maintain a second asset body under NAS `artifacts/`, `write/assets/learning/`, `write/drafts/learning/`, or `outputs/qa/learning/`
- For authorized object writes, validate assets and the manifest; update learning progress only from real user interaction. Commit and push only when synchronization is in scope
- Never announce completion before evidence
- Local commit is not completion: push to `origin/main`, then require `git rev-list --count origin/main..HEAD` to be 0 and `git status --porcelain` to be empty; if push fails, mark `sync_pending` and report the task as incomplete
- All seed objects must have real sources
- Series ID is the canonical bridge between KB and workstation
- Concept and entity links use the relative Markdown form the ingest script writes, e.g. `[收益率曲线](../../concepts/finance/收益率曲线.md)`; lint checks these for broken targets. Code format `` `概念` `` is prohibited
- Never write to wiki/ without approval: a classification approval file (user-written, or generated from an `active` rule in `schema/source-preapproval.yaml`) for ingest, or an approved proposal for refactor/promotion
- Course and reading tasks use this existing Skill; do not create a competing learning Skill
- Chinese sources pass through without translation; English content becomes Chinese working material in preprocessing
- Record date and time come from `schema/kb-timezone.yaml` through `python3 ops/scripts/kb_date.py date|ts|tzname`, never from the host clock. Current `record_tz` is `America/New_York` (epoch `e2`); files written under `e1` used `Asia/Shanghai`, and the boundary lives in that yaml. Never hardcode `TZ=Asia/Shanghai` or a `-04:00` / `-05:00` offset — New York shifts twice a year. When a shell script needs it, put `KB_TIME_TZ="$(python3 ops/scripts/kb_date.py tzname)"` and `export TZ="$KB_TIME_TZ"` on separate lines so a failed substitution is not swallowed
- Never overwrite original source files with transcripts, extraction, or translation output
- Preprocessing readiness is not learning completion; update learning progress only from real user interaction
- Use flexible sustained scheduling: weekly capacity first, daily minimum action when practical, and no failure reset for a missed day
- Durable `outputs/` reports are Git-tracked across devices but excluded from Obsidian search and graph indexing; never use `.gitignore` as the graph boundary
- Codex, Claude, and Hermes are instance-managed report families; bind each family once per clone before its first report
- New managed-family reports go under the registered instance directory; never add a new report at a managed family root
- Output is evidence: a command exiting 0 with truncated or partial output is NOT complete proof; verify counts, hashes, and required sections, and write one logical document per operation. Expected size/SHA-256 must be computed independently from the intended payload or source manifest before the final write lands; do not accept a post-write backfill as verification
- Prefer `scripts/verify_output_batch.py` as the machine-verifiable evidence entrypoint for batch output: it checks expected files (existence, size, SHA-256, required sections) from a small JSON manifest and prints one JSON line. Manual protocol checks are fallback only

---

## Cross-Device Agent Report Closeout

Read `schema/AGENT_RULES.md` and the task-relevant contract when writing Agent-KB. Read `schema/agent_report_contract.md` and `ops/agents/instance-registry.json` only when creating a managed report; reuse them while the checkout is unchanged. Plain read-only queries do not enter report closeout. The repository contract is authoritative for repository operations.

### Clone-local identities

| Agent family | Instance | Platform | Local Git config |
| --- | --- | --- | --- |
| `Hermes` | `hermes-mac` | macOS | `agentkb.hermesInstance` |
| `Hermes` | `hermes-ubuntu-desktop` | Ubuntu | `agentkb.hermesInstance` |
| `Hermes` | `hermes-vivo-mobile` | Android | `agentkb.hermesInstance` |
| `Codex` | `codex-mac` | macOS | `agentkb.codexInstance` |
| `Codex` | `codex-ubuntu-desktop` | Ubuntu | `agentkb.codexInstance` |
| `Claude` | `claude-code-mac` | macOS | `agentkb.claudeInstance` |
| `Claude` | `claude-code-ubuntu-desktop` | Ubuntu | `agentkb.claudeInstance` |
| `Pi` | `pi-mac` | macOS | `agentkb.piInstance` |
| `Pi` | `pi-ubuntu-desktop` | Ubuntu | `agentkb.piInstance` |
| `DeepSeekHarness` | `deepseek-harness-mac` | macOS | `agentkb.deepseekHarnessInstance` |
| `DeepSeekHarness` | `deepseek-harness-ubuntu-desktop` | Ubuntu | `agentkb.deepseekHarnessInstance` |
| `DeepSeekHarness` | `deepseek-harness-android-mobile` | Android | `agentkb.deepseekHarnessInstance` |

Bind an instance from inside the actual clone, then validate the canonical family name:

```bash
python3 ops/scripts/configure_agent_instance.py set <instance_id>
python3 ops/scripts/configure_agent_instance.py check Hermes
python3 ops/scripts/configure_agent_instance.py check Codex
python3 ops/scripts/configure_agent_instance.py check Claude
python3 ops/scripts/configure_agent_instance.py check Pi
python3 ops/scripts/configure_agent_instance.py check DeepSeekHarness
```

Claude Code uses the canonical family `Claude`, never `ClaudeCode`. Identity lives only in that clone's `.git/config`; a new clone must bind again. Do not infer identity from hostname, username, IP, or device serial.

Pi uses the canonical family `Pi` and lowercase instance ids `pi-mac` / `pi-ubuntu-desktop`. The macOS and Ubuntu Pi are separate devices: each writes only its own instance directory and never writes for the other.

DeepSeek Harness uses the canonical family `DeepSeekHarness` and lowercase instance ids `deepseek-harness-mac` / `deepseek-harness-ubuntu-desktop` / `deepseek-harness-android-mobile`. The three devices are separate: each writes only its own instance directory and never writes for the others.

### Durable report paths

Managed families write only to:

```text
outputs/review/agent_task_summaries/<agent_family>/<instance_id>/TASK-<task-id>.md
outputs/review/agent_activity/<agent_family>/<instance_id>/YYYY-MM-DD[-e2].md
```

Activity files written under epoch `e2` carry the `-e2` suffix so e1 and e2 never
share one file; the report tool derives it from the epoch config. Do not hand-create
a new activity file without the suffix.

When report commit and synchronization are authorized, use the safe closeout entrypoint (it writes, commits and pushes; it is not a read-only verification command):

```bash
bash ops/scripts/agent_finish.sh <agent_family> TASK-<task-id> <summary-file.md>
```

It validates identity, injects `agent-report-v1` frontmatter, stages only the summary and activity record, commits, and pushes. Existing staged work blocks closeout; unrelated unstaged work stays untouched. A failed push preserves the local commit and returns `sync_pending`.

If that entrypoint cannot run in the current sandbox, do not skip the record or the
push — fall back to the report writer and close out by hand:

```bash
python3 ops/scripts/agent_report.py write --root . --family <agent_family> \
  --task-id TASK-<task-id> --source <body.md>
git add outputs/review/agent_task_summaries/<family>/<instance>/TASK-*.md \
        outputs/review/agent_activity/<family>/<instance>/*.md
git commit -m "chore(kb-review): 记录 <task>" && git pull --rebase origin main && git push origin main
```

`--source` is a plain body file; the script owns the frontmatter and the record date,
and refuses to overwrite an existing report. Then verify the remote head:
`git ls-remote origin main` must equal `git rev-parse HEAD`.

Delivery is a separate gate from reporting. A task is not done while
`git rev-list --count @{u}..HEAD` is non-zero, and a report whose own 遗留 section says
未推送 is evidence of an unfinished task, not a finished one: push, re-verify, then
mark complete.

Historical root-level reports are immutable legacy. `ops/agents/legacy-report-baseline.json` is the exact allowlist: do not migrate old reports, invent device provenance, add new root-level reports, or expand the baseline during ordinary work.

### `outputs/` admission (hard)

`outputs/` is a run-artifact layer with a **closed directory list**. Agents must not create directories there. A missing slot is a contract change, not a local decision.

Allowed top level, only these five: `health/`, `planning/`, `qa/`, `recovery/`, `review/`.

Allowed under `outputs/review/`, only these five: `agent_task_summaries/`, `agent_activity/`, `film/`, `movie-library/`, `user_summaries/`.

Allowed under `outputs/qa/`, only this one: `learning/`.

Task-scoped evidence and review files live **flat** in `outputs/review/`, prefixed with the task id:

```text
outputs/review/TASK-<task-id>-<name>.md
outputs/review/TASK-<task-id>-<name>.json
```

No per-task subdirectories. Article workspaces, conversation backups and per-task lifecycle logs are **not** sanctioned as directories: prose goes to `write/drafts/`, raw dialogue to `raw/conversations/`, task lifecycle traces follow the flat `TASK-<id>` rule, and other intermediates stay out of Git.

Never treat "not covered by `.gitignore`" as evidence of admissibility. `.gitignore` decides what syncs; it never decides what may exist.

Need a new directory? Amend `schema/AGENT_RULES.md` §2.2 and get owner approval **first**, then write. The contract states this explicitly: a gap is fixed in the contract, never by creating the directory and explaining afterwards.

Enforcement: `outputs_structure_violations` in the lint report must be 0. It walks `outputs/` → `outputs/review/` → `outputs/qa/`. Any other directory, or a stray file directly under `outputs/`, is a P1 finding.

### Git and Obsidian are separate boundaries

- Durable reports remain Git-tracked so other Agents and devices receive them.
- `ops/obsidian/index-policy.json` excludes all of `outputs/` and `write/` from Obsidian search and graph indexing.
- After pull or policy changes, run `bash ops/scripts/sync_obsidian_graph.sh` and then `bash ops/scripts/sync_obsidian_graph.sh --check`.
- If stale nodes remain, rebuild the vault cache. In Settings → Files and links → Rebuild vault cache, or, when Obsidian is running on this machine, from the shell with the Obsidian CLI:
  ```bash
  obsidian vault=agent-kb eval code="app.metadataCache.clear().then(()=>'cleared')"
  obsidian vault=agent-kb command id=app:reload
  ```
  Confirm afterwards that no cached path is missing from the vault: `obsidian vault=agent-kb eval code="app.metadataCache.getCachedFiles().filter(p=>!app.vault.getAbstractFileByPath(p)).length"` must print 0. Obsidian may re-save `.obsidian/app.json` without its trailing newline; that is not a semantic change, so restore it with `git checkout -- .obsidian/app.json`.
- On Android shared storage, the active Vault may be `/storage/emulated/0/agent-kb`; verify the real Vault and Git root before pulling.

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
Preprocess → approval (sources under an `active` rule in `schema/source-preapproval.yaml` are approved automatically by ingest; everything else needs a user-written approval file) → execute ingest → confirm one summary per source → domain/topic maps are rebuilt by ingest → lint (`new_violations` 0) → git push.

PDFs whose text cannot be extracted (scans, broken font encoding) must not produce a garbage summary: OCR first, or mark the page `needs-ocr` (`schema/AGENT_RULES.md` §8 item 3).

### NAS Sync
Remote inbox from TrueNAS (`192.168.10.32`) via SSH/SCP.

Full content archived at `agent-kb-pdf-ingestion-workflow`.

---

## Phase 2: Deduplication (was `agent-kb-summary-dedupe`)

The rule is `schema/AGENT_RULES.md` §5 item 4: one summary per source document. Duplicates are identified by **source**, not by title: two pages are duplicates when their `sources` resolve to the same document (a PDF and its `_prepared_md/` copy count as one). Same title with a different source is not a duplicate.

### Process
1. Detect: lint `summaries_duplicate_source`, or `python3 ops/scripts/migrate_legacy_summaries.py dedupe --report <path>` (dry run by default).
2. Keep the page whose file name carries the source's numeric ID; otherwise the one with an excerpt and full frontmatter.
3. Lines of the dropped page's excerpt that the kept page lacks go into `## 补充摘录`; sources, entities and concepts are unioned.
4. Delete the dropped page and rewrite every link in `wiki/` and `write/` (the script does both with `--apply`).
5. Batch merges need an approved proposal first (`schema/refactor_contract.md`).
6. Lint, then commit and push.

Date or sequence numbers in names (`-2`, `【19】 220107`) are not IDs; only hyphen-joined 6–8 digit source numbers are (`kb_summary_rules.source_numeric_id`).

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
3. Update the Concepts block with relative Markdown links to the canonical concept pages (`schema/AGENT_RULES.md` §4 item 6)
4. Create concept pages only at the reuse threshold in `schema/AGENT_RULES.md` §4.2 (3–4 summaries: candidate list; ≥5: page)
5. Update domain map

Full content archived at `agent-kb-domain-concept-linking`.

---

## Phase 7: Domain Map Fix (was `agent-kb-fix-domain-maps`)

Navigation is `index.md → domain map → [topic map] → summary` (`schema/AGENT_RULES.md` §9). A domain with more than 300 summaries lists only generated topic maps under `wiki/maps/<domain>/`; never hand-edit them. Rebuild with `python3 ops/scripts/kb_topic_maps.py rebuild --domain <domain>` (ingest does this automatically).

### Critical Discovery
When filenames contain `)`, `]`, `(`, `[`, standard markdown regex truncates link targets. **Must use angle-bracket format**: `[text](<target>)`.

### Lint Script Patch
`summary_slugs_from_map()` and `find_links()` must support angle-bracket format.

### Expected Outcome
All core lint metrics in `schema/lint_contract.md` §4 are 0, including `pages_not_reachable_from_index`, `summaries_missing_from_domain_map`, `broken_summary_links` and `new_violations`.

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
   - Write `raw/manifests/<YYYY-MM>/series-manifest-<series>.md`
2. **Classification Proposal → generate proposal**
   - Present domain reasoning in chat; if user already stated domain, respect it
3. **Wait for approval → user confirms in chat**
   - Approval: `raw/manifests/<YYYY-MM>/classification-approval-<task-id>.md` with `approved: yes`, written by the user or generated by ingest when every source matches an active rule in `schema/source-preapproval.yaml` (`schema/AGENT_RULES.md` §7)
   - **Never write to wiki/ before this file exists**
4. **Precheck → readability, dedup** (MD5 hash: IDENTICAL/SIMILAR/DIFFERENT)
5. **Compile (summary-first)**
   - **SRT → MD**: strip timestamps, place in `<domain>/` or `_prepared_md/`
   - One source → one summary; file name per `schema/AGENT_RULES.md` §5 (numeric source ID, else 6-char source hash — the ingest script computes it)
6. **Concept Linking** → relative Markdown links `[概念](../../concepts/<domain>/概念.md)` (not code backticks)
7. **Navigation/Lint → maps are rebuilt by ingest; lint core metrics 0 and `new_violations` 0**
8. **Verify → Closeout**: run `python3 scripts/verify_output_batch.py --manifest <expected-manifest.json> --root "$PWD"` and require exit 0; manual counts, hashes, and required-section checks are fallback. Confirm lint zero-metrics, then git commit + push

### Dedup Rules
Extract pure text → normalize → MD5 hash. Verdicts: IDENTICAL, SIMILAR, DIFFERENT, MOSTLY_IDENTICAL.
**Re-Upload handling**: compare file sizes and line counts; keep larger/revised version; document in manifest.

### Format Conversion
SRT → MD (strip timestamps and sequence numbers), HTML → MD (extract rich_media_content, preserve image order), TSV → MD (keep text column only).

### Absolutely Prohibited
- No writing to wiki/ without approval
- No large files in Git main repo
- No 6th top-level domain
- No code format for concepts (use relative Markdown links)
- No skipping the classification approval step
- No entity/concept pages below reuse threshold (≥5 summaries)

### Known Pitfalls
- **skill_view SOP lookup failure**: `references/standards/Series Compilation SOP.md` does NOT exist — SOP content is inline here. Use the new `references/series-compilation-sop.md` file instead.
- **SRT language register**: spoken-word text contains colloquialisms, fragments, and repetition — normal, not a quality issue.
- **Large examination episodes**: mid-terms and final exams are 2-3× longer than standard episodes.
- **Output-safe large batches**: terminal output may truncate at exit 0, and large `write_file` payloads may time out, but neither is a universal hard size limit. Prefer `scripts/verify_output_batch.py` for verification; fall back to byte-capped or structured single-line summaries, independently precomputed expected size/SHA-256 (from the intended payload or source manifest), manifest/hash/required-section verification, one logical document per write, bounded chunking with idempotent retries, and retry only failed pieces. After a timeout, check the target first: if it already matches the expected hash, do not rewrite; if it does not, use atomic replacement or restore only the missing chunks rather than appending repeatedly. `wc -l` alone never proves completeness. See `references/series-compilation-sop.md` Pitfall 6 for the full output-safe protocol.

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

## Phase 10.5: Legacy Migration and OCR Backfill

Use when lint reports `historical_backlog`, or when the user supplies readable versions (OCR text or text PDFs) of sources whose pages are marked `needs-ocr`.

- Tool: `python3 ops/scripts/migrate_legacy_summaries.py <step> [--apply] --report <path>`; steps `dedupe`, `rename-id`, `frontmatter`, `residue`, `boilerplate`, `excerpt`. Always dry-run first and read the report.
- OCR queue: `outputs/review/TASK-20261103-KB-RULES-REVIEW-ocr-queue.md` maps each `needs-ocr` page to its source.
- OCR backfill: put the readable text next to the original as `<same name>.md` or `.txt`, run the `excerpt` step, regenerate the Summary / Key Points from the readable text, then remove `review_status: needs-ocr` and `quality_flag`.
- The `excerpt` step rejects garbled extraction (readability check) instead of writing it; never paste unreadable text into a page.
- Deleting or merging pages, or lowering a backlog by relaxing a check, needs an approved proposal (`outputs/planning/refactor-proposal-*.md`).

---

## Phase 11: Film / Screenplay Work

Screenplay intake, scene audits, format checks, scaffolding, asset generation and drafting under `write/film/` belong to the `film-skill` Skill. Load `film-skill` and follow it; this Skill no longer carries a copy of that workflow (`schema/AGENT_RULES.md` §1 item 11).

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
NAS object entry
→ file and language inventory
→ type and 25,000,000-byte storage routing
→ Chinese-ready preprocessing
→ Git object assets (qa / analysis / maps / extensions)
→ single assets/manifest.yaml
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
3. the object `README.md`, metadata, preprocessing manifest, and `assets/manifest.yaml`
4. the progress file
5. the relevant user or Agent handbook

Do not mark a lesson or chapter learned merely because the Agent translated, summarized, or analyzed it.
If NAS is unavailable, block only work that requires NAS-only source material; continue from existing Git translations, conversations, assets, and progress. If Git push fails, mark `sync_pending` and do not claim cross-device synchronization.
