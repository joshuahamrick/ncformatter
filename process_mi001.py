#!/usr/bin/env python3
"""
Process MI001 document locally
"""
import sys
import os
import json
import importlib.util

# Load process_doc module
spec = importlib.util.spec_from_file_location("process_doc", r"c:\Users\jhamrick\Desktop\NcFormatter\api\process-doc.py")
process_doc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_doc)

# Load generate_template module
spec2 = importlib.util.spec_from_file_location("generate_template", r"c:\Users\jhamrick\Desktop\NcFormatter\api\generate-template.py")
generate_template = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(generate_template)

# Path to MI001
doc_path = r"C:\Users\jhamrick\Downloads\MI001 - PMI Brrwr Can Req Inquiry -Keesler - V3.0.docx"

if not os.path.exists(doc_path):
    print(f"[ERROR] Document not found: {doc_path}")
    sys.exit(1)

print("Reading document...")
with open(doc_path, 'rb') as f:
    file_content = f.read()

print("Processing document (extracting IR)...")
# Extract IR
from io import BytesIO
from docx import Document

doc = Document(BytesIO(file_content))
ir_blocks = process_doc._build_ir_document(doc)

print(f"Type of ir_blocks: {type(ir_blocks)}")
print(f"ir_blocks keys: {ir_blocks.keys() if isinstance(ir_blocks, dict) else 'N/A'}")

# If it's already a dict with 'blocks', use it directly
if isinstance(ir_blocks, dict) and 'blocks' in ir_blocks:
    ir_data = ir_blocks
else:
    ir_data = {'blocks': ir_blocks}

blocks_list = ir_data.get('blocks', [])
print(f"Extracted {len(blocks_list)} blocks")

print("\nGenerating template with Claude...")
# Load API key from .env
env_path = r"c:\Users\jhamrick\Desktop\NcFormatter\.env"
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            if line.startswith('ANTHROPIC_API_KEY'):
                api_key = line.split('=')[1].strip().strip('"')
                os.environ['ANTHROPIC_API_KEY'] = api_key
                break

api_key = os.environ.get('ANTHROPIC_API_KEY')
if not api_key:
    print("[ERROR] ANTHROPIC_API_KEY not set")
    sys.exit(1)

print(f"API key found: {api_key[:10]}...")

# Initialize Anthropic client
import anthropic
client = anthropic.Anthropic(api_key=api_key)

# Load few-shot examples
few_shot_examples = generate_template.load_few_shot_examples()
print(f"Loaded {len(few_shot_examples)} examples")

# Build prompt
system_prompt, user_message, few_shot_text = generate_template.build_prompt(ir_data, few_shot_examples, None)
print("Prompt built")

# Call Claude API
print("Calling Claude API...")
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=16000,
    system=system_prompt,
    messages=[{"role": "user", "content": user_message}]
)

html = response.content[0].text
html = generate_template.normalize_html(html)

print("\n" + "="*80)
print("GENERATED HTML:")
print("="*80)
print(html)
print("="*80)

# Save to file
output_path = r"c:\Users\jhamrick\Desktop\NcFormatter\MI001-output.html"
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\n[OK] Saved to: {output_path}")
