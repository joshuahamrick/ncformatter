import json, sys, importlib.util
sys.path.insert(0, '.')

with open(r'formatter examples\ES027\ES027-ir.json') as f:
    ir = json.load(f)

spec = importlib.util.spec_from_file_location('gen_template', 'api/generate-template.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

result = mod.format_ir_for_prompt(ir)
lines = result.split('\n')
print(f"Total output lines: {len(lines)}")
print()
for l in lines:
    print(l)
