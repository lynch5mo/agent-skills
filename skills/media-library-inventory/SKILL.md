---
name: media-library-inventory
description: >-
  Scan, inventory, and analyze media (movie/video) file collections at scale.
  Covers: recursive file listing, video/sidecar classification, ReleaseGroup
  filename parsing, duplicate detection, cross-directory overlap analysis, and
  multi-report generation, and safe duplicate cleanup execution.
  1000s of entries.
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  tags: [media, video, inventory, scanning, movie-library, dedup, csv-generation]
  trigger: User asks to scan, inventory, audit, analyze, or catalog a media collection, find duplicates, check directory overlap, generate an inventory report, or execute a safe deduplication cleanup plan.
---

# Media Library Inventory Skill

## When to Use

- User requests a **movie/video library scan** or **inventory report**
- User wants to **find duplicates** across directories
- User wants to **check directory overlap** (e.g. US1 vs US2)
- User wants to **classify files** (video / sidecar / other) and **parse filenames**
- User wants a **multi-file report pack** (CSV/MD) for dedup planning

## Workflow

### 1. Define Scope

Identify the target root directory(ies) and subdirectory structure. Confirm the output directory path with the user.

**Convention:** create a dedicated output dir like `/Users/lynch5mo/Work Documents/LLM/<project-name>-<YYYYMMDD>/`.

### 2. Collect Raw File Listings (Phase 1)

Run `find` per top-level directory to produce a flat file list:

```bash
find /path/to/dir -type f > raw_dirname.txt
```

- Batch parallel `find` calls when multiple directories (use `terminal` sequentially or delegate).
- Use generous timeouts (300-600s) for SMB-mounted shares — they are slow.
- One `raw_*.txt` file per directory for traceability.

### 3. Extract File Sizes (Phase 2)

For each raw listing, batch-extract byte sizes:

```bash
> stats_dirname.txt
while IFS= read -r path; do
  size=$(stat -f%z "$path")
  echo "$path|$size" >> stats_dirname.txt
done < raw_dirname.txt
```

Output format per line: `relative/path|bytes`

### 4. Process with Python (Phase 3)

**DO NOT** use `read_file()` to load large stats files — the 6000-char safety limit will fail on files > 664 lines.

**Instead:** write a standalone `.py` script to the output directory and run it via `terminal()`.

The script must:

#### a. Load & Classify
```python
video_exts = {'.mkv', '.mp4', '.avi', '.m4v', '.mov', '.wmv', '.ts', '.m2ts', ...}
sidecar_exts = {'.srt', '.ass', '.ssa', '.idx', '.sub', '.nfo', '.jpg', '.png', ...}
```

#### b. Parse Filenames (ReleaseGroup convention)
Standard naming: `Title.Year.Quality.Source.Codec[-Edition]-Group`

Extract via regex:
- Resolution: `(2160p|1080p|720p|4K)`
- Source: `(BluRay|WEB-DL|WEBRip|HDTV|DVDRip|...)`
- Codec: `(x264|x265|H\.264|HEVC|AV1|...)`
- Year: `(19[0-9]{2}|20[0-2][0-9])`
- Edition: `(EXTENDED|DIRECTOR[_\s]*CUT|UNRATED|CRITERION|...)`
- Title: everything before the year when filename is dot-separated

#### c. Associate Sidecars to Videos
Match by: same directory + overlapping basename (prefix match for multi-file videos like CD1/CD2).

#### d. Generate 6 Output Reports

| # | File | Content |
|---|------|---------|
| 1 | `focused-inventory.csv` | All video files with parsed metadata |
| 2 | `sidecars-by-video.csv` | Video ↔ sidecar association table |
| 3 | `duplicate-name-candidates.csv` | Same parsed title in multiple locations |
| 4 | `us-directory-overlap.md` | Cross-directory overlap analysis (hardcoded for US dirs) |
| 5 | `misplaced-file-list.csv` | Anomalies: zero-byte, orphan sidecars, macOS metadata, small videos |
| 6 | `command-log.md` | Full scan summary, commands used, known gaps, next steps |

### 5. Deliver Results

- Report total file count, video/sidecar/other breakdown, total size.
- Flag key findings: duplicate titles, orphan sidecars, small videos.
- Offer to review specific reports (dedup candidates, overlap analysis).

### 6. Generate Decision Pack (Post-Scan Phase)

When the user already has scan CSVs (`focused-inventory.csv`, `sidecars-by-video.csv`, `misplaced-file-list.csv`, `duplicate-name-candidates.csv`) and wants cleanup recommendations, run the **decision pack** phase.

**Input:** CSVs from Phase 3
**Output:** 6 files in a dedicated output directory:

| # | File | Purpose |
|---|------|---------|
| 1 | `clean-main-videos.csv` | Videos passing all quality filters |
| 2 | `excluded-video-like-files.csv` | Every excluded entry with reason |
| 3 | `exact-duplicate-candidates.csv` | Groups where filename + size_bytes match (100% dups) |
| 4 | `version-upgrade-candidates.csv` | Same title+year with different quality levels |
| 5 | `cross-directory-overlap-clean.md` | Re-computed from cleaned data |
| 6 | `sidecar-risk-summary.md` | Exact vs fuzzy sidecar counts, misplaced categories |

**Key techniques:**

#### a. Two-tier Duplicate Detection

| Tier | Key | Meaning |
|------|-----|---------|
| **Exact duplicate** | `filename.lower()` + `size_bytes` | Same content — keep one copy |
| **Version upgrade** | `parsed_title.lower()` + `year` (int) | Different encodes — keep the best quality |

Edition variants (Director's Cut, Extended, Criterion) must be flagged for user review.

#### b. Quality Scoring Matrix

Score each video on resolution × source (0-90 scale):

| Resolution ↓ \ Source → | **Remux** | **BluRay** | **WEB-DL** | **WEB** | **HDTV** |
|---|---|---|---|---|---|
| **2160p / 4K** | 90 | 85 | 80 | 78 | 70 |
| **1080p** | 80 | 75 | 70 | 68 | 60 |
| **720p** | 70 | 65 | 60 | 58 | 50 |
| **SD / below** | 55 | 50 | 45 | — | 35 |

Gap < 10 between best and worst → flag for bitrate/audio/subtitle review instead of auto-deleting.

#### c. Apple Double (`._`) Detection

macOS Apple Double files (`._<name>`) have valid video extensions (.mkv) but are exactly 4096 bytes. Catch by `filename.startswith("._")` — extension alone is not enough. Exclude before any analysis.

#### d. Recompute Overlap from Cleaned Data

Always recompute cross-directory overlap after excluding `._` files, samples, and <500MB entries. Raw overlap includes false positives from small/metadata files sharing a parsed title.

#### e. Exclusion Filter Chain

1. Extension not in whitelist → `not_whitelisted_extension`
2. Filename starts with `._` → `apple_double_dot_underscore`
3. Path/filename contains `sample` → `sample_file`
4. Filename is `rarbg.com.mp4` etc. → `rarbg_com_metadata`
5. Size < 500MB → `too_small`
6. Size ≤ 0 → `zero_or_null_size`

### 7. Execute Cleanup Plan (Post-Decision)

When the user has an `exact-duplicate-candidates.csv` or `version-upgrade-candidates.csv` and wants to actually remove duplicates, run the **cleanup execution** phase.

**Input:** `exact-duplicate-candidates.csv` (or similar decision-pack output)
**Output:** 7 files in a dedicated ops directory

| # | File | Purpose |
|---|------|---------|
| 1 | `00-plan.md` | Full plan with candidate table, skip reasons |
| 2 | `move-plan.csv` | Machine-readable move list (priority, group id, source/keep/target paths) |
| 3 | `skipped.csv` | Candidates that failed pre-flight (with reason) |
| 4 | `rollback.sh` | Reversible `mv` commands (NO `rm` — safety first) |
| 5 | `verify-after.md` | Post-move verification report |
| 6 | `moved-manifest.csv` | Source→target mapping: group_id, old_path, new_path, keep_path, size_gb, moved_at, verified |
| 7 | `operation-log.md` | Chronological log: batches, timestamps, group IDs, sizes, verification status |

#### a. Filter Candidates

From the candidate list, select groups meeting ALL criteria:
- **Exact duplicate** (same category/directory depth, identical content)
- **Exactly one (1) copy** — the duplicate path contains `(1)` in its folder name (macOS folder naming convention for collisions)
- **Same category** — both original and duplicate sit in the same category directory

Filter out any candidate where `recommended_action != review_exact_duplicate` or context is unclear.

#### b. Generate Dry-Run Plan (Python Script)

Write a single Python script that:

1. Reads the candidate CSV (pipe `|` delimited, not comma)
2. For each candidate, resolves source path, keep path, and target path
3. **Pre-flight checks:**
   - Source exists (yes/no) — `test -d "source_path"`
   - Keep exists (yes/no) — `test -d "keep_path"` or `test -f "keep_path"`
   - Target doesn't already exist (yes/no)
   - Parent folder is a clean move unit (only 1 video file, no mixed content)
4. Determines **move unit**: prefer folder-level move over file-level move when folder exists
5. Generates `00-plan.md` (human-readable plan table)
6. Generates `move-plan.csv` (machine-readable with `priority,group_id,filename,size_gb,move_unit,source_rel_path,target_rel_path,keep_rel_path`)
7. Generates `moved-manifest.csv` (empty initially, with header: `group_id,old_path,new_path,keep_path,size_gb,moved_at,verified`) — filled after actual moves
8. Generates `operation-log.md` (initial entry with plan, expected groups, date) — appended after each batch
9. Generates `skipped.csv` (candidates failing pre-flight with reason)
10. Generates `rollback.sh` — bash script with `set -e`, `mkdir -p` for parent dirs, `mv` commands wrapped in `if [ -d ... ] || [ -f ... ]` guards, and **NO `rm` commands**

#### c. Conventions

- **Target isolation directory:** `_review/duplicates/OP-<date>-<batch-name>/` under the media root
- **Keep original relative path structure** at the target — same directory tree under the review dir
- **Priority ordering:** by file size descending (largest dup = highest priority)
- **Batch size:** move only first N groups (default 5) per batch, let user confirm before next batch
- **Phase A / Phase B separation:** When the user finds that existing records (e.g. moved-manifest.csv) have incorrect `new_path` values (wrong prefix, missing `_review/duplicates/OP-<id>/`), address Phase A (record correction) **before** Phase B (new moves). Run a dedicated script that reads each record, verifies the live filesystem state, and rewrites the column. Do NOT move new data until records are correct — mixing corrections and moves in one batch invites confusion.
- **new_path must NOT equal old_path:** The `new_path` column in moved-manifest.csv records where the file was moved TO — always `_review/duplicates/OP-<id>/<relative_path>`. If it matches `old_path`, the record is wrong. Correct by prepending the review prefix.
- **Record-keeping discipline:** Between batches, generate `moved-manifest.csv` (source→target mapping for ALL moved groups so far) and `operation-log.md` (chronological timeline with timestamps, group IDs, sizes, and verification status) before proceeding to the next batch. If the user notes records are missing, fill them from current file state before moving any new data.
- **rollback.sh must be safe to run even if nothing was moved** — the `[ -d ... ] || [ -f ... ]` guards handle this
- **rollback.sh header comment** must list which groups were actually moved vs which are guarded/skipped, e.g.: `# 已移动组：1,4,5,10,11,13,20,22,24,26\n# 未移动组（已跳过）：31,37,39,40,44`

#### d. Execute

After generating the plan and confirming with the user:

1. Create target base directory at `_review/duplicates/OP-<date>-<batch-name>/`
2. Create parent dirs at target (mirror relative path)
3. `mv` each source folder to target
4. Generate verification: check source GONE ✓, keep PRESERVE ✓, target MOVED ✓ for every moved group
5. **After each batch, update ALL records:**
   - Append moved groups to `moved-manifest.csv` with `moved_at` timestamp and `verified=yes`
   - Append a new section to `operation-log.md` with batch number, timestamps, group IDs, sizes, verification status
   - Update `verify-after.md` with cumulative totals (moved/total/skipped)
   - Update `rollback.sh` header comment to reflect which groups were actually moved vs guarded

**Multi-batch rule:** Never begin a subsequent batch without first ensuring ALL records from previous batches are complete and match the user's expectations. If the user asks for missing records, generate them from current file state (stat the actual filesystem) — do not move new data until the historical record is settled.

#### e. Rollback Safety

- rollback.sh ONLY contains `mv` commands — never `rm`
- Each mv is guarded by existence check: restore only if target exists
- Group-specific `mkdir -p` for parent dirs before restore
- User can run `bash rollback.sh` at any time to undo the batch
- **Header comment must be updated after each batch** to show exactly which groups were actually moved and which are guarded/skipped, so the user can tell at a glance what the script will do

## Template

See `templates/process_scan_template.py` for a complete, reusable Python script that performs Phases 3-5. Copy it, adjust the `DIR_PREFIX_MAP` and `BASE` paths, and run.

## Pitfalls

1. **`read_file` 6K safety limit** — Files > 6000 chars / ~664 lines cannot be read with `read_file()`. Always fall back to an on-disk Python script + `terminal()`.
2. **`extend([` needs `])`** — `list.extend([...])` requires two closing brackets. Missing `)` causes `SyntaxError: '(' was never closed`.
3. **`defaultdict` factory completeness** — If counting categories programmatically (`ds[category] += 1`), the factory dict must include ALL possible keys including `"other"`.
4. **SMB latency** — Large `find`/`stat` operations on network mounts may need 600s+ timeouts. Prefer one-shot `find` over iterative `ls`.
5. **Filename parsing accuracy** — Chinese-only titles, missing year, or non-standard naming (e.g. `movie.cd1.mkv`) will produce partial/incomplete parsed metadata.
6. **Duplicate detection is title-only** — No content hashing. Same movie with different naming (translated title vs original) won't match.
7. **Apple Double (`._`) files masquerade as video** — macOS `._` forks have valid video extensions (.mkv) and are exactly 4096 bytes. Check `filename.startswith("._")`, not just the extension. Exclude before any analysis.
8. **Two-tier duplicate detection is cleaner than one** — Separate exact duplicates (filename+size_bytes) from version upgrades (title+year). Exact dups are 100% waste; version upgrades need quality scoring to determine which to keep.
9. **Quality scoring must use resolution × source matrix** — A simple resolution-based ranking (4K > 1080p) is wrong: a 720p Remux (~70pts) can be better than a 1080p HDTV (~60pts). Use the 5×4 matrix described in Phase 6.
10. **Edition variants (Director's Cut, Extended, Criterion) must be flagged** — These can legitimately coexist on disk. Never auto-delete; always flag for user review.
11. **Recompute cross-directory overlap from the CLEANED set** — Raw overlap analysis includes Apple Double files, samples, and tiny files that share a parsed title with real videos, creating false positives.
12. **Zero-byte files and orphan sidecars** — Always flag these in `misplaced-file-list.csv` (or in the decision pack's excluded-video-like-files.csv) for manual review. A zero-byte file may be a failed download; an orphan sidecar has no matching video and may be leftover debris.
13. **Pre-flight is mandatory before any move** — Always check source exists, keep exists, target doesn't exist, and parent folder is a clean move unit (1 video file only). `mv` without pre-flight can silently orphan data.
14. **Rollback.sh must be generated BEFORE execution** — Generate it in the dry-run phase, not after. Include guards (`[ -d ... ] || [ -f ... ]`) so it's safe to run even if nothing was moved.
15. **Check CSV delimiter from the header line** — Different phases produce different delimiters. The decision pack's `exact-duplicate-candidates.csv` may use pipe `|`, while `move-plan.csv` uses comma. Always read the first line and split to determine the separator. Assuming the wrong delimiter silently produces one-field-per-row data corruption.
16. **Read CSV from disk, not from `read_file` truncation** — Use a Python script that reads the file directly. `read_file` truncates long lines (>6000 chars) silently, which corrupts row data.
17. **`moved-manifest.csv` and `operation-log.md` are mandatory output files, not optional** — The user expects a complete record of every move: source→target mapping (manifest) and chronological timeline (operation log). Generate them in the dry-run phase (even if empty) and append after each batch. Starting a new batch without these files complete will be flagged as missing documentation.
18. **Record-keeping must match current filesystem state** — When filling missing records mid-operation, stat the actual filesystem to determine what was moved. Do not assume or reconstruct from memory. Check source GONE / target PRESENT / keep PRESENT for each group.
19. **Rollback.sh header comment must reflect the actual moved set** — After each batch, update the header comment to list which groups were actually moved vs which are guarded/skipped. A stale comment (claiming all 16 groups can be restored when only 10 were moved) is misleading.
20. **CSV append via `echo` in shell can mangle newlines** — `echo "...\n..." >> file` in a shell may concatenate the first new row to the end of the previous line (newlines inside double-quoted strings are eaten by `sh`). Always use `write_file()` (for full rewrites) or a Python script (for incremental appends) when writing CSV rows from `execute_code`. Reserve `terminal()` echo for single-line writes only.
21. **Group IDs are often non-contiguous** — Don't assume sequential group IDs (e.g. 31,32,37,39,40,44). Gaps are expected from candidate filtering. Verify the intended group set with the user rather than filling gaps automatically.
22. **Final summary format — user-defined structured template** — After completing all batches, report in this exact format:
    ```
    **第三批安全去重完成。**
    **本批移动组数：** N
    **本批移动容量：** ~X.XX GB
    **累计移动组数：** N
    **累计隔离容量：** ~X.XX GB
    **跳过项：** 0
    **验证结果：** N/N
    **本 OP 是否完成：** 是
    **剩余不处理事项：**
    - 跨目录重复
    - 版本升级候选
    - sidecar/junk 清理
    ```
    Replace batch number and totals per the actual batch order. The "剩余不处理事项" list is constant across all exact-dup ops.
23. **skipped.csv must be empty at sign-off** — Before marking an OP complete, confirm `skipped.csv` exists and is header-only (no data rows). A non-empty skipped.csv means candidates were blocked — raise them with the user rather than silently reporting 0 skipped.
24. **verify-after.md must show cumulative totals across ALL batches** — The verification report is a rolling cumulative document. After each batch, update the summary table (total moved, total groups, skipped, failed) to reflect ALL batches, not just the current one. The per-group detail table appends new rows per batch.
25. **Rollback dest-exists guard prevents re-run corruption** — In `rollback_one()`, check BOTH that source (review path) exists AND that destination (original path) does NOT exist before restoring. This prevents overwriting a restored file if rollback.sh is run twice. Pattern:
    ```bash
    if [ ! -d "$src" ]; then echo "SKIP: source not found"; return 0; fi
    if [ -d "$dst" ]; then echo "SKIP: destination already exists"; return 0; fi
    mv "$src" "$dst"
    ```

## Supporting Files

- `templates/process_scan_template.py` — Reusable Python script for Phases 3-5
- `templates/generate_decision_pack.py` — Reusable Python script for Phase 6 (post-scan decision pack)
- `references/quality_scoring.md` — Resolution × source quality score matrix reference
