#!/usr/bin/env python3
"""Get actual text content from LM158 document"""
import sys
import os
from docx import Document

doc_path = os.path.join(os.path.dirname(__file__), '..', 'LM158 - HUD FB Disaster Off Ltr - Keesler - V2.0.docx')
doc = Document(doc_path)

print("DOCUMENT CONTENT:\n")
for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()
    if text and not text.startswith('[') and 'Company Address' not in text and 'System Date' not in text:
        # Check if it's actual content (not variable definitions)
        if len(text) > 10:  # Skip short variable labels
            print(f"{i}: {text[:300]}")
