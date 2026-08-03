---
type: agent_policy
domain: film
project_id: FILM-TEMPLATE
project: 模板项目
updated_at: 2026-07-01
---

default_read:
  - 00_project.md
  - bible/
  - outline/
  - characters/
  - scenes/
  - clues/
  - source-cards/
  - ideas/
  - conversations/

default_write:
  - ai-workspace/
  - ideas/
  - conversations/
  - outputs/review/film/FILM-TEMPLATE/

requires_explicit_approval:
  - frontmatter_bulk_update
  - export_generation
  - version_snapshot

forbidden:
  - overwrite_scenes
  - delete_files
  - rename_project_files
  - write_wiki_directly
  - read_other_projects_by_default
