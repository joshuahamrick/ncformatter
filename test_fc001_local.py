"""Full pipeline test for FC001"""
import sys, os, importlib.util
from io import BytesIO
from docx import Document

BASE = os.path.dirname(__file__)

pd_spec = importlib.util.spec_from_file_location("process_doc", os.path.join(BASE, 'api', 'process-doc.py'))
process_doc = importlib.util.module_from_spec(pd_spec)
pd_spec.loader.exec_module(process_doc)

gt_spec = importlib.util.spec_from_file_location("generate_template", os.path.join(BASE, 'api', 'generate-template.py'))
gen = importlib.util.module_from_spec(gt_spec)
gt_spec.loader.exec_module(gen)

env_path = os.path.join(BASE, '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith('ANTHROPIC_API_KEY'):
                os.environ['ANTHROPIC_API_KEY'] = line.split('=', 1)[1].strip().strip('"')
                break

docx_path = os.path.join(BASE, 'formatter examples', 'FC001', 'FC001 - Notice of FCL Brw Options - EHL - V2.0.docx')
with open(docx_path, 'rb') as f:
    content = f.read()

doc = Document(BytesIO(content))
ir = process_doc._build_ir_document(doc)
print(f"Blocks: {len(ir.get('blocks',[]))}")

ir_text = gen.format_ir_for_prompt(ir)
print(f"IR text: {len(ir_text)} chars")
if ir_text:
    print("=== First 3000 chars of IR ===")
    print(ir_text[:3000])
    print("\n=== Last 2000 chars of IR ===")
    print(ir_text[-2000:])
else:
    print("ERROR: IR text is empty!")
    sys.exit(1)

few_shot = gen.load_few_shot_examples()
print(f"\nFew-shot: {len(few_shot)} examples ({[e['name'] for e in few_shot]})")
system_prompt, user_message, few_shot_text = gen.build_prompt(ir, few_shot)
full_system = system_prompt + "\n\n" + few_shot_text

import anthropic
api_key = os.environ.get('ANTHROPIC_API_KEY')
if not api_key:
    print("ERROR: No API key"); sys.exit(1)
print(f"\nCalling Claude (key: {api_key[:10]}...)...")
client = anthropic.Anthropic(api_key=api_key)
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=16000,
    system=full_system,
    messages=[{"role": "user", "content": user_message}],
    temperature=0
)
html = gen.normalize_html(response.content[0].text)
out_path = os.path.join(BASE, 'fc001_output.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)
print("=== OUTPUT ===")
print(html)
print(f"\nWritten to {out_path}")
