#!/usr/bin/env python3
"""Extract full SI002 content"""

from docx import Document
from pathlib import Path

doc_path = Path(__file__).parent.parent / "SI002 - SII Document Request - Triad - V1.0.docx"
doc = Document(str(doc_path))

paras = [p for p in doc.paragraphs if p.text.strip()]

# Find main content start
main_idx = next(i for i, p in enumerate(paras) if 'You may qualify' in p.text)
closing_idx = next(i for i, p in enumerate(paras) if 'Sincerely' in p.text or 'You may obtain' in p.text)

print("=== HEADER SECTION ===")
for i, p in enumerate(paras[:20]):
    text = p.text.strip()
    if not text.startswith('[') and not '(see' in text and not '(If [' in text and not '(OR' in text:
        print(f"{i+1}. {text[:150]}")

print("\n=== MAIN CONTENT ===")
for i, p in enumerate(paras[main_idx:main_idx+100]):
    text = p.text.strip()
    if text and len(text) > 5:
        print(f"{i+1}. {text[:200]}")

print("\n=== CLOSING SECTION ===")
for i, p in enumerate(paras[closing_idx-5:closing_idx+5]):
    text = p.text.strip()
    if text:
        print(f"{i+1}. {text[:200]}")

