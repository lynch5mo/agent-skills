# Scene Audit and Format Test Protocol

Use this when the user asks for a format audit, scene-unit audit, or "test whether the format is right" before committing to a full rewrite.

## Format Testing (small-sample → prove → scale)

Do not rewrite the full screenplay to try a format rule. Use a 4-round incremental approach.

### Round 1: Room/indoor slow scene (baseline)

Select one indoor scene with 2–3 characters, slow pacing, dialogue-driven (e.g., Erjiu trying to take the baby in the room).

- Write a single sample into `rewrite-candidates/`.
- Run `screenplay_kb_check.py --project <project_id>`.
- If the sample appears in the error list, fix and re-test.
- Goal: zero errors on the first sample.

### Round 2: Apply format contract changes from Round 1 learnings

If the user requests a different format style (e.g., Scrivener Chinese vs. INT./EXT. English), rewrite the same scene content in the new format rather than picking a different scene.

### Round 3: Dialogue-block indentation

Test the same scene content again, this time enforcing dialogue-block indentation (character ≥12 spaces, dialogue/parenthetical ≥8 spaces, action flush left). This round specifically tests whether the middle block is visually distinct from the action margin.

### Round 4: Exterior action + multi-character alternating dialogue

Select an exterior scene with ≥3 characters trading dialogue quickly, action pressure, and a mid-scene turn. This is the highest-risk format scenario because multi-person alternating dialogue breaks the dialogue-block indentation pattern most easily.

Write a fresh sample. Run the checker. Zero errors = format proven for all scene types.

### Validation gate

Only proceed to full-scale scene-unit audit or rewrite after a Round 4 sample passes the project-level checker with zero errors.

## Scene Unit Audit (full-play audit)

When the user asks for "全片 scene_unit_audit" or "检查哪些需要拆分":

### Step 1: Read all scenes

Read `scenes/S001–S026` and the project outline. For each scene, extract:
- frontmatter `location` and `time`
- embedded scene headings in `## 剧本正文` (count `INT.` / `EXT.` / `内` / `外` header lines)
- presence of `###` Markdown sub-beats
- presence of `角色：对白` inline dialogue

### Step 2: Categorize each file into one of three buckets

| Category | Rule |
|----------|------|
| ✅ **可保留** | One continuous location + time, one dramatic unit. Only needs format cleanup (remove `###`, replace `角色：对白`, apply Scrivener indentation). |
| ⚠️ **需要确认** | Borderline cases. Typically: same general area but different specific spots; or INT→EXT transition that a single tracking shot could cover. Flag these for the user to decide. |
| 🔧 **必须拆分** | Two or more distinct locations + times in the body. Each embedded scene heading marks a new film scene that must become its own `scenes/` file. Also flag if the same file spans morning-to-night — that makes it impossible to be one continuous scene regardless of location. |

### Step 3: For each 必须拆分 file, produce a candidate list

Each candidate entry must include:

```
| Candidate ID | Suggested heading | Continuous time/location | Dramatic objective | Conflict/pressure | Ending turn | Split reason |
```

The candidate ID should use the parent file's number plus a letter suffix (e.g., `S012-A`, `S012-B`, `S012-C`).

### Step 4: Estimate final scene count

- 可保留 → 1 × count
- 需要确认 → 1–2 × count (mark range)
- 必须拆分 → sum of candidates

Typical result: 26 files → 40–45 standard film scenes.

### Step 5: Identify top structure problems

Find the 3–5 most severe issues that would affect the rewrite plan if left unaddressed. Common patterns:

- **时序错乱**: one file spans multiple time periods (morning → evening). Cannot be one scene.
- **场景桶式堆积**: one file crams 3–4 disconnected locations (bedroom → street → police station → return walk).
- **空间跳跃不标记**: characters move between rooms without a new scene heading.
- **蒙太奇未标记**: a travel or time-compression sequence written as ordinary action paragraphs instead of `MONTAGE`.
- **碎片化外景切换**: same event bounces between INT. and EXT. without proper scene breaks.

### Step 6: Run the project-level checker

```bash
python3 scripts/screenplay_kb_check.py --project <project_id>
```

Expected result: FAIL (old scenes are known to be non-compliant). Confirm in the report that newly written candidate samples do NOT appear in the error list.

## Report structure for an audit

1. Which files were read
2. Which files were NOT read (explicit)
3. Per-file verdict: 可保留 / 必须拆分 / 需要确认
4. Candidate split table for each 必须拆分 file
5. Top 3–5 structure problems
6. Checker result + explanation of expected FAIL
7. Recommendation: should the next step be "拆分候选生成"?

## Pitfalls

- Do not modify `scenes/` during an audit. All recommendations go into `ai-workspace/reports/`. Scene files are only rewritten after explicit user approval.
- The scene-unit-contract requires exactly one heading per scene body. If the body contains 2+ headings, the file MUST be split — no exception for "continuous action" if locations differ.
- When the frontmatter `location` field contains a range (e.g., "街头→游戏室→夜市"), treat this as a strong signal that the file contains multiple film scenes.
- The `sequence` field in frontmatter is the ordering key across scenes — candidate scenes from a split should use decimal sequence numbers (e.g., 012.1, 012.2, 012.3) or keep the original convention the project uses.
