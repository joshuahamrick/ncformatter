#!/usr/bin/env python3
"""
Format CT302 document directly
"""
import sys
import os
import json
import importlib.util

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

def format_ct302():
    """Format CT302 document"""
    doc_path = os.path.join(os.path.dirname(__file__), '..', 'CT302 - CT Compliance Mailing - MSF - V1.0 (1).docx')
    
    if not os.path.exists(doc_path):
        print(f"Error: Document not found at {doc_path}")
        return
    
    print(f"Loading document: {doc_path}")
    doc = Document(doc_path)
    
    print("Extracting IR...")
    ir = process_doc._build_ir_document(doc)
    
    print(f"IR extracted: {len(ir.get('blocks', []))} content blocks")
    
    # Generate HTML template
    print("Generating HTML template...")
    
    # Format IR for prompt
    ir_content = generate_template.format_ir_for_prompt(ir)
    
    # Load system prompt and few-shot examples
    system_prompt = generate_template.load_system_prompt()
    few_shot_examples = generate_template.load_few_shot_examples()
    
    # Build user message
    user_message = f"""Convert the following Word document Intermediate Representation (IR) into a formatted HTML template.

{ir_content}

Generate the complete HTML template following all the rules and examples provided."""
    
    # Call OpenAI API via HTTP
    import urllib.request
    import urllib.parse
    import json as json_lib
    
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Please set the OPENAI_API_KEY environment variable and try again")
        return
    
    # Estimate tokens
    system_tokens = len(system_prompt.split()) * 1.3
    user_tokens = len(user_message.split()) * 1.3
    few_shot_tokens = sum(len(ex['content'].split()) * 1.3 for ex in few_shot_examples)
    total_input_tokens = system_tokens + user_tokens + few_shot_tokens
    
    print(f"Estimated input tokens: {int(total_input_tokens)}")
    
    # Determine max_tokens based on document size
    num_blocks = len(ir.get('blocks', []))
    if num_blocks > 500:
        max_tokens = 16000
    elif num_blocks > 200:
        max_tokens = 12000
    else:
        max_tokens = 8000
    
    print(f"Using max_tokens: {max_tokens}")
    
    # Make API call
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Add few-shot examples
    for example in few_shot_examples:
        messages.append({"role": "user", "content": example['content']})
        messages.append({"role": "assistant", "content": example['response']})
    
    # Add actual request
    messages.append({"role": "user", "content": user_message})
    
    try:
        # Call OpenAI API via HTTP
        url = "https://api.openai.com/v1/chat/completions"
        
        payload = {
            "model": "gpt-4o",
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens
        }
        
        data = json_lib.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )
        
        print("Calling OpenAI API...")
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json_lib.loads(response.read().decode('utf-8'))
            html = result['choices'][0]['message']['content'].strip()
        
        # Normalize HTML
        html = generate_template.normalize_html(html)
        
        # Save to output directory
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'formatter examples', 'CT302')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, 'CT302-formatted.html')
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"\nHTML template generated successfully!")
        print(f"Saved to: {output_path}")
        print(f"Template length: {len(html)} characters")
        
        return html
        
    except Exception as e:
        print(f"Error generating template: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    format_ct302()

