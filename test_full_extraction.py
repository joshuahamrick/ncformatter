"""Full end-to-end test with the updated color filtering"""
import sys
sys.path.insert(0, 'api')

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
import re
import io

doc_path = r"C:\Users\jhamrick\Downloads\CA030 - CA Initial Contact - VCI - V1.0.docx"

def extract_paragraph_formatting(paragraph):
    """Extract paragraph with updated color filtering that preserves template vars"""
    
    para_data = {
        'text': '',
        'alignment': 'left',
        'fontSize': None,
        'bold': False,
        'underline': False,
        'italic': False,
        'runs': []
    }
    
    # Get paragraph alignment
    alignment = paragraph.paragraph_format.alignment
    if alignment:
        if alignment == WD_ALIGN_PARAGRAPH.CENTER:
            para_data['alignment'] = 'center'
        elif alignment == WD_ALIGN_PARAGRAPH.RIGHT:
            para_data['alignment'] = 'right'
        elif alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
            para_data['alignment'] = 'justify'
    
    # Process each run with new filtering
    full_text = ''
    for run in paragraph.runs:
        skip_run = False
        
        # Check if this run contains template variables
        has_template_var = False
        run_text = run.text
        if run_text:
            if re.search(r'(\{\[[\w\.]+\]\}|\[\[[\w\.]+\]\]|\{\{[\w\.]+\}\})', run_text):
                has_template_var = True
        
        # Only filter by color if NOT a template variable
        if not has_template_var:
            try:
                if run.font.color and run.font.color.rgb:
                    rgb = run.font.color.rgb
                    r, g, b = rgb[0], rgb[1], rgb[2]
                    if not (r < 50 and g < 50 and b < 50):
                        skip_run = True
                
                if hasattr(run.font, 'highlight_color') and run.font.highlight_color:
                    skip_run = True
            except:
                pass
        
        if skip_run:
            continue
        
        run_data = {
            'text': run.text,
            'bold': run.bold,
            'underline': run.underline,
            'italic': run.italic,
            'fontSize': None
        }
        
        if run.font.size:
            run_data['fontSize'] = str(int(run.font.size.pt)) + 'pt'
        
        para_data['runs'].append(run_data)
        full_text += run.text
    
    para_data['text'] = full_text
    
    return para_data

# Load document
doc = Document(doc_path)

print("EXTRACTING WITH UPDATED COLOR FILTERING:\n")
print("="*80)

extracted = []
for idx, para in enumerate(doc.paragraphs):
    para_data = extract_paragraph_formatting(para)
    if para_data['text'].strip():
        extracted.append(para_data)
        print(f"[{idx:3d}] {para_data['text'][:100]}")

print("\n" + "="*80)
print(f"TOTAL EXTRACTED: {len(extracted)} paragraphs")
print("="*80)

# Check for key content
print("\nKEY CONTENT CHECK:")
all_text = '\n'.join([p['text'] for p in extracted])

checks = [
    ("RE:", "RE: label found"),
    ("Loan Number", "Loan Number label found"),
    ("{[M594]}", "M594 variable found"),
    ("{[M567]}", "M567 variable found"),
    ("CompanyLongName", "CompanyLongName found"),
    ("CompanyReturnAddr", "CompanyReturnAddr found"),
    ("FEDERAL LAW", "FEDERAL LAW notice found"),
    ("SPOCContactPhone", "SPOCContactPhone found")
]

for phrase, desc in checks:
    if phrase in all_text:
        print(f"  [OK] {desc}")
    else:
        print(f"  [MISSING] {desc}")
