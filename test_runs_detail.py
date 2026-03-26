"""Check what text is actually in each run near the M594 area"""
import sys
sys.path.insert(0, 'api')

from docx import Document

doc_path = r"C:\Users\jhamrick\Downloads\CA030 - CA Initial Contact - VCI - V1.0.docx"
doc = Document(doc_path)

print("CHECKING RUNS IN PARAGRAPHS 0-155 (looking for keywords):\n")

for p_idx in range(155):
    para = doc.paragraphs[p_idx]
    if len(para.runs) > 0:
        # Combine all run text
        full_text = ''.join([r.text for r in para.runs])
        
        # Check if this paragraph contains interesting keywords
        if any(word in full_text for word in ["RE:", "Loan", "M594", "M567", "Property", "Company", "FEDERAL"]):
            print(f"\n{'='*80}")
            print(f"PARAGRAPH {p_idx}: '{full_text[:100]}'")
            print(f"Total runs: {len(para.runs)}")
            print(f"{'='*80}")
            
            for r_idx, run in enumerate(para.runs[:10]):  # First 10 runs
                # Check color
                color_info = "BLACK"
                try:
                    if run.font.color and run.font.color.rgb:
                        rgb = run.font.color.rgb
                        color_info = f"RGB({rgb[0]},{rgb[1]},{rgb[2]})"
                except:
                    color_info = "NO_RGB"
                
                print(f"  Run {r_idx:2d} [{color_info:15s}]: '{run.text}'")
