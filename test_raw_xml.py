"""Read raw XML from the .docx zip file"""
import zipfile
import xml.etree.ElementTree as ET

doc_path = r"C:\Users\jhamrick\Downloads\CA030 - CA Initial Contact - VCI - V1.0.docx"

# .docx files are zip files
with zipfile.ZipFile(doc_path, 'r') as zip_ref:
    # List all files in the zip
    print("FILES IN .DOCX ZIP:")
    for name in zip_ref.namelist():
        print(f"  {name}")
    
    print("\n" + "="*80)
    print("READING word/document.xml:")
    print("="*80 + "\n")
    
    # Read the main document XML
    with zip_ref.open('word/document.xml') as xml_file:
        content = xml_file.read().decode('utf-8')
        
        # Search for key phrases
        key_phrases = ["Loan Number", "M594", "M567", "CompanyLongName", 
                      "CompanyReturnAddr", "FEDERAL LAW", "RE:"]
        
        print("SEARCHING FOR KEY PHRASES IN RAW XML:")
        for phrase in key_phrases:
            if phrase in content:
                print(f"\nFOUND: {phrase}")
                # Get context
                idx = content.find(phrase)
                start = max(0, idx - 200)
                end = min(len(content), idx + 300)
                print(f"Context: ...{content[start:end]}...")
            else:
                print(f"\nNOT FOUND: {phrase}")
        
        # Write full XML to file for inspection
        with open('ca030_document_xml.txt', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("\n" + "="*80)
        print("Full XML saved to: ca030_document_xml.txt")
        print(f"Total XML length: {len(content)} characters")
        print("="*80)
        
        # Count paragraphs in XML
        import re
        para_count = len(re.findall(r'<w:p\s', content))
        text_count = len(re.findall(r'<w:t>', content))
        print(f"\nParagraph tags (<w:p>): {para_count}")
        print(f"Text tags (<w:t>): {text_count}")
