---
name: large-doc-chapter-split
description: Split a large merged Markdown documentation file into navigable chapter files with TOC, cross-links, and clean headings. Handles Mintlify zero-width space artifacts.
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  category: knowledge-management
---

# Large Document Chapter Splitter

Split a massive merged Markdown file (e.g., 9MB+ documentation manual) into manageable chapter-sized files suitable for Obsidian or similar editors.

## When to Use
- Combined documentation file crashes Obsidian or other editors
- Need to split by logical chapters/sections
- Source docs came from Mintlify or similar SSR sites with `[​ ](#anchor)` artifacts

## Steps

### 1. Identify Chapter Boundaries
Scan for level-1 headings (`# Title`) to find chapter breaks. Define chapter mapping:
```python
CHAPTERS = [
    {"file": "prefix-chapter-name.md", "title": "Chapter Title",
     "dirs": ["source-dir/"], "files": ["top-level-file.md"]},
    ...
]
```

### 2. Build Chapter Files
For each chapter:
- Collect all source files from directories and explicit file lists
- Generate a clickable TOC with anchor links
- Adjust heading levels: content H1→H2, H2→H3 (leave room for chapter title as H1)
- Add `<a id="anchor"></a>` before each section for deep linking
- Add navigation links to prev/next chapters at top and bottom

### 3. Clean Mintlify Artifacts (CRITICAL)
Mintlify generates invisible zero-width space characters in anchor syntax:

**Pattern:** `[[\u200b ](#anchor) 中文标题](#target)` or `## [​ ](#anchor) 标题`

**Fix (3 passes needed):**
```python
# Pass 1: TOC entries — [[​ ](#anchor) title](#target) → [title](#target)
content = re.sub(r'\[\[\u200b\s*\]\(#[^)]*\)\s*([^\]]+)\]', r'[\1]', content)

# Pass 2: Heading lines — ## [​ ](#anchor) title → ## title
content = re.sub(r'^(#{1,6}\s+)\[\u200b\s*\]\(#[^)]*\)\s*', r'\1', content, flags=re.MULTILINE)

# Pass 3: Inline remnants
content = re.sub(r'\[\u200b\s*\]\(#[^)]*\)', '', content)
```

⚠️ **Common pitfall**: Using `'[​]'` literal string won't match — must use `\u200b` in regex because the character is U+200B (zero-width space), not a regular space.

### 4. Transform Cross-Chapter Links
Convert inter-page links to reference the correct chapter file:
```python
# /zh-CN/concepts/agent → openclaw-核心概念.md#agent
def transform_link(url):
    for prefix, chapter_file in CHAPTER_MAP.items():
        if url.startswith(prefix):
            anchor = url.rstrip('.md').split('/')[-1]
            return f'{chapter_file}#{anchor}'
```

### 5. Verify
- Check zero remaining `\u200b` characters: `grep -c '\[\u200b' file.md` should return 0
- Check file sizes are Obsidian-safe (target <400KB each)
- Verify TOC anchor links match section anchors

## Output Format
Each chapter file:
```markdown
# Chapter Title

> Manual Name · Chapter N/M

← Previous: [Prev Title](prev.md) | Next: [Next Title](next.md)

## 目录
  - [Section 1](#section-1)
  - [Section 2](#section-2)

---
<a id="section-1"></a>
## Section 1
...content...

---
<a id="section-2"></a>
## Section 2
...content...

---
*Source: https://... | Generated: YYYY-MM-DD*
```

## Pitfalls
- `\u200b` zero-width space is INVISIBLE in editors — always verify with `repr()` or hex dump
- Regex `'[​]'` in Python source is treated as two separate characters; use `\u200b` escape
- Heading level adjustment must happen BEFORE TOC generation to avoid mismatched anchors
- Image paths remain relative to original directory, not chapter file location
