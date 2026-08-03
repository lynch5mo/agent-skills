# Project Contract

## Root

Use one directory per closed creative world:

```text
write/film/FILM-001-项目名/
```

Series films or multi-season shows belong inside one large `FILM-*` project under `works/`.

## Required Files

- `00_project.md`
- `agent-policy.md`

## Required Directories

- `bible/`
- `outline/`
- `characters/`
- `scenes/`
- `clues/`
- `source-cards/`
- `ideas/`
- `conversations/`
- `ai-workspace/tasks/`
- `ai-workspace/reports/`
- `ai-workspace/rewrite-candidates/`
- `versions/`
- `exports/`

## Object Types

- `project`
- `outline`
- `scene`
- `character`
- `clue`
- `source_card`
- `idea_note`
- `conversation_log`
- `ai_task`
- `ai_report`

Required common fields:

```yaml
type:
domain: film
project_id:
project:
updated_at:
```

## Scene Files

`scenes/S###_name.md` is one playable film scene, not a sequence bucket.

One scene means continuous screen time and place, one immediate dramatic objective, one conflict pressure, and one turn or changed state. A location/time jump creates a new scene unless it is a clearly marked montage handled outside source `scenes/`.

Scene design notes may live above `## 剧本正文`. The screenplay body itself must follow `screenplay-format-contract.md` and must not contain multiple scene headings, markdown beat headings, analysis tables, or `角色：对白` dialogue lines.

## Conversation Logs

`conversations/CONV-YYYYMMDD.md` stores the full visible chat content for all project-related Agent discussion on that local date. It is a project asset, not an AI report.

The conversation log must use `type: conversation_log`, include local `date`, `agents`, and `updated_at`, and preserve chronological transcript blocks before any summary or decision list. If a same-day file already exists, append a new time-block instead of creating a topic/session file.

## Ideas

`ideas/IDEA-YYYYMMDD-001-<slug>.md` stores substantial Agent ideas created during discussion: distilled points, creative directions, structural judgments, options, and open questions. It is separate from raw conversation logs, reports, proposals, and rewrite candidates.

The idea note must use `type: idea_note`, include `idea_id`, `idea_kind`, `status`, `source_conversation` when available, and `updated_at`.
