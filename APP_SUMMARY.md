# NcFormatter: Quick Summary

## What It Does
Converts Word documents to production-ready HTML, reducing formatting time by **60-80%**.

## How It Works
1. **Upload** → Drag & drop Word document
2. **Extract** → Python parses document structure (IR)
3. **Transform** → JavaScript applies formatting rules
4. **Output** → Standardized HTML with placeholders and functions

## Key Technologies
- **Frontend**: Vanilla JavaScript, HTML5/CSS3
- **Backend**: Python 3.11 (Vercel serverless)
- **Libraries**: python-docx, pdf.js
- **Architecture**: IR pattern (extraction → transformation → rendering)

## Core Features
- ✅ Universal rules (works for any document)
- ✅ Dynamic font/header detection
- ✅ Placeholder normalization (`#TAG#` → `{[TAG]}`)
- ✅ Table structure recognition
- ✅ Math/Date expression formatting
- ✅ Conditional block wrapping

## Business Value
- **60-80% time reduction** for letter formatting
- **Standardized output** reduces errors
- **Frees programmers** for higher-value work
- **Scales** to any document type

## Technical Highlights
- **IR Pattern**: Clean separation between extraction and rendering
- **Universal Rules**: No document-specific code
- **Serverless**: Cost-effective, scalable deployment
- **Snapshot Testing**: Ensures quality and catches regressions

## Usage
1. Open `index.html`
2. Drag Word document
3. Copy HTML output
4. Paste into NcConnect

