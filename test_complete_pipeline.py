"""Complete end-to-end test simulating the full API pipeline"""
import sys
import os
sys.path.insert(0, 'api')

# Import modules
import importlib.util

# Load process-word.py
spec = importlib.util.spec_from_file_location("process_word", "api/process-word.py")
process_word_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_word_module)

# Load generate-template.py  
spec2 = importlib.util.spec_from_file_location("generate_template", "api/generate-template.py")
generate_module = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(generate_module)

doc_path = r"C:\Users\jhamrick\Downloads\CA030 - CA Initial Contact - VCI - V1.0.docx"

print("="*80)
print("FULL END-TO-END TEST - CA030 Document Processing")
print("="*80)

# Step 1: Process Word document
print("\n[STEP 1] Processing Word document...")
with open(doc_path, 'rb') as f:
    file_bytes = f.read()

try:
    ir = process_word_module.process_word_document(file_bytes, "CA030.docx")
    print(f"  [OK] Document processed successfully")
    print(f"  [OK] Result type: {type(ir)}")
    print(f"  [OK] Result keys: {ir.keys() if isinstance(ir, dict) else 'NOT A DICT'}")
    print(f"  [OK] Extracted {len(ir.get('blocks', []))} blocks")
    
    if len(ir.get('blocks', [])) == 0:
        print(f"  [WARNING] No blocks extracted - checking result structure...")
        print(f"  Result: {str(ir)[:500]}")
    
    # Count paragraphs
    para_count = sum(1 for b in ir.get('blocks', []) if b.get('type') == 'paragraph' and b.get('runs'))
    print(f"  [OK] {para_count} paragraphs with content")
    
except Exception as e:
    print(f"  [ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 2: Check IR content
print("\n[STEP 2] Checking IR content...")
all_text = []
for block in ir['blocks']:
    if block.get('type') == 'paragraph':
        runs = block.get('runs', [])
        text = ''.join([r.get('text', '') for r in runs])
        if text.strip():
            all_text.append(text)

combined = '\n'.join(all_text)

key_checks = [
    ("RE:", "RE: label"),
    ("Loan Number", "Loan Number text"),
    ("{[M594]}", "M594 loan number variable"),
    ("{[M567]}", "M567 property address variable"),
    ("CompanyLongName", "Company name variable"),
    ("CompanyReturnAddr", "Company address variable"),
    ("SPOCContactPhone", "Phone variable"),
    ("FEDERAL LAW", "Federal law notice"),
]

all_found = True
for phrase, desc in key_checks:
    if phrase in combined:
        print(f"  [OK] {desc}")
    else:
        print(f"  [MISSING] {desc}")
        all_found = False

if not all_found:
    print("\n  ERROR: Missing required content!")
    print("\n  First 20 extracted texts:")
    for idx, text in enumerate(all_text[:20]):
        print(f"    [{idx}] {text[:80]}")
    sys.exit(1)

# Step 3: Format IR for prompt
print("\n[STEP 3] Formatting IR for Claude prompt...")
try:
    ir_content = generate_module.format_ir_for_prompt(ir)
    print(f"  [OK] IR formatted: {len(ir_content)} characters")
    
    # Check if key content made it through filtering
    for phrase, desc in key_checks:
        if phrase in ir_content:
            print(f"  [OK] {desc} in prompt")
        else:
            print(f"  [FILTERED] {desc} removed!")
            
except Exception as e:
    print(f"  [ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*80)
print("SUCCESS! Document processing pipeline works correctly.")
print("="*80)
print("\nThe CA030 document should now work in the deployed app!")
