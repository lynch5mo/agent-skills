# Scene Unit Contract

A film scene is one playable unit of continuous screen time and place.

It must have:

- one location and time condition;
- one immediate dramatic objective;
- one active conflict or pressure;
- one turn, reveal, decision, or changed state by the end.

Do not use a scene file as a sequence bucket. If the text moves from room to street to factory, or from morning to night, split it into separate scene candidates and group them in `outline/` or `ai-workspace/reports/`.

Allowed inside `scenes/`:

- one scene card per playable scene;
- design notes above `## 剧本正文`;
- one screenplay body for that scene after `## 剧本正文`.

Not allowed inside one `## 剧本正文`:

- multiple `INT.` / `EXT.` / `内景` / `外景` scene headings;
- numbered markdown sub-beats such as `### 12.1`;
- sequence reports, tables, or analysis text.
