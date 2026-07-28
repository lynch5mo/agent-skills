# Series Compilation SOP — Full Reference

Extracted & enriched from agent-kb-workflow Phase 9. Load this file directly via:
`skill_view(name="agent-kb-workflow", file_path="references/series-compilation-sop.md")`

## 8-Step Flow (Strict Order — Do Not Reorder)

### Step 1: Title Filter → Generate Manifest
- List all source files in the inbox directory
- **Deduplicate source files**: check for Re-Upload vs original (compare file sizes, keep larger/revised)
- Create `raw/manifests/series-manifest-<series-name>.md`
- Manifest structure: table with `#`, `Title`, `Format`, `Size`, `Status`
- Flag known duplicates and document the keep/discard decision

### Step 2: Classification Proposal
- Propose domain and reasoning to the user in chat
- Use all available context: user's explicit directive ("编译分类进 knowledge"), topical fit, channel context
- Let user approve by typing "允许" (or equivalent) in chat
- **IMPORTANT**: If the user already stated the domain in their original request, respect it — do not ask again. Just confirm and proceed.

### Step 3: Wait for Classification Approval
- User confirms in chat → write approval file at `raw/manifests/classification-approval-<task-id>.md`
- Approval file format:
  ```yaml
  ---
  task_id: <task-id>
  domain: <domain>
  approved: yes
  approved_by: user
  date: YYYY-MM-DD
  ---
  ```
- **Strict rule**: never write to `wiki/` before this file exists with `approved: yes`

### Step 4: Precheck
- **Readability**: for SRT, check if text content is clean and complete; skip video if SRT is sufficient
- **Dedup**: extract text → normalize → MD5 hash; verdicts: IDENTICAL, SIMILAR, DIFFERENT, MOSTLY_IDENTICAL
- **Duplicate source handling** (Re-Upload scenario): compare file sizes and line counts, keep the larger/revised version, note the decision in the manifest

### Step 5: Compile (Summary-First)
1. **Format Conversion**: convert source to clean MD
   - **SRT → MD**: strip timestamps (`HH:MM:SS,mmm --> HH:MM:SS,mmm` lines) and sequence numbers, keep only dialogue/narration. Place MD output in `raw/<domain>/` or `raw/inbox/_prepared_md/`
   - **HTML → MD**: extract rich_media_content, preserve image positions relative to text
   - **TSV → MD**: keep text column only
2. Run the ingest pipeline: one source item → one summary page
3. Summary page path: `wiki/summaries/<domain>/<canonical_title>-<numeric_id>.md`
4. Every summary must have fixed sections: `摘要`, `要点`, `实体`, `概念`, `原文摘录`

### Step 6: Concept Linking
- Must use `[[wiki/concepts/<domain>/<concept>|<concept>]]` wiki-link format
- Code format `` `概念` `` is prohibited
- Only create independent entity/concept pages when reuse threshold is met: referenced by ≥5 summary pages

### Step 7: Navigation / Lint
- Update domain map at `wiki/maps/<domain>.md`
- Run lint checks: broken links, missing pages, orphaned summaries
- Verify three zero-metrics: `pages_not_reachable_from_index=0`, `summaries_missing_from_domain_map=0`, `broken_summary_links=0`

### Step 8: Closeout
- `git add` all changed files
- `git commit -m "<series-name>: <domain> series compilation — N files"`
- `git push origin main`
- Report: commit hash, file count, lint results, known gaps

---

## Format Conversion Reference

| Source | Target | Method |
|--------|--------|--------|
| SRT | MD | Strip timestamps `(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})` and sequence number lines; keep dialogue/narration text only |
| HTML | MD | Extract rich_media_content; preserve image positions and ordering |
| TSV | MD | Keep text column only; drop metadata/audio columns |

---

## Absolutely Prohibited
- No writing to `wiki/` without approval
- No large files in Git main repo (>50MB)
- No 6th top-level domain
- No code format for concepts (use `[[wiki-links]]`, not `` `backtick` ``)
- No bypassing the classification approval step
- No creating entity/concept pages below reuse threshold (5 summary references)

---

## Known Pitfalls

### 1. `skill_view` Reference File Lookup
The SOP reference file at `references/standards/Series Compilation SOP.md` **does not exist**. The SOP is inline in the main SKILL.md under Phase 9. Future efforts to load it must use:
- ✅ `skill_view(name="agent-kb-workflow")` — reads the full SKILL.md including Phase 9
- ✅ `skill_view(name="agent-kb-workflow", file_path="references/series-compilation-sop.md")` — reads this extracted file (now exists)

### 2. Re-Upload Duplicates
When source directory contains both `Title.srt` and `Title (Re-Upload).srt`:
- The Re-Upload is typically a revised/corrected version
- Compare file sizes — the larger one is almost always the keeper
- Document the decision in the manifest; delete or skip the original
- Verify by sampling: check a few paragraphs of each for differences

### 3. SRT Language Register
SRT text reflects the speaker's spoken language, not polished prose. Summaries based on SRT may contain:
- Colloquialisms and verbal pauses
- Sentence fragments and run-ons
- Repetition for emphasis
These are normal and don't indicate poor source quality — but be aware when writing `摘要` sections.

### 4. Large Examination Episodes
Some series have mid-term or final examination episodes that are significantly longer (2-3× file size). These contain:
- Review of all previous content
- New integrative analysis
- Student questions and answers
Expect these to produce longer summaries and more concepts.

### 5. Domain Classification When User Already Specified
If the user says "编译分类进 knowledge" (or similar), **respect it**. Do NOT ask for reclassification — just document the user's decision in the classification proposal and proceed. Confirm only: "分类为 knowledge，确认开始编译？" with a simple "允许" response expected.

### 6. Tool Constraint Workarounds for Large Compilations (Batch Write Failure)
When compiling large series (e.g. 29+ files), several Hermes tool constraints may surface. These are NOT environment-specific bugs — they are durable Hermes agent limitations with known workarounds.

#### 6a. `write_file` Payload Ceiling
`write_file` times out when its content payload exceeds ~8K tokens (~50 lines of Markdown). **Do NOT attempt batch writes of concatenated files.** Write ONE file per tool call.
- ✅ Safe: 51–56 line file via single `write_file` call
- ❌ Fails: concatenating 3+ files into one `write_file` call (~150+ lines)
- ✅ Recovery: write each summary individually; verify with `wc -l` after each batch

#### 6b. `terminal` Output Truncation
`terminal` frequently truncates multi-line stdout to exactly 1 line (exit 0, partial output). Do NOT rely on `ls`, `cat`, or grep output for file enumeration or content verification.
- ✅ Use `wc -l` for file counting — this correctly returns the full count
- ✅ Use `python3 -c` within `terminal` for structured validation (iterate filesystem with `os.listdir()`, check file contents, validate formats)
- ✅ Confirm file existence via `python3 -c "import os; print(os.path.exists(path))"` rather than `ls path`
- ❌ Avoid parsing multi-line shell output — it will be incomplete

#### 6c. Delegation / Subagent Timeouts
Subagent (`delegate_task`) batches may time out silently for content-generation tasks (compilation, summary writing). This is NOT a rate-limit — it is a tool constraint for heavy text generation.
- ✅ Preferred approach for compilation: manual single-file writes via `write_file` + validation via `python3 -c` in terminal
- ✅ Use `terminal python3 -c` scripts for batch operations that need iteration (format checking, link validation, grep-style searches)
- ❌ Do not rely on subagents for bulk summary generation — use them only for parallel research, code generation, or light inspection tasks

#### 6d. Counting Files Under Truncation
When you need to confirm N files exist but `ls` truncates:
```python
python3 -c "
import os
d = 'wiki/summaries/knowledge'
files = [f for f in os.listdir(d) if 'Game Theory' in f]
print(f'Count: {len(files)}')
# Optionally list them if count is small enough
for f in sorted(files):
    print(f'  {f}')
"
```
