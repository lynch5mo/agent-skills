# Agent Task Contract

Create task cards for project-level work:

```text
ai-workspace/tasks/AI-TASK-YYYYMMDD-<slug>.md
```

Required frontmatter:

```yaml
type: ai_task
domain: film
project_id:
task_id:
task_kind:
status: proposed
allowed_read_paths: []
allowed_write_paths: []
forbidden_paths: []
```

Allowed first-pass `task_kind` values:

- `source_intake`
- `outline_deconstruction`
- `scene_breakdown`
- `scene_unit_audit`
- `scene_goal_build`
- `screenplay_format_check`
- `asset_build`
- `draft_completion`
- `draft_deconstruction`
- `revision_plan`
- `revision_iteration`
- `reference_script_analysis`
- `technique_extraction`
- `classification_map`
- `outline_seed`
- `outline_check`
- `structure_check`
- `character_consistency`
- `clue_audit`
- `scene_summary`
- `rewrite_candidate`
- `metadata_check`
- `conversation_log`
- `project_closeout`

Do not start broad project scans without a task card or equivalent user-provided scope.

## Intake-Oriented Tasks

- `source_intake`: identify what the source is, where it lives, ownership/status, and what can be safely read.
- `outline_deconstruction`: split the user's outline into acts, sequences, scene candidates, dramatic questions, gaps, and asset needs.
- `scene_breakdown`: turn an approved outline or draft into scene cards or scene-map reports.
- `scene_unit_audit`: verify whether each proposed scene is one continuous film scene; split sequence-like chunks into separate scene candidates.
- `scene_goal_build`: define each scene's dramatic purpose, conflict, turn, character pressure, and output target.
- `screenplay_format_check`: verify draft text against standard screenplay format before it is treated as completed screenplay writing.
- `asset_build`: build character bios, background/world bible, clue maps, relationship maps, and reference source cards.
- `draft_completion`: draft scenes or a screenplay only inside a user-approved framework.
- `draft_deconstruction`: split the user's older draft into structure, scene, character, clue, and theme observations.
- `revision_plan`: propose changes after deconstructing an existing draft, before rewriting.
- `revision_iteration`: produce rewrite candidates or apply explicitly authorized revisions.
- `reference_script_analysis`: analyze a mature or third-party screenplay as reference material only.
- `technique_extraction`: extract reusable craft techniques from reference scripts without copying story assets.
- `classification_map`: categorize imported scripts or drafts by genre, structure, protagonist type, conflict engine, theme, and craft pattern.
- `outline_seed`: analyze a user-written outline and propose the first project structure without creating source scenes by default.
- `conversation_log`: save the current project-related Agent chat as a complete timestamped project asset under `conversations/`.

For imported source files, `allowed_read_paths` must name the exact file or folder. Do not use broad paths such as the whole vault, all `raw/`, or all `write/`.

## Approval Gates

- Before `draft_completion`: require approved scene breakdown, scene goals, and core assets.
- Before treating a scene file as screenplay text: require one scene unit per file and a passing screenplay format check.
- Before `revision_iteration`: require a revision plan accepted by the user.
- Before modifying `scenes/`: require explicit user authorization in the task card or current user instruction.
- Before learning from reference scripts: mark the task as `reference_script_analysis` or `technique_extraction`, not `draft_deconstruction`.
