#!/usr/bin/env python3
"""Process LM156 document using the process_word_document function"""

import sys
import os
import base64

# Add api directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

# Import the processing function
from process_word import process_word_document

def main():
    docx_path = "LM156 - GSE Suspended FB Plan - Flat Branch - V5.0.docx"
    
    if not os.path.exists(docx_path):
        print(f"Error: File not found: {docx_path}")
        return
    
    # Read the document
    with open(docx_path, 'rb') as f:
        file_bytes = f.read()
    
    # Process the document
    print(f"Processing {docx_path}...")
    result = process_word_document(file_bytes, docx_path)
    
    if result['success']:
        # Write the formatted HTML
        output_path = "formatter examples/LM156/LM156-formatted.html"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result['formattedHtml'])
        
        print(f"✓ Successfully processed document")
        print(f"✓ Output written to: {output_path}")
        print(f"✓ Document type: {result.get('documentType', 'unknown')}")
    else:
        print(f"✗ Error processing document: {result.get('error', 'Unknown error')}")

if __name__ == '__main__':
    main()
