#!/usr/bin/env python3
import sys
import os
import json
import importlib.util
from docx import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

process_doc_path = os.path.join(os.path.dirname(__file__), '..', 'api', 'process-doc.py')
spec = importlib.util.spec_from_file_location("process_doc", process_doc_path)
process_doc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_doc)

doc_path = os.path.join(os.path.dirname(__file__), '..', 'LM158 - HUD FB Disaster Off Ltr - Keesler - V2.0.docx')
doc = Document(doc_path)
ir = process_doc._build_ir_document(doc)

print(f"Extracted {len(ir.get('blocks', []))} blocks\n")
print("=" * 80)
print("DOCUMENT CONTENT:")
print("=" * 80)

for i, block in enumerate(ir.get('blocks', [])[:50]):  # First 50 blocks
    if block.get('type') == 'paragraph':
        text = ''.join([run.get('text', '') for run in block.get('runs', [])]).strip()
        if text:
            print(f"Para {i+1}: {text[:200]}")
    elif block.get('type') == 'table':
        print(f"Table {i+1}: {len(block.get('rows', []))} rows")
