#!/usr/bin/env python3
"""Generate DS033 formatted HTML using OpenAI"""

import sys
import os
import json
import importlib.util
from docx import Document

# Paths
docx_path = "formatter examples/DS033/DS033_Payment Refusal-Electronic.docx"
output_path = "formatter examples/DS033/DS033-formatted.html"

if not os.path.exists(docx_path):
    print(f"Error: File not found: {docx_path}")
    sys.exit(1)

# Load process-doc module to build IR
process_doc_path = "api/process-doc.py"
spec = importlib.util.spec_from_file_location("process_doc", process_doc_path)
process_doc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_doc)

# Load generate-template module
gen_template_path = "api/generate-template.py"
spec2 = importlib.util.spec_from_file_location("generate_template", gen_template_path)
generate_template = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(generate_template)

print(f"Processing {docx_path}...")

# Build IR from document
doc = Document(docx_path)
ir = process_doc._build_ir_document(doc)

print(f"Document has {len(ir.get('blocks', []))} blocks")

# Load few-shot examples
few_shot_examples = generate_template.load_few_shot_examples()
print(f"Loaded {len(few_shot_examples)} few-shot examples")

# Build prompt
system_prompt, user_message, few_shot_text = generate_template.build_prompt(ir, few_shot_examples)

print("\n=== CALLING OPENAI ===")

# Check for OpenAI API key
import openai
api_key = os.environ.get('OPENAI_API_KEY')
if not api_key:
    print("ERROR: OPENAI_API_KEY environment variable not set")
    print("Please set it with: set OPENAI_API_KEY=your-key-here")
    sys.exit(1)

# Initialize OpenAI client
client = openai.OpenAI(api_key=api_key)

# Combine system prompt with few-shot examples
full_system_prompt = system_prompt + "\n\n" + few_shot_text

# Call OpenAI
try:
    model_name = "gpt-4o"
    print(f"Using model: {model_name}")
    
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": full_system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0,
        max_tokens=4000
    )
    
    html = response.choices[0].message.content.strip()
    
    # Remove markdown code blocks if present
    if html.startswith('```html'):
        html = html.replace('```html', '').replace('```', '').strip()
    elif html.startswith('```'):
        html = html.replace('```', '').strip()
    
    # Normalize HTML
    html = generate_template.normalize_html(html)
    
    # Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n=== SUCCESS ===")
    print(f"Output written to: {output_path}")
    print(f"HTML length: {len(html)} chars")
    
except Exception as e:
    print(f"\n=== ERROR ===")
    print(f"OpenAI API error: {str(e)}")
    sys.exit(1)
