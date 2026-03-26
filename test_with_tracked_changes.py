"""Test the tracked changes fix locally"""
import sys
import os
sys.path.insert(0, 'api')

# Import the function directly from the file
import importlib.util
spec = importlib.util.spec_from_file_location("process_word", "api/process-word.py")
process_word = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_word)

process_word_document = process_word.process_word_document

doc_path = r"C:\Users\jhamrick\Downloads\CA030 - CA Initial Contact - VCI - V1.0.docx"

# Read file
with open(doc_path, 'rb') as f:
    file_bytes = f.read()

# Process with new tracked changes handling
print("Processing document with tracked changes acceptance...\n")

try:
    result = process_word_document(file_bytes, "CA030.docx")
    
    blocks = result.get('blocks', [])
    print(f"Total blocks extracted: {len(blocks)}\n")
    
    # Show all blocks
    for idx, block in enumerate(blocks):
        if block.get('type') == 'paragraph':
            runs = block.get('runs', [])
            text = ''.join([r.get('text', '') for r in runs])
            if text.strip():
                print(f"[{idx:3d}] {text[:100]}")
    
    # Check for key content
    print("\n" + "="*80)
    print("KEY CONTENT CHECK:")
    print("="*80)
    
    all_text = '\n'.join([
        ''.join([r.get('text', '') for r in b.get('runs', [])])
        for b in blocks if b.get('type') == 'paragraph'
    ])
    
    checks = [
        ("RE:", "RE: label"),
        ("Loan Number", "Loan Number label"),
        ("{[M594]}", "M594 variable"),
        ("{[M567]}", "M567 variable"),  
        ("CompanyLongName", "CompanyLongName"),
        ("CompanyReturnAddr", "CompanyReturnAddr"),
        ("FEDERAL LAW", "FEDERAL LAW notice"),
        ("SPOCContactPhone", "SPOCContactPhone")
    ]
    
    for phrase, desc in checks:
        if phrase in all_text:
            print(f"  [OK] {desc}")
        else:
            print(f"  [MISSING] {desc}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
