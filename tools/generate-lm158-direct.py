#!/usr/bin/env python3
"""Generate HTML template for LM158 using the API endpoint"""
import sys
import os
import json
import base64
import importlib.util
from docx import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load process-doc module
process_doc_path = os.path.join(os.path.dirname(__file__), '..', 'api', 'process-doc.py')
spec = importlib.util.spec_from_file_location("process_doc", process_doc_path)
process_doc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_doc)

def generate_html():
    """Generate HTML template for LM158"""
    doc_path = os.path.join(os.path.dirname(__file__), '..', 'LM158 - HUD FB Disaster Off Ltr - Keesler - V2.0.docx')
    
    if not os.path.exists(doc_path):
        print(f"ERROR: Document not found at {doc_path}")
        return None
    
    print(f"Step 1: Extracting IR from document...")
    try:
        doc = Document(doc_path)
        ir = process_doc._build_ir_document(doc)
        print(f"IR extracted: {len(ir.get('blocks', []))} blocks")
    except Exception as e:
        print(f"ERROR processing document: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # Try to use the deployed API endpoint
    import urllib.request
    import urllib.parse
    
    print("Step 2: Calling generate-template API endpoint...")
    
    try:
        # Prepare the request
        payload = {
            'ir': ir
        }
        
        data = json.dumps(payload).encode('utf-8')
        
        # Try localhost first, then vercel
        for url in ['http://localhost:3000/api/generate-template', 'https://ncformatter.vercel.app/api/generate-template']:
            try:
                print(f"Trying {url}...")
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={
                        'Content-Type': 'application/json'
                    }
                )
                
                with urllib.request.urlopen(req, timeout=60) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    if result.get('success'):
                        html = result.get('html', '')
                        
                        # Save to output directory
                        output_dir = os.path.join(os.path.dirname(__file__), '..', 'formatter examples', 'LM158')
                        os.makedirs(output_dir, exist_ok=True)
                        output_path = os.path.join(output_dir, 'LM158-formatted.html')
                        
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(html)
                        
                        print(f"\n✓ HTML template generated successfully!")
                        print(f"  Saved to: {output_path}")
                        print(f"  Template length: {len(html)} characters")
                        return html
                    else:
                        print(f"API returned error: {result.get('error')}")
                        continue
            except Exception as e:
                print(f"Failed to connect to {url}: {e}")
                continue
        
        print("ERROR: Could not connect to API endpoint. Please use the web interface or set OPENAI_API_KEY.")
        return None
        
    except Exception as e:
        print(f"ERROR generating template: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    generate_html()
