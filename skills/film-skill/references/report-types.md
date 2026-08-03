# Report Types

## AI Report

Write reports to:

```text
ai-workspace/reports/
outputs/review/film/<project_id>/
```

Every report states:

- input scope
- unread scope
- findings
- recommendations
- rejected actions
- risks
- files changed

## Import and Analysis Reports

For `source_intake`, `outline_deconstruction`, `scene_breakdown`, `scene_unit_audit`, `scene_goal_build`, `screenplay_format_check`, `asset_build`, `draft_deconstruction`, `outline_seed`, `reference_script_analysis`, `technique_extraction`, or `classification_map`, every report also states:

- source identity and ownership/status;
- whether the source is user draft, user outline, or reference-only material;
- exact files read;
- extracted structure map;
- extracted character/conflict map when relevant;
- classification tags;
- what was not imported or not inferred.

For `scene_unit_audit` and `screenplay_format_check`, also state which scene files are valid, which must be split or reformatted, and whether the result is only a scene design artifact or accepted screenplay text.

## Draft and Revision Reports

For `draft_completion`, `revision_plan`, or `revision_iteration`, every report also states:

- approved framework used;
- scene breakdown version;
- asset files consulted;
- user constraints;
- draft/revision scope;
- what was changed or left unchanged;
- remaining questions for the user.

## Rewrite Candidate

Write candidate rewrites to:

```text
ai-workspace/rewrite-candidates/
```

Never write candidates directly into `scenes/`.

Required sections:

- input scene
- rewrite goal
- constraints
- candidate text
- change notes
- risk
- human adoption record
