#!/usr/bin/env python3
"""Test script to process SR121 document and compare with expected output"""
import sys
import os

# Add api directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

from process_word import process_word_document

def test_sr121():
    """Process SR121 document and compare output"""
    
    # Read the Word document
    doc_path = 'formatter examples/SR121/SR121 - Chase Goodbye Letter  - UMH - V1.0.docx'
    with open(doc_path, 'rb') as f:
        file_bytes = f.read()
    
    # Process the document
    print("Processing SR121 document...")
    result = process_word_document(file_bytes, 'SR121 - Chase Goodbye Letter  - UMH - V1.0.docx')
    
    if not result['success']:
        print(f"ERROR: {result['error']}")
        return
    
    # Read expected output
    expected_path = 'formatter examples/SR121/SR121-formatted.html'
    with open(expected_path, 'r', encoding='utf-8') as f:
        expected_html = f.read()
    
    # Get actual output
    actual_html = result['formattedHtml']
    
    # Write actual output for comparison
    actual_path = 'formatter examples/SR121/SR121-actual-output.html'
    with open(actual_path, 'w', encoding='utf-8') as f:
        f.write(actual_html)
    
    print(f"\n✓ Processed document successfully")
    print(f"✓ Output written to: {actual_path}")
    print(f"\nComparing with expected output...")
    
    # Compare key sections
    expected_lines = expected_html.split('\n')
    actual_lines = actual_html.split('\n')
    
    print(f"\nExpected: {len(expected_lines)} lines")
    print(f"Actual: {len(actual_lines)} lines")
    
    # Check key differences
    issues = []
    
    # Check header
    if '{Insert(UHM Header)}' in expected_html and '{Insert(UHM Header)}' not in actual_html:
        issues.append("Missing UHM Header")
    
    # Check label-value pairs table
    if '<table width="100%"><tbody><tr>' in expected_html:
        expected_tables = expected_html.count('<table width="100%"><tbody><tr>')
        actual_tables = actual_html.count('<table width="100%"><tbody><tr>')
        if expected_tables > actual_tables:
            issues.append(f"Missing tables: expected {expected_tables}, got {actual_tables}")
    
    # Check PROPERTY compression
    if '{Compress({[M567]}|{[M583]}|{[M568]})}' in expected_html:
        if '{Compress({[M567]}|{[M583]}|{[M568]})}' not in actual_html:
            issues.append("PROPERTY not compressed correctly")
    
    # Check salutation
    if 'Dear {[Salutation]},' in expected_html:
        if 'Dear {[Salutation]},' not in actual_html:
            issues.append("Salutation not converted correctly")
    
    # Check conditional logic removal
    if '{[M838]}' in actual_html or '{[M956]}' in actual_html or '{[M928]}' in actual_html or '{[M929]}' in actual_html:
        issues.append("Conditional logic sections still present")
    
    if issues:
        print("\n❌ Issues found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n✓ No major issues detected!")
    
    return actual_html, expected_html

if __name__ == '__main__':
    test_sr121()

