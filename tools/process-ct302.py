#!/usr/bin/env python3
"""
Process CT302 document and generate HTML template
"""
import sys
import os
import json
import importlib.util

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from docx import Document

# Load process-doc module dynamically
process_doc_path = os.path.join(os.path.dirname(__file__), '..', 'api', 'process-doc.py')
spec = importlib.util.spec_from_file_location("process_doc", process_doc_path)
process_doc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_doc)

_build_ir_document = process_doc._build_ir_document

def process_ct302():
    """Process CT302 document"""
    doc_path = os.path.join(os.path.dirname(__file__), '..', 'CT302 - CT Compliance Mailing - MSF - V1.0 (1).docx')
    
    if not os.path.exists(doc_path):
        print(f"Error: Document not found at {doc_path}")
        return
    
    print(f"Loading document: {doc_path}")
    doc = Document(doc_path)
    
    print("Extracting IR...")
    ir = _build_ir_document(doc)
    
    print(f"IR extracted: {len(ir.get('blocks', []))} content blocks")
    
    # Save the IR for inspection
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'formatter examples', 'CT302')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'CT302-ir.json')
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(ir, f, indent=2, ensure_ascii=False)
    
    print(f"IR saved to: {output_path}")
    print(f"\nDocument has {len(ir.get('blocks', []))} blocks")
    
    if len(ir.get('blocks', [])) == 0:
        print("WARNING: No blocks extracted. This might indicate an issue with the document structure.")
    else:
        print("\nTo generate the HTML template:")
        print("1. Use the web interface (deployed on Vercel or locally)")
        print("2. Upload the CT302 document")
        print("3. The AI will generate the formatted HTML template")
    
    return ir

if __name__ == '__main__':
    process_ct302()

