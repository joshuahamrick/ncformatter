#!/usr/bin/env python3
"""
UNIVERSAL Document Extraction Tool
Usage: python tools/extract-document.py <path-to-docx-file>
Example: python tools/extract-document.py "LM250 - GSE RPP Offer CBRP - Keesler - V1.0.docx"

Extracts ALL formatting information from ANY Word document:
- BOLD, UNDERLINE, ITALIC
- FONT_SIZE (only non-default, i.e., not 11pt)
- ALIGNMENT (only non-left)
- Table structure
"""
import sys
import os
import importlib.util
from docx import Document

def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/extract-document.py <path-to-docx-file>")
        print("Example: python tools/extract-document.py \"LM250 - GSE RPP Offer CBRP - Keesler - V1.0.docx\"")
        sys.exit(1)
    
    doc_path = sys.argv[1]
    
    # If relative path, resolve from project root
    if not os.path.isabs(doc_path):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        doc_path = os.path.join(project_root, doc_path)
    
    if not os.path.exists(doc_path):
        print(f"Error: File not found: {doc_path}")
        sys.exit(1)
    
    # Load process-doc module
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    process_doc_path = os.path.join(os.path.dirname(__file__), '..', 'api', 'process-doc.py')
    spec = importlib.util.spec_from_file_location("process_doc", process_doc_path)
    process_doc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(process_doc)
    
    # Load document and build IR
    print(f"Extracting: {os.path.basename(doc_path)}")
    print("=" * 80)
    doc = Document(doc_path)
    ir = process_doc._build_ir_document(doc)
    
    print(f"Total blocks: {len(ir.get('blocks', []))}\n")
    print("=" * 80)
    print("DOCUMENT CONTENT WITH ALL FORMATTING:")
    print("=" * 80)
    print()
    
    for i, block in enumerate(ir.get('blocks', [])):
        if block.get('type') == 'paragraph':
            runs = block.get('runs', [])
            text = ''.join([r.get('text', '') for r in runs]).strip()
            if text:
                # Extract ALL formatting
                has_bold = any(r.get('bold', False) for r in runs)
                has_underline = any(r.get('underline', False) for r in runs)
                has_italic = any(r.get('italic', False) for r in runs)
                
                # Get font size (only if non-default)
                font_size = None
                for r in runs:
                    if r.get('fontSizePt') and r.get('fontSizePt') != 11.0:
                        font_size = r.get('fontSizePt')
                        break
                
                # Get alignment (only if non-left)
                alignment = block.get('align', 'left')
                
                # Build formatting list
                fmt = []
                if has_bold:
                    fmt.append('BOLD')
                if has_underline:
                    fmt.append('UNDERLINE')
                if has_italic:
                    fmt.append('ITALIC')
                if font_size:
                    fmt.append(f'FONT_SIZE_{int(font_size)}pt')
                if alignment and alignment != 'left':
                    fmt.append(f'ALIGN_{alignment.upper()}')
                
                fmt_str = f" [{', '.join(fmt)}]" if fmt else ""
                
                try:
                    print(f"{i+1:3d}: {text[:500]}{fmt_str}")
                except UnicodeEncodeError:
                    print(f"{i+1:3d}: {text[:500].encode('ascii', 'ignore').decode('ascii')}{fmt_str}")
                    
        elif block.get('type') == 'table':
            rows = block.get('rows', [])
            print(f"{i+1:3d}: TABLE with {len(rows)} rows")
            
            # Show table content with formatting
            # Table cells contain 'content' which is an array of paragraph IRs
            for row_idx, row in enumerate(rows[:10]):  # Show first 10 rows
                cells = row.get('cells', [])
                for cell_idx, cell in enumerate(cells[:5]):  # Show first 5 cells
                    cell_content = cell.get('content', [])
                    
                    # Process each paragraph in the cell
                    for para_content in cell_content:
                        if para_content.get('type') == 'paragraph':
                            cell_runs = para_content.get('runs', [])
                            cell_text = ''.join([r.get('text', '') for r in cell_runs]).strip()
                            if cell_text:
                                # Check cell formatting
                                cell_fmt = []
                                if any(r.get('bold', False) for r in cell_runs):
                                    cell_fmt.append('BOLD')
                                if any(r.get('underline', False) for r in cell_runs):
                                    cell_fmt.append('UNDERLINE')
                                
                                # Check font size in table cells
                                cell_font_size = None
                                for r in cell_runs:
                                    if r.get('fontSizePt') and r.get('fontSizePt') != 11.0:
                                        cell_font_size = r.get('fontSizePt')
                                        break
                                if cell_font_size:
                                    cell_fmt.append(f'FONT_SIZE_{int(cell_font_size)}pt')
                                
                                cell_fmt_str = f" [{', '.join(cell_fmt)}]" if cell_fmt else ""
                                try:
                                    print(f"     Row {row_idx}, Cell {cell_idx}: {cell_text[:200]}{cell_fmt_str}")
                                except UnicodeEncodeError:
                                    print(f"     Row {row_idx}, Cell {cell_idx}: {cell_text[:200].encode('ascii', 'ignore').decode('ascii')}{cell_fmt_str}")
            print()

if __name__ == '__main__':
    main()
