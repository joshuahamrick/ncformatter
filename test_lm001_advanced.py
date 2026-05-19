#!/usr/bin/env python3
"""Test LM001 with Advanced mode (layout PNG passed to Claude)."""
import sys, os, importlib.util, json, io, base64

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

BASE = r'C:\Users\jhamrick\Desktop\NcFormatter'
API = os.path.join(BASE, 'api')

print('Loading modules...', flush=True)
for sub in ['pii_scanner', 'docx_to_pdf', 'layout_raster', 'anthropic_retry']:
    path = os.path.join(API, f'{sub}.py')
    if os.path.exists(path):
        try:
            load_module(f'api.{sub}', path)
            load_module(sub, path)
            print(f'  Loaded {sub}', flush=True)
        except Exception as e:
            print(f'  Warning: {sub}: {e}', flush=True)

process_doc = load_module('process_doc', os.path.join(API, 'process-doc.py'))
gen_tmpl    = load_module('gen_tmpl',    os.path.join(API, 'generate-template.py'))
dtop        = load_module('dtop',        os.path.join(API, 'docx_to_pdf.py'))
lr          = load_module('lr',          os.path.join(API, 'layout_raster.py'))
print('All modules loaded', flush=True)

from docx import Document
DOCX_PATH = r'K:\ncConnect\Letters\Triad\Letters\LM001\20231121\LM001 Loss Mit Acknowledgement Letter - Triad -V1.0.docx'
print('Loading docx...', flush=True)
with open(DOCX_PATH, 'rb') as f:
    file_bytes = f.read()

# Generate PDF and all-page PNGs (advanced mode)
print('Generating layout PDF/PNGs (all pages)...', flush=True)
pdf_bytes, pdf_err = dtop.try_convert_docx_to_pdf(file_bytes, 'LM001.docx')
layout_png_pages = []
if pdf_bytes:
    print(f'  PDF: {len(pdf_bytes)} bytes', flush=True)
    png_pages, pages_err = lr.try_pdf_all_pages_png_list(pdf_bytes)
    if png_pages:
        layout_png_pages = [base64.b64encode(p).decode('ascii') for p in png_pages]
        print(f'  Pages: {len(layout_png_pages)} PNGs ({sum(len(p) for p in png_pages):,} bytes total)', flush=True)
    else:
        print(f'  PNG pages error: {pages_err}', flush=True)
else:
    print(f'  PDF error: {pdf_err}', flush=True)

doc = Document(io.BytesIO(file_bytes))
print('\nBuilding IR...', flush=True)
ir = process_doc._build_ir_document(doc)
print(f'  IR: {len(ir["blocks"])} blocks', flush=True)

# Load API key
api_key = os.environ.get('ANTHROPIC_API_KEY')
if not api_key:
    env_path = os.path.join(BASE, '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('ANTHROPIC_API_KEY='):
                    api_key = line.split('=', 1)[1].strip().strip('"\'')
                    os.environ['ANTHROPIC_API_KEY'] = api_key

if not api_key:
    print('No ANTHROPIC_API_KEY - stopping')
    sys.exit(1)

import anthropic
client = anthropic.Anthropic(api_key=api_key)

few_shot_examples = gen_tmpl.load_few_shot_examples()
print(f'\nLoaded {len(few_shot_examples)} examples', flush=True)

system_prompt, user_message, few_shot_text = gen_tmpl.build_prompt(ir, few_shot_examples)
full_system = system_prompt + "\n\n" + few_shot_text

print(f'Calling Claude API (Advanced mode with layout image)...', flush=True)

ir_blocks = len(ir.get('blocks', []))
max_tokens = 8000 + 4000  # Extra for image

if layout_png_pages:
    n = len(layout_png_pages)
    layout_note = (
        f"The {n} image{'s' if n > 1 else ''} above show all {n} page{'s' if n > 1 else ''} of the source Word document as rendered (PDF raster). "
        "Use them to supplement the IR text below. Specifically, look for:\n"
        "  1. TABLE STRUCTURE — exact number of columns, visible borders (or no borders), column width proportions\n"
        "  2. INDENTATION — any section visually indented (approximate pixel offset → use padding-left or margin-left)\n"
        "  3. TAB STOPS — within a line, where text jumps horizontally after a bold label (use <span style=\"padding-left: 55px\"> for the indented portion)\n"
        "  4. TEXT ALIGNMENT — centered, left, justified per section\n"
        "  5. HORIZONTAL RULES — visible dividing lines between sections\n"
        "  6. SPACING — blank lines / extra whitespace between paragraphs or after the closing\n"
        "All wording and merge field variables MUST still come from the Document Content / IR text below. "
        "The images are visual reference only — do not invent text from them.\n\n"
    )
    user_blocks = []
    for idx, p in enumerate(layout_png_pages):
        user_blocks.append({"type": "text", "text": f"[Page {idx+1} of {n}]"})
        user_blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": p}})
    user_blocks.append({"type": "text", "text": layout_note + user_message})
    messages = [{"role": "user", "content": user_blocks}]
else:
    messages = [{"role": "user", "content": user_message}]

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=max_tokens,
    system=full_system,
    messages=messages,
    temperature=0,
)

html = response.content[0].text.strip()
if html.startswith('```html'):
    html = html.replace('```html', '').replace('```', '').strip()
elif html.startswith('```'):
    html = html.replace('```', '').strip()

html = gen_tmpl.normalize_html(html)

out_path = os.path.join(BASE, 'lm001_generated_advanced.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'\nAdvanced mode HTML saved: lm001_generated_advanced.html ({len(html)} chars)', flush=True)
print('\n--- ADVANCED GENERATED HTML ---', flush=True)
print(html, flush=True)
