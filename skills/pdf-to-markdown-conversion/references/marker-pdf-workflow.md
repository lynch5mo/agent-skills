# Marker-PDF Workflow (High-Fidelity Conversion)

*Archived from `pdf-to-markdown-high-fidelity-conversion`*

## Installation
```bash
pip3 install marker-pdf
pip3 install psutil
```

## Basic Usage
marker-pdf requires a folder input (not a single file):
```bash
mkdir -p /tmp/marker_input
cp "path/to/file.pdf" /tmp/marker_input/
marker /tmp/marker_input --output_dir /tmp/marker_output --output_format markdown --disable_ocr
```

## Expected Output
```
/tmp/marker_output/
└── filename/
    ├── filename.md                # Main Markdown
    ├── filename_meta.json         # Metadata
    ├── _page_1_Figure_0.jpeg
    └── ...                        # All extracted images
```

## Verify Conversion Quality
```bash
# Count images in PDF
python3 -c "import pymupdf; doc=pymupdf.open('file.pdf'); print(sum(len(p.get_images()) for p in doc))"

# Count images in Markdown output
grep -c '!\[\]' /tmp/marker_output/filename/filename.md
```

## Base64 Embedding for Sharing
When sending via Telegram where relative image paths break:
```python
import base64, os
with open('_page_1_Figure_0.jpeg', 'rb') as f:
    encoded = base64.b64encode(f.read()).decode('utf-8')
    print(f'![](data:image/jpeg;base64,{encoded})')
```

## Performance
- First run: downloads ~3.5GB of ML models (surya layout detection, table recognition, OCR)
- Conversion speed: ~0.1 pages/second on CPU
- macOS MPS warning on table recognition model → falls back to CPU (expected)

## Pitfalls
- **Folder input required** — cannot pass single PDF
- **Model download** — first run takes 10-30 minutes
- **OCR vs embedded text** — use `--disable_ocr` for text PDFs; remove for scanned PDFs
