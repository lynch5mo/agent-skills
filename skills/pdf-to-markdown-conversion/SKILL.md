---
name: pdf-to-markdown-conversion
description: Convert PDF documents to Markdown format with image extraction using pymupdf4llm and pymupdf. Preserves text content and extracts images to a companion _files directory. Handles both English and Chinese PDFs.
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  tags: [pdf, markdown, pymupdf, image-extraction, knowledge-base, conversion]
---

# PDF to Markdown Conversion

Convert PDF documents to Markdown format with image extraction. This approach preserves text content and creates a companion `_files` directory with extracted images.

## When to Use

- Converting PDF files to Markdown for knowledge base ingestion
- When you need to extract both text AND images from PDFs
- When working with documents that contain charts, graphs, or diagrams
- When PDF files need to be imported into systems that support Markdown (like Obsidian, Hugo, etc.)

## Prerequisites

```bash
pip3 install pymupdf pymupdf4llm
```

## Approach

This solution uses a two-stage process:

1. **Text Conversion**: Use `pymupdf4llm.to_markdown()` to extract text and basic structure
2. **Image Extraction**: Manually extract images using `pymupdf` and replace placeholder markers with actual image links

**Why this approach?**
- `pymupdf4llm.to_markdown()` is fast and produces good text quality but marks complex vector graphics as "intentionally omitted"
- Manual image extraction ensures all actual image files are preserved and properly linked
- Vector graphics may still be omitted, but raster images (charts, photos) are captured

## Implementation

```python
import pymupdf4llm
import pymupdf
from pathlib import Path
import re

def convert_pdf_to_markdown(pdf_path, output_md_path, output_files_dir=None):
    """
    Convert PDF to Markdown with image extraction.

    Args:
        pdf_path: Path to the input PDF file
        output_md_path: Path where the Markdown file should be saved
        output_files_dir: Directory to save extracted images (optional, creates _files by default)

    Returns:
        Number of images extracted
    """
    # Create images directory if not specified
    if output_files_dir:
        Path(output_files_dir).mkdir(parents=True, exist_ok=True)
    else:
        # Default to same name as markdown file but with _files suffix
        md_path = Path(output_md_path)
        output_files_dir = str(md_path.parent / f"{md_path.stem}_files")
        Path(output_files_dir).mkdir(parents=True, exist_ok=True)

    # Convert PDF to Markdown using pymupdf4llm
    md_text = pymupdf4llm.to_markdown(pdf_path)

    # Extract all images manually
    doc = pymupdf.open(pdf_path)
    extracted_images = []

    for page_index, page in enumerate(doc):
        # Get all images on this page
        image_list = page.get_images(full=True)

        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)

            # Extract image bytes and extension
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            # Save image
            image_filename = f"page{page_index}_img{img_index}.{image_ext}"
            image_path = f"{output_files_dir}/{image_filename}"
            with open(image_path, "wb") as img_file:
                img_file.write(image_bytes)

            # Record image info
            extracted_images.append({
                "filename": image_filename,
                "width": img[2],
                "height": img[3],
                "page": page_index
            })

    doc.close()

    # Replace "picture intentionally omitted" markers with actual image links
    lines = md_text.split('\n')
    img_counter = 0

    for i, line in enumerate(lines):
        if '==>' in line and 'intentionally omitted' in line:
            # Match pattern: "==> picture [width x height] intentionally omitted <=="
            match = re.search(r'==> picture \[(\d+) x (\d+)\] intentionally omitted <==', line)
            if match and img_counter < len(extracted_images):
                img = extracted_images[img_counter]
                image_filename = img["filename"]
                files_dir_name = Path(output_files_dir).name

                # Replace with actual image link
                new_line = f'![图表 {img_counter + 1}]({files_dir_name}/{image_filename})'
                lines[i] = new_line
                img_counter += 1

    # Write Markdown file
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(lines))

    return len(extracted_images)


# Example usage
gmn_pdf = "path/to/GMN1.pdf"
gmn_md = "path/to/GMN1.md"
gmn_files = "path/to/GMN1_files"

img_count = convert_pdf_to_markdown(gmn_pdf, gmn_md, gmn_files)
print(f"Extracted {img_count} images to {gmn_files}")
print(f"Markdown saved to {gmn_md}")
```

## Batch Processing Multiple PDFs

```python
from pathlib import Path

def batch_convert_pdfs(source_dir, output_dir=None):
    """
    Convert all PDFs in a directory to Markdown format.
    """
    source_path = Path(source_dir)
    if not output_dir:
        output_dir = source_dir

    pdf_files = list(source_path.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files")

    for pdf_file in pdf_files:
        # Generate output paths
        md_name = pdf_file.stem + ".md"
        files_dir = pdf_file.stem + "_files"

        md_path = Path(output_dir) / md_name
        files_path = Path(output_dir) / files_dir

        print(f"Converting {pdf_file.name}...")
        try:
            img_count = convert_pdf_to_markdown(
                str(pdf_file),
                str(md_path),
                str(files_path)
            )
            print(f"  ✓ Extracted {img_count} images")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print("Batch conversion complete!")

# Example
batch_convert_pdfs("raw/inbox/智堡主站付费文章", "raw/inbox/智堡主站付费文章")
```

## Limitations and Pitfalls

### 1. Vector Graphics May Be Omitted
- **Issue**: Complex vector graphics (SVG-style diagrams, line drawings, charts drawn with shapes) are often marked as "intentionally omitted" by `pymupdf4llm`
- **Impact**: You'll lose visual charts that are drawn as vector graphics, not raster images
- **Workaround**:
  - Use `marker-pdf` (requires ~3-5GB) for better OCR and vector handling
  - Accept that vector graphics may be lost but text content is preserved
  - Take screenshots manually for critical charts

### 2. Image Ordering
- The replacement logic assumes markers appear in the same order as extracted images
- This usually works but may fail for complex layouts
- **Check**: Always verify a few converted files before batch processing

### 3. File Paths
- Image links use relative paths (`directory/filename.png`)
- When moving Markdown files, also move the `_files` directory
- Keep the Markdown and its `_files` directory together

### 4. Encoding
- Always use UTF-8 encoding when writing Markdown files
- This handles both English and Chinese content correctly

### 5. Duplicate Files
- When re-running conversion, the script will overwrite existing files
- Delete old Markdown and `_files` directories before re-converting if you want a clean start

## Alternative: marker-pdf (High-Fidelity Layout Preservation)

If vector graphics preservation is critical, use `marker-pdf`. Full workflow is documented in `references/marker-pdf-workflow.md` (absorbed from the archived `pdf-to-markdown-high-fidelity-conversion` skill).

```bash
pip3 install marker-pdf marker-pdf# Requires ~3.5GB model download on first run
marker /path/to/input/folder --output_dir /path/to/output --output_format markdown --disable_ocr
```

**Pros:**
- Best layout preservation (tables, figures, vector graphics)
- OCR for scanned PDFs
- Extracts both raster and vector images

**Cons:**
- Requires ~3-5GB disk space for models
- Slow (~0.1 pages/second on CPU)
- Requires folder input (not single file)

## Tool Comparison

| Tool | Use Case | Layout Fidelity | Vector Graphics | Speed | Disk |
|------|----------|----------------|-----------------|-------|------|
| pymupdf4llm | Simple text-heavy PDFs | ⭐⭐ | ❌ | ⭐⭐⭐⭐⭐ | ~50MB |
| marker-pdf | Reports with charts, complex layouts | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ~3-5GB |
| pdftotext | Ultra-fast text-only | ⭐ | ❌ | ⭐⭐⭐⭐⭐ | n/a |
| MarkItDown (MS) | LLM text extraction only | ⭐⭐ | ❌ (no images at all) | ⭐⭐⭐⭐⭐ | ~100MB |

A full tool evaluation report with decision tree is available at `references/pdf-conversion-tool-evaluation.md` (absorbed from the archived `pdf-to-markdown-evaluation` skill).

## Decision Tree

```
User needs PDF → Markdown
├─ Need to preserve images/charts?
│  ├─ YES → Use marker-pdf (best fidelity)
│  │  └─ Satisfied? → batch convert
│  │  └─ Not satisfied → consider dual-track (below)
│  └─ NO → Use pymupdf4llm (fastest)
│
└─ What's the real goal?
   ├─ Preserve original doc → keep PDF, don't convert
   ├─ Extract knowledge → dual-track (PDF + MD summary)
   └─ Other → reassess requirements
```

## Troubleshooting

### No images extracted
- Check if PDF contains actual raster images vs vector graphics
- Vector graphics won't be extracted as image files
- Use `pymupdf` directly to inspect page structure

### Images not appearing in Markdown
- Verify image files exist in `_files` directory
- Check that Markdown links reference correct filenames
- Ensure relative paths are correct

### Encoding errors with Chinese content
- Always use `encoding="utf-8"` when writing files
- pymupdf4llm should handle Chinese text automatically
- If issues occur, check PDF's internal encoding

### Empty Markdown output
- PDF may be scanned (image-based) rather than text-based
- Requires OCR (Tesseract) or use marker-pdf with OCR enabled
- Check if `pymupdf4llm.to_markdown()` returns meaningful text

## Related Skills

- `agent-kb-concept-extraction-ingest`: For extracting concepts from converted content
- `agent-kb-add-file-format-support`: For extending ingestion systems
