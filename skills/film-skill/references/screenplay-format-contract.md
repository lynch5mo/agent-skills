# Screenplay Format Contract

Use this contract for draft text in `scenes/`, `rewrite-candidates/`, `versions/`, and `exports/`.

The body after `## 剧本正文` is screenplay text, not analysis.

Default format is the user's Scrivener-exported Chinese screenplay format.

There are two output modes:

- `reading_print`: normal reading/print draft, without scene numbers.
- `shooting_print`: production/shooting draft, with scene numbers at the left of scene headings.

Only shooting drafts carry scene numbers. Do not add scene numbers to normal print drafts unless the task asks for a shooting/production draft.

Required shape for normal print draft:

```text
内  地点  日

可被镜头看见或听见的动作。

                人物名
        对白。

                人物名
        （必要时的括注）
        继续对白。
```

Required shape for shooting draft:

```text
12  内  地点  日

可被镜头看见或听见的动作。

                人物名（身份）
        对白。
```

Rules:

- Use exactly one scene heading per scene body.
- Scene heading may use Chinese or English interior/exterior markers. Both `内` / `外` / `内景` / `外景` and `INT.` / `EXT.` / `INT/EXT.` are acceptable.
- Scene heading must contain interior/exterior, location, and time. Time may be `日` / `夜` / `夜晚` or equivalent.
- Scene heading parts must be visibly separated in source: use at least 4 half-width spaces or 2 full-width spaces between interior/exterior, location, and time, for example `外    城市十字路口    日`.
- Scene heading must start at the left action margin. In PDF export it must render in bold Heiti/blackface.
- Scene numbers are optional only in `shooting_print`; they are forbidden by default in `reading_print`.
- Action lines describe visible or audible behavior in present tense.
- Action lines start at the left action margin.
- Dialogue is a centered dialogue block, visually distinct from action. In Markdown source, preserve this with indentation: character cue lines use at least 16 leading spaces; dialogue and parenthetical lines use at least 8 leading spaces.
- Dialogue uses a standalone character cue line, then dialogue on following lines.
- Character cue lines must be visually closer to the page center than action text. In PDF export they must render in bold Heiti/blackface.
- Character cue, optional parenthetical, and dialogue must be consecutive lines. Do not insert blank lines inside a dialogue block.
- Do not write `角色：对白` in draft text.
- Do not put markdown headings, beat tables, scene analysis, or comments inside draft text.
- Put craft notes, goals, and beat plans above `## 剧本正文` or in `ai-workspace/reports/`.
- Use only single blank lines between action paragraphs or dialogue blocks. Do not use repeated blank lines to fake scene spacing; scene-to-scene spacing is handled by Longform/PDF export.
