#!/usr/bin/env python3
"""Generate HTML template for LM156 document"""
import sys
import os
import json
import importlib.util
import urllib.request

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from docx import Document

# Load process-doc module
process_doc_path = os.path.join(os.path.dirname(__file__), '..', 'api', 'process-doc.py')
spec = importlib.util.spec_from_file_location("process_doc", process_doc_path)
process_doc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_doc)

# Load generate-template module  
generate_template_path = os.path.join(os.path.dirname(__file__), '..', 'api', 'generate-template.py')
spec2 = importlib.util.spec_from_file_location("generate_template", generate_template_path)
generate_template = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(generate_template)

def generate_html():
    """Generate HTML template for LM156"""
    doc_path = os.path.join(os.path.dirname(__file__), '..', 'LM156 - GSE FB Plan Ofr Ltr - Keesler - V2.0.docx')
    
    if not os.path.exists(doc_path):
        print(f"ERROR: Document not found at {doc_path}")
        return None
    
    print(f"Loading document: {doc_path}")
    doc = Document(doc_path)
    
    print("Extracting IR...")
    ir = process_doc._build_ir_document(doc)
    print(f"IR extracted: {len(ir.get('blocks', []))} content blocks")
    
    # Load system prompt and few-shot examples
    print("Loading prompts...")
    system_prompt = generate_template.load_system_prompt()
    few_shot_examples = generate_template.load_few_shot_examples()
    
    # Build prompt using the same function as the API
    user_message = generate_template.build_prompt(ir, few_shot_examples)
    
    # Get API key
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set")
        print("Please set it and try again:")
        print("  $env:OPENAI_API_KEY='your-key-here' (PowerShell)")
        print("  set OPENAI_API_KEY=your-key-here (Command Prompt)")
        return None
    
    # Build messages
    full_system_prompt = system_prompt + "\n\n" + generate_template._format_few_shot_examples(few_shot_examples)
    
    messages = [
        {"role": "system", "content": full_system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    # Determine max_tokens
    num_blocks = len(ir.get('blocks', []))
    if num_blocks > 500:
        max_tokens = 16000
    elif num_blocks > 200:
        max_tokens = 12000
    else:
        max_tokens = 8000
    
    print(f"Calling OpenAI API (max_tokens: {max_tokens})...")
    
    # Call OpenAI API via HTTP
    url = "https://api.openai.com/v1/chat/completions"
    
    payload = {
        "model": "gpt-4o",
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens
    }
    
    data = json.dumps(payload).encode('utf-8')
    
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode('utf-8'))
            html = result['choices'][0]['message']['content'].strip()
            
            # Remove markdown code blocks if present
            if html.startswith('```html'):
                html = html.replace('```html', '').replace('```', '').strip()
            elif html.startswith('```'):
                html = html.replace('```', '').strip()
            
            # Normalize HTML
            html = generate_template.normalize_html(html)
            
            # Save to output directory
            output_dir = os.path.join(os.path.dirname(__file__), '..', 'formatter examples', 'LM156')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, 'LM156-formatted.html')
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)
            
            print(f"\nHTML template generated successfully!")
            print(f"  Saved to: {output_path}")
            print(f"  Template length: {len(html)} characters")
            
            return html
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"ERROR: API call failed with status {e.code}")
        print(f"Response: {error_body}")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    generate_html()

