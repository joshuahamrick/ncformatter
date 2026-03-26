#!/usr/bin/env python3
"""Process LM156 document locally"""

import sys
import os
import importlib.util

# Read the document
docx_path = "LM156 - GSE Suspended FB Plan - Flat Branch - V5.0.docx"

if not os.path.exists(docx_path):
    print(f"Error: File not found: {docx_path}")
    sys.exit(1)

# Load the process-word module
spec = importlib.util.spec_from_file_location("process_word", "api/process-word.py")
process_word_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_word_module)

# Read the document
with open(docx_path, 'rb') as f:
    file_bytes = f.read()

# Process the document
print(f"Processing {docx_path}...")
result = process_word_module.process_word_document(file_bytes, docx_path)

if result['success']:
    # Write the formatted HTML
    output_path = "formatter examples/LM156/LM156-formatted.html"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result['formattedHtml'])
    
    print("Successfully processed document")
    print(f"Output written to: {output_path}")
    print(f"Document type: {result.get('documentType', 'unknown')}")
else:
    print(f"Error processing document: {result.get('error', 'Unknown error')}")
    sys.exit(1)
