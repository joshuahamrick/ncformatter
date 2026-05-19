import os
from io import BytesIO
from docx import Document
import importlib.util

BASE = r'c:\Users\jhamrick\Desktop\NcFormatter'

with open(os.path.join(BASE, 'api', 'generate-template.py'), encoding='utf-8') as f:
    src = f.read()

# Add print right before the total_blocks line
target = 'total_blocks = len(formatted)'
replacement = 'print(f"[AFTER LOOP] formatted has {len(formatted)} items")\n\t' + target
debug_src = src.replace(target, replacement)
print(f'Found target: {target in src}')

ns = {}
exec(compile(debug_src, 'gen', 'exec'), ns)
gen_fn = ns['format_ir_for_prompt']

pd_spec = importlib.util.spec_from_file_location('pd', os.path.join(BASE, 'api', 'process-doc.py'))
pd = importlib.util.module_from_spec(pd_spec)
pd_spec.loader.exec_module(pd)

with open(r'C:\Users\jhamrick\Downloads\CL008 - Loss Mit Consult 44 Day - Commerce - V1.0 (1).docx', 'rb') as f:
    content = f.read()
doc = Document(BytesIO(content))
ir = pd._build_ir_document(doc)
ir['blocks'] = ir['blocks'][:10]
result = gen_fn(ir)
print(f'Result: {len(result)} chars')
