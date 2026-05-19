"""Debug CL008 IR formatting pipeline locally."""
import base64, json, urllib.request, sys, os, re, importlib.util

SITE = "https://ncformatter.vercel.app"
DOCX = r"C:\Users\jhamrick\Downloads\CL008 - Loss Mit Consult 44 Day - Commerce - V1.0 (2).docx"

with open(DOCX, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")

data = json.dumps({"fileData": b64, "fileName": "CL008.docx"}).encode("utf-8")
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
        print(f"  Line {i}: {line[:250]}")

print("\n--- Lines containing RE: or Property Address ---")
for i, line in enumerate(lines):
    if re.search(r'RE:|Property Address', line):
        print(f"  Line {i}: {line[:250]}")

print("\n--- Lines containing Compress ---")
for i, line in enumerate(lines):
    if 'Compress' in line:
        print(f"  Line {i}: {line[:250]}")

print("\n--- Lines containing Loan Number ---")
for i, line in enumerate(lines):
    if 'Loan Number' in line:
        print(f"  Line {i}: {line[:250]}")

print("\n--- Lines containing 'bullet' or 'LIST_ITEM' (first 10) ---")
count = 0
for i, line in enumerate(lines):
    if 'LIST_ITEM' in line or 'bullet' in line.lower():
        print(f"  Line {i}: {line[:200]}")
        count += 1
        if count >= 10:
            break
