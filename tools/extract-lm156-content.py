#!/usr/bin/env python3
"""Extract content from LM156 document"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from docx import Document

doc = Document('LM156 - GSE FB Plan Ofr Ltr - Keesler - V2.0.docx')

print("=== DOCUMENT CONTENT ===\n")
for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()
    if text and len(text) > 5:
        print(f"Para {i}: {text[:200]}")
