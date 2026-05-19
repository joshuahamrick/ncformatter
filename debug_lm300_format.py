"""Debug LM300 IR formatting pipeline locally."""
import base64, json, urllib.request, sys, os, re, importlib.util

SITE = "https://ncformatter.vercel.app"
DOCX = r"C:\Users\jhamrick\Downloads\LM300_VP_HUD Pre-Foreclosure Sale_V1 (1).docx"

with open(DOCX, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")

data = json.dumps({"fileData": b64, "fileName": "LM300.docx"}).encode("utf-8")
req = urllib.request.Request(f"{SITE}/api/process-doc", data=data, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as resp:
    result = json.loads(resp.read().decode("utf-8"))

ir = result["ir"]
spec = importlib.util.spec_from_file_location("gen_template", os.path.join("api", "generate-template.py"))
gt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gt)

formatted_ir = gt.format_ir_for_prompt(ir)
lines = formatted_ir.split("\n")
print(f"Total formatted lines: {len(lines)}")

print("\n--- Lines containing M567, M583, M568 ---")
for i, line in enumerate(lines):
    if re.search(r'M567|M583|M568', line):
        print(f"  Line {i}: {line[:200]}")

print("\n--- Lines containing Compress ---")
for i, line in enumerate(lines):
    if 'Compress' in line:
        print(f"  Line {i}: {line[:200]}")
