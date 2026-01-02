#!/usr/bin/env python3
"""Find bullet points in SI002"""

from docx import Document
from pathlib import Path

doc_path = Path(__file__).parent.parent / "SI002 - SII Document Request - Triad - V1.0.docx"
doc = Document(str(doc_path))

paras = [p for p in doc.paragraphs if p.text.strip()]

# Find patterns that indicate list items
list_patterns = []
for i, p in enumerate(paras):
    text = p.text.strip()
    
    # Check for "or" endings (common in lists)
    if text.endswith(' or') or text.endswith(' or.'):
        # Check if previous line is part of same list
        if i > 0:
            prev_text = paras[i-1].text.strip()
            if prev_text.endswith(' or') or prev_text.endswith(' or.'):
                list_patterns.append((i, text))
    
    # Check for list markers
    if text.startswith('•') or text.startswith('-') or text.startswith('*'):
        list_patterns.append((i, text))
    
    # Check for numbered items
    if re.match(r'^\d+\.', text):
        list_patterns.append((i, text))

print(f"Found {len(list_patterns)} potential list items")
for idx, (i, text) in enumerate(list_patterns[:30]):
    print(f"{idx+1}. Para {i}: {text[:100]}")

