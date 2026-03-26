"""Check what label text is actually extracted for the RE/Property row"""
import sys
import os
sys.path.insert(0, 'api')

# Import process-doc
import importlib.util
spec = importlib.util.spec_from_file_location("process_doc", "api/process-doc.py")
process_doc_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_doc_module)

doc_path = r"C:\Users\jhamrick\Downloads\CA030 - CA Initial Contact - VCI - V1.0.docx"

with open(doc_path, 'rb') as f:
    file_bytes = f.read()

# Process document
result = process_doc_module.handler.process_docx_file(file_bytes)
blocks = result.get('blocks', [])

print("EXTRACTED PARAGRAPHS (first 30):\n")

for idx, block in enumerate(blocks[:30]):
    if block.get('type') == 'paragraph':
        runs = block.get('runs', [])
        text = ''.join([r.get('text', '') for r in runs])
        if text.strip():
            print(f"[{idx:3d}] {text}")
