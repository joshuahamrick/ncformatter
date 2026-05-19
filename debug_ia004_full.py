"""Show full formatted IR for IA004."""
import base64, json, urllib.request, os, importlib.util

SITE = "https://ncformatter.vercel.app"
DOCX = r"C:\Users\jhamrick\Downloads\IA004 - FHA Coverage Term - FUB - V1.0 (1).docx"

with open(DOCX, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")

data = json.dumps({"fileData": b64, "fileName": "IA004.docx"}).encode("utf-8")
req = urllib.request.Request(f"{SITE}/api/process-doc", data=data, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as resp:
    result = json.loads(resp.read().decode("utf-8"))

ir = result["ir"]
spec = importlib.util.spec_from_file_location("gen_template", os.path.join("api", "generate-template.py"))
gt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gt)

formatted_ir = gt.format_ir_for_prompt(ir)
print("FULL FORMATTED IR FOR IA004:")
print(formatted_ir)

# Also show raw table blocks
print("\n\n=== RAW TABLE BLOCKS ===")
blocks = ir.get("blocks", [])
for i, b in enumerate(blocks):
    if b.get("type") == "table":
        rows = b.get("rows", [])
        print(f"\nBlock {i}: TABLE with {len(rows)} rows")
        for j, row in enumerate(rows):
            cells = row.get("cells", [])
            cell_texts = []
            for c in cells:
                ct = "".join(r.get("text", "") for r in c.get("runs", []))
                cell_texts.append(ct[:100])
            print(f"  Row {j}: {' | '.join(cell_texts)}")
