#!/usr/bin/env python3
"""Extract ALL SI002 content"""

from docx import Document
from pathlib import Path

doc_path = Path(__file__).parent.parent / "SI002 - SII Document Request - Triad - V1.0.docx"
doc = Document(str(doc_path))

paras = [p for p in doc.paragraphs if p.text.strip()]

# Find main content start
main_idx = next(i for i, p in enumerate(paras) if 'You may qualify' in p.text)
closing_idx = next(i for i, p in enumerate(paras) if 'Sincerely' in p.text or 'You may obtain' in p.text)

print(f"Total paragraphs: {len(paras)}")
print(f"Main content starts at: {main_idx}")
print(f"Closing starts at: {closing_idx}")
print(f"Content paragraphs: {closing_idx - main_idx}\n")

# Extract ALL content paragraphs
content_paras = []
for i, p in enumerate(paras[main_idx:closing_idx+5]):
    text = p.text.strip()
    if text and len(text) > 2:
        # Skip pure metadata
        if not (text.startswith('[') and ']' in text and len(text) < 50):
            content_paras.append((i, text))

print(f"Found {len(content_paras)} content paragraphs\n")
print("=== ALL CONTENT ===")
for idx, text in content_paras:
    print(f"{idx+1}. {text[:250]}")

