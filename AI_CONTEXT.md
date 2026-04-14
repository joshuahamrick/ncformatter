# AI Context for NcFormatter

This document provides context for the AI-driven HTML template generation system.

## Overview

The AI system generates HTML templates from Word document structure (IR format) by learning from curated examples and following a strict style guide.

## Key Components

### 1. Style Guide (`ai/style-guide.md`)
Comprehensive formatting rules covering:
- Variable placeholders (`{[TAG]}` format)
- Helper functions (`Money()`, `Compress()`, `DateAdd()`, etc.)
- Table structures
- Conditional logic syntax
- Common patterns (property addresses, salutations, etc.)

### 2. System Prompt (`ai/prompts/system-prompt.txt`)
Core instructions for the AI model, emphasizing:
- Exact formatting requirements
- Variable naming conventions
- Structure consistency
- Output format (pure HTML only)

### 3. Few-Shot Examples
Curated examples from `formatter examples/`:
- GB001: Transfer letters with tables
- ES114: Simple subject + property letters
- CA001: Welcome letters with bullet lists
- CA003: ACH confirmations with conditionals
- LM401: Complex tables + conditionals

### 4. API Endpoints

#### `/api/process-doc.py`
- Input: `{ fileData, fileName, includeLayoutPdf? }` — optional `includeLayoutPdf: true` requests DOCX→PDF after the PII gate (see `api/docx_to_pdf.py`: LibreOffice `soffice` on `PATH` or `SOFFICE_PATH`, or Word + pywin32 on Windows). Response may include `layoutPdfBase64` or `layoutPdfError` without blocking `ir`. When PDF succeeds, `api/layout_raster.py` may add `layoutPngBase64` (page 1 for vision) or `layoutPngError` if `pypdfium2`/Pillow are missing or raster fails.

#### `/api/generate-template.py`
- Input: `{ ir, docMeta, optionalChatHistory, optionalUserInstruction, layoutPngBase64? }` — optional PNG (same as `process-doc` output) enables multimodal layout hints in Claude.
- Output: `{ html, notes }`
- Generates initial HTML template from IR

#### `/api/patch-template.py`
- Input: `{ currentHtml, instruction, ir }`
- Output: `{ html }`
- Applies user-specified changes to existing HTML

### 5. Normalization (`ai/normalize-html.js`)
Ensures deterministic output for exact snapshot matching:
- Normalizes whitespace
- Standardizes `<br>` tags
- Normalizes conditional block formatting
- Handles table attribute ordering

## Usage

### Setting Up OpenAI API Key
Set environment variable:
```bash
export OPENAI_API_KEY=your_key_here
```

### Generating Templates
1. Drop a Word document in the UI
2. System extracts IR structure
3. AI generates HTML template
4. Output is normalized and displayed

### Making Adjustments
1. Use the chat panel on the right
2. Describe the change needed
3. Click "Apply Change" or press Ctrl+Enter
4. AI regenerates HTML with the change

### Resetting
Click "Reset" button to return to initial AI-generated output.

## Determinism

- Temperature set to 0 for consistent outputs
- HTML normalization ensures exact matching
- Fixed prompt templates
- Few-shot examples provide stable patterns

## Testing

Use `tools/snapshot-ai-runner.js` to:
- Compare AI-generated HTML against expected snapshots
- Identify differences
- Track accuracy over time

## Cost Considerations

- OpenAI API calls cost per token
- Caching recommended for repeated documents
- Few-shot examples add to prompt size but improve quality

## Future Improvements

- Add caching layer (by file hash + instruction hash)
- Expand few-shot examples
- Add confidence scoring
- Support for more document types
- Batch processing capabilities
