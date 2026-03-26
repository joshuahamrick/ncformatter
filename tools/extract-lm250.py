#!/usr/bin/env python3
"""Extract content from LM250 document"""
import sys
import os
import importlib.util
from docx import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

process_doc_path = os.path.join(os.path.dirname(__file__), '..', 'api', 'process-doc.py')
spec = importlib.util.spec_from_file_location("process_doc", process_doc_path)
process_doc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_doc)

doc_path = os.path.join(os.path.dirname(__file__), '..', 'LM250 - GSE RPP Offer CBRP - Keesler - V1.0.docx')
doc = Document(doc_path)
ir = process_doc._build_ir_document(doc)

print(f"Total blocks: {len(ir.get('blocks', []))}\n")
print("=" * 80)
print("DOCUMENT CONTENT:")
print("=" * 80)

for i, block in enumerate(ir.get('blocks', [])):
    if block.get('type') == 'paragraph':
        runs = block.get('runs', [])
        text = ''.join([r.get('text', '') for r in runs]).strip()
        if text:
            has_bold = any(r.get('bold', False) for r in runs)
            has_underline = any(r.get('underline', False) for r in runs)
            fmt = []
            if has_bold:
                fmt.append('BOLD')
            if has_underline:
                fmt.append('UNDERLINE')
            fmt_str = f" [{', '.join(fmt)}]" if fmt else ""
            try:
                print(f"{i+1:3d}: {text[:500]}{fmt_str}")
            except UnicodeEncodeError:
                print(f"{i+1:3d}: {text[:500].encode('ascii', 'ignore').decode('ascii')}{fmt_str}")
    elif block.get('type') == 'table':
        rows = block.get('rows', [])
        print(f"{i+1:3d}: TABLE with {len(rows)} rows")
