# Word/PDF → Canonical HTML Formatter

A web app that converts DOCX and PDF into your canonical HTML using a unified, style-driven pipeline. Deployed on Vercel with Python functions for DOCX and a client-first PDF path.

## Features

- Drag & drop DOCX or PDF
- Real-time preview and HTML code tabs
- One-click copy
- Unified Intermediate Representation (IR) for DOCX/PDF
- Client PDF (pdf.js) with server fallback (pdfminer.six)
- Exact wording preservation

## Getting Started (Local)

1. Serve the repo (e.g., `npx serve .`) so the browser can fetch examples and API routes.
2. Open `index.html` and drop a `.docx` or `.pdf`.
3. DOCX is processed by `/api/process-doc.py` into IR; PDF uses pdf.js client extractor.
4. The renderer outputs canonical HTML.

## Snapshot Tests (Manual)

- Open `tests/snapshots/index.html` while serving the repo.
- Select a sample and click “Load Expected HTML”.
- Upload the matching input DOCX/PDF.
- The page renders and compares normalized DOM against the expected HTML.

## Vercel

- Functions: `api/process-doc.py`, `api/process-pdf.py`
- Runtime: Python 3.11 (configured in `vercel.json`)
- Dependencies: `requirements.txt` (`python-docx`, `pdfminer.six`)

## Project Structure

```
NcFormatter/
├── index.html
├── styles.css
├── script-new.js         # UI + IR + PDF client + parser + renderer
├── api/
│   ├── process-doc.py    # DOCX → IR
│   └── process-pdf.py    # PDF → IR (fallback)
├── style-map.json        # Style mapping (paragraph/table classes)
├── tests/snapshots/      # Browser-based snapshot harness
├── vercel.json
└── requirements.txt
```

## Notes

- OCR is not enabled by default; PDF aims for exact text extraction. You can extend fallback to OCR later if needed.
- The UI remains lightweight; letter-specific logic is removed in favor of style-based rules.
