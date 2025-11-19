#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test script to process SR121 document locally and compare output"""

import sys
import os
import io

# Add the api directory to the path
sys.path.insert(0, os.path.dirname(__file__))

try:
    # Import the function from the api module
    # The file is process-word.py, so we need to import it as a module
    import importlib.util
    api_path = os.path.join(os.path.dirname(__file__), 'api', 'process-word.py')
    spec = importlib.util.spec_from_file_location("process_word", api_path)
    process_word_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(process_word_module)
    process_word_document = process_word_module.process_word_document
    
    # Read the Word document
    docx_path = r'formatter examples\SR121\SR121 - Chase Goodbye Letter  - UMH - V1.0.docx'
    
    print(f"Reading document: {docx_path}")
    with open(docx_path, 'rb') as f:
        file_bytes = f.read()
    
    print("Processing document...")
    result = process_word_document(file_bytes, 'SR121 - Chase Goodbye Letter - UMH - V1.0.docx')
    
    if result['success']:
        formatted_html = result['formattedHtml']
        
        # Write output to file for comparison
        output_path = r'formatter examples\SR121\SR121-test-output.html'
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(formatted_html)
        
        print(f"\n[OK] Processing successful!")
        print(f"Output written to: {output_path}")
        print(f"\nOutput length: {len(formatted_html)} characters")
        print(f"\nFirst 500 characters of output:")
        print("-" * 80)
        print(formatted_html[:500])
        print("-" * 80)
        
        # Check for key issues
        issues = []
        if '{[tagHeader]}' in formatted_html and '{Insert(UHM Header)}' not in formatted_html:
            issues.append("[X] Header still shows {[tagHeader]} instead of {Insert(UHM Header)}")
        if '{[M838]}' in formatted_html or 'PLSID' in formatted_html:
            issues.append("[X] M838/PLSID still present")
        if '{[M956]}' in formatted_html or '{[M928]}' in formatted_html or '{[M929]}' in formatted_html:
            issues.append("[X] Conditional logic sections (M956, M928, M929) still present")
        if 'SII Confirmed' in formatted_html:
            issues.append("[X] SII Confirmed still present")
        if 'SUBJECT:' in formatted_html:
            # Check if SUBJECT is in a table
            subj_pos = formatted_html.find('SUBJECT:')
            if subj_pos > 0:
                # Look backwards for table tag
                before_subj = formatted_html[max(0, subj_pos-500):subj_pos]
                if '<table' not in before_subj:
                    issues.append("[X] SUBJECT/UHM/JPMORGAN not converted to table")
        if 'Dear {[M558]} and {[M559]}' in formatted_html:
            issues.append("[X] Salutation still shows {[M558]} and {[M559]} instead of {[Salutation]}")
        if '1 / 2 /202' in formatted_html or '12 /3 1 /202' in formatted_html:
            issues.append("[X] Dates still have spaces")
        
        if issues:
            print("\nISSUES FOUND:")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("\n[OK] No obvious issues detected!")
            
    else:
        print(f"\n[X] Processing failed: {result.get('error', 'Unknown error')}")
        
except ImportError as e:
    print(f"[X] Import error: {e}")
    print("\nMake sure python-docx is installed:")
    print("  pip install python-docx")
except FileNotFoundError as e:
    print(f"[X] File not found: {e}")
except Exception as e:
    print(f"[X] Error: {e}")
    import traceback
    traceback.print_exc()

