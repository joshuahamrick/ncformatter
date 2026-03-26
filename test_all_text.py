"""Check if all document content is being read - look for ANY text after Sincerely"""
import sys
sys.path.insert(0, 'api')

from docx import Document

doc_path = r"C:\Users\jhamrick\Downloads\CA030 - CA Initial Contact - VCI - V1.0.docx"
doc = Document(doc_path)

print("COMPLETE DOCUMENT TEXT (no filtering):\n")
print("=" * 80)

all_text = []
for p_idx, para in enumerate(doc.paragraphs):
    if para.text.strip():
        all_text.append(f"[{p_idx:3d}] {para.text}")

# Print all text
for line in all_text:
    print(line)
    print()

print("\n" + "=" * 80)
print(f"TOTAL NON-EMPTY PARAGRAPHS: {len(all_text)}")
print("=" * 80)

# Check for key phrases in ALL text (no filtering)
combined_text = "\n".join(all_text)
key_phrases = ["RE:", "Loan Number", "M594", "M567", "CompanyLongName", "CompanyReturnAddr", 
               "SPOCContactPhone", "FEDERAL LAW", "DEBT COLLECTOR", "BANKRUPTCY"]

print("\nSEARCHING IN RAW TEXT:")
for phrase in key_phrases:
    if phrase in combined_text:
        print(f"FOUND: {phrase}")
    else:
        print(f"NOT FOUND: {phrase}")
