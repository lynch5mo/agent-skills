# Series Compilation SOP — Full Reference

Extracted & enriched from agent-kb-workflow Phase 9. Load this file directly via:
`skill_view(name="agent-kb-workflow", file_path="references/series-compilation-sop.md")`

## Contents

- [8-Step Flow](#8-step-flow-strict-order--do-not-reorder)
- [Format Conversion Reference](#format-conversion-reference)
- [Absolutely Prohibited](#absolutely-prohibited)
- [Known Pitfalls](#known-pitfalls)
- [Output-Safe Large-Batch Protocol](#output-safe-large-batch-protocol)
- [Machine-Verifiable Evidence](#machine-verifiable-evidence-preferred)

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

### Step 8: Verify + Closeout
1. Verify the manifest count, per-file SHA-256, and required sections (`摘要`, `要点`, `实体`, `概念`, `原文摘录`) before treating the batch as complete
2. Run lint checks and confirm the three zero-metrics are still zero
3. `git add` all changed files
4. `git commit -m "<series-name>: <domain> series compilation — N files"`
5. `git push origin main`
6. Report: commit hash, verified file count, lint results, known gaps

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
When compiling large series (e.g. 29+ files), some tool surfaces may truncate command output at exit 0 or time out on large write payloads. These are real failure modes to design around, but they are NOT a universal hard limit tied to a specific token or line count. The exact threshold differs by runtime and payload shape, so do not encode "~8K tokens" or "~50 lines" as a rule.

#### 6a. `terminal` Output Truncation
`terminal` (and similar shell tools) may truncate multi-line stdout while still exiting 0. **exit 0 + truncated output is NOT complete evidence.** The command may have run correctly; the visible result may not prove it.
- ✅ Keep command output small: byte-cap (`| head -c <bytes>`), use `sort | uniq -c`, or print a single-line summary from a structured command
- ✅ Validate filesystem state with `python3 -c` one-liners: `print(os.path.exists(path))`, `print(len([f for f in os.listdir(d) if ...]))`, or hash/format checks that print one line
- ✅ Treat the manifest as the source of truth: compare the written inventory against the expected item list, then verify hashes
- ❌ Do not use `ls`, `cat`, or `grep` multi-line output as the only proof of file enumeration or content completeness
- ❌ `wc -l` alone never proves completeness: it counts lines, not required sections, content, or hashes

#### 6b. `write_file` Large Payload Timeout / Partial Write
Large `write_file` payloads may time out mid-write. Treat a timeout as an **unknown write state**, not a committed success or a guaranteed failure.
- ✅ Write ONE logical document per operation; never concatenate multiple documents into one payload
- ✅ Compute expected size and SHA-256 independently BEFORE the final write, from the intended payload or the source manifest; never compute the acceptance hash from the file after writing and call that verification
- ✅ If the full expected hash cannot be precomputed (for example, streaming/assembled content), maintain a chunk ledger with `chunk_id`, `offset`, `expected_size`, and per-chunk `hash`, and still validate the assembled file against every required section
- ✅ For genuinely large documents, use bounded chunking: build content in chunks, write append-mode or merge with an idempotent retry that can safely resume
- ✅ After a timeout, check the target first: if it already matches the expected hash, treat it as complete and do NOT rewrite; if it does not match, replace the whole file atomically or restore ONLY the missing/corrupt chunks
- ✅ After each write, verify the file exists, matches the independently precomputed expected SHA-256, and contains every required section
- ✅ Retry idempotently and ONLY the failed item/chunk; do not restart the whole batch, and do not rewrite successfully verified files
- ❌ Do not batch-write several documents in one call just because the total is under some guessed line/token ceiling
- ❌ Do not blindly append-and-retry the same content; an append retry over an already partially written file can duplicate chunks
- ❌ Do not declare a document complete from a success-looking tool response alone without content verification

#### 6c. Delegation / Subagent Timeouts
Delegated content-generation batches may time out silently (compilation, summary writing). Prefer local single-document writes for the actual file creation; use subagents only for bounded research, code generation, or light inspection.
- ✅ On timeout, enumerate which items are still missing from the manifest and retry only those
- ✅ Validate every delegated result the same way as local output: presence, hash, required sections
- ❌ Do not rely on subagents for bulk summary generation when local writes plus structured validation are available

#### 6d. Counting Files Under Truncation
When you need to confirm N files exist but multi-line output may truncate:
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
Pair the count with the manifest and per-file SHA-256; the count alone is a signal, not proof.

---

## Output-Safe Large-Batch Protocol

Use this protocol for every large compilation batch. It generalizes the truncated-output and large-write cases above.

### Mandatory rules
- **exit 0 is not complete evidence**: a tool call can exit successfully while returning truncated output or failing to persist content; always verify the artifact, not the response text
- **One logical document per write**: each summary/navigation/report file is written by its own operation; never concatenate multiple documents into one payload
- **Bounded chunking with idempotent retry**: if a single document is too large for one write, split it at stable boundaries, append/merge deterministically, and make retries safe to resume
- **Retry only failed pieces**: verify each item against the manifest and required sections before considering it done; a timeout retries the missing or corrupt item only
- **Manifest + hash + required-section verification**: record expected path, size, and SHA-256 from the intended payload or source manifest BEFORE the final write lands; after writing, check the file exists, matches that independently computed hash, and contains every required section (`摘要`, `要点`, `实体`, `概念`, `原文摘录` for summaries). If precomputation is impossible, use a chunk ledger with `chunk_id`, `offset`, `expected_size`, and per-chunk `hash` plus required-section validation
- **Byte-capped or structured single-line summaries**: prefer `head -c` capping, `python3 -c` state checks, and one-line counts over parsing long multi-line shell output
- **`wc -l` is never proof**: line counts supplement manifest/hash/section verification; they cannot prove completeness
- **Timeout recovery**: after any timeout, inspect the target first; matching expected hash means done, non-matching means atomic replacement or restoring only the missing/corrupt chunks, never blind append retries

### Machine-Verifiable Evidence (Preferred)

`scripts/verify_output_batch.py` is the preferred verification entrypoint for batch output. It reads a small expected JSON manifest and checks each file under `--root` for existence, byte size, SHA-256, and required sections. The manual protocol above remains the fallback when the script or a compatible manifest is unavailable.

```bash
python3 scripts/verify_output_batch.py \
  --manifest expected-manifest.json \
  --root /path/to/agent-kb \
  --max-samples 10
```

Exit codes: `0` = every item verified; `1` = artifact mismatch; `2` = manifest/usage error. stdout is exactly one compact JSON line with `ok`, `expected`/`verified` counts, per-category error counts, and bounded samples (default 10, `--max-samples`). File content and secrets are never printed. Relative paths must stay under `--root`; duplicate paths, non-64-hex SHA-256 values, and unknown manifest fields are rejected as manifest errors.

Minimal manifest schema:

```json
{
  "schema_version": "1",
  "files": [
    {
      "path": "wiki/summaries/knowledge/Game-Theory-01-0001.md",
      "expected_size": 2048,
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "required_sections": ["摘要", "要点", "实体", "概念", "原文摘录"]
    }
  ]
}
```

Expected `size`/`sha256` are computed independently from the intended payload or source manifest before the final write; the verifier never derives the acceptance hash from the written file.

### Closeout checklist
1. `scripts/verify_output_batch.py` exits 0 against the expected manifest; the manifest lists every expected item and the actual item count matches
2. Every written file matches the independently precomputed expected SHA-256 (or a verified chunk ledger plus required sections)
3. Every summary contains all required sections
4. Lint three zero-metrics remain zero
5. Git status shows exactly the intended files; unrelated user changes are untouched
6. Only then commit, push, and report completion
