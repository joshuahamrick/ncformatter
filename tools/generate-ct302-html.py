#!/usr/bin/env python3
"""Generate HTML template for CT302 document"""
import sys
import os
import json
import importlib.util
import urllib.request
import urllib.parse

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
    """Generate HTML template for CT302"""
    doc_path = os.path.join(os.path.dirname(__file__), '..', 'CT302 - CT Compliance Mailing - MSF - V1.0 (1).docx')
    
    print(f"Loading document: {doc_path}")
    doc = Document(doc_path)
    
    print("Extracting IR...")
    ir = process_doc._build_ir_document(doc)
    print(f"IR extracted: {len(ir.get('blocks', []))} content blocks")
    
    # Format IR for prompt
    print("Formatting IR for prompt...")
    ir_content = generate_template.format_ir_for_prompt(ir)
    
    # Load system prompt and few-shot examples
    print("Loading prompts...")
    system_prompt = generate_template.load_system_prompt()
    few_shot_examples = generate_template.load_few_shot_examples()
    
    # Build user message using the same format as the API
    few_shot_text = "\n## CRITICAL: Example Outputs - Study These Carefully\n\n"
    few_shot_text += "These examples show the EXACT formatting structure you must follow:\n\n"
    
    for idx, ex in enumerate(few_shot_examples):
        few_shot_text += f"### Example {idx + 1}: {ex['name']}\n```html\n{ex['html']}\n```\n\n"
    
    user_message = """You are converting a Word document into a formatted HTML template. Your task is to:

1. Extract the actual document content (ignore variable definitions and instructions)
2. Format it as HTML following the EXACT structure and style shown in the examples
3. Use proper newlines - each HTML element on its own line
4. Include ALL required elements: header, date, mailing address, property address table, salutation, content
5. Wrap conditional content in {If()}...{End If} blocks
6. Match spacing from the source document

CRITICAL RULES:
- Extract ONLY the actual document text content
- IGNORE variable definitions like "[H002] Company Address Line 1" - those are metadata
- IGNORE conditional logic text like "(or if [H581] and/or [H582] present)" - do NOT include this
- IGNORE instructions like "If [M065] ≥ 'July 29, 1999' then print:" - convert to proper {If()} syntax
- NEVER include conditional salutation logic - ALWAYS use <div>Dear {[Salutation]},</div>
- ALWAYS include property address table after mailing address
- ALWAYS format with newlines - each tag on its own line

Document Content:
""" + ir_content + "\n\n" + few_shot_text + """

CRITICAL: You MUST format the HTML with proper newlines. Each HTML element MUST be on its own line.

Generate the complete HTML template following these EXACT rules."""
    
    # Get API key
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set")
        print("Please set it and try again:")
        print("  $env:OPENAI_API_KEY='your-key-here'")
        return None
    
    # Build messages
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Add few-shot examples - format them properly
    # The examples are just HTML, so we need to create proper user/assistant pairs
    # For now, skip few-shot examples in the direct script to simplify
    # The system prompt contains the formatting rules
    
    # Add actual request
    messages.append({"role": "user", "content": user_message})
    
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
            
            # Normalize HTML
            html = generate_template.normalize_html(html)
            
            # Save to output directory
            output_dir = os.path.join(os.path.dirname(__file__), '..', 'formatter examples', 'CT302')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, 'CT302-formatted.html')
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)
            
            print(f"\n✓ HTML template generated successfully!")
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

