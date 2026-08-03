---
name: boe-paper-download
description: Download Bank of England Quarterly Bulletin PDFs and academic papers from BoE website
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  category: knowledge-management
  tags: [BoE, download, PDF, academic, monetary-economics]
---

# Bank of England Paper Download Guide

## Key Finding (2026-04-19)
BoE restructured their website around 2020. **Individual article PDF URLs are broken** (404). But the full Quarterly Bulletin issue PDFs still work.

## Working URL Pattern
Full Quarterly Bulletin issue:
```
https://www.bankofengland.co.uk/-/media/boe/files/quarterly-bulletin/{YEAR}/quarterly-bulletin-{YEAR}-q{QUARTER}.pdf
```

Example (2014 Q1, 114 pages, 1.6MB):
```
https://www.bankofengland.co.uk/-/media/boe/files/quarterly-bulletin/2014/quarterly-bulletin-2014-q1.pdf
```

## Broken URL Patterns (do NOT use)
```
# These all return 404 or redirect to HTML error pages:
/-/media/boe/files/quarterly-bulletin/{YEAR}/{article-slug}.pdf
/publications/Documents/quarterlybulletin/{YEAR}/{filename}.pdf
```

## Download Command
```bash
curl -sL "https://www.bankofengland.co.uk/-/media/boe/files/quarterly-bulletin/2014/quarterly-bulletin-2014-q1.pdf" \
  -o /path/to/output.pdf
```

## Extracting Individual Articles from Full Issue
Use pdfplumber to identify article boundaries by page headers, then extract specific page ranges:

```python
import pdfplumber
with pdfplumber.open('quarterly-bulletin-2014-q1.pdf') as pdf:
    # Find article boundaries by searching for titles in page text
    for i, page in enumerate(pdf.pages):
        text = (page.extract_text() or '')[:300]
        if 'Article Title Here' in text:
            print(f'Starts at page {i+1}')
```

## Money Creation Papers (2014 Q1)
The famous BoE money creation series is in QB 2014 Q1:
1. "Money in the modern economy: an introduction" (pages 6-15)
2. "Money creation in the modern economy" (pages 17-29)
3. "The information content of different types of money and monetary aggregates" (embedded box, pages 22-26)

## Other Sources
- Internet Archive has limited BoE papers (search "bank of england quarterly bulletin")
- SSRN blocks direct downloads (403)
- BoE old URL structure CDX search in Wayback Machine returns no results for these papers

## Pitfalls
- Internet Archive download URLs may return HTML instead of PDF (test with `file` command)
- `textutil` fails on BoE PDFs (encoding issue); use `pdfplumber` instead
- Some BoE papers require accepting cookies/terms; add `-L` flag to curl for redirects
