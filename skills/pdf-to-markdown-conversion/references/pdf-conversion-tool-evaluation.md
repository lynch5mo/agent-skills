# PDF to Markdown Conversion Tool Evaluation

*Archived from `pdf-to-markdown-evaluation`*

## Tested Tools Summary

### pymupdf4llm
- **GitHub**: https://github.com/pymupdf4llm/pymupdf4llm
- **Speed**: Very fast
- **Images**: Only raster images extracted; vector graphics marked "intentionally omitted"
- **Test**: 12-page PDF with 11 images → only 1 extracted
- **Use**: Simple text-heavy PDFs only

### marker-pdf
- **GitHub**: https://github.com/VikParuchuri/marker
- **Speed**: Slow (~0.1 pages/sec on CPU)
- **Images**: Both raster and vector; good position preservation
- **Test**: 12 pages → 18 images extracted
- **Use**: Reports with charts, complex layouts
- **Cost**: ~3.5GB model download, ~3-5GB disk

### MarkItDown (Microsoft)
- **GitHub**: https://github.com/microsoft/markitdown
- **Speed**: Instant (<1s)
- **Images**: COMPLETELY FAILS — no image extraction at all
- **Design**: For LLM text consumption, NOT human-readable docs
- **Use**: Only for LLM text extraction; NOT for document preservation

### Other Candidates (quick-test tier)
- **pdfmd** (https://github.com/M1ck4/pdfmd) — explicit image support, Optimized for Obsidian
- **e2m** (https://github.com/wisupai/e2m) — multi-format, configurable
- **Pandoc** — universal converter, PDF→HTML→MD chain

## Key Insight: Dual-Track Strategy
Don't expect perfect PDF→MD conversion. Instead:
1. Keep PDF as the original archive (raw/)
2. Create MD as the knowledge extraction (wiki/summaries/)
3. The MD references back to the PDF for visual content
