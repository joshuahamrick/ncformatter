#!/usr/bin/env python3
"""Extract content from SI002 document"""

from docx import Document
from pathlib import Path

doc_path = Path(__file__).parent.parent / "SI002 - SII Document Request - Triad - V1.0.docx"
doc = Document(str(doc_path))

paras = [p for p in doc.paragraphs if p.text.strip()]

print(f"Total paragraphs: {len(paras)}\n")

# Find main content
main_start = None
for i, p in enumerate(paras):
    text = p.text.strip()
    if 'You may qualify' in text or 'successor in interest' in text.lower():
        main_start = i
        break

if main_start:
    print(f"Main content starts at paragraph {main_start+1}\n")
    print("First 30 content paragraphs:")
    for i, p in enumerate(paras[main_start:main_start+30]):
        print(f"{i+1}. {p.text[:200]}")

print("\n\nLooking for closing...")
for i, p in enumerate(paras[-50:]):
    text = p.text.strip()
    if any(word in text for word in ['Sincerely', 'Customer Service', 'Department', 'Thank you']):
        print(f"Paragraph {len(paras)-50+i+1}: {text[:200]}")

