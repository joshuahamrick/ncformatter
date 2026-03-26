# NcFormatter — Technical Overview

**For:** CTO / Technical Leadership
**Purpose:** Understand the system well enough to evaluate, extend, or rebuild it.

---

## What It Does

NcFormatter is an internal web tool that converts Word `.docx` letter templates into production-ready HTML for NcConnect, New Course Communications' loan servicing platform. Mortgage operations staff upload a template; the system returns formatted, copy-paste-ready HTML — complete with NcConnect variable placeholders, conditional logic, and table structures — in seconds.

**Bottom line:** What used to take a developer 2–4 hours of hand-coding per letter template now takes under a minute.

---

## How It Works — The Pipeline

```
.docx Upload
     │
     ▼
[1] Word Extraction (Python / python-docx)
     │  Parses runs, tables, styles, headers
     │  Accepts all tracked changes automatically
     │  Blocks real PII before anything leaves the server
     ▼
[2] Intermediate Representation (IR) — JSON
     │  Structured, format-agnostic description of the document
     ▼
[3] AI HTML Generation (Claude Sonnet via Anthropic API)
     │  System prompt encodes NcConnect formatting rules
     │  6 curated few-shot examples guide output style
     │  Returns valid NcConnect HTML
     ▼
[4] Browser Display
     │  Preview tab + raw HTML tab
     │  Optional: chat-based refinement (Claude patches the HTML)
     ▼
User copies HTML → pastes into NcConnect
```

---

## Architecture

| Layer | Technology | Role |
|---|---|---|
| Frontend | Vanilla JS (ES6+), HTML5, CSS3 | Single-page UI — upload, preview, copy |
| Backend | Python 3.11 serverless (Vercel) | Document extraction + AI orchestration |
| AI | Anthropic Claude (Sonnet) | IR → formatted HTML generation |
| Document parsing | `python-docx`, `pdfminer.six` | Word and PDF extraction |
| Deployment | Vercel (serverless, zero-ops) | Auto-deploys `api/` as Python functions |

No database. No auth layer. No build step. The only secret is `ANTHROPIC_API_KEY`.

---

## Key Files

```
NcFormatter/
├── index.html                  # The entire UI
├── script-new.js               # All browser logic (~3,500 lines, one class)
├── styles.css                  # UI styling
│
├── api/
│   ├── process-doc.py          # POST: .docx → IR JSON
│   ├── process-pdf.py          # POST: PDF → IR JSON
│   ├── generate-template.py    # POST: IR JSON → HTML (Claude call)
│   ├── patch-template.py       # POST: HTML + instruction → patched HTML (chat)
│   ├── pii_scanner.py          # Shared PII detection logic
│   └── health.py               # GET: library availability check
│
├── ai/
│   ├── prompts/system-prompt.txt   # Claude's formatting rulebook
│   └── style-guide.md              # Human-readable NcConnect HTML rules
│
├── formatter examples/         # ~35 document types, each with gold-standard HTML
└── tests/snapshots/            # Regression test harness (browser + CLI)
```

---

## The AI Layer in Detail

The core intelligence lives in two places:

1. **System Prompt** (`ai/prompts/system-prompt.txt`) — Teaches Claude the NcConnect HTML dialect: variable syntax (`{[TAG]}`), company prefix matrix (`{[plsMatrix.CompanyLongName]}`), conditional blocks (`{If(...)}...{End If}`), table patterns, date/math helpers, and spacing rules.

2. **Few-Shot Examples** — On every request, `generate-template.py` loads 6 real gold-standard formatted letters and sends them alongside the IR. Claude learns "by example" what correct output looks like for different letter types.

The **chat refinement** feature (`patch-template.py`) lets users describe a correction in plain English ("make the table two columns," "add a blank line before the signature block") — Claude receives the current HTML + chat history and returns an updated version.

---

## PII Safety

Enforced at three independent layers so real customer data can never reach the Claude API:

1. **Client-side JS** — scans the file before upload
2. **Server-side Python** (`pii_scanner.py`) — scans the extracted IR; returns HTTP 403 if triggered
3. **UI warning banner** — policy notice always visible to users

---

## Document Coverage

~35 mortgage servicing letter types across loss mitigation (LM), breach (BR), denial (DS), compliance (CT), PMI (MI), welcome (WL), customer service (CS), and more — all in the `formatter examples/` folder with expected HTML outputs that serve as both reference and regression tests.

---

## What It Would Take to Rebuild or Extend

**To rebuild from scratch, you need:**
- A Python serverless backend (Vercel works well; AWS Lambda or GCP Functions are equivalent)
- `python-docx` for Word extraction (mature, well-documented)
- An LLM API (Claude Sonnet is the sweet spot for instruction-following structured output; GPT-4o is a viable alternative)
- A well-crafted system prompt that encodes your target HTML dialect — *this is the hardest part and where the domain knowledge lives*
- A library of few-shot examples in your target format — quality matters more than quantity

**To extend this codebase:**
- The extraction pipeline (`process-doc.py`) is modular — new document quirks can be handled by expanding the IR schema
- New letter types are supported automatically once they're uploaded; no code changes needed for new document codes
- The system prompt can be versioned and iterated independently of the app code
- Snapshot tests in `tests/snapshots/` provide a regression safety net when the prompt or extractor changes

---

## Recommendation

Starting from this codebase is the faster path. The extraction logic, PII policy layer, AI orchestration pattern, and ~35 gold-standard examples represent months of iteration. The hardest parts — getting the prompt right, handling edge cases in Word XML, and building the example library — are already done.

The codebase is lean (~4,000 lines of JS, ~1,200 lines of Python across all API files), well-separated by concern, and runs at near-zero infrastructure cost on Vercel's free/hobby tier for internal tool usage levels.
