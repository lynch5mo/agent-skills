# Permission Boundary

## Default Read

- `00_project.md`
- `agent-policy.md`
- `bible/`
- `outline/`
- `characters/`
- `scenes/`
- `clues/`
- `source-cards/`
- `conversations/`
- explicitly selected `related_notes`

## Source Intake Read

For old drafts, user outlines, PDF/DOCX extracts, or mature reference screenplays, read only exact paths named in the task card. Prefer a single file or one narrow folder under `raw/inbox/<batch-id>/`.

Do not read all projects, the whole vault, or broad `raw/` folders just because the task says "import".

## Default Write

- `ai-workspace/`
- `conversations/`
- `outputs/review/film/<project_id>/`

## Requires Explicit User Authorization

- bulk frontmatter updates
- export generation
- version snapshots
- modifying source scenes
- applying candidate drafts into `scenes/`
- moving from asset construction to full screenplay drafting
- applying a revision plan to source text

## Forbidden By Default

- overwrite `scenes/`
- delete files
- rename project files
- write directly to `wiki/`
- read other `FILM-*` projects by default
- package the whole vault for a cloud model
- send whole third-party/reference scripts to cloud models by default
- treat reference scripts as the user's own draft
